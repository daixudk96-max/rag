"""Wave-1 thirteenth-remediation checks without PostgreSQL or Docker.

Covers the disposable SQL lexer regression checks and the formerly affected
15-module collection/execution regression. Track-A scope only.
"""

from __future__ import annotations

import subprocess
import sys
import typing
from collections.abc import Mapping
from pathlib import Path

import pytest

from llamaindex_runtime.okf import e2a_disposable_sql_lexer as lexer
from llamaindex_runtime.okf.e2a_contracts import Outcome
from okf._e2a_pipeline_testkit import (
    E2aOutcomeType,
    _FakeReconciler,
    _make_reconciliation_result,
)

_ROOT = Path(__file__).resolve().parents[3]
_SQL_PATH = (
    _ROOT
    / "llamaindex_runtime"
    / "registry"
    / "migrations"
    / "019_e2a_materialization_contract.sql"
)

# The 15 formerly affected modules whose shared _FakeReconciler import once
# broke collection.  The regression test must prove they collect together under
# normal pytest import semantics, not mere source compilation.
_FORMERLY_AFFECTED_MODULE_NAMES: tuple[str, ...] = (
    "test_chunking_strategies.py",
    "test_evidence_object.py",
    "test_kag_schema.py",
    "test_kg_graphrag_enrichment.py",
    "test_kg_persistence.py",
    "test_live_ingestion_postgres.py",
    "test_overlap_refinery.py",
    "test_pageindex_comparison.py",
    "test_summary_index.py",
    "test_tree_rollup_query.py",
    "test_tree_expansion.py",
    "test_tree_persistence.py",
    "test_tree_scoring_pruning.py",
    "test_tree_summary.py",
    "test_vector_persistence.py",
)

# ---------------------------------------------------------------------------
# Subprocess environment + execution proof (Defects C, D, E)
# ---------------------------------------------------------------------------

_TESTS_LLM_ROOT = _ROOT / "tests" / "llamaindex_runtime"

# Minimal explicit safe allowlist for subprocess pytest execution.
# Deliberately EXCLUDES from the parent: PYTEST_ADDOPTS, PYTEST_DEBUG,
# PYTEST_CURRENT_TEST, PYTHONPATH (parent value), PYTHONHOME, and every
# credential / database / libpq / Wave 2 authorization variable.
# PYTHONPATH is set to a FIXED non-secret test path separately by the builder.
_COLLECTION_ALLOWED_ENV_VARS: frozenset[str] = frozenset(
    {
        # Python interpreter operation (no PYTHONPATH/PYTHONHOME from parent)
        "PATH",
        "PYTHONIOENCODING",
        "PYTHONUTF8",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONBREAKPOINT",
        # Windows-specific platform paths
        "SYSTEMROOT",
        "SYSTEMDRIVE",
        "TEMP",
        "TMP",
        "HOME",
        "USERPROFILE",
        "LOCALAPPDATA",
        "APPDATA",
        # Locale
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
    }
)


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        ("", ""),
        ("left -- ignored\n right", "left right"),
        ("left /* outer /* inner */ outer */ right", "left right"),
        ("(value = ')')", "(value = ')')"),
        (r"(value = E'\\)')", r"(value = E'\\)')"),
        ("(value = U&')')", "(value = U&')')"),
        ('("column)")', '("column)")'),
        ("(value = $$)$$)", "(value = $$)$$)"),
        ("(value = $tag$)$tag$)", "(value = $tag$)$tag$)"),
        ("'it''s (still) quoted'", "'it''s (still) quoted'"),
    ),
)
def test_lexer_normalizes_lexically_significant_tokens_exactly(
    value: str, expected: str
) -> None:
    assert lexer._definition(value) == expected  # noqa: SLF001


@pytest.mark.parametrize(
    "value",
    (
        None,
        0,
        "/* unterminated",
        "*/",
        ")",
        "(",
        "'unterminated",
        '"unterminated',
        r"E'\\",
        "$$unterminated",
        "$tag$unterminated",
        "$tag",
        "$_",
        "$tag-",
        "$1",
        "$12abc",
        "$1$",
        "$猫$",
        "$tag猫$",
    ),
)
def test_lexer_rejects_malformed_or_incomplete_input(value: object) -> None:
    with pytest.raises(ValueError, match="^executed_failed$"):
        lexer._definition(value)  # type: ignore[arg-type]  # noqa: SLF001


@pytest.mark.parametrize(
    ("value", "start", "expected"),
    (
        ("$$body$$", 0, "$$"),
        ("$tag$body$tag$", 0, "$tag$"),
        ("$tag", 0, None),
        ("$1$", 0, None),
        ("x$tag$", 1, "$tag$"),
        ("text", 0, None),
    ),
)
def test_dollar_delimiter_table(value: str, start: int, expected: str | None) -> None:
    assert lexer._dollar_delimiter(value, start) == expected  # noqa: SLF001


@pytest.mark.parametrize(
    ("value", "start", "expected"),
    (
        ("$", 0, False),
        ("$tag", 0, True),
        ("$_", 0, True),
        ("$tag-", 0, True),
        ("$1", 0, True),
        ("$1$", 0, True),
        ("$猫", 0, True),
        ("$tag猫", 0, True),
        ("$$", 0, False),
        ("$tag$", 0, False),
    ),
)
def test_invalid_dollar_delimiter_table(value: str, start: int, expected: bool) -> None:
    assert lexer._is_invalid_dollar_delimiter(value, start) is expected  # noqa: SLF001
    assert (
        lexer._is_malformed_dollar_delimiter(value, start) is expected
    )  # noqa: SLF001


@pytest.mark.parametrize(
    ("value", "start", "expected"),
    (
        ("$tag$", 0, True),
        ("x$tag$", 1, False),
        ("猫$tag$", 1, False),
        (" $tag$", 1, True),
    ),
)
def test_dollar_quote_eligibility_respects_identifier_adjacency(
    value: str, start: int, expected: bool
) -> None:
    assert lexer._is_dollar_quote_eligible(value, start) is expected  # noqa: SLF001


@pytest.mark.parametrize(
    ("actual", "expected", "matches"),
    (
        ("(value = ')')", "value = ')'", True),
        ("((value = $tag$)$tag$))", "value = $tag$)$tag$", True),
        ('(("quoted)") )', '"quoted)"', True),
        ("(left) OR (right)", "left OR right", False),
        ("(value = ')') OR (other = '(')", "value = ')' OR other = '('", False),
    ),
)
def test_outer_wrapper_reference_is_quote_aware_and_non_whole_safe(
    actual: str, expected: str, matches: bool
) -> None:
    assert lexer._expressions_match(actual, expected) is matches  # noqa: SLF001


@pytest.mark.parametrize(
    ("actual", "expected", "matches"),
    (
        (
            "CHECK (((okf_relative_path <> ''::text)))",
            "CHECK (okf_relative_path <> ''::text)",
            True,
        ),
        ("CHECK ((value = ')'))", "CHECK (value = ')')", True),
        ("CHECK ((value = $tag$)$tag$))", "CHECK (value = $tag$)$tag$)", True),
        ('CHECK (("column)" IS NOT NULL))', 'CHECK ("column)" IS NOT NULL)', True),
        (
            "CHECK (value = ')') OR (other = '(')",
            "CHECK (value = ')' OR other = '(')",
            False,
        ),
        ("not a check", "CHECK (value = 1)", False),
    ),
)
def test_check_wrapper_reference_matches_only_complete_outer_wrappers(
    actual: str, expected: str, matches: bool
) -> None:
    assert lexer._check_definitions_match(actual, expected) is matches  # noqa: SLF001


@pytest.mark.parametrize(
    ("value", "wrapped"),
    (
        ("(value = ')')", True),
        ("((value = $tag$)$tag$))", True),
        ('("column)")', True),
        ("(left) OR (right)", False),
        ("value = ')'", False),
    ),
)
def test_wrapper_reference_identifies_only_complete_outer_parentheses(
    value: str, wrapped: bool
) -> None:
    assert (
        lexer._is_wrapped_in_parentheses(  # noqa: SLF001
            lexer._definition(value)  # noqa: SLF001
        )
        is wrapped
    )


def _normalizer_copy(sql: str, loop_marker: str) -> str:
    return sql.split(loop_marker, maxsplit=1)[1].split(
        "IF e2a_normalize_expression_side", maxsplit=1
    )[0]


def _outer_wrapper_copies(sql: str) -> tuple[str, str]:
    marker = "WHILE pg_catalog.left(e2a_normalize_expression_output, 1) = '('"
    normalizers = (
        _normalizer_copy(sql, "FOR e2a_normalize_expression_side IN 1..4 LOOP"),
        _normalizer_copy(sql, "FOR e2a_normalize_expression_side IN 1..2 LOOP"),
    )
    first_normalizer, second_normalizer = normalizers
    assert all(normalizer.count(marker) == 1 for normalizer in normalizers)
    return (
        first_normalizer.split(marker, maxsplit=1)[1],
        second_normalizer.split(marker, maxsplit=1)[1],
    )


def test_each_inline_normalizer_rejects_eligible_incomplete_ascii_dollars() -> None:
    sql = _SQL_PATH.read_text(encoding="utf-8")
    normalizers = (
        (
            _normalizer_copy(sql, "FOR e2a_normalize_expression_side IN 1..4 LOOP"),
            "e2a_preflight_audit_check_drift",
        ),
        (
            _normalizer_copy(sql, "FOR e2a_normalize_expression_side IN 1..2 LOOP"),
            "e2a_preflight_final_catalog_drift",
        ),
    )

    for normalizer, error in normalizers:
        generic_guard = normalizer.split("FROM '^\\$[A-Za-z_0-9]'", maxsplit=1)[
            1
        ].split("END IF;", maxsplit=1)[0]
        assert "FROM '^\\$[^[:ascii:]]'" in normalizer
        assert "FROM '^\\$[A-Za-z_][A-Za-z_0-9]*[^[:ascii:]]'" in normalizer
        assert f"RAISE EXCEPTION '{error}'" in generic_guard


def test_each_sql_outer_wrapper_scan_is_lexical_not_raw_parenthesis_counting() -> None:
    sql = _SQL_PATH.read_text(encoding="utf-8")

    for wrapper in _outer_wrapper_copies(sql):
        assert "e2a_normalize_expression_character = '$'" in wrapper
        assert "e2a_normalize_expression_character IN ('''', '\"')" in wrapper
        assert "e2a_normalize_expression_tag := substring" in wrapper
        assert "e2a_normalize_expression_escape :=" in wrapper
        assert "e2a_normalize_expression_next := position" in wrapper


def test_final_and_fresh_paths_requery_function_and_trigger_contracts_at_exit() -> None:
    sql = _SQL_PATH.read_text(encoding="utf-8")
    final_branch, fresh_branch = sql.split(
        "-- Only the exact fresh signature reaches this DDL phase.", maxsplit=1
    )
    final_branch = final_branch.split("IF final_signature THEN", maxsplit=1)[1]
    reattestation_markers = (
        "-- Detection-only final re-attestation.",
        "-- Detection-only fresh re-attestation.",
    )

    for branch, marker, error in zip(
        (final_branch, fresh_branch),
        reattestation_markers,
        ("e2a_preflight_final_catalog_drift", "e2a_preflight_audit_check_drift"),
        strict=True,
    ):
        reattestation = branch.split(marker, maxsplit=1)[1]
        assert "procedure_row.prosrc" in reattestation
        assert "procedure_row.prokind" in reattestation
        assert "language_row.lanname" in reattestation
        assert "append_only_function_final_oid" in reattestation
        assert (
            "e2a_normalize_expression_input := append_only_function_final_source"
            in reattestation
        )
        assert "append_only_function_final_source_matches" in reattestation
        assert (
            "IS NOT DISTINCT FROM append_only_function_source_expected" in reattestation
        )
        assert (
            "append_only_function_final_oid IS DISTINCT FROM append_only_function_oid"
            in reattestation
        )
        assert (
            "trigger_row.tgfoid IS DISTINCT FROM append_only_function_final_oid"
            in reattestation
        )
        assert error in reattestation

    assert final_branch.index(reattestation_markers[0]) > final_branch.index(
        "IF final_row_drift THEN"
    )
    assert final_branch.index(reattestation_markers[0]) < final_branch.rindex("RETURN;")
    assert fresh_branch.index(reattestation_markers[1]) > fresh_branch.rindex(
        "VALIDATE CONSTRAINT"
    )
    assert fresh_branch.index(reattestation_markers[1]) < fresh_branch.rindex(
        "END\n$e2a019$"
    )


def test_migration_remains_one_do_block_and_classifies_before_ddl() -> None:
    sql = _SQL_PATH.read_text(encoding="utf-8")
    classification, ddl = sql.split(
        "-- Only the exact fresh signature reaches this DDL phase.", maxsplit=1
    )

    assert sql.count("DO $e2a019$") == 1
    assert "CREATE FUNCTION" not in sql
    assert "CREATE OR REPLACE FUNCTION" not in sql
    assert "ALTER TABLE" not in classification
    assert "CREATE TABLE" not in classification
    assert "CREATE INDEX" not in classification
    assert "VALIDATE CONSTRAINT" in ddl


def test_touched_python_and_regression_files_stay_under_line_caps() -> None:
    paths = (
        _ROOT / "llamaindex_runtime" / "okf" / "e2a_disposable_sql_lexer.py",
        Path(__file__),
    )

    assert all(
        len(path.read_text(encoding="utf-8").splitlines()) < 800 for path in paths
    )


def _build_subprocess_env(
    parent_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build a minimal explicit environment for subprocess pytest execution.

    Uses direct lookup of fixed safe names only. Never iterates, copies, or
    scans the parent environment (no ``.keys()``, ``.items()``, ``.copy()``,
    ``dict(os.environ)``, or platform-wide casefold maps). On Windows the
    native ``os.environ`` is case-insensitive, so canonical-case direct lookup
    resolves variants without iteration.

    Accepts an injectable ``Mapping[str, str]`` for synthetic tests so the real
    ``os.environ`` is never read by tests. The fixed ``PYTHONPATH`` is a
    non-secret test-directory path required solely so the Track-A call-phase
    guard plugin can be loaded via ``-p`` before collection's prepend mode.
    """
    import os

    source: Mapping[str, str] = parent_env if parent_env is not None else os.environ
    result: dict[str, str] = {}
    for key in _COLLECTION_ALLOWED_ENV_VARS:
        value = source.get(key)
        if value is not None:
            result[key] = value
    # Fixed, non-secret PYTHONPATH enables the call-phase guard plugin load.
    result["PYTHONPATH"] = str(_TESTS_LLM_ROOT)
    return result


def _assert_env_is_safe(env: Mapping[str, str]) -> None:
    """Assert the subprocess env contains only allowlisted keys plus fixed PYTHONPATH."""
    allowed = _COLLECTION_ALLOWED_ENV_VARS | {"PYTHONPATH"}
    bad = [k for k in env if k not in allowed]
    assert not bad, f"Non-allowlisted env keys present: {sorted(bad)}"
    # The PYTHONPATH must be the fixed test path, never a parent-derived value.
    assert env.get("PYTHONPATH") == str(_TESTS_LLM_ROOT)


# ---------------------------------------------------------------------------
# Behavioral tests: Defects A, B, D, C
# ---------------------------------------------------------------------------


class TestFakeReconcilerResetSemantics:
    """Defect A: deterministic class-level call tracking with honest reset."""

    def test_class_assignment_resets_honestly(self) -> None:
        r = _FakeReconciler()
        r.reconcile(None, None)
        r.reconcile(None, None)
        assert _FakeReconciler.calls == 2
        _FakeReconciler.calls = 0
        r.reconcile(None, None)
        assert _FakeReconciler.calls == 1

    def test_reset_calls_across_preexisting_instances(self) -> None:
        _FakeReconciler.calls = 0
        a = _FakeReconciler()
        b = _FakeReconciler()
        a.reconcile(None, None)
        b.reconcile(None, None)
        assert _FakeReconciler.calls == 2
        a.reset_calls()
        assert _FakeReconciler.calls == 0
        b.reconcile(None, None)
        assert _FakeReconciler.calls == 1

    def test_no_stale_state_after_instance_lifecycle(self) -> None:
        _FakeReconciler.calls = 0
        r = _FakeReconciler()
        r.reconcile(None, None)
        del r
        _FakeReconciler.calls = 0
        r2 = _FakeReconciler()
        r2.reconcile(None, None)
        assert _FakeReconciler.calls == 1

    def test_multiple_instances_accumulate(self) -> None:
        _FakeReconciler.calls = 0
        a = _FakeReconciler()
        b = _FakeReconciler()
        a.reconcile(None, None)
        b.reconcile(None, None)
        b.reconcile(None, None)
        assert _FakeReconciler.calls == 3


class TestOutcomeTypeAlignment:
    """Defect B: E2aOutcomeType matches the real contract Outcome."""

    def test_outcome_type_matches_contract(self) -> None:
        assert set(typing.get_args(E2aOutcomeType)) == set(typing.get_args(Outcome))

    def test_factory_rejects_invalid_error_literal(self) -> None:
        with pytest.raises(ValueError):
            _make_reconciliation_result("error")  # type: ignore[arg-type]

    def test_factory_rejects_invalid_rollback_literal(self) -> None:
        with pytest.raises(ValueError):
            _make_reconciliation_result("rollback")  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "outcome",
        (
            "changed",
            "no_op",
            "rolled_back_failure",
            "acceptance_blocked",
            "outcome_unknown",
        ),
    )
    def test_factory_accepts_all_contract_outcomes(self, outcome: str) -> None:
        result = _make_reconciliation_result(outcome)  # type: ignore[arg-type]
        assert result.outcome == outcome


class TestSubprocessEnvironmentSecurity:
    """Defect D: minimal explicit safe allowlist, direct lookup only."""

    def test_reads_only_allowed_keys_from_synthetic_mapping(self) -> None:
        synthetic = {
            "PATH": "/usr/bin",
            "DATABASE_URL": "secret-value",
            "OKF_E2A_DISPOSABLE_TEST_AUTHORIZED": "1",
            "PGPASSWORD": "secret",
            "PYTEST_ADDOPTS": "--evil",
            "PYTEST_DEBUG": "1",
            "PYTEST_CURRENT_TEST": "evil",
            "PYTHONPATH": "/evil/parent",
            "PYTHONHOME": "/evil",
            "FORMAL_RUNTIME_DATABASE_URL": "secret",
        }
        result = _build_subprocess_env(synthetic)
        for bad in (
            "DATABASE_URL",
            "OKF_E2A_DISPOSABLE_TEST_AUTHORIZED",
            "PGPASSWORD",
            "PYTEST_ADDOPTS",
            "PYTEST_DEBUG",
            "PYTEST_CURRENT_TEST",
            "FORMAL_RUNTIME_DATABASE_URL",
        ):
            assert bad not in result
        assert result["PYTHONPATH"] == str(_TESTS_LLM_ROOT)
        assert "/evil/parent" not in result["PYTHONPATH"]
        assert "PYTHONHOME" not in result

    def test_never_iterates_source_mapping(self) -> None:
        class _NoIteration(Mapping[str, str]):
            def __init__(self, data: dict[str, str]) -> None:
                self._d = data

            def __getitem__(self, key: str) -> str:
                return self._d[key]

            def __iter__(self) -> None:
                raise AssertionError("source mapping must not be iterated")

            def __len__(self) -> int:
                raise AssertionError("source mapping must not be sized")

        synthetic = _NoIteration({"PATH": "/usr/bin", "DATABASE_URL": "x"})
        result = _build_subprocess_env(synthetic)
        assert "DATABASE_URL" not in result

    def test_injectable_mapping_does_not_copy_real_environment(self) -> None:
        synthetic = {"PATH": "/synthetic"}
        result = _build_subprocess_env(synthetic)
        assert result.get("PATH") == "/synthetic"
        assert set(result.keys()) <= (_COLLECTION_ALLOWED_ENV_VARS | {"PYTHONPATH"})

    def test_result_contains_only_allowlisted_keys_plus_fixed_pythonpath(self) -> None:
        result = _build_subprocess_env()
        allowed = _COLLECTION_ALLOWED_ENV_VARS | {"PYTHONPATH"}
        assert set(result.keys()) <= allowed

    def test_database_and_auth_vars_excluded_from_real_env(self) -> None:
        result = _build_subprocess_env()
        for bad in (
            "DATABASE_URL",
            "FORMAL_RUNTIME_DATABASE_URL",
            "OKF_E2A_DISPOSABLE_TEST_AUTHORIZED",
            "OKF_REBUILD_DOCKER_ACCEPTANCE",
            "PGPASSWORD",
            "PGHOST",
        ):
            assert bad not in result


class TestCallPhaseGuardPlugin:
    """Defect C: the guard plugin forces nonzero when a module lacks a call phase."""

    def test_plugin_forces_nonzero_when_no_calls(self) -> None:
        from okf._e2a_call_phase_guard import (
            _called_modules,
            _collected_modules,
            pytest_collection_modifyitems,
            pytest_sessionfinish,
        )

        _collected_modules.clear()
        _called_modules.clear()

        class _Item:
            fspath = "/repo/tests/m.py"

        class _Session:
            class config:
                class option:
                    collectonly = False

            exitstatus = 0

        pytest_collection_modifyitems(None, [_Item()])
        # No runtest_call -> module lacks call phase
        pytest_sessionfinish(_Session, 0)
        assert _Session.exitstatus == 1

    def test_plugin_passes_when_all_modules_called(self) -> None:
        from okf._e2a_call_phase_guard import (
            _called_modules,
            _collected_modules,
            pytest_collection_modifyitems,
            pytest_runtest_call,
            pytest_sessionfinish,
        )

        _collected_modules.clear()
        _called_modules.clear()

        class _Item:
            fspath = "/repo/tests/m.py"

        class _Session:
            class config:
                class option:
                    collectonly = False

            exitstatus = 0

        pytest_collection_modifyitems(None, [_Item()])
        pytest_runtest_call(_Item())
        pytest_sessionfinish(_Session, 0)
        assert _Session.exitstatus == 0

    def test_plugin_skips_enforcement_during_collect_only(self) -> None:
        from okf._e2a_call_phase_guard import (
            _called_modules,
            _collected_modules,
            pytest_collection_modifyitems,
            pytest_sessionfinish,
        )

        _collected_modules.clear()
        _called_modules.clear()

        class _Item:
            fspath = "/repo/tests/m.py"

        class _Session:
            class config:
                class option:
                    collectonly = True

            exitstatus = 0

        pytest_collection_modifyitems(None, [_Item()])
        pytest_sessionfinish(_Session, 0)
        assert _Session.exitstatus == 0


# ---------------------------------------------------------------------------
# Main regression test: Defect C
# ---------------------------------------------------------------------------


def test_all_wave1_modules_collect_and_run_together() -> None:
    """Regression: prove formerly uncollectable modules collect AND execute together.

    A real ``pytest --collect-only`` subprocess exercises normal pytest import
    and collection semantics. A second real ``pytest`` subprocess executes the
    15 modules and loads the Track-A call-phase guard plugin, which forces a
    nonzero exit if any collected module never reached a test call phase
    (all-skipped is not valid proof).

    Both subprocesses use ``subprocess.DEVNULL`` for stdout/stderr: no raw child
    output is captured, parsed, logged, interpolated, or persisted. Only the
    bounded return code and a static timeout error are observed.
    """
    # Exercise the private testkit fake (compatible API preserved).
    _FakeReconciler.calls = 0
    reconciler = _FakeReconciler()
    reconciled = reconciler.reconcile(None, None)
    assert reconciled.outcome == "no_op"
    assert _FakeReconciler.calls == 1
    _FakeReconciler.calls = 0

    factory_result = _make_reconciliation_result("changed")
    assert factory_result.outcome == "changed"

    # Resolve the 15 formerly affected modules relative to the repo root.
    tests_dir = Path("tests") / "llamaindex_runtime"
    module_args = [str(tests_dir / name) for name in _FORMERLY_AFFECTED_MODULE_NAMES]
    for name in _FORMERLY_AFFECTED_MODULE_NAMES:
        assert (_ROOT / tests_dir / name).exists(), f"Test module not found: {name}"

    subprocess_env = _build_subprocess_env()
    _assert_env_is_safe(subprocess_env)

    ignore_self = f"--ignore={Path(__file__).resolve()}"

    # --- Phase 1: Collection proof (real pytest --collect-only) ---
    collect_cmd = [
        sys.executable,
        "-m",
        "pytest",
        "--collect-only",
        "-q",
        "-p",
        "no:cacheprovider",
        ignore_self,
        *module_args,
    ]
    try:
        collect_completed = subprocess.run(
            collect_cmd,
            cwd=_ROOT,
            env=subprocess_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("pytest collection timed out (bounded static 180s)")

    assert (
        collect_completed.returncode == 0
    ), "pytest collection failed (nonzero exit status)"

    # --- Phase 2: Execution proof (real pytest with call-phase guard) ---
    execute_cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        "-p",
        "okf._e2a_call_phase_guard",
        "--no-header",
        "--tb=no",
        "-rN",
        ignore_self,
        *module_args,
    ]
    try:
        execute_completed = subprocess.run(
            execute_cmd,
            cwd=_ROOT,
            env=subprocess_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("pytest execution timed out (bounded static 600s)")

    assert (
        execute_completed.returncode == 0
    ), "pytest execution failed (nonzero exit status or missing call phase)"


class TestNoOutputCaptureInvariant:
    """Defect C: static invariant check that DEVNULL is used, not capture."""

    def test_subprocess_invocation_uses_devnull(self) -> None:
        """Verify the main test's subprocess calls use DEVNULL."""
        source = Path(__file__).read_text(encoding="utf-8")
        main_test_start = source.find(
            "def test_all_wave1_modules_collect_and_run_together"
        )
        assert main_test_start != -1, "main test not found"
        # Find the end of the main test function (next top-level def)
        main_test_block = source[main_test_start:]
        main_test_end = main_test_block.find("\n\ndef ")
        if main_test_end != -1:
            main_test_block = main_test_block[:main_test_end]
        # Verify DEVNULL is used for stdout/stderr in subprocess.run calls
        assert "stdout=subprocess.DEVNULL" in main_test_block
        assert "stderr=subprocess.DEVNULL" in main_test_block
