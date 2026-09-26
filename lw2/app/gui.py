import sys
import os
import platform
import subprocess
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QTableWidget, QTableWidgetItem,
    QMessageBox, QTextEdit, QComboBox, QGroupBox, QHeaderView, QDialog
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from .extractor import extract_pdf_text, pdf_page_count
from .methods import identify, NEURAL
from .report import build_report, save_txt, save_csv

class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Справка")
        self.resize(720, 520)
        layout = QVBoxLayout(self)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(
"""СПРАВКА ПО ПРОГРАММЕ

Назначение
Программа определяет язык PDF-документов: русский или немецкий.

1. Добавление документов
Нажмите «Добавить PDF» и выберите один или несколько PDF-файлов.
В таблице появится активная ссылка на каждый документ.

2. Выбор метода
• Коротких слов — использует частотность характерных служебных слов.
• Алфавитный — анализирует алфавит, символы и характерные сочетания.
• Нейросетевой — MLP классификатор по символьным TF-IDF признакам.

3. Идентификация
Нажмите «Определить язык». Для каждого PDF будет извлечен текст и
показан результат с оценкой уверенности.

4. Нейросетевой метод
Для учебного запуска используется встроенный демонстрационный корпус.
Для улучшения результата положите TXT-файлы в:
corpus/ru/ и corpus/de/
и нажмите «Переобучить нейросеть».

5. Сохранение
«Сохранить TXT» сохраняет полный отчет.
«Сохранить CSV» сохраняет табличные результаты.

6. Печать
Кнопка «Печать» открывает системный диалог печати.

Ограничение
PDF должен содержать текстовый слой. Если это скан, сначала требуется OCR.
"""
        )
        layout.addWidget(text)
        btn = QPushButton("Закрыть")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Идентификатор языка PDF — Русский / Немецкий")
        self.resize(1200, 760)
        self.files = []
        self.results = []
        self.last_report = ""
        self._build()

    def _build(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        title = QLabel("Идентификация языка текстовых PDF")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        root.addWidget(title)

        info = QLabel("Варианты: Русский и Немецкий | Методы: коротких слов, алфавитный, нейросетевой")
        root.addWidget(info)

        controls = QHBoxLayout()
        self.add_btn = QPushButton("Добавить PDF")
        self.add_btn.clicked.connect(self.add_files)
        controls.addWidget(self.add_btn)

        self.clear_btn = QPushButton("Очистить")
        self.clear_btn.clicked.connect(self.clear_files)
        controls.addWidget(self.clear_btn)

        controls.addWidget(QLabel("Метод:"))
        self.method = QComboBox()
        self.method.addItems(["Коротких слов", "Алфавитный", "Нейросетевой"])
        controls.addWidget(self.method)

        self.run_btn = QPushButton("Определить язык")
        self.run_btn.clicked.connect(self.identify_all)
        controls.addWidget(self.run_btn)

        self.train_btn = QPushButton("Переобучить нейросеть")
        self.train_btn.clicked.connect(self.retrain)
        controls.addWidget(self.train_btn)

        help_btn = QPushButton("Справка")
        help_btn.clicked.connect(lambda: HelpDialog(self).exec())
        controls.addWidget(help_btn)
        root.addLayout(controls)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["№", "Документ", "Активная ссылка", "Страниц", "Язык", "Уверенность"]
        )
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        root.addWidget(self.table)

        stat_box = QGroupBox("Сводная статистика")
        stat_layout = QVBoxLayout(stat_box)
        self.stats = QLabel("Документы не обработаны.")
        self.stats.setStyleSheet("font-size: 15px;")
        stat_layout.addWidget(self.stats)
        root.addWidget(stat_box)

        bottom = QHBoxLayout()
        self.save_txt_btn = QPushButton("Сохранить TXT")
        self.save_txt_btn.clicked.connect(self.save_txt)
        bottom.addWidget(self.save_txt_btn)
        self.save_csv_btn = QPushButton("Сохранить CSV")
        self.save_csv_btn.clicked.connect(self.save_csv)
        bottom.addWidget(self.save_csv_btn)
        self.print_btn = QPushButton("Печать")
        self.print_btn.clicked.connect(self.print_report)
        bottom.addWidget(self.print_btn)
        root.addLayout(bottom)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("Журнал работы программы…")
        root.addWidget(self.log)

        self.statusBar().showMessage("Готово. Добавьте PDF-файлы.")

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Выберите PDF-файлы", "", "PDF files (*.pdf)"
        )
        for path in paths:
            if path not in self.files:
                self.files.append(path)
                row = self.table.rowCount()
                self.table.insertRow(row)
                self.table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
                self.table.setItem(row, 1, QTableWidgetItem(Path(path).name))
                link = QLabel(f'<a href="file:///{path.replace(chr(92), "/")}">{path}</a>')
                link.setOpenExternalLinks(True)
                self.table.setCellWidget(row, 2, link)
                try:
                    pages = pdf_page_count(path)
                except Exception:
                    pages = "?"
                self.table.setItem(row, 3, QTableWidgetItem(str(pages)))
                self.table.setItem(row, 4, QTableWidgetItem("—"))
                self.table.setItem(row, 5, QTableWidgetItem("—"))
        self.statusBar().showMessage(f"Выбрано документов: {len(self.files)}")

    def clear_files(self):
        self.files.clear()
        self.results.clear()
        self.table.setRowCount(0)
        self.stats.setText("Документы не обработаны.")
        self.log.clear()
        self.last_report = ""

    def identify_all(self):
        if not self.files:
            QMessageBox.information(self, "Нет файлов", "Сначала добавьте PDF-документы.")
            return
        method = self.method.currentText()
        self.results = []
        self.log.clear()
        for row, path in enumerate(self.files):
            try:
                text = extract_pdf_text(path)
                if len(text.strip()) < 20:
                    lang, conf, details = "Недостаточно текста", 0.0, {"символов": len(text)}
                else:
                    lang, conf, details = identify(text, method)
                pages = pdf_page_count(path)
                detail_str = "; ".join(f"{k}: {v}" for k, v in details.items())
                result = {
                    "name": Path(path).name, "path": path, "pages": pages,
                    "language": lang, "confidence": conf, "details": detail_str
                }
                self.results.append(result)
                self.table.setItem(row, 4, QTableWidgetItem(lang))
                self.table.setItem(row, 5, QTableWidgetItem(f"{conf:.1%}"))
                self.log.append(f"{Path(path).name}: {lang}, уверенность {conf:.1%}")
            except Exception as e:
                self.log.append(f"Ошибка {Path(path).name}: {e}")
                self.results.append({
                    "name": Path(path).name, "path": path, "pages": "?",
                    "language": "Ошибка", "confidence": 0.0, "details": str(e)
                })
                self.table.setItem(row, 4, QTableWidgetItem("Ошибка"))
                self.table.setItem(row, 5, QTableWidgetItem("0%"))

        ru = sum(r["language"] == "Русский" for r in self.results)
        de = sum(r["language"] == "Немецкий" for r in self.results)
        other = len(self.results) - ru - de
        self.stats.setText(
            f"Всего: {len(self.results)} | Русский: {ru} | Немецкий: {de} | "
            f"Не определен/ошибка: {other}"
        )
        self.last_report = build_report(self.results, method)
        self.statusBar().showMessage("Идентификация завершена.")

    def retrain(self):
        try:
            n = NEURAL.fit()
            QMessageBox.information(self, "Готово", f"Нейросеть переобучена на {n} текстах.")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка обучения", str(e))

    def save_txt(self):
        if not self.results:
            QMessageBox.information(self, "Нет данных", "Сначала выполните идентификацию.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить отчет", "report.txt", "Text (*.txt)")
        if path:
            save_txt(self.last_report, path)
            self.statusBar().showMessage(f"Отчет сохранен: {path}")

    def save_csv(self):
        if not self.results:
            QMessageBox.information(self, "Нет данных", "Сначала выполните идентификацию.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить CSV", "results.csv", "CSV (*.csv)")
        if path:
            save_csv(self.results, path)
            self.statusBar().showMessage(f"CSV сохранен: {path}")

    def print_report(self):
        if not self.last_report:
            QMessageBox.information(self, "Нет данных", "Сначала выполните идентификацию.")
            return

        from PySide6.QtPrintSupport import QPrinter, QPrintDialog
        from PySide6.QtGui import QTextDocument, QFont, QPageLayout, QPageSize
        from PySide6.QtCore import QMarginsF

        printer = QPrinter(QPrinter.HighResolution)
        printer.setPageSize(QPageSize(QPageSize.A4))

        # Совместимо с актуальным API PySide6:
        # setPageMargins() вызывается через QPageLayout.
        layout = printer.pageLayout()
        layout.setUnits(QPageLayout.Millimeter)
        layout.setMargins(QMarginsF(15, 15, 15, 15))
        printer.setPageLayout(layout)

        dialog = QPrintDialog(printer, self)
        if dialog.exec():
            doc = QTextDocument()
            font = QFont("Arial", 10)
            font.setStyleStrategy(QFont.PreferAntialias)
            doc.setDefaultFont(font)
            doc.setPlainText(self.last_report)
            doc.print_(printer)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Идентификатор языка PDF")
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
