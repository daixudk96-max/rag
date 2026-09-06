"""Shared evidence content hydration for selected tree nodes."""
from __future__ import annotations

import logging
from typing import Any, Protocol, Sequence
from uuid import UUID

logger = logging.getLogger(__name__)


class EvidenceRegistry(Protocol):
    """Registry read contract required for evidence content hydration."""

    def query_spans_by_version(self, version_id: UUID) -> list[dict[str, Any]]: ...

    def query_vector_chunks_by_version(self, version_id: UUID) -> list[dict[str, Any]]: ...

    def query_vector_chunk_spans_by_version(self, version_id: UUID) -> list[dict[str, Any]]: ...


class EvidenceContentResolver:
    """Resolve selected-node preview text from spans, chunks, then fallback text."""

    def build_text_preview(
        self,
        *,
        registry: EvidenceRegistry,
        version_id: UUID,
        node_id: UUID,
        span_ids: Sequence[UUID],
        fallback_text: str,
        chunk_id: UUID | None = None,
    ) -> str:
        """Build preview text without affecting retrieval ranking or selection."""
        span_text = self._text_preview_from_spans(registry, version_id, span_ids)
        if span_text:
            return span_text

        chunk_text = self._text_preview_from_chunks(
            registry,
            version_id,
            node_id,
            span_ids,
            chunk_id,
        )
        if chunk_text:
            return chunk_text

        return self._normalize_preview_text(fallback_text)

    def _text_preview_from_spans(
        self,
        registry: EvidenceRegistry,
        version_id: UUID,
        span_ids: Sequence[UUID],
    ) -> str:
        if not span_ids:
            return ""

        try:
            spans = registry.query_spans_by_version(version_id)
        except Exception as exc:
            logger.debug(
                "Span preview query failed for version_id=%s: %s",
                version_id,
                exc,
            )
            return ""

        span_order = {span_id: index for index, span_id in enumerate(span_ids)}
        selected: list[tuple[int, str]] = []
        for span in spans:
            span_id = self._coerce_uuid(span.get("span_id"))
            if span_id in span_order:
                selected.append((span_order[span_id], span.get("raw_text") or ""))

        selected.sort(key=lambda item: item[0])
        return self._normalize_preview_text(" ".join(text for _, text in selected))

    def _text_preview_from_chunks(
        self,
        registry: EvidenceRegistry,
        version_id: UUID,
        node_id: UUID,
        span_ids: Sequence[UUID],
        chunk_id: UUID | None,
    ) -> str:
        try:
            chunks = registry.query_vector_chunks_by_version(version_id)
        except Exception as exc:
            logger.debug(
                "Chunk preview query failed for version_id=%s: %s",
                version_id,
                exc,
            )
            chunks = []

        if not chunks:
            return ""

        chunk_ids = self._chunk_ids_for_span_ids(registry, version_id, span_ids)
        if chunk_id is not None:
            chunk_ids.add(chunk_id)

        selected: list[str] = []
        for chunk in chunks:
            row_chunk_id = self._coerce_uuid(chunk.get("chunk_id"))
            row_node_id = self._coerce_uuid(chunk.get("node_id"))
            if row_chunk_id in chunk_ids or row_node_id == node_id:
                selected.append(chunk.get("text_preview") or "")

        return self._normalize_preview_text(" ".join(selected))

    def _chunk_ids_for_span_ids(
        self,
        registry: EvidenceRegistry,
        version_id: UUID,
        span_ids: Sequence[UUID],
    ) -> set[UUID]:
        if not span_ids:
            return set()

        try:
            vector_chunk_spans = registry.query_vector_chunk_spans_by_version(version_id)
        except Exception as exc:
            logger.debug(
                "Chunk-span preview query failed for version_id=%s: %s",
                version_id,
                exc,
            )
            return set()

        span_id_set = set(span_ids)
        chunk_ids: set[UUID] = set()
        for row in vector_chunk_spans:
            span_id = self._coerce_uuid(row.get("span_id"))
            chunk_id = self._coerce_uuid(row.get("chunk_id"))
            if span_id in span_id_set and chunk_id is not None:
                chunk_ids.add(chunk_id)
        return chunk_ids

    def _coerce_uuid(self, value: Any) -> UUID | None:
        if value is None:
            return None
        if isinstance(value, UUID):
            return value
        try:
            return UUID(str(value))
        except (AttributeError, TypeError, ValueError):
            return None

    def _normalize_preview_text(self, text: str, max_length: int = 1600) -> str:
        normalized = " ".join(text.split())
        if len(normalized) <= max_length:
            return normalized
        return normalized[: max_length - 1].rstrip() + "…"
