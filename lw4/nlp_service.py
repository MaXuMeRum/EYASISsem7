import re
from collections import Counter
from typing import Optional

import spacy
import benepar

try:
    from deep_translator import GoogleTranslator
except ImportError:
    GoogleTranslator = None

from graphviz import Digraph


POS_RU = {
    "NOUN": "существительное",
    "VERB": "глагол",
    "AUX": "вспомогательный глагол",
    "ADJ": "прилагательное",
    "ADV": "наречие",
    "PRON": "местоимение",
    "DET": "определитель/артикль",
    "ADP": "предлог",
    "CONJ": "союз",
    "CCONJ": "сочинительный союз",
    "SCONJ": "подчинительный союз",
    "NUM": "числительное",
    "PART": "частица",
    "INTJ": "междометие",
    "PROPN": "имя собственное",
    "PUNCT": "пунктуация",
    "SYM": "символ",
    "X": "другое/неопределённое",
    "SPACE": "пробел",
}


class NLPService:
    def __init__(self):
        self.nlp = spacy.load("en_core_web_sm")
        self.nlp.max_length = 3_000_000

        try:
            if "benepar" not in self.nlp.pipe_names:
                self.nlp.add_pipe("benepar", config={"model": "benepar_en3"})
        except Exception:
            try:
                benepar.download("benepar_en3")
                self.nlp.add_pipe("benepar", config={"model": "benepar_en3"})
            except Exception:
                pass

        self.translator = (
            GoogleTranslator(source="en", target="ru")
            if GoogleTranslator else None
        )
        self.word_cache = {}

    def analyze(self, text: str):
        doc = self.nlp(text)
        words = [t for t in doc if t.is_alpha]
        rows = []
        for token in words:
            lemma = token.lemma_.lower()
            rows.append({
                "word": token.text,
                "lemma": lemma,
                "pos": token.pos_,
                "pos_description": POS_RU.get(token.pos_, token.pos_),
            })
        return doc, rows

    @staticmethod
    def word_count(text: str) -> int:
        # Словом считаем последовательность букв/цифр, включая дефисные варианты.
        return len(re.findall(r"\b[\w]+(?:[-'][\w]+)*\b", text, flags=re.UNICODE))

    def translate_text(self, text: str) -> str:
        if not text.strip():
            return ""
        if not self.translator:
            raise RuntimeError("Не установлен пакет deep-translator.")
        # Google Translate имеет ограничения на размер одного запроса.
        chunks = self._split_for_translation(text, 4500)
        result = []
        for chunk in chunks:
            result.append(self.translator.translate(chunk))
        return "\n".join(result)

    @staticmethod
    def _split_for_translation(text, limit):
        if len(text) <= limit:
            return [text]
        parts = re.split(r"(?<=[.!?])\s+", text)
        chunks, current = [], ""
        for part in parts:
            if len(current) + len(part) + 1 > limit:
                if current:
                    chunks.append(current)
                current = part
            else:
                current = f"{current} {part}".strip()
        if current:
            chunks.append(current)
        return chunks

    def translate_word(self, word: str) -> str:
        key = word.lower()
        if key in self.word_cache:
            return self.word_cache[key]
        if not self.translator:
            return ""
        try:
            result = self.translator.translate(word)
        except Exception:
            result = ""
        self.word_cache[key] = result or ""
        return result or ""

    def dependency_dot(self, doc) -> str:
        dot = Digraph(comment="Dependency Tree")
        dot.attr(rankdir="LR")
        for token in doc:
            label = f"{token.text}\\n[{token.pos_}]"
            dot.node(str(token.i), label)
            if token.dep_ != "ROOT":
                dot.edge(str(token.head.i), str(token.i), label=token.dep_)
        return dot.source

    def constituency_dot(self, sentence) -> str:
        dot = Digraph(comment="Constituency Tree")
        node_id = [0]

        def add_node(node, parent=None):
            current = str(node_id[0])
            node_id[0] += 1
            label = node._.labels[0] if hasattr(node._, "labels") and node._.labels else node.text
            dot.node(current, label)
            if parent is not None:
                dot.edge(parent, current)
            if hasattr(node._, "children"):
                for child in node._.children:
                    add_node(child, current)

        add_node(sentence)
        return dot.source

    def get_sentences(self, doc):
        return list(doc.sents)

    def frequency_table(self, rows, db):
        counter = Counter(r["lemma"] for r in rows)
        result = []
        for lemma, freq in counter.most_common():
            info = db.get(lemma)
            if info:
                translation = info["translation_ru"]
                domain = info["domain"]
                comment = info["comment"]
                pos = info["pos"] or next(
                    r["pos"] for r in rows if r["lemma"] == lemma
                )
                pos_desc = info["pos_description"] or POS_RU.get(pos, pos)
            else:
                same = next(r for r in rows if r["lemma"] == lemma)
                translation = self.translate_word(lemma)
                pos = same["pos"]
                pos_desc = same["pos_description"]
                domain = "general"
                comment = ""
                if translation:
                    db.upsert(
                        lemma, translation, pos, pos_desc, domain, comment
                    )

            result.append({
                "lemma": lemma,
                "frequency": freq,
                "translation": translation,
                "pos": pos,
                "pos_description": pos_desc,
                "domain": domain,
                "comment": comment,
            })
        return result
