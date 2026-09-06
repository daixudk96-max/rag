"""Confirmed-disposable Docker acceptance coverage for failure audit persistence."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest

from llamaindex_runtime.okf.parser import OKFParser

from . import _rebuild_cli_testkit as cli_testkit
from . import _rebuild_integration_testkit as testkit
from ._rebuild_integration_testkit import (
    _apply_schema,
    _disposable_connection,
    _failure_rows,
    _insert_document_version,
    _insert_stale_span,
    _provision_bundle_root,
    _RedactedDatabaseUrl,
    _run_cli,
    _write_raw_document,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("OKF_REBUILD_DOCKER_ACCEPTANCE") != "1"
        or os.environ.get("OKF_FAILURE_AUDIT_ACCEPTANCE") != "1",
        reason=(
            "set OKF_REBUILD_DOCKER_ACCEPTANCE=1 and "
            "OKF_FAILURE_AUDIT_ACCEPTANCE=1 for confirmed disposable Docker tests"
        ),
    ),
]


def test_disposable_subprocess_environment_removes_libpq_canaries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    canaries = {
        "PGHOST": "host-canary",
        "PGHOSTADDR": "address-canary",
        "PGSERVICE": "service-canary",
        "PGSERVICEFILE": "service-file-canary",
        "PGPORT": "port-canary",
        "PGDATABASE": "database-canary",
        "PGUSER": "user-canary",
        "PGPASSWORD": "password-canary",
        "PGPASSFILE": "passfile-canary",
        "PGTARGETSESSIONATTRS": "target-canary",
        "DATABASE_URL": "url-canary",
        "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE": "gate-canary",
        "OKF_REBUILD_EXPECTED_DATABASE": "expected-canary",
    }
    for key, value in canaries.items():
        monkeypatch.setenv(key, value)
    captured: dict[str, object] = {}

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["argv"] = argv
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(testkit.subprocess, "run", fake_run)
    database_url = _RedactedDatabaseUrl(
        "postgresql://okf:secret@127.0.0.1:5432/okf_task34"
    )
    testkit._run_cli(tmp_path, database_url)

    environment = captured["env"]
    assert isinstance(environment, dict)
    removed_canaries = set(canaries) - {
        "DATABASE_URL",
        "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE",
        "OKF_REBUILD_EXPECTED_DATABASE",
    }
    assert not removed_canaries & environment.keys()
    assert environment["DATABASE_URL"] == str(database_url)
    assert environment["OKF_MIGRATION_TEST_DATABASE_DISPOSABLE"] == "1"
    assert environment["OKF_REBUILD_EXPECTED_DATABASE"] == "okf_task34"


def test_cli_subprocess_environment_removes_libpq_canaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canaries = {
        "PGHOST": "host-canary",
        "PGHOSTADDR": "address-canary",
        "PGSERVICE": "service-canary",
        "PGSERVICEFILE": "service-file-canary",
        "PGPORT": "port-canary",
        "PGDATABASE": "database-canary",
        "PGUSER": "user-canary",
        "PGPASSWORD": "password-canary",
        "PGPASSFILE": "passfile-canary",
        "PGTARGETSESSIONATTRS": "target-canary",
    }
    for key, value in canaries.items():
        monkeypatch.setenv(key, value)
    captured: dict[str, object] = {}

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(cli_testkit.subprocess, "run", fake_run)
    cli_testkit.run_cli(
        "--help",
        database_url="postgresql://okf:secret@127.0.0.1:5432/okf_task34",
        expected_database="okf_task34",
    )

    environment = captured["env"]
    assert isinstance(environment, dict)
    assert not set(canaries) & environment.keys()
    assert environment["DATABASE_URL"].endswith("/okf_task34")
    assert environment["OKF_MIGRATION_TEST_DATABASE_DISPOSABLE"] == "1"
    assert environment["OKF_REBUILD_EXPECTED_DATABASE"] == "okf_task34"


def test_docker_helper_uses_direct_docker_and_static_guard() -> None:
    source = Path(testkit.__file__).read_text(encoding="utf-8")
    assert "['rtk'" not in source
    assert '"rtk"' not in source
    assert 'shutil.which("docker")' in source


@pytest.fixture
def disposable_postgres() -> Iterator[_RedactedDatabaseUrl]:
    yield from testkit._disposable_postgres_impl()


def test_later_scope_rollback_leaves_one_redacted_audit(
    tmp_path: Path, disposable_postgres: _RedactedDatabaseUrl
) -> None:
    _apply_schema(disposable_postgres)
    document_id = UUID("00000000-0000-0000-0000-000000000010")
    version_id = UUID("00000000-0000-0000-0000-000000000010")
    missing_doc_id = UUID("00000000-0000-0000-0000-000000000020")
    missing_version_id = UUID("00000000-0000-0000-0000-000000000020")
    bundle = tmp_path / "secret-path-must-not-persist"
    _provision_bundle_root(bundle)
    _write_raw_document(
        bundle,
        name="first",
        doc_id=str(document_id),
        version_id=str(version_id),
        changed=True,
    )
    _write_raw_document(
        bundle,
        name="second",
        doc_id=str(missing_doc_id),
        version_id=str(missing_version_id),
        changed=False,
    )
    with _disposable_connection(disposable_postgres) as connection:
        with connection.cursor() as cursor:
            _insert_document_version(cursor, document_id, version_id)
            _insert_stale_span(cursor, version_id, "stale")
        connection.commit()
        result = _run_cli(bundle, disposable_postgres)
        assert result.returncode == 2
        assert _failure_rows(connection)[0][:5] == (
            "scope_validation",
            "unregistered_document_version",
            "scope_lock",
            True,
            2,
        )
        assert "secret-path-must-not-persist" not in repr(_failure_rows(connection)[0])
        with pytest.raises(
            psycopg.errors.RaiseException,
            match=r"^okf_rebuild_failure_audit is append-only",
        ):
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute("TRUNCATE okf_rebuild_failure_audit")
        assert len(_failure_rows(connection)) == 1


def test_collision_failure_leaves_identity_conflict_audit(
    tmp_path: Path, disposable_postgres: _RedactedDatabaseUrl
) -> None:
    _apply_schema(disposable_postgres)
    doc_id, version_id, owner_id = uuid4(), uuid4(), uuid4()
    bundle = tmp_path / "collision"
    _provision_bundle_root(bundle)
    _write_raw_document(
        bundle,
        name="target",
        doc_id=str(doc_id),
        version_id=str(version_id),
        changed=False,
    )
    document = OKFParser().parse_bundle(bundle)[0]
    span_id = UUID(document.spans[0].span_id)
    with _disposable_connection(disposable_postgres) as connection:
        with connection.cursor() as cursor:
            _insert_document_version(cursor, doc_id, version_id)
            _insert_document_version(cursor, uuid4(), owner_id)
            cursor.execute(
                "INSERT INTO canonical_spans "
                "(span_id, version_id, span_kind, start_offset, end_offset) "
                "VALUES (%s, %s, 'paragraph', 0, 1)",
                (span_id, owner_id),
            )
        connection.commit()
        assert _run_cli(bundle, disposable_postgres).returncode == 2
        assert _failure_rows(connection)[0][:3] == (
            "identity_conflict",
            "span_id_owned_by_other_version",
            "span_reconciliation",
        )


def test_successful_rebuild_leaves_zero_failure_audits(
    tmp_path: Path, disposable_postgres: _RedactedDatabaseUrl
) -> None:
    _apply_schema(disposable_postgres)
    doc_id, version_id = uuid4(), uuid4()
    bundle = tmp_path / "success"
    _provision_bundle_root(bundle)
    _write_raw_document(
        bundle,
        name="target",
        doc_id=str(doc_id),
        version_id=str(version_id),
        changed=False,
    )
    with _disposable_connection(disposable_postgres) as connection:
        with connection.cursor() as cursor:
            _insert_document_version(cursor, doc_id, version_id)
        connection.commit()
        assert _run_cli(bundle, disposable_postgres).returncode == 0
        assert _failure_rows(connection) == []
