"""POSIX rooted-open unit contracts, including Windows-host mock coverage."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from llamaindex_runtime.okf import _rooted_posix as backend


class _FakePosixOS:
    O_RDONLY = 1
    O_DIRECTORY = 2
    O_NOFOLLOW = 4
    O_CLOEXEC = 8
    O_NONBLOCK = 16

    def __init__(
        self, *, supported: bool = True, close_failures: frozenset[int] = frozenset()
    ) -> None:
        self.calls: list[tuple[object, int, int | None]] = []
        self.close_attempts: list[int] = []
        self.closed: list[int] = []
        self.close_failures = close_failures
        self.reads = iter((b"safe", b""))
        self.supports_dir_fd = {self.open} if supported else set()

    @staticmethod
    def fspath(value: object) -> str:
        return str(value)

    def open(self, path: object, flags: int, *, dir_fd: int | None = None) -> int:
        self.calls.append((path, flags, dir_fd))
        return (10, 11, 12)[len(self.calls) - 1]

    @staticmethod
    def fstat(descriptor: int) -> SimpleNamespace:
        modes = {10: 0o040000, 11: 0o040000, 12: 0o100000}
        return SimpleNamespace(st_mode=modes[descriptor])

    def read(self, _descriptor: int, _size: int) -> bytes:
        return next(self.reads)

    def close(self, descriptor: int) -> None:
        self.close_attempts.append(descriptor)
        if descriptor in self.close_failures:
            raise OSError
        self.closed.append(descriptor)


def test_missing_descriptor_capability_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakePosixOS(supported=False)
    monkeypatch.setattr(backend, "os", fake)
    monkeypatch.setattr(backend, "stat", SimpleNamespace(S_ISDIR=lambda _: True))

    with pytest.raises(ValueError, match="^bundle root cannot be read$"):
        backend.PosixBundleBackend.open_root(Path("bundle"))

    assert fake.calls == []


@pytest.mark.parametrize(
    "flag_name, flag_value, missing",
    [
        ("O_DIRECTORY", None, False),
        ("O_DIRECTORY", "directory", False),
        ("O_DIRECTORY", True, False),
        ("O_DIRECTORY", False, False),
        ("O_DIRECTORY", None, True),
        ("O_NOFOLLOW", None, False),
        ("O_NOFOLLOW", "nofollow", False),
        ("O_NOFOLLOW", True, False),
        ("O_NOFOLLOW", False, False),
        ("O_NOFOLLOW", None, True),
        ("O_CLOEXEC", None, False),
        ("O_CLOEXEC", "cloexec", False),
        ("O_CLOEXEC", True, False),
        ("O_CLOEXEC", False, False),
        ("O_CLOEXEC", None, True),
        ("O_NONBLOCK", None, False),
        ("O_NONBLOCK", "nonblock", False),
        ("O_NONBLOCK", True, False),
        ("O_NONBLOCK", False, False),
        ("O_NONBLOCK", None, True),
        ("O_DIRECTORY", 0, False),
        ("O_NOFOLLOW", 0, False),
        ("O_CLOEXEC", 0, False),
        ("O_NONBLOCK", 0, False),
    ],
)
def test_invalid_open_flag_capability_fails_closed_before_open(
    monkeypatch: pytest.MonkeyPatch,
    flag_name: str,
    flag_value: object,
    missing: bool,
) -> None:
    fake = _FakePosixOS()
    if missing:
        monkeypatch.delattr(_FakePosixOS, flag_name)
    else:
        monkeypatch.setattr(fake, flag_name, flag_value)
    monkeypatch.setattr(backend, "os", fake)

    with pytest.raises(ValueError) as error:
        backend.PosixBundleBackend.open_root(Path("bundle"))

    assert str(error.value) == "bundle root cannot be read"
    assert fake.calls == []


def test_readonly_zero_flag_is_valid_for_root_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakePosixOS()
    monkeypatch.setattr(fake, "O_RDONLY", 0)
    monkeypatch.setattr(backend, "os", fake)
    monkeypatch.setattr(backend, "stat", SimpleNamespace(S_ISDIR=lambda _: True))

    rooted = backend.PosixBundleBackend.open_root(Path("bundle"))
    rooted.close()

    assert fake.calls == [
        ("bundle", fake.O_DIRECTORY | fake.O_NOFOLLOW | fake.O_CLOEXEC, None)
    ]


@pytest.mark.parametrize("close_fails", [False, True])
def test_root_fstat_failure_closes_acquired_descriptor_and_maps_error(
    monkeypatch: pytest.MonkeyPatch, close_fails: bool
) -> None:
    fake = _FakePosixOS(close_failures=frozenset({10}) if close_fails else frozenset())
    monkeypatch.setattr(fake, "fstat", lambda _: (_ for _ in ()).throw(OSError()))
    monkeypatch.setattr(backend, "os", fake)

    with pytest.raises(ValueError) as error:
        backend.PosixBundleBackend.open_root(Path("bundle"))

    assert str(error.value) == "bundle root cannot be read"
    assert fake.close_attempts == [10]
    assert fake.closed == ([] if close_fails else [10])


def test_descriptor_walk_uses_held_parent_and_closes_each_fd_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakePosixOS()
    monkeypatch.setattr(backend, "os", fake)
    monkeypatch.setattr(
        backend,
        "stat",
        SimpleNamespace(
            S_ISDIR=lambda mode: mode == 0o040000, S_ISREG=lambda mode: mode == 0o100000
        ),
    )

    rooted = backend.PosixBundleBackend.open_root(Path("bundle"))
    assert rooted.read_bytes(("raw", "document.md"), 64) == b"safe"
    rooted.close()
    rooted.close()

    root, parent, leaf = fake.calls
    assert root == (
        "bundle",
        fake.O_RDONLY | fake.O_DIRECTORY | fake.O_NOFOLLOW | fake.O_CLOEXEC,
        None,
    )
    assert parent == ("raw", root[1], 10)
    assert leaf == (
        "document.md",
        fake.O_RDONLY | fake.O_NOFOLLOW | fake.O_NONBLOCK | fake.O_CLOEXEC,
        11,
    )
    assert fake.closed == [12, 11, 10]


@pytest.mark.parametrize("failing_descriptor", [12, 11])
def test_cleanup_attempts_every_transient_descriptor_after_close_error(
    monkeypatch: pytest.MonkeyPatch, failing_descriptor: int
) -> None:
    fake = _FakePosixOS(close_failures=frozenset({failing_descriptor}))
    monkeypatch.setattr(backend, "os", fake)
    monkeypatch.setattr(
        backend,
        "stat",
        SimpleNamespace(S_ISDIR=lambda _: True, S_ISREG=lambda _: True),
    )

    rooted = backend.PosixBundleBackend.open_root(Path("bundle"))
    with pytest.raises(ValueError) as error:
        rooted.read_bytes(("raw", "document.md"), 64)
    rooted.close()

    assert str(error.value) == "document cannot be read"
    assert fake.close_attempts == [12, 11, 10]
    assert fake.closed == [
        descriptor for descriptor in (12, 11) if descriptor != failing_descriptor
    ] + [10]


@pytest.mark.parametrize("failure_source", ["read", "open", "stat"])
def test_primary_descriptor_error_is_not_masked_by_cleanup_error(
    monkeypatch: pytest.MonkeyPatch, failure_source: str
) -> None:
    fake = _FakePosixOS(close_failures=frozenset({11, 12}))
    if failure_source == "read":
        monkeypatch.setattr(fake, "read", lambda *_: (_ for _ in ()).throw(OSError()))
    elif failure_source == "open":
        original_open = fake.open

        def failing_open(path: object, flags: int, *, dir_fd: int | None = None) -> int:
            if path == "document.md":
                raise OSError
            return original_open(path, flags, dir_fd=dir_fd)

        monkeypatch.setattr(fake, "open", failing_open)
        fake.supports_dir_fd = {failing_open}
    else:
        original_fstat = fake.fstat
        monkeypatch.setattr(
            fake,
            "fstat",
            lambda descriptor: (
                (_ for _ in ()).throw(OSError())
                if descriptor == 12
                else original_fstat(descriptor)
            ),
        )
    monkeypatch.setattr(backend, "os", fake)
    monkeypatch.setattr(
        backend,
        "stat",
        SimpleNamespace(S_ISDIR=lambda _: True, S_ISREG=lambda _: True),
    )

    rooted = backend.PosixBundleBackend.open_root(Path("bundle"))
    with pytest.raises(ValueError) as error:
        rooted.read_bytes(("raw", "document.md"), 64)

    assert str(error.value) == "document cannot be read"


def test_successful_read_with_cleanup_error_is_not_returned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakePosixOS(close_failures=frozenset({12}))
    monkeypatch.setattr(backend, "os", fake)
    monkeypatch.setattr(
        backend,
        "stat",
        SimpleNamespace(S_ISDIR=lambda _: True, S_ISREG=lambda _: True),
    )

    rooted = backend.PosixBundleBackend.open_root(Path("bundle"))
    with pytest.raises(ValueError) as error:
        rooted.read_bytes(("raw", "document.md"), 64)

    assert str(error.value) == "document cannot be read"
    assert fake.close_attempts == [12, 11]


def test_root_close_maps_os_error_and_remains_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakePosixOS(close_failures=frozenset({10}))
    monkeypatch.setattr(backend, "os", fake)
    monkeypatch.setattr(backend, "stat", SimpleNamespace(S_ISDIR=lambda _: True))

    rooted = backend.PosixBundleBackend.open_root(Path("bundle"))
    with pytest.raises(ValueError) as error:
        rooted.close()
    rooted.close()

    assert str(error.value) == "bundle root cannot be read"
    assert fake.close_attempts == [10]


def test_bounded_read_collects_short_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    chunks = iter((b"ab", b"c", b""))
    monkeypatch.setattr(backend.os, "read", lambda *_: next(chunks))
    assert backend._bounded_read(7, 3) == b"abc"


def test_bounded_read_rejects_growing_input(monkeypatch: pytest.MonkeyPatch) -> None:
    chunks = iter((b"ab", b"cd"))
    monkeypatch.setattr(backend.os, "read", lambda *_: next(chunks))
    with pytest.raises(ValueError, match="^document exceeds maximum size$"):
        backend._bounded_read(7, 3)


class _DirectoryEntry:
    def __init__(self, name: str) -> None:
        self.name = name


class _StreamingScan:
    def __init__(
        self,
        owner: "_StreamingEnumerationOS",
        descriptor: int,
        descriptors: tuple[str, ...],
    ) -> None:
        self._owner = owner
        self._descriptor = descriptor
        self._entries = iter(descriptors)

    def __enter__(self) -> "_StreamingScan":
        self._owner.scans_open += 1
        self._owner.maximum_scans_open = max(
            self._owner.maximum_scans_open, self._owner.scans_open
        )
        return self

    def __exit__(self, *_: object) -> None:
        self._owner.scans_open -= 1
        self._owner.close(self._descriptor)

    def __iter__(self) -> "_StreamingScan":
        return self

    def __next__(self) -> _DirectoryEntry:
        name = next(self._entries)
        self._owner.entries_yielded += 1
        return _DirectoryEntry(name)


class _StreamingEnumerationOS:
    O_RDONLY = 1
    O_DIRECTORY = 2
    O_NOFOLLOW = 4
    O_CLOEXEC = 8
    O_NONBLOCK = 16

    def __init__(self, *, close_failures: frozenset[int] = frozenset()) -> None:
        self.close_failures = close_failures
        self.closed: list[int] = []
        self.close_attempts: list[int] = []
        self.entries_yielded = 0
        self.scans_open = 0
        self.maximum_scans_open = 0
        self._children = {
            (2, "nested"): 3,
            (2, "top.txt"): 4,
            (3, "deep.txt"): 5,
        }
        self._modes = {2: 0o040000, 3: 0o040000, 4: 0o100000, 5: 0o100000}
        self._directories = {2: ("nested", "top.txt"), 3: ("deep.txt",)}
        self._scan_sources = {6: 2, 7: 3}
        self._modes = {2: 0o040000, 3: 0o040000, 4: 0o100000, 5: 0o100000}

    def dup(self, descriptor: int) -> int:
        if descriptor == 1:
            return 2
        return {2: 6, 3: 7}[descriptor]

    def scandir(self, descriptor: int) -> _StreamingScan:
        source = self._scan_sources[descriptor]
        return _StreamingScan(self, descriptor, self._directories[source])

    def open(self, name: str, _flags: int, *, dir_fd: int) -> int:
        return self._children[(dir_fd, name)]

    def fstat(self, descriptor: int) -> SimpleNamespace:
        return SimpleNamespace(st_mode=self._modes[descriptor])

    def close(self, descriptor: int) -> None:
        self.close_attempts.append(descriptor)
        if descriptor in self.close_failures:
            raise OSError
        self.closed.append(descriptor)


def test_enumeration_streams_nested_directories_with_only_active_dfs_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _StreamingEnumerationOS()
    monkeypatch.setattr(backend, "os", fake)
    monkeypatch.setattr(
        backend,
        "stat",
        SimpleNamespace(
            S_ISDIR=lambda mode: mode == 0o040000, S_ISREG=lambda mode: mode == 0o100000
        ),
    )

    values = backend.PosixBundleBackend(1).enumerate_regular_files(
        maximum_files=2, maximum_entries=3, maximum_depth=2
    )

    assert values == (("nested", "deep.txt"), ("top.txt",))
    assert fake.entries_yielded == 3
    assert fake.maximum_scans_open == 2
    assert fake.closed == [5, 7, 3, 4, 6, 2]


def test_enumeration_cleanup_failure_closes_ancestor_chain_and_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _StreamingEnumerationOS(close_failures=frozenset({5}))
    monkeypatch.setattr(backend, "os", fake)
    monkeypatch.setattr(
        backend,
        "stat",
        SimpleNamespace(
            S_ISDIR=lambda mode: mode == 0o040000, S_ISREG=lambda mode: mode == 0o100000
        ),
    )

    with pytest.raises(ValueError, match="^bundle enumeration cannot be read$"):
        backend.PosixBundleBackend(1).enumerate_regular_files(
            maximum_files=2, maximum_entries=3, maximum_depth=2
        )

    assert fake.close_attempts == [5, 7, 3, 6, 2]
