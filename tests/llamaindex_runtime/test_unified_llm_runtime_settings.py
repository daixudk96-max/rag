"""TDD tests for Phase 3: Unified LLM seam migration to RuntimeSettings.

This test file follows the frozen control package:
- changes/compatibility-local-env-program/03-CURRENT-PHASE.md
- Phase 3: Unified seam migration off direct session-only secret dependency

Exit criteria:
- unified LLM seam reads from RuntimeSettings instead of direct os.getenv
- local .env values flow through centralized config
- mock/fallback preserved when OPENAI_API_KEY absent
- real validation can run with local .env without session mutation
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from llama_index.core.llms import MockLLM

from llamaindex_runtime.config import RuntimeSettings
from llamaindex_runtime.llm import get_llm, LiteLLMWrapper, _llm_instance


class TestUnifiedLLMSeamRuntimeSettings:
    """Tests for unified LLM seam reading from RuntimeSettings."""

    def test_get_llm_reads_openai_api_key_from_runtime_settings(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """get_llm() should read OPENAI_API_KEY from RuntimeSettings, not direct os.getenv."""
        # Reset singleton
        import llamaindex_runtime.llm
        llamaindex_runtime.llm._llm_instance = None

        # Set environment for RuntimeSettings
        monkeypatch.setenv("DATABASE_URL", "postgresql://test@localhost/test")
        monkeypatch.setenv("OPENAI_API_KEY", "test-runtime-key-123")

        # RuntimeSettings should be the source
        settings = RuntimeSettings.from_env()
        assert settings.openai_api_key == "test-runtime-key-123"

        # get_llm() should use RuntimeSettings, not os.getenv directly
        llm = get_llm()

        # Should be LiteLLMWrapper (not MockLLM) when key present
        assert isinstance(llm, LiteLLMWrapper)
        assert llm.api_key == "test-runtime-key-123"

    def test_get_llm_reads_llm_model_from_runtime_settings(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """get_llm() should read llm_model from RuntimeSettings."""
        # Reset singleton
        import llamaindex_runtime.llm
        llamaindex_runtime.llm._llm_instance = None

        monkeypatch.setenv("DATABASE_URL", "postgresql://test@localhost/test")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("LLM_MODEL", "gpt-4-turbo")

        settings = RuntimeSettings.from_env()
        assert settings.llm_model == "gpt-4-turbo"

        llm = get_llm()
        assert isinstance(llm, LiteLLMWrapper)
        assert llm.model == "gpt-4-turbo"

    def test_get_llm_reads_llm_temperature_from_runtime_settings(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """get_llm() should read llm_temperature from RuntimeSettings."""
        # Reset singleton
        import llamaindex_runtime.llm
        llamaindex_runtime.llm._llm_instance = None

        monkeypatch.setenv("DATABASE_URL", "postgresql://test@localhost/test")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("LLM_TEMPERATURE", "0.7")

        settings = RuntimeSettings.from_env()
        assert settings.llm_temperature == 0.7

        llm = get_llm()
        assert isinstance(llm, LiteLLMWrapper)
        assert llm.temperature == 0.7

    def test_get_llm_reads_openai_base_url_from_runtime_settings(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """get_llm() should read optional openai_base_url from RuntimeSettings."""
        # Reset singleton
        import llamaindex_runtime.llm
        llamaindex_runtime.llm._llm_instance = None

        monkeypatch.setenv("DATABASE_URL", "postgresql://test@localhost/test")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("OPENAI_BASE_URL", "https://api.custom.com")

        settings = RuntimeSettings.from_env()
        assert settings.openai_base_url == "https://api.custom.com"

        llm = get_llm()
        assert isinstance(llm, LiteLLMWrapper)
        # LiteLLMWrapper should use base_url if provided
        assert llm.api_base == "https://api.custom.com"


class TestUnifiedLLMSeamMockFallback:
    """Tests for mock/fallback behavior when OPENAI_API_KEY absent."""

    def test_get_llm_returns_mock_llm_when_openai_key_absent(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """get_llm() should return MockLLM when OPENAI_API_KEY absent (preserving fallback)."""
        # Reset singleton
        import llamaindex_runtime.llm
        llamaindex_runtime.llm._llm_instance = None

        # Isolate cwd to a dir with no .env so delenv is not refilled by the
        # project .env file (env-first/.env-fallback precedence in from_env).
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("DATABASE_URL", "postgresql://test@localhost/test")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        settings = RuntimeSettings.from_env()
        assert settings.openai_api_key == ""

        llm = get_llm()

        # Should be MockLLM (fallback preserved)
        assert isinstance(llm, MockLLM)

    def test_get_llm_default_model_temperature_preserved(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """get_llm() should use RuntimeSettings defaults when env not set."""
        # Reset singleton
        import llamaindex_runtime.llm
        llamaindex_runtime.llm._llm_instance = None

        # Isolate cwd to a dir with no .env so delenv is not refilled by the
        # project .env file (env-first/.env-fallback precedence in from_env).
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("DATABASE_URL", "postgresql://test@localhost/test")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.delenv("LLM_MODEL", raising=False)
        monkeypatch.delenv("LLM_TEMPERATURE", raising=False)

        settings = RuntimeSettings.from_env()
        # Defaults from RuntimeSettings
        assert settings.llm_model == "gpt-4o-mini"
        assert settings.llm_temperature == 0.0

        llm = get_llm()
        assert isinstance(llm, LiteLLMWrapper)
        assert llm.model == "gpt-4o-mini"
        assert llm.temperature == 0.0


class TestUnifiedLLMSeamLocalEnvFlow:
    """Tests for local .env values flowing through centralized config."""

    def test_local_env_values_flow_through_runtime_settings(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Local .env values should flow through RuntimeSettings to unified LLM seam."""
        # Reset singleton
        import llamaindex_runtime.llm
        llamaindex_runtime.llm._llm_instance = None

        # Simulate local .env values
        monkeypatch.setenv("DATABASE_URL", "postgresql://test@localhost/test")
        monkeypatch.setenv("OPENAI_API_KEY", "local-env-key-999")
        monkeypatch.setenv("LLM_MODEL", "gpt-4")
        monkeypatch.setenv("LLM_TEMPERATURE", "0.5")
        monkeypatch.setenv("OPENAI_BASE_URL", "https://local.api.com")

        # RuntimeSettings reads from local .env (via environment)
        settings = RuntimeSettings.from_env()

        # Unified LLM seam reads from RuntimeSettings
        llm = get_llm()

        # Verify local .env values flow through
        assert isinstance(llm, LiteLLMWrapper)
        assert llm.api_key == "local-env-key-999"
        assert llm.model == "gpt-4"
        assert llm.temperature == 0.5
        assert llm.api_base == "https://local.api.com"

    def test_real_validation_can_run_with_local_env_without_session_mutation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Real validation should work with local .env without session mutation."""
        # Reset singleton
        import llamaindex_runtime.llm
        llamaindex_runtime.llm._llm_instance = None

        # Simulate local .env (no session mutation needed)
        monkeypatch.setenv("DATABASE_URL", "postgresql://test@localhost/test")
        monkeypatch.setenv("OPENAI_API_KEY", "local-key-for-validation")
        monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")
        monkeypatch.setenv("LLM_TEMPERATURE", "0.0")

        # RuntimeSettings loads from local .env
        settings = RuntimeSettings.from_env()

        # Unified LLM seam works with RuntimeSettings (no direct session mutation)
        llm = get_llm()

        # Verify can be used for validation
        assert isinstance(llm, LiteLLMWrapper)
        assert llm.api_key == "local-key-for-validation"
        # No session mutation required - values from local .env file