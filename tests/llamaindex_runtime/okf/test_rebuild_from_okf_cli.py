"""CLI roundtrip and diagnostic-redaction behavior tests for OKF rebuild."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import replace
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from llamaindex_runtime.okf.parser import BundleResult, OKFParser
from llamaindex_runtime.okf.roundtrip import recompute_span_id
from llamaindex_runtime.okf.sidecar import SpanRecord

from ._rebuild_cli_testkit import (
    FIXTURE_ROOT,
    bundle_result,
    load_rebuild_module,
    make_bundle,
    run_cli,
)
from .raw_pair_testkit import refresh_raw_manifest

_PRODUCT_DIAGNOSTIC_PREFIXES = (
    "ERROR:llamaindex_runtime.okf.parser:",
    "ROUNDTRIP MISMATCH ",
)
_DISALLOWED_STDERR_CONTROL_CHARACTERS = re.compile(r"[\x00-\x09\x0b-\x1f\x7f-\x9f]")


def _assert_no_unicode_controls(value: str) -> None:
    assert all(
        not unicodedata.category(character).startswith("C") for character in value
    )


def _product_diagnostic_lines(stderr: str) -> list[str]:
    """Return only CLI product diagnostics, excluding library warnings."""
    return [
        line
        for line in stderr.splitlines()
        if line.startswith(_PRODUCT_DIAGNOSTIC_PREFIXES)
    ]


def _assert_product_diagnostics_have_no_unicode_controls(stderr: str) -> None:
    for line in _product_diagnostic_lines(stderr):
        _assert_no_unicode_controls(line)


def _assert_canaries_are_redacted(
    result: CompletedProcess[str], canaries: dict[str, str]
) -> None:
    stdout = result.stdout
    stderr = result.stderr
    assert not _DISALLOWED_STDERR_CONTROL_CHARACTERS.search(stderr)
    for stream in (stdout, stderr):
        assert all(canary not in stream for canary in canaries.values())


def test_cli_subprocess_hashes_unsafe_missing_bundle_argument() -> None:
    """A hostile CLI bundle argument cannot inject characters into stderr."""
    unsafe_bundle = "missing-\x1b\t\x7f\x85‮​\x1b]8;;canary.invalid\x1b\\bundle"

    result = run_cli(
        "--bundle",
        unsafe_bundle,
        "--verify-roundtrip",
        "--fixture",
        "sectioned-pdf",
    )

    assert result.returncode == 1
    assert result.stdout == ""
    expected = (
        f"len={len(unsafe_bundle.encode('utf-8', 'surrogatepass'))} "
        f"sha256={hashlib.sha256(unsafe_bundle.encode('utf-8', 'surrogatepass')).hexdigest()}"
    )
    assert f"Bundle path does not exist: {expected}" in result.stderr
    assert "canary.invalid" not in result.stderr
    assert "missing-" not in result.stderr
    assert all(
        not unicodedata.category(character).startswith("C")
        for character in result.stderr.replace("\r", "").replace("\n", "")
    )


def test_cli_roundtrip_uses_parser_only_and_matches_frozen_fixture(
    tmp_path: Path,
) -> None:
    bundle = make_bundle(tmp_path, "sectioned-pdf")

    result = run_cli(
        "--bundle", str(bundle), "--verify-roundtrip", "--fixture", "sectioned-pdf"
    )

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""
    assert not _DISALLOWED_STDERR_CONTROL_CHARACTERS.search(result.stderr)
    _assert_no_unicode_controls(result.stderr)


def test_cli_roundtrip_redacts_heading_text_and_absolute_path_canaries(
    tmp_path: Path,
) -> None:
    """CLI diagnostics retain the mismatch coordinate but not untrusted content."""
    bundle, canaries = _make_bundle_with_heading_canaries(tmp_path)

    result = run_cli(
        "--bundle", str(bundle), "--verify-roundtrip", "--fixture", "sectioned-pdf"
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert _product_diagnostic_lines(result.stderr) == [_heading_mismatch_line()]
    assert str(tmp_path) not in result.stderr
    _assert_canaries_are_redacted(result, canaries)


def _make_bundle_with_heading_canaries(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    bundle = make_bundle(tmp_path, "sectioned-pdf")
    sidecar_path = next(bundle.glob("raw/*.spans.json"))
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    expected = json.loads(
        (FIXTURE_ROOT / "sectioned-pdf" / "expected_span_ids.json").read_text(
            encoding="utf-8"
        )
    )
    canaries = {
        "heading": "canary-heading-cli-秘密\nnext-line",
        "text": "canary-text-cli-秘密",
        "path": "canary-path-cli-秘密",
        "uuid": "00000000-0000-0000-0000-000000000098",
        "absolute_path": str(tmp_path / "canary-absolute-path-cli"),
    }
    sidecar["spans"][0]["heading_path"] = list(canaries.values())[:-1]
    changed_span = SpanRecord.from_dict(sidecar["spans"][0])
    sidecar["spans"][0]["span_id"] = recompute_span_id(
        changed_span, doc_id=expected["doc_id"], version_id=expected["version_id"]
    )
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
    refresh_raw_manifest(next(bundle.glob("raw/*.md")))
    return bundle, canaries


def _heading_mismatch_line() -> str:
    safe_file = "raw/sectioned-pdf.md"
    safe_file_summary = (
        f"len={len(safe_file.encode('utf-8'))} "
        f"sha256={hashlib.sha256(safe_file.encode('utf-8')).hexdigest()}"
    )
    return (
        "ROUNDTRIP MISMATCH at span[0]: field=heading_path "
        "direct=len=32 sha256=46c27fdf49e3048fec8f1d7279a1840c4755cab26840f916308fcaad57afac16 "
        "okf=len=115 sha256=c6ad1e9e163bfa34b70fe6f09c6e81d6dae0d324997602673b4ee9e0b4695050 "
        "(doc=00000000-0000-0000-0000-000000000001 "
        f"file={safe_file_summary})"
    )


def test_cli_roundtrip_hashes_osc_style_relative_path_without_controls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The CLI emits a safe product line even when parser metadata is hostile."""
    bundle = make_bundle(tmp_path, "sectioned-pdf")
    document = OKFParser().parse_bundle(bundle)[0]
    unsafe_path = "raw/\x1b]8;;https://canary.invalid\x1b\\canary.md"
    unsafe_document = replace(
        document,
        frontmatter=replace(document.frontmatter, okf_file_path=unsafe_path),
        spans=(replace(document.spans[0], offset=1), *document.spans[1:]),
    )
    module = load_rebuild_module()

    class _UnsafePathParser:
        def parse_bundle(self, _: Path) -> BundleResult:
            return bundle_result(unsafe_document)

    monkeypatch.setattr(module, "OKFParser", _UnsafePathParser)
    assert (
        module.main(
            [
                "--bundle",
                str(bundle),
                "--verify-roundtrip",
                "--fixture",
                "sectioned-pdf",
            ]
        )
        == 1
    )

    stderr = capsys.readouterr().err
    expected_hash = hashlib.sha256(unsafe_path.encode("utf-8")).hexdigest()
    assert _product_diagnostic_lines(stderr) == [
        "ROUNDTRIP MISMATCH at span[0]: field=offset direct=0 okf=1 "
        "(doc=00000000-0000-0000-0000-000000000001 "
        f"file=len={len(unsafe_path.encode('utf-8'))} sha256={expected_hash})"
    ]
    assert "canary.invalid" not in stderr
    assert "canary.md" not in stderr
    _assert_product_diagnostics_have_no_unicode_controls(stderr)


def test_cli_refuses_roundtrip_after_admission_rejects_corrupt_sidecar_offset(
    tmp_path: Path,
) -> None:
    """Corrupt sidecars are rejected before the roundtrip field comparison runs."""
    bundle = make_bundle(tmp_path, "sectioned-pdf")
    sidecar_path = next(bundle.glob("raw/*.spans.json"))
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    canaries = {
        "path": "canary-path-not-for-cli-output",
        "uuid": "00000000-0000-0000-0000-000000000099",
        "text": "canary-text-not-for-cli-output",
    }
    sidecar["spans"][1].update(
        offset=1291, **{f"canary_{key}": value for key, value in canaries.items()}
    )
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")

    parsed = OKFParser().parse_bundle(bundle)
    assert list(parsed) == []
    assert (parsed.stats.parsed, parsed.stats.skipped, parsed.stats.malformed) == (
        0,
        1,
        1,
    )

    result = run_cli(
        "--bundle", str(bundle), "--verify-roundtrip", "--fixture", "sectioned-pdf"
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert _product_diagnostic_lines(result.stderr) == _corrupt_sidecar_diagnostics()
    assert str(tmp_path) not in result.stderr
    _assert_canaries_are_redacted(result, canaries)


def _corrupt_sidecar_diagnostics() -> list[str]:
    safe_file = "raw/sectioned-pdf.md"
    safe_file_summary = (
        f"len={len(safe_file.encode('utf-8'))} "
        f"sha256={hashlib.sha256(safe_file.encode('utf-8')).hexdigest()}"
    )
    return [
        "ERROR:llamaindex_runtime.okf.parser:Failed to parse OKF document: "
        f"path={safe_file_summary} category=invalid_document",
        "ROUNDTRIP MISMATCH at span[0]: field=document_count direct_count=1 okf_count=0 "
        "(doc=00000000-0000-0000-0000-000000000001 "
        f"file={safe_file_summary})",
    ]
