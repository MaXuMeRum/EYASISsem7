"""Синтетические токены и предложения для русского дерева перевода.

Эмулируют минимальный интерфейс spaCy Token/Span, чтобы существующий
конвертер SpacyDependencyToConstituencyConverter и методы SyntaxAnalyzer
работали без переписывания.
"""


class SyntheticToken:
    """Минимальная эмуляция spaCy Token."""

    __slots__ = ('i', 'text', 'lemma_', 'pos_', 'pos_ru', 'tag_',
                 'morph_ru', 'dep_', 'head', 'children',
                 'is_punct', 'is_space', 'like_num')

    def __init__(self, index, text, lemma='', pos='', pos_ru='', tag='',
                 morph_ru='', dep='', is_punct=False, is_space=False):
        self.i = index
        self.text = text
        self.lemma_ = lemma
        self.pos_ = pos              # EN UPOS
        self.pos_ru = pos_ru         # RU POS от pymorphy3
        self.tag_ = tag              # EN Penn tag
        self.morph_ru = morph_ru     # RU морфология от pymorphy3
        self.dep_ = dep
        self.head = None
        self.children = []
        self.is_punct = is_punct
        self.is_space = is_space
        self.like_num = False

    def __repr__(self):
        return f"<SyntheticToken {self.i} '{self.text}' {self.dep_}>"


class SyntheticSentence:
    """Итерируемый контейнер синтетических токенов."""

    def __init__(self, tokens):
        self.tokens = tokens
        self.root = next((t for t in tokens if t.dep_ == 'ROOT'),
                         tokens[0] if tokens else None)

    def __iter__(self):
        return iter(self.tokens)

    def __len__(self):
        return len(self.tokens)

    @property
    def text(self):
        return ' '.join(t.text for t in self.tokens)

    @property
    def start(self):
        return 0

    @property
    def end(self):
        return len(self.tokens)
