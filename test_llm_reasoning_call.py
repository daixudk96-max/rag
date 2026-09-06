"""Test LLM reasoning call implementation for Task 1.1.

Tests verify:
1. _llm_judge_relevant_pages() uses unified LLM seam
2. LLM receives properly formatted tree structure
3. Response parsing extracts relevant page numbers
4. Mock LLM returns expected filtered results
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
from typing import Any, ClassVar

from llama_index.core.llms import LLM, CompletionResponse, LLMMetadata


# Custom Mock LLM that we control
class ControllableMockLLM(LLM):
    """Mock LLM with configurable response."""
    _response_text: str = "1,5"
    _model_name: ClassVar[str] = "mock-llm"

    @property
    def metadata(self) -> Any:
        return LLMMetadata(model_name=self._model_name)

    def complete(self, prompt: str, **kwargs: Any) -> CompletionResponse:
        return CompletionResponse(text=self._response_text)

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        from llama_index.core.llms import ChatResponse
        return ChatResponse(message={"role": "assistant", "content": self._response_text})

    async def acomplete(self, prompt: str, **kwargs: Any) -> CompletionResponse:
        return self.complete(prompt, **kwargs)

    async def achat(self, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        return self.chat(messages, **kwargs)

    def stream_complete(self, prompt: str, **kwargs: Any) -> Any:
        raise NotImplementedError("Streaming not supported")

    async def astream_complete(self, prompt: str, **kwargs: Any) -> Any:
        raise NotImplementedError("Async streaming not supported")

    def stream_chat(self, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        raise NotImplementedError("Chat streaming not supported")

    async def astream_chat(self, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        raise NotImplementedError("Async chat streaming not supported")


# Import implementation
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from llamaindex_runtime.tree.reasoning_backend import ReasoningTreeBackend


def test_llm_judge_relevant_pages_uses_unified_seam():
    """Test that _llm_judge_relevant_pages() uses get_llm() from unified seam."""
    print("=== Unified Seam Usage Verification ===\n")

    backend = ReasoningTreeBackend(llm_model="gpt-4o-mini")

    # Mock tree structure
    structure = [
        {"title": "Introduction", "page_no": 1, "heading_path": "# Introduction"},
        {"title": "SWOT Analysis", "page_no": 5, "heading_path": "# SWOT Analysis"},
        {"title": "Conclusion", "page_no": 10, "heading_path": "# Conclusion"},
    ]

    # Create controllable mock LLM
    mock_llm = ControllableMockLLM()
    mock_llm._response_text = "1,5"

    # Patch get_llm to return our mock
    with patch("llamaindex_runtime.tree.reasoning_backend.get_llm", return_value=mock_llm):
        result = backend._llm_judge_relevant_pages(
            query_text="What is the SWOT analysis?",
            structure=structure
        )

    # Verify unified seam was called
    print("[OK] _llm_judge_relevant_pages() uses get_llm()")
    print(f"[OK] Mock LLM response: {result}")
    assert result == "1,5", f"Expected '1,5', got '{result}'"


def test_llm_judge_relevant_pages_formats_structure():
    """Test that LLM receives properly formatted tree structure."""
    print("\n=== Structure Formatting Verification ===\n")

    backend = ReasoningTreeBackend()

    structure = [
        {"title": "Introduction", "page_no": 1},
        {"title": "Methods", "page_no": 3},
        {"title": "Results", "page_no": 7},
    ]

    # Capture prompt sent to LLM
    captured_prompts = []

    class PromptCaptureLLM(ControllableMockLLM):
        def complete(self, prompt: str, **kwargs: Any) -> CompletionResponse:
            captured_prompts.append(prompt)
            return CompletionResponse(text="1,3")

    mock_llm = PromptCaptureLLM()

    with patch("llamaindex_runtime.tree.reasoning_backend.get_llm", return_value=mock_llm):
        backend._llm_judge_relevant_pages(
            query_text="test query",
            structure=structure
        )

    # Verify prompt contains structure information (ultra-compact format)
    assert len(captured_prompts) > 0, "LLM should have been called"
    prompt_text = captured_prompts[0]

    print("[OK] LLM receives formatted structure")
    print(f"  - Prompt length: {len(prompt_text)} chars")
    assert "Introduction" in prompt_text, "Prompt should contain structure titles"
    # Ultra-compact format: "1:Introduction" (not "page 1")
    assert "1:" in prompt_text or "1 " in prompt_text, "Prompt should contain page numbers in compact format"
    print("[OK] Structure formatting verified (ultra-compact)")


def test_llm_judge_relevant_pages_parses_response():
    """Test that response parsing extracts relevant page numbers."""
    print("\n=== Response Parsing Verification ===\n")

    backend = ReasoningTreeBackend()

    structure = [
        {"title": "Chapter 1", "page_no": 1},
        {"title": "Chapter 2", "page_no": 5},
        {"title": "Chapter 3", "page_no": 9},
    ]

    # Test different response formats
    # Format 1: Comma-separated pages
    mock_llm = ControllableMockLLM()
    mock_llm._response_text = "1,5"

    with patch("llamaindex_runtime.tree.reasoning_backend.get_llm", return_value=mock_llm):
        result1 = backend._llm_judge_relevant_pages("test", structure)
        print(f"[OK] Comma-separated format: {result1}")
        assert result1 == "1,5", "Should parse comma-separated format"

    # Format 2: JSON array
    mock_llm._response_text = '[1, 5]'
    with patch("llamaindex_runtime.tree.reasoning_backend.get_llm", return_value=mock_llm):
        result2 = backend._llm_judge_relevant_pages("test", structure)
        print(f"[OK] JSON array format: {result2}")
        assert result2 == "1,5", "Should parse JSON array format"

    # Format 3: Natural language with numbers
    mock_llm._response_text = "pages 1 and 5 are relevant"
    with patch("llamaindex_runtime.tree.reasoning_backend.get_llm", return_value=mock_llm):
        result3 = backend._llm_judge_relevant_pages("test", structure)
        print(f"[OK] Natural language format: {result3}")
        # Should extract 1 and 5 from text
        assert "1" in result3 and "5" in result3, "Should extract numbers from natural language"


def test_llm_judge_relevant_pages_returns_filtered_subset():
    """Test that method returns filtered subset (not all nodes)."""
    print("\n=== Filtering Verification ===\n")

    backend = ReasoningTreeBackend()

    structure = [
        {"title": "Intro", "page_no": 1},
        {"title": "Main", "page_no": 3},
        {"title": "End", "page_no": 5},
    ]

    mock_llm = ControllableMockLLM()
    mock_llm._response_text = "3"

    with patch("llamaindex_runtime.tree.reasoning_backend.get_llm", return_value=mock_llm):
        result = backend._llm_judge_relevant_pages("test", structure)

    # Verify filtered subset (not all pages)
    pages_list = [p for p in result.split(",") if p.strip()]
    assert len(pages_list) < len(structure), "Should return filtered subset, not all nodes"
    print(f"[OK] Filtered subset: {len(pages_list)} pages (vs {len(structure)} total)")
    print("[OK] Token savings demonstrated (not retrieving all nodes)")


if __name__ == "__main__":
    test_llm_judge_relevant_pages_uses_unified_seam()
    test_llm_judge_relevant_pages_formats_structure()
    test_llm_judge_relevant_pages_parses_response()
    test_llm_judge_relevant_pages_returns_filtered_subset()

    print("\n=== All RED phase tests passed ===")
    print("Task 1.1: LLM reasoning call tests written (await GREEN implementation)")