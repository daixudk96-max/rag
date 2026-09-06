"""Lifecycle and session management for Phase 15 E2A harness (Task #132).

This module provides public DisposableE2aSession context manager, container lifecycle,
migration execution, failure composition, and resource management helpers.

Contract: Never import from e2a_disposable_execution or e2a_disposable_acceptance.
"""

from __future__ import annotations

import builtins
import importlib.resources
import logging
import subprocess
import tempfile
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Literal,
    Mapping,
    NamedTuple,
    Protocol,
    Sequence,
    cast,
)

import psycopg

from ._phase15_e2a_harness_types import (
    ContainerPresenceResult,
    _ATTESTATION_ERROR,
    _CLEANUP_ERROR,
    _require_authorization,
    _sanitized_env_copy,
    _validate_container_id,
    _validate_container_name,
    _validate_host_port_str,
    _validate_ownership_token,
    _validate_returncode,
    _generate_ownership_token,
    _validate_env_value,
    _validate_disposable_image,
    _normalize_docker_run_id,
    TRUSTED_DISPOSABLE_IMAGE,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)


def _build_docker_command(
    subcommand_args: Sequence[str],
    config_dir: str,
) -> list[str]:
    """Build Docker command with global isolation prefix.

    Args:
        subcommand_args: Docker subcommand and its arguments (e.g., ['ps', '-a'])
        config_dir: Path to session-owned empty config directory

    Returns:
        Full Docker command list with isolation prefix

    Security:
        - Every production Docker invocation must use this helper
        - Ensures --config and --context default are always present
        - Prevents Docker from reading user config or context files
        - Caller must clean up result/args locals before raising
    """
    return [
        "docker",
        "--config",
        config_dir,
        "--context",
        "default",
    ] + list(subcommand_args)


class DockerRunner(Protocol):
    """Protocol for Docker runner function."""

    def __call__(
        self,
        args: Sequence[str],
        *,
        capture_output: bool = ...,
        text: bool = ...,
        check: bool = ...,
        env: Mapping[str, str] | None = ...,
    ) -> subprocess.CompletedProcess[str]: ...


class ConnectionFactory(Protocol):
    """Protocol for connection factory function."""

    def __call__(
        self,
        host: str,
        port: int,
        database: str,
        user: str,
        password: str | None = None,
        **kwargs: Any,
    ) -> psycopg.Connection[tuple[Any, ...]]: ...


class SleepFunction(Protocol):
    """Protocol for sleep function."""

    def __call__(self, seconds: float) -> None: ...


class TokenFactory(Protocol):
    """Protocol for ownership token factory."""

    def __call__(self) -> str: ...


def _observe_container_presence(
    name: str,
    *,
    config_dir: str,
    run: Callable[..., subprocess.CompletedProcess[str]],
    env: Mapping[str, str] | None = None,
) -> ContainerPresenceResult:
    """Observe container presence with EXACT parsing.

    EXACT parsing rules:
    - Empty string: confirmed_absent
    - All-whitespace (spaces/tabs/LF/CRLF only): confirmed_absent
    - Non-whitespace: must be EXACTLY "expected_name\\t<64-hex>" with:
      - No leading/trailing whitespace
      - No extra content before or after
      - Ending: either none, single LF, or single CRLF
      - NO embedded CR/LF in the record itself
      - NO extra blank lines
      - NO multiple records
    - Any deviation: ambiguous_output (fail closed)

    Security: Uses --config and --context default for isolation.
    """
    try:
        validated_name = _validate_container_name(name)
    except ValueError:
        return ContainerPresenceResult(
            status="inspection_failure", rc=None, error_message="Invalid container name"
        )

    try:
        result = run(
            _build_docker_command(
                [
                    "ps",
                    "-a",
                    "--no-trunc",
                    "--format",
                    "{{.Names}}	{{.ID}}",
                    "--filter",
                    f"name={validated_name}",
                ],
                config_dir,
            ),
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
    except Exception:
        return ContainerPresenceResult(
            status="inspection_failure", rc=None, error_message="Docker runner failed"
        )

    try:
        rc = _validate_returncode(result.returncode)
    except ValueError:
        return ContainerPresenceResult(
            status="inspection_failure", rc=None, error_message="Invalid return code"
        )

    if rc != 0:
        return ContainerPresenceResult(
            status="inspection_failure", rc=rc, error_message="Docker inspect failed"
        )

    stdout = result.stdout if result.stdout else ""

    # === EXACT PARSING: Character-by-character ===

    # Case 1: Empty string is confirmed_absent
    if stdout == "":
        return ContainerPresenceResult(status="confirmed_absent", rc=0)

    # Case 2: All-whitespace is confirmed_absent
    # Check each character - only spaces, tabs, LF, CR allowed
    all_whitespace = True
    for ch in stdout:
        if ch not in " \t\n\r":
            all_whitespace = False
            break

    if all_whitespace:
        return ContainerPresenceResult(status="confirmed_absent", rc=0)

    # Case 3: Non-whitespace content - must be EXACTLY one valid record

    # Determine the record and ending
    # Valid endings: no ending, single \n, single \r\n
    record: str

    if stdout.endswith("\r\n"):
        # Has CRLF ending
        record = stdout[:-2]
    elif stdout.endswith("\n"):
        # Has LF ending
        record = stdout[:-1]
    else:
        # No ending
        record = stdout

    # After removing ending, check for embedded CR/LF in record
    if "\n" in record or "\r" in record:
        return ContainerPresenceResult(
            status="ambiguous_output",
            rc=0,
            error_message="Embedded line ending in record",
        )

    # Check for leading/trailing whitespace in record
    if record != record.strip(" \t"):
        return ContainerPresenceResult(
            status="ambiguous_output",
            rc=0,
            error_message="Leading/trailing whitespace in record",
        )

    # Check if record is empty (e.g., input was just "\n" or "\r\n")
    if not record:
        return ContainerPresenceResult(
            status="ambiguous_output",
            rc=0,
            error_message="Empty record with line ending",
        )

    # Parse the record: must be exactly "name\t<id>"
    parts = record.split("\t")
    if len(parts) != 2:
        return ContainerPresenceResult(
            status="ambiguous_output",
            rc=0,
            error_message="Malformed record: expected exactly 2 tab-separated fields",
        )

    container_name, container_id = parts

    # Check name matches
    if container_name != validated_name:
        return ContainerPresenceResult(
            status="ambiguous_output",
            rc=0,
            error_message="Unexpected container name",  # Fixed redacted message
        )

    # Validate container ID format
    try:
        validated_id = _validate_container_id(container_id)
    except ValueError:
        return ContainerPresenceResult(
            status="ambiguous_output", rc=0, error_message="Invalid container ID format"
        )

    # SUCCESS: exact match
    return ContainerPresenceResult(status="present", rc=0, container_id=validated_id)


def _remove_container_by_id(
    container_id: str,
    *,
    config_dir: str,
    run: Callable[..., subprocess.CompletedProcess[str]],
    env: Mapping[str, str] | None = None,
) -> bool:
    """Remove container by exact full 64-hex ID.

    Security: Uses --config and --context default for isolation.
    """
    try:
        validated_id = _validate_container_id(container_id)
    except ValueError:
        return False

    try:
        result = run(
            _build_docker_command(["rm", "-f", validated_id], config_dir),
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
    except Exception:
        return False

    try:
        rc = _validate_returncode(result.returncode)
    except ValueError:
        return False

    return rc == 0


@dataclass(frozen=True)
class FullInspectResult:
    """Result of structured full container inspection.

    Security: All Docker-derived values (container_id, name, host_ip, host_port)
    are redacted in repr/str to prevent disclosure in logs/tracebacks.
    """

    container_id: str
    name: str
    owner: str = field(repr=False)  # Exclude owner token from repr for security
    host_ip: str
    host_port: int
    valid: bool

    def __repr__(self) -> str:
        """Fully redacted repr - no Docker-derived values disclosed."""
        return f"FullInspectResult(valid={self.valid}, container_id=<redacted>, name=<redacted>, host_ip=<redacted>, host_port=<redacted>)"

    def __str__(self) -> str:
        """Fully redacted str - no sensitive values disclosed."""
        return f"FullInspectResult(valid={self.valid})"


_INVALID_INSPECT = FullInspectResult(
    container_id="", name="", owner="", host_ip="", host_port=0, valid=False
)


def _full_container_inspect(
    container_id: str,
    expected_name: str,
    expected_token: str,
    expected_port: int,
    *,
    config_dir: str,
    run: Callable[..., subprocess.CompletedProcess[str]],
    env: Mapping[str, str] | None = None,
) -> FullInspectResult:
    """Structured full inspect verifying ID, name, owner, HostIp, and port.

    Security:
        - Requests ONLY necessary fields, never captures Config.Env
        - Uses minimal structured format instead of raw {{json .}}
        - Uses --config and --context default for isolation
        - Exact parsing: no strip(), validates ending strictly
    """
    try:
        validated_id = _validate_container_id(container_id)
    except ValueError:
        return _INVALID_INSPECT

    # Use minimal structured format that extracts only needed fields
    minimal_format = (
        "{{.Id}}|{{.Name}}|{{.Config.Labels.owner}}|"
        "{{range $k, $v := .NetworkSettings.Ports}}"
        '{{if eq $k "5432/tcp"}}{{range $v}}{{.HostIp}}:{{.HostPort}}{{end}}{{end}}'
        "{{end}}"
    )

    try:
        result = run(
            _build_docker_command(
                ["inspect", validated_id, "--format", minimal_format], config_dir
            ),
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
    except Exception:
        return _INVALID_INSPECT

    try:
        rc = _validate_returncode(result.returncode)
    except ValueError:
        return _INVALID_INSPECT

    if rc != 0:
        return _INVALID_INSPECT

    # EXACT parsing: character-by-character validation
    stdout = result.stdout if result.stdout else ""
    if not stdout:
        return _INVALID_INSPECT

    # Valid endings: no ending, single LF, or single CRLF
    record: str
    if len(stdout) >= 2 and stdout[-2:] == "\r\n":
        # CRLF ending - valid
        record = stdout[:-2]
    elif len(stdout) >= 1 and stdout[-1] == "\n":
        # LF ending - valid
        record = stdout[:-1]
    elif "\r" in stdout or "\n" in stdout:
        # Bare CR, LFCR, embedded CR/LF, or multiple endings - INVALID
        return _INVALID_INSPECT
    else:
        # No ending - valid
        record = stdout

    # Reject empty record
    if not record:
        return _INVALID_INSPECT

    # Reject any remaining CR/LF in record (embedded)
    if "\r" in record or "\n" in record:
        return _INVALID_INSPECT

    # Reject trailing whitespace in record
    if record.endswith(" ") or record.endswith("\t"):
        return _INVALID_INSPECT

    # Expected format: <id>|/<name>|<owner>|<host_ip>:<host_port>
    parts = record.split("|")
    if len(parts) != 4:
        return _INVALID_INSPECT

    actual_id, name_raw, owner, port_binding = parts

    # Verify ID matches exactly
    if actual_id != validated_id:
        return _INVALID_INSPECT

    # Verify name
    if not name_raw or not name_raw.startswith("/"):
        return _INVALID_INSPECT
    actual_name = name_raw[1:]
    if actual_name != expected_name:
        return _INVALID_INSPECT

    # Verify owner token
    if owner != expected_token:
        return _INVALID_INSPECT

    # Parse port binding
    if ":" not in port_binding:
        return _INVALID_INSPECT

    try:
        host_ip, host_port_str = port_binding.rsplit(":", 1)
    except ValueError:
        return _INVALID_INSPECT

    if host_ip != "127.0.0.1":
        return _INVALID_INSPECT

    # Strict ASCII decimal validation for port
    if not host_port_str:
        return _INVALID_INSPECT
    if not all(c in "0123456789" for c in host_port_str):
        return _INVALID_INSPECT
    try:
        host_port = int(host_port_str)
    except ValueError:
        return _INVALID_INSPECT

    if host_port != expected_port:
        return _INVALID_INSPECT

    return FullInspectResult(
        container_id=validated_id,
        name=actual_name,
        owner=owner,
        host_ip=host_ip,
        host_port=host_port,
        valid=True,
    )


def _compose_failures(
    primary: BaseException | None,
    cleanup: BaseException | None,
) -> BaseException:
    """Compose primary and cleanup failures with exact exception semantics."""
    if primary is not None and cleanup is not None:
        sanitized_cleanup = RuntimeError(_CLEANUP_ERROR)
        if isinstance(primary, Exception):
            return builtins.ExceptionGroup(
                "Setup and cleanup failed", [primary, sanitized_cleanup]
            )
        else:
            return builtins.BaseExceptionGroup(
                "Setup and cleanup failed", [primary, sanitized_cleanup]
            )

    if primary is not None:
        return primary

    if cleanup is not None:
        return RuntimeError(_CLEANUP_ERROR)

    raise RuntimeError("compose_failures called with no exceptions")


def _attest_target(
    cursor: Any,
    expected_database: str,
    expected_schema: str,
    expected_user: str,
) -> None:
    """Attest that connection target matches expectations."""
    try:
        cursor.execute("SELECT current_database()")
        row = cursor.fetchone()
        if not row or len(row) != 1 or row[0] != expected_database:
            raise ValueError(_ATTESTATION_ERROR)

        cursor.execute("SELECT current_schema()")
        row = cursor.fetchone()
        if not row or len(row) != 1 or row[0] != expected_schema:
            raise ValueError(_ATTESTATION_ERROR)

        cursor.execute("SELECT current_user")
        row = cursor.fetchone()
        if not row or len(row) != 1 or row[0] != expected_user:
            raise ValueError(_ATTESTATION_ERROR)

        cursor.execute("SELECT session_user")
        row = cursor.fetchone()
        if not row or len(row) != 1 or row[0] != expected_user:
            raise ValueError(_ATTESTATION_ERROR)
    except ValueError:
        raise
    except Exception:
        raise ValueError(_ATTESTATION_ERROR) from None


# Readiness budget for a cold disposable PostgreSQL first boot.
#
# A freshly started pgvector/pgvector:pg15 container may still be running
# initdb/postgres bootstrap when the first readiness probes arrive. The legacy
# probe (3 attempts, ~2s of sleep) could fail a legitimate first boot,
# so the production policy grants a bounded budget of 30 attempts spaced 1.0s
# apart, i.e. a sleep budget of ~29s (30 attempts, 29 inter-attempt sleeps),
# before failing closed. The ~29s figure describes only the inter-attempt
# sleep time, NOT an absolute wall-clock bound: each individual connection
# attempt is separately bounded by the connection factory's own timeout, so
# the worst-case wall clock is the sleep budget plus the per-attempt timeouts
# of all 30 attempts. The budget is intentionally bounded: a database that
# never becomes ready must fail closed, never retry forever. Only
# psycopg.OperationalError is ever retried.
_READY_MAX_ATTEMPTS = 30
_READY_RETRY_DELAY_SECONDS = 1.0


def _wait_for_ready(
    conn_factory: Callable[[], psycopg.Connection[tuple[Any, ...]]],
    max_retries: int = _READY_MAX_ATTEMPTS,
    delay: float = _READY_RETRY_DELAY_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Wait for database connection to be ready.

    Policy: only psycopg.OperationalError is retried; all other exceptions
    propagate immediately. The bounded default budget (see _READY_MAX_ATTEMPTS
    and _READY_RETRY_DELAY_SECONDS) is sized for a cold disposable PostgreSQL
    first boot, where the server may legitimately still be initializing when
    the first probes arrive. Exhausting the budget raises the fixed error.
    """
    for attempt in range(max_retries):
        conn = None
        cursor = None
        try:
            conn = conn_factory()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            return
        except psycopg.OperationalError:
            if attempt < max_retries - 1:
                sleep(delay)
        except Exception:
            raise
        finally:
            if cursor is not None:
                try:
                    cursor.close()
                except Exception:
                    pass
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    raise RuntimeError("Database connection never became ready")


def _apply_migrations(
    cursor: Any, migration_filenames: Sequence[str] | None = None
) -> None:
    """Apply all migrations from immutable catalog. Subset bypass rejected."""
    from llamaindex_runtime.registry.migration_catalog import FULL_MIGRATION_CATALOG

    if migration_filenames is not None:
        raise ValueError("Migration subset bypass not allowed - must use full catalog")

    filenames: Sequence[str] = FULL_MIGRATION_CATALOG

    for filename in filenames:
        if (
            not filename
            or "/" in filename
            or "\\" in filename
            or ".." in filename
            or not filename.endswith(".sql")
        ):
            raise ValueError("Invalid migration filename")
        try:
            migration_module = importlib.resources.files(
                "llamaindex_runtime.registry.migrations"
            )
            sql_text = (migration_module / filename).read_text(encoding="utf-8")
        except Exception:
            raise ValueError("Failed to read migration file") from None
        cursor.execute(sql_text)


def _apply_migrations_with_connection(
    conn: Any, migration_filenames: Sequence[str] | None = None
) -> None:
    """Apply migrations with controlled transaction."""
    cursor = None
    try:
        cursor = conn.cursor()
        _apply_migrations(cursor, migration_filenames)
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass


def _write_env_file(fd: int, database: str, user: str, password: str) -> None:
    """Write environment variables to file descriptor.

    Security: Scopes the sensitive values to this helper.
    """
    import os

    with os.fdopen(fd, "w") as f:
        f.write(f"POSTGRES_DB={database}\n")
        f.write(f"POSTGRES_USER={user}\n")
        f.write(f"POSTGRES_PASSWORD={password}\n")


class _EnvFileResult(NamedTuple):
    """Result of env file creation attempt - no sensitive values."""

    success: bool
    path: Path | None = None  # None if not successful

    def __repr__(self) -> str:
        return f"_EnvFileResult(success={self.success!r}, path=<redacted>)"

    def __str__(self) -> str:
        return f"_EnvFileResult(success={self.success!r})"


def _create_env_file_impl(password: str, database: str, user: str) -> _EnvFileResult:
    """Internal helper to create env file.

    Security: Absorbs all failures, returns safe result.
    No sensitive values (password, database, user, path) can escape this frame.
    """
    import os
    import tempfile

    # Initialize locals early to avoid UnboundLocalError on cleanup
    fd = -1
    path = ""

    try:
        # Validate values don't contain dangerous characters
        _validate_env_value(database, "database")
        _validate_env_value(user, "user")
        _validate_env_value(password, "password")

        fd, path = tempfile.mkstemp(suffix=".env", prefix="docker_pg_")
        _write_env_file(fd, database, user, password)

        return _EnvFileResult(success=True, path=Path(path))
    except Exception:
        # All failures absorbed - clean up partial file
        if fd >= 0:
            try:
                os.close(fd)
            except Exception:
                pass
        if path:
            try:
                os.unlink(path)
            except Exception:
                pass
        # No sensitive values escape this frame
        return _EnvFileResult(success=False)


class _DockerStartResult(NamedTuple):
    """Result of Docker start attempt - no sensitive values."""

    success: bool
    container_id: str = ""  # Empty if not successful
    invalid_id: bool = False  # True if container ID was invalid

    def __repr__(self) -> str:
        return f"_DockerStartResult(success={self.success!r}, container_id=<redacted>, invalid_id={self.invalid_id!r})"

    def __str__(self) -> str:
        return f"_DockerStartResult(success={self.success!r}, invalid_id={self.invalid_id!r})"


class _DatabaseSetupResult(NamedTuple):
    """Result of database setup attempt - no sensitive values."""

    success: bool

    def __repr__(self) -> str:
        return f"_DatabaseSetupResult(success={self.success!r})"

    def __str__(self) -> str:
        return f"_DatabaseSetupResult(success={self.success!r})"


# Safe failure reason enum - no sensitive values
_StartupFailureReason = Literal[
    "container_exists",
    "env_file_failed",
    "docker_start_failed",
    "invalid_container_id",
    "post_start_failed",
    "database_setup_failed",
]


class _StartupResult(NamedTuple):
    """Result of full startup attempt - no sensitive values."""

    success: bool
    container_id: str = ""  # Empty if not successful
    token: str = ""  # Empty if not successful
    env_file_path: Path | None = None  # Path for cleanup; None if not successful
    failure_reason: _StartupFailureReason = (
        "docker_start_failed"  # Only meaningful if not successful
    )

    def __repr__(self) -> str:
        return f"_StartupResult(success={self.success!r}, container_id=<redacted>, token=<redacted>, env_file_path=<redacted>, failure_reason={self.failure_reason!r})"

    def __str__(self) -> str:
        return f"_StartupResult(success={self.success!r}, failure_reason={self.failure_reason!r})"


def _run_docker_start(
    runner: Callable[..., subprocess.CompletedProcess[str]],
    config_dir: str,
    container_name: str,
    port: str,
    token: str,
    env_file_path: Path,
    image: str,
    sanitized_env: Mapping[str, str],
) -> _DockerStartResult:
    """Internal helper to run Docker container.

    Security: Absorbs all failures, returns safe result.
    No sensitive values (args, result, stdout) can escape this frame.
    """
    try:
        docker_args = _build_docker_command(
            [
                "run",
                "-d",
                "--name",
                container_name,
                "-p",
                f"127.0.0.1:{port}:5432",
                "-l",
                f"owner={token}",
                "--env-file",
                str(env_file_path),
                image,
            ],
            config_dir,
        )

        result = runner(
            docker_args,
            capture_output=True,
            text=True,
            check=False,
            env=sanitized_env,
        )

        rc = _validate_returncode(result.returncode)
        if rc != 0:
            return _DockerStartResult(success=False)

        container_id_raw = result.stdout if result.stdout else ""

        # Try to normalize - catch invalid container ID
        try:
            container_id = _normalize_docker_run_id(container_id_raw)
        except RuntimeError:
            # Invalid container ID format
            return _DockerStartResult(success=False, invalid_id=True)

        return _DockerStartResult(success=True, container_id=container_id)
    except Exception:
        # All failures absorbed - no sensitive values escape
        return _DockerStartResult(success=False)


class _FreshConnectionResult(NamedTuple):
    """Result of fresh attested connection attempt - no sensitive values."""

    success: bool
    # Connection is only set on success; caller owns it
    # Using object() sentinel would leak repr, so we use Optional
    connection: psycopg.Connection[Any] | None = None

    def __repr__(self) -> str:
        return (
            f"_FreshConnectionResult(success={self.success!r}, connection=<redacted>)"
        )

    def __str__(self) -> str:
        return f"_FreshConnectionResult(success={self.success!r})"


def _open_fresh_attested_connection_impl(
    container_id: str,
    container_name: str,
    token: str,
    port: int,
    user: str,
    password: str,
    database: str,
    config_dir: str,
    runner: DockerRunner,
) -> _FreshConnectionResult:
    """Internal helper to open fresh attested connection.

    Security: Absorbs all failures, returns safe result.
    No sensitive values (target, URI, credentials, env) can escape this frame.
    On failure, all resources are closed before returning.
    Creates Docker environment internally - no public frame holds allowlisted values.
    """
    # Initialize all locals early to avoid UnboundLocalError on cleanup
    conn: psycopg.Connection[Any] | None = None
    cursor = None
    target = None

    try:
        # Create safe Docker environment internally (no public frame holds it)
        env = _sanitized_env_copy()

        # Perform full exact-container re-attestation before connecting
        inspect_result = _full_container_inspect(
            container_id,
            container_name,
            token,
            port,
            config_dir=config_dir,
            run=runner,
            env=env,
        )

        if not inspect_result.valid:
            return _FreshConnectionResult(success=False)

        # Build connection using centralized factory with autocommit=False
        from scripts._rebuild_database_connection import (
            parse_disposable_postgresql_target,
            runtime_connection_factory,
        )

        # Percent-encode user/password/database for URI safety
        target = parse_disposable_postgresql_target(
            f"postgresql://{urllib.parse.quote(user, safe='')}:"
            f"{urllib.parse.quote(password, safe='')}@"
            f"127.0.0.1:{port}/"
            f"{urllib.parse.quote(database, safe='')}",
            database,
        )

        # Open fresh connection with autocommit=False and controlled env
        conn = runtime_connection_factory(target, autocommit=False, environ=env)

        # Perform database/schema/current_user/session_user attestation
        cursor = conn.cursor()
        _attest_target(cursor, database, "public", user)

        # Close attestation cursor
        cursor.close()
        cursor = None

        # Rollback the read transaction so returned connection is fresh/idle
        conn.rollback()

        # Return success - caller owns the connection
        return _FreshConnectionResult(success=True, connection=conn)
    except Exception:
        # All failures absorbed - clean up and return safe result
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        # No sensitive values escape this frame
        return _FreshConnectionResult(success=False)


def _startup_impl(
    runner: DockerRunner,
    config_dir: str,
    container_name: str,
    port: str,
    token: str,
    password: str,
    database: str,
    user: str,
    image: str,
    conn_factory_input: ConnectionFactory | None,
    sleep_fn: SleepFunction,
) -> _StartupResult:
    """Internal helper for full startup process.

    Security: Absorbs all failures, returns safe result.
    No sensitive values (token, credentials, paths, container_id, env) can escape this frame.
    Performs full cleanup on any failure.
    Creates Docker environment internally - no public frame holds allowlisted values.
    """
    import os

    # Initialize all locals early
    env_file_path: Path | None = None
    container_id = ""

    try:
        # Create safe Docker environment internally (no public frame holds it)
        sanitized_env = _sanitized_env_copy()

        # Step 1: Verify container absent
        presence = _observe_container_presence(
            container_name,
            config_dir=config_dir,
            run=runner,
            env=sanitized_env,
        )
        if presence.status != "confirmed_absent":
            return _StartupResult(success=False, failure_reason="container_exists")

        # Step 2: Create env file
        env_result = _create_env_file_impl(password, database, user)
        if not env_result.success:
            return _StartupResult(success=False, failure_reason="env_file_failed")
        # Type narrowing: on success path, path is guaranteed non-None
        assert env_result.path is not None
        env_file_path = env_result.path

        # Step 3: Start container
        docker_result = _run_docker_start(
            runner,
            config_dir,
            container_name,
            port,
            token,
            env_file_path,
            image,
            sanitized_env,
        )
        if not docker_result.success:
            # Clean up env file before returning
            try:
                os.unlink(env_file_path)
            except Exception:
                pass
            # Check if it was an invalid container ID
            failure_reason: _StartupFailureReason = (
                "invalid_container_id"
                if docker_result.invalid_id
                else "docker_start_failed"
            )
            return _StartupResult(success=False, failure_reason=failure_reason)
        container_id = docker_result.container_id

        # Step 4: Verify post-start
        inspect_result = _full_container_inspect(
            container_id,
            container_name,
            token,
            int(port),
            config_dir=config_dir,
            run=runner,
            env=sanitized_env,
        )
        if not inspect_result.valid:
            # DO NOT remove container on verification failure
            # We may not own it (e.g., if token mismatch or pre-existing container)
            # Just clean up env file and return failure
            try:
                os.unlink(env_file_path)
            except Exception:
                pass
            return _StartupResult(success=False, failure_reason="post_start_failed")

        # Step 5: Setup database
        db_result = _setup_database_impl(
            port, database, user, password, conn_factory_input, sleep_fn
        )
        if not db_result.success:
            # Clean up container and env file
            # SECURITY: Fresh attestation before removal to prove ownership
            try:
                port_int = int(port)
            except ValueError:
                port_int = 0
            attest_result = _full_container_inspect(
                container_id,
                config_dir=config_dir,
                expected_name=container_name,
                expected_token=token,
                expected_port=port_int,
                run=runner,
                env=sanitized_env,
            )
            if attest_result.valid:
                _remove_container_by_id(
                    container_id, config_dir=config_dir, run=runner, env=sanitized_env
                )
            try:
                os.unlink(env_file_path)
            except Exception:
                pass
            return _StartupResult(success=False, failure_reason="database_setup_failed")

        # Success - return results (caller will store them)
        # Include env_file_path for caller to track for cleanup
        return _StartupResult(
            success=True,
            container_id=container_id,
            token=token,
            env_file_path=env_file_path,
        )
    except Exception:
        # All failures absorbed - clean up any created resources
        if container_id:
            # SECURITY: Fresh attestation before removal to prove ownership
            try:
                try:
                    port_int = int(port)
                except ValueError:
                    port_int = 0
                attest_result = _full_container_inspect(
                    container_id,
                    config_dir=config_dir,
                    expected_name=container_name,
                    expected_token=token,
                    expected_port=port_int,
                    run=runner,
                    env=sanitized_env,
                )
                if attest_result.valid:
                    _remove_container_by_id(
                        container_id,
                        config_dir=config_dir,
                        run=runner,
                        env=sanitized_env,
                    )
            except Exception:
                pass
        if env_file_path:
            try:
                os.unlink(env_file_path)
            except Exception:
                pass
        # No sensitive values escape this frame
        return _StartupResult(success=False, failure_reason="docker_start_failed")


def _setup_database_impl(
    port: str,
    database: str,
    user: str,
    password: str,
    conn_factory_input: ConnectionFactory | None,
    sleep_fn: SleepFunction,
) -> _DatabaseSetupResult:
    """Internal helper to set up database.

    Security: Absorbs all failures, returns safe result.
    No sensitive values (credentials, target, connection, env) can escape this frame.
    Creates Docker environment internally - no public frame holds allowlisted values.
    """
    # Initialize all locals early to avoid UnboundLocalError on cleanup
    conn: psycopg.Connection[Any] | None = None
    cursor = None
    target = None

    try:
        # Create safe Docker environment internally (no public frame holds it)
        sanitized_env = _sanitized_env_copy()

        if conn_factory_input is not None:
            # Injected factory path - must still run full lifecycle

            def conn_factory() -> psycopg.Connection[tuple[Any, ...]]:
                return conn_factory_input(
                    host="127.0.0.1",
                    port=int(port),
                    database=database,
                    user=user,
                    password=password,
                )

            # Wait for readiness
            _wait_for_ready(conn_factory, sleep=sleep_fn)

            # Run attestation and migrations (same as production path)
            conn = conn_factory()
            cursor = conn.cursor()
            _attest_target(cursor, database, "public", user)
            _apply_migrations_with_connection(conn)
        else:
            # Default production path
            from scripts._rebuild_database_connection import (
                parse_disposable_postgresql_target,
                runtime_connection_factory,
            )

            # Percent-encode user/password/database for URI safety
            encoded_user = urllib.parse.quote(user, safe="")
            encoded_password = urllib.parse.quote(password, safe="")
            encoded_database = urllib.parse.quote(database, safe="")

            # Build target inline
            target = parse_disposable_postgresql_target(
                f"postgresql://{encoded_user}:{encoded_password}@"
                f"127.0.0.1:{port}/{encoded_database}",
                database,
            )

            # Clear encoded credentials immediately after target creation
            del encoded_user, encoded_password, encoded_database

            def conn_factory() -> psycopg.Connection[tuple[Any, ...]]:
                assert target is not None  # Type narrowing for mypy
                return runtime_connection_factory(target, environ=sanitized_env)

            _wait_for_ready(conn_factory, sleep=sleep_fn)

            conn = conn_factory()
            cursor = conn.cursor()
            _attest_target(cursor, database, "public", user)
            _apply_migrations_with_connection(conn)

        return _DatabaseSetupResult(success=True)
    except Exception:
        # All failures absorbed - clean up and return safe result
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        # No sensitive values escape this frame
        return _DatabaseSetupResult(success=False)


class _PrepareResult(NamedTuple):
    """Result of startup preparation - no sensitive values."""

    success: bool
    config_dir_obj: tempfile.TemporaryDirectory | None = None  # None if not successful
    config_dir_name: str = ""  # Empty if not successful
    token: str = ""  # Empty if not successful
    invalid_token: bool = False  # True if token validation failed

    def __repr__(self) -> str:
        return f"_PrepareResult(success={self.success!r}, config_dir_obj=<redacted>, config_dir_name=<redacted>, token=<redacted>, invalid_token={self.invalid_token!r})"

    def __str__(self) -> str:
        return f"_PrepareResult(success={self.success!r}, invalid_token={self.invalid_token!r})"


def _prepare_startup_impl(
    token_factory: TokenFactory,
) -> _PrepareResult:
    """Internal helper for startup preparation.

    Security: Absorbs all failures, returns safe result.
    No sensitive values (token, config_dir) can escape this frame.
    Caller takes ownership of config_dir_obj on success.
    """
    import tempfile

    try:
        # Generate and validate token
        token = token_factory()
        validated_token = _validate_ownership_token(token)

        # Create empty Docker config directory
        config_dir_obj = tempfile.TemporaryDirectory(prefix="docker-config-empty-")

        return _PrepareResult(
            success=True,
            config_dir_obj=config_dir_obj,
            config_dir_name=config_dir_obj.name,
            token=validated_token,
        )
    except ValueError:
        # Token validation failed - return failure result (no re-raise)
        # This ensures raw token doesn't escape the frame
        return _PrepareResult(success=False, invalid_token=True)
    except Exception:
        # All other failures absorbed - cleanup happens via garbage collection
        return _PrepareResult(success=False)


class _CleanupResult(NamedTuple):
    """Result of session cleanup - no sensitive values."""

    success: bool
    error_reason: str = ""

    def __repr__(self) -> str:
        return f"_CleanupResult(success={self.success!r}, error_reason={self.error_reason!r})"

    def __str__(self) -> str:
        return f"_CleanupResult(success={self.success!r})"


def _cleanup_session_impl(
    container_id: str,
    container_name: str,
    token: str,
    port: int,
    config_dir: str,
    runner: DockerRunner,
    env_file_path: Path | None,
) -> _CleanupResult:
    """Internal helper for session cleanup.

    Security: Absorbs all failures, returns safe result.
    No sensitive values (container_id, token, config_dir) can escape this frame.

    Env file deletion is always attempted after container cleanup attempt,
    regardless of cleanup outcome. This ensures credentials are cleaned up
    even if the container is unowned or removal fails.
    """
    cleanup_error_reason: str | None = None
    env_file_deleted = False

    try:
        # Get sanitized environment
        sanitized_env = _sanitized_env_copy()

        # Verify ownership before removal
        # SECURITY: Never delete a potentially unowned container
        inspect_result = _full_container_inspect(
            container_id,
            container_name,
            token,
            port,
            config_dir=config_dir,
            run=runner,
            env=sanitized_env,
        )

        if not inspect_result.valid:
            cleanup_error_reason = "ownership_verification_failed"
        else:
            # Remove container
            removed = _remove_container_by_id(
                container_id,
                config_dir=config_dir,
                run=runner,
                env=sanitized_env,
            )

            if not removed:
                cleanup_error_reason = "removal_failed"
            else:
                # Verify removal
                post_presence = _observe_container_presence(
                    container_name,
                    config_dir=config_dir,
                    run=runner,
                    env=sanitized_env,
                )

                if post_presence.status != "confirmed_absent":
                    cleanup_error_reason = "post_removal_verification_failed"

        # CRITICAL: Always attempt env file deletion after cleanup attempt
        # This ensures credentials are cleaned up regardless of container state
        if env_file_path is not None:
            try:
                env_file_path.unlink()
                env_file_deleted = True
            except Exception:
                # Env file deletion failed
                env_file_deleted = False
        else:
            # No env file to delete
            env_file_deleted = True

        # Determine final result
        # Failure if: cleanup failed OR env file deletion failed
        if cleanup_error_reason is not None:
            return _CleanupResult(success=False, error_reason=cleanup_error_reason)

        if not env_file_deleted:
            return _CleanupResult(
                success=False, error_reason="env_file_deletion_failed"
            )

        return _CleanupResult(success=True)
    except Exception:
        # All failures absorbed - no sensitive values escape
        # Still attempt env file cleanup
        if env_file_path is not None:
            try:
                env_file_path.unlink()
            except Exception:
                pass
        return _CleanupResult(success=False, error_reason="exception_during_cleanup")


class DisposableE2aSession:
    """Public context manager for disposable E2A test execution.

    This is the primary public API for Task #89 to use.

    Contract:
        - Owns the Docker lifecycle
        - Manages migrations/readiness
        - Ensures cleanup semantics
        - Fails closed if not authorized
        - Never uses pytest.skip or similar
    """

    def __init__(
        self,
        *,
        container_name: str,
        image: str = TRUSTED_DISPOSABLE_IMAGE,
        port: str = "5432",  # Must be exact built-in str, not int
        database: str = "test_db",
        user: str = "test_user",
        password: str = "test_password",
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        conn_factory: ConnectionFactory | None = None,
        sleep_fn: SleepFunction | None = None,
        token_factory: TokenFactory | None = None,
    ) -> None:
        """Initialize disposable session.

        Args:
            container_name: Docker container name
            image: Docker image to use (must be pgvector/pgvector:pg15)
            port: Host port as exact built-in str (not int)
            database: Database name
            user: Database user
            password: Database password (required, never in Docker argv)
            runner: Docker runner (injected for testing)
            conn_factory: Connection factory (injected for testing)
            sleep_fn: Sleep function (injected for testing)
            token_factory: Token factory (injected for testing)

        Raises:
            RuntimeError: If not authorized
            ValueError: If inputs fail validation
        """
        # Authorization check at construction time
        _require_authorization()

        self._container_name = _validate_container_name(container_name)

        # Validate image is trusted disposable image
        self._image = _validate_disposable_image(image)

        # Port must be exact built-in str (not int)
        if type(port) is not str:
            raise ValueError("Port must be exact built-in str, not int")
        self._port = _validate_host_port_str(port)

        # Validate env-file values for injection safety
        self._database = _validate_env_value(database, "database")
        self._user = _validate_env_value(user, "user")
        self._password = _validate_env_value(password, "password")

        self._runner = runner or subprocess.run
        self._conn_factory = conn_factory
        # Type: time.sleep has broader signature, cast for strict protocol matching
        self._sleep_fn: SleepFunction = sleep_fn or cast(SleepFunction, time.sleep)

        # Token factory will be validated at __enter__ time
        self._token_factory_input = token_factory
        self._token_factory: TokenFactory = token_factory or _generate_ownership_token

        self._container_id: str | None = None
        self._token: str | None = None
        self._started = False
        self._env_file_path: Path | None = None
        self._docker_config_dir: tempfile.TemporaryDirectory | None = None

    def __enter__(self) -> "DisposableE2aSession":
        """Start container and wait for readiness.

        Rechecks authorization before any Docker/connection action.

        Security: Uses helpers that absorb all failures and return safe results.
        Only stores sensitive values in self after all helpers succeed.
        """
        # Recheck authorization at __enter__ time
        _require_authorization()

        # Prepare startup via helper - absorbs all preparation failures
        prepare_result = _prepare_startup_impl(self._token_factory)
        if not prepare_result.success:
            # Clean up config directory on failure (if any)
            if prepare_result.config_dir_obj is not None:
                try:
                    prepare_result.config_dir_obj.cleanup()
                except Exception:
                    pass
            # Raise specific error based on failure reason
            if prepare_result.invalid_token:
                # Raise from clean frame - no raw token in locals
                raise ValueError("Invalid token format") from None
            raise RuntimeError("Startup preparation failed") from None

        # Run startup via helper that absorbs all failures
        # Environment is created inside helper - no public frame holds it
        startup_result = _startup_impl(
            self._runner,
            prepare_result.config_dir_name,
            self._container_name,
            self._port,
            prepare_result.token,
            self._password,
            self._database,
            self._user,
            self._image,
            self._conn_factory,
            self._sleep_fn,
        )

        if not startup_result.success:
            # Clean up config directory on failure - ownership was in prepare_result
            if prepare_result.config_dir_obj is not None:
                try:
                    prepare_result.config_dir_obj.cleanup()
                except Exception:
                    pass
            # Raise specific error based on failure reason
            error_msg = {
                "container_exists": "Container already exists",
                "env_file_failed": "Failed to create env file",
                "docker_start_failed": "Failed to start container",
                "invalid_container_id": "Invalid container ID",
                "post_start_failed": "Post-start verification failed",
                "database_setup_failed": "Database setup failed",
            }.get(startup_result.failure_reason, "Startup failed")
            raise RuntimeError(error_msg) from None

        # Success - now store results in self
        # Transfer ownership of config_dir_obj from prepare_result
        self._token = startup_result.token
        self._container_id = startup_result.container_id
        self._docker_config_dir = prepare_result.config_dir_obj
        # Store env_file_path for cleanup (narrowed from Optional)
        if startup_result.env_file_path is not None:
            self._env_file_path = startup_result.env_file_path
        self._started = True
        return self

    def _verify_container_absent(self, sanitized_env: Mapping[str, str]) -> None:
        """Verify container does not exist before starting."""
        if not self._docker_config_dir:
            raise RuntimeError("Docker config directory not initialized")

        presence = _observe_container_presence(
            self._container_name,
            config_dir=self._docker_config_dir.name,
            run=self._runner,
            env=sanitized_env,
        )
        if presence.status != "confirmed_absent":
            raise RuntimeError("Container already exists")

    def _start_container(
        self, env_file_path: Path, sanitized_env: Mapping[str, str]
    ) -> str:
        """Start Docker container and return container ID.

        Security: Uses helper that absorbs failures and returns safe result.
        Only raises fixed public error after helper returns.
        """
        if not self._docker_config_dir:
            raise RuntimeError("Docker config directory not initialized")

        # Type narrowing: token is set after __enter__ succeeds
        if not self._token:
            raise RuntimeError("Session not active - must enter context first")

        result = _run_docker_start(
            self._runner,
            self._docker_config_dir.name,
            self._container_name,
            self._port,
            self._token,
            env_file_path,
            self._image,
            sanitized_env,
        )

        if not result.success:
            # Fixed public error - no sensitive values in frame
            raise RuntimeError("Failed to start container")

        return result.container_id

    def _verify_post_start(self, sanitized_env: Mapping[str, str]) -> None:
        """Verify container after start using structured full inspect."""
        if not self._container_id:
            raise RuntimeError("No container ID to verify")

        if not self._token:
            raise RuntimeError("No ownership token to verify")

        if not self._docker_config_dir:
            raise RuntimeError("Docker config directory not initialized")

        try:
            result = _full_container_inspect(
                self._container_id,
                self._container_name,
                self._token,
                int(self._port),
                config_dir=self._docker_config_dir.name,
                run=self._runner,
                env=sanitized_env,
            )
            if not result.valid:
                raise RuntimeError("Post-start verification failed") from None
        except RuntimeError:
            raise
        except Exception:
            raise RuntimeError("Post-start verification failed") from None

    def _setup_database(self, sanitized_env: Mapping[str, str]) -> None:
        """Wait for database readiness and apply migrations.

        Both connection paths (default production and injected) must run:
        - Fresh readiness attempts
        - Exact target attestation
        - Full migration execution

        Raises:
            RuntimeError: Fixed public error if setup fails.
        """
        result = _setup_database_impl(
            self._port,
            self._database,
            self._user,
            self._password,
            self._conn_factory,
            self._sleep_fn,
        )

        if not result.success:
            raise RuntimeError("Database setup failed") from None

    def _cleanup_on_failure(self, sanitized_env: Mapping[str, str]) -> None:
        """Cleanup container on startup failure with ownership attestation.

        Contract: Same protocol as normal exit - pre-attest ownership, remove by exact ID, confirm absence.
        """
        if not self._docker_config_dir:
            return  # Config dir not created yet

        if self._container_id and self._token:
            try:
                # Pre-attest ownership before removal
                inspect_result = _full_container_inspect(
                    self._container_id,
                    self._container_name,
                    self._token,
                    int(self._port),
                    config_dir=self._docker_config_dir.name,
                    run=self._runner,
                    env=sanitized_env,
                )

                # Only remove if we own it
                if inspect_result.valid:
                    removed = _remove_container_by_id(
                        self._container_id,
                        config_dir=self._docker_config_dir.name,
                        run=self._runner,
                        env=sanitized_env,
                    )

                    if removed:
                        # Confirm post-removal absence
                        post_presence = _observe_container_presence(
                            self._container_name,
                            config_dir=self._docker_config_dir.name,
                            run=self._runner,
                            env=sanitized_env,
                        )
                        # Log if not confirmed absent, but don't raise
                        if post_presence.status != "confirmed_absent":
                            logger.warning(
                                "Container not confirmed absent after removal"
                            )
            except Exception:
                # Preserve primary exception identity - cleanup errors are logged but not raised
                logger.debug("Cleanup failed during startup failure")
                pass

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Literal[False]:
        """Clean up container with structured pre-attestation.

        Security: Uses helper that absorbs all failures, then raises from clean frame.
        Raises fixed redacted error (_CLEANUP_ERROR) instead of interpolated reason.
        Clears all sensitive state on both normal and failed cleanup.
        """
        primary_exception = exc_val
        cleanup_failed = False

        if (
            self._started
            and self._container_id
            and self._token
            and self._docker_config_dir
        ):
            # Call helper that absorbs all failures
            # Env file deletion is handled inside helper
            cleanup_result = _cleanup_session_impl(
                container_id=self._container_id,
                container_name=self._container_name,
                token=self._token,
                port=int(self._port),
                config_dir=self._docker_config_dir.name,
                runner=self._runner,
                env_file_path=self._env_file_path,
            )

            if not cleanup_result.success:
                cleanup_failed = True

        # CRITICAL: Clear all sensitive state on both normal and failed cleanup
        # This prevents sensitive values from leaking via exception frames
        self._started = False
        self._container_id = None
        self._token = None
        self._env_file_path = None

        # Clean up Docker config directory AFTER container cleanup
        if self._docker_config_dir:
            try:
                self._docker_config_dir.cleanup()
            except Exception:
                pass
            self._docker_config_dir = None

        # Raise cleanup exception from clean frame if needed
        # Use fixed error message instead of interpolated reason
        if cleanup_failed:
            raise RuntimeError(_CLEANUP_ERROR) from None

        if primary_exception is not None:
            raise primary_exception

        return False

    def open_fresh_attested_connection(self) -> psycopg.Connection[Any]:
        """Open a fresh, attested connection to the disposable database.

        This is a restricted bridge that:
        - Rechecks authorization
        - Rejects injected conn_factory sessions before connection action
        - Requires an active entered session with stored container ID/token
        - Performs full exact-container re-attestation before connecting
        - Returns a fresh connection in manual transaction mode (autocommit=False)
        - Rolls back the attestation read transaction before returning

        Returns:
            A new caller-owned psycopg connection (caller responsible for closing)

        Raises:
            RuntimeError: If not authorized, not in active session, or bridge failure

        Contract:
            - NEVER returns a connection from injected conn_factory
            - NEVER exposes target/URI/token/cursor/internals
            - Each call returns a distinct fresh connection
            - On failure, closes connection and raises fixed redacted error
        """
        # Recheck authorization
        _require_authorization()

        # Reject injected conn_factory sessions before connection action
        if self._conn_factory is not None:
            raise RuntimeError(
                "Fresh attested connection not available for injected factory sessions"
            )

        # Require active entered session with container ID and token
        if not self._started:
            raise RuntimeError("Session not active - must enter context first")

        if not self._container_id or not self._token:
            raise RuntimeError("Session not active - must enter context first")

        if not self._docker_config_dir:
            raise RuntimeError("Docker config directory not initialized")

        # Call helper that absorbs all failures
        # Environment is created inside helper - no public frame holds it
        result = _open_fresh_attested_connection_impl(
            self._container_id,
            self._container_name,
            self._token,
            int(self._port),
            self._user,
            self._password,
            self._database,
            self._docker_config_dir.name,
            self._runner,
        )

        if not result.success:
            # Fixed public error - no sensitive values can escape
            raise RuntimeError("Fresh attested connection bridge failed") from None

        # Success - return the connection (caller owns it)
        # Explicit guard: on success path, connection must be non-None
        if result.connection is None:
            # This should never happen on success, but guard explicitly
            raise RuntimeError(
                "Connection unavailable after successful bridge"
            ) from None

        return result.connection


__all__ = [
    "DisposableE2aSession",
    "_observe_container_presence",
    "_remove_container_by_id",
    "_full_container_inspect",
    "FullInspectResult",
    "_compose_failures",
    "_attest_target",
    "_wait_for_ready",
    "_apply_migrations",
    "_apply_migrations_with_connection",
    "DockerRunner",
    "ConnectionFactory",
    "SleepFunction",
    "TokenFactory",
]
