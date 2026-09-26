# semantic.py
"""
Семантический компонент: эмбеддинги документов и запросов,
поиск по косинусной близости.

По умолчанию используется локальная мультиязычная модель
sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2.
Опционально можно переключиться на Qwen3-Embedding через OpenRouter,
установив переменную окружения USE_OPENROUTER=1 и OPENROUTER_API_KEY.
"""
import os
from typing import Iterable
import numpy as np

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
USE_OPENROUTER = os.environ.get("USE_OPENROUTER", "0") == "1"
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = "qwen/qwen3-embedding-8b"

_model = None


def get_model():
    """Ленивая загрузка локальной модели."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def _embed_openrouter(texts: list[str]) -> np.ndarray:
    """Альтернативный путь: Qwen3-Embedding через OpenRouter."""
    import requests
    r = requests.post(
        "https://openrouter.ai/api/v1/embeddings",
        headers={"Authorization": f"Bearer {OPENROUTER_KEY}"},
        json={"model": OPENROUTER_MODEL, "input": texts},
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()["data"]
    vecs = np.array([d["embedding"] for d in data], dtype=np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    return vecs / np.clip(norms, 1e-9, None)


def embed_texts(texts: Iterable[str]) -> np.ndarray:
    """Возвращает матрицу [N, D] нормализованных эмбеддингов."""
    texts = list(texts)
    if USE_OPENROUTER and OPENROUTER_KEY:
        return _embed_openrouter(texts)

    model = get_model()
    vecs = model.encode(
        texts,
        normalize_embeddings=True,
        batch_size=16,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    return vecs.astype(np.float32)


def embed_one(text: str) -> np.ndarray:
    """Эмбеддинг одного текста."""
    return embed_texts([text])[0]


def cosine_sim(qv: np.ndarray, dv: np.ndarray) -> float:
    """Косинус через скалярное произведение нормализованных векторов."""
    return float(np.dot(qv, dv))


def semantic_ranking(
    query_vec: np.ndarray,
    doc_vectors: dict[int, np.ndarray],
    candidate_ids: set[int] | None = None,
    top_k: int | None = None,
):
    """
    Возвращает список (doc_id, similarity), отсортированный по убыванию.
    Если задан candidate_ids — считает близость только для них.
    """
    if candidate_ids is not None:
        ids = [i for i in candidate_ids if i in doc_vectors]
    else:
        ids = list(doc_vectors.keys())

    if not ids:
        return []

    scored = [(i, cosine_sim(query_vec, doc_vectors[i])) for i in ids]
    scored.sort(key=lambda x: -x[1])
    if top_k is not None:
        scored = scored[:top_k]
    return scored