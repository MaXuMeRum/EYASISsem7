import re
from collections import Counter
from pathlib import Path
import numpy as np

RU_STOP = {
    "и","в","во","не","что","он","на","я","с","со","как","а","то","все","она",
    "так","его","но","да","ты","к","у","же","вы","за","бы","по","только","ее",
    "мне","было","вот","от","меня","еще","нет","о","из","ему","теперь","когда",
    "даже","ну","вдруг","ли","если","уже","или","ни","быть","был","него","до",
    "вас","нибудь","опять","уж","вам","ведь","там","потом","себя","ничего","ей",
    "может","они","тут","где","есть","надо","ней","для","мы","тебя","их","чем",
    "была","сам","чтобы","без","будет","тогда","кто","этот","того","потому",
    "этого","какой","совсем","ним","здесь","этом","один","почти","мой","тем",
    "чтобы","сейчас"
}

DE_STOP = {
    "der","die","das","den","dem","des","ein","eine","einer","einem","einen",
    "und","oder","aber","nicht","ist","im","in","auf","zu","von","mit","für",
    "als","auch","an","es","er","sie","wir","ihr","ich","du","sich","dass",
    "bei","aus","nach","über","vor","nur","noch","wie","was","wer","war","sind",
    "wird","werden","hat","haben","hatte","kann","können","muss","müssen","durch",
    "gegen","unter","zwischen","sehr","mehr","dies","diese","dieser","diesem",
    "dieses","weil","wenn","wo","hier","dort"
}

RU_CHARS = set("абвгдеёжзийклмнопрстуфхцчшщъыьэюя")
DE_CHARS = set("abcdefghijklmnopqrstuvwxyzäöüß")

def words(text):
    return re.findall(r"[A-Za-zА-Яа-яЁёÄÖÜäöüß]+", text.lower())

def normalize(text):
    return re.sub(r"\s+", " ", text.lower()).strip()

def short_words(text):
    ws = words(text)
    if not ws:
        return "Недостаточно текста", 0.0, {}
    c = Counter(ws)
    ru = sum(c[w] for w in RU_STOP)
    de = sum(c[w] for w in DE_STOP)
    score = (ru - de) / max(1, ru + de)
    lang = "Русский" if score >= 0 else "Немецкий"
    confidence = min(1.0, abs(score) + 0.35)
    return lang, confidence, {"русские короткие слова": ru, "немецкие короткие слова": de}

def char_features(text):
    s = normalize(text)
    letters = [ch for ch in s if ch.isalpha()]
    n = max(1, len(letters))
    ru = sum(ch in RU_CHARS for ch in letters)
    de = sum(ch in DE_CHARS for ch in letters)
    # Немецкие признаки
    german_patterns = ["sch","ch","ei","ie","eu","ä","ö","ü","ß","ung","lich","keit"]
    russian_patterns = ["ст","но","то","ни","ть","ого","ами","ыми","ение","ость"]
    gp = sum(s.count(p) for p in german_patterns)
    rp = sum(s.count(p) for p in russian_patterns)
    # Кириллица дает сильный сигнал, латиница — немецкий.
    ru_score = 2.0 * ru / n + 0.08 * rp
    de_score = 2.0 * de / n + 0.08 * gp
    total = ru_score + de_score
    lang = "Русский" if ru_score >= de_score else "Немецкий"
    confidence = 0.5 if total == 0 else min(1.0, abs(ru_score-de_score)/total + 0.5)
    return lang, confidence, {
        "доля кириллицы": round(ru/n, 3),
        "доля латиницы": round(de/n, 3),
        "русские шаблоны": rp,
        "немецкие шаблоны": gp
    }

class NeuralLanguageModel:
    def __init__(self):
        self.model = None
        self.vectorizer = None
        self.classes_ = ["Русский", "Немецкий"]

    def _make_training_data(self):
        base = Path(__file__).resolve().parent.parent / "corpus"
        texts, labels = [], []
        for label, folder in [("Русский", base/"ru"), ("Немецкий", base/"de")]:
            if folder.exists():
                for p in sorted(folder.glob("*.txt")):
                    txt = p.read_text(encoding="utf-8", errors="ignore").strip()
                    if txt:
                        texts.append(txt)
                        labels.append(label)
        return texts, labels

    def fit(self, texts=None, labels=None):
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.neural_network import MLPClassifier
        if texts is None or labels is None:
            texts, labels = self._make_training_data()
        if len(set(labels)) < 2 or len(texts) < 4:
            raise ValueError("Нужны тексты обоих языков, минимум по два примера.")
        self.vectorizer = TfidfVectorizer(
            analyzer="char", ngram_range=(2, 5), min_df=1,
            sublinear_tf=True, max_features=10000
        )
        X = self.vectorizer.fit_transform(texts)
        self.model = MLPClassifier(
            hidden_layer_sizes=(64, 32), activation="relu",
            solver="adam", alpha=0.0005, max_iter=400,
            random_state=42, early_stopping=False
        )
        self.model.fit(X, labels)
        self.classes_ = list(self.model.classes_)
        return len(texts)

    def predict(self, text):
        if self.model is None:
            self.fit()
        X = self.vectorizer.transform([text])
        pred = self.model.predict(X)[0]
        try:
            proba = self.model.predict_proba(X)[0]
            conf = float(max(proba))
        except Exception:
            conf = 0.0
        return pred, conf, {"классы": ", ".join(self.classes_)}

NEURAL = NeuralLanguageModel()

def identify(text, method):
    if method == "Коротких слов":
        return short_words(text)
    if method == "Алфавитный":
        return char_features(text)
    if method == "Нейросетевой":
        return NEURAL.predict(text)
    raise ValueError("Неизвестный метод")
