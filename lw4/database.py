import sqlite3
from pathlib import Path
from typing import Optional


class DictionaryDB:
    """SQLite-словарь: английское слово/лемма -> русский перевод + грамматика."""

    def __init__(self, path="translator.db"):
        self.path = Path(path)
        self.init_db()
        self.seed_domain_dictionary()

    def connect(self):
        return sqlite3.connect(self.path)

    def init_db(self):
        with self.connect() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS dictionary (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lemma_en TEXT NOT NULL UNIQUE,
                    translation_ru TEXT NOT NULL,
                    pos TEXT DEFAULT '',
                    pos_description TEXT DEFAULT '',
                    domain TEXT DEFAULT 'general',
                    comment TEXT DEFAULT '',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS translation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_text TEXT,
                    translated_text TEXT,
                    source_word_count INTEGER,
                    translated_word_count INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def seed_domain_dictionary(self):
        # Небольшой встроенный словарь для двух заданных предметных областей.
        entries = [
            ("article", "статья", "NOUN", "существительное", "medicine"),
            ("medical", "медицинский", "ADJ", "прилагательное", "medicine"),
            ("patient", "пациент", "NOUN", "существительное", "medicine"),
            ("diagnosis", "диагноз", "NOUN", "существительное", "medicine"),
            ("treatment", "лечение", "NOUN", "существительное", "medicine"),
            ("disease", "заболевание", "NOUN", "существительное", "medicine"),
            ("symptom", "симптом", "NOUN", "существительное", "medicine"),
            ("clinical", "клинический", "ADJ", "прилагательное", "medicine"),
            ("therapy", "терапия", "NOUN", "существительное", "medicine"),
            ("diagnostic", "диагностический", "ADJ", "прилагательное", "medicine"),
            ("art", "искусство", "NOUN", "существительное", "art"),
            ("painting", "живопись", "NOUN", "существительное", "art"),
            ("sculpture", "скульптура", "NOUN", "существительное", "art"),
            ("portrait", "портрет", "NOUN", "существительное", "art"),
            ("artist", "художник", "NOUN", "существительное", "art"),
            ("composition", "композиция", "NOUN", "существительное", "art"),
            ("color", "цвет", "NOUN", "существительное", "art"),
            ("colour", "цвет", "NOUN", "существительное", "art"),
            ("canvas", "холст", "NOUN", "существительное", "art"),
            ("criticism", "критика", "NOUN", "существительное", "art"),
            ("aesthetic", "эстетический", "ADJ", "прилагательное", "art"),
            ("style", "стиль", "NOUN", "существительное", "art"),
        ]
        with self.connect() as con:
            for e in entries:
                con.execute("""
                    INSERT OR IGNORE INTO dictionary
                    (lemma_en, translation_ru, pos, pos_description, domain)
                    VALUES (?, ?, ?, ?, ?)
                """, e)

    def get(self, lemma_en: str) -> Optional[dict]:
        with self.connect() as con:
            row = con.execute("""
                SELECT id, lemma_en, translation_ru, pos, pos_description, domain, comment
                FROM dictionary WHERE lemma_en=?
            """, (lemma_en.lower(),)).fetchone()
        if not row:
            return None
        keys = ["id", "lemma_en", "translation_ru", "pos",
                "pos_description", "domain", "comment"]
        return dict(zip(keys, row))

    def upsert(self, lemma_en, translation_ru, pos="", pos_description="",
               domain="general", comment=""):
        lemma_en = lemma_en.strip().lower()
        translation_ru = translation_ru.strip()
        if not lemma_en or not translation_ru:
            return
        with self.connect() as con:
            con.execute("""
                INSERT INTO dictionary
                (lemma_en, translation_ru, pos, pos_description, domain, comment, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(lemma_en) DO UPDATE SET
                    translation_ru=excluded.translation_ru,
                    pos=excluded.pos,
                    pos_description=excluded.pos_description,
                    domain=excluded.domain,
                    comment=excluded.comment,
                    updated_at=CURRENT_TIMESTAMP
            """, (lemma_en, translation_ru, pos, pos_description, domain, comment))

    def delete(self, lemma_en):
        with self.connect() as con:
            con.execute("DELETE FROM dictionary WHERE lemma_en=?", (lemma_en.lower(),))

    def all_entries(self):
        with self.connect() as con:
            return con.execute("""
                SELECT id, lemma_en, translation_ru, pos, pos_description, domain, comment
                FROM dictionary ORDER BY lemma_en
            """).fetchall()

    def save_history(self, source, translated, source_count, translated_count):
        with self.connect() as con:
            con.execute("""
                INSERT INTO translation_history
                (source_text, translated_text, source_word_count, translated_word_count)
                VALUES (?, ?, ?, ?)
            """, (source, translated, source_count, translated_count))
