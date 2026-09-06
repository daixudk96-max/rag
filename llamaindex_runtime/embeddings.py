"""Embedding provider adapters for the formal runtime.

Supports:
- ``mock`` -- LlamaIndex MockEmbedding (for testing, no real vectors)
- ``sentence_transformers`` -- local SentenceTransformers-backed adapter
"""
from __future__ import annotations

import asyncio
from typing import Any

import numpy as np
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.embeddings import MockEmbedding
from pydantic import PrivateAttr
from sentence_transformers import SentenceTransformer

from llamaindex_runtime.config import RuntimeSettings

# Known model dimension mapping to avoid querying the model at construction time.
_MODEL_DIMS: dict[str, int] = {
    "all-MiniLM-L6-v2": 384,
    "paraphrase-MiniLM-L3-v2": 384,
    "all-MiniLM-L12-v2": 384,
    "all-mpnet-base-v2": 768,
}


def _resolve_embed_dim(model_name: str) -> int:
    """Return the embedding dimension for a known model, or 384 as default."""
    return _MODEL_DIMS.get(model_name, 384)


class SentenceTransformersEmbedding(BaseEmbedding):
    """LlamaIndex-compatible embedding adapter backed by SentenceTransformers.

    Runs entirely locally -- no API keys or network calls after model download.
    """

    model_name: str = "all-MiniLM-L6-v2"
    embed_dim: int = 384
    _st_model: SentenceTransformer = PrivateAttr()

    def __init__(self, model_name: str = "all-MiniLM-L6-v2", embed_dim: int | None = None) -> None:
        if embed_dim is not None and embed_dim < 1:
            raise ValueError("embed_dim must be >= 1")
        embed_dim = embed_dim if embed_dim is not None else _resolve_embed_dim(model_name)
        super().__init__(model_name=model_name, embed_dim=embed_dim)
        self._st_model = SentenceTransformer(model_name)

    def _get_query_embedding(self, query: str) -> list[float]:
        vec: np.ndarray = np.atleast_1d(np.ravel(self._st_model.encode(query)))
        return vec.tolist()

    def _get_text_embedding(self, text: str) -> list[float]:
        vec: np.ndarray = np.atleast_1d(np.ravel(self._st_model.encode(text)))
        return vec.tolist()

    def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        vecs: np.ndarray = self._st_model.encode(texts)
        if vecs.ndim == 1:
            return [vecs.tolist()]
        return [np.ravel(v).tolist() for v in vecs]

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return await asyncio.to_thread(self._get_query_embedding, query)

    async def _aget_text_embedding(self, text: str) -> list[float]:
        return await asyncio.to_thread(self._get_text_embedding, text)

    async def _aget_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(self._get_text_embeddings, texts)

    @classmethod
    def class_name(cls) -> str:
        return "SentenceTransformersEmbedding"


def create_embed_model(settings: RuntimeSettings) -> BaseEmbedding:
    """Factory: create the appropriate BaseEmbedding from RuntimeSettings.

    Parameters
    ----------
    settings:
        RuntimeSettings with ``embedding_provider`` and ``embedding_model_name``.

    Returns
    -------
    BaseEmbedding
        Either a MockEmbedding (provider="mock") or a
        SentenceTransformersEmbedding (provider="sentence_transformers").
    """
    if settings.embedding_provider == "mock":
        embed_dim = _resolve_embed_dim(settings.embedding_model_name)
        return MockEmbedding(embed_dim=embed_dim)

    if settings.embedding_provider == "sentence_transformers":
        return SentenceTransformersEmbedding(model_name=settings.embedding_model_name)

    # Should be unreachable due to config validation, but defensive.
    raise ValueError(f"Unsupported embedding_provider: {settings.embedding_provider}")
