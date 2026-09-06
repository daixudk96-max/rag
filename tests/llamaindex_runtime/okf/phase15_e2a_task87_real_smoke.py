"""Phase 15 E2A Task #87 live-bridge smoke selector.

This module provides an explicitly selected live test for DisposableE2aSession
bridge functionality. It intentionally does NOT match the default test_*.py
collection pattern to prevent accidental collection during normal test runs.

Contract:
    - Fails closed without exact authorization (RuntimeError, no pytest.skip)
    - Uses only the permitted DisposableE2aSession live lifecycle
    - Tests two fresh bridge connections with object identity and PID distinctness
    - Never logs/prints container name, password, token, or target values
"""

from __future__ import annotations

import contextlib
import socket
import secrets
from typing import NamedTuple

from psycopg.pq import TransactionStatus

from ._phase15_e2a_harness_types import (
    _require_authorization,
    _validate_container_name,
)
from ._phase15_e2a_harness_lifecycle import (
    DisposableE2aSession,
)


class ConnectionObservations(NamedTuple):
    """Non-sensitive observations from connection verification."""

    object_identity_distinct: bool
    backend_pids_distinct: bool
    both_idle: bool
    both_manual: bool
    both_select_one_ok: bool
    success: bool = True
    error_reason: str = ""

    def __repr__(self) -> str:
        return (
            f"ConnectionObservations("
            f"object_identity_distinct={self.object_identity_distinct!r}, "
            f"backend_pids_distinct={self.backend_pids_distinct!r}, "
            f"both_idle={self.both_idle!r}, "
            f"both_manual={self.both_manual!r}, "
            f"both_select_one_ok={self.both_select_one_ok!r}, "
            f"success={self.success!r})"
        )


def _verify_two_fresh_connections_impl(
    session: DisposableE2aSession,
) -> ConnectionObservations:
    """Internal worker to verify two fresh connections.

    Security: Absorbs all failures, returns safe result.
    No sensitive values (connections, cursors, rows, PIDs) escape this frame.
    All resources are closed before returning.
    """
    conn1 = None
    conn2 = None
    cur1 = None
    cur2 = None

    try:
        conn1 = session.open_fresh_attested_connection()
        conn2 = session.open_fresh_attested_connection()

        # Capture observations before cleanup
        obj_distinct = conn1 is not conn2
        manual1 = conn1.autocommit is False
        manual2 = conn2.autocommit is False
        idle1 = conn1.info.transaction_status == TransactionStatus.IDLE
        idle2 = conn2.info.transaction_status == TransactionStatus.IDLE
        pid1 = conn1.info.backend_pid
        pid2 = conn2.info.backend_pid

        # Execute queries
        cur1 = conn1.cursor()
        cur1.execute("SELECT 1")
        row1 = cur1.fetchone()
        select1_ok = row1 == (1,)

        cur2 = conn2.cursor()
        cur2.execute("SELECT 1")
        row2 = cur2.fetchone()
        select2_ok = row2 == (1,)

        observations = ConnectionObservations(
            object_identity_distinct=obj_distinct,
            backend_pids_distinct=pid1 != pid2,
            both_idle=idle1 and idle2,
            both_manual=manual1 and manual2,
            both_select_one_ok=select1_ok and select2_ok,
            success=True,
        )
    except Exception:
        # Absorb all failures - return safe result
        observations = ConnectionObservations(
            object_identity_distinct=False,
            backend_pids_distinct=False,
            both_idle=False,
            both_manual=False,
            both_select_one_ok=False,
            success=False,
            error_reason="connection_verification_failed",
        )
    finally:
        # Clean up all sensitive locals in reverse order
        if cur2 is not None:
            try:
                cur2.close()
            except Exception:
                pass
        if cur1 is not None:
            try:
                cur1.close()
            except Exception:
                pass
        if conn2 is not None:
            try:
                conn2.close()
            except Exception:
                pass
        if conn1 is not None:
            try:
                conn1.close()
            except Exception:
                pass

    return observations


def _generate_safe_container_name() -> str:
    """Generate a unique safe container name for test isolation.

    Uses cryptographically random hex prefix to avoid collisions.
    """
    random_hex = secrets.token_hex(8)
    return f"e2a-smoke-{random_hex}"


def _generate_test_password() -> str:
    """Generate a random test-only password.

    Uses alphanumeric characters for safety in Docker env-file.
    """
    import string

    chars = string.ascii_letters + string.digits
    return "".join(secrets.choice(chars) for _ in range(24))


def _select_ephemeral_port() -> str:
    """Select an ephemeral free port by binding to 127.0.0.1:0.

    Contract:
        - Binds AF_INET/SOCK_STREAM to 127.0.0.1:0
        - Reads the assigned port number
        - Closes the socket before returning
        - No SO_REUSEADDR, no fixed host port, no retry
        - If port is claimed afterwards, the test must fail rather than mask it
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        return str(port)


def test_e2a_task87_bridge_smoke_two_fresh_connections() -> None:
    """Smoke test for DisposableE2aSession bridge with two fresh connections.

    Contract:
        - Calls _require_authorization() at function start (not module import)
        - Creates unique container name and password without logging
        - Selects ephemeral port via socket binding
        - Opens two bridge connections with ExitStack cleanup
        - Each connection is manual (autocommit=False), IDLE, returns (1,) from SELECT 1
        - Proves fresh physical connections via distinct object identity AND distinct backend PID
        - Relies on DisposableE2aSession.__exit__ for attested container removal confirmation
        - Outer frame never contains password, container_name, port, connection, cursor, or rows
    """
    # Fail closed before any Docker/connection action if not authorized
    _require_authorization()

    # All sensitive values passed directly to session - never bound to outer locals
    with contextlib.ExitStack() as stack:
        session = stack.enter_context(
            DisposableE2aSession(
                container_name=_validate_container_name(
                    _generate_safe_container_name()
                ),
                port=_select_ephemeral_port(),
                password=_generate_test_password(),
            )
        )

        # Helper encapsulates all connection/cursor/row operations
        result = _verify_two_fresh_connections_impl(session)

    if not result.success:
        raise RuntimeError("Connection verification failed") from None

    # Verify non-sensitive observations only
    assert result.both_manual, "Both connections must be in manual mode"
    assert result.both_idle, "Both connections must be IDLE"
    assert result.both_select_one_ok, "Both connections must return (1,) from SELECT 1"
    assert result.object_identity_distinct, "Connections must be distinct objects"
    assert result.backend_pids_distinct, "Connections must have distinct backend PIDs"
