"""Lazy public facade for Open Knowledge Format parser types."""

from __future__ import annotations

from importlib import import_module
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .parser import OKFDocument, OKFFrontmatter, OKFParagraph, OKFParser


__all__ = ["OKFParser", "OKFDocument", "OKFFrontmatter", "OKFParagraph"]

_LAZY_EXPORTS = MappingProxyType(
    {
        "OKFParser": ("llamaindex_runtime.okf.parser", "OKFParser"),
        "OKFDocument": ("llamaindex_runtime.okf.parser", "OKFDocument"),
        "OKFFrontmatter": ("llamaindex_runtime.okf.parser", "OKFFrontmatter"),
        "OKFParagraph": ("llamaindex_runtime.okf.parser", "OKFParagraph"),
    }
)


def __getattr__(name: str) -> Any:
    """Resolve and cache a public parser export on first access."""
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
