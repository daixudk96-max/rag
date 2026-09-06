"""Explicit normalization contract for span generation.

This module makes normalization rules first-class, testable, and
configurable, replacing the implicit rules previously scattered across
DoclingIngestor private static methods and CanonicalSpan.__post_init__.

The contract defines how raw node data (text, metadata) is normalized
into the fields required for CanonicalSpan construction.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NormalizationRules:
    """Explicit, verifiable configuration of normalization behavior.

    These rules define how text, headings, page numbers, and offsets
    are extracted and normalized from raw node metadata.
    """

    collapse_whitespace: bool = True
    strip_headings: bool = True
    filter_empty_headings: bool = True
    heading_separator_priority: tuple[str, ...] = (" > ", ">")
    page_number_keys: tuple[str, ...] = ("page_no",)
    offset_keys: tuple[str, ...] = ("offset", "start_offset", "doc_offset")


@dataclass(frozen=True)
class NormalizedNodeData:
    """The normalized output for a single node, ready for CanonicalSpan construction.

    This is the result of applying the NormalizationContract to raw node data.
    All fields are in their final, canonical form.
    """

    text: str
    headings: tuple[str, ...]
    page_no: int | None
    offset: int


class NormalizationContract:
    """Explicit normalization contract: raw node data -> normalized span data.

    This makes normalization rules first-class, testable, and configurable,
    replacing the implicit normalization previously scattered across
    DoclingIngestor static methods and CanonicalSpan.__post_init__.

    Usage:
        contract = NormalizationContract()  # default rules
        normalized = contract.normalize(raw_text=node_text, metadata=node_metadata, ordinal=0)
        span = CanonicalSpan(..., text=normalized.text, headings=normalized.headings, ...)
    """

    def __init__(self, rules: NormalizationRules | None = None) -> None:
        self._rules = rules or NormalizationRules()

    @property
    def rules(self) -> NormalizationRules:
        return self._rules

    def normalize_text(self, text: str) -> str:
        if self._rules.collapse_whitespace:
            return " ".join(text.split())
        return text

    def normalize_headings(self, raw_headings: Any) -> tuple[str, ...]:
        if raw_headings is None:
            return ()
        if isinstance(raw_headings, str):
            parts = self._split_heading_string(raw_headings)
        else:
            parts = list(raw_headings)

        if self._rules.strip_headings:
            parts = [p.strip() for p in parts]
        if self._rules.filter_empty_headings:
            parts = [p for p in parts if p]
        return tuple(parts)

    def _split_heading_string(self, raw: str) -> list[str]:
        for sep in self._rules.heading_separator_priority:
            if sep in raw:
                return raw.split(sep)
        return [raw]

    def extract_page_no(self, metadata: dict[str, Any]) -> int | None:
        for key in self._rules.page_number_keys:
            value = metadata.get(key)
            if isinstance(value, int) and value >= 0:
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
        return None

    def extract_offset(self, metadata: dict[str, Any], ordinal: int) -> int:
        for key in self._rules.offset_keys:
            value = metadata.get(key)
            if isinstance(value, int) and value >= 0:
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
        return ordinal

    def normalize(self, *, raw_text: str, metadata: dict[str, Any], ordinal: int) -> NormalizedNodeData:
        headings_raw = metadata.get("headings") or metadata.get("heading_path")
        return NormalizedNodeData(
            text=self.normalize_text(raw_text),
            headings=self.normalize_headings(headings_raw),
            page_no=self.extract_page_no(metadata),
            offset=self.extract_offset(metadata, ordinal),
        )


__all__ = ["NormalizationContract", "NormalizationRules", "NormalizedNodeData"]