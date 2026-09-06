"""Bounded STATIC unresolved runtime compatibility (Phase 16-13)."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from .contracts import canonical_json_sha256

BLOCKED_STATUS = "blocked_not_executed"

_TOP_LEVEL_FIELDS = (
    "extractor_id",
    "extractor_version",
    "model_id",
    "model_revision",
    "artifact_digest",
    "label_map_digest",
    "schema_version",
    "normalization_version",
    "segmentation_version",
    "resource_envelope",
)

_RESOURCE_FIELDS = (
    "cold_start_ms",
    "peak_memory_bytes",
    "throughput_mentions_per_sec",
    "p95_latency_ms",
)


@dataclass(frozen=True)
class RuntimeCompatibilityState:
    status: str
    runtime_compatibility_id: str | None


BLOCKED = RuntimeCompatibilityState(BLOCKED_STATUS, None)

CURRENT_STATUS: str = BLOCKED_STATUS
CURRENT_RUNTIME_COMPATIBILITY_ID: str | None = None


def _require_nonempty_string(value: object, name: str) -> None:
    if type(value) is not str or not value:
        raise ValueError(f"{name} must be a non-empty string")


def _require_digest(value: object, name: str) -> None:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")


def _require_measured(value: object, name: str) -> None:
    if type(value) is int:
        if value < 0:
            raise ValueError(f"{name} must be a nonnegative measurement")
        return
    if type(value) is float:
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"{name} must be a finite nonnegative measurement")
        return
    raise ValueError(f"{name} must be a real number measurement")


def _validate_evidence(evidence: object) -> None:
    if not isinstance(evidence, Mapping):
        raise ValueError("evidence must be a mapping")
    if set(evidence) != set(_TOP_LEVEL_FIELDS):
        raise ValueError("evidence must carry exactly the recorded fields")
    for name in _TOP_LEVEL_FIELDS[:-1]:
        if name in ("artifact_digest", "label_map_digest"):
            _require_digest(evidence[name], name)
        else:
            _require_nonempty_string(evidence[name], name)
    envelope = evidence["resource_envelope"]
    if not isinstance(envelope, Mapping):
        raise ValueError("resource_envelope must be a mapping")
    if set(envelope) != set(_RESOURCE_FIELDS):
        raise ValueError("resource_envelope must carry exactly four measured values")
    for name in _RESOURCE_FIELDS:
        _require_measured(envelope[name], name)


def compute_compatibility_id(evidence: object) -> str:
    """Deterministic canonical SHA-256 over validated recorded evidence."""
    _validate_evidence(evidence)
    return canonical_json_sha256(evidence)


def freeze(evidence: object) -> RuntimeCompatibilityState:
    """Freeze a new immutable state from complete recorded evidence."""
    computed = compute_compatibility_id(evidence)
    return RuntimeCompatibilityState("frozen", computed)
