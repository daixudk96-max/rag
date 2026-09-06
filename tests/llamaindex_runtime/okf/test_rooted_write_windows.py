"""Windows rooted writer ABI and reparse fail-closed contracts."""

from __future__ import annotations

import ctypes
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from llamaindex_runtime.okf import _rooted_write_windows as backend


def _record_close(closed: list[int], handle: int) -> bool:
    closed.append(handle)
    return True


def test_windows_writer_rename_buffer_uses_pointer_width_root_and_utf16_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def rename(handle, status, information, length, information_class):
        captured["handle"] = handle
        captured["length"] = length
        captured["class"] = information_class
        header = backend._RenameHeader.from_buffer_copy(
            ctypes.string_at(information, length)
        )
        captured["root"] = header.RootDirectory
        captured["name_length"] = header.FileNameLength
        return 0

    api = SimpleNamespace(ntdll=SimpleNamespace(NtSetInformationFile=rename))
    backend._rename(cast(Any, api), 11, 22, "report.md")

    assert captured == {
        "handle": 11,
        "length": 20 + len("report.md".encode("utf-16-le")),
        "class": backend.FILE_RENAME_INFO_CLASS,
        "root": 22,
        "name_length": len("report.md".encode("utf-16-le")),
    }
    assert ctypes.sizeof(backend._RenameHeader) >= ctypes.sizeof(ctypes.c_void_p) * 2


def test_windows_writer_rejects_raw_reparse_and_closes_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[int] = []
    api = SimpleNamespace(
        kernel32=SimpleNamespace(
            CloseHandle=lambda handle: _record_close(closed, handle)
        )
    )
    monkeypatch.setattr(backend, "_open_child", lambda *_args, **_kwargs: 41)
    monkeypatch.setattr(backend.native, "_is_reparse", lambda *_: True)

    with pytest.raises(OSError):
        backend._open_or_create_raw(cast(Any, api), 21)

    assert closed == [41]


def test_windows_writer_has_no_path_based_descendant_publish_fallback() -> None:
    source = Path(backend.__file__).read_text(encoding="utf-8")
    assert "os.replace" not in source
    assert "DeleteFileW" not in source
    assert "NtCreateFile" in source
    assert "NtSetInformationFile" in source


def test_windows_writer_manifest_last_and_flushes_raw_before_and_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, object]] = []
    api = SimpleNamespace()
    monkeypatch.setattr(backend, "_load_api", lambda: api)
    monkeypatch.setattr(backend, "_open_root", lambda *_: 10)
    monkeypatch.setattr(backend, "_open_or_create_raw", lambda *_: 11)
    monkeypatch.setattr(
        backend, "_stage", lambda _api, _raw, label, _payload: (len(label), label)
    )
    monkeypatch.setattr(
        backend,
        "_rename",
        lambda _api, handle, _raw, name: events.append(("rename", name)),
    )
    monkeypatch.setattr(
        backend, "_flush", lambda _api, handle: events.append(("flush", handle))
    )
    monkeypatch.setattr(backend, "_dispose_all", lambda *_: False)
    monkeypatch.setattr(backend, "_close_all", lambda *_: False)

    backend.publish(
        Path("root"), ("a.md", "a.spans.json", "a.pair.json"), (b"a", b"b", b"c")
    )

    assert events == [
        ("rename", "a.md"),
        ("rename", "a.spans.json"),
        ("flush", 11),
        ("rename", "a.pair.json"),
        ("flush", 11),
    ]


def test_windows_writer_disposition_false_is_cleanup_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = SimpleNamespace(
        kernel32=SimpleNamespace(SetFileInformationByHandle=lambda *_: False)
    )

    assert not backend._dispose(cast(Any, api), 4)


def test_windows_writer_cleanup_cannot_mask_primary_base_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary = SystemExit(2)
    api = SimpleNamespace()
    monkeypatch.setattr(backend, "_load_api", lambda: api)
    monkeypatch.setattr(backend, "_open_root", lambda *_: 10)
    monkeypatch.setattr(backend, "_open_or_create_raw", lambda *_: 11)
    monkeypatch.setattr(backend, "_stage", lambda *_: (_ for _ in ()).throw(primary))
    monkeypatch.setattr(backend, "_dispose_all", lambda *_: True)
    monkeypatch.setattr(backend, "_close_all", lambda *_: True)

    with pytest.raises(SystemExit) as raised:
        backend.publish(Path("root"), ("a", "b", "c"), (b"a", b"b", b"c"))

    assert raised.value is primary
