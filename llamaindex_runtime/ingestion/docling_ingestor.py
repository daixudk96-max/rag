from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence
from uuid import NAMESPACE_URL, UUID, uuid5

from llamaindex_runtime.integration import (
    load_docling_node_parser_class,
    load_docling_reader_class,
)
from llamaindex_runtime.interfaces import CanonicalSpan

from .models import IngestResult
from .normalization import NormalizationContract


class DoclingReaderProtocol(Protocol):
    def load_data(self, *, file_path: str) -> Sequence[object]: ...


class DoclingNodeParserProtocol(Protocol):
    def get_nodes_from_documents(
        self, documents: Sequence[object]
    ) -> Sequence[object]: ...


@dataclass(frozen=True)
class DoclingConversionResult:
    """Frozen conversion result for OKF serialization."""

    source_uri: str
    source_sha256: str
    docling_version: str
    nodes: tuple[object, ...]


def _build_default_reader() -> DoclingReaderProtocol:
    """Build the default DoclingReader with heading hierarchy enabled.

    Configures Docling's official HeadingHierarchyModel for PDF processing,
    enabling multi-level heading extraction from PDF bookmarks/outline,
    numbering patterns, and font style inference.

    This is a Phase 14 scope expansion: pin docling==2.109.0 and enable
    HeadingHierarchyOptions in the default production reader.

    Configuration:
        - export_type: 'json' for structured output
        - heading_hierarchy_options.enabled: True
        - heading_hierarchy_options.use_bookmarks: True (PDF outline)
        - heading_hierarchy_options.use_numbering: True (1.1, 1.2, etc.)
        - heading_hierarchy_options.use_style: True (font size/weight)
        - heading_hierarchy_options.max_level: 6
        - heading_hierarchy_options.bookmark_match_threshold: 0.8
        - generate_parsed_pages: True (required for style inference)
    """
    from docling.datamodel.base_models import InputFormat
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.pipeline_options import (
        PdfPipelineOptions,
        HeadingHierarchyOptions,
    )

    # Configure heading hierarchy for multi-level heading extraction
    heading_hierarchy_options = HeadingHierarchyOptions(
        enabled=True,
        use_bookmarks=True,
        use_numbering=True,
        use_style=True,
        max_level=6,
        bookmark_match_threshold=0.8,
    )

    pipeline_options = PdfPipelineOptions(
        heading_hierarchy_options=heading_hierarchy_options,
        generate_parsed_pages=True,  # Required for style-based heading inference
    )

    pdf_format = PdfFormatOption(pipeline_options=pipeline_options)

    # Create DocumentConverter with PDF-specific options
    # Non-PDF formats (DOCX, etc.) use default handling
    doc_converter = DocumentConverter(format_options={InputFormat.PDF: pdf_format})

    reader_class = load_docling_reader_class()
    return reader_class(export_type="json", doc_converter=doc_converter)


def _build_default_node_parser() -> DoclingNodeParserProtocol:
    return load_docling_node_parser_class()()


class DoclingIngestor:
    def __init__(
        self,
        *,
        reader: DoclingReaderProtocol | None = None,
        node_parser: DoclingNodeParserProtocol | None = None,
        normalization_contract: NormalizationContract | None = None,
    ) -> None:
        self._reader = reader or _build_default_reader()
        self._node_parser = node_parser or _build_default_node_parser()
        self._normalization_contract = normalization_contract or NormalizationContract()

    @property
    def normalization_contract(self) -> NormalizationContract:
        return self._normalization_contract

    def convert_for_okf(self, source: Path) -> DoclingConversionResult:
        """Convert source to frozen OKF-serializable result.

        Returns a frozen dataclass with:
        - source_uri: resolved URI of the source file
        - source_sha256: 1 MiB-chunked SHA256 of source bytes
        - docling_version: installed docling version string
        - nodes: tuple of parser output nodes
        """
        resolved_path = Path(source).expanduser().resolve()
        if not resolved_path.exists():
            raise FileNotFoundError(f"Source file not found: {resolved_path}")

        # Hash source bytes BEFORE reader
        source_bytes = resolved_path.read_bytes()
        source_sha256 = _chunked_sha256(source_bytes)

        # Call reader and parser exactly once each
        documents = self._reader.load_data(file_path=str(resolved_path))

        # Hash source bytes AFTER reader to detect mutation
        post_reader_bytes = resolved_path.read_bytes()
        post_reader_sha256 = _chunked_sha256(post_reader_bytes)

        if source_sha256 != post_reader_sha256:
            raise ValueError("Source file mutated during reader.load_data")

        nodes = self._node_parser.get_nodes_from_documents(documents)

        # Get docling version
        docling_version = _detect_docling_version()

        return DoclingConversionResult(
            source_uri=resolved_path.as_uri(),
            source_sha256=source_sha256,
            docling_version=docling_version,
            nodes=tuple(nodes),
        )

    def ingest(
        self, source_path: str | Path, *, doc_id: UUID, version_id: UUID
    ) -> IngestResult:
        resolved_path = Path(source_path).expanduser().resolve()
        if not resolved_path.exists():
            raise FileNotFoundError(f"Source file not found: {resolved_path}")
        documents = self._reader.load_data(file_path=str(resolved_path))
        nodes = self._node_parser.get_nodes_from_documents(documents)
        spans: list[CanonicalSpan] = []
        dropped_nodes = 0
        for ordinal, node in enumerate(nodes):
            raw_text = self._extract_text(node)
            if not raw_text.strip():
                dropped_nodes += 1
                continue
            spans.append(
                self._build_span(
                    node=node, ordinal=ordinal, doc_id=doc_id, version_id=version_id
                )
            )
        return IngestResult(
            doc_id=doc_id,
            version_id=version_id,
            source_uri=resolved_path.as_uri(),
            spans=tuple(spans),
            dropped_nodes=dropped_nodes,
        )

    def _build_span(
        self, *, node: object, ordinal: int, doc_id: UUID, version_id: UUID
    ) -> CanonicalSpan:
        raw_text = self._extract_text(node)
        metadata = dict(getattr(node, "metadata", {}) or {})
        flat_metadata = self._flatten_docling_metadata(metadata)
        normalized = self._normalization_contract.normalize(
            raw_text=raw_text,
            metadata=flat_metadata,
            ordinal=ordinal,
        )
        span_id = uuid5(
            NAMESPACE_URL,
            f"{doc_id}|{version_id}|{normalized.page_no}|{'/'.join(normalized.headings)}|{normalized.offset}|{normalized.text}",
        )
        return CanonicalSpan(
            doc_id=doc_id,
            version_id=version_id,
            span_id=span_id,
            text=normalized.text,
            page_no=normalized.page_no,
            headings=normalized.headings,
            offset=normalized.offset,
        )

    @staticmethod
    def _flatten_docling_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
        """Flatten Docling's nested metadata structure into top-level keys.

        Docling stores provenance in nested structures:
        - page_no inside doc_items[0]['prov'][0]['page_no']
        - charspan (offsets) inside doc_items[0]['prov'][0]['charspan']
        - label inside doc_items[0]['label']
        - heading_path from parent references

        This method extracts those values to top-level keys that
        NormalizationContract can consume, preserving any existing
        top-level keys (they take priority).
        """
        flat: dict[str, Any] = dict(metadata)
        doc_items = metadata.get("doc_items")
        if not isinstance(doc_items, list) or not doc_items:
            return flat

        first_item = doc_items[0]
        if not isinstance(first_item, dict):
            return flat
        # Extract page_no from prov[0]['page_no'] if not already at top level
        if "page_no" not in flat:
            prov_list = first_item.get("prov")
            if isinstance(prov_list, list) and prov_list:
                first_prov = prov_list[0]
                if isinstance(first_prov, dict) and "page_no" in first_prov:
                    flat["page_no"] = first_prov["page_no"]

        # Extract charspan as start_offset from prov[0]['charspan'][0] if not already at top level
        if (
            "offset" not in flat
            and "start_offset" not in flat
            and "doc_offset" not in flat
        ):
            prov_list = first_item.get("prov")
            if isinstance(prov_list, list) and prov_list:
                first_prov = prov_list[0]
                if isinstance(first_prov, dict):
                    charspan = first_prov.get("charspan")
                    if isinstance(charspan, (list, tuple)) and len(charspan) >= 1:
                        flat["start_offset"] = charspan[0]

        # Extract label as heading context if not already at top level
        if "label" not in flat:
            label = first_item.get("label")
            if isinstance(label, str):
                flat["label"] = label

        return flat

    @staticmethod
    def _extract_text(node: object) -> str:
        getter = getattr(node, "get_content", None)
        if callable(getter):
            content = getter()
            return content if isinstance(content, str) else str(content)
        text = getattr(node, "text", "")
        return text if isinstance(text, str) else str(text)


def _chunked_sha256(data: bytes, chunk_size: int = 1024 * 1024) -> str:
    """Compute SHA256 hash with 1 MiB chunked reading."""
    hasher = hashlib.sha256()
    for offset in range(0, len(data), chunk_size):
        hasher.update(data[offset : offset + chunk_size])
    return hasher.hexdigest()


def _detect_docling_version() -> str:
    """Detect installed docling version."""
    try:
        import docling
    except ModuleNotFoundError:
        return "unknown"
    return str(getattr(docling, "__version__", "unknown"))


__all__ = ["DoclingConversionResult", "DoclingIngestor"]
