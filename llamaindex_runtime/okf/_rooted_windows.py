"""Windows Native-API rooted handle backend.

Descendants are opened only through ``NtCreateFile`` with RootDirectory set to
an already-held parent handle. It intentionally has no full-path fallback.
Native DLL binding is lazy so this module remains importable off Windows.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from collections.abc import Iterator
from pathlib import Path
from typing import Any

FILE_ATTRIBUTE_DIRECTORY = 0x10
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
FILE_TYPE_DISK = 1
GENERIC_READ = 0x80000000
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
FILE_OPEN = 1
FILE_OPEN_REPARSE_POINT = 0x00200000
FILE_DIRECTORY_FILE = 0x00000001
FILE_NON_DIRECTORY_FILE = 0x00000040
FILE_SYNCHRONOUS_IO_NONALERT = 0x00000020
SYNCHRONIZE = 0x00100000
FILE_SHARE_ALL = 7


class _UnicodeString(ctypes.Structure):
    _fields_ = [
        ("Length", wintypes.USHORT),
        ("MaximumLength", wintypes.USHORT),
        ("Buffer", wintypes.LPWSTR),
    ]


class _ObjectAttributes(ctypes.Structure):
    _fields_ = [
        ("Length", wintypes.ULONG),
        ("RootDirectory", wintypes.HANDLE),
        ("ObjectName", ctypes.POINTER(_UnicodeString)),
        ("Attributes", wintypes.ULONG),
        ("SecurityDescriptor", wintypes.LPVOID),
        ("SecurityQualityOfService", wintypes.LPVOID),
    ]


class _IoStatusBlock(ctypes.Structure):
    _fields_ = [("Status", wintypes.LONG), ("Information", ctypes.c_size_t)]


class _ByHandleInfo(ctypes.Structure):
    _fields_ = [("attributes", wintypes.DWORD), ("_rest", ctypes.c_byte * 48)]


class _WindowsApi:
    """Injectable Native API surface, loaded only by Windows root opening."""

    def __init__(self, kernel32: Any, ntdll: Any) -> None:
        self.kernel32 = kernel32
        self.ntdll = ntdll


def _load_native_api() -> _WindowsApi | None:
    """Load and configure the native functions, or fail closed off Windows."""
    loader = getattr(ctypes, "WinDLL", None)
    if loader is None:
        return None
    try:
        kernel32 = loader("kernel32", use_last_error=True)
        ntdll = loader("ntdll", use_last_error=True)
    except OSError:
        return None
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.GetFileInformationByHandle.argtypes = [wintypes.HANDLE, wintypes.LPVOID]
    kernel32.GetFileInformationByHandle.restype = wintypes.BOOL
    kernel32.GetFileType.argtypes = [wintypes.HANDLE]
    kernel32.GetFileType.restype = wintypes.DWORD
    kernel32.ReadFile.argtypes = [
        wintypes.HANDLE,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPVOID,
    ]
    kernel32.ReadFile.restype = wintypes.BOOL
    ntdll.NtCreateFile.argtypes = [
        ctypes.POINTER(wintypes.HANDLE),
        wintypes.DWORD,
        ctypes.POINTER(_ObjectAttributes),
        ctypes.POINTER(_IoStatusBlock),
        wintypes.LPVOID,
        wintypes.ULONG,
        wintypes.ULONG,
        wintypes.ULONG,
        wintypes.ULONG,
        wintypes.LPVOID,
        wintypes.ULONG,
    ]
    ntdll.NtCreateFile.restype = wintypes.LONG
    query = getattr(ntdll, "NtQueryDirectoryFile", None)
    if query is not None:
        query.argtypes = [
            wintypes.HANDLE,
            wintypes.HANDLE,
            wintypes.LPVOID,
            wintypes.LPVOID,
            ctypes.POINTER(_IoStatusBlock),
            wintypes.LPVOID,
            wintypes.ULONG,
            wintypes.ULONG,
            wintypes.BOOL,
            wintypes.LPVOID,
            wintypes.BOOL,
        ]
        query.restype = wintypes.LONG
    return _WindowsApi(kernel32, ntdll)


class WindowsBundleBackend:
    def __init__(self, handle: int, api: _WindowsApi) -> None:
        self._handle = handle
        self._api = api

    @classmethod
    def open_root(cls, root: Path) -> WindowsBundleBackend:
        api = _load_native_api()
        if api is None:
            raise ValueError("bundle root cannot be read")
        handle = api.kernel32.CreateFileW(
            str(root),
            GENERIC_READ,
            FILE_SHARE_ALL,
            None,
            OPEN_EXISTING,
            FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT,
            None,
        )
        if handle == INVALID_HANDLE_VALUE:
            raise ValueError("bundle root cannot be read")
        try:
            valid = _is_directory(api, handle)
        except Exception:
            valid = False
        if not valid:
            _close_handles(api, (handle,))
            raise ValueError("bundle root cannot be read")
        return cls(handle, api)

    def close(self) -> None:
        handle = self._handle
        self._handle = 0
        if handle and _close_handles(self._api, (handle,)):
            raise ValueError("bundle root cannot be read")

    def read_bytes(self, parts: tuple[str, ...], maximum: int) -> bytes:
        parents: list[int] = []
        leaf = 0
        result = b""
        error: ValueError | None = None
        try:
            parent = self._handle
            for part in parts[:-1]:
                child = _open_child(self._api, parent, part, directory=True)
                parents.append(child)
                parent = child
            leaf = _open_child(self._api, parent, parts[-1], directory=False)
            result = _read_handle(self._api, leaf, maximum)
        except ValueError as exc:
            error = exc
        except Exception:
            error = ValueError("document cannot be read")

        cleanup_failed = _close_handles(self._api, (leaf, *reversed(parents)))
        if error is not None:
            raise error
        if cleanup_failed:
            raise ValueError("document cannot be read")
        return result

    def enumerate_regular_files(
        self, *, maximum_files: int, maximum_entries: int, maximum_depth: int
    ) -> tuple[tuple[str, ...], ...]:
        """Stream native directory records through a depth-first handle chain."""
        files: list[tuple[str, ...]] = []
        entries_seen = 0

        def walk(parent: int, prefix: tuple[str, ...]) -> None:
            nonlocal entries_seen
            for name, attributes in _directory_entries(self._api, parent):
                if name in {".", ".."}:
                    continue
                entries_seen += 1
                if entries_seen > maximum_entries:
                    raise ValueError("bundle enumeration exceeds maximum entries")
                if attributes & FILE_ATTRIBUTE_REPARSE_POINT:
                    raise OSError
                parts = (*prefix, name)
                if len(parts) > maximum_depth:
                    raise ValueError("bundle enumeration exceeds maximum depth")
                directory = bool(attributes & FILE_ATTRIBUTE_DIRECTORY)
                child = _open_child(self._api, parent, name, directory=directory)
                try:
                    if directory:
                        walk(child, parts)
                    else:
                        if len(files) >= maximum_files:
                            raise ValueError("bundle enumeration exceeds maximum files")
                        files.append(parts)
                finally:
                    if _close_handles(self._api, (child,)):
                        raise OSError

        try:
            walk(self._handle, ())
        except ValueError:
            raise
        except Exception:
            raise ValueError("bundle enumeration cannot be read") from None
        return tuple(sorted(files))


def _close_handles(api: _WindowsApi, handles: tuple[int, ...]) -> bool:
    """Close every supplied transient handle and report any close failure."""
    failed = False
    for handle in handles:
        if not handle:
            continue
        try:
            failed = not bool(api.kernel32.CloseHandle(handle)) or failed
        except Exception:
            failed = True
    return failed


def _open_child(api: _WindowsApi, parent: int, name: str, *, directory: bool) -> int:
    buffer = ctypes.create_unicode_buffer(name)
    encoded_length = len(name.encode("utf-16-le"))
    unicode = _UnicodeString(
        encoded_length,
        encoded_length + ctypes.sizeof(ctypes.c_wchar),
        ctypes.cast(buffer, wintypes.LPWSTR),
    )
    attributes = _ObjectAttributes(
        ctypes.sizeof(_ObjectAttributes),
        parent,
        ctypes.pointer(unicode),
        0x40,
        None,
        None,
    )
    status = _IoStatusBlock()
    handle = wintypes.HANDLE()
    options = (
        FILE_OPEN_REPARSE_POINT
        | FILE_SYNCHRONOUS_IO_NONALERT
        | (FILE_DIRECTORY_FILE if directory else FILE_NON_DIRECTORY_FILE)
    )
    result = api.ntdll.NtCreateFile(
        ctypes.byref(handle),
        GENERIC_READ | SYNCHRONIZE,
        ctypes.byref(attributes),
        ctypes.byref(status),
        None,
        0,
        FILE_SHARE_ALL,
        FILE_OPEN,
        options,
        None,
        0,
    )
    if result != 0 or status.Status != 0 or not handle.value:
        raise OSError
    try:
        attributes_value = _metadata_attributes(api, handle.value)
        valid = bool(attributes_value & FILE_ATTRIBUTE_DIRECTORY) == directory
        valid = valid and not bool(attributes_value & FILE_ATTRIBUTE_REPARSE_POINT)
        if not directory:
            valid = valid and _is_disk_file(api, handle.value)
    except Exception:
        _close_handles(api, (handle.value,))
        raise OSError from None
    if not valid:
        _close_handles(api, (handle.value,))
        raise OSError
    return handle.value


def _metadata_attributes(api: _WindowsApi, handle: int) -> int:
    info = _ByHandleInfo()
    try:
        succeeded = api.kernel32.GetFileInformationByHandle(handle, ctypes.byref(info))
    except Exception:
        raise OSError from None
    if not succeeded:
        raise OSError
    return int(info.attributes)


def _is_reparse(api: _WindowsApi, handle: int) -> bool:
    return bool(_metadata_attributes(api, handle) & FILE_ATTRIBUTE_REPARSE_POINT)


def _is_directory(api: _WindowsApi, handle: int) -> bool:
    attributes_value = _metadata_attributes(api, handle)
    return bool(attributes_value & FILE_ATTRIBUTE_DIRECTORY) and not bool(
        attributes_value & FILE_ATTRIBUTE_REPARSE_POINT
    )


def _is_disk_file(api: _WindowsApi, handle: int) -> bool:
    return api.kernel32.GetFileType(handle) == FILE_TYPE_DISK


def _read_handle(api: _WindowsApi, handle: int, maximum: int) -> bytes:
    chunks = bytearray()
    while True:
        remaining = maximum + 1 - len(chunks)
        if remaining <= 0:
            raise ValueError("document exceeds maximum size")
        buffer = ctypes.create_string_buffer(min(64 * 1024, remaining))
        count = wintypes.DWORD()
        if not api.kernel32.ReadFile(
            handle, buffer, len(buffer), ctypes.byref(count), None
        ):
            if ctypes.get_last_error() == 38:  # EOF
                return bytes(chunks)
            raise OSError
        if not count.value:
            return bytes(chunks)
        chunks.extend(buffer.raw[: count.value])


def _directory_entries(api: _WindowsApi, handle: int) -> Iterator[tuple[str, int]]:
    """Yield validated FILE_DIRECTORY_INFORMATION records one native buffer at a time."""
    query = getattr(api.ntdll, "NtQueryDirectoryFile", None)
    if query is None:
        raise OSError
    buffer = ctypes.create_string_buffer(64 * 1024)
    status = _IoStatusBlock()
    restart = True
    no_more_files = {0x80000006, -2147483642}
    while True:
        result = query(
            handle,
            None,
            None,
            None,
            ctypes.byref(status),
            buffer,
            len(buffer),
            1,
            False,
            None,
            restart,
        )
        restart = False
        used = int(status.Information)
        if result in no_more_files:
            if status.Status not in no_more_files or used != 0:
                raise OSError
            return
        if result != 0 or status.Status != 0 or used <= 0 or used > len(buffer):
            raise OSError
        raw = buffer.raw
        offset = 0
        while offset < used:
            if offset % 8 or used - offset < 64:
                raise OSError
            next_offset = int.from_bytes(raw[offset : offset + 4], "little")
            attributes = int.from_bytes(raw[offset + 56 : offset + 60], "little")
            length = int.from_bytes(raw[offset + 60 : offset + 64], "little")
            record_end = offset + 64 + length
            if not length or length % 2 or record_end > used:
                raise OSError
            try:
                name = raw[offset + 64 : record_end].decode("utf-16-le", "strict")
            except UnicodeDecodeError as error:
                raise OSError from error
            if not name or any(part in name for part in ("\\", "/", chr(0))):
                raise OSError
            yield name, attributes
            if next_offset == 0:
                padding = raw[record_end:used]
                if len(padding) >= 8 or any(padding):
                    raise OSError
                offset = used
            elif (
                next_offset < 64 + length
                or next_offset % 8
                or offset + next_offset > used
            ):
                raise OSError
            else:
                offset += next_offset
