"""Wait-for-database unit tests for Task #87.

Extracted from ``test_real_e2a_reconciler_harness_unit`` to keep that
file under the 800-line limit.
"""

from __future__ import annotations

import builtins
from unittest.mock import MagicMock

import pytest

from scripts._rebuild_database_connection import DisposablePostgresqlTarget

from ._real_e2a_reconciler_lifecycle import (
    _EXPECTED_DATABASE,
    _wait_for_database,
)


def _make_mock_target() -> DisposablePostgresqlTarget:
    """Build a fully-specified mock DisposablePostgresqlTarget."""
    target = MagicMock(spec=DisposablePostgresqlTarget)
    target.dbname = _EXPECTED_DATABASE
    target.user = "okf"
    target.host = "127.0.0.1"
    target.hostaddr = "127.0.0.1"
    target.port = 5432
    target.password = "test-password"
    return target


def test_wait_for_database_only_retries_on_operational_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-OperationalError failure inside readiness raises immediately."""
    from . import _real_e2a_reconciler_lifecycle as lifecycle

    class _Cursor:
        def execute(self, sql, params=None):
            raise ValueError("not a connection error")

        def fetchone(self):
            return None

        def close(self):
            pass

    class _Conn:
        def cursor(self):
            return _Cursor()

        def close(self) -> None:
            pass

    monkeypatch.setattr(lifecycle.psycopg, "connect", lambda **_kwargs: _Conn())

    # Bypass the attestation functions to let cursor.execute raise directly
    def _bypass_attest_1(cursor, target):
        cursor.execute("SELECT 1")

    monkeypatch.setattr(lifecycle, "_attest_connection_target", _bypass_attest_1)

    target = _make_mock_target()
    with pytest.raises(ValueError, match="not a connection error"):
        _wait_for_database(target)


def test_wait_for_database_conn_close_failure_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful probe + conn.close failure: must raise sanitized cleanup."""
    from . import _real_e2a_reconciler_lifecycle as lifecycle

    class _Cursor:
        def execute(self, sql, params=None):
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

    monkeypatch.setattr(lifecycle.psycopg, "connect", lambda **_kwargs: _Conn())
    monkeypatch.setattr(lifecycle, "_attest_connection_target", lambda *_a: None)
    monkeypatch.setattr(lifecycle, "_attest_exact_target", lambda *_a: None)

    target = _make_mock_target()
    with pytest.raises(RuntimeError, match="connection cleanup failed"):
        _wait_for_database(target)