"""Система машинного перевода EN -> RU: прямой (пословный) и трансферный.

Трансферный режим реализован в три этапа, как предписывает методика:
анализ (дерево зависимостей EN) -> трансфер (листья дерева заменяются
русскими переводами, структура связей сохраняется) -> синтез
(линеаризация уже русского дерева в порядке слов, характерном для RU).
Русское дерево — самостоятельный артефакт, оно возвращается в результате
перевода в поле `russian_sentences`.
"""
import spacy
from collections import Counter

import pymorphy3

from core.translators import SyntaxTagTranslator
from mt.mt_constants import EN_STOPWORDS, SKIP_POS
from mt.synthetic_tree import SyntheticSentence, SyntheticToken

# en_core_web_sm размечен по UD v2, где часть связей называется иначе,
# чем в актуальной UD (dobj -> obj и т.д.). Русское дерево строим сразу
# в современных метках, чтобы дальше работали и линеаризация, и таблица.
DEP_NORMALIZE = {
    'nsubjpass': 'nsubj:pass',
    'auxpass': 'aux:pass',
    'dobj': 'obj',
    'pobj': 'obl',
    'prep': 'obl',
    'dative': 'iobj',
    'agent': 'obl:agent',
    'relcl': 'acl:relcl',
}


class MTEngine:
    # Модификаторы, которые в русском идут ПЕРЕД головным словом
    _LEFT_MODS = ('det', 'amod', 'nummod', 'nummod:entity', 'compound',
                  'fixed', 'flat', 'poss', 'case', 'neg', 'expl',
                  'aux', 'aux:pass', 'auxpass')
    # Модификаторы, которые идут ПОСЛЕ головного слова
    _RIGHT_MODS = ('nmod', 'appos', 'acl', 'acl:relcl', 'advmod', 'obl',
                   'iobj', 'obj', 'dobj', 'pobj', 'ccomp', 'advcl', 'xcomp',
                   'compound:prt', 'obl:agent', 'agent', 'conj', 'parataxis',
                   'discourse', 'vocative', 'goeswith')
    _SUBJECT_DEPS = ('nsubj', 'nsubj:pass', 'nsubjpass', 'csubj')
    _ADVERB_DEPS = ('advmod',)

    def __init__(self, dict_manager):
        self.dict_manager = dict_manager
        self.tag_translator = SyntaxTagTranslator()
        self._nlp = None
        self._morph_ru = pymorphy3.MorphAnalyzer(lang='ru')

    def _load_nlp(self):
        if self._nlp is None:
            try:
                self._nlp = spacy.load("en_core_web_sm")
            except OSError:
                raise RuntimeError(
                    "Модель spaCy 'en_core_web_sm' не установлена. "
                    "Выполните: python -m spacy download en_core_web_sm"
                )
        return self._nlp

    # ------------------------------------------------------------------
    # Прямой перевод
    # ------------------------------------------------------------------
    def translate_direct(self, text: str, auto_fill: bool = True) -> dict:
        doc = self._load_nlp()(text)
        translation, all_tokens, unknown, skipped, rus_sents = \
            self._process_sentences(doc, auto_fill, linearize=False)
        result = self._finalize('direct', text, translation,
                                all_tokens, unknown, skipped)
        result['russian_sentences'] = rus_sents
        return result

    # ------------------------------------------------------------------
    # Трансферный перевод
    # ------------------------------------------------------------------
    def translate_transfer(self, text: str, auto_fill: bool = True) -> dict:
        doc = self._load_nlp()(text)
        translation, all_tokens, unknown, skipped, rus_sents = \
            self._process_sentences(doc, auto_fill, linearize=True)
        result = self._finalize('transfer', text, translation,
                                all_tokens, unknown, skipped)
        result['russian_sentences'] = rus_sents
        return result

    def _process_sentences(self, doc, auto_fill: bool, linearize: bool):
        """Общая часть обоих режимов.

        Для каждого предложения:
          1. перевод токенов (словарь + опционально Argos);
          2. построение русского дерева по английской структуре;
          3. склейка — либо линеаризация дерева (трансфер), либо
             сохранение исходного порядка (прямой перевод).

        Возвращает: (translation, all_tokens, unknown, skipped, rus_sents).
        """
        out_fragments, all_tokens, unknown_all = [], [], []
        russian_sentences = []
        skipped_total = 0

        for sent in doc.sents:
            words = [t for t in sent if not t.is_punct and not t.is_space]
            if not words:
                continue
            all_tokens.extend(words)
            ru_map, unknown, skipped = self._translate_tokens(words, auto_fill)
            skipped_total += skipped

            syn_sent = self._build_russian_sentence(sent, ru_map)
            russian_sentences.append(syn_sent)

            if linearize:
                ordered = self._linearize(syn_sent)
                out_fragments.append(' '.join(t.text for t in ordered))
            else:
                # прямой перевод — порядок исходный, но стоп-слова отброшены
                out_fragments.append(
                    ' '.join(ru_map.get(t.i, '')
                             for t in words if ru_map.get(t.i, ''))
                )
            unknown_all.extend(unknown)

        translation = '. '.join(out_fragments)
        return translation, all_tokens, unknown_all, skipped_total, russian_sentences

    def _translate_tokens(self, tokens, auto_fill: bool):
        ru_map, unknown, cache, skipped = {}, [], {}, 0
        for t in tokens:
            lemma = (t.lemma_ or t.text).lower()
            pos = t.pos_ or ''
            tag = t.tag_ or ''

            # AUX пропускаем, только если это НЕ модальный глагол.
            # Penn-тег MD помечает именно модальные (must, should, could),
            # у которых есть прямые русские аналоги. Обычные AUX (is, has, was)
            # в русском отдельным словом не выражаются — их пропускаем.
            is_skippable_aux = (pos == 'AUX' and tag != 'MD')

            if lemma in EN_STOPWORDS or pos in SKIP_POS or is_skippable_aux:
                ru_map[t.i] = ''
                skipped += 1
                continue
            key = (lemma, pos)
            if key not in cache:
                # tag — Penn-тег (NN, VBZ), morph — признаки spaCy
                # (Number=Sing|Person=3|Tense=Pres). Пишем их в словарь,
                # чтобы новые записи не оставались с пустой грамматикой.
                cache[key] = self.dict_manager.lookup_or_fetch(
                    lemma, pos,
                    form=t.text.lower(),
                    tag=t.tag_ or '',
                    morph=str(t.morph) if t.morph else '',
                    auto_fetch=auto_fill,
                )
            ru = cache[key]
            if ru:
                ru_map[t.i] = ru
            else:
                ru_map[t.i] = t.text
                unknown.append(t.text)
        return ru_map, unknown, skipped

    # ------------------------------------------------------------------
    # Трансфер: построение русского дерева и его синтез (линеаризация)
    # ------------------------------------------------------------------
    def _build_russian_sentence(self, en_sent, ru_map):
        """Строит русское дерево зависимостей по английскому.

        Структура (dep_/head) переносится из EN, листья заменяются на
        переводы, для каждого русского слова заполняются POS/морфология
        через pymorphy3.
        """
        new_tokens, idx_map = [], {}

        for en_tok in en_sent:
            if en_tok.is_punct or en_tok.is_space:
                continue
            ru_text = ru_map.get(en_tok.i, '')
            if not ru_text:
                continue  # пропущенное стоп-слово

            # морфология RU по словоформе
            p = self._morph_ru.parse(ru_text)[0]
            pos_ru = p.tag.POS or 'UNK'

            syn = SyntheticToken(
                index=len(new_tokens),
                text=ru_text,
                lemma=p.normal_form,
                pos=en_tok.pos_ or 'X',         # сохраняем EN UPOS
                pos_ru=pos_ru,
                tag=en_tok.tag_ or '',
                morph_ru=str(p.tag),
                dep=DEP_NORMALIZE.get(en_tok.dep_, en_tok.dep_ or ''),
            )
            new_tokens.append(syn)
            idx_map[en_tok.i] = syn

        # связываем головы (с перескоком через пропущенные стоп-слова)
        for en_tok in en_sent:
            if en_tok.i not in idx_map:
                continue
            syn = idx_map[en_tok.i]
            head = en_tok.head
            guard = 0
            while (head.i not in idx_map and head.i != head.head.i
                   and guard < len(en_sent)):
                head = head.head
                guard += 1
            if head.i in idx_map:
                syn.head = idx_map[head.i]
                syn.head.children.append(syn)
            else:
                syn.head = syn
                syn.dep_ = 'ROOT'

        if new_tokens and not any(t.dep_ == 'ROOT' for t in new_tokens):
            new_tokens[0].dep_ = 'ROOT'
            new_tokens[0].head = new_tokens[0]

        return SyntheticSentence(new_tokens)

    def _linearize(self, syn_sent):
        """Обход русского дерева в порядке, характерном для RU."""
        tokens = list(syn_sent)
        if not tokens:
            return []
        root = syn_sent.root
        if root is None:
            return tokens

        def leading_conjunction(tok):
            """Союз перед токеном: в UD «cc» — ребёнок головы координации."""
            head = tok.head
            if head is None:
                return None
            return next((c for c in head.children
                         if c.dep_ == 'cc' and c.i < tok.i), None)

        def emit(tok, out, seen):
            if tok.i in seen:
                return
            left = sorted((c for c in tok.children
                           if c.dep_ in self._LEFT_MODS and c.i != tok.i),
                          key=lambda x: x.i)
            for c in left:
                emit(c, out, seen)
            cc = leading_conjunction(tok)
            if cc is not None:
                emit(cc, out, seen)
            out.append(tok)
            seen.add(tok.i)
            right = sorted((c for c in tok.children
                            if c.dep_ in self._RIGHT_MODS and c.i != tok.i),
                           key=lambda x: x.i)
            for c in right:
                emit(c, out, seen)

        subjects = sorted((t for t in tokens if t.dep_ in self._SUBJECT_DEPS),
                          key=lambda x: x.i)
        adverbs = sorted((t for t in tokens
                          if t.dep_ in self._ADVERB_DEPS and t.head is root),
                         key=lambda x: x.i)

        ordered, seen = [], set()
        for t in subjects + adverbs + [root]:
            emit(t, ordered, seen)
        for t in sorted(tokens, key=lambda x: x.i):
            if t.i not in seen:
                emit(t, ordered, seen)
        return ordered

    # ------------------------------------------------------------------
    def _finalize(self, mode, source_text, translation, tokens, unknown, skipped=0):
        total = len(tokens)
        translated = total - len(unknown) - skipped
        return {
            'mode': mode,
            'translation': translation,
            'total_words': total,
            'translated_words': translated,
            'skipped_words': skipped,
            'coverage': round(translated / total * 100, 1) if total else 0.0,
            'unknown_words': unknown,
            'statistics': self._build_statistics(tokens),
        }

    def _build_statistics(self, tokens):
        counter, meta = Counter(), {}
        for t in tokens:
            lemma = (t.lemma_ or t.text).lower()
            pos = t.pos_ or ''
            key = (lemma, pos)
            counter[key] += 1
            if key not in meta:
                meta[key] = {
                    'form': t.text,
                    'tag': t.tag_ or '',
                    'morph': str(t.morph) if t.morph else '',
                    'translation': self.dict_manager.lookup_target(lemma, pos) or '',
                }
        rows = []
        for (lemma, pos), freq in counter.most_common():
            m = meta[(lemma, pos)]
            rows.append({
                'Частота': freq,
                'Словоформа': m['form'],
                'Лемма': lemma,
                'Перевод': m['translation'],
                'POS (EN)': pos,
                'POS (RU)': self.tag_translator.get_pos_rus(pos),
                'Tag': m['tag'],
                'Tag (RU)': self.tag_translator.get_tag_rus(m['tag']),
                'Морфология': m['morph'],
            })
        return rows

    # ------------------------------------------------------------------
    def export_txt(self, result) -> bytes:
        mode = ('прямой (пословный)' if result['mode'] == 'direct'
                else 'непрямой (трансферный)')
        unknown = result['unknown_words']
        lines = [
            "=" * 72,
            "ОТЧЁТ МАШИННОГО ПЕРЕВОДА (EN -> RU)",
            "=" * 72,
            "",
            f"Режим перевода:       {mode}",
            f"Всего слов:           {result['total_words']}",
            f"Переведено:           {result['translated_words']}",
            f"Пропущено (стоп-слова/артикли): {result.get('skipped_words', 0)}",
            f"Не найдено в словаре: {len(unknown)}",
            f"Покрытие:             {result.get('coverage', 0.0)}%",
        ]
        if unknown:
            unique = sorted(set(unknown))
            lines.append(f"Не переведённые слова ({len(unique)}):")
            for i in range(0, len(unique), 8):
                lines.append("    " + ", ".join(unique[i:i + 8]))
        lines += [
            "", "-" * 72, "ПЕРЕВОД:", "-" * 72,
            result['translation'], "",
            "-" * 72, "СЛОВА, УПОРЯДОЧЕННЫЕ ПО ЧАСТОТЕ:", "-" * 72,
        ]
        header = (f"{'Частота':>8} | {'Лемма':<20} | {'Перевод':<22} | "
                  f"{'POS':<7} | {'Морфология'}")
        lines.append(header)
        lines.append("-" * len(header))
        for r in result['statistics']:
            lines.append(
                f"{r['Частота']:>8} | {r['Лемма']:<20} | {r['Перевод']:<22} | "
                f"{r['POS (EN)']:<7} | {r['Морфология']}"
            )
        lines += ["", "-" * 72, "ГРАММАТИЧЕСКИЕ ХАРАКТЕРИСТИКИ СЛОВ:", "-" * 72]
        for r in result['statistics']:
            lines.append(
                f"{r['Лемма']:<20} {r['POS (EN)']:<7} {r['POS (RU)']:<20} "
                f"tag={r['Tag'] or '-'} ({r['Tag (RU)'] or '-'})"
            )
        return ('\n'.join(lines) + '\n').encode('utf-8')
