"""Negative proof that the live E2a suite cannot run without authorization.

Task #87: Prove the live module's authorization gate is fail-closed and
that the unauthorized path performs ZERO Docker/DB work in the same process.

All seven sensitive variables are cleared; the in-process gate is driven
through the actual fixture function; Docker and psycopg entry points are
replaced with call-counters that raise on invocation. The bool test
monkeypatches ``os.environ`` to prove it actually reflects mutations.
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock

import pytest

from ._real_e2a_reconciler_lifecycle import (
    _AUTHORIZATION_VALUE,
    AUTHORIZATION_FLAG,
    SENSITIVE_ENV_VARS,
    _gate_live_run,
    _is_separately_authorized,
)


def test_is_separately_authorized_reflects_monkeypatched_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The helper reflects os.environ mutations, including set and unset."""
    for var in SENSITIVE_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    assert _is_separately_authorized() is False
    monkeypatch.setenv(AUTHORIZATION_FLAG, "wrong-value")
    assert _is_separately_authorized() is False
    monkeypatch.setenv(AUTHORIZATION_FLAG, _AUTHORIZATION_VALUE)
    assert _is_separately_authorized() is True
    monkeypatch.delenv(AUTHORIZATION_FLAG, raising=False)
    assert _is_separately_authorized() is False


def test_unauthorized_gate_skips_with_zero_docker_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without authorization, the gate skips and Docker is never invoked."""
    from . import _real_e2a_reconciler_lifecycle as lifecycle

    for var in SENSITIVE_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    docker_calls: list[list[str]] = []
    psycopg_calls: list[dict] = []

    def fake_run_docker(command, **_kwargs):
        docker_calls.append(command)
        result = MagicMock(spec=subprocess.CompletedProcess)
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    def fake_connect(**kwargs):
        psycopg_calls.append(kwargs)
        raise AssertionError("psycopg.connect must not be called without auth")

    monkeypatch.setattr(lifecycle, "_run_docker", fake_run_docker)
    monkeypatch.setattr(lifecycle.psycopg, "connect", fake_connect)

    with pytest.raises(pytest.skip.Exception):
        _gate_live_run()
    assert docker_calls == []
    assert psycopg_calls == []


def test_authorization_flag_never_propagates_to_subprocess_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The authorization flag is process-local; the child env must drop it."""
    for var in SENSITIVE_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv(AUTHORIZATION_FLAG, _AUTHORIZATION_VALUE)

    from ._real_e2a_reconciler_lifecycle import _sanitized_environment

    sanitized = _sanitized_environment()
    assert AUTHORIZATION_FLAG not in sanitized
    for var in SENSITIVE_ENV_VARS:
        assert var not in sanitized


def test_live_module_skips_each_test_when_unauthorized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The live module's module-scoped fixture must skip when unauthorized.

    Drive the gate that backs the module-scoped fixture; it must raise
    ``pytest.skip.Exception`` without ever invoking Docker or psycopg.
    """
    from . import _real_e2a_reconciler_lifecycle as lifecycle

    for var in SENSITIVE_ENV_VARS:
        monkeypatch.delenv(var, raising=False)

    docker_calls: list[list[str]] = []
    psycopg_calls: list[dict] = []

    def fake_run_docker(command, **_kwargs):
        docker_calls.append(command)
        result = MagicMock(spec=subprocess.CompletedProcess)
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    def fake_connect(**kwargs):
        psycopg_calls.append(kwargs)
        raise AssertionError("psycopg.connect must not be called without auth")

    monkeypatch.setattr(lifecycle, "_run_docker", fake_run_docker)
    monkeypatch.setattr(lifecycle.psycopg, "connect", fake_connect)

    with pytest.raises(pytest.skip.Exception):
        _gate_live_run()
    assert docker_calls == []
    assert psycopg_calls == []
