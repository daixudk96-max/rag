"""Capability-rooted raw-pair publication facade.

Returned paths are reporting values only.  They are never supplied to a writer
or used to authorize descendant access.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from ._naming import is_okf_slug
from ._raw_pair_admission import admit_raw_pair
from . import _limits
from .generation_manifest import GenerationManifest

_PLATFORM_PATH_TYPE = type(Path())


def publish_raw_pair(
    bundle_root: Path,
    slug: str,
    markdown_bytes: bytes,
    sidecar_bytes: bytes,
    manifest_bytes: bytes,
) -> tuple[Path, Path, Path]:
    """Publish a verified adjacent pair through a rooted native capability."""
    try:
        names = _validate_inputs(
            bundle_root, slug, markdown_bytes, sidecar_bytes, manifest_bytes
        )
        _publish(bundle_root, names, (markdown_bytes, sidecar_bytes, manifest_bytes))
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:
        raise ValueError("pair_publish_failed") from None
    raw = Path(bundle_root) / "raw"
    return tuple(raw / name for name in names)  # type: ignore[return-value]


def _validate_inputs(
    bundle_root: Path, slug: str, markdown: bytes, sidecar: bytes, manifest_bytes: bytes
) -> tuple[str, str, str]:
    if (
        type(bundle_root) is not _PLATFORM_PATH_TYPE
        or not is_okf_slug(slug)
        or type(markdown) is not bytes
        or type(sidecar) is not bytes
        or type(manifest_bytes) is not bytes
    ):
        raise ValueError
    if _limits.document_size_exceeds_limit(len(markdown)):
        raise ValueError
    manifest = GenerationManifest.from_bytes(manifest_bytes)
    names = (f"{slug}.md", f"{slug}.spans.json", f"{slug}.pair.json")
    if (manifest.markdown_file, manifest.sidecar_file) != names[:2]:
        raise ValueError
    if (hashlib.sha256(markdown).hexdigest(), hashlib.sha256(sidecar).hexdigest()) != (
        manifest.markdown_sha256,
        manifest.sidecar_sha256,
    ):
        raise ValueError
    admit_raw_pair(markdown, sidecar, manifest)
    return names


def _publish(
    root: Path, names: tuple[str, str, str], payloads: tuple[bytes, bytes, bytes]
) -> None:
    if sys.platform == "win32":
        from ._rooted_write_windows import publish
    else:
        from ._rooted_write_posix import publish
    publish(root, names, payloads)
