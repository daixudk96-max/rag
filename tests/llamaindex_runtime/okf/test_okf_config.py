from __future__ import annotations

import pytest

from llamaindex_runtime.config import RuntimeSettings


@pytest.fixture(autouse=True)
def _isolate_cwd_from_project_env(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_okf_bundle_root_defaults_for_direct_runtime_settings() -> None:
    settings = RuntimeSettings(database_url="postgresql://test@localhost/test")

    assert settings.okf_bundle_root == "okf_bundle"


def test_okf_bundle_root_reads_process_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://test@localhost/test")
    monkeypatch.setenv("OKF_BUNDLE_ROOT", "custom-okf-bundle")

    settings = RuntimeSettings.from_env()

    assert settings.okf_bundle_root == "custom-okf-bundle"
