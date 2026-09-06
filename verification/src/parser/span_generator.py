from __future__ import annotations

import uuid
from typing import Any

from .normalization import clean_text


class SpanGenerator:
    def generate_spans(self, parsed_output: dict[str, Any]) -> list[dict[str, Any]]:
        spans: list[dict[str, Any]] = []
        for item in parsed_output.get("items", []):
            raw_text = clean_text(item["text"])
            span_id = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"{item.get('page_no')}|{item.get('heading_path')}|{item.get('start_offset')}|{item.get('end_offset')}|{raw_text}",
            )
            spans.append(
                {
                    "span_id": span_id,
                    "span_kind": "paragraph",
                    "start_offset": item["start_offset"],
                    "end_offset": item["end_offset"],
                    "page_no": item.get("page_no"),
                    "heading_path": item.get("heading_path"),
                    "raw_text": raw_text,
                }
            )
        return spans
