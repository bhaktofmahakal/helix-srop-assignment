"""
Embeddings using HuggingFace with token for higher rate limits.

Set HF_TOKEN in .env for authenticated requests.
Uses sentence-transformers locally (all-MiniLM-L6-v2 = 384 dims).
"""

import asyncio
from typing import Iterable

from app.settings import settings

_EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
_cached_model = None


def _get_model():
    global _cached_model
    if _cached_model is None:
        from sentence_transformers import SentenceTransformer

        auth_kwargs = {}
        if settings.hf_token:
            auth_kwargs["use_auth_token"] = settings.hf_token
        _cached_model = SentenceTransformer(_EMBED_MODEL, **auth_kwargs)
    return _cached_model


async def embed_documents(texts: list[str]) -> list[list[float]]:
    model = _get_model()

    def _call() -> list[list[float]]:
        return model.encode(texts).tolist()

    return await asyncio.to_thread(_call)


async def embed_query(query: str) -> list[float]:
    model = _get_model()

    def _call() -> list[float]:
        return model.encode([query]).tolist()[0]

    return await asyncio.to_thread(_call)
