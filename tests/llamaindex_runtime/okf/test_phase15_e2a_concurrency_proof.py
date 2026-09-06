"""Source proofs for the Task #88 Stage 4 C6 advisory-lock concurrency slice.

This collected (non-live) module pins, by structural ``ast`` shape checks
and one fresh-process import proof, the safety contracts of the C6 slice:
filename non-collection identity; authorization-first selected test body;
exactly two default reconcilers (bare ABC plus hooked AB via
``_hold_after_locks``); exactly one advisory-lock catalog query filtered to
``locktype = 'advisory'`` and no manual advisory-lock statements; no
forbidden APIs, patterns, credentials, or environment access; redacted
observation reprs; bounded finally cleanup (release + join both workers
with timeouts); PARTIAL(C6) docstring boundaries; and clean fresh-process
imports with the fails-closed authorization gate. Fixtures are parsed
only, never executed. No database, no Docker, no authorized live selector
invocation.
"""

from __future__ import annotations

import ast
import fnmatch
import glob
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ._phase15_e2a_task88_cells import module_name_is_blocked

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
OKF_DIR = Path(__file__).parent

HELPER_FILENAME = "_phase15_e2a_task88_concurrency_cells.py"
SELECTOR_FILENAME = "phase15_e2a_task88_live_concurrency.py"
PROOF_FILENAME = "test_phase15_e2a_concurrency_proof.py"
SELECTED_TEST_NAME = "test_phase15_e2a_task88_c6_advisory_lock_concurrency_live"
OBSERVATIONS_CLASS_NAME = "C6AdvisoryLockObservations"
AUTHORIZATION_FIRST_MESSAGE = "E2A disposable test requires separate authorization"

_SENSITIVE_ENV_VARS = frozenset(
    {
        "DATABASE_URL",
        "FORMAL_RUNTIME_DATABASE_URL",
        "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE",
        "OKF_REBUILD_EXPECTED_DATABASE",
        "OKF_FAILURE_AUDIT_ACCEPTANCE",
        "OKF_REBUILD_DOCKER_ACCEPTANCE",
        "PGSERVICE",
        "PGSERVICEFILE",
        "PGSYSCONFDIR",
        "PGHOST",
        "PGPORT",
        "PGUSER",
        "PGPASSWORD",
        "PGDATABASE",
        "OKF_E2A_DISPOSABLE_TEST_AUTHORIZED",
    }
)

_SANITIZED_ALLOWLIST = (
    "PATH",
    "HOME",
    "SystemRoot",
    "PATHEXT",
    "WINDIR",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    "COMSPEC",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
)


def _single_function_by_name(tree: ast.Module, function_name: str) -> ast.FunctionDef:
    """Return the single top-level function with the given name."""
    functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    ]
    assert (
        len(functions) == 1
    ), f"the {function_name!r} function must exist exactly once"
    return functions[0]


def _single_class_by_name(tree: ast.Module, class_name: str) -> ast.ClassDef:
    """Return the single top-level class with the given name."""
    classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    ]
    assert len(classes) == 1, f"the {class_name!r} class must exist exactly once"
    return classes[0]


def _is_direct_getenv_call(call: ast.Call) -> bool:
    """True only for the direct zero-keyword ``os.getenv(<one arg>)`` form."""
    if call.keywords:
        return False
    if not isinstance(call.func, ast.Attribute):
        return False
    if call.func.attr != "getenv":
        return False
    if not (isinstance(call.func.value, ast.Name) and call.func.value.id == "os"):
        return False
    return len(call.args) == 1


def _verify_sanitized_env_structure(function: ast.FunctionDef) -> None:
    """Structural proof: the builder reads only literal allowlist keys.

    Every attribute access must be exactly the direct ``os.getenv`` form
    (aliased module reads are rejected) and every call must be the direct
    zero-keyword ``os.getenv("<literal key>")`` form; the collected keys
    must equal the allowlist exactly and stay disjoint from sensitive
    variable names.
    """
    getenv_keys: list[str] = []
    for node in ast.walk(function):
        if isinstance(node, ast.Attribute):
            assert (
                isinstance(node.value, ast.Name)
                and node.value.id == "os"
                and node.attr == "getenv"
            ), "every attribute access must be the direct os.getenv form"
        if not isinstance(node, ast.Call):
            continue
        assert _is_direct_getenv_call(node), (
            "every call must be the direct zero-keyword os.getenv(<key>) form"
        )
        argument = node.args[0]
        assert isinstance(argument, ast.Constant) and isinstance(
            argument.value, str
        ), "os.getenv key must be a string literal"
        getenv_keys.append(argument.value)
    assert getenv_keys, "_sanitized_env must read allowlisted keys via os.getenv"
    assert set(getenv_keys) == set(
        _SANITIZED_ALLOWLIST
    ), "os.getenv keys must match the explicit allowlist exactly"
    assert not (
        set(_SANITIZED_ALLOWLIST) & _SENSITIVE_ENV_VARS
    ), "the allowlist must never contain sensitive variable names"


def _sanitized_env() -> dict[str, str]:
    """Child env dict: explicit per-key reads of non-sensitive allowlist keys."""
    env: dict[str, str] = {}
    for key, value in (
        ("PATH", os.getenv("PATH")),
        ("HOME", os.getenv("HOME")),
        ("SystemRoot", os.getenv("SystemRoot")),
        ("PATHEXT", os.getenv("PATHEXT")),
        ("WINDIR", os.getenv("WINDIR")),
        ("TEMP", os.getenv("TEMP")),
        ("TMP", os.getenv("TMP")),
        ("USERPROFILE", os.getenv("USERPROFILE")),
        ("HOMEDRIVE", os.getenv("HOMEDRIVE")),
        ("HOMEPATH", os.getenv("HOMEPATH")),
        ("COMSPEC", os.getenv("COMSPEC")),
        ("NUMBER_OF_PROCESSORS", os.getenv("NUMBER_OF_PROCESSORS")),
        ("PROCESSOR_ARCHITECTURE", os.getenv("PROCESSOR_ARCHITECTURE")),
    ):
        if value is not None:
            env[key] = value
    return env


def _helper_source() -> str:
    """Raw helper module source (the file must exist)."""
    return (OKF_DIR / HELPER_FILENAME).read_text(encoding="utf-8")


def _selector_source() -> str:
    """Raw selector module source (the file must exist)."""
    return (OKF_DIR / SELECTOR_FILENAME).read_text(encoding="utf-8")


# --- Filename / collection identity


def test_c6_filenames_not_matched_by_default_pytest_patterns() -> None:
    """The helper and the selector must escape default pytest collection."""
    for filename in (SELECTOR_FILENAME, HELPER_FILENAME):
        assert not fnmatch.fnmatch(filename, "test_*.py")
        assert not fnmatch.fnmatch(filename, "*_test.py")
    assert fnmatch.fnmatch(HELPER_FILENAME, "_*.py")
    assert fnmatch.fnmatch(PROOF_FILENAME, "test_*.py")


def test_c6_module_names_not_blocked_by_family_guard() -> None:
    """The C6 slice must never collide with a prohibited naming family.

    A future rename of the C6 helper or selector into a mandated
    prohibited family (``real_e2a_reconciler``, ``disposable_acceptance``,
    ``disposable_postgres``, ``_real_e2a_``) must fail here.
    """
    for module_name in (
        "tests.llamaindex_runtime.okf._phase15_e2a_task88_concurrency_cells",
        "tests.llamaindex_runtime.okf.phase15_e2a_task88_live_concurrency",
    ):
        assert not module_name_is_blocked(module_name), (
            f"C6 module name collides with a prohibited family: {module_name}"
        )


def test_pytest_collect_only_excludes_c6_modules() -> None:
    """A real pytest collection over the Phase 15 glob never lists C6 modules."""
    target_paths = sorted(glob.glob(str(OKF_DIR / "test_phase15_e2a_*.py")))
    collected_names = {Path(path).name for path in target_paths}
    assert PROOF_FILENAME in collected_names
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *target_paths],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        env=_sanitized_env(),
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, f"collection failed:\n{output}"
    assert HELPER_FILENAME not in output
    assert SELECTOR_FILENAME not in output
    assert PROOF_FILENAME in output


# --- Authorization-first selector body


def test_selected_live_test_authorization_first_then_session() -> None:
    """The selected live test's first statement must be the bare auth call.

    The authorization call must precede any session construction, and the
    test body must not open connections itself (connections are opened only
    inside the helper cell).
    """
    source = _selector_source()
    tree = ast.parse(source)
    function = _single_function_by_name(tree, SELECTED_TEST_NAME)
    assert not function.decorator_list, "the selected live test must not be decorated"

    statements = list(function.body)
    if (
        statements
        and isinstance(statements[0], ast.Expr)
        and isinstance(statements[0].value, ast.Constant)
        and isinstance(statements[0].value.value, str)
    ):
        statements = statements[1:]
    assert statements, "the selected live test body must not be empty"
    first_statement = statements[0]
    assert isinstance(first_statement, ast.Expr) and isinstance(
        first_statement.value, ast.Call
    ), "the first statement must be the bare _require_authorization() call"
    first_call = first_statement.value
    assert isinstance(first_call.func, ast.Name), (
        "the first call must be the direct _require_authorization()"
    )
    assert first_call.func.id == "_require_authorization"
    assert not first_call.args and not first_call.keywords

    session_calls = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "DisposableE2aSession"
    ]
    assert session_calls, "the selected live test must construct a session"
    for session_call in session_calls:
        assert session_call.lineno > first_call.lineno, (
            "no session construction may precede the authorization check"
        )
    referenced_names = {
        node.id for node in ast.walk(function) if isinstance(node, ast.Name)
    }
    assert "open_fresh_attested_connection" not in referenced_names


# --- Helper reconciler arrangement


def test_helper_constructs_exactly_two_default_reconcilers() -> None:
    """The helper must build exactly two default reconcilers.

    One bare ``E2aReconciler()`` (the ABC second reconciliation) and one
    ``E2aReconciler(post_lock_sync_hook=_hold_after_locks(...))`` (the AB
    hooked reconciliation). No repository, builder, or failure-audit
    keyword may appear anywhere in the helper.
    """
    tree = ast.parse(_helper_source())
    reconciler_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "E2aReconciler"
    ]
    assert len(reconciler_calls) == 2, (
        "the helper must construct exactly two E2aReconciler instances"
    )
    hooked = [
        call
        for call in reconciler_calls
        if any(keyword.arg == "post_lock_sync_hook" for keyword in call.keywords)
    ]
    bare = [
        call for call in reconciler_calls if not call.args and not call.keywords
    ]
    assert len(hooked) == 1, "exactly one reconciler must carry the lock hook"
    assert len(bare) == 1, "exactly one reconciler must be the bare default"
    assert not hooked[0].args, "the hooked reconciler must take no positional args"
    assert len(hooked[0].keywords) == 1, (
        "the hooked reconciler must take only the post_lock_sync_hook keyword"
    )
    hook_value = hooked[0].keywords[0].value
    assert isinstance(hook_value, ast.Call) and isinstance(
        hook_value.func, ast.Name
    ), "the hook must come from the _hold_after_locks factory"
    assert hook_value.func.id == "_hold_after_locks"
    assert hook_value.args and not hook_value.keywords, (
        "_hold_after_locks must receive the two events positionally"
    )

    for keyword in ast.walk(tree):
        if not isinstance(keyword, ast.keyword):
            continue
        assert keyword.arg not in {
            "repository",
            "builder",
            "failure_audit_connection_factory",
        }, f"forbidden reconciler keyword used: {keyword.arg!r}"


# --- Exactly one observer catalog query; no manual lock statements


def test_observer_runs_exactly_one_advisory_catalog_query() -> None:
    """The helper source must contain the catalog view name exactly once.

    The single query must filter ``locktype = 'advisory'`` (distinguishing
    advisory tuples from relation and tuple locks), and no manual
    advisory-lock statement may appear in either module.
    """
    helper_source = _helper_source()
    selector_source = _selector_source()
    assert helper_source.count("pg_locks") == 1, (
        "the helper must contain exactly one advisory-lock catalog view query"
    )
    assert "pg_locks" not in selector_source
    query_line = next(
        line for line in helper_source.splitlines() if "pg_locks" in line
    )
    assert "locktype = 'advisory'" in query_line
    assert "pg_advisory" not in helper_source
    assert "pg_advisory" not in selector_source


# --- Forbidden APIs and patterns


_FORBIDDEN_IMPORT_MODULES = frozenset(
    {
        "select",
        "multiprocessing",
        "subprocess",
        "asyncio",
        "os",
        "socket",
        "signal",
    }
)
_FORBIDDEN_IDENTIFIERS = frozenset(
    {
        "sleep",
        "poll",
        "_Repository",
        "_Connection",
        "_Cursor",
        "conn_factory",
        "_conn_factory",
        "injected",
        "testkit",
        "module_name_is_blocked",
    }
)
_FORBIDDEN_CONSTANT_FRAGMENTS = (
    "pg_advisory",
    "LISTEN",
    "NOTIFY",
    "CREATE TABLE",
    "ALTER TABLE",
    "DROP TABLE",
    "TRUNCATE",
    "CREATE TRIGGER",
    "CREATE INDEX",
    "DATABASE_URL",
    "OKF_E2A_DISPOSABLE_TEST_AUTHORIZED",
    "conn_factory",
    "connection_factory",
)


def test_no_forbidden_apis_or_patterns_in_c6_modules() -> None:
    """No forbidden imports, calls, identifiers, or SQL fragments.

    Applies to both the helper and the selector: no sleep or polling, no
    multiprocessing/subprocess, no LISTEN/NOTIFY, no DDL, no environment
    access, no docker, no fakes, no injected factory, no manual advisory
    lock statements.
    """
    for filename, source in (
        (HELPER_FILENAME, _helper_source()),
        (SELECTOR_FILENAME, _selector_source()),
    ):
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert (
                        alias.name not in _FORBIDDEN_IMPORT_MODULES
                    ), f"{filename}: forbidden import {alias.name!r}"
            if isinstance(node, ast.ImportFrom):
                assert (
                    node.module not in _FORBIDDEN_IMPORT_MODULES
                ), f"{filename}: forbidden import from {node.module!r}"
                for alias in node.names:
                    assert (
                        alias.name not in _FORBIDDEN_IMPORT_MODULES
                    ), f"{filename}: forbidden import {alias.name!r}"
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    assert node.func.id not in {"sleep", "poll", "print"}, (
                        f"{filename}: forbidden call {node.func.id}()"
                    )
                if isinstance(node.func, ast.Attribute):
                    assert node.func.attr not in {"sleep", "poll"}, (
                        f"{filename}: forbidden call .{node.func.attr}()"
                    )
            if isinstance(node, ast.Name):
                assert node.id not in _FORBIDDEN_IDENTIFIERS, (
                    f"{filename}: forbidden identifier {node.id!r}"
                )
            if isinstance(node, ast.Attribute):
                assert node.attr not in _FORBIDDEN_IDENTIFIERS, (
                    f"{filename}: forbidden attribute {node.attr!r}"
                )
            if isinstance(node, ast.keyword):
                assert node.arg not in _FORBIDDEN_IDENTIFIERS, (
                    f"{filename}: forbidden keyword {node.arg!r}"
                )
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for fragment in _FORBIDDEN_CONSTANT_FRAGMENTS:
                    assert fragment not in node.value, (
                        f"{filename}: forbidden string fragment {fragment!r}"
                    )


def test_helper_never_constructs_a_session() -> None:
    """The helper must never reference the disposable session type.

    Session construction happens only in the explicitly selected live
    selector; the helper receives the entered session as an opaque value
    and opens every connection through the shared live-cell helpers.
    """
    tree = ast.parse(_helper_source())
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            assert node.id != "DisposableE2aSession", (
                "the helper must not reference the session type"
            )
        if isinstance(node, ast.Attribute):
            assert node.attr != "open_fresh_attested_connection", (
                "the helper must not open connections itself"
            )


def test_helper_imports_only_trusted_seams() -> None:
    """The helper imports only stdlib plus the shared live-cell helpers.

    The bounded ``_error_reason`` diagnostic must come from the shared
    live-cell module (never redefined here), and the helper must not import
    the recording testkit (no fakes in the live helper).
    """
    tree = ast.parse(_helper_source())
    import_froms = [
        node for node in tree.body if isinstance(node, ast.ImportFrom)
    ]
    modules = {
        node.module.lstrip(".") for node in import_froms if node.module is not None
    }
    assert "_phase15_e2a_task88_live_cells" in modules, (
        "the helper must reuse the shared live-cell trusted seams"
    )
    names = {
        alias.name for node in import_froms for alias in node.names if alias.name
    }
    assert "_error_reason" in names, (
        "the bounded diagnostic must come from the shared live-cell module"
    )
    assert "_open_reconciler_primary_connection" in names
    assert "_open_observer_connection" in names
    assert "_build_foundation_desired_state" in names
    assert "_phase15_e2a_task88_testkit" not in modules
    assert "_phase15_e2a_task88_cells" not in modules


def test_selector_imports_only_expected_seams() -> None:
    """The selector imports only the session, the auth gate, and the cell."""
    tree = ast.parse(_selector_source())
    import_froms = [
        node for node in tree.body if isinstance(node, ast.ImportFrom)
    ]
    names = {
        alias.name for node in import_froms for alias in node.names if alias.name
    }
    assert "_run_c6_impl" in names
    assert "DisposableE2aSession" in names
    assert "_require_authorization" in names
    assert "_validate_container_name" in names
    assert "_generate_safe_container_name" in names
    assert "_generate_test_password" in names
    assert "_select_ephemeral_port" in names
    assert "E2aReconciler" not in names
    assert "E2aMaterializationRepository" not in names
    referenced = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert "E2aReconciler" not in referenced, (
        "the selector must never construct or reference a reconciler"
    )


# --- Redacted diagnostics


def test_observations_repr_redacts_error_reason() -> None:
    """The observations repr must filter out ``error_reason`` entirely.

    The repr body must compare the key against the literal
    ``"error_reason"`` and skip it, and the class must declare the
    observation fields used by the selector assertions. No ``print`` call
    may appear in either module.
    """
    source = _helper_source()
    tree = ast.parse(source)
    observations = _single_class_by_name(tree, OBSERVATIONS_CLASS_NAME)
    repr_functions = [
        node
        for node in observations.body
        if isinstance(node, ast.FunctionDef) and node.name == "__repr__"
    ]
    assert len(repr_functions) == 1, "the observations class needs a __repr__"
    segment = ast.get_source_segment(source, repr_functions[0])
    assert segment is not None
    assert 'key != "error_reason"' in segment, (
        "the repr must structurally exclude the error_reason field"
    )
    field_names = {
        node.target.id for node in observations.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    for required in ("first_outcome", "second_outcome", "common_tuple_exact",
                     "lock_mapping_exact", "threads_joined_cleanly", "success",
                     "error_reason"):
        assert required in field_names, f"missing observation field {required!r}"


# --- Bounded finally cleanup


def test_finally_releases_and_joins_workers_bounded() -> None:
    """Finally must release hook and join both workers with bounded timeouts."""
    tree = ast.parse(_helper_source())
    impl = _single_function_by_name(tree, "_run_c6_impl")

    try_nodes = [node for node in ast.walk(impl) if isinstance(node, ast.Try)]
    assert try_nodes, "_run_c6_impl must contain a try/finally block"
    final_tries = [node for node in try_nodes if node.finalbody]
    assert final_tries, "a try block must carry a finally block"
    finalbody_tree = ast.Module(body=list(final_tries[0].finalbody), type_ignores=[])
    release_calls = [
        node
        for node in ast.walk(finalbody_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "set"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "release_event"
    ]
    assert release_calls, "the finally block must release the AB hook"
    join_calls = [
        node
        for node in ast.walk(finalbody_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "join"
    ]
    assert len(join_calls) >= 2, (
        "the finally block must join both reconciliation worker threads"
    )

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(
            node.func, ast.Attribute
        ):
            continue
        if node.func.attr not in {"wait", "join"}:
            continue
        if not isinstance(node.func.value, ast.Name):
            continue
        timeout_keywords = [
            keyword for keyword in node.keywords if keyword.arg == "timeout"
        ]
        assert len(timeout_keywords) == 1, (
            f"every .{node.func.attr}() call must carry exactly one timeout"
        )
        assert _is_bounded_timeout(timeout_keywords[0].value), (
            f".{node.func.attr}() timeout must be bounded (constant or deadline)"
        )


def _is_bounded_timeout(value: ast.expr) -> bool:
    """True for positive constants or the shared-deadline remaining helper."""
    if (
        isinstance(value, ast.Constant)
        and isinstance(value.value, (int, float))
        and value.value > 0
    ):
        return True
    return (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id == "_remaining"
        and len(value.args) == 1
    )


# --- PARTIAL(C6) docstring boundary


_FORBIDDEN_DOCSTRING_FRAGMENTS = ("C14", "completion", "delivered", "closure",
                                  "throughput", "latency", "guarantee", "DATABASE_URL")


def test_c6_docstrings_pin_partial_boundary() -> None:
    """Every C6 docstring pins PARTIAL(C6) and no completion claims."""
    helper_tree = ast.parse(_helper_source())
    selector_tree = ast.parse(_selector_source())
    selected = _single_function_by_name(selector_tree, SELECTED_TEST_NAME)

    docstrings = (
        ast.get_docstring(helper_tree, clean=False) or "",
        ast.get_docstring(selector_tree, clean=False) or "",
        ast.get_docstring(selected, clean=False) or "",
    )
    for docstring in docstrings:
        assert "PARTIAL(C6)" in docstring, "the docstring must pin PARTIAL(C6)"
        for fragment in _FORBIDDEN_DOCSTRING_FRAGMENTS:
            assert fragment not in docstring, (
                f"docstring must not claim completion or expose URLs: {fragment!r}"
            )


# --- Fresh-process import and fails-closed proof


def _spec_loader_script() -> str:
    """Fresh-process script: spec-load the C6 helper and selector."""
    return f"""
import os, sys, importlib.util
from types import ModuleType
from pathlib import Path

project_root = Path("{PROJECT_ROOT.as_posix()}")
sys.path.insert(0, str(project_root))
for var in ("OKF_E2A_DISPOSABLE_TEST_AUTHORIZED","DATABASE_URL","FORMAL_RUNTIME_DATABASE_URL","OKF_MIGRATION_TEST_DATABASE_DISPOSABLE","OKF_REBUILD_EXPECTED_DATABASE","OKF_FAILURE_AUDIT_ACCEPTANCE","OKF_REBUILD_DOCKER_ACCEPTANCE","PGSERVICE","PGSERVICEFILE","PGSYSCONFDIR","PGHOST","PGPORT","PGUSER","PGPASSWORD","PGDATABASE"):
    os.environ.pop(var, None)
for pkg, rel in (("tests","tests"),("tests.llamaindex_runtime","tests/llamaindex_runtime"),("tests.llamaindex_runtime.okf","tests/llamaindex_runtime/okf")):
    m = ModuleType(pkg)
    m.__path__ = [str(project_root / rel)]
    m.__package__ = pkg
    sys.modules[pkg] = m
def load(name, file):
    spec = importlib.util.spec_from_file_location(name, project_root / "tests" / "llamaindex_runtime" / "okf" / file, submodule_search_locations=[])
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "tests.llamaindex_runtime.okf"
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod
for name, file in (("tests.llamaindex_runtime.okf._phase15_e2a_task88_cells","_phase15_e2a_task88_cells.py"),("tests.llamaindex_runtime.okf._phase15_e2a_harness_types","_phase15_e2a_harness_types.py"),("tests.llamaindex_runtime.okf._phase15_e2a_harness_lifecycle","_phase15_e2a_harness_lifecycle.py"),("tests.llamaindex_runtime.okf._phase15_e2a_task88_live_cells","_phase15_e2a_task88_live_cells.py"),("tests.llamaindex_runtime.okf._phase15_e2a_task88_concurrency_cells","_phase15_e2a_task88_concurrency_cells.py"),("tests.llamaindex_runtime.okf.phase15_e2a_task88_live_concurrency","phase15_e2a_task88_live_concurrency.py")):
    load(name, file)
guard = sys.modules["tests.llamaindex_runtime.okf._phase15_e2a_task88_cells"]
if [n for n in sys.modules if guard.module_name_is_blocked(n)]:
    print("prohibited module loaded", file=sys.stderr); sys.exit(1)
if "tests.llamaindex_runtime.okf._phase15_e2a_task88_testkit" in sys.modules:
    print("testkit imported", file=sys.stderr); sys.exit(2)
helper = sys.modules["tests.llamaindex_runtime.okf._phase15_e2a_task88_concurrency_cells"]
selector = sys.modules["tests.llamaindex_runtime.okf.phase15_e2a_task88_live_concurrency"]
if "DisposableE2aSession" in dir(helper):
    print("helper exposes session", file=sys.stderr); sys.exit(3)
if "E2aReconciler" in dir(selector):
    print("selector exposes reconciler", file=sys.stderr); sys.exit(4)
if not callable(getattr(selector, "test_phase15_e2a_task88_c6_advisory_lock_concurrency_live", None)):
    print("selected test missing", file=sys.stderr); sys.exit(5)
from tests.llamaindex_runtime.okf._phase15_e2a_harness_types import _require_authorization
try: _require_authorization()
except RuntimeError as e:
    if str(e) != "{AUTHORIZATION_FIRST_MESSAGE}": sys.exit(6)
else: sys.exit(7)
sys.exit(0)
"""


def test_fresh_process_imports_c6_modules_and_fails_closed() -> None:
    """Verify the C6 modules import cleanly and the gate fails closed."""
    result = subprocess.run(
        [sys.executable, "-c", _spec_loader_script()],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        env=_sanitized_env(),
    )
    if result.returncode == 0:
        return
    messages = {
        1: "prohibited module loaded",
        2: "testkit imported",
        3: "helper exposes session",
        4: "selector exposes reconciler",
        5: "selected test missing",
        6: "authorization message changed",
        7: "authorization passed without flag",
    }
    msg = messages.get(result.returncode, "unexpected failure")
    assert False, f"fresh-process verification failed: {msg}\n{result.stderr}"


def test_sanitized_env_builder_never_reads_broad_environment() -> None:
    """AST guard: _sanitized_env reads only explicit allowlist keys.

    The builder must never enumerate, copy, or read ``os.environ`` as a
    container, may only read individual non-sensitive keys via literal
    ``os.getenv`` calls, and the structural verifier must reject the
    getattr-indirection shape a future intentional edit could try.
    """
    source = (OKF_DIR / PROOF_FILENAME).read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = _single_function_by_name(tree, "_sanitized_env")
    segment = ast.get_source_segment(source, function)
    assert segment is not None
    for forbidden in (
        "os.environ",
        "environ",
        "dict(",
        "__import__",
        ".items(",
        ".keys(",
        ".values(",
        ".copy(",
        ".get(",
    ):
        assert (
            forbidden not in segment
        ), f"_sanitized_env must not use broad environment access: {forbidden!r}"
    _verify_sanitized_env_structure(function)

    allowlist_reads = "\n".join(
        f'        ("{key}", os.getenv("{key}")),' for key in _SANITIZED_ALLOWLIST
    )
    fixture = (
        "def _sanitized_env() -> dict[str, str]:\n"
        "    env: dict[str, str] = {}\n"
        "    for key, value in (\n"
        f"{allowlist_reads}\n"
        '        ("DATABASE_URL", getattr(os, "getenv")("DATABASE_URL")),\n'
        "    ):\n"
        "        if value is not None:\n"
        "            env[key] = value\n"
        "    return env\n"
    )
    fixture_function = _single_function_by_name(ast.parse(fixture), "_sanitized_env")
    with pytest.raises(AssertionError):
        _verify_sanitized_env_structure(fixture_function)
