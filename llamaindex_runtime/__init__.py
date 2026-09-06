"""Lazy public facade for the LlamaIndex runtime package."""

from __future__ import annotations

from importlib import import_module
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .agent import QueryAgent, RetrievalTool
    from .cli import format_result_as_json, main
    from .config import RuntimeSettings
    from .embeddings import SentenceTransformersEmbedding, create_embed_model
    from .entrypoints import QueryHit, QueryResult, classify_query, query
    from .interfaces import CanonicalSpan
    from .logging import JsonFormatter, get_request_logger, setup_logging
    from .registry.contracts import RegistryWriter
    from .registry.postgres_adapter import PostgresRegistryWriter
    from .workflow import HybridRetrievalWorkflow


__all__ = [
    "CanonicalSpan",
    "HybridRetrievalWorkflow",
    "JsonFormatter",
    "PostgresRegistryWriter",
    "QueryAgent",
    "QueryHit",
    "QueryResult",
    "RegistryWriter",
    "RetrievalTool",
    "RuntimeSettings",
    "SentenceTransformersEmbedding",
    "classify_query",
    "create_embed_model",
    "format_result_as_json",
    "get_request_logger",
    "main",
    "query",
    "setup_logging",
]
__version__ = "0.1.0"

_LAZY_EXPORTS = MappingProxyType(
    {
        "CanonicalSpan": ("llamaindex_runtime.interfaces", "CanonicalSpan"),
        "HybridRetrievalWorkflow": (
            "llamaindex_runtime.workflow",
            "HybridRetrievalWorkflow",
        ),
        "JsonFormatter": ("llamaindex_runtime.logging", "JsonFormatter"),
        "PostgresRegistryWriter": (
            "llamaindex_runtime.registry.postgres_adapter",
            "PostgresRegistryWriter",
        ),
        "QueryAgent": ("llamaindex_runtime.agent", "QueryAgent"),
        "QueryHit": ("llamaindex_runtime.entrypoints", "QueryHit"),
        "QueryResult": ("llamaindex_runtime.entrypoints", "QueryResult"),
        "RegistryWriter": ("llamaindex_runtime.registry.contracts", "RegistryWriter"),
        "RetrievalTool": ("llamaindex_runtime.agent", "RetrievalTool"),
        "RuntimeSettings": ("llamaindex_runtime.config", "RuntimeSettings"),
        "SentenceTransformersEmbedding": (
            "llamaindex_runtime.embeddings",
            "SentenceTransformersEmbedding",
        ),
        "classify_query": ("llamaindex_runtime.entrypoints", "classify_query"),
        "create_embed_model": ("llamaindex_runtime.embeddings", "create_embed_model"),
        "format_result_as_json": ("llamaindex_runtime.cli", "format_result_as_json"),
        "get_request_logger": ("llamaindex_runtime.logging", "get_request_logger"),
        "main": ("llamaindex_runtime.cli", "main"),
        "query": ("llamaindex_runtime.entrypoints", "query"),
        "setup_logging": ("llamaindex_runtime.logging", "setup_logging"),
    }
)


def __getattr__(name: str) -> Any:
    """Resolve and cache a public export on first access."""
    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError:
        raise AttributeError(name) from None
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Expose lazy public names to interactive and introspection tools."""
    return sorted(set(globals()) | set(__all__))
