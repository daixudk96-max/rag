"""Private support module for Docker/connection lifecycle.

Task #87: Split the lifecycle primitives (container, env, connection, gate)
into their own cohesive file so the testkit stays under the 800-line limit.
All symbols in this module are intended to be reused by the live acceptance
suite and the mechanical in-process authorization proof.

Design:
- Reuses ``DisposablePostgresqlTarget``/``parse_disposable_postgresql_target``
  from ``scripts._rebuild_database_connection`` to avoid string-formatting
  URIs and to keep the raw URI process-local.
- Every connection is opened via ``runtime_connection_kwargs`` and
  attests the exact dbname / schema / address / role before use.
- Authorization check, sanitized environment, and label-gated cleanup are
  exposed as small primitives so the in-process mechanical tests can drive
  them without spawning pytest in a subprocess.
- No raw rows / connection strings / credentials appear in any log or assertion.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Protocol, cast

import psycopg
import pytest

from llamaindex_runtime.okf.e2a_disposable_acceptance import _attest_connection_target
from scripts._rebuild_database_connection import (
    DisposablePostgresqlTarget,
    parse_disposable_postgresql_target,
    reject_ambient_service_routing,
    runtime_connection_factory,
    runtime_connection_kwargs,
)

from ._real_e2a_reconciler_container_cleanup import (
    _CLEANUP_FAILURE_MESSAGE,
    _CONTAINER_LABEL_KEY,
    _CONTAINER_LABEL_VALUE,
    _LIFECYCLE_CLEANUP_MESSAGE,
    RunDocker,
    _compose_failures,
    _exact_name_list_container,
    _remove_owned_container,
    _validate_exact_returncode,
)

# Re-exported for convenience; matches the env-var denylist in
# _rebuild_cli_testkit plus the live authorization flag (defect 5).
SENSITIVE_ENV_VARS: tuple[str, ...] = (
    "DATABASE_URL",
    "FORMAL_RUNTIME_DATABASE_URL",
    "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE",
    "OKF_REBUILD_EXPECTED_DATABASE",
    "OKF_FAILURE_AUDIT_ACCEPTANCE",
    "OKF_REBUILD_DOCKER_ACCEPTANCE",
    "OKF_E2A_DISPOSABLE_TEST_AUTHORIZED",
)
_SENSITIVE_ENV_VARS_SET = frozenset(SENSITIVE_ENV_VARS)

# Authorization constants.
AUTHORIZATION_FLAG = "OKF_E2A_DISPOSABLE_TEST_AUTHORIZED"
_AUTHORIZATION_VALUE = "separately-authorized"

# Docker / container constants (label/image kept in container_cleanup module).
_CONTAINER_IMAGE = "pgvector/pgvector:pg16"
_DOCKER_TIMEOUT = 60
_EXPECTED_DATABASE = "okf_task87"
_EXPECTED_SCHEMA = "public"
_LOOPBACK_HOST = "127.0.0.1"


class _CursorProto(Protocol):
    """Minimal psycopg cursor protocol used by the attest wrapper.

    Note: This protocol only defines execute/fetchone for attestation.
    Context manager methods are intentionally omitted to avoid
    incompatibility with psycopg.Cursor[Any] signatures.
    """

    def execute(self, sql: Any, params: Any = ...) -> Any: ...

    def fetchone(self) -> tuple[Any, ...] | None: ...


def _is_separately_authorized() -> bool:
    """Return True only when the live authorization flag is exactly correct."""
    return os.environ.get(AUTHORIZATION_FLAG) == _AUTHORIZATION_VALUE


def _sanitized_environment() -> dict[str, str]:
    """Return a child environment stripped of every sensitive variable."""
    return {
        key: value
        for key, value in os.environ.items()
        if key not in _SENSITIVE_ENV_VARS_SET
    }


def _run_docker(
    command: list[str],
    *,
    timeout: int = _DOCKER_TIMEOUT,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Execute ``docker`` with a sanitized environment and bounded timeout."""
    return subprocess.run(
        ["docker", *command],
        capture_output=True,
        check=False,
        text=True,
        timeout=timeout,
        env=env if env is not None else _sanitized_environment(),
    )


def _owned_container_name() -> str:
    """A unique container name keyed off this test session."""
    import uuid as _uuid

    return f"okf-task87-{_uuid.uuid4().hex}"


def _build_docker_env(password: str) -> dict[str, str]:
    """Build the child environment for Docker, stripping sensitive vars."""
    return _sanitized_environment() | {"POSTGRES_PASSWORD": password}


def _redact_docker_failure(
    message: str,
    primary: subprocess.CompletedProcess[str],
    label: subprocess.CompletedProcess[str],
    state: subprocess.CompletedProcess[str],
) -> str:
    """Build a fixed-text failure message with only integer return codes."""
    return (
        f"{message} "
        f"(rc={primary.returncode}, "
        f"label_rc={label.returncode}, "
        f"state_rc={state.returncode})"
    )


def _start_disposable_container(
    container_name: str,
    *,
    run: RunDocker = _run_docker,
) -> DisposablePostgresqlTarget:
    """Start a pgvector container and return a parsed target.

    Note: This function is kept for compatibility with existing tests.
    Prefer `_yield_disposable_target` for the full lifecycle envelope.
    """
    import uuid as _uuid

    password = _uuid.uuid4().hex
    env = _build_docker_env(password)
    run_result = run(
        [
            "run",
            "--detach",
            "--name",
            container_name,
            "--label",
            f"{_CONTAINER_LABEL_KEY}={_CONTAINER_LABEL_VALUE}",
            "--publish",
            f"{_LOOPBACK_HOST}::5432",
            "--env",
            f"POSTGRES_DB={_EXPECTED_DATABASE}",
            "--env",
            "POSTGRES_USER=okf",
            "--env",
            "POSTGRES_PASSWORD",
            _CONTAINER_IMAGE,
        ],
        env=env,
    )
    # Validate returncode is exact int
    run_rc = _validate_exact_returncode(run_result.returncode)
    if run_rc != 0:
        # Do NOT clean up here - caller owns lifecycle
        raise pytest.fail.Exception(f"Unable to start container (rc={run_rc})")
    # Inspect port
    inspect_result = run(
        [
            "inspect",
            "--format",
            '{{ (index .NetworkSettings.Ports "5432/tcp" 0).HostPort }}',
            container_name,
        ]
    )
    inspect_rc = _validate_exact_returncode(inspect_result.returncode)
    if inspect_rc != 0 or not inspect_result.stdout.strip():
        label = run(
            [
                "inspect",
                "--format",
                f'{{{{ index .Config.Labels "{_CONTAINER_LABEL_KEY}" }}}}',
                container_name,
            ]
        )
        state = run(["inspect", "--format", "{{ .State.Status }}", container_name])
        # Do NOT clean up here - caller owns lifecycle
        raise pytest.fail.Exception(
            _redact_docker_failure(
                "Unable to determine the allocated host port",
                inspect_result,
                label,
                state,
            )
        )
    port_text = inspect_result.stdout.strip()
    try:
        port = _validate_host_port(port_text)
    except ValueError:
        # Do NOT clean up here - caller owns lifecycle
        raise pytest.fail.Exception("Invalid host port from Docker")
    # Parse target
    raw_url = (
        f"postgresql://okf:{password}@{_LOOPBACK_HOST}:{port}/{_EXPECTED_DATABASE}"
    )
    return parse_disposable_postgresql_target(raw_url, _EXPECTED_DATABASE)


def _validate_host_port(port_text: str) -> int:
    """Validate and parse host port; raise on invalid input.

    Requirements:
    - type(port_text) is str (rejects str subclasses)
    - ASCII decimal digits only, no whitespace/sign/Unicode
    - Range 1..65535

    Every invalid input raises ValueError with ONE fixed redacted message.
    """
    if type(port_text) is not str:
        raise ValueError("invalid host port")
    if not port_text:
        raise ValueError("invalid host port")
    # Check whitespace
    if port_text != port_text.strip():
        raise ValueError("invalid host port")
    # Check ASCII decimal digits only
    if not port_text.isascii() or not port_text.isdigit():
        raise ValueError("invalid host port")
    port = int(port_text)
    if port < 1 or port > 65535:
        raise ValueError("invalid host port")
    return port


def _attest_exact_target(
    cursor: _CursorProto,
    target: DisposablePostgresqlTarget,
) -> None:
    """Attest dbname, schema, and role without echoing rows.

    Security:
    - ``parse_disposable_postgresql_target`` validates hostname == '127.0.0.1'
      at URI parse time, ensuring client-side loopback binding.
    - ``_attest_connection_target`` checks database and schema match.
    - This function additionally verifies current_user and session_user match
      the expected role, preventing privilege escalation.

    Errors are fixed text only; observed/expected values are never revealed.
    """
    cursor.execute("SELECT current_database(), current_schema()")
    row = cursor.fetchone()
    dbname, schema = (row[0], row[1]) if row else (None, None)
    if dbname != target.dbname:
        raise RuntimeError("attestation failed: database mismatch")
    if schema != _EXPECTED_SCHEMA:
        raise RuntimeError("attestation failed: schema mismatch")
    cursor.execute("SELECT current_user, session_user")
    row = cursor.fetchone()
    current_user, session_user = (row[0], row[1]) if row else (None, None)
    if current_user != target.user:
        raise RuntimeError("attestation failed: current_user mismatch")
    if session_user != target.user:
        raise RuntimeError("attestation failed: session_user mismatch")


def _open_attested_connection(
    target: DisposablePostgresqlTarget,
    *,
    autocommit: bool,
) -> psycopg.Connection[Any]:
    """Open a connection and attest; preserve failures deterministically.

    Single deterministic cleanup protocol:

    1. connect/cursor/attestation/commit primary-only: re-raise exact exception object
    2. Any cleanup failure: sanitized RuntimeError("connection cleanup failed")
    3. primary+cleanup group: [exact primary, sanitized cleanup]
       - All Exception -> ExceptionGroup
       - Any non-Exception BaseException -> BaseExceptionGroup
    4. cleanup-only: fixed RuntimeError
    5. Success: return open conn, cursor confirmed closed, manual commit succeeded

    Never exposes raw cleanup exception/message.
    """
    reject_ambient_service_routing(os.environ)
    kwargs = runtime_connection_kwargs(target, autocommit=autocommit)

    # Open connection - failure needs no cleanup
    conn = psycopg.connect(**cast(Any, kwargs))

    primary_exc: BaseException | None = None
    cursor_closed = False

    try:
        # Phase 1: Cursor creation
        try:
            cursor = conn.cursor()
        except BaseException as e:
            primary_exc = e
            # Cursor creation failure: must attempt conn.close
            conn_closed = _close_conn_silently(conn)
            if not conn_closed:
                # Cursor creation + conn.close failure: compose group
                raise _compose_cleanup_failure(primary_exc)
            # Cursor creation failure + successful close: re-raise exact primary
            raise primary_exc

        # Phase 2: Attestation
        try:
            _attest_connection_target(cursor, target)
            _attest_exact_target(cursor, target)
        except BaseException as e:
            primary_exc = e

        # Phase 3: Close cursor (always attempted after cursor creation success)
        try:
            cursor.close()
            cursor_closed = True
        except BaseException:
            pass  # cursor.close failure tracked by cursor_closed=False

        # Phase 4: Handle attestation failure
        if primary_exc is not None:
            conn_closed = _close_conn_silently(conn)
            # If ANY cleanup failed (cursor or conn), compose group
            if not cursor_closed or not conn_closed:
                raise _compose_cleanup_failure(primary_exc)
            # Attestation failure + successful cleanup: re-raise exact primary
            raise primary_exc

        # Phase 5: Cursor close failed after successful attestation
        # Requirement: ONE fixed cleanup-only RuntimeError, regardless of conn.close
        if not cursor_closed:
            # Always attempt conn.close for hygiene, but result doesn't change outcome
            _close_conn_silently(conn)
            raise RuntimeError(_CLEANUP_FAILURE_MESSAGE)

        # Phase 6: Commit for manual transactions
        if not autocommit:
            try:
                conn.commit()
            except BaseException as e:
                primary_exc = e
                conn_closed = _close_conn_silently(conn)
                if not conn_closed:
                    # Commit + conn.close failure: compose group
                    raise _compose_cleanup_failure(primary_exc)
                # Commit failure + successful close: re-raise exact primary
                raise primary_exc

        return conn

    except BaseException:
        raise


def _close_conn_silently(conn: psycopg.Connection[Any]) -> bool:
    """Close connection; return True if successful."""
    try:
        conn.close()
        return True
    except BaseException:
        return False


def _compose_cleanup_failure(primary: BaseException | None) -> BaseException:
    """Compose primary + cleanup failure; never None."""
    result = _compose_failures(primary, _CLEANUP_FAILURE_MESSAGE)
    if result is None:
        return RuntimeError(_CLEANUP_FAILURE_MESSAGE)
    return result


def _open_manual_connection(
    target: DisposablePostgresqlTarget,
) -> psycopg.Connection[Any]:
    """Open a manual (autocommit=False) attested connection."""
    return _open_attested_connection(target, autocommit=False)


def _open_verification_connection(
    target: DisposablePostgresqlTarget,
) -> psycopg.Connection[Any]:
    """Open an autocommit verification connection with attestation."""
    return _open_attested_connection(target, autocommit=True)


def _wait_for_database(target: DisposablePostgresqlTarget) -> None:
    """Wait for the disposable database to accept connections.

    Closes each probe connection properly; never leaks connections.
    Cleanup failures are composed with primary exceptions.
    """
    reject_ambient_service_routing(os.environ)
    close_failed = False

    for _ in range(30):
        conn = None
        close_failed = False

        try:
            conn = _open_attested_connection(target, autocommit=True)
            # Success - close and return
        except psycopg.OperationalError:
            import time as _time

            _time.sleep(1)
            continue
        except BaseException:
            # Non-OperationalError: propagate immediately
            raise
        finally:
            if conn is not None:
                try:
                    conn.close()
                except BaseException:
                    close_failed = True

        # Check for cleanup failure after successful probe
        if close_failed:
            raise RuntimeError(_CLEANUP_FAILURE_MESSAGE)

        return

    raise RuntimeError("disposable database did not become ready")


def _apply_migrations_once(target: DisposablePostgresqlTarget) -> None:
    """Apply the full E2a migration catalog to the disposable database."""
    from llamaindex_runtime.okf.e2a_disposable_execution import (
        _apply_catalog,
    )

    _apply_catalog(target, runtime_connection_factory)


def _gate_live_run(
    *,
    run: RunDocker = _run_docker,
) -> None:
    """Authorization + Docker-availability gate; raises pytest.skip on failure."""
    if not _is_separately_authorized():
        pytest.skip(
            f"set {AUTHORIZATION_FLAG}={_AUTHORIZATION_VALUE} for live E2a tests"
        )
    if shutil.which("docker") is None:
        pytest.skip("Docker is unavailable for live E2a tests")
    info_result = run(["info"])
    info_rc = _validate_exact_returncode(info_result.returncode)
    if info_rc != 0:
        pytest.skip("Docker daemon is unavailable for live E2a tests")


@contextmanager
def _yield_disposable_target(
    *,
    container_name: str,
    run: RunDocker = _run_docker,
) -> Iterator[DisposablePostgresqlTarget]:
    """Own the full lifecycle: allocate name, start, parse, ready, yield, cleanup.

    Single envelope covering all setup stages:
    - docker run
    - port inspect
    - port validation
    - target parse
    - database readiness
    - migration application
    - body execution

    Every path gets cleanup exactly once (even if docker run raises/fails).
    Cleanup uses exact-name listing for mechanical proof.

    Exception handling:
    - Body/setup-only: re-raise exact exception object
    - Cleanup-only: fixed RuntimeError
    - Both: ExceptionGroup/BaseExceptionGroup with [exact primary, sanitized cleanup]
    - BaseException primary (KeyboardInterrupt, SystemExit): BaseExceptionGroup
    """
    import uuid as _uuid

    password = _uuid.uuid4().hex
    target: DisposablePostgresqlTarget | None = None
    primary_exc: BaseException | None = None

    try:
        # Stage 1: docker run
        env = _build_docker_env(password)
        run_result = run(
            [
                "run",
                "--detach",
                "--name",
                container_name,
                "--label",
                f"{_CONTAINER_LABEL_KEY}={_CONTAINER_LABEL_VALUE}",
                "--publish",
                f"{_LOOPBACK_HOST}::5432",
                "--env",
                f"POSTGRES_DB={_EXPECTED_DATABASE}",
                "--env",
                "POSTGRES_USER=okf",
                "--env",
                "POSTGRES_PASSWORD",
                _CONTAINER_IMAGE,
            ],
            env=env,
        )
        run_rc = _validate_exact_returncode(run_result.returncode)
        if run_rc != 0:
            raise pytest.fail.Exception("unable to start container")

        # Stage 2: port inspect
        inspect_result = run(
            [
                "inspect",
                "--format",
                '{{ (index .NetworkSettings.Ports "5432/tcp" 0).HostPort }}',
                container_name,
            ]
        )
        inspect_rc = _validate_exact_returncode(inspect_result.returncode)
        if inspect_rc != 0 or not inspect_result.stdout.strip():
            raise pytest.fail.Exception("unable to determine host port")

        # Stage 3: port validation
        port_text = inspect_result.stdout.strip()
        port = _validate_host_port(port_text)

        # Stage 4: target parse
        raw_url = (
            f"postgresql://okf:{password}@{_LOOPBACK_HOST}:{port}/{_EXPECTED_DATABASE}"
        )
        target = parse_disposable_postgresql_target(raw_url, _EXPECTED_DATABASE)

        # Stage 5: database readiness
        _wait_for_database(target)

        # Stage 6: migration
        _apply_migrations_once(target)

        # Stage 7: yield to test
        yield target

    except BaseException as e:
        primary_exc = e
        raise
    finally:
        # Cleanup: ALWAYS attempt exactly once (container may exist even if run failed)
        try:
            cleanup_result = _remove_owned_container(container_name, run=run)
        except BaseException:
            # Sanitize cleanup exceptions
            cleanup_result = None

        # Compose failures if cleanup didn't confirm
        if cleanup_result is None or not cleanup_result.confirmed:
            composed = _compose_failures(primary_exc, _LIFECYCLE_CLEANUP_MESSAGE)
            if composed is not None:
                raise composed


@pytest.fixture(scope="module")
def disposable_postgres_target() -> Iterator[DisposablePostgresqlTarget]:
    """Start/teardown a disposable PostgreSQL container for real acceptance tests.

    Authorization gate: requires ``OKF_E2A_DISPOSABLE_TEST_AUTHORIZED=separately-authorized``.
    Cleanup is label-gated; the full URI never appears in any log or assertion.
    """
    _gate_live_run()
    container_name = _owned_container_name()
    with _yield_disposable_target(container_name=container_name) as target:
        yield target


__all__ = [
    "AUTHORIZATION_FLAG",
    "SENSITIVE_ENV_VARS",
    "_AUTHORIZATION_VALUE",
    "_EXPECTED_DATABASE",
    "_is_separately_authorized",
    "_sanitized_environment",
    "_run_docker",
    "_owned_container_name",
    "_redact_docker_failure",
    "_start_disposable_container",
    "_validate_host_port",
    # Re-exported from _real_e2a_reconciler_container_cleanup
    "_compose_failures",
    "_validate_exact_returncode",
    "_exact_name_list_container",
    "_remove_owned_container",
    "_attest_exact_target",
    "_open_manual_connection",
    "_open_verification_connection",
    "_wait_for_database",
    "_apply_migrations_once",
    "_gate_live_run",
    "_yield_disposable_target",
    "disposable_postgres_target",
]
