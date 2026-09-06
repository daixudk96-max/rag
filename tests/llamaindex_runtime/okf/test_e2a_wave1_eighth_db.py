"""Static and isolated regressions for Wave 1 eighth database remediation.

These tests never open PostgreSQL or Docker.  They exercise only lexical and
connector-boundary behavior through injected fakes.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from llamaindex_runtime.okf import e2a_disposable_acceptance as acceptance
from scripts._rebuild_database_connection import DisposablePostgresqlTarget

_MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "llamaindex_runtime"
    / "registry"
    / "migrations"
    / "019_e2a_materialization_contract.sql"
)
_TARGET = DisposablePostgresqlTarget(
    host="127.0.0.1",
    hostaddr="127.0.0.1",
    port=55432,
    dbname="e2a_disposable",
    user="acceptance",
    password="redacted",
)


class _Authority:
    authorized = True


class _NoAuthority:
    authorized = False


class _Cursor:
    def __init__(self, identity: tuple[object, ...]) -> None:
        self.identity = identity
        self.statements: list[str] = []

    def execute(self, statement: str, *_: object) -> None:
        self.statements.append(statement)

    def fetchone(self) -> tuple[object, ...]:
        return self.identity


class _Connection:
    def __init__(self, identity: tuple[object, ...]) -> None:
        self.cursor_value = _Cursor(identity)
        self.commits = 0
        self.rollbacks = 0
        self.closes = 0

    def cursor(self) -> _Cursor:
        return self.cursor_value

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closes += 1


class _CatalogCursor:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.rows = rows

    def execute(self, *_: object) -> None:
        pass

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.rows


def test_migration_019_does_not_use_invalid_pg_catalog_scalar_or_array_aliases() -> (
    None
):
    sql = _MIGRATION.read_text(encoding="utf-8")

    for invalid in (
        "pg_catalog.boolean",
        "pg_catalog.integer",
        "pg_catalog.smallint[]",
    ):
        assert invalid not in sql


def test_fresh_signature_checks_retained_triggers_before_the_ddl_boundary() -> None:
    sql = _MIGRATION.read_text(encoding="utf-8")
    preflight, _ = sql.split(
        "-- Only the exact fresh signature reaches this DDL phase.", maxsplit=1
    )

    trigger_check = preflight.index("fresh_trigger_shape")
    fresh_signature = preflight.index("AND fresh_trigger_shape INTO fresh_signature")
    assert trigger_check < fresh_signature
    assert "trg_okf_rebuild_failure_audit_append_only" in preflight
    assert "trg_okf_rebuild_failure_audit_no_truncate" in preflight
    for metadata in (
        "trigger_row.tgfoid",
        "trigger_row.tgtype",
        "trigger_row.tgenabled",
        "trigger_row.tgisinternal",
        "trigger_row.tgargs",
        "trigger_row.tgqual",
        "trigger_row.tgattr",
        "trigger_row.tgconstraint",
    ):
        assert metadata in preflight


def test_final_signature_and_detailed_validation_include_every_retained_index() -> None:
    sql = _MIGRATION.read_text(encoding="utf-8")
    signature = sql.split("INTO final_signature;", maxsplit=1)[0]
    detailed = sql.split("WITH expected_final_indexes", maxsplit=1)[1]

    for index_name in (
        "idx_evidence_links_span",
        "idx_evidence_links_evidence",
        "idx_okf_rebuild_failure_audit_occurred_at",
        "idx_okf_rebuild_failure_audit_scope",
    ):
        assert index_name in signature
        assert index_name in detailed
        assert f"CREATE INDEX {index_name}" not in sql
        assert f"CREATE UNIQUE INDEX {index_name}" not in sql


def test_migration_index_vectors_use_zero_origin_offsets_and_normalized_predicates() -> (
    None
):
    sql = _MIGRATION.read_text(encoding="utf-8")

    assert "pg_catalog.unnest(expected_final_indexes.columns) WITH ORDINALITY" in sql
    for vector in ("indkey", "indclass", "indcollation", "indoption"):
        assert f"index_row.{vector}[column_row.ordinality - 1]" in sql
    assert not re.search(
        r"index_row\.(?:indkey|indclass|indcollation|indoption)\[column_row\.ordinality\]",
        sql,
    )
    assert (
        "WHEN expected_final_indexes.index_name = 'idx_okf_rebuild_failure_audit_occurred_at'"
        in sql
    )
    assert "THEN 1::smallint" in sql
    assert "ELSE 0::smallint" in sql
    assert "e2a_normalize_expression_predicate_actual" in sql
    assert "e2a_normalize_expression_predicate_expected" in sql


def test_old_check_and_partial_predicates_accept_only_safe_outer_wrappers() -> None:
    old_five_phase_body = (
        "failure_phase = ANY (ARRAY['target_validation'::text, "
        "'scope_lock'::text, 'span_reconciliation'::text, "
        "'success_log_write'::text, 'transaction_commit'::text])"
    )

    assert acceptance._expressions_match(
        f"((({old_five_phase_body})))", old_five_phase_body
    )
    assert acceptance._expressions_match(
        "(((evidence_id IS NOT NULL)))", "evidence_id IS NOT NULL"
    )
    assert not acceptance._expressions_match(
        "(evidence_id IS NULL)", "evidence_id IS NOT NULL"
    )


@pytest.mark.parametrize(
    "value", ("$$ body $$", "$_tag$ body $_tag$", "$Tag9_$ body $Tag9_$")
)
def test_dollar_lexing_accepts_only_postgresql_valid_delimiters(value: str) -> None:
    assert acceptance._definition(value) == value


@pytest.mark.parametrize(
    "value", ("$1$ body $1$", "$9name$ body $9name$", "value */ other")
)
def test_dollar_lexing_and_stray_block_comment_closers_fail_closed(value: str) -> None:
    with pytest.raises(ValueError, match="^executed_failed$"):
        acceptance._definition(value)


def test_authorized_flow_passes_the_same_validated_target_to_all_four_opens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received_targets: list[object] = []
    connections: list[_Connection] = []

    def factory(target: object) -> _Connection:
        received_targets.append(target)
        connection = _Connection((_TARGET.dbname, "public"))
        connections.append(connection)
        return connection

    monkeypatch.setattr(
        acceptance, "parse_disposable_postgresql_target", lambda *_: _TARGET
    )
    monkeypatch.setattr(acceptance, "_assert_019_catalog_shape", lambda _: None)
    monkeypatch.setattr(
        acceptance, "_run_rollback_only_probe", lambda _connection, _cursor: None
    )

    assert (
        acceptance.run_disposable_migration_acceptance(
            _Authority(), "postgresql://ignored", _TARGET.dbname, factory
        )
        == "executed_pass"
    )
    assert received_targets == [_TARGET, _TARGET, _TARGET, _TARGET]
    assert all(target is _TARGET for target in received_targets)
    assert all(
        connection.cursor_value.statements[0]
        == "SELECT current_database(), current_schema()"
        for connection in connections
    )


@pytest.mark.parametrize(
    "identity", (("other_database", "public"), (_TARGET.dbname, "other"))
)
def test_target_attestation_rejects_wrong_database_or_schema_before_migration(
    monkeypatch: pytest.MonkeyPatch, identity: tuple[object, ...]
) -> None:
    connection = _Connection(identity)
    monkeypatch.setattr(
        acceptance, "parse_disposable_postgresql_target", lambda *_: _TARGET
    )

    result = acceptance.run_disposable_migration_acceptance(
        _Authority(), "postgresql://ignored", _TARGET.dbname, lambda _: connection
    )

    assert result == "executed_failed"
    assert connection.cursor_value.statements == [
        "SELECT current_database(), current_schema()"
    ]
    assert connection.rollbacks == 1
    assert connection.closes == 1


def test_unauthorized_selector_skips_parser_and_connector_even_when_live_gated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def parser(*_: object) -> DisposablePostgresqlTarget:
        calls.append("parser")
        return _TARGET

    def connector(*_: object) -> _Connection:
        calls.append("connector")
        return _Connection((_TARGET.dbname, "public"))

    monkeypatch.setattr(acceptance, "parse_disposable_postgresql_target", parser)

    assert (
        acceptance.run_current_disposable_postgresql_acceptance(
            _NoAuthority(), "not-parsed", "not-connected", connector
        )
        == "blocked_not_executed"
    )
    assert calls == []


def _backing_row(
    expectation: acceptance._ConstraintExpectation, relation_oid: int
) -> tuple[object, ...]:
    key_count = len(expectation.columns.split(","))
    return (
        expectation.table,
        expectation.name,
        expectation.contype,
        900,
        relation_oid,
        True,
        expectation.contype == "p",
        True,
        True,
        True,
        False,
        "btree",
        key_count,
        key_count,
        expectation.columns,
        "",
        "",
        True,
        "0" if key_count == 1 else ",".join("0" for _ in range(key_count)),
    )


@pytest.mark.parametrize(
    ("position", "value"),
    ((17, False), (18, "1")),
)
def test_backing_index_validation_rejects_opclass_collation_and_option_drift(
    position: int, value: object
) -> None:
    expectation = next(
        item
        for item in acceptance._EXPECTED_019_CONSTRAINT_ROWS
        if item.contype in {"p", "u"}
    )
    row = list(_backing_row(expectation, 101))
    row[position] = value

    with pytest.raises(ValueError, match="^executed_failed$"):
        acceptance._assert_backing_index_rows(
            _CatalogCursor([tuple(row)]), {expectation.table: 101}
        )
