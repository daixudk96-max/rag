"""Offline span-identity round-trip gate for frozen Docling fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from llamaindex_runtime.okf.contracts import dump_raw_frontmatter, load_raw_frontmatter
from llamaindex_runtime.okf.diagnostics import diagnostic_safe_uuid
from llamaindex_runtime.okf.parser import OKFParser
from llamaindex_runtime.okf.roundtrip import (
    diagnostic_safe_path,
    diagnostic_safe_text,
    first_roundtrip_mismatch,
    persisted_span_id_mismatch,
    recompute_span_dicts,
    roundtrip_mismatch,
)
from llamaindex_runtime.okf.serializer import SerializedRawFile, serialize_document
from llamaindex_runtime.okf.sidecar import SpanRecord

from .raw_pair_testkit import refresh_raw_manifest

FIXTURE_ROOT = Path(__file__).parents[2] / "fixtures" / "okf_roundtrip"
FIXTURE_SLUGS = ("sectioned-pdf", "complex-layout-pdf", "docx")
SPEC_BUNDLE_ROOT = Path(__file__).parents[2] / "fixtures" / "okf_spec_bundles"
SPEC_BUNDLE_STATS = {
    "crypto_bitcoin": (5, 3, 0),
    "ga4": (11, 6, 0),
    "stackoverflow": (49, 4, 0),
}
SPEC_BUNDLE_TYPES = {
    "crypto_bitcoin": {"BigQuery Dataset", "BigQuery Table"},
    "ga4": {"BigQuery Dataset", "BigQuery Table", "Reference"},
    "stackoverflow": {"BigQuery Dataset", "BigQuery Table", "Reference"},
}
SPAN_FIELDS = ("page_no", "heading_path", "offset", "text", "span_id")


class _UnsafeSpanId:
    def __str__(self) -> str:
        raise AssertionError("span-ID diagnostics must not stringify objects")

    def __repr__(self) -> str:
        raise AssertionError("span-ID diagnostics must not render objects")


def _load_fixture(slug: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    fixture_dir = FIXTURE_ROOT / slug
    return (
        json.loads((fixture_dir / "docling_output.json").read_text(encoding="utf-8")),
        json.loads(
            (fixture_dir / "expected_span_ids.json").read_text(encoding="utf-8")
        ),
    )


def _serialize_fixture(
    slug: str, bundle_root: Path
) -> tuple[SerializedRawFile, dict[str, Any]]:
    nodes, expected = _load_fixture(slug)
    return (
        serialize_document(
            nodes,
            doc_id=expected["doc_id"],
            version_id=expected["version_id"],
            source_checksum="0" * 64,
            docling_version="2.109.0",
            bundle_root=bundle_root,
            name=slug,
        ),
        expected,
    )


def _span_dicts(spans: tuple[Any, ...]) -> list[dict[str, Any]]:
    return [span.to_dict() for span in spans]


def _recompute_span_ids(
    spans: tuple[Any, ...], *, doc_id: str, version_id: str
) -> list[dict[str, Any]]:
    """Rebuild S_okf through the production verifier shared with the CLI."""
    return recompute_span_dicts(spans, doc_id=doc_id, version_id=version_id)


def _assert_persisted_span_ids_match_recomputed(
    persisted: list[dict[str, Any]], recomputed: list[dict[str, Any]]
) -> None:
    """Reject sidecars that carry valid UUIDs inconsistent with their coordinates."""
    for index, (persisted_span, recomputed_span) in enumerate(
        zip(persisted, recomputed)
    ):
        if persisted_span["span_id"] != recomputed_span["span_id"]:
            raise AssertionError(
                f"SIDECAR SPAN ID MISMATCH at span[{index}]: "
                f"persisted={persisted_span['span_id']} "
                f"recomputed={recomputed_span['span_id']}"
            )
    if len(persisted) != len(recomputed):
        raise AssertionError(
            "SIDECAR SPAN ID MISMATCH: "
            f"persisted_count={len(persisted)} recomputed_count={len(recomputed)}"
        )


def _first_roundtrip_mismatch(
    direct: list[dict[str, Any]],
    okf: list[dict[str, Any]],
    *,
    doc_id: str,
    file_path: str,
) -> str | None:
    """Delegate deterministic mismatch selection to the production verifier."""
    return first_roundtrip_mismatch(direct, okf, doc_id=doc_id, file_path=file_path)


def _assert_roundtrip_identity(
    direct: list[dict[str, Any]],
    okf: list[dict[str, Any]],
    *,
    doc_id: str,
    file_path: str,
) -> None:
    """Assert set, document order, and each identity coordinate are identical."""
    mismatch = _first_roundtrip_mismatch(
        direct, okf, doc_id=doc_id, file_path=file_path
    )
    direct_span_ids = [span["span_id"] for span in direct]
    okf_span_ids = [span["span_id"] for span in okf]
    if set(direct_span_ids) != set(okf_span_ids):
        raise AssertionError(mismatch)
    if direct_span_ids != okf_span_ids:
        raise AssertionError(mismatch)
    if mismatch is not None:
        raise AssertionError(mismatch)


@pytest.mark.parametrize("slug", FIXTURE_SLUGS)
def test_frozen_docling_spans_roundtrip_through_real_okf(
    slug: str, tmp_path: Path
) -> None:
    """S_direct equals parser-sidecar S_okf for every frozen fixture class."""
    serialized, expected = _serialize_fixture(slug, tmp_path)

    parsed = OKFParser().parse_document(serialized.md_path, tmp_path)
    assert (
        roundtrip_mismatch(
            direct=expected["spans"],
            spans=parsed.spans,
            doc_id=parsed.frontmatter.doc_id or "",
            version_id=parsed.frontmatter.version_id or "",
            file_path=parsed.frontmatter.okf_file_path or "",
        )
        is None
    )


def test_roundtrip_identity_reports_corrupt_persisted_sidecar_span_id(
    tmp_path: Path,
) -> None:
    """A valid but wrong stored UUID cannot pass recomputed S_okf verification."""
    serialized, expected = _serialize_fixture("sectioned-pdf", tmp_path)
    sidecar_json = json.loads(serialized.sidecar_path.read_text(encoding="utf-8"))
    wrong_id = "00000000-0000-0000-0000-000000000099"
    sidecar_json["spans"][1]["span_id"] = wrong_id
    serialized.sidecar_path.write_text(
        json.dumps(sidecar_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    persisted = tuple(SpanRecord.from_dict(span) for span in sidecar_json["spans"])
    recomputed = _recompute_span_ids(
        persisted,
        doc_id=expected["doc_id"],
        version_id=expected["version_id"],
    )

    assert recomputed[1]["span_id"] == expected["spans"][1]["span_id"]
    assert persisted_span_id_mismatch(persisted, recomputed) == (
        "SIDECAR SPAN ID MISMATCH at span[1]: "
        "persisted=00000000-0000-0000-0000-000000000099 "
        "recomputed=53dc3531-7955-525e-8ad5-b63943758f92"
    )


@pytest.mark.parametrize(
    "invalid_span_id",
    (
        "span-id-printable-canary",
        "span-id-control-\x00canary",
        "span-id-high-surrogate-\ud800canary",
        "span-id-low-surrogate-\udcffcanary",
    ),
    ids=("printable", "control", "high-surrogate", "low-surrogate"),
)
def test_first_roundtrip_mismatch_summarizes_invalid_direct_and_okf_span_ids(
    invalid_span_id: str,
) -> None:
    """Every direct comparison span ID follows the UUID diagnostic policy."""
    direct = {
        "page_no": 1,
        "heading_path": ["safe"],
        "offset": 0,
        "text": "safe",
        "span_id": invalid_span_id,
    }
    okf = {**direct, "span_id": "other-span-id-canary"}

    mismatch = first_roundtrip_mismatch(
        [direct], [okf], doc_id="doc", file_path="raw/test.md"
    )

    assert mismatch is not None
    assert mismatch.startswith(
        "ROUNDTRIP MISMATCH at span[0]: field=span_id "
        f"direct={diagnostic_safe_uuid(invalid_span_id)} "
        f"okf={diagnostic_safe_uuid('other-span-id-canary')} "
    )
    assert invalid_span_id not in mismatch
    assert "other-span-id-canary" not in mismatch


@pytest.mark.parametrize(
    ("persisted_span_id", "recomputed_span_id"),
    (
        ("persisted-printable-canary", "recomputed-printable-canary"),
        ("persisted-control-\x00canary", "recomputed-control-\x00canary"),
        (
            "persisted-high-surrogate-\ud800canary",
            "recomputed-high-surrogate-\ud800canary",
        ),
        (
            "persisted-low-surrogate-\udcffcanary",
            "recomputed-low-surrogate-\udcffcanary",
        ),
    ),
    ids=("printable", "control", "high-surrogate", "low-surrogate"),
)
def test_persisted_span_id_mismatch_summarizes_persisted_and_recomputed_ids(
    persisted_span_id: str, recomputed_span_id: str
) -> None:
    """Stored-sidecar diagnostics do not disclose invalid span identifiers."""
    stored_span = object.__new__(SpanRecord)
    object.__setattr__(stored_span, "span_id", persisted_span_id)

    mismatch = persisted_span_id_mismatch(
        (stored_span,), [{"span_id": recomputed_span_id}]
    )

    assert mismatch == (
        "SIDECAR SPAN ID MISMATCH at span[0]: "
        f"persisted={diagnostic_safe_uuid(persisted_span_id)} "
        f"recomputed={diagnostic_safe_uuid(recomputed_span_id)}"
    )
    assert persisted_span_id not in mismatch
    assert recomputed_span_id not in mismatch


def test_span_id_diagnostics_never_stringify_direct_recomputed_or_persisted_ids() -> (
    None
):
    """Each span-ID diagnostic position uses the opaque non-string token."""
    canonical_id = "00000000-0000-0000-0000-000000000001"
    unsafe_id = _UnsafeSpanId()
    base_span = {
        "page_no": 1,
        "heading_path": ["safe"],
        "offset": 0,
        "text": "safe",
        "span_id": canonical_id,
    }
    stored_span = object.__new__(SpanRecord)
    object.__setattr__(stored_span, "span_id", unsafe_id)

    direct_mismatch = first_roundtrip_mismatch(
        [{**base_span, "span_id": unsafe_id}],
        [base_span],
        doc_id="doc",
        file_path="raw/test.md",
    )
    recomputed_mismatch = first_roundtrip_mismatch(
        [base_span],
        [{**base_span, "span_id": unsafe_id}],
        doc_id="doc",
        file_path="raw/test.md",
    )
    persisted_mismatch = persisted_span_id_mismatch(
        (stored_span,), [{"span_id": canonical_id}]
    )

    assert direct_mismatch is not None
    assert "direct=invalid-type=non-string" in direct_mismatch
    assert recomputed_mismatch is not None
    assert "okf=invalid-type=non-string" in recomputed_mismatch
    assert persisted_mismatch == (
        "SIDECAR SPAN ID MISMATCH at span[0]: "
        "persisted=invalid-type=non-string "
        f"recomputed={canonical_id}"
    )


def test_first_mismatch_report_redacts_heading_text_and_absolute_path() -> None:
    """Untrusted coordinates cannot escape through the roundtrip diagnostic."""
    direct = {
        "page_no": 1,
        "heading_path": ["Direct heading\ncanary-heading-direct-秘密"],
        "offset": 0,
        "text": "canary-text-direct-秘密",
        "span_id": "same-id",
    }
    okf = {
        **direct,
        "heading_path": ["OKF heading\ncanary-heading-okf-��"],
    }
    absolute_path = "C:/sensitive/canary-absolute-path/private.md"

    mismatch = first_roundtrip_mismatch(
        [direct], [okf], doc_id="safe-doc-id", file_path=absolute_path
    )

    assert mismatch is not None
    assert "ROUNDTRIP MISMATCH at span[0]: field=heading_path" in mismatch
    assert "direct=len=" in mismatch
    assert "okf=len=" in mismatch
    assert "canary-heading-direct-秘密" not in mismatch
    assert "canary-heading-okf-��" not in mismatch
    assert "canary-text-direct-秘密" not in mismatch
    assert "canary-absolute-path" not in mismatch
    assert "\n" not in mismatch


@pytest.mark.parametrize(
    "unsafe_character",
    (
        chr(0x1B),
        chr(0x09),
        chr(0x00),
        chr(0x7F),
        chr(0x85),
        chr(0x202E),
        chr(0x200B),
    ),
    ids=("escape", "tab", "nul", "delete", "c1", "bidi", "zero-width"),
)
def test_first_mismatch_hashes_relative_paths_with_control_characters(
    unsafe_character: str,
) -> None:
    """Unsafe relative paths are represented only by a hash in diagnostics."""
    direct = {
        "page_no": 1,
        "heading_path": ["safe"],
        "offset": 0,
        "text": "safe",
        "span_id": "same-id",
    }
    okf = {**direct, "offset": 1}
    raw_path = f"raw/{unsafe_character}canary-path.md"

    mismatch = first_roundtrip_mismatch(
        [direct], [okf], doc_id="safe-doc-id", file_path=raw_path
    )

    assert mismatch == (
        "ROUNDTRIP MISMATCH at span[0]: field=offset direct=0 okf=1 "
        f"(doc={diagnostic_safe_text('safe-doc-id')} "
        f"file={diagnostic_safe_path(raw_path)})"
    )
    assert "canary-path" not in mismatch
    assert unsafe_character not in mismatch


def test_first_mismatch_summarizes_all_relative_paths() -> None:
    """Caller paths are always opaque summaries, even when relative."""
    direct = {
        "page_no": 1,
        "heading_path": ["safe"],
        "offset": 0,
        "text": "safe",
        "span_id": "same-id",
    }
    okf = {**direct, "offset": 1}

    mismatch = first_roundtrip_mismatch(
        [direct], [okf], doc_id="safe-doc-id", file_path="raw/sectioned-pdf.md"
    )

    assert mismatch == (
        "ROUNDTRIP MISMATCH at span[0]: field=offset direct=0 okf=1 "
        f"(doc={diagnostic_safe_text('safe-doc-id')} "
        f"file={diagnostic_safe_path('raw/sectioned-pdf.md')})"
    )


def test_diagnostic_safe_path_summarizes_safe_posix_path() -> None:
    """Even ordinary relative paths must not appear in external diagnostics."""
    assert "raw/normal.md" not in diagnostic_safe_path("raw/normal.md")


def test_heading_path_summaries_are_deterministic_and_segment_sensitive() -> None:
    """Canonical summaries distinguish otherwise similarly sized headings."""
    direct = {
        "page_no": 1,
        "heading_path": ["reference"],
        "offset": 0,
        "text": "safe",
        "span_id": "same-id",
    }
    split_one = {**direct, "heading_path": ["ab", "c"]}
    split_two = {**direct, "heading_path": ["a", "bc"]}

    first = first_roundtrip_mismatch(
        [direct], [split_one], doc_id="doc", file_path="raw/test.md"
    )
    repeated = first_roundtrip_mismatch(
        [direct], [split_one], doc_id="doc", file_path="raw/test.md"
    )
    other = first_roundtrip_mismatch(
        [direct], [split_two], doc_id="doc", file_path="raw/test.md"
    )

    assert first == repeated
    assert first is not None and other is not None
    assert first != other
    assert "direct=len=" in first
    assert "sha256=" in first
    assert "['ab', 'c']" not in first


def test_first_mismatch_report_selects_corrupted_sidecar_offset(tmp_path: Path) -> None:
    """A corrupt sidecar offset reports the first mismatch in the fixed format."""
    serialized, expected = _serialize_fixture("sectioned-pdf", tmp_path)
    sidecar_json = json.loads(serialized.sidecar_path.read_text(encoding="utf-8"))
    sidecar_json["spans"][1]["offset"] = 1291
    serialized.sidecar_path.write_text(
        json.dumps(sidecar_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    persisted = tuple(SpanRecord.from_dict(span) for span in sidecar_json["spans"])
    recomputed = _recompute_span_ids(
        persisted,
        doc_id=expected["doc_id"],
        version_id=expected["version_id"],
    )

    with pytest.raises(AssertionError) as error:
        _assert_roundtrip_identity(
            expected["spans"],
            recomputed,
            doc_id=expected["doc_id"],
            file_path="raw/sectioned-pdf.md",
        )

    assert str(error.value) == (
        "ROUNDTRIP MISMATCH at span[1]: field=offset direct=0 okf=1291 "
        "(doc=00000000-0000-0000-0000-000000000001 "
        f"file={diagnostic_safe_path('raw/sectioned-pdf.md')})"
    )


def test_markdown_reflow_does_not_change_sidecar_identity_or_canonical_hash(
    tmp_path: Path,
) -> None:
    """Sidecar-backed identity and canonical hash ignore a reflowed raw body."""
    serialized, expected = _serialize_fixture("sectioned-pdf", tmp_path)
    parser = OKFParser()
    before = parser.parse_document(serialized.md_path, tmp_path)
    persisted_before = _span_dicts(before.spans)
    recomputed_before = _recompute_span_ids(
        before.spans,
        doc_id=before.frontmatter.doc_id or "",
        version_id=before.frontmatter.version_id or "",
    )
    _assert_persisted_span_ids_match_recomputed(persisted_before, recomputed_before)
    frontmatter, _ = load_raw_frontmatter(
        serialized.md_path.read_text(encoding="utf-8")
    )
    serialized.md_path.write_text(
        dump_raw_frontmatter(frontmatter, "Reflowed Markdown is not span evidence."),
        encoding="utf-8",
    )
    refresh_raw_manifest(serialized.md_path)
    after = parser.parse_document(serialized.md_path, tmp_path)
    persisted_after = _span_dicts(after.spans)
    recomputed_after = _recompute_span_ids(
        after.spans,
        doc_id=after.frontmatter.doc_id or "",
        version_id=after.frontmatter.version_id or "",
    )
    _assert_persisted_span_ids_match_recomputed(persisted_after, recomputed_after)

    assert after.canonical_hash == before.canonical_hash == serialized.canonical_hash
    _assert_roundtrip_identity(
        expected["spans"],
        recomputed_after,
        doc_id=expected["doc_id"],
        file_path="raw/sectioned-pdf.md",
    )


def test_parse_then_reserialize_does_not_accumulate_trailing_newlines(
    tmp_path: Path,
) -> None:
    """Parser-output raw rewrites are byte-stable over repeated cycles."""
    serialized, _ = _serialize_fixture("docx", tmp_path)
    original = serialized.md_path.read_bytes()
    parser = OKFParser()

    for _ in range(2):
        parsed = parser.parse_document(serialized.md_path, tmp_path)
        frontmatter, _ = load_raw_frontmatter(
            serialized.md_path.read_text(encoding="utf-8")
        )
        serialized.md_path.write_bytes(
            dump_raw_frontmatter(frontmatter, parsed.body).encode("utf-8")
        )
        refresh_raw_manifest(serialized.md_path)

    assert serialized.md_path.read_bytes() == original


def test_unknown_frontmatter_and_crlf_are_preserved_and_readable(
    tmp_path: Path,
) -> None:
    """Parser preserves unknown fields while normalizing CRLF raw input."""
    serialized, expected = _serialize_fixture("docx", tmp_path)
    text = serialized.md_path.read_text(encoding="utf-8")
    frontmatter, body = load_raw_frontmatter(text)
    future_field = {"language": "中文", "emoji": "��"}
    frontmatter["future_producer_field"] = future_field
    crlf_text = dump_raw_frontmatter(frontmatter, body).replace("\n", "\r\n")
    serialized.md_path.write_bytes(crlf_text.encode("utf-8"))
    refresh_raw_manifest(serialized.md_path)

    raw_crlf = serialized.md_path.read_bytes()
    assert b"\r\n" in raw_crlf
    parser = OKFParser()
    parsed = parser.parse_document(serialized.md_path, tmp_path)
    assert parsed.frontmatter.extra_fields["future_producer_field"] == future_field
    assert "中国" in " ".join(span.text for span in parsed.spans)
    assert "\U0001f310" in " ".join(span.text for span in parsed.spans)

    parsed_frontmatter, _ = load_raw_frontmatter(
        serialized.md_path.read_text(encoding="utf-8")
    )
    normalized = dump_raw_frontmatter(
        {**parsed_frontmatter, **parsed.frontmatter.extra_fields}, parsed.body
    )
    assert "\r\n" not in normalized
    assert normalized.endswith("\n")
    assert not normalized.endswith("\n\n")
    serialized.md_path.write_text(normalized, encoding="utf-8")
    refresh_raw_manifest(serialized.md_path)

    reparsed = parser.parse_document(serialized.md_path, tmp_path)
    assert reparsed.frontmatter.extra_fields["future_producer_field"] == future_field
    assert reparsed.body == parsed.body
    _assert_roundtrip_identity(
        _recompute_span_ids(
            parsed.spans,
            doc_id=parsed.frontmatter.doc_id or "",
            version_id=parsed.frontmatter.version_id or "",
        ),
        _recompute_span_ids(
            reparsed.spans,
            doc_id=reparsed.frontmatter.doc_id or "",
            version_id=reparsed.frontmatter.version_id or "",
        ),
        doc_id=expected["doc_id"],
        file_path="raw/docx.md",
    )


def test_bundle_counts_reserved_and_malformed_files(tmp_path: Path) -> None:
    """Reserved and malformed files are skipped with observable bundle statistics."""
    serialized, _ = _serialize_fixture("sectioned-pdf", tmp_path)
    (tmp_path / "index.md").write_text("---\ntype: index\n---\n", encoding="utf-8")
    (tmp_path / "log.md").write_text("# Log\n", encoding="utf-8")
    (tmp_path / "bad.md").write_text("---\ninvalid: [\n---\n", encoding="utf-8")

    result = OKFParser().parse_bundle(tmp_path)
    assert [doc.file_path for doc in result] == [serialized.md_path]
    assert result.stats.parsed == 1
    assert result.stats.skipped == 3
    assert result.stats.malformed == 1


@pytest.mark.parametrize(("bundle_name", "expected_stats"), SPEC_BUNDLE_STATS.items())
def test_checked_in_knowledge_catalog_spec_bundles_parse(
    bundle_name: str, expected_stats: tuple[int, int, int]
) -> None:
    """Apache-2.0 Knowledge Catalog examples scan without rejecting unknown types."""
    bundle_root = SPEC_BUNDLE_ROOT / bundle_name

    assert bundle_root.is_dir(), f"Missing checked-in fixture bundle: {bundle_root}"
    result = OKFParser().parse_bundle(bundle_root)

    assert (result.stats.parsed, result.stats.skipped, result.stats.malformed) == (
        expected_stats
    )
    assert result.stats.malformed == 0
    assert {document.frontmatter.type for document in result} == SPEC_BUNDLE_TYPES[
        bundle_name
    ]
