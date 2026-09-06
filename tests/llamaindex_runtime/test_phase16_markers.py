"""TDD tests for Phase 16-01: pytest marker registration.

Static reads of ``llamaindex_runtime/pyproject.toml`` and ``tests/conftest.py``
so a marker typo is caught before any ``disposable_db``
test exists (D8: those surfaces stay non-imported and non-collected by default).
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT_PATH = REPO_ROOT / "llamaindex_runtime" / "pyproject.toml"
CONFTEST_PATH = REPO_ROOT / "tests" / "conftest.py"

EXPECTED_MARKERS = {
    "disposable_db": (
        "disposable_db: tests that require a separately authorized "
        "disposable PostgreSQL/Docker target"
    ),
}
FORBIDDEN_DEFAULT_DEPS = ("modelscope", "torch", "transformers", "sentencepiece")


def _pyproject() -> dict:
    return tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))


def _pyproject_markers() -> list[str]:
    return _pyproject()["tool"]["pytest"]["ini_options"]["markers"]


class TestPyprojectDefaultDependencies:
    def test_default_dependencies_exclude_heavy_model_packages(self) -> None:
        dependencies = _pyproject()["project"]["dependencies"]
        for package in FORBIDDEN_DEFAULT_DEPS:
            assert package not in dependencies


class TestPyprojectMarkerRegistration:
    @pytest.mark.parametrize("marker_name", sorted(EXPECTED_MARKERS))
    def test_pyproject_declares_marker(self, marker_name: str) -> None:
        marker_lines = _pyproject_markers()
        assert any(line.startswith(marker_name + ":") for line in marker_lines)

    @pytest.mark.parametrize("expected", sorted(EXPECTED_MARKERS.values()))
    def test_pyproject_marker_lines_match_contract(self, expected: str) -> None:
        marker_lines = _pyproject_markers()
        assert expected in marker_lines


class TestConftestMarkerRegistration:
    @pytest.mark.parametrize("marker_name", sorted(EXPECTED_MARKERS))
    def test_conftest_registers_marker(self, marker_name: str) -> None:
        source = CONFTEST_PATH.read_text(encoding="utf-8")
        source = re.sub(r"\s+", " ", source)  # formatting-robust
        assert f'"markers", "{marker_name}:' in source

    def test_conftest_still_registers_existing_markers(self) -> None:
        source = CONFTEST_PATH.read_text(encoding="utf-8")
        source = re.sub(r"\s+", " ", source)  # formatting-robust
        assert '"markers", "live_st:' in source
        assert '"markers", "integration:' in source
