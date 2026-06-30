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
        LlamaIndex LLM instance configured from RuntimeSettings.

    Configuration
    -------------
    - Reads from RuntimeSettings (centralized config):
      - openai_api_key: required for real LLM
      - llm_model: default "gpt-4o-mini"
      - llm_temperature: default 0.0
      - openai_base_url: optional custom API endpoint
    - If openai_api_key exists → Use litellm with OpenAI
    - Otherwise → MockLLM (for testing)

    Phase 3 Migration:
    - Migrated off direct os.getenv to RuntimeSettings
    - Local .env values flow through centralized config
    - No session mutation required
    - LLM config independent of DATABASE_URL

    Returns
    -------
    LLM
        Singleton LLM instance.
    """
    global _llm_instance

    if _llm_instance is not None:
        return _llm_instance

    # Phase 3: Read from RuntimeSettings (not direct os.getenv)
    # Use from_env_llm_only() to avoid DATABASE_URL requirement
    from llamaindex_runtime.config import RuntimeSettings
    llm_config = RuntimeSettings.from_env_llm_only()

    if llm_config["openai_api_key"]:
        # Use litellm completion wrapper (compatible with LlamaIndex)
        # litellm is already used by PageIndex donor
        # Create custom LLM wrapper that calls litellm
        _llm_instance = LiteLLMWrapper(
            model=llm_config["llm_model"],
            api_key=llm_config["openai_api_key"],
            temperature=llm_config["llm_temperature"],
            api_base=llm_config["openai_base_url"] if llm_config["openai_base_url"] else None,
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
    api_base: str | None = None  # Phase 3: Support custom base URL

    # ClassVar for metadata (LlamaIndex protocol)
    _model_name: ClassVar[str] = "litellm-gpt-4o-mini"

    @property
    def metadata(self) -> Any:
        """LLM metadata (LlamaIndex protocol).

        Provides complete metadata so downstream consumers (e.g., FunctionAgent
        capability detection) can correctly identify this as a function-calling
        chat model. litellm routes to OpenAI-compatible endpoints that support
        tool/function calling, hence ``is_function_calling_model=True``.
        """
        from llama_index.core.llms import LLMMetadata
        return LLMMetadata(
            model_name=self._model_name,
            context_window=4096,
            num_output=1024,
            is_chat_model=True,
            is_function_calling_model=True,
        )

    def complete(self, prompt: str, **kwargs: Any) -> CompletionResponse:
        """Complete prompt using litellm."""
        # Use litellm.completion (same as PageIndex)
        response = litellm.completion(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.temperature,
            api_key=self.api_key,
            api_base=self.api_base,
        )

        # Return CompletionResponse (LlamaIndex protocol)
        return CompletionResponse(
            text=response.choices[0].message.content,
        )

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        """Chat completion using litellm."""
        response = litellm.completion(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            api_key=self.api_key,
            api_base=self.api_base,
        )
        from llama_index.core.llms import ChatResponse
        return ChatResponse(message=response.choices[0].message)

    async def acomplete(self, prompt: str, **kwargs: Any) -> CompletionResponse:
        """Async complete - delegates to sync complete for simplicity."""
        return self.complete(prompt, **kwargs)

    async def achat(self, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        """Async chat - delegates to sync chat for simplicity."""
        return self.chat(messages, **kwargs)

    def stream_complete(self, prompt: str, **kwargs: Any) -> Any:
        """Stream complete - not implemented, raises NotImplementedError."""
        raise NotImplementedError("Streaming not supported in LiteLLMWrapper")

    async def astream_complete(self, prompt: str, **kwargs: Any) -> Any:
        """Async stream complete - not implemented."""
        raise NotImplementedError("Async streaming not supported in LiteLLMWrapper")

    def stream_chat(self, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        """Stream chat - not implemented."""
        raise NotImplementedError("Chat streaming not supported in LiteLLMWrapper")

    async def astream_chat(self, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        """Async stream chat - not implemented."""
        raise NotImplementedError("Async chat streaming not supported in LiteLLMWrapper")


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