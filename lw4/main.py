import sys
from PyQt6.QtWidgets import QApplication
from ui import MainWindow
from nlp_service import NLPService
from database import DictionaryDB


def main():
    app = QApplication(sys.argv)
    db = DictionaryDB("translator.db")
    nlp = NLPService()
    window = MainWindow(db, nlp)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()