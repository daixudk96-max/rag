"""Native Windows rooted-open ABI contracts, runnable with mocked wrappers."""

from __future__ import annotations

import ctypes
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from llamaindex_runtime.okf import _rooted_windows as backend


class _Handles:
    def __init__(self, *, root: int = 21) -> None:
        self.root = root
        self.closed: list[int] = []
        self.create_calls: list[tuple[object, ...]] = []

    def CreateFileW(self, *args: object) -> int:
        self.create_calls.append(args)
        return self.root

    def CloseHandle(self, handle: int) -> bool:
        self.closed.append(handle)
        return True

    def GetFileType(self, handle: int) -> int:
        return backend.FILE_TYPE_DISK


def _successful_create(handle: Any, *_: Any) -> int:
    handle._obj.value = 42
    return 0


def test_native_structures_use_pointer_width_and_signed_ntstatus() -> None:
    assert ctypes.sizeof(backend._IoStatusBlock) >= ctypes.sizeof(ctypes.c_size_t) * 2
    assert backend._IoStatusBlock._fields_[0][1] is wintypes.LONG
    assert (
        ctypes.sizeof(backend._ObjectAttributes) >= ctypes.sizeof(ctypes.c_void_p) * 3
    )


def test_module_imports_when_ctypes_has_no_windll() -> None:
    script = """
import ctypes
import importlib
import sys
sys.modules.pop('llamaindex_runtime.okf._rooted_windows', None)
delattr(ctypes, 'WinDLL')
module = importlib.import_module('llamaindex_runtime.okf._rooted_windows')
assert module._load_native_api() is None
"""
    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr


def test_native_loader_configures_windows_bool_abi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Function:
        pass

    kernel32 = SimpleNamespace(
        CreateFileW=Function(),
        CloseHandle=Function(),
        GetFileInformationByHandle=Function(),
        GetFileType=Function(),
        ReadFile=Function(),
    )
    ntdll = SimpleNamespace(NtCreateFile=Function())
    calls: list[str] = []

    def loader(name: str, *, use_last_error: bool) -> SimpleNamespace:
        assert use_last_error
        calls.append(name)
        return {"kernel32": kernel32, "ntdll": ntdll}[name]

    monkeypatch.setattr(ctypes, "WinDLL", loader, raising=False)

    api = backend._load_native_api()

    assert api is not None
    assert calls == ["kernel32", "ntdll"]
    assert kernel32.CloseHandle.restype is wintypes.BOOL
    assert ntdll.NtCreateFile.restype is wintypes.LONG


def test_root_junction_is_rejected_and_handle_is_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handles = _Handles()
    api = backend._WindowsApi(handles, SimpleNamespace())
    monkeypatch.setattr(backend, "_load_native_api", lambda: api)
    monkeypatch.setattr(backend, "_is_directory", lambda _api, _handle: False)

    with pytest.raises(ValueError, match="^bundle root cannot be read$"):
        backend.WindowsBundleBackend.open_root(Path("C:/junction"))
    assert handles.closed == [21]


def test_root_open_uses_only_full_root_path_and_closes_idempotently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handles = _Handles()
    api = backend._WindowsApi(handles, SimpleNamespace())
    monkeypatch.setattr(backend, "_load_native_api", lambda: api)
    monkeypatch.setattr(backend, "_is_directory", lambda _api, handle: handle == 21)

    rooted = backend.WindowsBundleBackend.open_root(Path("C:/bundle"))
    rooted.close()
    rooted.close()

    assert handles.create_calls == [
        (
            "C:\\bundle",
            backend.GENERIC_READ,
            backend.FILE_SHARE_ALL,
            None,
            backend.OPEN_EXISTING,
            backend.FILE_FLAG_BACKUP_SEMANTICS | backend.FILE_FLAG_OPEN_REPARSE_POINT,
            None,
        )
    ]
    assert handles.closed == [21]


def test_child_open_uses_held_parent_and_reparse_protection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, int]] = []
    api = backend._WindowsApi(_Handles(), SimpleNamespace())

    def create(handle, _access, attributes, _status, *_args):  # type: ignore[no-untyped-def]
        calls.append((attributes._obj.RootDirectory, _args[4]))
        handle._obj.value = 42
        return 0

    monkeypatch.setattr(api.ntdll, "NtCreateFile", create, raising=False)
    monkeypatch.setattr(
        backend,
        "_metadata_attributes",
        lambda _api, _: backend.FILE_ATTRIBUTE_DIRECTORY,
    )

    assert backend._open_child(api, 17, "nested", directory=True) == 42
    parent, options = calls.pop()
    assert parent == 17
    assert options & backend.FILE_OPEN_REPARSE_POINT
    assert options & backend.FILE_DIRECTORY_FILE


@pytest.mark.parametrize("attributes", (backend.FILE_ATTRIBUTE_REPARSE_POINT, 0))
def test_nested_junction_or_directory_type_mismatch_closes_rejected_handle(
    monkeypatch: pytest.MonkeyPatch, attributes: int
) -> None:
    handles = _Handles()
    api = backend._WindowsApi(handles, SimpleNamespace())
    monkeypatch.setattr(
        api.ntdll,
        "NtCreateFile",
        _successful_create,
        raising=False,
    )
    monkeypatch.setattr(backend, "_is_reparse", lambda _api, _: attributes != 0)
    monkeypatch.setattr(backend, "_is_directory", lambda _api, _: False)

    with pytest.raises(OSError):
        backend._open_child(api, 17, "external-marker.md", directory=True)
    assert handles.closed == [42]


def test_leaf_rejects_non_disk_handle_and_closes_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handles = _Handles()
    api = backend._WindowsApi(handles, SimpleNamespace())
    monkeypatch.setattr(
        api.ntdll,
        "NtCreateFile",
        _successful_create,
        raising=False,
    )
    monkeypatch.setattr(backend, "_is_reparse", lambda _api, _: False)
    monkeypatch.setattr(backend, "_is_directory", lambda _api, _: False)
    monkeypatch.setattr(backend, "_is_disk_file", lambda _api, _: False)

    with pytest.raises(OSError):
        backend._open_child(api, 17, "pipe", directory=False)
    assert handles.closed == [42]


def test_descendant_walk_uses_only_held_handles_and_closes_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handles = _Handles()
    api = backend._WindowsApi(handles, SimpleNamespace())
    calls: list[tuple[int, str, bool]] = []
    monkeypatch.setattr(
        backend,
        "_read_handle",
        lambda _api, handle, _: b"safe" if handle == 25 else b"",
    )

    def child(
        _api: backend._WindowsApi, parent: int, name: str, *, directory: bool
    ) -> int:
        calls.append((parent, name, directory))
        return 22 + len(calls)

    monkeypatch.setattr(backend, "_open_child", child)
    assert (
        backend.WindowsBundleBackend(21, api).read_bytes(
            ("raw", "nested", "safe.md"), 64
        )
        == b"safe"
    )
    assert calls == [(21, "raw", True), (23, "nested", True), (24, "safe.md", False)]
    assert handles.closed == [25, 24, 23]


def test_failed_ntstatus_never_falls_back_to_a_descendant_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = backend._WindowsApi(_Handles(), SimpleNamespace())
    monkeypatch.setattr(api.ntdll, "NtCreateFile", lambda *_: -1, raising=False)
    monkeypatch.setattr(backend, "_is_reparse", lambda _api, _: False)
    with pytest.raises(OSError):
        backend._open_child(api, 17, "external-marker.md", directory=False)


def test_native_backend_unavailable_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(backend, "_load_native_api", lambda: None)
    with pytest.raises(ValueError, match="^bundle root cannot be read$"):
        backend.WindowsBundleBackend.open_root(Path("C:/bundle"))


@pytest.mark.parametrize("failed_handle", (23, 22))
def test_read_cleanup_attempts_every_transient_handle_when_close_fails(
    monkeypatch: pytest.MonkeyPatch, failed_handle: int
) -> None:
    handles = _Handles()
    api = backend._WindowsApi(handles, SimpleNamespace())
    monkeypatch.setattr(
        backend,
        "_open_child",
        lambda _api, _parent, _name, *, directory: 22 if directory else 23,
    )
    monkeypatch.setattr(backend, "_read_handle", lambda *_: b"safe")

    def close(handle: int) -> int:
        handles.closed.append(handle)
        return int(handle != failed_handle)

    monkeypatch.setattr(handles, "CloseHandle", close)

    with pytest.raises(ValueError, match="^document cannot be read$"):
        backend.WindowsBundleBackend(21, api).read_bytes(("nested", "safe.md"), 64)
    assert handles.closed == [23, 22]


@pytest.mark.parametrize(
    ("failure", "message"),
    ((OSError(), "document cannot be read"), (ValueError("wrong type"), "wrong type")),
)
def test_read_primary_error_is_not_masked_by_cleanup_failure(
    monkeypatch: pytest.MonkeyPatch, failure: Exception, message: str
) -> None:
    handles = _Handles()
    api = backend._WindowsApi(handles, SimpleNamespace())
    monkeypatch.setattr(
        backend,
        "_open_child",
        lambda _api, _parent, _name, *, directory: 22,
    )
    monkeypatch.setattr(
        backend, "_read_handle", lambda *_: (_ for _ in ()).throw(failure)
    )

    def close(handle: int) -> int:
        handles.closed.append(handle)
        return 0

    monkeypatch.setattr(handles, "CloseHandle", close)

    with pytest.raises(ValueError, match=f"^{message}$"):
        backend.WindowsBundleBackend(21, api).read_bytes(("safe.md",), 64)
    assert handles.closed == [22]


def test_root_close_failure_clears_handle_and_is_idempotent() -> None:
    handles = _Handles()
    api = backend._WindowsApi(handles, SimpleNamespace())
    rooted = backend.WindowsBundleBackend(21, api)
    monkeypatch = pytest.MonkeyPatch()

    def close(handle: int) -> int:
        handles.closed.append(handle)
        return 0

    monkeypatch.setattr(handles, "CloseHandle", close)
    try:
        with pytest.raises(ValueError, match="^bundle root cannot be read$"):
            rooted.close()
        rooted.close()
    finally:
        monkeypatch.undo()

    assert handles.closed == [21]


def test_close_handle_bool_result_is_interpreted_as_windows_bool() -> None:
    handles = _Handles()
    api = backend._WindowsApi(handles, SimpleNamespace())
    rooted = backend.WindowsBundleBackend(21, api)
    monkeypatch = pytest.MonkeyPatch()

    def close(handle: int) -> int:
        handles.closed.append(handle)
        return 1

    monkeypatch.setattr(handles, "CloseHandle", close)
    try:
        rooted.close()
    finally:
        monkeypatch.undo()

    assert handles.closed == [21]


def _directory_record(name: str, attributes: int, next_offset: int = 0) -> bytes:
    encoded = name.encode("utf-16-le")
    record = bytearray(64 + len(encoded))
    record[:4] = next_offset.to_bytes(4, "little")
    record[56:60] = attributes.to_bytes(4, "little")
    record[60:64] = len(encoded).to_bytes(4, "little")
    record[64:] = encoded
    return bytes(record)


def test_native_directory_query_streams_multiple_buffers_with_one_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _directory_record("nested", backend.FILE_ATTRIBUTE_DIRECTORY)
    second = _directory_record("safe.md", 0)
    responses = iter((first, second, None))
    restarts: list[bool] = []

    def query(
        _handle: int,
        _event: object,
        _apc: object,
        _context: object,
        status: object,
        buffer: object,
        _length: int,
        _information_class: int,
        _single_entry: bool,
        _file_name: object,
        restart: bool,
    ) -> int:
        restarts.append(restart)
        payload = next(responses)
        if payload is None:
            status._obj.Status = -2147483642  # type: ignore[attr-defined]
            status._obj.Information = 0  # type: ignore[attr-defined]
            return -2147483642
        status._obj.Status = 0  # type: ignore[attr-defined]
        status._obj.Information = len(payload)  # type: ignore[attr-defined]
        ctypes.memmove(buffer, payload, len(payload))
        return 0

    api = backend._WindowsApi(_Handles(), SimpleNamespace(NtQueryDirectoryFile=query))

    assert list(backend._directory_entries(api, 17)) == [
        ("nested", backend.FILE_ATTRIBUTE_DIRECTORY),
        ("safe.md", 0),
    ]
    assert restarts == [True, False, False]


@pytest.mark.parametrize(
    "payload,status_information",
    (
        (b"x" * 63, 63),
        (_directory_record("bad", 0, 65), 70),
        (_directory_record("bad", 0), 65),
    ),
)
def test_native_directory_query_rejects_invalid_headers_offsets_and_status(
    payload: bytes, status_information: int
) -> None:
    calls = 0

    def query(*args: object) -> int:
        nonlocal calls
        calls += 1
        status = args[4]
        buffer = args[5]
        status._obj.Status = 0  # type: ignore[attr-defined]
        status._obj.Information = status_information  # type: ignore[attr-defined]
        ctypes.memmove(buffer, payload, min(len(payload), status_information))
        return 0

    api = backend._WindowsApi(_Handles(), SimpleNamespace(NtQueryDirectoryFile=query))

    with pytest.raises(OSError):
        list(backend._directory_entries(api, 17))
    assert calls == 1


def test_windows_enumeration_is_depth_first_and_cleanup_failure_is_fatal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handles = _Handles()
    api = backend._WindowsApi(handles, SimpleNamespace())
    entries = {
        21: iter((("nested", backend.FILE_ATTRIBUTE_DIRECTORY), ("top.md", 0))),
        22: iter((("deep.md", 0),)),
    }
    calls: list[tuple[int, str, bool]] = []

    monkeypatch.setattr(
        backend,
        "_directory_entries",
        lambda _api, handle: entries[handle],
    )

    def child(
        _api: backend._WindowsApi, parent: int, name: str, *, directory: bool
    ) -> int:
        calls.append((parent, name, directory))
        return {"nested": 22, "deep.md": 23, "top.md": 24}[name]

    monkeypatch.setattr(backend, "_open_child", child)
    assert backend.WindowsBundleBackend(21, api).enumerate_regular_files(
        maximum_files=2, maximum_entries=3, maximum_depth=2
    ) == (("nested", "deep.md"), ("top.md",))
    assert calls == [
        (21, "nested", True),
        (22, "deep.md", False),
        (21, "top.md", False),
    ]
    assert handles.closed == [23, 22, 24]

    def close(handle: int) -> int:
        handles.closed.append(handle)
        return int(handle != 23)

    monkeypatch.setattr(handles, "CloseHandle", close)
    entries[21] = iter((("nested", backend.FILE_ATTRIBUTE_DIRECTORY),))
    entries[22] = iter((("deep.md", 0),))
    with pytest.raises(ValueError, match="^bundle enumeration cannot be read$"):
        backend.WindowsBundleBackend(21, api).enumerate_regular_files(
            maximum_files=2, maximum_entries=3, maximum_depth=2
        )
