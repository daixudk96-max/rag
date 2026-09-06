from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest

import scripts.run_pageindex_real_retrieval_workflow as workflow
from scripts.run_pageindex_real_retrieval_workflow import (
    apply_migrations,
    database_is_reachable,
)


class _FakeCursor:
    def __init__(self, fail_on_call: int | None = None) -> None:
        self.executed_sql: list[str] = []
        self._fail_on_call = fail_on_call

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def execute(self, sql: str) -> None:
        self.executed_sql.append(sql)
        if (
            self._fail_on_call is not None
            and len(self.executed_sql) == self._fail_on_call
        ):
            raise RuntimeError("boom")


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor

    def __enter__(self) -> _FakeConnection:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return self._cursor


class _HostileError(Exception):
    def __str__(self) -> str:
        raise AssertionError("exception __str__ must not be called")

    def __repr__(self) -> str:
        raise AssertionError("exception __repr__ must not be called")


class _HostileCursor(_FakeCursor):
    def execute(self, sql: str) -> None:
        self.executed_sql.append(sql)
        if sql == "SELECT 1":
            raise _HostileError()


def _installed_libpq_envvars() -> set[str]:
    envvars: set[str] = set()
    for option in psycopg.pq.Conninfo.get_defaults():
        metadata_value: object = option.envvar
        envvar = workflow._normalize_libpq_metadata_value(metadata_value)
        if envvar is not None:
            envvars.add(envvar)
    return envvars


def test_apply_migrations_respects_provided_file_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    migration_files = ["001_initial.sql", "002_version_lifecycle.sql"]
    for index, name in enumerate(migration_files, start=1):
        (tmp_path / name).write_text(f"-- migration {index}", encoding="utf-8")

    fake_cursor = _FakeCursor()
    fake_connection = _FakeConnection(fake_cursor)

    monkeypatch.setattr(
        "scripts.run_pageindex_real_retrieval_workflow.psycopg.connect",
        lambda **_kwargs: fake_connection,
    )

    applied = apply_migrations(
        database_url="postgresql://postgres:postgres@localhost:5432/rag",
        migrations_dir=tmp_path,
        migration_files=migration_files,
    )

    assert applied == migration_files
    assert fake_cursor.executed_sql == [
        workflow.MIGRATION_LOCK_TIMEOUT_SQL,
        workflow.MIGRATION_STATEMENT_TIMEOUT_SQL,
        "-- migration 1",
        "-- migration 2",
    ]


def test_apply_migrations_stops_on_sql_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    migration_files = [
        "001_initial.sql",
        "002_version_lifecycle.sql",
        "003_tree_persistence.sql",
    ]
    for index, name in enumerate(migration_files, start=1):
        (tmp_path / name).write_text(f"-- migration {index}", encoding="utf-8")

    fake_cursor = _FakeCursor(fail_on_call=4)
    fake_connection = _FakeConnection(fake_cursor)

    monkeypatch.setattr(
        "scripts.run_pageindex_real_retrieval_workflow.psycopg.connect",
        lambda **_kwargs: fake_connection,
    )

    with pytest.raises(RuntimeError, match="002_version_lifecycle.sql"):
        apply_migrations(
            database_url="postgresql://postgres:postgres@localhost:5432/rag",
            migrations_dir=tmp_path,
            migration_files=migration_files,
        )

    assert fake_cursor.executed_sql == [
        workflow.MIGRATION_LOCK_TIMEOUT_SQL,
        workflow.MIGRATION_STATEMENT_TIMEOUT_SQL,
        "-- migration 1",
        "-- migration 2",
    ]


@pytest.mark.parametrize(
    ("input_host", "expected_host"),
    [("localhost", "127.0.0.1"), ("127.0.0.1", "127.0.0.1"), ("[::1]", "::1")],
)
def test_parent_connections_pin_normalized_loopback_despite_libpq_environment(
    input_host: str, expected_host: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    canaries = {
        "PGHOSTADDR": "remote-hostaddr-canary",
        "PGHOST": "remote-host-canary",
        "PGPORT": "6543",
        "PGDATABASE": "remote-database-canary",
        "PGUSER": "remote-user-canary",
        "PGPASSWORD": "remote-password-canary",
    }
    for key, value in canaries.items():
        monkeypatch.setenv(key, value)
    original_environment = os.environ.copy()
    calls: list[dict[str, object]] = []

    def _connect(**kwargs: object) -> _FakeConnection:
        calls.append(kwargs)
        return _FakeConnection(_FakeCursor())

    monkeypatch.setattr(workflow.psycopg, "connect", _connect)
    migration = tmp_path / "001_initial.sql"
    migration.write_text("SELECT 1", encoding="utf-8")
    database_url = f"postgresql://local-user:local-password@{input_host}:5432/local-db"

    assert workflow.database_is_reachable(database_url)
    assert workflow.apply_migrations(
        database_url=database_url,
        migrations_dir=tmp_path,
        migration_files=(migration.name,),
    ) == [migration.name]

    expected = {
        "host": expected_host,
        "hostaddr": expected_host,
        "port": 5432,
        "dbname": "local-db",
        "user": "local-user",
        "password": "local-password",
        "connect_timeout": workflow.DATABASE_CONNECT_TIMEOUT,
        "options": workflow.MIGRATION_CONNECTION_OPTIONS,
        "autocommit": True,
    } | workflow._supported_parent_connection_controls()
    assert calls == [expected, expected]
    assert os.environ == original_environment


def test_parent_connections_override_hostile_pgoptions_with_safe_search_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    hostile_pgoptions = (
        "-c search_path=hostile_schema -c application_name=secret-canary"
    )
    monkeypatch.setenv("PGOPTIONS", hostile_pgoptions)
    calls: list[dict[str, object]] = []

    def _connect(**kwargs: object) -> _FakeConnection:
        calls.append(kwargs)
        return _FakeConnection(_FakeCursor())

    monkeypatch.setattr(workflow.psycopg, "connect", _connect)
    migration = tmp_path / "001_initial.sql"
    migration.write_text("CREATE TABLE example (id integer)", encoding="utf-8")
    database_url = "postgresql://postgres:password@localhost/rag"

    assert database_is_reachable(database_url)
    assert apply_migrations(
        database_url=database_url,
        migrations_dir=tmp_path,
        migration_files=(migration.name,),
    ) == [migration.name]

    assert workflow.MIGRATION_CONNECTION_OPTIONS == "-c search_path=public"
    assert all(
        call["options"] == workflow.MIGRATION_CONNECTION_OPTIONS for call in calls
    )
    assert all(call["options"] != hostile_pgoptions for call in calls)
    assert all("secret-canary" not in str(call["options"]) for call in calls)
    assert capsys.readouterr().out == ""


def test_migration_failure_uses_safe_stage_and_filename_without_cause_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    migration_name = "002_version_lifecycle.sql"
    (tmp_path / migration_name).write_text("SELECT 1", encoding="utf-8")
    monkeypatch.setattr(
        workflow.psycopg,
        "connect",
        lambda **_kwargs: _FakeConnection(_HostileCursor()),
    )

    with pytest.raises(workflow._WorkflowError) as exc_info:
        apply_migrations(
            database_url="postgresql://postgres:password@localhost/rag",
            migrations_dir=tmp_path,
            migration_files=(migration_name,),
        )

    assert exc_info.value.stage == "migration"
    assert exc_info.value.message == f"Migration stage failed: {migration_name}"
    assert str(exc_info.value) == f"Migration stage failed: {migration_name}"


def test_missing_migration_file_uses_safe_stage_and_filename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    migration_name = "003_tree_persistence.sql"
    monkeypatch.setattr(
        workflow.psycopg,
        "connect",
        lambda **_kwargs: _FakeConnection(_FakeCursor()),
    )

    with pytest.raises(workflow._WorkflowError) as exc_info:
        apply_migrations(
            database_url="postgresql://postgres:password@localhost/rag",
            migrations_dir=tmp_path,
            migration_files=(migration_name,),
        )

    assert exc_info.value.stage == "migration"
    assert exc_info.value.message == f"Migration stage failed: {migration_name}"


def test_parent_connections_use_fixed_bounded_connect_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, object]] = []

    def _connect(**kwargs: object) -> _FakeConnection:
        calls.append(kwargs)
        return _FakeConnection(_FakeCursor())

    monkeypatch.setattr(workflow.psycopg, "connect", _connect)
    migration = tmp_path / "001_initial.sql"
    migration.write_text("SELECT 1", encoding="utf-8")
    database_url = "postgresql://postgres:password@localhost/rag"

    assert database_is_reachable(database_url)
    assert apply_migrations(
        database_url=database_url,
        migrations_dir=tmp_path,
        migration_files=(migration.name,),
    ) == [migration.name]

    assert workflow.DATABASE_CONNECT_TIMEOUT == 10
    assert all(
        call["connect_timeout"] == workflow.DATABASE_CONNECT_TIMEOUT for call in calls
    )


def test_migrations_set_fixed_session_timeouts_before_migration_ddl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    migration = tmp_path / "001_initial.sql"
    migration.write_text("CREATE TABLE example (id integer)", encoding="utf-8")
    cursor = _FakeCursor()
    monkeypatch.setattr(
        workflow.psycopg, "connect", lambda **_kwargs: _FakeConnection(cursor)
    )

    apply_migrations(
        database_url="postgresql://postgres:password@localhost/rag",
        migrations_dir=tmp_path,
        migration_files=(migration.name,),
    )

    assert cursor.executed_sql == [
        workflow.MIGRATION_LOCK_TIMEOUT_SQL,
        workflow.MIGRATION_STATEMENT_TIMEOUT_SQL,
        "CREATE TABLE example (id integer)",
    ]
    assert workflow.MIGRATION_LOCK_TIMEOUT_SQL == "SET lock_timeout = '5s'"
    assert workflow.MIGRATION_STATEMENT_TIMEOUT_SQL == "SET statement_timeout = '60s'"


def test_parent_connections_neutralize_all_supported_installed_nonservice_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed_envvars = _installed_libpq_envvars()
    for envvar in installed_envvars:
        monkeypatch.setenv(envvar, f"canary-{envvar}")
    monkeypatch.delenv("PGSERVICE", raising=False)
    monkeypatch.delenv("PGSERVICEFILE", raising=False)
    calls: list[dict[str, object]] = []

    def _connect(**kwargs: object) -> _FakeConnection:
        calls.append(kwargs)
        return _FakeConnection(_FakeCursor())

    monkeypatch.setattr(workflow.psycopg, "connect", _connect)
    migration = tmp_path / "001_initial.sql"
    migration.write_text("SELECT 1", encoding="utf-8")
    url = "postgresql://local-user:local-password@localhost:5432/local-db"

    assert workflow.database_is_reachable(url)
    assert apply_migrations(
        database_url=url, migrations_dir=tmp_path, migration_files=(migration.name,)
    ) == [migration.name]

    expected_controls = workflow._supported_parent_connection_controls()
    for call in calls:
        assert call["host"] == "127.0.0.1"
        assert call["hostaddr"] == "127.0.0.1"
        assert call["port"] == 5432
        assert call["dbname"] == "local-db"
        assert call["user"] == "local-user"
        assert call["password"] == "local-password"
        assert call["options"] == "-c search_path=public"
        assert call["connect_timeout"] == workflow.DATABASE_CONNECT_TIMEOUT
        assert not any("canary-" in str(value) for value in call.values())
        for keyword, value in expected_controls.items():
            assert call[keyword] == value


def test_parent_connection_fails_closed_for_ambient_service_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PGSERVICE", "hostile-service")

    with pytest.raises(
        workflow._WorkflowError, match="Connection configuration failed"
    ):
        workflow.database_is_reachable("postgresql://user:password@localhost/rag")


def test_parent_connection_fails_closed_for_legacy_tls_without_sslmode_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata = (SimpleNamespace(keyword=b"host", envvar=b"PGHOST"),)
    monkeypatch.setattr(workflow.psycopg.pq.Conninfo, "get_defaults", lambda: metadata)
    monkeypatch.setenv("PGREQUIRESSL", "1")

    with pytest.raises(
        workflow._WorkflowError, match="Connection configuration failed"
    ):
        workflow.database_is_reachable("postgresql://user:password@localhost/rag")
