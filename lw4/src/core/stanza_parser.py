"""Constituency parsing для английского языка через Stanza.

Заменяет эвристический SpacyDependencyToConstituencyConverter
для английского языка: Stanza содержит обученный shift-reduce парсер
составляющих (Penn Treebank, ~93 F1), а не набор правил над dependency-деревом.
Для русского остаётся эвристика — Stanza не поддерживает constituency для ru.

Зависимость необязательна: если stanza или её модели нет, модуль не падает
на импорте и не на запуске приложения, а сообщает об ошибке при первой
попытке разбора (см. SyntaxAnalyzer.constituency_trees_for).
"""
import logging

from nltk.tree import Tree

logger = logging.getLogger(__name__)


class StanzaConstituencyParser:
    """Обёртка над Stanza Pipeline для constituency parsing (EN).

    Pipeline загружается лениво и один раз: инициализация нейросетевой модели
    занимает несколько секунд, поэтому держим её в атрибуте инстанса.
    Анализатор SyntaxAnalyzer живёт дольше одного прогона Streamlit,
    поэтому повторных загрузок не происходит.

    Результаты кэшируются по тексту предложения: один и тот же текст
    (например, при перерисовке вкладки) не разбирается заново.
    """

    def __init__(self, lang='en', use_gpu=True):
        self.lang = lang
        self.use_gpu = use_gpu
        self._nlp = None
        self._load_error = None
        self._cache = {}
        # Кэш ограничен, чтобы не расти вместе с длиной документа:
        # при переполнении он просто сбрасывается целиком.
        self._cache_maxsize = 512

    # ------------------------------------------------------------------
    def _load(self):
        if self._nlp is not None:
            return self._nlp
        if self._load_error is not None:
            raise RuntimeError(self._load_error)

        try:
            import stanza
        except ImportError as e:
            self._load_error = (
                f"Stanza не установлена ({e}). Установите: pip install stanza"
            )
            raise RuntimeError(self._load_error)

        try:
            self._nlp = stanza.Pipeline(
                lang=self.lang,
                processors='tokenize,pos,constituency',
                # Предложения режем сами (spaCy), иначе Stanza разобьёт
                # текст на предложения по-своему и деревья разъедутся.
                tokenize_no_ssplit=True,
                use_gpu=self.use_gpu,
                # Модель лежит на диске, поэтому обращаться к сети при
                # старте приложения незачем. NONE запрещает любые загрузки:
                # если весов нет, Stanza сообщает, какой файл отсутствует.
                download_method=stanza.DownloadMethod.NONE,
                logging_level='WARN',
                verbose=False,
            )
        except Exception as e:
            self._load_error = (
                f"Не удалось загрузить Stanza {self.lang.upper()}: {e}. "
                f"Скачайте модель: "
                f"python -c \"import stanza; stanza.download('{self.lang}')\""
            )
            raise RuntimeError(self._load_error)
        return self._nlp

    # ------------------------------------------------------------------
    def parse(self, text):
        """Возвращает список NLTK-деревьев составляющих по предложениям.

        Для одного предложения список содержит один элемент, для пустого
        текста — пустой список. Список, а не Tree: текст может содержать
        больше одного предложения.
        """
        if not text or not text.strip():
            return []
        return self.parse_many([text])[0]

    def parse_many(self, texts):
        """Батчевый разбор: список предложений -> список списков деревьев.

        Stanza умеет обрабатывать список документов за один вызов, поэтому
        предложения документа разбираются одним проходом модели, а не по
        одному. Результат выровнен по входному списку: texts[i] ->
        result[i]. Для каждого элемента result[i] — список деревьев
        (обычно одно, если текст — одно предложение).
        """
        results = [None] * len(texts)
        pending = []
        for idx, text in enumerate(texts):
            key = self._cache_key(text)
            if not key:
                results[idx] = []
            elif key in self._cache:
                results[idx] = self._cache[key]
            else:
                pending.append((idx, key))

        if not pending:
            return results

        nlp = self._load()
        # tokenize_no_ssplit=True даёт ровно одно предложение на входной
        # документ, поэтому порядок деревьев совпадает с порядком texts.
        doc = nlp([key for _, key in pending])
        trees = [self._to_nltk_tree(s.constituency) for s in doc.sentences]

        if len(trees) != len(pending):
            # Нарушение 1:1 означало бы сдвиг разметки: дерево от одного
            # предложения показалось бы для другого. Лучше честно отдать
            # пустые результаты, чем перепутать предложения.
            logger.warning(
                'Stanza вернула %d предложений на %d входных; '
                'деревья составляющих для этого документа пропущены.',
                len(trees), len(pending),
            )
            return [[] if results[i] is None else results[i]
                    for i in range(len(results))]

        for (idx, key), tree in zip(pending, trees):
            results[idx] = [tree] if tree is not None else []
            self._remember(key, results[idx])
        return results

    # ------------------------------------------------------------------
    @staticmethod
    def _cache_key(text):
        if not text:
            return None
        stripped = text.strip()
        return stripped or None

    def _remember(self, key, value):
        if len(self._cache) >= self._cache_maxsize:
            self._cache.clear()
        self._cache[key] = value

    @staticmethod
    def _to_nltk_tree(constituency):
        """Stanza ParseTree -> NLTK Tree.

        Stanza отдаёт дерево как объект ParseTree; str() даёт
        S-expression, который NLTK разбирает штатным Tree.fromstring.
        """
        if constituency is None:
            return None
        if isinstance(constituency, Tree):
            return constituency
        try:
            tree = Tree.fromstring(str(constituency))
        except Exception as e:
            logger.warning("Не удалось разобрать дерево Stanza: %s", e)
            return None
        if tree is None or len(tree) == 0:
            return None
        return tree
