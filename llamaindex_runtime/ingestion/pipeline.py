from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from llamaindex_runtime.interfaces import CanonicalSpan
from llamaindex_runtime.okf import e2a_admission
from llamaindex_runtime.okf import serializer
from llamaindex_runtime.okf.rooted_open import BundleAuthority
from llamaindex_runtime.registry import RegistryWriter

from .docling_ingestor import DoclingIngestor
from .models import IngestResult


class IngestionPipeline:
    def __init__(
        self,
        *,
        registry: RegistryWriter,
        ingestor: DoclingIngestor | None = None,
        bundle_root: Path | None = None,
        connection_factory: Callable[[], Any] | None = None,
        reconciler: Any = None,
    ) -> None:
        self._registry = registry
        self._ingestor = ingestor or DoclingIngestor()
        self._bundle_root = bundle_root
        self._connection_factory = connection_factory
        self._reconciler = reconciler

    def ingest(
        self, source_path: str | Path, *, title: str | None = None
    ) -> IngestResult:
        resolved_path = Path(source_path).expanduser().resolve()

        # CRITICAL: Validate source exists FIRST (before any dependency checks)
        if not resolved_path.exists():
            raise FileNotFoundError(f"Source file not found: {resolved_path}")

        # Validate E2a dependencies BEFORE registry registration
        missing: list[str] = []
        if self._bundle_root is None:
            missing.append("bundle_root")
        if self._connection_factory is None:
            missing.append("connection_factory")
        if self._reconciler is None:
            missing.append("reconciler")

        if missing:
            # Raise ValueError with the missing kwarg(s) in the message
            raise ValueError(f"Missing E2a dependencies: {', '.join(missing)}")

        # E2a route is the only route - all dependencies satisfied
        return self._ingest_e2a(resolved_path, title)

    def _ingest_e2a(self, resolved_path: Path, title: str | None) -> IngestResult:
        """Execute E2a route with exact sequence and hash guard."""
        # Note: dependencies already validated in ingest(), but keep as safety check

        # Step 1: register
        registered = self._registry.register_document(
            source_path=resolved_path,
            source_uri=resolved_path.as_uri(),
            title=title,
        )

        # Step 2: get_version
        version_info = self._registry.get_version(registered.version_id)
        if version_info is None:
            raise ValueError("Version not found after registration")

        # Step 3: convert
        conversion = self._ingestor.convert_for_okf(resolved_path)

        # Step 4: hash mismatch guard
        if version_info.content_hash != conversion.source_sha256:
            raise ValueError(
                f"Content hash mismatch: registry={version_info.content_hash}, "
                f"source={conversion.source_sha256}"
            )

        # Step 5: serialize (internally calls publish_raw_pair exactly once)
        serialized = serializer.serialize_document(
            conversion.nodes,
            doc_id=str(registered.doc_id),
            version_id=str(registered.version_id),
            source_checksum=version_info.content_hash,
            docling_version=conversion.docling_version,
            bundle_root=self._bundle_root,
            name=str(registered.version_id),
        )

        # Step 6: admit via BundleAuthority (internally calls read_raw_pair per pair)
        with BundleAuthority(self._bundle_root) as authority:
            materialization_input = e2a_admission.admit_e2a_materialization_input(
                authority
            )

        # Step 7: factory
        connection = self._connection_factory()

        # Validate connection autocommit is exactly False
        autocommit = getattr(connection, "autocommit", None)
        if type(autocommit) is not bool or autocommit is not False:
            raise ValueError("connection autocommit must be exactly False")

        # Step 8: reconcile
        reconciliation_result = self._reconciler.reconcile(
            connection, materialization_input
        )

        # Step 9: reconstruct canonical spans from admitted data
        spans = _reconstruct_spans(
            materialization_input.admitted.canonical_spans,
            registered.doc_id,
            registered.version_id,
            materialization_input.span_records,
        )

        return IngestResult(
            doc_id=registered.doc_id,
            version_id=registered.version_id,
            source_uri=registered.source_uri,
            spans=spans,
            dropped_nodes=serialized.dropped_node_count,
            reconciliation_result=reconciliation_result,
        )

    def _ingest_legacy(self, resolved_path: Path, title: str | None) -> IngestResult:
        """Execute legacy route with existing span persistence."""
        registered = self._registry.register_document(
            source_path=resolved_path,
            source_uri=resolved_path.as_uri(),
            title=title,
        )

        # Check if spans already exist for this version (idempotent ingest)
        existing_spans = self._registry.query_spans_by_version(registered.version_id)
        if existing_spans:
            # Version already has spans; return existing result without re-parsing
            spans = tuple(
                CanonicalSpan(
                    doc_id=registered.doc_id,
                    version_id=registered.version_id,
                    span_id=row["span_id"],
                    text=row["raw_text"],
                    page_no=row["page_no"],
                    headings=(
                        tuple(row["heading_path"].split(" > "))
                        if row.get("heading_path") and row["heading_path"] != "(root)"
                        else ()
                    ),
                    offset=row["start_offset"],
                )
                for row in existing_spans
            )
            return IngestResult(
                doc_id=registered.doc_id,
                version_id=registered.version_id,
                source_uri=registered.source_uri,
                spans=spans,
            )

        result = self._ingestor.ingest(
            resolved_path,
            doc_id=registered.doc_id,
            version_id=registered.version_id,
        )
        self._registry.write_spans(version_id=registered.version_id, spans=result.spans)
        return result


def _reconstruct_spans(
    canonical_spans: tuple[Any, ...],
    doc_id: Any,
    version_id: Any,
    span_records: tuple[dict[str, Any], ...],
) -> tuple[CanonicalSpan, ...]:
    """Reconstruct CanonicalSpan instances from E2a admitted data.

    Preserves the original span order from the sidecar (not sorted by offset).
    """
    from uuid import UUID

    # Build lookup for canonical spans by span_id
    canonical_by_span_id = {span.span_id: span for span in canonical_spans}

    # Reconstruct spans in span_records order (preserves original node order)
    spans: list[CanonicalSpan] = []
    for record in span_records:
        span_id = record["span_id"]

        # Get the canonical span
        canonical = canonical_by_span_id.get(span_id)
        if canonical is None:
            continue

        # Filter to current version only (foreign excluded)
        if canonical.version_id != str(version_id):
            continue

        # Extract heading_path and normalize
        heading_path_str = record.get("heading_path")
        if heading_path_str and heading_path_str != "(root)":
            headings = tuple(heading_path_str.split(" > "))
        else:
            headings = ()

        # Get page_no (can be None)
        page_no = record.get("page_no")

        # Convert span_id to UUID
        span_uuid = UUID(span_id)

        spans.append(
            CanonicalSpan(
                doc_id=doc_id,
                version_id=version_id,
                span_id=span_uuid,
                text=_normalize_whitespace(canonical.text),
                page_no=page_no,
                headings=headings,
                offset=canonical.offset,
            )
        )

    return tuple(spans)


def _normalize_whitespace(text: str) -> str:
    """Collapse multiple whitespaces to single space."""
    return " ".join(text.split())
