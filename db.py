# db.py
import sqlite3
from pathlib import Path
from collections import Counter, defaultdict
import math

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "index.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Создаёт схему БД, если её нет."""
    conn = get_conn()
    cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS documents (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        filename    TEXT    NOT NULL UNIQUE,
        text        TEXT    NOT NULL,
        length      INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS terms (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        lemma       TEXT    NOT NULL UNIQUE,
        df          INTEGER NOT NULL DEFAULT 0,
        idf         REAL    NOT NULL DEFAULT 0.0
    );

    CREATE TABLE IF NOT EXISTS postings (
        term_id     INTEGER NOT NULL,
        doc_id      INTEGER NOT NULL,
        tf          INTEGER NOT NULL,
        weight      REAL    NOT NULL,
        PRIMARY KEY (term_id, doc_id),
        FOREIGN KEY (term_id) REFERENCES terms(id)   ON DELETE CASCADE,
        FOREIGN KEY (doc_id)  REFERENCES documents(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS meta (
        key   TEXT PRIMARY KEY,
        value TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_postings_doc  ON postings(doc_id);
    CREATE INDEX IF NOT EXISTS idx_postings_term ON postings(term_id);
    CREATE INDEX IF NOT EXISTS idx_terms_lemma   ON terms(lemma);
    """)
    conn.commit()
    conn.close()


def clear_index():
    """Полная очистка индекса (документы остаются)."""
    conn = get_conn()
    conn.executescript("""
        DELETE FROM postings;
        DELETE FROM terms;
        DELETE FROM documents;
        DELETE FROM sqlite_sequence WHERE name IN ('documents','terms');
    """)
    conn.commit()
    conn.close()


def save_index(parsed_docs):
    """
    parsed_docs: список словарей:
      {
        'filename': str,
        'text': str,
        'tf': Counter({lemma: count}),
        'terms': list[lemma],
      }
    Пересчитывает df/idf/weights и сохраняет всё в БД.
    """
    conn = get_conn()
    cur = conn.cursor()

    # 1. Чистим всё (полная переиндексация)
    cur.executescript("""
        DELETE FROM postings;
        DELETE FROM terms;
        DELETE FROM documents;
        DELETE FROM sqlite_sequence WHERE name IN ('documents','terms');
    """)

    N = len(parsed_docs)
    if N == 0:
        conn.commit()
        conn.close()
        return

    # 2. df по всем документам
    df = Counter()
    for d in parsed_docs:
        for term in d["tf"]:
            df[term] += 1

    # 3. idf: B_i = ln(N / df_i)
    idf = {t: math.log(N / c) if c else 0.0 for t, c in df.items()}

    # 4. Вставляем документы, получаем их id
    doc_ids = {}
    for d in parsed_docs:
        cur.execute(
            "INSERT INTO documents(filename, text, length) VALUES (?,?,?)",
            (d["filename"], d["text"], len(d["terms"]))
        )
        doc_ids[d["filename"]] = cur.lastrowid

    # 5. Вставляем термины
    term_ids = {}
    for lemma, dfv in df.items():
        cur.execute(
            "INSERT INTO terms(lemma, df, idf) VALUES (?,?,?)",
            (lemma, dfv, idf[lemma])
        )
        term_ids[lemma] = cur.lastrowid

    # 6. Вставляем постинги: weight = tf * idf
    postings = []
    for d in parsed_docs:
        did = doc_ids[d["filename"]]
        for lemma, tf in d["tf"].items():
            tid = term_ids[lemma]
            w = tf * idf[lemma]
            postings.append((tid, did, tf, w))
    cur.executemany(
        "INSERT INTO postings(term_id, doc_id, tf, weight) VALUES (?,?,?,?)",
        postings
    )

    # 7. meta
    cur.execute("INSERT OR REPLACE INTO meta(key,value) VALUES ('N',?)", (str(N),))
    cur.execute("INSERT OR REPLACE INTO meta(key,value) VALUES ('built_at',datetime('now'))")

    conn.commit()
    conn.close()


def load_documents():
    """Возвращает словарь {doc_id: {'id','filename','text',...}} + ключевые слова."""
    conn = get_conn()

    docs = {}
    for row in conn.execute("SELECT id, filename, text FROM documents ORDER BY id"):
        docs[row["id"]] = {
            "id": row["id"],
            "filename": row["filename"],
            "text": row["text"],
            "tf": {},
            "weights": {},
            "keywords": [],
        }

    # tf + weights
    for row in conn.execute(
        "SELECT term_id, doc_id, tf, weight FROM postings"
    ):
        d = docs.get(row["doc_id"])
        if not d:
            continue
        d["tf"][row["term_id"]] = row["tf"]
        d["weights"][row["term_id"]] = row["weight"]

    # lemma map
    term_lemma = {r["id"]: r["lemma"] for r in conn.execute("SELECT id, lemma FROM terms")}

    # Переводим tf/weights в lemma-ключи и считаем ключевые слова
    for d in docs.values():
        d["tf"] = {term_lemma[t]: v for t, v in d["tf"].items()}
        d["weights"] = {term_lemma[t]: v for t, v in d["weights"].items()}
        d["keywords"] = sorted(
            d["weights"].items(),
            key=lambda x: (-x[1], -d["tf"][x[0]], x[0])
        )[:15]

    conn.close()
    return docs


def load_inverted():
    """Возвращает (inverted: {lemma: set(doc_id)}, term_ids: {lemma: term_id})."""
    conn = get_conn()
    term_lemma = {r["id"]: r["lemma"] for r in conn.execute("SELECT id, lemma FROM terms")}
    term_ids = {v: k for k, v in term_lemma.items()}

    inverted = defaultdict(set)
    for row in conn.execute("SELECT term_id, doc_id FROM postings"):
        inverted[term_lemma[row["term_id"]]].add(row["doc_id"])

    conn.close()
    return inverted, term_ids


def get_meta():
    conn = get_conn()
    meta = {r["key"]: r["value"] for r in conn.execute("SELECT key,value FROM meta")}
    conn.close()
    return meta


def db_exists_and_filled():
    if not DB_PATH.exists():
        return False
    conn = get_conn()
    try:
        row = conn.execute("SELECT COUNT(*) AS c FROM documents").fetchone()
        return row["c"] > 0
    except sqlite3.OperationalError:
        return False
    finally:
        conn.close()