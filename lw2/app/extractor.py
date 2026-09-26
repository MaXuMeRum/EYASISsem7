from pathlib import Path
import fitz


def extract_pdf_text(path: str) -> str:
    doc = fitz.open(path)
    try:
        parts = []
        for page in doc:
            parts.append(page.get_text("text"))
        return "\n".join(parts).strip()
    finally:
        doc.close()


def pdf_page_count(path: str) -> int:
    doc = fitz.open(path)
    try:
        return len(doc)
    finally:
        doc.close()
