import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import re
import json
import threading
import queue
import os
from datetime import datetime

# ---- Опциональные зависимости ----
try:
    import numpy as np
    import sounddevice as sd
except ImportError:
    np = None
    sd = None

try:
    from vosk import Model, KaldiRecognizer, SetLogLevel
    SetLogLevel(-1)
except ImportError:
    Model = None
    KaldiRecognizer = None

try:
    import pyttsx3
except ImportError:
    pyttsx3 = None


APP_TITLE = "English Literature Essay Analyzer"
VOSK_MODEL_PATH = os.path.join("models", "vosk-model-small-en-us-0.15")
SAMPLE_RATE = 16000
BLOCK_SIZE = 8000


class EssayAnalyzerApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1000x760")
        self.root.minsize(860, 620)

        self.events = queue.Queue()
        self.listening = False
        self.audio_stream = None
        self.vosk_model = None
        self.vosk_recognizer = None
        self.tts_engine = None

        self.operations = {
            "Word count": tk.BooleanVar(value=True),
            "Character count": tk.BooleanVar(value=True),
            "Sentence count": tk.BooleanVar(value=True),
            "Paragraph count": tk.BooleanVar(value=True),
            "Literary vocabulary hints": tk.BooleanVar(value=True),
            "Essay structure hints": tk.BooleanVar(value=True),
        }
        self.speak_results = tk.BooleanVar(value=False)
        self.language = tk.StringVar(value="English")

        self._init_tts()
        self._build_ui()
        self.root.after(100, self._process_events)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- Инициализация ----------
    def _init_tts(self):
        if pyttsx3 is None:
            return
        try:
            self.tts_engine = pyttsx3.init()
            self.tts_engine.setProperty("rate", 170)
        except Exception:
            self.tts_engine = None

    def _load_vosk(self):
        if Model is None:
            return False, "Библиотека vosk не установлена."
        if not os.path.isdir(VOSK_MODEL_PATH):
            return False, (
                f"Модель Vosk не найдена: {VOSK_MODEL_PATH}\n"
                "Скачайте vosk-model-small-en-us-0.15 и распакуйте в папку models/."
            )
        try:
            self.vosk_model = Model(VOSK_MODEL_PATH)
            self.vosk_recognizer = KaldiRecognizer(self.vosk_model, SAMPLE_RATE)
            return True, "OK"
        except Exception as exc:
            return False, f"Ошибка загрузки модели Vosk: {exc}"

    # ---------- UI ----------
    def _build_ui(self):
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x")
        ttk.Label(header, text=APP_TITLE, font=("Segoe UI", 18, "bold")).pack(side="left")
        ttk.Label(header, text="Language:").pack(side="right", padx=(10, 5))
        language_box = ttk.Combobox(
            header, textvariable=self.language,
            values=["English"], state="readonly", width=12
        )
        language_box.pack(side="right")

        description = (
            "Paste an English literature essay below, analyze it, or use offline speech input (Vosk). "
            "Speech recognition works without internet. Enable speaking to hear the results."
        )
        ttk.Label(outer, text=description, wraplength=940).pack(anchor="w", pady=(8, 12))

        body = ttk.Panedwindow(outer, orient=tk.HORIZONTAL)
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body, padding=(0, 0, 8, 0))
        right = ttk.Frame(body, padding=(8, 0, 0, 0))
        body.add(left, weight=3)
        body.add(right, weight=2)

        ttk.Label(left, text="Essay text").pack(anchor="w")
        self.essay_text = tk.Text(left, wrap="word", undo=True, font=("Segoe UI", 11), height=20)
        self.essay_text.pack(fill="both", expand=True, pady=(5, 8))
        self.essay_text.insert(
            "1.0",
            "Example: In William Shakespeare's Hamlet, the theme of appearance versus reality "
            "reveals the uncertainty experienced by the protagonist. Through imagery and conflict, "
            "Shakespeare develops the idea that truth can be difficult to recognize."
        )

        buttons = ttk.Frame(left)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Analyze essay", command=self.analyze).pack(side="left")
        ttk.Button(buttons, text="Start speech input", command=self.start_listening).pack(side="left", padx=6)
        ttk.Button(buttons, text="Stop listening", command=self.stop_listening).pack(side="left")
        ttk.Button(buttons, text="Open .txt", command=self.open_file).pack(side="right")
        ttk.Button(buttons, text="Save report", command=self.save_report).pack(side="right", padx=6)

        ttk.Label(right, text="Operations (select what the system should perform)").pack(anchor="w")
        operations_box = ttk.LabelFrame(right, text="Analysis operations", padding=8)
        operations_box.pack(fill="x", pady=(5, 12))
        for name, var in self.operations.items():
            ttk.Checkbutton(operations_box, text=name, variable=var).pack(anchor="w", pady=2)
        ttk.Checkbutton(
            operations_box, text="Speak results (TTS)",
            variable=self.speak_results
        ).pack(anchor="w", pady=(8, 2))

        ttk.Label(right, text="Analysis results").pack(anchor="w")
        self.results = tk.Text(right, wrap="word", state="disabled", font=("Consolas", 10), height=18)
        self.results.pack(fill="both", expand=True, pady=(5, 8))

        self.status_var = tk.StringVar(value="Ready. Choose operations and analyze an essay.")
        ttk.Label(outer, textvariable=self.status_var, relief="sunken", anchor="w").pack(fill="x", pady=(10, 0))

    # ---------- Утилиты ----------
    def notify(self, text):
        self.status_var.set(text)

    def _set_results(self, value):
        self.results.configure(state="normal")
        self.results.delete("1.0", "end")
        self.results.insert("1.0", value)
        self.results.configure(state="disabled")

    def _speak(self, text):
        if self.tts_engine is None or not self.speak_results.get():
            return
        def worker():
            try:
                self.tts_engine.say(text)
                self.tts_engine.runAndWait()
            except Exception:
                pass
        threading.Thread(target=worker, daemon=True).start()

    # ---------- Анализ ----------
    def analyze(self):
        text = self.essay_text.get("1.0", "end-1c").strip()
        if not text:
            messagebox.showwarning("No text", "Enter or dictate an essay first.")
            return

        selected = [name for name, var in self.operations.items() if var.get()]
        if not selected:
            messagebox.showwarning("No operations", "Select at least one analysis operation.")
            return

        report = ["ENGLISH LITERATURE ESSAY ANALYSIS",
                  f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S}", ""]
        words = re.findall(r"\b[\w’'-]+\b", text)
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
        paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
        lower = text.lower()

        if self.operations["Word count"].get():
            report.append(f"Word count: {len(words)}")
        if self.operations["Character count"].get():
            report.append(f"Character count (including spaces): {len(text)}")
        if self.operations["Sentence count"].get():
            report.append(f"Sentence count: {len(sentences)}")
        if self.operations["Paragraph count"].get():
            report.append(f"Paragraph count: {len(paragraphs)}")

        if self.operations["Literary vocabulary hints"].get():
            terms = {
                "theme": "central idea or message",
                "symbolism": "an object or image representing a deeper meaning",
                "imagery": "language that appeals to the senses",
                "metaphor": "a direct comparison",
                "simile": "a comparison using 'like' or 'as'",
                "characterization": "how a character is presented",
                "conflict": "a struggle between opposing forces",
                "narrator": "the voice telling the story",
                "tone": "the author's or speaker's attitude",
                "setting": "the time and place of the work",
                "irony": "a contrast between expectation and reality",
                "motif": "a recurring element with significance",
                "foreshadowing": "a hint about later events",
                "point of view": "the perspective from which a story is told",
                "appearance versus reality": "the difference between what seems true and what is true",
            }
            found = [(term, expl) for term, expl in terms.items() if term in lower]
            report.extend(["", "Literary vocabulary detected:"])
            if found:
                report.extend([f"• {term}: {expl}" for term, expl in found])
            else:
                report.append("• No common literary-analysis terms detected.")

        if self.operations["Essay structure hints"].get():
            report.extend(["", "Essay structure hints:"])
            if len(paragraphs) < 3:
                report.append("• A typical analytical essay often has an introduction, body paragraphs, and a conclusion.")
            else:
                report.append(f"• {len(paragraphs)} paragraphs detected. Check that the introduction presents a thesis.")
            if not re.search(r"\b(thesis|argue|suggests|demonstrates|shows|reveals|illustrates)\b", lower):
                report.append("• Make the central argument explicit with a clear thesis statement.")
            if not re.search(r"\b(because|therefore|this shows|this suggests|for example|for instance)\b", lower):
                report.append("• Explain how each quotation or example supports your interpretation.")
            if not re.search(r"\b(conclusion|in conclusion|ultimately|overall|to conclude)\b", lower):
                report.append("• Make sure the ending synthesizes the argument.")

        report.extend(["", "Note: This is a rule-based study aid, not an official grade."])
        full_text = "\n".join(report)
        self._set_results(full_text)
        self.notify("Analysis complete.")
        self._speak("Analysis complete. " + " ".join(report[:6]))

    # ---------- Файлы ----------
    def open_file(self):
        path = filedialog.askopenfilename(
            title="Open essay text",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.essay_text.delete("1.0", "end")
            self.essay_text.insert("1.0", content)
            self.notify(f"Loaded: {path}")
        except OSError as exc:
            messagebox.showerror("Open error", str(exc))

    def save_report(self):
        content = self.results.get("1.0", "end-1c")
        if not content.strip():
            messagebox.showwarning("No report", "Analyze an essay before saving.")
            return
        path = filedialog.asksaveasfilename(
            title="Save analysis report", defaultextension=".txt",
            filetypes=[("Text files", "*.txt")]
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            self.notify(f"Report saved: {path}")
        except OSError as exc:
            messagebox.showerror("Save error", str(exc))

    # ---------- Распознавание речи (Vosk + sounddevice) ----------
    def start_listening(self):
        if sd is None or np is None:
            messagebox.showerror(
                "Speech recognition unavailable",
                "Установите зависимости:\n    pip install sounddevice numpy vosk"
            )
            return
        if self.listening:
            self.notify("Already listening.")
            return
        ok, msg = self._load_vosk()
        if not ok:
            messagebox.showerror("Vosk", msg)
            return

        self.listening = True
        self.notify("Listening… Speak clearly in English.")
        threading.Thread(target=self._listen_worker, daemon=True).start()

    def stop_listening(self):
        self.listening = False
        self.notify("Stopping listening…")

    def _listen_worker(self):
        try:
            def callback(indata, frames, time_info, status):
                if status:
                    pass
                if self.listening and self.vosk_recognizer is not None:
                    if self.vosk_recognizer.AcceptWaveform(bytes(indata)):
                        result = json.loads(self.vosk_recognizer.Result())
                        text = result.get("text", "").strip()
                        if text:
                            self.events.put(("speech", text))

            with sd.RawInputStream(
                samplerate=SAMPLE_RATE, blocksize=BLOCK_SIZE,
                dtype="int16", channels=1, callback=callback
            ):
                while self.listening:
                    sd.sleep(200)

                # финальный результат
                if self.vosk_recognizer is not None:
                    final = json.loads(self.vosk_recognizer.FinalResult())
                    text = final.get("text", "").strip()
                    if text:
                        self.events.put(("speech", text))
        except Exception as exc:
            self.events.put(("error", f"Microphone error: {exc}"))
        finally:
            self.events.put(("listening_stopped", None))

    def _process_events(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "status":
                    self.status_var.set(payload)
                elif kind == "speech":
                    current = self.essay_text.get("1.0", "end-1c").strip()
                    if current.startswith("Example: In William Shakespeare"):
                        current = ""
                    addition = (current + "\n" + payload).strip() if current else payload
                    self.essay_text.delete("1.0", "end")
                    self.essay_text.insert("1.0", addition)
                    self.status_var.set("Speech recognized and added.")
                elif kind == "error":
                    self.status_var.set(payload)
                    messagebox.showerror("Speech input", payload)
                elif kind == "listening_stopped":
                    self.listening = False
                    if "error" not in self.status_var.get().lower():
                        self.status_var.set("Speech input stopped.")
        except queue.Empty:
            pass
        self.root.after(100, self._process_events)

    def _on_close(self):
        self.listening = False
        try:
            if self.audio_stream is not None:
                self.audio_stream.close()
        except Exception:
            pass
        self.root.destroy()


def main():
    root = tk.Tk()
    EssayAnalyzerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()