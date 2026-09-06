"""Deterministic, strict schema for adjacent generated raw-pair manifests."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from ._naming import is_okf_slug

MAX_MANIFEST_BYTES = 16 * 1024
_SCHEMA_FIELDS = (
    "schema_version",
    "markdown_file",
    "markdown_sha256",
    "sidecar_file",
    "sidecar_sha256",
    "canonical_hash",
)
_HEX = frozenset("0123456789abcdef")


@dataclass(frozen=True)
class GenerationManifest:
    schema_version: int
    markdown_file: str
    markdown_sha256: str
    sidecar_file: str
    sidecar_sha256: str
    canonical_hash: str

    @classmethod
    def create(
        cls,
        *,
        markdown_file: str,
        markdown_bytes: bytes,
        sidecar_file: str,
        sidecar_bytes: bytes,
        canonical_hash: str,
    ) -> "GenerationManifest":
        return cls(
            1,
            markdown_file,
            hashlib.sha256(markdown_bytes).hexdigest(),
            sidecar_file,
            hashlib.sha256(sidecar_bytes).hexdigest(),
            canonical_hash,
        )._validated()

    @classmethod
    def from_bytes(cls, raw: bytes) -> "GenerationManifest":
        if len(raw) > MAX_MANIFEST_BYTES:
            raise ValueError("pair_manifest_invalid")
        try:
            value = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicates)
            if not isinstance(value, dict) or set(value) != set(_SCHEMA_FIELDS):
                raise ValueError
            manifest = cls(**value)._validated()
            if raw != manifest.to_bytes():
                raise ValueError
            return manifest
        except (UnicodeDecodeError, TypeError, ValueError, json.JSONDecodeError):
            raise ValueError("pair_manifest_invalid") from None

    def to_bytes(self) -> bytes:
        value = {field: getattr(self, field) for field in _SCHEMA_FIELDS}
        return (
            json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            + "\n"
        ).encode("utf-8")

    def _validated(self) -> "GenerationManifest":
        if (
            not isinstance(self.schema_version, int)
            or isinstance(self.schema_version, bool)
            or self.schema_version != 1
        ):
            raise ValueError("pair_manifest_invalid")
        if not all(
            isinstance(getattr(self, field), str) for field in _SCHEMA_FIELDS[1:]
        ):
            raise ValueError("pair_manifest_invalid")
        if not _safe_filename(self.markdown_file, ".md") or not _safe_filename(
            self.sidecar_file, ".spans.json"
        ):
            raise ValueError("pair_manifest_invalid")
        if self.markdown_file[:-3] != self.sidecar_file[:-11]:
            raise ValueError("pair_manifest_invalid")
        if not all(
            _valid_hash(getattr(self, field))
            for field in ("markdown_sha256", "sidecar_sha256", "canonical_hash")
        ):
            raise ValueError("pair_manifest_invalid")
        return self


def _no_duplicates(pairs: list[tuple[str, Any]]) -> Mapping[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _safe_filename(value: str, suffix: str) -> bool:
    basename = value[: -len(suffix)]
    return bool(
        value
        and value.endswith(suffix)
        and is_okf_slug(basename)
        and "/" not in value
        and "\\" not in value
        and value not in {".", ".."}
    )


def _valid_hash(value: str) -> bool:
    return len(value) == 64 and all(character in _HEX for character in value)
