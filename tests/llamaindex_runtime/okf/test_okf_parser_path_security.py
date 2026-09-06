"""Path and descriptor security contracts for OKF Markdown parsing."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest

from llamaindex_runtime.okf import parser as parser_module
from llamaindex_runtime.okf.canonical_hash import canonical_hash
from llamaindex_runtime.okf.generation_manifest import GenerationManifest
from llamaindex_runtime.okf.parser import OKFParser
from llamaindex_runtime.okf.roundtrip import recompute_span_id
from llamaindex_runtime.okf.sidecar import SpanRecord, SpanSidecar

from .raw_pair_testkit import bind_raw_bytes


def _write_non_raw(root: Path, relative: str, content: str | None = None) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        content or "---\ntype: legacy_entity\n---\nbody\n", encoding="utf-8"
    )
    return path


def _write_raw(root: Path, relative: str = "raw/source.md") -> Path:
    doc_id, version_id = str(uuid4()), str(uuid4())
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        "type: raw\n"
        f"doc_id: {doc_id}\nversion_id: {version_id}\n"
        "source_checksum: " + "a" * 64 + "\n"
        "docling_version: test\ngenerated_by: test\n---\nbody\n",
        encoding="utf-8",
    )
    record = SpanRecord(
        span_id="00000000-0000-0000-0000-000000000000",
        page_no=1,
        heading_path=(),
        offset=0,
        text="body",
    )
    sidecar = SpanSidecar(
        schema_version=1,
        doc_id=doc_id,
        version_id=version_id,
        spans=(
            SpanRecord(
                span_id=recompute_span_id(record, doc_id=doc_id, version_id=version_id),
                page_no=1,
                heading_path=(),
                offset=0,
                text="body",
            ),
        ),
    )
    sidecar_path = path.with_suffix(".spans.json")
    sidecar.dump(sidecar_path)
    markdown_bytes, sidecar_bytes = path.read_bytes(), sidecar_path.read_bytes()
    manifest = GenerationManifest.create(
        markdown_file=path.name,
        markdown_bytes=markdown_bytes,
        sidecar_file=sidecar_path.name,
        sidecar_bytes=sidecar_bytes,
        canonical_hash=canonical_hash(
            OKFParser().parse_frontmatter(markdown_bytes.decode("utf-8")), sidecar
        ),
    )
    path.with_suffix(".pair.json").write_bytes(manifest.to_bytes())
    return path


def _symlink_or_skip(link: Path, target: Path, *, directory: bool = False) -> None:
    try:
        link.symlink_to(target, target_is_directory=directory)
    except (NotImplementedError, OSError):
        pytest.skip("symlink creation is unavailable on this platform")


def test_top_level_raw_is_the_only_raw_location_and_sidecar_is_loaded(
    tmp_path: Path,
) -> None:
    raw = _write_raw(tmp_path, "raw/nested/source.md")
    nested_non_raw = _write_non_raw(tmp_path, "entities/raw/entity.md")

    raw_document = OKFParser().parse_document(raw, tmp_path)
    entity_document = OKFParser().parse_document(nested_non_raw, tmp_path)

    assert raw_document.frontmatter.okf_file_path == "raw/nested/source.md"
    assert raw_document.spans
    assert entity_document.frontmatter.type == "legacy_entity"


@pytest.mark.parametrize(
    "relative", ("entities/raw.md", "templates/raw.md", "archive/raw.md")
)
def test_raw_outside_bundle_top_level_raw_is_rejected(
    tmp_path: Path, relative: str
) -> None:
    path = _write_raw(tmp_path, relative)

    with pytest.raises(
        ValueError, match="^raw document must reside under bundle root raw directory$"
    ) as raised:
        OKFParser().parse_document(path, tmp_path)

    assert raised.value.__cause__ is None


def test_raw_without_bundle_root_fails_closed(tmp_path: Path) -> None:
    path = _write_raw(tmp_path)

    with pytest.raises(
        ValueError, match="^raw document must reside under bundle root raw directory$"
    ):
        OKFParser().parse_document(path)


def test_non_raw_inside_top_level_raw_is_rejected_by_reader_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_non_raw(tmp_path, "raw/incorrect.md")
    bind_raw_bytes(path, SpanSidecar(1, str(uuid4()), str(uuid4()), ()).to_bytes())
    calls = 0
    original_read_raw_pair = parser_module.read_raw_pair

    def record_reader(*args: object, **kwargs: object):
        nonlocal calls
        calls += 1
        return original_read_raw_pair(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(parser_module, "read_raw_pair", record_reader)

    with pytest.raises(
        ValueError, match="^raw directory document must declare type 'raw'$"
    ):
        OKFParser().parse_document(path, tmp_path)

    assert calls == 1


def test_direct_lexically_outside_file_is_rejected_before_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = _write_non_raw(tmp_path.parent, "outside-secret.md")
    called = False

    def fail_open(*_: object, **__: object) -> int:
        nonlocal called
        called = True
        raise AssertionError("must not open outside file")

    monkeypatch.setattr(parser_module.os, "open", fail_open)
    with pytest.raises(
        ValueError, match="^document path must be contained in bundle root$"
    ) as raised:
        OKFParser().parse_document(outside, tmp_path)

    assert raised.value.__cause__ is None
    assert not called


@pytest.mark.parametrize("inside", (False, True))
def test_terminal_symlink_is_contained_or_rejected_without_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, inside: bool
) -> None:
    target_root = tmp_path if inside else tmp_path.parent / "external"
    target = _write_non_raw(target_root, "target.md")
    link = tmp_path / "entities" / "link.md"
    link.parent.mkdir()
    _symlink_or_skip(link, target)
    opened = False
    original_open = os.open

    def record_open(candidate: Path, flags: int) -> int:
        nonlocal opened
        opened = True
        return original_open(candidate, flags)

    monkeypatch.setattr(parser_module.os, "open", record_open)
    expected = "document cannot be read"
    with pytest.raises(ValueError, match=f"^{expected}$"):
        OKFParser().parse_document(link, tmp_path)
    assert not opened


@pytest.mark.parametrize("inside", (False, True))
def test_parent_symlink_is_contained_or_rejected_without_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, inside: bool
) -> None:
    target_root = (
        tmp_path / "safe-target" if inside else tmp_path.parent / "external-parent"
    )
    target = _write_non_raw(target_root, "nested/file.md")
    link_parent = tmp_path / "linked"
    _symlink_or_skip(link_parent, target.parent, directory=True)
    candidate = link_parent / target.name
    opened = False
    original_open = os.open

    def record_open(candidate: Path, flags: int) -> int:
        nonlocal opened
        opened = True
        return original_open(candidate, flags)

    monkeypatch.setattr(parser_module.os, "open", record_open)
    expected = "document cannot be read"
    with pytest.raises(ValueError, match=f"^{expected}$"):
        OKFParser().parse_document(candidate, tmp_path)
    assert not opened


def test_bundle_symlink_candidate_is_malformed_and_valid_sibling_continues(
    tmp_path: Path,
) -> None:
    valid = _write_non_raw(tmp_path, "entities/valid.md")
    external = _write_non_raw(tmp_path.parent / "external-bundle", "outside.md")
    link = tmp_path / "entities" / "outside.md"
    _symlink_or_skip(link, external)

    result = OKFParser().parse_bundle(tmp_path)

    assert [document.file_path for document in result] == [valid]
    assert result.stats.parsed == 1
    assert result.stats.malformed == result.stats.skipped == 1


def test_bundle_malformed_misplaced_raw_continues_and_reserved_is_not_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_raw(tmp_path, "entities/misplaced.md")
    valid = _write_non_raw(tmp_path, "entities/valid.md")
    reserved = _write_non_raw(tmp_path, "raw/index.md")
    opened: list[Path] = []
    original_open = parser_module.os.open

    def record_open(candidate: Path, flags: int) -> int:
        opened.append(candidate)
        return original_open(candidate, flags)

    monkeypatch.setattr(parser_module.os, "open", record_open)
    result = OKFParser().parse_bundle(tmp_path)
    assert [document.file_path for document in result] == [valid]
    assert result.stats.parsed == 1
    assert result.stats.malformed == 1
    assert result.stats.skipped == 2
    assert reserved not in opened


def test_obsidian_is_pure_skip_and_is_not_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_non_raw(tmp_path, ".obsidian/config.md")
    opened = False
    original_open = parser_module.os.open

    def record_open(candidate: Path, flags: int) -> int:
        nonlocal opened
        opened = True
        return original_open(candidate, flags)

    monkeypatch.setattr(parser_module.os, "open", record_open)
    result = OKFParser().parse_bundle(tmp_path)
    assert result.stats.parsed == result.stats.malformed == 0
    assert result.stats.skipped == 1
    assert not opened


def test_reader_detects_lstat_fstat_identity_mismatch_before_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_non_raw(tmp_path, "document.md")
    monkeypatch.setattr(parser_module.os.path, "samestat", lambda *_: False)
    monkeypatch.setattr(
        parser_module.os, "read", lambda *_: pytest.fail("must not read")
    )

    with pytest.raises(ValueError, match="^document cannot be read$") as raised:
        parser_module._read_document_bytes_bounded(path)

    assert raised.value.__cause__ is None


def test_reader_collects_short_reads_and_rejects_growth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_non_raw(tmp_path, "document.md")
    original_read = parser_module.os.read
    chunks = iter((b"ab", b"c", b""))
    monkeypatch.setattr(parser_module.os, "read", lambda *_: next(chunks))
    assert parser_module._read_document_bytes_bounded(path) == b"abc"

    monkeypatch.setattr(parser_module._limits, "MAX_DOCUMENT_BYTES", 3)
    chunks = iter((b"ab", b"cd"))
    monkeypatch.setattr(parser_module.os, "read", lambda *_: next(chunks))
    with pytest.raises(ValueError, match="^document exceeds maximum size$"):
        parser_module._read_document_bytes_bounded(path)
    monkeypatch.setattr(parser_module.os, "read", original_read)


def test_reader_closes_descriptor_on_read_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_non_raw(tmp_path, "document.md")
    closed: list[int] = []
    original_close = parser_module.os.close
    monkeypatch.setattr(
        parser_module.os, "read", lambda *_: (_ for _ in ()).throw(OSError("no"))
    )

    def record_close(fd: int) -> None:
        closed.append(fd)
        original_close(fd)

    monkeypatch.setattr(parser_module.os, "close", record_close)

    with pytest.raises(ValueError, match="^document cannot be read$"):
        parser_module._read_document_bytes_bounded(path)
    assert closed
