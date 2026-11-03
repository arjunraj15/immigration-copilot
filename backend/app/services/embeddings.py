"""Local text embeddings with fastembed. Not installed in the slim image, so it is imported on first use."""

from functools import lru_cache

import numpy as np

from app.core.config import get_settings


@lru_cache
def get_embedder():
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=get_settings().embedding_model)


def embed(texts: list[str]) -> list[np.ndarray]:
    return list(get_embedder().embed(texts))


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
