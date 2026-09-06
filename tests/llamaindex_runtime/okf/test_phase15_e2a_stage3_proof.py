"""Static AST source-proof for the Task #88 Stage 3 tranche (non-live).

Never imports, executes, or collects the live modules; reads source text and
inspects parsed ASTs only, so comments/docstrings cannot cause false
positives or satisfy a check by accident. Pinned for ALL new Stage 3 modules
(helper + one explicitly selected live selector with five cells): auth-first
plain live tests; ``phase15_`` filename uncollected by default discovery; no
prohibited module families, no pytest/skip/xfail references, no environment
access, no direct connections, no dynamic imports, no fakes; connections
only through the Stage 1 attested openers or the Stage 3 seed opener;
PARTIAL(C7), PARTIAL(C8), PARTIAL(C9), PARTIAL(C10), PARTIAL(C12) disclaimer
labels; every cell uses the default ``E2aReconciler()`` (the C5-only audit
factory policy is unchanged and no Stage 3 cell injects a factory); failures
absorb into redacted observations via the bounded ``_error_reason``; failed
cells raise RuntimeError carrying only ``observations.error_reason``; the
superseded C4/C5 identities (``_run_c4_impl`` / ``_run_c5_impl`` and the
C4 default-failure contract test name) are never reused or renamed; the
Task #88 global acceptance selector identity is never referenced; no
PASS language; all new modules under 800 lines; helper defines
no test functions.

Stage 3 specific pins: exactly five live cells with pinned names and pinned
reconcile-call counts; C7 pins the sparse stale-ID count map plus committed
row-count absence probes (never equating statement counts with row counts);
C8 pins the deterministic repair target and source-backed program order plus
post-state (never observed interleaving); C9 pins 16-dimensional chunk
vectors and 384-dimensional node embedding vectors, an explicit ``%s::vector``
cast on the seeded embedding parameter, measured
``cache_invalidation_counts``, and join-free committed post-delete absence
probes (never the production JOIN-based measurement query as the final
absence probe); C10 pins the exact production-anchored fail-closed pre-DML
error ``stale span has entity_mentions dependencies`` and the intact
post-state, isolated from E2b and C14 and never late-DML evidence; C12 pins
the parentless cleanup with registry document/version retention and an exact
second-run no-op, never claiming shared-global manual-fact preservation.

This module complements (never weakens) the Stage 1/2/2R proof modules; it
adds proofs only for the new Stage 3 surface.
"""

from __future__ import annotations

import ast
from pathlib import Path

_DIR = Path(__file__).parent
_HELPER_PATH = _DIR / "_phase15_e2a_task88_stage3_cells.py"
_SELECTOR_PATH = _DIR / "phase15_e2a_task88_live_stale_cells.py"
_STAGE1_HELPER_PATH = _DIR / "_phase15_e2a_task88_live_cells.py"
_ALL_PATHS = (_HELPER_PATH, _SELECTOR_PATH)

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

_STAGE3_IMPL_NAMES = (
    "_run_c7_impl",
    "_run_c8_impl",
    "_run_c9_impl",
    "_run_c10_impl",
    "_run_c12_impl",
)
_STAGE3_OBSERVATION_TYPES = frozenset(
    {
        "C7StaleDeletionObservations",
        "C8ChunkRepointObservations",
        "C9CacheInvalidationObservations",
        "C10DestructiveClosureObservations",
        "C12ParentlessCleanupObservations",
    }
)
_EXPECTED_LIVE_TEST_NAMES = (
    "test_phase15_e2a_task88_c7_stale_span_deletion_live",
    "test_phase15_e2a_task88_c8_chunk_repoint_live",
    "test_phase15_e2a_task88_c9_cache_invalidation_live",
    "test_phase15_e2a_task88_c10_destructive_closure_live",
    "test_phase15_e2a_task88_c12_parentless_cleanup_live",
)
# Source-backed program order: each cell reconciles exactly this many times.
_EXPECTED_RECONCILE_COUNTS = {
    "_run_c7_impl": 2,
    "_run_c8_impl": 2,
    "_run_c9_impl": 2,
    "_run_c10_impl": 2,
    "_run_c12_impl": 3,
}
# Every connection each cell opens must be closed in its finally block.
_EXPECTED_FINALLY_CLOSE_NAMES = {
    "_run_c7_impl": frozenset(
        {"writer_conn", "primary_conn", "second_primary_conn", "observer_conn"}
    ),
    "_run_c8_impl": frozenset(
        {"writer_conn", "primary_conn", "second_primary_conn", "observer_conn"}
    ),
    "_run_c9_impl": frozenset(
        {
            "writer_conn",
            "primary_conn",
            "second_primary_conn",
            "seed_conn",
            "observer_conn",
        }
    ),
    "_run_c10_impl": frozenset(
        {"writer_conn", "primary_conn", "seed_conn", "observer_conn"}
    ),
    "_run_c12_impl": frozenset(
        {"writer_conn", "primary_conn", "cleanup_conn", "noop_conn", "observer_conn"}
    ),
}
_FORBIDDEN_DIRECT_DB_ATTRIBUTES = frozenset(
    {"cursor", "execute", "fetchone", "fetchall", "commit", "rollback", "connect"}
)
_DYNAMIC_IMPORT_MECHANISM_NAMES = ("importlib", "import_module", "__import__")
_FAKE_MACHINERY_NAMES = ("mock", "MagicMock", "monkeypatch", "unittest", "patch")

_STAGE1_OPENERS = (
    "_open_writer_connection",
    "_open_reconciler_primary_connection",
    "_open_observer_connection",
)
_ALL_OPENER_NAMES = (*_STAGE1_OPENERS, "_open_seed_connection")

# Per-cell disclaimer tokens (normalized docstring substrings).
_DISCLAIMER_TOKENS = {
    "test_phase15_e2a_task88_c7_stale_span_deletion_live": (
        "PARTIAL(C7)",
        "sparse stale-ID",
        "row counts",
        "never C14",
    ),
    "test_phase15_e2a_task88_c8_chunk_repoint_live": (
        "PARTIAL(C8)",
        "deterministic repair target",
        "source-backed program order",
        "never C14",
    ),
    "test_phase15_e2a_task88_c9_cache_invalidation_live": (
        "PARTIAL(C9)",
        "measured cache invalidation counts",
        "join-free",
        "never C14",
    ),
    "test_phase15_e2a_task88_c10_destructive_closure_live": (
        "PARTIAL(C10)",
        "fail-closed pre-DML",
        "foreign dependency",
        "never E2b",
        "late-DML evidence",
        "never C14",
    ),
    "test_phase15_e2a_task88_c12_parentless_cleanup_live": (
        "PARTIAL(C12)",
        "exact no-op",
        "shared-global manual-fact",
        "never C14",
    ),
}


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


def _function_docstring(tree: ast.Module, name: str) -> str:
    doc = ast.get_docstring(_function_by_name(tree, name))
    assert doc is not None, f"{name} docstring is required"
    return " ".join(doc.split())


def _function_source_segment(path: Path, name: str) -> str:
    tree, source = _parse_module(path)
    segment = ast.get_source_segment(source, _function_by_name(tree, name))
    assert segment is not None, f"missing source segment for {name}"
    return segment


# ---------------------------------------------------------------------------
# Files, discovery, and auth-first structure
# ---------------------------------------------------------------------------


def test_stage3_files_exist() -> None:
    for path in _ALL_PATHS:
        assert path.is_file(), f"missing Stage 3 module: {path}"


def test_stage3_files_under_800_lines() -> None:
    for path in _ALL_PATHS:
        source = _parse_module(path)[1]
        assert source.count("\n") + 1 < 800, f"{path.name} exceeds 800 lines"


def test_stage3_selector_not_collected_by_discovery() -> None:
    name = _SELECTOR_PATH.name
    assert name.startswith("phase15_"), "selector must use the phase15_ prefix"
    assert not name.startswith("test_"), "selector must not match test_*.py"
    assert not name.endswith("_test.py"), "selector must not match *_test.py"
    assert name.endswith(".py"), "selector must be a python module"


def test_stage3_selector_live_test_names_exact() -> None:
    tree, _ = _parse_module(_SELECTOR_PATH)
    functions = _test_functions(tree)
    assert [fn.name for fn in functions] == list(
        _EXPECTED_LIVE_TEST_NAMES
    ), "selector must define exactly the five pinned live cells"


def test_stage3_selector_test_functions_auth_first() -> None:
    tree, _ = _parse_module(_SELECTOR_PATH)
    functions = _test_functions(tree)
    assert len(functions) == 5, "selector must define exactly five live tests"
    for fn in functions:
        assert _auth_first(fn), f"{fn.name} live test must be auth-first"


def test_stage3_selector_test_functions_no_decorators_or_fixtures() -> None:
    tree, _ = _parse_module(_SELECTOR_PATH)
    for fn in _test_functions(tree):
        assert not fn.decorator_list, f"{fn.name} must have no decorators"
        params = fn.args.posonlyargs + fn.args.args + fn.args.kwonlyargs
        assert not params, f"{fn.name} must take no parameters (no fixtures)"


def test_stage3_selector_imports_require_authorization() -> None:
    tree, _ = _parse_module(_SELECTOR_PATH)
    found = any(
        isinstance(node, ast.ImportFrom)
        and any(alias.name == "_require_authorization" for alias in node.names)
        for node in ast.walk(tree)
    )
    assert found, "selector must import _require_authorization"


def test_stage3_selector_imports_stage3_helper() -> None:
    tree, _ = _parse_module(_SELECTOR_PATH)
    found = any(
        isinstance(node, ast.ImportFrom)
        and node.module is not None
        and "stage3_cells" in node.module
        for node in ast.walk(tree)
    )
    assert found, "selector must import the Stage 3 helper"


def test_stage3_helper_defines_no_test_functions() -> None:
    tree, _ = _parse_module(_HELPER_PATH)
    assert not _test_functions(tree), "helper must not define test functions"


# ---------------------------------------------------------------------------
# Security and boundary surface
# ---------------------------------------------------------------------------


def test_stage3_modules_no_forbidden_imports() -> None:
    for path in _ALL_PATHS:
        tree, _ = _parse_module(path)
        forbidden = [
            name for name in _imported_module_names(tree) if _module_is_forbidden(name)
        ]
        assert not forbidden, f"forbidden import in {path.name}: {forbidden}"


def test_stage3_modules_no_environment_access() -> None:
    for path in _ALL_PATHS:
        _assert_no_environment_access(path)


def test_stage3_modules_no_pytest_references() -> None:
    for path in _ALL_PATHS:
        _assert_no_pytest_references(path)


def test_stage3_modules_no_dynamic_import_mechanisms() -> None:
    for path in _ALL_PATHS:
        violations = _dynamic_import_violations(_parse_module(path)[0])
        assert not violations, f"{path.name} must not use dynamic imports: {violations}"


def test_stage3_modules_no_fake_machinery() -> None:
    for path in _ALL_PATHS:
        _, source = _parse_module(path)
        lowered = source.lower()
        for token in _FAKE_MACHINERY_NAMES:
            assert token not in lowered, f"{path.name} must not reference {token}"


def test_stage3_helper_no_direct_database_or_factory_bypass() -> None:
    tree, _ = _parse_module(_HELPER_PATH)
    for name in _imported_module_names(tree):
        assert "psycopg" not in name, f"helper must not import psycopg: {name}"
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr == "connect":
            raise AssertionError("helper must not call .connect(...) directly")


def test_stage3_selector_no_direct_database_or_reconciler_work() -> None:
    tree, _ = _parse_module(_SELECTOR_PATH)
    for name in _imported_module_names(tree):
        assert "psycopg" not in name, "selector must not import psycopg"
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            assert not (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in _FORBIDDEN_DIRECT_DB_ATTRIBUTES
            ), "selector must not issue direct database work"
        if isinstance(node, ast.Name) and node.id == "E2aReconciler":
            raise AssertionError("selector must not construct the reconciler")


def test_stage3_helper_all_attested_connections_via_session_openers() -> None:
    """All connections flow through the Stage 1 attested openers or the
    Stage 3 seed opener; every opener call receives the session object and no
    opener is bypassed."""
    tree, _ = _parse_module(_HELPER_PATH)
    for name in _STAGE1_OPENERS:
        found = any(
            isinstance(node, ast.ImportFrom)
            and node.module == "_phase15_e2a_task88_live_cells"
            and any(alias.name == name for alias in node.names)
            for node in ast.walk(tree)
        )
        assert found, f"helper must import {name}"
    seed_opener = any(
        isinstance(node, ast.FunctionDef) and node.name == "_open_seed_connection"
        for node in tree.body
    )
    assert seed_opener, "helper must define _open_seed_connection"
    opener_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _ALL_OPENER_NAMES
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


def test_stage3_helper_observation_types_redacted_repr() -> None:
    tree, source = _parse_module(_HELPER_PATH)
    classes = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name in _STAGE3_OBSERVATION_TYPES
    }
    assert classes == set(
        _STAGE3_OBSERVATION_TYPES
    ), f"missing observation types: {classes}"
    repr_functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "__repr__"
    ]
    assert len(repr_functions) == 5, "exactly five observation reprs expected"
    segments = [ast.get_source_segment(source, fn) or "" for fn in repr_functions]
    for segment in segments:
        assert "<redacted>" in segment, "every observation repr must redact details"


def test_stage3_helper_cells_default_reconciler_only() -> None:
    """All five Stage 3 cells use default E2aReconciler(); the C5-only audit
    factory policy is unchanged and no Stage 3 cell injects a factory."""
    tree, _ = _parse_module(_HELPER_PATH)
    for name in _STAGE3_IMPL_NAMES:
        fn = _function_by_name(tree, name)
        calls = _e2a_reconciler_calls(fn)
        assert calls, f"{name} must construct E2aReconciler"
        for call in calls:
            assert not call.args, f"{name}: E2aReconciler takes no positional args"
            assert not call.keywords, f"{name}: E2aReconciler must be default"
    _, source = _parse_module(_HELPER_PATH)
    assert (
        "failure_audit_connection_factory" not in source
    ), "Stage 3 cells must not inject the audit factory"


def test_stage3_helper_cells_close_resources_in_finally() -> None:
    tree, _ = _parse_module(_HELPER_PATH)
    for name, expected in _EXPECTED_FINALLY_CLOSE_NAMES.items():
        closed = _finally_close_arguments(_function_by_name(tree, name))
        assert expected <= closed, f"{name} must close every connection in finally"


def test_stage3_helper_cells_bounded_diagnostics() -> None:
    tree, source = _parse_module(_HELPER_PATH)
    assert (
        source.count("error_reason=_error_reason(") >= 5
    ), "each cell must absorb failures into a bounded _error_reason"
    for name in _STAGE3_IMPL_NAMES:
        fn = _function_by_name(tree, name)
        handlers = [n for n in ast.walk(fn) if isinstance(n, ast.ExceptHandler)]
        assert any(
            isinstance(h.type, ast.Name)
            and h.type.id == "Exception"
            and h.name is not None
            for h in handlers
        ), f"{name} failure path must bind the original exception"


def test_stage3_selectors_raise_only_observation_error_reason() -> None:
    tree, _ = _parse_module(_SELECTOR_PATH)
    for fn in _test_functions(tree):
        raises = _runtime_error_raises(fn)
        assert len(raises) == 1, f"{fn.name} must raise exactly one RuntimeError"
        for raise_node in raises:
            assert _raise_message_is_only_observation_error_reason(raise_node)


def test_stage3_reconcile_call_counts_pinned() -> None:
    """Source-backed program order: each cell performs exactly the pinned
    number of reconciles (never observed interleaving, never polling)."""
    tree, _ = _parse_module(_HELPER_PATH)
    for name, expected in _EXPECTED_RECONCILE_COUNTS.items():
        fn = _function_by_name(tree, name)
        assert (
            len(_reconcile_calls(fn)) == expected
        ), f"{name} must reconcile exactly {expected} times"


# ---------------------------------------------------------------------------
# Disclaimer labels, claim language, superseded C4/C5, global acceptance isolation
# ---------------------------------------------------------------------------


def test_stage3_selector_disclaimer_tokens_present() -> None:
    tree, _ = _parse_module(_SELECTOR_PATH)
    for name, tokens in _DISCLAIMER_TOKENS.items():
        doc = _function_docstring(tree, name)
        for token in tokens:
            assert token in doc, f"{name} docstring must contain {token!r}"


def test_stage3_modules_no_task_or_phase_pass_completion_language() -> None:
    for path in _ALL_PATHS:
        _, source = _parse_module(path)
        lowered = source.lower()
        for phrase in _FORBIDDEN_CLAIM_PHRASES:
            assert phrase not in lowered, f"forbidden claim language: {phrase}"


def test_stage3_helper_does_not_reuse_superseded_c4_c5_identities() -> None:
    """The old C4/C5 identities are one-run: never reused or renamed."""
    tree, _ = _parse_module(_HELPER_PATH)
    defined = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "_run_c4_impl" not in defined, "old C4 identity must not be reused"
    assert "_run_c5_impl" not in defined, "old C5 identity must not be reused"
    _, source = _parse_module(_SELECTOR_PATH)
    assert "test_phase15_e2a_task88_c4_default_failure_contract_live" not in source


def test_stage3_modules_isolated_from_global_acceptance_selector() -> None:
    """The Task #88 global acceptance selector identity is never referenced."""
    for path in _ALL_PATHS:
        _, source = _parse_module(path)
        for identifier in _TASK88_GLOBAL_ACCEPTANCE_IDENTIFIERS:
            assert identifier not in source, f"{path.name} references {identifier}"


def test_stage3_helper_role_separation_means_connections_not_principals() -> None:
    doc = _docstring_normalized(_HELPER_PATH)
    assert "not distinct PostgreSQL principals" in doc
    assert "fresh attested connection" in doc


# ---------------------------------------------------------------------------
# Stage 3 behavioral pins (C7/C8/C9/C10/C12)
# ---------------------------------------------------------------------------


def test_stage3_c7_sparse_stale_id_map_and_row_count_absence() -> None:
    """C7 must pin a sparse stale-ID count map and committed row-count absence
    probes, never equating statement counts with row counts."""
    segment = _function_source_segment(_HELPER_PATH, "_run_c7_impl")
    assert "stale_deletion_counts" in segment, "C7 must read the stale-ID map"
    assert "SELECT COUNT(*) FROM canonical_spans WHERE span_id" in segment
    assert "SELECT COUNT(*) FROM tree_node_spans WHERE span_id" in segment
    assert "SELECT COUNT(*) FROM vector_chunk_spans WHERE span_id" in segment


def test_stage3_c8_deterministic_repair_target_pinned() -> None:
    """C8 must pin the deterministic per-version repair target against the
    production _tree_repair_targets authority and observe post-state only."""
    segment = _function_source_segment(_HELPER_PATH, "_run_c8_impl")
    assert "_tree_repair_targets" in segment, "C8 must use the production target"
    assert "SELECT node_id FROM vector_chunks WHERE chunk_id" in segment
    assert "SELECT COUNT(*) FROM tree_nodes WHERE node_id" in segment


def test_stage3_c9_dimension_pins() -> None:
    """C9 must seed 384-dimensional node embeddings while chunks stay
    16-dimensional (foundation builder), and must read the measured
    cache_invalidation_counts."""
    helper_source = _parse_module(_HELPER_PATH)[1]
    assert "range(384)" in helper_source, "node embeddings must be 384-dimensional"
    stage1_source = _parse_module(_STAGE1_HELPER_PATH)[1]
    assert "range(16)" in stage1_source, "chunk vectors must be 16-dimensional"
    segment = _function_source_segment(_HELPER_PATH, "_run_c9_impl")
    assert "INSERT INTO node_embeddings" in segment, "C9 must seed node_embeddings"
    assert "INSERT INTO summaries" in segment, "C9 must seed summaries"
    assert "INSERT INTO semantic_distribution" in segment, "C9 must seed distribution"
    assert (
        "cache_invalidation_counts" in segment
    ), "C9 must read the measured invalidation counts"


def test_stage3_c9_join_free_final_absence_probe() -> None:
    """The final absence probe must be join-free; the production JOIN-based
    measurement query is never the final absence probe."""
    segment = _function_source_segment(_HELPER_PATH, "_run_c9_impl")
    assert "FROM summaries WHERE node_id" in segment
    assert "FROM node_embeddings WHERE node_id" in segment
    assert "FROM semantic_distribution WHERE node_id" in segment
    assert "JOIN" not in segment, "final absence probes must be join-free"


def test_stage3_c9_embedding_vector_explicit_vector_cast() -> None:
    """The seeded node embedding must bind through an explicit %s::vector cast
    on the node_embeddings INSERT (a plain text bind can never reach the
    VECTOR(384) column)."""
    tree, source = _parse_module(_HELPER_PATH)
    fn = _function_by_name(tree, "_run_c9_impl")
    inserts = [
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "execute"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
        and "INSERT INTO node_embeddings" in node.args[0].value
    ]
    assert len(inserts) == 1, "C9 must contain exactly one node_embeddings INSERT"
    segment = ast.get_source_segment(source, inserts[0])
    assert segment is not None, "missing C9 node_embeddings INSERT source segment"
    assert "embedding_vector" in segment, "the cast must apply to embedding_vector"
    assert segment.count("%s") == 3, "the INSERT must stay fully parameterized"
    assert "VALUES (%s, %s, %s::vector)" in segment, (
        "the embedding_vector parameter must be bound with an explicit ::vector cast"
    )


def test_stage3_c10_exact_production_guard_message() -> None:
    """C10 must pin the exact production-anchored fail-closed error and prove
    the pre-DML state is intact."""
    helper_source = _parse_module(_HELPER_PATH)[1]
    assert (
        "stale span has entity_mentions dependencies" in helper_source
    ), "C10 must pin the exact production guard message"
    segment = _function_source_segment(_HELPER_PATH, "_run_c10_impl")
    assert "INSERT INTO entity_mentions" in segment, "C10 must seed entity_mentions"
    assert "SELECT COUNT(*) FROM canonical_spans WHERE span_id" in segment
    assert "SELECT COUNT(*) FROM entity_mentions WHERE mention_id" in segment
    assert "SELECT COUNT(*) FROM documents WHERE doc_id" in segment
    assert "SELECT COUNT(*) FROM document_versions WHERE version_id" in segment


def test_stage3_c12_second_run_exact_noop_pinned() -> None:
    """C12 must pin the parentless cleanup and an exact second-run no-op with
    registry document/version retention and no global manual facts."""
    segment = _function_source_segment(_HELPER_PATH, "_run_c12_impl")
    assert (
        segment.count("reconcile(") == 3
    ), "C12 must reconcile three times in the impl"
    assert "no_op" in segment, "C12 must pin the exact no_op outcome"
    assert "stale_deletion_counts" in segment, "C12 must pin the empty stale map"
    assert "cache_invalidation_counts" in segment, "C12 must pin the empty cache map"
    assert "SELECT COUNT(*) FROM documents WHERE doc_id" in segment
    assert "SELECT COUNT(*) FROM document_versions WHERE version_id" in segment
    helper_source = _parse_module(_HELPER_PATH)[1]
    assert "second_noop_exact" in helper_source, "C12 must carry the noop observation"
