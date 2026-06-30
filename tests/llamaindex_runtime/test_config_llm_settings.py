"""TDD tests for Phase 2: RuntimeSettings LLM configuration extension.

This test file follows the frozen control package:
- changes/compatibility-local-env-program/03-CURRENT-PHASE.md
- Phase 2: RuntimeSettings extension with LLM fields

Exit criteria:
- RuntimeSettings class has LLM-specific fields
- config.py reads from local .env when available
- validation tests confirm new configuration inputs work cleanly
- existing runtime behavior unchanged when LLM key absent
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from llamaindex_runtime.config import RuntimeSettings


@pytest.fixture(autouse=True)
def _isolate_cwd_from_project_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Chdir to a tmp dir with no .env so from_env's .env-fallback does not
    refill keys that tests delenv'd. Project .env (e.g. OPENAI_API_KEY) would
    otherwise override monkeypatch.delenv and break default-value assertions.
    """
    monkeypatch.chdir(tmp_path)


class TestRuntimeSettingsLLMFields:
    """Tests for LLM configuration fields in RuntimeSettings."""

    def test_runtime_settings_has_openai_api_key_field(self) -> None:
        """RuntimeSettings should have openai_api_key field."""
        settings = RuntimeSettings(
            database_url="postgresql://test@localhost/test",
            openai_api_key="test-key-12345",
        )
        assert hasattr(settings, "openai_api_key")
        assert settings.openai_api_key == "test-key-12345"

    def test_runtime_settings_has_llm_model_field_with_default(self) -> None:
        """RuntimeSettings should have llm_model field with default gpt-4o-mini."""
        settings = RuntimeSettings(
            database_url="postgresql://test@localhost/test",
        )
        assert hasattr(settings, "llm_model")
        assert settings.llm_model == "gpt-4o-mini"

    def test_runtime_settings_has_llm_temperature_field_with_default(self) -> None:
        """RuntimeSettings should have llm_temperature field with default 0.0."""
        settings = RuntimeSettings(
            database_url="postgresql://test@localhost/test",
        )
        assert hasattr(settings, "llm_temperature")
        assert settings.llm_temperature == 0.0

    def test_runtime_settings_has_openai_base_url_optional_field(self) -> None:
        """RuntimeSettings should have optional openai_base_url field."""
        settings = RuntimeSettings(
            database_url="postgresql://test@localhost/test",
            openai_base_url="https://custom.openai.api",
        )
        assert hasattr(settings, "openai_base_url")
        assert settings.openai_base_url == "https://custom.openai.api"

    def test_runtime_settings_llm_fields_can_be_empty_or_none(self) -> None:
        """LLM fields should accept empty values for local-only config."""
        settings = RuntimeSettings(
            database_url="postgresql://test@localhost/test",
            openai_api_key="",
            openai_base_url="",
        )
        assert settings.openai_api_key == ""
        assert settings.openai_base_url == ""


class TestRuntimeSettingsFromEnvLLM:
    """Tests for from_env() loading LLM configuration."""

    def test_from_env_reads_openai_api_key_from_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """from_env() should read OPENAI_API_KEY from environment."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://test@localhost/test")
        monkeypatch.setenv("OPENAI_API_KEY", "test-env-key-67890")

        settings = RuntimeSettings.from_env()
        assert settings.openai_api_key == "test-env-key-67890"

    def test_from_env_reads_llm_model_from_env_with_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """from_env() should read LLM_MODEL with default fallback."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://test@localhost/test")
        monkeypatch.delenv("LLM_MODEL", raising=False)

        settings = RuntimeSettings.from_env()
        assert settings.llm_model == "gpt-4o-mini"

    def test_from_env_reads_llm_temperature_from_env_with_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """from_env() should read LLM_TEMPERATURE with default fallback."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://test@localhost/test")
        monkeypatch.delenv("LLM_TEMPERATURE", raising=False)

        settings = RuntimeSettings.from_env()
        assert settings.llm_temperature == 0.0

    def test_from_env_reads_openai_base_url_optional(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """from_env() should optionally read OPENAI_BASE_URL."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://test@localhost/test")
        monkeypatch.setenv("OPENAI_BASE_URL", "https://api.custom.com")

        settings = RuntimeSettings.from_env()
        assert settings.openai_base_url == "https://api.custom.com"


class TestRuntimeSettingsDefaultBehavior:
    """Tests for preserving existing behavior when LLM key absent."""

    def test_runtime_settings_works_without_llm_fields(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """RuntimeSettings should work when no LLM fields provided."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://test@localhost/test")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("LLM_MODEL", raising=False)
        monkeypatch.delenv("LLM_TEMPERATURE", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

        settings = RuntimeSettings.from_env()
        # Should succeed without error
        assert settings.database_url == "postgresql://test@localhost/test"
        # LLM fields should have safe defaults
        assert settings.openai_api_key == ""
        assert settings.llm_model == "gpt-4o-mini"
        assert settings.llm_temperature == 0.0

    def test_runtime_settings_validation_unchanged_for_vector_backend(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Existing validation for vector_backend should remain unchanged."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://test@localhost/test")
        monkeypatch.setenv("VECTOR_BACKEND", "invalid_backend")

        with pytest.raises(ValueError, match="Unsupported vector backend"):
            RuntimeSettings.from_env()

    def test_runtime_settings_validation_unchanged_for_embedding_provider(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Existing validation for embedding_provider should remain unchanged."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://test@localhost/test")
        monkeypatch.setenv("EMBEDDING_PROVIDER", "invalid_provider")

        with pytest.raises(ValueError, match="Unsupported embedding_provider"):
            RuntimeSettings.from_env()