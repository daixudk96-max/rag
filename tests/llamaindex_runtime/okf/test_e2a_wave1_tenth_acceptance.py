"""Wave-1 tenth source-split and dollar-quote regressions.

These tests use only imports, fake collaborators, and static SQL inspection.  They
never open a PostgreSQL connection or invoke Docker.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from llamaindex_runtime.okf import e2a_disposable_acceptance as acceptance

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


_MODULES = (
    "e2a_disposable_acceptance.py",
    "e2a_disposable_sql_lexer.py",
    "e2a_disposable_catalog_contracts.py",
    "e2a_disposable_catalog.py",
    "e2a_disposable_execution.py",
)
_LEGACY_MOVED_NAMES = (
    "_Connection",
    "_ApplyRollbackFailure",
    "_ProbeRollbackFailure",
    "_ConstraintExpectation",
    "_IndexExpectation",
    "_TriggerExpectation",
    "_is_word_character",
    "_is_ascii_dollar_tag_start",
    "_is_ascii_dollar_tag_continuation",
    "_is_dollar_quote_eligible",
    "_dollar_delimiter",
    "_is_invalid_dollar_delimiter",
    "_is_malformed_dollar_delimiter",
    "_scan_quoted",
    "_append_token",
    "_definition",
    "_check_definitions_match",
    "_expressions_match",
    "_check_body",
    "_strip_outer_parentheses",
    "_is_wrapped_in_parentheses",
    "_fk",
    "_unique",
    "_check",
    "_EXPECTED_019_CONSTRAINT_ROWS",
    "_EXPECTED_019_CONSTRAINTS",
    "_EXPECTED_019_CONSTRAINT_DEFINITIONS",
    "_EXPECTED_019_FK_KEYS",
    "_EXPECTED_019_INDEX_ROWS",
    "_EXPECTED_019_INDEXES",
    "_EXPECTED_018_TRIGGER_ROWS",
    "_EXPECTED_019_INDEX_DEFINITIONS",
    "_EXPECTED_019_COLUMNS",
    "_assert_019_catalog_shape",
    "_expected_relations",
    "_relation_oids",
    "_assert_constraint_rows",
    "_validate_constraint_row",
    "_assert_index_rows",
    "_validate_index_row",
    "_assert_backing_index_rows",
    "_assert_trigger_rows",
    "_assert_column_rows",
    "_attest_connection_target",
    "_apply_catalog",
    "_close",
    "_run_rollback_only_probe",
    "_SEMANTIC_PROBE",
    "FULL_MIGRATION_CATALOG",
)


class _Authority:
    authorized = True


class _Target:
    dbname = "fake"


def test_split_modules_remain_under_the_source_line_cap() -> None:
    for name in _MODULES:
        path = _ROOT / "llamaindex_runtime" / "okf" / name
        assert path.exists(), name
        assert len(path.read_text(encoding="utf-8").splitlines()) < 800, name


def test_contracts_are_independent_of_the_migration_sql_reader() -> None:
    source = (
        _ROOT / "llamaindex_runtime" / "okf" / "e2a_disposable_catalog_contracts.py"
    ).read_text(encoding="utf-8")

    assert ".sql" not in source
    assert "registry.migrations" not in source
    assert "read_text" not in source


def test_facade_reexports_legacy_moved_symbols_and_keeps_runner_seams(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in _LEGACY_MOVED_NAMES:
        assert hasattr(acceptance, name), name
    assert set(_LEGACY_MOVED_NAMES) <= set(acceptance.__all__)

    target = _Target()
    steps: list[str] = []
    monkeypatch.setattr(
        acceptance, "parse_disposable_postgresql_target", lambda *_: target
    )
    monkeypatch.setattr(
        acceptance,
        "_apply_catalog",
        lambda *_args: steps.append("apply"),
    )
    monkeypatch.setattr(
        acceptance,
        "_verify_catalog",
        lambda *_args: steps.append("verify"),
    )

    assert (
        acceptance.run_disposable_migration_acceptance(
            _Authority(), "postgresql://fake", "fake", lambda _: None
        )
        == "executed_pass"
    )
    assert steps == ["apply", "verify", "apply", "verify"]


@pytest.mark.parametrize("value", ("$猫$", "$é$", "$tag猫$", "$tag"))
def test_eligible_non_ascii_or_unclosed_dollar_quotes_fail_closed(value: str) -> None:
    with pytest.raises(ValueError, match="^executed_failed$"):
        acceptance._definition(value)  # noqa: SLF001


@pytest.mark.parametrize("character", ("́", "猫", "😀"))
def test_every_high_bit_codepoint_is_an_identifier_continuation(character: str) -> None:
    assert acceptance._is_word_character(character)  # noqa: SLF001


@pytest.mark.parametrize("value", ("x$猫$", "é$tag$", "😀$tag$", "x$tag$"))
def test_identifier_adjacent_non_ascii_dollar_text_is_not_a_dollar_quote(
    value: str,
) -> None:
    assert acceptance._definition(value) == value  # noqa: SLF001


def test_both_inline_sql_normalizers_treat_high_bit_predecessors_as_identifiers() -> (
    None
):
    sql = _SQL.read_text(encoding="utf-8")
    normalizers = _inline_normalizers(sql)
    predecessor = (
        "pg_catalog.substr(e2a_normalize_expression_input, "
        "e2a_normalize_expression_index - 1, 1)"
    )

    assert (
        sum(
            normalizer.count(f"{predecessor} ~ '^[[:ascii:]]$'")
            for normalizer in normalizers
        )
        == 2
    )
    assert (
        sum(
            normalizer.count(f"{predecessor} !~ '^[A-Za-z0-9_$]$'")
            for normalizer in normalizers
        )
        == 2
    )
    assert (
        sum(
            normalizer.count("FROM '^\\$[A-Za-z_][A-Za-z_0-9]*[^[:ascii:]]'")
            for normalizer in normalizers
        )
        == 2
    )
    assert (
        sum(normalizer.count("FROM '^\\$[^[:ascii:]]'") for normalizer in normalizers)
        == 2
    )


def test_both_inline_sql_lexers_terminate_high_bit_dollar_guard_predicates() -> None:
    sql = _SQL.read_text(encoding="utf-8")
    normalizers = _inline_normalizers(sql)

    assert (
        sum(
            normalizer.count("AND pg_catalog.substr(e2a_normalize_expression_input,")
            for normalizer in normalizers
        )
        >= 4
    )
    assert (
        sum(
            normalizer.count(
                "e2a_normalize_expression_index - 2, 1) !~ '^[A-Za-z0-9_$]$'"
            )
            for normalizer in normalizers
        )
        == 2
    )
