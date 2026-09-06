"""Regression tests for capability-rooted raw-pair publication semantics."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import UUID

import pytest

from llamaindex_runtime.okf.canonical_hash import canonical_hash
from llamaindex_runtime.okf.contracts import dump_raw_frontmatter
from llamaindex_runtime.okf.generation_manifest import GenerationManifest
from llamaindex_runtime.okf.raw_pair import publish_raw_pair, read_raw_pair
from llamaindex_runtime.okf.rooted_open import BundleAuthority
from llamaindex_runtime.okf.sidecar import SpanSidecar


def _payload(body: bytes, slug: str = "report") -> tuple[bytes, bytes, bytes]:
    doc_id = str(UUID("11111111-1111-1111-1111-111111111111"))
    version_id = str(UUID("22222222-2222-2222-2222-222222222222"))
    frontmatter = {
        "type": "raw",
        "doc_id": doc_id,
        "version_id": version_id,
        "source_checksum": "a" * 64,
        "docling_version": "test",
        "generated_by": "test",
    }
    markdown = dump_raw_frontmatter(frontmatter, body.decode()).encode()
    sidecar = SpanSidecar(1, doc_id, version_id, ())
    sidecar_bytes = sidecar.to_bytes()
    manifest = GenerationManifest.create(
        markdown_file=f"{slug}.md",
        markdown_bytes=markdown,
        sidecar_file=f"{slug}.spans.json",
        sidecar_bytes=sidecar_bytes,
        canonical_hash=canonical_hash(frontmatter, sidecar),
    ).to_bytes()
    return markdown, sidecar_bytes, manifest


def _backend():
    if sys.platform == "win32":
        from llamaindex_runtime.okf import _rooted_write_windows as backend
    else:
        from llamaindex_runtime.okf import _rooted_write_posix as backend
    return backend


def test_publish_replaces_all_members_in_manifest_last_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = _payload(b"old")
    new = _payload(b"new")
    publish_raw_pair(tmp_path, "report", *old)
    backend = _backend()
    observed: list[str] = []
    original = backend._rename if sys.platform == "win32" else backend.os.replace

    if sys.platform == "win32":

        def rename(api, handle, raw, name):
            observed.append(name)
            return original(api, handle, raw, name)

        monkeypatch.setattr(backend, "_rename", rename)
    else:

        def replace(source, target, **kwargs):
            observed.append(target)
            return original(source, target, **kwargs)

        monkeypatch.setattr(backend.os, "replace", replace)

    publish_raw_pair(tmp_path, "report", *new)

    assert observed == ["report.md", "report.spans.json", "report.pair.json"]
    assert tuple(
        path.read_bytes()
        for path in (tmp_path / "raw").iterdir()
        if path.name == "report.md"
    ) == (new[0],)
    assert (tmp_path / "raw" / "report.pair.json").read_bytes() == new[2]


def test_publish_failure_after_member_replacement_leaves_old_manifest_unmodified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old, new = _payload(b"old"), _payload(b"new")
    publish_raw_pair(tmp_path, "report", *old)
    backend = _backend()
    calls = 0
    original = backend._rename if sys.platform == "win32" else backend.os.replace

    if sys.platform == "win32":

        def fail_after_markdown(api, handle, raw, name):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("secret")
            return original(api, handle, raw, name)

        monkeypatch.setattr(backend, "_rename", fail_after_markdown)
    else:

        def fail_after_markdown(source, target, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("secret")
            return original(source, target, **kwargs)

        monkeypatch.setattr(backend.os, "replace", fail_after_markdown)

    with pytest.raises(ValueError, match="^pair_publish_failed$") as raised:
        publish_raw_pair(tmp_path, "report", *new)

    assert raised.value.__cause__ is None
    assert (tmp_path / "raw" / "report.pair.json").read_bytes() == old[2]
    with BundleAuthority(tmp_path) as authority:
        with pytest.raises(ValueError, match="^pair_hash_mismatch$"):
            read_raw_pair(authority, ("raw", "report.md"))


@pytest.mark.parametrize("error_type", (KeyboardInterrupt, SystemExit))
def test_publish_propagates_base_exception_from_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error_type: type[BaseException]
) -> None:
    backend = _backend()
    monkeypatch.setattr(
        backend, "_stage", lambda *_: (_ for _ in ()).throw(error_type())
    )

    with pytest.raises(error_type):
        publish_raw_pair(tmp_path, "report", *_payload(b"body"))


def test_leaf_symlink_is_replaced_without_mutating_its_external_target(
    tmp_path: Path,
) -> None:
    external = tmp_path / "external.md"
    external.write_bytes(b"external")
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "report.md").symlink_to(external)

    publish_raw_pair(tmp_path, "report", *_payload(b"body"))

    assert external.read_bytes() == b"external"
    assert not (raw / "report.md").is_symlink()
