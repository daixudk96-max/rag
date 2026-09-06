"""Unit tests for lifecycle envelope, cleanup outcomes, and type invariants.

Task #87: RED-first tests for exact-name proof, cleanup outcomes, invariants.
"""

# ruff: noqa: F811

from __future__ import annotations

import subprocess
from collections.abc import Callable
from types import MappingProxyType
from unittest.mock import MagicMock

import pytest

from ._real_e2a_reconciler_lifecycle import (
    _EXPECTED_DATABASE,
    _remove_owned_container,
)


def _make_completed(rc: int, stdout: str = "", stderr: str = "") -> MagicMock:
    """Build a MagicMockCompletedProcess with exact int returncode."""
    result = MagicMock(spec=subprocess.CompletedProcess)
    result.returncode = rc
    result.stdout = stdout
    result.stderr = stderr
    return result


# =============================================================================
# Exact-name listing tests for _remove_owned_container
# =============================================================================


def test_remove_owned_container_confirmed_absent_exact_name() -> None:
    """Container never existed: exact-name listing returns empty, rc=0."""

    def fake_run(command, **_kwargs):
        # docker container ls --filter name=^container$ --format {{.Names}}
        if command[0] == "container" and command[1] == "ls":
            return _make_completed(0, stdout="")  # Empty = absent
        return _make_completed(0)

    result = _remove_owned_container("missing-container", run=fake_run)
    assert result.outcome == "confirmed_absent"
    assert result.confirmed is True
    assert result.stage == "inspect"
    assert result.inspect_rc == 0
    assert result.remove_rc is None


def test_remove_owned_container_confirmed_absent_rejects_substring_trick() -> None:
    """If output contains 'no such container' but exact-name query shows container exists,
    must NOT return confirmed_absent.

    This is the adversarial test: Docker stderr says 'no such container' but
    exact-name listing shows container exists. Must fail closed.
    """

    def fake_run(command, **_kwargs):
        if command[0] == "container" and command[1] == "ls":
            # Exact-name query shows container EXISTS (adversarial)
            return _make_completed(0, stdout="missing-container")
        # Other commands might say 'no such container' but we ignore them
        return _make_completed(1, stderr="Error: No such container")

    result = _remove_owned_container("missing-container", run=fake_run)
    # Must NOT be confirmed_absent - container exists!
    assert result.outcome != "confirmed_absent"


def test_remove_owned_container_list_daemon_failure() -> None:
    """Docker daemon failure during listing: inspection_failure."""

    def fake_run(command, **_kwargs):
        if command[0] == "container" and command[1] == "ls":
            return _make_completed(1, stderr="Cannot connect to Docker daemon")
        return _make_completed(0)

    result = _remove_owned_container("daemon-error", run=fake_run)
    assert result.outcome == "inspection_failure"
    assert result.confirmed is False
    assert result.stage == "inspect"
    assert result.inspect_rc == 1


def test_remove_owned_container_runner_exception_during_list() -> None:
    """Runner raises during list: inspection_failure with inspect_rc=-1."""

    def fake_run(command, **_kwargs):
        if command[0] == "container" and command[1] == "ls":
            raise OSError("connection reset")
        return _make_completed(0)

    result = _remove_owned_container("exc-list", run=fake_run)
    assert result.outcome == "inspection_failure"
    assert result.confirmed is False
    assert result.stage == "inspect"
    assert result.inspect_rc == -1


def test_remove_owned_container_unowned_label() -> None:
    """Container exists but label doesn't match: unowned_label, never delete."""
    listed = [False]

    def fake_run(command, **_kwargs):
        if command[0] == "container" and command[1] == "ls":
            listed[0] = True
            return _make_completed(0, stdout="test-container")  # Exists
        if command[0] == "inspect":
            # Label check - returns wrong label
            return _make_completed(0, stdout="wrong-label")
        return _make_completed(0)

    result = _remove_owned_container("test-container", run=fake_run)
    assert result.outcome == "unowned_label"
    assert result.confirmed is False
    assert result.stage == "inspect"
    assert result.inspect_rc == 0


def test_remove_owned_container_confirmed_removed() -> None:
    """Container exists, owned, removed, post-removal listing empty."""
    phase = ["list1"]

    def fake_run(command, **_kwargs):
        if command[0] == "container" and command[1] == "ls":
            if phase[0] == "list1":
                # Initial: container exists
                return _make_completed(0, stdout="test-container")
            else:
                # Post-removal: empty
                return _make_completed(0, stdout="")
        if command[0] == "inspect":
            return _make_completed(0, stdout="87.real.e2a.acceptance")
        if command[0] == "rm":
            phase[0] = "list2"
            return _make_completed(0)
        return _make_completed(0)

    result = _remove_owned_container("test-container", run=fake_run)
    assert result.outcome == "confirmed_removed"
    assert result.confirmed is True
    assert result.stage == "confirm"
    assert result.inspect_rc == 0
    assert result.remove_rc == 0


def test_remove_owned_container_removal_failure() -> None:
    """Remove command fails: removal_failure."""

    def fake_run(command, **_kwargs):
        if command[0] == "container" and command[1] == "ls":
            return _make_completed(0, stdout="remove-fails")
        if command[0] == "inspect":
            return _make_completed(0, stdout="87.real.e2a.acceptance")
        if command[0] == "rm":
            return _make_completed(1, stderr="device busy")
        return _make_completed(0)

    result = _remove_owned_container("remove-fails", run=fake_run)
    assert result.outcome == "removal_failure"
    assert result.confirmed is False
    assert result.stage == "remove"
    assert result.inspect_rc == 0
    assert result.remove_rc == 1


def test_remove_owned_container_post_removal_still_exists() -> None:
    """Container still exists after rm: confirmation_failure."""

    def fake_run(command, **_kwargs):
        if command[0] == "container" and command[1] == "ls":
            # Both initial and post-removal show container exists
            return _make_completed(0, stdout="stubborn-container")
        if command[0] == "inspect":
            return _make_completed(0, stdout="87.real.e2a.acceptance")
        if command[0] == "rm":
            return _make_completed(0)
        return _make_completed(0)

    result = _remove_owned_container("stubborn-container", run=fake_run)
    assert result.outcome == "post_removal_confirmation_failure"
    assert result.confirmed is False
    assert result.stage == "confirm"


def test_remove_owned_container_post_removal_daemon_failure() -> None:
    """Daemon failure during post-removal listing: confirmation_failure."""
    phase = ["list1"]

    def fake_run(command, **_kwargs):
        if command[0] == "container" and command[1] == "ls":
            if phase[0] == "list1":
                phase[0] = "list2"
                return _make_completed(0, stdout="daemon-confirm")
            else:
                # Post-removal daemon failure
                return _make_completed(1, stderr="daemon error")
        if command[0] == "inspect":
            return _make_completed(0, stdout="87.real.e2a.acceptance")
        if command[0] == "rm":
            return _make_completed(0)
        return _make_completed(0)

    result = _remove_owned_container("daemon-confirm", run=fake_run)
    assert result.outcome == "post_removal_confirmation_failure"
    assert result.confirmed is False


# =============================================================================
# Returncode validation tests
# =============================================================================


def test_validate_exact_returncode_accepts_int() -> None:
    """Exact int returncode passes validation."""
    from ._real_e2a_reconciler_lifecycle import _validate_exact_returncode

    assert _validate_exact_returncode(0) == 0
    assert _validate_exact_returncode(1) == 1
    assert _validate_exact_returncode(-1) == -1


def test_validate_exact_returncode_rejects_bool() -> None:
    """bool is rejected, returns -1 sentinel."""
    from ._real_e2a_reconciler_lifecycle import _validate_exact_returncode

    assert _validate_exact_returncode(True) == -1
    assert _validate_exact_returncode(False) == -1


def test_validate_exact_returncode_rejects_int_subclass() -> None:
    """int subclass is rejected, returns -1 sentinel."""

    class MyInt(int):
        pass

    from ._real_e2a_reconciler_lifecycle import _validate_exact_returncode

    assert _validate_exact_returncode(MyInt(5)) == -1


# =============================================================================
# ContainerCleanupResult invariant tests
# =============================================================================


def test_container_cleanup_result_rejects_bool_inspect_rc() -> None:
    """bool is not accepted as int for inspect_rc."""
    from ._real_e2a_reconciler_types import ContainerCleanupResult

    with pytest.raises(ValueError, match="exact built-in int"):
        ContainerCleanupResult(
            outcome="inspection_failure",
            stage="inspect",
            confirmed=False,
            inspect_rc=True,  # type: ignore[arg-type]
        )


def test_container_cleanup_result_rejects_bool_remove_rc() -> None:
    """bool is not accepted as int for remove_rc."""
    from ._real_e2a_reconciler_types import ContainerCleanupResult

    with pytest.raises(ValueError, match="exact built-in int"):
        ContainerCleanupResult(
            outcome="removal_failure",
            stage="remove",
            confirmed=False,
            inspect_rc=0,
            remove_rc=False,  # type: ignore[arg-type]
        )


def test_container_cleanup_result_confirmed_removed_invariants() -> None:
    """confirmed_removed requires stage=confirm, confirmed=True, both rc=0."""
    from ._real_e2a_reconciler_types import ContainerCleanupResult

    # Valid
    r = ContainerCleanupResult(
        outcome="confirmed_removed",
        stage="confirm",
        confirmed=True,
        inspect_rc=0,
        remove_rc=0,
    )
    assert r.outcome == "confirmed_removed"

    # Wrong stage
    with pytest.raises(ValueError, match="not valid for stage"):
        ContainerCleanupResult(
            outcome="confirmed_removed",
            stage="inspect",
            confirmed=True,
            inspect_rc=0,
            remove_rc=0,
        )


def test_container_cleanup_result_confirmed_absent_invariants() -> None:
    """confirmed_absent requires stage=inspect, confirmed=True, exact int inspect_rc."""
    from ._real_e2a_reconciler_types import ContainerCleanupResult

    # Valid with rc=0 (successful query, empty result)
    r = ContainerCleanupResult(
        outcome="confirmed_absent",
        stage="inspect",
        confirmed=True,
        inspect_rc=0,
    )
    assert r.outcome == "confirmed_absent"

    # Must have inspect_rc
    with pytest.raises(ValueError, match="requires inspect_rc"):
        ContainerCleanupResult(
            outcome="confirmed_absent",
            stage="inspect",
            confirmed=True,
            inspect_rc=None,
        )

    # Must not have remove_rc
    with pytest.raises(ValueError, match="must not have remove_rc"):
        ContainerCleanupResult(
            outcome="confirmed_absent",
            stage="inspect",
            confirmed=True,
            inspect_rc=0,
            remove_rc=0,
        )

    # RED cases: inspect_rc must be exactly 0 (reject 1, -1, bool, int subclass)
    with pytest.raises(ValueError, match="confirmed_absent requires inspect_rc=0"):
        ContainerCleanupResult(
            outcome="confirmed_absent",
            stage="inspect",
            confirmed=True,
            inspect_rc=1,
        )

    with pytest.raises(ValueError, match="confirmed_absent requires inspect_rc=0"):
        ContainerCleanupResult(
            outcome="confirmed_absent",
            stage="inspect",
            confirmed=True,
            inspect_rc=-1,
        )

    with pytest.raises(ValueError, match="inspect_rc must be exact built-in int"):
        ContainerCleanupResult(
            outcome="confirmed_absent",
            stage="inspect",
            confirmed=True,
            inspect_rc=True,  # type: ignore[arg-type]
        )

    class IntSubclass(int):
        pass

    with pytest.raises(ValueError, match="inspect_rc must be exact built-in int"):
        ContainerCleanupResult(
            outcome="confirmed_absent",
            stage="inspect",
            confirmed=True,
            inspect_rc=IntSubclass(0),  # type: ignore[arg-type]
        )


def test_container_cleanup_result_unowned_label_invariants() -> None:
    """unowned_label requires stage=inspect, confirmed=False, inspect_rc=0."""
    from ._real_e2a_reconciler_types import ContainerCleanupResult

    r = ContainerCleanupResult(
        outcome="unowned_label",
        stage="inspect",
        confirmed=False,
        inspect_rc=0,
    )
    assert r.outcome == "unowned_label"


def test_container_cleanup_result_removal_failure_invariants() -> None:
    """removal_failure requires stage=remove, confirmed=False, exact int remove_rc."""
    from ._real_e2a_reconciler_types import ContainerCleanupResult

    r = ContainerCleanupResult(
        outcome="removal_failure",
        stage="remove",
        confirmed=False,
        inspect_rc=0,
        remove_rc=1,
    )
    assert r.outcome == "removal_failure"


def test_container_cleanup_result_post_removal_failure_invariants() -> None:
    """post_removal_confirmation_failure requires stage=confirm, both rc=0."""
    from ._real_e2a_reconciler_types import ContainerCleanupResult

    r = ContainerCleanupResult(
        outcome="post_removal_confirmation_failure",
        stage="confirm",
        confirmed=False,
        inspect_rc=0,
        remove_rc=0,
    )
    assert r.outcome == "post_removal_confirmation_failure"


def test_container_cleanup_result_is_frozen() -> None:
    """Frozen dataclass cannot be mutated."""
    from ._real_e2a_reconciler_types import ContainerCleanupResult

    r = ContainerCleanupResult(
        outcome="unowned_label",
        stage="inspect",
        confirmed=False,
        inspect_rc=0,
    )
    with pytest.raises(Exception):
        r.outcome = "confirmed_removed"  # type: ignore[misc]


# =============================================================================
# ScopeSnapshot defensive-copy tests
# =============================================================================


def test_scope_snapshot_defensive_copy_mutation() -> None:
    """Mutating original dicts after construction does NOT affect snapshot."""
    from ._real_e2a_reconciler_types import make_scope_snapshot

    original_counts: dict[str, int] = {"t1": 5}
    original_digests: dict[str, str] = {"t1": "abc123"}
    original_denylist: dict[str, int | None] = {"t1": 0}

    snapshot = make_scope_snapshot(
        counts=original_counts,
        digests=original_digests,
        denylist=original_denylist,
        sync_ts="2026-07-27T00:00:00Z",
    )

    # Mutate originals
    original_counts["t1"] = 999
    original_counts["t2"] = 100
    original_digests["t1"] = "mutated"
    original_denylist["t1"] = None

    # Snapshot should be unchanged
    assert snapshot.counts["t1"] == 5
    assert "t2" not in snapshot.counts
    assert snapshot.digests["t1"] == "abc123"
    assert snapshot.denylist["t1"] == 0


def test_scope_snapshot_defensive_copy_from_mapping_proxy() -> None:
    """Even when constructed with MappingProxyType, creates fresh copy."""
    from ._real_e2a_reconciler_types import ScopeSnapshot

    # Create a mutable dict, wrap it, then pass to ScopeSnapshot
    original = {"t1": 5}
    wrapped = MappingProxyType(original)

    snapshot = ScopeSnapshot(
        counts=wrapped,
        digests=MappingProxyType({}),
        denylist=MappingProxyType({}),
        sync_ts=None,
    )

    # Mutate original
    original["t1"] = 999
    original["t2"] = 100

    # Snapshot should be unchanged (defensive copy in __post_init__)
    assert snapshot.counts["t1"] == 5
    assert "t2" not in snapshot.counts


def test_scope_snapshot_rejects_bool_count() -> None:
    """bool is not accepted as int for counts."""
    from ._real_e2a_reconciler_types import ScopeSnapshot

    with pytest.raises(ValueError, match="exact built-in int"):
        ScopeSnapshot(
            counts=MappingProxyType({"t": True}),  # type: ignore[arg-type]
            digests=MappingProxyType({}),
            denylist=MappingProxyType({}),
            sync_ts=None,
        )


def test_scope_snapshot_rejects_negative_count() -> None:
    """Negative count values are rejected."""
    from ._real_e2a_reconciler_types import ScopeSnapshot

    with pytest.raises(ValueError, match="nonnegative"):
        ScopeSnapshot(
            counts=MappingProxyType({"t": -1}),
            digests=MappingProxyType({}),
            denylist=MappingProxyType({}),
            sync_ts=None,
        )


def test_scope_snapshot_is_frozen() -> None:
    """Frozen dataclass cannot be mutated."""
    from ._real_e2a_reconciler_types import ScopeSnapshot

    r = ScopeSnapshot(
        counts=MappingProxyType({"t": 0}),
        digests=MappingProxyType({}),
        denylist=MappingProxyType({}),
        sync_ts=None,
    )
    with pytest.raises(Exception):
        r.sync_ts = "x"  # type: ignore[misc]


# =============================================================================
# Lifecycle envelope tests
# =============================================================================


def _make_lifecycle_run(
    *,
    run_rc: int = 0,
    port: str = "5432",
    list_exists: bool = True,
    list_rc: int = 0,
    remove_rc: int = 0,
    confirm_exists: bool = False,
    confirm_rc: int = 0,
) -> Callable[..., subprocess.CompletedProcess[str]]:
    """Build a fake run function for lifecycle tests."""
    list_count = [0]
    inspect_count = [0]

    def fake_run(command, **_kwargs):
        if command[0] == "run":
            return _make_completed(run_rc, stdout="container-id")
        if command[0] == "container" and command[1] == "ls":
            list_count[0] += 1
            if list_count[0] == 1:
                # Initial listing
                if list_rc != 0:
                    return _make_completed(list_rc, stderr="daemon error")
                return _make_completed(
                    0, stdout="test-container" if list_exists else ""
                )
            else:
                # Post-removal listing
                if confirm_rc != 0:
                    return _make_completed(confirm_rc, stderr="daemon error")
                return _make_completed(
                    0, stdout="test-container" if confirm_exists else ""
                )
        if command[0] == "inspect":
            inspect_count[0] += 1
            fmt = command[2] if len(command) > 2 else ""
            if "HostPort" in fmt:
                return _make_completed(0, stdout=port)
            # Label inspect
            return _make_completed(0, stdout="87.real.e2a.acceptance")
        if command[0] == "rm":
            return _make_completed(remove_rc)
        return _make_completed(0)

    return fake_run


def _patch_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch lifecycle module with mock connection and bypass attestation/migrations."""
    from . import _real_e2a_reconciler_lifecycle as lifecycle

    class _Conn:
        def cursor(self):
            class _C:
                def execute(self, *a, **k):
                    pass

                def fetchone(self):
                    return ("okf_task87", "public", "okf", "okf")

                def close(self):
                    pass

            return _C()

        def close(self):
            pass

    monkeypatch.setattr(lifecycle.psycopg, "connect", lambda **_kw: _Conn())
    monkeypatch.setattr(lifecycle, "_attest_connection_target", lambda *_a, **_k: None)
    monkeypatch.setattr(lifecycle, "_attest_exact_target", lambda *_a, **_k: None)
    monkeypatch.setattr(lifecycle, "_apply_migrations_once", lambda *_a, **_k: None)


def test_yield_disposable_target_normal_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Body succeeds, cleanup confirmed_removed: no exception from cleanup."""
    from . import _real_e2a_reconciler_lifecycle as lifecycle

    fake_run = _make_lifecycle_run(list_exists=True, confirm_exists=False)
    _patch_lifecycle(monkeypatch)

    with lifecycle._yield_disposable_target(
        container_name="test-container", run=fake_run
    ) as target:
        assert target is not None
        assert target.dbname == _EXPECTED_DATABASE


def test_yield_disposable_target_body_raises_cleanup_confirmed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Body raises, cleanup confirmed: original exception re-raised (exact identity)."""
    from . import _real_e2a_reconciler_lifecycle as lifecycle

    fake_run = _make_lifecycle_run(list_exists=True, confirm_exists=False)
    _patch_lifecycle(monkeypatch)

    body_exc = RuntimeError("body failure")
    with pytest.raises(RuntimeError, match="body failure") as exc_info:
        with lifecycle._yield_disposable_target(
            container_name="test-container", run=fake_run
        ):
            raise body_exc

    # EXACT IDENTITY: same object, not just equal
    assert exc_info.value is body_exc


def test_yield_disposable_target_body_succeeds_cleanup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Body succeeds, cleanup fails: RuntimeError('label-gated cleanup failed')."""
    from . import _real_e2a_reconciler_lifecycle as lifecycle

    # Cleanup fails: post-removal listing shows container still exists
    fake_run = _make_lifecycle_run(list_exists=True, confirm_exists=True)
    _patch_lifecycle(monkeypatch)

    with pytest.raises(RuntimeError, match="label-gated cleanup failed"):
        with lifecycle._yield_disposable_target(
            container_name="test-container", run=fake_run
        ):
            pass


def test_yield_disposable_target_body_raises_cleanup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Body raises AND cleanup fails: ExceptionGroup with exact identity."""
    import builtins

    from . import _real_e2a_reconciler_lifecycle as lifecycle

    fake_run = _make_lifecycle_run(list_exists=True, confirm_exists=True)
    _patch_lifecycle(monkeypatch)

    body_exc = ValueError("body error")
    with pytest.raises(builtins.ExceptionGroup) as exc_info:
        with lifecycle._yield_disposable_target(
            container_name="test-container", run=fake_run
        ):
            raise body_exc

    eg = exc_info.value
    assert len(eg.exceptions) == 2
    # EXACT IDENTITY: first exception is the exact original
    assert eg.exceptions[0] is body_exc
    assert isinstance(eg.exceptions[1], RuntimeError)
    assert str(eg.exceptions[1]) == "label-gated cleanup failed"


def test_yield_disposable_target_keyboard_interrupt_with_cleanup_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """KeyboardInterrupt + cleanup failure: BaseExceptionGroup with exact order."""
    import builtins

    from . import _real_e2a_reconciler_lifecycle as lifecycle

    fake_run = _make_lifecycle_run(list_exists=True, confirm_exists=True)
    _patch_lifecycle(monkeypatch)

    body_exc = KeyboardInterrupt()
    with pytest.raises(builtins.BaseExceptionGroup) as exc_info:
        with lifecycle._yield_disposable_target(
            container_name="test-container", run=fake_run
        ):
            raise body_exc

    beg = exc_info.value
    assert len(beg.exceptions) == 2
    # EXACT IDENTITY: first exception is the exact original
    assert beg.exceptions[0] is body_exc
    assert isinstance(beg.exceptions[1], RuntimeError)


def test_yield_disposable_target_run_failure_triggers_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Docker run fails: pytest.fail raised, cleanup still attempted and verified."""
    from . import _real_e2a_reconciler_lifecycle as lifecycle

    # Track cleanup calls
    cleanup_calls = [0]

    # run fails, cleanup finds container absent -> confirmed_absent
    def fake_run(cmd, **kwargs):
        if "run" in cmd:
            result = MagicMock()
            result.returncode = 1
            result.stdout = ""
            result.stderr = "docker run failed"
            return result
        elif "container" in cmd and "ls" in cmd:
            # Cleanup listing - must be called
            cleanup_calls[0] += 1
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""  # Container absent
            result.stderr = ""
            return result
        else:
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

    _patch_lifecycle(monkeypatch)

    with pytest.raises(pytest.fail.Exception, match="unable to start container"):
        with lifecycle._yield_disposable_target(
            container_name="test-container", run=fake_run
        ):
            pass

    # CRITICAL: Cleanup must have been attempted even when run fails
    assert cleanup_calls[0] >= 1, "Cleanup was not attempted after run failure"


def test_yield_disposable_target_run_exception_triggers_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Docker run raises exception: cleanup still attempted."""
    from . import _real_e2a_reconciler_lifecycle as lifecycle

    cleanup_calls = [0]

    def fake_run(cmd, **kwargs):
        if "run" in cmd:
            raise RuntimeError("docker daemon unreachable")
        elif "container" in cmd and "ls" in cmd:
            cleanup_calls[0] += 1
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result
        else:
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

    _patch_lifecycle(monkeypatch)

    with pytest.raises(RuntimeError, match="docker daemon unreachable"):
        with lifecycle._yield_disposable_target(
            container_name="test-container", run=fake_run
        ):
            pass

    assert cleanup_calls[0] >= 1, "Cleanup was not attempted after run exception"


def test_yield_disposable_target_inspect_failure_triggers_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Port inspect fails: cleanup still attempted."""
    from . import _real_e2a_reconciler_lifecycle as lifecycle

    cleanup_calls = [0]

    def fake_run(cmd, **kwargs):
        if "run" in cmd:
            result = MagicMock()
            result.returncode = 0
            result.stdout = "container-id"
            result.stderr = ""
            return result
        elif "inspect" in cmd and "NetworkSettings" in str(cmd):
            # Port inspect fails
            cleanup_calls[0] += 1
            result = MagicMock()
            result.returncode = 1
            result.stdout = ""
            result.stderr = "inspect failed"
            return result
        elif "container" in cmd and "ls" in cmd:
            cleanup_calls[0] += 1
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result
        else:
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

    _patch_lifecycle(monkeypatch)

    with pytest.raises(pytest.fail.Exception, match="unable to determine host port"):
        with lifecycle._yield_disposable_target(
            container_name="test-container", run=fake_run
        ):
            pass

    assert cleanup_calls[0] >= 1, "Cleanup was not attempted after inspect failure"
