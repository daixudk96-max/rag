"""Source proofs: production advisory-lock order and key/seed semantics.

This collected (non-live) module pins the exact production semantics the
Task #88 Stage 4 C6 advisory-lock concurrency assertion depends on
(database review): ``llamaindex_runtime/okf/e2a_reconciler.py`` must

- acquire the whole-corpus advisory lock before any per-parent advisory
  lock, exactly once,
- build parent keys from the exact
  ``okf:e2a:parent:<document_id>:<version_id>`` f-string over parents
  sorted by (document_id, version_id),
- take parent row ``FOR UPDATE`` locks only after all advisory locks and
  the manual fact-table locks (module constant) last,
- fire ``post_lock_sync_hook`` only after ``_acquire_scope_locks``
  returns,
- use ONLY the exclusive transaction-scoped ``pg_advisory_xact_lock``
  (never shared/session/try variants), with exactly one
  ``hashtextextended`` argument, the fixed zero seed, and a single-element
  parameter tuple per lock statement.

The C6 observer key recomputation must use identical key strings and
seed. Only file contents are parsed; nothing here touches a database or
Docker.
"""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
OKF_DIR = Path(__file__).parent

_PRODUCTION_PATH = PROJECT_ROOT / "llamaindex_runtime" / "okf" / "e2a_reconciler.py"
_HELPER_PATH = OKF_DIR / "_phase15_e2a_task88_concurrency_cells.py"


def _production_source() -> str:
    """Raw production reconciler source (the file must exist)."""
    return _PRODUCTION_PATH.read_text(encoding="utf-8")


def _helper_source() -> str:
    """Raw C6 helper source (the file must exist)."""
    return _HELPER_PATH.read_text(encoding="utf-8")


def _acquire_scope_locks(tree: ast.Module) -> ast.FunctionDef:
    """Return the production scope-lock method (unique name in the file)."""
    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "_acquire_scope_locks"
    ]
    assert len(functions) == 1, "_acquire_scope_locks must exist exactly once"
    return functions[0]


def _reconciler_reconcile(tree: ast.Module) -> ast.FunctionDef:
    """Return the real E2aReconciler.reconcile (the one calling the locks)."""
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "reconcile"
        and any(
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "_acquire_scope_locks"
            for call in ast.walk(node)
        )
    ]
    assert len(matches) == 1, "E2aReconciler.reconcile must exist exactly once"
    return matches[0]


def _advisory_lock_execute_calls(
    function: ast.FunctionDef,
) -> list[tuple[int, bool]]:
    """Collect (lineno, is_whole_corpus) for each scope advisory lock."""
    found: list[tuple[int, bool]] = []
    for node in ast.walk(function):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "execute"
            and len(node.args) >= 2
        ):
            continue
        statement = node.args[0]
        if not (
            isinstance(statement, ast.Constant)
            and isinstance(statement.value, str)
            and "pg_advisory_xact_lock" in statement.value
        ):
            continue
        is_whole = any(
            isinstance(c, ast.Constant) and c.value == "okf:e2a:whole-corpus"
            for c in ast.walk(node.args[1])
        )
        found.append((node.lineno, is_whole))
    return found


def test_production_acquires_whole_corpus_advisory_lock_first() -> None:
    """The whole-corpus advisory lock must be the first scope lock."""
    calls = _advisory_lock_execute_calls(
        _acquire_scope_locks(ast.parse(_production_source()))
    )
    assert len(calls) >= 2, (
        "both the whole-corpus and at least one per-parent lock are required"
    )
    assert calls[0][1], "the whole-corpus advisory lock must be acquired first"
    assert calls[0][0] < calls[1][0], (
        "the whole-corpus lock must precede every per-parent lock"
    )
    assert sum(1 for _, whole in calls if whole) == 1, (
        "exactly one whole-corpus advisory lock is required"
    )
    assert all(not whole for _, whole in calls[1:]), (
        "no second whole-corpus advisory lock may exist"
    )


def test_production_parent_keys_use_document_and_version_identity() -> None:
    """Parent keys must be sorted (document_id, version_id) f-strings."""
    source = _production_source()
    acquire = _acquire_scope_locks(ast.parse(source))
    sorted_calls = [
        node
        for node in ast.walk(acquire)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "sorted"
    ]
    assert len(sorted_calls) == 1, "the parents must be sorted exactly once"
    key_keywords = [
        keyword for keyword in sorted_calls[0].keywords if keyword.arg == "key"
    ]
    assert len(key_keywords) == 1, "the sort must carry an explicit key"
    key_segment = ast.get_source_segment(source, key_keywords[0].value)
    assert key_segment is not None
    assert "document_id" in key_segment and "version_id" in key_segment, (
        "the sort key must use document_id and version_id"
    )

    joined = [
        node
        for node in ast.walk(acquire)
        if isinstance(node, ast.JoinedStr)
        and any(
            isinstance(value, ast.Constant) and value.value == "okf:e2a:parent:"
            for value in node.values
        )
    ]
    assert len(joined) == 1, "the parent lock key must be the single f-string"
    values = joined[0].values
    assert len(values) == 4, "the parent key must be prefix, id, colon, version"
    assert (
        isinstance(values[0], ast.Constant) and values[0].value == "okf:e2a:parent:"
    )
    assert (
        isinstance(values[1], ast.FormattedValue)
        and isinstance(values[1].value, ast.Attribute)
        and values[1].value.attr == "document_id"
    )
    assert isinstance(values[2], ast.Constant) and values[2].value == ":"
    assert (
        isinstance(values[3], ast.FormattedValue)
        and isinstance(values[3].value, ast.Attribute)
        and values[3].value.attr == "version_id"
    )


def test_production_lock_order_advisory_then_rows_then_tables() -> None:
    """Row FOR UPDATE locks and table locks must follow all advisory locks."""
    acquire = _acquire_scope_locks(ast.parse(_production_source()))
    calls = _advisory_lock_execute_calls(acquire)
    last_advisory = max(line for line, _ in calls)
    row_lock_lineno: int | None = None
    for node in ast.walk(acquire):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "execute"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
            and "FOR UPDATE" in node.args[0].value
        ):
            continue
        row_lock_lineno = node.lineno
        break
    assert row_lock_lineno is not None, "the parent row FOR UPDATE lock is required"
    table_lock_fors = [
        node
        for node in ast.walk(acquire)
        if isinstance(node, ast.For)
        and isinstance(node.iter, ast.Name)
        and node.iter.id == "_MANUAL_FACT_TABLE_LOCKS"
    ]
    assert len(table_lock_fors) == 1, (
        "the manual fact table locks must be executed via the module constant"
    )
    assert last_advisory < row_lock_lineno, (
        "row locks must be taken only after every advisory lock"
    )
    assert row_lock_lineno < table_lock_fors[0].lineno, (
        "the manual fact table locks must be taken last"
    )


def test_production_post_lock_hook_fires_after_scope_locks() -> None:
    """The hook must be invoked only after the scope locks are acquired."""
    reconcile = _reconciler_reconcile(ast.parse(_production_source()))
    acquire_calls = [
        node
        for node in ast.walk(reconcile)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_acquire_scope_locks"
    ]
    hook_calls = [
        node
        for node in ast.walk(reconcile)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_post_lock_sync_hook"
    ]
    assert len(acquire_calls) == 1, "_acquire_scope_locks must be called once"
    assert len(hook_calls) == 1, "the post-lock hook must be called once"
    assert acquire_calls[0].lineno < hook_calls[0].lineno, (
        "the hook must fire strictly after the scope locks are acquired"
    )


def test_production_uses_only_transaction_scoped_advisory_locks() -> None:
    """Only pg_advisory_xact_lock, one key, fixed zero seed, one parameter."""
    source = _production_source()
    tree = ast.parse(source)
    assert "pg_advisory_xact_lock" in source
    for variant in (
        "pg_advisory_xact_lock_shared",
        "pg_advisory_lock",
        "pg_advisory_lock_shared",
        "pg_try_advisory_xact_lock",
        "pg_try_advisory_lock",
    ):
        assert variant not in source, f"forbidden lock variant {variant!r}"
    assert "hashtextextended(%s, 0)" in source
    assert "hashtextextended(%s, %s)" not in source, (
        "the key hash must take exactly one argument with the zero seed"
    )
    acquire = _acquire_scope_locks(tree)
    for node in ast.walk(acquire):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "execute"
            and len(node.args) >= 2
        ):
            continue
        statement = node.args[0]
        if not (
            isinstance(statement, ast.Constant)
            and isinstance(statement.value, str)
            and "pg_advisory_xact_lock" in statement.value
        ):
            continue
        assert statement.value.count("hashtextextended") == 1, (
            "each advisory lock must hash exactly one key"
        )
        assert statement.value.count("%s") == 1, (
            "each advisory lock must take exactly one parameter"
        )
        params = node.args[1]
        assert isinstance(params, ast.Tuple) and len(params.elts) == 1, (
            "each advisory lock must pass a single-element parameter tuple"
        )


def test_c6_observer_key_and_seed_semantics_match_production() -> None:
    """The C6 observer must recompute keys with production's exact values."""
    production = _production_source()
    helper = _helper_source()
    assert '"okf:e2a:whole-corpus"' in production
    assert "okf:e2a:parent:" in production
    assert "hashtextextended(%s, 0)" in production
    assert "hashtextextended('okf:e2a:whole-corpus', 0)" in helper
    assert "hashtextextended(%s, 0)" in helper
