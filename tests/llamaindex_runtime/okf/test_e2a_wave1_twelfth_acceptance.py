"""Wave-1 twelfth-remediation regressions without live PostgreSQL or Docker."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from llamaindex_runtime.okf import e2a_disposable_acceptance as acceptance
from llamaindex_runtime.okf import e2a_disposable_execution as execution
from llamaindex_runtime.registry.migration_catalog import FULL_MIGRATION_CATALOG

_ROOT = Path(__file__).resolve().parents[3]
_SQL = (
    _ROOT
    / "llamaindex_runtime"
    / "registry"
    / "migrations"
    / "019_e2a_materialization_contract.sql"
)


def _inline_normalizers(sql: str) -> tuple[str, str]:
    first_marker, second_marker = (
        "FOR e2a_normalize_expression_side IN 1..4 LOOP",
        "FOR e2a_normalize_expression_side IN 1..2 LOOP",
    )
    outer_wrapper_marker = (
        "WHILE pg_catalog.left(e2a_normalize_expression_output, 1) = '('"
    )
    first_normalizer = sql.split(first_marker, maxsplit=1)[1].split(
        "IF e2a_normalize_expression_side", maxsplit=1
    )[0]
    second_normalizer = sql.split(second_marker, maxsplit=1)[1].split(
        "IF e2a_normalize_expression_side", maxsplit=1
    )[0]
    return (
        first_normalizer.split(outer_wrapper_marker, maxsplit=1)[0],
        second_normalizer.split(outer_wrapper_marker, maxsplit=1)[0],
    )


class _Authority:
    authorized = True


class _Target:
    dbname = "disposable"


_TARGET = _Target()


class _CatalogCursor:
    def __init__(self, responses: list[list[tuple[object, ...]]]) -> None:
        self._responses = iter(responses)
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, statement: str, parameters: tuple[object, ...]) -> None:
        self.executed.append((statement, parameters))

    def fetchall(self) -> list[tuple[object, ...]]:
        return next(self._responses)


class _StringSubclass(str):
    pass


class _StringCanary:
    def __str__(self) -> str:
        raise AssertionError("catalog adapters must not coerce values")


def _function_row(
    *,
    oid: object = 701,
    source: object = "BEGIN\n  RAISE EXCEPTION 'okf_rebuild_failure_audit is append-only';\nEND;",
) -> tuple[object, ...]:
    return (
        oid,
        "prevent_okf_rebuild_failure_audit_mutation",
        "f",
        0,
        "",
        0,
        "trigger",
        False,
        "plpgsql",
        source,
    )


def _trigger_rows(function_oid: object = 701) -> list[tuple[object, ...]]:
    return [
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
            function_oid,
        )
        for item in acceptance._EXPECTED_018_TRIGGER_ROWS  # noqa: SLF001
    ]


def test_independent_append_only_function_contract_is_exact_and_sql_free() -> None:
    expectation = acceptance._EXPECTED_018_APPEND_ONLY_FUNCTION  # noqa: SLF001
    source = (
        _ROOT / "llamaindex_runtime" / "okf" / "e2a_disposable_catalog_contracts.py"
    ).read_text(encoding="utf-8")

    assert expectation.name == "prevent_okf_rebuild_failure_audit_mutation"
    assert expectation.prokind == "f"
    assert expectation.pronargs == 0
    assert expectation.proargtypes == ""
    assert expectation.provariadic == 0
    assert expectation.prorettype == "trigger"
    assert expectation.proretset is False
    assert expectation.language == "plpgsql"
    assert acceptance._definition(expectation.source) == (  # noqa: SLF001
        "BEGIN RAISE EXCEPTION 'okf_rebuild_failure_audit is append-only'; END;"
    )
    assert ".sql" not in source
    assert "read_text" not in source


def test_catalog_attests_exact_function_once_and_shared_trigger_oid() -> None:
    cursor = _CatalogCursor([[_function_row()], _trigger_rows()])

    acceptance._assert_trigger_rows(  # noqa: SLF001
        cursor, {"okf_rebuild_failure_audit": 71}
    )

    assert len(cursor.executed) == 2
    assert "procedure_row.prosrc" in cursor.executed[0][0]
    assert "trigger_row.tgfoid" in cursor.executed[1][0]


@pytest.mark.parametrize(
    "function_row, trigger_oid",
    (
        (_function_row(source="BEGIN RETURN NEW; END;"), 701),
        (_function_row(oid=702), 701),
        (_function_row(), 702),
        (_function_row(), "701"),
    ),
)
def test_catalog_rejects_function_source_metadata_or_shared_oid_drift(
    function_row: tuple[object, ...], trigger_oid: object
) -> None:
    cursor = _CatalogCursor([[function_row], _trigger_rows(trigger_oid)])

    with pytest.raises(ValueError, match="^executed_failed$"):
        acceptance._assert_trigger_rows(  # noqa: SLF001
            cursor, {"okf_rebuild_failure_audit": 71}
        )


@pytest.mark.parametrize(
    "position, value",
    (
        (1, _StringSubclass("prevent_okf_rebuild_failure_audit_mutation")),
        (2, "p"),
        (3, True),
        (4, _StringSubclass("")),
        (5, True),
        (6, "void"),
        (7, True),
        (8, "sql"),
        (9, _StringCanary()),
    ),
)
def test_catalog_rejects_exact_function_value_impostors(
    position: int, value: object
) -> None:
    row = list(_function_row())
    row[position] = value

    with pytest.raises(ValueError, match="^executed_failed$"):
        acceptance._assert_trigger_rows(  # noqa: SLF001
            _CatalogCursor([[tuple(row)], _trigger_rows()]),
            {"okf_rebuild_failure_audit": 71},
        )


def test_catalog_rejects_multiple_same_schema_function_overloads() -> None:
    cursor = _CatalogCursor([[_function_row(), _function_row(oid=702)]])

    with pytest.raises(ValueError, match="^executed_failed$"):
        acceptance._assert_trigger_rows(  # noqa: SLF001
            cursor, {"okf_rebuild_failure_audit": 71}
        )


def _fk_expectation() -> acceptance._ConstraintExpectation:
    return acceptance._ConstraintExpectation(
        "links",
        "fk_links_target",
        "f",
        "FOREIGN KEY (target_id) REFERENCES targets(target_id) ON DELETE RESTRICT",
        "target_id",
        "targets",
        "target_id",
    )


def _fk_row() -> tuple[object, ...]:
    return (
        "links",
        "fk_links_target",
        "f",
        "FOREIGN KEY (target_id) REFERENCES targets(target_id) ON DELETE RESTRICT",
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


def _index_expectation() -> acceptance._IndexExpectation:
    return acceptance._IndexExpectation(
        "links",
        "idx_links_target",
        "target_id",
        unique=True,
        predicate="target_id IS NOT NULL",
    )


def _index_row() -> tuple[object, ...]:
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
        1,
        1,
        "target_id",
        "",
        "target_id IS NOT NULL",
        True,
        "0",
    )


@pytest.mark.parametrize(
    "operation",
    (
        lambda: acceptance._relation_oids(  # noqa: SLF001
            _CatalogCursor([[(_StringSubclass("links"), 41)]]), ("links",)
        ),
        lambda: acceptance._validate_constraint_row(  # noqa: SLF001
            tuple([_StringCanary(), *_fk_row()[1:]]),
            _fk_expectation(),
            {"links": 41, "targets": 42},
        ),
        lambda: acceptance._validate_index_row(  # noqa: SLF001
            tuple([*_index_row()[:10], _StringSubclass("btree"), *_index_row()[11:]]),
            _index_expectation(),
            {"links": 41},
        ),
        lambda: acceptance._assert_column_rows(  # noqa: SLF001
            _CatalogCursor([[("links", "target_id", "uuid", "YES", "")]]),
            (("links", "target_id", "uuid", "YES", None),),
        ),
        lambda: acceptance._assert_trigger_rows(  # noqa: SLF001
            _CatalogCursor([[_function_row()], _trigger_rows(memoryview(b""))]),
            {"okf_rebuild_failure_audit": 71},
        ),
    ),
)
def test_catalog_adapters_reject_coercible_text_binary_and_falsey_default_values(
    operation: Callable[[], object],
) -> None:
    with pytest.raises(ValueError, match="^executed_failed$"):
        operation()


@pytest.mark.parametrize("value", (bytearray(), memoryview(b""), 0, ""))
def test_trigger_bytea_contract_accepts_only_exact_bytes(value: object) -> None:
    rows = _trigger_rows()
    row = list(rows[0])
    row[7] = value
    rows[0] = tuple(row)

    with pytest.raises(ValueError, match="^executed_failed$"):
        acceptance._assert_trigger_rows(  # noqa: SLF001
            _CatalogCursor([[_function_row()], rows]),
            {"okf_rebuild_failure_audit": 71},
        )


def test_catalog_selection_rejects_invalid_generator_before_facade_delegate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def source() -> object:
        yield "019_e2a_materialization_contract.sql"
        yield Path("019_e2a_materialization_contract.sql")

    monkeypatch.setattr(
        acceptance,
        "_apply_catalog_implementation",
        lambda *_args, **_kwargs: calls.append("delegate"),
    )

    with pytest.raises(ValueError, match="^executed_failed$"):
        acceptance._apply_catalog(_TARGET, lambda _: calls.append("factory"), source())

    assert calls == []


@pytest.mark.parametrize(
    "filenames",
    (
        ("../019_e2a_materialization_contract.sql",),
        ("/019_e2a_materialization_contract.sql",),
        ("019_e2a_materialization_contract.sql\\",),
        (Path("019_e2a_materialization_contract.sql"),),
        (_StringSubclass("019_e2a_materialization_contract.sql"),),
        ("unknown.sql",),
    ),
)
def test_execution_selection_rejects_every_invalid_member_before_factory(
    filenames: tuple[object, ...],
) -> None:
    calls: list[str] = []

    with pytest.raises(ValueError, match="^executed_failed$"):
        execution._apply_catalog(  # noqa: SLF001
            _TARGET, lambda _: calls.append("factory"), filenames  # type: ignore[arg-type]
        )

    assert calls == []


def test_catalog_selection_preserves_allowed_subsets_order_and_duplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: list[tuple[object, ...]] = []
    subset = (
        "019_e2a_materialization_contract.sql",
        FULL_MIGRATION_CATALOG[0],
        "019_e2a_materialization_contract.sql",
    )
    monkeypatch.setattr(
        acceptance,
        "_apply_catalog_implementation",
        lambda _target, _factory, filenames, **_kwargs: received.append(
            tuple(filenames)
        ),
    )

    acceptance._apply_catalog(_TARGET, lambda _: None, subset)
    acceptance._apply_catalog(_TARGET, lambda _: None, ())

    assert received == [subset, ()]


def test_public_runners_late_bind_the_current_facade_factory_after_authority_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: list[object] = []

    def current_factory(_: object) -> object:
        return object()

    monkeypatch.setattr(acceptance, "runtime_connection_factory", current_factory)
    monkeypatch.setattr(
        acceptance, "parse_disposable_postgresql_target", lambda *_: _TARGET
    )
    monkeypatch.setattr(
        acceptance,
        "_apply_catalog",
        lambda _target, factory, *_args: received.append(factory),
    )
    monkeypatch.setattr(
        acceptance, "_verify_catalog", lambda _target, factory: received.append(factory)
    )

    assert (
        acceptance.run_disposable_migration_acceptance(_Authority(), "target", "db")
        == "executed_pass"
    )
    assert (
        acceptance.run_current_disposable_postgresql_acceptance(
            _Authority(), "target", "db"
        )
        == "executed_pass"
    )
    assert received == [
        current_factory,
        current_factory,
        current_factory,
        current_factory,
        current_factory,
        current_factory,
        current_factory,
        current_factory,
    ]


def test_explicit_none_never_selects_the_default_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        acceptance, "parse_disposable_postgresql_target", lambda *_: _TARGET
    )
    monkeypatch.setattr(
        acceptance,
        "runtime_connection_factory",
        lambda _: (_ for _ in ()).throw(AssertionError("default selected")),
    )
    monkeypatch.setattr(
        acceptance,
        "_apply_catalog",
        lambda _target, factory, *_args: (_ for _ in ()).throw(
            TypeError("explicit None")
            if factory is None
            else AssertionError("default selected")
        ),
    )

    assert (
        acceptance.run_disposable_migration_acceptance(
            _Authority(), "target", "db", None  # type: ignore[arg-type]
        )
        == "executed_failed"
    )


class _FlowCursor:
    def __init__(self, fail_statement: str | None = None) -> None:
        self.fail_statement = fail_statement
        self.executed: list[str] = []

    def execute(self, statement: str, *_: object) -> None:
        self.executed.append(statement)
        if statement == self.fail_statement:
            raise RuntimeError(statement)


class _FlowConnection:
    def __init__(
        self,
        cursor: _FlowCursor | None = None,
        *,
        cursor_fails: bool = False,
        rollback_fails: bool = False,
        close_fails: bool = False,
    ) -> None:
        self.value = cursor or _FlowCursor()
        self.cursor_fails = cursor_fails
        self.rollback_fails = rollback_fails
        self.close_fails = close_fails
        self.rollbacks = 0
        self.closes = 0

    def cursor(self) -> _FlowCursor:
        if self.cursor_fails:
            raise RuntimeError("cursor")
        return self.value

    def rollback(self) -> None:
        self.rollbacks += 1
        if self.rollback_fails:
            raise RuntimeError("rollback")

    def close(self) -> None:
        self.closes += 1
        if self.close_fails:
            raise RuntimeError("close")


@pytest.mark.parametrize("stage", ("cursor", "attestation", "catalog"))
def test_verify_rolls_back_once_before_probe_and_preserves_primary_failure(
    monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    connection = _FlowConnection(cursor_fails=stage == "cursor")
    monkeypatch.setattr(
        acceptance,
        "_attest_connection_target",
        (
            (lambda *_: (_ for _ in ()).throw(RuntimeError("attestation")))
            if stage == "attestation"
            else lambda *_: None
        ),
    )
    monkeypatch.setattr(
        acceptance,
        "_assert_019_catalog_shape",
        (
            (lambda *_: (_ for _ in ()).throw(RuntimeError("catalog")))
            if stage == "catalog"
            else lambda *_: None
        ),
    )

    with pytest.raises(RuntimeError, match=f"^{stage}$"):
        acceptance._verify_catalog(_TARGET, lambda _: connection)  # noqa: SLF001

    assert connection.rollbacks == 1
    assert connection.closes == 1


def test_probe_begin_failure_rolls_back_once_without_verify_double_rollback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _FlowConnection(_FlowCursor("BEGIN"))
    monkeypatch.setattr(acceptance, "_attest_connection_target", lambda *_: None)
    monkeypatch.setattr(acceptance, "_assert_019_catalog_shape", lambda *_: None)

    with pytest.raises(ValueError, match="^executed_failed$"):
        acceptance._verify_catalog(_TARGET, lambda _: connection)  # noqa: SLF001

    assert connection.value.executed == ["BEGIN"]
    assert connection.rollbacks == 1
    assert connection.closes == 1


def test_verify_chains_cleanup_but_keeps_preprobe_failure_primary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _FlowConnection(rollback_fails=True, close_fails=True)
    monkeypatch.setattr(
        acceptance,
        "_attest_connection_target",
        lambda *_: (_ for _ in ()).throw(RuntimeError("attestation")),
    )

    with pytest.raises(RuntimeError, match="^attestation$") as error:
        acceptance._verify_catalog(_TARGET, lambda _: connection)  # noqa: SLF001

    assert error.value.__cause__ is not None
    assert connection.rollbacks == 1
    assert connection.closes == 1


def test_verify_surfaces_close_only_without_primary_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _FlowConnection(close_fails=True)
    monkeypatch.setattr(acceptance, "_attest_connection_target", lambda *_: None)
    monkeypatch.setattr(acceptance, "_assert_019_catalog_shape", lambda *_: None)
    monkeypatch.setattr(acceptance, "_run_rollback_only_probe", lambda *_: None)

    with pytest.raises(ValueError, match="^executed_failed$"):
        acceptance._verify_catalog(_TARGET, lambda _: connection)  # noqa: SLF001

    assert connection.rollbacks == 0
    assert connection.closes == 1


@pytest.mark.parametrize("character", ("$", "é", "猫", "😀", "́"))
def test_python_lexer_word_characters_are_ascii_or_high_bit_exactly(
    character: str,
) -> None:
    assert acceptance._is_word_character(character)  # noqa: SLF001


@pytest.mark.parametrize("character", (" ", "\t", "\n", "\r", "\f", " ", " "))
def test_python_lexer_ascii_whitespace_does_not_collapse_unicode_separators(
    character: str,
) -> None:
    value = f"left{character}right"
    expected = "left right" if character in " \t\n\r\f" else value

    assert acceptance._definition(value) == expected  # noqa: SLF001


@pytest.mark.parametrize(
    "value",
    (
        "a$$tag$",
        "a$ /* comment */ $tag$ body $tag$",
        "é$tag$",
        "😀$tag$",
        "xE'\\'",
    ),
)
def test_lexer_keeps_identifier_adjacent_dollar_and_embedded_e_streams_ordinary(
    value: str,
) -> None:
    assert acceptance._definition(value) == (  # noqa: SLF001
        "a$ $tag$ body $tag$" if value.startswith("a$ ") else value
    )


@pytest.mark.parametrize("value", ("$tag/", "$tag-", "$1$", "$猫$", "$tag猫$", "E'\\'"))
def test_lexer_rejects_eligible_invalid_dollar_and_escaped_string_streams(
    value: str,
) -> None:
    with pytest.raises(ValueError, match="^executed_failed$"):
        acceptance._definition(value)  # noqa: SLF001


def test_sql_lexers_use_ascii_whitespace_word_boundaries_and_e_token_guard() -> None:
    sql = _SQL.read_text(encoding="utf-8")
    normalizers = _inline_normalizers(sql)
    whitespace = "IN (' ', E'\\t', E'\\n', E'\\r', E'\\f')"
    predecessor = (
        "pg_catalog.substr(e2a_normalize_expression_input, "
        "e2a_normalize_expression_index - 1, 1)"
    )

    for pattern in (
        "e2a_normalize_expression_output ~ '[A-Za-z0-9_$]$'",
        "e2a_normalize_expression_output ~ '[^[:ascii:]]$'",
        "e2a_normalize_expression_character ~ '^[A-Za-z0-9_$]$'",
        "e2a_normalize_expression_character ~ '^[^[:ascii:]]$'",
        whitespace,
        f"{predecessor} !~ '^[A-Za-z0-9_$]$'",
        "e2a_normalize_expression_index - 2, 1) !~ '^[A-Za-z0-9_$]$'",
    ):
        assert sum(normalizer.count(pattern) for normalizer in normalizers) == 2

    assert "^[[:space:]]$" not in sql
    assert "pg_get_functiondef" not in sql


def test_migration_attests_append_only_function_before_ddl_and_before_final_return() -> (
    None
):
    sql = _SQL.read_text(encoding="utf-8")
    preflight, ddl = sql.split(
        "-- Only the exact fresh signature reaches this DDL phase.", maxsplit=1
    )
    final_branch = sql.split("IF final_signature THEN", maxsplit=1)[1]

    assert "procedure_row.prosrc" in sql
    assert "procedure_row.prokind" in sql
    assert "procedure_row.pronargs" in sql
    assert "procedure_row.proargtypes" in sql
    assert "procedure_row.provariadic" in sql
    assert "procedure_row.prorettype" in sql
    assert "procedure_row.proretset" in sql
    assert "language_row.lanname" in sql
    assert "append_only_function_oid" in sql
    assert (
        sql.count("trigger_row.tgfoid IS DISTINCT FROM append_only_function_oid") >= 2
    )
    assert "append_only_function_source_matches" in preflight
    assert "append_only_function_source_matches" in final_branch
    assert "pg_get_functiondef" not in sql
    assert "ALTER TABLE" not in preflight
    assert "CREATE TABLE" not in preflight
    assert "CREATE INDEX" not in preflight
    assert final_branch.index(
        "append_only_function_source_matches"
    ) < final_branch.index("RETURN;")
    assert "ALTER TABLE" in ddl


def test_touched_sources_and_new_regression_file_stay_under_the_line_cap() -> None:
    paths = (
        _ROOT / "llamaindex_runtime" / "okf" / "e2a_disposable_acceptance.py",
        _ROOT / "llamaindex_runtime" / "okf" / "e2a_disposable_execution.py",
        _ROOT / "llamaindex_runtime" / "okf" / "e2a_disposable_sql_lexer.py",
        _ROOT / "llamaindex_runtime" / "okf" / "e2a_disposable_catalog_contracts.py",
        _ROOT / "llamaindex_runtime" / "okf" / "e2a_disposable_catalog.py",
        Path(__file__),
    )

    assert all(
        len(path.read_text(encoding="utf-8").splitlines()) < 800 for path in paths
    )
