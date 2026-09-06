"""Source and behavior proofs: C6 PID attribution and snapshot contracts.

This collected (non-live) module pins the PID-attribution contracts of the
Task #88 Stage 4 C6 advisory-lock concurrency slice:

- Both reconciliation workers publish their real PostgreSQL backend pid
  (pg_backend_pid) from their own fresh attested primaries before running
  the real reconcile.
- The sole pg_locks evidence snapshot selects the pid column, and the
  analyzer attributes every observed advisory tuple to the real sessions:
  the whole-corpus granted holder must be the AB pid, the whole-corpus
  waiter must be the ABC pid, and the parent-lock holder must be the AB pid
  (consistent with ABC blocking on the first whole-corpus lock).
- Empty or missing expected lock rows fail BOTH lock_mapping_exact and
  common_tuple_exact (never vacuously true).
- PIDs never leak into observation reprs, error reasons, or results.

The behavioral tests import the helper cell module (pure Python module
imports only; no database, no Docker) and exercise the pure row analyzer
deterministically. Nothing here executes a live selector.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ._phase15_e2a_task88_concurrency_cells import _analyze_advisory_rows

OKF_DIR = Path(__file__).parent
HELPER_FILENAME = "_phase15_e2a_task88_concurrency_cells.py"
SELECTOR_FILENAME = "phase15_e2a_task88_live_concurrency.py"

_WHOLE_KEY = 0x0102030405060708
_PARENT_KEY = 0x1112131415161718
_DATABASE_OID = 16384
_AB_PID = 10101
_ABC_PID = 20202
_OTHER_PID = 30303


def _row(
    classid: int,
    objid: int,
    granted: bool,
    pid: int,
    database: int = _DATABASE_OID,
    mode: str = "ExclusiveLock",
    objsubid: int = 1,
    locktype: str = "advisory",
) -> tuple[int, int, int, int, str, bool, str, int]:
    """One catalog row in the exact SELECT order with the pid column."""
    return (database, classid, objid, objsubid, mode, granted, locktype, pid)


def _whole_row(granted: bool, pid: int) -> tuple[int, int, int, int, str, bool, str, int]:
    """Row for the whole-corpus key halves."""
    return _row(_WHOLE_KEY >> 32, _WHOLE_KEY & 0xFFFFFFFF, granted, pid)


def _parent_row(granted: bool, pid: int) -> tuple[int, int, int, int, str, bool, str, int]:
    """Row for the per-parent key halves."""
    return _row(_PARENT_KEY >> 32, _PARENT_KEY & 0xFFFFFFFF, granted, pid)


def _exact_rows() -> tuple[tuple[int, int, int, int, str, bool, str, int], ...]:
    """The exact expected tuple set: AB granted, ABC waiting, AB parent."""
    return (
        _whole_row(True, _AB_PID),
        _whole_row(False, _ABC_PID),
        _parent_row(True, _AB_PID),
    )


def _analyze(rows: tuple[tuple[int, int, int, int, str, bool, str, int], ...]) -> tuple[bool, bool]:
    """Call the analyzer with the fixed expectation parameters."""
    return _analyze_advisory_rows(
        rows=rows,
        whole_corpus_key=_WHOLE_KEY,
        parent_key=_PARENT_KEY,
        database_oid=_DATABASE_OID,
        ab_pid=_AB_PID,
        abc_pid=_ABC_PID,
    )


# ---------------------------------------------------------------------------
# Behavioral analyzer contracts
# ---------------------------------------------------------------------------


def test_analyzer_empty_rows_fail_closed() -> None:
    """An empty snapshot must fail BOTH flags, never vacuously pass."""
    assert _analyze(()) == (False, False)


def test_analyzer_missing_parent_row_fails_closed() -> None:
    """A missing expected parent tuple must fail BOTH flags."""
    rows = (_whole_row(True, _AB_PID), _whole_row(False, _ABC_PID))
    assert _analyze(rows) == (False, False)


def test_analyzer_exact_attributed_tuples_pass() -> None:
    """The exact expected tuple set with real pids passes BOTH flags."""
    assert _analyze(_exact_rows()) == (True, True)


def test_analyzer_rejects_wrong_whole_waiter_pid() -> None:
    """A whole-corpus waiter with the wrong pid fails BOTH flags."""
    rows = (
        _whole_row(True, _AB_PID),
        _whole_row(False, _OTHER_PID),
        _parent_row(True, _AB_PID),
    )
    assert _analyze(rows) == (False, False)


def test_analyzer_rejects_wrong_whole_holder_pid() -> None:
    """A whole-corpus holder with the wrong pid fails BOTH flags."""
    rows = (
        _whole_row(True, _OTHER_PID),
        _whole_row(False, _ABC_PID),
        _parent_row(True, _AB_PID),
    )
    assert _analyze(rows) == (False, False)


def test_analyzer_rejects_wrong_parent_holder_pid() -> None:
    """A parent holder that is not AB fails BOTH flags."""
    rows = (
        _whole_row(True, _AB_PID),
        _whole_row(False, _ABC_PID),
        _parent_row(True, _OTHER_PID),
    )
    assert _analyze(rows) == (False, False)


def test_analyzer_rejects_unexpected_parent_waiter() -> None:
    """A parent waiter is inconsistent with first whole-corpus blocking."""
    rows = (
        _whole_row(True, _AB_PID),
        _whole_row(False, _ABC_PID),
        _parent_row(True, _AB_PID),
        _parent_row(False, _OTHER_PID),
    )
    assert _analyze(rows) == (False, False)


def test_analyzer_rejects_unknown_key_row() -> None:
    """A tuple mapping to neither expected key fails BOTH flags."""
    rows = _exact_rows() + (
        _row(0xDEADBEEF, 0x12345678, True, _AB_PID),
    )
    assert _analyze(rows) == (False, False)


def test_analyzer_rejects_foreign_database() -> None:
    """A tuple from another database fails BOTH flags."""
    rows = (
        _whole_row(True, _AB_PID),
        _whole_row(False, _ABC_PID),
        _row(
            _PARENT_KEY >> 32,
            _PARENT_KEY & 0xFFFFFFFF,
            True,
            _AB_PID,
            database=_DATABASE_OID + 1,
        ),
    )
    assert _analyze(rows) == (False, False)


# ---------------------------------------------------------------------------
# Structural snapshot and attribution contracts
# ---------------------------------------------------------------------------


def _helper_source() -> str:
    """Raw C6 helper source (the file must exist)."""
    return (OKF_DIR / HELPER_FILENAME).read_text(encoding="utf-8")


def _single_function_by_name(tree: ast.Module, function_name: str) -> ast.FunctionDef:
    """Return the single top-level function with the given name."""
    functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    ]
    assert len(functions) == 1, (
        f"the {function_name!r} function must exist exactly once"
    )
    return functions[0]


def test_snapshot_selects_pid_column_exactly_once() -> None:
    """The single pg_locks query must select the pid column."""
    source = _helper_source()
    assert source.count("pg_locks") == 1, (
        "the helper must contain exactly one pg_locks evidence snapshot"
    )
    query_line = next(
        line for line in source.splitlines() if "FROM pg_locks" in line
    )
    assert "pid" in query_line, "the snapshot must select the pid column"
    assert "locktype = 'advisory'" in query_line


def test_analyzer_signature_requires_both_real_pids() -> None:
    """The analyzer must take ab_pid and abc_pid as required parameters."""
    tree = ast.parse(_helper_source())
    analyzer = _single_function_by_name(tree, "_analyze_advisory_rows")
    argument_names = [argument.arg for argument in analyzer.args.args]
    for required in ("ab_pid", "abc_pid"):
        assert required in argument_names, (
            f"the analyzer must require the {required} parameter"
        )


def test_impl_passes_both_published_pids_to_analyzer() -> None:
    """The impl must feed the published pids into the analyzer call."""
    tree = ast.parse(_helper_source())
    impl = _single_function_by_name(tree, "_run_c6_impl")
    analyzer_calls = [
        node
        for node in ast.walk(impl)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_analyze_advisory_rows"
    ]
    assert len(analyzer_calls) == 1, "the analyzer must be called exactly once"
    keywords = {keyword.arg: keyword.value for keyword in analyzer_calls[0].keywords}
    for expected_box, key in (("ab_pid", "ab_pid"), ("abc_pid", "pid")):
        value = keywords.get(expected_box)
        assert value is not None, f"missing analyzer keyword {expected_box}"
        assert isinstance(value, ast.Subscript), (
            f"the analyzer {expected_box} must come from the pid box"
        )
        assert isinstance(value.value, ast.Name) and value.value.id == "pid_box"
        assert isinstance(value.slice, ast.Constant) and value.slice.value == key


def test_ab_worker_publishes_pid_before_reconcile() -> None:
    """The AB worker must publish its real backend pid before reconcile."""
    tree = ast.parse(_helper_source())
    impl = _single_function_by_name(tree, "_run_c6_impl")
    ab_worker = next(
        node
        for node in ast.walk(impl)
        if isinstance(node, ast.FunctionDef) and node.name == "_ab_worker"
    )
    pid_read_lineno: int | None = None
    for node in ast.walk(ab_worker):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "execute"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and "pg_backend_pid" in node.args[0].value
        ):
            continue
        pid_read_lineno = node.lineno
        break
    assert pid_read_lineno is not None, (
        "the AB worker must read its real backend pid"
    )
    reconcile_lineno = next(
        node.lineno
        for node in ast.walk(ab_worker)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "reconcile"
    )
    assert pid_read_lineno < reconcile_lineno, (
        "the AB pid must be published before the real reconcile"
    )
    pid_stores = [
        node
        for node in ast.walk(ab_worker)
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Subscript)
        and isinstance(node.targets[0].value, ast.Name)
        and node.targets[0].value.id == "pid_box"
        and isinstance(node.targets[0].slice, ast.Constant)
        and node.targets[0].slice.value == "ab_pid"
    ]
    assert len(pid_stores) == 1, "the AB pid must be stored in the pid box once"


def test_abc_worker_publishes_pid_before_reconcile() -> None:
    """The ABC worker must publish its real backend pid before reconcile."""
    tree = ast.parse(_helper_source())
    impl = _single_function_by_name(tree, "_run_c6_impl")
    abc_worker = next(
        node
        for node in ast.walk(impl)
        if isinstance(node, ast.FunctionDef) and node.name == "_abc_worker"
    )
    pid_read_lineno: int | None = None
    for node in ast.walk(abc_worker):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "execute"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and "pg_backend_pid" in node.args[0].value
        ):
            continue
        pid_read_lineno = node.lineno
        break
    assert pid_read_lineno is not None, (
        "the ABC worker must read its real backend pid"
    )
    reconcile_lineno = next(
        node.lineno
        for node in ast.walk(abc_worker)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "reconcile"
    )
    assert pid_read_lineno < reconcile_lineno, (
        "the ABC pid must be published before the real reconcile"
    )
    pid_stores = [
        node
        for node in ast.walk(abc_worker)
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Subscript)
        and isinstance(node.targets[0].value, ast.Name)
        and node.targets[0].value.id == "pid_box"
        and isinstance(node.targets[0].slice, ast.Constant)
        and node.targets[0].slice.value == "pid"
    ]
    assert len(pid_stores) == 1, "the ABC pid must be stored in the pid box once"


def test_pids_never_leak_into_repr_or_reasons() -> None:
    """PIDs must never appear in reprs, observation fields, or reasons."""
    source = _helper_source()
    selector_source = (OKF_DIR / SELECTOR_FILENAME).read_text(encoding="utf-8")
    tree = ast.parse(source)
    observations = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "C6AdvisoryLockObservations"
    )
    repr_functions = [
        node
        for node in observations.body
        if isinstance(node, ast.FunctionDef) and node.name == "__repr__"
    ]
    assert len(repr_functions) == 1
    repr_segment = ast.get_source_segment(source, repr_functions[0])
    assert repr_segment is not None
    assert "pid" not in repr_segment, "the repr must never render pids"
    field_names = {
        node.target.id
        for node in observations.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    assert not any("pid" in name for name in field_names), (
        "no observation field may carry a pid"
    )
    for constant in ast.walk(tree):
        if not (
            isinstance(constant, ast.Constant)
            and isinstance(constant.value, str)
            and constant.value.startswith("c6_")
        ):
            continue
        assert not any(char.isdigit() for char in constant.value[3:]), (
            "error reasons must never embed numeric identifiers"
        )
    assert "pid_box" not in selector_source, (
        "the selector must never reference the pid box"
    )
