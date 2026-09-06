"""Public capability-rooted raw-pair writer contracts."""

from __future__ import annotations

import inspect
from pathlib import Path
from uuid import UUID

import pytest

from llamaindex_runtime.okf.canonical_hash import canonical_hash
from llamaindex_runtime.okf.contracts import dump_raw_frontmatter
from llamaindex_runtime.okf.generation_manifest import GenerationManifest
from llamaindex_runtime.okf.raw_pair import publish_raw_pair
from llamaindex_runtime.okf.sidecar import SpanSidecar


def _payload(name: str = "report") -> tuple[bytes, bytes, bytes]:
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
    markdown = dump_raw_frontmatter(frontmatter, "body").encode()
    sidecar = SpanSidecar(1, doc_id, version_id, ())
    sidecar_bytes = sidecar.to_bytes()
    manifest = GenerationManifest.create(
        markdown_file=f"{name}.md",
        markdown_bytes=markdown,
        sidecar_file=f"{name}.spans.json",
        sidecar_bytes=sidecar_bytes,
        canonical_hash=canonical_hash(frontmatter, sidecar),
    ).to_bytes()
    return markdown, sidecar_bytes, manifest


def test_publish_facade_accepts_only_root_slug_and_three_payloads() -> None:
    assert tuple(inspect.signature(publish_raw_pair).parameters) == (
        "bundle_root",
        "slug",
        "markdown_bytes",
        "sidecar_bytes",
        "manifest_bytes",
    )


@pytest.mark.parametrize("slug", ("report-", "report--draft", "Report", "report_1"))
def test_publish_rejects_non_strict_slug_before_writing(
    tmp_path: Path, slug: str
) -> None:
    with pytest.raises(ValueError, match="^pair_publish_failed$"):
        publish_raw_pair(tmp_path, slug, *_payload())
    assert not (tmp_path / "raw").exists()


def test_publish_creates_raw_and_emits_exact_bound_bytes(tmp_path: Path) -> None:
    markdown, sidecar, manifest = _payload()

    paths = publish_raw_pair(tmp_path, "report", markdown, sidecar, manifest)

    assert paths == (
        tmp_path / "raw" / "report.md",
        tmp_path / "raw" / "report.spans.json",
        tmp_path / "raw" / "report.pair.json",
    )
    assert tuple(path.read_bytes() for path in paths) == (markdown, sidecar, manifest)


@pytest.mark.skipif(
    not hasattr(__import__("os"), "symlink"), reason="symlinks unavailable"
)
def test_publish_rejects_existing_raw_symlink_without_touching_external_sentinel(
    tmp_path: Path,
) -> None:
    external = tmp_path / "external"
    external.mkdir()
    sentinel = external / "sentinel"
    sentinel.write_bytes(b"unchanged")
    (tmp_path / "raw").symlink_to(external, target_is_directory=True)

    with pytest.raises(ValueError, match="^pair_publish_failed$"):
        publish_raw_pair(tmp_path, "report", *_payload())

    assert sentinel.read_bytes() == b"unchanged"
    assert not (external / "report.md").exists()


def test_publish_rejects_manifest_not_bound_to_fixed_member_names(
    tmp_path: Path,
) -> None:
    markdown, sidecar, manifest = _payload("other")

    with pytest.raises(ValueError, match="^pair_publish_failed$"):
        publish_raw_pair(tmp_path, "report", markdown, sidecar, manifest)

    assert not (tmp_path / "raw").exists()
