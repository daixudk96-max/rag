"""Static AST source-proof for the Task #88 Stage 2 transition tranche (non-live).

Never imports, executes, or collects the live modules; reads source text and
inspects parsed ASTs only, so comments/docstrings cannot cause false
positives or satisfy a check by accident. Pinned: auth-first plain live
tests; no prohibited module families, pytest/skip/xfail, env access, direct
connections, or factory injection; connections only via
session.open_fresh_attested_connection(); the C2 projection is FIXED to
``no_op`` (no flexible changed/no_op acceptance, no opportunistic reads of
``last_synced_at``); C3 and C4 are distinct cells (C3 pins the exact global
primary-key preflight rejection message and unchanged committed state; C4
additionally pins the default ``E2aReconciler()`` failure contract: unwrapped
exact error, rollback/closed primary, no durable audit row, later fresh
reconcile unlocked); the C3/C4 exact message is rendered by the helper from a
single module-level template anchored to the production f-string, never
hand-reconstructed; C5 alone injects the audit factory, seeds only
parameterized SQL on its own fresh attested connection, observes the
durable append-only audit through fresh connections (including the exact
``scope_manifest`` JSONB body and its sha256), and never issues audit DML;
role separation in the Stage 2 tranche means independent fresh attested
connections/transactions, NOT distinct PostgreSQL principals; failures absorb
into redacted observations via the imported bounded ``_error_reason``;
failed cells raise RuntimeError carrying only observations.error_reason;
PARTIAL(C2)...PARTIAL(C5) disclaimers; no PASS language; phase15_ filename
uncollected; both modules under 800 lines; helper has no tests.
RED: fails until the Stage 2 transition modules carry the pinned structure.
"""

from __future__ import annotations

import ast
from pathlib import Path

_HELPER_PATH = Path(__file__).with_name("_phase15_e2a_task88_transition_cells.py")
_LIVE_PATH = Path(__file__).with_name("phase15_e2a_task88_live_transition_cells.py")

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

# Case-insensitive claim phrases that must never appear in the live module.
_FORBIDDEN_CLAIM_PHRASES = (
    "task #88 pass",
    "task #88 complete",
    "phase 15 pass",
    "phase 15 complete",
)

_DISCLAIMER_TOKENS = ("PARTIAL(C2)", "PARTIAL(C3)", "PARTIAL(C4)", "PARTIAL(C5)")
_OBSERVATION_TYPES = frozenset(
    {"C2Observations", "C3Observations", "C4Observations", "C5Observations"}
)
_CELL_IMPL_NAMES = ("_run_c2_impl", "_run_c3_impl", "_run_c4_impl", "_run_c5_impl")
_CELL_TOKENS = ("c2", "c3", "c4", "c5")

# Names the transition helper must import from the Stage 1 support module.
_FOUNDATION_IMPORT_ALIASES = frozenset(
    {
        "_close_quietly",
        "_error_reason",
        "_open_writer_connection",
        "_open_reconciler_primary_connection",
        "_open_observer_connection",
        "_build_foundation_desired_state",
        "_verify_durable_state",
        "_create_source_fixture",
        "_SOURCE_URI",
        "_SOURCE_RELATIVE_PATH",
        "_FIXTURE_TITLE",
    }
)
_FORBIDDEN_DIRECT_DB_ATTRIBUTES = frozenset(
    {"cursor", "execute", "fetchone", "fetchall", "commit", "rollback", "connect"}
)


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


def _execute_sql_constants(fn: ast.FunctionDef) -> list[str]:
    sqls: list[str] = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "execute":
            continue
        if not node.args:
            continue
        for child in ast.walk(node.args[0]):
            if isinstance(child, ast.Constant) and isinstance(child.value, str):
                sqls.append(child.value)
    return sqls


def _attribute_names(fn: ast.FunctionDef) -> set[str]:
    return {node.attr for node in ast.walk(fn) if isinstance(node, ast.Attribute)}


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


_DYNAMIC_IMPORT_MECHANISM_NAMES = ("importlib", "import_module", "__import__")


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


def _is_audit_factory_reference(expression: ast.expr) -> bool:
    return (
        isinstance(expression, ast.Attribute)
        and expression.attr == "open_fresh_attested_connection"
        and isinstance(expression.value, ast.Name)
        and expression.value.id == "session"
    )


def _reconcile_calls(fn: ast.FunctionDef) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "reconcile"
    ]


def test_transition_files_exist() -> None:
    assert _HELPER_PATH.is_file(), f"missing helper module: {_HELPER_PATH}"
    assert _LIVE_PATH.is_file(), f"missing live module: {_LIVE_PATH}"


def test_transition_files_under_800_lines() -> None:
    for path in (_HELPER_PATH, _LIVE_PATH):
        source = _parse_module(path)[1]
        assert source.count("\n") + 1 < 800, f"{path.name} exceeds 800 lines"


def test_live_module_filename_not_collected_by_discovery() -> None:
    name = _LIVE_PATH.name
    assert name.startswith("phase15_"), "live module must use the phase15_ prefix"
    assert not name.startswith("test_"), "live module must not match test_*.py"
    assert not name.endswith("_test.py"), "live module must not match *_test.py"
    assert name.endswith(".py"), "live module must be a python module"


def test_live_module_test_functions_auth_first() -> None:
    tree, _ = _parse_module(_LIVE_PATH)
    functions = _test_functions(tree)
    assert functions, "live module must define at least one test function"
    for fn in functions:
        assert _auth_first(fn), f"{fn.name}: _require_authorization() must be first"


def test_live_module_test_functions_have_no_decorators_or_fixtures() -> None:
    tree, _ = _parse_module(_LIVE_PATH)
    functions = _test_functions(tree)
    assert functions, "live module must define at least one test function"
    for fn in functions:
        assert not fn.decorator_list, f"{fn.name} must have no decorators"
        params = fn.args.posonlyargs + fn.args.args + fn.args.kwonlyargs
        assert not params, f"{fn.name} must take no parameters (no fixtures)"


def test_live_module_imports_require_authorization() -> None:
    tree, _ = _parse_module(_LIVE_PATH)
    found = any(
        isinstance(node, ast.ImportFrom)
        and any(alias.name == "_require_authorization" for alias in node.names)
        for node in ast.walk(tree)
    )
    assert found, "live module must import _require_authorization"


def test_live_module_imports_transition_helper() -> None:
    tree, _ = _parse_module(_LIVE_PATH)
    found = any(
        isinstance(node, ast.ImportFrom)
        and node.module is not None
        and "transition_cells" in node.module
        for node in ast.walk(tree)
    )
    assert found, "live module must import the transition helper"


def test_live_module_no_forbidden_imports() -> None:
    tree, _ = _parse_module(_LIVE_PATH)
    forbidden = [
        name for name in _imported_module_names(tree) if _module_is_forbidden(name)
    ]
    assert not forbidden, f"forbidden import in live module: {forbidden}"


def test_helper_module_no_forbidden_imports() -> None:
    tree, _ = _parse_module(_HELPER_PATH)
    forbidden = [
        name for name in _imported_module_names(tree) if _module_is_forbidden(name)
    ]
    assert not forbidden, f"forbidden import in helper: {forbidden}"


def test_helper_module_no_environment_or_process_env_access() -> None:
    _assert_no_environment_access(_HELPER_PATH)


def test_live_module_no_environment_or_process_env_access() -> None:
    _assert_no_environment_access(_LIVE_PATH)


def test_live_module_no_pytest_references() -> None:
    _assert_no_pytest_references(_LIVE_PATH)


def test_helper_module_no_pytest_references() -> None:
    _assert_no_pytest_references(_HELPER_PATH)


def test_live_module_disclaimer_text_present() -> None:
    doc = ast.get_docstring(_parse_module(_LIVE_PATH)[0])
    assert doc is not None, "live module docstring is required"
    for token in _DISCLAIMER_TOKENS:
        assert token in doc, f"missing disclaimer token {token} in module docstring"


def test_live_module_no_task_or_phase_pass_completion_language() -> None:
    _, source = _parse_module(_LIVE_PATH)
    lowered = source.lower()
    for phrase in _FORBIDDEN_CLAIM_PHRASES:
        assert phrase not in lowered, f"forbidden claim language: {phrase}"


def test_live_module_no_broad_except() -> None:
    tree, _ = _parse_module(_LIVE_PATH)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        assert node.type is not None, "live module must not use bare except"
        assert not (isinstance(node.type, ast.Name) and node.type.id == "Exception")


def test_live_module_no_direct_cursor_or_database_work() -> None:
    tree, _ = _parse_module(_LIVE_PATH)
    for name in _imported_module_names(tree):
        assert "psycopg" not in name, f"live module must not import psycopg: {name}"
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            assert not (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in _FORBIDDEN_DIRECT_DB_ATTRIBUTES
            ), "live module must not issue direct database work"
        if isinstance(node, ast.Name) and node.id == "E2aReconciler":
            raise AssertionError("live module must not construct the reconciler")


def test_live_cell_failures_raise_only_observation_error_reason() -> None:
    tree, _ = _parse_module(_LIVE_PATH)
    for fn in _test_functions(tree):
        raises = _runtime_error_raises(fn)
        assert len(raises) == 1, f"{fn.name} must raise exactly one RuntimeError"
        for raise_node in raises:
            assert _raise_message_is_only_observation_error_reason(raise_node)


def test_live_module_no_preinitialized_observation_blocks() -> None:
    tree, _ = _parse_module(_LIVE_PATH)
    for fn in _test_functions(tree):
        for node in ast.walk(fn):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    assert not (
                        isinstance(target, ast.Name)
                        and isinstance(node.value, ast.Call)
                        and isinstance(node.value.func, ast.Name)
                        and node.value.func.id in _OBSERVATION_TYPES
                    )


def test_live_module_four_distinct_cell_tests_present() -> None:
    tree, _ = _parse_module(_LIVE_PATH)
    names = [fn.name for fn in _test_functions(tree)]
    assert len(names) == 4, f"expected exactly four live cell tests, got {names}"
    assert len(set(names)) == 4, "live cell test names must be distinct"
    for token in _CELL_TOKENS:
        matching = [name for name in names if token in name]
        assert (
            len(matching) == 1
        ), f"expected exactly one live test for {token}: {names}"


def test_helper_defines_no_test_functions() -> None:
    tree, _ = _parse_module(_HELPER_PATH)
    assert not _test_functions(tree), "helper module must not define test functions"


def test_helper_imports_foundation_support_names() -> None:
    tree, _ = _parse_module(_HELPER_PATH)
    found = False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module is not None
            and node.module.endswith("_phase15_e2a_task88_live_cells")
        ):
            aliases = {alias.name for alias in node.names}
            assert (
                _FOUNDATION_IMPORT_ALIASES <= aliases
            ), "helper must import the foundation support names from Stage 1"
            found = True
    assert found, "helper must import from the Stage 1 support module"
    defined = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "_error_reason" not in defined, "helper must not redefine _error_reason"
    assert "_close_quietly" not in defined, "helper must not redefine _close_quietly"


def test_helper_observation_types_with_redacted_repr() -> None:
    tree, source = _parse_module(_HELPER_PATH)
    classes = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name in _OBSERVATION_TYPES
    }
    assert classes == set(_OBSERVATION_TYPES), f"missing observation types: {classes}"
    repr_functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "__repr__"
    ]
    assert repr_functions, "helper must define observation types with __repr__"
    segments = [ast.get_source_segment(source, fn) or "" for fn in repr_functions]
    assert any("<redacted>" in segment for segment in segments)


def test_helper_seed_role_helper_single_attested_call() -> None:
    tree, _ = _parse_module(_HELPER_PATH)
    fn = _function_by_name(tree, "_open_seed_connection")
    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)]
    assert len(calls) == 1, "_open_seed_connection must contain exactly one call"
    call = calls[0]
    assert isinstance(call.func, ast.Attribute), "seed helper must call a method"
    assert call.func.attr == "open_fresh_attested_connection"
    assert isinstance(call.func.value, ast.Name) and call.func.value.id == "session"
    assert not call.args and not call.keywords, "seed helper must pass no arguments"


def test_helper_all_attested_connections_via_session() -> None:
    tree, _ = _parse_module(_HELPER_PATH)
    references = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr == "open_fresh_attested_connection"
    ]
    assert references, "helper must use open_fresh_attested_connection"
    for reference in references:
        assert isinstance(reference.value, ast.Name), "attested calls need a receiver"
        assert (
            reference.value.id == "session"
        ), "attested calls must be session.open_fresh_attested_connection"


def test_helper_no_direct_database_or_factory_bypass() -> None:
    tree, _ = _parse_module(_HELPER_PATH)
    for name in _imported_module_names(tree):
        assert "psycopg" not in name, f"helper must not import psycopg: {name}"
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr == "connect":
            raise AssertionError("helper must not call .connect(...) directly")


def test_helper_reconciler_construction_contract() -> None:
    tree, _ = _parse_module(_HELPER_PATH)
    for name in _CELL_IMPL_NAMES:
        fn = _function_by_name(tree, name)
        calls = _e2a_reconciler_calls(fn)
        assert calls, f"{name} must construct E2aReconciler"
        for call in calls:
            assert not call.args, f"{name}: E2aReconciler takes no positional args"
    # C5 alone injects the audit factory: the reconciler never raises once a
    # factory is present (it returns rolled_back_failure), so C3 and C4 must
    # use default construction to observe the exact preflight error at all.
    c5_calls = _e2a_reconciler_calls(_function_by_name(tree, "_run_c5_impl"))
    audited = [
        call
        for call in c5_calls
        if call.keywords
        and {kw.arg for kw in call.keywords} == {"failure_audit_connection_factory"}
        and len(call.keywords) == 1
        and _is_audit_factory_reference(call.keywords[0].value)
    ]
    assert (
        audited
    ), "C5 must inject session.open_fresh_attested_connection as the audit factory"
    for call in c5_calls:
        assert all(
            kw.arg == "failure_audit_connection_factory" for kw in call.keywords
        ), "C5: unexpected reconciler keywords"
    for name in ("_run_c2_impl", "_run_c3_impl", "_run_c4_impl"):
        for call in _e2a_reconciler_calls(_function_by_name(tree, name)):
            assert (
                not call.args and not call.keywords
            ), f"{name} must use default E2aReconciler()"


def test_helper_c2_fixed_projection_pinned() -> None:
    tree, source = _parse_module(_HELPER_PATH)
    assert '== "no_op"' in source, "C2 must pin the fixed no_op projection"
    assert '"changed", "no_op"' not in source, "C2 must not accept either outcome"
    assert '"no_op", "changed"' not in source, "C2 must not accept either outcome"
    assert "last_synced_at" in source, "C2 must observe timestamp churn"
    fn = _function_by_name(tree, "_run_c2_impl")
    assert len(_reconcile_calls(fn)) == 2, "C2 must reconcile twice"
    assert fn.returns, "C2 impl must return an observation"


def test_helper_c3_c4_distinct_cells() -> None:
    tree, source = _parse_module(_HELPER_PATH)
    for name in ("_run_c3_impl", "_run_c4_impl"):
        _function_by_name(tree, name)
    c4_fn = _function_by_name(tree, "_run_c4_impl")
    audit_sqls = [
        sql
        for sql in _execute_sql_constants(c4_fn)
        if "okf_rebuild_failure_audit" in sql
    ]
    assert audit_sqls, "C4 must observe the audit table"
    assert ".args ==" in source, "C4 must compare the exact error message"
    assert "exact_error_match" in source, "C4 observation must carry the match flag"


def test_helper_c5_seed_and_audit_shapes() -> None:
    _, source = _parse_module(_HELPER_PATH)
    assert "INSERT INTO entities" in source, "C5 must seed the entities table"
    assert "%s" in source, "C5 seed must be parameterized SQL"
    assert "pg_trigger" in source, "C5 must observe the append-only trigger catalog"
    assert "okf_rebuild_failure_audit" in source, "C5 must observe the audit table"
    fn = _function_by_name(_parse_module(_HELPER_PATH)[0], "_run_c5_impl")
    closed = _finally_close_arguments(fn)
    assert "seed_conn" in closed, "C5 must close the seed connection in a finally path"


def test_helper_cell_failures_bounded_diagnostics() -> None:
    tree, source = _parse_module(_HELPER_PATH)
    assert (
        source.count("error_reason=_error_reason(") >= 4
    ), "each cell must absorb failures into a bounded _error_reason"
    for name in _CELL_IMPL_NAMES:
        fn = _function_by_name(tree, name)
        handlers = [n for n in ast.walk(fn) if isinstance(n, ast.ExceptHandler)]
        assert any(
            isinstance(h.type, ast.Name)
            and h.type.id == "Exception"
            and h.name is not None
            for h in handlers
        ), f"{name} failure path must bind the original exception"


def test_helper_impls_close_resources_in_finally() -> None:
    tree, _ = _parse_module(_HELPER_PATH)
    for name in _CELL_IMPL_NAMES:
        fn = _function_by_name(tree, name)
        tries = [n for n in ast.walk(fn) if isinstance(n, ast.Try)]
        assert any(
            any(
                isinstance(stmt, ast.Expr)
                and isinstance(stmt.value, ast.Call)
                and isinstance(stmt.value.func, ast.Name)
                and stmt.value.func.id == "_close_quietly"
                for stmt in try_node.finalbody
            )
            for try_node in tries
        ), f"{name} must close resources in a finally path"


def test_helper_connection_role_helpers_present() -> None:
    tree, _ = _parse_module(_HELPER_PATH)
    def_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "_open_seed_connection" in def_names
    import_names = set(_imported_module_names(tree))
    for key in "writer reconciler_primary observer".split():
        assert any(
            key in name and name.startswith("_open_") for name in def_names
        ) or any(
            "live_cells" in name for name in import_names
        ), f"no {key} role helper available"


def test_helper_collision_message_single_source_wiring() -> None:
    tree, source = _parse_module(_HELPER_PATH)
    fn = _function_by_name(tree, "_expected_span_collision_message")
    fn_source = ast.get_source_segment(source, fn) or ""
    assert "incompatible scope version" not in fn_source
    assert ".format(" in fn_source
    assert "_GLOBAL_PREFLIGHT_COLLISION_TEMPLATE" in fn_source


def test_helper_global_collision_template_constant_module_level() -> None:
    tree, _ = _parse_module(_HELPER_PATH)
    assignments = [
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name)
            and target.id == "_GLOBAL_PREFLIGHT_COLLISION_TEMPLATE"
            for target in node.targets
        )
    ]
    assert len(assignments) == 1, "helper must define the template constant once"
    value = assignments[0].value
    assert isinstance(value, ast.Constant) and isinstance(value.value, str)
    template = value.value
    assert template.startswith("global canonical_spans span_id=")
    assert "is owned by incompatible scope version " in template
    assert "{span_id}" in template
    assert "{version_id}" in template


def test_helper_c5_scope_manifest_observation_pinned() -> None:
    tree, source = _parse_module(_HELPER_PATH)
    fn = _function_by_name(tree, "_run_c5_impl")
    sqls = _execute_sql_constants(fn)
    scope_queries = [
        sql
        for sql in sqls
        if "okf_rebuild_failure_audit" in sql and ", scope_manifest, " in sql
    ]
    assert scope_queries, "C5 observer query must read scope_manifest"
    assert any(
        "scope_manifest_sha256" in sql for sql in scope_queries
    ), "C5 observer query must read scope_manifest_sha256"
    fn_source = ast.get_source_segment(source, fn) or ""
    assert '"manifest_sha256"' in fn_source, "C5 must compute the expected scope body"
    assert '"parent_count"' in fn_source
    assert '"version_ids"' in fn_source


def test_helper_c5_observation_carries_scope_manifest_match_flag() -> None:
    _, source = _parse_module(_HELPER_PATH)
    assert "audit_scope_manifest_matches" in source


def _docstring_normalized(path: Path) -> str:
    """Module docstring with prose wrapping normalized for phrase pins."""
    doc = ast.get_docstring(_parse_module(path)[0])
    assert doc is not None, f"{path.name} docstring is required"
    return " ".join(doc.split())


def test_live_module_role_separation_means_connections_not_principals() -> None:
    doc = _docstring_normalized(_LIVE_PATH)
    assert "not distinct PostgreSQL principals" in doc
    assert "fresh attested connection" in doc


def test_helper_module_role_separation_means_connections_not_principals() -> None:
    doc = _docstring_normalized(_HELPER_PATH)
    assert "not distinct PostgreSQL principals" in doc
    assert "fresh attested connection" in doc


def test_live_modules_use_no_dynamic_import_mechanisms() -> None:
    for path in (_LIVE_PATH, _HELPER_PATH):
        violations = _dynamic_import_violations(_parse_module(path)[0])
        assert not violations, f"{path.name} must not use dynamic imports: {violations}"


def test_module_forbidden_import_detection_rejects_historic_families() -> None:
    assert _module_is_forbidden("llamaindex_runtime.okf.e2a_disposable_execution")
    assert _module_is_forbidden(
        "verification.phase15-okf-ingestion-pipeline.run_e2a_verification"
    )
    assert _module_is_forbidden("from . import disposable_postgres".split()[-1])
    assert _module_is_forbidden("real_e2a_reconciler")
    assert not _module_is_forbidden("llamaindex_runtime.okf.e2a_reconciler")
    assert not _module_is_forbidden("_phase15_e2a_task88_live_cells")
