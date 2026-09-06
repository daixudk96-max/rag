"""Docling→OKF serializer producing raw/*.md + sidecar.

CRITICAL CONSTRAINT: This module MUST import and use NormalizationContract
from the ingestion module, and MUST call DoclingIngestor._flatten_docling_metadata
directly. Any reimplementation, however faithful-looking, eventually diverges
and permanently breaks S_direct == S_okf round-trip.
Do NOT copy normalization/flattening logic from ingestion code.

The serializer accepts a node-shaped docling output sequence (objects with
get_content()/text and metadata, or Mapping dicts) and produces:
- raw/<slug>.md with RawFrontmatterContract frontmatter
- <slug>.spans.json with SpanSidecar schema v1
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import NAMESPACE_URL, UUID, uuid5

from llamaindex_runtime.ingestion.docling_ingestor import DoclingIngestor
from llamaindex_runtime.ingestion.normalization import NormalizationContract

from .canonical_hash import canonical_hash
from ._naming import is_okf_slug
from .contracts import RawFrontmatterContract, dump_raw_frontmatter
from .generation_manifest import GenerationManifest
from .raw_pair import publish_raw_pair
from .roundtrip import validate_span_identity_admission
from .sidecar import SpanRecord, SpanSidecar

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SerializedRawFile:
    """Immutable result of serialize_document."""

    md_path: Path
    sidecar_path: Path
    doc_id: str
    version_id: str
    canonical_hash: str
    span_count: int
    dropped_node_count: int


@dataclass(frozen=True)
class _SpanPreparation:
    spans: tuple[SpanRecord, ...]
    first_heading: str | None
    dropped_node_count: int


@dataclass(frozen=True)
class _RawPairPaths:
    md_path: Path
    sidecar_path: Path
    manifest_path: Path


@dataclass(frozen=True)
class _SerializedContent:
    markdown_bytes: bytes
    sidecar_bytes: bytes
    canonical_hash: str


@dataclass(frozen=True)
class _RawPairPayload:
    bundle_root: Path
    slug: str
    md_path: Path
    sidecar_path: Path
    manifest_path: Path
    markdown_bytes: bytes
    sidecar_bytes: bytes
    manifest_bytes: bytes
    canonical_hash: str


def serialize_document(
    docling_output: Sequence[object],
    *,
    doc_id: str,
    version_id: str,
    source_checksum: str,
    docling_version: str,
    bundle_root: Path,
    name: str,
) -> SerializedRawFile:
    """Serialize docling output to OKF raw/*.md + sidecar."""
    _validate_inputs(docling_output, doc_id, version_id, name)
    preparation = _prepare_spans(docling_output, doc_id, version_id)
    payload = _build_raw_pair_payload(
        preparation,
        doc_id,
        version_id,
        source_checksum,
        docling_version,
        bundle_root,
        name,
    )
    _publish_payload(payload)
    return _build_result(payload, doc_id, version_id, preparation)


def _validate_inputs(
    docling_output: Sequence[object], doc_id: str, version_id: str, name: str
) -> None:
    try:
        UUID(doc_id)
    except ValueError:
        raise ValueError("doc_id must be a UUID") from None
    try:
        UUID(version_id)
    except ValueError:
        raise ValueError("version_id must be a UUID") from None
    if not is_okf_slug(name):
        raise ValueError("invalid slug")
    if not docling_output:
        raise ValueError("Empty or invalid node sequence")


def _prepare_spans(
    docling_output: Sequence[object], doc_id: str, version_id: str
) -> _SpanPreparation:
    contract = NormalizationContract()
    spans: list[SpanRecord] = []
    first_heading: str | None = None
    dropped_node_count = 0
    for ordinal, node in enumerate(docling_output):
        raw_text = _extract_text(node)
        if not raw_text.strip():
            dropped_node_count += 1
            continue
        span = _build_span(node, raw_text, ordinal, doc_id, version_id, contract)
        spans.append(span)
        if first_heading is None and span.heading_path:
            first_heading = span.heading_path[0]
    if not spans:
        raise ValueError("Empty or invalid node sequence: no valid spans")
    validate_span_identity_admission(spans, doc_id=doc_id, version_id=version_id)
    return _SpanPreparation(tuple(spans), first_heading, dropped_node_count)


def _build_span(
    node: object,
    raw_text: str,
    ordinal: int,
    doc_id: str,
    version_id: str,
    contract: NormalizationContract,
) -> SpanRecord:
    metadata = _extract_metadata(node)
    flat_metadata = DoclingIngestor._flatten_docling_metadata(metadata)
    normalized = contract.normalize(
        raw_text=raw_text, metadata=flat_metadata, ordinal=ordinal
    )
    span_id = uuid5(
        NAMESPACE_URL,
        f"{doc_id}|{version_id}|{normalized.page_no}|"
        f"{'/'.join(normalized.headings)}|{normalized.offset}|{normalized.text}",
    )
    return SpanRecord(
        span_id=str(span_id),
        page_no=normalized.page_no,
        heading_path=normalized.headings,
        offset=normalized.offset,
        text=normalized.text,
    )


def _build_raw_pair_payload(
    preparation: _SpanPreparation,
    doc_id: str,
    version_id: str,
    source_checksum: str,
    docling_version: str,
    bundle_root: Path,
    name: str,
) -> _RawPairPayload:
    frontmatter = _build_frontmatter(
        preparation.first_heading,
        doc_id,
        version_id,
        source_checksum,
        docling_version,
        name,
    )
    body = _build_body(list(preparation.spans))
    paths = _build_raw_pair_paths(bundle_root, name)
    content = _serialize_content(
        frontmatter, body, doc_id, version_id, preparation.spans
    )
    manifest_bytes = _build_manifest_bytes(paths, content)
    return _RawPairPayload(
        bundle_root=bundle_root,
        slug=name,
        md_path=paths.md_path,
        sidecar_path=paths.sidecar_path,
        manifest_path=paths.manifest_path,
        markdown_bytes=content.markdown_bytes,
        sidecar_bytes=content.sidecar_bytes,
        manifest_bytes=manifest_bytes,
        canonical_hash=content.canonical_hash,
    )


def _build_raw_pair_paths(bundle_root: Path, name: str) -> _RawPairPaths:
    """Derive reporting paths only; the publisher owns all write authority."""
    raw_dir = bundle_root / "raw"
    return _RawPairPaths(
        md_path=raw_dir / f"{name}.md",
        sidecar_path=raw_dir / f"{name}.spans.json",
        manifest_path=raw_dir / f"{name}.pair.json",
    )


def _serialize_content(
    frontmatter: dict[str, Any],
    body: str,
    doc_id: str,
    version_id: str,
    spans: tuple[SpanRecord, ...],
) -> _SerializedContent:
    markdown_bytes = dump_raw_frontmatter(frontmatter, body).encode("utf-8")
    sidecar = SpanSidecar(1, doc_id, version_id, spans)
    sidecar_bytes = sidecar.to_bytes()
    return _SerializedContent(
        markdown_bytes=markdown_bytes,
        sidecar_bytes=sidecar_bytes,
        canonical_hash=canonical_hash(frontmatter, sidecar),
    )


def _build_manifest_bytes(paths: _RawPairPaths, content: _SerializedContent) -> bytes:
    return GenerationManifest.create(
        markdown_file=paths.md_path.name,
        markdown_bytes=content.markdown_bytes,
        sidecar_file=paths.sidecar_path.name,
        sidecar_bytes=content.sidecar_bytes,
        canonical_hash=content.canonical_hash,
    ).to_bytes()


def _build_frontmatter(
    first_heading: str | None,
    doc_id: str,
    version_id: str,
    source_checksum: str,
    docling_version: str,
    name: str,
) -> dict[str, Any]:
    frontmatter: dict[str, Any] = {
        "type": "raw",
        "doc_id": doc_id,
        "version_id": version_id,
        "source_checksum": source_checksum,
        "docling_version": docling_version,
        "generated_by": "docling-to-okf/1.0",
        "title": first_heading or name.replace("-", " ").title(),
    }
    RawFrontmatterContract.validate(frontmatter)
    return frontmatter


def _publish_payload(payload: _RawPairPayload) -> None:
    publish_raw_pair(
        payload.bundle_root,
        payload.slug,
        payload.markdown_bytes,
        payload.sidecar_bytes,
        payload.manifest_bytes,
    )


def _build_result(
    payload: _RawPairPayload,
    doc_id: str,
    version_id: str,
    preparation: _SpanPreparation,
) -> SerializedRawFile:
    logger.info(
        "OKF serialization complete: span_count=%d dropped_node_count=%d",
        len(preparation.spans),
        preparation.dropped_node_count,
    )
    return SerializedRawFile(
        md_path=payload.md_path,
        sidecar_path=payload.sidecar_path,
        doc_id=doc_id,
        version_id=version_id,
        canonical_hash=payload.canonical_hash,
        span_count=len(preparation.spans),
        dropped_node_count=preparation.dropped_node_count,
    )


def _extract_text(node: object) -> str:
    """Extract text from a docling node (object or Mapping)."""
    # Mapping/dict path
    if isinstance(node, Mapping):
        text = node.get("text")
        return text if isinstance(text, str) else ""

    # Object path: use get_content() first, then .text attribute
    # (mirrors DoclingIngestor._extract_text exactly)
    getter = getattr(node, "get_content", None)
    if callable(getter):
        content = getter()
        return content if isinstance(content, str) else str(content)
    text = getattr(node, "text", "")
    return text if isinstance(text, str) else str(text)


def _extract_metadata(node: object) -> dict[str, Any]:
    """Extract metadata from a docling node (object or Mapping)."""
    if isinstance(node, Mapping):
        metadata = node.get("metadata")
        if metadata is None:
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = dict(metadata) if hasattr(metadata, "items") else {}
        return dict(metadata)

    # Object path: mirror DoclingIngestor._build_span
    metadata = dict(getattr(node, "metadata", {}) or {})
    return metadata


def _build_body(spans: list[SpanRecord]) -> str:
    """Build human-readable markdown body from spans."""
    paragraphs: list[str] = []
    current_heading: tuple[str, ...] = ()

    for span in spans:
        if span.heading_path != current_heading:
            current_heading = span.heading_path
            for i, heading in enumerate(current_heading):
                level = i + 1
                heading_marker = "#" * level
                paragraphs.append(f"{heading_marker} {heading}")

        paragraphs.append(span.text)

    return "\n\n".join(paragraphs)


__all__ = [
    "SerializedRawFile",
    "serialize_document",
]
