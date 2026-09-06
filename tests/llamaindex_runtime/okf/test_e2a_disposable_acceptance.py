from __future__ import annotations

from pathlib import Path

import pytest

from llamaindex_runtime.okf import e2a_disposable_acceptance as acceptance
from llamaindex_runtime.okf import e2a_disposable_catalog as catalog
from llamaindex_runtime.okf import e2a_disposable_execution as execution


class _Authority:
    authorized = True


class _Cursor:
    def __init__(
        self,
        *,
        fail: bool = False,
        fail_after: int = 1,
        identity: tuple[object, ...] = ("fake", "public"),
    ) -> None:
        self.fail = fail
        self.fail_after = fail_after
        self.identity = identity
        self.executed: list[str] = []

    def execute(self, statement: str, *_: object) -> None:
        self.executed.append(statement)
        if self.fail and len(self.executed) > self.fail_after:
            raise RuntimeError("controlled")

    def fetchone(self) -> tuple[object, ...]:
        return self.identity


class _Target:
    dbname = "fake"


_TARGET = _Target()


class _Connection:
    def __init__(
        self,
        cursor: _Cursor,
        *,
        rollback_fails: bool = False,
        close_fails: bool = False,
    ) -> None:
        self._cursor = cursor
        self.rollback_fails = rollback_fails
        self.close_fails = close_fails
        self.commits = 0
        self.rollbacks = 0
        self.closed = 0

    def cursor(self) -> _Cursor:
        return self._cursor

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1
        if self.rollback_fails:
            raise RuntimeError("rollback")

    def close(self) -> None:
        self.closed += 1
        if self.close_fails:
            raise RuntimeError("close")


class _CatalogCursor:
    def __init__(self, responses: list[list[tuple[object, ...]]]) -> None:
        self._responses = iter(responses)
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, statement: str, parameters: tuple[object, ...]) -> None:
        self.executed.append((statement, parameters))

    def fetchall(self) -> list[tuple[object, ...]]:
        return next(self._responses)


def _fk_expectation() -> acceptance._ConstraintExpectation:
    return acceptance._ConstraintExpectation(
        table="links",
        name="fk_links_target",
        contype="f",
        definition="FOREIGN KEY (target_id) REFERENCES targets(target_id) ON DELETE RESTRICT",
        columns="target_id",
        reference_table="targets",
        reference_columns="target_id",
    )


def _fk_row(*, definition: str | None = None) -> tuple[object, ...]:
    return (
        "links",
        "fk_links_target",
        "f",
        definition
        or "FOREIGN KEY (target_id) REFERENCES targets(target_id) ON DELETE RESTRICT",
        "target_id",
        "target_id",
        41,
        42,
        True,
        "r",
        "s",
        "a",
        False,
        False,
        0,
    )


def test_current_disposable_selector_blocks_absent_authority_before_parser_or_connector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fail_parser(*_: object) -> None:
        calls.append("parser")
        raise AssertionError("parser must not be attempted")

    def fail_connector(*_: object, **__: object) -> None:
        calls.append("connector")
        raise AssertionError("connector must not be attempted")

    monkeypatch.setattr(acceptance, "parse_disposable_postgresql_target", fail_parser)

    assert (
        acceptance.run_current_disposable_postgresql_acceptance(
            None, "not-a-target", "not-a-database", fail_connector
        )
        == "blocked_not_executed"
    )
    assert calls == []


def _structural_index_row() -> tuple[object, ...]:
    return (
        "links",
        "idx_links_target",
        41,
        51,
        True,
        False,
        True,
        True,
        True,
        False,
        "btree",
        2,
        2,
        "version_id,target_id",
        "",
        "source_kind = 'manual_okf'::text",
        True,
        "0,0",
    )


def test_index_verifier_accepts_structural_catalog_row() -> None:
    acceptance._validate_index_row(
        _structural_index_row(), _index_expectation(), {"links": 41}
    )


@pytest.mark.parametrize(
    ("label", "position", "value"),
    (
        ("non_btree", 10, "hash"),
        ("primary", 5, True),
        ("invalid", 6, False),
        ("not_ready", 7, False),
        ("not_live", 8, False),
        ("exclusion", 9, True),
        ("wrong_key_count", 11, 1),
        ("include_column", 12, 3),
        ("expression_key", 14, "lower(target_id)"),
        ("wrong_predicate", 15, "source_kind = 'other'::text"),
        ("wrong_opclass_or_collation", 16, False),
        ("wrong_options", 17, "1,0"),
    ),
)
def test_index_verifier_rejects_structural_metadata_drift(
    label: str, position: int, value: object
) -> None:
    row = list(_structural_index_row())
    row[position] = value

    with pytest.raises(ValueError, match="^executed_failed$"):
        acceptance._validate_index_row(tuple(row), _index_expectation(), {"links": 41})


def test_trigger_verifier_rejects_retained_trigger_drift() -> None:
    expected = acceptance._EXPECTED_018_TRIGGER_ROWS  # noqa: SLF001
    function_row = (
        701,
        "prevent_okf_rebuild_failure_audit_mutation",
        "f",
        0,
        "",
        0,
        "trigger",
        False,
        "plpgsql",
        "BEGIN RAISE EXCEPTION 'okf_rebuild_failure_audit is append-only'; END;",
    )
    good_rows = [
        (
            item.table,
            item.name,
            item.function,
            71,
            item.trigger_type,
            "O",
            False,
            b"",
            None,
            "",
            0,
            701,
        )
        for item in expected
    ]
    acceptance._assert_trigger_rows(  # noqa: SLF001
        _CatalogCursor([[function_row], good_rows]), {"okf_rebuild_failure_audit": 71}
    )
    drifted = list(good_rows[0])
    drifted[4] = 99
    with pytest.raises(ValueError, match="^executed_failed$"):
        acceptance._assert_trigger_rows(  # noqa: SLF001
            _CatalogCursor([[function_row], [tuple(drifted), good_rows[1]]]),
            {"okf_rebuild_failure_audit": 71},
        )


def test_backing_index_verifier_accepts_and_rejects_structural_rows() -> None:
    expected = tuple(
        item
        for item in acceptance._EXPECTED_019_CONSTRAINT_ROWS  # noqa: SLF001
        if item.contype in {"p", "u"}
    )
    relation_oids = {
        table: index
        for index, table in enumerate(
            sorted({item.table for item in expected}), start=101
        )
    }
    rows = sorted(
        [
            (
                item.table,
                item.name,
                item.contype,
                501 + index,
                relation_oids[item.table],
                True,
                item.contype == "p",
                True,
                True,
                True,
                False,
                "btree",
                len(item.columns.split(",")),
                len(item.columns.split(",")),
                item.columns,
                "",
                "",
                True,
                (
                    "0"
                    if len(item.columns.split(",")) == 1
                    else ",".join("0" for _ in item.columns.split(","))
                ),
            )
            for index, item in enumerate(expected)
        ]
    )
    acceptance._assert_backing_index_rows(  # noqa: SLF001
        _CatalogCursor([rows]), relation_oids
    )

    drifted = list(rows[0])
    drifted[8] = False
    with pytest.raises(ValueError, match="^executed_failed$"):
        acceptance._assert_backing_index_rows(  # noqa: SLF001
            _CatalogCursor([[tuple(drifted), *rows[1:]]]), relation_oids
        )


def test_lexer_boundary_helpers_fail_closed_and_selector_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="^executed_failed$"):
        acceptance._definition(None)  # type: ignore[arg-type]  # noqa: SLF001
    with pytest.raises(ValueError, match="^executed_failed$"):
        acceptance._scan_quoted("'unterminated", 0, escaped=False)  # noqa: SLF001
    assert acceptance._dollar_delimiter("not-a-delimiter", 0) is None  # noqa: SLF001

    sentinel = object()
    monkeypatch.setattr(
        acceptance,
        "run_disposable_migration_acceptance",
        lambda authority, target, expected_database, connection_factory: sentinel,
    )
    assert (
        acceptance.run_current_disposable_postgresql_acceptance(
            _Authority(), "target", "database", lambda _: _Connection(_Cursor())
        )
        is sentinel
    )


def test_constraint_verifier_accepts_independently_authored_exact_catalog_row() -> None:
    acceptance._validate_constraint_row(
        _fk_row(), _fk_expectation(), {"links": 41, "targets": 42}
    )


@pytest.mark.parametrize(
    ("position", "value"),
    (
        (4, "wrong_id"),
        (7, 99),
        (8, False),
        (9, "c"),
        (10, "f"),
        (12, True),
        (13, True),
    ),
)
def test_constraint_verifier_rejects_catalog_metadata_corruption(
    position: int, value: object
) -> None:
    row = list(_fk_row())
    row[position] = value

    with pytest.raises(ValueError, match="^executed_failed$"):
        acceptance._validate_constraint_row(
            tuple(row), _fk_expectation(), {"links": 41, "targets": 42}
        )


def test_constraint_verifier_rejects_quoted_shadow_relation_and_reversed_keys() -> None:
    quoted_shadow = _fk_row(
        definition='FOREIGN KEY (target_id) REFERENCES "targets"(target_id) ON DELETE RESTRICT'
    )
    reversed_keys = list(_fk_row())
    reversed_keys[4] = "other_id,target_id"

    with pytest.raises(ValueError, match="^executed_failed$"):
        acceptance._validate_constraint_row(
            quoted_shadow, _fk_expectation(), {"links": 41, "targets": 42}
        )
    with pytest.raises(ValueError, match="^executed_failed$"):
        acceptance._validate_constraint_row(
            tuple(reversed_keys), _fk_expectation(), {"links": 41, "targets": 42}
        )


def _index_expectation() -> acceptance._IndexExpectation:
    return acceptance._IndexExpectation(
        table="links",
        name="idx_links_target",
        keys="version_id,target_id",
        unique=True,
        predicate="source_kind = 'manual_okf'::text",
        definition=(
            "CREATE UNIQUE INDEX idx_links_target ON links USING btree "
            "(version_id, target_id) WHERE source_kind = 'manual_okf'::text"
        ),
    )


def _index_row() -> tuple[object, ...]:
    return (
        "links",
        "idx_links_target",
        41,
        51,
        True,
        True,
        "version_id,target_id",
        "",
        "source_kind = 'manual_okf'::text",
        "CREATE UNIQUE INDEX idx_links_target ON links USING btree "
        "(version_id, target_id) WHERE source_kind = 'manual_okf'::text",
    )


def test_catalog_row_wrappers_validate_independently_authored_fake_rows() -> None:
    constraint = _fk_expectation()
    index = _index_expectation()
    column = ("links", "manual_target_id", "uuid", "YES", None)
    cursor = _CatalogCursor([[_fk_row()], [_index_row()], [column]])

    assert acceptance._relation_oids(
        _CatalogCursor([[("links", 41), ("targets", 42)]]), ("links", "targets")
    ) == {"links": 41, "targets": 42}
    acceptance._assert_constraint_rows(
        cursor, {"links": 41, "targets": 42}, (constraint,)
    )
    acceptance._assert_index_rows(cursor, {"links": 41}, (index,))
    acceptance._assert_column_rows(cursor, (column,))
    assert len(cursor.executed) == 3


def test_catalog_relation_lookup_rejects_missing_current_schema_oid() -> None:
    cursor = _CatalogCursor([[("links", 41)]])

    with pytest.raises(ValueError, match="^executed_failed$"):
        acceptance._relation_oids(cursor, ("links", "targets"))


def test_index_verifier_accepts_independently_authored_exact_catalog_row() -> None:
    acceptance._validate_index_row(_index_row(), _index_expectation(), {"links": 41})


@pytest.mark.parametrize(
    ("position", "value"),
    (
        (2, 99),
        (4, False),
        (5, False),
        (6, "target_id,version_id"),
        (7, "lower(target_id)"),
        (8, "source_kind = 'other'::text"),
    ),
)
def test_index_verifier_rejects_oid_uniqueness_validity_key_and_predicate_corruption(
    position: int, value: object
) -> None:
    row = list(_index_row())
    row[position] = value

    with pytest.raises(ValueError, match="^executed_failed$"):
        acceptance._validate_index_row(tuple(row), _index_expectation(), {"links": 41})


def test_catalog_query_shape_selects_oid_and_ordered_index_metadata() -> None:
    text = Path(catalog.__file__).read_text(encoding="utf-8")

    for required in (
        "constraint_row.conrelid",
        "constraint_row.confrelid",
        "constraint_row.convalidated",
        "constraint_row.confdeltype",
        "constraint_row.confmatchtype",
        "constraint_row.confupdtype",
        "constraint_row.condeferrable",
        "constraint_row.condeferred",
        "constraint_row.conindid",
        "index_row.indrelid",
        "index_row.indexrelid",
        "index_row.indisunique",
        "index_row.indisvalid",
        "generate_series(0, index_row.indnkeyatts - 1)",
        "index_row.indisready",
        "index_row.indislive",
        "index_row.indclass",
        "index_row.indcollation",
        "index_row.indoption",
        "index_row.indexprs",
        "index_row.indpred",
    ):
        assert required in text


def test_apply_failure_rolls_back_and_closes_once() -> None:
    connection = _Connection(_Cursor(fail=True))

    with pytest.raises(RuntimeError, match="controlled"):
        acceptance._apply_catalog(_TARGET, lambda _: connection)

    assert (
        connection._cursor.executed[0] == "SELECT current_database(), current_schema()"
    )
    assert len(connection._cursor.executed) == 2
    assert connection.rollbacks == 1
    assert connection.closed == 1


def test_probe_rollback_failure_is_distinct_and_connection_closes_once() -> None:
    connection = _Connection(_Cursor(), rollback_fails=True)

    with pytest.raises(acceptance._ProbeRollbackFailure):
        acceptance._run_rollback_only_probe(connection, connection.cursor())

    assert connection.rollbacks == 1


def test_authorized_apply_rollback_failure_is_a_distinct_redacted_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _Connection(_Cursor(fail=True), rollback_fails=True)
    monkeypatch.setattr(
        acceptance, "parse_disposable_postgresql_target", lambda *_: _TARGET
    )

    assert (
        acceptance.run_disposable_migration_acceptance(
            _Authority(), "postgresql://fake", "fake", lambda _: connection
        )
        == "executed_apply_rollback_failed"
    )
    assert connection.closed == 1


def test_apply_catalog_commits_each_migration_and_closes_once() -> None:
    connection = _Connection(_Cursor())

    acceptance._apply_catalog(_TARGET, lambda _: connection)

    assert (
        connection._cursor.executed[0] == "SELECT current_database(), current_schema()"
    )
    assert (
        len(connection._cursor.executed) == len(acceptance.FULL_MIGRATION_CATALOG) + 1
    )
    assert connection.commits == len(acceptance.FULL_MIGRATION_CATALOG)
    assert connection.rollbacks == 0
    assert connection.closed == 1


def test_catalog_helpers_cover_expected_relations_and_close_failure() -> None:
    relations = acceptance._expected_relations()
    assert relations == tuple(sorted(relations))
    assert {"evidence_links", "okf_manual_evidence_targets"} <= set(relations)

    class CloseFailure:
        def close(self) -> None:
            raise RuntimeError("close")

    with pytest.raises(ValueError, match="^executed_failed$"):
        acceptance._close(CloseFailure())


def test_verify_catalog_closes_after_fake_catalog_rejection() -> None:
    class InvalidCatalogCursor(_Cursor):
        def fetchall(self) -> list[tuple[object, ...]]:
            return []

    connection = _Connection(InvalidCatalogCursor())

    with pytest.raises(ValueError, match="^executed_failed$"):
        acceptance._verify_catalog(_TARGET, lambda _: connection)

    assert connection.closed == 1


def test_semantic_probe_covers_generic_and_manual_rollback_only_cases() -> None:
    for label in (
        "another_generic",
        "e2a_probe_missing_manual_evidence_owner_scope",
        "e2a_probe_wrong_shadow_projection",
        "e2a_probe_wrong_owner_target",
        "e2a_probe_wrong_target_mapping",
        "e2a_probe_cross_version_span_evidence",
        "e2a_probe_invalid_global_scoped_scope",
        "e2a_probe_restrict_delete",
    ):
        assert label in acceptance._SEMANTIC_PROBE


def test_facade_apply_catalog_uses_patched_attestation_and_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _Connection(_Cursor())
    calls: list[str] = []
    monkeypatch.setattr(
        acceptance,
        "_attest_connection_target",
        lambda _cursor, _target: calls.append("attest"),
    )
    monkeypatch.setattr(acceptance, "_close", lambda _connection: calls.append("close"))

    acceptance._apply_catalog(_TARGET, lambda _: connection, ())  # noqa: SLF001

    assert calls == ["attest", "close"]
    assert connection.closed == 0


def test_facade_verify_catalog_uses_patched_attestation_close_and_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _Connection(_Cursor())
    calls: list[str] = []
    monkeypatch.setattr(
        acceptance,
        "_attest_connection_target",
        lambda _cursor, _target: calls.append("attest"),
    )
    monkeypatch.setattr(
        acceptance, "_assert_019_catalog_shape", lambda _cursor: calls.append("catalog")
    )
    monkeypatch.setattr(acceptance, "_SEMANTIC_PROBE", "facade semantic probe")
    monkeypatch.setattr(acceptance, "_close", lambda _connection: calls.append("close"))

    acceptance._verify_catalog(_TARGET, lambda _: connection)  # noqa: SLF001

    assert calls == ["attest", "catalog", "close"]
    assert connection._cursor.executed == ["BEGIN", "facade semantic probe"]
    assert connection.rollbacks == 1
    assert connection.closed == 0


def test_execution_helpers_resolve_omitted_collaborators_from_execution_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    apply_connection = _Connection(_Cursor())
    probe_connection = _Connection(_Cursor())
    calls: list[str] = []
    monkeypatch.setattr(
        execution,
        "_attest_connection_target",
        lambda _cursor, _target: calls.append("attest"),
    )
    monkeypatch.setattr(execution, "_close", lambda _connection: calls.append("close"))
    monkeypatch.setattr(execution, "_SEMANTIC_PROBE", "execution semantic probe")

    execution._apply_catalog(_TARGET, lambda _: apply_connection, ())
    execution._run_rollback_only_probe(probe_connection, probe_connection.cursor())

    assert calls == ["attest", "close"]
    assert probe_connection._cursor.executed == ["BEGIN", "execution semantic probe"]
    assert probe_connection.rollbacks == 1


@pytest.mark.parametrize("stage", ("attestation", "catalog", "probe"))
def test_verify_catalog_preserves_primary_failure_when_close_also_fails(
    monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    connection = _Connection(_Cursor())
    close_calls: list[str] = []

    def fail(stage_name: str) -> None:
        raise RuntimeError(stage_name)

    if stage == "attestation":
        monkeypatch.setattr(
            acceptance,
            "_attest_connection_target",
            lambda _cursor, _target: fail(stage),
        )
    else:
        monkeypatch.setattr(acceptance, "_attest_connection_target", lambda *_: None)
    if stage == "catalog":
        monkeypatch.setattr(
            acceptance,
            "_assert_019_catalog_shape",
            lambda _cursor: fail(stage),
        )
    else:
        monkeypatch.setattr(acceptance, "_assert_019_catalog_shape", lambda _: None)
    if stage == "probe":
        monkeypatch.setattr(
            acceptance,
            "_run_rollback_only_probe",
            lambda _connection, _cursor: fail(stage),
        )
    monkeypatch.setattr(
        acceptance,
        "_close",
        lambda _connection: (close_calls.append("close"), fail("close"))[1],
    )

    with pytest.raises(RuntimeError, match=f"^{stage}$"):
        acceptance._verify_catalog(_TARGET, lambda _: connection)  # noqa: SLF001

    assert close_calls == ["close"]


def test_apply_catalog_preserves_work_failure_when_close_also_fails() -> None:
    connection = _Connection(_Cursor(fail=True), close_fails=True)

    with pytest.raises(RuntimeError, match="^controlled$"):
        acceptance._apply_catalog(_TARGET, lambda _: connection)  # noqa: SLF001

    assert connection.rollbacks == 1
    assert connection.closed == 1


def test_apply_rollback_failure_survives_a_close_failure() -> None:
    connection = _Connection(_Cursor(fail=True), rollback_fails=True, close_fails=True)

    with pytest.raises(acceptance._ApplyRollbackFailure):
        acceptance._apply_catalog(_TARGET, lambda _: connection)  # noqa: SLF001

    assert connection.rollbacks == 1
    assert connection.closed == 1


def test_probe_rollback_failure_survives_a_close_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _Connection(
        _Cursor(fail=True, fail_after=2), rollback_fails=True, close_fails=True
    )
    monkeypatch.setattr(acceptance, "_assert_019_catalog_shape", lambda _: None)

    with pytest.raises(acceptance._ProbeRollbackFailure):
        acceptance._verify_catalog(_TARGET, lambda _: connection)  # noqa: SLF001

    assert connection.rollbacks == 1
    assert connection.closed == 1


@pytest.mark.parametrize("invalid_value", ("41", True, 41.0, None))
def test_catalog_validators_reject_non_integer_catalog_fields(
    invalid_value: object,
) -> None:
    with pytest.raises(ValueError, match="^executed_failed$"):
        acceptance._relation_oids(  # noqa: SLF001
            _CatalogCursor([[("links", invalid_value)]]), ("links",)
        )

    for position in (6, 7, 14):
        row = list(_fk_row())
        row[position] = invalid_value
        with pytest.raises(ValueError, match="^executed_failed$"):
            acceptance._validate_constraint_row(  # noqa: SLF001
                tuple(row), _fk_expectation(), {"links": 41, "targets": 42}
            )

    for position in (2, 3, 11, 12):
        row = list(_structural_index_row())
        row[position] = invalid_value
        with pytest.raises(ValueError, match="^executed_failed$"):
            acceptance._validate_index_row(  # noqa: SLF001
                tuple(row), _index_expectation(), {"links": 41}
            )
