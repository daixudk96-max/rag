"""Wave-1 fourteenth-remediation contract regressions without PostgreSQL."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from llamaindex_runtime.okf import e2a_disposable_catalog as catalog

_ROOT = Path(__file__).resolve().parents[3]
_SQL_PATH = (
    _ROOT
    / "llamaindex_runtime"
    / "registry"
    / "migrations"
    / "019_e2a_materialization_contract.sql"
)
_AUDIT_OID = 71
_FUNCTION_OID = 701


class _CatalogCursor:
    def __init__(self, responses: list[list[tuple[object, ...]]]) -> None:
        self._responses: Iterator[list[tuple[object, ...]]] = iter(responses)
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, statement: str, parameters: tuple[object, ...]) -> None:
        self.executed.append((statement, parameters))

    def fetchall(self) -> list[tuple[object, ...]]:
        return next(self._responses)


def _function_row(source: str | None = None) -> tuple[object, ...]:
    return (
        _FUNCTION_OID,
        "prevent_okf_rebuild_failure_audit_mutation",
        "f",
        0,
        "",
        0,
        "trigger",
        False,
        "plpgsql",
        source
        or "BEGIN RAISE EXCEPTION 'okf_rebuild_failure_audit is append-only'; END;",
    )


def _expected_trigger_rows() -> list[tuple[object, ...]]:
    return [
        (
            expected.table,
            expected.name,
            expected.function,
            _AUDIT_OID,
            expected.trigger_type,
            "O",
            False,
            b"",
            None,
            "",
            0,
            _FUNCTION_OID,
        )
        for expected in catalog._EXPECTED_018_TRIGGER_ROWS  # noqa: SLF001
    ]


@pytest.mark.parametrize(
    "extra_trigger",
    (
        (
            "okf_rebuild_failure_audit",
            "trg_unexpected_before_insert",
            "prevent_okf_rebuild_failure_audit_mutation",
            _AUDIT_OID,
            7,
            "O",
            False,
            b"",
            None,
            "",
            0,
            _FUNCTION_OID,
        ),
        (
            "okf_rebuild_failure_audit",
            "RI_ConstraintTrigger_internal",
            "RI_FKey_check_ins",
            _AUDIT_OID,
            5,
            "O",
            True,
            b"",
            None,
            "",
            999,
            999,
        ),
    ),
    ids=("ordinary_before_insert", "internal_fk_style"),
)
def test_trigger_attestation_rejects_every_extra_audit_trigger(
    extra_trigger: tuple[object, ...],
) -> None:
    cursor = _CatalogCursor(
        [[_function_row()], [*_expected_trigger_rows(), extra_trigger]]
    )

    with pytest.raises(ValueError, match="^executed_failed$"):
        catalog._assert_trigger_rows(  # noqa: SLF001
            cursor, {"okf_rebuild_failure_audit": _AUDIT_OID}
        )


def test_trigger_attestation_accepts_exact_inventory_and_queries_by_audit_oid() -> None:
    cursor = _CatalogCursor([[_function_row()], _expected_trigger_rows()])

    catalog._assert_trigger_rows(  # noqa: SLF001
        cursor, {"okf_rebuild_failure_audit": _AUDIT_OID}
    )

    trigger_query, parameters = cursor.executed[1]
    assert "WHERE trigger_row.tgrelid = %s" in trigger_query
    assert "procedure_schema" not in trigger_query
    assert "trigger_row.tgname) = ANY" not in trigger_query
    assert parameters == (_AUDIT_OID,)


def test_append_only_function_comparison_ignores_punctuation_adjacent_whitespace() -> (
    None
):
    expected = catalog._EXPECTED_018_APPEND_ONLY_FUNCTION  # noqa: SLF001

    assert (
        catalog._validate_append_only_function_row(  # noqa: SLF001
            _function_row(
                "BEGIN RAISE EXCEPTION 'okf_rebuild_failure_audit is append-only';END;"
            ),
            expected,
        )
        == _FUNCTION_OID
    )
    with pytest.raises(ValueError, match="^executed_failed$"):
        catalog._validate_append_only_function_row(  # noqa: SLF001
            _function_row("BEGIN RAISE EXCEPTION 'altered body';END;"), expected
        )


def _trigger_attestation_blocks(sql: str) -> tuple[str, str, str, str]:
    initial = sql.split("-- Retained 018 append-only triggers", maxsplit=1)[1].split(
        ") INTO fresh_trigger_shape;", maxsplit=1
    )[0]
    final_classifier = sql.split("IF final_signature THEN", maxsplit=1)[1].split(
        "-- Detection-only final re-attestation.", maxsplit=1
    )[0]
    final_exit = sql.split("-- Detection-only final re-attestation.", maxsplit=1)[
        1
    ].split("RETURN;", maxsplit=1)[0]
    fresh_exit = sql.split("-- Detection-only fresh re-attestation.", maxsplit=1)[
        1
    ].split("END\n$e2a019$", maxsplit=1)[0]
    return initial, final_classifier, final_exit, fresh_exit


def test_each_trigger_attestation_locally_counts_all_audit_trigger_rows() -> None:
    sql = _SQL_PATH.read_text(encoding="utf-8")

    for attestation in _trigger_attestation_blocks(sql):
        observed_start = attestation.index(
            "FROM pg_catalog.pg_trigger AS observed_trigger"
        )
        comparison_start = attestation.index(") <> (")
        observed_count = attestation[observed_start:comparison_start]
        right_hand_comparison = attestation[comparison_start + len(") <> (") :]
        assert attestation.count("WITH expected(trigger_name, expected_type) AS (") == 1
        assert attestation.count("FROM pg_catalog.pg_trigger AS observed_trigger") == 1
        assert attestation.count("WHERE observed_trigger.tgrelid = audit_oid") == 1
        assert "tgisinternal" not in observed_count
        assert "tgname" not in observed_count
        assert "procedure" not in observed_count
        assert "function" not in observed_count
        assert "SELECT pg_catalog.count(*)" in right_hand_comparison
        assert "FROM expected" in right_hand_comparison


def _lexical_wrapper_scanners(sql: str) -> tuple[str, str, str, str]:
    initial = sql.split("FOR e2a_normalize_expression_side IN 1..4 LOOP", maxsplit=1)[
        1
    ].split("-- Final signature first", maxsplit=1)[0]
    final_classifier = sql.split(
        "FOR e2a_normalize_expression_side IN 1..2 LOOP", maxsplit=1
    )[1].split("IF final_signature THEN", maxsplit=1)[0]
    final_exit = sql.split("-- Detection-only final re-attestation.", maxsplit=1)[
        1
    ].split("RETURN;", maxsplit=1)[0]
    fresh_exit = sql.split("-- Detection-only fresh re-attestation.", maxsplit=1)[
        1
    ].split("END\n$e2a019$", maxsplit=1)[0]
    return initial, final_classifier, final_exit, fresh_exit


def test_each_sql_lexical_wrapper_scanner_is_delimited_and_locally_fail_closed() -> (
    None
):
    sql = _SQL_PATH.read_text(encoding="utf-8")

    for scanner in _lexical_wrapper_scanners(sql):
        assert "e2a_normalize_expression_comment_depth := 1" in scanner
        assert (
            "e2a_normalize_expression_comment_depth := e2a_normalize_expression_comment_depth + 1"
            in scanner
        )
        assert "e2a_normalize_expression_character IN ('''', '\"')" in scanner
        assert (
            "pg_catalog.substr(e2a_normalize_expression_input, "
            "e2a_normalize_expression_index - 1, 1) IN ('E', 'e')" in scanner
        )
        assert "e2a_normalize_expression_character = '$'" in scanner
        assert "e2a_normalize_expression_next = 0" in scanner
        assert "e2a_normalize_expression_depth < 0" in scanner
        assert "e2a_normalize_expression_depth <> 0" in scanner
        assert (
            "WHILE pg_catalog.left(e2a_normalize_expression_output, 1) = '('" in scanner
        )
        assert "pg_catalog.length(e2a_normalize_expression_output) - 2" in scanner
