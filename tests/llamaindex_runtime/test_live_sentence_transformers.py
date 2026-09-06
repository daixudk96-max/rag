"""Live integration tests using the real SentenceTransformers embedding provider.

These tests exercise the full pipeline: config -> create_embed_model -> query()
with a real local model. They are gated behind a pytest marker so they only
run when explicitly requested.

Run with:
    pytest -m live_st tests/llamaindex_runtime/test_live_sentence_transformers.py
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from llamaindex_runtime.config import RuntimeSettings
from llamaindex_runtime.embeddings import SentenceTransformersEmbedding, create_embed_model
from llamaindex_runtime.entrypoints import QueryHit, QueryResult, query


_REAL_DOCX_ENV_VAR = "RAG_TEST_DOCX_PATH"
_REAL_DOCX = Path(os.getenv(_REAL_DOCX_ENV_VAR, "")) if os.getenv(_REAL_DOCX_ENV_VAR) else Path("")


def _docx_available() -> bool:
    return _REAL_DOCX.is_file()


pytestmark = pytest.mark.live_st


class TestLiveSentenceTransformersAdapter:
    """Smoke tests for the real SentenceTransformers adapter."""

    def test_adapter_produces_real_embeddings(self) -> None:
        adapter = SentenceTransformersEmbedding(model_name="all-MiniLM-L6-v2")
        vec = adapter._get_text_embedding("hello world")
        assert isinstance(vec, list)
        assert len(vec) == 384
        assert any(v != 0.0 for v in vec)

    def test_adapter_query_and_text_embeddings_consistent(self) -> None:
        adapter = SentenceTransformersEmbedding(model_name="all-MiniLM-L6-v2")
        text_vec = adapter._get_text_embedding("hello world")
        query_vec = adapter._get_query_embedding("hello world")
        # Same input should produce same vector
        assert text_vec == query_vec

    def test_adapter_batch_embeddings(self) -> None:
        adapter = SentenceTransformersEmbedding(model_name="all-MiniLM-L6-v2")
        vecs = adapter._get_text_embeddings(["hello", "world"])
        assert len(vecs) == 2
        assert all(len(v) == 384 for v in vecs)


class TestLiveCreateEmbedModel:
    """Factory produces a working adapter from config."""

    def test_sentence_transformers_factory(self) -> None:
        settings = RuntimeSettings(
            database_url="postgresql://localhost/test",
            embedding_provider="sentence_transformers",
            embedding_model_name="all-MiniLM-L6-v2",
        )
        model = create_embed_model(settings)
        assert isinstance(model, SentenceTransformersEmbedding)
        vec = model._get_text_embedding("test")
        assert len(vec) == 384


class TestLiveDocxVectorQuery:
    """End-to-end: query the real DOCX with SentenceTransformers via vector mode."""

    @pytest.mark.skipif(not _docx_available(), reason="Real DOCX file not found")
    def test_vector_query_with_real_embeddings(self) -> None:
        settings = RuntimeSettings(
            database_url="postgresql://localhost/test",
            embedding_provider="sentence_transformers",
            embedding_model_name="all-MiniLM-L6-v2",
        )
        embed_model = create_embed_model(settings)

        result = query(
            source_path=_REAL_DOCX,
            query_text="短视频流量优化策略",
            embed_model=embed_model,
            mode="vector",
            similarity_top_k=3,
        )

        assert isinstance(result, QueryResult)
        assert result.mode == "vector"
        assert result.source_path == str(_REAL_DOCX)
        assert result.query == "短视频流量优化策略"
        assert len(result.hits) > 0
        assert all(isinstance(h, QueryHit) for h in result.hits)
        # With real embeddings, hits should contain relevant Chinese text
        combined_text = " ".join(h.text for h in result.hits)
        assert len(combined_text) > 10  # Non-trivial content

    @pytest.mark.skipif(not _docx_available(), reason="Real DOCX file not found")
    def test_tree_query_with_real_embeddings(self) -> None:
        settings = RuntimeSettings(
            database_url="postgresql://localhost/test",
            embedding_provider="sentence_transformers",
            embedding_model_name="all-MiniLM-L6-v2",
        )
        embed_model = create_embed_model(settings)

        result = query(
            source_path=_REAL_DOCX,
            query_text="直播间数据优化",
            embed_model=embed_model,
            mode="tree",
            similarity_top_k=4,
        )

        assert isinstance(result, QueryResult)
        assert result.mode == "tree"
        assert len(result.hits) > 0
        combined_text = " ".join(h.text for h in result.hits)
        assert len(combined_text) > 10
