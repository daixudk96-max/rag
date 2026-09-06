"""Source proofs: the C6 readiness-gate non-regression contracts.

This collected (non-live) module pins the Task #88 Stage 4 C6
advisory-lock readiness-gate contracts: the gate is a single
monotone-deadline loop on the fresh attested observer connection that
probes ``pg_stat_activity`` for the real ABC backend pid
(``wait_event = 'advisory'``), never reads ``pg_locks``, never sleeps,
fails closed with a bounded diagnostic, and is followed by exactly one
``pg_locks`` evidence snapshot. The ABC worker must publish its backend
pid before reconcile blocks, and the finally path must join worker
threads only when they were actually started.

The production lock-order and key/seed semantics proofs live in the
companion module ``test_phase15_e2a_concurrency_production_lock_proof.py``.

Only file contents are parsed; nothing here touches a database or Docker.
"""

from __future__ import annotations

import ast
from pathlib import Path

OKF_DIR = Path(__file__).parent

_HELPER_PATH = OKF_DIR / "_phase15_e2a_task88_concurrency_cells.py"
_SELECTOR_PATH = OKF_DIR / "phase15_e2a_task88_live_concurrency.py"


def _helper_source() -> str:
    """Raw C6 helper source (the file must exist)."""
    return _HELPER_PATH.read_text(encoding="utf-8")


def _selector_source() -> str:
    """Raw C6 selector source (the file must exist)."""
    return _SELECTOR_PATH.read_text(encoding="utf-8")


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


# ---------------------------------------------------------------------------
# B) C6 readiness-gate non-regression contracts
# ---------------------------------------------------------------------------


def test_readiness_gate_is_bounded_and_never_repeats_pg_locks() -> None:
    """The gate is one monotone-deadline probe loop; one snapshot only."""
    source = _helper_source()
    tree = ast.parse(source)
    assert source.count("pg_locks") == 1, (
        "the helper must contain exactly one pg_locks evidence snapshot"
    )
    assert source.count("pg_stat_activity") >= 1

    gate = _single_function_by_name(tree, "_abc_reached_advisory_wait")
    segment = ast.get_source_segment(source, gate)
    assert segment is not None
    assert "pg_stat_activity" in segment
    assert "wait_event = 'advisory'" in segment, (
        "the gate must probe the advisory wait event specifically"
    )
    assert "pid = %s" in segment, "the gate must probe the real backend pid"
    assert "pg_locks" not in segment, "the gate must never read pg_locks"
    assert "time.sleep" not in segment, "the gate must never sleep"
    assert "sleep(" not in segment, "the gate must never call a sleep"
    assert "poll" not in segment, "the gate must never poll via a poll call"

    whiles = [node for node in ast.walk(gate) if isinstance(node, ast.While)]
    assert len(whiles) == 1, "the gate must contain exactly one bounded loop"
    test_names = {
        node.id for node in ast.walk(whiles[0].test) if isinstance(node, ast.Name)
    }
    assert "deadline" in test_names, "the loop bound must be the deadline"
    assert any(
        isinstance(node, ast.Attribute)
        and node.attr == "monotonic"
        and isinstance(node.value, ast.Name)
        and node.value.id == "time"
        for node in ast.walk(whiles[0].test)
    ), "the deadline must be a monotone time bound"
    returns = [node.value for node in ast.walk(gate) if isinstance(node, ast.Return)]
    assert any(isinstance(r, ast.Constant) and r.value is True for r in returns), (
        "the gate must return True when readiness is observed"
    )
    assert any(isinstance(r, ast.Constant) and r.value is False for r in returns), (
        "the gate must return False when the deadline expires"
    )
    assert len([node for node in ast.walk(tree) if isinstance(node, ast.While)]) == 1, (
        "the readiness gate must be the only loop in the helper"
    )

    impl = _single_function_by_name(tree, "_run_c6_impl")
    readiness_deadline_assigns = [
        node
        for node in ast.walk(impl)
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "readiness_deadline"
    ]
    assert len(readiness_deadline_assigns) == 1, (
        "the impl must read the readiness deadline exactly once"
    )
    rhs = readiness_deadline_assigns[0].value
    assert (
        isinstance(rhs, ast.Subscript)
        and isinstance(rhs.value, ast.Name)
        and rhs.value.id == "deadline_box"
        and isinstance(rhs.slice, ast.Constant)
        and rhs.slice.value == "readiness_deadline"
    ), "the readiness deadline must come from the hook-published box"

    gate_calls = [
        node
        for node in ast.walk(impl)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_abc_reached_advisory_wait"
    ]
    assert len(gate_calls) == 1, "the gate must be invoked exactly once"
    assert len(gate_calls[0].args) == 3
    assert (
        isinstance(gate_calls[0].args[2], ast.Name)
        and gate_calls[0].args[2].id == "readiness_deadline"
    ), "the gate must receive the readiness deadline"

    key_read_lineno: int | None = None
    oid_read_lineno: int | None = None
    for node in ast.walk(impl):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "execute"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            continue
        statement = node.args[0].value
        if "hashtextextended" in statement:
            key_read_lineno = node.lineno
        elif "pg_database" in statement:
            oid_read_lineno = node.lineno
    assert key_read_lineno is not None and oid_read_lineno is not None
    assert key_read_lineno < gate_calls[0].lineno, (
        "key recomputation must precede the readiness-success interval"
    )
    assert oid_read_lineno < gate_calls[0].lineno, (
        "the database oid read must precede the readiness-success interval"
    )

    snapshot_lineno: int | None = None
    for node in ast.walk(impl):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "execute"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
            and "FROM pg_locks" in node.args[0].value
        ):
            continue
        snapshot_lineno = node.lineno
    assert snapshot_lineno is not None, "the pg_locks evidence snapshot is required"
    assert snapshot_lineno > gate_calls[0].lineno, (
        "the single evidence snapshot must be taken only after the gate"
    )


def test_two_deadlines_published_by_hook_before_acquired_signal() -> None:
    """Two deadlines anchor at AB lock acquisition; hold = readiness + margin.

    The hook publishes deadline_box["readiness_deadline"] =
    time.monotonic() + _READINESS_DEADLINE_SECONDS and the later
    deadline_box["hold_deadline"] = readiness_deadline +
    _SNAPSHOT_MARGIN_SECONDS BEFORE locks_acquired_event.set(). The ABC
    pid wait and the readiness gate derive from the readiness deadline; the
    AB hook release wait derives from the hold deadline; the impl never
    computes an independent offset. A return to a single shared deadline
    fails this test.
    """
    source = _helper_source()
    tree = ast.parse(source)
    readiness_values: list[ast.expr] = []
    margin_values: list[ast.expr] = []
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "_READINESS_DEADLINE_SECONDS":
                readiness_values.append(node.value)
            elif node.target.id == "_SNAPSHOT_MARGIN_SECONDS":
                margin_values.append(node.value)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    if target.id == "_READINESS_DEADLINE_SECONDS":
                        readiness_values.append(node.value)
                    elif target.id == "_SNAPSHOT_MARGIN_SECONDS":
                        margin_values.append(node.value)
    assert len(readiness_values) == 1, (
        "_READINESS_DEADLINE_SECONDS must be defined exactly once"
    )
    assert len(margin_values) == 1, (
        "_SNAPSHOT_MARGIN_SECONDS must be defined exactly once"
    )
    for deadline_value in (*readiness_values, *margin_values):
        assert (
            isinstance(deadline_value, ast.Constant)
            and isinstance(deadline_value.value, (int, float))
            and deadline_value.value > 0
        ), "both deadline constants must be positive numeric constants"

    hook = _single_function_by_name(tree, "_hold_after_locks")
    hook_functions = [
        node
        for node in hook.body
        if isinstance(node, ast.FunctionDef) and node.name == "_hook"
    ]
    assert len(hook_functions) == 1, "the hook must define the inner _hook once"

    publish_nodes = [
        node
        for node in ast.walk(hook_functions[0])
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Subscript)
        and isinstance(node.targets[0].value, ast.Name)
        and node.targets[0].value.id == "deadline_box"
        and isinstance(node.targets[0].slice, ast.Constant)
        and node.targets[0].slice.value in {"readiness_deadline", "hold_deadline"}
    ]
    assert len(publish_nodes) == 2, (
        "the hook must publish both deadlines exactly once each"
    )
    publish_segments = {
        ast.get_source_segment(source, node) for node in publish_nodes
    }
    assert any(
        segment is not None
        and "time.monotonic() + _READINESS_DEADLINE_SECONDS" in segment
        for segment in publish_segments
    ), "the readiness deadline must be now plus the readiness budget"
    hold_segments = [
        segment
        for segment in publish_segments
        if segment is not None and "_SNAPSHOT_MARGIN_SECONDS" in segment
    ]
    assert len(hold_segments) == 1, (
        "the hold deadline must be readiness plus the snapshot margin"
    )
    assert "readiness_deadline" in hold_segments[0], (
        "the hold deadline must derive from the readiness deadline"
    )

    acquired_set = [
        node
        for node in ast.walk(hook_functions[0])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "set"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "locks_acquired_event"
    ]
    assert len(acquired_set) == 1
    assert max(node.lineno for node in publish_nodes) < acquired_set[0].lineno, (
        "both deadlines must be published before locks_acquired_event.set()"
    )

    release_waits = [
        node
        for node in ast.walk(hook_functions[0])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "wait"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "release_event"
    ]
    assert len(release_waits) == 1
    timeout_keywords = [
        keyword for keyword in release_waits[0].keywords if keyword.arg == "timeout"
    ]
    assert len(timeout_keywords) == 1
    remaining_call = timeout_keywords[0].value
    assert (
        isinstance(remaining_call, ast.Call)
        and isinstance(remaining_call.func, ast.Name)
        and remaining_call.func.id == "_remaining"
        and len(remaining_call.args) == 1
    ), "the hook release wait must derive from the remaining-time helper"
    deadline_arg = remaining_call.args[0]
    derives_from_hold = (
        isinstance(deadline_arg, ast.Name) and deadline_arg.id == "hold_deadline"
    ) or (
        isinstance(deadline_arg, ast.Subscript)
        and isinstance(deadline_arg.value, ast.Name)
        and deadline_arg.value.id == "deadline_box"
        and isinstance(deadline_arg.slice, ast.Constant)
        and deadline_arg.slice.value == "hold_deadline"
    )
    assert derives_from_hold, "the hook release wait must derive from the hold deadline"

    remaining = _single_function_by_name(tree, "_remaining")
    remaining_segment = ast.get_source_segment(source, remaining)
    assert remaining_segment is not None
    assert "max(0.0, deadline - time.monotonic())" in remaining_segment, (
        "the remaining-time helper must clamp to zero"
    )

    impl = _single_function_by_name(tree, "_run_c6_impl")
    impl_segment = ast.get_source_segment(source, impl)
    assert impl_segment is not None
    assert "time.monotonic() +" not in impl_segment, (
        "the impl must never compute an independent offset"
    )
    assert "_SNAPSHOT_MARGIN_SECONDS" not in impl_segment, (
        "the margin must be applied only in the hook publication"
    )
    readiness_assigns = [
        node
        for node in ast.walk(impl)
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "readiness_deadline"
    ]
    assert len(readiness_assigns) == 1, (
        "the impl must read the readiness deadline exactly once"
    )
    rhs = readiness_assigns[0].value
    assert (
        isinstance(rhs, ast.Subscript)
        and isinstance(rhs.value, ast.Name)
        and rhs.value.id == "deadline_box"
        and isinstance(rhs.slice, ast.Constant)
        and rhs.slice.value == "readiness_deadline"
    ), "the readiness deadline must come from the hook-published box"

    pid_waits = [
        node
        for node in ast.walk(impl)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "wait"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "abc_pid_event"
    ]
    assert len(pid_waits) == 1, "the ABC pid wait must exist once"
    pid_timeout_keywords = [
        keyword for keyword in pid_waits[0].keywords if keyword.arg == "timeout"
    ]
    assert len(pid_timeout_keywords) == 1
    assert (
        isinstance(pid_timeout_keywords[0].value, ast.Call)
        and isinstance(pid_timeout_keywords[0].value.func, ast.Name)
        and pid_timeout_keywords[0].value.func.id == "_remaining"
        and isinstance(pid_timeout_keywords[0].value.args[0], ast.Name)
        and pid_timeout_keywords[0].value.args[0].id == "readiness_deadline"
    ), "the ABC pid wait must derive from the readiness deadline"


def test_readiness_gate_identifies_abc_backend_before_reconcile() -> None:
    """The ABC worker publishes its real backend pid before reconcile."""
    source = _helper_source()
    tree = ast.parse(source)
    impl = _single_function_by_name(tree, "_run_c6_impl")
    worker = next(
        node
        for node in ast.walk(impl)
        if isinstance(node, ast.FunctionDef) and node.name == "_abc_worker"
    )

    pid_lineno: int | None = None
    for node in ast.walk(worker):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "execute"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and "pg_backend_pid" in node.args[0].value
        ):
            continue
        pid_lineno = node.lineno
        break
    assert pid_lineno is not None, "the ABC worker must read its real backend pid"

    reconcile_lineno: int | None = None
    for node in ast.walk(worker):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "reconcile"
        ):
            reconcile_lineno = node.lineno
            break
    assert reconcile_lineno is not None, "the ABC worker must run reconcile"
    assert pid_lineno < reconcile_lineno, (
        "the backend pid must be published before reconcile blocks"
    )

    pid_cursor_assigns = [
        node
        for node in ast.walk(worker)
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "pid_cursor"
        and isinstance(node.value, ast.Call)
    ]
    assert len(pid_cursor_assigns) == 1
    pid_cursor_rhs = pid_cursor_assigns[0].value
    assert (
        isinstance(pid_cursor_rhs, ast.Call)
        and isinstance(pid_cursor_rhs.func, ast.Attribute)
        and pid_cursor_rhs.func.attr == "cursor"
        and isinstance(pid_cursor_rhs.func.value, ast.Name)
        and pid_cursor_rhs.func.value.id == "abc_primary_conn"
    ), "the pid must come from the ABC fresh attested primary"

    set_lineno = next(
        node.lineno
        for node in ast.walk(worker)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "set"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "abc_pid_event"
    )
    assert pid_lineno < set_lineno < reconcile_lineno, (
        "the pid event must be set after the pid read and before reconcile"
    )

    pid_waits = [
        node
        for node in ast.walk(impl)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "wait"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "abc_pid_event"
    ]
    assert len(pid_waits) == 1, "the main frame must wait for the abc pid event"
    assert len([k for k in pid_waits[0].keywords if k.arg == "timeout"]) == 1, (
        "the pid wait must carry a bounded timeout"
    )

    gate_call = next(
        node
        for node in ast.walk(impl)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_abc_reached_advisory_wait"
    )
    assert isinstance(gate_call.args[1], ast.Subscript), (
        "the gate must receive the published backend pid"
    )


def test_readiness_gate_fails_closed_with_bounded_diagnostic() -> None:
    """Readiness timeouts must fail the cell with a bounded reason."""
    source = _helper_source()
    tree = ast.parse(source)
    impl = _single_function_by_name(tree, "_run_c6_impl")
    assert "c6_abc_pid_timeout" in source
    assert "c6_abc_readiness_timeout" in source

    guarded = [
        node
        for node in ast.walk(impl)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.UnaryOp)
        and isinstance(node.test.op, ast.Not)
        and isinstance(node.test.operand, ast.Call)
        and isinstance(node.test.operand.func, ast.Name)
        and node.test.operand.func.id == "_abc_reached_advisory_wait"
    ]
    assert len(guarded) == 1, "the gate result must be checked with fail closed"

    def _fail_closed_reason(branch: ast.If) -> ast.Constant | None:
        returns = [
            node for node in ast.walk(branch) if isinstance(node, ast.Return)
        ]
        assert len(returns) == 1, "the fail-closed branch must return once"
        call = returns[0].value
        assert (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "C6AdvisoryLockObservations"
        ), "the fail-closed branch must return redacted observations"
        error_keywords = [k for k in call.keywords if k.arg == "error_reason"]
        assert len(error_keywords) == 1, "the failure must carry an error_reason"
        reason_call = error_keywords[0].value
        assert (
            isinstance(reason_call, ast.Call)
            and isinstance(reason_call.func, ast.Name)
            and reason_call.func.id == "_error_reason"
        ), "the diagnostic must come from the bounded trusted seam"
        for argument in ast.walk(reason_call):
            if (
                isinstance(argument, ast.Constant)
                and isinstance(argument.value, str)
            ):
                return argument
        return None

    readiness_reason = _fail_closed_reason(guarded[0])
    assert readiness_reason is not None and readiness_reason.value == (
        "c6_abc_readiness_timeout"
    ), "readiness expiry must fail closed with the bounded diagnostic"

    pid_guarded = [
        node
        for node in ast.walk(impl)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.UnaryOp)
        and isinstance(node.test.op, ast.Not)
        and isinstance(node.test.operand, ast.Call)
        and isinstance(node.test.operand.func, ast.Attribute)
        and node.test.operand.func.attr == "wait"
        and isinstance(node.test.operand.func.value, ast.Name)
        and node.test.operand.func.value.id == "abc_pid_event"
    ]
    assert len(pid_guarded) == 1, "the pid wait must be checked with fail closed"
    pid_reason = _fail_closed_reason(pid_guarded[0])
    assert pid_reason is not None and pid_reason.value == "c6_abc_pid_timeout", (
        "a pid timeout must fail closed with the bounded diagnostic"
    )


def _join_calls_with_guards(
    module_tree: ast.Module,
) -> list[tuple[str, tuple[frozenset[str], ...]]]:
    """Yield (joined_thread_name, enclosing guard name sets) for join calls."""
    found: list[tuple[str, tuple[frozenset[str], ...]]] = []

    def visit(body: list[ast.stmt], guards: tuple[frozenset[str], ...]) -> None:
        for statement in body:
            if isinstance(statement, ast.If):
                guard_names = frozenset(
                    node.id
                    for node in ast.walk(statement.test)
                    if isinstance(node, ast.Name)
                )
                child_guards = guards + (guard_names,)
                visit(statement.body, child_guards)
                visit(statement.orelse, child_guards)
            elif isinstance(statement, ast.Try):
                visit(statement.body, guards)
                for handler in statement.handlers:
                    visit(handler.body, guards)
                visit(statement.orelse, guards)
                visit(statement.finalbody, guards)
            elif isinstance(statement, (ast.For, ast.While)):
                visit(statement.body, guards)
                visit(statement.orelse, guards)
            elif isinstance(statement, ast.With):
                visit(statement.body, guards)
            else:
                for node in ast.walk(statement):
                    if (
                        isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "join"
                        and isinstance(node.func.value, ast.Name)
                    ):
                        found.append((node.func.value.id, guards))

    visit(module_tree.body, ())
    return found


def test_finally_joins_only_started_threads() -> None:
    """The finally path must join workers only when actually started."""
    tree = ast.parse(_helper_source())
    impl = _single_function_by_name(tree, "_run_c6_impl")
    final_tries = [
        node for node in ast.walk(impl) if isinstance(node, ast.Try) and node.finalbody
    ]
    assert final_tries, "the impl must carry a finally path"
    finalbody_tree = ast.Module(
        body=list(final_tries[0].finalbody), type_ignores=[]
    )
    joins = _join_calls_with_guards(finalbody_tree)
    assert len(joins) >= 2, "both worker threads must be joined in the finally path"
    for thread_name, guards in joins:
        assert guards, f"the join of {thread_name} must be guarded"
        nearest = guards[-1]
        flag_name = thread_name.removesuffix("_thread") + "_started"
        assert flag_name in nearest, (
            f"the join of {thread_name} must be guarded by {flag_name}"
        )
        assert thread_name in nearest, (
            f"the guard must also reference the thread {thread_name}"
        )

    for thread_name in ("ab_thread", "abc_thread"):
        flag_name = thread_name.removesuffix("_thread") + "_started"
        flag_assigns = [
            node
            for node in ast.walk(impl)
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == flag_name
            and isinstance(node.value, ast.Constant)
            and node.value.value is True
        ]
        assert len(flag_assigns) == 1, f"{flag_name} must be set True exactly once"
        start_calls = [
            node
            for node in ast.walk(impl)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "start"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == thread_name
        ]
        assert len(start_calls) == 1
        assert start_calls[0].lineno < flag_assigns[0].lineno, (
            f"{flag_name} must be set right after {thread_name}.start()"
        )


def test_helper_uses_monotonic_deadline_and_never_sleep() -> None:
    """The only time usage is the monotonic deadline; sleep never appears."""
    helper_source = _helper_source()
    selector_source = _selector_source()
    helper_tree = ast.parse(helper_source)
    selector_tree = ast.parse(selector_source)

    time_imports = [
        node
        for node in helper_tree.body
        if isinstance(node, ast.Import)
        and any(alias.name == "time" for alias in node.names)
    ]
    assert len(time_imports) == 1, "the helper must import time exactly once"
    assert not any(
        isinstance(node, ast.Import)
        and any(alias.name == "time" for alias in node.names)
        for node in selector_tree.body
    ), "the selector must not import time"

    for node in ast.walk(helper_tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "time"
        ):
            assert node.attr == "monotonic", (
                f"the only permitted time usage is monotonic: time.{node.attr}"
            )
    assert "time.monotonic()" in helper_source
    assert "time.monotonic() < deadline" in helper_source
    assert "time.monotonic() + _READINESS_DEADLINE_SECONDS" in helper_source
    assert "_SNAPSHOT_MARGIN_SECONDS" in helper_source
    assert "time.sleep" not in helper_source
    assert "time.sleep" not in selector_source
    assert "sleep(" not in helper_source
    assert "sleep(" not in selector_source
