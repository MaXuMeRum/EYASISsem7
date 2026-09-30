import re
from pathlib import Path

import pymupdf as fitz
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTabWidget,
    QTableWidget, QTableWidgetItem, QPushButton, QLabel, QTextEdit, QLineEdit,
    QFileDialog, QMessageBox, QComboBox, QDialog, QFormLayout, QDialogButtonBox,
    QSpinBox, QHeaderView, QListWidget
)



class DictionaryDialog(QDialog):
    def __init__(self, db, parent=None, entry=None):
        super().__init__(parent)
        self.db = db
        self.entry = entry
        self.setWindowTitle("Редактирование словаря")
        self.resize(500, 300)

        form = QFormLayout(self)
        self.en = QLineEdit(entry["lemma_en"] if entry else "")
        self.ru = QLineEdit(entry["translation_ru"] if entry else "")
        self.pos = QLineEdit(entry["pos"] if entry else "")
        self.pos_desc = QLineEdit(entry["pos_description"] if entry else "")
        self.domain = QComboBox()
        self.domain.addItems(["general", "medicine", "art"])
        if entry and entry["domain"] in ["general", "medicine", "art"]:
            self.domain.setCurrentText(entry["domain"])
        self.comment = QLineEdit(entry["comment"] if entry else "")

        form.addRow("English lemma:", self.en)
        form.addRow("Русский перевод:", self.ru)
        form.addRow("POS:", self.pos)
        form.addRow("Расшифровка POS:", self.pos_desc)
        form.addRow("Предметная область:", self.domain)
        form.addRow("Комментарий:", self.comment)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def save(self):
        self.db.upsert(
            self.en.text(), self.ru.text(), self.pos.text(),
            self.pos_desc.text(), self.domain.currentText(), self.comment.text()
        )


class MainWindow(QMainWindow):
    def __init__(self, db, nlp):
        super().__init__()
        self.db = db
        self.nlp = nlp
        self.current_text = ""
        self.current_translation = ""
        self.current_rows = []
        self.current_frequency = []
        self.current_doc = None

        self.setWindowTitle("Англо-русская система машинного перевода")
        self.resize(1450, 900)
        self.build_ui()

    def build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        top = QHBoxLayout()
        self.status = QLabel("Готово")
        self.btn_open = QPushButton("Открыть PDF")
        self.btn_translate = QPushButton("Перевести текст")
        self.btn_save = QPushButton("Сохранить TXT")
        self.btn_dictionary = QPushButton("Словарь БД")
        self.btn_help = QPushButton("Справка")
        for b in [self.btn_open, self.btn_translate, self.btn_save,
                  self.btn_dictionary, self.btn_help]:
            top.addWidget(b)
        top.addStretch()
        top.addWidget(self.status)
        root.addLayout(top)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs)

        # --- Вкладка 0: перевод ---
        translation_tab = QWidget()
        t_layout = QVBoxLayout(translation_tab)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        right = QWidget()
        ll = QVBoxLayout(left)
        rl = QVBoxLayout(right)

        ll.addWidget(QLabel("Входной текст (English)"))
        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText(
            "Введите английский текст научной статьи по медицине "
            "или критический текст об изобразительном искусстве..."
        )
        ll.addWidget(self.input_text)

        rl.addWidget(QLabel("Перевод (Русский)"))
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        rl.addWidget(self.output_text)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([700, 700])
        t_layout.addWidget(splitter)

        self.stats = QLabel("Слов: 0 | Переведено: 0")
        t_layout.addWidget(self.stats)
        self.tabs.addTab(translation_tab, "Перевод")

        # --- Вкладка 1: частотный словарь ---
        dictionary_tab = QWidget()
        d_layout = QVBoxLayout(dictionary_tab)
        filter_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Фильтр по слову или переводу...")
        self.domain_filter = QComboBox()
        self.domain_filter.addItems(["Все", "general", "medicine", "art"])
        filter_row.addWidget(self.search)
        filter_row.addWidget(self.domain_filter)
        d_layout.addLayout(filter_row)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "English lemma", "Частота", "Перевод", "POS",
            "Расшифровка", "Область", "Комментарий", "ID"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        d_layout.addWidget(self.table)

        btns = QHBoxLayout()
        self.btn_add = QPushButton("Добавить")
        self.btn_edit = QPushButton("Редактировать")
        self.btn_delete = QPushButton("Удалить")
        btns.addWidget(self.btn_add)
        btns.addWidget(self.btn_edit)
        btns.addWidget(self.btn_delete)
        btns.addStretch()
        d_layout.addLayout(btns)
        self.tabs.addTab(dictionary_tab, "Частотный словарь")

        # --- Вкладка 2: синтаксическое дерево ---
        syntax_tab = QWidget()
        s_layout = QVBoxLayout(syntax_tab)
        self.sentences = QListWidget()
        self.sentences.setMaximumHeight(130)
        s_layout.addWidget(QLabel("Выберите предложение:"))
        s_layout.addWidget(self.sentences)

        tree_buttons = QHBoxLayout()
        self.btn_dep = QPushButton("Показать Dependency Tree")
        self.btn_const = QPushButton("Показать Constituency Tree")
        tree_buttons.addWidget(self.btn_dep)
        tree_buttons.addWidget(self.btn_const)
        s_layout.addLayout(tree_buttons)

        self.dot_view = QTextEdit()
        self.dot_view.setReadOnly(True)
        self.dot_view.setPlaceholderText(
            "Здесь будет DOT-код выбранного дерева. "
            "Его можно открыть Graphviz или использовать для визуализации."
        )
        s_layout.addWidget(self.dot_view)
        self.tabs.addTab(syntax_tab, "Синтаксический разбор")

        # --- Словарь БД ---
        self.connect_signals()
        self.refresh_dictionary()

    def connect_signals(self):
        self.btn_open.clicked.connect(self.open_pdf)
        self.btn_translate.clicked.connect(self.translate)
        self.btn_save.clicked.connect(self.save_txt)
        self.btn_dictionary.clicked.connect(lambda: self.tabs.setCurrentIndex(1))
        self.btn_help.clicked.connect(self.help)
        self.search.textChanged.connect(self.refresh_dictionary)
        self.domain_filter.currentTextChanged.connect(self.refresh_dictionary)
        self.btn_add.clicked.connect(self.add_entry)
        self.btn_edit.clicked.connect(self.edit_entry)
        self.btn_delete.clicked.connect(self.delete_entry)
        self.btn_dep.clicked.connect(lambda: self.show_tree("dep"))
        self.btn_const.clicked.connect(lambda: self.show_tree("const"))
        self.sentences.currentRowChanged.connect(lambda _: self.dot_view.clear())

    def open_pdf(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Открыть PDF", "", "PDF Files (*.pdf)"
        )
        if not path:
            return
        try:
            with fitz.open(path) as doc:
                text = "\n".join(page.get_text() for page in doc)
            self.input_text.setPlainText(text)
            self.status.setText(f"Загружен PDF: {Path(path).name}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def translate(self):
        text = self.input_text.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Нет текста", "Введите или загрузите английский текст.")
            return

        try:
            self.status.setText("Анализ и перевод...")
            self.current_text = text
            self.current_doc, self.current_rows = self.nlp.analyze(text)
            self.current_translation = self.nlp.translate_text(text)

            source_count = self.nlp.word_count(text)
            translated_count = self.nlp.word_count(self.current_translation)
            # "Переведено" — количество слов исходного текста, для лемм которых
            # удалось получить русский перевод из БД или переводчика.
            self.current_frequency = self.nlp.frequency_table(
                self.current_rows, self.db
            )
            translated_lemmas = sum(
                r["frequency"] for r in self.current_frequency if r["translation"]
            )

            self.output_text.setPlainText(self.current_translation)
            self.stats.setText(
                f"Слов во входном тексте: {source_count} | "
                f"Слов в переводе: {translated_count} | "
                f"Переведено исходных слов: {translated_lemmas}"
            )
            self.load_sentences()
            self.refresh_dictionary()
            self.status.setText("Готово")

            self.db.save_history(
                text, self.current_translation, source_count, translated_lemmas
            )
        except Exception as e:
            self.status.setText("Ошибка")
            QMessageBox.critical(
                self, "Ошибка перевода",
                "Не удалось выполнить обработку.\n\n"
                + str(e) +
                "\n\nПроверьте интернет-соединение и установку моделей spaCy."
            )

    def load_sentences(self):
        self.sentences.clear()
        if not self.current_doc:
            return
        for i, sent in enumerate(self.current_doc.sents):
            self.sentences.addItem(f"{i + 1}. {sent.text.strip()}")

    def show_tree(self, tree_type):
        if not self.current_doc or self.sentences.currentRow() < 0:
            QMessageBox.information(self, "Выбор предложения",
                                    "Сначала выберите предложение.")
            return
        sentence = list(self.current_doc.sents)[self.sentences.currentRow()]
        try:
            dot = (
                self.nlp.dependency_dot(sentence)
                if tree_type == "dep"
                else self.nlp.constituency_dot(sentence)
            )
            self.dot_view.setPlainText(dot)
        except Exception as e:
            self.dot_view.setPlainText(f"Ошибка построения дерева:\n{e}")

    def refresh_dictionary(self):
        query = self.search.text().strip().lower()
        domain = self.domain_filter.currentText()
        rows = self.db.all_entries()

        self.table.setRowCount(0)
        frequency_map = {x["lemma"]: x["frequency"] for x in self.current_frequency}

        for row in rows:
            id_, lemma, ru, pos, pos_desc, dom, comment = row
            if domain != "Все" and dom != domain:
                continue
            if query and query not in lemma.lower() and query not in ru.lower():
                continue

            r = self.table.rowCount()
            self.table.insertRow(r)
            values = [
                lemma, str(frequency_map.get(lemma, 0)), ru, pos,
                pos_desc, dom, comment, str(id_)
            ]
            for c, value in enumerate(values):
                self.table.setItem(r, c, QTableWidgetItem(value))

        # Внутри текущего текста строки фактически сортируются по частоте.
        if self.current_frequency and not query and domain == "Все":
            ordered = {x["lemma"]: x for x in self.current_frequency}
            for i in range(self.table.rowCount()):
                lemma = self.table.item(i, 0).text()
                if lemma in ordered:
                    self.table.item(i, 1).setText(str(ordered[lemma]["frequency"]))

    def selected_lemma(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        return self.table.item(row, 0).text()

    def add_entry(self):
        dlg = DictionaryDialog(self.db, self)
        if dlg.exec():
            dlg.save()
            self.refresh_dictionary()

    def edit_entry(self):
        lemma = self.selected_lemma()
        if not lemma:
            QMessageBox.information(self, "Выбор", "Выберите запись.")
            return
        entry = self.db.get(lemma)
        dlg = DictionaryDialog(self.db, self, entry)
        if dlg.exec():
            dlg.save()
            self.refresh_dictionary()

    def delete_entry(self):
        lemma = self.selected_lemma()
        if not lemma:
            return
        answer = QMessageBox.question(
            self, "Удаление",
            f"Удалить запись «{lemma}» из словаря?"
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.db.delete(lemma)
            self.refresh_dictionary()

    def save_txt(self):
        if not self.current_text:
            QMessageBox.information(self, "Нет результата",
                                    "Сначала выполните перевод.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить результаты", "translation_results.txt",
            "Text files (*.txt)"
        )
        if not path:
            return

        lines = []
        lines.append("АНГЛО-РУССКАЯ СИСТЕМА МАШИННОГО ПЕРЕВОДА")
        lines.append("=" * 70)
        lines.append("")
        lines.append("ИСХОДНЫЙ ТЕКСТ (EN)")
        lines.append("-" * 70)
        lines.append(self.current_text)
        lines.append("")
        lines.append("ПЕРЕВОД (RU)")
        lines.append("-" * 70)
        lines.append(self.current_translation)
        lines.append("")
        lines.append("СТАТИСТИКА")
        lines.append("-" * 70)
        lines.append(f"Количество слов во входном тексте: {self.nlp.word_count(self.current_text)}")
        lines.append(
            f"Количество переведенных слов: "
            f"{sum(x['frequency'] for x in self.current_frequency if x['translation'])}"
        )
        lines.append("")
        lines.append("ЧАСТОТНЫЙ СЛОВАРЬ")
        lines.append("-" * 70)
        lines.append(
            "№ | Лемма | Частота | Перевод | POS | Расшифровка | Область"
        )

        for i, item in enumerate(self.current_frequency, 1):
            lines.append(
                f"{i} | {item['lemma']} | {item['frequency']} | "
                f"{item['translation']} | {item['pos']} | "
                f"{item['pos_description']} | {item['domain']}"
            )

        lines.append("")
        lines.append("ГРАММАТИЧЕСКАЯ ИНФОРМАЦИЯ")
        lines.append("-" * 70)
        for r in self.current_rows:
            lines.append(
                f"{r['word']} -> {r['lemma']} -> "
                f"{r['pos']} ({r['pos_description']})"
            )

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            QMessageBox.information(self, "Сохранено",
                                    f"Результаты сохранены в:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка сохранения", str(e))

    def help(self):
        QMessageBox.information(
            self, "Справка",
            "1. Введите английский текст или загрузите PDF.\n"
            "2. Нажмите «Перевести текст».\n"
            "3. На вкладке «Частотный словарь» доступны леммы, "
            "частота, перевод и POS с расшифровкой.\n"
            "4. Записи словаря можно добавлять, исправлять и удалять. "
            "Изменения автоматически сохраняются в SQLite.\n"
            "5. На вкладке «Синтаксический разбор» выберите предложение "
            "и постройте дерево зависимостей или составляющих.\n"
            "6. «Сохранить TXT» сохраняет исходный текст, перевод, "
            "статистику и частотный словарь в Unicode UTF-8.\n\n"
            "Предметные области: medicine и art."
        )
