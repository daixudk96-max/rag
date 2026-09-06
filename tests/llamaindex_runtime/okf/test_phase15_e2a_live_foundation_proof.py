"""Static AST source-proof for the Task #88 foundation live tranche (non-live).

Never imports, executes, or collects the live modules; reads source text
and inspects parsed ASTs only, so comments/docstrings cannot cause false
positives or satisfy a check by accident. Pinned: auth-first plain live
tests; no prohibited module families, pytest/skip/xfail, env access,
direct connections, or factory injection; connections only via
session.open_fresh_attested_connection(); C1/C11 workers close
primary_conn in a finally path; failures absorb into redacted
observations via _error_reason (body proven class-name-only, bounded 64
chars); a failed cell raises RuntimeError carrying only
observations.error_reason; C11 boundary incl. observer transaction reset
between count reads; phase15_ filename uncollected; disclaimers present;
no PASS language; both modules under 800 lines; helper has no tests.
RED: fails until the live modules carry the pinned structure.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from pathlib import Path

_HELPER_PATH = Path(__file__).with_name("_phase15_e2a_task88_live_cells.py")
_LIVE_PATH = Path(__file__).with_name("phase15_e2a_task88_live_foundation.py")

_PROHIBITED_EXACT_MODULE_NAMES = frozenset(
    {
        "llamaindex_runtime.okf.e2a_disposable_execution",
        "verification.phase15-okf-ingestion-pipeline.run_e2a_verification",
    }
)
_PROHIBITED_MODULE_FRAGMENTS = frozenset(
    "real_e2a_reconciler disposable_acceptance disposable_postgres _real_e2a_".split()
)
# Tail segments of the exact names, so relative imports are also caught.
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

_CONNECTION_ROLE_HELPERS = tuple(
    "_open_writer_connection _open_reconciler_primary_connection "
    "_open_observer_connection".split()
)
_OBSERVATION_TYPES = frozenset({"C13Observations", "C1Observations", "C11Observations"})
_C11_MARKER_CALL_NAMES = frozenset(
    {"_denylist_present_counts", "_catalog_absent_flags", "E2aReconciler"}
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


def _called_names(fn: ast.FunctionDef) -> set[str]:
    return {
        node.func.id
        for node in ast.walk(fn)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


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


def _simple_name_assignments(fn: ast.FunctionDef) -> dict[str, ast.expr]:
    assignments: dict[str, ast.expr] = {}
    for statement in fn.body:
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            continue
        target = statement.targets[0]
        if isinstance(target, ast.Name):
            if target.id in assignments:
                return {}
            assignments[target.id] = statement.value
    return assignments


def _is_class_name_of_failure(expression: ast.expr) -> bool:
    return (
        isinstance(expression, ast.Attribute)
        and expression.attr == "__name__"
        and isinstance(expression.value, ast.Call)
        and isinstance(expression.value.func, ast.Name)
        and expression.value.func.id == "type"
        and len(expression.value.args) == 1
        and isinstance(expression.value.args[0], ast.Name)
        and expression.value.args[0].id == "failure"
    )


def _is_bounded_class_name_slice(
    expression: ast.expr, local_type_names: Mapping[str, ast.expr]
) -> bool:
    if not (
        isinstance(expression, ast.Subscript)
        and isinstance(expression.slice, ast.Slice)
        and expression.slice.lower is None
        and expression.slice.step is None
        and isinstance(expression.slice.upper, ast.Constant)
        and expression.slice.upper.value == 64
    ):
        return False
    sliced = expression.value
    if isinstance(sliced, ast.Name):
        resolved = local_type_names.get(sliced.id)
        if resolved is None:
            return False
        sliced = resolved
    return _is_class_name_of_failure(sliced)


def _leaks_failure(node: ast.AST) -> bool:
    if isinstance(node, ast.Call) and not node.keywords:
        if isinstance(node.func, ast.Name) and node.func.id in ("str", "repr"):
            return True
        passes_failure = any(
            isinstance(argument, ast.Name) and argument.id == "failure"
            for argument in node.args
        )
        if passes_failure and not (
            isinstance(node.func, ast.Name)
            and node.func.id == "type"
            and len(node.args) == 1
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == "failure"
        ):
            return True
    if (
        isinstance(node, (ast.Attribute, ast.Subscript, ast.FormattedValue))
        and isinstance(node.value, ast.Name)
        and node.value.id == "failure"
    ):
        return True
    return False


def _error_reason_body_is_bounded(fn: ast.FunctionDef) -> bool:
    parameters = {argument.arg for argument in fn.args.args}
    if "failure" not in parameters or "prefix" not in parameters:
        return False
    if any(_leaks_failure(node) for node in ast.walk(fn)):
        return False
    returns = [node for node in ast.walk(fn) if isinstance(node, ast.Return)]
    if len(returns) != 1 or not isinstance(returns[0].value, ast.JoinedStr):
        return False
    returned = returns[0].value
    local_type_names = _simple_name_assignments(fn)
    class_slice_found = False
    separator_found = False
    for value in returned.values:
        if isinstance(value, ast.Constant):
            if not isinstance(value.value, str):
                return False
            if ":" in value.value:
                separator_found = True
            continue
        if not isinstance(value, ast.FormattedValue):
            return False
        dynamic = value.value
        if isinstance(dynamic, ast.Name) and dynamic.id == "prefix":
            continue
        if _is_bounded_class_name_slice(dynamic, local_type_names):
            class_slice_found = True
            continue
        return False
    return class_slice_found and separator_found


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


def _c11_impl_markers(fn: ast.FunctionDef) -> list[str]:
    markers: list[str] = []
    pending = list(fn.body)
    while pending:
        statement = pending.pop(0)
        if isinstance(statement, ast.Try):
            pending = statement.body + pending
            continue
        for node in ast.walk(statement):
            if not isinstance(node, ast.Call):
                continue
            if (
                isinstance(node.func, ast.Name)
                and node.func.id in _C11_MARKER_CALL_NAMES
            ):
                markers.append(node.func.id)
            elif (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "rollback"
                and isinstance(node.func.value, ast.Name)
            ):
                markers.append(f"rollback:{node.func.value.id}")
    return markers


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


# Dynamic import mechanisms that could load prohibited historic execution
# code at runtime; rejected structurally on names, imports, and calls.
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


# Sibling-relative import forms of the prohibited families; the
# hyphenated verification-module name is runtime-guarded elsewhere.
_SIBLING_RELATIVE_PROHIBITED_IMPORT_SOURCES = (
    "from . import e2a_disposable_execution\n",
    "from . import run_e2a_verification\n",
    "from . import real_e2a_reconciler\n",
    "from . import disposable_postgres\n",
    "from . import _real_e2a_lifecycle\n",
    "from .e2a_disposable_execution import run_cell\n",
    "from ..e2a_disposable_execution import run_cell\n",
)

# Plausible future _error_reason rewrites that leak exception text (parsed only).
_LEAKY_ERROR_REASON_SOURCES = (
    "def _error_reason(prefix, failure):\n    return f'{prefix}:{failure}'\n",
    "def _error_reason(prefix, failure):\n    return f'{prefix}:{failure.args[0]}'\n",
    "def _error_reason(prefix, failure):\n    return f'{prefix}:{failure.message}'\n",
    "def _error_reason(prefix, failure):\n"
    "    return f'{prefix}:{failure.__class__.__name__}'\n",
    "def _error_reason(prefix, failure):\n    return prefix + ':' + str(failure)\n",
    "def _error_reason(prefix, failure):\n    return prefix + ':' + repr(failure)\n",
    "def _error_reason(prefix, failure):\n"
    "    return prefix + ':' + format_exception(failure)\n",
    "def _error_reason(prefix, failure):\n"
    "    error_type = type(failure).__name__\n"
    "    return f'{prefix}:{error_type}'\n",
)

# Parsed-only negative fixtures: dynamic import mechanisms that could
# load prohibited historic execution code at runtime.
_DYNAMIC_IMPORT_MECHANISM_SOURCES = (
    "import importlib\n",
    "import importlib as il\n",
    "import importlib.util\n",
    "from importlib import import_module\n",
    "from importlib import import_module as im\n",
    "from importlib.util import spec_from_file_location\n",
    "from . import import_module\n",
    "mod = __import__('some.module')\n",
    "importlib.import_module('some.module')\n",
    "import importlib as il\nil.import_module('some.module')\n",
    "from importlib import import_module\nimport_module('some.module')\n",
)


def test_live_foundation_files_exist() -> None:
    assert _HELPER_PATH.is_file(), f"missing helper module: {_HELPER_PATH}"
    assert _LIVE_PATH.is_file(), f"missing live module: {_LIVE_PATH}"


def test_live_foundation_files_under_800_lines() -> None:
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


def test_live_module_imports_helper() -> None:
    tree, _ = _parse_module(_LIVE_PATH)
    found = any(
        isinstance(node, ast.ImportFrom)
        and node.module is not None
        and "live_cells" in node.module
        for node in ast.walk(tree)
    )
    assert found, "live module must import the helper module"


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


def test_imported_module_names_rejects_sibling_relative_prohibited_imports() -> None:
    for source in _SIBLING_RELATIVE_PROHIBITED_IMPORT_SOURCES:
        tree = ast.parse(source)
        names = _imported_module_names(tree)
        assert names, f"no import names collected from: {source!r}"
        assert any(_module_is_forbidden(name) for name in names)


def test_imported_module_names_detects_regular_and_relative_imports() -> None:
    tree = ast.parse(
        "import hashlib\n"
        "from . import _phase15_e2a_harness_types\n"
        "from ._phase15_e2a_task88_live_cells import _run_c11_impl\n"
        "from llamaindex_runtime.okf.e2a_contracts import E2aParent\n"
    )
    names = _imported_module_names(tree)
    assert "hashlib" in names
    assert "_phase15_e2a_harness_types" in names
    assert "_phase15_e2a_task88_live_cells" in names
    assert "llamaindex_runtime.okf.e2a_contracts" in names
    assert "E2aParent" in names
    assert not any(_module_is_forbidden(name) for name in names)


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
    for token in ("PARTIAL(C13)", "PARTIAL(C1)", "PARTIAL(C11)"):
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


def test_live_module_c11_functions_ast_validated() -> None:
    tree, _ = _parse_module(_LIVE_PATH)
    c11_functions = [fn for fn in _test_functions(tree) if "c11" in fn.name]
    assert c11_functions, "live module must define a C11 test function"
    for fn in c11_functions:
        attributes = _attribute_names(fn)
        names = {node.id for node in ast.walk(fn) if isinstance(node, ast.Name)}
        assert "absent_catalog_flags" in attributes, f"{fn.name}: missing flags"
        assert "_run_c11_impl" in names, f"{fn.name} must delegate to the C11 worker"
        assert not _execute_sql_constants(fn), f"{fn.name}: no SQL of its own"


def test_live_module_no_direct_cursor_or_database_work() -> None:
    tree, _ = _parse_module(_LIVE_PATH)
    for name in _imported_module_names(tree):
        assert "psycopg" not in name, f"live module must not import psycopg: {name}"
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            assert not (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in _FORBIDDEN_DIRECT_DB_ATTRIBUTES
            )
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


def test_helper_connection_role_helpers_use_attested_session() -> None:
    tree, _ = _parse_module(_HELPER_PATH)
    for name in _CONNECTION_ROLE_HELPERS:
        fn = _function_by_name(tree, name)
        calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)]
        assert len(calls) == 1, f"{name} must contain exactly one call"
        call = calls[0]
        assert isinstance(call.func, ast.Attribute), f"{name} must call a method"
        assert call.func.attr == "open_fresh_attested_connection"
        assert isinstance(call.func.value, ast.Name) and call.func.value.id == "session"
        assert not call.args and not call.keywords, f"{name} must pass no arguments"


def test_helper_all_connections_attested_via_session() -> None:
    tree, _ = _parse_module(_HELPER_PATH)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "open_fresh_attested_connection"
    ]
    assert calls, "helper must call open_fresh_attested_connection"
    for call in calls:
        assert isinstance(call.func, ast.Attribute)
        assert isinstance(call.func.value, ast.Name) and call.func.value.id == "session"


def test_helper_no_direct_database_or_factory_bypass() -> None:
    tree, _ = _parse_module(_HELPER_PATH)
    for name in _imported_module_names(tree):
        assert "psycopg" not in name, f"helper must not import psycopg: {name}"
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr == "connect":
            raise AssertionError("helper must not call .connect(...) directly")
        if isinstance(node.func, ast.Name) and node.func.id == "E2aReconciler":
            assert not node.args and not node.keywords, (
                "E2aReconciler must use defaults"
            )


def test_c1_and_c11_workers_close_primary_connection_in_finally() -> None:
    tree, _ = _parse_module(_HELPER_PATH)
    for name in ("_run_c1_reconcile_impl", "_run_c11_impl"):
        fn = _function_by_name(tree, name)
        closed = _finally_close_arguments(fn)
        assert "primary_conn" in closed, (
            f"{name} must close primary_conn in a finally path"
        )


def test_cell_failures_report_bounded_type_only_diagnostics() -> None:
    tree, _ = _parse_module(_HELPER_PATH)
    for name in ("_run_c13_impl", "_run_c1_reconcile_impl", "_run_c11_impl"):
        fn = _function_by_name(tree, name)
        handlers = [n for n in ast.walk(fn) if isinstance(n, ast.ExceptHandler)]
        assert handlers, f"{name} must absorb failures into redacted observations"
        assert any(
            isinstance(h.type, ast.Name)
            and h.type.id == "Exception"
            and h.name is not None
            for h in handlers
        ), f"{name} failure path must bind the original exception"
        for handler in handlers:
            reasons = [
                keyword.value
                for stmt in handler.body
                if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Call)
                for keyword in stmt.value.keywords
                if keyword.arg == "error_reason"
            ]
            if not reasons:
                # Only other shape: the quiet-close swallow inside _close_quietly.
                assert handler.name is None and any(
                    isinstance(stmt, ast.Pass) for stmt in handler.body
                ), f"{name} failure path must set error_reason"
                continue
            for value in reasons:
                assert (
                    isinstance(value, ast.Call)
                    and isinstance(value.func, ast.Name)
                    and value.func.id == "_error_reason"
                ), f"{name} diagnostic must be a bounded type-only _error_reason"


def test_helper_error_reason_body_is_bounded_type_only() -> None:
    tree, _ = _parse_module(_HELPER_PATH)
    fn = _function_by_name(tree, "_error_reason")
    assert _error_reason_body_is_bounded(fn), "bounded class/type-only diagnostic"


def test_helper_error_reason_verifier_rejects_leaky_bodies() -> None:
    for source in _LEAKY_ERROR_REASON_SOURCES:
        fn = _function_by_name(ast.parse(source), "_error_reason")
        assert not _error_reason_body_is_bounded(fn), f"leaky body rejected: {source!r}"


def test_helper_c11_observations_ast_based() -> None:
    tree, _ = _parse_module(_HELPER_PATH)
    present_fn = _function_by_name(tree, "_denylist_present_counts")
    absent_fn = _function_by_name(tree, "_catalog_absent_flags")
    impl_fn = _function_by_name(tree, "_run_c11_impl")

    present_sqls = _execute_sql_constants(present_fn)
    assert len(present_sqls) == 1, "present-count worker must issue one COUNT query"
    present_names = {n.id for n in ast.walk(present_fn) if isinstance(n, ast.Name)}
    assert "_C11_PRESENT_TABLES" in present_names, "must iterate catalog-present names"
    assert present_sqls[0].upper().startswith("SELECT COUNT("), "must be COUNT"

    absent_sqls = _execute_sql_constants(absent_fn)
    assert absent_sqls, "absent worker must issue a catalog query"
    assert all("information_schema" in s for s in absent_sqls), "info_schema-only"
    absent_names = {n.id for n in ast.walk(absent_fn) if isinstance(n, ast.Name)}
    assert "_C11_ABSENT_TABLES" in absent_names, "must iterate absent table names"

    impl_calls = _called_names(impl_fn)
    assert "_denylist_present_counts" in impl_calls
    assert "_catalog_absent_flags" in impl_calls
    assert "E2aReconciler" in impl_calls
    assert "reconcile" in _attribute_names(impl_fn)
    assert "denylist_dml_counts" in _attribute_names(impl_fn)

    for node in ast.walk(tree):
        if isinstance(node, ast.DictComp) and isinstance(node.value, ast.Constant):
            assert node.value.value != 0, "denylist maps must never be literal zeros"

    all_count_sqls = absent_sqls + _execute_sql_constants(
        _function_by_name(tree, "_verify_durable_state")
    )
    assert all("join" not in s.lower() for s in all_count_sqls), "queries join-free"


def test_helper_c11_impl_resets_observer_transaction_between_reads() -> None:
    tree, _ = _parse_module(_HELPER_PATH)
    impl_fn = _function_by_name(tree, "_run_c11_impl")
    markers = _c11_impl_markers(impl_fn)
    counts = [i for i, m in enumerate(markers) if m == "_denylist_present_counts"]
    rollbacks = [i for i, m in enumerate(markers) if m == "rollback:observer_conn"]
    assert len(counts) == 2, "C11 must observe counts before and after reconcile"
    assert len(rollbacks) == 1, "C11 must reset the observer transaction once"
    assert counts[0] < rollbacks[0] < counts[1], "reset must sit between the reads"


def test_helper_observation_types_with_redacted_repr() -> None:
    tree, source = _parse_module(_HELPER_PATH)
    repr_functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "__repr__"
    ]
    assert repr_functions, "helper must define observation types with __repr__"
    segments = [ast.get_source_segment(source, fn) or "" for fn in repr_functions]
    assert any("<redacted>" in segment for segment in segments)


def test_helper_connection_role_helpers_present() -> None:
    tree, _ = _parse_module(_HELPER_PATH)
    def_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for key in "writer reconciler_primary observer c13 c1_reconcile c11".split():
        assert any(key in name for name in def_names), f"no {key} helper defined"


def test_live_module_three_cell_tests_present() -> None:
    tree, _ = _parse_module(_LIVE_PATH)
    names = [fn.name for fn in _test_functions(tree)]
    assert any("c13" in name for name in names), "missing C13 live test"
    assert any("c1_reconcile" in name for name in names), "missing C1 live test"
    assert any("c11" in name for name in names), "missing C11 live test"


def test_helper_defines_no_test_functions() -> None:
    tree, _ = _parse_module(_HELPER_PATH)
    assert not _test_functions(tree), "helper module must not define test functions"


def test_live_modules_use_no_dynamic_import_mechanisms() -> None:
    for path in (_LIVE_PATH, _HELPER_PATH):
        violations = _dynamic_import_violations(_parse_module(path)[0])
        assert not violations, f"{path.name} must not use dynamic imports: {violations}"


def test_dynamic_import_guard_rejects_fixture_shapes() -> None:
    for source in _DYNAMIC_IMPORT_MECHANISM_SOURCES:
        violations = _dynamic_import_violations(ast.parse(source))
        assert violations, f"not rejected: {source!r}"
