"""Docker-backed acceptance coverage for parser-only OKF rebuild scope."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from . import _rebuild_integration_testkit as testkit
from ._rebuild_integration_testkit import (
    _apply_schema,
    _assert_collision_rollback,
    _assert_missing_scope_rollback,
    _assert_reconciliation_after_first_run,
    _assert_reconciliation_after_second_run,
    _build_collision_scenario,
    _build_missing_scope_scenario,
    _build_reconciliation_scenario,
    _completed_logs,
    _disposable_connection,
    _insert_document_version,
    _provision_bundle_root,
    _RedactedDatabaseUrl,
    _run_cli,
    _seed_collision_scenario,
    _seed_missing_scope_scenario,
    _seed_reconciliation_scenario,
    _write_raw_document,
)


@pytest.fixture
def disposable_postgres() -> Iterator[_RedactedDatabaseUrl]:
    yield from testkit._disposable_postgres_impl()


def test_outer_docker_authorization_precedes_docker_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docker_checks: list[str] = []

    def fail_unexpected_docker_lookup(_: str) -> str | None:
        docker_checks.append("which")
        pytest.fail("gate must run first")
        return None

    monkeypatch.delenv("OKF_REBUILD_DOCKER_ACCEPTANCE", raising=False)
    monkeypatch.setattr(testkit.shutil, "which", fail_unexpected_docker_lookup)
    monkeypatch.setattr(
        testkit,
        "_run_docker",
        lambda *_: pytest.fail("gate must run before Docker commands"),
    )

    with pytest.raises(pytest.skip.Exception, match="OKF_REBUILD_DOCKER_ACCEPTANCE=1"):
        next(testkit._disposable_postgres_impl())

    assert docker_checks == []


def test_bundle_fixture_provisions_root_before_serialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle_root = tmp_path / "nested" / "bundle"
    observed_roots: list[Path] = []
    with pytest.raises(ValueError, match="^pair_publish_failed$"):
        _write_raw_document(
            bundle_root,
            name="target",
            doc_id=str(uuid4()),
            version_id=str(uuid4()),
            changed=False,
        )

    def capture_serializer(*args: Any, **kwargs: Any) -> None:
        bundle_root_argument = kwargs["bundle_root"]
        assert isinstance(bundle_root_argument, Path)
        observed_roots.append(bundle_root_argument)
        assert bundle_root.is_dir()

    monkeypatch.setattr(testkit, "serialize_document", capture_serializer)
    _provision_bundle_root(bundle_root)
    _write_raw_document(
        bundle_root,
        name="target",
        doc_id=str(uuid4()),
        version_id=str(uuid4()),
        changed=False,
    )
    assert observed_roots == [bundle_root]


@pytest.mark.integration
def test_rebuild_reconciles_spans_without_destroying_retained_dependencies(
    tmp_path: Path, disposable_postgres: _RedactedDatabaseUrl
) -> None:
    """Reconciliation preserves retained span dependencies and removes only stale ones."""
    _apply_schema(disposable_postgres)
    scenario = _build_reconciliation_scenario(tmp_path)
    seed = _seed_reconciliation_scenario(disposable_postgres, scenario)
    first = _run_cli(scenario.bundle, disposable_postgres)
    assert (first.returncode, first.stdout, first.stderr) == (0, "", "")
    target_snapshot = _assert_reconciliation_after_first_run(
        disposable_postgres, scenario, seed
    )
    second = _run_cli(scenario.bundle, disposable_postgres)
    assert (second.returncode, second.stdout, second.stderr) == (0, "", "")
    _assert_reconciliation_after_second_run(
        disposable_postgres, scenario, target_snapshot
    )


@pytest.mark.integration
def test_rebuild_bundle_writes_one_completed_log_per_successful_scope(
    tmp_path: Path, disposable_postgres: _RedactedDatabaseUrl
) -> None:
    """Each successful raw scope creates its own completed rebuild log."""
    _apply_schema(disposable_postgres)
    first_doc_id = UUID("00000000-0000-0000-0000-000000000010")
    first_version_id = UUID("00000000-0000-0000-0000-000000000010")
    second_doc_id = UUID("00000000-0000-0000-0000-000000000020")
    second_version_id = UUID("00000000-0000-0000-0000-000000000020")
    bundle = tmp_path / "multi-scope"
    _provision_bundle_root(bundle)
    _write_raw_document(
        bundle,
        name="01-first",
        doc_id=str(first_doc_id),
        version_id=str(first_version_id),
        changed=True,
    )
    _write_raw_document(
        bundle,
        name="02-second",
        doc_id=str(second_doc_id),
        version_id=str(second_version_id),
        changed=False,
    )
    with _disposable_connection(disposable_postgres) as connection:
        with connection.cursor() as cursor:
            _insert_document_version(cursor, first_doc_id, first_version_id)
            _insert_document_version(cursor, second_doc_id, second_version_id)
        connection.commit()
    result = _run_cli(bundle, disposable_postgres)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    with _disposable_connection(disposable_postgres) as connection:
        assert _completed_logs(connection) == [
            ("completed", 6, None),
            ("completed", 6, None),
        ]


@pytest.mark.integration
def test_rebuild_bundle_rolls_back_on_cross_version_span_id_collision(
    tmp_path: Path, disposable_postgres: _RedactedDatabaseUrl
) -> None:
    """A later global span-ID collision rolls back every earlier scope mutation."""
    _apply_schema(disposable_postgres)
    scenario = _build_collision_scenario(tmp_path)
    snapshots = _seed_collision_scenario(disposable_postgres, scenario)
    failed = _run_cli(scenario.bundle, disposable_postgres)
    assert failed.returncode == 2
    assert "belongs to a different document version" in failed.stderr
    _assert_collision_rollback(disposable_postgres, scenario, snapshots)


@pytest.mark.integration
def test_rebuild_bundle_rolls_back_registered_scope_when_later_scope_is_missing(
    tmp_path: Path, disposable_postgres: _RedactedDatabaseUrl
) -> None:
    """A later unregistered scope rolls back prior DML, cascades, audits, and logs."""
    _apply_schema(disposable_postgres)
    scenario = _build_missing_scope_scenario(tmp_path)
    seed = _seed_missing_scope_scenario(disposable_postgres, scenario)
    failed = _run_cli(scenario.bundle, disposable_postgres)
    assert failed.returncode == 2
    assert "not registered" in failed.stderr
    _assert_missing_scope_rollback(disposable_postgres, scenario, seed)
