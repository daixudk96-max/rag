"""Derive vector chunks from canonical spans.

Provides multiple chunking strategies:
- SimpleSpanChunker: 1:1 span-to-chunk mapping (baseline)
- HeadingGroupedChunker: Groups spans under the same heading_path

All chunkers preserve canonical spans as the source backbone and maintain
provenance via span_ids.

Chunk IDs are deterministic (uuid5) so that the same version + span/heading
always yields the same chunk_id, enabling idempotent writes.
"""
from __future__ import annotations

import uuid
from typing import Any


def _require_span_field(span: dict[str, Any], field: str) -> Any:
    if field not in span:
        raise ValueError(f"span missing required field: {field}")
    return span[field]


class SimpleSpanChunker:
    def generate(
        self,
        spans: list[dict[str, Any]],
        *,
        version_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        """Generate one vector chunk per canonical span.

        Parameters
        ----------
        spans : list of dict
            Each dict must have keys: span_id, and optionally
            raw_text, page_no, heading_path.
        version_id : UUID
            The document version these spans belong to.

        Returns
        -------
        list of dict
            Each dict has keys: chunk_id, chunk_type, chunk_order,
            token_count, text_preview, page_no, heading_path, span_ids.
        """
        if not spans:
            return []

        chunks: list[dict[str, Any]] = []
        for order, span in enumerate(spans):
            span_id = _require_span_field(span, "span_id")
            text = span.get("raw_text") or ""
            chunks.append(
                {
                    "chunk_id": uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"{version_id}:{span_id}",
                    ),
                    "chunk_type": "semantic_leaf",
                    "chunk_order": order,
                    "token_count": len(text.split()) if text.strip() else 0,
                    "text_preview": text,
                    "page_no": span.get("page_no"),
                    "heading_path": span.get("heading_path"),
                    "span_ids": [span_id],
                }
            )
        return chunks


class HeadingGroupedChunker:
    """Group spans under the same heading_path into semantic chunks.

    This chunker creates one chunk per heading_path, concatenating all spans
    that share that heading. Spans with NULL heading_path are treated as
    individual chunks (fallback to 1:1 behavior).

    Preserves provenance by maintaining span_ids for each grouped chunk.
    """

    def generate(
        self,
        spans: list[dict[str, Any]],
        *,
        version_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        """Generate chunks grouped by heading_path.

        Parameters
        ----------
        spans : list of dict
            Each dict must have keys: span_id, start_offset, and optionally
            raw_text, page_no, heading_path.
        version_id : UUID
            The document version these spans belong to.

        Returns
        -------
        list of dict
            Each dict has keys: chunk_id, chunk_type, chunk_order,
            token_count, text_preview, page_no, heading_path, span_ids.

        Notes
        -----
        - Spans are sorted by start_offset to ensure correct grouping order
        - NULL heading_path spans become individual chunks
        - chunk_id is deterministic based on version_id + heading_path
        - chunk_order follows the order of first span in each group
        """
        if not spans:
            return []

        # Validate required fields before any grouping
        for span in spans:
            _require_span_field(span, "span_id")
            _require_span_field(span, "start_offset")

        # Sort spans by offset to preserve document order
        sorted_spans = sorted(spans, key=lambda s: s.get("start_offset", 0))

        # Group spans by heading_path, tracking first occurrence order
        # Use a dict that preserves insertion order (Python 3.7+ dict is ordered)
        heading_groups: dict[str | None, list[dict[str, Any]]] = {}
        for span in sorted_spans:
            heading_path = span.get("heading_path")
            if heading_path not in heading_groups:
                heading_groups[heading_path] = []
            heading_groups[heading_path].append(span)

        # Generate chunks in document order (order of first span in each group)
        chunks: list[dict[str, Any]] = []
        chunk_order = 0

        for heading_path, group_spans in heading_groups.items():
            # Handle NULL heading: each span becomes its own chunk
            if heading_path is None:
                for span in group_spans:
                    span_id = _require_span_field(span, "span_id")
                    text = span.get("raw_text") or ""
                    chunk_id = uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"{version_id}:orphan:{span_id}",
                    )
                    chunks.append(
                        {
                            "chunk_id": chunk_id,
                            "chunk_type": "semantic_leaf",
                            "chunk_order": chunk_order,
                            "token_count": len(text.split()) if text.strip() else 0,
                            "text_preview": text,
                            "page_no": span.get("page_no"),
                            "heading_path": None,
                            "span_ids": [span_id],
                        }
                    )
                    chunk_order += 1
            else:
                # Non-NULL heading: group all spans into one chunk
                texts = [span.get("raw_text") or "" for span in group_spans]
                combined_text = " ".join(texts)
                token_count = len(combined_text.split()) if combined_text.strip() else 0
                first_span = group_spans[0]

                chunk_id = uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"{version_id}:heading:{heading_path}",
                )
                chunks.append(
                    {
                        "chunk_id": chunk_id,
                        "chunk_type": "semantic_group",
                        "chunk_order": chunk_order,
                        "token_count": token_count,
                        "text_preview": combined_text,
                        "page_no": first_span.get("page_no"),
                        "heading_path": heading_path,
                        "span_ids": [span["span_id"] for span in group_spans],
                    }
                )
                chunk_order += 1

        return chunks
