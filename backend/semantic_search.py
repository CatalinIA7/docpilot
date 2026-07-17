from __future__ import annotations

import re
from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity


MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_MODEL = None


def get_model() -> SentenceTransformer:
    global _MODEL
    if _MODEL is None:
        _MODEL = SentenceTransformer(MODEL_NAME)
    return _MODEL


def split_text(text: str, chunk_size: int = 250, overlap: int = 40) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []

    words = normalized.split()
    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(len(words), start + chunk_size)
        chunk = " ".join(words[start:end])
        if chunk:
            chunks.append(chunk)
        if end == len(words):
            break
        start = max(0, end - overlap)

    return chunks


def build_embeddings(chunks: list[str]) -> np.ndarray:
    if not chunks:
        return np.empty((0, 0))

    model = get_model()
    embeddings = model.encode(chunks, convert_to_numpy=True)
    return embeddings


def rank_chunks(query: str, chunks: list[str], embeddings: np.ndarray) -> list[dict[str, Any]]:
    if not chunks or embeddings.size == 0:
        return []

    model = get_model()
    query_embedding = model.encode([query], convert_to_numpy=True)[0].reshape(1, -1)
    similarity_scores = cosine_similarity(query_embedding, embeddings)[0]
    ranked_indices = np.argsort(similarity_scores)[::-1]

    results = []
    for idx in ranked_indices:
        results.append({
            "text": chunks[int(idx)],
            "score": float(similarity_scores[int(idx)]),
        })

    return results
