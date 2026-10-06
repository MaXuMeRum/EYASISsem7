# Константы модуля машинного перевода EN -> RU
#
# Таблицы лингвистических тегов (EN_TAG_TRANSLATE, SYNTAX_POS_TRANSLATE,
# SYNTAX_DEP_TRANSLATE, PYMORPH_POS_TRANSLATE) хранятся в core.constants,
# чтобы пакет core не зависел от mt.

# Слова, не требующие перевода (артикли, вспомогательные глаголы, предлоги)
EN_STOPWORDS = {'a', 'an', 'the', 'to', 'of', 'in', 'on', 'at', 'by', 'for',
                'with', 'from', 'as', 'is', 'are', 'was', 'were', 'be', 'been',
                'being', 'do', 'does', 'did', 'have', 'has', 'had'}

# Теги spaCy, которые не переводятся.
# AUX НЕ входит: среди AUX есть модальные глаголы (must, should, could),
# у которых есть прямые русские аналоги. Разделяем их по Penn-тегу
# (MD = модальный, VB* = обычный вспомогательный) — см. mt_engine.
SKIP_POS = {'DET', 'PUNCT', 'SPACE'}

# Категории источников перевода
TRANSLATION_SOURCES = {
    'manual': 'Вручную',
    'api_argos': 'Argos Translate (офлайн)',
    'imported': 'Импорт',
}
