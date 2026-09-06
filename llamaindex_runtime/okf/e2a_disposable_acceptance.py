"""Explicitly gated disposable migration-019 acceptance support.

This facade retains the historic import and monkeypatch surface while its lexer,
catalog contracts, catalog inspection, and connection execution live in focused
internal modules.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, Protocol, cast

from llamaindex_runtime.okf.e2a_disposable_catalog import (
    _assert_019_catalog_shape,
    _assert_backing_index_rows,
    _assert_column_rows,
    _assert_constraint_rows,
    _assert_index_rows,
    _assert_trigger_rows,
    _expected_relations,
    _relation_oids,
    _validate_constraint_row,
    _validate_index_row,
)
from llamaindex_runtime.okf.e2a_disposable_catalog_contracts import (
    _ConstraintExpectation,
    _EXPECTED_018_APPEND_ONLY_FUNCTION,
    _EXPECTED_018_TRIGGER_ROWS,
    _EXPECTED_019_COLUMNS,
    _EXPECTED_019_CONSTRAINT_DEFINITIONS,
    _EXPECTED_019_CONSTRAINT_ROWS,
    _EXPECTED_019_CONSTRAINTS,
    _EXPECTED_019_FK_KEYS,
    _EXPECTED_019_INDEX_DEFINITIONS,
    _EXPECTED_019_INDEX_ROWS,
    _EXPECTED_019_INDEXES,
    _FunctionExpectation,
    _IndexExpectation,
    _TriggerExpectation,
)
from llamaindex_runtime.okf.e2a_disposable_execution import (
    _ApplyRollbackFailure,
    _attest_connection_target,
    _Connection,
    _apply_catalog as _apply_catalog_implementation,
    _close,
    _ProbeRollbackFailure,
    _run_rollback_only_probe as _run_rollback_only_probe_implementation,
    _SEMANTIC_PROBE,
    _validate_catalog_filenames,
)
from llamaindex_runtime.okf.e2a_disposable_sql_lexer import (
    _append_token,
    _check,
    _check_body,
    _check_definitions_match,
    _definition,
    _dollar_delimiter,
    _expressions_match,
    _fk,
    _is_ascii_dollar_tag_continuation,
    _is_ascii_dollar_tag_start,
    _is_dollar_quote_eligible,
    _is_invalid_dollar_delimiter,
    _is_malformed_dollar_delimiter,
    _is_word_character,
    _is_wrapped_in_parentheses,
    _scan_quoted,
    _strip_outer_parentheses,
    _unique,
)
from llamaindex_runtime.registry.migration_catalog import FULL_MIGRATION_CATALOG
from scripts._rebuild_database_connection import (
    DisposablePostgresqlTarget,
    parse_disposable_postgresql_target,
    runtime_connection_factory,
)


__all__ = (
    "DisposableAcceptanceAuthority",
    "DisposablePostgresqlTarget",
    "FULL_MIGRATION_CATALOG",
    "parse_disposable_postgresql_target",
    "run_current_disposable_postgresql_acceptance",
    "run_disposable_migration_acceptance",
    "runtime_connection_factory",
    "_ApplyRollbackFailure",
    "_Connection",
    "_ConstraintExpectation",
    "_EXPECTED_018_APPEND_ONLY_FUNCTION",
    "_EXPECTED_018_TRIGGER_ROWS",
    "_EXPECTED_019_COLUMNS",
    "_EXPECTED_019_CONSTRAINT_DEFINITIONS",
    "_EXPECTED_019_CONSTRAINT_ROWS",
    "_EXPECTED_019_CONSTRAINTS",
    "_EXPECTED_019_FK_KEYS",
    "_EXPECTED_019_INDEX_DEFINITIONS",
    "_EXPECTED_019_INDEX_ROWS",
    "_EXPECTED_019_INDEXES",
    "_FunctionExpectation",
    "_IndexExpectation",
    "_ProbeRollbackFailure",
    "_SEMANTIC_PROBE",
    "_TriggerExpectation",
    "_append_token",
    "_apply_catalog",
    "_assert_019_catalog_shape",
    "_assert_backing_index_rows",
    "_assert_column_rows",
    "_assert_constraint_rows",
    "_assert_index_rows",
    "_assert_trigger_rows",
    "_attest_connection_target",
    "_check",
    "_check_body",
    "_check_definitions_match",
    "_close",
    "_definition",
    "_dollar_delimiter",
    "_expected_relations",
    "_expressions_match",
    "_fk",
    "_is_ascii_dollar_tag_continuation",
    "_is_ascii_dollar_tag_start",
    "_is_dollar_quote_eligible",
    "_is_invalid_dollar_delimiter",
    "_is_malformed_dollar_delimiter",
    "_is_word_character",
    "_is_wrapped_in_parentheses",
    "_relation_oids",
    "_run_rollback_only_probe",
    "_scan_quoted",
    "_strip_outer_parentheses",
    "_unique",
    "_validate_constraint_row",
    "_validate_index_row",
    "_verify_catalog",
)


class DisposableAcceptanceAuthority(Protocol):
    @property
    def authorized(self) -> bool: ...


class _DefaultConnectionFactory:
    pass


_DEFAULT_CONNECTION_FACTORY = _DefaultConnectionFactory()


def _apply_catalog(
    target: DisposablePostgresqlTarget,
    connection_factory: Callable[[DisposablePostgresqlTarget], _Connection],
    filenames: Iterable[str] = FULL_MIGRATION_CATALOG,
) -> None:
    """Validate before delegating while retaining historic facade monkeypatch seams."""
    selected_filenames = _validate_catalog_filenames(filenames)
    _apply_catalog_implementation(
        target,
        connection_factory,
        selected_filenames,
        attest_connection_target=_attest_connection_target,
        close=_close,
    )


def _run_rollback_only_probe(connection: _Connection, cursor: Any) -> None:
    """Run the facade-owned semantic probe through the extracted execution helper."""
    _run_rollback_only_probe_implementation(
        connection,
        cursor,
        semantic_probe=_SEMANTIC_PROBE,
    )


def run_disposable_migration_acceptance(
    authority: DisposableAcceptanceAuthority,
    target: str,
    expected_database: str,
    connection_factory: (
        Callable[[DisposablePostgresqlTarget], _Connection]
        | None
        | _DefaultConnectionFactory
    ) = _DEFAULT_CONNECTION_FACTORY,
) -> str:
    """Apply and inspect a separately authorized disposable database only."""
    try:
        authorized = authority.authorized
    except Exception:
        return "blocked_not_executed"
    if type(authorized) is not bool or authorized is not True:
        return "blocked_not_executed"
    factory = (
        runtime_connection_factory
        if connection_factory is _DEFAULT_CONNECTION_FACTORY
        else cast(
            Callable[[DisposablePostgresqlTarget], _Connection], connection_factory
        )
    )
    try:
        validated_target = parse_disposable_postgresql_target(target, expected_database)
        _apply_catalog(validated_target, factory)
        _verify_catalog(validated_target, factory)
        _apply_catalog(
            validated_target,
            factory,
            ("019_e2a_materialization_contract.sql",),
        )
        _verify_catalog(validated_target, factory)
    except _ApplyRollbackFailure:
        return "executed_apply_rollback_failed"
    except _ProbeRollbackFailure:
        return "executed_probe_rollback_failed"
    except Exception:
        return "executed_failed"
    return "executed_pass"


def run_current_disposable_postgresql_acceptance(
    authority: DisposableAcceptanceAuthority | None,
    target: str,
    expected_database: str,
    connection_factory: (
        Callable[[DisposablePostgresqlTarget], _Connection]
        | None
        | _DefaultConnectionFactory
    ) = _DEFAULT_CONNECTION_FACTORY,
) -> str:
    """Select the positive disposable path only after explicit current authority."""
    if authority is None:
        return "blocked_not_executed"
    return run_disposable_migration_acceptance(
        authority, target, expected_database, connection_factory
    )


def _verify_catalog(
    target: DisposablePostgresqlTarget,
    connection_factory: Callable[[DisposablePostgresqlTarget], _Connection],
) -> None:
    """Inspect the target with facade globals retained as monkeypatch seams."""
    connection: _Connection | None = None
    primary_failure: Exception | None = None
    probe_started = False
    try:
        connection = connection_factory(target)
        cursor: Any = connection.cursor()
        _attest_connection_target(cursor, target)
        _assert_019_catalog_shape(cursor)
        probe_started = True
        _run_rollback_only_probe(connection, cursor)
    except Exception as error:
        primary_failure = error
        if connection is not None and not probe_started:
            try:
                connection.rollback()
            except Exception as cleanup_error:
                raise error from cleanup_error
        raise
    finally:
        if connection is not None:
            try:
                _close(connection)
            except Exception as cleanup_error:
                if primary_failure is None:
                    raise
                if primary_failure.__cause__ is None:
                    raise primary_failure from cleanup_error
