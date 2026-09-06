"""Lazy public facade for unified query entrypoints."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ._query import query

__all__ = ["QueryHit", "QueryResult", "classify_query", "query"]

_EXPORTS = {
    "QueryHit": (".types", "QueryHit"),
    "QueryResult": (".types", "QueryResult"),
    "classify_query": (".classifier", "classify_query"),
    "query": ("._query", "query"),
}


def __getattr__(name: str) -> Any:
    """Load a public entrypoint only when it is requested."""
    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None

    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Expose lazy public names to interactive tooling."""
    return sorted(set(globals()) | set(__all__))
