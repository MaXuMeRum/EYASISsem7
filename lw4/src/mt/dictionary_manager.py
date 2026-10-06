"""Словарь EN -> RU: CRUD, автопополнение через Argos Translate, импорт/экспорт файлов.

Хранит данные в локальном SQLite-файле app.db в корне проекта.
Файл создаётся автоматически при первом запуске, никаких внешних
серверов не требуется.
"""
import time
from pathlib import Path

import argostranslate.package
import argostranslate.translate
from sqlalchemy import create_engine, event, or_
from sqlalchemy.orm import sessionmaker

from mt.mt_models import Dictionary


# Корень проекта: .../lww4/
# dictionary_manager.py лежит в .../lww4/src/mt/, значит parents[2] -> lww4/
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DB_PATH = _PROJECT_ROOT / "app.db"
_DATABASE_URL = f"sqlite:///{_DB_PATH.as_posix()}"


class DictionaryManager:
    def __init__(self):
        _PROJECT_ROOT.mkdir(parents=True, exist_ok=True)

        self.engine = create_engine(
            _DATABASE_URL,
            # Streamlit обрабатывает запросы в разных потоках:
            # без этого флага SQLite будет ругаться на shared connection.
            connect_args={"check_same_thread": False},
            echo=False,
        )

        # Включаем WAL и внешние ключи для каждого нового соединения.
        # WAL сильно уменьшает вероятность "database is locked" при
        # параллельных чтениях из UI.
        @event.listens_for(self.engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

        from core.models import Base
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self._argos_ready = False

    # ------------------------------------------------------------------
    # Argos Translate (офлайн, без API-ключа)
    # ------------------------------------------------------------------
    def _ensure_argos(self, retries: int = 3, delay: float = 2.0):
        """Лениво готовит модель EN→RU. Модель ставится один раз при первом
        обращении; повторные попытки — с экспоненциальной паузой, потому что
        именно этот шаг единственный сетевой и может оборваться."""
        if self._argos_ready:
            return
        last_error = None
        for attempt in range(retries):
            try:
                if not self._argos_pair_ready():
                    argostranslate.package.update_package_index()
                    available = argostranslate.package.get_available_packages()
                    pkg = next((p for p in available
                                if p.from_code == 'en' and p.to_code == 'ru'), None)
                    if pkg is None:
                        raise RuntimeError(
                            "Пакет перевода EN→RU не найден в индексе Argos")
                    argostranslate.package.install_from_path(pkg.download())
                    if not self._argos_pair_ready():
                        raise RuntimeError("Модель EN→RU установилась, но не видна")
                self._argos_ready = True
                return
            except Exception as e:
                last_error = e
                if attempt < retries - 1:
                    time.sleep(delay * (2 ** attempt))
        raise RuntimeError(f"Не удалось подготовить Argos Translate: {last_error}")

    @staticmethod
    def _argos_pair_ready() -> bool:
        """Проверяет именно направление EN→RU: наличие языка RU само по
        себе ничего не значит (может быть установлен только RU→EN)."""
        try:
            return (argostranslate.translate
                    .get_translation_from_codes('en', 'ru')) is not None
        except AttributeError:
            return False

    def fetch_translation(self, word: str):
        """Перевод через Argos Translate (офлайн, без ключа и лимитов)."""
        try:
            self._ensure_argos()
        except Exception as e:
            # Первый запуск без сети — модель не скачается
            print(f"Не удалось подготовить Argos: {e}")
            return None
        try:
            res = argostranslate.translate.translate(word, 'en', 'ru')
            return res.strip() if res else None
        except Exception as e:
            print(f"Ошибка Argos для '{word}': {e}")
            return None

    # ------------------------------------------------------------------
    # Поиск
    # ------------------------------------------------------------------
    def lookup(self, lemma: str, pos: str = ''):
        if not lemma:
            return None
        with self.Session() as s:
            q = s.query(Dictionary).filter(Dictionary.source_word == lemma.lower())
            row = q.filter(Dictionary.pos == pos).first() if pos else None
            if row is None:
                row = q.first()
            if row is None:
                return None
            return {
                'id': row.id, 'source_word': row.source_word,
                'source_form': row.source_form, 'target_word': row.target_word,
                'pos': row.pos or '', 'tag': row.tag or '', 'morph': row.morph or '',
                'translation_source': row.translation_source,
            }

    def lookup_target(self, lemma: str, pos: str = ''):
        row = self.lookup(lemma, pos)
        return row['target_word'] if row else None

    def lookup_or_fetch(self, lemma: str, pos: str = '', form: str = '',
                        tag: str = '', morph: str = '',
                        auto_fetch: bool = True):
        if not lemma:
            return None
        row = self.lookup(lemma, pos)
        if row:
            return row['target_word']
        if not auto_fetch:
            return None
        translation = self.fetch_translation(lemma)
        if translation:
            self.add_or_update(lemma, translation, pos=pos, form=form,
                               tag=tag, morph=morph, source='api_argos')
            return translation
        return None

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def add_or_update(self, source_word, target_word, pos='', tag='', morph='',
                      form='', source='manual'):
        with self.Session() as s:
            row = (s.query(Dictionary)
                   .filter(Dictionary.source_word == source_word.lower(),
                           Dictionary.pos == pos).first())
            if row:
                row.target_word = target_word
                row.tag = tag or row.tag
                row.morph = morph or row.morph
                row.source_form = form or row.source_form
                row.translation_source = source
                row_id = row.id
            else:
                row = Dictionary(
                    source_word=source_word.lower(),
                    source_form=form or source_word,
                    target_word=target_word, pos=pos, tag=tag, morph=morph,
                    translation_source=source,
                )
                s.add(row)
                s.flush()
                row_id = row.id
            s.commit()
            return row_id

    def delete_by_word(self, source_word: str) -> int:
        with self.Session() as s:
            n = (s.query(Dictionary)
                 .filter(Dictionary.source_word == source_word.lower())
                 .delete(synchronize_session=False))
            s.commit()
            return n

    def delete_all(self) -> int:
        """Полностью очищает словарь. Возвращает число удалённых записей.

        Использует bulk-DELETE (одним SQL-запросом), без загрузки
        объектов в память.
        """
        with self.Session() as s:
            n = s.query(Dictionary).delete(synchronize_session=False)
            s.commit()
            return n

    def list_all(self, search: str = ''):
        with self.Session() as s:
            q = s.query(Dictionary)
            if search:
                pat = f"%{search.lower()}%"
                # SQLite по умолчанию LIKE регистронезависим только для ASCII.
                # ilike в SQLAlchemy на SQLite реализуется через lower(...) LIKE lower(...),
                # так что для латиницы и кириллицы работает корректно.
                q = q.filter(or_(Dictionary.source_word.ilike(pat),
                                 Dictionary.target_word.ilike(pat)))
            rows = q.order_by(Dictionary.source_word).all()
            return [{
                'id': r.id, 'source_word': r.source_word,
                'source_form': r.source_form, 'target_word': r.target_word,
                'pos': r.pos or '', 'tag': r.tag or '', 'morph': r.morph or '',
                'translation_source': r.translation_source or '',
            } for r in rows]

    def count(self) -> int:
        with self.Session() as s:
            return s.query(Dictionary).count()

    # ------------------------------------------------------------------
    # Импорт / экспорт
    # ------------------------------------------------------------------
    def import_file(self, uploaded_file):
        """Импорт из текстового файла.

        Формат строки: source [SEP] target [SEP] pos [SEP] tag [SEP] morph.
        SEP определяется автоматически: \\t, |, ;, запятая.
        Строки, начинающиеся с '#', игнорируются.
        Возвращает (добавлено, обновлено).
        """
        data = uploaded_file.getvalue().decode('utf-8', errors='ignore')
        added, updated = 0, 0
        for line in data.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = None
            for sep in ('\t', '|', ';', ','):
                if sep in line:
                    parts = [p.strip() for p in line.split(sep)]
                    break
            if parts is None:
                parts = [line]
            if len(parts) < 2:
                continue
            src, tgt = parts[0], parts[1]
            if not src or not tgt:
                continue
            pos = parts[2] if len(parts) > 2 else ''
            tag = parts[3] if len(parts) > 3 else ''
            morph = parts[4] if len(parts) > 4 else ''
            existed = self.lookup(src, pos) is not None
            self.add_or_update(src, tgt, pos=pos, tag=tag, morph=morph,
                               source='imported')
            if existed:
                updated += 1
            else:
                added += 1
        return added, updated

    def export_txt(self) -> bytes:
        rows = self.list_all()
        lines = ["# Словарь EN→RU",
                 "# source_word | target_word | POS | tag | morph | source"]
        for r in rows:
            lines.append(f"{r['source_word']} | {r['target_word']} | "
                         f"{r['pos']} | {r['tag']} | {r['morph']} | "
                         f"{r['translation_source']}")
        return ('\n'.join(lines) + '\n').encode('utf-8')