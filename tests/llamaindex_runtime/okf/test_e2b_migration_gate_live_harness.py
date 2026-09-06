"""FROZEN Phase 16-14 live harness RED contract.

The future live harness ``tests/llamaindex_runtime/okf/run_e2b_migration_gate_live.py``
is loaded lazily so collection stays valid while absent; every test that needs it
fails with an explicit ``RED: live harness absent`` message.

The contract pins the authorized orchestration as an exactly-once, fully injected
sequence: prepare -> absence -> env-file -> docker-start -> inspect -> readiness
(NO migration) -> gate exactly once with keyword-only ``target_uri`` -> evidence/hash
validation -> finally cleanup. Authorization is checked first: an unauthorized
invocation returns the exact ``blocked_not_executed`` status with zero touch before
generating secrets/containers/ports/tempfiles or touching Docker/connection/gate.
Only the three gate-routing environment keys may ever be read. One invocation owns
one container and issues one gate call, no loop/retry. Failure after container
creation still cleans up; cleanup failure fails closed. The harness never writes
evidence. All tests are pure-injected/static: no Docker, database, or network.
"""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import sys
import types
from collections.abc import Mapping
from pathlib import Path

import pytest

from llamaindex_runtime.registry.migration_catalog import FULL_MIGRATION_CATALOG

HARNESS_NAME = "run_e2b_migration_gate_live"
HARNESS_PATH = Path(__file__).with_name(f"{HARNESS_NAME}.py")
HARNESS_MODULE = f"tests.llamaindex_runtime.okf.{HARNESS_NAME}"

# The three gate-routing keys -- the ONLY environment the live harness may read.
AUTH_ENV = "OKF_E2B_MIGRATION_TEST_AUTHORIZED"
DISPOSABLE_ENV = "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE"
EXPECTED_DATABASE_ENV = "OKF_REBUILD_EXPECTED_DATABASE"
_GATE_ROUTING_KEYS = frozenset((AUTH_ENV, DISPOSABLE_ENV, EXPECTED_DATABASE_ENV))

# The nine routing/authorization switches that must never leak into or be read
# by the live harness.
_OTHER_ROUTING_KEYS = frozenset(
    "DATABASE_URL FORMAL_RUNTIME_DATABASE_URL "
    "OKF_FAILURE_AUDIT_ACCEPTANCE OKF_REBUILD_DOCKER_ACCEPTANCE "
    "OKF_E2A_DISPOSABLE_TEST_AUTHORIZED OKF_E2B_DISPOSABLE_TEST_AUTHORIZED "
    "OKF_E2B_MODELSCOPE_MIRROR_AUTHORIZED OKF_E2B_RANER_SMOKE_AUTHORIZED "
    "OKF_E2B_C2_ENTRY_AUTHORIZED".split()
)

_EXPECTED_DB = "okf_e2b_migration_disposable"
_DISPOSABLE_USER = "okf"
_CATALOG_TAIL = ("019_e2a_materialization_contract.sql", "020_ner_entity_mentions.sql")

# Bytes the fake gate writes as evidence -- never written by the harness.
_EVIDENCE_BYTES = b"live-gate-fake-evidence\n"
_EVIDENCE_SHA256 = hashlib.sha256(_EVIDENCE_BYTES).hexdigest()

_BLOCKED_STATUS = "blocked_not_executed"
_EXECUTED_STATUS = "executed"

# The orchestration steps, in exact order, each occurring exactly once.
_ORCHESTRATION = (
    "prepare",
    "absence",
    "env_file",
    "docker_start",
    "inspect",
    "readiness",
    "gate",
    "evidence_verify",
    "cleanup",
)


def _authorized_env() -> dict[str, str]:
    """Explicit authorized live-harness environment -- never ambient env."""
    return {
        DISPOSABLE_ENV: "1",
        EXPECTED_DATABASE_ENV: _EXPECTED_DB,
        AUTH_ENV: "1",
    }


def _harness() -> types.ModuleType:
    """Lazily load the live harness; fail with a clear RED when absent."""
    if not HARNESS_PATH.is_file():
        pytest.fail(f"RED: live harness absent: {HARNESS_PATH}")
    spec = importlib.util.spec_from_file_location(HARNESS_MODULE, str(HARNESS_PATH))
    if spec is None or spec.loader is None:
        pytest.fail(f"RED: live harness unloadable: {HARNESS_PATH}")
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "tests.llamaindex_runtime.okf"
    sys.modules[HARNESS_MODULE] = module
    spec.loader.exec_module(module)
    return module


def _harness_source() -> str:
    """Read the live harness source; fail with a clear RED when absent."""
    if not HARNESS_PATH.is_file():
        pytest.fail(f"RED: live harness source absent: {HARNESS_PATH}")
    return HARNESS_PATH.read_text(encoding="utf-8")


class _FakeGateOutcome:
    """GateOutcome-shaped fake surfacing the exact facts the harness validates."""

    def __init__(
        self,
        *,
        status: str = _EXECUTED_STATUS,
        catalog_tail: tuple[str, ...] = _CATALOG_TAIL,
        catalog_apply_count: int = 1,
        idempotence_reapply_count: int = 1,
        idempotence_ddl_count: int = 0,
        inventory: Mapping[str, object] | None = None,
        evidence_sha256: str | None = _EVIDENCE_SHA256,
    ) -> None:
        self.status = status
        self.catalog_tail = catalog_tail
        self.catalog_apply_count = catalog_apply_count
        self.idempotence_reapply_count = idempotence_reapply_count
        self.idempotence_ddl_count = idempotence_ddl_count
        self.inventory = {} if inventory is None else inventory
        self.evidence_sha256 = evidence_sha256


class _RecordingEnviron(dict):
    """A dict recording every lookup and every enumeration/copy attempt."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.get_calls: list[str] = []
        self.enumeration_calls: list[str] = []

    def get(self, key: str, default: object = None) -> object:
        self.get_calls.append(key)
        return super().get(key, default)

    def keys(self):
        self.enumeration_calls.append("keys")
        return super().keys()

    def items(self):
        self.enumeration_calls.append("items")
        return super().items()

    def values(self):
        self.enumeration_calls.append("values")
        return super().values()

    def copy(self):
        self.enumeration_calls.append("copy")
        return type(self)(super().copy())


class _FakeHarness:
    """Pure-fake seams driving the live harness with a complete call log.

    Every orchestration seam appends its event to ``call_log``; generation seams
    are likewise logged so the zero-touch boundary is provable. No Docker/DB/network.
    """

    def __init__(
        self,
        *,
        token: str = "0" * 64,
        password: str = "live_fake_password_123",
        container_name: str = "e2b-live-abcd1234",
        port: str = "5432",
        container_id: str = "1" * 64,
        evidence_path: Path | None = None,
        config_dir_obj: object = None,
        env_file_path: Path | None = None,
        prepare_ok: bool = True,
        absence_ok: bool = True,
        env_file_ok: bool = True,
        start_ok: bool = True,
        start_invalid_id: bool = False,
        recovery_presence: object = None,
        inspect_ok: bool = True,
        ready_ok: bool = True,
        gate_error: Exception | None = None,
        outcome: _FakeGateOutcome | None = None,
        verify_ok: bool = True,
        tampered_evidence: bool = False,
        cleanup_ok: bool = True,
        cleanup_error: Exception | None = None,
    ) -> None:
        self.token = token
        self.password = password
        self.container_name = container_name
        self.port = port
        self.container_id = container_id
        self.evidence_path = evidence_path
        self.config_dir_obj = config_dir_obj
        self.env_file_path = (
            env_file_path if env_file_path is not None else Path("fake-okf.env")
        )
        self.prepare_ok = prepare_ok
        self.absence_ok = absence_ok
        self.env_file_ok = env_file_ok
        self.start_ok = start_ok
        self.start_invalid_id = start_invalid_id
        self.recovery_presence = recovery_presence
        self.inspect_ok = inspect_ok
        self.ready_ok = ready_ok
        self.gate_error = gate_error
        self.outcome = outcome
        self.verify_ok = verify_ok
        self.tampered_evidence = tampered_evidence
        self.cleanup_ok = cleanup_ok
        self.cleanup_error = cleanup_error
        self.call_log: list[tuple[object, ...]] = []
        # Per-invocation state for corrective assertions (default-path defects).
        self.sanitized_env_value: dict[str, str] = {"PATH": "/usr/bin"}
        self.target = types.SimpleNamespace(dbname=_EXPECTED_DB)
        self.cleanup_ports: list[object] = []
        self.cleanup_env_files: list[object] = []
        self.absence_envs: list[object] = []
        for name in (
            "token_calls",
            "password_calls",
            "container_name_calls",
            "port_calls",
            "evidence_path_calls",
            "target_parser_calls",
            "connection_factory_calls",
            "prepare_calls",
            "absence_calls",
            "env_file_calls",
            "docker_start_calls",
            "inspect_calls",
            "ready_calls",
            "gate_calls",
            "verify_calls",
            "cleanup_calls",
            "sanitized_env_calls",
        ):
            setattr(self, name, [])

    # --- generation seams (zero-touch boundary) ---
    def token_factory(self) -> str:
        self.token_calls.append(None)
        self.call_log.append(("token",))
        return self.token

    def password_factory(self) -> str:
        self.password_calls.append(None)
        self.call_log.append(("password",))
        return self.password

    def container_name_factory(self) -> str:
        self.container_name_calls.append(None)
        self.call_log.append(("container_name",))
        return self.container_name

    def port_factory(self) -> str:
        self.port_calls.append(None)
        self.call_log.append(("port",))
        return self.port

    def evidence_path_factory(self) -> Path | None:
        self.evidence_path_calls.append(None)
        self.call_log.append(("evidence_path",))
        return self.evidence_path

    def sanitized_env(self) -> object:
        self.sanitized_env_calls.append(None)
        self.call_log.append(("sanitized_env",))
        return self.sanitized_env_value

    # --- infra seams (default-path only; must not fire when injected) ---
    def target_parser(self, target_uri: object, expected_database: object) -> object:
        self.target_parser_calls.append((target_uri, expected_database))
        return self.target

    def connection_factory(
        self, target: object, *args: object, **kwargs: object
    ) -> object:
        self.connection_factory_calls.append((target, args, kwargs))
        return object()

    def runner(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("runner must not be used with injected orchestration")

    def sleep_fn(self, seconds: object) -> None:
        raise AssertionError("sleep_fn must not be used with injected wait_ready")

    # --- orchestration seams (exact ordered contract) ---
    def prepare(self, token_factory: object) -> object:
        token = token_factory()  # type: ignore[call-arg]
        self.prepare_calls.append(token)
        self.call_log.append(("prepare",))
        if not self.prepare_ok:
            raise RuntimeError("prepare failed")
        return types.SimpleNamespace(
            config_dir="docker-config-empty-fake",
            token=token,
            config_dir_obj=self.config_dir_obj,
        )

    def observe_presence(
        self, container_name: str, *, config_dir: str, run: object, env: object = None
    ) -> object:
        self.absence_calls.append(container_name)
        self.absence_envs.append(env)
        self.call_log.append(("absence",))
        if not self.absence_ok:
            return "present"
        if self.recovery_presence is not None and self.docker_start_calls:
            # Post-start recovery observation: docker_start already ran, so this
            # is the single bounded recovery observation after invalid_id.
            return self.recovery_presence
        return "confirmed_absent"

    def create_env_file(self, password: str, database: str, user: str) -> object:
        self.env_file_calls.append((password, database, user))
        self.call_log.append(("env_file",))
        if not self.env_file_ok:
            return types.SimpleNamespace(success=False, path=None)
        return types.SimpleNamespace(success=True, path=self.env_file_path)

    def docker_start(
        self,
        runner: object,
        config_dir: str,
        container_name: str,
        port: str,
        token: str,
        env_file_path: object,
        image: str,
        sanitized_env: object,
    ) -> object:
        # NOTE: no password parameter -- password must never reach Docker argv.
        self.docker_start_calls.append(
            (container_name, port, token, env_file_path, image, sanitized_env)
        )
        self.call_log.append(("docker_start",))
        if not self.start_ok:
            if self.start_invalid_id:
                # docker run -d exited 0 but stdout was not a usable ID: the
                # container may still exist and must be recovered by name.
                return types.SimpleNamespace(
                    success=False, container_id="", invalid_id=True
                )
            return types.SimpleNamespace(
                success=False, container_id="", invalid_id=False
            )
        return types.SimpleNamespace(success=True, container_id=self.container_id)

    def full_inspect(
        self,
        container_id: str,
        name: str,
        token: str,
        port: int,
        *,
        config_dir: str,
        run: object,
        env: object = None,
    ) -> object:
        self.inspect_calls.append(container_id)
        self.call_log.append(("inspect",))
        return types.SimpleNamespace(valid=self.inspect_ok)

    def wait_ready(self, connection_factory: object, *, sleep: object = None) -> None:
        self.ready_calls.append(connection_factory)
        self.call_log.append(("readiness",))
        if not self.ready_ok:
            raise RuntimeError("database never became ready")

    def run_gate(self, environ: object, *, target_uri: str, **kwargs: object) -> object:
        self.gate_calls.append((environ, target_uri, kwargs))
        self.call_log.append(("gate",))
        if self.gate_error is not None:
            raise self.gate_error
        if self.outcome is None:
            self.outcome = _FakeGateOutcome()
        payload = (
            _EVIDENCE_BYTES if not self.tampered_evidence else b"tampered-evidence\n"
        )
        evidence_path = kwargs.get("evidence_path")
        if evidence_path is not None:
            evidence_path.write_bytes(payload)  # the GATE writes evidence, not harness
        return self.outcome

    def verify_evidence_hash(self, path: Path, expected_sha256: str) -> bool:
        self.verify_calls.append((path, expected_sha256))
        self.call_log.append(("evidence_verify",))
        if not path.exists():
            return False
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        return actual == expected_sha256 and self.verify_ok

    def cleanup(
        self,
        *,
        container_id: str,
        container_name: str,
        token: str,
        port: object,
        config_dir: str,
        env_file_path: object,
    ) -> bool:
        self.cleanup_calls.append(container_id)
        self.cleanup_ports.append(port)
        self.cleanup_env_files.append(env_file_path)
        self.call_log.append(("cleanup",))
        if self.cleanup_error is not None:
            raise self.cleanup_error
        # Fidelity to the real _cleanup_session_impl: the credential env file is
        # always deleted after a container-cleanup attempt.
        if env_file_path is not None:
            try:
                env_file_path.unlink()
            except FileNotFoundError:
                pass
        return self.cleanup_ok


class _RecordingConfigDir:
    """Recording stand-in for the prepared TemporaryDirectory owner."""

    def __init__(self) -> None:
        self.cleanup_calls = 0

    @property
    def cleanup_called(self) -> bool:
        return self.cleanup_calls > 0

    def cleanup(self) -> None:
        self.cleanup_calls += 1


def _run_live(
    module: types.ModuleType,
    deps: _FakeHarness,
    *,
    environ: Mapping[str, str] | None = None,
    evidence_path: Path | None = None,
) -> object:
    """Drive the live harness with every seam injected as keyword arguments."""
    if evidence_path is not None:
        deps.evidence_path = evidence_path
    return module.run_live_gate(
        _authorized_env() if environ is None else environ,
        target_parser=deps.target_parser,
        connection_factory=deps.connection_factory,
        runner=deps.runner,
        sleep_fn=deps.sleep_fn,
        token_factory=deps.token_factory,
        password_factory=deps.password_factory,
        container_name_factory=deps.container_name_factory,
        port_factory=deps.port_factory,
        prepare=deps.prepare,
        observe_presence=deps.observe_presence,
        create_env_file=deps.create_env_file,
        docker_start=deps.docker_start,
        full_inspect=deps.full_inspect,
        wait_ready=deps.wait_ready,
        run_gate=deps.run_gate,
        verify_evidence_hash=deps.verify_evidence_hash,
        evidence_path_factory=deps.evidence_path_factory,
        sanitized_env=deps.sanitized_env,
        cleanup=deps.cleanup,
    )


def _orchestration_events(deps: _FakeHarness) -> list[str]:
    return [e[0] for e in deps.call_log if e[0] in _ORCHESTRATION]


# --- lazy-load RED (harness absent until implemented) ---
def test_live_harness_module_must_exist_for_lazy_load() -> None:
    assert HARNESS_PATH.is_file(), f"RED: live harness absent: {HARNESS_PATH}"


# --- authorization-first contract ---
def test_unauthorized_returns_blocked_not_executed_with_zero_touch(
    tmp_path: Path,
) -> None:
    module = _harness()
    deps = _FakeHarness()
    evidence_path = tmp_path / "evidence.md"
    result = _run_live(
        module,
        deps,
        environ={},
        evidence_path=evidence_path,
    )
    assert result.status == _BLOCKED_STATUS
    assert result.gate_outcome is None
    assert result.evidence_verified is False
    assert result.cleanup_ok is False
    assert deps.target_parser_calls == []  # no URI constructed/parsed
    assert deps.call_log == []  # zero-touch: no secret/container/port/tempfile
    assert not evidence_path.exists()
    for name in (
        "token_calls",
        "password_calls",
        "container_name_calls",
        "port_calls",
        "prepare_calls",
        "absence_calls",
        "env_file_calls",
        "docker_start_calls",
        "inspect_calls",
        "ready_calls",
        "gate_calls",
        "verify_calls",
        "cleanup_calls",
        "evidence_path_calls",
        "sanitized_env_calls",
    ):
        assert getattr(deps, name) == []


def test_unauthorized_reads_only_gate_routing_keys() -> None:
    module = _harness()
    fake = _RecordingEnviron(
        {"DATABASE_URL": "postgresql://okf:secret@127.0.0.1:5432/prod"}
    )
    deps = _FakeHarness()
    result = _run_live(module, deps, environ=fake)
    assert result.status == _BLOCKED_STATUS
    assert set(fake.get_calls) <= _GATE_ROUTING_KEYS
    assert "DATABASE_URL" not in fake.get_calls
    assert fake.enumeration_calls == []


def test_run_live_gate_has_no_caller_target_uri_but_keeps_seams() -> None:
    module = _harness()
    assert callable(module.run_live_gate)
    signature = inspect.signature(module.run_live_gate)
    # The caller must never supply a raw target_uri; it is built internally.
    assert "target_uri" not in signature.parameters
    for seam in (
        "target_parser",
        "connection_factory",
        "runner",
        "sleep_fn",
        "token_factory",
        "password_factory",
        "container_name_factory",
        "port_factory",
        "prepare",
        "observe_presence",
        "create_env_file",
        "docker_start",
        "full_inspect",
        "wait_ready",
        "run_gate",
        "verify_evidence_hash",
        "evidence_path_factory",
        "cleanup",
    ):
        assert seam in signature.parameters, f"public gate seam missing: {seam}"


# --- authorized fully injected orchestration ---
def test_authorized_full_path_exact_order_single_invocation(tmp_path: Path) -> None:
    module = _harness()
    deps = _FakeHarness()
    evidence_path = tmp_path / "evidence.md"
    result = _run_live(module, deps, evidence_path=evidence_path)

    assert _orchestration_events(deps) == list(_ORCHESTRATION)
    assert deps.call_log[-1][0] == "cleanup"
    for event in _ORCHESTRATION:
        assert [e[0] for e in deps.call_log].count(event) == 1, event

    # Generation (secret/container/port/tempfile-path) happens after auth,
    # before any Docker-touching absence check.
    events = [e[0] for e in deps.call_log]
    absence_index = events.index("absence")
    for generation in ("token", "password", "container_name", "port"):
        assert generation in events, generation
        assert events.index(generation) < absence_index, generation

    # One container, one gate call; the internally built target is used for
    # parser, env-file, and the keyword-only production gate target.
    assert len(deps.docker_start_calls) == 1
    assert deps.docker_start_calls[0][0] == deps.container_name
    assert deps.docker_start_calls[0][1] == deps.port  # real port published
    assert deps.docker_start_calls[0][2] == deps.token
    expected_uri = module._build_loopback_target_uri(
        _DISPOSABLE_USER, deps.password, deps.port, _EXPECTED_DB
    )
    assert deps.target_parser_calls == [(expected_uri, _EXPECTED_DB)]
    assert deps.env_file_calls == [(deps.password, _EXPECTED_DB, _DISPOSABLE_USER)]
    assert len(deps.gate_calls) == 1
    assert deps.gate_calls[0][1] == expected_uri
    assert deps.gate_calls[0][2]["evidence_path"] is evidence_path
    assert deps.cleanup_calls == [deps.container_id]

    # Result contract.
    assert result.status == _EXECUTED_STATUS
    assert result.gate_outcome is deps.outcome
    assert result.evidence_verified is True
    assert result.cleanup_ok is True


def test_authorized_reads_only_gate_routing_keys(tmp_path: Path) -> None:
    module = _harness()
    fake = _RecordingEnviron(_authorized_env())
    fake["DATABASE_URL"] = "postgresql://okf:secret@127.0.0.1:5432/prod"
    fake["OKF_E2B_C2_ENTRY_AUTHORIZED"] = "1"
    deps = _FakeHarness()
    _run_live(module, deps, environ=fake, evidence_path=tmp_path / "evidence.md")
    assert set(fake.get_calls) == _GATE_ROUTING_KEYS
    assert "DATABASE_URL" not in fake.get_calls
    assert "OKF_E2B_C2_ENTRY_AUTHORIZED" not in fake.get_calls
    assert fake.enumeration_calls == []


def test_gate_outcome_facts_validated_on_success(tmp_path: Path) -> None:
    module = _harness()
    deps = _FakeHarness()
    result = _run_live(module, deps, evidence_path=tmp_path / "evidence.md")
    outcome = result.gate_outcome
    assert outcome.status == _EXECUTED_STATUS
    assert outcome.catalog_tail == _CATALOG_TAIL
    assert outcome.catalog_apply_count == 1
    assert outcome.idempotence_reapply_count == 1
    assert outcome.idempotence_ddl_count == 0
    assert outcome.evidence_sha256 and len(outcome.evidence_sha256) == 64


@pytest.mark.parametrize(
    ("name", "overrides"),
    [
        ("status-not-executed", {"status": "failed"}),
        ("wrong-catalog-tail", {"catalog_tail": (FULL_MIGRATION_CATALOG[-2],)}),
        ("apply-count-ne-1", {"catalog_apply_count": 2}),
        ("reapply-count-ne-1", {"idempotence_reapply_count": 0}),
        ("ddl-delta-ne-0", {"idempotence_ddl_count": 1}),
        ("empty-evidence-hash", {"evidence_sha256": ""}),
        ("none-evidence-hash", {"evidence_sha256": None}),
    ],
)
def test_run_live_gate_rejects_invalid_gate_outcome(
    tmp_path: Path, name: str, overrides: dict[str, object]
) -> None:
    module = _harness()
    kwargs = dict(
        status=_EXECUTED_STATUS,
        catalog_tail=_CATALOG_TAIL,
        catalog_apply_count=1,
        idempotence_reapply_count=1,
        idempotence_ddl_count=0,
        evidence_sha256=_EVIDENCE_SHA256,
    )
    kwargs.update(overrides)
    deps = _FakeHarness(outcome=_FakeGateOutcome(**kwargs))  # type: ignore[arg-type]
    with pytest.raises(Exception):
        _run_live(module, deps, evidence_path=tmp_path / "evidence.md")
    assert len(deps.gate_calls) == 1
    assert deps.cleanup_calls == [deps.container_id]


# --- evidence/hash validation ---
def test_injected_fake_evidence_bytes_and_path_hash_match(tmp_path: Path) -> None:
    module = _harness()
    deps = _FakeHarness()
    evidence_path = tmp_path / "evidence.md"
    result = _run_live(module, deps, evidence_path=evidence_path)
    assert evidence_path.read_bytes() == _EVIDENCE_BYTES
    assert deps.verify_calls == [(evidence_path, _EVIDENCE_SHA256)]
    assert result.evidence_verified is True


def test_evidence_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    module = _harness()
    deps = _FakeHarness(tampered_evidence=True)
    with pytest.raises(Exception):
        _run_live(module, deps, evidence_path=tmp_path / "evidence.md")
    assert len(deps.verify_calls) == 1
    assert deps.cleanup_calls == [deps.container_id]


# --- cleanup semantics ---
def test_cleanup_failure_fails_closed(tmp_path: Path) -> None:
    module = _harness()
    deps = _FakeHarness(cleanup_error=RuntimeError("cleanup exploded"))
    with pytest.raises(Exception, match="cleanup"):
        _run_live(module, deps, evidence_path=tmp_path / "evidence.md")
    assert len(deps.gate_calls) == 1
    assert len(deps.cleanup_calls) == 1


@pytest.mark.parametrize(
    ("failure", "flag"),
    [
        ("inspect", "inspect_ok"),
        ("readiness", "ready_ok"),
        ("gate", "gate_error"),
    ],
)
def test_failure_after_container_creation_always_cleans_up(
    tmp_path: Path, failure: str, flag: str
) -> None:
    module = _harness()
    deps = _FakeHarness()
    setattr(
        deps, flag, RuntimeError("injected failure") if flag == "gate_error" else False
    )
    with pytest.raises(Exception):
        _run_live(module, deps, evidence_path=tmp_path / "evidence.md")
    assert len(deps.docker_start_calls) == 1  # container was created
    assert deps.cleanup_calls == [deps.container_id]  # always cleanup
    assert deps.call_log[-1][0] == "cleanup"


@pytest.mark.parametrize(
    ("failure", "flag"),
    [
        ("prepare", "prepare_ok"),
        ("absence", "absence_ok"),
        ("env-file", "env_file_ok"),
        ("docker-start", "start_ok"),
    ],
)
def test_failure_before_container_creation_no_cleanup(
    tmp_path: Path, failure: str, flag: str
) -> None:
    module = _harness()
    deps = _FakeHarness()
    setattr(deps, flag, False)
    with pytest.raises(Exception):
        _run_live(module, deps, evidence_path=tmp_path / "evidence.md")
    assert deps.cleanup_calls == []  # no container owned by this invocation
    assert deps.gate_calls == []


def test_each_invocation_is_isolated_one_container_one_gate(tmp_path: Path) -> None:
    module = _harness()
    first = _FakeHarness(container_id="1" * 64)
    second = _FakeHarness(container_id="2" * 64)
    _run_live(module, first, evidence_path=tmp_path / "evidence_1.md")
    _run_live(module, second, evidence_path=tmp_path / "evidence_2.md")
    assert len(first.docker_start_calls) == 1 and len(first.gate_calls) == 1
    assert len(second.docker_start_calls) == 1 and len(second.gate_calls) == 1
    assert first.container_id != second.container_id
    assert first.cleanup_calls == ["1" * 64]
    assert second.cleanup_calls == ["2" * 64]


# --- harness never writes evidence ---
def test_harness_never_writes_evidence_itself(tmp_path: Path) -> None:
    module = _harness()
    deps = _FakeHarness()
    evidence_path = tmp_path / "evidence.md"
    _run_live(module, deps, evidence_path=evidence_path)
    # Only the (fake) gate wrote the file; the harness only verified the hash.
    assert evidence_path.read_bytes() == _EVIDENCE_BYTES
    assert len(deps.verify_calls) == 1
    assert deps.cleanup_calls == [deps.container_id]


def test_source_forbids_direct_evidence_writes() -> None:
    source = _harness_source()
    for forbidden in ("write_text(", "write_bytes(", ".open(", "os.makedirs"):
        assert forbidden not in source, f"direct evidence writer forbidden: {forbidden}"


# --- source guards ---
def test_source_forbids_disposable_session_and_migrations() -> None:
    source = _harness_source()
    for forbidden in (
        "DisposableE2aSession",
        "run_migrations",
        "_apply_migrations",
        "apply_catalog",
        "time.sleep",
        "sleep(",
        "for attempt",
        "while True",
        "retry",
        "backoff",
    ):
        assert forbidden not in source, f"forbidden live-harness reference: {forbidden}"


def test_source_forbids_password_in_docker_argv_and_shell() -> None:
    source = _harness_source()
    assert "shell=True" not in source
    assert "POSTGRES_PASSWORD=" not in source
    assert "os.system" not in source
    assert "os.popen" not in source
    assert "Popen" not in source


def test_source_no_raw_uri_from_env_or_argv() -> None:
    source = _harness_source()
    for forbidden in (
        "DATABASE_URL",
        "FORMAL_RUNTIME_DATABASE_URL",
        "sys.argv",
        "getenv(",
    ):
        assert forbidden not in source, f"raw URI/env/argv source: {forbidden}"


def test_source_reads_only_the_three_routing_keys() -> None:
    source = _harness_source()
    for key in _GATE_ROUTING_KEYS:
        assert key in source, f"routing key missing: {key}"
    for key in _OTHER_ROUTING_KEYS:
        assert key not in source, f"forbidden routing key present: {key}"


def test_source_forbids_environment_enumeration_and_copy() -> None:
    source = _harness_source()
    assert source.count("os.environ") == 1
    for forbidden in (
        "os.environ.copy",
        "dict(os.environ",
        "environ.items()",
        "environ.keys()",
        "environ.values()",
    ):
        assert forbidden not in source


def test_source_no_sensitive_print() -> None:
    source = _harness_source()
    sensitive = ("password", "token", "secret", "target_uri", "container_id", "uri")
    for line in source.splitlines():
        if "print(" in line:
            assert not any(
                s in line for s in sensitive
            ), f"sensitive print: {line.strip()}"


def test_source_pins_injected_seams_and_keyword_only_target() -> None:
    source = _harness_source()
    assert "def run_live_gate(" in source
    assert "target_uri" in source
    assert "*," in source, "keyword-only target is required"
    for seam in (
        "target_parser=",
        "connection_factory=",
        "token_factory=",
        "password_factory=",
        "container_name_factory=",
        "port_factory=",
        "prepare=",
        "observe_presence=",
        "create_env_file=",
        "docker_start=",
        "full_inspect=",
        "wait_ready=",
        "run_gate=",
        "verify_evidence_hash=",
        "evidence_path_factory=",
        "cleanup=",
    ):
        assert seam in source, f"public harness seam missing: {seam}"


def test_source_builds_internal_target_with_percent_encoding() -> None:
    """The harness builds its own loopback URI with quote(value, safe='')."""
    source = _harness_source()
    assert "def _build_loopback_target_uri(" in source
    assert 'safe=""' in source
    assert "_DISPOSABLE_USER" in source
    assert "127.0.0.1" in source


def test_source_defines_controlled_connection_factory() -> None:
    """The harness must define the environ-forcing connection wrapper."""
    source = _harness_source()
    assert "def _controlled_connection_factory(" in source
    assert "environ" in source


# --- corrective tests for confirmed default-path defects (RED before fix) ---
def test_harness_loads_lifecycle_sibling_package_aware() -> None:
    """Package-aware lazy import: relative sibling imports must resolve."""
    module = _harness()
    lifecycle = module._load_harness_sibling("_phase15_e2a_harness_lifecycle")
    assert lifecycle.__package__ == "tests.llamaindex_runtime.okf"
    assert callable(lifecycle._sanitized_env_copy)
    assert callable(lifecycle._cleanup_session_impl)
    # The same helper must be cached and reused.
    assert module._load_harness_sibling("_phase15_e2a_harness_lifecycle") is lifecycle


def test_harness_does_not_mutate_injected_dependency(tmp_path: Path) -> None:
    """The harness must never rewrite injected dependency internal state."""
    module = _harness()
    deps = _FakeHarness(container_id="1" * 64)
    _run_live(module, deps, evidence_path=tmp_path / "evidence.md")
    assert deps.container_id == "1" * 64
    assert deps.docker_start_calls[0][2] == deps.token


def test_cleanup_receives_real_port_not_zero(tmp_path: Path) -> None:
    """Cleanup must attest the real port, never a hardcoded zero."""
    module = _harness()
    deps = _FakeHarness(port="55321")
    result = _run_live(module, deps, evidence_path=tmp_path / "evidence.md")
    assert result.cleanup_ok is True
    assert deps.cleanup_ports == ["55321"]
    assert deps.docker_start_calls[0][1] == "55321"
    assert deps.cleanup_calls == [deps.container_id]


def test_readiness_uses_target_bound_zero_arg_probe(tmp_path: Path) -> None:
    """Readiness must get a zero-argument probe bound to the parsed target."""
    module = _harness()
    deps = _FakeHarness()
    _run_live(module, deps, evidence_path=tmp_path / "evidence.md")
    assert len(deps.ready_calls) == 1
    probe = deps.ready_calls[0]
    assert callable(probe)
    assert deps.connection_factory_calls == []
    probe()  # zero-argument probe opens a connection on the parsed target
    assert len(deps.connection_factory_calls) == 1
    target, args, kwargs = deps.connection_factory_calls[0]
    assert target is deps.target
    assert args == ()
    assert kwargs == {"environ": deps.sanitized_env_value}


def test_docker_helpers_receive_sanitized_env_not_gate_environ(
    tmp_path: Path,
) -> None:
    """Docker subprocess env must never be the gate environ."""
    module = _harness()
    deps = _FakeHarness()
    environ = _authorized_env()
    environ["DATABASE_URL"] = "postgresql://leak:secret@127.0.0.1:5432/prod"
    _run_live(module, deps, environ=environ, evidence_path=tmp_path / "evidence.md")
    assert deps.absence_envs == [deps.sanitized_env_value]
    assert deps.docker_start_calls[0][5] is deps.sanitized_env_value
    assert deps.docker_start_calls[0][5] is not environ


def test_gate_receives_fresh_three_key_environ_even_with_extras(
    tmp_path: Path,
) -> None:
    """The gate environ is a fresh three-key mapping, never the ambient extras."""
    module = _harness()
    deps = _FakeHarness()
    environ = _authorized_env()
    environ["DATABASE_URL"] = "postgresql://leak:secret@127.0.0.1:5432/prod"
    environ["OKF_E2B_C2_ENTRY_AUTHORIZED"] = "1"
    _run_live(module, deps, environ=environ, evidence_path=tmp_path / "evidence.md")
    assert len(deps.gate_calls) == 1
    captured = deps.gate_calls[0][0]
    assert captured is not environ
    assert set(captured) == {DISPOSABLE_ENV, AUTH_ENV, EXPECTED_DATABASE_ENV}
    assert captured[DISPOSABLE_ENV] == "1"
    assert captured[AUTH_ENV] == "1"
    assert captured[EXPECTED_DATABASE_ENV] == _EXPECTED_DB


def test_controlled_connection_factory_forces_environ_and_preserves_kwargs() -> None:
    """The wrapper forces environ while preserving positionals and kwargs."""
    module = _harness()
    calls: list[tuple[object, tuple[object, ...], dict[str, object]]] = []

    def _fake(target: object, *args: object, **kwargs: object) -> object:
        calls.append((target, args, kwargs))
        return "connection"

    sanitized = {"PATH": "/usr/bin"}
    wrapped = module._controlled_connection_factory(_fake, sanitized)
    assert wrapped("target", "positional", autocommit=True) == "connection"
    assert calls == [
        ("target", ("positional",), {"environ": sanitized, "autocommit": True})
    ]


def test_readiness_and_gate_factory_share_sanitized_env(tmp_path: Path) -> None:
    """Readiness and the gate-captured factory never see ambient/routing values."""
    module = _harness()
    deps = _FakeHarness()
    environ = _authorized_env()
    environ["DATABASE_URL"] = "postgresql://leak:secret@127.0.0.1:5432/prod"
    _run_live(module, deps, environ=environ, evidence_path=tmp_path / "evidence.md")

    # The gate captured a callable connection factory.
    assert len(deps.gate_calls) == 1
    controlled = deps.gate_calls[0][2]["connection_factory"]
    assert callable(controlled)

    # Readiness invocation (the recorded zero-arg probe).
    assert len(deps.ready_calls) == 1
    deps.ready_calls[0]()  # type: ignore[operator]

    # Direct invocation (e.g. autocommit) forces the same sanitized env.
    controlled(deps.target, autocommit=True)

    # Every connection attempt received exactly the sanitized mapping.
    assert len(deps.connection_factory_calls) == 2
    for target, args, kwargs in deps.connection_factory_calls:
        assert target is deps.target
        assert args == ()
        assert kwargs["environ"] is deps.sanitized_env_value
        assert kwargs["environ"] is not environ
        assert set(kwargs["environ"]) == {"PATH"}  # no ambient/routing keys
    # Readiness came first, gate-captured direct call second.
    assert deps.connection_factory_calls[0][2] == {"environ": deps.sanitized_env_value}
    assert deps.connection_factory_calls[1][2] == {
        "environ": deps.sanitized_env_value,
        "autocommit": True,
    }


def test_build_loopback_target_uri_percent_encodes_and_roundtrips() -> None:
    """Percent-sensitive password/database round-trip through the real parser."""
    module = _harness()
    password = "p@ss:w/rd+%?&"
    database = "okf_e2b db@mig"
    uri = module._build_loopback_target_uri(
        _DISPOSABLE_USER, password, "55432", database
    )
    assert uri.startswith("postgresql://")
    assert "127.0.0.1:55432" in uri
    # quote(value, safe="") percent-encodes sensitive characters.
    assert "%40" in uri  # @
    assert "%2F" in uri  # /
    assert "%20" in uri  # space in database
    target = module._lazy_target_parser(uri, database)
    assert target.host == "127.0.0.1"
    assert target.hostaddr == "127.0.0.1"
    assert target.port == 55432
    assert target.user == _DISPOSABLE_USER
    assert target.dbname == database
    assert target.password == password


def test_remove_env_file_missing_returns_true() -> None:
    module = _harness()
    assert module._remove_env_file(Path("definitely-missing-okf.env")) is True


def test_remove_env_file_oserror_returns_false(monkeypatch) -> None:
    module = _harness()

    def _boom(self: object) -> None:
        raise OSError("injected unlink failure")

    monkeypatch.setattr(Path, "unlink", _boom)
    assert module._remove_env_file(Path("okf.env")) is False


def test_env_file_cleanup_failure_fails_closed_and_cleans_config_dir(
    tmp_path: Path, monkeypatch
) -> None:
    """Pre-container env-file deletion failure raises the fixed error."""
    module = _harness()
    env_file = tmp_path / "okf.env"
    env_file.write_text("POSTGRES_PASSWORD=x\n")
    config_obj = _RecordingConfigDir()
    deps = _FakeHarness(
        start_ok=False, env_file_path=env_file, config_dir_obj=config_obj
    )

    def _boom(self: object) -> None:
        raise PermissionError("injected unlink failure")

    monkeypatch.setattr(Path, "unlink", _boom)
    with pytest.raises(RuntimeError, match="credential file cleanup failed"):
        _run_live(module, deps, evidence_path=tmp_path / "evidence.md")
    assert deps.cleanup_calls == []
    assert config_obj.cleanup_called is True  # config dir still cleaned


def test_read_routing_environ_is_explicit_three_key_mapping() -> None:
    """The real gate environ must be an explicit three-key mapping only."""
    module = _harness()
    mapping = module._read_routing_environ()
    assert set(mapping) == {DISPOSABLE_ENV, AUTH_ENV, EXPECTED_DATABASE_ENV}
    assert len(mapping) == 3


def test_env_file_and_config_dir_cleaned_when_container_never_created(
    tmp_path: Path,
) -> None:
    """Pre-container failures still delete the env file and config dir."""
    module = _harness()
    env_file = tmp_path / "okf.env"
    env_file.write_text("POSTGRES_PASSWORD=x\n")
    config_obj = _RecordingConfigDir()
    deps = _FakeHarness(
        start_ok=False, env_file_path=env_file, config_dir_obj=config_obj
    )
    with pytest.raises(Exception):
        _run_live(module, deps, evidence_path=tmp_path / "evidence.md")
    assert deps.cleanup_calls == []  # container cleanup seam never invoked
    assert deps.gate_calls == []
    assert not env_file.exists()  # env file deleted
    assert config_obj.cleanup_called is True  # config dir explicitly cleaned


def test_config_dir_cleaned_after_container_cleanup(tmp_path: Path) -> None:
    """Success path cleans the config dir after the attested container cleanup."""
    module = _harness()
    config_obj = _RecordingConfigDir()
    deps = _FakeHarness(config_dir_obj=config_obj)
    result = _run_live(module, deps, evidence_path=tmp_path / "evidence.md")
    assert result.cleanup_ok is True
    assert deps.cleanup_calls == [deps.container_id]
    assert config_obj.cleanup_called is True


def test_port_factory_returns_ephemeral_port_string() -> None:
    """Port factory returns a decimal string, no loop, no auto re-run."""
    module = _harness()
    port = module._lazy_port_factory()
    assert isinstance(port, str)
    assert port.isdigit()
    assert 1 <= int(port) <= 65535


def test_source_port_factory_binds_loopback_socket() -> None:
    source = _harness_source()
    assert "AF_INET" in source
    assert "getsockname()" in source
    assert "127.0.0.1" in source
    assert "sock.bind((" in source


# --- corrective tests for the confirmed HIGH defect (start invalid_id) ---
def test_lazy_observe_presence_returns_full_result_with_validated_id() -> None:
    """The default presence seam returns the full immutable result, not status."""
    module = _harness()
    container_name = "okf-e2b-1234abcd"
    container_id = "a" * 64
    calls: list[object] = []

    class _Result:
        returncode = 0
        stdout = f"{container_name}\t{container_id}\n"

    def _run(args: object, **kwargs: object) -> object:
        calls.append(args)
        return _Result()

    result = module._lazy_observe_presence(
        container_name, config_dir="cfg", run=_run, env={}
    )
    assert result.status == "present"
    assert result.container_id == container_id
    assert len(calls) == 1


def test_recovered_container_id_requires_present_and_exact_64_hex() -> None:
    """Identity recovery accepts only present + exact full 64-hex, else None."""
    module = _harness()
    valid_id = "b" * 64
    assert (
        module._recovered_container_id(
            types.SimpleNamespace(status="present", container_id=valid_id)
        )
        == valid_id
    )
    assert (
        module._recovered_container_id(
            types.SimpleNamespace(status="confirmed_absent", container_id=None)
        )
        is None
    )
    assert (
        module._recovered_container_id(
            types.SimpleNamespace(status="present", container_id=None)
        )
        is None
    )
    assert (
        module._recovered_container_id(
            types.SimpleNamespace(status="present", container_id="abc")
        )
        is None
    )
    assert (
        module._recovered_container_id(
            types.SimpleNamespace(status="ambiguous_output", container_id=None)
        )
        is None
    )


def test_presence_status_normalizes_string_and_object_results() -> None:
    """Observed presence may arrive as a status string or a full result."""
    module = _harness()
    assert module._presence_status("confirmed_absent") == "confirmed_absent"
    assert (
        module._presence_status(
            types.SimpleNamespace(status="present", container_id="a" * 64)
        )
        == "present"
    )
    assert module._presence_status(types.SimpleNamespace()) == ""


def test_start_invalid_id_recovers_exact_id_and_cleans_up(tmp_path: Path) -> None:
    """docker run -d exited 0 (invalid_id): one recovery, exact ID, cleanup once."""
    module = _harness()
    recovered_id = "c" * 64
    env_file = tmp_path / "okf.env"
    env_file.write_text("POSTGRES_PASSWORD=x\n")
    config_obj = _RecordingConfigDir()
    deps = _FakeHarness(
        start_ok=False,
        start_invalid_id=True,
        recovery_presence=types.SimpleNamespace(
            status="present", container_id=recovered_id
        ),
        env_file_path=env_file,
        config_dir_obj=config_obj,
    )
    with pytest.raises(RuntimeError, match="docker start failed"):
        _run_live(module, deps, evidence_path=tmp_path / "evidence.md")
    # Exactly one bounded recovery observation (initial absence + one recovery).
    assert deps.absence_calls == [deps.container_name, deps.container_name]
    assert deps.absence_envs == [
        deps.sanitized_env_value,
        deps.sanitized_env_value,
    ]
    # Never proceeds to normal inspect/readiness/gate/evidence.
    assert deps.inspect_calls == []
    assert deps.ready_calls == []
    assert deps.gate_calls == []
    assert deps.verify_calls == []
    # One Docker start only, never a second Docker start.
    assert len(deps.docker_start_calls) == 1
    # Ownership-attested cleanup invoked exactly once with the recovered ID.
    assert deps.cleanup_calls == [recovered_id]
    assert deps.cleanup_env_files == [env_file]
    # Credential env file deleted and config dir still cleaned.
    assert not env_file.exists()
    assert config_obj.cleanup_called is True


@pytest.mark.parametrize(
    ("recovery_status", "recovery_id"),
    [
        ("confirmed_absent", None),
        ("ambiguous_output", None),
        ("inspection_failure", None),
        ("present", None),
        ("present", "not-a-64-hex-id"),
    ],
)
def test_start_invalid_id_unrecovered_fails_closed_no_unsafe_cleanup(
    tmp_path: Path,
    recovery_status: str,
    recovery_id: str | None,
) -> None:
    """Identity not recoverable: fail closed, no gate, no unsafe name-only delete."""
    module = _harness()
    env_file = tmp_path / "okf.env"
    env_file.write_text("POSTGRES_PASSWORD=x\n")
    config_obj = _RecordingConfigDir()
    deps = _FakeHarness(
        start_ok=False,
        start_invalid_id=True,
        recovery_presence=types.SimpleNamespace(
            status=recovery_status, container_id=recovery_id
        ),
        env_file_path=env_file,
        config_dir_obj=config_obj,
    )
    with pytest.raises(RuntimeError, match="unresolved container cleanup"):
        _run_live(module, deps, evidence_path=tmp_path / "evidence.md")
    # Exactly one bounded recovery observation; never a second Docker start/gate.
    assert deps.absence_calls == [deps.container_name, deps.container_name]
    assert len(deps.docker_start_calls) == 1
    assert deps.inspect_calls == []
    assert deps.ready_calls == []
    assert deps.gate_calls == []
    assert deps.verify_calls == []
    # Identity is not recoverable: never invoke ownership-attested cleanup and
    # never perform an unsafe name-only deletion.
    assert deps.cleanup_calls == []
    # Credential env file still deleted explicitly; config dir still cleaned.
    assert not env_file.exists()
    assert config_obj.cleanup_called is True


# --- one-source contract for the env file (review MEDIUM) ---
def test_env_file_receives_expected_database_and_fixed_user_not_parser_values(
    tmp_path: Path,
) -> None:
    """Env file gets generated password + expected db + fixed user directly."""
    module = _harness()
    deps = _FakeHarness()
    deps.target = types.SimpleNamespace(dbname="attacker-db", user="attacker-user")
    _run_live(module, deps, evidence_path=tmp_path / "evidence.md")
    assert deps.env_file_calls == [(deps.password, _EXPECTED_DB, _DISPOSABLE_USER)]
