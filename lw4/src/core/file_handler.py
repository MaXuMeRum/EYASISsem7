"""Чтение входных файлов (PDF, TXT) и экспорт результата в PDF."""
import os

import fitz  # PyMuPDF
from fpdf import FPDF


# Возможные пути к Unicode-шрифту с поддержкой кириллицы.
# fpdf2 требует TTF-файл, встроенные шрифты покрывают только Latin-1.
_PDF_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/DejaVuSans.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]


def _find_cyrillic_font():
    for path in _PDF_FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


class FileHandler:
    def extract_text(self, uploaded_file) -> str:
        name = uploaded_file.name.lower()
        data = uploaded_file.getvalue()
        if name.endswith('.txt'):
            return data.decode('utf-8', errors='ignore')
        if name.endswith('.pdf'):
            doc = fitz.open(stream=data, filetype="pdf")
            text = '\n'.join(page.get_text() or '' for page in doc)
            doc.close()
            return text
        return ""

    def export_pdf(self, text: str) -> bytes:
        """Рендерит произвольный текст (UTF-8) в PDF с поддержкой кириллицы."""
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        font_path = _find_cyrillic_font()
        if font_path:
            pdf.add_font("uni", "", font_path)
            pdf.set_font("uni", size=11)
        else:
            # Fallback: латиница без кириллицы. Лучше предупредить пользователя.
            pdf.set_font("Helvetica", size=11)
        for line in text.split("\n"):
            # new_x/new_y обязательны: без них второй и последующие вызовы
            # multi_cell считают ширину от текущей позиции и падают.
            pdf.multi_cell(0, 5, line, new_x="LMARGIN", new_y="NEXT")
        return bytes(pdf.output())
