"""End-to-end parser admission evidence for rooted raw M-D-S-M pairs."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from llamaindex_runtime.okf.contracts import dump_raw_frontmatter
from llamaindex_runtime.okf.parser import OKFParser
from llamaindex_runtime.okf.sidecar import SpanSidecar

from .raw_pair_testkit import bind_raw_bytes, refresh_raw_manifest, write_raw_pair


def _valid_pair(root: Path) -> Path:
    doc_id, version_id = str(uuid4()), str(uuid4())
    markdown = dump_raw_frontmatter(
        {
            "type": "raw",
            "doc_id": doc_id,
            "version_id": version_id,
            "source_checksum": "a" * 64,
            "docling_version": "test",
            "generated_by": "test",
        },
        "body",
    )
    path = root / "raw" / "source.md"
    write_raw_pair(path, markdown, SpanSidecar(1, doc_id, version_id, ()))
    return path


def _assert_rejected(root: Path, path: Path, expected: str) -> None:
    with pytest.raises(ValueError, match=f"^{expected}$") as raised:
        OKFParser().parse_document(path, bundle_root=root)
    message = str(raised.value)
    assert str(root) not in message
    assert "$" not in message
    assert raised.value.__cause__ is None


@pytest.mark.parametrize("mutation", ("missing", "malformed", "unknown", "unsafe"))
def test_parser_rejects_invalid_manifest_through_rooted_production_path(
    tmp_path: Path, mutation: str
) -> None:
    path = _valid_pair(tmp_path)
    manifest = path.with_suffix(".pair.json")
    if mutation == "missing":
        manifest.unlink()
    elif mutation == "malformed":
        manifest.write_bytes(b"{")
    elif mutation == "unknown":
        value = json.loads(manifest.read_bytes())
        manifest.write_bytes(json.dumps({**value, "unknown": True}).encode())
    else:
        value = json.loads(manifest.read_bytes())
        value["markdown_file"] = "../outside.md"
        manifest.write_bytes(json.dumps(value).encode())

    _assert_rejected(tmp_path, path, "pair_manifest_invalid")


@pytest.mark.parametrize("member", ("markdown", "sidecar"))
def test_parser_rejects_digest_mismatch_through_rooted_production_path(
    tmp_path: Path, member: str
) -> None:
    path = _valid_pair(tmp_path)
    target = path if member == "markdown" else path.with_suffix(".spans.json")
    target.write_bytes(target.read_bytes() + b"tamper")

    _assert_rejected(tmp_path, path, "pair_hash_mismatch")


def test_parser_rejects_invalid_rebound_sidecar_through_rooted_production_path(
    tmp_path: Path,
) -> None:
    path = _valid_pair(tmp_path)
    bind_raw_bytes(path, b"{")

    _assert_rejected(tmp_path, path, "sidecar contains invalid JSON")


def test_parser_rejects_canonical_mismatch_with_correct_byte_hashes(
    tmp_path: Path,
) -> None:
    path = _valid_pair(tmp_path)
    refresh_raw_manifest(path, canonical="f" * 64)

    _assert_rejected(tmp_path, path, "pair_canonical_mismatch")


def test_parser_propagates_classified_m2_unstable_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _valid_pair(tmp_path)
    error = ValueError("pair_unstable")
    monkeypatch.setattr(
        "llamaindex_runtime.okf.parser.read_raw_pair",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(error),
    )

    with pytest.raises(ValueError) as raised:
        OKFParser().parse_document(path, bundle_root=tmp_path)

    assert raised.value is error
    assert str(raised.value) == "pair_unstable"
    assert raised.value.__cause__ is None


def test_raw_parser_uses_admitted_snapshot_without_reparsing_or_reopening_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _valid_pair(tmp_path)
    from llamaindex_runtime.okf import parser as parser_module

    sidecar_reads = 0
    original_read_sidecar = parser_module.BundleAuthority.read_sidecar

    def record_read_sidecar(self: object, parts: tuple[str, ...]) -> bytes:
        nonlocal sidecar_reads
        sidecar_reads += 1
        return original_read_sidecar(self, parts)  # type: ignore[arg-type]

    monkeypatch.setattr(
        parser_module.BundleAuthority, "read_sidecar", record_read_sidecar
    )
    monkeypatch.setattr(
        OKFParser,
        "parse_frontmatter",
        lambda *_: pytest.fail("raw parser must consume admitted frontmatter"),
    )

    document = OKFParser().parse_document(path, bundle_root=tmp_path)

    assert document.body == "body"
    assert document.spans == ()
    assert sidecar_reads == 1


def test_raw_parser_reaches_the_shared_reader_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _valid_pair(tmp_path)
    from llamaindex_runtime.okf import raw_pair

    calls = 0
    original_admission = raw_pair.prepare_raw_pair

    def record_admission(*args: object):
        nonlocal calls
        calls += 1
        return original_admission(*args)  # type: ignore[arg-type]

    monkeypatch.setattr(raw_pair, "prepare_raw_pair", record_admission)

    OKFParser().parse_document(path, bundle_root=tmp_path)

    assert calls == 1


def test_raw_parser_preserves_body_that_starts_with_frontmatter_delimiter(
    tmp_path: Path,
) -> None:
    doc_id, version_id = str(uuid4()), str(uuid4())
    body = "---\ninner: preserved-content\n---\nafter"
    markdown = dump_raw_frontmatter(
        {
            "type": "raw",
            "doc_id": doc_id,
            "version_id": version_id,
            "source_checksum": "a" * 64,
            "docling_version": "test",
            "generated_by": "test",
        },
        body,
    )
    path = tmp_path / "raw" / "source.md"
    write_raw_pair(path, markdown, SpanSidecar(1, doc_id, version_id, ()))

    document = OKFParser().parse_document(path, bundle_root=tmp_path)

    assert document.body == body


def test_nonraw_parser_preserves_body_that_starts_with_frontmatter_delimiter(
    tmp_path: Path,
) -> None:
    body = "---\ninner: preserved-content\n---\nafter"
    path = tmp_path / "entities" / "source.md"
    path.parent.mkdir()
    path.write_text("---\ntype: legacy_entity\n---\n" + body, encoding="utf-8")

    document = OKFParser().parse_document(path, bundle_root=tmp_path)

    assert document.body == body


def test_raw_parser_thaws_nested_snapshot_data_for_independent_public_dto(
    tmp_path: Path,
) -> None:
    doc_id, version_id = str(uuid4()), str(uuid4())
    markdown = dump_raw_frontmatter(
        {
            "type": "raw",
            "doc_id": doc_id,
            "version_id": version_id,
            "source_checksum": "a" * 64,
            "docling_version": "test",
            "generated_by": "test",
            "future_field": {"nested": ["original"]},
        },
        "body",
    )
    path = tmp_path / "raw" / "source.md"
    write_raw_pair(path, markdown, SpanSidecar(1, doc_id, version_id, ()))

    from llamaindex_runtime.okf.raw_pair import read_raw_pair
    from llamaindex_runtime.okf.rooted_open import BundleAuthority

    with BundleAuthority(tmp_path) as authority:
        snapshot = read_raw_pair(authority, ("raw", "source.md"))
    document = OKFParser()._parse_admitted_raw(path, "raw/source.md", snapshot)
    document.frontmatter.extra_fields["future_field"]["nested"].append("changed")

    assert snapshot.frontmatter["future_field"] == {"nested": ("original",)}


def test_parser_e2e_raw_pair_success_has_stable_bundle_authority_read_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _valid_pair(tmp_path)
    from llamaindex_runtime.okf.rooted_open import BundleAuthority

    counts = {"manifest": 0, "document": 0, "sidecar": 0}
    for method, key in (
        ("read_manifest", "manifest"),
        ("read_document", "document"),
        ("read_sidecar", "sidecar"),
    ):
        original = getattr(BundleAuthority, method)

        def record(
            self: BundleAuthority, *args: object, _key: str = key, _original=original
        ):
            counts[_key] += 1
            return _original(self, *args)

        monkeypatch.setattr(BundleAuthority, method, record)

    OKFParser().parse_document(path, bundle_root=tmp_path)

    assert counts == {"manifest": 2, "document": 1, "sidecar": 1}
