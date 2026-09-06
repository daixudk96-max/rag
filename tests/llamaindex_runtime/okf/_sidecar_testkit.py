from __future__ import annotations

from typing import TypedDict
from uuid import uuid4

from llamaindex_runtime.okf.sidecar import SpanRecord, SpanSidecar


class _SpanRecordValues(TypedDict):
    span_id: str
    page_no: int
    heading_path: tuple[str, ...]
    offset: int
    text: str


def _sidecar() -> SpanSidecar:
    return SpanSidecar(
        schema_version=1,
        doc_id=str(uuid4()),
        version_id=str(uuid4()),
        spans=(
            SpanRecord(
                span_id=str(uuid4()),
                page_no=3,
                heading_path=("Introduction", "Scope"),
                offset=128,
                text="Normalized first span.",
            ),
            SpanRecord(
                span_id=str(uuid4()),
                page_no=4,
                heading_path=(),
                offset=256,
                text="Normalized second span.",
            ),
        ),
    )


def _valid_span_values() -> _SpanRecordValues:
    return {
        "span_id": str(uuid4()),
        "page_no": 3,
        "heading_path": ("Introduction", "Scope"),
        "offset": 128,
        "text": "Normalized span.",
    }


def _valid_sidecar_values() -> dict[str, object]:
    return {
        "schema_version": 1,
        "doc_id": str(uuid4()),
        "version_id": str(uuid4()),
        "spans": (SpanRecord(**_valid_span_values()),),
    }


def _valid_span_dict() -> dict[str, object]:
    return {
        "span_id": str(uuid4()),
        "page_no": 3,
        "heading_path": ["Introduction", "Scope"],
        "offset": 128,
        "text": "Normalized span.",
    }


def _valid_sidecar_dict() -> dict[str, object]:
    return {
        "schema_version": 1,
        "doc_id": str(uuid4()),
        "version_id": str(uuid4()),
        "spans": [_valid_span_dict()],
    }
