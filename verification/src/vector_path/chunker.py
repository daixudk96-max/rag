from __future__ import annotations

import uuid
from typing import Any


class SimpleSpanChunker:
    def generate(self, spans: list[dict[str, Any]], *, version_id: uuid.UUID) -> list[dict[str, Any]]:
        chunks: list[dict[str, Any]] = []
        for order, span in enumerate(spans):
            chunks.append(
                {
                    "chunk_id": uuid.uuid5(uuid.NAMESPACE_URL, f"{version_id}:{span['span_id']}"),
                    "chunk_type": "semantic_leaf",
                    "chunk_order": order,
                    "token_count": len((span.get('raw_text') or '').split()),
                    "text_preview": span.get("raw_text"),
                    "page_no": span.get("page_no"),
                    "heading_path": span.get("heading_path"),
                    "span_ids": [span["span_id"]],
                }
            )
        return chunks
