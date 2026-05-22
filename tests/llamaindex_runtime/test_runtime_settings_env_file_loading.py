"""File-based TDD tests for .env auto-loading (Phase 3 fix).

This test file proves .env FILE loading works (not just process environment).
Tests use real temporary .env files, NOT monkeypatch.setenv().

Exit criteria:
- .env file values are loaded WITHOUT monkeypatch/setenv
- MockLLM/fallback works when .env file missing
- Real-validation fields readable from local .env file
- No session mutation required (file-based config)
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import pytest
from llama_index.core.llms import MockLLM

from llamaindex_runtime.config import RuntimeSettings
from llamaindex_runtime.llm import get_llm, LiteLLMWrapper, _llm_instance


class TestEnvFileLoading:
    """Tests proving .env FILE loading works (not just process environment)."""

    def test_runtime_settings_reads_from_env_file_not_process_env(self, tmp_path: Path) -> None:
        """RuntimeSettings.from_env_llm_only() should read from .env FILE, not process environment."""
        # Create temporary .env file
        env_file = tmp_path / ".env"
        env_file.write_text(
            "OPENAI_API_KEY=file-key-12345\n"
            "LLM_MODEL=gpt-4-turbo\n"
            "LLM_TEMPERATURE=0.8\n"
            "OPENAI_BASE_URL=https://file.api.com\n"
        )

        # Ensure process environment is EMPTY (no monkeypatch.setenv)
        # This proves we read from FILE, not process
        original_env = dict(os.environ)
        os.environ.clear()

        # Change to tmp_path directory where .env file exists
        original_cwd = os.getcwd()
        os.chdir(tmp_path)

        try:
            # Call from_env_llm_only() - should load from .env file
            llm_config = RuntimeSettings.from_env_llm_only()

            # Verify values from FILE (not process env which is empty)
            assert llm_config["openai_api_key"] == "file-key-12345"
            assert llm_config["llm_model"] == "gpt-4-turbo"
            assert llm_config["llm_temperature"] == 0.8
            assert llm_config["openai_base_url"] == "https://file.api.com"
        finally:
            # Restore original environment and cwd
            os.chdir(original_cwd)
            os.environ.clear()
            os.environ.update(original_env)

    def test_runtime_settings_from_env_reads_full_config_from_file(self, tmp_path: Path) -> None:
        """RuntimeSettings.from_env() should load full config from .env file."""
        # Create temporary .env file with all settings
        env_file = tmp_path / ".env"
        env_file.write_text(
            "DATABASE_URL=postgresql://fileuser@localhost/filedb\n"
            "VECTOR_BACKEND=pgvector\n"
            "TREE_STRATEGY=auto_merging\n"
            "EMBEDDING_PROVIDER=mock\n"
            "OPENAI_API_KEY=file-full-key\n"
            "LLM_MODEL=gpt-4\n"
            "LLM_TEMPERATURE=0.5\n"
        )

        # Clear process environment
        original_env = dict(os.environ)
        os.environ.clear()

        original_cwd = os.getcwd()
        os.chdir(tmp_path)

        try:
            # Load from file
            settings = RuntimeSettings.from_env()

            # Verify all values from FILE
            assert settings.database_url == "postgresql://fileuser@localhost/filedb"
            assert settings.openai_api_key == "file-full-key"
            assert settings.llm_model == "gpt-4"
            assert settings.llm_temperature == 0.5
        finally:
            os.chdir(original_cwd)
            os.environ.clear()
            os.environ.update(original_env)

    def test_env_file_missing_returns_empty_defaults(self, tmp_path: Path) -> None:
        """from_env_llm_only() should return empty defaults when .env file missing."""
        # Ensure NO .env file exists
        env_file = tmp_path / ".env"
        assert not env_file.exists()

        # Clear process environment
        original_env = dict(os.environ)
        os.environ.clear()

        original_cwd = os.getcwd()
        os.chdir(tmp_path)

        try:
            # Should work gracefully when file missing
            llm_config = RuntimeSettings.from_env_llm_only()

            # Defaults (not error)
            assert llm_config["openai_api_key"] == ""
            assert llm_config["llm_model"] == "gpt-4o-mini"
            assert llm_config["llm_temperature"] == 0.0
            assert llm_config["openai_base_url"] == ""
        finally:
            os.chdir(original_cwd)
            os.environ.clear()
            os.environ.update(original_env)


class TestUnifiedLLMSeamEnvFileFlow:
    """Tests proving unified LLM seam works with .env file (no session mutation)."""

    def test_get_llm_reads_from_env_file(self, tmp_path: Path) -> None:
        """get_llm() should read config from .env FILE without session mutation."""
        # Reset singleton
        import llamaindex_runtime.llm
        llamaindex_runtime.llm._llm_instance = None

        # Create .env file with LLM config
        env_file = tmp_path / ".env"
        env_file.write_text(
            "OPENAI_API_KEY=env-file-key-789\n"
            "LLM_MODEL=gpt-4o\n"
            "LLM_TEMPERATURE=0.3\n"
        )

        # Clear process environment (no monkeypatch/setenv)
        original_env = dict(os.environ)
        os.environ.clear()

        original_cwd = os.getcwd()
        os.chdir(tmp_path)

        try:
            # get_llm() should load from .env file
            llm = get_llm()

            # Should be LiteLLMWrapper (key from file)
            assert isinstance(llm, LiteLLMWrapper)
            assert llm.api_key == "env-file-key-789"
            assert llm.model == "gpt-4o"
            assert llm.temperature == 0.3
        finally:
            llamaindex_runtime.llm._llm_instance = None
            os.chdir(original_cwd)
            os.environ.clear()
            os.environ.update(original_env)

    def test_get_llm_returns_mock_when_env_file_missing(self, tmp_path: Path) -> None:
        """get_llm() should return MockLLM when .env file missing (fallback preserved)."""
        # Reset singleton
        import llamaindex_runtime.llm
        llamaindex_runtime.llm._llm_instance = None

        # Ensure NO .env file
        env_file = tmp_path / ".env"
        assert not env_file.exists()

        # Clear process environment
        original_env = dict(os.environ)
        os.environ.clear()

        original_cwd = os.getcwd()
        os.chdir(tmp_path)

        try:
            # Should fallback to MockLLM (no key in file or process)
            llm = get_llm()

            # MockLLM fallback (preserved)
            assert isinstance(llm, MockLLM)
        finally:
            llamaindex_runtime.llm._llm_instance = None
            os.chdir(original_cwd)
            os.environ.clear()
            os.environ.update(original_env)


class TestRealValidationEnvFileSupport:
    """Tests proving real-validation can run with local .env (no session mutation)."""

    def test_real_validation_document_path_from_env_file(self, tmp_path: Path) -> None:
        """REAL_VALIDATION_DOCUMENT_PATH should be readable from .env file."""
        # Create .env with real-validation fields
        env_file = tmp_path / ".env"
        env_file.write_text(
            "DATABASE_URL=postgresql://test@localhost/test\n"
            "REAL_VALIDATION_DOCUMENT_PATH=/path/to/real/doc.pdf\n"
            "REAL_VALIDATION_QUERY=document structure analysis\n"
        )

        # Clear process environment
        original_env = dict(os.environ)
        os.environ.clear()

        original_cwd = os.getcwd()
        os.chdir(tmp_path)

        try:
            # Load from file
            settings = RuntimeSettings.from_env()

            # Real-validation fields from FILE
            # Note: These aren't in RuntimeSettings dataclass yet, but we can read via os.getenv
            # after load_dotenv() has been called
            doc_path = os.getenv("REAL_VALIDATION_DOCUMENT_PATH")
            query = os.getenv("REAL_VALIDATION_QUERY")

            assert doc_path == "/path/to/real/doc.pdf"
            assert query == "document structure analysis"
        finally:
            os.chdir(original_cwd)
            os.environ.clear()
            os.environ.update(original_env)

    def test_real_validation_llm_config_from_env_file_no_session_mutation(self, tmp_path: Path) -> None:
        """Real-validation LLM config should load from .env file without session mutation."""
        # Reset singleton
        import llamaindex_runtime.llm
        llamaindex_runtime.llm._llm_instance = None

        # Create .env file for real validation
        env_file = tmp_path / ".env"
        env_file.write_text(
            "OPENAI_API_KEY=real-validation-key-from-file\n"
            "LLM_MODEL=gpt-4o-mini\n"
            "LLM_TEMPERATURE=0.0\n"
        )

        # Clear process environment (no session mutation!)
        original_env = dict(os.environ)
        os.environ.clear()

        original_cwd = os.getcwd()
        os.chdir(tmp_path)

        try:
            # Load LLM config from FILE
            llm_config = RuntimeSettings.from_env_llm_only()
            llm = get_llm()

            # Real validation can proceed with file-based config
            assert isinstance(llm, LiteLLMWrapper)
            assert llm.api_key == "real-validation-key-from-file"
            # No session mutation required - values from .env file
        finally:
            llamaindex_runtime.llm._llm_instance = None
            os.chdir(original_cwd)
            os.environ.clear()
            os.environ.update(original_env)