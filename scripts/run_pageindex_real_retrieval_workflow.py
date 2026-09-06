from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence, cast
from urllib.parse import quote, urlparse

import psycopg
from psycopg.abc import ConnParam

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# REPO_ROOT must precede this import for direct script execution.
from llamaindex_runtime.config import RuntimeSettings  # noqa: E402

MIGRATIONS_DIR = REPO_ROOT / "llamaindex_runtime" / "registry" / "migrations"
MIGRATION_FILES: tuple[str, ...] = (
    "001_initial.sql",
    "002_version_lifecycle.sql",
    "003_tree_persistence.sql",
    "004_vector_extension.sql",
    "007_processing_status.sql",
)
CONTAINER_NAME = "rag-pg"
CONTAINER_IMAGE = "pgvector/pgvector:pg15"
DATABASE_CONNECT_TIMEOUT = 10
MIGRATION_CONNECTION_OPTIONS = "-c search_path=public"
MIGRATION_LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"
MIGRATION_STATEMENT_TIMEOUT_SQL = "SET statement_timeout = '60s'"
LOCAL_DATABASE_URL_ERROR = "DATABASE_URL must be a valid local loopback URL"
FINAL_WORKFLOW_FAILURE = "Workflow failed; see preceding safe diagnostics"
WORKFLOW_CHILD_SCRIPTS = frozenset(
    {
        "test_real_integration.py",
        "verification/phase5-evidence-chain-verification/verify_active_version_counts.py",
        "verification/phase5-evidence-chain-verification/invoke_vector_loader.py",
        "test_retrieve_real.py",
    }
)
_POSTGRES_URI_USERINFO = re.compile(
    r"(?i)\b(?P<scheme>postgres(?:ql)?://)(?P<userinfo>[^@\s]+)@"
)
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_LIBPQ_LEGACY_AND_SERVICE_ENVVARS = frozenset(
    {"PGREQUIRESSL", "PGSERVICE", "PGSERVICEFILE", "PGSYSCONFDIR"}
)
_SERVICE_ENVVARS = frozenset({"PGSERVICE", "PGSERVICEFILE"})
_PINNED_PARENT_CONNECTION_KEYWORDS = frozenset(
    {"host", "hostaddr", "port", "dbname", "user", "password"}
)
_PARENT_CONNECTION_CONTROLS: dict[str, ConnParam] = {
    "passfile": "",
    "channel_binding": "disable",
    "connect_timeout": DATABASE_CONNECT_TIMEOUT,
    "client_encoding": "UTF8",
    "options": MIGRATION_CONNECTION_OPTIONS,
    "application_name": "rag-pageindex-real-retrieval",
    "sslmode": "disable",
    "sslnegotiation": "postgres",
    "sslcompression": "0",
    "sslcert": "",
    "sslkey": "",
    "sslcertmode": "allow",
    "sslrootcert": "",
    "sslcrl": "",
    "sslcrldir": "",
    "sslsni": "0",
    "requirepeer": "",
    "require_auth": "none",
    "min_protocol_version": "",
    "max_protocol_version": "",
    "ssl_min_protocol_version": "",
    "ssl_max_protocol_version": "",
    "gssencmode": "disable",
    "krbsrvname": "postgres",
    "gsslib": "gssapi",
    "gssdelegation": "0",
    "target_session_attrs": "any",
    "load_balance_hosts": "disable",
}


_ALLOWED_MIGRATION_FILES = frozenset(MIGRATION_FILES)
_WORKFLOW_ERROR_DETAILS = {
    "docker_required": ("docker", "Docker stage failed: docker is required"),
    "docker_unreachable": ("docker", "Docker stage failed: daemon is not reachable"),
    "docker_create_failed": (
        "docker",
        "Docker stage failed: unable to create local PostgreSQL container",
    ),
    "docker_start_failed": (
        "docker",
        "Docker stage failed: unable to start local PostgreSQL container",
    ),
    "docker_probe_failed": (
        "docker",
        "Docker stage failed: readiness probe could not run",
    ),
    "docker_not_ready": (
        "docker",
        "Docker stage failed: PostgreSQL container did not become ready",
    ),
    "connection_config_failed": (
        "connection",
        "Connection configuration failed: ambient libpq configuration is unsafe",
    ),
    "migration_failed": ("migration", "Migration stage failed"),
    "child_failed": ("child", "Child script stage failed"),
}
_IDENTIFIER_ERROR_CODES = frozenset({"migration_failed", "child_failed"})


def _normalize_libpq_metadata_value(value: object) -> str | None:
    if isinstance(value, bytes):
        try:
            return value.decode("ascii")
        except UnicodeDecodeError:
            return None
    return value if isinstance(value, str) else None


def _libpq_default_options() -> tuple[tuple[str, str | None], ...]:
    options: list[tuple[str, str | None]] = []
    for option in psycopg.pq.Conninfo.get_defaults():
        keyword = _normalize_libpq_metadata_value(getattr(option, "keyword", None))
        if keyword:
            options.append(
                (
                    keyword,
                    _normalize_libpq_metadata_value(getattr(option, "envvar", None)),
                )
            )
    return tuple(options)


def _libpq_connection_envvars() -> frozenset[str]:
    metadata_envvars = {
        normalized
        for option in psycopg.pq.Conninfo.get_defaults()
        if (
            normalized := _normalize_libpq_metadata_value(
                getattr(option, "envvar", None)
            )
        )
        is not None
    }
    return frozenset(metadata_envvars | _LIBPQ_LEGACY_AND_SERVICE_ENVVARS)


def _supported_parent_connection_controls() -> dict[str, ConnParam]:
    installed_keywords = {keyword for keyword, _envvar in _libpq_default_options()}
    return {
        keyword: value
        for keyword, value in _PARENT_CONNECTION_CONTROLS.items()
        if keyword in installed_keywords
    }


def _ambient_libpq_requires_fail_closed(
    controls: dict[str, ConnParam],
) -> bool:
    for keyword, envvar in _libpq_default_options():
        if envvar and envvar in os.environ:
            if envvar in _SERVICE_ENVVARS or (
                keyword not in controls
                and keyword not in _PINNED_PARENT_CONNECTION_KEYWORDS
            ):
                return True
    if any(envvar in os.environ for envvar in _SERVICE_ENVVARS):
        return True
    return "PGREQUIRESSL" in os.environ and "sslmode" not in controls


class _WorkflowError(RuntimeError):
    def __init__(self, code: str, identifier: str | None = None) -> None:
        if type(code) is not str or code not in _WORKFLOW_ERROR_DETAILS:
            raise ValueError("Unknown workflow error code")
        self.code = code
        self.stage, self._message = _WORKFLOW_ERROR_DETAILS[code]
        self.identifier = self._validated_identifier(identifier)
        super().__init__(self.message)

    def _validated_identifier(self, identifier: str | None) -> str | None:
        if self.code not in _IDENTIFIER_ERROR_CODES:
            if identifier is not None:
                raise ValueError("Workflow error code does not accept an identifier")
            return None
        allowed = (
            _ALLOWED_MIGRATION_FILES
            if self.code == "migration_failed"
            else WORKFLOW_CHILD_SCRIPTS
        )
        if identifier is not None and (
            type(identifier) is not str or identifier not in allowed
        ):
            raise ValueError("Unrecognized workflow error identifier")
        return identifier

    @property
    def message(self) -> str:
        return (
            f"{self._message}: {self.identifier}" if self.identifier else self._message
        )

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class _LocalDatabaseTarget:
    host: str
    port: int
    database: str
    user: str
    password: str = field(repr=False)

    @property
    def database_url(self) -> str:
        host = f"[{self.host}]" if self.host == "::1" else self.host
        return (
            f"postgresql://{quote(self.user, safe='')}:{quote(self.password, safe='')}"
            f"@{host}:{self.port}/{quote(self.database, safe='')}"
        )


def _local_database_target(database_url: str) -> _LocalDatabaseTarget:
    """Parse a strict local PostgreSQL URI without connecting or resolving DNS."""
    if type(database_url) is not str:
        raise ValueError(LOCAL_DATABASE_URL_ERROR)
    try:
        parsed = urlparse(database_url)
        if (
            parsed.scheme not in {"postgresql", "postgres"}
            or parsed.query
            or parsed.fragment
            or parsed.params
        ):
            raise ValueError(LOCAL_DATABASE_URL_ERROR)
        conninfo = psycopg.conninfo.conninfo_to_dict(database_url)
        host = conninfo.get("host")
        port = conninfo.get("port", "5432")
        database = conninfo.get("dbname")
        user = conninfo.get("user")
        password = conninfo.get("password")
        if (
            conninfo.get("hostaddr")
            or conninfo.get("service")
            or not isinstance(host, str)
            or host not in LOCAL_HOSTS
            or not isinstance(port, str)
            or not port.isdigit()
            or not 1 <= int(port) <= 65535
            or not isinstance(database, str)
            or not database
            or not isinstance(user, str)
            or not user
            or not isinstance(password, str)
            or not password
        ):
            raise ValueError(LOCAL_DATABASE_URL_ERROR)
    except (TypeError, ValueError, psycopg.Error) as exc:
        raise ValueError(LOCAL_DATABASE_URL_ERROR) from exc
    return _LocalDatabaseTarget(
        host="127.0.0.1" if host == "localhost" else host,
        port=int(port),
        database=database,
        user=user,
        password=password,
    )


def _parent_connection_kwargs(target: _LocalDatabaseTarget) -> dict[str, ConnParam]:
    controls = _supported_parent_connection_controls()
    if _ambient_libpq_requires_fail_closed(controls):
        raise _WorkflowError("connection_config_failed")
    return {
        "host": target.host,
        "hostaddr": target.host,
        "port": target.port,
        "dbname": target.database,
        "user": target.user,
        "password": target.password,
        **controls,
    }


def _connect_parent(
    target: _LocalDatabaseTarget, *, autocommit: bool
) -> psycopg.Connection[tuple[Any, ...]]:
    """Cross psycopg's dynamic keyword boundary after capability filtering."""
    kwargs = {**_parent_connection_kwargs(target), "autocommit": autocommit}
    return psycopg.connect(**cast(Any, kwargs))


def _validate_local_database_target(database_url: str) -> str:
    """Return the normalized local host without connecting or resolving DNS."""
    try:
        return _local_database_target(database_url).host
    except ValueError as exc:
        raise RuntimeError(LOCAL_DATABASE_URL_ERROR) from exc


def parse_postgres_database_url(database_url: str) -> dict[str, str | int]:
    target = _local_database_target(database_url)
    return {
        "scheme": "postgresql",
        "host": target.host,
        "port": target.port,
        "database": target.database,
        "user": target.user,
        "password": target.password,
    }


def _wrap_command(args: Sequence[str]) -> list[str]:
    command = list(args)
    if command and command[0] == "docker":
        return ["rtk", "proxy", *command]
    return command


def _run_command(
    args: Sequence[str],
    *,
    cwd: Path = REPO_ROOT,
    timeout: int = 600,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        _wrap_command(args),
        cwd=cwd,
        check=True,
        text=True,
        capture_output=True,
        timeout=timeout,
        env=env,
    )


def _redaction_values(
    *, target: _LocalDatabaseTarget | None = None, database_url: str | None = None
) -> tuple[str, ...]:
    values: list[str] = []
    if database_url:
        values.append(database_url)
    if target:
        values.extend(
            (target.database_url, target.password, quote(target.password, safe=""))
        )
    return tuple(value for value in values if value)


def _redact_text(text: str, sensitive_values: Iterable[str]) -> str:
    redacted = _POSTGRES_URI_USERINFO.sub(
        lambda match: f"{match.group('scheme')}[REDACTED]@", text
    )
    values = {value for value in sensitive_values if type(value) is str and value}
    for value in sorted(values, key=len, reverse=True):
        pattern = re.escape(value)
        if "%" in value:
            pattern = rf"(?<![A-Za-z0-9]){pattern}(?![A-Za-z0-9])"
            redacted = re.sub(pattern, "[REDACTED]", redacted, flags=re.IGNORECASE)
        else:
            redacted = redacted.replace(value, "[REDACTED]")
    return redacted


def _print_completed_output(
    result: subprocess.CompletedProcess[str], *, sensitive_values: Iterable[str] = ()
) -> None:
    for output in (result.stdout, result.stderr):
        if output and output.strip():
            print(_redact_text(output.strip(), sensitive_values))


def database_is_reachable(database_url: str) -> bool:
    target = _local_database_target(database_url)
    try:
        with _connect_parent(target, autocommit=True):
            return True
    except psycopg.Error:
        return False


def _require_docker() -> None:
    if shutil.which("docker") is None:
        raise _WorkflowError("docker_required")


def _docker_container_status(container_name: str) -> str:
    try:
        return _run_command(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                f"name=^{container_name}$",
                "--format",
                "{{.Names}}|{{.Status}}",
            ]
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise _WorkflowError("docker_unreachable") from exc


def _docker_loopback_binding(target: _LocalDatabaseTarget) -> str:
    host = f"[{target.host}]" if target.host == "::1" else target.host
    return f"{host}:{target.port}:5432"


def _create_pgvector_container(
    *,
    container_name: str,
    image: str,
    target: _LocalDatabaseTarget,
    sensitive_values: Iterable[str],
) -> None:
    docker_env = {**os.environ, "POSTGRES_PASSWORD": target.password}
    try:
        result = _run_command(
            [
                "docker",
                "run",
                "--name",
                container_name,
                "-e",
                f"POSTGRES_USER={target.user}",
                "-e",
                "POSTGRES_PASSWORD",
                "-e",
                f"POSTGRES_DB={target.database}",
                "-p",
                _docker_loopback_binding(target),
                "-d",
                image,
            ],
            env=docker_env,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise _WorkflowError("docker_create_failed") from exc
    _print_completed_output(result, sensitive_values=sensitive_values)


def _start_pgvector_container(
    *, container_name: str, sensitive_values: Iterable[str]
) -> None:
    try:
        result = _run_command(["docker", "start", container_name])
    except (OSError, subprocess.SubprocessError) as exc:
        raise _WorkflowError("docker_start_failed") from exc
    _print_completed_output(result, sensitive_values=sensitive_values)


def _find_start_or_create_pgvector_container(
    *,
    container_name: str,
    image: str,
    target: _LocalDatabaseTarget,
    sensitive_values: Iterable[str] = (),
) -> None:
    existing = _docker_container_status(container_name)
    if not existing:
        _create_pgvector_container(
            container_name=container_name,
            image=image,
            target=target,
            sensitive_values=sensitive_values,
        )
    elif "|Up " not in existing:
        _start_pgvector_container(
            container_name=container_name, sensitive_values=sensitive_values
        )


def _wait_for_pgvector_container(
    *, container_name: str, target: _LocalDatabaseTarget
) -> None:
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            probe = subprocess.run(
                _wrap_command(
                    [
                        "docker",
                        "exec",
                        container_name,
                        "pg_isready",
                        "-U",
                        target.user,
                        "-d",
                        target.database,
                    ]
                ),
                cwd=REPO_ROOT,
                check=False,
                text=True,
                capture_output=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise _WorkflowError("docker_probe_failed") from exc
        if probe.returncode == 0:
            return
        time.sleep(2)
    raise _WorkflowError("docker_not_ready")


def ensure_local_pgvector_container(
    database_url: str,
    *,
    container_name: str = CONTAINER_NAME,
    image: str = CONTAINER_IMAGE,
) -> None:
    target = _local_database_target(database_url)
    _require_docker()
    _find_start_or_create_pgvector_container(
        container_name=container_name,
        image=image,
        target=target,
        sensitive_values=_redaction_values(target=target, database_url=database_url),
    )
    _wait_for_pgvector_container(container_name=container_name, target=target)


def apply_migrations(
    *,
    database_url: str,
    migrations_dir: Path = MIGRATIONS_DIR,
    migration_files: Sequence[str] = MIGRATION_FILES,
) -> list[str]:
    target = _local_database_target(database_url)
    applied: list[str] = []
    with _connect_parent(target, autocommit=True) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute(MIGRATION_LOCK_TIMEOUT_SQL)
                cursor.execute(MIGRATION_STATEMENT_TIMEOUT_SQL)
            except Exception as exc:
                raise _WorkflowError("migration_failed") from exc
            for migration_file in migration_files:
                try:
                    sql = (migrations_dir / migration_file).read_text(encoding="utf-8")
                    cursor.execute(sql)
                except Exception as exc:
                    safe_name = (
                        migration_file
                        if migration_file in _ALLOWED_MIGRATION_FILES
                        else None
                    )
                    raise _WorkflowError("migration_failed", safe_name) from exc
                applied.append(migration_file)
    return applied


def _child_environment(target: _LocalDatabaseTarget) -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if key not in _libpq_connection_envvars()
    } | {"DATABASE_URL": target.database_url}


def _run_python_script(script_name: str, *, database_url: str) -> None:
    target = _local_database_target(database_url)
    if script_name not in WORKFLOW_CHILD_SCRIPTS:
        raise _WorkflowError("child_failed")
    script_path = REPO_ROOT / script_name
    if not script_path.exists():
        raise _WorkflowError("child_failed", script_name)
    sensitive_values = _redaction_values(target=target, database_url=database_url)
    try:
        result = _run_command(
            [sys.executable, str(script_path)],
            cwd=REPO_ROOT,
            env=_child_environment(target),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise _WorkflowError("child_failed", script_name) from exc
    _print_completed_output(result, sensitive_values=sensitive_values)


def main() -> None:
    try:
        database_url = RuntimeSettings.from_env().database_url
    except Exception:
        raise SystemExit(FINAL_WORKFLOW_FAILURE) from None
    try:
        _validate_local_database_target(database_url)
    except RuntimeError:
        raise SystemExit(LOCAL_DATABASE_URL_ERROR) from None
    try:
        print("[STEP] Ensure local pgvector PostgreSQL container")
        if database_is_reachable(database_url):
            print("PostgreSQL already reachable; skipping Docker startup.")
        else:
            ensure_local_pgvector_container(database_url)
        print("[STEP] Apply registry migrations")
        applied = apply_migrations(database_url=database_url)
        print(f"Applied migrations: {', '.join(applied)}")
        print("[STEP] Populate real integration data")
        _run_python_script("test_real_integration.py", database_url=database_url)
        print("[STEP] Verify active-version evidence-chain counts")
        _run_python_script(
            "verification/phase5-evidence-chain-verification/verify_active_version_counts.py",
            database_url=database_url,
        )
        print("[STEP] Materialize vector chunks for active version")
        _run_python_script(
            "verification/phase5-evidence-chain-verification/invoke_vector_loader.py",
            database_url=database_url,
        )
        print("[STEP] Re-check active-version evidence-chain counts")
        _run_python_script(
            "verification/phase5-evidence-chain-verification/verify_active_version_counts.py",
            database_url=database_url,
        )
        print("[STEP] Verify real retrieval path")
        _run_python_script("test_retrieve_real.py", database_url=database_url)
    except _WorkflowError as error:
        print(error.message)
        raise SystemExit(FINAL_WORKFLOW_FAILURE) from None
    except Exception:
        raise SystemExit(FINAL_WORKFLOW_FAILURE) from None
    print("\nWorkflow complete.")
    print(f"Re-run command: rtk python {Path(__file__).as_posix()}")


if __name__ == "__main__":
    main()
