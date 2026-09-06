"""Windows native writer integration evidence (normal publication must not skip)."""

from __future__ import annotations

import os

# Windows junction capability test invokes cmd.exe.
import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest

from llamaindex_runtime.okf.canonical_hash import canonical_hash
from llamaindex_runtime.okf.contracts import dump_raw_frontmatter
from llamaindex_runtime.okf.generation_manifest import GenerationManifest
from llamaindex_runtime.okf.raw_pair import publish_raw_pair, read_raw_pair
from llamaindex_runtime.okf.rooted_open import BundleAuthority
from llamaindex_runtime.okf.sidecar import SpanSidecar

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Windows native integration"
)


def _payload() -> tuple[bytes, bytes, bytes]:
    doc_id, version_id = str(uuid4()), str(uuid4())
    frontmatter = {
        "type": "raw",
        "doc_id": doc_id,
        "version_id": version_id,
        "source_checksum": "a" * 64,
        "docling_version": "test",
        "generated_by": "test",
    }
    markdown = dump_raw_frontmatter(frontmatter, "body").encode()
    sidecar = SpanSidecar(1, doc_id, version_id, ())
    sidecar_bytes = sidecar.to_bytes()
    manifest = GenerationManifest.create(
        markdown_file="report.md",
        markdown_bytes=markdown,
        sidecar_file="report.spans.json",
        sidecar_bytes=sidecar_bytes,
        canonical_hash=canonical_hash(frontmatter, sidecar),
    ).to_bytes()
    return markdown, sidecar_bytes, manifest


def _create_junction_or_skip(link: Path, target: Path) -> None:
    command = f'mklink /J "{link}" "{target}"'
    # This is a literal cmd.exe argv invocation; it never enables shell=True.
    result = subprocess.run(  # nosec B603, B607
        ["cmd.exe", "/d", "/s", "/c", command],
        capture_output=True,
        check=False,
        shell=False,
        text=True,
    )
    if result.returncode or not link.exists():
        pytest.skip(
            f"directory junction capability unavailable: exit {result.returncode}"
        )


def test_windows_native_publish_and_rooted_read(tmp_path: Path) -> None:
    payload = _payload()
    publish_raw_pair(tmp_path, "report", *payload)

    with BundleAuthority(tmp_path) as authority:
        snapshot = read_raw_pair(authority, ("raw", "report.md"))

    assert (snapshot.markdown_bytes, snapshot.sidecar_bytes) == payload[:2]


def test_windows_existing_raw_symlink_preserves_external_sentinel(
    tmp_path: Path,
) -> None:
    external = tmp_path / "external"
    external.mkdir()
    sentinel = external / "sentinel"
    sentinel.write_bytes(b"unchanged")
    try:
        os.symlink(external, tmp_path / "raw", target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlink capability unavailable: {error.winerror}")

    with pytest.raises(ValueError, match="^pair_publish_failed$"):
        publish_raw_pair(tmp_path, "report", *_payload())

    assert sentinel.read_bytes() == b"unchanged"
    assert not (external / "report.md").exists()


def test_create_junction_quotes_metacharacter_paths_as_single_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    junction = Path(r"C:\controlled\raw & pipe | group (junction)")
    external = Path(r"C:\controlled\external & pipe | group (target)")
    calls: list[tuple[object, ...]] = []

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        assert kwargs == {
            "capture_output": True,
            "check": False,
            "shell": False,
            "text": True,
        }
        return subprocess.CompletedProcess(cast(Any, args), 0)

    def fake_exists(path: Path) -> bool:
        return path == junction

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(Path, "exists", fake_exists)

    _create_junction_or_skip(junction, external)

    command = f'mklink /J "{junction}" "{external}"'
    assert calls == [(["cmd.exe", "/d", "/s", "/c", command],)]


def test_windows_existing_raw_junction_preserves_external_sentinel(
    tmp_path: Path,
) -> None:
    external = tmp_path / "external"
    external.mkdir()
    sentinel = external / "sentinel"
    sentinel.write_bytes(b"unchanged")
    junction = tmp_path / "raw"
    _create_junction_or_skip(junction, external)
    try:
        with pytest.raises(ValueError, match="^pair_publish_failed$"):
            publish_raw_pair(tmp_path, "report", *_payload())

        assert sentinel.read_bytes() == b"unchanged"
        assert not any(
            entry.name in {"report.md", "report.spans.json", "report.pair.json"}
            or entry.name.endswith(".tmp")
            for entry in external.iterdir()
        )
    finally:
        junction.rmdir()
    assert external.is_dir()
    assert sentinel.read_bytes() == b"unchanged"
