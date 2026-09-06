from __future__ import annotations

from pathlib import Path

import pytest

from llamaindex_runtime.okf.rooted_open import BundleAuthority


class _Backend:
    def __init__(self, result: tuple[tuple[str, ...], ...]) -> None:
        self.result = result
        self.calls: list[tuple[int, int, int]] = []

    def close(self) -> None:
        pass

    def read_bytes(self, parts: tuple[str, ...], maximum: int) -> bytes:
        return b""

    def enumerate_regular_files(
        self, *, maximum_files: int, maximum_entries: int, maximum_depth: int
    ) -> tuple[tuple[str, ...], ...]:
        self.calls.append((maximum_files, maximum_entries, maximum_depth))
        return self.result


def test_authority_enumeration_validates_exact_positive_integer_limits() -> None:
    authority = BundleAuthority(Path("unused"))
    authority._backend = _Backend(())  # type: ignore[assignment]
    for bad in (0, -1, True, 1.0, "1"):
        with pytest.raises(ValueError, match="positive integers"):
            authority.enumerate_regular_files(  # type: ignore[arg-type]
                maximum_files=bad, maximum_entries=1, maximum_depth=1
            )


def test_authority_enumeration_returns_canonical_sorted_components() -> None:
    authority = BundleAuthority(Path("not-used-for-discovery"))
    backend = _Backend((("raw", "z.md"), ("raw", "a.md")))
    authority._backend = backend  # type: ignore[assignment]

    assert authority.enumerate_regular_files(
        maximum_files=2, maximum_entries=3, maximum_depth=2
    ) == (("raw", "a.md"), ("raw", "z.md"))
    assert backend.calls == [(2, 3, 2)]


def test_real_authority_enumerates_nested_regular_files_in_order(
    tmp_path: Path,
) -> None:
    (tmp_path / "z").mkdir()
    (tmp_path / "a").mkdir()
    (tmp_path / "z" / "two.txt").write_text("z", encoding="utf-8")
    (tmp_path / "a" / "one.txt").write_text("a", encoding="utf-8")

    with BundleAuthority(tmp_path) as authority:
        assert authority.enumerate_regular_files(
            maximum_files=2, maximum_entries=4, maximum_depth=2
        ) == (("a", "one.txt"), ("z", "two.txt"))


def test_real_authority_fails_closed_at_file_entry_and_depth_boundaries(
    tmp_path: Path,
) -> None:
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "item.txt").write_text("x", encoding="utf-8")

    with BundleAuthority(tmp_path) as authority:
        with pytest.raises(ValueError):
            authority.enumerate_regular_files(
                maximum_files=1, maximum_entries=1, maximum_depth=2
            )
        with pytest.raises(ValueError):
            authority.enumerate_regular_files(
                maximum_files=1, maximum_entries=2, maximum_depth=1
            )


def test_authority_public_read_boundary_rejects_noncanonical_runtime_types() -> None:
    authority = BundleAuthority(Path("unused"))
    backend = _Backend(())
    authority._backend = backend  # type: ignore[assignment]

    for parts, maximum in (
        (["raw", "source.md"], 1),
        (("raw", "source.md"), True),
        (("raw", "source.md"), 1.5),
        (("raw", "source.md"), "1"),
    ):
        with pytest.raises(ValueError, match="^bundle read arguments are invalid$"):
            authority.read_bytes(parts, maximum)  # type: ignore[arg-type]

    assert backend.calls == []
