"""Strict disposable PostgreSQL connection support for OKF rebuilds."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, TypeAlias, cast
from urllib.parse import unquote, urlsplit

import psycopg
from psycopg import pq

RuntimeConnectValue: TypeAlias = str | int | bool
RuntimeConnectKwargs: TypeAlias = dict[str, RuntimeConnectValue]
_SERVICE_ROUTING_ENVIRONMENT_KEYS = frozenset(
    {"PGSERVICE", "PGSERVICEFILE", "PGSYSCONFDIR"}
)
_SAFE_LIBPQ_CONTROLS: dict[str, str] = (
    dict.fromkeys(
        (
            "channel_binding",
            "sslmode",
            "sslnegotiation",
            "sslcompression",
            "sslcertmode",
            "sslsni",
            "gssencmode",
            "gssdelegation",
            "load_balance_hosts",
        ),
        "disable",
    )
    | dict.fromkeys(
        ("passfile", "sslcert", "sslkey", "sslrootcert", "sslcrl", "sslcrldir"),
        os.devnull,
    )
    | {
        "client_encoding": "UTF8",
        "options": "-c search_path=public",
        "application_name": "okf-rebuild-disposable",
        "requirepeer": "postgres",
        "require_auth": "scram-sha-256",
        "min_protocol_version": "3.0",
        "max_protocol_version": "3.0",
        "ssl_min_protocol_version": "TLSv1.2",
        "ssl_max_protocol_version": "TLSv1.3",
        "krbsrvname": "postgres",
        "gsslib": "gssapi",
        "target_session_attrs": "any",
        "sslcompression": "0",
        "sslnegotiation": "postgres",
        "sslsni": "0",
        "gssdelegation": "0",
    }
)


@dataclass(frozen=True)
class DisposablePostgresqlTarget:
    """A validated loopback-only disposable database connection target.

    Security: All fields are redacted in repr/str to prevent disclosure
    of host, port, dbname, user, or password in logs/tracebacks.
    """

    host: str
    hostaddr: str
    port: int
    dbname: str
    user: str
    password: str = field(repr=False)

    def __repr__(self) -> str:
        """Fully redacted repr - no field values disclosed."""
        return "DisposablePostgresqlTarget(<redacted>)"

    def __str__(self) -> str:
        """Fully redacted str - no field values disclosed."""
        return "DisposablePostgresqlTarget(<redacted>)"


def _invalid_disposable_target() -> ValueError:
    return ValueError("Invalid disposable PostgreSQL target; refusing rebuild")


def normalize_libpq_metadata(value: object) -> str | None:
    """Normalize the exact metadata representations supplied by libpq."""
    if value is None or type(value) is str:
        return value
    if type(value) is bytes:
        return value.decode("ascii")
    raise TypeError("Unsupported libpq metadata type")


def _parse_and_validate_target(
    database_url: str, expected_database: str
) -> tuple[int, str, str, str]:
    """Internal helper to parse and validate target - returns (port, dbname, username, password).

    Security: All sensitive data is scoped to this helper.
    Raises ValueError on any validation failure.
    """
    parsed = urlsplit(database_url)
    port = parsed.port
    dbname = unquote(parsed.path[1:]) if parsed.path.startswith("/") else ""
    username = unquote(parsed.username) if parsed.username else ""
    password = unquote(parsed.password) if parsed.password else ""

    if (
        parsed.scheme != "postgresql"
        or "?" in database_url
        or "#" in database_url
        or parsed.query
        or parsed.fragment
        or parsed.hostname != "127.0.0.1"
        or port is None
        or not 1 <= port <= 65535
        or not parsed.username
        or parsed.password is None
        or not dbname
        or "/" in dbname
        or dbname != expected_database
    ):
        raise ValueError("Invalid disposable PostgreSQL target")

    return port, dbname, username, password


def parse_disposable_postgresql_target(
    database_url: str, expected_database: str
) -> DisposablePostgresqlTarget:
    """Parse only the strict loopback URI accepted for disposable rebuilds.

    Security: Failure frames do not leak URI, credentials, or parsed components.
    Uses helper function to scope sensitive parsing locals.
    """
    try:
        port, dbname, username, password = _parse_and_validate_target(
            database_url, expected_database
        )
    except (TypeError, ValueError):
        # Helper has already cleaned up its locals
        raise _invalid_disposable_target() from None

    return DisposablePostgresqlTarget(
        "127.0.0.1",
        "127.0.0.1",
        port,
        dbname,
        username,
        password,
    )


def reject_ambient_service_routing(environ: Mapping[str, str]) -> None:
    """Reject service-file connection routing before any connection is opened."""
    if _SERVICE_ROUTING_ENVIRONMENT_KEYS & environ.keys():
        raise ValueError("Disposable connections refuse ambient service routing")


def runtime_connection_kwargs(
    target: DisposablePostgresqlTarget,
    *,
    autocommit: bool = False,
    connect_timeout: int = 5,
    environ: Mapping[str, str] | None = None,
) -> RuntimeConnectKwargs:
    """Build explicit, capability-aware libpq parameters for a target."""
    reject_ambient_service_routing(os.environ if environ is None else environ)
    controls: RuntimeConnectKwargs = dict(_SAFE_LIBPQ_CONTROLS)
    defaults = tuple(pq.Conninfo.get_defaults())
    installed = {normalize_libpq_metadata(default.keyword) for default in defaults}
    protected = {
        *controls,
        "user",
        "password",
        "dbname",
        "host",
        "hostaddr",
        "port",
        "connect_timeout",
    }
    for default in defaults:
        keyword = normalize_libpq_metadata(default.keyword)
        envvar = normalize_libpq_metadata(default.envvar)
        if envvar is not None and keyword != "service" and keyword not in protected:
            raise ValueError("Unsupported libpq environment-backed setting")
    return {
        **{key: value for key, value in controls.items() if key in installed},
        "user": target.user,
        "password": target.password,
        "dbname": target.dbname,
        "host": target.host,
        "hostaddr": target.hostaddr,
        "port": target.port,
        "connect_timeout": connect_timeout,
        "autocommit": autocommit,
    }


def runtime_connection_factory(
    target: DisposablePostgresqlTarget,
    *,
    autocommit: bool = False,
    environ: Mapping[str, str] | None = None,
) -> psycopg.Connection[Any]:
    """Open a controlled psycopg connection without URI passthrough.

    Args:
        target: Validated disposable PostgreSQL connection target
        autocommit: If True, connection uses autocommit mode (default False)
        environ: Optional environment mapping for service routing rejection

    Returns:
        New psycopg connection with controlled libpq parameters

    Contract:
        - Never passes raw URI to psycopg.connect()
        - Uses runtime_connection_kwargs for explicit parameter construction
        - Forwards autocommit and environ parameters to kwargs builder
    """
    return psycopg.connect(
        **cast(
            Any,
            runtime_connection_kwargs(target, autocommit=autocommit, environ=environ),
        )
    )
