"""Unified LLM seam for donor-facing structural extraction.

Phase 4a: Single LlamaIndex-based LLM integration path.

This module provides:
- get_llm(): Unified LLM instance factory (singleton)
- llm_acompletion_unified(): Adapter for donor structural extraction

Configuration:
- Environment variables: OPENAI_API_KEY
- Uses litellm (same as PageIndex) or MockLLM for testing

Usage:
    from llamaindex_runtime.llm import get_llm

    llm = get_llm()
    response = llm.complete("Prompt")

    # Or use adapter for donor integration:
    from llamaindex_runtime.llm import llm_acompletion_unified
    response = llm_acompletion_unified(prompt="Prompt")
"""
from __future__ import annotations

import os
import litellm
from typing import Any, ClassVar

from llama_index.core.llms import LLM, MockLLM, CompletionResponse


# Singleton LLM instance
_llm_instance: LLM | None = None


def get_llm() -> LLM:
    """Get unified LLM instance (singleton).

    Returns
    -------
    LLM
        LlamaIndex LLM instance configured from environment.

    Configuration
    -------------
    - If OPENAI_API_KEY exists → Use litellm with OpenAI
    - Otherwise → MockLLM (for testing)

    Returns
    -------
    LLM
        Singleton LLM instance.
    """
    global _llm_instance

    if _llm_instance is not None:
        return _llm_instance

    # Check if OpenAI API key exists
    openai_key = os.getenv("OPENAI_API_KEY")

    if openai_key:
        # Use litellm completion wrapper (compatible with LlamaIndex)
        # litellm is already used by PageIndex donor
        # Create custom LLM wrapper that calls litellm
        _llm_instance = LiteLLMWrapper(
            model="gpt-4o-mini",
            api_key=openai_key,
        )
    else:
        # Use MockLLM for testing (no real API calls)
        _llm_instance = MockLLM()

    return _llm_instance


class LiteLLMWrapper(LLM):
    """Custom LLM wrapper using litellm for unified seam.

    This wrapper allows using litellm (which PageIndex already uses)
    as a LlamaIndex LLM instance, preventing duplicate LLM abstraction layers.
    """

    model: str = "gpt-4o-mini"
    api_key: str | None = None
    temperature: float = 0.0

    # ClassVar for metadata (LlamaIndex protocol)
    _model_name: ClassVar[str] = "litellm-gpt-4o-mini"

    def complete(self, prompt: str, **kwargs: Any) -> CompletionResponse:
        """Complete prompt using litellm."""
        # Use litellm.completion (same as PageIndex)
        response = litellm.completion(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.temperature,
            api_key=self.api_key,
        )

        # Return CompletionResponse (LlamaIndex protocol)
        return CompletionResponse(
            text=response.choices[0].message.content,
        )


async def llm_acompletion_unified(
    prompt: str,
    model: str | None = None,
) -> str:
    """Adapter for donor structural extraction (PageIndex llm_acompletion).

    This adapter routes donor LLM calls through unified seam,
    preventing donor-owned independent LLM configuration stacks.

    Parameters
    ----------
    prompt:
        Prompt string (same as PageIndex llm_acompletion).
    model:
        Model name (ignored - unified seam provides default).

    Returns
    -------
    str
        Completion text.

    Note
    ----
    - Signature matches PageIndex llm_acompletion(model, prompt)
    - model parameter is ignored (unified seam handles model config)
    - Uses LlamaIndex LLM.complete() internally
    """
    llm = get_llm()

    # LlamaIndex LLM.complete() returns CompletionResponse
    response = llm.complete(prompt)

    # Extract text from CompletionResponse
    return response.text


def llm_completion_unified(
    prompt: str,
    model: str | None = None,
    chat_history: list[dict[str, str]] | None = None,
) -> str:
    """Synchronous adapter for donor llm_completion.

    Parameters
    ----------
    prompt:
        Prompt string.
    model:
        Model name (ignored).
    chat_history:
        Chat history (optional, ignored for now).

    Returns
    -------
    str
        Completion text.
    """
    llm = get_llm()
    response = llm.complete(prompt)
    return response.text