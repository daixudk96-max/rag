"""Phase 16-15 Task 1 RED contract for the E2b full-corpus acceptance runner.

This test file is written FIRST (TDD). It proves, without any real database:

- The default blocked path: with any of the three gate routing variables
  missing, the runner emits exactly blocked_not_executed and performs ZERO
  connection attempts (no psycopg.connect, no parser, no orchestration).
- The authorized matrix semantics through injected fakes/stubs (repository +
  lock seams), never against a real database: first materialization with full
  provenance and zero chunk_entity_links, equivalent-rerun idempotence,
  changed-set convergence with stale-cleanup and bridge-deletion DML counts,
  manual/legacy preservation, invalid-document isolation with a fresh-connection
  failure-audit row, changed-set failure rollback, and E2b-vs-E2b plus
  E2a-vs-E2b serialization on E2a's shared advisory lock key.
- The deterministic FIXTURE candidates path (16-15 truth #20): the runner and its
  evidence record fixture_candidates and never exercise a real RaNER adapter.
- Redacted single-line JSON evidence with no connection string, credential, or
  corpus text, and zero generative-LLM tokens.
"""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
import os
import subprocess
import sys
import types
from collections.abc import Callable, Mapping
from dataclasses import fields
from pathlib import Path
from typing import Any

import psycopg
import pytest

from llamaindex_runtime.entity.contracts import deterministic_id
from llamaindex_runtime.entity.materialization_repository import (
    E2bDesiredState,
    E2bDmlRecorder,
    E2bDocumentScope,
    E2bReconciliationResult,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
VERIFICATION_DIR = REPO_ROOT / "verification" / "phase16-raw-corpus-entity-layer"
RUNNER_PATH = VERIFICATION_DIR / "run_e2b_full_corpus_acceptance.py"
EVIDENCE_NAME = "e2b_full_corpus_acceptance_evidence.md"
EVIDENCE_PATH = VERIFICATION_DIR / EVIDENCE_NAME

AUTH_ENV = "OKF_E2B_DISPOSABLE_TEST_AUTHORIZED"
DISPOSABLE_ENV = "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE"
EXPECTED_DATABASE_ENV = "OKF_REBUILD_EXPECTED_DATABASE"
_GATE_ROUTING_KEYS = frozenset((AUTH_ENV, DISPOSABLE_ENV, EXPECTED_DATABASE_ENV))

_DATABASE_ROUTING_KEYS = frozenset(
    "DATABASE_URL FORMAL_RUNTIME_DATABASE_URL "
    "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE OKF_REBUILD_EXPECTED_DATABASE "
    "OKF_FAILURE_AUDIT_ACCEPTANCE OKF_REBUILD_DOCKER_ACCEPTANCE "
    "OKF_E2A_DISPOSABLE_TEST_AUTHORIZED OKF_E2B_DISPOSABLE_TEST_AUTHORIZED "
    "OKF_E2B_MIGRATION_TEST_AUTHORIZED OKF_E2B_MODELSCOPE_MIRROR_AUTHORIZED "
    "OKF_E2B_RANER_SMOKE_AUTHORIZED OKF_E2B_C2_ENTRY_AUTHORIZED".split()
)

_CLI_FAILURE_MESSAGE = (
    "E2b full-corpus acceptance refused; failure details are not disclosed"
)
_CONNECT_FAILURE_MESSAGE = "Database connection failed; refusing full-corpus acceptance"
_EXPECTED_DB_CANARY = "okf_e2b_full_corpus_disposable"
_DB_URL = f"postgresql://okf:secret@127.0.0.1:5432/{_EXPECTED_DB_CANARY}"

_FIXTURE_DOCUMENT_ID = "11111111-1111-4111-8111-111111111111"
_FIXTURE_VERSION_ID = "22222222-2222-4222-8222-222222222222"


def _authorized_env() -> dict[str, str]:
    """Explicit authorized environment: only the three gate routing keys."""
    return {
        DISPOSABLE_ENV: "1",
        EXPECTED_DATABASE_ENV: _EXPECTED_DB_CANARY,
        AUTH_ENV: "1",
    }


def _runner() -> types.ModuleType:
    """Lazy-load the runner module (RED: fails until the runner exists)."""
    if not RUNNER_PATH.is_file():
        pytest.fail(f"RED: runner absent: {RUNNER_PATH}")
    spec = importlib.util.spec_from_file_location(
        "run_e2b_full_corpus_acceptance", str(RUNNER_PATH)
    )
    if spec is None or spec.loader is None:
        pytest.fail(f"RED: runner cannot be loaded: {RUNNER_PATH}")
    module = importlib.util.module_from_spec(spec)
    # The runner uses the future annotations import, so its dataclass
    # machinery resolves string annotations through sys.modules; register the
    # lazily loaded module exactly like a normal import would.
    sys.modules["run_e2b_full_corpus_acceptance"] = module
    spec.loader.exec_module(module)
    return module


def _runner_source() -> str:
    if not RUNNER_PATH.is_file():
        pytest.fail(f"RED: runner absent: {RUNNER_PATH}")
    return RUNNER_PATH.read_text(encoding="utf-8")


class _RecordingEnviron(dict):
    """dict subclass that records every read and enumeration."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__()
        self.get_calls: list[tuple[object, object]] = []
        self.enumeration_calls: list[str] = []
        for key, value in dict(*args, **kwargs).items():
            self[key] = value

    def get(self, key: str, default: object = None) -> object:
        self.get_calls.append((key, default))
        return super().get(key, default)

    def keys(self) -> Any:
        self.enumeration_calls.append("keys")
        return super().keys()

    def items(self) -> Any:
        self.enumeration_calls.append("items")
        return super().items()

    def values(self) -> Any:
        self.enumeration_calls.append("values")
        return super().values()

    def copy(self) -> Any:
        self.enumeration_calls.append("copy")
        return super().copy()


class _HostileTarget:
    """Every attribute read raises: proves the gate never touches the target."""

    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"hostile target attribute read: {name}")


def _valid_matrix() -> dict[str, object]:
    """Deterministic redacted matrix used by the orchestration fakes."""
    return {
        "first_materialization": {
            "outcome": "changed",
            "entity_mentions_dml": 2,
            "node_entity_links_dml": 2,
            "okf_e2b_node_link_ownership_dml": 2,
            "chunk_entity_links_dml": 0,
            "mention_count": 2,
            "bridge_count": 2,
            "ledger_count": 2,
            "chunk_entity_links_count": 0,
        },
        "equivalent_rerun": {
            "outcome": "no_op",
            "dml_total": 0,
            "timestamp_churn": False,
        },
        "changed_set_convergence": {
            "outcome": "changed",
            "stale_mention_deletions": 1,
            "stale_link_ownership_deletions": 1,
            "bridge_deletion_dml": 1,
            "fail_closed_preserved_bridges": 0,
            "mention_count": 1,
            "bridge_count": 1,
        },
        "manual_legacy_preservation": {
            "outcome": "changed",
            "manual_mentions_preserved": 1,
            "manual_bridges_preserved": 1,
            "claimed": 0,
            "deleted": 0,
            "new_mention_count": 1,
            "new_bridge_count": 1,
        },
        "invalid_document_isolation": {
            "outcome": "rolled_back_failure",
            "scope_writes": 0,
            "failure_audit_outcome": "written",
            "continued_to_next": True,
        },
        "changed_set_failure_rollback": {
            "outcome": "rolled_back_failure",
            "rollback_confirmed": True,
            "old_state_restored": True,
            "failure_audit_outcome": "written",
        },
        "e2b_vs_e2b_serialization": {
            "serialized": True,
            "duplicate_rows": 0,
            "lock_key_is_e2a": True,
            "lock_key_is_e2b": False,
            "overlap_blocked_on_lock": True,
            "pre_converge_outcome": "changed",
            "second_outcome": "no_op",
        },
        "e2a_vs_e2b_serialization": {
            "serialized": True,
            "duplicate_rows": 0,
            "lock_key_is_e2a": True,
            "lock_key_is_e2b": False,
            "overlap_blocked_on_lock": True,
            "pre_converge_outcome": "no_op",
            "second_outcome": "no_op",
        },
    }


class _FakeSeams:
    """Pure-fake seams driving the authorized gate path with recorded calls."""

    def __init__(self, matrix: dict[str, object] | None = None) -> None:
        self.matrix = _valid_matrix() if matrix is None else matrix
        self.target_parser_calls: list[tuple[object, object]] = []
        self.connect_calls: list[object] = []
        self.matrix_calls: list[tuple[object, dict[str, object]]] = []
        self.write_calls: list[tuple[Mapping[str, object], Path]] = []
        self.target: object = None

    def target_parser(self, target_uri: object, expected_database: object) -> object:
        self.target_parser_calls.append((target_uri, expected_database))
        self.target = types.SimpleNamespace(dbname=_EXPECTED_DB_CANARY)
        return self.target

    def connection_factory(self, target: object) -> object:
        self.connect_calls.append(target)
        return types.SimpleNamespace(closed=True)

    def matrix_runner(
        self,
        target: object,
        *,
        connection_factory: object,
        repository_factory: object,
    ) -> dict[str, object]:
        self.matrix_calls.append(
            (
                target,
                {
                    "connection_factory": connection_factory,
                    "repository_factory": repository_factory,
                },
            )
        )
        return self.matrix

    def evidence_writer(self, payload: Mapping[str, object], path: Path) -> str:
        self.write_calls.append((payload, path))
        text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        path.write_text(text, encoding="utf-8")
        return hashlib.sha256(text.encode("utf-8")).hexdigest()


class _FakeCursor:
    """Records execute calls and serves canned count rows."""

    def __init__(
        self,
        connection: _FakeConnection,
        count_resolver: Callable[[str], int],
    ) -> None:
        self.connection = connection
        self.count_resolver = count_resolver
        self.rows: list[Mapping[str, object]] = []

    def execute(self, statement: str, parameters: object | None = None) -> None:
        self.connection.call_log.append(("execute", statement, parameters))
        self.rows = []
        if "count(*)" in statement:
            self.rows = [{"count": self.count_resolver(statement)}]

    def fetchone(self) -> Mapping[str, object] | None:
        if not self.rows:
            return None
        return self.rows.pop(0)

    def fetchall(self) -> list[Mapping[str, object]]:
        rows = self.rows
        self.rows = []
        return rows


class _FakeConnection:
    """Minimal fake connection satisfying the runner's cursor protocol."""

    def __init__(
        self,
        call_log: list[tuple[object, ...]],
        label: str,
        count_resolver: Callable[[str], int],
    ) -> None:
        self.call_log = call_log
        self.label = label
        self.count_resolver = count_resolver
        self.autocommit = False
        self.closed = False
        self.close_calls = 0
        self.commit_calls = 0
        self.rollback_calls = 0

    def cursor(self) -> _FakeCursor:
        self.call_log.append(("cursor", self.label))
        return _FakeCursor(self, self.count_resolver)

    def commit(self) -> None:
        self.commit_calls += 1
        self.call_log.append(("commit", self.label))

    def rollback(self) -> None:
        self.rollback_calls += 1
        self.call_log.append(("rollback", self.label))

    def close(self) -> None:
        self.closed = True
        self.close_calls += 1
        self.call_log.append(("close", self.label))


class _FakeRepository:
    """Records reconcile_document calls and pops canned results."""

    def __init__(
        self,
        call_log: list[tuple[object, ...]],
        results: list[E2bReconciliationResult],
        scope_sink: list[E2bDocumentScope],
    ) -> None:
        self.call_log = call_log
        # Shared list: every repository pops the next canned result in order.
        self.results = results
        self.scope_sink = scope_sink
        self.reconcile_calls: list[tuple[object, object, object]] = []

    def reconcile_document(
        self,
        cursor: object,
        scope: E2bDocumentScope,
        *,
        desired: E2bDesiredState,
        recorder: E2bDmlRecorder,
    ) -> E2bReconciliationResult:
        self.reconcile_calls.append((scope, desired, recorder))
        self.scope_sink.append(scope)
        self.call_log.append(("reconcile", scope.document_id, scope.version_id))
        if not self.results:
            raise AssertionError("no canned result left for the matrix")
        return self.results.pop(0)


class _FakeMatrixSeams:
    """Fake connection/repository seams for the full transition matrix."""

    def __init__(
        self,
        results: list[E2bReconciliationResult],
        count_resolver: Callable[[str], int],
    ) -> None:
        self.results = list(results)
        self.count_resolver = count_resolver
        self.call_log: list[tuple[object, ...]] = []
        self.opened: list[_FakeConnection] = []
        self.repositories: list[_FakeRepository] = []
        self.reconcile_scopes: list[E2bDocumentScope] = []

    def connection_factory(self, target: object) -> _FakeConnection:
        label = f"connection-{len(self.opened) + 1}"
        connection = _FakeConnection(self.call_log, label, self.count_resolver)
        self.opened.append(connection)
        self.call_log.append(("open", label))
        return connection

    def repository_factory(self, audit_factory: object) -> _FakeRepository:
        repository = _FakeRepository(self.call_log, self.results, self.reconcile_scopes)
        self.repositories.append(repository)
        return repository


def _result(
    outcome: str,
    dml: Mapping[str, int] | None = None,
    stale: Mapping[str, int] | None = None,
    audit: str | None = None,
) -> E2bReconciliationResult:
    return E2bReconciliationResult(
        outcome=outcome,
        primary_dml_by_table=dict(dml or {}),
        stale_deletion_counts=dict(stale or {}),
        failure_audit_outcome=audit,
        reconciliation_required=False,
    )


def _matrix_results() -> list[E2bReconciliationResult]:
    """Eight canned results, one per matrix reconcile, in transition order."""
    return [
        _result(
            "changed",
            {
                "entity_mentions": 2,
                "node_entity_links": 2,
                "okf_e2b_node_link_ownership": 2,
            },
        ),
        _result("no_op"),
        _result(
            "changed",
            {
                "entity_mentions": 1,
                "okf_e2b_node_link_ownership": 1,
                "node_entity_links": 1,
            },
            {
                "entity_mentions": 1,
                "okf_e2b_node_link_ownership": 1,
                "node_entity_links": 1,
            },
        ),
        _result(
            "changed",
            {
                "entity_mentions": 1,
                "node_entity_links": 1,
                "okf_e2b_node_link_ownership": 1,
            },
        ),
        _result("rolled_back_failure", audit="written"),
        _result("rolled_back_failure", audit="written"),
        # FINDING D: transition 7 pre-converges the main scope from the
        # SHRUNK state (left by transition 3) back to the FULL desired state
        # (changed), then the overlap reconcile completes without new DML
        # (no_op). Transition 8 pre-converges an already-full scope (no_op).
        _result(
            "changed",
            {
                "entity_mentions": 1,
                "node_entity_links": 1,
                "okf_e2b_node_link_ownership": 1,
            },
        ),
        _result("no_op"),
        _result("no_op"),
        _result("no_op"),
    ]


def _count_resolver(statement: str) -> int:
    """Deterministic canned counts keyed by statement markers."""
    if "chunk_entity_links" in statement:
        return 0
    if "unnest" in statement:
        return 0
    if "e2b_owner_scope IS NULL" in statement:
        return 1
    if "NOT EXISTS" in statement:
        return 1
    if "node_id = %s AND entity_id = %s" in statement:
        return 0
    if "okf_e2b_node_link_ownership" in statement:
        return 2
    if "node_entity_links" in statement:
        return 2
    if "entity_mentions" in statement:
        return 2
    return 0


# -- production prerequisites ---------------------------------------------


def test_production_db_prerequisites_are_real() -> None:
    from scripts._rebuild_database_connection import (  # noqa: PLC0415
        parse_disposable_postgresql_target,
        runtime_connection_factory,
    )

    target = parse_disposable_postgresql_target(_DB_URL, _EXPECTED_DB_CANARY)
    assert target.dbname == _EXPECTED_DB_CANARY
    assert callable(runtime_connection_factory)
    scope = E2bDocumentScope(
        document_id=_FIXTURE_DOCUMENT_ID, version_id=_FIXTURE_VERSION_ID
    )
    assert scope.advisory_lock_key == (
        f"okf:e2a:parent:{_FIXTURE_DOCUMENT_ID}:{_FIXTURE_VERSION_ID}"
    )
    assert "okf:e2b:parent" not in scope.advisory_lock_key


def test_runner_defaults_are_exact_production_symbols() -> None:
    module = _runner()
    from scripts._rebuild_database_connection import (  # noqa: PLC0415
        parse_disposable_postgresql_target,
        runtime_connection_factory,
    )

    signature = inspect.signature(module.run_full_corpus_acceptance)
    parameters = signature.parameters
    assert parameters["target_uri"].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters["target_uri"].default is None
    assert parameters["target_parser"].default is parse_disposable_postgresql_target
    assert module.runtime_connection_factory is runtime_connection_factory
    assert parameters["connection_factory"].default is module._e2b_connection_factory
    assert parameters["repository_factory"].default is None
    assert parameters["matrix_runner"].default is module._run_transition_matrix
    assert parameters["evidence_writer"].default is module._write_evidence
    assert parameters["evidence_path"].default is module.EVIDENCE_PATH
    main_signature = inspect.signature(module.main)
    assert main_signature.parameters["target_uri"].kind is (
        inspect.Parameter.KEYWORD_ONLY
    )
    assert main_signature.parameters["target_uri"].default is None
    assert [field.name for field in fields(module.AcceptanceOutcome)] == [
        "status",
        "candidate_path",
        "matrix",
        "evidence_sha256",
    ]


def test_runner_module_must_exist_for_lazy_load() -> None:
    assert RUNNER_PATH.is_file(), f"RED: runner absent: {RUNNER_PATH}"


def test_runner_constants_pin_gate_contract() -> None:
    module = _runner()
    assert module.AUTH_ENV == AUTH_ENV
    assert module.DISPOSABLE_ENV == DISPOSABLE_ENV
    assert module.EXPECTED_DATABASE_ENV == EXPECTED_DATABASE_ENV
    assert module.GATE_ROUTING_KEYS == _GATE_ROUTING_KEYS
    assert module.BLOCKED_STATUS == "blocked_not_executed"
    assert module.EXECUTED_STATUS == "executed"
    assert module.FAILED_STATUS == "executed_failed"
    assert module.FAILED_EXIT_CODE == 3
    assert module.EVIDENCE_NAME == EVIDENCE_NAME
    assert module.CLI_FAILURE_MESSAGE == _CLI_FAILURE_MESSAGE
    assert module.CONNECT_FAILURE_MESSAGE == _CONNECT_FAILURE_MESSAGE
    assert module.FIXTURE_CANDIDATE_PATH == "fixture_candidates"


# -- blocked path ----------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {DISPOSABLE_ENV: "0"},
        {DISPOSABLE_ENV: ""},
        {AUTH_ENV: "0"},
        {AUTH_ENV: ""},
        {EXPECTED_DATABASE_ENV: ""},
        {EXPECTED_DATABASE_ENV: None},
    ],
)
def test_main_blocked_on_partial_or_malformed_authorization(
    capsys: pytest.CaptureFixture[str], overrides: Mapping[str, object]
) -> None:
    module = _runner()
    environ = _authorized_env()
    for key, value in overrides.items():
        if value is None:
            environ.pop(key, None)
        else:
            environ[key] = str(value)
    code = module.main([], target_uri=_DB_URL)
    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == "blocked_not_executed\n"
    assert captured.err == ""


def test_blocked_main_reads_only_gate_routing_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _runner()
    environ = _RecordingEnviron({DISPOSABLE_ENV: "0"})
    monkeypatch.setattr(module, "os", types.SimpleNamespace(environ=environ))
    code = module.main([], target_uri=_DB_URL)
    assert code == 1
    assert {key for key, _ in environ.get_calls} <= _GATE_ROUTING_KEYS
    assert not environ.enumeration_calls


def test_blocked_main_zero_parser_connect_and_orchestration_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _runner()
    connect_calls: list[object] = []
    orchestration_calls: list[object] = []
    parser_calls: list[object] = []

    def _connect(*args: object, **kwargs: object) -> object:
        connect_calls.append((args, kwargs))
        raise AssertionError("blocked path must never connect")

    def _orchestrate(*args: object, **kwargs: object) -> object:
        orchestration_calls.append((args, kwargs))
        raise AssertionError("blocked path must never orchestrate")

    def _parse(*args: object, **kwargs: object) -> object:
        parser_calls.append((args, kwargs))
        raise AssertionError("blocked path must never parse a target")

    monkeypatch.setattr(psycopg, "connect", _connect)
    monkeypatch.setattr(module, "run_full_corpus_acceptance", _orchestrate)
    monkeypatch.setattr(module, "parse_disposable_postgresql_target", _parse)
    if EVIDENCE_PATH.exists():
        EVIDENCE_PATH.unlink()
    code = module.main([], target_uri=_DB_URL)
    assert code == 1
    assert not connect_calls
    assert not orchestration_calls
    assert not parser_calls
    assert not EVIDENCE_PATH.exists()


def test_run_full_corpus_acceptance_unauthorized_returns_before_parsing_hostile_target() -> (
    None
):
    module = _runner()
    hostile = _HostileTarget()
    outcome = module.run_full_corpus_acceptance(
        {DISPOSABLE_ENV: "0"},
        target_uri=_DB_URL,
        target_parser=hostile,  # type: ignore[arg-type]
        connection_factory=hostile,  # type: ignore[arg-type]
        repository_factory=hostile,  # type: ignore[arg-type]
        matrix_runner=hostile,  # type: ignore[arg-type]
        evidence_writer=hostile,  # type: ignore[arg-type]
        evidence_path=Path("unused"),
    )
    assert outcome.status == "blocked_not_executed"
    assert outcome.candidate_path == ""
    assert outcome.matrix == {}
    assert outcome.evidence_sha256 == ""


def test_main_forwards_only_keyword_programmatic_target_after_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _runner()
    environ = _authorized_env()
    forwarded: list[tuple[object, object]] = []

    def _run(environ_arg: object, *, target_uri: object) -> object:
        forwarded.append((environ_arg, target_uri))
        return types.SimpleNamespace(status="executed")

    monkeypatch.setattr(module, "run_full_corpus_acceptance", _run)
    monkeypatch.setattr(os, "environ", environ)
    code = module.main([], target_uri=_DB_URL)
    assert code == 0
    assert len(forwarded) == 1
    assert forwarded[0][0] is environ
    assert forwarded[0][1] == _DB_URL


def test_main_rejects_target_uri_in_argv_before_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _runner()
    gate_calls: list[object] = []
    monkeypatch.setattr(
        module,
        "run_full_corpus_acceptance",
        lambda *a, **k: gate_calls.append((a, k)),
    )
    monkeypatch.setattr(os, "environ", _authorized_env())
    with pytest.raises(ValueError, match="argv credential route is forbidden"):
        module.main([_DB_URL], target_uri=None)
    assert gate_calls == []


def test_require_gate_authorization_reads_only_allowlist() -> None:
    module = _runner()
    environ = _RecordingEnviron({DISPOSABLE_ENV: "0"})
    with pytest.raises(ValueError):
        module._require_gate_authorization(environ)
    assert {key for key, _ in environ.get_calls} <= _GATE_ROUTING_KEYS
    assert not environ.enumeration_calls


@pytest.mark.parametrize(
    "disposable,authorized,expected_database",
    [
        ("0", "1", _EXPECTED_DB_CANARY),
        ("", "1", _EXPECTED_DB_CANARY),
        ("1", "0", _EXPECTED_DB_CANARY),
        ("1", "", _EXPECTED_DB_CANARY),
        ("1", "1", ""),
        ("1", "1", None),
    ],
)
def test_guard_requires_exact_value(
    disposable: str,
    authorized: str,
    expected_database: str | None,
) -> None:
    module = _runner()
    environ: dict[str, str] = {DISPOSABLE_ENV: disposable, AUTH_ENV: authorized}
    if expected_database is not None:
        environ[EXPECTED_DATABASE_ENV] = expected_database
    with pytest.raises(ValueError):
        module._require_gate_authorization(environ)


def test_guard_requires_nonempty_expected_database() -> None:
    module = _runner()
    with pytest.raises(ValueError, match=EXPECTED_DATABASE_ENV):
        module._require_gate_authorization(
            {DISPOSABLE_ENV: "1", AUTH_ENV: "1", EXPECTED_DATABASE_ENV: ""}
        )


# -- authorized orchestration ----------------------------------------------


def test_run_full_corpus_acceptance_full_authorized_path_with_pure_fakes(
    tmp_path: Path,
) -> None:
    module = _runner()
    seams = _FakeSeams()
    evidence_path = tmp_path / EVIDENCE_NAME
    outcome = module.run_full_corpus_acceptance(
        _authorized_env(),
        target_uri=_DB_URL,
        target_parser=seams.target_parser,
        connection_factory=seams.connection_factory,
        repository_factory=None,
        matrix_runner=seams.matrix_runner,
        evidence_writer=seams.evidence_writer,
        evidence_path=evidence_path,
    )
    assert seams.target_parser_calls == [(_DB_URL, _EXPECTED_DB_CANARY)]
    assert len(seams.matrix_calls) == 1
    assert seams.matrix_calls[0][0] is seams.target
    assert set(seams.matrix_calls[0][1]) == {
        "connection_factory",
        "repository_factory",
    }
    assert len(seams.write_calls) == 1
    assert seams.write_calls[0][1] is evidence_path
    assert isinstance(outcome, module.AcceptanceOutcome)
    assert outcome.status == "executed"
    assert outcome.candidate_path == "fixture_candidates"
    assert outcome.matrix == _valid_matrix()
    written = evidence_path.read_text(encoding="utf-8")
    assert (
        outcome.evidence_sha256 == hashlib.sha256(written.encode("utf-8")).hexdigest()
    )
    payload = seams.write_calls[0][0]
    assert isinstance(payload, Mapping)
    assert payload["candidate_path"] == "fixture_candidates"
    for forbidden in ("postgresql://", "127.0.0.1", "secret", _EXPECTED_DB_CANARY):
        assert forbidden not in json.dumps(payload, sort_keys=True)
        assert forbidden not in written


def test_run_full_corpus_acceptance_reads_only_gate_routing_keys(
    tmp_path: Path,
) -> None:
    module = _runner()
    seams = _FakeSeams()
    environ = _RecordingEnviron(_authorized_env())
    module.run_full_corpus_acceptance(
        environ,
        target_uri=_DB_URL,
        target_parser=seams.target_parser,
        connection_factory=seams.connection_factory,
        matrix_runner=seams.matrix_runner,
        evidence_writer=seams.evidence_writer,
        evidence_path=tmp_path / EVIDENCE_NAME,
    )
    assert {key for key, _ in environ.get_calls} <= _GATE_ROUTING_KEYS
    assert not environ.enumeration_calls


def test_run_full_corpus_acceptance_evidence_write_is_deterministic(
    tmp_path: Path,
) -> None:
    module = _runner()
    first_path = tmp_path / "first.md"
    second_path = tmp_path / "second.md"
    first = module.run_full_corpus_acceptance(
        _authorized_env(),
        target_uri=_DB_URL,
        target_parser=_FakeSeams().target_parser,
        connection_factory=_FakeSeams().connection_factory,
        matrix_runner=_FakeSeams().matrix_runner,
        evidence_writer=module._write_evidence,
        evidence_path=first_path,
    )
    second = module.run_full_corpus_acceptance(
        _authorized_env(),
        target_uri=_DB_URL,
        target_parser=_FakeSeams().target_parser,
        connection_factory=_FakeSeams().connection_factory,
        matrix_runner=_FakeSeams().matrix_runner,
        evidence_writer=module._write_evidence,
        evidence_path=second_path,
    )
    assert first.evidence_sha256 == second.evidence_sha256
    assert first_path.read_text(encoding="utf-8") == second_path.read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize(
    "bad_key",
    [
        "connection_string",
        "host",
        "credential",
        "database_url",
        "password",
        "corpus_text",
    ],
)
def test_redact_evidence_payload_rejects_unknown_fields(bad_key: str) -> None:
    module = _runner()
    payload = {
        "schema_version": 1,
        "status": "executed",
        "candidate_path": "fixture_candidates",
        "matrix": _valid_matrix(),
        bad_key: "leak",
    }
    with pytest.raises(ValueError, match="unknown evidence payload field"):
        module._redact_evidence_payload(payload)


def test_redact_evidence_payload_rejects_unknown_matrix_keys() -> None:
    module = _runner()
    matrix = _valid_matrix()
    matrix["sneaky_transition"] = {"outcome": "changed"}
    payload = {
        "schema_version": 1,
        "status": "executed",
        "candidate_path": "fixture_candidates",
        "matrix": matrix,
    }
    with pytest.raises(ValueError, match="matrix keys"):
        module._redact_evidence_payload(payload)


def test_redact_evidence_payload_rejects_unknown_transition_fields() -> None:
    module = _runner()
    matrix = _valid_matrix()
    matrix["first_materialization"]["connection_string"] = "leak"  # type: ignore[index]
    payload = {
        "schema_version": 1,
        "status": "executed",
        "candidate_path": "fixture_candidates",
        "matrix": matrix,
    }
    with pytest.raises(ValueError, match="transition field"):
        module._redact_evidence_payload(payload)


def test_redact_evidence_payload_canonical_and_redacted() -> None:
    module = _runner()
    payload = module._canonical_evidence_payload("executed", _valid_matrix())
    redacted = module._redact_evidence_payload(payload)
    assert redacted["schema_version"] == 1
    assert redacted["status"] == "executed"
    assert redacted["candidate_path"] == "fixture_candidates"
    assert set(redacted["matrix"]) == set(_valid_matrix())
    for forbidden in ("postgresql://", "127.0.0.1", "secret", _EXPECTED_DB_CANARY):
        assert forbidden not in json.dumps(redacted, sort_keys=True)


# -- matrix semantics via injected fakes (repository + lock seams) ----------


def test_matrix_drives_repository_through_full_transition_sequence() -> None:
    module = _runner()
    target = module.parse_disposable_postgresql_target(_DB_URL, _EXPECTED_DB_CANARY)
    seams = _FakeMatrixSeams(_matrix_results(), _count_resolver)
    matrix = module._run_transition_matrix(
        target,
        connection_factory=seams.connection_factory,
        repository_factory=seams.repository_factory,
    )
    assert set(matrix) == set(_valid_matrix())

    first = matrix["first_materialization"]
    assert first["outcome"] == "changed"
    assert first["entity_mentions_dml"] == 2
    assert first["node_entity_links_dml"] == 2
    assert first["okf_e2b_node_link_ownership_dml"] == 2
    assert first["chunk_entity_links_dml"] == 0
    assert first["mention_count"] == 2
    assert first["bridge_count"] == 2
    assert first["ledger_count"] == 2
    assert first["chunk_entity_links_count"] == 0

    equivalent = matrix["equivalent_rerun"]
    assert equivalent["outcome"] == "no_op"
    assert equivalent["dml_total"] == 0
    assert equivalent["timestamp_churn"] is False

    changed = matrix["changed_set_convergence"]
    assert changed["outcome"] == "changed"
    assert changed["stale_mention_deletions"] == 1
    assert changed["stale_link_ownership_deletions"] == 1
    assert changed["bridge_deletion_dml"] == 1
    assert changed["fail_closed_preserved_bridges"] == 0

    manual = matrix["manual_legacy_preservation"]
    assert manual["outcome"] == "changed"
    assert manual["manual_mentions_preserved"] == 1
    assert manual["manual_bridges_preserved"] == 1
    assert manual["claimed"] == 0
    assert manual["deleted"] == 0
    assert manual["new_mention_count"] == 1
    assert manual["new_bridge_count"] == 1

    invalid = matrix["invalid_document_isolation"]
    assert invalid["outcome"] == "rolled_back_failure"
    assert invalid["scope_writes"] == 0
    assert invalid["failure_audit_outcome"] == "written"
    assert invalid["continued_to_next"] is True

    rollback = matrix["changed_set_failure_rollback"]
    assert rollback["outcome"] == "rolled_back_failure"
    assert rollback["rollback_confirmed"] is True
    assert rollback["old_state_restored"] is True
    assert rollback["failure_audit_outcome"] == "written"

    for key in ("e2b_vs_e2b_serialization", "e2a_vs_e2b_serialization"):
        serial = matrix[key]
        assert serial["serialized"] is True
        assert serial["duplicate_rows"] == 0
        assert serial["lock_key_is_e2a"] is True
        assert serial["lock_key_is_e2b"] is False
        assert serial["second_outcome"] == "no_op"
    # FINDING D: the e2b pre-converge converges the SHRUNK state back to the
    # full desired set (changed); the e2a pre-converge finds it already full.
    assert matrix["e2b_vs_e2b_serialization"]["pre_converge_outcome"] == "changed"
    assert matrix["e2a_vs_e2b_serialization"]["pre_converge_outcome"] == "no_op"

    assert len(seams.repositories) == 10
    assert len(seams.reconcile_scopes) == 10
    for repository in seams.repositories:
        assert len(repository.reconcile_calls) == 1
    for scope in seams.reconcile_scopes:
        assert scope.advisory_lock_key == (
            f"okf:e2a:parent:{scope.document_id}:{scope.version_id}"
        )
        assert "okf:e2b:parent" not in scope.advisory_lock_key


def test_matrix_asserts_e2a_shared_lock_key() -> None:
    module = _runner()
    scope = E2bDocumentScope(
        document_id=_FIXTURE_DOCUMENT_ID, version_id=_FIXTURE_VERSION_ID
    )
    module._assert_e2a_shared_lock_key(scope)
    hostile = types.SimpleNamespace(
        document_id=_FIXTURE_DOCUMENT_ID,
        version_id=_FIXTURE_VERSION_ID,
        advisory_lock_key=f"okf:e2b:parent:{_FIXTURE_DOCUMENT_ID}:{_FIXTURE_VERSION_ID}",
    )
    with pytest.raises(ValueError, match="shared advisory lock key"):
        module._assert_e2a_shared_lock_key(hostile)


# -- FINDING A: dict-row default connection factory --------------------------


def test_default_connection_factory_binds_dict_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FINDING A: the default factory must yield Mapping rows.

    The repository's _acquire_locks checks isinstance(row, Mapping); real
    psycopg connections return tuple rows by default, so every reconcile
    failed with ValueError (rolled_back_failure). The runner's default
    connection factory must bind psycopg.rows.dict_row; the audit connection
    factory inherits it because _reconcile_once derives it from the same
    connection_factory.
    """
    module = _runner()

    class _RowFactoryConnection:
        def __init__(self) -> None:
            self.row_factory: object = None
            self.closed = True

    fake = _RowFactoryConnection()
    monkeypatch.setattr(module, "runtime_connection_factory", lambda target: fake)
    connection = module._e2b_connection_factory(object())
    assert connection is fake
    assert connection.row_factory is psycopg.rows.dict_row


# -- FINDING B: fail-closed acceptance semantics -----------------------------


def _mutate(
    matrix: dict[str, object], key: str, **updates: object
) -> dict[str, object]:
    """Return the matrix with one transition's fields updated."""
    transition = matrix[key]
    assert isinstance(transition, dict)
    transition.update(updates)
    return matrix


def test_run_full_corpus_acceptance_fails_closed_when_proof_transition_fails(
    tmp_path: Path,
) -> None:
    """FINDING B: a proof transition ending rolled_back_failure must not
    report executed; evidence is still written so the failure is diagnosed."""
    module = _runner()
    matrix = _mutate(
        _valid_matrix(),
        "first_materialization",
        outcome="rolled_back_failure",
        entity_mentions_dml=0,
        mention_count=0,
    )
    seams = _FakeSeams(matrix)
    evidence_path = tmp_path / EVIDENCE_NAME
    outcome = module.run_full_corpus_acceptance(
        _authorized_env(),
        target_uri=_DB_URL,
        target_parser=seams.target_parser,
        connection_factory=seams.connection_factory,
        matrix_runner=seams.matrix_runner,
        evidence_writer=seams.evidence_writer,
        evidence_path=evidence_path,
    )
    assert outcome.status == module.FAILED_STATUS
    assert outcome.status != module.EXECUTED_STATUS
    assert outcome.candidate_path == "fixture_candidates"
    assert evidence_path.exists()
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert payload["status"] == module.FAILED_STATUS
    assert (
        payload["matrix"]["first_materialization"]["outcome"] == "rolled_back_failure"
    )


def test_main_returns_nonzero_when_acceptance_failed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """FINDING B: the CLI must exit non-zero when the acceptance failed."""
    module = _runner()
    monkeypatch.setattr(os, "environ", _authorized_env())
    monkeypatch.setattr(
        module,
        "run_full_corpus_acceptance",
        lambda environ_arg, *, target_uri: module.AcceptanceOutcome(
            module.FAILED_STATUS, "fixture_candidates", _valid_matrix(), "sha"
        ),
    )
    code = module.main([], target_uri=_DB_URL)
    captured = capsys.readouterr()
    assert code == module.FAILED_EXIT_CODE
    assert code != 0
    assert captured.out == module.FAILED_STATUS + "\n"


def test_validate_matrix_outcomes_accepts_valid_and_negative_controls() -> None:
    """Negative-control transitions alone may be rolled_back_failure."""
    module = _runner()
    assert module._validate_matrix_outcomes(_valid_matrix()) == []
    matrix = _mutate(
        _valid_matrix(), "invalid_document_isolation", outcome="rolled_back_failure"
    )
    matrix = _mutate(
        matrix, "changed_set_failure_rollback", outcome="rolled_back_failure"
    )
    assert module._validate_matrix_outcomes(matrix) == []


def test_validate_matrix_outcomes_detects_each_proof_failure() -> None:
    """Every proof-transition failure must be reported by the validator."""
    module = _runner()
    cases: list[tuple[str, dict[str, object]]] = [
        (
            "first_materialization",
            {
                "outcome": "rolled_back_failure",
                "entity_mentions_dml": 0,
                "mention_count": 0,
            },
        ),
        ("equivalent_rerun", {"dml_total": 1}),
        ("equivalent_rerun", {"outcome": "rolled_back_failure"}),
        ("changed_set_convergence", {"outcome": "rolled_back_failure"}),
        ("manual_legacy_preservation", {"outcome": "rolled_back_failure"}),
        ("e2b_vs_e2b_serialization", {"serialized": False}),
        ("e2a_vs_e2b_serialization", {"second_outcome": "rolled_back_failure"}),
    ]
    for marker, updates in cases:
        matrix = _mutate(_valid_matrix(), marker, **updates)
        failures = module._validate_matrix_outcomes(matrix)
        assert any(
            marker in failure for failure in failures
        ), f"expected a failure mentioning {marker}, got {failures}"


# -- FINDING C: transition-error fail-closed + derivable manual links -------


def test_fixture_manual_desired_links_are_derivable_from_mentions() -> None:
    """FINDING C: every manual desired link must be derivable from mentions.

    The repository's _validate_links rejects any desired link that is not
    derivable from the desired mentions' span mapping (collision mentions are
    excluded from derivation), raising _E2bLinkProofError before any DML. The
    manual desired state must therefore carry only links derivable from its
    non-collision mentions; the manual pair is represented by the preloaded
    bridge only, never as a desired link.
    """
    module = _runner()
    scope = E2bDocumentScope(
        document_id=module._FIXTURE_MANUAL_DOCUMENT_ID,
        version_id=module._FIXTURE_MANUAL_VERSION_ID,
    )
    desired = module._fixture_manual_desired_state(scope)
    collision_ids = {
        deterministic_id(
            "e2b_mention", f"{scope.document_id}:{scope.version_id}:manual"
        )
    }
    # Span -> node mapping established by the fixture preload
    # (_insert_span_node for the manual scope).
    span_to_nodes: dict[str, tuple[str, ...]] = {
        module._FIXTURE_SPAN_IDS[1]: (module._FIXTURE_NODE_IDS[1],),
        module._FIXTURE_SPAN_IDS[2]: (module._FIXTURE_NODE_IDS[2],),
    }
    derived: set[tuple[str, str]] = set()
    for mention in desired.mentions:
        if mention.entity_id is None or mention.mention_id in collision_ids:
            continue
        for node_id in span_to_nodes.get(mention.span_id, ()):
            derived.add((node_id, mention.entity_id))
    for link in desired.links:
        assert (link.node_id, link.entity_id) in derived, (
            f"desired link ({link.node_id}, {link.entity_id}) is not derivable "
            "from any resolved mention span mapping"
        )
    manual_pair = (module._FIXTURE_NODE_IDS[1], module._FIXTURE_ENTITY_IDS[0])
    assert manual_pair not in {
        (link.node_id, link.entity_id) for link in desired.links
    }, "the manual pair must be represented by the preloaded bridge only"


def test_matrix_records_transition_error_when_transition_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FINDING C: an unexpected transition exception must be recorded.

    A caller-contract failure (e.g. _E2bLinkProofError) must never kill the
    live gate with zero evidence: the matrix records outcome=transition_error
    with the error type, the remaining transitions still run, and the
    fail-closed validator marks the gate executed_failed.
    """
    module = _runner()
    target = module.parse_disposable_postgresql_target(_DB_URL, _EXPECTED_DB_CANARY)
    seams = _FakeMatrixSeams(_matrix_results(), _count_resolver)

    def _boom(
        target: object,
        *,
        connection_factory: object,
        repository_factory: object,
    ) -> dict[str, object]:
        raise ValueError("boom")

    monkeypatch.setattr(module, "_transition_manual_legacy_preservation", _boom)
    matrix = module._run_transition_matrix(
        target,
        connection_factory=seams.connection_factory,
        repository_factory=seams.repository_factory,
    )
    assert set(matrix) == set(_valid_matrix())
    failed = matrix["manual_legacy_preservation"]
    assert isinstance(failed, dict)
    assert failed["outcome"] == "transition_error"
    assert failed["error_type"] == "ValueError"
    # The remaining transitions still ran and recorded their evidence.
    assert matrix["first_materialization"]["outcome"] == "changed"
    assert matrix["equivalent_rerun"]["outcome"] == "no_op"
    assert matrix["e2a_vs_e2b_serialization"]["serialized"] is True


def test_run_full_corpus_acceptance_fails_closed_on_transition_error(
    tmp_path: Path,
) -> None:
    """FINDING C: a transition_error anywhere fails the gate closed.

    The gate must never report executed when a transition crashed; the
    evidence file is still written with the per-transition failure so the
    live run is diagnosable.
    """
    module = _runner()
    matrix = _mutate(
        _valid_matrix(),
        "manual_legacy_preservation",
        outcome="transition_error",
        error_type="ValueError",
    )
    seams = _FakeSeams(matrix)
    evidence_path = tmp_path / EVIDENCE_NAME
    outcome = module.run_full_corpus_acceptance(
        _authorized_env(),
        target_uri=_DB_URL,
        target_parser=seams.target_parser,
        connection_factory=seams.connection_factory,
        matrix_runner=seams.matrix_runner,
        evidence_writer=seams.evidence_writer,
        evidence_path=evidence_path,
    )
    assert outcome.status == module.FAILED_STATUS
    assert outcome.status != module.EXECUTED_STATUS
    assert evidence_path.exists()
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert payload["status"] == module.FAILED_STATUS
    assert (
        payload["matrix"]["manual_legacy_preservation"]["outcome"] == "transition_error"
    )
    assert payload["matrix"]["manual_legacy_preservation"]["error_type"] == "ValueError"


def test_validate_matrix_outcomes_fails_on_transition_error_any_transition() -> None:
    """FINDING C: transition_error fails the gate on ANY transition.

    Negative-control exemptions (rolled_back_failure on
    invalid_document_isolation / changed_set_failure_rollback) do not extend
    to transition_error: a crashed transition is never an acceptable outcome.
    """
    module = _runner()
    for key in _valid_matrix():
        matrix = _mutate(
            _valid_matrix(), key, outcome="transition_error", error_type="ValueError"
        )
        failures = module._validate_matrix_outcomes(matrix)
        assert any(
            "transition_error" in failure for failure in failures
        ), f"expected a transition_error failure for {key}, got {failures}"


def test_source_pins_transition_error_fail_closed() -> None:
    """FINDING C source pins: transition_error recording + error_type."""
    source = _runner_source()
    assert "transition_error" in source
    assert "error_type" in source
    assert "def _run_transition_matrix" in source


# -- FINDING D: serialization pre-converge ----------------------------------


def test_serialization_transitions_pre_converge_before_overlap() -> None:
    """FINDING D: the overlap reconcile must see the FULL desired state.

    The matrix shares one disposable DB across transitions and transition 3
    leaves the main scope at the SHRUNK state. A serialization transition must
    FIRST pre-converge the target with one reconcile of the full desired
    state, THEN run the lock-overlap exercise: the overlapping reconcile must
    complete WITHOUT new DML (second_outcome == 'no_op'). The stateful fake
    returns 'changed' for the first reconcile (the pre-converge converging
    shrunk->full) and 'no_op' for every subsequent one; on the pre-fix code
    the overlap reconcile itself pops the 'changed' result and the strict
    assertion fails.
    """
    module = _runner()
    target = module.parse_disposable_postgresql_target(_DB_URL, _EXPECTED_DB_CANARY)
    scope = module.E2bDocumentScope(
        document_id=module._FIXTURE_DOCUMENT_ID,
        version_id=module._FIXTURE_VERSION_ID,
    )
    for transition_name, first_outcome in (
        ("_transition_e2b_serialization", "changed"),
        ("_transition_e2a_serialization", "no_op"),
    ):
        seams = _FakeMatrixSeams(
            [_result(first_outcome), _result("no_op")], _count_resolver
        )
        transition = getattr(module, transition_name)(
            target,
            connection_factory=seams.connection_factory,
            repository_factory=seams.repository_factory,
        )
        assert transition["pre_converge_outcome"] == first_outcome
        assert transition["second_outcome"] == "no_op"
        assert transition["serialized"] is True
        assert transition["duplicate_rows"] == 0
        assert transition["lock_key_is_e2a"] is True
        assert transition["lock_key_is_e2b"] is False
        # The pre-converge reconcile must happen BEFORE the lock-overlap
        # exercise: the first reconcile entry precedes the holder's advisory
        # lock acquisition in the call log.
        reconcile_index = next(
            i for i, entry in enumerate(seams.call_log) if entry[0] == "reconcile"
        )
        lock_index = next(
            i
            for i, entry in enumerate(seams.call_log)
            if entry[0] == "execute" and "pg_advisory_xact_lock" in str(entry[1])
        )
        assert reconcile_index < lock_index
        assert len(seams.reconcile_scopes) == 2
        for recorded_scope in seams.reconcile_scopes:
            assert recorded_scope == scope


def test_source_pins_serialization_pre_converge() -> None:
    """FINDING D source pins: pre-converge before the lock-overlap exercise."""
    source = _runner_source()
    assert "pre_converge_outcome" in source
    assert "def _transition_e2b_serialization" in source
    assert "def _transition_e2a_serialization" in source


# -- fixture setup SQL (real-database unique-key coverage) ------------------


def _fixture_executes(
    seams: _FakeMatrixSeams,
) -> list[tuple[str, object]]:
    """Return (statement, parameters) pairs for every executed statement."""
    return [
        (str(entry[1]), entry[2]) for entry in seams.call_log if entry[0] == "execute"
    ]


def test_fixture_setup_uses_distinct_source_uri_per_document() -> None:
    """Every fixture document INSERT must carry a distinct source_uri.

    documents.source_uri has the UNIQUE index idx_documents_source_uri
    (migration 002); hardcoding one source_uri for all fixture documents
    violates it on a real database because ON CONFLICT (doc_id) cannot fire
    for a different doc_id. The fake-cursor capture proves the parameter is
    passed per document and distinct across all three fixture documents.
    """
    module = _runner()
    target = module.parse_disposable_postgresql_target(_DB_URL, _EXPECTED_DB_CANARY)
    seams = _FakeMatrixSeams([], _count_resolver)
    module._prepare_fixture_state(target, connection_factory=seams.connection_factory)
    executes = _fixture_executes(seams)
    document_inserts = [
        (statement, parameters)
        for statement, parameters in executes
        if "INSERT INTO documents" in statement
    ]
    assert len(document_inserts) == 3
    source_uris: list[str] = []
    for statement, parameters in document_inserts:
        assert isinstance(parameters, tuple)
        assert (
            len(parameters) == 2
        ), "documents INSERT must pass (doc_id, source_uri) as parameters"
        source_uri = parameters[1]
        assert isinstance(source_uri, str) and source_uri
        source_uris.append(source_uri)
    assert len(set(source_uris)) == 3


def test_fixture_setup_inserts_are_idempotent_and_unique_key_covered() -> None:
    """Every fixture INSERT must be idempotent and re-runnable.

    Audits the full fixture setup for unique-key coverage: every INSERT must
    carry ON CONFLICT ... DO NOTHING, and a second run against the same
    database must issue the exact same deterministic statements without
    failing or duplicating fixture rows.
    """
    module = _runner()
    target = module.parse_disposable_postgresql_target(_DB_URL, _EXPECTED_DB_CANARY)
    first_seams = _FakeMatrixSeams([], _count_resolver)
    module._prepare_fixture_state(
        target, connection_factory=first_seams.connection_factory
    )
    first_executes = _fixture_executes(first_seams)
    inserts = [
        (statement, parameters)
        for statement, parameters in first_executes
        if "INSERT INTO" in statement
    ]
    assert inserts
    for statement, _ in inserts:
        assert (
            "ON CONFLICT" in statement
        ), f"fixture INSERT lacks unique-key coverage: {statement}"
    second_seams = _FakeMatrixSeams([], _count_resolver)
    module._prepare_fixture_state(
        target, connection_factory=second_seams.connection_factory
    )
    second_executes = _fixture_executes(second_seams)
    assert [statement for statement, _ in second_executes] == [
        statement for statement, _ in first_executes
    ]
    assert [parameters for _, parameters in second_executes] == [
        parameters for _, parameters in first_executes
    ]


# -- redacted CLI ----------------------------------------------------------


def test_run_redacted_cli_blocked_returns_nonzero_with_exact_stdout(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _runner()
    code = module._run_redacted_cli([])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == "blocked_not_executed\n"
    assert captured.err == ""


def test_run_redacted_cli_maps_value_error_to_fixed_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _runner()

    def _main(argv: object) -> int:
        raise ValueError("secret detail must never be printed")

    monkeypatch.setattr(module, "main", _main)
    code = module._run_redacted_cli([])
    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert captured.err == _CLI_FAILURE_MESSAGE + "\n"


def test_run_redacted_cli_maps_psycopg_error_to_fixed_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _runner()

    def _main(argv: object) -> int:
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(module, "main", _main)
    code = module._run_redacted_cli([])
    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert captured.err == _CONNECT_FAILURE_MESSAGE + "\n"


def test_cli_subprocess_default_blocked_with_sanitized_env() -> None:
    if not RUNNER_PATH.is_file():
        pytest.fail(f"RED: runner absent: {RUNNER_PATH}")
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "COMSPEC": os.environ.get("COMSPEC", ""),
        "TEMP": os.environ.get("TEMP", ""),
        "PYTHONPATH": str(REPO_ROOT),
    }
    assert not (_DATABASE_ROUTING_KEYS & env.keys())
    result = subprocess.run(
        [sys.executable, str(RUNNER_PATH)],
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    assert result.returncode != 0
    assert result.stdout == "blocked_not_executed\n"
    assert result.stderr == ""
    assert not EVIDENCE_PATH.exists()


# -- source-level contract pins --------------------------------------------


def test_source_forbids_live_automation_surfaces() -> None:
    source = _runner_source()
    for forbidden in (
        "run_migrations",
        "psycopg.connect(",
        "DATABASE_URL",
        "FORMAL_RUNTIME_DATABASE_URL",
        "postgresql://",
        "PGSERVICE",
        "PGPASSWORD",
        "retry",
        "backoff",
        "time.sleep",
        "sleep(",
        "max_attempts",
        "subprocess",
        "os.system",
        "os.popen",
        "Popen",
        "docker",
        "docker-compose",
        "socket",
        "http.client",
        "urllib.",
        "requests.",
        "curl",
        "psql",
        "pg_dump",
        "createdb",
        "initdb",
        "pg_ctl",
        "wsl",
        "sqlalchemy",
        "modelscope",
        "torch",
        "transformers",
        "snapshot_download",
    ):
        assert (
            forbidden not in source
        ), f"forbidden live-automation reference: {forbidden}"


def test_source_forbids_environment_enumeration_and_copy() -> None:
    source = _runner_source()
    assert source.count("os.environ") == 1
    for forbidden in (
        "os.environ.copy",
        "dict(os.environ",
        "os.getenv",
        "getenv(",
        "environ.items()",
        "environ.keys()",
        "environ.values()",
        "FORMAL_RUNTIME_DATABASE_URL",
    ):
        assert forbidden not in source, f"forbidden environment reference: {forbidden}"


def test_source_evidence_writes_only_after_authorization() -> None:
    source = _runner_source()
    assert source.count("def _write_evidence(") == 1
    assert source.count(".write_text(") <= 1
    for forbidden in (".write_bytes(", ".open(", "os.makedirs"):
        assert forbidden not in source, f"forbidden write surface: {forbidden}"
    assert "evidence_writer(" in source
    assert source.index("def _write_evidence(") < source.rindex("evidence_writer(")
    assert source.index("_require_gate_authorization") < source.rindex(
        "evidence_writer("
    )


def test_source_has_main_entry_guard() -> None:
    source = _runner_source()
    assert 'if __name__ == "__main__":' in source
    assert "raise SystemExit(_run_redacted_cli())" in source


def test_source_pins_keyword_only_public_gate_function() -> None:
    source = _runner_source()
    assert "def run_full_corpus_acceptance(" in source
    assert "AcceptanceOutcome" in source
    assert "*," in source
    assert "target_uri" in source
    # The runner is fully annotated, so each seam appears as name: Type =
    # default; pin the seam names and their exact defaults.
    for required in (
        "target_parser",
        "connection_factory",
        "repository_factory",
        "matrix_runner",
        "evidence_writer",
        "evidence_path",
    ):
        assert required in source, f"public gate seam missing: {required}"
    for default in (
        "parse_disposable_postgresql_target",
        "runtime_connection_factory",
        "_run_transition_matrix",
        "_write_evidence",
        "EVIDENCE_PATH",
    ):
        assert default in source, f"public gate default missing: {default}"


def test_source_pins_fixture_candidate_path_and_matrix() -> None:
    source = _runner_source()
    assert "fixture_candidates" in source
    for marker in (
        "first_materialization",
        "equivalent_rerun",
        "changed_set_convergence",
        "manual_legacy_preservation",
        "invalid_document_isolation",
        "changed_set_failure_rollback",
        "e2b_vs_e2b_serialization",
        "e2a_vs_e2b_serialization",
        "okf:e2a:parent:",
        "chunk_entity_links",
        "e2b_owner_scope",
        "okf_e2b_node_link_ownership",
        "reconcile_document",
    ):
        assert marker in source, f"matrix marker missing: {marker}"


def test_source_pins_dict_row_default_and_failed_status() -> None:
    """FINDING A/B source pins: dict-row default factory and fail-closed status."""
    source = _runner_source()
    assert "def _e2b_connection_factory(" in source
    assert "row_factory" in source
    assert "dict_row" in source
    # The audit connection factory is derived from the same connection_factory
    # inside _reconcile_once, so it inherits the dict-row binding.
    assert "lambda: connection_factory(target)" in source
    assert "executed_failed" in source
    assert "def _validate_matrix_outcomes(" in source
    assert "FAILED_EXIT_CODE" in source
