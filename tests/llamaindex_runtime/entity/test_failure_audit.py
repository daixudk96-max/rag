"""RED tests for the E2b failure-audit writer (Phase 16-09, Task 1).

Freezes the planned ``E2bFailureAudit.write`` contract before any implementation
exists. ``write`` is called AFTER the primary transaction has been rolled back
and closed; it opens an independent FRESH connection and appends exactly one
row to the append-only ``okf_e2b_failure_audit`` table (migration 020). The
Phase 15 ``okf_rebuild_failure_audit`` table is never touched.

Redaction contract: only a truncated ``error_type`` class name plus a redacted
scope manifest ever reaches the connection; the failure message and any
connection-string/credential text inside it never leak into parameters.

Audit identity contract: ``audit_id`` AND ``e2b_run_id`` are BOTH per-event
server-generated ``gen_random_uuid()``. ``e2b_run_id`` is deliberately NOT a
scope-fixed deterministic id: migration 020 declares
``uq_okf_e2b_failure_audit_run`` UNIQUE on ``e2b_run_id`` and the audit table
is append-only, so the SAME document/version scope may fail repeatedly and each
failure must get a fresh, collision-free run id.

Cleanup contract: on a fresh-transaction audit insert/cursor failure the writer
rolls the fresh audit transaction back and closes it (and still closes and
returns a truthful ``failed`` outcome even when that rollback itself fails); on
a commit failure it returns ``outcome_unknown`` and closes the fresh connection;
on a post-commit close failure it returns ``written_cleanup_unconfirmed``. All
tests are pure: fake connections only, no database/model/network/env access.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from uuid import UUID

from llamaindex_runtime.entity.contracts import canonical_json_sha256
from llamaindex_runtime.entity.failure_audit import AuditWriteResult, E2bFailureAudit
from llamaindex_runtime.entity.materialization_repository import E2bDocumentScope

_DOC = str(UUID(int=1))
_VER = str(UUID(int=2))
_SCOPE = f"okf:e2b:{_DOC}:{_VER}"


def _scope() -> E2bDocumentScope:
    return E2bDocumentScope(document_id=_DOC, version_id=_VER)


def _normalized(statement: str) -> str:
    return " ".join(statement.lower().split())


def _values_clause(statement: str) -> str:
    return statement.lower().split("values", 1)[1]


def _values_by_column(
    statement: str, parameters: tuple[object, ...]
) -> dict[str, object]:
    """Map migration-020 columns to their VALUES expression/parameter."""
    lowered = statement.lower()
    columns_start = lowered.index("(") + 1
    columns_end = lowered.index(")")
    columns = [c.strip() for c in lowered[columns_start:columns_end].split(",")]
    values = _values_clause(lowered)
    values_open = values.index("(") + 1
    values_close = values.rindex(")")
    expressions = [e.strip() for e in values[values_open:values_close].split(",")]
    param_iter = iter(parameters)
    mapped: dict[str, object] = {}
    for column, expression in zip(columns, expressions):
        if expression == "gen_random_uuid()":
            mapped[column] = "gen_random_uuid()"
        else:
            mapped[column] = next(param_iter)
    return mapped


def _audit_factory(
    events: list[str], connection: _AuditConnection
) -> Callable[[], _AuditConnection]:
    """Named factory that records the fresh-connection open event."""

    def factory() -> _AuditConnection:
        events.append("audit.connect")
        return connection

    return factory


class _AuditCursor:
    def __init__(self, connection: _AuditConnection) -> None:
        self.connection = connection
        self.executed: list[tuple[str, object]] = []

    def execute(self, statement: str, parameters: object | None = None) -> None:
        self.executed.append((statement, parameters))
        self.connection.events.append("audit.insert")

    def fetchall(self) -> list[dict[str, object]]:
        return []

    def fetchone(self) -> None:
        return None


class _AuditConnection:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.committed = False
        self.closed = False
        self.rolled_back = False
        self.cursor_value: _AuditCursor | None = None

    def cursor(self) -> _AuditCursor:
        self.cursor_value = _AuditCursor(self)
        return self.cursor_value

    def commit(self) -> None:
        self.events.append("audit.commit")
        self.committed = True

    def rollback(self) -> None:
        self.events.append("audit.rollback")
        self.rolled_back = True

    def close(self) -> None:
        self.events.append("audit.close")
        self.closed = True


class _InsertFailCursor(_AuditCursor):
    def execute(self, statement: str, parameters: object | None = None) -> None:
        del statement, parameters
        self.connection.events.append("audit.insert")
        raise RuntimeError("audit insert failed")


class _InsertFailConnection(_AuditConnection):
    def cursor(self) -> _InsertFailCursor:
        self.cursor_value = _InsertFailCursor(self)
        return self.cursor_value


class _RollbackFailConnection(_InsertFailConnection):
    def rollback(self) -> None:
        self.events.append("audit.rollback")
        self.rolled_back = True
        raise RuntimeError("audit rollback failed")


class _CommitFailConnection(_AuditConnection):
    def commit(self) -> None:
        self.events.append("audit.commit")
        self.committed = True
        raise RuntimeError("audit commit failed")


class _CloseFailConnection(_AuditConnection):
    def close(self) -> None:
        self.events.append("audit.close")
        raise RuntimeError("close failed")


def test_write_appends_only_okf_e2b_failure_audit_on_fresh_connection() -> None:
    events: list[str] = []
    audit = _AuditConnection(events)

    def factory() -> _AuditConnection:
        events.append("audit.connect")
        return audit

    result = E2bFailureAudit().write(factory, _scope(), RuntimeError("boom"))

    assert result.outcome == "written"
    statement, parameters = audit.cursor_value.executed[0]
    assert "insert into okf_e2b_failure_audit" in _normalized(statement)
    assert "okf_rebuild_failure_audit" not in statement.lower()
    assert isinstance(parameters, tuple)
    # failing_doc_id / failing_version_id carry the failing scope.
    assert _DOC in parameters
    assert _VER in parameters
    assert audit.committed is True
    assert audit.closed is True
    # A successful write must NOT roll the fresh audit transaction back.
    assert audit.rolled_back is False
    assert events == ["audit.connect", "audit.insert", "audit.commit", "audit.close"]


def test_write_persists_only_redacted_error_type_not_failure_message() -> None:
    secret = "SECRET_VALUE=hunter2-postgres-connection-string"
    failure = RuntimeError(f"driver leaked {secret}")
    audit = _AuditConnection([])

    result = E2bFailureAudit().write(lambda: audit, _scope(), failure)

    assert result.outcome == "written"
    statement, parameters = audit.cursor_value.executed[0]
    assert "insert into okf_e2b_failure_audit" in _normalized(statement)
    rendered = repr(parameters)
    assert secret not in rendered
    assert "RuntimeError" in rendered
    assert "error_type" in rendered
    assert _SCOPE in rendered
    assert "owner_scope" in rendered


def test_write_returns_failed_when_connection_factory_raises() -> None:
    def factory() -> _AuditConnection:
        raise RuntimeError("fresh connection unavailable")

    result = E2bFailureAudit().write(factory, _scope(), RuntimeError("boom"))

    assert isinstance(result, AuditWriteResult)
    assert result.outcome == "failed"


def test_write_returns_failed_when_audit_insert_raises_and_rolls_back_fresh_txn() -> (
    None
):
    events: list[str] = []
    audit = _InsertFailConnection(events)

    result = E2bFailureAudit().write(
        _audit_factory(events, audit), _scope(), RuntimeError("boom")
    )

    assert result.outcome == "failed"
    # The fresh audit transaction is explicitly rolled back before close.
    assert audit.rolled_back is True
    assert audit.closed is True
    assert audit.committed is False
    assert events == [
        "audit.connect",
        "audit.insert",
        "audit.rollback",
        "audit.close",
    ]


def test_write_audit_and_run_ids_are_server_generated_random_uuids() -> None:
    audit = _AuditConnection([])

    result = E2bFailureAudit().write(lambda: audit, _scope(), RuntimeError("boom"))

    assert result.outcome == "written"
    statement, parameters = audit.cursor_value.executed[0]
    mapped = _values_by_column(statement, parameters)
    # Both audit_id and e2b_run_id are per-event server-generated random UUIDs.
    # e2b_run_id must NOT be scope-fixed: the audit table is append-only and
    # migration 020 has UNIQUE on e2b_run_id, so repeated failures of the same
    # document/version need a fresh, collision-free run id each time.
    assert mapped["audit_id"] == "gen_random_uuid()"
    assert mapped["e2b_run_id"] == "gen_random_uuid()"
    random_values = [
        expression
        for expression in mapped.values()
        if expression == "gen_random_uuid()"
    ]
    assert random_values == ["gen_random_uuid()", "gen_random_uuid()"]


def test_write_commit_failure_returns_outcome_unknown_and_closes() -> None:
    events: list[str] = []
    audit = _CommitFailConnection(events)

    result = E2bFailureAudit().write(
        _audit_factory(events, audit), _scope(), RuntimeError("boom")
    )

    assert result.outcome == "outcome_unknown"
    assert audit.committed is True
    # A commit failure must still close the fresh connection.
    assert audit.closed is True
    # The failure message must never leak into the result.
    assert "audit commit failed" not in repr(result)
    assert "boom" not in repr(result)


def test_write_rollback_failure_still_closes_and_returns_failed_without_raising() -> (
    None
):
    events: list[str] = []
    audit = _RollbackFailConnection(events)

    result = E2bFailureAudit().write(
        _audit_factory(events, audit), _scope(), RuntimeError("boom")
    )

    assert result.outcome == "failed"
    assert audit.rolled_back is True
    # Even when the rollback of the fresh audit txn fails, close still happens.
    assert audit.closed is True
    assert "audit rollback failed" not in repr(result)


def test_write_close_failure_returns_written_cleanup_unconfirmed() -> None:
    audit = _CloseFailConnection([])

    result = E2bFailureAudit().write(lambda: audit, _scope(), RuntimeError("boom"))

    assert result.outcome == "written_cleanup_unconfirmed"
    assert audit.committed is True


def test_write_matches_exact_migration_020_checks() -> None:
    audit = _AuditConnection([])

    result = E2bFailureAudit().write(lambda: audit, _scope(), RuntimeError("boom"))

    assert result.outcome == "written"
    statement, parameters = audit.cursor_value.executed[0]
    mapped = _values_by_column(statement, parameters)
    # Migration 020 CHECK constraints are exact: rollback_confirmed is strictly
    # True, scope_count >= 1 is satisfied with exactly 1, and the failing scope
    # pair is present.
    assert mapped["rollback_confirmed"] is True
    assert mapped["scope_count"] == 1
    assert mapped["failing_doc_id"] == _DOC
    assert mapped["failing_version_id"] == _VER


def test_write_scope_manifest_is_deterministic_with_canonical_hash() -> None:
    audit = _AuditConnection([])

    result = E2bFailureAudit().write(lambda: audit, _scope(), RuntimeError("boom"))

    assert result.outcome == "written"
    statement, parameters = audit.cursor_value.executed[0]
    mapped = _values_by_column(statement, parameters)
    manifest = json.loads(str(mapped["scope_manifest"]))
    assert manifest == {
        "schema_version": 1,
        "owner_scope": _SCOPE,
        "document_id": _DOC,
        "version_id": _VER,
    }
    expected_hash = canonical_json_sha256(manifest)
    assert mapped["scope_manifest_sha256"] == expected_hash
    assert re.fullmatch(r"[0-9a-f]{64}", expected_hash)


def test_write_diagnostic_contains_only_error_type_not_message_or_credential() -> None:
    secret = "PGPASSWORD=hunter2-postgres"
    failure = RuntimeError(f"driver leaked {secret}")
    audit = _AuditConnection([])

    result = E2bFailureAudit().write(lambda: audit, _scope(), failure)

    assert result.outcome == "written"
    statement, parameters = audit.cursor_value.executed[0]
    mapped = _values_by_column(statement, parameters)
    rendered = repr(parameters)
    assert secret not in rendered
    assert "driver leaked" not in rendered
    diagnostic = json.loads(str(mapped["diagnostic"]))
    assert set(diagnostic) == {"error_type"}
    assert diagnostic["error_type"] == "RuntimeError"
