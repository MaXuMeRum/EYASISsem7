from core.constants import (EN_TAG_TRANSLATE, PYMORPH_POS_TRANSLATE,
                             SYNTAX_DEP_TRANSLATE, SYNTAX_POS_TRANSLATE)


def en_tag_rus(tag):
    """Расшифровка Penn Treebank тега spaCy (EN) на русский."""
    if not tag:
        return ''
    return EN_TAG_TRANSLATE.get(tag, tag)


class SyntaxTagTranslator:
    DEP_TRANSLATE = SYNTAX_DEP_TRANSLATE
    POS_TRANSLATE = SYNTAX_POS_TRANSLATE          # UPOS (для EN)
    PYMORPH_TRANSLATE = PYMORPH_POS_TRANSLATE     # pymorphy3 (для RU)

    def get_dep_rus(self, dep):
        if not dep:
            return 'неизвестно'
        return self.DEP_TRANSLATE.get(dep, dep)

    def get_pos_rus(self, pos):
        """Перевод UPOS-тега spaCy (ADJ, NOUN, ...)."""
        if not pos:
            return 'неизвестно'
        return self.POS_TRANSLATE.get(pos, pos)

    def get_pymorph_pos_rus(self, pos):
        """Перевод POS-тега pymorphy3 (ADJF, INFN, ...)."""
        if not pos:
            return 'неизвестно'
        return self.PYMORPH_TRANSLATE.get(pos, pos)

    def get_tag_rus(self, tag):
        return en_tag_rus(tag)

    def translate_token(self, token_data):
        return {
            'text': token_data.get('text', ''),
            'lemma': token_data.get('lemma', ''),
            'pos_rus': self.get_pos_rus(token_data.get('pos', '')),
            'tag': token_data.get('tag', ''),
            'tag_rus': self.get_tag_rus(token_data.get('tag', '')),
            'dep_rus': self.get_dep_rus(token_data.get('dep', '')),
            'dep': token_data.get('dep', ''),
            'head': token_data.get('head', ''),
            'head_idx': token_data.get('head_idx', 0)
        }
