"""Live authorization-first disposable migration gate harness.

Authorization is checked first and only the three exact gate-routing environment
keys may ever be read; every other environment value is out of scope. An
unauthorized invocation returns the immutable blocked status with zero touch:
no secrets, container names, ports, temp paths, URIs, Docker, connection, or
gate work happens, and no evidence is written. A single invocation owns exactly
one container and issues exactly one production gate call, then validates the
gate outcome facts and the evidence hash only, and always cleans up once the
container has been created. The invocation holds the prepared config directory
until the final cleanup and forwards a sanitized Docker environment rather than
the gate environ. The disposable loopback target URI is built internally from
the fixed ``okf`` user, the generated password and port, and the expected
database -- callers never supply a raw target URI. A created env file is
deleted even when no container was ever created; deletion failure fails closed.
If ``docker run -d`` exits 0 but returns no usable container ID, the harness
performs exactly one post-start presence observation through the exact
name-presence primitive; when the full 64-hex ID is recovered, the container is
attested and cleaned up, and a fixed redacted start failure is raised. When the
identity is not safely recoverable, the harness fails closed with a fixed
redacted cleanup-recovery error and never deletes by name alone.
The harness never writes evidence itself; the gate does.
"""

import os
import sys
import types
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from time import sleep as _time_sleep
from typing import Callable

AUTH_ENV = "OKF_E2B_MIGRATION_TEST_AUTHORIZED"
DISPOSABLE_ENV = "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE"
EXPECTED_DATABASE_ENV = "OKF_REBUILD_EXPECTED_DATABASE"

BLOCKED_STATUS = "blocked_not_executed"
EXECUTED_STATUS = "executed"

_DISPOSABLE_IMAGE = "pgvector/pgvector:pg15"
_DISPOSABLE_USER = "okf"
_CATALOG_TAIL = ("019_e2a_materialization_contract.sql", "020_ner_entity_mentions.sql")

_ROUTING_KEYS = (DISPOSABLE_ENV, AUTH_ENV, EXPECTED_DATABASE_ENV)

# Fixed redacted failure texts for the post-start recovery path. Neither carries
# any Docker-derived, credential, container-name, or URI value.
_START_RECOVERY_ERROR = "docker start failed after container creation"
_START_RECOVERY_UNRESOLVED_ERROR = (
    "docker start failed with unresolved container cleanup"
)

# Exact 64 lowercase-hex characters for a full Docker container ID.
_HEX64_CHARS = frozenset("0123456789abcdef")


@dataclass(frozen=True)
class LiveGateResult:
    """Immutable result of one live harness invocation."""

    status: str
    gate_outcome: object | None = None
    evidence_verified: bool = False
    cleanup_ok: bool = False


def _read_routing_environ() -> dict[str, str | None]:
    """Explicit three-key mapping; never the full ambient environment."""
    values = tuple(os.environ.get(key) for key in _ROUTING_KEYS)
    return {key: value for key, value in zip(_ROUTING_KEYS, values)}


def _harness_package() -> str:
    """Return the real package this harness file lives in."""
    if __package__:
        return __package__
    root = Path(__file__).resolve().parents[3]
    return ".".join(Path(__file__).resolve().parent.relative_to(root).parts)


def _register_parent_packages(package: str) -> None:
    """Register synthetic parent packages without executing any __init__."""
    base = Path(__file__).resolve().parent
    parts = package.split(".")
    for index in range(1, len(parts) + 1):
        name = ".".join(parts[:index])
        if name in sys.modules:
            continue
        stub = types.ModuleType(name)
        stub.__package__ = name
        if index == len(parts):
            stub.__path__ = [str(base)]
        else:
            stub.__path__ = [str(base.parents[len(parts) - index - 1])]
        sys.modules[name] = stub


def _load_file_module(module_name: str, path: Path) -> types.ModuleType:
    """Load a module from a file, registered in sys.modules before exec."""
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location(module_name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError("live harness module unavailable")
    module = module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(module_name, None)
        raise
    return module


def _load_harness_sibling(name: str) -> types.ModuleType:
    """Load a same-directory helper under the real package identity.

    Helpers may use relative imports into sibling type modules, so they are
    registered under the real package name with the parent package chain present
    in sys.modules before exec. Cached modules are reused.
    """
    package = _harness_package()
    module_name = f"{package}.{name}"
    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    _register_parent_packages(package)
    return _load_file_module(module_name, Path(__file__).with_name(name + ".py"))


def _lazy_runner(*args: object, **kwargs: object) -> object:
    import subprocess

    return subprocess.run(*args, **kwargs)


def _lazy_target_parser(target_uri: object, expected_database: object) -> object:
    from scripts._rebuild_database_connection import parse_disposable_postgresql_target

    return parse_disposable_postgresql_target(target_uri, expected_database)


def _lazy_connection_factory(target: object, **kwargs: object) -> object:
    from scripts._rebuild_database_connection import runtime_connection_factory

    return runtime_connection_factory(target, **kwargs)


def _lazy_token_factory() -> str:
    import secrets

    return secrets.token_hex(32)


def _lazy_password_factory() -> str:
    import secrets

    return secrets.token_urlsafe(24)


def _lazy_container_name_factory() -> str:
    import secrets

    return "okf-e2b-" + secrets.token_hex(4)


def _lazy_port_factory() -> str:
    """Bind an ephemeral loopback port, release it, and return it as text."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return str(port)


def _lazy_evidence_path_factory() -> Path:
    root = Path(__file__).resolve().parents[3]
    return (
        root
        / "verification"
        / "phase16-raw-corpus-entity-layer"
        / ("e2b_migration_gate_evidence.md")
    )


def _build_loopback_target_uri(
    user: str, password: str, port: str, database: str
) -> str:
    """Build the strict loopback-only disposable URI with percent encoding.

    Every user-supplied field is percent-encoded with an empty safe set so a
    hostile password or database name can never change URI structure.
    """
    from urllib.parse import quote

    return "postgresql://{}:{}@127.0.0.1:{}/{}".format(
        quote(user, safe=""),
        quote(password, safe=""),
        port,
        quote(database, safe=""),
    )


def _lazy_prepare(token_factory: Callable) -> object:
    module = _load_harness_sibling("_phase15_e2a_harness_lifecycle")
    result = module._prepare_startup_impl(token_factory)
    if not result.success:
        raise RuntimeError("prepare failed")
    return types.SimpleNamespace(
        config_dir=result.config_dir_name,
        token=result.token,
        config_dir_obj=result.config_dir_obj,
    )


def _lazy_observe_presence(
    container_name: str, *, config_dir: str, run: object, env: object = None
) -> object:
    """Run the exact name-presence primitive and return the full immutable result.

    The full ``ContainerPresenceResult`` is returned so a later recovery path
    can re-use its validated ``container_id`` rather than a stripped status.
    """
    module = _load_harness_sibling("_phase15_e2a_harness_lifecycle")
    return module._observe_container_presence(
        container_name, config_dir=config_dir, run=run, env=env
    )


def _presence_status(presence: object) -> str:
    """Normalize an observed presence seam result to its status string.

    Injected seams may return either a status string (legacy) or a full result
    object exposing ``status``; both are accepted. A missing status fails closed
    to an empty string so no call site treats it as ``confirmed_absent``.
    """
    if isinstance(presence, str):
        return presence
    status = getattr(presence, "status", None)
    if status is None:
        return ""
    return str(status)


def _recovered_container_id(presence: object) -> str | None:
    """Recover an exact full 64-hex container ID, or None when not trustable.

    Only a ``present`` observation may carry an ID, and the ID must be an exact
    64 lowercase-hex string. Anything else fails closed so the caller never
    removes a container by name alone or with an unverified partial identity.
    """
    if _presence_status(presence) != "present":
        return None
    container_id = getattr(presence, "container_id", None)
    if type(container_id) is not str:
        return None
    if len(container_id) != 64:
        return None
    if not all(ch in _HEX64_CHARS for ch in container_id):
        return None
    return container_id


def _lazy_create_env_file(password: str, database: str, user: str) -> object:
    module = _load_harness_sibling("_phase15_e2a_harness_lifecycle")
    return module._create_env_file_impl(password, database, user)


def _lazy_docker_start(
    runner: object,
    config_dir: str,
    container_name: str,
    port: str,
    token: str,
    env_file_path: object,
    image: str,
    sanitized_env: object,
) -> object:
    module = _load_harness_sibling("_phase15_e2a_harness_lifecycle")
    return module._run_docker_start(
        runner,
        config_dir,
        container_name,
        port,
        token,
        env_file_path,
        image,
        sanitized_env,
    )


def _lazy_full_inspect(
    container_id: str,
    name: str,
    token: str,
    port: object,
    *,
    config_dir: str,
    run: object,
    env: object = None,
) -> object:
    module = _load_harness_sibling("_phase15_e2a_harness_lifecycle")
    return module._full_container_inspect(
        container_id,
        name,
        token,
        int(port),
        config_dir=config_dir,
        run=run,
        env=env,
    )


def _lazy_wait_ready(connection_factory: object, *, sleep: object = None) -> None:
    module = _load_harness_sibling("_phase15_e2a_harness_lifecycle")
    module._wait_for_ready(connection_factory, sleep=sleep)


def _lazy_sanitized_env() -> object:
    module = _load_harness_sibling("_phase15_e2a_harness_types")
    return module._sanitized_env_copy()


def _lazy_cleanup(
    *,
    container_id: str,
    container_name: str,
    token: str,
    port: object,
    config_dir: str,
    env_file_path: object,
) -> bool:
    module = _load_harness_sibling("_phase15_e2a_harness_lifecycle")
    result = module._cleanup_session_impl(
        container_id=container_id,
        container_name=container_name,
        token=token,
        port=int(port),
        config_dir=config_dir,
        runner=_lazy_runner,
        env_file_path=env_file_path,
    )
    return result.success


def _lazy_run_gate(environ: object, *, target_uri: object, **kwargs: object) -> object:
    module_name = "okf_live_production_gate"
    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached.run_migration_gate(environ, target_uri=target_uri, **kwargs)
    root = Path(__file__).resolve().parents[3]
    target = (
        root
        / "verification"
        / "phase16-raw-corpus-entity-layer"
        / "run_e2b_migration_gate.py"
    )
    module = _load_file_module(module_name, target)
    return module.run_migration_gate(environ, target_uri=target_uri, **kwargs)


def _lazy_verify_evidence_hash(path: Path, expected_sha256: str) -> bool:
    import hashlib

    if not path.exists():
        return False
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    return actual == expected_sha256


def _remove_env_file(path: Path) -> bool:
    """Delete a created env file; missing is success, other OSError is failure."""
    try:
        path.unlink()
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return True


def _controlled_connection_factory(
    connection_factory: Callable, sanitized_environ: object
) -> Callable:
    """Wrap a factory so every call forces the sanitized environ mapping.

    Positional/keyword arguments are preserved except ``environ``, which is
    unconditionally replaced with the sanitized mapping so no ambient routing
    value can ever reach a connection attempt.
    """

    def _factory(target: object, *args: object, **kwargs: object) -> object:
        kwargs["environ"] = sanitized_environ
        return connection_factory(target, *args, **kwargs)

    return _factory


def _target_bound_connection_probe(
    target: object, connection_factory: object
) -> Callable[[], object]:
    """Bind target into a zero-argument connection callable for readiness."""

    def _probe() -> object:
        return connection_factory(target)  # type: ignore[operator]

    return _probe


def _validate_outcome(outcome: object) -> None:
    """Reject any deviation from the exact seven-field gate outcome contract."""
    if outcome is None:
        raise ValueError("gate produced no outcome")
    if getattr(outcome, "status", None) != EXECUTED_STATUS:
        raise ValueError("gate status is not executed")
    if tuple(getattr(outcome, "catalog_tail", ())) != _CATALOG_TAIL:
        raise ValueError("gate catalog tail mismatch")
    if getattr(outcome, "catalog_apply_count", None) != 1:
        raise ValueError("gate catalog apply count mismatch")
    if getattr(outcome, "idempotence_reapply_count", None) != 1:
        raise ValueError("gate idempotence reapply count mismatch")
    if getattr(outcome, "idempotence_ddl_count", None) != 0:
        raise ValueError("gate idempotence ddl delta mismatch")
    if not getattr(outcome, "evidence_sha256", None):
        raise ValueError("gate evidence sha256 missing")


def run_live_gate(
    environ: Mapping[str, str] | None = None,
    *,
    target_parser=_lazy_target_parser,
    connection_factory=_lazy_connection_factory,
    runner=_lazy_runner,
    sleep_fn=_time_sleep,
    token_factory=_lazy_token_factory,
    password_factory=_lazy_password_factory,
    container_name_factory=_lazy_container_name_factory,
    port_factory=_lazy_port_factory,
    prepare=_lazy_prepare,
    observe_presence=_lazy_observe_presence,
    create_env_file=_lazy_create_env_file,
    docker_start=_lazy_docker_start,
    full_inspect=_lazy_full_inspect,
    wait_ready=_lazy_wait_ready,
    run_gate=_lazy_run_gate,
    verify_evidence_hash=_lazy_verify_evidence_hash,
    evidence_path_factory=_lazy_evidence_path_factory,
    sanitized_env=_lazy_sanitized_env,
    cleanup=_lazy_cleanup,
) -> LiveGateResult:
    """Authorize first, then one container and one gate call, always cleaned up."""
    if environ is None:
        environ = _read_routing_environ()
    disposable = environ.get(DISPOSABLE_ENV)
    authorized = environ.get(AUTH_ENV)
    expected_database = environ.get(EXPECTED_DATABASE_ENV)
    if disposable != "1" or authorized != "1" or not expected_database:
        return LiveGateResult(
            status=BLOCKED_STATUS,
            gate_outcome=None,
            evidence_verified=False,
            cleanup_ok=False,
        )
    # Fresh three-key mapping: never forward ambient extras to the gate.
    gate_environ = {
        DISPOSABLE_ENV: disposable,
        AUTH_ENV: authorized,
        EXPECTED_DATABASE_ENV: expected_database,
    }

    container_created = False
    container_id = ""
    outcome = None
    evidence_verified = False
    cleanup_ok = False
    prepare_result = None
    env_file_path = None
    try:
        prepare_result = prepare(token_factory)
        token = prepare_result.token
        password = password_factory()
        container_name = container_name_factory()
        port = port_factory()
        evidence_path = evidence_path_factory()

        docker_env = sanitized_env()
        presence = observe_presence(
            container_name,
            config_dir=prepare_result.config_dir,
            run=runner,
            env=docker_env,
        )
        if _presence_status(presence) != "confirmed_absent":
            raise RuntimeError("disposable container already present")

        target_uri = _build_loopback_target_uri(
            _DISPOSABLE_USER, password, port, expected_database
        )
        target = target_parser(target_uri, expected_database)
        # One-source contract: the env file receives the original generated
        # password plus the expected database and the fixed disposable user
        # directly. Parsing remains required to produce the connection target
        # and fails closed; parser-returned dbname/user are never reused for
        # the env file.
        env_result = create_env_file(password, expected_database, _DISPOSABLE_USER)
        if not env_result.success:
            raise RuntimeError("env file creation failed")
        env_file_path = env_result.path

        docker_result = docker_start(
            runner,
            prepare_result.config_dir,
            container_name,
            port,
            token,
            env_file_path,
            _DISPOSABLE_IMAGE,
            docker_env,
        )
        if not docker_result.success:
            if getattr(docker_result, "invalid_id", False):
                # docker run -d exited 0, so the container may exist even though
                # no usable ID was returned. Perform exactly one post-start
                # presence observation through the exact name-presence primitive.
                recovered_presence = observe_presence(
                    container_name,
                    config_dir=prepare_result.config_dir,
                    run=runner,
                    env=docker_env,
                )
                recovered_id = _recovered_container_id(recovered_presence)
                if recovered_id is None:
                    # Identity is not safely recoverable: fail closed with a
                    # fixed redacted error, never delete by name alone, and do
                    # not pretend the container was removed.
                    raise RuntimeError(_START_RECOVERY_UNRESOLVED_ERROR)
                container_id = recovered_id
                container_created = True
                raise RuntimeError(_START_RECOVERY_ERROR)
            raise RuntimeError("docker start failed")
        container_id = docker_result.container_id
        container_created = True

        inspect_result = full_inspect(
            container_id,
            container_name,
            token,
            port,
            config_dir=prepare_result.config_dir,
            run=runner,
            env=docker_env,
        )
        if not inspect_result.valid:
            raise RuntimeError("container inspect failed")

        controlled_factory = _controlled_connection_factory(
            connection_factory, docker_env
        )
        wait_ready(
            _target_bound_connection_probe(target, controlled_factory),
            sleep=sleep_fn,
        )

        outcome = run_gate(
            gate_environ,
            target_uri=target_uri,
            evidence_path=evidence_path,
            connection_factory=controlled_factory,
        )
        _validate_outcome(outcome)

        evidence_verified = verify_evidence_hash(evidence_path, outcome.evidence_sha256)
        if not evidence_verified:
            raise RuntimeError("evidence hash mismatch")
    finally:
        try:
            if container_created:
                cleanup_ok = bool(
                    cleanup(
                        container_id=container_id,
                        container_name=container_name,
                        token=token,
                        port=port,
                        config_dir=prepare_result.config_dir,
                        env_file_path=env_file_path,
                    )
                )
                if not cleanup_ok:
                    raise RuntimeError("cleanup failed")
            elif env_file_path is not None:
                if not _remove_env_file(env_file_path):
                    raise RuntimeError("credential file cleanup failed")
        finally:
            config_dir_obj = (
                getattr(prepare_result, "config_dir_obj", None)
                if prepare_result is not None
                else None
            )
            if config_dir_obj is not None:
                config_dir_obj.cleanup()
    return LiveGateResult(
        status=EXECUTED_STATUS,
        gate_outcome=outcome,
        evidence_verified=evidence_verified,
        cleanup_ok=cleanup_ok,
    )
