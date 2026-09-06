from __future__ import annotations

import hashlib
from dataclasses import dataclass

import pytest

from llamaindex_runtime.okf.canonical_hash import canonical_hash, canonical_serialize
from llamaindex_runtime.okf.sidecar import SpanRecord, SpanSidecar

FRONTMATTER = {
    "type": "raw",
    "doc_id": "b2191a11-cd8b-4c6e-b34a-7b5552e3c03c",
    "version_id": "306dfedb-d8cf-4828-9e91-1d1855aa8b55",
    "source_checksum": "a" * 64,
    "docling_version": "2.45.0",
    "generated_by": "docling-to-okf/1.0",
}


def _sidecar(*, text: str = "Normalized span.", offset: int = 128) -> SpanSidecar:
    return SpanSidecar(
        schema_version=1,
        doc_id=FRONTMATTER["doc_id"],
        version_id=FRONTMATTER["version_id"],
        spans=(
            SpanRecord(
                span_id="b6a836c6-66f0-5ffa-9b5f-8a0ec29b3c9a",
                page_no=3,
                heading_path=("Introduction", "Scope"),
                offset=offset,
                text=text,
            ),
        ),
    )


def test_canonical_hash_ignores_frontmatter_order_and_markdown_formatting() -> None:
    reordered_frontmatter = {
        "generated_by": "docling-to-okf/1.0",
        "docling_version": "2.45.0",
        "source_checksum": "a" * 64,
        "version_id": "306dfedb-d8cf-4828-9e91-1d1855aa8b55",
        "doc_id": "b2191a11-cd8b-4c6e-b34a-7b5552e3c03c",
        "type": "raw",
    }

    assert canonical_hash(FRONTMATTER, _sidecar()) == canonical_hash(
        reordered_frontmatter,
        _sidecar(),
    )


def test_canonical_hash_changes_for_span_text_change() -> None:
    assert canonical_hash(FRONTMATTER, _sidecar()) != canonical_hash(
        FRONTMATTER,
        _sidecar(text="Normalized span changed."),
    )


def test_canonical_hash_changes_for_span_offset_change() -> None:
    assert canonical_hash(FRONTMATTER, _sidecar()) != canonical_hash(
        FRONTMATTER,
        _sidecar(offset=129),
    )


def test_canonical_hash_changes_for_span_page_number_change() -> None:
    original = _sidecar()
    changed = SpanSidecar(
        schema_version=original.schema_version,
        doc_id=original.doc_id,
        version_id=original.version_id,
        spans=(
            SpanRecord(
                span_id=original.spans[0].span_id,
                page_no=4,
                heading_path=original.spans[0].heading_path,
                offset=original.spans[0].offset,
                text=original.spans[0].text,
            ),
        ),
    )

    assert canonical_hash(FRONTMATTER, original) != canonical_hash(FRONTMATTER, changed)


def test_canonical_hash_changes_for_span_heading_path_change() -> None:
    original = _sidecar()
    changed = SpanSidecar(
        schema_version=original.schema_version,
        doc_id=original.doc_id,
        version_id=original.version_id,
        spans=(
            SpanRecord(
                span_id=original.spans[0].span_id,
                page_no=original.spans[0].page_no,
                heading_path=("Changed",),
                offset=original.spans[0].offset,
                text=original.spans[0].text,
            ),
        ),
    )

    assert canonical_hash(FRONTMATTER, original) != canonical_hash(FRONTMATTER, changed)


def test_canonical_hash_changes_for_frontmatter_value_change() -> None:
    changed_frontmatter = {**FRONTMATTER, "generated_by": "docling-to-okf/2.0"}

    assert canonical_hash(FRONTMATTER, _sidecar()) != canonical_hash(
        changed_frontmatter,
        _sidecar(),
    )


def test_canonical_hash_uses_locked_concatenated_payload_formula() -> None:
    sidecar = _sidecar()
    expected = hashlib.sha256(
        canonical_serialize(FRONTMATTER)
        + canonical_serialize([span.to_dict() for span in sidecar.spans])
    ).hexdigest()

    assert canonical_hash(FRONTMATTER, sidecar) == expected


def test_canonical_hash_is_lowercase_sha256_and_deterministic() -> None:
    first = canonical_hash(FRONTMATTER, _sidecar())
    second = canonical_hash(FRONTMATTER, _sidecar())

    assert first == second
    assert len(first) == 64
    assert first == first.lower()
    assert int(first, 16) >= 0


def test_canonical_serialize_uses_sorted_stable_json() -> None:
    assert canonical_serialize({"z": ["中", 2], "a": {"b": True}}) == (
        '{"a":{"b":true},"z":["中",2]}'.encode("utf-8")
    )


# --- Wave 1 Remediation: dataclass class guard (Fix B) ---


@dataclass(frozen=True)
class _SampleDataclass:
    """A sample dataclass for canonical_hash testing."""

    value: int


def test_canonical_serialize_dataclass_instance_is_outside_frozen_v1_domain() -> None:
    """Arbitrary objects are rejected rather than acquiring a new v1 encoding."""
    instance = _SampleDataclass(value=42)

    with pytest.raises(ValueError, match="^frontmatter_canonical_unsupported$"):
        canonical_serialize(instance)


def test_canonical_serialize_dataclass_class_is_outside_frozen_v1_domain() -> None:
    """Dataclass classes cannot be accepted as arbitrary canonical objects."""
    with pytest.raises(ValueError, match="^frontmatter_canonical_unsupported$"):
        canonical_serialize(_SampleDataclass)
