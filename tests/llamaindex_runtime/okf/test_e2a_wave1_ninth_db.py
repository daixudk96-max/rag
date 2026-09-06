"""Phase-15 Wave-1 ninth-remediation catalog-contract regressions.

These tests are static or fake-backed only. They do not open PostgreSQL or Docker.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from llamaindex_runtime.okf import e2a_disposable_acceptance as acceptance

_MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "llamaindex_runtime"
    / "registry"
    / "migrations"
    / "019_e2a_materialization_contract.sql"
)


def _constraint(name: str) -> acceptance._ConstraintExpectation:
    return next(
        item
        for item in acceptance._EXPECTED_019_CONSTRAINT_ROWS  # noqa: SLF001
        if item.name == name
    )


def test_ownership_target_contract_requires_a_nonnull_matching_branch_target() -> None:
    expected = _constraint("chk_okf_manual_fact_ownership_target")
    body = acceptance._check_body(expected.definition)  # noqa: SLF001
    sql = _MIGRATION.read_text(encoding="utf-8")

    assert "(entity_id IS NOT NULL)" in body
    assert "(relation_id IS NOT NULL)" in body
    assert "(entity_id = fact_id)" in body
    assert "(relation_id = fact_id)" in body
    assert sql.count("CONSTRAINT chk_okf_manual_fact_ownership_target CHECK") == 1
    assert sql.count("('chk_okf_manual_fact_ownership_target', ownership_oid") == 2
    assert sql.count("(entity_id IS NOT NULL) AND (entity_id = fact_id)") == 2
    assert sql.count("(relation_id IS NOT NULL) AND (relation_id = fact_id)") == 2


def test_ownership_path_contract_matches_casted_pg_get_expr_shape_and_rejects_uncast_drift() -> (
    None
):
    expected = _constraint("chk_okf_manual_fact_ownership_path")
    expected_body = acceptance._check_body(expected.definition)  # noqa: SLF001
    deparsed_body = (
        "okf_relative_path <> ''::text AND "
        "okf_relative_path !~ '^(?:/|\\\\)'::text AND "
        "okf_relative_path !~ '/$'::text AND "
        "okf_relative_path !~ '//'::text AND "
        "okf_relative_path !~ '(^|/)(\\.|\\.\\.)(/|$)'::text AND "
        "okf_relative_path !~ '[\\\\:]'::text AND "
        "okf_relative_path !~ '(^|/)[^/]*[. ](/|$)'::text AND "
        "okf_relative_path !~* '(^|/)(con|prn|aux|nul|com[1-9]|lpt[1-9])(\\.[^/]*)?(/|$)'::text"
    )
    sql = _MIGRATION.read_text(encoding="utf-8")

    assert acceptance._expressions_match(deparsed_body, expected_body)  # noqa: SLF001
    assert not acceptance._expressions_match(  # noqa: SLF001
        deparsed_body.replace("''::text", "''", 1), expected_body
    )
    for literal in (
        "''::text",
        "'^(?:/|\\\\)'::text",
        "'/$'::text",
        "'//'::text",
        "'(^|/)(\\.|\\.\\.)(/|$)'::text",
        "'[\\\\:]'::text",
        "'(^|/)[^/]*[. ](/|$)'::text",
        "'(^|/)(con|prn|aux|nul|com[1-9]|lpt[1-9])(\\.[^/]*)?(/|$)'::text",
    ):
        assert literal in expected_body
        assert sql.count(literal) >= 2


@pytest.mark.parametrize(
    "value",
    (
        "x$tag$",
        "x$1$",
        "x$tag$ $_tag$ body $_tag$",
    ),
)
def test_definition_preserves_identifiers_containing_dollars_and_valid_delimiters(
    value: str,
) -> None:
    assert acceptance._definition(value) == value  # noqa: SLF001


@pytest.mark.parametrize(
    "value",
    (
        "$tag-$tag$ body $tag$",
        "x$tag$ $tag$ body",
    ),
)
def test_definition_rejects_malformed_or_unclosed_eligible_dollar_quotes(
    value: str,
) -> None:
    with pytest.raises(ValueError, match="^executed_failed$"):
        acceptance._definition(value)  # noqa: SLF001


def test_rollback_only_probe_rejects_ownership_rows_with_missing_branch_targets() -> (
    None
):
    probe = acceptance._SEMANTIC_PROBE  # noqa: SLF001

    for label, kind, fact_id in (
        (
            "e2a_probe_entity_owner_without_entity_target",
            "entity",
            "00000000-0000-0000-0000-000000000104",
        ),
        (
            "e2a_probe_relation_owner_without_relation_target",
            "relation",
            "00000000-0000-0000-0000-000000000106",
        ),
    ):
        assert label in probe
        assert f"'{kind}',\n              '{fact_id}'" in probe
    assert probe.count("EXCEPTION WHEN check_violation THEN NULL; END;") >= 4
