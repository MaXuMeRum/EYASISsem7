# app.py
from pathlib import Path
from collections import Counter, defaultdict
import base64
import io
import math
import re

from flask import (
    Flask, request, redirect, url_for,
    send_from_directory, render_template_string, abort
)
import pymorphy3
from pypdf import PdfReader
from docx import Document as DocxDocument

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import db  # <-- модуль работы с SQLite

BASE_DIR = Path(__file__).resolve().parent
DOCUMENTS_DIR = BASE_DIR / "documents"
ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}

app = Flask(__name__)
morph = pymorphy3.MorphAnalyzer()

STOP_WORDS = {
    "и","в","во","не","что","он","на","я","с","со","как","а","то","все","она",
    "так","его","но","да","ты","к","у","же","вы","за","бы","по","только","ее",
    "мне","было","вот","от","меня","еще","нет","о","из","ему","теперь","когда",
    "даже","ну","вдруг","ли","если","уже","или","ни","быть","был","него","до",
    "вас","нибудь","опять","уж","вам","ведь","там","потом","себя","ничего","ей",
    "может","они","тут","где","есть","надо","ней","для","мы","тебя","их","чем",
    "была","сам","чтоб","без","будто","чего","раз","тоже","себе","под","будет",
    "тогда","кто","этот","того","потому","этого","какой","совсем","ним","здесь",
    "этом","один","почти","мой","тем","чтобы","нее","сейчас","были","куда",
    "зачем","сказать","всех","никогда","сегодня","можно","при","наконец","два",
    "об","другой","хоть","после","над","больше","тот","через","эти","нас","про",
    "всего","них","какая","много","разве","три","эту","моя","впрочем","хорошо",
    "свою","этой","перед","иногда","лучше","чуть","том","нельзя","такой","им",
    "более","всегда","конечно","всю","между"
}

TOKEN_RE = re.compile(r"[А-Яа-яЁёA-Za-z0-9]+", re.UNICODE)
QUERY_RE = re.compile(
    r"\(|\)|\b(?:AND|OR|NOT|И|ИЛИ|НЕ)\b|[А-Яа-яЁёA-Za-z0-9]+",
    re.I | re.U
)
OPERATORS = {"AND", "OR", "NOT"}
PRECEDENCE = {"OR": 1, "AND": 2, "NOT": 3}


def html_escape(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;"))


def read_document(path):
    try:
        if path.suffix.lower() in {".txt", ".md"}:
            return path.read_text(encoding="utf-8", errors="ignore")
        if path.suffix.lower() == ".pdf":
            reader = PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        if path.suffix.lower() == ".docx":
            doc = DocxDocument(str(path))
            return "\n".join(p.text for p in doc.paragraphs)
    except Exception as e:
        return f"[Ошибка чтения: {e}]"
    return ""


class SearchIndex:
    """
    Обёртка над SQLite.
    - documents / inverted / idf / term_ids живут в памяти (для скорости);
    - сами тексты, постинги и веса — в БД index.db.
    """

    def __init__(self):
        self.documents = {}          # {doc_id: {...}}
        self.df = Counter()
        self.idf = {}
        self.inverted = defaultdict(set)
        self.term_ids = {}
        self.meta = {}

    # ---------- лемматизация ----------
    def lemma(self, word):
        word = word.lower().replace("ё", "е")
        if word in STOP_WORDS or len(word) < 2:
            return ""
        return morph.parse(word)[0].normal_form

    def terms(self, text):
        result = []
        for token in TOKEN_RE.findall(text):
            w = self.lemma(token)
            if w and w not in STOP_WORDS:
                result.append(w)
        return result

    # ---------- пересборка индекса ----------
    def rebuild(self):
        """Читает documents/, лемматизирует и сохраняет всё в SQLite."""
        db.init_db()

        files = sorted(
            p for p in DOCUMENTS_DIR.iterdir()
            if p.is_file() and p.suffix.lower() in ALLOWED_EXTENSIONS
        )

        parsed = []
        for path in files:
            text = read_document(path)
            terms = self.terms(text)
            tf = Counter(terms)
            parsed.append({
                "filename": path.name,
                "text": text,
                "terms": terms,
                "tf": tf,
            })

        db.save_index(parsed)
        self.load()

    # ---------- загрузка из БД ----------
    def load(self):
        """Загружает индекс из SQLite в память."""
        db.init_db()
        self.documents = db.load_documents()
        inv, tid = db.load_inverted()
        self.inverted = inv
        self.term_ids = tid

        conn = db.get_conn()
        self.df = Counter()
        self.idf = {}
        for r in conn.execute("SELECT lemma, df, idf FROM terms"):
            self.df[r["lemma"]] = r["df"]
            self.idf[r["lemma"]] = r["idf"]
        self.meta = db.get_meta()
        conn.close()

    @property
    def all_ids(self):
        return set(self.documents)


INDEX = SearchIndex()


def operator(token):
    return {
        "И": "AND", "ИЛИ": "OR", "НЕ": "NOT",
        "AND": "AND", "OR": "OR", "NOT": "NOT"
    }.get(token.upper())


def tokenize_query(query):
    raw = QUERY_RE.findall(query)
    out = []
    for token in raw:
        op = operator(token)
        if op:
            out.append(op)
        elif token in {"(", ")"}:
            out.append(token)
        else:
            w = INDEX.lemma(token)
            if w:
                out.append(w)

    # ЕЯ-запрос без операторов = неявное AND.
    result = []
    prev = None
    for token in out:
        if prev is not None:
            prev_operand = prev not in OPERATORS and prev != "("
            current_operand = token not in OPERATORS and token != ")"
            if (prev_operand or prev == ")") and (
                current_operand or token == "(" or token == "NOT"
            ):
                result.append("AND")
        result.append(token)
        prev = token
    return result


def postfix(tokens):
    output, stack = [], []
    for token in tokens:
        if token not in OPERATORS and token not in {"(", ")"}:
            output.append(token)
        elif token in OPERATORS:
            while stack and stack[-1] in OPERATORS and (
                PRECEDENCE[stack[-1]] > PRECEDENCE[token] or
                (PRECEDENCE[stack[-1]] == PRECEDENCE[token] and token != "NOT")
            ):
                output.append(stack.pop())
            stack.append(token)
        elif token == "(":
            stack.append(token)
        else:
            while stack and stack[-1] != "(":
                output.append(stack.pop())
            if not stack:
                raise ValueError("Несогласованные скобки")
            stack.pop()
    while stack:
        if stack[-1] in {"(", ")"}:
            raise ValueError("Несогласованные скобки")
        output.append(stack.pop())
    return output


def evaluate(post):
    stack = []
    for token in post:
        if token not in OPERATORS:
            stack.append(set(INDEX.inverted.get(token, set())))
        elif token == "NOT":
            if not stack:
                raise ValueError("Некорректное выражение после НЕ")
            stack.append(INDEX.all_ids - stack.pop())
        else:
            if len(stack) < 2:
                raise ValueError(f"Недостаточно операндов для {token}")
            b, a = stack.pop(), stack.pop()
            stack.append(a & b if token == "AND" else a | b)
    if len(stack) != 1:
        raise ValueError("Некорректный запрос")
    return stack[0]


def search(query):
    tokens = tokenize_query(query)
    if not tokens:
        return [], ""
    found = evaluate(postfix(tokens))
    qterms = list(dict.fromkeys(
        x for x in tokens if x not in OPERATORS and x not in {"(", ")"}
    ))
    results = []
    for doc_id in found:
        doc = INDEX.documents[doc_id]
        present = [x for x in qterms if x in doc["tf"]]
        score = sum(doc["weights"].get(x, 0) for x in present)
        results.append((score, doc, present))
    results.sort(key=lambda x: (-x[0], x[1]["filename"].lower()))
    return results, " ".join(tokens)


def metrics(ranked, relevant):
    retrieved = set(ranked)
    tp = len(retrieved & relevant)
    precision = tp / len(retrieved) if retrieved else 0
    recall = tp / len(relevant) if relevant else 0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0

    found, ap_sum = 0, 0
    for rank, doc_id in enumerate(ranked, 1):
        if doc_id in relevant:
            found += 1
            ap_sum += found / rank
    ap = ap_sum / len(relevant) if relevant else 0

    r = len(relevant)
    rprec = sum(x in relevant for x in ranked[:r]) / r if r else 0

    def p_at(k):
        return sum(x in relevant for x in ranked[:k]) / k if k else 0

    return {
        "Precision": precision,
        "Recall": recall,
        "F1": f1,
        "P@5": p_at(5),
        "P@10": p_at(10),
        "Average Precision (AP)": ap,
        "R-Precision": rprec
    }


def pr_chart(ranked, relevant):
    if not relevant:
        points = [(0, 0)]
    else:
        found = 0
        points = []
        for rank, doc_id in enumerate(ranked, 1):
            if doc_id in relevant:
                found += 1
            points.append((found / len(relevant), found / rank))

    fig = plt.figure(figsize=(7, 4))
    ax = fig.add_subplot(111)
    ax.plot([p[0] for p in points], [p[1] for p in points], marker="o")
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.set_title("Precision–Recall")
    ax.set_xlim(0, 1.02)
    ax.set_ylim(0, 1.02)
    ax.grid(True, alpha=.3)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


CSS = """
body{margin:0;background:#f4f6f8;color:#202124;font-family:Arial,sans-serif}
header{background:white;border-bottom:1px solid #ddd;padding:18px 28px}
nav{margin-top:12px} nav a{margin-right:18px;text-decoration:none}
main{max-width:1100px;margin:24px auto;padding:0 16px}
.card{background:white;border:1px solid #ddd;border-radius:12px;padding:20px;margin-bottom:18px}
input[type=text]{width:min(720px,90%);padding:12px;border:1px solid #bbb;border-radius:8px;font-size:16px}
button{padding:11px 16px;border:0;border-radius:8px;cursor:pointer}
.badge{display:inline-block;background:#edf1f5;border-radius:20px;padding:5px 9px;margin:2px}
.muted{color:#666}.error{color:#b00020}
table{width:100%;border-collapse:collapse}th,td{padding:10px;border-bottom:1px solid #ddd;text-align:left}
.chart{max-width:760px;width:100%}
code{background:#f0f2f5;padding:2px 5px;border-radius:4px}
"""

TEMPLATE = """
<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>СИП — информационный поиск</title><style>{{css}}</style></head>
<body><header><b>СИП — русскоязычный логический поиск</b>
<nav><a href="/">Поиск</a><a href="/upload">Загрузка файлов</a>
<a href="/index">Индекс</a><a href="/db">БД</a>
<a href="/metrics">Оценка качества</a>
<a href="/help">Помощь</a></nav></header><main>{{body|safe}}</main></body></html>
"""


def page(body):
    return render_template_string(TEMPLATE, css=CSS, body=body)


# ----------------------- Маршруты -----------------------

@app.route("/")
def home():
    q = request.args.get("q", "")
    body = f"""
    <div class="card"><h2>Поиск документов</h2>
    <form><input type="text" name="q" value="{html_escape(q)}"
    placeholder="Например: информационный поиск локальная сеть">
    <button>Найти</button></form>
    <p class="muted">Слова без операторов автоматически объединяются через И.
    Поддерживаются И, ИЛИ, НЕ и скобки.</p></div>
    """
    if q:
        try:
            results, expression = search(q)
            body += f'<div class="card"><b>Запрос:</b> {html_escape(expression)}'
            body += f'<br><b>Найдено:</b> {len(results)}</div>'
            for score, doc, present in results:
                words = " ".join(
                    f'<span class="badge">{html_escape(x)}</span>' for x in present
                ) or '<span class="muted">нет</span>'
                body += f"""
                <div class="card">
                <h3><a href="/document/{doc["id"]}" target="_blank">
                {html_escape(doc["filename"])}</a></h3>
                <b>Слова запроса в документе:</b> {words}
                <p class="muted">Вес для сортировки: {score:.4f}</p>
                </div>"""
        except ValueError as e:
            body += f'<div class="card error">{html_escape(e)}</div>'
    return page(body)


@app.route("/upload", methods=["GET", "POST"])
def upload():
    message = ""
    error = ""
    if request.method == "POST":
        files = request.files.getlist("files")
        count = 0
        for f in files:
            if not f or not f.filename:
                continue
            name = Path(f.filename).name
            ext = Path(name).suffix.lower()
            if ext not in ALLOWED_EXTENSIONS:
                error += f"Пропущен {html_escape(name)}: формат не поддерживается.<br>"
                continue
            target = DOCUMENTS_DIR / name
            if target.exists():
                stem, suffix, n = target.stem, target.suffix, 2
                while (DOCUMENTS_DIR / f"{stem}_{n}{suffix}").exists():
                    n += 1
                target = DOCUMENTS_DIR / f"{stem}_{n}{suffix}"
            f.save(str(target))
            count += 1
        if count:
            INDEX.rebuild()
            message = f"Загружено файлов: {count}. Индекс перестроен и сохранён в SQLite."

    files = sorted(
        p.name for p in DOCUMENTS_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in ALLOWED_EXTENSIONS
    )
    rows = "".join(
        f"""<tr><td>{html_escape(name)}</td><td>
        <form method="post" action="/delete/{name}">
        <button>Удалить</button></form></td></tr>""" for name in files
    ) or "<tr><td colspan=2>Файлов пока нет.</td></tr>"

    body = f"""
    <div class="card"><h2>Загрузка файлов с компьютера</h2>
    <form method="post" enctype="multipart/form-data">
      <input type="file" name="files" multiple accept=".txt,.md,.pdf,.docx">
      <button type="submit">Загрузить и индексировать</button>
    </form>
    <p class="muted">Файлы хранятся в папке <code>documents</code>,
    а индексы — в базе <code>index.db</code> (SQLite). Можно выбрать сразу
    несколько файлов.</p>
    {"<p><b>"+message+"</b></p>" if message else ""}
    {"<p class=error>"+error+"</p>" if error else ""}
    </div>
    <div class="card"><h3>Загруженные документы</h3>
    <table><tr><th>Файл</th><th>Действие</th></tr>{rows}</table></div>
    """
    return page(body)


@app.route("/delete/<path:name>", methods=["POST"])
def delete(name):
    target = DOCUMENTS_DIR / Path(name).name
    if target.exists() and target.is_file():
        target.unlink()
    INDEX.rebuild()
    return redirect(url_for("upload"))


@app.route("/document/<int:doc_id>")
def document(doc_id):
    doc = INDEX.documents.get(doc_id)
    if not doc:
        abort(404)
    return send_from_directory(DOCUMENTS_DIR, doc["filename"])


@app.route("/index")
def index_page():
    rows = ""
    for doc in INDEX.documents.values():
        kw = ", ".join(f"{w} ({v:.2f})" for w, v in doc["keywords"])
        rows += f"""<tr><td>{doc["id"]}</td><td>{html_escape(doc["filename"])}</td>
        <td>{html_escape(kw)}</td></tr>"""
    body = f"""
    <div class="card"><h2>Модуль индексирования</h2>
    <p>Документов в индексе: <b>{len(INDEX.documents)}</b></p>
    <p>Уникальных терминов: <b>{len(INDEX.idf)}</b></p>
    <p>Вес термина: <code>A_ij = Q_ij × B_i</code>,
    где <code>B_i = ln(N / df_i)</code>.</p>
    <p class="muted">Индекс хранится в SQLite: <code>{html_escape(str(db.DB_PATH))}</code></p>
    </div>
    <div class="card"><table><tr><th>ID</th><th>Документ</th>
    <th>Ключевые слова</th></tr>{rows or
    "<tr><td colspan=3>Индекс пуст.</td></tr>"}</table></div>"""
    return page(body)


@app.route("/reindex")
def reindex():
    INDEX.rebuild()
    return redirect(url_for("index_page"))


@app.route("/db")
def db_page():
    meta = db.get_meta()

    # Статистика по таблицам
    conn = db.get_conn()
    counts = {
        "documents": conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
        "terms":     conn.execute("SELECT COUNT(*) FROM terms").fetchone()[0],
        "postings":  conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0],
    }

    # Топ-20 терминов по df
    top_terms = conn.execute(
        "SELECT lemma, df, idf FROM terms ORDER BY df DESC, lemma LIMIT 20"
    ).fetchall()
    conn.close()

    term_rows = "".join(
        f"<tr><td>{html_escape(r['lemma'])}</td>"
        f"<td>{r['df']}</td><td>{r['idf']:.4f}</td></tr>"
        for r in top_terms
    )

    body = f"""
    <div class="card"><h2>Хранилище индексов (SQLite)</h2>
    <p>Файл БД: <code>{html_escape(str(db.DB_PATH))}</code></p>
    <p>Последняя индексация: <b>{html_escape(meta.get("built_at", "—"))}</b></p>
    <p>Всего документов N = <b>{html_escape(meta.get("N", "0"))}</b></p>
    <table>
      <tr><th>Таблица</th><th>Записей</th></tr>
      <tr><td>documents</td><td>{counts["documents"]}</td></tr>
      <tr><td>terms</td><td>{counts["terms"]}</td></tr>
      <tr><td>postings</td><td>{counts["postings"]}</td></tr>
    </table>
    <p><a href="/reindex">Переиндексировать</a></p>
    </div>

    <div class="card"><h3>Топ-20 терминов по df</h3>
    <table><tr><th>Термин</th><th>df</th><th>idf = ln(N/df)</th></tr>
    {term_rows or "<tr><td colspan=3>Пусто.</td></tr>"}
    </table></div>
    """
    return page(body)


@app.route("/metrics", methods=["GET", "POST"])
def metrics_page():
    q = request.values.get("q", "")
    rel_text = request.values.get("relevant", "")
    result = ""
    if request.method == "POST" and q:
        try:
            results, _ = search(q)
            ranked = [x[1]["id"] for x in results]
            relevant = {
                int(x) for x in re.split(r"[,;\s]+", rel_text.strip()) if x
            } & INDEX.all_ids
            m = metrics(ranked, relevant)
            rows = "".join(
                f"<tr><td>{html_escape(k)}</td><td>{v:.4f}</td></tr>"
                for k, v in m.items()
            )
            chart = pr_chart(ranked, relevant)
            result = f"""
            <div class="card"><h3>Метрики</h3>
            <p>Выдано: {len(ranked)}, релевантных по эталону: {len(relevant)}</p>
            <table><tr><th>Метрика</th><th>Значение</th></tr>{rows}</table>
            </div>
            <div class="card"><h3>Precision–Recall</h3>
            <img class="chart" src="data:image/png;base64,{chart}">
            </div>"""
        except ValueError as e:
            result = f'<div class="card error">{html_escape(e)}</div>'

    body = f"""
    <div class="card"><h2>Оценка качества поиска</h2>
    <form method="post">
      <p><input type="text" name="q" value="{html_escape(q)}"
      placeholder="Поисковый запрос"></p>
      <p><input type="text" name="relevant" value="{html_escape(rel_text)}"
      placeholder="ID релевантных документов: 1, 3, 5"></p>
      <button>Рассчитать</button>
    </form>
    <p class="muted">Precision, Recall, F1, P@5, P@10, Average Precision,
    R-Precision и график Precision–Recall.</p></div>
    {result}"""
    return page(body)


@app.route("/help")
def help_page():
    body = """
    <div class="card"><h2>Помощь</h2>
    <h3>1. Загрузка</h3>
    <p>Откройте «Загрузка файлов», нажмите выбор файлов и выберите документы
    прямо на компьютере. Поддерживаются TXT, MD, PDF и DOCX.</p>

    <h3>2. Поиск</h3>
    <p>Запрос <code>информационный поиск</code> означает
    <code>информационный И поиск</code>.</p>
    <p>Примеры: <code>поиск И документы</code>,
    <code>поиск ИЛИ индексирование</code>,
    <code>поиск И НЕ интернет</code>,
    <code>(поиск И документы) ИЛИ индексирование</code>.</p>

    <h3>3. Индекс</h3>
    <p>Ключевые слова выделяются автоматически по формуле
    <code>A_ij = Q_ij × B_i</code>, где <code>B_i = ln(N / df_i)</code>.
    Индекс хранится в базе данных SQLite — файл <code>index.db</code>
    в папке проекта.</p>

    <h3>4. Оценка</h3>
    <p>Введите запрос и ID документов, которые эксперт считает релевантными.
    Система рассчитает метрики и построит график Precision–Recall.</p>

    <h3>5. Хранилище</h3>
    <p>В разделе «БД» можно посмотреть статистику индекса: количество
    документов, терминов, постингов и топ-20 наиболее частых терминов.
    </p>
    </div>"""
    return page(body)


if __name__ == "__main__":
    DOCUMENTS_DIR.mkdir(exist_ok=True)
    db.init_db()

    if db.db_exists_and_filled():
        # Индекс уже есть — просто загружаем (быстро!)
        INDEX.load()
        print(f"[db] Загружено документов из index.db: {len(INDEX.documents)}")
    else:
        # Первый запуск — строим индекс и сохраняем в БД
        print("[db] Индекс пуст, строю заново...")
        INDEX.rebuild()
        print(f"[db] Сохранено документов: {len(INDEX.documents)}")

    app.run(host="0.0.0.0", port=5000, debug=False)