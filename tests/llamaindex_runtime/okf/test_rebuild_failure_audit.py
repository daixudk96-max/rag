"""No-database regression coverage for rebuild failure-audit contracts."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import UUID

import psycopg
import pytest

from llamaindex_runtime.okf.parser import OKFDocument

from ._rebuild_failure_audit_testkit import (
    _admitted,
    _Connection,
    _Cursor,
    _document,
    _load_module,
)
from ._rebuild_integration_testkit import MIGRATION_NAMES

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "rebuild_from_okf.py"
MIGRATION = (
    REPO_ROOT
    / "llamaindex_runtime"
    / "registry"
    / "migrations"
    / "018_okf_rebuild_failure_audit.sql"
)


def _assert_failure_audit_schema(source: str) -> None:
    assert "CREATE TABLE IF NOT EXISTS okf_rebuild_failure_audit" in source
    assert (
        "CREATE OR REPLACE FUNCTION prevent_okf_rebuild_failure_audit_mutation"
        in source
    )
    assert "BEFORE UPDATE OR DELETE ON okf_rebuild_failure_audit" in source
    assert "BEFORE TRUNCATE ON okf_rebuild_failure_audit" in source
    assert "FOR EACH ROW" in source
    assert "FOR EACH STATEMENT" in source
    assert "RAISE EXCEPTION 'okf_rebuild_failure_audit is append-only'" in source
    assert "DROP TRIGGER IF EXISTS trg_okf_rebuild_failure_audit_append_only" in source
    assert "CREATE TRIGGER trg_okf_rebuild_failure_audit_append_only" in source
    assert "chk_okf_rebuild_failure_audit_category_code_pair" in source
    assert "failure_category = 'scope_validation'" in source
    assert "failure_code = 'unregistered_document_version'" in source
    assert (
        "failure_category = 'scope_validation'\n            AND failure_code = 'database_error'"
        not in source
    )
    for column in (
        "audit_id UUID PRIMARY KEY",
        "rebuild_run_id UUID NOT NULL UNIQUE",
        "scope_manifest JSONB NOT NULL",
        "scope_manifest_sha256 CHAR(64) NOT NULL",
        "failing_doc_id UUID",
        "failing_version_id UUID",
    ):
        assert column in source
    assert "jsonb_typeof(scope_manifest) = 'object'" in source
    assert "scope_count >= 1" in source
    assert "failing_doc_id IS NULL AND failing_version_id IS NULL" in source
    assert "^[0-9a-f]{64}$" in source


def _assert_failure_audit_registration() -> None:
    import run_migrations
    from llamaindex_runtime.registry.migration_catalog import FULL_MIGRATION_CATALOG

    migration = "018_okf_rebuild_failure_audit.sql"
    required_predecessors = (
        "015_okf_sync_state.sql",
        "016_entity_mentions.sql",
        "017_relation_qualifiers.sql",
    )
    assert run_migrations.KEY_MIGRATIONS is FULL_MIGRATION_CATALOG
    assert migration in FULL_MIGRATION_CATALOG
    migration_index = FULL_MIGRATION_CATALOG.index(migration)
    assert all(
        FULL_MIGRATION_CATALOG.index(name) < migration_index
        for name in required_predecessors
    )
    assert migration in MIGRATION_NAMES
    test_index = MIGRATION_NAMES.index(migration)
    assert all(
        MIGRATION_NAMES.index(name) < test_index for name in required_predecessors
    )


def _assert_failure_audit_script_contract() -> None:
    script_source = SCRIPT.read_text(encoding="utf-8")
    assert (
        'raise _database_failure(error, "scope_lock", doc_id, version_id) from None'
        in script_source
    )
    assert script_source.count(") from None") >= 3
    assert script_source.count("raise SystemExit(2) from None") == 2
    assert (
        'LOGGER.warning("event=okf_rebuild_failure_audit_write_failed")'
        in script_source
    )
    assert "LOGGER.exception" not in script_source


def test_failure_audit_migration_and_general_lists_are_locked() -> None:
    _assert_failure_audit_schema(MIGRATION.read_text(encoding="utf-8"))
    _assert_failure_audit_registration()
    _assert_failure_audit_script_contract()


def test_scope_manifest_is_stable_sorted_and_redacted() -> None:
    module = _load_module()
    first = _document()
    second = replace(
        _document(),
        frontmatter=replace(
            first.frontmatter,
            doc_id="00000000-0000-0000-0000-000000000001",
            version_id="00000000-0000-0000-0000-000000000002",
        ),
        canonical_hash="b" * 64,
        spans=(first.spans[0], first.spans[0]),
    )

    manifest, manifest_hash = module._scope_manifest(_admitted(module, first, second))
    reversed_manifest, reversed_hash = module._scope_manifest(
        _admitted(module, second, first)
    )

    assert manifest == reversed_manifest
    assert manifest_hash == reversed_hash
    assert manifest == {
        "schema_version": 1,
        "scopes": [
            {
                "doc_id": "00000000-0000-0000-0000-000000000001",
                "version_id": "00000000-0000-0000-0000-000000000002",
                "canonical_hash": "b" * 64,
                "span_count": 2,
            },
            {
                "doc_id": "00000000-0000-0000-0000-000000000002",
                "version_id": "00000000-0000-0000-0000-000000000001",
                "canonical_hash": "a" * 64,
                "span_count": 1,
            },
        ],
    }
    rendered = repr(manifest)
    assert "never-in-a-manifest" not in rendered
    assert "must never persist" not in rendered
    assert len(manifest_hash) == 64


def test_failure_taxonomy_uses_allowlisted_safe_codes() -> None:
    module = _load_module()
    doc_id = UUID("00000000-0000-0000-0000-000000000001")
    version_id = UUID("00000000-0000-0000-0000-000000000002")

    integrity = module._database_failure(
        psycopg.IntegrityError(), "span_reconciliation", doc_id, version_id
    )
    database = module._database_failure(
        psycopg.OperationalError(), "success_log_write", doc_id, version_id
    )

    assert module._safe_failure_details(integrity, "scope_lock") == (
        "integrity",
        "integrity_error",
        "span_reconciliation",
        doc_id,
        version_id,
    )
    assert module._safe_failure_details(database, "scope_lock") == (
        "database",
        "database_error",
        "success_log_write",
        doc_id,
        version_id,
    )
    assert module._safe_failure_details(
        RuntimeError("unsafe details"), "transaction_commit"
    ) == ("internal", "internal_failure", "transaction_commit", None, None)


def test_database_failure_wrapper_hides_driver_cause() -> None:
    module = _load_module()
    document = _document()
    doc_id = UUID(document.frontmatter.doc_id or "")
    version_id = UUID(document.frontmatter.version_id or "")

    class _FailingCursor(_Cursor):
        def execute(
            self, query: str, parameters: tuple[object, ...] | None = None
        ) -> None:
            del query, parameters
            raise psycopg.OperationalError("driver canary must not escape")

    with pytest.raises(module._RebuildFailure) as captured:
        module._rebuild_admitted_document(
            _Connection(_FailingCursor()), module._freeze_raw_document(document)
        )

    assert captured.value.failure_category == "database"
    assert captured.value.failure_code == "database_error"
    assert captured.value.failure_phase == "scope_lock"
    assert (captured.value.doc_id, captured.value.version_id) == (doc_id, version_id)
    assert captured.value.__cause__ is None
    assert "driver canary" not in str(captured.value)


def test_pre_database_admission_failure_opens_no_connection_or_audit() -> None:
    module = _load_module()
    calls: list[str] = []

    def factory(_: str) -> object:
        calls.append("connect")
        raise AssertionError("pre-database failure must not connect")

    with pytest.raises(ValueError, match="No raw OKF documents"):
        module._rebuild_admitted_bundle(
            _admitted(module), "ignored", "expected", connection_factory=factory
        )

    assert calls == []


def test_identity_mismatch_has_no_second_connection_or_audit() -> None:
    module = _load_module()
    primary = _Connection(_Cursor([("wrong",)]))
    connections = [primary]

    def factory(_: str) -> _Connection:
        return connections.pop(0)

    with pytest.raises(ValueError, match="database identity"):
        module._rebuild_admitted_bundle(
            _admitted(module, _document()),
            "ignored",
            "expected",
            connection_factory=factory,
        )

    assert connections == []
    assert primary.rolled_back is True
    assert not any(
        "failure_audit" in query for query, _ in primary.cursor_value.executed
    )


class _PrimaryStringSubclass(str):
    pass


@pytest.mark.parametrize(
    "current_database",
    [
        (),
        ("expected", "unexpected"),
        (123,),
        (_PrimaryStringSubclass("expected"),),
        ("wrong",),
    ],
    ids=(
        "empty-tuple",
        "multi-column-tuple",
        "non-string",
        "string-subclass",
        "mismatch",
    ),
)
def test_primary_database_identity_rejects_malformed_results_before_rebuild_dml(
    monkeypatch: pytest.MonkeyPatch, current_database: tuple[object, ...]
) -> None:
    module = _load_module()
    primary = _Connection(_Cursor([current_database]))

    def fail_rebuild_dml(*_: object) -> int:
        pytest.fail("primary database identity rejection must precede rebuild DML")
        raise AssertionError("pytest.fail must raise")

    monkeypatch.setattr(module, "_rebuild_admitted_document", fail_rebuild_dml)

    rebuilt, error, rollback_confirmed, target_verified, phase = (
        module._run_primary_transaction(
            primary, _admitted(module, _document()), "expected"
        )
    )

    assert rebuilt is None
    assert isinstance(error, ValueError)
    assert str(error) == "Connected database identity does not match rebuild target"
    assert rollback_confirmed is True
    assert target_verified is False
    assert phase == "target_validation"
    assert primary.cursor_value.executed == [("SELECT current_database()", None)]
    assert primary.committed is False
    assert primary.rolled_back is True


def test_primary_database_identity_accepts_exact_one_column_builtin_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    primary = _Connection(_Cursor([("expected",)]))
    rebuild_dml_calls: list[object] = []

    def rebuild_once(*_: object) -> int:
        rebuild_dml_calls.append("rebuild")
        return 1

    monkeypatch.setattr(module, "_rebuild_admitted_document", rebuild_once)

    rebuilt, error, rollback_confirmed, target_verified, phase = (
        module._run_primary_transaction(
            primary, _admitted(module, _document()), "expected"
        )
    )

    assert rebuilt == 1
    assert error is None
    assert rollback_confirmed is False
    assert target_verified is True
    assert phase == "transaction_commit"
    assert rebuild_dml_calls == ["rebuild"]
    assert primary.cursor_value.executed == [("SELECT current_database()", None)]
    assert primary.committed is True
    assert primary.rolled_back is False


def _assert_failure_audit_insert(
    module: ModuleType, audit: _Connection, document: OKFDocument
) -> None:
    query, parameters = audit.cursor_value.executed[-1]
    assert "INSERT INTO okf_rebuild_failure_audit" in query
    assert "ON CONFLICT (rebuild_run_id) DO NOTHING" in query
    assert parameters is not None
    assert parameters[2:6] == (
        "scope_validation",
        "unregistered_document_version",
        "scope_lock",
        True,
    )
    assert parameters[6] == 1
    assert isinstance(parameters[7], module.Jsonb)
    assert "%s" in query
    assert parameters[9:11] == (
        UUID(document.frontmatter.doc_id or ""),
        UUID(document.frontmatter.version_id or ""),
    )
    assert "must never persist" not in repr(parameters)
    assert "never-in-a-manifest" not in repr(parameters)


def test_primary_rollback_uses_distinct_connection_for_one_safe_audit_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    primary = _Connection(_Cursor([("expected",)]))
    audit = _Connection(_Cursor([("expected",)]))
    connections = [primary, audit]
    document = _document()

    def factory(_: str) -> _Connection:
        return connections.pop(0)

    def fail(_: object, admitted: Any) -> int:
        raise module._RebuildFailure(
            "scope_validation",
            "unregistered_document_version",
            "scope_lock",
            UUID(admitted.doc_id),
            UUID(admitted.version_id),
        )

    monkeypatch.setattr(module, "_rebuild_admitted_document", fail)
    with pytest.raises(module._RebuildFailure) as captured:
        module._rebuild_admitted_bundle(
            _admitted(module, document),
            "ignored",
            "expected",
            connection_factory=factory,
        )

    assert captured.value.failure_code == "unregistered_document_version"
    assert captured.value.__cause__ is None
    assert primary.rolled_back is True
    assert primary is not audit
    assert audit.transaction_count == 1
    assert audit.cursor_value.executed[0] == ("SELECT current_database()", None)
    _assert_failure_audit_insert(module, audit, document)


class _StringSubclass(str):
    pass


@pytest.mark.parametrize(
    "audit_results",
    [[("other_disposable_database",)], [], [(123,)], [(_StringSubclass("expected"),)]],
    ids=("mismatch", "no-row", "non-string", "string-subclass"),
)
def test_audit_target_mismatch_preserves_primary_failure_without_dml(
    monkeypatch: pytest.MonkeyPatch, audit_results: list[tuple[object, ...]]
) -> None:
    module = _load_module()
    primary = _Connection(_Cursor([("expected",)]))
    audit = _Connection(_Cursor(audit_results))
    primary_failure = module._RebuildFailure(
        "scope_validation",
        "unregistered_document_version",
        "scope_lock",
        None,
        None,
    )
    monkeypatch.setattr(
        module,
        "_rebuild_admitted_document",
        lambda *_: (_ for _ in ()).throw(primary_failure),
    )

    connections = [primary, audit]
    with pytest.raises(module._RebuildFailure) as captured:
        module._rebuild_admitted_bundle(
            _admitted(module, _document()),
            "ignored",
            "expected",
            connection_factory=lambda _: connections.pop(0),
        )

    assert captured.value is primary_failure
    assert primary.rolled_back is True
    assert audit.cursor_value.executed == [("SELECT current_database()", None)]
    assert audit.transaction_count == 0
    assert audit.committed is False
    assert audit.rolled_back is True
    assert audit.closed is True


def test_audit_write_failure_preserves_primary_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    primary = _Connection(_Cursor([("expected",)]))
    broken_audit = _Connection(_Cursor(fail=True))
    connections = [primary, broken_audit]
    primary_failure = module._RebuildFailure(
        "identity_conflict",
        "span_id_owned_by_other_version",
        "span_reconciliation",
        None,
        None,
    )
    monkeypatch.setattr(
        module,
        "_rebuild_admitted_document",
        lambda *_: (_ for _ in ()).throw(primary_failure),
    )

    with pytest.raises(module._RebuildFailure) as captured:
        module._rebuild_admitted_bundle(
            _admitted(module, _document()),
            "ignored",
            "expected",
            connection_factory=lambda _: connections.pop(0),
        )

    assert captured.value is primary_failure
    assert primary.rolled_back is True


def test_successful_rebuild_never_writes_failure_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    success_primary = _Connection(_Cursor([("expected",)]))
    connections = [success_primary]
    monkeypatch.setattr(module, "_rebuild_admitted_document", lambda *_: 1)

    assert (
        module._rebuild_admitted_bundle(
            _admitted(module, _document()),
            "ignored",
            "expected",
            connection_factory=lambda _: connections.pop(0),
        )
        == 1
    )

    assert connections == []
    assert success_primary.rolled_back is False
    assert not any(
        "failure_audit" in query for query, _ in success_primary.cursor_value.executed
    )
