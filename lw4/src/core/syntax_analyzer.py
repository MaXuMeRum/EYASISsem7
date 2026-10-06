import spacy
import streamlit as st
from spacy import displacy
from core.stanza_parser import StanzaConstituencyParser
from core.translators import SyntaxTagTranslator
from nltk.tree import Tree
import matplotlib.pyplot as plt
import base64
from io import BytesIO
from collections import defaultdict


class SyntaxAnalyzer:
    SPACY_MODELS = {'ru': 'ru_core_news_sm', 'en': 'en_core_web_sm'}

    # Языки, для которых есть обученный парсер составляющих.
    # Stanza constituency поддерживает только EN, для RU остаётся эвристика.
    STANZA_LANGS = {'en'}

    def __init__(self, lang='ru'):
        self.nlp = None
        self.lang = lang
        self.model_name = self.SPACY_MODELS.get(lang)
        self.translator = SyntaxTagTranslator()
        self._stanza = None
        self._stanza_error = None
        if lang in self.STANZA_LANGS:
            self._stanza = StanzaConstituencyParser(lang=lang)

    def ensure_loaded(self):
        if self.nlp is None:
            try:
                self.nlp = spacy.load(self.model_name)
            except OSError:
                st.error(f"Модель {self.model_name} не найдена. "
                         f"Установите: python -m spacy download {self.model_name}")
                return False
        return True

    def analyze(self, text):
        if not self.ensure_loaded():
            return None
        return self.nlp(text)

    def constituency_trees_for(self, sents):
        """Деревья составляющих для списка предложений spaCy.

        Для EN — батчевый разбор Stanza (одним проходом модели на весь
        документ), для остальных языков — эвристика по дереву зависимостей.
        Список результатов выровнен по sents; None означает, что дерево
        построить не удалось.
        """
        if not sents:
            return []

        if self._stanza is not None:
            try:
                parsed = self._stanza.parse_many([s.text for s in sents])
                return [p[0] if p else None for p in parsed]
            except RuntimeError as e:
                # Модель Stanza может быть не скачана или не подгрузиться.
                # Не роняем разбор целиком: предупреждаем один раз и
                # откатываемся на эвристику для всех предложений.
                if self._stanza_error != str(e):
                    self._stanza_error = str(e)
                    st.warning(
                        f"{e} Дерево составляющих построено эвристикой."
                    )
                self._stanza = None
            except Exception as e:
                st.warning(
                    f"Stanza вернула ошибку при разборе ({e}). "
                    f"Дерево составляющих построено эвристикой."
                )
                self._stanza = None

        return [self.deps_to_constituents_tree(s) for s in sents]

    def get_sentence_trees(self, doc):
        sentences = []
        spacy_sents = list(doc.sents)
        constituency = self.constituency_trees_for(spacy_sents)

        for sent_idx, sent in enumerate(spacy_sents):
            sent_doc = doc[sent.start:sent.end]
            tokens_list = list(sent_doc)
            if tokens_list and tokens_list[-1].pos_ == 'PUNCT':
                tokens_list = tokens_list[:-1]

            html = displacy.render(sent_doc, style="dep", options={"compact": True, "bg": "#fff"},
                                   jupyter=False, page=False)

            tokens_data = []
            for token in tokens_list:
                token_data = {
                    'text': token.text,
                    'lemma': token.lemma_,
                    'pos': token.pos_,
                    'tag': token.tag_,
                    'dep': token.dep_,
                    'head': token.head.text,
                    'head_idx': token.head.i - sent.start,
                }
                translated = self.translator.translate_token(token_data)
                tokens_data.append({
                    'wordform': translated['text'],
                    'lemma': translated['lemma'],
                    'pos': translated['pos_rus'],
                    'tag': translated['tag'],              # raw Penn (IN, NNS)
                    'tag_rus': translated['tag_rus'],      # расшифровка Penn
                    'dependency': translated['dep_rus'],   # перевод dep
                    'head_word': translated['head']
                })

            nltk_tree = constituency[sent_idx] if sent_idx < len(constituency) else None
            constituency_data = None

            if nltk_tree:
                lisp_format = nltk_tree.pformat()
                img_base64 = self.draw_tree_matplotlib_constituency(nltk_tree)
                constituency_data = {
                    'lisp_format': lisp_format,
                    'image_base64': img_base64
                }

            sentences.append({
                'sentence_id': sent_idx,
                'text': sent.text,
                'tokens': tokens_data,
                'dependency_html': html,
                'root': sent.root.text,
                'constituency_tree': constituency_data
            })

        return sentences

    def build_trees_from_synthetic(self, synthetic_sents):
        """Строит структуру для отображения по списку SyntheticSentence.

        Для каждого предложения возвращает:
        - dependency_image_base64 — дерево зависимостей (PNG);
        - constituency_tree — дерево составляющих;
        - tokens — морфологическую разметку (для выбранного предложения).
        """
        sentences = []
        for idx, sent in enumerate(synthetic_sents):
            dep_img = self.draw_dependency_tree_matplotlib(sent)

            nltk_tree = self.deps_to_constituents_tree(sent)
            cons_data = None
            if nltk_tree:
                cons_data = {
                    'lisp_format': nltk_tree.pformat(),
                    'image_base64': self.draw_tree_matplotlib_constituency(nltk_tree),
                }

            tokens_data = []
            for tok in sent:
                tokens_data.append({
                    'wordform': tok.text,
                    'lemma': tok.lemma_,
                    'pos': self.translator.get_pymorph_pos_rus(tok.pos_ru),
                    'tag': tok.pos_ru or '',           # raw pymorphy3 (ADJF, NOUN)
                    'tag_rus': self.translator.get_pymorph_pos_rus(tok.pos_ru),
                    'dependency': self.translator.get_dep_rus(tok.dep_),
                    'head_word': tok.head.text if tok.head else '',
                })

            sentences.append({
                'sentence_id': idx,
                'text': sent.text,
                'root': sent.root.text if sent.root else '',
                'dependency_image_base64': dep_img,
                'constituency_tree': cons_data,
                'tokens': tokens_data,
            })
        return sentences

    class SpacyDependencyToConstituencyConverter:
        def __init__(self, sent):
            self.sent = sent
            self.tokens = list(sent)
            self.token_by_i = {t.i: t for t in self.tokens}
            self.sent_token_indices = set(t.i for t in self.tokens)
            self.children = defaultdict(list)
            for tok in self.tokens:
                if tok.head.i != tok.i and tok.head.i in self.sent_token_indices:
                    self.children[tok.head.i].append(tok)
            for head_i in self.children:
                self.children[head_i].sort(key=lambda t: t.i)

        def get_root(self):
            for tok in self.tokens:
                if tok.head == tok or tok.dep_ == "ROOT":
                    return tok
            return self.tokens[0] if self.tokens else None

        def is_nominal(self, token):
            return token.pos_ in ('NOUN', 'PROPN', 'PRON', 'NUM')

        def is_verbal(self, token):
            return token.pos_ in ('VERB', 'AUX')

        def is_adjectival(self, token):
            return token.pos_ in ('ADJ', 'DET')

        def is_adverbial(self, token):
            return token.pos_ in ('ADV',)

        def word_leaf(self, token):
            return Tree(token.pos_, [token.text])

        def sort_nodes_by_surface(self, nodes):
            return sorted(nodes, key=lambda x: x[0])

        def find_cc_for_conj(self, conj_token):
            for child in self.children.get(conj_token.i, []):
                if child.dep_ == 'cc':
                    return child
            # В UD союз «cc» — ребёнок головы координации, а не самого
            # конъюнкта: у "читает книги и пишет" «и» ребёнок «читает».
            head = conj_token.head
            if head is not None and head is not conj_token:
                for child in self.children.get(head.i, []):
                    if child.dep_ == 'cc' and child.i < conj_token.i:
                        return child
            return None

        def find_subject(self, head):
            for child in self.children.get(head.i, []):
                if child.dep_ in ('nsubj', 'nsubj:pass', 'nsubjpass', 'csubj'):
                    return child
            return None

        def build(self):
            root = self.get_root()
            if not root:
                return Tree('S', [])
            return self.build_sentence(root)

        def build_phrase(self, token):
            if self.is_verbal(token):
                return self.build_vp(token)
            if self.is_nominal(token):
                return self.build_np(token)
            if self.is_adjectival(token):
                return self.build_adjp(token)
            if self.is_adverbial(token):
                return self.build_advp(token)
            if token.pos_ == 'ADP':
                return self.build_pp(token)
            if token.pos_ == 'SCONJ':
                return Tree('SCONJP', [token.text])
            return self.word_leaf(token)

        def build_np(self, head):
            left_mods = []
            right_mods = []
            punct = []
            for child in self.children.get(head.i, []):
                rel = child.dep_
                if rel == 'punct':
                    punct.append(child)
                elif rel in ('det', 'amod', 'nummod', 'nummod:entity'):
                    if self.is_adjectival(child):
                        left_mods.append((child.i, self.build_adjp(child)))
                    else:
                        left_mods.append((child.i, self.word_leaf(child)))
                elif rel == 'case':
                    left_mods.append((child.i, Tree('P', [child.text])))
                elif rel in ('fixed', 'flat', 'compound'):
                    right_mods.append((child.i, self.word_leaf(child)))
                elif rel == 'nmod':
                    right_mods.append((child.i, self.build_np(child)))
                elif rel == 'appos':
                    right_mods.append((child.i, Tree('Appos', [self.build_np(child)])))
                elif rel in ('acl', 'acl:relcl'):
                    right_mods.append((child.i, Tree('RC', [self.build_clause(child)])))
                elif rel == 'conj':
                    cc = self.find_cc_for_conj(child)
                    coord_children = []
                    if cc:
                        coord_children.append(Tree('CC', [cc.text]))
                    coord_children.append(self.build_np(child))
                    right_mods.append((child.i, Tree('CoordNP', coord_children)))
                elif rel == 'parataxis':
                    right_mods.append((child.i, Tree('Parataxis', [self.build_phrase(child)])))
                elif rel == 'discourse':
                    right_mods.append((child.i, Tree('Discourse', [child.text])))
            np_head = Tree(head.pos_, [head.text])
            ordered = (
                self.sort_nodes_by_surface(left_mods)
                + [(head.i, np_head)]
                + self.sort_nodes_by_surface(right_mods)
                + [(w.i, Tree('PUNCT', [w.text])) for w in punct]
            )
            return Tree('NP', [node for _, node in ordered])

        def build_adjp(self, head):
            left = []
            right = []
            punct = []
            for child in self.children.get(head.i, []):
                rel = child.dep_
                if rel == 'advmod':
                    left.append((child.i, self.build_advp(child)))
                elif rel in ('obl', 'obj', 'dobj'):
                    right.append((child.i, self.build_np(child)))
                elif rel == 'conj':
                    cc = self.find_cc_for_conj(child)
                    coord = []
                    if cc:
                        coord.append(Tree('CC', [cc.text]))
                    coord.append(self.build_adjp(child))
                    right.append((child.i, Tree('CoordADJP', coord)))
                elif rel == 'punct':
                    punct.append(child)
            head_node = Tree(head.pos_, [head.text])
            ordered = (
                self.sort_nodes_by_surface(left)
                + [(head.i, head_node)]
                + self.sort_nodes_by_surface(right)
                + [(w.i, Tree('PUNCT', [w.text])) for w in punct]
            )
            return Tree('ADJP', [node for _, node in ordered])

        def build_advp(self, head):
            left = []
            right = []
            punct = []
            for child in self.children.get(head.i, []):
                rel = child.dep_
                if rel == 'advmod':
                    left.append((child.i, self.build_advp(child)))
                elif rel in ('obl', 'obj', 'dobj'):
                    right.append((child.i, self.build_np(child)))
                elif rel == 'conj':
                    cc = self.find_cc_for_conj(child)
                    coord = []
                    if cc:
                        coord.append(Tree('CC', [cc.text]))
                    coord.append(self.build_advp(child))
                    right.append((child.i, Tree('CoordADVP', coord)))
                elif rel == 'punct':
                    punct.append(child)
            head_node = Tree(head.pos_, [head.text])
            ordered = (
                self.sort_nodes_by_surface(left)
                + [(head.i, head_node)]
                + self.sort_nodes_by_surface(right)
                + [(w.i, Tree('PUNCT', [w.text])) for w in punct]
            )
            return Tree('ADVP', [node for _, node in ordered])

        def build_pp(self, head):
            parts = [Tree('P', [head.text])]
            for child in self.children.get(head.i, []):
                parts.append(self.build_phrase(child))
            return Tree('PP', parts)

        def build_clause(self, head):
            if self.is_verbal(head):
                subj = self.find_subject(head)
                vp = self.build_vp(head)
                if subj:
                    return Tree('S', [self.build_np(subj), vp])
                return Tree('S', [vp])
            if self.is_nominal(head) or self.is_adjectival(head):
                return self.build_sentence(head)
            return Tree('S', [self.build_phrase(head)])

        def build_vp(self, head):
            left = []
            right = []
            punct = []
            aux_nodes = []
            cop_nodes = []
            mark_nodes = []
            discourse_nodes = []
            for child in self.children.get(head.i, []):
                rel = child.dep_
                if rel in ('nsubj', 'nsubj:pass', 'nsubjpass', 'csubj'):
                    continue
                elif rel in ('aux', 'aux:pass', 'auxpass'):
                    aux_nodes.append((child.i, Tree('AUX', [child.text])))
                elif rel == 'cop':
                    cop_nodes.append((child.i, Tree('COP', [child.text])))
                elif rel == 'mark':
                    mark_nodes.append((child.i, Tree('MARK', [child.text])))
                elif rel == 'advmod':
                    left.append((child.i, self.build_advp(child)))
                elif rel in ('obj', 'iobj', 'dobj', 'pobj'):
                    right.append((child.i, self.build_np(child)))
                elif rel == 'obl':
                    right.append((child.i, self.build_oblique(child)))
                elif rel == 'xcomp':
                    right.append((child.i, Tree('XCOMP', [self.build_phrase(child)])))
                elif rel == 'ccomp':
                    right.append((child.i, Tree('CCOMP', [self.build_clause(child)])))
                elif rel == 'advcl':
                    right.append((child.i, Tree('SBAR', [self.build_clause(child)])))
                elif rel == 'expl':
                    left.append((child.i, Tree('EXPL', [child.text])))
                elif rel in ('discourse', 'vocative'):
                    discourse_nodes.append((child.i, Tree('DISCOURSE', [child.text])))
                elif rel in ('obl:agent', 'agent'):
                    right.append((child.i, Tree('AgentPP', [self.build_np(child)])))
                elif rel == 'conj':
                    cc = self.find_cc_for_conj(child)
                    coord = []
                    if cc:
                        coord.append(Tree('CC', [cc.text]))
                    if self.is_verbal(child):
                        coord.append(self.build_vp(child))
                    else:
                        coord.append(self.build_phrase(child))
                    right.append((child.i, Tree('CoordVP', coord)))
                elif rel == 'parataxis':
                    right.append((child.i, Tree('Parataxis', [self.build_clause(child)])))
                elif rel == 'punct':
                    punct.append(child)
                elif rel == 'compound:prt':
                    right.append((child.i, Tree('PRT', [child.text])))
                elif rel == 'appos':
                    right.append((child.i, Tree('Appos', [self.build_phrase(child)])))
            head_node = Tree('V', [head.text])
            ordered = (
                self.sort_nodes_by_surface(mark_nodes)
                + self.sort_nodes_by_surface(aux_nodes)
                + self.sort_nodes_by_surface(cop_nodes)
                + self.sort_nodes_by_surface(left)
                + [(head.i, head_node)]
                + self.sort_nodes_by_surface(right)
                + self.sort_nodes_by_surface(discourse_nodes)
                + [(w.i, Tree('PUNCT', [w.text])) for w in punct]
            )
            return Tree('VP', [node for _, node in ordered])

        def build_oblique(self, head):
            case_children = [c for c in self.children.get(head.i, []) if c.dep_ == 'case']
            if case_children:
                parts = []
                for c in sorted(case_children, key=lambda x: x.i):
                    parts.append(Tree('P', [c.text]))
                parts.append(self.build_np_without_case(head))
                return Tree('PP', parts)
            if self.is_nominal(head):
                return self.build_np(head)
            return self.build_phrase(head)

        def build_np_without_case(self, head):
            left_mods = []
            right_mods = []
            punct = []
            for child in self.children.get(head.i, []):
                rel = child.dep_
                if rel == 'case':
                    continue
                elif rel == 'punct':
                    punct.append(child)
                elif rel in ('det', 'amod', 'nummod', 'nummod:entity'):
                    if self.is_adjectival(child):
                        left_mods.append((child.i, self.build_adjp(child)))
                    else:
                        left_mods.append((child.i, self.word_leaf(child)))
                elif rel in ('fixed', 'flat', 'compound'):
                    right_mods.append((child.i, self.word_leaf(child)))
                elif rel == 'nmod':
                    right_mods.append((child.i, self.build_np(child)))
                elif rel == 'appos':
                    right_mods.append((child.i, Tree('Appos', [self.build_np(child)])))
                elif rel in ('acl', 'acl:relcl'):
                    right_mods.append((child.i, Tree('RC', [self.build_clause(child)])))
                elif rel == 'conj':
                    cc = self.find_cc_for_conj(child)
                    coord_children = []
                    if cc:
                        coord_children.append(Tree('CC', [cc.text]))
                    coord_children.append(self.build_np(child))
                    right_mods.append((child.i, Tree('CoordNP', coord_children)))
            np_head = Tree(head.pos_, [head.text])
            ordered = (
                self.sort_nodes_by_surface(left_mods)
                + [(head.i, np_head)]
                + self.sort_nodes_by_surface(right_mods)
                + [(w.i, Tree('PUNCT', [w.text])) for w in punct]
            )
            return Tree('NP', [node for _, node in ordered])

        def build_sentence(self, root):
            parts = []
            if self.is_verbal(root):
                subj = self.find_subject(root)
                if subj:
                    parts.append(self.build_np(subj))
                parts.append(self.build_vp(root))
                for child in self.children.get(root.i, []):
                    if child.dep_ == 'parataxis':
                        parts.append(Tree('Parataxis', [self.build_clause(child)]))
                    elif child.dep_ == 'dislocated':
                        parts.append(Tree('Dislocated', [self.build_phrase(child)]))
                return Tree('S', parts)
            pred_parts = []
            subj = self.find_subject(root)
            if subj and subj.i != root.i:
                pred_parts.append(self.build_np(subj))
            has_cop = any(c.dep_ == 'cop' for c in self.children.get(root.i, []))
            if has_cop:
                vp = self.build_vp(root)
                if subj and subj.i != root.i:
                    return Tree('S', [self.build_np(subj), vp])
                return Tree('S', [vp])
            pred_parts.append(self.build_phrase(root))
            return Tree('S', pred_parts)

    def deps_to_constituents_tree(self, sent):
        converter = self.SpacyDependencyToConstituencyConverter(sent)
        return converter.build()

    def draw_dependency_tree_matplotlib(self, syn_sent,
                                        figsize=(16, 6), font_size=9):
        """Рисует дерево зависимостей синтетического предложения.

        displaCy работает только с настоящим spaCy Doc, а у нас
        SyntheticSentence. Поэтому рисуем сами в том же стиле, что и
        дерево составляющих: голова сверху, зависимые снизу, рёбра
        подписаны типом связи (dep_), листья — словоформа + POS.

        Возвращает PNG в base64.
        """
        tokens = list(syn_sent)
        if not tokens:
            return ''

        # --- дети каждого токена ---
        children = defaultdict(list)
        root = None
        for t in tokens:
            if t.head is None or t.head.i == t.i:
                if root is None:
                    root = t
                continue
            children[t.head.i].append(t)
        for k in children:
            children[k].sort(key=lambda x: x.i)

        if root is None:
            root = tokens[0]

        # --- раскладка: X — inorder-номер, Y — глубина ---
        positions = {}
        counter = [0]

        def compute(tok, depth):
            kids = children.get(tok.i, [])
            if not kids:
                x = counter[0]
                counter[0] += 1
            else:
                xs = [compute(k, depth + 1) for k in kids]
                x = (min(xs) + max(xs)) / 2
            positions[tok.i] = (x, -depth)
            return x

        compute(root, 0)

        # если какой-то токен остался без позиции (висячий) — кладём справа
        for t in tokens:
            if t.i not in positions:
                positions[t.i] = (counter[0], 0)
                counter[0] += 1

        # --- рисуем ---
        max_depth = max(-y for _, y in positions.values()) + 1
        width = max(figsize[0], counter[0] * 1.4)
        height = max(figsize[1], (max_depth + 1) * 1.2)
        fig, ax = plt.subplots(figsize=(width, height))
        ax.axis('off')

        # рёбра + подписи dep
        for t in tokens:
            if t.head is None or t.head.i == t.i:
                continue
            x1, y1 = positions[t.head.i]
            x2, y2 = positions[t.i]
            ax.plot([x1, x2], [y1, y2], color='#888888', linewidth=1, alpha=0.7)
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            ax.text(mx, my + 0.05, t.dep_, ha='center', va='bottom',
                    fontsize=font_size - 1, color='#B71C1C',
                    bbox=dict(boxstyle='round,pad=0.15',
                              facecolor='#FFEBEE', edgecolor='none'))

        # узлы
        for t in tokens:
            x, y = positions[t.i]
            label = f"{t.text}\n{t.pos_ru or ''}"
            bbox = dict(boxstyle='round,pad=0.3',
                        facecolor='#E8F5E9',
                        edgecolor='#388E3C',
                        linewidth=1.2)
            ax.text(x, y, label, ha='center', va='center',
                    bbox=bbox, fontsize=font_size, family='monospace')

        margin = 1
        ax.set_xlim(-margin, counter[0] - 1 + margin)
        ax.set_ylim(-max_depth - margin, margin)

        plt.tight_layout()
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=200, bbox_inches='tight',
                    facecolor='white')
        plt.close()
        return base64.b64encode(buf.getvalue()).decode('utf-8')

    def draw_tree_matplotlib_constituency(self, tree,
                                          figsize=(16, 10), font_size=9):
        """Рисует дерево и возвращает PNG как base64.

        Изображение рендерится в память: файлы в рабочем каталоге не создаются.
        """
        leaves_in_order = []

        def collect_leaves(node):
            if isinstance(node, Tree):
                for child in node:
                    collect_leaves(child)
            else:
                leaves_in_order.append(node)

        collect_leaves(tree)

        leaf_positions = {}
        for i, leaf_text in enumerate(leaves_in_order):
            leaf_positions[(leaf_text, i)] = (i, -tree.height() * 1.0)

        node_positions = {}
        leaf_counter = [0]

        def compute_positions(node, depth):
            if isinstance(node, Tree):
                children_x = []
                for child in node:
                    child_x = compute_positions(child, depth + 1)
                    children_x.append(child_x)
                x = (min(children_x) + max(children_x)) / 2 if children_x else 0
                y = -depth * 1.0
                node_positions[id(node)] = (x, y)
                return x
            else:
                idx = leaf_counter[0]
                leaf_counter[0] += 1
                x, y = leaf_positions[(node, idx)]
                node_positions[('leaf', idx)] = (x, y)
                return x

        compute_positions(tree, 0)

        fig_width = max(figsize[0], len(leaves_in_order) * 1.5)
        fig_height = max(figsize[1], tree.height() * 1.0)

        fig, ax = plt.subplots(figsize=(fig_width, fig_height))
        ax.axis('off')

        leaf_draw_counter = [0]

        def draw_node(node, parent_pos=None):
            if isinstance(node, Tree):
                x, y = node_positions.get(id(node), (0, 0))
                if parent_pos is not None:
                    ax.plot([parent_pos[0], x], [parent_pos[1], y],
                            'k-', linewidth=1, color='#888888', alpha=0.7)
                label = node.label()
                bbox = dict(
                    boxstyle='round,pad=0.3',
                    facecolor='#E3F2FD',
                    edgecolor='#1976D2',
                    linewidth=1.5
                )
                ax.text(
                    x, y, label,
                    ha='center', va='center',
                    bbox=bbox, fontsize=font_size,
                    fontweight='bold', family='sans-serif'
                )
                for child in node:
                    draw_node(child, (x, y))
            else:
                idx = leaf_draw_counter[0]
                leaf_draw_counter[0] += 1
                x, y = node_positions.get(('leaf', idx), (0, 0))
                if parent_pos is not None:
                    ax.plot([parent_pos[0], x], [parent_pos[1], y],
                            'k-', linewidth=1, color='#888888', alpha=0.7)
                bbox = dict(
                    boxstyle='round,pad=0.3',
                    facecolor='#E8F5E9',
                    edgecolor='#388E3C',
                    linewidth=1.5
                )
                ax.text(
                    x, y, node,
                    ha='center', va='center',
                    bbox=bbox, fontsize=font_size,
                    family='monospace'
                )

        draw_node(tree)

        margin = 1
        total_width = len(leaves_in_order)
        ax.set_xlim(-margin, total_width + margin)
        ax.set_ylim(-tree.height() * 1.0 - margin, margin)

        plt.tight_layout()
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight',
                    facecolor='white')
        plt.close()

        return base64.b64encode(buffer.getvalue()).decode('utf-8')

