import tkinter as tk
from tkinter import ttk, messagebox
import multiprocessing as mp

try:
    import pyttsx3
except ImportError:
    pyttsx3 = None


SAMPLE_TEXT = (
    "William Shakespeare's \"Romeo and Juliet\" is one of the most famous "
    "tragedies in English literature. The play tells the story of two young "
    "lovers whose families are in conflict. Shakespeare explores themes of "
    "love, fate, conflict, and the consequences of impulsive decisions."
)

SECOND_SAMPLE = (
    "Jane Austen's \"Pride and Prejudice\" is a classic English novel. "
    "The story focuses on Elizabeth Bennet and Mr. Darcy. Through their "
    "relationship, the author explores love, social class, prejudice, and personal growth."
)


def _tts_worker(text, voice_id, rate, volume, queue):
    """Выполняется в отдельном процессе.

    Каждый вызов — чистый интерпретатор Python и чистая инициализация SAPI5,
    поэтому синтез срабатывает при каждом запуске, а не только в первый раз.
    """
    try:
        import pyttsx3 as _pyttsx3
        engine = _pyttsx3.init()
        engine.setProperty("rate", rate)
        engine.setProperty("volume", volume)
        if voice_id:
            engine.setProperty("voice", voice_id)
        engine.say(text)
        engine.runAndWait()
        try:
            engine.stop()
        except Exception:
            pass
        try:
            del engine
        except Exception:
            pass
        queue.put(("ok", None))
    except Exception as error:
        try:
            queue.put(("error", str(error)))
        except Exception:
            pass


class TTSApp:
    def __init__(self, root):
        self.root = root
        self.root.title("English Literature — Speech Synthesis")
        self.root.geometry("900x650")
        self.root.minsize(700, 500)

        self.engine = None
        self.voices = []
        self.voice_map = {}
        self.speaking = False
        self._proc = None

        self._build_ui()
        self._load_engine()

    # ---------- UI ----------
    def _build_ui(self):
        header = ttk.Frame(self.root, padding=12)
        header.pack(fill="x")
        ttk.Label(
            header,
            text="English Literature — Text to Speech",
            font=("Arial", 18, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            header,
            text="Система синтеза речи для сочинений по литературе",
        ).pack(anchor="w", pady=(3, 0))

        settings = ttk.LabelFrame(self.root, text="Настройки речи", padding=10)
        settings.pack(fill="x", padx=12, pady=(0, 10))
        settings.columnconfigure(1, weight=1)

        ttk.Label(settings, text="Голос:").grid(
            row=0, column=0, sticky="w", padx=5, pady=5
        )
        self.voice_combo = ttk.Combobox(settings, state="readonly", width=42)
        self.voice_combo.grid(row=0, column=1, sticky="ew", padx=5, pady=5)

        ttk.Button(
            settings, text="Обновить голоса", command=self._reload_voices
        ).grid(row=0, column=2, padx=5)
        ttk.Button(
            settings, text="Тест голоса", command=self._test_voice
        ).grid(row=0, column=3, padx=5)

        ttk.Label(settings, text="Темп:").grid(
            row=1, column=0, sticky="w", padx=5
        )
        self.rate = tk.IntVar(value=170)
        ttk.Scale(
            settings, from_=80, to=300, variable=self.rate,
            orient="horizontal", length=180
        ).grid(row=1, column=1, sticky="w", padx=5)

        ttk.Label(settings, text="Громкость:").grid(
            row=1, column=2, sticky="w", padx=5
        )
        self.volume = tk.DoubleVar(value=1.0)
        ttk.Scale(
            settings, from_=0.0, to=1.0, variable=self.volume,
            orient="horizontal", length=180
        ).grid(row=1, column=3, sticky="w", padx=5)

        ttk.Label(settings, text="Высота тона:").grid(
            row=2, column=0, sticky="w", padx=5, pady=5
        )
        self.pitch = tk.IntVar(value=50)
        ttk.Scale(
            settings, from_=0, to=100, variable=self.pitch,
            orient="horizontal", length=180
        ).grid(row=2, column=1, sticky="w", padx=5)

        text_frame = ttk.LabelFrame(
            self.root, text="Текст сочинения на английском языке", padding=8
        )
        text_frame.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        self.text = tk.Text(text_frame, wrap="word", font=("Arial", 13), undo=True)
        scrollbar = ttk.Scrollbar(text_frame, command=self.text.yview)
        self.text.configure(yscrollcommand=scrollbar.set)
        self.text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.text.insert("1.0", SAMPLE_TEXT)

        buttons = ttk.Frame(self.root, padding=(12, 0, 12, 12))
        buttons.pack(fill="x")
        ttk.Button(
            buttons, text="Воспроизвести", command=self.speak
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            buttons, text="Остановить", command=self.stop
        ).pack(side="left", padx=6)
        ttk.Button(
            buttons, text="Очистить",
            command=lambda: self.text.delete("1.0", "end")
        ).pack(side="left", padx=6)
        ttk.Button(
            buttons, text="Другой пример", command=self.insert_sample
        ).pack(side="left", padx=6)
        ttk.Button(
            buttons, text="Вставить из буфера", command=self.paste_from_clipboard
        ).pack(side="left", padx=6)

        self.status = tk.StringVar(value="Запуск...")
        ttk.Label(
            self.root, textvariable=self.status, relief="sunken", anchor="w"
        ).pack(fill="x", side="bottom")

    # ---------- Инициализация движка (только для чтения списка голосов) ----------
    def _load_engine(self):
        if pyttsx3 is None:
            self.status.set("Не установлена библиотека pyttsx3. Запустите install.bat.")
            return

        try:
            self.engine = pyttsx3.init()
            self._refresh_voice_list()
            self.status.set("Готово к синтезу")
        except Exception as error:
            self.status.set("Не удалось запустить движок синтеза")
            messagebox.showerror(
                "Ошибка синтеза речи",
                "Не удалось инициализировать pyttsx3.\n\n"
                f"{error}\n\n"
                "В Windows проверьте наличие системного голоса и повторите запуск."
            )

    def _refresh_voice_list(self):
        """Загружает список голосов, включая все английские."""
        self.voices = self.engine.getProperty("voices") or []
        self.voice_map = {}
        names = []
        for index, voice in enumerate(self.voices):
            name = str(getattr(voice, "name", None) or
                       getattr(voice, "id", f"Voice {index}"))
            label = name if name not in self.voice_map else f"{name} ({index + 1})"
            names.append(label)
            self.voice_map[label] = voice.id

        self.voice_combo["values"] = names
        if names:
            preferred_index = 0
            for index, voice in enumerate(self.voices):
                details = (
                    str(getattr(voice, "id", "")) + " " +
                    str(getattr(voice, "name", ""))
                ).lower()
                if "english" in details or "en_" in details or "en-" in details:
                    preferred_index = index
                    break
            self.voice_combo.current(preferred_index)

    def _reload_voices(self):
        """Пересоздаёт движок и обновляет список голосов."""
        if pyttsx3 is None:
            return
        try:
            self.engine = pyttsx3.init()
            self._refresh_voice_list()
            self.status.set("Список голосов обновлён")
        except Exception as error:
            messagebox.showerror("Ошибка", f"Не удалось обновить голоса:\n{error}")

    # ---------- Работа с текстом ----------
    def insert_sample(self):
        self.text.delete("1.0", "end")
        self.text.insert("1.0", SECOND_SAMPLE)

    def paste_from_clipboard(self):
        try:
            data = self.root.clipboard_get()
        except tk.TclError:
            return
        self.text.insert("insert", data)

    # ---------- Синтез ----------
    def speak(self):
        if pyttsx3 is None or self.engine is None:
            messagebox.showwarning(
                "Синтез речи недоступен",
                "Установите зависимости командой install.bat и проверьте сообщение внизу окна."
            )
            return

        content = self.text.get("1.0", "end").strip()
        if not content:
            messagebox.showinfo("Нет текста", "Введите или вставьте английский текст.")
            return

        if self.speaking:
            return
        self.speaking = True

        voice_id = self.voice_map.get(self.voice_combo.get())
        rate = int(float(self.rate.get()))
        volume = float(self.volume.get())

        self._run_tts(content, voice_id, rate, volume)

    def _test_voice(self):
        if pyttsx3 is None or self.engine is None:
            messagebox.showwarning("TTS", "Движок не инициализирован.")
            return
        if self.speaking:
            return
        self.speaking = True

        voice_id = self.voice_map.get(self.voice_combo.get())
        rate = int(float(self.rate.get()))
        volume = float(self.volume.get())
        self._run_tts(
            "This is a test of the selected voice.",
            voice_id, rate, volume
        )

    def _run_tts(self, text, voice_id, rate, volume):
        """Запускает синтез в отдельном процессе.

        Отдельный процесс — ключ к тому, чтобы каждый запуск работал:
        SAPI5 в Windows не переносит повторную инициализацию в одном процессе.
        """
        self.status.set("Воспроизведение...")

        queue = mp.Queue()
        process = mp.Process(
            target=_tts_worker,
            args=(text, voice_id, rate, volume, queue),
            daemon=True,
        )
        self._proc = process
        process.start()

        def poll():
            if process.is_alive():
                self.root.after(100, poll)
                return

            try:
                status, err = queue.get_nowait()
            except Exception:
                status, err = ("ok", None)

            self.speaking = False

            if status == "error":
                self.status.set("Ошибка воспроизведения")
                messagebox.showerror("Ошибка TTS", err or "Неизвестная ошибка")
            else:
                self.status.set("Готово")

        self.root.after(100, poll)

    def stop(self):
        proc = getattr(self, "_proc", None)
        if proc is not None and proc.is_alive():
            try:
                proc.terminate()
                proc.join(timeout=1)
            except Exception:
                pass
        self.speaking = False
        self.status.set("Остановлено")


def main():
    # "spawn" надёжнее на Windows для чистой инициализации дочерних процессов
    try:
        mp.set_start_method("spawn", force=True)
    except RuntimeError:
        pass

    root = tk.Tk()
    TTSApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()