"""Bounded, non-disclosing diagnostics for untrusted OKF values."""

from __future__ import annotations

import hashlib
from pathlib import (
    Path,
    PosixPath,
    PurePath,
    PurePosixPath,
    PureWindowsPath,
    WindowsPath,
)
from uuid import UUID

_TRUSTED_PATH_TYPES = frozenset(
    {PurePosixPath, PureWindowsPath, PosixPath, WindowsPath, type(Path())}
)


def diagnostic_summary(value: object) -> str:
    """Return deterministic string bytes without rendering untrusted content."""
    if not isinstance(value, str):
        return "invalid-type=non-string"
    encoded = str.encode(str.__str__(value), "utf-8", "surrogatepass")
    return f"len={len(encoded)} sha256={hashlib.sha256(encoded).hexdigest()}"


def diagnostic_safe_text(value: object, *, label: str = "value") -> str:
    """Summarize arbitrary untrusted text; ``label`` remains API-compatible only."""
    del label
    return diagnostic_summary(value)


def diagnostic_safe_path(value: object) -> str:
    """Summarize exact strings and trusted stdlib path instances only."""
    if isinstance(value, str):
        return diagnostic_summary(value)
    if type(value) in _TRUSTED_PATH_TYPES:
        return diagnostic_summary(PurePath.__str__(value))
    return diagnostic_summary(value)


def diagnostic_safe_uuid(value: object) -> str:
    """Return canonical UUID text or an opaque, fixed diagnostic category."""
    if not isinstance(value, str):
        return "invalid-type=non-string"
    try:
        return str(UUID(str.__str__(value)))
    except (TypeError, ValueError, AttributeError):
        return diagnostic_summary(value)
