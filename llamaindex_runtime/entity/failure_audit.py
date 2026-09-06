"""Append-only E2b failure-audit writer (Phase 16-09).

``E2bFailureAudit.write`` is invoked AFTER the primary transaction has been
rolled back and closed. It opens an independent FRESH connection and appends
exactly one row to the append-only ``okf_e2b_failure_audit`` table (migration
020). The Phase 15 ``okf_rebuild_failure_audit`` table is never written.

Diagnostics are redacted: only the truncated ``error_type`` class name and a
redacted scope manifest (owner scope plus the failing document/version ids)
reach the connection; the failure message and any connection-string/credential
text inside it never leak into parameters.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from .contracts import canonical_json_sha256


class _Connection(Protocol):
    def cursor(self) -> object: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...


class _Cursor(Protocol):
    def execute(self, statement: str, parameters: object | None = None) -> None: ...


@dataclass(frozen=True)
class AuditWriteResult:
    """Outcome of one append-only E2b failure-audit write."""

    outcome: str


class E2bFailureAudit:
    """Writer for the migration-020 append-only ``okf_e2b_failure_audit`` row."""

    def write(
        self,
        connection_factory: Callable[[], _Connection],
        scope: object,
        failure: BaseException,
    ) -> AuditWriteResult:
        """Open a fresh connection and append one redacted audit row.

        The caller (the materialization repository) has already rolled back and
        closed the primary connection. Only ``okf_e2b_failure_audit`` is ever
        written; ``okf_rebuild_failure_audit`` is never touched.
        """
        try:
            connection = connection_factory()
        except Exception:
            return AuditWriteResult("failed")
        try:
            cursor = connection.cursor()
            _insert_failure_audit(cursor, scope, failure)
        except Exception:
            # Fresh-transaction insert/cursor failure: roll the fresh audit
            # transaction back, then close regardless of whether the rollback
            # itself raised, and report a truthful ``failed`` without leaking.
            _rollback_quietly(connection)
            _close_quietly(connection)
            return AuditWriteResult("failed")
        try:
            connection.commit()
        except Exception:
            # Commit outcome is ambiguous on the fresh transaction: close the
            # connection WITHOUT rolling back and report ``outcome_unknown``.
            _close_quietly(connection)
            return AuditWriteResult("outcome_unknown")
        close_confirmed = _close_quietly(connection)
        if not close_confirmed:
            return AuditWriteResult("written_cleanup_unconfirmed")
        return AuditWriteResult("written")


def _insert_failure_audit(
    cursor: _Cursor, scope: object, failure: BaseException
) -> None:
    """Insert one row with migration-020 columns and redacted diagnostics."""
    scope_manifest = _scope_manifest(scope)
    diagnostic = _diagnostic(failure)
    cursor.execute(
        "INSERT INTO okf_e2b_failure_audit ("
        "audit_id, e2b_run_id, failure_phase, failure_code, rollback_confirmed, "
        "scope_count, scope_manifest, scope_manifest_sha256, failing_doc_id, "
        "failing_version_id, diagnostic"
        ") VALUES (gen_random_uuid(), gen_random_uuid(), %s, %s, %s, %s, "
        "%s::jsonb, %s, %s, %s, %s::jsonb)",
        (
            "entity_materialization",
            "internal_failure",
            True,
            1,
            json.dumps(scope_manifest, sort_keys=True, ensure_ascii=False),
            canonical_json_sha256(scope_manifest),
            getattr(scope, "document_id"),
            getattr(scope, "version_id"),
            json.dumps(diagnostic, sort_keys=True, ensure_ascii=False),
        ),
    )


def _scope_manifest(scope: object) -> Mapping[str, object]:
    """Redacted scope manifest: owner scope plus the failing doc/version ids."""
    return {
        "schema_version": 1,
        "owner_scope": getattr(scope, "e2b_owner_scope"),
        "document_id": getattr(scope, "document_id"),
        "version_id": getattr(scope, "version_id"),
    }


def _diagnostic(failure: BaseException) -> Mapping[str, object]:
    """Redacted diagnostic: only the truncated error-type class name."""
    return {"error_type": type(failure).__name__[:64]}


def _close_quietly(connection: _Connection) -> bool:
    try:
        connection.close()
    except Exception:
        return False
    return True


def _rollback_quietly(connection: _Connection) -> bool:
    try:
        connection.rollback()
    except Exception:
        return False
    return True


__all__ = ["AuditWriteResult", "E2bFailureAudit"]
