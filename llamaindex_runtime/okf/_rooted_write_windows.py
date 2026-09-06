"""Windows Native-API capability-rooted raw-pair writer.

The only complete pathname accepted by this module opens the bundle authority.
Every descendant is created/opened relative to a held handle; unsupported native
operations fail closed rather than reverting to path-based I/O.
"""

from __future__ import annotations

import ctypes
import secrets
from ctypes import wintypes
from pathlib import Path

from . import _rooted_windows as native

FILE_ATTRIBUTE_DIRECTORY = 0x10
FILE_ATTRIBUTE_NORMAL = 0x80
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
FILE_CREATE = 2
FILE_OPEN = 1
FILE_OPEN_IF = 3
FILE_DIRECTORY_FILE = 0x1
FILE_NON_DIRECTORY_FILE = 0x40
FILE_OPEN_REPARSE_POINT = 0x00200000
FILE_SYNCHRONOUS_IO_NONALERT = 0x20
FILE_WRITE_DATA = 0x2
FILE_READ_ATTRIBUTES = 0x80
FILE_WRITE_ATTRIBUTES = 0x100
FILE_ADD_FILE = 0x2
FILE_ADD_SUBDIRECTORY = 0x4
DELETE = 0x10000
SYNCHRONIZE = 0x100000
FILE_SHARE_ALL = 7
FILE_RENAME_INFO_CLASS = 10
FILE_DISPOSITION_INFO_CLASS = 4
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
STATUS_OBJECT_NAME_COLLISION = -1073741771


class _RenameHeader(ctypes.Structure):
    _fields_ = [
        ("ReplaceIfExists", wintypes.BOOL),
        ("RootDirectory", wintypes.HANDLE),
        ("FileNameLength", wintypes.DWORD),
    ]


class _Disposition(ctypes.Structure):
    _fields_ = [("DeleteFile", wintypes.BOOL)]


class _Api(native._WindowsApi):
    pass


def publish(
    root: Path, names: tuple[str, str, str], payloads: tuple[bytes, bytes, bytes]
) -> None:
    api = _load_api()
    root_handle = raw_handle = 0
    staged: list[tuple[int, str]] = []
    handles: list[int] = []
    primary: BaseException | None = None
    try:
        root_handle = _open_root(api, root)
        raw_handle = _open_or_create_raw(api, root_handle)
        for label, payload in zip(("markdown", "sidecar", "manifest"), payloads):
            handle, temporary = _stage(api, raw_handle, label, payload)
            handles.append(handle)
            staged.append((handle, temporary))
        _replace_members(api, raw_handle, staged, names)
        staged.clear()
    except BaseException as error:
        primary = error
        raise
    finally:
        disposal_failed = _dispose_all(api, staged)
        close_failed = _close_all(api, tuple(handles) + (raw_handle, root_handle))
        if primary is None and (disposal_failed or close_failed):
            raise OSError("publication cleanup failed")


def _replace_members(
    api: _Api, raw: int, staged: list[tuple[int, str]], names: tuple[str, str, str]
) -> None:
    for staged_file, final_name in zip(staged[:2], names[:2]):
        _rename(api, staged_file[0], raw, final_name)
        staged.remove(staged_file)
    _flush(api, raw)
    staged_file = staged[0]
    _rename(api, staged_file[0], raw, names[2])
    staged.remove(staged_file)
    _flush(api, raw)


def _load_api() -> _Api:
    api = native._load_native_api()
    if api is None:
        raise OSError("native capability unavailable")
    kernel = api.kernel32
    kernel.WriteFile.argtypes = [
        wintypes.HANDLE,
        wintypes.LPCVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPVOID,
    ]
    kernel.WriteFile.restype = wintypes.BOOL
    kernel.FlushFileBuffers.argtypes = [wintypes.HANDLE]
    kernel.FlushFileBuffers.restype = wintypes.BOOL
    kernel.SetFileInformationByHandle.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    kernel.SetFileInformationByHandle.restype = wintypes.BOOL
    api.ntdll.NtSetInformationFile.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(native._IoStatusBlock),
        wintypes.LPVOID,
        wintypes.ULONG,
        wintypes.ULONG,
    ]
    api.ntdll.NtSetInformationFile.restype = wintypes.LONG
    return api  # type: ignore[return-value]


def _open_root(api: _Api, root: Path) -> int:
    handle = api.kernel32.CreateFileW(
        str(root),
        GENERIC_READ_WRITE(),
        FILE_SHARE_ALL,
        None,
        native.OPEN_EXISTING,
        native.FILE_FLAG_BACKUP_SEMANTICS | native.FILE_FLAG_OPEN_REPARSE_POINT,
        None,
    )
    if handle == INVALID_HANDLE_VALUE or not native._is_directory(api, handle):
        _close_all(api, (handle,))
        raise OSError
    return handle


def GENERIC_READ_WRITE() -> int:
    return native.GENERIC_READ | 0x40000000


def _open_or_create_raw(api: _Api, root: int) -> int:
    handle = _open_child(api, root, "raw", directory=True, disposition=FILE_OPEN_IF)
    if native._is_reparse(api, handle) or not native._is_directory(api, handle):
        _close_all(api, (handle,))
        raise OSError
    return handle


def _open_child(
    api: _Api, parent: int, name: str, *, directory: bool, disposition: int
) -> int:
    buffer, unicode, attributes = _child_object_attributes(parent, name)
    status = native._IoStatusBlock()
    handle = wintypes.HANDLE()
    result = api.ntdll.NtCreateFile(
        ctypes.byref(handle),
        _child_access(directory),
        ctypes.byref(attributes),
        ctypes.byref(status),
        None,
        FILE_ATTRIBUTE_DIRECTORY if directory else FILE_ATTRIBUTE_NORMAL,
        FILE_SHARE_ALL,
        disposition,
        _child_options(directory),
        None,
        0,
    )
    _ = buffer, unicode
    if result < 0 or not handle.value:
        if result == STATUS_OBJECT_NAME_COLLISION:
            raise FileExistsError
        raise OSError
    if not _valid_child(api, handle.value, directory):
        _close_all(api, (handle.value,))
        raise OSError
    return handle.value


def _child_object_attributes(
    parent: int, name: str
) -> tuple[
    ctypes.Array[ctypes.c_wchar], native._UnicodeString, native._ObjectAttributes
]:
    buffer = ctypes.create_unicode_buffer(name)
    byte_length = len(name.encode("utf-16-le"))
    unicode = native._UnicodeString(
        byte_length,
        byte_length + ctypes.sizeof(ctypes.c_wchar),
        ctypes.cast(buffer, wintypes.LPWSTR),
    )
    attributes = native._ObjectAttributes(
        ctypes.sizeof(native._ObjectAttributes),
        parent,
        ctypes.pointer(unicode),
        0x40,
        None,
        None,
    )
    return buffer, unicode, attributes


def _child_access(directory: bool) -> int:
    if directory:
        return (
            FILE_ADD_FILE
            | FILE_ADD_SUBDIRECTORY
            | FILE_READ_ATTRIBUTES
            | FILE_WRITE_ATTRIBUTES
            | SYNCHRONIZE
        )
    return FILE_WRITE_DATA | FILE_READ_ATTRIBUTES | DELETE | SYNCHRONIZE


def _child_options(directory: bool) -> int:
    return (
        FILE_OPEN_REPARSE_POINT
        | FILE_SYNCHRONOUS_IO_NONALERT
        | (FILE_DIRECTORY_FILE if directory else FILE_NON_DIRECTORY_FILE)
    )


def _valid_child(api: _Api, handle: int, directory: bool) -> bool:
    if native._is_reparse(api, handle):
        return False
    return (
        native._is_directory(api, handle)
        if directory
        else native._is_disk_file(api, handle)
    )


def _stage(api: _Api, raw: int, label: str, payload: bytes) -> tuple[int, str]:
    for _ in range(32):
        name = f".{label}.{secrets.token_hex(16)}.tmp"
        try:
            handle = _open_child(
                api, raw, name, directory=False, disposition=FILE_CREATE
            )
        except FileExistsError:
            continue
        try:
            _write_all(api, handle, payload)
            _flush(api, handle)
            return handle, name
        except BaseException:
            _dispose(api, handle)
            _close_all(api, (handle,))
            raise
    raise OSError("temporary name collision limit reached")


def _write_all(api: _Api, handle: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        chunk = payload[offset : offset + 64 * 1024]
        written = wintypes.DWORD()
        buffer = ctypes.create_string_buffer(chunk)
        if (
            not api.kernel32.WriteFile(
                handle, buffer, len(chunk), ctypes.byref(written), None
            )
            or not written.value
        ):
            raise OSError
        offset += written.value


def _rename(api: _Api, handle: int, raw: int, final_name: str) -> None:
    encoded = final_name.encode("utf-16-le")
    name_offset = _RenameHeader.FileNameLength.offset + ctypes.sizeof(wintypes.DWORD)
    size = name_offset + len(encoded)
    buffer = ctypes.create_string_buffer(size)
    header = _RenameHeader.from_buffer(buffer)
    header.ReplaceIfExists = True
    header.RootDirectory = raw
    header.FileNameLength = len(encoded)
    ctypes.memmove(ctypes.addressof(buffer) + name_offset, encoded, len(encoded))
    status = native._IoStatusBlock()
    result = api.ntdll.NtSetInformationFile(
        handle, ctypes.byref(status), buffer, size, FILE_RENAME_INFO_CLASS
    )
    if result < 0:
        raise OSError


def _flush(api: _Api, handle: int) -> None:
    if not api.kernel32.FlushFileBuffers(handle):
        raise OSError("flush failed")


def _dispose_all(api: _Api, staged: list[tuple[int, str]]) -> bool:
    failed = False
    for handle, _ in staged:
        failed = not _dispose(api, handle) or failed
    return failed


def _dispose(api: _Api, handle: int) -> bool:
    try:
        info = _Disposition(True)
        return bool(
            api.kernel32.SetFileInformationByHandle(
                handle,
                FILE_DISPOSITION_INFO_CLASS,
                ctypes.byref(info),
                ctypes.sizeof(info),
            )
        )
    except BaseException:
        return False


def _close_all(api: _Api, handles: tuple[int, ...]) -> bool:
    return native._close_handles(api, handles)
