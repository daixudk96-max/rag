"""Versioned RaNER raw-to-canonical label map for the E2b entity layer.

Phase 16-06. Maps the six frozen ModelScope RaNER raw labels (``PER``,
``LOC``, ``CORP``, ``GRP``, ``CW``, ``PROD``) to their OKF canonical entity
types while always preserving the distinct raw label. The mapping is immutable
(``MappingProxyType``), contains exactly the six frozen entries, and is
versioned. Unknown or invalid raw labels fail closed with ``LabelMapError``
(a ``ValueError`` subclass) carrying the label-map version.

``CORP`` and ``GRP`` both normalize to ``Organization`` but remain distinct
raw-label keys, so provenance is never collapsed. No text coordinate is ever
recovered by substring search. This module imports only the standard library;
it has no dependency on modelscope, torch, transformers, tokenizers,
sentencepiece, or jieba.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

RAINER_LABEL_MAP_VERSION = "e2b-raner-label-map-v1"

RAINER_RAW_TO_CANONICAL: Mapping[str, str] = MappingProxyType(
    {
        "PER": "Person",
        "LOC": "Location",
        "CORP": "Organization",
        "GRP": "Organization",
        "CW": "CreativeWork",
        "PROD": "Product",
    }
)


class LabelMapError(ValueError):
    """Raised when a raw label cannot be resolved by the versioned label map."""


def resolve_label(raw_label: str) -> str:
    """Resolve a raw RaNER label to its frozen canonical entity type.

    The lookup is exact and case-sensitive: whitespace is not normalized, and
    any non-string or unknown raw label fails closed with a versioned
    ``LabelMapError``.
    """
    if type(raw_label) is not str or raw_label not in RAINER_RAW_TO_CANONICAL:
        raise LabelMapError(
            f"unknown raw label {raw_label!r}; label map {RAINER_LABEL_MAP_VERSION}"
        )
    return RAINER_RAW_TO_CANONICAL[raw_label]


__all__ = [
    "LabelMapError",
    "RAINER_LABEL_MAP_VERSION",
    "RAINER_RAW_TO_CANONICAL",
    "resolve_label",
]
