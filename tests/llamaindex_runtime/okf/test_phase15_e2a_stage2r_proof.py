"""Static AST source-proof for the Task #88 Stage 2R tranche (non-live).

Never imports, executes, or collects the live modules; reads source text and
inspects parsed ASTs only, so comments/docstrings cannot cause false
positives or satisfy a check by accident. Pinned for ALL new Stage 2R
modules (helper + two explicitly selected live selectors): auth-first plain
live tests; ``phase15_`` filenames uncollected by default discovery; no
prohibited module families, no pytest/skip/xfail references, no environment
access, no direct connections, no dynamic imports, no fakes; connections
only via ``session.open_fresh_attested_connection()``; PARTIAL(C4-lock-release)
and PARTIAL(v1-v2) disclaimer labels; the C4 lock-release cell never
re-reconciles ``second_desired`` (the release reconcile passes the same
``first_desired`` object) and both cells use default ``E2aReconciler()``
(the C5-only audit-factory policy is unchanged); failures absorb into
redacted observations via the bounded ``_error_reason``; failed cells raise
RuntimeError carrying only ``observations.error_reason``; the superseded C4
identity (``_run_c4_impl`` / ``test_phase15_e2a_task88_c4_default_failure_contract_live``)
is one-run and is never reused or renamed in the new modules; the Task #88
global acceptance selector identity is never referenced; no PASS
language; all three new modules under 800 lines; helper defines no
test functions.

This module complements (never weakens) the Stage 1/2 proof modules; it adds
proofs only for the new Stage 2R surface.
"""

from __future__ import annotations

import ast
from pathlib import Path

_DIR = Path(__file__).parent
_HELPER_PATH = _DIR / "_phase15_e2a_task88_stage2r_cells.py"
_LOCK_RELEASE_PATH = _DIR / "phase15_e2a_task88_stage2r_lock_release.py"
_V1V2_PATH = _DIR / "phase15_e2a_task88_stage2r_v1v2_transition.py"
_ALL_PATHS = (_HELPER_PATH, _LOCK_RELEASE_PATH, _V1V2_PATH)

_PROHIBITED_EXACT_MODULE_NAMES = frozenset(
    {
        "llamaindex_runtime.okf.e2a_disposable_execution",
        "verification.phase15-okf-ingestion-pipeline.run_e2a_verification",
    }
)
_PROHIBITED_MODULE_FRAGMENTS = frozenset(
    "real_e2a_reconciler disposable_acceptance disposable_postgres _real_e2a_".split()
)
_PROHIBITED_TAIL_SEGMENTS = frozenset(
    {"e2a_disposable_execution", "run_e2a_verification"}
)

# Case-insensitive claim phrases that must never appear in the new modules.
_FORBIDDEN_CLAIM_PHRASES = (
    "task #88 pass",
    "task #88 complete",
    "phase 15 pass",
    "phase 15 complete",
)

# Unique identifiers of the Task #88 global acceptance selector machinery.
_TASK88_GLOBAL_ACCEPTANCE_IDENTIFIERS = (
    "test_task88_authorized_live_acceptance",
    "TASK88_REQUIRED_CELL_ID",
    "true_late_dml_failure",
    "phase15_e2a_task88_real_acceptance",
)

_STAGE2R_IMPL_NAMES = ("_run_c4_lock_release_impl", "_run_v1v2_transition_impl")
_STAGE2R_OBSERVATION_TYPES = frozenset(
    {"C4LockReleaseObservations", "V1V2TransitionObservations"}
)
_FORBIDDEN_DIRECT_DB_ATTRIBUTES = frozenset(
    {"cursor", "execute", "fetchone", "fetchall", "commit", "rollback", "connect"}
)
_DYNAMIC_IMPORT_MECHANISM_NAMES = ("importlib", "import_module", "__import__")
_FAKE_MACHINERY_NAMES = ("mock", "MagicMock", "monkeypatch", "unittest", "patch")


def _parse_module(path: Path) -> tuple[ast.Module, str]:
    assert path.is_file(), f"missing expected module: {path}"
    source = path.read_text(encoding="utf-8")
    return ast.parse(source, filename=str(path)), source


def _imported_module_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                names.add(node.module)
            names.update(alias.name for alias in node.names if alias.name != "*")
    return names


def _test_functions(tree: ast.Module) -> list[ast.FunctionDef]:
    return [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    ]


def _function_by_name(tree: ast.Module, name: str) -> ast.FunctionDef:
    functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    assert len(functions) == 1, f"expected exactly one top-level function {name!r}"
    return functions[0]


def _auth_first(fn: ast.FunctionDef) -> bool:
    body = fn.body
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    statement = body[0] if body else None
    return (
        statement is not None
        and isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Call)
        and isinstance(statement.value.func, ast.Name)
        and statement.value.func.id == "_require_authorization"
    )


def _module_is_forbidden(name: str) -> bool:
    if name in _PROHIBITED_EXACT_MODULE_NAMES:
        return True
    if any(fragment in name for fragment in _PROHIBITED_MODULE_FRAGMENTS):
        return True
    return name.rsplit(".", 1)[-1] in _PROHIBITED_TAIL_SEGMENTS


def _finally_close_arguments(fn: ast.FunctionDef) -> set[str]:
    closed: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Try):
            for stmt in node.finalbody:
                call = stmt.value if isinstance(stmt, ast.Expr) else None
                if (
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Name)
                    and call.func.id == "_close_quietly"
                    and call.args
                    and isinstance(call.args[0], ast.Name)
                ):
                    closed.add(call.args[0].id)
    return closed


def _runtime_error_raises(fn: ast.FunctionDef) -> list[ast.Raise]:
    raises: list[ast.Raise] = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Raise) or node.exc is None:
            continue
        call = node.exc
        if not (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "RuntimeError"
            and len(call.args) == 1
        ):
            continue
        raises.append(node)
    return raises


def _raise_message_is_only_observation_error_reason(raise_node: ast.Raise) -> bool:
    call = raise_node.exc
    if call is None or not (isinstance(call, ast.Call) and call.args):
        return False
    message = call.args[0]
    if not isinstance(message, ast.JoinedStr):
        return False
    dynamic_values = [v for v in message.values if isinstance(v, ast.FormattedValue)]
    if len(dynamic_values) != 1:
        return False
    dynamic = dynamic_values[0].value
    return (
        isinstance(dynamic, ast.Attribute)
        and dynamic.attr == "error_reason"
        and isinstance(dynamic.value, ast.Name)
        and dynamic.value.id == "observations"
    )


def _assert_no_environment_access(path: Path) -> None:
    tree, _ = _parse_module(path)
    for name in _imported_module_names(tree):
        assert name != "os", f"{path.name} must not import os"
        assert "dotenv" not in name, f"{path.name} must not import dotenv"
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in ("os", "DATABASE_URL"):
            raise AssertionError(f"{path.name} must not reference os or DATABASE_URL")
        if isinstance(node, ast.Attribute) and node.attr in ("environ", "getenv"):
            raise AssertionError(f"{path.name} must not access process environment")


def _assert_no_pytest_references(path: Path) -> None:
    tree, source = _parse_module(path)
    assert "pytest" not in source.lower(), f"{path.name} must not reference pytest"
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "pytest":
            raise AssertionError(f"{path.name} must not reference pytest")


def _dynamic_import_violations(tree: ast.Module) -> list[str]:
    violations = [
        name
        for name in _imported_module_names(tree)
        if name == "importlib"
        or name.startswith("importlib.")
        or name == "import_module"
    ]
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in _DYNAMIC_IMPORT_MECHANISM_NAMES:
            violations.append(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in (
            "import_module",
            "__import__",
        ):
            violations.append(node.attr)
    return violations


def _e2a_reconciler_calls(fn: ast.FunctionDef) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "E2aReconciler"
    ]


def _reconcile_calls(fn: ast.FunctionDef) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "reconcile"
    ]


def _docstring_normalized(path: Path) -> str:
    doc = ast.get_docstring(_parse_module(path)[0])
    assert doc is not None, f"{path.name} docstring is required"
    return " ".join(doc.split())


# ---------------------------------------------------------------------------
# Files, discovery, and auth-first structure
# ---------------------------------------------------------------------------


def test_stage2r_files_exist() -> None:
    for path in _ALL_PATHS:
        assert path.is_file(), f"missing Stage 2R module: {path}"


def test_stage2r_files_under_800_lines() -> None:
    for path in _ALL_PATHS:
        source = _parse_module(path)[1]
        assert source.count("\n") + 1 < 800, f"{path.name} exceeds 800 lines"


def test_stage2r_selectors_not_collected_by_discovery() -> None:
    for path in (_LOCK_RELEASE_PATH, _V1V2_PATH):
        name = path.name
        assert name.startswith("phase15_"), "selector must use the phase15_ prefix"
        assert not name.startswith("test_"), "selector must not match test_*.py"
        assert not name.endswith("_test.py"), "selector must not match *_test.py"
        assert name.endswith(".py"), "selector must be a python module"


def test_stage2r_selector_test_functions_auth_first() -> None:
    for path in (_LOCK_RELEASE_PATH, _V1V2_PATH):
        tree, _ = _parse_module(path)
        functions = _test_functions(tree)
        assert len(functions) == 1, f"{path.name} must define exactly one live test"
        assert _auth_first(functions[0]), "live test must be auth-first"


def test_stage2r_selector_test_functions_no_decorators_or_fixtures() -> None:
    for path in (_LOCK_RELEASE_PATH, _V1V2_PATH):
        tree, _ = _parse_module(path)
        for fn in _test_functions(tree):
            assert not fn.decorator_list, f"{fn.name} must have no decorators"
            params = fn.args.posonlyargs + fn.args.args + fn.args.kwonlyargs
            assert not params, f"{fn.name} must take no parameters (no fixtures)"


def test_stage2r_selectors_import_require_authorization() -> None:
    for path in (_LOCK_RELEASE_PATH, _V1V2_PATH):
        tree, _ = _parse_module(path)
        found = any(
            isinstance(node, ast.ImportFrom)
            and any(alias.name == "_require_authorization" for alias in node.names)
            for node in ast.walk(tree)
        )
        assert found, f"{path.name} must import _require_authorization"


def test_stage2r_selectors_import_stage2r_helper() -> None:
    for path in (_LOCK_RELEASE_PATH, _V1V2_PATH):
        tree, _ = _parse_module(path)
        found = any(
            isinstance(node, ast.ImportFrom)
            and node.module is not None
            and "stage2r_cells" in node.module
            for node in ast.walk(tree)
        )
        assert found, f"{path.name} must import the Stage 2R helper"


def test_stage2r_helper_defines_no_test_functions() -> None:
    tree, _ = _parse_module(_HELPER_PATH)
    assert not _test_functions(tree), "helper must not define test functions"


# ---------------------------------------------------------------------------
# Security and boundary surface
# ---------------------------------------------------------------------------


def test_stage2r_modules_no_forbidden_imports() -> None:
    for path in _ALL_PATHS:
        tree, _ = _parse_module(path)
        forbidden = [
            name for name in _imported_module_names(tree) if _module_is_forbidden(name)
        ]
        assert not forbidden, f"forbidden import in {path.name}: {forbidden}"


def test_stage2r_modules_no_environment_access() -> None:
    for path in _ALL_PATHS:
        _assert_no_environment_access(path)


def test_stage2r_modules_no_pytest_references() -> None:
    for path in _ALL_PATHS:
        _assert_no_pytest_references(path)


def test_stage2r_modules_no_dynamic_import_mechanisms() -> None:
    for path in _ALL_PATHS:
        violations = _dynamic_import_violations(_parse_module(path)[0])
        assert not violations, f"{path.name} must not use dynamic imports: {violations}"


def test_stage2r_modules_no_fake_machinery() -> None:
    for path in _ALL_PATHS:
        _, source = _parse_module(path)
        lowered = source.lower()
        for token in _FAKE_MACHINERY_NAMES:
            assert token not in lowered, f"{path.name} must not reference {token}"


def test_stage2r_helper_no_direct_database_or_factory_bypass() -> None:
    tree, _ = _parse_module(_HELPER_PATH)
    for name in _imported_module_names(tree):
        assert "psycopg" not in name, f"helper must not import psycopg: {name}"
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr == "connect":
            raise AssertionError("helper must not call .connect(...) directly")


def test_stage2r_selector_no_direct_database_or_reconciler_work() -> None:
    for path in (_LOCK_RELEASE_PATH, _V1V2_PATH):
        tree, _ = _parse_module(path)
        for name in _imported_module_names(tree):
            assert "psycopg" not in name, f"{path.name} must not import psycopg"
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                assert not (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr in _FORBIDDEN_DIRECT_DB_ATTRIBUTES
                ), f"{path.name} must not issue direct database work"
            if isinstance(node, ast.Name) and node.id == "E2aReconciler":
                raise AssertionError(f"{path.name} must not construct the reconciler")


def test_stage2r_helper_all_attested_connections_via_session_openers() -> None:
    """All connections flow through the Stage 1 attested openers, which build
    fresh attested connections from the session; every opener call receives
    the session object and no opener is bypassed."""
    tree, _ = _parse_module(_HELPER_PATH)
    opener_names = {
        "_open_writer_connection",
        "_open_reconciler_primary_connection",
        "_open_observer_connection",
    }
    assert "_phase15_e2a_task88_live_cells" in _imported_module_names(tree)
    for name in opener_names:
        found = any(
            isinstance(node, ast.ImportFrom)
            and node.module == "_phase15_e2a_task88_live_cells"
            and any(alias.name == name for alias in node.names)
            for node in ast.walk(tree)
        )
        assert found, f"helper must import {name}"
    opener_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in opener_names
    ]
    assert opener_calls, "helper must route every connection through an opener"
    for node in opener_calls:
        assert len(node.args) == 1, "opener must take exactly the session"
        assert (
            isinstance(node.args[0], ast.Name) and node.args[0].id == "session"
        ), "opener must receive the session object"


# ---------------------------------------------------------------------------
# Cell structure: redaction, cleanup, bounded diagnostics, default reconciler
# ---------------------------------------------------------------------------


def test_stage2r_helper_observation_types_redacted_repr() -> None:
    tree, source = _parse_module(_HELPER_PATH)
    classes = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name in _STAGE2R_OBSERVATION_TYPES
    }
    assert classes == set(
        _STAGE2R_OBSERVATION_TYPES
    ), f"missing observation types: {classes}"
    repr_functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "__repr__"
    ]
    assert len(repr_functions) == 2, "exactly two observation reprs expected"
    segments = [ast.get_source_segment(source, fn) or "" for fn in repr_functions]
    for segment in segments:
        assert "<redacted>" in segment, "every observation repr must redact details"


def test_stage2r_helper_cells_default_reconciler_only() -> None:
    """Both Stage 2R cells use default E2aReconciler(); the C5-only audit
    factory policy is unchanged and no Stage 2R cell injects a factory."""
    tree, _ = _parse_module(_HELPER_PATH)
    for name in _STAGE2R_IMPL_NAMES:
        fn = _function_by_name(tree, name)
        calls = _e2a_reconciler_calls(fn)
        assert calls, f"{name} must construct E2aReconciler"
        for call in calls:
            assert not call.args, f"{name}: E2aReconciler takes no positional args"
            assert not call.keywords, f"{name}: E2aReconciler must be default"
    _, source = _parse_module(_HELPER_PATH)
    assert (
        "failure_audit_connection_factory" not in source
    ), "Stage 2R cells must not inject the audit factory"


def test_stage2r_helper_cells_close_resources_in_finally() -> None:
    tree, _ = _parse_module(_HELPER_PATH)
    lock_fn = _function_by_name(tree, "_run_c4_lock_release_impl")
    lock_closed = _finally_close_arguments(lock_fn)
    assert {
        "writer_conn",
        "primary_conn",
        "collision_conn",
        "observer_conn",
        "release_conn",
        "release_observer_conn",
    } <= lock_closed, "lock-release cell must close every connection in finally"
    v1v2_fn = _function_by_name(tree, "_run_v1v2_transition_impl")
    v1v2_closed = _finally_close_arguments(v1v2_fn)
    assert {
        "writer_conn",
        "primary_conn",
        "second_primary_conn",
        "observer_conn",
    } <= v1v2_closed, "v1v2 cell must close every connection in finally"


def test_stage2r_helper_cells_bounded_diagnostics() -> None:
    tree, source = _parse_module(_HELPER_PATH)
    assert (
        source.count("error_reason=_error_reason(") >= 2
    ), "each cell must absorb failures into a bounded _error_reason"
    for name in _STAGE2R_IMPL_NAMES:
        fn = _function_by_name(tree, name)
        handlers = [n for n in ast.walk(fn) if isinstance(n, ast.ExceptHandler)]
        assert any(
            isinstance(h.type, ast.Name)
            and h.type.id == "Exception"
            and h.name is not None
            for h in handlers
        ), f"{name} failure path must bind the original exception"


def test_stage2r_selectors_raise_only_observation_error_reason() -> None:
    for path in (_LOCK_RELEASE_PATH, _V1V2_PATH):
        tree, _ = _parse_module(path)
        for fn in _test_functions(tree):
            raises = _runtime_error_raises(fn)
            assert len(raises) == 1, f"{fn.name} must raise exactly one RuntimeError"
            for raise_node in raises:
                assert _raise_message_is_only_observation_error_reason(raise_node)


# ---------------------------------------------------------------------------
# Disclaimer labels, claim language, superseded C4, global acceptance isolation
# ---------------------------------------------------------------------------


def test_stage2r_selector_disclaimer_tokens_present() -> None:
    lock_doc = _docstring_normalized(_LOCK_RELEASE_PATH)
    assert "PARTIAL(C4-lock-release)" in lock_doc
    assert "lock release/idempotence only" in lock_doc
    assert "never C14" in lock_doc
    v1v2_doc = _docstring_normalized(_V1V2_PATH)
    assert "PARTIAL(v1-v2)" in v1v2_doc
    assert "never C14" in v1v2_doc
    assert "late-DML evidence" in v1v2_doc


def test_stage2r_modules_no_task_or_phase_pass_completion_language() -> None:
    for path in _ALL_PATHS:
        _, source = _parse_module(path)
        lowered = source.lower()
        for phrase in _FORBIDDEN_CLAIM_PHRASES:
            assert phrase not in lowered, f"forbidden claim language: {phrase}"


def test_stage2r_helper_does_not_reuse_superseded_c4_identity() -> None:
    """The old C4 identity is one-run: never reused or renamed in Stage 2R."""
    tree, _ = _parse_module(_HELPER_PATH)
    defined = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "_run_c4_impl" not in defined, "old C4 identity must not be reused"
    assert "_run_c5_impl" not in defined, "old C5 identity must not be reused"
    for path in (_LOCK_RELEASE_PATH, _V1V2_PATH):
        _, source = _parse_module(path)
        assert "test_phase15_e2a_task88_c4_default_failure_contract_live" not in source


def test_stage2r_modules_isolated_from_global_acceptance_selector() -> None:
    """The Task #88 global acceptance selector identity is never referenced."""
    for path in _ALL_PATHS:
        _, source = _parse_module(path)
        for identifier in _TASK88_GLOBAL_ACCEPTANCE_IDENTIFIERS:
            assert identifier not in source, f"{path.name} references {identifier}"


def test_stage2r_c4_lock_release_cell_never_reconciles_second_desired() -> None:
    """The release reconcile passes the same first_desired object (no v1-v2 DML)."""
    tree, _ = _parse_module(_HELPER_PATH)
    fn = _function_by_name(tree, "_run_c4_lock_release_impl")
    calls = _reconcile_calls(fn)
    assert len(calls) == 3, "lock-release cell must reconcile exactly three times"
    # Find the release reconcile by its assignment target, not by walk order.
    release_assign = None
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "release_result":
                    release_assign = node
                    break
            if release_assign:
                break
    assert release_assign is not None, "release_result assignment must exist"
    assert isinstance(
        release_assign.value, ast.Call
    ), "release_result must be a reconcile call"
    release_call = release_assign.value
    assert len(release_call.args) == 2, "release reconcile takes connection + desired"
    argument = release_call.args[1]
    assert isinstance(argument, ast.Name), "release reconcile argument must be a name"
    assert (
        argument.id == "first_desired"
    ), "release reconcile must re-run first_desired, never second_desired"
    for call in calls:
        for call_arg in call.args:
            assert not (
                isinstance(call_arg, ast.Name) and call_arg.id == "second_desired"
            ), "no reconcile call in the lock-release cell may pass second_desired"
    assert (
        len(_reconcile_calls(_function_by_name(tree, "_run_v1v2_transition_impl"))) == 2
    )


def test_stage2r_helper_role_separation_means_connections_not_principals() -> None:
    doc = _docstring_normalized(_HELPER_PATH)
    assert "not distinct PostgreSQL principals" in doc
    assert "fresh attested connection" in doc
