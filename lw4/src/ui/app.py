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
    def _inject_styles(self):
        """Единый визуальный стиль интерфейса. Логика приложения не изменяется."""
        st.markdown("""
        <style>
        .stApp {
            background: #f5f7fb;
        }
        [data-testid="stHeader"] {
            background: rgba(245,247,251,.92);
        }
        .block-container {
            max-width: 1400px;
            padding-top: 2rem;
            padding-bottom: 3rem;
        }
        .hero {
            background: linear-gradient(135deg, #172554 0%, #1e3a8a 55%, #2563eb 100%);
            color: white;
            padding: 28px 32px;
            border-radius: 20px;
            margin-bottom: 24px;
            box-shadow: 0 12px 30px rgba(30,58,138,.18);
        }
        .hero h1 { margin: 0 0 8px 0; font-size: 2rem; }
        .hero p { margin: 0; opacity: .86; font-size: 1rem; }
        .section-card {
            background: white;
            border: 1px solid #e5e7eb;
            border-radius: 16px;
            padding: 20px;
            margin: 10px 0 18px 0;
            box-shadow: 0 4px 14px rgba(15,23,42,.05);
        }
        .section-title {
            font-size: 1.15rem;
            font-weight: 700;
            color: #172554;
            margin-bottom: 4px;
        }
        .section-caption { color: #64748b; margin-bottom: 14px; }
        div[data-testid="stMetric"] {
            background: white;
            border: 1px solid #e5e7eb;
            border-radius: 14px;
            padding: 12px 14px;
            box-shadow: 0 3px 10px rgba(15,23,42,.04);
        }
        .result-box {
            background: #eff6ff;
            border: 1px solid #bfdbfe;
            border-radius: 14px;
            padding: 18px 20px;
            line-height: 1.7;
            font-size: 1.05rem;
        }
        .danger-box {
            background: #fff7ed;
            border: 1px solid #fed7aa;
            border-radius: 14px;
            padding: 16px;
        }
        div.stButton > button, div.stDownloadButton > button {
            border-radius: 10px;
            font-weight: 600;
        }
        .small-note { color:#64748b; font-size:.88rem; }
        </style>
        """, unsafe_allow_html=True)

    def _hero(self):
        st.markdown("""
        <div class="hero">
            <h1>EN → RU · Машинный перевод</h1>
            <p>Перевод текста, частотный анализ, морфология, синтаксические деревья и управление словарём.</p>
        </div>
        """, unsafe_allow_html=True)

    def _card_start(self, title, caption=None):
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)
        if caption:
            st.markdown(f'<div class="section-caption">{caption}</div>', unsafe_allow_html=True)

    def _card_end(self):
        st.markdown('</div>', unsafe_allow_html=True)

    # ------------------------------------------------------------------
    def run(self):
        self._inject_styles()
        self._hero()

        tab1, tab2, tab3 = st.tabs(["🔤  Перевод", "📚  Словарь", "❔  Справка"])
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
            "🚀  Перевод",
            "📊  Частотный анализ",
            "🌳  Синтаксический разбор",
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
        self._card_start("Исходный текст", "Загрузите документ или вставьте английский текст вручную.")

        col1, col2 = st.columns([1.7, 1])
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

        self._card_end()
        action_col, info_col = st.columns([1, 3])
        with action_col:
            translate_clicked = st.button("🚀 Перевести", type="primary", key="translate_btn", use_container_width=True)
        with info_col:
            st.markdown('<div class="small-note">После перевода станут доступны статистика, грамматическая информация и деревья разбора.</div>', unsafe_allow_html=True)

        if translate_clicked:
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
        st.markdown("### Результат")
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
        st.markdown("#### Перевод на русский")
        st.markdown(f'<div class="result-box">{res["translation"]}</div>', unsafe_allow_html=True)

        # ---- Экспорт ----
        report_txt = self.engine.export_txt(res)
        try:
            report_pdf = self.file_handler.export_pdf(report_txt.decode('utf-8'))
        except Exception as e:
            report_pdf = None
            st.warning(f"Экспорт в PDF недоступен: {e}")

        st.markdown("#### Экспорт результата")
        c1, c2 = st.columns(2)
        with c1:
            st.download_button(
                "⬇️ Скачать перевод (TXT)",
                data=report_txt,
                file_name="translation_report.txt",
                mime="text/plain; charset=utf-8",
                key="dl_txt",
            )
        with c2:
            if report_pdf:
                st.download_button(
                    "⬇️ Скачать перевод (PDF)",
                    data=report_pdf,
                    file_name="translation_report.pdf",
                    mime="application/pdf",
                    key="dl_pdf",
                )

    # ------------------------------------------------------------------
    # Под-вкладка 2: список слов по частоте (вкладка 1 методички)
    # ------------------------------------------------------------------
    def _render_statistics_tab(self):
        st.markdown("### 📊 Список слов по частоте")
        st.caption("Леммы отсортированы по частоте; доступны перевод и грамматические характеристики.")
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
        st.markdown("### 📚 Словарь EN → RU")
        st.caption("Редактирование пользовательского словаря и автоматическое пополнение через Argos.")

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
        st.markdown("### Добавить или изменить запись")
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
        st.markdown("### Импорт и экспорт")
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
        st.markdown("### ⚠️ Опасная зона")
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
        st.markdown("### ❔ Справка")
        st.markdown(HELP_TEXT)
