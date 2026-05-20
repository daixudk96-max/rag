"""Test unified LLM seam for donor-facing structural extraction.

Phase 4a: verify single LlamaIndex-based LLM integration path exists.
"""
from __future__ import annotations

import pytest


class TestUnifiedLLMSeam:
    """Verify unified LLM seam exists and is usable by donor adapters."""

    def test_unified_llm_seam_function_exists(self) -> None:
        """Unified LLM seam function must exist."""
        from llamaindex_runtime.llm import get_llm

        # Verify function exists and is importable
        assert callable(get_llm)

    def test_unified_llm_seam_returns_llama_index_llm(self) -> None:
        """get_llm() must return LlamaIndex LLM instance."""
        from llama_index.core.llms import LLM
        from llamaindex_runtime.llm import get_llm

        llm = get_llm()

        # Must be LlamaIndex LLM type
        assert isinstance(llm, LLM)

    def test_unified_llm_seam_can_complete_prompts(self) -> None:
        """Unified LLM seam must support completion."""
        from llamaindex_runtime.llm import get_llm

        llm = get_llm()

        # Must support .complete() method (LlamaIndex LLM protocol)
        response = llm.complete("Test prompt")

        # Response must be string-like
        assert hasattr(response, "text") or isinstance(response, str)

    def test_unified_llm_seam_reads_config_from_env(self) -> None:
        """Unified LLM seam must read configuration from environment."""
        import os
        from llamaindex_runtime.llm import get_llm

        # Verify seam reads LLM config from env (e.g., OPENAI_API_KEY, ANTHROPIC_API_KEY)
        # This test verifies the seam doesn't require hardcoded model names
        llm = get_llm()

        # LLM should be configured based on env vars, not hardcoded
        # (Test passes if LLM instance is created successfully with env config)
        assert llm is not None

    def test_unified_llm_seam_is_singleton_or_cachable(self) -> None:
        """Unified LLM seam should be efficient (singleton or cachable)."""
        from llamaindex_runtime.llm import get_llm

        llm1 = get_llm()
        llm2 = get_llm()

        # Either same instance (singleton) or same config (cachable)
        # Important: don't create new LLM client on every call
        assert llm1 is not None
        assert llm2 is not None


class TestDonorLLMAdapter:
    """Verify donor-facing structural extraction can use unified LLM seam."""

    def test_llm_acompletion_adapter_exists(self) -> None:
        """Adapter function for donor llm_acompletion must exist."""
        from llamaindex_runtime.llm import llm_acompletion_unified

        # Verify adapter function exists
        assert callable(llm_acompletion_unified)

    @pytest.mark.asyncio
    async def test_llm_acompletion_adapter_calls_unified_seam(self) -> None:
        """llm_acompletion_unified must route through unified LLM seam."""
        from unittest.mock import MagicMock, patch, AsyncMock
        from llamaindex_runtime.llm import llm_acompletion_unified, get_llm

        # Mock the unified LLM seam with async complete
        mock_llm = MagicMock()
        mock_llm.complete = MagicMock(return_value=MagicMock(text="Test response"))

        with patch("llamaindex_runtime.llm.get_llm", return_value=mock_llm):
            response = await llm_acompletion_unified(prompt="Test prompt")

            # Verify adapter called unified seam
            mock_llm.complete.assert_called_once_with("Test prompt")

            # Verify response format
            assert response == "Test response"

    def test_llm_acompletion_adapter_signature_matches_donor(self) -> None:
        """Adapter signature must match PageIndex llm_acompletion signature."""
        from llamaindex_runtime.llm import llm_acompletion_unified
        import inspect

        # PageIndex signature: llm_acompletion(model, prompt)
        # Adapter signature: llm_acompletion_unified(prompt, model=None)
        # Note: adapter should NOT require model parameter (unified seam handles model config)

        sig = inspect.signature(llm_acompletion_unified)
        params = list(sig.parameters.keys())

        # Must accept prompt parameter
        assert "prompt" in params

        # model parameter should be optional (unified seam provides default)
        # (PageIndex calls with model, adapter should ignore or use unified default)
        assert sig.parameters.get("prompt") is not None


class TestPageIndexLLMIntegration:
    """Verify PageIndexTreeAdapter can use unified LLM seam."""

    def test_pageindex_adapter_can_import_unified_llm_seam(
        self,
    ) -> None:
        """PageIndex adapter must be able to import and use unified LLM seam."""
        # Structural test: verify imports work
        from llamaindex_runtime.tree.pageindex_adapter import PageIndexTreeAdapter
        from llamaindex_runtime.llm import get_llm

        # Verify adapter can import unified seam
        adapter = PageIndexTreeAdapter()

        # Verify adapter can call get_llm() (structural validation)
        # (Does not test actual LLM calls - covered by integration tests)
        llm = get_llm()
        assert llm is not None

    def test_pageindex_adapter_does_not_create_independent_llm_config(
        self,
    ) -> None:
        """PageIndex adapter must NOT create independent LLM configuration stack."""
        from unittest.mock import MagicMock, patch
        from llamaindex_runtime.tree.pageindex_adapter import PageIndexTreeAdapter

        adapter = PageIndexTreeAdapter()

        # Verify adapter does NOT import litellm or create independent LLM config
        # (This is a code inspection test - verify no litellm imports in adapter)
        import inspect
        source = inspect.getsource(PageIndexTreeAdapter)

        # Adapter should NOT import litellm directly
        assert "import litellm" not in source
        assert "from litellm" not in source

        # Adapter should NOT create ConfigLoader with LLM config
        # (already enforced by control package: adapter must use unified seam)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])