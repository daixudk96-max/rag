"""Explicit strict raw-pair fixture helpers for OKF parser tests."""

from __future__ import annotations

from pathlib import Path

from llamaindex_runtime.okf.canonical_hash import canonical_hash
from llamaindex_runtime.okf.generation_manifest import GenerationManifest
from llamaindex_runtime.okf.parser import OKFParser
from llamaindex_runtime.okf.sidecar import SpanSidecar


def refresh_raw_manifest(markdown_path: Path, *, canonical: str | None = None) -> Path:
    """Bind the current raw Markdown and sidecar bytes with a strict manifest."""
    sidecar_path = markdown_path.with_suffix(".spans.json")
    markdown_bytes = markdown_path.read_bytes()
    sidecar_bytes = sidecar_path.read_bytes()
    manifest_hash = canonical or _canonical_hash(markdown_bytes, sidecar_bytes)
    manifest_path = markdown_path.with_suffix(".pair.json")
    manifest_path.write_bytes(
        GenerationManifest.create(
            markdown_file=markdown_path.name,
            markdown_bytes=markdown_bytes,
            sidecar_file=sidecar_path.name,
            sidecar_bytes=sidecar_bytes,
            canonical_hash=manifest_hash,
        ).to_bytes()
    )
    return manifest_path


def write_raw_pair(markdown_path: Path, markdown: str, sidecar: SpanSidecar) -> Path:
    """Write a valid raw pair and its strict adjacent manifest explicitly."""
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(markdown, encoding="utf-8")
    sidecar.dump(markdown_path.with_suffix(".spans.json"))
    return refresh_raw_manifest(markdown_path)


def bind_raw_bytes(
    markdown_path: Path,
    sidecar_bytes: bytes,
    *,
    canonical: str = "a" * 64,
    write_sidecar: bool = True,
) -> Path:
    """Bind explicit sidecar bytes, including malformed or absent-sidecar cases."""
    sidecar_path = markdown_path.with_suffix(".spans.json")
    if write_sidecar:
        sidecar_path.write_bytes(sidecar_bytes)
    manifest_path = markdown_path.with_suffix(".pair.json")
    manifest_path.write_bytes(
        GenerationManifest.create(
            markdown_file=markdown_path.name,
            markdown_bytes=markdown_path.read_bytes(),
            sidecar_file=sidecar_path.name,
            sidecar_bytes=sidecar_bytes,
            canonical_hash=canonical,
        ).to_bytes()
    )
    return manifest_path


def _canonical_hash(markdown_bytes: bytes, sidecar_bytes: bytes) -> str:
    frontmatter = OKFParser().parse_frontmatter(markdown_bytes.decode("utf-8"))
    return canonical_hash(frontmatter, SpanSidecar.from_bytes(sidecar_bytes))
