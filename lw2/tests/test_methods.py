import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.methods import short_words, char_features

def test_short_words():
    assert short_words("Это русский текст и он написан на русском языке.")[0] == "Русский"
    assert short_words("Das ist ein deutscher Text und er ist auf Deutsch geschrieben.")[0] == "Немецкий"

def test_alphabetic():
    assert char_features("Москва и Россия являются большими городами.")[0] == "Русский"
    assert char_features("Berlin ist eine große Stadt in Deutschland.")[0] == "Немецкий"

if __name__ == "__main__":
    test_short_words()
    test_alphabetic()
    print("OK")
