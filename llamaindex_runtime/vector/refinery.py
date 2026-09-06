"""Overlap refinery for adding context continuity between adjacent chunks.

This module provides a minimal overlap capability on top of existing chunkers
(SimpleSpanChunker, HeadingGroupedChunker) to improve retrieval quality by
ensuring context continuity between adjacent chunks.

Key principles:
- Preserves canonical spans as the source backbone
- Does NOT create new chunks, only refines existing ones
- Extends span_ids to include overlapping sources (provenance preserved)
- Configurable overlap via token count
- Works with any chunker output
"""
from __future__ import annotations

import uuid
from typing import Any


class OverlapRefinery:
    """Refine chunks by adding overlap between adjacent chunks.

    This refinery adds text from neighboring chunks to create overlap windows,
    improving retrieval quality by ensuring context continuity.

    Parameters
    ----------
    overlap_tokens : int
        Number of tokens to overlap from adjacent chunks (default: 50)

    Notes
    -----
    - Single chunk returns unchanged (no adjacent chunks to overlap)
    - Empty chunk list returns empty
    - Provenance is preserved by extending span_ids
    - Original chunk_ids are preserved (no new chunks created)
    """

    def __init__(self, overlap_tokens: int = 50) -> None:
        """Initialize refinery with overlap token count."""
        if overlap_tokens < 0:
            raise ValueError("overlap_tokens must be >= 0")
        self._overlap_tokens = overlap_tokens

    def refine(
        self,
        chunks: list[dict[str, Any]],
        *,
        version_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        """Refine chunks by adding overlap between adjacent chunks.

        Parameters
        ----------
        chunks : list of dict
            Each dict must have keys: chunk_id, text_preview, span_ids,
            chunk_order, chunk_type, token_count, and optionally
            page_no, heading_path.
        version_id : UUID
            The document version these chunks belong to.

        Returns
        -------
        list of dict
            Refined chunks with overlap added. Each chunk has updated
            text_preview, token_count, and span_ids.

        Notes
        -----
        - Adjacent chunks have overlap text appended/prepended
        - span_ids are extended to include overlapping source chunks
        - Original chunk_ids are preserved (no new chunks created)
        - Zero overlap returns chunks unchanged
        """
        if not chunks:
            return []

        if len(chunks) == 1:
            # Single chunk: no adjacent chunks to overlap
            return chunks

        if self._overlap_tokens == 0:
            # Zero overlap: return unchanged
            return chunks

        # Refine each chunk by adding overlap from neighbors
        refined_chunks: list[dict[str, Any]] = []
        for i, chunk in enumerate(chunks):
            refined_text = chunk["text_preview"]
            refined_span_ids = list(chunk["span_ids"])  # Copy original span_ids

            # Add overlap from previous chunk (if exists)
            if i > 0:
                prev_chunk = chunks[i - 1]
                prev_text = prev_chunk["text_preview"]
                prev_tokens = prev_text.split()

                # Take last N tokens from previous chunk
                overlap_tokens_count = min(self._overlap_tokens, len(prev_tokens))
                if overlap_tokens_count > 0:
                    overlap_text = " ".join(prev_tokens[-overlap_tokens_count:])
                    refined_text = overlap_text + " " + refined_text

                    # Extend span_ids to include previous chunk's spans
                    refined_span_ids.extend(prev_chunk["span_ids"])

            # Add overlap from next chunk (if exists)
            if i < len(chunks) - 1:
                next_chunk = chunks[i + 1]
                next_text = next_chunk["text_preview"]
                next_tokens = next_text.split()

                # Take first N tokens from next chunk
                overlap_tokens_count = min(self._overlap_tokens, len(next_tokens))
                if overlap_tokens_count > 0:
                    overlap_text = " ".join(next_tokens[:overlap_tokens_count])
                    refined_text = refined_text + " " + overlap_text

                    # Extend span_ids to include next chunk's spans
                    refined_span_ids.extend(next_chunk["span_ids"])

            # Create refined chunk preserving metadata
            refined_chunk = {
                "chunk_id": chunk["chunk_id"],  # Preserve original chunk_id
                "chunk_type": chunk["chunk_type"],
                "chunk_order": chunk["chunk_order"],
                "token_count": len(refined_text.split()) if refined_text.strip() else 0,
                "text_preview": refined_text,
                "page_no": chunk.get("page_no"),
                "heading_path": chunk.get("heading_path"),
                "span_ids": refined_span_ids,
            }
            refined_chunks.append(refined_chunk)

        return refined_chunks