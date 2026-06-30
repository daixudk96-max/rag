"""QueryAgent - minimal FunctionAgent wrapper for retrieval orchestration.

This is a factory function that creates a FunctionAgent configured with RetrievalTool.
It demonstrates minimal formal-runtime control-plane without reimplementing
agent logic.

Paradigm choice: FunctionAgent (LLM function calling) over ReActAgent (prompting).
Per LlamaIndex current guidance, FunctionAgent is the recommended paradigm for
simple single-tool agents; our RetrievalTool is a single retrieval tool, so
function calling is the appropriate fit. Both paradigms remain supported in
llama-index-core 0.14.x; FunctionAgent shares the same constructor signature as
ReActAgent, so this migration preserves the existing factory contract.
"""
from __future__ import annotations

from typing import Any

from llama_index.core.agent import FunctionAgent
from llama_index.core.llms import LLM
from llama_index.core.tools import BaseTool

from .retrieval_tool import RetrievalTool


def QueryAgent(
    tools: list[BaseTool] | None = None,
    llm: LLM | None = None,
    *,
    source_path: str | None = None,
    registry: Any | None = None,
    embed_model: Any | None = None,
    driver: Any | None = None,
    entity_id: Any | None = None,
    similarity_top_k: int | None = None,
    version_id: Any | None = None,
    limit: int | None = None,
    depth: int | None = None,
    vector_backend: Any | None = None,
    **kwargs: Any,
) -> FunctionAgent:
    """Factory function that creates a FunctionAgent with RetrievalTool.

    This is a minimal wrapper that configures a LlamaIndex FunctionAgent
    with the provided tools (typically RetrievalTool). It does not
    implement agent logic - just orchestrates existing LlamaIndex primitives.

    Parameters
    ----------
    tools:
        List of tools for the agent. If None, will auto-construct a RetrievalTool
        from source_path, registry, and embed_model.
    llm:
        LLM for agent reasoning. Required for FunctionAgent.
    source_path:
        Path to the source PDF document. Required if tools is None.
    registry:
        A RegistryWriter instance. Required if tools is None.
    embed_model:
        Embedding model for vector/tree retrieval paths. Required if tools is None.
    driver:
        Optional Neo4j driver instance for graph path.
    entity_id:
        Optional UUID for graph path (must be paired with driver).
    similarity_top_k:
        Optional top-k for vector/tree backends.
    version_id:
        Optional version filter for keyword search.
    limit:
        Optional maximum results for keyword search.
    depth:
        Optional traversal depth for graph queries.
    **kwargs:
        Additional kwargs passed to FunctionAgent (e.g., memory, system_prompt).

    Returns
    -------
    FunctionAgent
        Configured FunctionAgent instance ready to use tools for retrieval.

    Raises
    ------
    ValueError
        If tools is empty.
        If llm is None.
        If tools is None and source_path is missing.
        If tools is None and registry or embed_model is missing.
    """
    if llm is None:
        raise ValueError("llm is required for FunctionAgent")

    # Auto-construct RetrievalTool if tools is None
    if tools is None:
        if source_path is None:
            raise ValueError("source_path is required when tools is not provided")
        if registry is None:
            raise ValueError("registry is required when tools is not provided")
        if embed_model is None:
            raise ValueError("embed_model is required when tools is not provided")

        # Create RetrievalTool with provided parameters
        tools = [
            RetrievalTool(
                source_path=source_path,
                registry=registry,
                embed_model=embed_model,
                driver=driver,
                entity_id=entity_id,
                similarity_top_k=similarity_top_k,
                version_id=version_id,
                limit=limit,
                depth=depth,
                vector_backend=vector_backend,
            )
        ]

    if len(tools) == 0:
        raise ValueError("tools must contain at least one tool")

    # Create and return FunctionAgent with provided tools and LLM
    # This is minimal - just wrapping LlamaIndex's FunctionAgent
    return FunctionAgent(
        tools=tools,
        llm=llm,
        **kwargs,
    )