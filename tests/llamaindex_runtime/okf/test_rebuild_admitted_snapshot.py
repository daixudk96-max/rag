"""Regression tests for the rebuild command's frozen admitted snapshot."""

from __future__ import annotations

import importlib.util
from dataclasses import replace
from functools import partial
from pathlib import Path
from types import ModuleType
from typing import Any, NoReturn

import pytest

from llamaindex_runtime.okf.parser import (
    BundleResult,
    BundleStats,
    OKFDocument,
    OKFFrontmatter,
)
from llamaindex_runtime.okf.roundtrip import recompute_span_dicts, recompute_span_id
from llamaindex_runtime.okf.sidecar import SpanRecord

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "rebuild_from_okf.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("rebuild_snapshot", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _document() -> OKFDocument:
    doc_id = "00000000-0000-0000-0000-000000000001"
    version_id = "00000000-0000-0000-0000-000000000002"
    span = SpanRecord("00000000-0000-0000-0000-000000000003", None, (), 0, "Text")
    admitted_span = replace(
        span, span_id=recompute_span_id(span, doc_id=doc_id, version_id=version_id)
    )
    return OKFDocument(
        file_path=Path("raw/test.md"),
        frontmatter=OKFFrontmatter(
            type="raw",
            doc_id=doc_id,
            version_id=version_id,
            okf_file_path="raw/test.md",
        ),
        body="Text",
        spans=(admitted_span,),
        canonical_hash="a" * 64,
    )


def _result(*documents: OKFDocument) -> BundleResult:
    return BundleResult(
        list(documents), BundleStats(parsed=len(documents), skipped=0, malformed=0)
    )


def _expected(document: OKFDocument) -> dict[str, Any]:
    return {
        "doc_id": document.frontmatter.doc_id,
        "version_id": document.frontmatter.version_id,
        "spans": recompute_span_dicts(
            document.spans,
            doc_id=document.frontmatter.doc_id or "",
            version_id=document.frontmatter.version_id or "",
        ),
    }


def _record_rebuild(rebuilt: list[object], admitted: object, *_: Any) -> int:
    rebuilt.append(admitted)
    return 1


def _record_scopes(
    rebuilt_scopes: list[tuple[str | None, str | None]], admitted: Any, *_: Any
) -> int:
    rebuilt_scopes.extend((item.doc_id, item.version_id) for item in admitted.documents)
    return 2


class _NoCursorConnection:
    def cursor(self) -> NoReturn:
        pytest.fail("bare documents must be rejected before cursor DML")
        raise AssertionError("pytest.fail must not return")


def test_bare_document_has_no_public_writer_and_is_rejected_before_cursor_dml() -> None:
    module = _load_module()
    forged = replace(
        _document(),
        frontmatter=replace(_document().frontmatter, type="derived"),
        canonical_hash=None,
    )

    assert not hasattr(module, "rebuild_document")
    with pytest.raises(TypeError, match="admitted raw document"):
        module._rebuild_admitted_document(_NoCursorConnection(), forged)


def test_combined_flow_parses_once_and_reuses_the_verified_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    document = _document()
    parser_calls = 0
    rebuilt: list[object] = []

    class _CountingParser:
        def parse_bundle(self, _: Path) -> BundleResult:
            nonlocal parser_calls
            parser_calls += 1
            return _result(document)

    monkeypatch.setattr(module, "OKFParser", _CountingParser)
    monkeypatch.setattr(module, "_load_expected_spans", lambda _: _expected(document))
    monkeypatch.setattr(
        module, "_require_disposable_database_url", lambda _: ("x", "y")
    )
    monkeypatch.setattr(
        module,
        "_rebuild_admitted_bundle",
        partial(_record_rebuild, rebuilt),
    )

    assert (
        module.main(
            [
                "--bundle",
                "bundle",
                "--verify-roundtrip",
                "--fixture",
                "docx",
                "--rebuild",
            ]
        )
        == 0
    )
    assert parser_calls == 1
    assert len(rebuilt) == 1


def test_combined_fixture_with_extra_raw_scope_fails_before_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    verified = _document()
    extra = replace(
        verified,
        frontmatter=replace(
            verified.frontmatter,
            doc_id="00000000-0000-0000-0000-000000000099",
            version_id="00000000-0000-0000-0000-000000000099",
        ),
    )

    class _Parser:
        def parse_bundle(self, _: Path) -> BundleResult:
            return _result(verified, extra)

    monkeypatch.setattr(module, "OKFParser", _Parser)
    monkeypatch.setattr(module, "_load_expected_spans", lambda _: _expected(verified))
    monkeypatch.setattr(
        module.psycopg,
        "connect",
        lambda *_: pytest.fail("extra scope must fail before connect"),
    )

    with pytest.raises(
        ValueError, match="fixture scope does not cover admitted bundle"
    ):
        module.main(
            [
                "--bundle",
                "bundle",
                "--verify-roundtrip",
                "--fixture",
                "docx",
                "--rebuild",
            ]
        )


def test_standalone_rebuild_preserves_all_admitted_raw_scopes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    first = _document()
    second = replace(
        first,
        frontmatter=replace(
            first.frontmatter,
            doc_id="00000000-0000-0000-0000-000000000099",
            version_id="00000000-0000-0000-0000-000000000099",
        ),
    )
    rebuilt_scopes: list[tuple[str | None, str | None]] = []

    class _Parser:
        def parse_bundle(self, _: Path) -> BundleResult:
            return _result(second, first)

    monkeypatch.setattr(module, "OKFParser", _Parser)
    monkeypatch.setattr(
        module, "_require_disposable_database_url", lambda _: ("x", "y")
    )
    monkeypatch.setattr(
        module,
        "_rebuild_admitted_bundle",
        partial(_record_scopes, rebuilt_scopes),
    )

    assert module.main(["--bundle", "bundle", "--rebuild"]) == 0
    assert rebuilt_scopes == [
        (first.frontmatter.doc_id, first.frontmatter.version_id),
        (second.frontmatter.doc_id, second.frontmatter.version_id),
    ]


def test_admission_rejects_forged_raw_without_canonical_pair_before_connect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    forged = replace(_document(), canonical_hash=None)

    class _Parser:
        def parse_bundle(self, _: Path) -> BundleResult:
            return _result(forged)

    monkeypatch.setattr(module, "OKFParser", _Parser)
    monkeypatch.setattr(
        module.psycopg,
        "connect",
        lambda *_: pytest.fail("forged raw document must fail before connect"),
    )

    with pytest.raises(ValueError, match="admitted raw pair"):
        module.main(["--bundle", "bundle", "--rebuild"])


def test_admission_copies_mutable_parser_output_for_manifest_scope_and_dml(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    document = _document()

    class _Parser:
        def parse_bundle(self, _: Path) -> BundleResult:
            return _result(document)

    monkeypatch.setattr(module, "OKFParser", _Parser)
    admitted = module._admit_bundle(Path("bundle"))
    manifest_before, manifest_hash_before = module._scope_manifest(admitted)
    prepared_before = module._prepare_rebuild(admitted.documents[0])

    document.frontmatter.doc_id = "00000000-0000-0000-0000-000000000099"
    document.frontmatter.version_id = "00000000-0000-0000-0000-000000000098"
    document.canonical_hash = "b" * 64
    document.spans = (
        SpanRecord(
            "00000000-0000-0000-0000-000000000097",
            99,
            ("mutated",),
            7,
            "Mutated",
        ),
    )

    assert module._scope_manifest(admitted) == (manifest_before, manifest_hash_before)
    assert module._prepare_rebuild(admitted.documents[0]) == prepared_before
    assert module._canonical_rows(admitted.documents[0]) == prepared_before[2]
