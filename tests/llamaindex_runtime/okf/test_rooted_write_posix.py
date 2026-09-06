"""Platform-independent fake-native tests for POSIX rooted publication."""

from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Any

import pytest

from llamaindex_runtime.okf import _rooted_write_posix as backend


def _record_event(events: list[tuple[str, object]], label: str, value: object) -> None:
    events.append((label, value))


def _record_event_result(
    events: list[tuple[str, object]], label: str, value: object, *, result: bool
) -> bool:
    _record_event(events, label, value)
    return result


def _record_replace(
    events: list[tuple[str, object]], _source: object, target: object, **_: Any
) -> None:
    _record_event(events, "replace", target)


def _record_int_result(values: list[int], value: int, *, result: bool) -> bool:
    values.append(value)
    return result


def _record_unlink(events: list[tuple[str, object]], fd: int, name: str) -> bool:
    _record_event(events, "unlink", (fd, name))
    return True


def _record_unlinked_name(unlinked: list[str], _fd: int, name: str) -> bool:
    unlinked.append(name)
    return True


def _record_raw_close(values: list[int], value: int) -> bool:
    values.append(value)
    return value == 11


def _record_open(
    calls: list[tuple[str, object]], _name: object, *_: Any, **kwargs: Any
) -> int:
    _record_event(calls, "open", kwargs.get("dir_fd"))
    return 7


def _record_sync(calls: list[tuple[str, object]], fd: int) -> None:
    _record_event(calls, "sync", fd)


def _record_close(calls: list[tuple[str, object]], fd: int) -> None:
    _record_event(calls, "close", fd)


def test_posix_replaces_members_manifest_last_with_required_directory_syncs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, object]] = []
    monkeypatch.setattr(backend, "_open_root", lambda _: 10)
    monkeypatch.setattr(backend, "_open_raw", lambda _: (11, True))
    monkeypatch.setattr(backend, "_stage", lambda _fd, label, _payload: f".{label}.tmp")
    monkeypatch.setattr(backend, "_cleanup", lambda *_: False)
    monkeypatch.setattr(
        backend, "_close", partial(_record_event_result, events, "close", result=False)
    )
    monkeypatch.setattr(backend, "_sync", partial(_record_event, events, "sync"))
    monkeypatch.setattr(backend.os, "replace", partial(_record_replace, events))

    backend.publish(
        Path("root"), ("a.md", "a.spans.json", "a.pair.json"), (b"a", b"b", b"c")
    )

    assert events == [
        ("replace", "a.md"),
        ("replace", "a.spans.json"),
        ("sync", 11),
        ("replace", "a.pair.json"),
        ("sync", 11),
        ("sync", 10),
        ("close", 11),
        ("close", 10),
    ]


@pytest.mark.parametrize("failed_label", ("sidecar", "manifest"))
def test_posix_stage_failure_cleans_every_previously_staged_temp(
    monkeypatch: pytest.MonkeyPatch, failed_label: str
) -> None:
    events: list[tuple[str, object]] = []
    primary = RuntimeError("C:/secret/path/$TOKEN")
    monkeypatch.setattr(backend, "_open_root", lambda _: 10)
    monkeypatch.setattr(backend, "_open_raw", lambda _: (11, False))

    def stage(_fd: int, label: str, _payload: bytes) -> str:
        if label == failed_label:
            raise primary
        return f".{label}.tmp"

    monkeypatch.setattr(backend, "_stage", stage)
    monkeypatch.setattr(
        backend,
        "_unlink",
        partial(_record_unlink, events),
    )
    monkeypatch.setattr(
        backend, "_close", partial(_record_event_result, events, "close", result=False)
    )

    with pytest.raises(RuntimeError) as raised:
        backend.publish(Path("root"), ("a", "b", "c"), (b"a", b"b", b"c"))

    assert raised.value is primary
    expected = [".markdown.tmp"]
    if failed_label == "manifest":
        expected.append(".sidecar.tmp")
    unlink_payloads = [
        payload
        for event, payload in events
        if event == "unlink" and isinstance(payload, tuple)
    ]
    assert [payload[1] for payload in unlink_payloads] == expected
    assert [event for event in events if event[0] == "close"] == [
        ("close", 11),
        ("close", 10),
    ]


def test_posix_close_attempts_root_after_raw_close_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[int] = []
    monkeypatch.setattr(backend, "_open_root", lambda _: 10)
    monkeypatch.setattr(backend, "_open_raw", lambda _: (11, False))
    monkeypatch.setattr(backend, "_stage", lambda _fd, label, _payload: f".{label}.tmp")
    monkeypatch.setattr(backend, "_replace_members", lambda *_: None)
    monkeypatch.setattr(backend, "_cleanup", lambda *_: False)
    monkeypatch.setattr(backend, "_close", partial(_record_raw_close, attempts))

    with pytest.raises(OSError, match="^publication cleanup failed$"):
        backend.publish(Path("root"), ("a", "b", "c"), (b"a", b"b", b"c"))

    assert attempts == [11, 10]


def test_posix_close_failures_do_not_mask_primary_and_both_are_attempted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[int] = []
    primary = RuntimeError("primary")
    monkeypatch.setattr(backend, "_open_root", lambda _: 10)
    monkeypatch.setattr(backend, "_open_raw", lambda _: (11, False))
    monkeypatch.setattr(backend, "_stage", lambda *_: (_ for _ in ()).throw(primary))
    monkeypatch.setattr(
        backend, "_close", partial(_record_int_result, attempts, result=True)
    )

    with pytest.raises(RuntimeError) as raised:
        backend.publish(Path("root"), ("a", "b", "c"), (b"a", b"b", b"c"))

    assert raised.value is primary
    assert attempts == [11, 10]


def test_posix_cleanup_error_cannot_replace_primary_base_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary = KeyboardInterrupt()
    monkeypatch.setattr(backend, "_open_root", lambda _: 10)
    monkeypatch.setattr(backend, "_open_raw", lambda _: (11, False))
    monkeypatch.setattr(backend, "_stage", lambda *_: (_ for _ in ()).throw(primary))
    monkeypatch.setattr(backend, "_cleanup", lambda *_: True)
    monkeypatch.setattr(backend, "_close", lambda _: True)

    with pytest.raises(KeyboardInterrupt) as raised:
        backend.publish(Path("root"), ("a", "b", "c"), (b"a", b"b", b"c"))

    assert raised.value is primary


def test_posix_cleanup_or_close_failure_after_success_is_public_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(backend, "_open_root", lambda _: 10)
    monkeypatch.setattr(backend, "_open_raw", lambda _: (11, False))
    monkeypatch.setattr(backend, "_stage", lambda _fd, label, _payload: f".{label}.tmp")
    monkeypatch.setattr(backend, "_replace_members", lambda *_: None)
    monkeypatch.setattr(backend, "_cleanup", lambda *_: True)
    monkeypatch.setattr(backend, "_close", lambda _: False)

    with pytest.raises(OSError, match="publication cleanup failed"):
        backend.publish(Path("root"), ("a", "b", "c"), (b"a", b"b", b"c"))


def test_posix_write_all_loops_and_rejects_zero_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writes = iter((2, 1))
    monkeypatch.setattr(backend.os, "write", lambda *_: next(writes))
    backend._write_all(4, b"abc")
    monkeypatch.setattr(backend.os, "write", lambda *_: 0)

    with pytest.raises(OSError, match="short write"):
        backend._write_all(4, b"x")


def test_posix_stage_and_open_raw_use_only_held_directory_descriptors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(backend.secrets, "token_hex", lambda _: "token")
    monkeypatch.setattr(backend, "_stage_flags", lambda: 1)
    monkeypatch.setattr(backend.os, "open", partial(_record_open, calls))
    monkeypatch.setattr(backend.os, "write", lambda _fd, view: len(view))
    monkeypatch.setattr(backend.os, "fsync", partial(_record_sync, calls))
    monkeypatch.setattr(backend.os, "close", partial(_record_close, calls))

    assert backend._stage(5, "markdown", b"abc") == ".markdown.token.tmp"
    assert calls == [("open", 5), ("sync", 7), ("close", 7)]


def test_posix_stage_collision_limit_and_failure_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(backend.secrets, "token_hex", lambda _: "token")
    monkeypatch.setattr(backend, "_stage_flags", lambda: 1)
    monkeypatch.setattr(
        backend.os,
        "open",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(FileExistsError()),
    )
    with pytest.raises(OSError, match="collision"):
        backend._stage(5, "markdown", b"abc")

    unlinked: list[str] = []
    monkeypatch.setattr(backend.os, "open", lambda *_args, **_kwargs: 7)
    monkeypatch.setattr(
        backend, "_write_all", lambda *_: (_ for _ in ()).throw(RuntimeError())
    )
    monkeypatch.setattr(backend, "_unlink", partial(_record_unlinked_name, unlinked))
    monkeypatch.setattr(backend, "_close", lambda _: False)
    with pytest.raises(RuntimeError):
        backend._stage(5, "markdown", b"abc")
    assert unlinked == [".markdown.token.tmp"]


def test_posix_open_raw_creation_and_helper_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def open_directory(*_: object) -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError(backend.errno.ENOENT, "missing")
        return 9

    monkeypatch.setattr(backend, "_open_directory", open_directory)
    monkeypatch.setattr(backend.os, "mkdir", lambda name, mode, *, dir_fd: None)
    assert backend._open_raw(5) == (9, True)

    monkeypatch.setattr(
        backend,
        "_open_directory",
        lambda *_: (_ for _ in ()).throw(OSError(backend.errno.EACCES, "denied")),
    )
    with pytest.raises(OSError):
        backend._open_raw(5)

    monkeypatch.setattr(
        backend.os, "unlink", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError())
    )
    monkeypatch.setattr(
        backend.os, "close", lambda *_: (_ for _ in ()).throw(OSError())
    )
    assert not backend._unlink(5, "temp")
    assert backend._close(5)


@pytest.mark.parametrize("name", ("O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC"))
def test_posix_directory_flags_require_nonzero_native_constants(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setattr(backend.os, name, 0, raising=False)
    with pytest.raises(OSError, match="required flag"):
        backend._directory_flags()
