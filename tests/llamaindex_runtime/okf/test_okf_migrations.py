"""Integration coverage for the additive OKF registry migrations."""

from __future__ import annotations

import os
import re
import uuid
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path

import psycopg
import pytest
from psycopg import sql

from llamaindex_runtime.registry.migration_catalog import FULL_MIGRATION_CATALOG

MIGRATIONS_DIR = (
    Path(__file__).resolve().parents[3]
    / "llamaindex_runtime"
    / "registry"
    / "migrations"
)
OKF_MIGRATIONS = (
    "015_okf_sync_state.sql",
    "016_entity_mentions.sql",
    "017_relation_qualifiers.sql",
    "018_okf_rebuild_failure_audit.sql",
    "019_e2a_materialization_contract.sql",
)
ROOT_MIGRATION_SEQUENCE = FULL_MIGRATION_CATALOG
APPEND_ONLY_ERROR_PATTERN = r"^okf_rebuild_failure_audit is append-only"


def _require_disposable_database_url(environ: Mapping[str, str]) -> str:
    database_url = environ.get("DATABASE_URL")
    if database_url is None:
        pytest.skip("DATABASE_URL is required for OKF migration integration tests")
    if database_url == "":
        pytest.skip("DATABASE_URL is required for OKF migration integration tests")
    assert database_url is not None
    if environ.get("OKF_MIGRATION_TEST_DATABASE_DISPOSABLE") != "1":
        raise RuntimeError(
            "OKF migration integration tests require "
            "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE=1"
        )
    return database_url


@pytest.fixture(scope="module")
def database_url() -> str:
    return _require_disposable_database_url(os.environ)


@pytest.fixture
def isolated_schema(database_url: str) -> Iterator[psycopg.Connection]:
    schema_name = f"okf_migration_{uuid.uuid4().hex}"
    with psycopg.connect(database_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name))
            )
            cursor.execute(
                sql.SQL("SET search_path TO {}, public").format(
                    sql.Identifier(schema_name)
                )
            )
        try:
            yield connection
        finally:
            with connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL("DROP SCHEMA {} CASCADE").format(
                        sql.Identifier(schema_name)
                    )
                )


def _migration_files_before(filename: str) -> tuple[str, ...]:
    return tuple(
        migration.name
        for migration in sorted(MIGRATIONS_DIR.glob("*.sql"))
        if migration.name < filename
    )


def _apply_migrations(
    connection: psycopg.Connection, migration_files: Sequence[str]
) -> None:
    with connection.cursor() as cursor:
        for migration_file in migration_files:
            cursor.execute(
                (MIGRATIONS_DIR / migration_file).read_text(encoding="utf-8")
            )


def _assert_okf_tables(connection: psycopg.Connection) -> None:
    expected_tables = {
        "okf_sync_state",
        "okf_rebuild_log",
        "okf_rebuild_failure_audit",
        "entity_aliases",
        "entity_mentions",
        "entity_merge_log",
    }
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = current_schema()"
        )
        assert expected_tables.issubset({row[0] for row in cursor.fetchall()})


def _assert_relation_qualifier_columns(connection: psycopg.Connection) -> None:
    expected_relation_columns = {
        "negation",
        "condition",
        "direction",
        "confidence",
        "qualifiers",
    }
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = 'relations'"
        )
        assert expected_relation_columns.issubset({row[0] for row in cursor.fetchall()})


def _assert_entity_mention_constraints(connection: psycopg.Connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = 'entity_mentions' AND column_name = 'entity_id'"
        )
        assert cursor.fetchone() == ("YES",)
        cursor.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid = 'entity_mentions'::regclass AND contype = 'f'"
        )
        assert any(
            "FOREIGN KEY (entity_id) REFERENCES entities(entity_id)" in constraint[0]
            for constraint in cursor.fetchall()
        )
        cursor.execute(
            "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid = 'entity_mentions'::regclass AND contype = 'c'"
        )
        constraints: dict[str, str] = dict(cursor.fetchall())
        assert "chk_entity_mentions_char_range" in constraints
        assert "char_start >= 0" in constraints["chk_entity_mentions_char_range"]
        assert "char_end > char_start" in constraints["chk_entity_mentions_char_range"]


def _assert_entity_aliases_index(connection: psycopg.Connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname = current_schema() AND tablename = 'entity_aliases'"
        )
        alias_index_names = {row[0] for row in cursor.fetchall()}
        assert (
            "idx_entity_aliases_entity" in alias_index_names
        ), "Expected idx_entity_aliases_entity index on entity_aliases.entity_id"


def _assert_okf_schema(connection: psycopg.Connection) -> None:
    _assert_okf_tables(connection)
    _assert_relation_qualifier_columns(connection)
    _assert_entity_mention_constraints(connection)
    _assert_entity_aliases_index(connection)


def _insert_entity_mention_fixture(
    connection: psycopg.Connection, mention_text: str
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    document_id = uuid.uuid4()
    version_id = uuid.uuid4()
    span_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    mention_id = uuid.uuid4()
    with connection.cursor() as cursor:
        cursor.execute("INSERT INTO documents (doc_id) VALUES (%s)", (document_id,))
        cursor.execute(
            "INSERT INTO document_versions "
            "(version_id, doc_id, content_hash, version_no) VALUES (%s, %s, %s, %s)",
            (version_id, document_id, uuid.uuid4().hex, 1),
        )
        cursor.execute(
            "INSERT INTO canonical_spans "
            "(span_id, version_id, span_kind, start_offset, end_offset) "
            "VALUES (%s, %s, %s, %s, %s)",
            (span_id, version_id, "paragraph", 0, 1),
        )
        cursor.execute(
            "INSERT INTO entities (entity_id, entity_key) VALUES (%s, %s)",
            (entity_id, uuid.uuid4().hex),
        )
        cursor.execute(
            "INSERT INTO entity_mentions "
            "(mention_id, entity_id, span_id, char_start, char_end, mention_text, source) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (mention_id, entity_id, span_id, 0, 1, mention_text, "test"),
        )
    return entity_id, mention_id, span_id


def _assert_entity_mention_char_range(connection: psycopg.Connection) -> None:
    entity_id, _, span_id = _insert_entity_mention_fixture(connection, "x")
    with pytest.raises(psycopg.errors.CheckViolation):
        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO entity_mentions "
                    "(mention_id, entity_id, span_id, char_start, char_end, mention_text, source) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (uuid.uuid4(), entity_id, span_id, -1, 1, "x", "test"),
                )


def test_require_disposable_database_url_skips_without_database_url() -> None:
    with pytest.raises(pytest.skip.Exception):
        _require_disposable_database_url({})


def test_require_disposable_database_url_rejects_unmarked_database() -> None:
    with pytest.raises(
        RuntimeError,
        match="OKF_MIGRATION_TEST_DATABASE_DISPOSABLE=1",
    ):
        _require_disposable_database_url({"DATABASE_URL": "configured"})


def test_require_disposable_database_url_returns_marked_database_url() -> None:
    environ = {
        "DATABASE_URL": "configured",
        "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE": "1",
    }

    assert _require_disposable_database_url(environ) == "configured"


def test_okf_migration_files_are_present() -> None:
    migration_names = tuple(
        migration.name for migration in sorted(MIGRATIONS_DIR.glob("*.sql"))
    )
    positions = tuple(migration_names.index(migration) for migration in OKF_MIGRATIONS)
    assert positions == tuple(sorted(positions))


def test_entity_mentions_and_failure_audit_migrations_have_required_shapes() -> None:
    entity_mentions_source = (MIGRATIONS_DIR / "016_entity_mentions.sql").read_text(
        encoding="utf-8"
    )
    failure_audit_source = (
        MIGRATIONS_DIR / "018_okf_rebuild_failure_audit.sql"
    ).read_text(encoding="utf-8")

    assert (
        "CREATE INDEX IF NOT EXISTS idx_entity_aliases_entity "
        "ON entity_aliases(entity_id);" in entity_mentions_source
    )
    assert (
        "CREATE TRIGGER trg_okf_rebuild_failure_audit_append_only\n"
        "    BEFORE UPDATE OR DELETE ON okf_rebuild_failure_audit\n"
        "    FOR EACH ROW" in failure_audit_source
    )
    assert (
        "CREATE TRIGGER trg_okf_rebuild_failure_audit_no_truncate\n"
        "    BEFORE TRUNCATE ON okf_rebuild_failure_audit\n"
        "    FOR EACH STATEMENT" in failure_audit_source
    )


def test_root_runner_uses_database_url_from_environment() -> None:
    runner_source = (MIGRATIONS_DIR.parents[2] / "run_migrations.py").read_text(
        encoding="utf-8"
    )

    assert "postgresql://" not in runner_source
    assert "DATABASE_URL" in runner_source


def test_root_runner_raises_runtime_error_for_missing_database_url(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Missing DATABASE_URL must raise RuntimeError naming DATABASE_URL, not KeyError.

    The error must be actionable and must not echo credentials or attempt a connection.
    """
    import run_migrations

    monkeypatch.delenv("DATABASE_URL", raising=False)

    def _fail_connect(*args: object, **kwargs: object) -> None:
        pytest.fail("psycopg.connect must not be called without DATABASE_URL")

    monkeypatch.setattr(run_migrations.psycopg, "connect", _fail_connect)

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        run_migrations.main()

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_root_runner_resolves_migrations_relative_to_script() -> None:
    runner_source = (MIGRATIONS_DIR.parents[2] / "run_migrations.py").read_text(
        encoding="utf-8"
    )
    for component in (
        "Path(__file__).resolve().parent",
        '"llamaindex_runtime"',
        '"registry"',
        '"migrations"',
    ):
        assert component in runner_source


def test_root_runner_has_exact_key_migration_order() -> None:
    import run_migrations

    assert run_migrations.KEY_MIGRATIONS == ROOT_MIGRATION_SEQUENCE


def test_append_only_error_pattern_allows_plpgsql_context() -> None:
    error = "okf_rebuild_failure_audit is append-only\nCONTEXT: PL/pgSQL function"

    assert re.search(APPEND_ONLY_ERROR_PATTERN, error)
    assert not re.search(
        APPEND_ONLY_ERROR_PATTERN,
        "another error: okf_rebuild_failure_audit is append-only",
    )


@pytest.mark.integration
def test_fresh_schema_applies_all_migrations(
    isolated_schema: psycopg.Connection,
) -> None:
    _apply_migrations(
        isolated_schema,
        tuple(migration.name for migration in sorted(MIGRATIONS_DIR.glob("*.sql"))),
    )
    _assert_okf_schema(isolated_schema)


@pytest.mark.integration
def test_entity_mention_char_range_is_enforced(
    isolated_schema: psycopg.Connection,
) -> None:
    _apply_migrations(
        isolated_schema,
        tuple(migration.name for migration in sorted(MIGRATIONS_DIR.glob("*.sql"))),
    )
    _assert_entity_mention_char_range(isolated_schema)


def _assert_entity_mention_on_delete_set_null(connection: psycopg.Connection) -> None:
    """Verify entity_mentions.entity_id ON DELETE SET NULL behavior."""
    entity_id, mention_id, span_id = _insert_entity_mention_fixture(
        connection, "TestEntity"
    )
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM entities WHERE entity_id = %s", (entity_id,))
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT mention_id, entity_id, span_id FROM entity_mentions WHERE mention_id = %s",
            (mention_id,),
        )
        row = cursor.fetchone()
        assert row is not None, "Mention row must survive entity deletion"
        assert row[0] == mention_id, "Mention ID must match"
        assert row[1] is None, "entity_id must be NULL after ON DELETE SET NULL"
        assert row[2] == span_id, "span_id must remain intact"


@pytest.mark.integration
def test_entity_mention_on_delete_set_null(
    isolated_schema: psycopg.Connection,
) -> None:
    """Phase 14 Wave 1: verify entity_mentions.entity_id ON DELETE SET NULL behavior."""
    _apply_migrations(
        isolated_schema,
        tuple(migration.name for migration in sorted(MIGRATIONS_DIR.glob("*.sql"))),
    )
    # Run within a transaction to preserve state for subsequent tests
    with isolated_schema.transaction():
        _assert_entity_mention_on_delete_set_null(isolated_schema)


@pytest.mark.integration
def test_existing_schema_adds_okf_migrations(
    isolated_schema: psycopg.Connection,
) -> None:
    _apply_migrations(isolated_schema, _migration_files_before(OKF_MIGRATIONS[0]))
    _apply_migrations(isolated_schema, OKF_MIGRATIONS)
    _assert_okf_schema(isolated_schema)


def _assert_append_only_rejects_statement(
    connection: psycopg.Connection, statement: str, parameters: tuple[object, ...]
) -> None:
    with pytest.raises(
        psycopg.errors.RaiseException,
        match=APPEND_ONLY_ERROR_PATTERN,
    ):
        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute(statement, parameters)


def _assert_invalid_failure_category_code_pair(
    connection: psycopg.Connection,
    insert_sql: str,
    failure_category: str,
    failure_code: str,
) -> None:
    invalid_values = (
        uuid.uuid4(),
        uuid.uuid4(),
        failure_category,
        failure_code,
        "scope_lock",
        True,
        1,
        "{}",
        "b" * 64,
        "{}",
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute(insert_sql, invalid_values)


def _failure_audit_insert_sql() -> str:
    return (
        "INSERT INTO okf_rebuild_failure_audit "
        "(audit_id, rebuild_run_id, failure_category, failure_code, failure_phase, "
        "rollback_confirmed, scope_count, scope_manifest, scope_manifest_sha256, diagnostic) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb)"
    )


def _insert_failure_audit_record(
    connection: psycopg.Connection,
) -> tuple[uuid.UUID, str]:
    audit_id = uuid.uuid4()
    insert_sql = _failure_audit_insert_sql()
    values = (
        audit_id,
        uuid.uuid4(),
        "scope_validation",
        "unregistered_document_version",
        "scope_lock",
        True,
        1,
        "{}",
        "a" * 64,
        "{}",
    )
    with connection.cursor() as cursor:
        cursor.execute(insert_sql, values)
    return audit_id, insert_sql


def _assert_failure_audit_record_is_unchanged(
    connection: psycopg.Connection, audit_id: uuid.UUID
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT failure_category, failure_code, failure_phase "
            "FROM okf_rebuild_failure_audit WHERE audit_id = %s",
            (audit_id,),
        )
        assert cursor.fetchone() == (
            "scope_validation",
            "unregistered_document_version",
            "scope_lock",
        )


@pytest.mark.integration
def test_failure_audit_is_append_only_and_rejects_invalid_category_code_pairs(
    isolated_schema: psycopg.Connection,
) -> None:
    _apply_migrations(
        isolated_schema,
        tuple(migration.name for migration in sorted(MIGRATIONS_DIR.glob("*.sql"))),
    )
    audit_id, insert_sql = _insert_failure_audit_record(isolated_schema)
    for statement, parameters in (
        (
            "UPDATE okf_rebuild_failure_audit SET failure_phase = 'scope_lock' "
            "WHERE audit_id = %s",
            (audit_id,),
        ),
        ("DELETE FROM okf_rebuild_failure_audit WHERE audit_id = %s", (audit_id,)),
        ("TRUNCATE okf_rebuild_failure_audit", ()),
    ):
        _assert_append_only_rejects_statement(isolated_schema, statement, parameters)
    _assert_failure_audit_record_is_unchanged(isolated_schema, audit_id)
    for failure_category, failure_code in (
        ("scope_validation", "database_error"),
        ("database", "internal_failure"),
    ):
        _assert_invalid_failure_category_code_pair(
            isolated_schema, insert_sql, failure_category, failure_code
        )


@pytest.mark.integration
def test_okf_migrations_are_idempotent(isolated_schema: psycopg.Connection) -> None:
    _apply_migrations(isolated_schema, _migration_files_before(OKF_MIGRATIONS[0]))
    _apply_migrations(isolated_schema, OKF_MIGRATIONS)
    _apply_migrations(isolated_schema, OKF_MIGRATIONS)
    _assert_okf_schema(isolated_schema)


def _apply_full_migration_sequence(connection: psycopg.Connection) -> None:
    """Apply the authoritative ordered migration catalog to reach final state."""
    _apply_migrations(connection, FULL_MIGRATION_CATALOG)


def _assert_reapply_rejects_drift(
    isolated_schema: psycopg.Connection, drift_sql: str
) -> None:
    """Apply full sequence, introduce drift, then verify 019 reapplication fails.

    The drift must leave the schema classified as ``final`` (not ``partial``) so
    that the final-branch validation runs and catches the drift.  This means the
    drift SQL must modify a property that the ``final_signature`` classification
    does NOT check (e.g. function source, trigger shape, index indoption,
    constraint body) while keeping the object itself in place.
    """
    _apply_full_migration_sequence(isolated_schema)
    with isolated_schema.cursor() as cursor:
        cursor.execute(drift_sql)
    with pytest.raises(
        psycopg.errors.RaiseException, match="e2a_preflight_final_catalog_drift"
    ):
        _apply_migrations(isolated_schema, ("019_e2a_materialization_contract.sql",))


@pytest.mark.integration
def test_final_reapply_rejects_control_plane_function_drift(
    isolated_schema: psycopg.Connection,
) -> None:
    """Replacing the append-only guard function body must be rejected on reapplication.

    The function still exists (so ``final_signature`` stays true), but the source
    no longer matches (so ``append_only_function_source_matches`` is false).  The
    final-branch check at line 1181 catches this.
    """
    _assert_reapply_rejects_drift(
        isolated_schema,
        "CREATE OR REPLACE FUNCTION prevent_okf_rebuild_failure_audit_mutation() "
        "RETURNS trigger LANGUAGE plpgsql AS $$BEGIN RAISE EXCEPTION 'tampered'; END;$$",
    )


@pytest.mark.integration
def test_final_reapply_rejects_trigger_drift(
    isolated_schema: psycopg.Connection,
) -> None:
    """Dropping the append-only trigger must be rejected on reapplication.

    Triggers are not checked in ``final_signature`` classification, so the schema
    stays classified as ``final``.  The final-branch trigger shape check at line
    1805 catches this.
    """
    _assert_reapply_rejects_drift(
        isolated_schema,
        "DROP TRIGGER trg_okf_rebuild_failure_audit_append_only "
        "ON okf_rebuild_failure_audit",
    )


@pytest.mark.integration
def test_final_reapply_rejects_index_drift(
    isolated_schema: psycopg.Connection,
) -> None:
    """Recreating a validated index with wrong indoption must be rejected.

    The index still exists (so ``final_signature`` stays true), but the indoption
    no longer matches. PostgreSQL 16 ``DESC`` yields indoption=3 (DESC+NULLS_FIRST
    because NULLS_FIRST is the default for DESC), while ASC yields indoption=0.
    The final-branch index inventory check at line 1697 catches this.
    """
    _assert_reapply_rejects_drift(
        isolated_schema,
        "DROP INDEX idx_okf_rebuild_failure_audit_occurred_at; "
        "CREATE INDEX idx_okf_rebuild_failure_audit_occurred_at "
        "ON okf_rebuild_failure_audit (occurred_at)",
    )


@pytest.mark.integration
def test_final_reapply_rejects_constraint_drift(
    isolated_schema: psycopg.Connection,
) -> None:
    """Recreating a validated CHECK constraint with wrong body must be rejected.

    The constraint still exists and is validated (so ``final_signature`` stays
    true), but the body no longer matches.  The final-branch CHECK constraint
    body comparison at line 1188 catches this.
    """
    _assert_reapply_rejects_drift(
        isolated_schema,
        "ALTER TABLE evidence_links DROP CONSTRAINT chk_evidence_links_manual_projection, "
        "ADD CONSTRAINT chk_evidence_links_manual_projection CHECK (true)",
    )
