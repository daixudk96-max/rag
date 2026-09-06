"""Capability-gated integration checks for actual Windows NTFS junction handling."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from llamaindex_runtime.okf.rooted_open import BundleAuthority


def _create_junction_or_skip(link: Path, target: Path) -> None:
    if sys.platform != "win32":
        pytest.skip("NTFS junctions are a Windows-only capability")
    command = f'mklink /J "{link}" "{target}"'
    result = subprocess.run(
        ["cmd.exe", "/d", "/s", "/c", command],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0 or not link.exists():
        pytest.skip("NTFS junction creation is unavailable for this test host")


def test_native_backend_rejects_root_junction(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    junction = tmp_path / "bundle-junction"
    _create_junction_or_skip(junction, target)

    with pytest.raises(ValueError, match="^bundle root cannot be read$"):
        BundleAuthority(junction).__enter__()


def test_native_backend_rejects_nested_junction(tmp_path: Path) -> None:
    root = tmp_path / "bundle"
    root.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    (target / "entry.md").write_bytes(b"outside")
    junction = root / "nested"
    _create_junction_or_skip(junction, target)

    with BundleAuthority(root) as authority:
        with pytest.raises(ValueError, match="^document cannot be read$"):
            authority.read_document(("nested", "entry.md"))
