"""Filesystem-free semantic admission for generated raw pairs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from .canonical_hash import canonical_hash, validate_canonical_value
from .contracts import RawFrontmatterContract, load_raw_frontmatter
from .generation_manifest import GenerationManifest
from .roundtrip import validate_span_identity_admission
from .sidecar import SpanSidecar


class _FrozenList(tuple):
    """Tuple-backed immutable representation of a YAML list."""


class _FrozenTuple(tuple):
    """Tuple-backed immutable representation of a YAML tuple."""


@dataclass(frozen=True)
class _PreparedRawPair:
    """Validated M1/D/S semantic snapshot awaiting stable-manifest confirmation."""

    frontmatter: Mapping[str, Any]
    body: str
    sidecar: SpanSidecar
    canonical_candidate: str


@dataclass(frozen=True)
class AdmittedRawPair:
    """Immutable result of parsing and validating one raw-pair byte snapshot."""

    frontmatter: Mapping[str, Any]
    body: str
    sidecar: SpanSidecar


def prepare_raw_pair(markdown_bytes: bytes, sidecar_bytes: bytes) -> _PreparedRawPair:
    """Validate M1/D/S bytes and compute their unbound canonical candidate."""
    frontmatter, body = _parse_frontmatter(markdown_bytes)
    sidecar = SpanSidecar.from_bytes(sidecar_bytes)
    _validate_identity(frontmatter, sidecar)
    validate_span_identity_admission(
        sidecar.spans, doc_id=sidecar.doc_id, version_id=sidecar.version_id
    )
    canonical_candidate = canonical_hash(frontmatter, sidecar)
    return _PreparedRawPair(
        _freeze_value(frontmatter), body, sidecar, canonical_candidate
    )


def confirm_raw_pair(
    prepared: _PreparedRawPair, manifest: GenerationManifest
) -> AdmittedRawPair:
    """Bind a prepared semantic snapshot to a stable manifest canonical hash."""
    if prepared.canonical_candidate != manifest.canonical_hash:
        raise ValueError("pair_canonical_mismatch")
    return AdmittedRawPair(prepared.frontmatter, prepared.body, prepared.sidecar)


def admit_raw_pair(
    markdown_bytes: bytes, sidecar_bytes: bytes, manifest: GenerationManifest
) -> AdmittedRawPair:
    """Synchronously prepare and confirm a raw pair for publisher admission."""
    return confirm_raw_pair(prepare_raw_pair(markdown_bytes, sidecar_bytes), manifest)


def thaw_frontmatter(frontmatter: Mapping[str, Any]) -> dict[str, Any]:
    """Return a detached parser-facing YAML-shaped copy of frozen frontmatter."""
    thawed = _thaw_value(frontmatter)
    assert isinstance(thawed, dict)
    return thawed


def _freeze_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {_freeze_value(key): _freeze_value(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return _FrozenList(_freeze_value(item) for item in value)
    if isinstance(value, tuple):
        return _FrozenTuple(_freeze_value(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze_value(item) for item in value)
    return value


def _thaw_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {_thaw_value(key): _thaw_value(item) for key, item in value.items()}
    if isinstance(value, _FrozenList):
        return [_thaw_value(item) for item in value]
    if isinstance(value, _FrozenTuple):
        return tuple(_thaw_value(item) for item in value)
    if isinstance(value, frozenset):
        return {_thaw_value(item) for item in value}
    return value


def _parse_frontmatter(markdown_bytes: bytes) -> tuple[dict[str, Any], str]:
    try:
        content = markdown_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("document must be valid UTF-8") from None
    frontmatter, body = load_raw_frontmatter(content)
    validate_canonical_value(frontmatter)
    if frontmatter.get("type") != "raw":
        raise ValueError("type must be 'raw'")
    RawFrontmatterContract.validate(frontmatter)
    return frontmatter, body


def _validate_identity(frontmatter: Mapping[str, Any], sidecar: SpanSidecar) -> None:
    if sidecar.doc_id != frontmatter["doc_id"]:
        raise ValueError("sidecar doc_id does not match frontmatter")
    if sidecar.version_id != frontmatter["version_id"]:
        raise ValueError("sidecar version_id does not match frontmatter")
