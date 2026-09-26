from pathlib import Path
import csv
from datetime import datetime

def build_report(results, method):
    total = len(results)
    ru = sum(r["language"] == "Русский" for r in results)
    de = sum(r["language"] == "Немецкий" for r in results)
    unknown = total - ru - de
    lines = [
        "ОТЧЕТ ОБ ИДЕНТИФИКАЦИИ ЯЗЫКА",
        "=" * 60,
        f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Метод: {method}",
        f"Всего документов: {total}",
        f"Русский: {ru}",
        f"Немецкий: {de}",
        f"Не определен: {unknown}",
        "",
        "РЕЗУЛЬТАТЫ",
        "-" * 60,
    ]
    for i, r in enumerate(results, 1):
        lines += [
            f"{i}. {r['name']}",
            f"   Файл: {r['path']}",
            f"   Страниц: {r['pages']}",
            f"   Язык: {r['language']}",
            f"   Уверенность: {r['confidence']:.1%}",
            f"   Детали: {r['details']}",
        ]
    return "\\n".join(lines)

def save_txt(report, path):
    Path(path).write_text(report, encoding="utf-8")

def save_csv(results, path):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Файл","Полный путь","Страницы","Язык","Уверенность","Детали"])
        for r in results:
            w.writerow([r["name"], r["path"], r["pages"], r["language"],
                        f"{r['confidence']:.4f}", r["details"]])
