"""Единая страница приложения: перевод + словарь + справка."""
import pandas as pd
import streamlit as st

from core.file_handler import FileHandler
from core.syntax_analyzer import SyntaxAnalyzer
from core.translators import SyntaxTagTranslator
from mt.dictionary_manager import DictionaryManager
from mt.mt_constants import TRANSLATION_SOURCES
from mt.mt_engine import MTEngine
from ui.help_text import HELP_TEXT


class App:
    def __init__(self):
        self.dict_mgr = DictionaryManager()
        self.engine = MTEngine(self.dict_mgr)
        self.file_handler = FileHandler()
        self._analyzers = {}
        self._tag_tr = SyntaxTagTranslator()

    def _analyzer(self, lang: str) -> SyntaxAnalyzer:
        if lang not in self._analyzers:
            self._analyzers[lang] = SyntaxAnalyzer(lang=lang)
        return self._analyzers[lang]

    # ------------------------------------------------------------------
    def run(self):
        st.title("Машинный перевод")
        tab1, tab2, tab3 = st.tabs(["Перевод", "Словарь", "Справка"])
        with tab1:
            self._render_translation()
        with tab2:
            self._render_dictionary()
        with tab3:
            self._render_help()

    # ------------------------------------------------------------------
    # Вкладка «Перевод» — три под-вкладки
    # ------------------------------------------------------------------
    def _render_translation(self):
        sub1, sub2, sub3 = st.tabs([
            "Перевод",
            "Список по частоте",
            "Дерево разбора",
        ])
        with sub1:
            self._render_translation_tab()
        with sub2:
            self._render_statistics_tab()
        with sub3:
            self._render_trees_tab()

    # ------------------------------------------------------------------
    # Под-вкладка 1: перевод
    # ------------------------------------------------------------------
    def _render_translation_tab(self):
        st.subheader("Входной текст (английский)")

        col1, col2 = st.columns([2, 1])
        with col1:
            uploaded = st.file_uploader(
                "Загрузите PDF или TXT (EN)",
                type=['pdf', 'txt'],
                key="src_file",
            )
        with col2:
            mode = st.radio(
                "Режим перевода",
                ["Прямой (пословный)", "Непрямой (трансферный)"],
                key="mt_mode",
            )
            auto_fill = st.checkbox(
                "Автопополнять словарь через Argos (офлайн)", value=True,
                key="mt_auto_fill",
            )

        source_text = ""
        if uploaded is not None:
            source_text = self.file_handler.extract_text(uploaded) or ""
            if source_text:
                with st.expander("Предпросмотр исходного текста", expanded=False):
                    st.text(source_text[:5000])

        manual_text = st.text_area(
            "Или введите текст вручную (EN)", height=120, key="manual_text",
        )
        if manual_text.strip():
            source_text = manual_text

        if st.button("Перевести", type="primary", key="translate_btn"):
            if not source_text.strip():
                st.warning("Загрузите файл или введите текст.")
            else:
                try:
                    with st.spinner("Перевод..."):
                        if mode.startswith("Прямой"):
                            res = self.engine.translate_direct(source_text,
                                                               auto_fill=auto_fill)
                        else:
                            res = self.engine.translate_transfer(source_text,
                                                                 auto_fill=auto_fill)
                    st.session_state['mt_result'] = res
                    st.session_state['mt_source'] = source_text
                    # Сбрасываем кэш разбора прошлого текста
                    st.session_state.pop('trees_source', None)
                    st.session_state.pop('trees_translation', None)
                except RuntimeError as e:
                    st.error(str(e))
                    return

        res = st.session_state.get('mt_result')
        if not res:
            st.info("Нажмите «Перевести», чтобы получить результат.")
            return

        # ---- Метрики ----
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Всего слов", res['total_words'])
        c2.metric("Переведено", res['translated_words'])
        c3.metric("Не найдено", len(res['unknown_words']))
        c4.metric("Покрытие, %", res.get('coverage', 0.0))

        if res.get('skipped_words'):
            st.caption(f"Пропущено как стоп-слова/артикли: {res['skipped_words']}")
        if res['unknown_words']:
            st.caption("Не найдены: "
                       + ", ".join(sorted(set(res['unknown_words']))))

        # ---- Перевод ----
        st.subheader("Перевод")
        st.success(res['translation'])

        # ---- Экспорт ----
        report_txt = self.engine.export_txt(res)
        try:
            report_pdf = self.file_handler.export_pdf(report_txt.decode('utf-8'))
        except Exception as e:
            report_pdf = None
            st.warning(f"Экспорт в PDF недоступен: {e}")

        c1, c2 = st.columns(2)
        with c1:
            st.download_button(
                "Скачать перевод (TXT)",
                data=report_txt,
                file_name="translation_report.txt",
                mime="text/plain; charset=utf-8",
                key="dl_txt",
            )
        with c2:
            if report_pdf:
                st.download_button(
                    "Скачать перевод (PDF)",
                    data=report_pdf,
                    file_name="translation_report.pdf",
                    mime="application/pdf",
                    key="dl_pdf",
                )

    # ------------------------------------------------------------------
    # Под-вкладка 2: список слов по частоте (вкладка 1 методички)
    # ------------------------------------------------------------------
    def _render_statistics_tab(self):
        st.subheader("Список слов по частоте с переводом и грамматикой")
        res = st.session_state.get('mt_result')
        if not res:
            st.info("Сначала выполните перевод во вкладке «Перевод».")
            return

        df = pd.DataFrame(res['statistics'])
        if df.empty:
            st.info("Нет данных.")
            return

        st.dataframe(df, width='stretch')
        st.caption(f"Всего уникальных лемм: {len(df)}")

    # ------------------------------------------------------------------
    # Под-вкладка 3: дерево разбора (вкладка 2 методички)
    # ------------------------------------------------------------------
    def _render_trees_tab(self):
        res = st.session_state.get('mt_result')
        if not res:
            st.info("Сначала выполните перевод во вкладке «Перевод».")
            return

        st.subheader("Разбор исходного текста (EN)")
        self._render_en_analysis(st.session_state.get('mt_source', ''))

        st.divider()
        st.subheader("Разбор перевода (RU)")
        self._render_synthetic_analysis(res.get('russian_sentences') or [])

    # ------------------------------------------------------------------
    # Разбор исходного текста (EN) — с выбором предложения
    # ------------------------------------------------------------------
    def _render_en_analysis(self, text: str):
        if not text.strip():
            st.info("Пустой текст.")
            return

        if 'trees_source' not in st.session_state:
            with st.spinner("Разбор исходного текста..."):
                try:
                    analyzer = self._analyzer('en')
                    doc = analyzer.analyze(text)
                    st.session_state['trees_source'] = (
                        analyzer.get_sentence_trees(doc) if doc else []
                    )
                except Exception as e:
                    st.error(f"Ошибка разбора: {e}")
                    return

        trees = st.session_state.get('trees_source') or []
        if not trees:
            st.info("Нет данных для отображения.")
            return

        options = [f"Предложение {i + 1}: {s['text'][:80]}..."
                   for i, s in enumerate(trees)]
        chosen = st.selectbox("Выберите предложение", options, key="sel_en")
        sent = trees[options.index(chosen)]

        st.markdown(f"**{sent['text']}**")
        t1, t2, t3 = st.tabs(["Дерево зависимостей",
                              "Дерево составляющих",
                              "Морфологическая разметка"])
        with t1:
            if sent.get('dependency_html'):
                # displacy отдаёт голый <svg> без обёртки, поэтому
                # вставляем его в iframe (не st.html), иначе SVG
                # сжимается или обрезается. Требует Streamlit >= 1.56.
                st.iframe(sent['dependency_html'], height=400)
            else:
                st.warning("Дерево зависимостей недоступно.")
        with t2:
            cons = sent.get('constituency_tree')
            if cons and cons.get('image_base64'):
                st.image(f"data:image/png;base64,{cons['image_base64']}",
                         caption="Дерево грамматических составляющих")
            else:
                st.warning("Дерево составляющих недоступно.")
        with t3:
            df = pd.DataFrame(sent['tokens']).rename(columns={
                'wordform': 'Словоформа',
                'lemma': 'Лемма',
                'pos': 'Часть речи',
                'tag': 'Тег',
                'tag_rus': 'Расшифровка тега',
                'dependency': 'Зависимость',
                'head_word': 'Главное слово',
            })
            st.dataframe(df, width='stretch')

    # ------------------------------------------------------------------
    # Разбор перевода (RU) — с выбором предложения
    # ------------------------------------------------------------------
    def _render_synthetic_analysis(self, synthetic_sents):
        if not synthetic_sents:
            st.info("Нет данных для анализа.")
            return

        if 'trees_translation' not in st.session_state:
            with st.spinner("Разбор перевода..."):
                try:
                    analyzer = self._analyzer('ru')
                    st.session_state['trees_translation'] = (
                        analyzer.build_trees_from_synthetic(synthetic_sents)
                    )
                except Exception as e:
                    st.error(f"Ошибка разбора: {e}")
                    return

        trees = st.session_state.get('trees_translation') or []
        if not trees:
            st.info("Нет данных для отображения.")
            return

        options = [f"Предложение {i + 1}: {s['text'][:80]}..."
                   for i, s in enumerate(trees)]
        chosen = st.selectbox("Выберите предложение", options, key="sel_ru")
        sent = trees[options.index(chosen)]

        st.markdown(f"**{sent['text']}**")
        t1, t2, t3 = st.tabs(["Дерево зависимостей",
                              "Дерево составляющих",
                              "Морфологическая разметка"])
        with t1:
            img = sent.get('dependency_image_base64')
            if img:
                st.image(f"data:image/png;base64,{img}",
                         caption="Дерево зависимостей (RU)")
            else:
                st.warning("Дерево зависимостей недоступно.")
        with t2:
            cons = sent.get('constituency_tree')
            if cons and cons.get('image_base64'):
                st.image(f"data:image/png;base64,{cons['image_base64']}",
                         caption="Дерево грамматических составляющих (RU)")
            else:
                st.warning("Дерево составляющих недоступно.")
        with t3:
            df = pd.DataFrame(sent['tokens']).rename(columns={
                'wordform': 'Словоформа',
                'lemma': 'Лемма',
                'pos': 'Часть речи',
                'tag': 'Тег',
                'tag_rus': 'Расшифровка тега',
                'dependency': 'Зависимость',
                'head_word': 'Главное слово',
            })
            st.dataframe(df, width='stretch')

    # ------------------------------------------------------------------
    # Вкладка «Словарь»
    # ------------------------------------------------------------------
    def _render_dictionary(self):
        st.subheader("Словарь EN → RU")

        c1, c2 = st.columns([3, 1])
        with c1:
            search = st.text_input("Поиск по слову или переводу",
                                   key="dict_search")
        with c2:
            st.metric("Записей", self.dict_mgr.count())

        rows = self.dict_mgr.list_all(search)
        if rows:
            # POS и Tag хранятся в БД сырыми (UPOS / Penn) — переводим
            # на лету тем же SyntaxTagTranslator, что и морфологию.
            for r in rows:
                r['pos_rus'] = self._tag_tr.get_pos_rus(r['pos']) if r['pos'] else ''
                r['tag_rus'] = self._tag_tr.get_tag_rus(r['tag'])
            df = pd.DataFrame(rows).rename(columns={
                'id': 'ID', 'source_word': 'EN', 'source_form': 'Форма',
                'target_word': 'RU', 'pos': 'POS', 'tag': 'Tag',
                'pos_rus': 'POS (RU)', 'tag_rus': 'Tag (RU)',
                'morph': 'Морфология', 'translation_source': 'Источник',
            })
            df['Источник'] = (df['Источник'].map(TRANSLATION_SOURCES)
                              .fillna(df['Источник']))
            df = df[['ID', 'EN', 'Форма', 'RU', 'POS', 'POS (RU)', 'Tag',
                     'Tag (RU)', 'Морфология', 'Источник']]
            st.dataframe(df, width='stretch')
        else:
            st.info("Словарь пуст.")

        st.divider()
        st.subheader("Добавить / изменить запись")
        col1, col2, col3 = st.columns(3)
        with col1:
            src = st.text_input("Слово (EN)", key="dict_add_src")
        with col2:
            tgt = st.text_input("Перевод (RU)", key="dict_add_tgt")
        with col3:
            pos = st.text_input("POS (например, NOUN)", key="dict_add_pos")

        col4, col5 = st.columns(2)
        with col4:
            tag = st.text_input("Penn-тег (например, NN)", key="dict_add_tag")
        with col5:
            morph = st.text_input("Морфология (например, Number=Sing)",
                                  key="dict_add_morph")
        st.caption("Тег и морфологию можно не заполнять: при автопополнении "
                   "через Argos они подставляются из spaCy автоматически.")

        b1, b2, b3 = st.columns(3)
        with b1:
            if st.button("Сохранить вручную", key="dict_save_btn"):
                if src.strip() and tgt.strip():
                    self.dict_mgr.add_or_update(
                        src.strip(), tgt.strip(),
                        pos=pos.strip().upper(),
                        tag=tag.strip(), morph=morph.strip(),
                        source='manual',
                    )
                    st.session_state['dict_flash'] = \
                        f"Сохранено: {src.strip()} → {tgt.strip()}"
                    st.rerun()
                else:
                    st.warning("Заполните оба поля.")
        with b2:
            if st.button("Получить перевод через Argos", key="dict_api_btn"):
                if src.strip():
                    with st.spinner("Перевод через Argos..."):
                        tr = self.dict_mgr.fetch_translation(src.strip())
                    if tr:
                        self.dict_mgr.add_or_update(
                            src.strip(), tr,
                            pos=pos.strip().upper(),
                            tag=tag.strip(), morph=morph.strip(),
                            source='api_argos',
                        )
                        st.session_state['dict_flash'] = \
                            f"Argos: {src.strip()} → {tr}"
                        st.rerun()
                    else:
                        st.error("Не удалось получить перевод.")
                else:
                    st.warning("Укажите слово (EN).")
        with b3:
            if st.button("Удалить по EN-слову", key="dict_del_btn"):
                if src.strip():
                    n = self.dict_mgr.delete_by_word(src.strip())
                    st.success(f"Удалено записей: {n}")
                    st.rerun()
                else:
                    st.warning("Укажите слово (EN).")

        # ---- Импорт / экспорт словаря ----
        st.divider()
        st.subheader("Импорт и экспорт словаря")
        st.caption("Формат строки: `EN <разделитель> RU [<разделитель> POS "
                   "[<разделитель> tag [<разделитель> morph]]]`. "
                   "Разделитель: `\\t`, `|`, `;` или `,`. Строки с `#` "
                   "игнорируются.")

        c1, c2 = st.columns(2)
        with c1:
            dict_file = st.file_uploader(
                "Импорт словаря (.txt, .tsv, .csv)",
                type=['txt', 'tsv', 'csv'],
                key="dict_import_file",
            )
            if dict_file is not None:
                if st.button("Импортировать", key="dict_import_btn"):
                    with st.spinner("Импорт..."):
                        added, updated = self.dict_mgr.import_file(dict_file)
                    st.session_state['dict_flash'] = \
                        f"Добавлено: {added}, обновлено: {updated}"
                    st.rerun()
        with c2:
            st.download_button(
                "Скачать словарь (.txt, Unicode)",
                data=self.dict_mgr.export_txt(),
                file_name="dictionary_en_ru.txt",
                mime="text/plain; charset=utf-8",
                key="dict_export_btn",
            )

        # ---- Полная очистка словаря ----
        st.divider()
        st.subheader("Опасная зона")
        st.caption("Действие необратимо. Перед удалением рекомендуется "
                   "скачать резервную копию кнопкой выше.")

        confirm = st.checkbox(
            "Подтверждаю полное удаление словаря",
            key="dict_confirm_delete_all",
        )
        if st.button("Очистить весь словарь", type="primary",
                     disabled=not confirm, key="dict_delete_all_btn"):
            with st.spinner("Удаление..."):
                deleted = self.dict_mgr.delete_all()
            st.session_state['dict_flash'] = f"Удалено записей: {deleted}"
            st.session_state.pop('dict_confirm_delete_all', None)
            st.rerun()

        # Сообщение переживает st.rerun() выше: сам rerun очищает вывод
        # текущего прогона, поэтому пишем его в session_state и показываем
        # уже на следующем.
        flash = st.session_state.pop('dict_flash', None)
        if flash:
            st.success(flash)

    # ------------------------------------------------------------------
    # Вкладка «Справка»
    # ------------------------------------------------------------------
    def _render_help(self):
        st.markdown(HELP_TEXT)
