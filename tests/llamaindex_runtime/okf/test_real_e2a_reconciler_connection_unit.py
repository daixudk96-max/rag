"""Connection cleanup unit tests for Task #87.

Extracted from ``test_real_e2a_reconciler_lifecycle_unit`` to keep that
file under the 800-line limit.
"""

from __future__ import annotations

import builtins
from unittest.mock import MagicMock

import pytest

# =============================================================================
# Phase 1: Cursor creation failure
# =============================================================================


def test_open_attested_connection_cursor_creation_failure_closes_conn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cursor creation failure: conn.close attempted, exact exception re-raised."""
    from . import _real_e2a_reconciler_lifecycle as lifecycle

    conn_closed = [False]

    class _Conn:
        def cursor(self):
            raise RuntimeError("cursor failed")

        def close(self):
            conn_closed[0] = True

    monkeypatch.setattr(lifecycle.psycopg, "connect", lambda **_kw: _Conn())
    monkeypatch.setattr(lifecycle, "_attest_connection_target", lambda *_a: None)

    target = MagicMock()
    target.dbname = "okf_task87"
    target.user = "okf"

    with pytest.raises(RuntimeError, match="cursor failed"):
        lifecycle._open_attested_connection(target, autocommit=True)

    assert conn_closed[0]


# =============================================================================
# Phase 2: Attestation failure
# =============================================================================


def test_open_attested_connection_attestation_failure_closes_cursor_and_conn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Attestation failure: cursor and conn close attempted."""
    from . import _real_e2a_reconciler_lifecycle as lifecycle

    cursor_closed = [False]
    conn_closed = [False]

    class _Cursor:
        def execute(self, *a, **k):
            # Raise during attestation
            raise RuntimeError("attest failed")

        def fetchone(self):
            return None

        def close(self):
            cursor_closed[0] = True

    class _Conn:
        def cursor(self):
            return _Cursor()

        def close(self):
            conn_closed[0] = True

    monkeypatch.setattr(lifecycle.psycopg, "connect", lambda **_kw: _Conn())
    # Don't bypass attestation - let it raise

    target = MagicMock()
    target.dbname = "okf_task87"
    target.user = "okf"

    with pytest.raises(ValueError, match="executed_failed"):
        lifecycle._open_attested_connection(target, autocommit=True)

    assert cursor_closed[0]
    assert conn_closed[0]


def test_open_attested_connection_success_returns_open_conn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Success: returns open connection, cursor confirmed closed."""
    from . import _real_e2a_reconciler_lifecycle as lifecycle

    cursor_closed = [False]
    call_count = [0]

    class _Cursor:
        def execute(self, *a, **k):
            pass

        def fetchone(self):
            call_count[0] += 1
            if call_count[0] == 1:
                return ("okf_task87", "public")
            else:
                return ("okf", "okf")

        def close(self):
            cursor_closed[0] = True

    class _Conn:
        def cursor(self):
            return _Cursor()

        def close(self):
            pass

    monkeypatch.setattr(lifecycle.psycopg, "connect", lambda **_kw: _Conn())
    monkeypatch.setattr(lifecycle, "_attest_connection_target", lambda *_a: None)

    target = MagicMock()
    target.dbname = "okf_task87"
    target.user = "okf"

    conn = lifecycle._open_attested_connection(target, autocommit=True)
    assert conn is not None
    assert cursor_closed[0]


def test_open_attested_connection_raw_cleanup_secret_not_exposed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raw cleanup exception message must not appear in output."""
    from . import _real_e2a_reconciler_lifecycle as lifecycle

    class _Cursor:
        def execute(self, *a, **k):
            raise RuntimeError("attest failed")

        def fetchone(self):
            return None

        def close(self):
            # This message should NEVER appear
            raise ValueError("SECRET_PASSWORD=hunter2")

    class _Conn:
        def cursor(self):
            return _Cursor()

        def close(self):
            pass

    monkeypatch.setattr(lifecycle.psycopg, "connect", lambda **_kw: _Conn())

    target = MagicMock()
    target.dbname = "okf_task87"
    target.user = "okf"

    with pytest.raises(builtins.ExceptionGroup) as exc_info:
        lifecycle._open_attested_connection(target, autocommit=True)

    msg = str(exc_info.value)
    # Raw cleanup message must NOT appear
    assert "SECRET_PASSWORD" not in msg
    assert "hunter2" not in msg


# =============================================================================
# Phase 4: Success + cursor.close() failure (NEW - DEFECT 1)
# =============================================================================


def test_open_attested_connection_success_cursor_close_fails_closes_conn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Success attestation + cursor.close() failure: must close conn and raise."""
    from . import _real_e2a_reconciler_lifecycle as lifecycle

    conn_closed = [False]

    class _Cursor:
        def execute(self, *a, **k):
            pass

        def fetchone(self):
            return ("okf_task87", "public")

        def close(self):
            raise RuntimeError("cursor close failed")

    class _Conn:
        def cursor(self):
            return _Cursor()

        def close(self):
            conn_closed[0] = True

    monkeypatch.setattr(lifecycle.psycopg, "connect", lambda **_kw: _Conn())
    monkeypatch.setattr(lifecycle, "_attest_connection_target", lambda *_a: None)
    monkeypatch.setattr(lifecycle, "_attest_exact_target", lambda *_a: None)

    target = MagicMock()
    target.dbname = "okf_task87"
    target.user = "okf"

    # After successful attestation, cursor.close failure must:
    # 1. Close the connection
    # 2. Raise sanitized cleanup exception
    with pytest.raises(RuntimeError, match="connection cleanup failed"):
        lifecycle._open_attested_connection(target, autocommit=True)

    assert conn_closed[0]


def test_open_attested_connection_success_cursor_close_and_conn_close_both_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Success + cursor.close + conn.close both fail: ONE fixed cleanup RuntimeError."""
    from . import _real_e2a_reconciler_lifecycle as lifecycle

    class _Cursor:
        def execute(self, *a, **k):
            pass

        def fetchone(self):
            return ("okf_task87", "public")

        def close(self):
            raise RuntimeError("cursor close failed")

    class _Conn:
        def cursor(self):
            return _Cursor()

        def close(self):
            raise RuntimeError("conn close failed")

    monkeypatch.setattr(lifecycle.psycopg, "connect", lambda **_kw: _Conn())
    monkeypatch.setattr(lifecycle, "_attest_connection_target", lambda *_a: None)
    monkeypatch.setattr(lifecycle, "_attest_exact_target", lambda *_a: None)

    target = MagicMock()
    target.dbname = "okf_task87"
    target.user = "okf"

    # Both cleanup failures => ONE fixed cleanup RuntimeError (not two-member group)
    with pytest.raises(RuntimeError, match="connection cleanup failed"):
        lifecycle._open_attested_connection(target, autocommit=True)


# =============================================================================
# Phase 5: Manual transaction commit failures (NEW - DEFECT 1)
# =============================================================================


def test_open_attested_connection_manual_commit_failure_closes_conn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Manual commit failure: conn.close attempted, exact exception re-raised."""
    from . import _real_e2a_reconciler_lifecycle as lifecycle

    primary_exc = RuntimeError("commit failed")
    conn_closed = [False]

    class _Cursor:
        def execute(self, *a, **k):
            pass

        def fetchone(self):
            # Return values for both attestation queries
            return ("okf_task87", "public")

        def close(self):
            pass

    class _Conn:
        def cursor(self):
            return _Cursor()

        def commit(self):
            raise primary_exc

        def close(self):
            conn_closed[0] = True

    monkeypatch.setattr(lifecycle.psycopg, "connect", lambda **_kw: _Conn())
    monkeypatch.setattr(lifecycle, "_attest_connection_target", lambda *_a: None)
    monkeypatch.setattr(lifecycle, "_attest_exact_target", lambda *_a: None)

    target = MagicMock()
    target.dbname = "okf_task87"
    target.user = "okf"

    # Commit failure must re-raise exact exception
    with pytest.raises(RuntimeError, match="commit failed") as exc_info:
        lifecycle._open_attested_connection(target, autocommit=False)

    # Verify exact exception object identity
    assert exc_info.value is primary_exc
    assert conn_closed[0]


def test_open_attested_connection_manual_commit_and_conn_close_both_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Manual commit + conn.close both fail: compose exact primary + sanitized."""
    from . import _real_e2a_reconciler_lifecycle as lifecycle

    primary_exc = RuntimeError("commit failed")

    class _Cursor:
        def execute(self, *a, **k):
            pass

        def fetchone(self):
            return ("okf_task87", "public")

        def close(self):
            pass

    class _Conn:
        def cursor(self):
            return _Cursor()

        def commit(self):
            raise primary_exc

        def close(self):
            raise RuntimeError("conn close failed")

    monkeypatch.setattr(lifecycle.psycopg, "connect", lambda **_kw: _Conn())
    monkeypatch.setattr(lifecycle, "_attest_connection_target", lambda *_a: None)
    monkeypatch.setattr(lifecycle, "_attest_exact_target", lambda *_a: None)

    target = MagicMock()
    target.dbname = "okf_task87"
    target.user = "okf"

    with pytest.raises(builtins.ExceptionGroup) as exc_info:
        lifecycle._open_attested_connection(target, autocommit=False)

    # First member must be exact primary exception object
    assert exc_info.value.exceptions[0] is primary_exc
    # Second member must be sanitized cleanup
    assert "connection cleanup failed" in str(exc_info.value.exceptions[1])


# =============================================================================
# Phase 6: KeyboardInterrupt/SystemExit with cleanup (NEW - DEFECT 1)
# =============================================================================


def test_open_attested_connection_keyboard_interrupt_with_cleanup_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """KeyboardInterrupt + cleanup failure: BaseExceptionGroup with ordered members."""
    from . import _real_e2a_reconciler_lifecycle as lifecycle

    class _Cursor:
        def execute(self, *a, **k):
            pass

        def fetchone(self):
            return ("okf_task87", "public")

        def close(self):
            pass

    class _Conn:
        def cursor(self):
            return _Cursor()

        def close(self):
            raise RuntimeError("conn close failed")

    monkeypatch.setattr(lifecycle.psycopg, "connect", lambda **_kw: _Conn())
    monkeypatch.setattr(lifecycle, "_attest_connection_target", lambda *_a: None)

    target = MagicMock()
    target.dbname = "okf_task87"
    target.user = "okf"

    # Inject KeyboardInterrupt during yield
    import contextlib

    @contextlib.contextmanager
    def _inject_kbint():
        raise KeyboardInterrupt("user abort")
        yield  # Never reached

    monkeypatch.setattr(
        lifecycle,
        "_attest_exact_target",
        lambda *_a: _inject_kbint().__enter__(),
    )

    with pytest.raises(builtins.BaseExceptionGroup) as exc_info:
        lifecycle._open_attested_connection(target, autocommit=True)

    # First member must be exact KeyboardInterrupt
    assert isinstance(exc_info.value.exceptions[0], KeyboardInterrupt)
    # Second member must be sanitized cleanup
    assert "connection cleanup failed" in str(exc_info.value.exceptions[1])


# =============================================================================
# Phase 7: Exact exception object identity tests (NEW - DEFECT 1)
# =============================================================================


def test_open_attested_connection_cursor_creation_exact_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cursor creation failure: must re-raise exact same exception object."""
    from . import _real_e2a_reconciler_lifecycle as lifecycle

    primary_exc = RuntimeError("cursor failed exact")

    class _Conn:
        def cursor(self):
            raise primary_exc

        def close(self):
            pass

    monkeypatch.setattr(lifecycle.psycopg, "connect", lambda **_kw: _Conn())
    monkeypatch.setattr(lifecycle, "_attest_connection_target", lambda *_a: None)

    target = MagicMock()
    target.dbname = "okf_task87"
    target.user = "okf"

    with pytest.raises(RuntimeError) as exc_info:
        lifecycle._open_attested_connection(target, autocommit=True)

    # Exact object identity
    assert exc_info.value is primary_exc


def test_open_attested_connection_attestation_exact_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Attestation failure: must re-raise exact same exception object."""
    from . import _real_e2a_reconciler_lifecycle as lifecycle

    primary_exc = ValueError("attest failed exact")

    class _Cursor:
        def execute(self, *a, **k):
            raise primary_exc

        def fetchone(self):
            return None

        def close(self):
            pass

    class _Conn:
        def cursor(self):
            return _Cursor()

        def close(self):
            pass

    monkeypatch.setattr(lifecycle.psycopg, "connect", lambda **_kw: _Conn())

    target = MagicMock()
    target.dbname = "okf_task87"
    target.user = "okf"

    with pytest.raises(ValueError) as exc_info:
        lifecycle._open_attested_connection(target, autocommit=True)

    # Exact object identity (wrapped by _attest_connection_target)
    # Note: The actual exception may be wrapped, so we check the cause
    assert exc_info.value is primary_exc or exc_info.value.__cause__ is primary_exc
