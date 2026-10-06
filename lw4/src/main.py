"""Точка входа приложения «Машинный перевод EN → RU».

Запуск:  streamlit run main.py

Порядок важен:
1. st.set_page_config() — строго до любых других st.* вызовов.
2. Импорт core.models и mt.mt_models — регистрация таблиц в Base.metadata
   до того, как DictionaryManager сделает Base.metadata.create_all().
"""
import streamlit as st

st.set_page_config(page_title="Машинный перевод EN → RU", layout="wide")

import core.models    # noqa: F401 — Base (declarative_base)
import mt.mt_models   # noqa: F401 — таблица dictionary в Base.metadata

from ui.app import App  # noqa: E402


def main():
    App().run()


if __name__ == "__main__":
    main()
