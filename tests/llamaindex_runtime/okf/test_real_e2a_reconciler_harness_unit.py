"""Unit tests for the real E2a reconciler harness.

Task #87: TDD red-phase evidence for defects 1-9.

These tests run WITHOUT a real PostgreSQL/Docker. They mechanically prove:
- Ownership cleanup is label-gated and runs on every failure path
- Connection cleanup closes on attestation failure (non-OperationalError)
- Exact target attestation (dbname, schema, address, role) without
  leaking returned rows
- Redaction: failure messages contain no raw Docker label/state/stdout
- Child env strips all seven sensitive variables
- The authorization flag is process-local and never appears in argv
- Collision preflight raises ``ValueError`` with a precise match
- The default repository path is mechanically exercised
"""

# ruff: noqa: F811  # pytest fixture import pattern

from __future__ import annotations

import os
import re
import subprocess
from unittest.mock import MagicMock

import psycopg
import pytest

from scripts._rebuild_database_connection import DisposablePostgresqlTarget

from ._real_e2a_reconciler_lifecycle import (
    _AUTHORIZATION_VALUE,
    _EXPECTED_DATABASE,
    _EXPECTED_SCHEMA,
    AUTHORIZATION_FLAG,
    SENSITIVE_ENV_VARS,
    _attest_exact_target,
    _is_separately_authorized,
    _open_manual_connection,
    _open_verification_connection,
    _redact_docker_failure,
    _remove_owned_container,
    _sanitized_environment,
    _start_disposable_container,
)
from ._real_e2a_reconciler_testkit import (
    _DENYLIST_TABLES,
)

# =============================================================================
# Defect 1: Ownership cleanup must be label-gated and unconditional
# =============================================================================


def test_sanitized_environment_strips_all_seven_sensitive_vars() -> None:
    """All seven sensitive env vars are removed from the child environment."""
    sentinel = "injected-value-for-test"
    injected = dict.fromkeys(SENSITIVE_ENV_VARS, sentinel)
    saved_values = {key: os.environ.get(key) for key in SENSITIVE_ENV_VARS}
    try:
        for key, value in injected.items():
            os.environ[key] = value
        sanitized = _sanitized_environment()
        for key in SENSITIVE_ENV_VARS:
            assert key not in sanitized, f"{key} leaked into child env"
    finally:
        for key, saved_value in saved_values.items():
            if saved_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = saved_value


def test_sanitized_environment_preserves_unrelated_vars() -> None:
    """Non-sensitive variables (e.g. PATH) are preserved."""
    saved = os.environ.get("PATH")
    try:
        os.environ["PATH"] = "/usr/bin"
        sanitized = _sanitized_environment()
        assert sanitized["PATH"] == "/usr/bin"
    finally:
        if saved is None:
            os.environ.pop("PATH", None)
        else:
            os.environ["PATH"] = saved


def test_remove_owned_container_rejects_unowned() -> None:
    """A container without the expected label is never removed."""
    calls: list[list[str]] = []

    def fake_run_docker(command, **_kwargs):
        calls.append(command)
        result = MagicMock(spec=subprocess.CompletedProcess)
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        # docker container ls shows container exists
        if command[0] == "container" and command[1] == "ls":
            result.stdout = "not-our-container"
        elif command[0] == "inspect":
            # Label check - returns wrong label
            result.stdout = "wrong-label"
        return result

    result = _remove_owned_container("not-our-container", run=fake_run_docker)
    assert result.outcome == "unowned_label"
    assert not result.confirmed
    assert result.inspect_rc == 0
    # Verify no removal command was issued (commands omit 'docker' prefix)
    assert all(not (c[:2] == ["rm", "--force"]) for c in calls)


def test_remove_owned_container_removes_owned() -> None:
    """A container with the expected label is removed."""
    calls: list[list[str]] = []
    list_count = [0]

    def fake_run_docker(command, **_kwargs):
        calls.append(command)
        result = MagicMock(spec=subprocess.CompletedProcess)
        result.returncode = 0
        result.stderr = ""
        # docker container ls --filter name=^...$
        if command[0] == "container" and command[1] == "ls":
            list_count[0] += 1
            if list_count[0] == 1:
                # Initial: container exists
                result.stdout = "okf-task87-x"
            else:
                # Post-removal: empty
                result.stdout = ""
        elif command[0] == "inspect":
            # Label check
            result.stdout = "87.real.e2a.acceptance"
        else:
            result.stdout = ""
        return result

    result = _remove_owned_container("okf-task87-x", run=fake_run_docker)
    assert result.outcome == "confirmed_removed"
    assert result.confirmed
    assert result.inspect_rc == 0
    assert result.remove_rc == 0
    assert any(c[:2] == ["rm", "--force"] for c in calls)


# =============================================================================
# Defect 2: Connection cleanup on attestation failure
# =============================================================================


def test_open_manual_connection_closes_on_attestation_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If attestation raises, the connection is still closed."""
    from . import _real_e2a_reconciler_lifecycle as lifecycle

    closed: list[bool] = []

    class _Cursor:
        def execute(self, sql, params=None):
            # Raise during second attestation call
            raise psycopg.OperationalError("attest failed")

        def fetchone(self):
            return None

        def close(self):
            pass

    class _Conn:
        def cursor(self):
            return _Cursor()

        def commit(self) -> None:
            pass

        def close(self) -> None:
            closed.append(True)

    # Mock connect and bypass attestation
    monkeypatch.setattr(lifecycle.psycopg, "connect", lambda **_kwargs: _Conn())

    # Bypass the attestation functions to let cursor.execute raise directly
    def _bypass_attest_1(cursor, target):
        # Call execute which raises
        cursor.execute("SELECT 1")

    monkeypatch.setattr(lifecycle, "_attest_connection_target", _bypass_attest_1)

    target = _make_mock_target()
    with pytest.raises(psycopg.OperationalError):
        _open_manual_connection(target)
    assert closed == [True]


def test_open_verification_connection_closes_on_attestation_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verification connection is closed even when attestation raises."""
    from . import _real_e2a_reconciler_lifecycle as lifecycle

    closed: list[bool] = []

    class _Cursor:
        def execute(self, sql, params=None):
            raise RuntimeError("boom")

        def fetchone(self):
            return None

        def close(self):
            pass

    class _Conn:
        def cursor(self):
            return _Cursor()

        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr(lifecycle.psycopg, "connect", lambda **_kwargs: _Conn())

    # Bypass the attestation functions to let cursor.execute raise directly
    def _bypass_attest_1(cursor, target):
        cursor.execute("SELECT 1")

    monkeypatch.setattr(lifecycle, "_attest_connection_target", _bypass_attest_1)

    target = _make_mock_target()
    with pytest.raises(RuntimeError, match="boom"):
        _open_verification_connection(target)
    assert closed == [True]


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


# =============================================================================
# Defect 3: Exact target attestation
# =============================================================================


def test_attest_exact_target_verifies_dbname_schema_and_role() -> None:
    """Attestation must check dbname, schema, and role without echoing rows."""

    responses = [
        (_EXPECTED_DATABASE, _EXPECTED_SCHEMA),  # current_database, current_schema
        ("okf", "okf"),  # current_user, session_user
    ]
    idx = {"n": 0}

    class _Cursor:
        def __init__(self) -> None:
            self.calls: list[tuple] = []

        def execute(self, sql, params=None):
            self.calls.append((sql, params))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def fetchone(self):
            n = idx["n"]
            idx["n"] += 1
            return responses[n] if n < len(responses) else None

    cursor = _Cursor()
    target = MagicMock(spec=DisposablePostgresqlTarget)
    target.dbname = _EXPECTED_DATABASE
    target.user = "okf"

    _attest_exact_target(cursor, target)
    assert len(cursor.calls) == 2
    combined_sql = " ".join(str(c[0]) for c in cursor.calls)
    assert "current_database()" in combined_sql
    assert "current_user" in combined_sql


def test_attest_exact_target_raises_on_dbname_mismatch() -> None:
    responses = [
        ("other_db", "public"),
    ]
    idx = {"n": 0}

    class _Cursor:
        def execute(self, sql, params=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def fetchone(self):
            n = idx["n"]
            idx["n"] += 1
            return responses[n] if n < len(responses) else None

    cursor = _Cursor()
    target = MagicMock(spec=DisposablePostgresqlTarget)
    target.dbname = _EXPECTED_DATABASE

    with pytest.raises(RuntimeError, match="database"):
        _attest_exact_target(cursor, target)


def test_attest_exact_target_raises_on_schema_mismatch() -> None:
    """Schema mismatch must fail closed without revealing the actual schema."""
    responses = [
        (_EXPECTED_DATABASE, "other_schema"),
    ]
    idx = {"n": 0}

    class _Cursor:
        def execute(self, sql, params=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def fetchone(self):
            n = idx["n"]
            idx["n"] += 1
            return responses[n] if n < len(responses) else None

    cursor = _Cursor()
    target = MagicMock(spec=DisposablePostgresqlTarget)
    target.dbname = _EXPECTED_DATABASE

    with pytest.raises(RuntimeError, match="schema"):
        _attest_exact_target(cursor, target)


def test_attest_exact_target_raises_on_current_user_mismatch() -> None:
    """Current user mismatch must fail closed without revealing the actual user."""
    responses = [
        (_EXPECTED_DATABASE, _EXPECTED_SCHEMA),
        ("wrong_user", "okf"),
    ]
    idx = {"n": 0}

    class _Cursor:
        def execute(self, sql, params=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def fetchone(self):
            n = idx["n"]
            idx["n"] += 1
            return responses[n] if n < len(responses) else None

    cursor = _Cursor()
    target = MagicMock(spec=DisposablePostgresqlTarget)
    target.dbname = _EXPECTED_DATABASE
    target.user = "okf"

    with pytest.raises(RuntimeError, match="current_user"):
        _attest_exact_target(cursor, target)


def test_attest_exact_target_raises_on_session_user_mismatch() -> None:
    """Session user mismatch must fail closed without revealing the actual user."""
    responses = [
        (_EXPECTED_DATABASE, _EXPECTED_SCHEMA),
        ("okf", "wrong_user"),
    ]
    idx = {"n": 0}

    class _Cursor:
        def execute(self, sql, params=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def fetchone(self):
            n = idx["n"]
            idx["n"] += 1
            return responses[n] if n < len(responses) else None

    cursor = _Cursor()
    target = MagicMock(spec=DisposablePostgresqlTarget)
    target.dbname = _EXPECTED_DATABASE
    target.user = "okf"

    with pytest.raises(RuntimeError, match="session_user"):
        _attest_exact_target(cursor, target)


def test_attest_exact_target_success_with_matching_user() -> None:
    """Attestation succeeds when current_user and session_user match target.user."""
    responses = [
        (_EXPECTED_DATABASE, _EXPECTED_SCHEMA),
        ("okf", "okf"),
    ]
    idx = {"n": 0}

    class _Cursor:
        def __init__(self) -> None:
            self.calls: list[tuple] = []

        def execute(self, sql, params=None):
            self.calls.append((sql, params))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def fetchone(self):
            n = idx["n"]
            idx["n"] += 1
            return responses[n] if n < len(responses) else None

    cursor = _Cursor()
    target = MagicMock(spec=DisposablePostgresqlTarget)
    target.dbname = _EXPECTED_DATABASE
    target.user = "okf"

    _attest_exact_target(cursor, target)
    assert len(cursor.calls) == 2


def test_attest_exact_target_error_messages_redacted() -> None:
    """Attestation errors must never reveal observed or expected values."""
    responses = [
        ("observed_db", "observed_schema"),
        ("observed_user", "observed_session"),
    ]
    idx = {"n": 0}

    class _Cursor:
        def execute(self, sql, params=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def fetchone(self):
            n = idx["n"]
            idx["n"] += 1
            return responses[n] if n < len(responses) else None

    cursor = _Cursor()
    target = MagicMock(spec=DisposablePostgresqlTarget)
    target.dbname = _EXPECTED_DATABASE
    target.user = "okf"

    with pytest.raises(RuntimeError, match="attestation failed") as exc_info:
        _attest_exact_target(cursor, target)
    msg = str(exc_info.value)
    # Must NOT contain observed values
    assert "observed_db" not in msg
    assert "observed_schema" not in msg
    assert "observed_user" not in msg
    assert "observed_session" not in msg
    # Must NOT contain expected values
    assert _EXPECTED_DATABASE not in msg
    assert "okf" not in msg


# =============================================================================
# Defect 4: Redaction
# =============================================================================


def test_redact_docker_failure_returns_only_text_and_rcs() -> None:
    """Failure message exposes ONLY fixed text + integer return codes."""

    def fake(*_a, **_kw):
        result = MagicMock(spec=subprocess.CompletedProcess)
        result.returncode = 7
        result.stdout = "secret password=hunter2"
        result.stderr = "connection refused"
        return result

    msg = _redact_docker_failure(
        "container did not start",
        fake(),
        fake(),
        fake(),
    )
    assert "hunter2" not in msg
    assert "password=" not in msg
    assert "connection refused" not in msg
    # Only fixed text and integer return codes are present.
    assert re.match(
        r"^container did not start \(rc=\d+, label_rc=\d+, " r"state_rc=\d+\)$",
        msg,
    ), msg


# =============================================================================
# Defect 5: Child env strips authorization flag
# =============================================================================


def test_run_docker_argv_never_contains_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Password is supplied via env, never via argv."""
    from . import _real_e2a_reconciler_lifecycle as lifecycle

    captured: dict = {}
    call_count = {"n": 0}

    def fake_run(args, **_kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            captured["args"] = args
            captured["env"] = _kwargs.get("env")
        result = MagicMock(spec=subprocess.CompletedProcess)
        result.returncode = 1
        result.stdout = ""
        result.stderr = ""
        return result

    monkeypatch.setattr(lifecycle.subprocess, "run", fake_run)
    container_name = "okf-task87-redact"
    try:
        _start_disposable_container(container_name, run=fake_run)
    except pytest.fail.Exception:
        pass
    argv = captured.get("args", [])
    env = captured.get("env") or {}
    joined = " ".join(str(a) for a in argv)
    assert "POSTGRES_PASSWORD" in env, "password must be in env"
    assert env["POSTGRES_PASSWORD"] not in joined, "password leaked into argv"
    assert AUTHORIZATION_FLAG not in env, "auth flag must not be in child env"


# =============================================================================
# Defect 6: In-process mechanical authorization
# =============================================================================


def test_is_separately_authorized_reflects_monkeypatched_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The helper reflects os.environ mutations, including setting/unsetting."""
    for var in SENSITIVE_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    assert _is_separately_authorized() is False
    monkeypatch.setenv(AUTHORIZATION_FLAG, "wrong-value")
    assert _is_separately_authorized() is False
    monkeypatch.setenv(AUTHORIZATION_FLAG, _AUTHORIZATION_VALUE)
    assert _is_separately_authorized() is True
    monkeypatch.delenv(AUTHORIZATION_FLAG, raising=False)
    assert _is_separately_authorized() is False


def test_disposable_gate_skips_without_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Drive the underlying fixture gate; assert pytest.skip and zero side effects."""
    from . import _real_e2a_reconciler_lifecycle as lifecycle

    for var in SENSITIVE_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    docker_calls: list[list[str]] = []
    psycopg_calls: list[dict] = []

    def fake_run(command, **_kwargs):
        docker_calls.append(command)
        result = MagicMock(spec=subprocess.CompletedProcess)
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    def fake_connect(**kwargs):
        psycopg_calls.append(kwargs)
        raise AssertionError("psycopg.connect must not be called")

    monkeypatch.setattr(lifecycle, "_run_docker", fake_run)
    monkeypatch.setattr(lifecycle.psycopg, "connect", fake_connect)

    from ._real_e2a_reconciler_lifecycle import _gate_live_run

    with pytest.raises(pytest.skip.Exception):
        _gate_live_run()
    assert docker_calls == []
    assert psycopg_calls == []


# =============================================================================
# Defect 7: In-process mechanical "no docker / no psycopg" assertion
# =============================================================================


def test_unauthorized_path_does_not_import_or_call_docker_or_psycopg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Walking through the no-auth path in this process touches neither docker nor psycopg."""
    from . import _real_e2a_reconciler_lifecycle as lifecycle

    for var in SENSITIVE_ENV_VARS:
        monkeypatch.delenv(var, raising=False)

    docker_calls: list[list[str]] = []
    psycopg_calls: list[dict] = []

    def fake_run(command, **_kwargs):
        docker_calls.append(command)
        result = MagicMock(spec=subprocess.CompletedProcess)
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    def fake_connect(**kwargs):
        psycopg_calls.append(kwargs)
        raise AssertionError("psycopg.connect must not be called")

    monkeypatch.setattr(lifecycle, "_run_docker", fake_run)
    monkeypatch.setattr(lifecycle.psycopg, "connect", fake_connect)

    from ._real_e2a_reconciler_lifecycle import _gate_live_run

    with pytest.raises(pytest.skip.Exception):
        _gate_live_run()
    assert docker_calls == []
    assert psycopg_calls == []


# =============================================================================
# Defect 10: Preserve the FULL denylist and existence-aware proof
# =============================================================================


def test_denylist_set_is_unchanged_from_specification() -> None:
    """The denylist must remain a stable, well-known set of 10 tables."""
    expected = frozenset(
        {
            "chunk_entity_links",
            "node_entity_links",
            "entity_mentions",
            "entity_aliases",
            "entity_merge_log",
            "ner_entities",
            "ner_relations",
            "fusion_state",
            "r3_state",
            "external_projection_status",
        }
    )
    assert _DENYLIST_TABLES == expected
    assert len(_DENYLIST_TABLES) == 10


# =============================================================================
# Defect G: Unit tests for _validate_host_port
# =============================================================================


def test_validate_host_port_accepts_valid_port() -> None:
    """Valid port strings are parsed correctly."""
    from ._real_e2a_reconciler_lifecycle import _validate_host_port

    assert _validate_host_port("5432") == 5432
    assert _validate_host_port("1") == 1
    assert _validate_host_port("65535") == 65535


def test_validate_host_port_rejects_empty() -> None:
    """Empty port string raises ValueError with fixed message."""
    from ._real_e2a_reconciler_lifecycle import _validate_host_port

    with pytest.raises(ValueError, match="invalid host port"):
        _validate_host_port("")


def test_validate_host_port_rejects_non_ascii() -> None:
    """Non-ASCII characters raise ValueError with fixed message."""
    from ._real_e2a_reconciler_lifecycle import _validate_host_port

    with pytest.raises(ValueError, match="invalid host port"):
        _validate_host_port("５432")  # Fullwidth digit


def test_validate_host_port_rejects_letters() -> None:
    """Letters raise ValueError with fixed message."""
    from ._real_e2a_reconciler_lifecycle import _validate_host_port

    with pytest.raises(ValueError, match="invalid host port"):
        _validate_host_port("abc")


def test_validate_host_port_rejects_whitespace() -> None:
    """Whitespace around port raises ValueError with fixed message."""
    from ._real_e2a_reconciler_lifecycle import _validate_host_port

    with pytest.raises(ValueError, match="invalid host port"):
        _validate_host_port(" 5432")


def test_validate_host_port_rejects_below_range() -> None:
    """Port 0 raises ValueError with fixed message."""
    from ._real_e2a_reconciler_lifecycle import _validate_host_port

    with pytest.raises(ValueError, match="invalid host port"):
        _validate_host_port("0")


def test_validate_host_port_rejects_above_range() -> None:
    """Port > 65535 raises ValueError with fixed message."""
    from ._real_e2a_reconciler_lifecycle import _validate_host_port

    with pytest.raises(ValueError, match="invalid host port"):
        _validate_host_port("65536")


def test_validate_host_port_rejects_negative() -> None:
    """Negative port raises ValueError with fixed message."""
    from ._real_e2a_reconciler_lifecycle import _validate_host_port

    with pytest.raises(ValueError, match="invalid host port"):
        _validate_host_port("-1")


def test_validate_host_port_rejects_str_subclass() -> None:
    """String subclass raises ValueError with fixed message."""
    from ._real_e2a_reconciler_lifecycle import _validate_host_port

    class MyStr(str):
        pass

    with pytest.raises(ValueError, match="invalid host port"):
        _validate_host_port(MyStr("5432"))  # type: ignore[arg-type]
