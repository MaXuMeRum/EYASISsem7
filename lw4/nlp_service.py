import re
import time
from collections import Counter

import spacy
import requests
from requests.adapters import HTTPAdapter
from graphviz import Digraph

try:
    from deep_translator import GoogleTranslator
    from deep_translator import google as _dt_google
except ImportError:
    GoogleTranslator = None
    _dt_google = None

# ============================================================
# ПУЛ СОЕДИНЕНИЙ ДЛЯ GOOGLE TRANSLATE
# ============================================================
# deep-translator использует requests.get(), который открывает
# новое TCP+TLS-соединение на каждый запрос. Google это банит (429).
# Решение: подменяем requests внутри deep_translator на сессию
# с переиспользованием соединений.
_session = requests.Session()
_adapter = HTTPAdapter(pool_connections=2, pool_maxsize=4)
_session.mount("https://", _adapter)
_session.mount("http://", _adapter)

if _dt_google is not None:
    class _SessionShim:
        @staticmethod
        def get(*args, **kwargs):
            kwargs.setdefault("timeout", 10)
            return _session.get(*args, **kwargs)

    _dt_google.requests = _SessionShim


POS_RU = {
    "NOUN": "существительное",
    "VERB": "глагол",
    "AUX": "вспомогательный глагол",
    "ADJ": "прилагательное",
    "ADV": "наречие",
    "PRON": "местоимение",
    "DET": "определитель/артикль",
    "ADP": "предлог",
    "CONJ": "союз",
    "CCONJ": "сочинительный союз",
    "SCONJ": "подчинительный союз",
    "NUM": "числительное",
    "PART": "частица",
    "INTJ": "междометие",
    "PROPN": "имя собственное",
    "PUNCT": "пунктуация",
    "SYM": "символ",
    "X": "другое/неопределённое",
    "SPACE": "пробел",
}


class NLPService:
    def __init__(self):
        # ========================================================
        # spaCy — для dependency parsing и лемматизации
        # ========================================================
        self.nlp = spacy.load("en_core_web_sm")
        self.nlp.max_length = 3_000_000

        # ========================================================
        # Constituent Tree через constituent-treelib
        # ========================================================
        # Требует transformers>=4.41.0 и benepar
        self.ct_nlp = None
        self.ctl_available = False
        try:
            from constituent_treelib import ConstituentTree, Language
            self.ct_nlp = ConstituentTree.create_pipeline(
                Language.English,
                ConstituentTree.SpacyModelSize.Small,
                download_models=True
            )
            self.ctl_available = True
            print("Constituent Tree подключён успешно.")
        except Exception as e:
            print(f"Не удалось подключить Constituent Tree: {e}")
            print("Constituency Tree будет недоступно, остальные функции работают.")

        # ========================================================
        # Google Translator
        # ========================================================
        self.translator = (
            GoogleTranslator(source="en", target="ru")
            if GoogleTranslator else None
        )

        # ========================================================
        # Кэши
        # ========================================================
        self.word_cache = {}
        self.text_cache = {}

        # ========================================================
        # Настройки переводчика
        # ========================================================
        # Пауза между запросами к Google.
        # 1.5 сек = ~0.67 запроса/сек. Безопасно против 429.
        self.translate_delay = 1.5
        self._last_translate_time = 0.0
        self.max_translate_retries = 2

    # ============================================================
    # ОЖИДАНИЕ ПЕРЕД ЗАПРОСОМ
    # ============================================================
    def _wait_before_translation(self):
        """Ограничивает частоту запросов к Google."""
        current_time = time.monotonic()
        elapsed = current_time - self._last_translate_time
        if elapsed < self.translate_delay:
            time.sleep(self.translate_delay - elapsed)
        self._last_translate_time = time.monotonic()

    # ============================================================
    # АНАЛИЗ ТЕКСТА
    # ============================================================
    def analyze(self, text: str):
        """Возвращает (spaCy doc, список строк с леммой и POS)."""
        doc = self.nlp(text)
        words = [t for t in doc if t.is_alpha]
        rows = []
        for token in words:
            rows.append({
                "word": token.text,
                "lemma": token.lemma_.lower(),
                "pos": token.pos_,
                "pos_description": POS_RU.get(token.pos_, token.pos_),
            })
        return doc, rows

    # ============================================================
    # ПОДСЧЁТ СЛОВ
    # ============================================================
    @staticmethod
    def word_count(text: str) -> int:
        return len(re.findall(r"\b[\w]+(?:[-'][\w]+)*\b", text, flags=re.UNICODE))

    # ============================================================
    # ПЕРЕВОД ОДНОГО ТЕКСТА
    # ============================================================
    def translate_text(self, text: str) -> str:
        """Переводит большой текст, разбивая его на части."""
        if not text or not text.strip():
            return ""
        if not self.translator:
            raise RuntimeError("Не установлен пакет deep-translator.")

        cache_key = text.strip()
        if cache_key in self.text_cache:
            return self.text_cache[cache_key]

        chunks = self._split_for_translation(text, 4500)
        result = []

        for chunk in chunks:
            if not chunk.strip():
                continue
            translated = self._translate_single(chunk)
            result.append(translated if translated else chunk)

        translated_text = "\n".join(result)
        self.text_cache[cache_key] = translated_text
        return translated_text

    # ============================================================
    # ОДИНОЧНЫЙ ЗАПРОС
    # ============================================================
    def _translate_single(self, text: str) -> str:
        """Перевод одного текста с повторными попытками."""
        if not self.translator:
            return ""

        last_error = None
        for attempt in range(self.max_translate_retries + 1):
            try:
                self._wait_before_translation()
                result = self.translator.translate(text)
                return result or ""
            except Exception as e:
                last_error = e
                print(f"Ошибка перевода (попытка {attempt + 1}): {e}")
                if attempt < self.max_translate_retries:
                    time.sleep(5 * (attempt + 1))

        print(f"Не удалось перевести текст: {last_error}")
        return ""

    # ============================================================
    # ПАКЕТНЫЙ ПЕРЕВОД (по одному слову с паузой)
    # ============================================================
    def translate_batch(self, texts):
        """
        Переводит список слов по одному с паузой между запросами.
        Это медленнее, но надёжнее, чем translate_batch из deep-translator,
        который вызывает ошибку 429 (too many requests).
        """
        if not texts:
            return []
        if not self.translator:
            return [""] * len(texts)

        texts = [str(t).strip() for t in texts]
        results = [""] * len(texts)

        for index, text in enumerate(texts):
            if not text:
                continue

            key = text.lower()
            if key in self.word_cache:
                results[index] = self.word_cache[key]
                continue

            translation = ""
            for attempt in range(self.max_translate_retries + 1):
                try:
                    self._wait_before_translation()
                    print(f"Перевод '{text}' (попытка {attempt + 1})")
                    translation = self.translator.translate(text) or ""
                    break
                except Exception as e:
                    print(f"Ошибка перевода '{text}' (попытка {attempt + 1}): {e}")
                    translation = ""
                    if attempt < self.max_translate_retries:
                        time.sleep(5 * (attempt + 1))

            results[index] = translation
            if translation:
                self.word_cache[key] = translation

        return results

    # ============================================================
    # РАЗБИВКА БОЛЬШОГО ТЕКСТА
    # ============================================================
    @staticmethod
    def _split_for_translation(text, limit):
        """Разбивает текст на части по предложениям."""
        if len(text) <= limit:
            return [text]

        parts = re.split(r"(?<=[.!?])\s+", text)
        chunks = []
        current = ""

        for part in parts:
            if len(part) > limit:
                if current:
                    chunks.append(current)
                    current = ""
                for i in range(0, len(part), limit):
                    chunks.append(part[i:i + limit])
                continue

            if len(current) + len(part) + 1 > limit:
                if current:
                    chunks.append(current)
                current = part
            else:
                current = f"{current} {part}".strip()

        if current:
            chunks.append(current)
        return chunks

    # ============================================================
    # ПЕРЕВОД ОДНОГО СЛОВА
    # ============================================================
    def translate_word(self, word: str) -> str:
        """Переводит одно слово, используя кэш и пакетный переводчик."""
        if not word or not word.strip():
            return ""

        key = word.lower().strip()
        if key in self.word_cache:
            return self.word_cache[key]

        result = self.translate_batch([word])
        return result[0] if result else ""

    # ============================================================
    # ДЕРЕВО ЗАВИСИМОСТЕЙ (Dependency Tree)
    # ============================================================
    def dependency_dot(self, doc) -> str:
        """Строит DOT-строку для дерева зависимостей."""
        dot = Digraph(comment="Dependency Tree")
        dot.attr(rankdir="LR")

        for token in doc:
            label = f"{token.text}\\n[{token.pos_}]"
            dot.node(str(token.i), label)
            if token.dep_ != "ROOT":
                dot.edge(str(token.head.i), str(token.i), label=token.dep_)

        return dot.source

    # ============================================================
    # СИНТАКСИЧЕСКОЕ ДЕРЕВО (Constituency Tree)
    # ============================================================
    def constituency_dot(self, sentence_text: str) -> str:
        """
        Строит DOT-строку для дерева составляющих через constituent-treelib.
        Принимает текст предложения (не spaCy Span).
        """
        if not self.ctl_available or not self.ct_nlp:
            return "Constituent Tree недоступно (Constituent Treelib не подключён)."

        try:
            from constituent_treelib import ConstituentTree
            tree = ConstituentTree(sentence_text, self.ct_nlp)
            nltk_tree = tree.tree_
            return self._nltk_to_dot(nltk_tree)
        except Exception as e:
            return f"Ошибка построения Constituency Tree:\n{e}"

    @staticmethod
    def _nltk_to_dot(tree) -> str:
        """Рекурсивно обходит NLTK Tree и строит Graphviz DOT."""
        dot = Digraph(comment="Constituency Tree")
        dot.attr(rankdir="TB")
        counter = [0]

        def walk(node, parent=None):
            current = str(counter[0])
            counter[0] += 1

            # Определяем метку узла
            if hasattr(node, "label") and callable(node.label):
                try:
                    label = node.label()
                except Exception:
                    label = str(node)
            else:
                label = str(node)

            dot.node(current, label)

            if parent is not None:
                dot.edge(parent, current)

            # Рекурсивно обходим детей
            if hasattr(node, "__iter__") and not isinstance(node, str):
                try:
                    for child in node:
                        walk(child, current)
                except TypeError:
                    pass

        walk(tree)
        return dot.source

    # ============================================================
    # ТАБЛИЦА ЧАСТОТНОСТИ
    # ============================================================
    def frequency_table(self, rows, db):
        """
        Формирует таблицу частотности слов.
        Сначала ищет переводы в БД, затем оставшиеся слова переводит через Google.
        """
        counter = Counter(r["lemma"] for r in rows)

        # Собираем все словоформы для каждой леммы
        forms_by_lemma = {}
        for r in rows:
            forms_by_lemma.setdefault(r["lemma"], set()).add(r["word"].lower())

        # Определяем POS для каждого lemma
        lemma_info = {}
        for row in rows:
            lemma = row["lemma"]
            if lemma not in lemma_info:
                lemma_info[lemma] = row

        result_data = {}
        words_to_translate = []

        for lemma, freq in counter.most_common():
            # 1) ищем лемму в БД
            info = db.get(lemma)

            # 2) если нет — ищем любую словоформу этой леммы
            if not info:
                for form in forms_by_lemma.get(lemma, ()):
                    info = db.get(form)
                    if info:
                        break

            if info:
                pos = info["pos"] or lemma_info[lemma]["pos"]
                pos_desc = info["pos_description"] or POS_RU.get(pos, pos)
                result_data[lemma] = {
                    "lemma": lemma,
                    "frequency": freq,
                    "translation": info["translation_ru"] or "",
                    "pos": pos,
                    "pos_description": pos_desc,
                    "domain": info["domain"] or "general",
                    "comment": info["comment"] or "",
                }
            else:
                words_to_translate.append(lemma)
                same = lemma_info[lemma]
                result_data[lemma] = {
                    "lemma": lemma,
                    "frequency": freq,
                    "translation": "",
                    "pos": same["pos"],
                    "pos_description": same["pos_description"],
                    "domain": "general",
                    "comment": "",
                }

        # Пакетный перевод слов, которых нет в БД
        if words_to_translate:
            print(f"Нужно перевести слов: {len(words_to_translate)}")
            translations = self.translate_batch(words_to_translate)

            for lemma, translation in zip(words_to_translate, translations):
                result_data[lemma]["translation"] = translation
                if translation:
                    db.upsert(
                        lemma,
                        translation,
                        result_data[lemma]["pos"],
                        result_data[lemma]["pos_description"],
                        result_data[lemma]["domain"],
                        result_data[lemma]["comment"],
                    )

        return [result_data[lemma] for lemma, _ in counter.most_common()]