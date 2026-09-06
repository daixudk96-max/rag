"""Rooted stable raw-pair reader and capability-rooted publisher."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, cast

from ._naming import is_okf_slug
from ._raw_pair_admission import _PreparedRawPair, confirm_raw_pair, prepare_raw_pair
from .generation_manifest import GenerationManifest
from .rooted_write import publish_raw_pair
from .sidecar import SpanSidecar


class _RawPairReadAuthority(Protocol):
    def read_manifest(self, parts: tuple[str, ...]) -> bytes: ...

    def read_document(
        self, parts: tuple[str, ...], maximum: int | None = None
    ) -> bytes: ...

    def read_sidecar(self, parts: tuple[str, ...]) -> bytes: ...


_SAFE_ERRORS = frozenset(
    {
        "pair_manifest_invalid",
        "pair_hash_mismatch",
        "pair_unstable",
        "pair_canonical_mismatch",
        "raw file requires adjacent sidecar",
        "sidecar cannot be read",
        "sidecar exceeds maximum size",
        "sidecar must be valid UTF-8",
        "sidecar contains invalid JSON",
        "sidecar contains duplicate JSON key",
        "sidecar contains unknown field",
        "sidecar root must be a JSON object",
        "sidecar exceeds maximum span count",
        "sidecar JSON resource limit exceeded",
        "sidecar JSON exceeds maximum depth",
        "sidecar schema has invalid container position",
        "sidecar contains duplicate persisted span identity",
        "sidecar contains duplicate recomputed span identity",
        "sidecar span identity does not match canonical coordinates",
        "raw directory document must declare type 'raw'",
        "type must be 'raw'",
        "source_checksum must be a lowercase SHA256 hex string",
        "frontmatter exceeds maximum size",
        "frontmatter must start with '---'",
        "frontmatter block must end with '---'",
        "frontmatter must be a YAML mapping",
        "frontmatter YAML is invalid",
        "frontmatter YAML exceeds maximum aliases",
        "frontmatter YAML exceeds maximum depth",
        "frontmatter YAML exceeds maximum nodes",
        "frontmatter_canonical_cycle",
        "frontmatter_canonical_unsupported",
        "frontmatter_canonical_resource_limit",
        "doc_id is required",
        "version_id is required",
        "source_checksum is required",
        "docling_version is required",
        "generated_by is required",
        "doc_id must be a UUID",
        "version_id must be a UUID",
        "docling_version must be a non-empty string",
        "generated_by must be a non-empty string",
        "sidecar doc_id does not match frontmatter",
        "sidecar version_id does not match frontmatter",
    }
)


@dataclass(frozen=True)
class RawPairSnapshot:
    """One stable M-D-S-M read with its already-admitted semantic content."""

    markdown_bytes: bytes
    sidecar_bytes: bytes
    manifest: GenerationManifest
    frontmatter: Mapping[str, Any]
    body: str
    sidecar: SpanSidecar


def read_raw_pair(
    authority: _RawPairReadAuthority, markdown_parts: tuple[str, ...]
) -> RawPairSnapshot:
    """Return a stable raw pair after exactly one shared semantic admission."""
    if not _is_safe_raw_pair_path(markdown_parts):
        raise ValueError("pair_manifest_invalid")
    last_error: ValueError | None = None
    for _ in range(3):
        try:
            return _read_once(authority, markdown_parts)
        except Exception as error:
            last_error = _redacted(error)
    if last_error is not None:
        raise last_error from None
    raise ValueError("pair_unstable")


def _is_safe_raw_pair_path(parts: object) -> bool:
    if type(parts) is not tuple or tuple.__len__(parts) < 2:
        return False
    for index in range(tuple.__len__(parts)):
        component = tuple.__getitem__(parts, index)
        if (
            type(component) is not str
            or str.__len__(component) == 0
            or component == "."
            or component == ".."
            or str.__contains__(component, "/")
            or str.__contains__(component, "\\")
        ):
            return False
    first = tuple.__getitem__(parts, 0)
    last = tuple.__getitem__(parts, -1)
    return (
        first == "raw"
        and str.endswith(last, ".md")
        and is_okf_slug(str.__getitem__(last, slice(None, -3)))
    )


def _read_once(
    authority: _RawPairReadAuthority, markdown_parts: tuple[str, ...]
) -> RawPairSnapshot:
    manifest_parts = _manifest_parts(markdown_parts)
    before = authority.read_manifest(manifest_parts)
    manifest = GenerationManifest.from_bytes(before)
    _validate_names(manifest, markdown_parts)
    markdown = authority.read_document((*markdown_parts[:-1], manifest.markdown_file))
    if hashlib.sha256(markdown).hexdigest() != manifest.markdown_sha256:
        raise ValueError("pair_hash_mismatch")
    sidecar_bytes = _read_sidecar(authority, markdown_parts, manifest)
    if hashlib.sha256(sidecar_bytes).hexdigest() != manifest.sidecar_sha256:
        raise ValueError("pair_hash_mismatch")
    prepared = _prepare_raw_directory_pair(markdown, sidecar_bytes)
    if before != authority.read_manifest(manifest_parts):
        raise ValueError("pair_unstable")
    admitted = confirm_raw_pair(prepared, manifest)
    return RawPairSnapshot(
        markdown,
        sidecar_bytes,
        manifest,
        admitted.frontmatter,
        admitted.body,
        admitted.sidecar,
    )


def _read_sidecar(
    authority: _RawPairReadAuthority,
    markdown_parts: tuple[str, ...],
    manifest: GenerationManifest,
) -> bytes:
    try:
        return authority.read_sidecar((*markdown_parts[:-1], manifest.sidecar_file))
    except ValueError as error:
        if _safe_error_code(error) == "sidecar cannot be read":
            raise ValueError("raw file requires adjacent sidecar") from None
        raise


def _prepare_raw_directory_pair(
    markdown: bytes, sidecar_bytes: bytes
) -> _PreparedRawPair:
    try:
        return prepare_raw_pair(markdown, sidecar_bytes)
    except ValueError as error:
        if _safe_error_code(error) == "type must be 'raw'":
            raise ValueError("raw directory document must declare type 'raw'") from None
        raise


def _manifest_parts(markdown_parts: tuple[str, ...]) -> tuple[str, ...]:
    if not markdown_parts or not markdown_parts[-1].endswith(".md"):
        raise ValueError("pair_manifest_invalid")
    return (*markdown_parts[:-1], f"{markdown_parts[-1][:-3]}.pair.json")


def _validate_names(manifest: GenerationManifest, parts: tuple[str, ...]) -> None:
    if (
        manifest.markdown_file != parts[-1]
        or manifest.sidecar_file != f"{parts[-1][:-3]}.spans.json"
    ):
        raise ValueError("pair_manifest_invalid")


def _safe_error_code(error: Exception) -> str | None:
    """Extract an allowlisted code without invoking exception protocols."""
    if type(error) is not ValueError:
        return None
    args = cast(tuple[Any, ...], object.__getattribute__(error, "args"))
    if type(args) is not tuple or tuple.__len__(args) != 1:
        return None
    message = tuple.__getitem__(args, 0)
    if type(message) is str and message in _SAFE_ERRORS:
        return message
    return None


def _redacted(error: Exception) -> ValueError:
    return ValueError(_safe_error_code(error) or "pair_manifest_invalid")


__all__ = ["RawPairSnapshot", "publish_raw_pair", "read_raw_pair"]
