"""Capability-rooted, bounded file reader for untrusted OKF bundles."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from types import TracebackType
from typing import Protocol

from . import _limits

_DRIVE = re.compile(r"^[A-Za-z]:")


_WINDOWS_RESERVED_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    }
)


def _is_windows_forbidden_component(part: str) -> bool:
    """Match Win32 ADS and device-name normalization for one path component."""
    normalized = part.rstrip(". ")
    device_stem = normalized.split(".", maxsplit=1)[0].upper()
    return (
        ":" in part
        or part != normalized
        or not normalized
        or device_stem in _WINDOWS_RESERVED_NAMES
    )


def validate_relative_path(
    value: str | Path | tuple[str, ...], *, windows: bool = False
) -> tuple[str, ...]:
    """Validate a lexical relative path once; resolution is never authorization."""
    if isinstance(value, tuple):
        parts = value
    else:
        raw = os.fspath(value)
        if not isinstance(raw, str) or not raw:
            raise ValueError("document path must be contained in bundle root")
        if raw.startswith(("/", "\\")) or _DRIVE.match(raw):
            raise ValueError("document path must be contained in bundle root")
        parts = tuple(raw.replace("\\", "/").split("/"))
    if not parts or any(
        not isinstance(part, str)
        or not part
        or part in {".", ".."}
        or "/" in part
        or "\\" in part
        or (windows and _is_windows_forbidden_component(part))
        for part in parts
    ):
        raise ValueError("document path must be contained in bundle root")
    return parts


def bundle_relative_components(
    candidate: Path, root: Path, *, windows: bool = False
) -> tuple[str, ...]:
    """Derive a same-flavour lexical relative path without normalization."""
    candidate_path = Path(candidate)
    root_path = Path(root)
    if ".." in candidate_path.parts or ".." in root_path.parts:
        raise ValueError("document path must be contained in bundle root")
    try:
        relative = candidate_path.relative_to(root_path)
    except ValueError:
        raise ValueError("document path must be contained in bundle root") from None
    return validate_relative_path(tuple(relative.parts), windows=windows)


class _Backend(Protocol):
    def close(self) -> None: ...
    def read_bytes(self, parts: tuple[str, ...], maximum: int) -> bytes: ...

    def enumerate_regular_files(
        self, *, maximum_files: int, maximum_entries: int, maximum_depth: int
    ) -> tuple[tuple[str, ...], ...]: ...


class BundleAuthority:
    """A held root handle which authorizes all descendant content reads."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._backend: _Backend | None = None

    def __enter__(self) -> BundleAuthority:
        try:
            if sys.platform == "win32":
                from ._rooted_windows import WindowsBundleBackend

                self._backend = WindowsBundleBackend.open_root(self._root)
            else:
                from ._rooted_posix import PosixBundleBackend

                self._backend = PosixBundleBackend.open_root(self._root)
        except ValueError:
            raise
        except Exception:
            raise ValueError("bundle root cannot be read") from None
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        backend = self._backend
        self._backend = None
        if backend is None:
            return
        try:
            backend.close()
        except BaseException:
            if exc_type is None:
                raise

    def read_bytes(self, parts: tuple[str, ...], maximum: int) -> bytes:
        if (
            type(parts) is not tuple
            or type(maximum) is not int
            or maximum <= 0
            or any(type(part) is not str for part in parts)
        ):
            raise ValueError("bundle read arguments are invalid")
        validated = validate_relative_path(parts, windows=sys.platform == "win32")
        if self._backend is None:
            raise ValueError("bundle root cannot be read")
        return self._backend.read_bytes(validated, maximum)

    def enumerate_regular_files(
        self, *, maximum_files: int, maximum_entries: int, maximum_depth: int
    ) -> tuple[tuple[str, ...], ...]:
        """Enumerate from the held root capability, never from a root pathname.

        This is an authorization walk, not a filesystem snapshot: each later read
        reopens and independently authorizes its requested descendants.
        """
        for value in (maximum_files, maximum_entries, maximum_depth):
            if type(value) is not int or value <= 0:
                raise ValueError("bundle enumeration limits must be positive integers")
        backend = self._backend
        if backend is None:
            raise ValueError("bundle root cannot be read")
        try:
            values = backend.enumerate_regular_files(
                maximum_files=maximum_files,
                maximum_entries=maximum_entries,
                maximum_depth=maximum_depth,
            )
            return tuple(sorted(values))
        except ValueError:
            raise
        except Exception:
            raise ValueError("bundle enumeration cannot be read") from None

    def read_document(
        self, parts: tuple[str, ...], maximum: int | None = None
    ) -> bytes:
        maximum = _limits.MAX_DOCUMENT_BYTES if maximum is None else maximum
        try:
            return self.read_bytes(parts, maximum)
        except ValueError as error:
            if str(error) == "document exceeds maximum size":
                raise
            raise ValueError("document cannot be read") from None

    def read_manifest(self, parts: tuple[str, ...]) -> bytes:
        """Read one bounded adjacent pair manifest through the held root handle."""
        try:
            return self.read_bytes(parts, 16 * 1024)
        except ValueError:
            raise ValueError("pair_manifest_invalid") from None

    def read_sidecar(self, parts: tuple[str, ...]) -> bytes:
        try:
            return self.read_bytes(parts, 64 * 1024 * 1024)
        except ValueError as error:
            if str(error) == "document exceeds maximum size":
                raise ValueError("sidecar exceeds maximum size") from None
            raise ValueError("sidecar cannot be read") from None
