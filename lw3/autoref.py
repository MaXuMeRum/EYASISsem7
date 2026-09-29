import os
import re
import json
import platform
import subprocess
import tempfile
from pathlib import Path
from collections import Counter
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

APP_NAME = "AutoRef — Sentence Extraction"
VERSION = "1.0"

STOPWORDS_RU = set("""и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по только ее мне было вот от меня еще нет о из ему теперь когда даже ну вдруг ли если уже или ни быть был него до вас нибудь опять уж вам ведь там потом себя ничего ей может они тут где есть надо ней для мы тебя их чем была сам чтоб без будто чего раз тоже себе под будет ж тогда кто этот того потому этого какой совсем ним здесь этом один почти мой тем чтобы нее сейчас были куда зачем сказать всех никогда сегодня можно при об обо через между""".split())

STOPWORDS_DE = set("""der die das den dem des ein eine einer einem einen eines und oder aber auch nicht ist sind war waren wird werden wurde wurden mit von zu für auf in im an am aus bei nach über unter vor hinter zwischen durch gegen ohne um als wie dass daß es er sie wir ihr ich du man sein seine seiner seinem seinen ihre ihrer ihrem ihren dies diese dieser diesem diesen dieses jene jeder jede jedem jeden jedes mehr noch nur sehr schon hier dort dann wenn weil wobei deren dessen dazu dabei sich bis vom zum zur""".split())

DOMAIN_TERMS = {
    "Медицина": {
        "ru": set("исследование пациент лечение диагностика заболевание терапия препарат симптом клинический анализ медицинский врач больной терапевтический хирургический биомаркер профилактика эффективность".split()),
        "de": set("patient behandlung diagnose krankheit therapie medikament symptom klinisch analyse medizinisch arzt chirurgisch biomarker prävention wirksamkeit untersuchung studie".split())
    },
    "Изобразительное искусство": {
        "ru": set("картина живопись художник композиция цвет свет форма образ портрет пейзаж стиль полотно искусство перспектива контраст сюжет критика эстетика визуальный".split()),
        "de": set("gemälde malerei künstler komposition farbe licht form bild porträt landschaft stil kunstwerk kunst perspektive kontrast handlung kritik ästhetik visuell".split())
    }
}

def read_txt(path):
    for enc in ("utf-8", "utf-8-sig", "cp1251", "latin-1"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            pass
    raise ValueError("Не удалось определить кодировку TXT-файла.")

def read_docx(path):
    try:
        from docx import Document
    except ImportError:
        raise ImportError("Для DOCX установите: pip install python-docx")
    return "\n".join(p.text.strip() for p in Document(path).paragraphs if p.text.strip())

def read_pdf(path):
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ImportError("Для PDF установите: pip install pypdf")
    return "\n".join((p.extract_text() or "") for p in PdfReader(path).pages)

def load_document(path):
    ext = Path(path).suffix.lower()
    if ext == ".txt": return read_txt(path)
    if ext == ".docx": return read_docx(path)
    if ext == ".pdf": return read_pdf(path)
    raise ValueError("Формат файла не поддерживается.")

def normalize_text(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()

def split_sentences(text):
    text = normalize_text(text)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-ZА-ЯÄÖÜЁ«„])", text)
    return [re.sub(r"\s+", " ", s.strip()) for s in parts if len(s.strip()) >= 20]

def tokenize(text):
    return re.findall(r"[A-Za-zА-Яа-яÄÖÜäöüßЁё]{3,}", text.lower())

def calculate_keywords(text, language, domain, limit=15):
    stop = STOPWORDS_RU if language == "ru" else STOPWORDS_DE
    freq = Counter(w for w in tokenize(text) if w not in stop and len(w) >= 4)
    domain_words = DOMAIN_TERMS.get(domain, {}).get(language, set())
    scored = {}
    for word, count in freq.items():
        score = count * (2.5 if word in domain_words else 1)
        score *= 1 + min(len(word), 15) / 100
        scored[word] = score
    return [w for w, _ in sorted(scored.items(), key=lambda x: x[1], reverse=True)[:limit]]

def sentence_score(sentence, keywords, domain, language):
    words = tokenize(sentence)
    domain_words = DOMAIN_TERMS.get(domain, {}).get(language, set())
    score = sum(3 for w in words if w in keywords)
    score += sum(2 for w in words if w in domain_words)
    if 10 <= len(words) <= 45:
        score += 1
    return score

def extract_summary(text, language, domain, percent=25):
    sentences = split_sentences(text)
    if not sentences:
        return []
    keywords = calculate_keywords(text, language, domain, 20)
    scored = []
    for i, sentence in enumerate(sentences):
        score = sentence_score(sentence, keywords, domain, language)
        if i < 3:
            score += 1
        scored.append((score, i, sentence))
    number = min(max(1, int(len(sentences) * percent / 100)), 15)
    selected = sorted(scored, reverse=True)[:number]
    return [x[2] for x in sorted(selected, key=lambda x: x[1])]


def create_result_text(source_path, language, domain, summary, keywords):
    lang = "Русский" if language == "ru" else "Немецкий"
    lines = [
        "=" * 70, "АВТОМАТИЧЕСКОЕ РЕФЕРИРОВАНИЕ",
        "Sentence Extraction", "=" * 70, "",
        f"Исходный документ: {os.path.basename(source_path)}",
        f"Язык: {lang}", f"Предметная область: {domain}", "",
        "Ссылка на исходный документ:",
        Path(source_path).resolve().as_uri(), "",
        "-" * 70, "РАЗДЕЛ 1. КЛАССИЧЕСКИЙ РЕФЕРАТ", "-" * 70
    ]
    lines.extend(summary)
    lines += ["", "-" * 70, "РАЗДЕЛ 2. РЕФЕРАТ В ВИДЕ КЛЮЧЕВЫХ СЛОВ", "-" * 70, ", ".join(keywords)]
    return "\n".join(lines)

def create_html(source_path, language, domain, summary, keywords):
    lang = "Русский" if language == "ru" else "Немецкий"
    uri = Path(source_path).resolve().as_uri()
    paragraphs = "\n".join(f"<p>{s}</p>" for s in summary)
    return f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<title>Автоматическое реферирование</title>
<style>body{{font-family:Arial,sans-serif;margin:40px;line-height:1.6}}h1{{color:#263238}}h2{{color:#37474F;border-bottom:1px solid #ccc}}.info{{background:#f4f6f7;padding:15px;border-radius:8px}}.keywords{{background:#eef4ff;padding:15px;border-radius:8px}}</style>
</head><body><h1>Автоматическое реферирование</h1>
<div class="info"><p><b>Методика:</b> Sentence Extraction</p>
<p><b>Исходный документ:</b> {os.path.basename(source_path)}</p>
<p><b>Язык:</b> {lang}</p><p><b>Предметная область:</b> {domain}</p>
<p><b>Источник:</b> <a href="{uri}">Открыть исходный документ</a></p></div>
<h2>1. Классический реферат</h2>{paragraphs}
<h2>2. Реферат в виде списка ключевых слов</h2><div class="keywords">{", ".join(keywords)}</div>
</body></html>"""

def print_file(filename):
    try:
        if platform.system() == "Windows":
            os.startfile(os.path.abspath(filename), "print")
        elif platform.system() == "Darwin":
            subprocess.run(["open", filename])
        else:
            subprocess.run(["lp", filename])
    except Exception as e:
        messagebox.showerror("Ошибка печати", str(e))

class AutoRefApp:
    def __init__(self, root):
        self.root = root
        root.title(f"{APP_NAME} {VERSION}")
        root.geometry("1100x720")
        root.minsize(850, 600)
        self.source_path = None
        self.source_text = ""
        self.language = "ru"
        self.domain = "Медицина"
        self.summary, self.keywords = [], []
        self.create_interface()

    def create_interface(self):
        main = ttk.Frame(self.root, padding=10); main.pack(fill="both", expand=True)
        ttk.Label(main, text=APP_NAME, font=("Arial", 18, "bold")).pack(pady=(0,10))
        settings = ttk.LabelFrame(main, text="Параметры"); settings.pack(fill="x", pady=5)
        ttk.Label(settings,text="Язык:").grid(row=0,column=0,padx=5,pady=7)
        self.language_combo=ttk.Combobox(settings,values=["Русский","Немецкий"],state="readonly",width=15); self.language_combo.current(0); self.language_combo.grid(row=0,column=1,padx=5)
        ttk.Label(settings,text="Предметная область:").grid(row=0,column=2,padx=5)
        self.domain_combo=ttk.Combobox(settings,values=["Медицина","Изобразительное искусство"],state="readonly",width=28); self.domain_combo.current(0); self.domain_combo.grid(row=0,column=3,padx=5)
        ttk.Label(settings,text="Размер реферата:").grid(row=0,column=4,padx=5)
        self.percent_combo=ttk.Combobox(settings,values=["15%","20%","25%","30%","35%"],state="readonly",width=8); self.percent_combo.current(2); self.percent_combo.grid(row=0,column=5,padx=5)
        toolbar=ttk.Frame(main); toolbar.pack(fill="x",pady=8)
        buttons=[("Открыть документ",self.open_document),("Построить реферат",self.create_summary),("Сохранить TXT",self.save_txt),("Сохранить HTML",self.save_html),("Печать",self.print_result),("Help",self.show_help)]
        for i,(txt,cmd) in enumerate(buttons):
            b=ttk.Button(toolbar,text=txt,command=cmd); b.pack(side="right" if txt=="Help" else "left",padx=3)
        self.file_label=ttk.Label(main,text="Документ не выбран."); self.file_label.pack(anchor="w",pady=3)
        panes=ttk.PanedWindow(main,orient=tk.HORIZONTAL); panes.pack(fill="both",expand=True)
        left=ttk.LabelFrame(panes,text="Исходный документ"); right=ttk.LabelFrame(panes,text="Результат реферирования")
        panes.add(left,weight=1); panes.add(right,weight=1)
        self.source_text_box=scrolledtext.ScrolledText(left,wrap=tk.WORD,font=("Arial",10)); self.source_text_box.pack(fill="both",expand=True,padx=5,pady=5)
        self.result_text_box=scrolledtext.ScrolledText(right,wrap=tk.WORD,font=("Arial",10)); self.result_text_box.pack(fill="both",expand=True,padx=5,pady=5)
        self.status=ttk.Label(main,text="Готово."); self.status.pack(anchor="w",pady=5)

    def open_document(self):
        filename=filedialog.askopenfilename(title="Открыть документ",filetypes=[("Текстовые документы","*.txt"),("Word","*.docx"),("PDF","*.pdf"),("Все файлы","*.*")])
        if not filename:return
        try:
            text=load_document(filename)
            if not text.strip(): raise ValueError("Документ не содержит текста.")
            self.source_path,self.source_text=filename,text
            self.source_text_box.delete("1.0",tk.END); self.source_text_box.insert(tk.END,text)
            self.file_label.config(text=f"Файл: {filename}"); self.status.config(text="Документ загружен.")
        except Exception as e: messagebox.showerror("Ошибка",str(e))

    def create_summary(self):
        if not self.source_text:
            messagebox.showwarning("Нет документа","Сначала откройте исходный документ."); return
        language="ru" if self.language_combo.get()=="Русский" else "de"
        domain=self.domain_combo.get(); percent=int(self.percent_combo.get().replace("%",""))
        self.language,self.domain=language,domain
        self.status.config(text="Выполняется анализ..."); self.root.update_idletasks()
        try:
            self.summary=extract_summary(self.source_text,language,domain,percent)
            self.keywords=calculate_keywords(self.source_text,language,domain,15)
            result=create_result_text(self.source_path,language,domain,self.summary,self.keywords)
            self.result_text_box.delete("1.0",tk.END); self.result_text_box.insert(tk.END,result)
            self.status.config(text=f"Готово. Предложений: {len(self.summary)}. Ключевых слов: {len(self.keywords)}.")
        except Exception as e: messagebox.showerror("Ошибка",str(e))

    def save_txt(self):
        if not self.summary: messagebox.showwarning("Нет результата","Сначала постройте реферат."); return
        filename=filedialog.asksaveasfilename(title="Сохранить результат",defaultextension=".txt",filetypes=[("TXT","*.txt")])
        if not filename:return
        with open(filename,"w",encoding="utf-8") as f: f.write(self.result_text_box.get("1.0",tk.END))
        messagebox.showinfo("Сохранение","Результат сохранен.")

    def save_html(self):
        if not self.summary: messagebox.showwarning("Нет результата","Сначала постройте реферат."); return
        filename=filedialog.asksaveasfilename(title="Сохранить HTML",defaultextension=".html",filetypes=[("HTML","*.html")])
        if not filename:return
        with open(filename,"w",encoding="utf-8") as f: f.write(create_html(self.source_path,self.language,self.domain,self.summary,self.keywords))
        messagebox.showinfo("Сохранение","HTML-файл сохранен.")

    def print_result(self):
        if not self.summary: messagebox.showwarning("Нет результата","Сначала постройте реферат."); return
        html=create_html(self.source_path,self.language,self.domain,self.summary,self.keywords)
        temp=tempfile.NamedTemporaryFile(delete=False,suffix=".html",mode="w",encoding="utf-8"); temp.write(html); temp.close()
        print_file(temp.name)

    def show_help(self):
        win=tk.Toplevel(self.root); win.title("Справка"); win.geometry("700x550")
        box=scrolledtext.ScrolledText(win,wrap=tk.WORD,font=("Arial",11)); box.pack(fill="both",expand=True,padx=10,pady=10)
        help_text="""АВТОМАТИЧЕСКОЕ РЕФЕРИРОВАНИЕ
Sentence Extraction

Назначение:
Программа выполняет автоматическое реферирование документов на русском и немецком языках.

Предметные области:
1. Научные статьи по медицине.
2. Критика предметов изобразительного искусства.

Порядок работы:
1. Открыть документ.
2. Выбрать язык.
3. Выбрать предметную область.
4. Выбрать размер реферата.
5. Нажать «Построить реферат».

Результат содержит:
1. Классический реферат.
2. Список ключевых слов.

Sentence Extraction:
для каждого предложения рассчитывается информативность с учетом ключевых слов,
терминов предметной области и положения предложения.

Сохранение:
TXT — текстовый результат.
HTML — форматированный результат с активной ссылкой на исходный документ.


Печать:
результат передается стандартной системе печати ОС."""
        box.insert("1.0",help_text); box.config(state="disabled")

def main():
    root=tk.Tk()
    try:
        style=ttk.Style()
        if "vista" in style.theme_names(): style.theme_use("vista")
        elif "clam" in style.theme_names(): style.theme_use("clam")
    except Exception: pass
    AutoRefApp(root)
    root.mainloop()

if __name__=="__main__":
    main()
