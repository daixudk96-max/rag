"""Private builders shared by parser-completion test modules."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from llamaindex_runtime.okf.roundtrip import recompute_span_id
from llamaindex_runtime.okf.sidecar import SpanRecord, SpanSidecar


def _make_raw_md_content(
    frontmatter: dict[str, Any],
    body: str = "First paragraph.\n\nSecond paragraph.",
) -> str:
    """Create raw markdown content with frontmatter."""
    fm_lines = ["---"]
    for key, value in frontmatter.items():
        if isinstance(value, str):
            fm_lines.append(f"{key}: {value}")
        elif isinstance(value, list):
            fm_lines.append(f"{key}:")
            for item in value:
                fm_lines.append(f"  - {item}")
        elif isinstance(value, dict):
            # Nested dict for relations
            fm_lines.append(f"{key}:")
            for r in value:
                fm_lines.append("  - target: " + r.get("target", ""))
                for k, v in r.items():
                    if k != "target":
                        fm_lines.append(f"    {k}: {v}")
        else:
            fm_lines.append(f"{key}: {value}")
    fm_lines.append("---")
    fm_lines.append("")
    fm_lines.append(body)
    return "\n".join(fm_lines)


def _make_sidecar(
    doc_id: str,
    version_id: str,
    spans: list[dict[str, Any]] | None = None,
) -> SpanSidecar:
    """Create a valid sidecar for testing."""
    if spans is None:
        spans = [
            {
                "span_id": str(uuid4()),
                "page_no": 1,
                "heading_path": [],
                "offset": 0,
                "text": "First paragraph.",
            }
        ]
    records = tuple(SpanRecord.from_dict(span) for span in spans)
    canonical_records = tuple(
        SpanRecord(
            span_id=recompute_span_id(record, doc_id=doc_id, version_id=version_id),
            page_no=record.page_no,
            heading_path=record.heading_path,
            offset=record.offset,
            text=record.text,
        )
        for record in records
    )
    return SpanSidecar(
        schema_version=1,
        doc_id=doc_id,
        version_id=version_id,
        spans=canonical_records,
    )
