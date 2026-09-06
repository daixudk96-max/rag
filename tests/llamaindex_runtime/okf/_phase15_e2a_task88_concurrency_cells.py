"""PARTIAL(C6) advisory-lock concurrency cell helper (Stage 4, Task #88).

This helper module is never collected by default test name discovery (the
``_`` prefix keeps it out of normal test collection). It provides ONE
explicitly selected live cell in a NEW identity (C6) that observes the
production whole-corpus advisory scope lock under real concurrency:

- AB: the default ``E2aReconciler`` with a ``post_lock_sync_hook`` runs on
  its own fresh attested manual-transaction primary and publishes its real
  backend pid (pg_backend_pid) before reconcile. The hook publishes TWO
  monotonic deadlines anchored at lock acquisition — a readiness deadline
  (now + _READINESS_DEADLINE_SECONDS) and a later hold deadline
  (readiness deadline + _SNAPSHOT_MARGIN_SECONDS) — then signals that the
  production scope locks are held and waits (bounded by the hold deadline)
  for the release event; a hold-deadline timeout fails the cell closed and
  is never waiting evidence. The snapshot margin keeps the AB hold alive
  across the bounded ABC pid handshake, the readiness gate, and the sole
  lock-catalog snapshot that follows a gate success.
- ABC: a second normal default ``E2aReconciler()`` on its own fresh
  attested manual-transaction primary reconciles the identical desired
  state, blocking on the same whole-corpus advisory lock. The worker
  publishes its real backend pid (pg_backend_pid) before reconcile.
- A third fresh attested observer recomputes the expected lock key halves
  and the database oid first, then runs a bounded readiness gate that
  probes pg_stat_activity until the ABC backend genuinely shows an
  advisory-lock wait for that real pid, then runs exactly ONE
  advisory-lock catalog view query immediately after the gate succeeds
  while AB holds the locks. The snapshot must establish exactly one common
  advisory-lock tuple for AB/ABC (AB granted, ABC waiting) attributed to
  the real AB and ABC backend pids; a missing tuple or snapshot is not a
  skipped, blocked, or pass receipt. Advisory tuples are distinguished
  from relation and tuple locks by the catalog filter; the observer is
  read-only.

After the release, the real post-release outcomes are asserted truthfully
(AB "changed", ABC "no_op") and both worker threads are joined with a
bounded cleanup timeout; a cleanup timeout fails the cell and never
constitutes waiting evidence. Threads are joined only when they were
actually started.

Boundary: this is PARTIAL(C6) evidence for one contended whole-corpus
advisory lock tuple under one interleaving. It is not evidence for any
other cell, any late-DML path, any other lock family, any performance
property, any general performance statement, or any task-level or
phase-level status claim.

Security contract: no environment variable access of any kind; no database
URL of any kind; no URI, credential, target, container token, or raw
fixture content is ever printed, logged, returned, or included in
observation reprs; backend pids are session identifiers that are never
leaked through reprs, results, or reasons. All connections come from
DisposableE2aSession.open_fresh_attested_connection; the registry writer,
both reconciler primaries, and the observer are separate fresh attested
connections/transactions. Timing is governed by TWO monotonic deadlines
published by the AB hook before it signals acquisition: a readiness
deadline for the ABC pid handshake and the readiness gate, and a later
hold deadline (readiness deadline plus a fixed snapshot margin) for the
AB release wait, so a gate success immediately before the readiness
deadline still leaves the reserved margin for the single immediate
snapshot; a late or suspended host fails closed instead of waiting
unbounded. The readiness gate is a
monotone-deadline condition-wait for the real backend pid (Event backoff,
never a sleep, and never the lock catalog view); readiness cannot be
fabricated, and the single lock-catalog evidence snapshot is taken only
after the gate returns true. No manual advisory-lock statement, no
sleep-based retry-to-pass, no repeated lock-catalog snapshot, no injected
factory, no fakes, and no test framework machinery appear in this helper.
Every cursor and connection is closed in a finally block; failures are
absorbed into redacted observations carrying a bounded class/type-only
diagnostic.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, NamedTuple

from ._phase15_e2a_task88_live_cells import (
    _FIXTURE_TITLE,
    _SOURCE_URI,
    _build_foundation_desired_state,
    _close_quietly,
    _create_source_fixture,
    _error_reason,
    _open_observer_connection,
    _open_reconciler_primary_connection,
    _open_writer_connection,
)


class C6AdvisoryLockObservations(NamedTuple):
    """Redacted observations for the C6 advisory-lock concurrency cell."""

    first_outcome: str = ""
    second_outcome: str = ""
    common_tuple_exact: bool = False
    lock_mapping_exact: bool = False
    threads_joined_cleanly: bool = False
    success: bool = True
    error_reason: str = ""

    def __repr__(self) -> str:
        rendered = ", ".join(
            f"{key}={value!r}"
            for key, value in self._asdict().items()
            if key != "error_reason"
        )
        return f"C6AdvisoryLockObservations({rendered}, details=<redacted>)"


def _unlink_quietly(path: Path | None) -> None:
    """Remove a temp fixture path without surfacing cleanup failures."""
    if path is None:
        return
    try:
        path.unlink()
    except Exception:
        pass


def _register_single_document(writer_conn: Any) -> tuple[Path, Any]:
    """Register one real document version through the real registry writer."""
    from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

    source_path = _create_source_fixture()
    registration = PostgresRegistryWriter(writer_conn).register_document(
        source_path=source_path,
        source_uri=_SOURCE_URI,
        title=_FIXTURE_TITLE,
    )
    return source_path, registration


def _hold_after_locks(
    locks_acquired_event: threading.Event,
    release_event: threading.Event,
    deadline_box: dict[str, float],
) -> Any:
    """Build the AB post-lock hook: publish deadlines, signal, hold release.

    The hook runs inside the production reconciler after the scope locks
    are acquired. It anchors TWO monotonic deadlines BEFORE signalling
    acquisition: the readiness deadline (time.monotonic() +
    _READINESS_DEADLINE_SECONDS) bounds the ABC pid handshake and the
    readiness gate, and the later hold deadline (readiness deadline +
    _SNAPSHOT_MARGIN_SECONDS) bounds the AB release wait, reserving the
    snapshot margin so a gate success at the readiness deadline still
    leaves time for the single immediate snapshot. If the hold deadline
    expires first (late or suspended host), the hook raises and the cell
    fails closed rather than waiting unbounded.
    """

    def _hook() -> None:
        deadline_box["readiness_deadline"] = (
            time.monotonic() + _READINESS_DEADLINE_SECONDS
        )
        deadline_box["hold_deadline"] = (
            deadline_box["readiness_deadline"] + _SNAPSHOT_MARGIN_SECONDS
        )
        locks_acquired_event.set()
        if not release_event.wait(timeout=_remaining(deadline_box["hold_deadline"])):
            raise RuntimeError("c6 hold deadline expired")

    return _hook


def _analyze_advisory_rows(
    rows: tuple[Any, ...],
    whole_corpus_key: int,
    parent_key: int,
    database_oid: int,
    ab_pid: int,
    abc_pid: int,
) -> tuple[bool, bool]:
    """Map every observed advisory tuple to real sessions and key halves.

    The production scope lock statement maps an int8 key to catalog halves
    as classid = key >> 32 and objid = key & 0xffffffff with objsubid = 1
    and the session database oid. Every observed advisory tuple must map to
    the whole-corpus key or the single parent key with exactly the expected
    halves, and the pid column must attribute the whole-corpus granted
    holder to AB, the whole-corpus waiter to ABC, and the parent holder to
    AB (consistent with ABC blocking on the first whole-corpus lock).
    Missing or empty expected tuples fail BOTH flags (never vacuously
    true). Returns (common_tuple_exact, lock_mapping_exact).
    """
    mask = 0xFFFFFFFF

    def _half_match(key: int, classid: int, objid: int) -> bool:
        return (
            classid == (key >> 32) & mask
            and objid == key & mask
        )

    granted_pids_by_key: dict[int, list[int]] = {}
    waiting_pids_by_key: dict[int, list[int]] = {}
    mapping_exact = True
    for row in rows:
        database, classid, objid, objsubid, mode, granted, _locktype, pid = row
        if (
            database != database_oid
            or mode != "ExclusiveLock"
            or objsubid != 1
        ):
            mapping_exact = False
        key: int | None = None
        if _half_match(whole_corpus_key, classid, objid):
            key = whole_corpus_key
        elif _half_match(parent_key, classid, objid):
            key = parent_key
        else:
            mapping_exact = False
        if key is None:
            continue
        bucket = granted_pids_by_key if granted else waiting_pids_by_key
        bucket.setdefault(key, []).append(pid)
    whole_granted_pids = granted_pids_by_key.get(whole_corpus_key, [])
    whole_waiting_pids = waiting_pids_by_key.get(whole_corpus_key, [])
    parent_granted_pids = granted_pids_by_key.get(parent_key, [])
    parent_waiting_pids = waiting_pids_by_key.get(parent_key, [])
    presence_exact = (
        len(whole_granted_pids) == 1
        and len(whole_waiting_pids) == 1
        and len(parent_granted_pids) == 1
        and not parent_waiting_pids
    )
    attribution_exact = (
        whole_granted_pids == [ab_pid]
        and whole_waiting_pids == [abc_pid]
        and parent_granted_pids == [ab_pid]
    )
    common_exact = mapping_exact and presence_exact and attribution_exact
    mapping_exact = common_exact
    return common_exact, mapping_exact


_READINESS_DEADLINE_SECONDS: float = 30.0
_SNAPSHOT_MARGIN_SECONDS: float = 5.0


def _remaining(deadline: float) -> float:
    """Bounded remaining time to the shared deadline, clamped at zero."""
    return max(0.0, deadline - time.monotonic())


def _is_hold_deadline_failure(failure: Any) -> bool:
    """True only for the bounded AB hold-deadline expiration marker."""
    return (
        isinstance(failure, RuntimeError)
        and str(failure) == "c6 hold deadline expired"
    )


def _abc_reached_advisory_wait(
    observer_conn: Any, abc_pid: int, deadline: float
) -> bool:
    """Bounded readiness gate: ABC must genuinely wait on the advisory lock.

    Runs on the fresh attested observer connection and reads only
    pg_stat_activity (never the lock catalog view): the ABC backend is
    waiting on the production advisory lock exactly when
    wait_event_type = 'Lock' and wait_event = 'advisory' for its real pid.
    The deadline is a fixed monotone bound; if readiness is never observed
    the gate returns False and the cell fails closed with a bounded
    diagnostic. The probe backoff is a bounded Event wait, never a sleep,
    and the single lock-catalog evidence snapshot is taken by the caller
    only after this gate returns True.
    """
    probe_cursor = observer_conn.cursor()
    probe_pause = threading.Event()
    try:
        while time.monotonic() < deadline:
            probe_cursor.execute(
                "SELECT 1 FROM pg_stat_activity WHERE pid = %s "
                "AND wait_event_type = 'Lock' AND wait_event = 'advisory'",
                (abc_pid,),
            )
            if probe_cursor.fetchone() is not None:
                return True
            probe_pause.wait(timeout=0.05)
        return False
    finally:
        _close_quietly(probe_cursor)


def _run_c6_impl(session: Any) -> C6AdvisoryLockObservations:
    """Run the C6 advisory-lock concurrency cell (module docstring details).

    Two worker threads run real reconciliations on their own fresh attested
    manual-transaction primaries; the AB reconciler carries the post-lock
    hook (which publishes the shared monotonic deadline before signalling
    acquisition), the ABC reconciler is the bare default. Both workers
    publish their real backend pids before reconcile. The observer reads
    the key halves and database oid first, then runs the bounded readiness
    gate until ABC genuinely waits on the advisory lock, then takes the
    single advisory-lock catalog snapshot and attributes every tuple to
    the real AB and ABC pids. The release event is set and both workers
    are joined with bounded timeouts in a finally path; threads are joined
    only when actually started.
    """
    from llamaindex_runtime.okf.e2a_reconciler import E2aReconciler

    source_path: Path | None = None
    writer_conn: Any = None
    ab_primary_conn: Any = None
    abc_primary_conn: Any = None
    observer_conn: Any = None
    observer_cursor: Any = None
    ab_thread: threading.Thread | None = None
    abc_thread: threading.Thread | None = None
    locks_acquired_event = threading.Event()
    release_event = threading.Event()
    abc_go_event = threading.Event()
    abc_pid_event = threading.Event()
    pid_box: dict[str, int] = {}
    deadline_box: dict[str, float] = {}
    ab_started = False
    abc_started = False
    results: dict[str, Any] = {}
    threads_joined_cleanly = False
    common_tuple_exact = False
    lock_mapping_exact = False
    try:
        writer_conn = _open_writer_connection(session)
        source_path, registration = _register_single_document(writer_conn)
        desired = _build_foundation_desired_state(registration, source_path)
        ab_primary_conn = _open_reconciler_primary_connection(session)
        abc_primary_conn = _open_reconciler_primary_connection(session)
        observer_conn = _open_observer_connection(session)

        def _ab_worker() -> None:
            ab_pid_cursor: Any = None
            try:
                ab_pid_cursor = ab_primary_conn.cursor()
                ab_pid_cursor.execute("SELECT pg_backend_pid()")
                pid_box["ab_pid"] = int(ab_pid_cursor.fetchone()[0])
                _close_quietly(ab_pid_cursor)
                ab_pid_cursor = None
                hooked = E2aReconciler(
                    post_lock_sync_hook=_hold_after_locks(
                        locks_acquired_event, release_event, deadline_box
                    )
                )
                results["ab"] = hooked.reconcile(ab_primary_conn, desired)
            except Exception as failure:
                results["ab"] = failure
            finally:
                _close_quietly(ab_pid_cursor)

        def _abc_worker() -> None:
            pid_cursor: Any = None
            try:
                if not abc_go_event.wait(timeout=30.0):
                    raise RuntimeError("c6 abc start timeout")
                pid_cursor = abc_primary_conn.cursor()
                pid_cursor.execute("SELECT pg_backend_pid()")
                pid_box["pid"] = int(pid_cursor.fetchone()[0])
                _close_quietly(pid_cursor)
                pid_cursor = None
                abc_pid_event.set()
                results["abc"] = E2aReconciler().reconcile(
                    abc_primary_conn, desired
                )
            except Exception as failure:
                results["abc"] = failure
            finally:
                _close_quietly(pid_cursor)

        ab_thread = threading.Thread(target=_ab_worker, name="c6-ab-reconciler")
        abc_thread = threading.Thread(target=_abc_worker, name="c6-abc-reconciler")
        ab_thread.start()
        ab_started = True
        if not locks_acquired_event.wait(timeout=30.0):
            return C6AdvisoryLockObservations(
                success=False,
                error_reason=_error_reason(
                    "c6_locks_never_acquired", RuntimeError("lock acquisition timeout")
                ),
            )
        readiness_deadline = deadline_box["readiness_deadline"]
        abc_thread.start()
        abc_started = True
        abc_go_event.set()
        if not abc_pid_event.wait(timeout=_remaining(readiness_deadline)):
            return C6AdvisoryLockObservations(
                success=False,
                error_reason=_error_reason(
                    "c6_abc_pid_timeout", RuntimeError("abc backend pid timeout")
                ),
            )

        observer_cursor = observer_conn.cursor()
        observer_cursor.execute(
            "SELECT hashtextextended('okf:e2a:whole-corpus', 0), "
            "hashtextextended(%s, 0)",
            (
                f"okf:e2a:parent:{str(registration.doc_id)}:"
                f"{str(registration.version_id)}",
            ),
        )
        key_row = observer_cursor.fetchone()
        observer_cursor.execute(
            "SELECT oid FROM pg_database WHERE datname = current_database()"
        )
        oid_row = observer_cursor.fetchone()
        if not _abc_reached_advisory_wait(
            observer_conn, pid_box["pid"], readiness_deadline
        ):
            return C6AdvisoryLockObservations(
                success=False,
                error_reason=_error_reason(
                    "c6_abc_readiness_timeout",
                    RuntimeError("abc never reached advisory lock wait"),
                ),
            )
        observer_cursor.execute(
            "SELECT database, classid, objid, objsubid, mode, granted, locktype, "
            "pid FROM pg_locks WHERE locktype = 'advisory'"
        )
        lock_rows = observer_cursor.fetchall()
        common_tuple_exact, lock_mapping_exact = _analyze_advisory_rows(
            rows=lock_rows,
            whole_corpus_key=int(key_row[0]),
            parent_key=int(key_row[1]),
            database_oid=int(oid_row[0]),
            ab_pid=pid_box["ab_pid"],
            abc_pid=pid_box["pid"],
        )

        release_event.set()
        if ab_started and ab_thread is not None:
            ab_thread.join(timeout=30.0)
        if abc_started and abc_thread is not None:
            abc_thread.join(timeout=30.0)
        threads_joined_cleanly = bool(
            ab_thread is not None
            and abc_thread is not None
            and not ab_thread.is_alive()
            and not abc_thread.is_alive()
        )
        if not threads_joined_cleanly:
            return C6AdvisoryLockObservations(
                success=False,
                error_reason=_error_reason(
                    "c6_worker_join_timeout", RuntimeError("cleanup join timeout")
                ),
            )

        ab_result = results.get("ab")
        abc_result = results.get("abc")
        if (
            ab_result is None
            or abc_result is None
            or isinstance(ab_result, Exception)
            or isinstance(abc_result, Exception)
        ):
            if isinstance(ab_result, Exception) and _is_hold_deadline_failure(
                ab_result
            ):
                return C6AdvisoryLockObservations(
                    success=False,
                    error_reason=_error_reason(
                        "c6_ab_hold_deadline_expired", ab_result
                    ),
                )
            failure = (
                ab_result
                if isinstance(ab_result, Exception)
                else abc_result
            )
            if failure is None:
                failure = RuntimeError("worker produced no outcome")
            return C6AdvisoryLockObservations(
                success=False,
                error_reason=_error_reason("c6_worker_failed", failure),
            )
        return C6AdvisoryLockObservations(
            first_outcome=ab_result.outcome,
            second_outcome=abc_result.outcome,
            common_tuple_exact=common_tuple_exact,
            lock_mapping_exact=lock_mapping_exact,
            threads_joined_cleanly=threads_joined_cleanly,
        )
    except Exception as failure:
        return C6AdvisoryLockObservations(
            success=False,
            error_reason=_error_reason("c6_advisory_lock_cell_failed", failure),
        )
    finally:
        release_event.set()
        if ab_started and ab_thread is not None:
            ab_thread.join(timeout=30.0)
        if abc_started and abc_thread is not None:
            abc_thread.join(timeout=30.0)
        _close_quietly(observer_cursor)
        _close_quietly(observer_conn)
        _close_quietly(abc_primary_conn)
        _close_quietly(ab_primary_conn)
        _close_quietly(writer_conn)
        _unlink_quietly(source_path)
