"""Descriptor-rooted, durable raw-pair publication for POSIX platforms."""

from __future__ import annotations

import errno
import os
import secrets
import stat
from pathlib import Path

_NAMES = ("markdown", "sidecar", "manifest")


def publish(
    root: Path, names: tuple[str, str, str], payloads: tuple[bytes, bytes, bytes]
) -> None:
    root_fd = raw_fd = None
    staged: list[str] = []
    primary: BaseException | None = None
    try:
        root_fd = _open_root(root)
        raw_fd, created = _open_raw(root_fd)
        for label, payload in zip(_NAMES, payloads):
            staged.append(_stage(raw_fd, label, payload))
        _replace_members(raw_fd, staged, names)
        staged.clear()
        if created:
            _sync(root_fd)
    except BaseException as error:
        primary = error
        raise
    finally:
        cleanup_failed = _cleanup(raw_fd, staged)
        raw_close_failed = _close(raw_fd)
        root_close_failed = _close(root_fd)
        if primary is None and (
            cleanup_failed or raw_close_failed or root_close_failed
        ):
            raise OSError("publication cleanup failed")


def _replace_members(
    raw_fd: int, staged: list[str], names: tuple[str, str, str]
) -> None:
    for temporary, final in zip(staged[:2], names[:2]):
        os.replace(temporary, final, src_dir_fd=raw_fd, dst_dir_fd=raw_fd)
        staged.remove(temporary)
    _sync(raw_fd)
    temporary = staged[0]
    os.replace(temporary, names[2], src_dir_fd=raw_fd, dst_dir_fd=raw_fd)
    staged.remove(temporary)
    _sync(raw_fd)


def _open_root(root: Path) -> int:
    descriptor = os.open(os.fspath(root), _directory_flags())
    if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
        _close(descriptor)
        raise OSError
    return descriptor


def _open_raw(root_fd: int) -> tuple[int, bool]:
    try:
        return _open_directory("raw", root_fd), False
    except OSError as error:
        if error.errno != errno.ENOENT:
            raise
    os.mkdir("raw", 0o700, dir_fd=root_fd)
    return _open_directory("raw", root_fd), True


def _open_directory(name: str, parent: int) -> int:
    descriptor = os.open(name, _directory_flags(), dir_fd=parent)
    if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
        _close(descriptor)
        raise OSError
    return descriptor


def _stage(raw_fd: int, label: str, payload: bytes) -> str:
    for _ in range(32):
        name = f".{label}.{secrets.token_hex(16)}.tmp"
        try:
            descriptor = os.open(name, _stage_flags(), 0o600, dir_fd=raw_fd)
        except FileExistsError:
            continue
        try:
            _write_all(descriptor, payload)
            _sync(descriptor)
        except BaseException:
            _unlink(raw_fd, name)
            _close(descriptor)
            raise
        if _close(descriptor):
            _unlink(raw_fd, name)
            raise OSError("temporary close failed")
        return name
    raise OSError("temporary name collision limit reached")


def _write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("short write")
        view = view[written:]


def _sync(descriptor: int) -> None:
    os.fsync(descriptor)


def _cleanup(raw_fd: int | None, names: list[str]) -> bool:
    if raw_fd is None:
        return False
    failed = False
    for name in tuple(names):
        failed = not _unlink(raw_fd, name) or failed
    return failed


def _unlink(raw_fd: int, name: str) -> bool:
    try:
        os.unlink(name, dir_fd=raw_fd)
    except BaseException:
        return False
    return True


def _close(descriptor: int | None) -> bool:
    if descriptor is None:
        return False
    try:
        os.close(descriptor)
    except BaseException:
        return True
    return False


def _required_flag(name: str) -> int:
    value = getattr(os, name, None)
    if not isinstance(value, int) or isinstance(value, bool) or not value:
        raise OSError(f"required flag unavailable: {name}")
    return value


def _directory_flags() -> int:
    return (
        os.O_RDONLY
        | _required_flag("O_DIRECTORY")
        | _required_flag("O_NOFOLLOW")
        | _required_flag("O_CLOEXEC")
    )


def _stage_flags() -> int:
    return (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | _required_flag("O_NOFOLLOW")
        | _required_flag("O_CLOEXEC")
    )
