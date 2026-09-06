"""POSIX descriptor-walk backend; no pathname fallback is permitted."""

from __future__ import annotations

import os
import stat
from pathlib import Path


class PosixBundleBackend:
    def __init__(self, descriptor: int) -> None:
        self._descriptor = descriptor

    @classmethod
    def open_root(cls, root: Path) -> PosixBundleBackend:
        supports_dir_fd = getattr(os, "supports_dir_fd", ())
        descriptor: int | None = None
        try:
            directory_flags = _directory_flags()
            _leaf_flags()
            if os.open not in supports_dir_fd:
                raise OSError
            descriptor = os.open(os.fspath(root), directory_flags)
            metadata = os.fstat(descriptor)
            if not stat.S_ISDIR(metadata.st_mode):
                raise OSError
            return cls(descriptor)
        except OSError:
            _cleanup_descriptors(descriptor, [])
            raise ValueError("bundle root cannot be read") from None

    def close(self) -> None:
        descriptor = self._descriptor
        self._descriptor = -1
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                raise ValueError("bundle root cannot be read") from None

    def read_bytes(self, parts: tuple[str, ...], maximum: int) -> bytes:
        parents: list[int] = []
        descriptor: int | None = None
        completed = False
        try:
            parent = self._descriptor
            directory_flags = _directory_flags()
            for part in parts[:-1]:
                child = os.open(part, directory_flags, dir_fd=parent)
                parents.append(child)
                if not stat.S_ISDIR(os.fstat(child).st_mode):
                    raise OSError
                parent = child
            leaf_flags = _leaf_flags()
            descriptor = os.open(parts[-1], leaf_flags, dir_fd=parent)
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise OSError
            document = _bounded_read(descriptor, maximum)
            completed = True
            return document
        except ValueError:
            raise
        except OSError:
            raise ValueError("document cannot be read") from None
        finally:
            if _cleanup_descriptors(descriptor, parents) and completed:
                raise ValueError("document cannot be read") from None

    def enumerate_regular_files(
        self, *, maximum_files: int, maximum_entries: int, maximum_depth: int
    ) -> tuple[tuple[str, ...], ...]:
        """Stream a no-follow DFS while retaining only its active descriptor chain."""
        files: list[tuple[str, ...]] = []
        entries_seen = 0
        root_copy: int | None = None
        failure: ValueError | OSError | None = None
        cleanup_failed = False

        def walk(directory: int, prefix: tuple[str, ...]) -> None:
            nonlocal entries_seen
            # scandir(fd) consumes its fd.  The active DFS descriptor remains ours.
            scan_descriptor = os.dup(directory)
            try:
                stream = os.scandir(scan_descriptor)
            except OSError:
                try:
                    os.close(scan_descriptor)
                except OSError:
                    pass
                raise
            with stream:
                for entry in stream:
                    entries_seen += 1
                    if entries_seen > maximum_entries:
                        raise ValueError("bundle enumeration exceeds maximum entries")
                    name = entry.name
                    if type(name) is not str or not name or name in {".", ".."}:
                        raise OSError
                    parts = (*prefix, name)
                    if len(parts) > maximum_depth:
                        raise ValueError("bundle enumeration exceeds maximum depth")
                    child = os.open(name, _leaf_flags(), dir_fd=directory)
                    try:
                        mode = os.fstat(child).st_mode
                        if stat.S_ISDIR(mode):
                            walk(child, parts)
                        elif stat.S_ISREG(mode):
                            if len(files) >= maximum_files:
                                raise ValueError(
                                    "bundle enumeration exceeds maximum files"
                                )
                            files.append(parts)
                        else:
                            raise OSError
                    finally:
                        os.close(child)

        try:
            root_copy = os.dup(self._descriptor)
            walk(root_copy, ())
        except (ValueError, OSError) as error:
            failure = error
        finally:
            if root_copy is not None:
                try:
                    os.close(root_copy)
                except OSError:
                    cleanup_failed = True
        if cleanup_failed or isinstance(failure, OSError):
            raise ValueError("bundle enumeration cannot be read") from None
        if failure is not None:
            raise failure
        return tuple(sorted(files))


def _cleanup_descriptors(descriptor: int | None, parents: list[int]) -> bool:
    cleanup_failed = False
    descriptors = (() if descriptor is None else (descriptor,)) + tuple(
        reversed(parents)
    )
    for held_descriptor in descriptors:
        try:
            os.close(held_descriptor)
        except OSError:
            cleanup_failed = True
    return cleanup_failed


def _cleanup_pending(pending: list[tuple[int, tuple[str, ...]]]) -> None:
    while pending:
        descriptor, _ = pending.pop()
        try:
            os.close(descriptor)
        except OSError:
            pass


def _required_open_flag(name: str, *, nonzero: bool = False) -> int:
    value = getattr(os, name, _MISSING)
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or (nonzero and value == 0)
    ):
        raise OSError
    return value


def _directory_flags() -> int:
    return (
        _required_open_flag("O_RDONLY")
        | _required_open_flag("O_DIRECTORY", nonzero=True)
        | _required_open_flag("O_NOFOLLOW", nonzero=True)
        | _required_open_flag("O_CLOEXEC", nonzero=True)
    )


def _leaf_flags() -> int:
    return (
        _required_open_flag("O_RDONLY")
        | _required_open_flag("O_NOFOLLOW", nonzero=True)
        | _required_open_flag("O_NONBLOCK", nonzero=True)
        | _required_open_flag("O_CLOEXEC", nonzero=True)
    )


_MISSING = object()


def _bounded_read(descriptor: int, maximum: int) -> bytes:
    chunks = bytearray()
    while True:
        remaining = maximum + 1 - len(chunks)
        if remaining <= 0:
            raise ValueError("document exceeds maximum size")
        chunk = os.read(descriptor, min(64 * 1024, remaining))
        if not chunk:
            return bytes(chunks)
        chunks.extend(chunk)
