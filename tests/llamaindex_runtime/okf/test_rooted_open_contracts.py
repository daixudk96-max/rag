"""Deterministic contracts for authority-rooted OKF reads."""

from __future__ import annotations

from pathlib import Path

import pytest

from llamaindex_runtime.okf.rooted_open import (
    BundleAuthority,
    bundle_relative_components,
    validate_relative_path,
)


@pytest.mark.parametrize(
    "value",
    (
        "",
        ".",
        "../raw/a.md",
        "entities/../raw/a.md",
        "raw/../entities/a.md",
        "/x.md",
        "C:/x.md",
        "\\\\server\\share\\x.md",
    ),
)
def test_lexical_paths_are_rejected_before_open(value: str) -> None:
    with pytest.raises(
        ValueError, match="^document path must be contained in bundle root$"
    ):
        validate_relative_path(value)


@pytest.mark.parametrize(
    "relative",
    ("entities/../raw/a.md", "raw/../entities/a.md", "nested/../inside/a.md"),
)
def test_candidate_dotdot_is_rejected_lexically_before_authorization(
    tmp_path: Path, relative: str
) -> None:
    with pytest.raises(
        ValueError, match="^document path must be contained in bundle root$"
    ):
        bundle_relative_components(tmp_path / relative, tmp_path)


@pytest.mark.parametrize(
    "value",
    ("entry.md:alternate", "CON.md", "LPT1.txt", "entry.", "entry "),
)
def test_windows_lexical_path_rejects_ads_devices_and_normalized_aliases(
    value: str,
) -> None:
    with pytest.raises(
        ValueError, match="^document path must be contained in bundle root$"
    ):
        validate_relative_path(value, windows=True)


def test_posix_lexical_path_keeps_colon_filename_compatible() -> None:
    assert validate_relative_path("entry.md:alternate") == ("entry.md:alternate",)


def test_authority_reads_nested_regular_file(tmp_path: Path) -> None:
    path = tmp_path / "entities" / "nested" / "entry.md"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"safe")
    with BundleAuthority(tmp_path) as authority:
        assert authority.read_bytes(("entities", "nested", "entry.md"), 64) == b"safe"


def test_root_symlink_is_rejected_before_discovery(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "bundle"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(ValueError, match="^bundle root cannot be read$"):
        BundleAuthority(link).__enter__()


class _FakeBackend:
    def __init__(self, close_error: ValueError | None = None) -> None:
        self.close_calls = 0
        self._close_error = close_error

    def close(self) -> None:
        self.close_calls += 1
        if self._close_error is not None:
            raise self._close_error

    def read_bytes(self, parts: tuple[str, ...], maximum: int) -> bytes:
        return b""


def _enter_without_opening(authority: BundleAuthority) -> BundleAuthority:
    return authority


def test_exit_preserves_body_error_when_cleanup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body_error = ValueError("document cannot be read")
    backend = _FakeBackend(ValueError("bundle root cannot be read"))
    authority = BundleAuthority(Path("bundle"))
    authority._backend = backend
    monkeypatch.setattr(BundleAuthority, "__enter__", _enter_without_opening)

    with pytest.raises(ValueError) as caught:
        with authority:
            raise body_error

    assert caught.value is body_error
    assert backend.close_calls == 1


def test_exit_propagates_cleanup_error_after_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cleanup_error = ValueError("bundle root cannot be read")
    backend = _FakeBackend(cleanup_error)
    authority = BundleAuthority(Path("bundle"))
    authority._backend = backend
    monkeypatch.setattr(BundleAuthority, "__enter__", _enter_without_opening)

    with pytest.raises(ValueError) as caught:
        with authority:
            pass

    assert caught.value is cleanup_error
    assert backend.close_calls == 1


def test_exit_closes_successfully_without_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _FakeBackend()
    authority = BundleAuthority(Path("bundle"))
    authority._backend = backend
    monkeypatch.setattr(BundleAuthority, "__enter__", _enter_without_opening)

    with authority:
        pass

    assert backend.close_calls == 1
