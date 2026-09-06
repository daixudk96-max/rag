"""Tests for the embedding provider module.

Covers:
- SentenceTransformersEmbedding adapter (unit tests with mocked ST)
- Provider selection via config
- Factory function create_embed_model
- Edge cases: null/empty input, large batch, special characters
"""
from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pytest
from llama_index.core.base.embeddings.base import BaseEmbedding

from llamaindex_runtime.config import RuntimeSettings


# ---------------------------------------------------------------------------
# Unit: SentenceTransformersEmbedding adapter construction
# ---------------------------------------------------------------------------


class TestSentenceTransformersAdapterConstruction:
    """The adapter must be a valid BaseEmbedding subclass."""

    def test_adapter_is_base_embedding_subclass(self) -> None:
        from llamaindex_runtime.embeddings import SentenceTransformersEmbedding

        assert issubclass(SentenceTransformersEmbedding, BaseEmbedding)

    def test_adapter_default_model_name(self) -> None:
        from llamaindex_runtime.embeddings import SentenceTransformersEmbedding

        with patch("llamaindex_runtime.embeddings.SentenceTransformer") as mock_st:
            mock_st.return_value.encode.return_value = np.zeros((1, 384), dtype=np.float32)
            adapter = SentenceTransformersEmbedding()
            assert adapter.model_name == "all-MiniLM-L6-v2"
            mock_st.assert_called_once_with("all-MiniLM-L6-v2")

    def test_adapter_custom_model_name(self) -> None:
        from llamaindex_runtime.embeddings import SentenceTransformersEmbedding

        with patch("llamaindex_runtime.embeddings.SentenceTransformer") as mock_st:
            mock_st.return_value.encode.return_value = np.zeros((1, 768), dtype=np.float32)
            adapter = SentenceTransformersEmbedding(model_name="some-other-model")
            assert adapter.model_name == "some-other-model"
            mock_st.assert_called_once_with("some-other-model")

    def test_adapter_embed_dim_matches_model(self) -> None:
        from llamaindex_runtime.embeddings import SentenceTransformersEmbedding

        with patch("llamaindex_runtime.embeddings.SentenceTransformer") as mock_st:
            mock_st.return_value.encode.return_value = np.zeros((1, 512), dtype=np.float32)
            adapter = SentenceTransformersEmbedding(embed_dim=512)
            assert adapter.embed_dim == 512

    def test_adapter_rejects_non_positive_embed_dim(self) -> None:
        from llamaindex_runtime.embeddings import SentenceTransformersEmbedding

        with patch("llamaindex_runtime.embeddings.SentenceTransformer"):
            with pytest.raises(ValueError, match="embed_dim"):
                SentenceTransformersEmbedding(embed_dim=0)


# ---------------------------------------------------------------------------
# Unit: _get_text_embedding and _get_query_embedding
# ---------------------------------------------------------------------------


class TestAdapterEmbeddingMethods:
    """Core embedding methods must return correct-dimension float lists."""

    @patch("llamaindex_runtime.embeddings.SentenceTransformer")
    def test_get_text_embedding_returns_list_of_float(self, mock_st_cls) -> None:
        from llamaindex_runtime.embeddings import SentenceTransformersEmbedding

        fake_vector = np.array([[0.1, 0.2, 0.3, 0.4]], dtype=np.float32)
        mock_st_cls.return_value.encode.return_value = fake_vector

        adapter = SentenceTransformersEmbedding(embed_dim=4)
        result = adapter._get_text_embedding("hello world")

        assert isinstance(result, list)
        assert len(result) == 4
        assert all(isinstance(v, float) for v in result)

    @patch("llamaindex_runtime.embeddings.SentenceTransformer")
    def test_get_query_embedding_returns_list_of_float(self, mock_st_cls) -> None:
        from llamaindex_runtime.embeddings import SentenceTransformersEmbedding

        fake_vector = np.array([[0.5, 0.6]], dtype=np.float32)
        mock_st_cls.return_value.encode.return_value = fake_vector

        adapter = SentenceTransformersEmbedding(embed_dim=2)
        result = adapter._get_query_embedding("search query")

        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(v, float) for v in result)

    @patch("llamaindex_runtime.embeddings.SentenceTransformer")
    def test_get_text_embeddings_batch(self, mock_st_cls) -> None:
        from llamaindex_runtime.embeddings import SentenceTransformersEmbedding

        fake_vectors = np.array([[0.1, 0.2], [0.3, 0.4]], dtype=np.float32)
        mock_st_cls.return_value.encode.return_value = fake_vectors

        adapter = SentenceTransformersEmbedding(embed_dim=2)
        results = adapter._get_text_embeddings(["text one", "text two"])

        assert isinstance(results, list)
        assert len(results) == 2
        assert all(isinstance(v, list) for v in results)
        assert all(len(v) == 2 for v in results)


# ---------------------------------------------------------------------------
# Unit: Edge cases
# ---------------------------------------------------------------------------


class TestAdapterEdgeCases:
    """Edge-case inputs must not crash the adapter."""

    @patch("llamaindex_runtime.embeddings.SentenceTransformer")
    def test_empty_string_input(self, mock_st_cls) -> None:
        from llamaindex_runtime.embeddings import SentenceTransformersEmbedding

        fake_vector = np.array([[0.0, 0.0]], dtype=np.float32)
        mock_st_cls.return_value.encode.return_value = fake_vector

        adapter = SentenceTransformersEmbedding(embed_dim=2)
        result = adapter._get_text_embedding("")
        assert isinstance(result, list)
        assert len(result) == 2

    @patch("llamaindex_runtime.embeddings.SentenceTransformer")
    def test_unicode_and_emoji_input(self, mock_st_cls) -> None:
        from llamaindex_runtime.embeddings import SentenceTransformersEmbedding

        fake_vector = np.array([[0.1]], dtype=np.float32)
        mock_st_cls.return_value.encode.return_value = fake_vector

        adapter = SentenceTransformersEmbedding(embed_dim=1)
        result = adapter._get_text_embedding("中文测试 \U0001f680")
        assert isinstance(result, list)

    @patch("llamaindex_runtime.embeddings.SentenceTransformer")
    def test_large_batch_input(self, mock_st_cls) -> None:
        from llamaindex_runtime.embeddings import SentenceTransformersEmbedding

        batch_size = 100
        fake_vectors = np.zeros((batch_size, 8), dtype=np.float32)
        mock_st_cls.return_value.encode.return_value = fake_vectors

        adapter = SentenceTransformersEmbedding(embed_dim=8)
        texts = [f"text {i}" for i in range(batch_size)]
        results = adapter._get_text_embeddings(texts)
        assert len(results) == batch_size

    @patch("llamaindex_runtime.embeddings.SentenceTransformer")
    def test_single_text_returns_2d_array_handled(self, mock_st_cls) -> None:
        """When SentenceTransformer.encode returns a 1-D array for a single text,
        the adapter must still return a flat list of floats."""
        from llamaindex_runtime.embeddings import SentenceTransformersEmbedding

        fake_vector = np.array([0.1, 0.2, 0.3], dtype=np.float32)
        mock_st_cls.return_value.encode.return_value = fake_vector

        adapter = SentenceTransformersEmbedding(embed_dim=3)
        result = adapter._get_text_embedding("single text")
        assert isinstance(result, list)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# Unit: Config embedding_provider and embedding_model_name
# ---------------------------------------------------------------------------


class TestConfigEmbeddingProvider:
    """RuntimeSettings must own embedding provider selection."""

    def test_default_embedding_provider_is_mock(self) -> None:
        settings = RuntimeSettings(database_url="postgresql://localhost/test")
        assert settings.embedding_provider == "mock"

    def test_default_embedding_model_name(self) -> None:
        settings = RuntimeSettings(database_url="postgresql://localhost/test")
        assert settings.embedding_model_name == "all-MiniLM-L6-v2"

    def test_custom_embedding_provider(self) -> None:
        settings = RuntimeSettings(
            database_url="postgresql://localhost/test",
            embedding_provider="sentence_transformers",
        )
        assert settings.embedding_provider == "sentence_transformers"

    def test_invalid_embedding_provider_rejected(self) -> None:
        with pytest.raises(ValueError, match="embedding_provider"):
            RuntimeSettings(
                database_url="postgresql://localhost/test",
                embedding_provider="openai",
            )

    def test_from_env_reads_embedding_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
        monkeypatch.setenv("EMBEDDING_PROVIDER", "sentence_transformers")
        monkeypatch.setenv("EMBEDDING_MODEL_NAME", "paraphrase-MiniLM-L3-v2")
        settings = RuntimeSettings.from_env()
        assert settings.embedding_provider == "sentence_transformers"
        assert settings.embedding_model_name == "paraphrase-MiniLM-L3-v2"

    def test_invalid_embedding_model_name_rejected_for_sentence_transformers(self) -> None:
        with pytest.raises(ValueError, match="embedding_model_name"):
            RuntimeSettings(
                database_url="postgresql://localhost/test",
                embedding_provider="sentence_transformers",
                embedding_model_name="unknown-model",
            )


# ---------------------------------------------------------------------------
# Unit: Factory function create_embed_model
# ---------------------------------------------------------------------------


class TestCreateEmbedModel:
    """create_embed_model must return the correct BaseEmbedding based on config."""

    def test_mock_provider_returns_mock_embedding(self) -> None:
        from llamaindex_runtime.embeddings import create_embed_model
        from llama_index.core.embeddings import MockEmbedding

        settings = RuntimeSettings(
            database_url="postgresql://localhost/test",
            embedding_provider="mock",
        )
        model = create_embed_model(settings)
        assert isinstance(model, MockEmbedding)

    def test_mock_provider_uses_configured_dim(self) -> None:
        from llamaindex_runtime.embeddings import create_embed_model
        from llama_index.core.embeddings import MockEmbedding

        settings = RuntimeSettings(
            database_url="postgresql://localhost/test",
            embedding_provider="mock",
            embedding_model_name="all-MiniLM-L6-v2",
        )
        model = create_embed_model(settings)
        assert isinstance(model, MockEmbedding)
        # MockEmbedding embed_dim defaults to whatever is passed
        assert model.embed_dim == 384

    @patch("llamaindex_runtime.embeddings.SentenceTransformer")
    def test_sentence_transformers_provider_returns_adapter(self, mock_st_cls) -> None:
        from llamaindex_runtime.embeddings import SentenceTransformersEmbedding, create_embed_model

        mock_st_cls.return_value.encode.return_value = np.zeros((1, 384), dtype=np.float32)

        settings = RuntimeSettings(
            database_url="postgresql://localhost/test",
            embedding_provider="sentence_transformers",
            embedding_model_name="all-MiniLM-L6-v2",
        )
        model = create_embed_model(settings)
        assert isinstance(model, SentenceTransformersEmbedding)
        assert model.model_name == "all-MiniLM-L6-v2"

    @patch("llamaindex_runtime.embeddings.SentenceTransformer")
    def test_sentence_transformers_provider_passes_model_name(self, mock_st_cls) -> None:
        from llamaindex_runtime.embeddings import create_embed_model

        mock_st_cls.return_value.encode.return_value = np.zeros((1, 384), dtype=np.float32)

        settings = RuntimeSettings(
            database_url="postgresql://localhost/test",
            embedding_provider="sentence_transformers",
            embedding_model_name="paraphrase-MiniLM-L3-v2",
        )
        create_embed_model(settings)
        mock_st_cls.assert_called_once_with("paraphrase-MiniLM-L3-v2")


# ---------------------------------------------------------------------------
# Unit: create_embed_model from env (integration of config + factory)
# ---------------------------------------------------------------------------


class TestCreateEmbedModelFromEnv:
    """End-to-end: settings from env drive the factory."""

    @patch("llamaindex_runtime.embeddings.SentenceTransformer")
    def test_env_sentence_transformers_round_trip(self, mock_st_cls, monkeypatch: pytest.MonkeyPatch) -> None:
        from llamaindex_runtime.embeddings import SentenceTransformersEmbedding, create_embed_model

        mock_st_cls.return_value.encode.return_value = np.zeros((1, 384), dtype=np.float32)
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
        monkeypatch.setenv("EMBEDDING_PROVIDER", "sentence_transformers")
        monkeypatch.setenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")

        settings = RuntimeSettings.from_env()
        model = create_embed_model(settings)
        assert isinstance(model, SentenceTransformersEmbedding)

    def test_env_mock_round_trip(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from llama_index.core.embeddings import MockEmbedding
        from llamaindex_runtime.embeddings import create_embed_model

        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")

        settings = RuntimeSettings.from_env()
        model = create_embed_model(settings)
        assert isinstance(model, MockEmbedding)


# ---------------------------------------------------------------------------
# Unit: Async methods and class_name
# ---------------------------------------------------------------------------


class TestAdapterAsyncMethods:
    """Async embedding methods must delegate to sync via to_thread."""

    @patch("llamaindex_runtime.embeddings.SentenceTransformer")
    @pytest.mark.asyncio
    async def test_aget_query_embedding(self, mock_st_cls) -> None:
        from llamaindex_runtime.embeddings import SentenceTransformersEmbedding

        fake_vector = np.array([0.5, 0.6], dtype=np.float32)
        mock_st_cls.return_value.encode.return_value = fake_vector

        adapter = SentenceTransformersEmbedding(embed_dim=2)
        result = await adapter._aget_query_embedding("search query")

        assert isinstance(result, list)
        assert len(result) == 2

    @patch("llamaindex_runtime.embeddings.SentenceTransformer")
    @pytest.mark.asyncio
    async def test_aget_text_embedding(self, mock_st_cls) -> None:
        from llamaindex_runtime.embeddings import SentenceTransformersEmbedding

        fake_vector = np.array([0.1, 0.2], dtype=np.float32)
        mock_st_cls.return_value.encode.return_value = fake_vector

        adapter = SentenceTransformersEmbedding(embed_dim=2)
        result = await adapter._aget_text_embedding("some text")

        assert isinstance(result, list)
        assert len(result) == 2

    @patch("llamaindex_runtime.embeddings.SentenceTransformer")
    @pytest.mark.asyncio
    async def test_aget_text_embeddings_uses_single_batch_encode(self, mock_st_cls) -> None:
        from llamaindex_runtime.embeddings import SentenceTransformersEmbedding

        fake_vectors = np.array([[0.1, 0.2], [0.3, 0.4]], dtype=np.float32)
        mock_st_cls.return_value.encode.return_value = fake_vectors

        adapter = SentenceTransformersEmbedding(embed_dim=2)
        result = await adapter._aget_text_embeddings(["text one", "text two"])

        assert len(result) == 2
        assert mock_st_cls.return_value.encode.call_count == 1

    @patch("llamaindex_runtime.embeddings.SentenceTransformer")
    def test_class_name(self, mock_st_cls) -> None:
        from llamaindex_runtime.embeddings import SentenceTransformersEmbedding

        mock_st_cls.return_value.encode.return_value = np.zeros((1, 4), dtype=np.float32)
        adapter = SentenceTransformersEmbedding(embed_dim=4)
        assert adapter.class_name() == "SentenceTransformersEmbedding"


# ---------------------------------------------------------------------------
# Unit: Batch with 1-D array fallback
# ---------------------------------------------------------------------------


class TestAdapterBatch1DFallback:
    """When encode returns 1-D for a single-item batch, adapter must handle it."""

    @patch("llamaindex_runtime.embeddings.SentenceTransformer")
    def test_single_item_batch_1d(self, mock_st_cls) -> None:
        from llamaindex_runtime.embeddings import SentenceTransformersEmbedding

        fake_vector = np.array([0.1, 0.2, 0.3], dtype=np.float32)
        mock_st_cls.return_value.encode.return_value = fake_vector

        adapter = SentenceTransformersEmbedding(embed_dim=3)
        results = adapter._get_text_embeddings(["single text"])
        assert len(results) == 1
        assert len(results[0]) == 3


# ---------------------------------------------------------------------------
# Unit: Defensive raise in create_embed_model
# ---------------------------------------------------------------------------


class TestCreateEmbedModelDefensiveRaise:
    """The factory must raise ValueError for an unsupported provider
    even if config validation were somehow bypassed."""

    def test_unsupported_provider_raises(self) -> None:
        from llamaindex_runtime.embeddings import create_embed_model

        # Bypass frozen dataclass validation by constructing via __class__
        settings = object.__new__(RuntimeSettings)
        # Manually set attributes to bypass __post_init__
        object.__setattr__(settings, "database_url", "postgresql://localhost/test")
        object.__setattr__(settings, "vector_backend", "pgvector")
        object.__setattr__(settings, "tree_strategy", "auto_merging")
        object.__setattr__(settings, "embedding_provider", "nonexistent")
        object.__setattr__(settings, "embedding_model_name", "all-MiniLM-L6-v2")

        with pytest.raises(ValueError, match="Unsupported embedding_provider"):
            create_embed_model(settings)
