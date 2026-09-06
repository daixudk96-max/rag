"""Shared test-only fixtures and direct-chain assertions for serializer tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5


class FakeDoclingNode:
    """Minimal node shape matching DoclingIngestor text and metadata access."""

    def __init__(self, text: str, metadata: dict[str, Any] | None = None) -> None:
        self._text = text
        self.metadata = metadata or {}

    def get_content(self) -> str:
        """Return text through DoclingIngestor's primary extraction path."""
        return self._text

    @property
    def text(self) -> str:
        """Return text through DoclingIngestor's fallback extraction path."""
        return self._text


class FakeDoclingNodeWithTextAttr:
    """Node with only the ``.text`` attribute extraction path."""

    def __init__(self, text: str, metadata: dict[str, Any] | None = None) -> None:
        self._text = text
        self.metadata = metadata or {}

    @property
    def text(self) -> str:
        """Return the node's text."""
        return self._text


def make_docling_metadata_with_nested_prov(
    page_no: int | None = 1,
    offset: int = 0,
    heading_path: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Build the nested ``doc_items/prov`` shape flattened by DoclingIngestor."""
    prov_entry: dict[str, Any] = {"charspan": [offset, offset + 100]}
    if page_no is not None:
        prov_entry["page_no"] = page_no

    return {
        "doc_items": [{"prov": [prov_entry], "label": "text"}],
        "headings": list(heading_path) if heading_path else None,
    }


def make_docling_metadata_flat(
    page_no: int | None = 1,
    offset: int = 0,
    heading_path: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Build top-level metadata; retained pending an intentional test removal."""
    metadata: dict[str, Any] = {"offset": offset}
    if page_no is not None:
        metadata["page_no"] = page_no
    if heading_path:
        metadata["headings"] = list(heading_path)
    return metadata


def make_normalize_spy(normalize_calls: list[dict[str, Any]]):
    """Build an observable normalization spy with the contract's output shape."""
    from llamaindex_runtime.ingestion.normalization import NormalizedNodeData

    def spy_normalize(
        self: object, *, raw_text: str, metadata: dict[str, Any], ordinal: int
    ) -> NormalizedNodeData:
        normalize_calls.append(
            {"raw_text": raw_text, "metadata": metadata, "ordinal": ordinal}
        )
        return NormalizedNodeData(
            text=" ".join(raw_text.split()),
            headings=tuple(metadata.get("headings") or ()),
            page_no=metadata.get("page_no"),
            offset=metadata.get("offset", ordinal),
        )

    return spy_normalize


@dataclass(frozen=True)
class DirectChainExpectation:
    """Expected normalized data and stable span identity from the direct chain."""

    normalized: Any
    span_id: str


def build_direct_chain_expectation(
    *,
    metadata: dict[str, Any],
    raw_text: str,
    doc_id: UUID,
    version_id: UUID,
) -> DirectChainExpectation:
    """Build the expected result using the production direct-chain helpers."""
    from llamaindex_runtime.ingestion.docling_ingestor import DoclingIngestor
    from llamaindex_runtime.ingestion.normalization import NormalizationContract

    flat_metadata = DoclingIngestor._flatten_docling_metadata(dict(metadata))
    normalized = NormalizationContract().normalize(
        raw_text=raw_text, metadata=flat_metadata, ordinal=0
    )
    span_id = uuid5(
        NAMESPACE_URL,
        f"{doc_id}|{version_id}|{normalized.page_no}|"
        f"{'/'.join(normalized.headings)}|{normalized.offset}|{normalized.text}",
    )
    return DirectChainExpectation(normalized=normalized, span_id=str(span_id))


def assert_span_identity_matches_direct_chain(
    span: Any, expected: DirectChainExpectation
) -> None:
    """Assert the generated UUID remains the direct-chain UUID5 identity."""
    assert span.span_id == expected.span_id, (
        f"span_id diverges from direct chain: "
        f"got {span.span_id}, expected {expected.span_id}"
    )
