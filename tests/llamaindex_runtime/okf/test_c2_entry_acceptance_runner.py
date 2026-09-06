"""TDD tests for the Phase 16-17 Task 3 C2 entry acceptance runner.

Mirrors the proven 16-15 gate-runner test discipline
(test_e2b_full_corpus_acceptance_runner.py): lazy runner loading, recording
environments, hostile seams, pure-fake authorized orchestration, fail-closed
proof validation, sanitized-env subprocess proof, and source-level contract
pins. No database, network, or live gate execution happens here.
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
import uuid
from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

import psycopg
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
VERIFICATION_DIR = REPO_ROOT / "verification" / "phase16-raw-corpus-entity-layer"
RUNNER_PATH = VERIFICATION_DIR / "run_c2_entry_acceptance.py"

EVIDENCE_NAME = "c2_entry_evidence.md"
EVIDENCE_PATH = VERIFICATION_DIR / EVIDENCE_NAME

AUTH_ENV = "OKF_E2B_C2_ENTRY_AUTHORIZED"
DISPOSABLE_ENV = "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE"
EXPECTED_DATABASE_ENV = "OKF_REBUILD_EXPECTED_DATABASE"
_GATE_ROUTING_KEYS = frozenset({AUTH_ENV, DISPOSABLE_ENV, EXPECTED_DATABASE_ENV})

_DATABASE_ROUTING_KEYS = frozenset(
    {
        "DATABASE_URL",
        "FORMAL_RUNTIME_DATABASE_URL",
        "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE",
        "OKF_REBUILD_EXPECTED_DATABASE",
        "OKF_FAILURE_AUDIT_ACCEPTANCE",
        "OKF_REBUILD_DOCKER_ACCEPTANCE",
        "OKF_E2A_DISPOSABLE_TEST_AUTHORIZED",
        "OKF_E2B_DISPOSABLE_TEST_AUTHORIZED",
        "OKF_E2B_MIGRATION_TEST_AUTHORIZED",
        "OKF_E2B_MODELSCOPE_MIRROR_AUTHORIZED",
        "OKF_E2B_RANER_SMOKE_AUTHORIZED",
        "OKF_E2B_C2_ENTRY_AUTHORIZED",
    }
)

_EXPECTED_DB_CANARY = "okf_e2b_c2_entry_disposable"
_DB_URL = f"postgresql://okf:secret@127.0.0.1:5432/{_EXPECTED_DB_CANARY}"

_C1_HASH = "53ae99b6e4f85223ccbfe99910a13a711d12d033670db4a408eb532068a412e3"
_C1_SUCCESS_NAME = "e2b_full_corpus_acceptance_evidence_executed_SUCCESS_2026-08-31.md"
_C1_PLAIN_NAME = "e2b_full_corpus_acceptance_evidence_executed_2026-08-31.md"
_ARCHIVED_C1_PATH = VERIFICATION_DIR / _C1_PLAIN_NAME
_C1_MATRIX_KEYS = frozenset(
    {
        "first_materialization",
        "equivalent_rerun",
        "changed_set_convergence",
        "manual_legacy_preservation",
        "invalid_document_isolation",
        "changed_set_failure_rollback",
        "e2b_vs_e2b_serialization",
        "e2a_vs_e2b_serialization",
    }
)

_SKIP_REASONS = frozenset(
    {"authorization_missing", "disposable_target_gate_missing", "c1_not_closed"}
)

_RUNNER_MODULES: dict[Path, Any] = {}


def _runner() -> Any:
    """Lazily load the runner module exactly like the 16-15 gate tests."""
    module = _RUNNER_MODULES.get(RUNNER_PATH)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(
        "run_c2_entry_acceptance", RUNNER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_c2_entry_acceptance"] = module
    spec.loader.exec_module(module)
    _RUNNER_MODULES[RUNNER_PATH] = module
    return module


def _runner_source() -> str:
    return RUNNER_PATH.read_text(encoding="utf-8")


def _authorized_env() -> dict[str, str]:
    return {
        AUTH_ENV: "1",
        DISPOSABLE_ENV: "1",
        EXPECTED_DATABASE_ENV: _EXPECTED_DB_CANARY,
    }


def _c1_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "status": "executed",
        "candidate_path": "fixture_candidates",
        "matrix": {key: {"outcome": "changed"} for key in _C1_MATRIX_KEYS},
    }
    payload.update(overrides)
    return payload


def _c1_bytes(payload: Mapping[str, object]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _archived_c1_bytes() -> bytes:
    """Real archived 16-15 success evidence; its hash pins the linkage."""
    raw = _ARCHIVED_C1_PATH.read_bytes()
    assert (
        hashlib.sha256(raw).hexdigest() == _C1_HASH
    ), "archived 16-15 success evidence no longer matches the C1 CLOSED record"
    return raw


def _valid_proof() -> dict[str, object]:
    return {
        "catalog_applied": {
            "outcome": "applied",
            "migrations": 21,
            "tail_includes_021": True,
        },
        "default_off_parity": {
            "outcome": "no_op",
            "cluster_count": 0,
            "membership_count": 0,
            "c2_dml_total": 0,
        },
        "rules_materialization": {
            "outcome": "materialized",
            "cluster_count": 1,
            "membership_count": 2,
            "deterministic_ids_verified": True,
        },
        "tombstone": {
            "outcome": "tombstoned",
            "cluster_count_tombstoned": 1,
            "membership_preserved": 2,
        },
    }


def _closed_proof() -> SimpleNamespace:
    return SimpleNamespace(
        closed=True,
        reason="closed",
        evidence_name=_C1_SUCCESS_NAME,
        evidence_sha256=_C1_HASH,
    )


def _open_proof(reason: str = "c1_evidence_missing") -> SimpleNamespace:
    return SimpleNamespace(
        closed=False, reason=reason, evidence_name="", evidence_sha256=""
    )


class _RecordingEnviron:
    # Records every get/enumeration access; exposes the gate allowlist only.
    # The runner only ever calls .get on the environment mapping (never
    # indexes or enumerates), so this plain class is behavior-compatible
    # while keeping the dict-override machinery out of the picture.

    def __init__(self, values: Mapping[str, str]) -> None:
        self._values = dict(values)
        self.get_calls: list[tuple[str, object]] = []
        self.enumeration_calls: list[str] = []

    def get(self, key: str, default: str | None = None) -> str | None:
        self.get_calls.append((key, default))
        return self._values.get(key, default)

    def keys(self) -> list[str]:
        self.enumeration_calls.append("keys")
        return list(self._values.keys())

    def items(self) -> list[tuple[str, str]]:
        self.enumeration_calls.append("items")
        return list(self._values.items())

    def values(self) -> list[str]:
        self.enumeration_calls.append("values")
        return list(self._values.values())

    def copy(self) -> dict[str, str]:
        self.enumeration_calls.append("copy")
        return dict(self._values)


class _Hostile:
    """Raises on ANY attribute access; proves a seam is never touched."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"hostile seam was touched: {name}")


class _FakeSeams:
    """Pure-fake seams for the authorized orchestration tests."""

    def __init__(self) -> None:
        self.target = SimpleNamespace(dbname=_EXPECTED_DB_CANARY)
        self.target_parser_calls: list[tuple[str, str]] = []
        self.proof_calls: list[tuple[object, dict[str, object]]] = []
        self.closure_calls: list[tuple[Path, ...]] = []
        self.write_calls: list[tuple[dict[str, object], Path]] = []

    def target_parser(self, database_url: str, expected_database: str) -> Any:
        self.target_parser_calls.append((database_url, expected_database))
        return self.target

    def connection_factory(self, target: object) -> Any:
        return SimpleNamespace(closed=True)

    def proof_runner(self, target: object, **kwargs: object) -> dict[str, object]:
        self.proof_calls.append((target, kwargs))
        return dict(_valid_proof())

    def closure_prover(self, verification_dir: Path) -> Any:
        self.closure_calls.append((verification_dir,))
        return _closed_proof()

    def evidence_writer(self, payload: Mapping[str, object], path: Path) -> str:
        self.write_calls.append((dict(payload), path))
        path.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        return hashlib.sha256(
            path.read_text(encoding="utf-8").encode("utf-8")
        ).hexdigest()


# -- module, constants and gate contract -----------------------------------


def test_runner_module_must_exist_for_lazy_load() -> None:
    assert RUNNER_PATH.is_file(), f"RED: runner absent: {RUNNER_PATH}"


def test_runner_constants_pin_gate_contract() -> None:
    module = _runner()
    assert module.AUTH_ENV == AUTH_ENV
    assert module.DISPOSABLE_ENV == DISPOSABLE_ENV
    assert module.EXPECTED_DATABASE_ENV == EXPECTED_DATABASE_ENV
    assert module.GATE_ROUTING_KEYS == _GATE_ROUTING_KEYS
    assert module.SKIPPED_STATUS == "skipped_not_entered"
    assert module.EXECUTED_STATUS == "executed"
    assert module.FAILED_STATUS == "executed_failed"
    assert module.SKIPPED_EXIT_CODE == 1
    assert module.FAILED_EXIT_CODE == 3
    assert module.EVIDENCE_NAME == EVIDENCE_NAME
    assert module.FIXTURE_CANDIDATE_PATH == "fixture_candidates"
    assert module.SKIP_REASONS == _SKIP_REASONS
    assert module.CLI_FAILURE_MESSAGE == (
        "C2 entry acceptance refused; failure details are not disclosed"
    )
    assert module.CONNECT_FAILURE_MESSAGE == (
        "Database connection failed; refusing C2 entry acceptance"
    )


def test_runner_pins_c1_closed_precondition_linkage() -> None:
    module = _runner()
    assert module.C1_SUCCESS_EVIDENCE_SHA256 == _C1_HASH
    assert module.C1_EVIDENCE_CANDIDATE_NAMES == (_C1_SUCCESS_NAME, _C1_PLAIN_NAME)
    assert module.C1_EVIDENCE_SCHEMA_VERSION == 1
    assert module.C1_MATRIX_KEYS == _C1_MATRIX_KEYS
    assert module.COREF_RULES_VERSION == "coref-rules-1"


def test_runner_defaults_are_exact_production_symbols() -> None:
    module = _runner()
    from scripts._rebuild_database_connection import (  # noqa: PLC0415
        parse_disposable_postgresql_target,
    )
    from llamaindex_runtime.registry.migration_catalog import (  # noqa: PLC0415
        FULL_MIGRATION_CATALOG,
    )

    signature = inspect.signature(module.run_c2_entry_acceptance)
    parameters = signature.parameters
    assert parameters["target_uri"].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters["target_uri"].default is None
    assert parameters["target_parser"].default is parse_disposable_postgresql_target
    assert parameters["connection_factory"].default is module._c2_connection_factory
    assert parameters["catalog"].default is FULL_MIGRATION_CATALOG
    assert parameters["apply_catalog"].default is module._apply_catalog
    assert parameters["resolution_reader"].default is module._read_resolved_mentions
    assert parameters["proof_runner"].default is module._run_proof_steps
    assert parameters["closure_prover"].default is module._prove_c1_closed
    assert parameters["evidence_writer"].default is module._write_evidence
    assert parameters["evidence_path"].default is module.EVIDENCE_PATH
    main_signature = inspect.signature(module.main)
    assert main_signature.parameters["target_uri"].kind is (
        inspect.Parameter.KEYWORD_ONLY
    )
    assert main_signature.parameters["target_uri"].default is None
    assert [field.name for field in fields(module.C2EntryOutcome)] == [
        "status",
        "candidate_path",
        "proof",
        "evidence_sha256",
    ]
    assert [field.name for field in fields(module.C1ClosureProof)] == [
        "closed",
        "reason",
        "evidence_name",
        "evidence_sha256",
    ]


def test_production_db_prerequisites_are_real() -> None:
    module = _runner()
    from scripts._rebuild_database_connection import (  # noqa: PLC0415
        parse_disposable_postgresql_target,
        runtime_connection_factory,
    )

    target = parse_disposable_postgresql_target(_DB_URL, _EXPECTED_DB_CANARY)
    assert target.dbname == _EXPECTED_DB_CANARY
    assert callable(runtime_connection_factory)
    assert callable(module.build_coref_clusters)
    assert callable(module.deterministic_id)


def test_archived_c1_evidence_hashes_to_recorded_artifact() -> None:
    """Locks the C1 CLOSED linkage: the checkout artifact matches R5 record."""
    _archived_c1_bytes()


# -- C1 CLOSED prover ------------------------------------------------------


def test_c1_closure_prover_accepts_success_evidence(tmp_path: Path) -> None:
    module = _runner()
    raw = _archived_c1_bytes()
    (tmp_path / _C1_SUCCESS_NAME).write_bytes(raw)
    proof = module._prove_c1_closed(tmp_path)
    assert proof.closed is True
    assert proof.reason == "closed"
    assert proof.evidence_name == _C1_SUCCESS_NAME
    assert proof.evidence_sha256 == _C1_HASH


def test_c1_closure_prover_accepts_plain_archived_name(tmp_path: Path) -> None:
    """Checkout reality: only the plain name exists; closure still holds."""
    module = _runner()
    (tmp_path / _C1_PLAIN_NAME).write_bytes(_archived_c1_bytes())
    proof = module._prove_c1_closed(tmp_path)
    assert proof.closed is True
    assert proof.evidence_name == _C1_PLAIN_NAME
    assert proof.evidence_sha256 == _C1_HASH


def test_c1_closure_prover_fails_closed_when_archive_missing(tmp_path: Path) -> None:
    module = _runner()
    proof = module._prove_c1_closed(tmp_path)
    assert proof.closed is False
    assert proof.reason == "c1_evidence_missing"
    assert proof.evidence_name == ""
    assert proof.evidence_sha256 == ""


def test_c1_closure_prover_never_shadows_contradictory_first_candidate(
    tmp_path: Path,
) -> None:
    """A present but corrupted success file fails closed; the plain copy is
    never consulted as a shadow."""

    module = _runner()
    raw = bytearray(_archived_c1_bytes())
    raw[0] = 0x5B  # corrupt the payload; content differs -> hash mismatch
    (tmp_path / _C1_SUCCESS_NAME).write_bytes(bytes(raw))
    (tmp_path / _C1_PLAIN_NAME).write_bytes(_archived_c1_bytes())
    proof = module._prove_c1_closed(tmp_path)
    assert proof.closed is False
    assert proof.reason == "c1_evidence_contradictory"
    assert proof.evidence_name == _C1_SUCCESS_NAME


def _patched_hash_proof(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, raw: bytes
) -> Any:
    module = _runner()
    monkeypatch.setattr(
        module, "C1_SUCCESS_EVIDENCE_SHA256", hashlib.sha256(raw).hexdigest()
    )
    (tmp_path / _C1_SUCCESS_NAME).write_bytes(raw)
    return module


def test_c1_closure_prover_fails_closed_on_non_executed_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = _patched_hash_proof(
        monkeypatch, tmp_path, _c1_bytes(_c1_payload(status="executed_failed"))
    )
    proof = module._prove_c1_closed(tmp_path)
    assert proof.closed is False
    assert proof.reason == "c1_evidence_not_success"


def test_c1_closure_prover_fails_closed_on_schema_mismatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = _patched_hash_proof(
        monkeypatch, tmp_path, _c1_bytes(_c1_payload(schema_version=2))
    )
    proof = module._prove_c1_closed(tmp_path)
    assert proof.closed is False
    assert proof.reason == "c1_evidence_contradictory"


def test_c1_closure_prover_fails_closed_on_matrix_subset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    partial = {key: {"outcome": "changed"} for key in sorted(_C1_MATRIX_KEYS)[:7]}
    module = _patched_hash_proof(
        monkeypatch, tmp_path, _c1_bytes(_c1_payload(matrix=partial))
    )
    proof = module._prove_c1_closed(tmp_path)
    assert proof.closed is False
    assert proof.reason == "c1_evidence_not_success"


def test_c1_closure_prover_fails_closed_on_non_mapping_payload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = _patched_hash_proof(monkeypatch, tmp_path, b"[]")
    proof = module._prove_c1_closed(tmp_path)
    assert proof.closed is False
    assert proof.reason == "c1_evidence_contradictory"


def test_c1_closure_prover_fails_closed_on_unparseable_payload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = _patched_hash_proof(monkeypatch, tmp_path, b"{not json")
    proof = module._prove_c1_closed(tmp_path)
    assert proof.closed is False
    assert proof.reason == "c1_evidence_contradictory"


# -- skipped (default) semantics -------------------------------------------


def test_run_c2_entry_acceptance_default_skip_before_parsing_hostile_target(
    tmp_path: Path,
) -> None:
    module = _runner()
    hostile = _Hostile()
    seams = _FakeSeams()
    outcome = module.run_c2_entry_acceptance(
        {},
        target_uri=_DB_URL,
        target_parser=hostile,  # type: ignore[arg-type]
        connection_factory=hostile,  # type: ignore[arg-type]
        proof_runner=hostile,  # type: ignore[arg-type]
        closure_prover=hostile,  # type: ignore[arg-type]
        evidence_writer=seams.evidence_writer,
        evidence_path=tmp_path / EVIDENCE_NAME,
    )
    assert outcome.status == "skipped_not_entered"
    assert outcome.candidate_path == ""
    assert outcome.proof == {}
    payload = seams.write_calls[0][0]
    assert payload["status"] == "skipped_not_entered"
    assert payload["reason"] == "authorization_missing"
    assert len(seams.write_calls) == 1


def test_skip_records_redacted_evidence_with_zero_connections(tmp_path: Path) -> None:
    module = _runner()
    evidence_path = tmp_path / EVIDENCE_NAME
    outcome = module.run_c2_entry_acceptance(
        {},
        target_uri=_DB_URL,
        evidence_writer=module._write_evidence,
        evidence_path=evidence_path,
    )
    assert outcome.status == "skipped_not_entered"
    assert outcome.evidence_sha256 != ""
    assert evidence_path.exists()
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert payload == {
        "schema_version": 1,
        "status": "skipped_not_entered",
        "reason": "authorization_missing",
    }
    for forbidden in ("postgresql://", "127.0.0.1", "secret", _EXPECTED_DB_CANARY):
        assert forbidden not in evidence_path.read_text(encoding="utf-8")


def test_skip_never_claims_okf09_tested(tmp_path: Path) -> None:
    module = _runner()
    evidence_path = tmp_path / EVIDENCE_NAME
    module.run_c2_entry_acceptance(
        {},
        target_uri=_DB_URL,
        evidence_writer=module._write_evidence,
        evidence_path=evidence_path,
    )
    text = evidence_path.read_text(encoding="utf-8")
    assert "R-OKF-09" not in text
    assert "tested" not in text


def test_authorization_missing_short_circuits_closure_prover(tmp_path: Path) -> None:
    module = _runner()
    hostile = _Hostile()
    seams = _FakeSeams()
    module.run_c2_entry_acceptance(
        {},
        target_uri=_DB_URL,
        target_parser=hostile,  # type: ignore[arg-type]
        connection_factory=hostile,  # type: ignore[arg-type]
        proof_runner=hostile,  # type: ignore[arg-type]
        closure_prover=hostile,  # type: ignore[arg-type]
        evidence_writer=seams.evidence_writer,
        evidence_path=tmp_path / EVIDENCE_NAME,
    )
    assert seams.closure_calls == []


@pytest.mark.parametrize(
    "overrides",
    [
        {DISPOSABLE_ENV: "0"},
        {DISPOSABLE_ENV: ""},
        {DISPOSABLE_ENV: None},
        {EXPECTED_DATABASE_ENV: ""},
        {EXPECTED_DATABASE_ENV: None},
    ],
)
def test_disposable_gate_missing_records_reason_without_closure(
    tmp_path: Path,
    overrides: Mapping[str, object],
) -> None:
    module = _runner()
    environ = {
        AUTH_ENV: "1",
        DISPOSABLE_ENV: "1",
        EXPECTED_DATABASE_ENV: _EXPECTED_DB_CANARY,
    }
    for key, value in overrides.items():
        if value is None:
            environ.pop(key, None)
        else:
            environ[key] = str(value)
    hostile = _Hostile()
    seams = _FakeSeams()
    outcome = module.run_c2_entry_acceptance(
        environ,
        target_uri=_DB_URL,
        target_parser=hostile,  # type: ignore[arg-type]
        connection_factory=hostile,  # type: ignore[arg-type]
        proof_runner=hostile,  # type: ignore[arg-type]
        closure_prover=hostile,  # type: ignore[arg-type]
        evidence_writer=seams.evidence_writer,
        evidence_path=tmp_path / EVIDENCE_NAME,
    )
    assert outcome.status == "skipped_not_entered"
    assert seams.write_calls[0][0]["reason"] == "disposable_target_gate_missing"
    assert seams.closure_calls == []


def test_c1_not_closed_records_skip_after_closure_proof(tmp_path: Path) -> None:
    module = _runner()
    seams = _FakeSeams()

    def _open_prover(verification_dir: Path) -> Any:
        seams.closure_calls.append((verification_dir,))
        return _open_proof()

    seams.closure_prover = _open_prover  # type: ignore[assignment]

    def _proof_runner(*args: object, **kwargs: object) -> dict[str, object]:
        raise AssertionError("skip path must never run the proof")

    outcome = module.run_c2_entry_acceptance(
        _authorized_env(),
        target_uri=_DB_URL,
        target_parser=seams.target_parser,
        connection_factory=seams.connection_factory,
        proof_runner=_proof_runner,
        closure_prover=seams.closure_prover,
        evidence_writer=seams.evidence_writer,
        evidence_path=tmp_path / EVIDENCE_NAME,
    )
    assert outcome.status == "skipped_not_entered"
    assert seams.write_calls[0][0]["reason"] == "c1_not_closed"
    assert len(seams.closure_calls) == 1
    assert seams.target_parser_calls == []


def test_skipped_evidence_write_is_deterministic(tmp_path: Path) -> None:
    module = _runner()
    first_path = tmp_path / "first.md"
    second_path = tmp_path / "second.md"
    first = module.run_c2_entry_acceptance(
        {},
        target_uri=_DB_URL,
        evidence_writer=module._write_evidence,
        evidence_path=first_path,
    )
    second = module.run_c2_entry_acceptance(
        {},
        target_uri=_DB_URL,
        evidence_writer=module._write_evidence,
        evidence_path=second_path,
    )
    assert first.evidence_sha256 == second.evidence_sha256
    assert first_path.read_bytes() == second_path.read_bytes()


# -- authorized orchestration ----------------------------------------------


def test_run_c2_entry_acceptance_full_authorized_path_with_pure_fakes(
    tmp_path: Path,
) -> None:
    module = _runner()
    seams = _FakeSeams()
    evidence_path = tmp_path / EVIDENCE_NAME
    outcome = module.run_c2_entry_acceptance(
        _authorized_env(),
        target_uri=_DB_URL,
        target_parser=seams.target_parser,
        connection_factory=seams.connection_factory,
        proof_runner=seams.proof_runner,
        closure_prover=seams.closure_prover,
        evidence_writer=seams.evidence_writer,
        evidence_path=evidence_path,
    )
    assert seams.target_parser_calls == [(_DB_URL, _EXPECTED_DB_CANARY)]
    assert len(seams.proof_calls) == 1
    assert seams.proof_calls[0][0] is seams.target
    assert set(seams.proof_calls[0][1]) == {
        "connection_factory",
        "catalog",
        "apply_catalog",
        "resolution_reader",
    }
    assert len(seams.closure_calls) == 1
    assert len(seams.write_calls) == 1
    assert seams.write_calls[0][1] is evidence_path
    assert isinstance(outcome, module.C2EntryOutcome)
    assert outcome.status == "executed"
    assert outcome.candidate_path == "fixture_candidates"
    assert outcome.proof == _valid_proof()
    written = evidence_path.read_text(encoding="utf-8")
    assert (
        outcome.evidence_sha256 == hashlib.sha256(written.encode("utf-8")).hexdigest()
    )
    payload = seams.write_calls[0][0]
    assert payload["candidate_path"] == "fixture_candidates"
    assert payload["c1_closure"] == {
        "status": "executed",
        "hash_matched": True,
        "evidence_name": _C1_SUCCESS_NAME,
        "matrix_keys": 8,
    }
    for forbidden in (
        "postgresql://",
        "127.0.0.1",
        "secret",
        _EXPECTED_DB_CANARY,
        "DATABASE_URL",
        "Acme",
    ):
        assert forbidden not in json.dumps(payload, sort_keys=True)
        assert forbidden not in written


def test_run_c2_entry_acceptance_requires_programmatic_target(
    tmp_path: Path,
) -> None:
    module = _runner()
    seams = _FakeSeams()
    with pytest.raises(ValueError, match="programmatic target_uri is required"):
        module.run_c2_entry_acceptance(
            _authorized_env(),
            target_uri=None,
            target_parser=seams.target_parser,
            connection_factory=seams.connection_factory,
            proof_runner=seams.proof_runner,
            closure_prover=seams.closure_prover,
            evidence_writer=seams.evidence_writer,
            evidence_path=tmp_path / EVIDENCE_NAME,
        )
    assert seams.target_parser_calls == []
    assert seams.proof_calls == []


def test_run_c2_entry_acceptance_reads_only_gate_routing_keys(
    tmp_path: Path,
) -> None:
    module = _runner()
    seams = _FakeSeams()
    environ = _RecordingEnviron(_authorized_env())
    module.run_c2_entry_acceptance(
        environ,
        target_uri=_DB_URL,
        target_parser=seams.target_parser,
        connection_factory=seams.connection_factory,
        proof_runner=seams.proof_runner,
        closure_prover=seams.closure_prover,
        evidence_writer=seams.evidence_writer,
        evidence_path=tmp_path / EVIDENCE_NAME,
    )
    assert {key for key, _ in environ.get_calls} <= _GATE_ROUTING_KEYS
    assert not environ.enumeration_calls


def test_run_c2_entry_acceptance_skipped_reads_only_gate_routing_keys(
    tmp_path: Path,
) -> None:
    module = _runner()
    environ = _RecordingEnviron({AUTH_ENV: "0"})
    module.run_c2_entry_acceptance(
        environ,
        target_uri=_DB_URL,
        evidence_writer=_FakeSeams().evidence_writer,
        evidence_path=tmp_path / EVIDENCE_NAME,
    )
    assert {key for key, _ in environ.get_calls} <= _GATE_ROUTING_KEYS
    assert not environ.enumeration_calls


def test_run_c2_entry_acceptance_evidence_write_is_deterministic(
    tmp_path: Path,
) -> None:
    module = _runner()
    first_path = tmp_path / "first.md"
    second_path = tmp_path / "second.md"
    first = module.run_c2_entry_acceptance(
        _authorized_env(),
        target_uri=_DB_URL,
        target_parser=_FakeSeams().target_parser,
        connection_factory=_FakeSeams().connection_factory,
        proof_runner=_FakeSeams().proof_runner,
        closure_prover=_FakeSeams().closure_prover,
        evidence_writer=module._write_evidence,
        evidence_path=first_path,
    )
    second = module.run_c2_entry_acceptance(
        _authorized_env(),
        target_uri=_DB_URL,
        target_parser=_FakeSeams().target_parser,
        connection_factory=_FakeSeams().connection_factory,
        proof_runner=_FakeSeams().proof_runner,
        closure_prover=_FakeSeams().closure_prover,
        evidence_writer=module._write_evidence,
        evidence_path=second_path,
    )
    assert first.evidence_sha256 == second.evidence_sha256
    assert first_path.read_bytes() == second_path.read_bytes()


# -- evidence redaction allowlist ------------------------------------------


def _authorized_payload(proof: Mapping[str, object] | None = None) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "executed",
        "candidate_path": "fixture_candidates",
        "c1_closure": {
            "status": "executed",
            "hash_matched": True,
            "evidence_name": _C1_SUCCESS_NAME,
            "matrix_keys": 8,
        },
        "proof": dict(_valid_proof() if proof is None else proof),
    }


@pytest.mark.parametrize(
    "extra_key",
    ["matrix", "credentials", "connection_string", "unexpected"],
)
def test_redact_rejects_unknown_authorized_payload_fields(extra_key: str) -> None:
    module = _runner()
    payload = _authorized_payload()
    payload[extra_key] = "x"
    with pytest.raises(ValueError, match="unexpected evidence fields"):
        module._redact_evidence_payload(payload)


@pytest.mark.parametrize(
    "bad_payload",
    [
        {
            "schema_version": 1,
            "status": "skipped_not_entered",
            "reason": "authorization_missing",
            "extra": 1,
        },
        {
            "schema_version": 1,
            "status": "executed",
            "reason": "authorization_missing",
            "note": 1,
        },
    ],
)
def test_redact_rejects_unknown_skipped_payload_fields(
    bad_payload: Mapping[str, object],
) -> None:
    module = _runner()
    with pytest.raises(ValueError, match="unexpected skipped evidence fields"):
        module._redact_evidence_payload(bad_payload, skipped=True)


def test_redact_rejects_unsupported_skip_reason() -> None:
    module = _runner()
    payload = {
        "schema_version": 1,
        "status": "skipped_not_entered",
        "reason": "not_a_real_reason",
    }
    with pytest.raises(ValueError, match="unsupported skip reason"):
        module._redact_evidence_payload(payload, skipped=True)


def test_redact_rejects_skipped_status_mismatch() -> None:
    module = _runner()
    payload = {
        "schema_version": 1,
        "status": "executed",
        "reason": "authorization_missing",
    }
    with pytest.raises(ValueError, match="skipped evidence status mismatch"):
        module._redact_evidence_payload(payload, skipped=True)


def _mutate_drop_matrix_keys(payload: Any) -> None:
    payload["c1_closure"].pop("matrix_keys")


def _mutate_add_closure_field(payload: Any) -> None:
    payload["c1_closure"]["extra"] = 1


def _mutate_break_hash_match(payload: Any) -> None:
    payload["c1_closure"]["hash_matched"] = False


def _mutate_candidate_path(payload: Any) -> None:
    payload["candidate_path"] = "other"


def _mutate_status(payload: Any) -> None:
    payload["status"] = "weird"


@pytest.mark.parametrize(
    "mutator",
    [
        _mutate_drop_matrix_keys,
        _mutate_add_closure_field,
        _mutate_break_hash_match,
        _mutate_candidate_path,
        _mutate_status,
    ],
)
def test_redact_rejects_malformed_authorized_payload(
    mutator: Any,
) -> None:
    module = _runner()
    payload = _authorized_payload()
    mutator(payload)
    with pytest.raises(ValueError):
        module._redact_evidence_payload(payload)


@pytest.mark.parametrize(
    "proof",
    [
        {"extra_step": {"outcome": "x"}},
        {
            "catalog_applied": {
                "outcome": "applied",
                "migrations": 21,
                "tail_includes_021": True,
                "extra": 1,
            }
        },
        {
            "catalog_applied": {
                "outcome": "applied",
                "migrations": 21,
                "tail_includes_021": True,
            },
            "default_off_parity": {"outcome": "no_op"},
        },
        {
            "proof_error": {"outcome": "proof_error", "error_type": "RuntimeError"},
            "extra": 1,
        },
    ],
)
def test_redact_rejects_unknown_or_incomplete_proof_step_fields(
    proof: Mapping[str, object],
) -> None:
    module = _runner()
    with pytest.raises(ValueError, match="unexpected proof step"):
        module._redact_evidence_payload(_authorized_payload(proof))


def test_redact_accepts_valid_skipped_and_authorized_payloads() -> None:
    module = _runner()
    skipped = {
        "schema_version": 1,
        "status": "skipped_not_entered",
        "reason": "c1_not_closed",
    }
    redacted = module._redact_evidence_payload(skipped, skipped=True)
    assert redacted == skipped
    redacted = module._redact_evidence_payload(_authorized_payload())
    assert redacted == _authorized_payload()


# -- proof validation -------------------------------------------------------


def test_validate_proof_outcomes_accepts_valid_proof() -> None:
    module = _runner()
    assert module._validate_proof_outcomes(_valid_proof()) == []


def test_validate_proof_outcomes_fails_on_proof_error() -> None:
    module = _runner()
    proof = _valid_proof()
    proof["proof_error"] = {"outcome": "proof_error", "error_type": "RuntimeError"}
    failures = module._validate_proof_outcomes(proof)
    assert failures == ["proof step raised an unexpected error"]


def _mutate_catalog_outcome(payload: Any) -> None:
    payload["catalog_applied"]["outcome"] = "skipped"


def _mutate_tail_flag(payload: Any) -> None:
    payload["catalog_applied"]["tail_includes_021"] = False


def _mutate_parity_clusters(payload: Any) -> None:
    payload["default_off_parity"]["cluster_count"] = 1


def _mutate_parity_membership(payload: Any) -> None:
    payload["default_off_parity"]["membership_count"] = 1


def _mutate_parity_dml(payload: Any) -> None:
    payload["default_off_parity"]["c2_dml_total"] = 1


def _mutate_parity_outcome(payload: Any) -> None:
    payload["default_off_parity"]["outcome"] = "changed"


def _mutate_cluster_count_zero(payload: Any) -> None:
    payload["rules_materialization"]["cluster_count"] = 0


def _mutate_membership_count_one(payload: Any) -> None:
    payload["rules_materialization"]["membership_count"] = 1


def _mutate_deterministic_false(payload: Any) -> None:
    payload["rules_materialization"]["deterministic_ids_verified"] = False


def _mutate_tombstone_count_zero(payload: Any) -> None:
    payload["tombstone"]["cluster_count_tombstoned"] = 0


def _mutate_preserved_zero(payload: Any) -> None:
    payload["tombstone"]["membership_preserved"] = 0


def _mutate_tombstone_count_two(payload: Any) -> None:
    payload["tombstone"]["cluster_count_tombstoned"] = 2


def _mutate_drop_tombstone(payload: Any) -> None:
    payload.pop("tombstone")


def _mutate_drop_catalog(payload: Any) -> None:
    payload.pop("catalog_applied")


@pytest.mark.parametrize(
    "mutator,expectation",
    [
        (_mutate_catalog_outcome, "catalog_applied outcome"),
        (_mutate_tail_flag, "migration 021"),
        (_mutate_parity_clusters, "cluster_count"),
        (_mutate_parity_membership, "membership_count"),
        (_mutate_parity_dml, "c2_dml_total"),
        (_mutate_parity_outcome, "no_op"),
        (_mutate_cluster_count_zero, "cluster_count must be >= 1"),
        (_mutate_membership_count_one, "membership_count must be >= 2"),
        (_mutate_deterministic_false, "deterministic ids must be verified"),
        (_mutate_tombstone_count_zero, "tombstoned"),
        (_mutate_preserved_zero, "membership_preserved"),
        (_mutate_tombstone_count_two, "must cover every materialized cluster"),
        (_mutate_drop_tombstone, "tombstone missing"),
        (_mutate_drop_catalog, "catalog_applied missing"),
    ],
)
def test_validate_proof_outcomes_detects_each_failure(
    mutator: Any, expectation: str
) -> None:
    module = _runner()
    proof = _valid_proof()
    mutator(proof)
    failures = module._validate_proof_outcomes(proof)
    assert any(expectation in failure for failure in failures)


def test_run_c2_entry_acceptance_fails_closed_when_proof_validation_fails(
    tmp_path: Path,
) -> None:
    module = _runner()
    seams = _FakeSeams()
    bad_proof: Any = _valid_proof()
    bad_proof["rules_materialization"]["cluster_count"] = 0
    seams.proof_runner = lambda *args, **kwargs: dict(bad_proof)  # type: ignore[assignment]
    evidence_path = tmp_path / EVIDENCE_NAME
    outcome = module.run_c2_entry_acceptance(
        _authorized_env(),
        target_uri=_DB_URL,
        target_parser=seams.target_parser,
        connection_factory=seams.connection_factory,
        proof_runner=seams.proof_runner,
        closure_prover=seams.closure_prover,
        evidence_writer=module._write_evidence,
        evidence_path=evidence_path,
    )
    assert outcome.status == "executed_failed"
    assert outcome.candidate_path == "fixture_candidates"
    assert evidence_path.exists()
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert payload["status"] == "executed_failed"


def test_run_c2_entry_acceptance_records_proof_error_and_writes_evidence(
    tmp_path: Path,
) -> None:
    module = _runner()
    seams = _FakeSeams()

    def _exploding(*args: object, **kwargs: object) -> dict[str, object]:
        raise RuntimeError("unexpected proof failure")

    evidence_path = tmp_path / EVIDENCE_NAME
    outcome = module.run_c2_entry_acceptance(
        _authorized_env(),
        target_uri=_DB_URL,
        target_parser=seams.target_parser,
        connection_factory=seams.connection_factory,
        proof_runner=_exploding,
        closure_prover=seams.closure_prover,
        evidence_writer=module._write_evidence,
        evidence_path=evidence_path,
    )
    assert outcome.status == "executed_failed"
    assert outcome.proof == {
        "proof_error": {"outcome": "proof_error", "error_type": "RuntimeError"}
    }
    assert evidence_path.exists()
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert payload["status"] == "executed_failed"
    assert payload["proof"] == {
        "proof_error": {"outcome": "proof_error", "error_type": "RuntimeError"}
    }


# -- main and redacted CLI --------------------------------------------------


def test_main_default_skipped_records_evidence_and_prints_status(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _runner()
    monkeypatch.setattr(module.os, "environ", {})
    try:
        code = module.main([], target_uri=_DB_URL)
        captured = capsys.readouterr()
        assert code == 1
        assert captured.out == "skipped_not_entered\n"
        assert captured.err == ""
        assert EVIDENCE_PATH.exists()
        payload = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
        assert payload == {
            "schema_version": 1,
            "status": "skipped_not_entered",
            "reason": "authorization_missing",
        }
    finally:
        if EVIDENCE_PATH.exists():
            EVIDENCE_PATH.unlink()


@pytest.mark.parametrize(
    "overrides",
    [
        {AUTH_ENV: "0"},
        {AUTH_ENV: ""},
        {AUTH_ENV: None},
        {DISPOSABLE_ENV: "0"},
        {DISPOSABLE_ENV: ""},
        {DISPOSABLE_ENV: None},
        {EXPECTED_DATABASE_ENV: ""},
        {EXPECTED_DATABASE_ENV: None},
    ],
)
def test_main_skipped_on_partial_or_malformed_authorization(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    overrides: Mapping[str, object],
) -> None:
    module = _runner()
    environ = _authorized_env()
    for key, value in overrides.items():
        if value is None:
            environ.pop(key, None)
        else:
            environ[key] = str(value)
    monkeypatch.setattr(module.os, "environ", environ)
    try:
        code = module.main([], target_uri=_DB_URL)
        captured = capsys.readouterr()
        assert code == 1
        assert captured.out == "skipped_not_entered\n"
        assert captured.err == ""
    finally:
        if EVIDENCE_PATH.exists():
            EVIDENCE_PATH.unlink()


def test_skipped_main_reads_only_gate_routing_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _runner()
    environ = _RecordingEnviron({AUTH_ENV: "0"})
    monkeypatch.setattr(module, "os", types.SimpleNamespace(environ=environ))
    try:
        code = module.main([], target_uri=_DB_URL)
        assert code == 1
        assert {key for key, _ in environ.get_calls} <= _GATE_ROUTING_KEYS
        assert not environ.enumeration_calls
    finally:
        if EVIDENCE_PATH.exists():
            EVIDENCE_PATH.unlink()


def test_skipped_main_zero_parser_connect_and_orchestration_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _runner()
    connect_calls: list[object] = []
    orchestration_calls: list[object] = []
    parser_calls: list[object] = []

    def _connect(*args: object, **kwargs: object) -> object:
        connect_calls.append((args, kwargs))
        raise AssertionError("skip path must never connect")

    def _orchestrate(*args: object, **kwargs: object) -> object:
        orchestration_calls.append((args, kwargs))
        raise AssertionError("skip path must never orchestrate")

    def _parse(*args: object, **kwargs: object) -> object:
        parser_calls.append((args, kwargs))
        raise AssertionError("skip path must never parse a target")

    monkeypatch.setattr(psycopg, "connect", _connect)
    monkeypatch.setattr(module, "build_coref_clusters", _orchestrate)
    monkeypatch.setattr(module, "parse_disposable_postgresql_target", _parse)
    monkeypatch.setattr(module.os, "environ", {})
    try:
        code = module.main([], target_uri=_DB_URL)
        assert code == 1
        assert not connect_calls
        assert not orchestration_calls
        assert not parser_calls
    finally:
        if EVIDENCE_PATH.exists():
            EVIDENCE_PATH.unlink()


def test_main_authorized_forwards_programmatic_target(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _runner()
    environ = _authorized_env()
    forwarded: list[tuple[object, object]] = []

    def _run(environ_arg: object, *, target_uri: object) -> object:
        forwarded.append((environ_arg, target_uri))
        return types.SimpleNamespace(status="executed")

    monkeypatch.setattr(module, "run_c2_entry_acceptance", _run)
    monkeypatch.setattr(module.os, "environ", environ)
    code = module.main([], target_uri=_DB_URL)
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out == "executed\n"
    assert len(forwarded) == 1
    assert forwarded[0][0] is environ
    assert forwarded[0][1] == _DB_URL


def test_main_returns_failed_exit_code_for_executed_failed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _runner()

    def _run(environ_arg: object, *, target_uri: object) -> object:
        return types.SimpleNamespace(status="executed_failed")

    monkeypatch.setattr(module, "run_c2_entry_acceptance", _run)
    monkeypatch.setattr(module.os, "environ", _authorized_env())
    code = module.main([], target_uri=_DB_URL)
    captured = capsys.readouterr()
    assert code == 3
    assert captured.out == "executed_failed\n"


def test_main_rejects_target_uri_in_argv_before_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _runner()
    gate_calls: list[object] = []
    monkeypatch.setattr(
        module,
        "run_c2_entry_acceptance",
        lambda *a, **k: gate_calls.append((a, k)),
    )
    monkeypatch.setattr(module.os, "environ", _authorized_env())
    with pytest.raises(ValueError, match="argv credential route is forbidden"):
        module.main([_DB_URL], target_uri=None)
    assert gate_calls == []


def test_main_requires_programmatic_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _runner()

    def _run(environ_arg: object, *, target_uri: object) -> object:
        raise ValueError("programmatic target_uri is required")

    monkeypatch.setattr(module, "run_c2_entry_acceptance", _run)
    monkeypatch.setattr(module.os, "environ", _authorized_env())
    with pytest.raises(ValueError, match="programmatic target_uri is required"):
        module.main([], target_uri=None)


def test_run_redacted_cli_skipped_returns_nonzero_with_exact_stdout(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _runner()
    code = module._run_redacted_cli([])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == "skipped_not_entered\n"
    assert captured.err == ""
    if EVIDENCE_PATH.exists():
        EVIDENCE_PATH.unlink()


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
    assert captured.err == module.CLI_FAILURE_MESSAGE + "\n"


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
    assert captured.err == module.CONNECT_FAILURE_MESSAGE + "\n"


def test_cli_subprocess_default_skipped_with_sanitized_env() -> None:
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
    try:
        result = subprocess.run(
            [sys.executable, str(RUNNER_PATH)],
            cwd=str(REPO_ROOT),
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )
        assert result.returncode == 1
        assert result.stdout == "skipped_not_entered\n"
        assert result.stderr == ""
        assert EVIDENCE_PATH.exists()
        payload = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
        assert payload["status"] == "skipped_not_entered"
        assert payload["reason"] == "authorization_missing"
    finally:
        if EVIDENCE_PATH.exists():
            EVIDENCE_PATH.unlink()


# -- proof SQL orchestration (scripted connection, real engine) -------------


class _FakeCursor:
    """Records execute calls; scripts dict-row SELECT results in order."""

    def __init__(self, scripted: list[list[dict[str, object]]]) -> None:
        self.scripted = list(scripted)
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self._current: list[dict[str, object]] = []

    def execute(self, query: str, params: object = ()) -> None:
        if not isinstance(params, tuple):
            params = (params,)
        self.calls.append((query, params))
        if query.lstrip().startswith("SELECT"):
            self._current = self.scripted.pop(0)
        return None

    def fetchone(self) -> dict[str, object] | None:
        if not self._current:
            return None
        return self._current[0]

    def fetchall(self) -> list[dict[str, object]]:
        rows = list(self._current)
        self._current = []
        return rows


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor) -> None:
        self.closed = False
        self._cursor = cursor

    def cursor(self) -> _FakeCursor:
        return self._cursor

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        raise AssertionError("rollback must not be reached on the happy path")

    def close(self) -> None:
        self.closed = True


def _reader_row(module: Any, index: int) -> dict[str, object]:
    span_id = module._FIXTURE_SPAN_IDS[index]
    return {
        "mention_id": module._FIXTURE_MENTION_IDS[index],
        "span_id": span_id,
        "entity_id": module._FIXTURE_ENTITY_IDS[index],
        "char_start": 0,
        "char_end": 4,
        "mention_text": module._FIXTURE_MENTION_TEXT,
        "confidence": None,
        "source": "dictionary",
        "input_id": span_id,
        "input_kind": "corpus_span",
        "input_revision": module._FIXTURE_CONTENT_HASH,
        "extractor_id": "e2b-c2-fixture",
        "extractor_version": "1.0.0",
        "model_id": None,
        "model_revision": None,
        "artifact_digest": None,
        "schema_version": "1.0.0",
        "normalization_version": "1.0.0",
        "segmentation_version": "1.0.0",
        "label_map_digest": module._FIXTURE_LABEL_MAP_DIGEST,
        "runtime_compatibility_id": None,
        "segment_id": None,
        "raw_label": module._FIXTURE_MENTION_TEXT,
        "entity_type": module._FIXTURE_ENTITY_TYPE,
        "confidence_kind": "unavailable",
        "raw_text": module._FIXTURE_MENTION_TEXT,
        "doc_id": module._FIXTURE_DOCUMENT_ID,
        "version_id": module._FIXTURE_VERSION_ID,
        "canonical_name": module._FIXTURE_MENTION_TEXT,
    }


def _uuid_reader_row(module: Any, index: int) -> dict[str, object]:
    """Live-parity row: psycopg3 dict_row yields uuid.UUID for UUID columns.

    Every UUID column (span_id/segment_id/version_id/doc_id) is converted to
    a uuid.UUID instance exactly as the live dict_row cursor returns it; the
    remaining scalar columns stay str/int/None like the materialized corpus.
    """

    row = _reader_row(module, index)
    for key in ("span_id", "segment_id", "version_id", "doc_id"):
        value = row[key]
        row[key] = None if value is None else uuid.UUID(str(value))
    return row


def _fixture_cluster(module: Any) -> Any:
    """One deterministic C2 fixture cluster over both fixture spans."""

    return module.CorefCluster(
        cluster_id=module.deterministic_id(
            module.COREF_CLUSTER_ID_KIND,
            module.canonical_json(
                {
                    "coref_rules_version": module.COREF_RULES_VERSION,
                    "member_mention_ids": list(sorted(module._FIXTURE_SPAN_IDS)),
                    "version_id": module._FIXTURE_VERSION_ID,
                }
            ),
        ),
        version_id=module._FIXTURE_VERSION_ID,
        member_mention_ids=tuple(sorted(module._FIXTURE_SPAN_IDS)),
        tombstoned=False,
        provenance={},
    )


def test_resolution_reader_live_parity_uuid_columns() -> None:
    """FINDING A regression: dict_row yields uuid.UUID for UUID columns.

    The reader must normalize every UUID column value to its canonical
    str(uuid) form before constructing MentionCandidate/ResolutionDecision/
    ResolutionResult; otherwise the live gate fails closed with
    "input_id must be a Unicode scalar string".
    """

    module = _runner()
    segment_id = "c2e1d0c2-0000-4000-8000-0000c1c10009"

    def _row(index: int, *, as_uuid: bool) -> dict[str, object]:
        row = _reader_row(module, index)
        row["segment_id"] = segment_id
        if as_uuid:
            for key in ("span_id", "segment_id", "version_id", "doc_id"):
                row[key] = uuid.UUID(str(row[key]))
        return row

    str_result = module._read_resolved_mentions(
        _FakeConnection(
            _FakeCursor([[_row(0, as_uuid=False), _row(1, as_uuid=False)]])
        ),
        module._FIXTURE_OWNER_SCOPE,
    )
    uuid_result = module._read_resolved_mentions(
        _FakeConnection(_FakeCursor([[_row(0, as_uuid=True), _row(1, as_uuid=True)]])),
        module._FIXTURE_OWNER_SCOPE,
    )
    assert uuid_result == str_result
    for decision in uuid_result.resolved:
        candidate = decision.candidate
        assert type(candidate.input_id) is str
        assert type(candidate.span_id) is str
        assert type(candidate.segment_id) is str
        assert type(candidate.document_id) is str
        assert type(candidate.version_id) is str
        assert type(decision.entity_id) is str
    assert all(type(key[1]) is str for key in uuid_result.chosen_priority)


def test_verify_cluster_membership_live_parity_uuid_span_ids() -> None:
    """FINDING A flow: membership SELECT rows carry uuid.UUID span_id live."""

    module = _runner()
    cluster = _fixture_cluster(module)
    rows: list[dict[str, object]] = [
        {
            "mention_id": uuid.UUID(str(module._FIXTURE_MENTION_IDS[0])),
            "span_id": uuid.UUID(str(module._FIXTURE_SPAN_IDS[0])),
        },
        {
            "mention_id": uuid.UUID(str(module._FIXTURE_MENTION_IDS[1])),
            "span_id": uuid.UUID(str(module._FIXTURE_SPAN_IDS[1])),
        },
    ]
    connection = _FakeConnection(_FakeCursor([rows]))
    total = module._verify_cluster_membership(
        connection, module.CorefClusterSet(clusters=(cluster,))
    )
    assert total == 2


def test_verify_tombstone_state_live_parity_uuid_cluster_ids() -> None:
    """FINDING A flow: tombstone SELECT rows carry uuid.UUID cluster_id live."""

    module = _runner()
    cluster = _fixture_cluster(module)
    scripted: list[list[dict[str, object]]] = [
        [{"cluster_id": uuid.UUID(str(cluster.cluster_id)), "tombstoned": True}],
        [{"row_count": 2}],
    ]
    connection = _FakeConnection(_FakeCursor(scripted))
    membership = module._verify_tombstone_state(
        connection, module.CorefClusterSet(clusters=(cluster,))
    )
    assert membership == 2


def test_proof_steps_drive_exact_sql_sequence() -> None:
    module = _runner()
    expected_cluster_id = module.deterministic_id(
        module.COREF_CLUSTER_ID_KIND,
        module.canonical_json(
            {
                "coref_rules_version": module.COREF_RULES_VERSION,
                "member_mention_ids": list(sorted(module._FIXTURE_SPAN_IDS)),
                "version_id": module._FIXTURE_VERSION_ID,
            }
        ),
    )
    scripted: list[list[dict[str, object]]] = [
        [_reader_row(module, 0), _reader_row(module, 1)],
        [{"row_count": 0}],
        [{"row_count": 0}],
        [
            {
                "mention_id": module._FIXTURE_MENTION_IDS[0],
                "span_id": module._FIXTURE_SPAN_IDS[0],
            },
            {
                "mention_id": module._FIXTURE_MENTION_IDS[1],
                "span_id": module._FIXTURE_SPAN_IDS[1],
            },
        ],
        [{"cluster_id": expected_cluster_id, "tombstoned": True}],
        [{"row_count": 2}],
    ]
    cursor = _FakeCursor(scripted)
    connection = _FakeConnection(cursor)
    applied: list[tuple[object, object, tuple[str, ...]]] = []

    def _recording_applier(
        target: object, connection_factory: object, catalog: tuple[str, ...]
    ) -> None:
        applied.append((target, connection_factory, catalog))

    target = SimpleNamespace(dbname=_EXPECTED_DB_CANARY)
    proof = module._run_proof_steps(
        target,
        connection_factory=lambda t: connection,
        apply_catalog=_recording_applier,
    )
    assert proof == _valid_proof()
    assert connection.closed is True
    assert len(applied) == 1
    assert applied[0][2] == module.FULL_MIGRATION_CATALOG
    assert applied[0][2][-2:] == module._CATALOG_TAIL

    statements = [sql for sql, _ in cursor.calls]
    reader_index = next(
        i for i, sql in enumerate(statements) if sql.startswith("SELECT em.mention_id")
    )
    assert "WHERE em.e2b_owner_scope = %s" in statements[reader_index]
    assert cursor.calls[reader_index][1] == (module._FIXTURE_OWNER_SCOPE,)

    coref_inserts = [
        (sql, params)
        for sql, params in cursor.calls
        if sql.startswith("INSERT INTO coref_cluster")
    ]
    assert len(coref_inserts) == 3
    assert "ON CONFLICT" not in coref_inserts[0][0]
    assert "ON CONFLICT" not in coref_inserts[1][0]
    assert coref_inserts[0][1] == (
        expected_cluster_id,
        module._FIXTURE_VERSION_ID,
        "coref-rules-1",
        False,
    )
    assert (
        "SELECT %s, em.mention_id, %s FROM entity_mentions AS em" in coref_inserts[1][0]
    )
    assert coref_inserts[1][1][0] == expected_cluster_id
    assert coref_inserts[1][1][2] in module._FIXTURE_SPAN_IDS

    parity_index = next(
        i
        for i, sql in enumerate(statements)
        if sql == "SELECT count(*) AS row_count FROM coref_clusters"
    )
    first_coref_insert_index = statements.index(coref_inserts[0][0])
    assert parity_index < first_coref_insert_index

    tombstone_updates = [
        params
        for sql, params in cursor.calls
        if sql.startswith("UPDATE coref_clusters SET tombstoned")
    ]
    assert tombstone_updates == [(expected_cluster_id,)]

    entity_mention_inserts = [
        sql for sql in statements if sql.startswith("INSERT INTO entity_mentions")
    ]
    assert len(entity_mention_inserts) == 2
    assert "ON CONFLICT (mention_id) DO NOTHING" in entity_mention_inserts[0]
    merged = " ".join(statements)
    assert "entity_merge_log" not in merged
    assert "UPDATE entities" not in merged
    assert "UPDATE entity_mentions" not in merged


def test_proof_steps_fail_closed_on_default_off_violation() -> None:
    """The parity proof must see zero coref rows before any C2 DML."""
    module = _runner()
    scripted: list[list[dict[str, object]]] = [
        [_reader_row(module, 0), _reader_row(module, 1)],
        [{"row_count": 0}],
        [{"row_count": 1}],  # membership exists while resolver is off -> violation
    ]
    cursor = _FakeCursor(scripted)
    connection = _FakeConnection(cursor)

    def _noop_applier(
        target: object, connection_factory: object, catalog: tuple[str, ...]
    ) -> None:
        return None

    with pytest.raises(ValueError, match="default-off parity violated"):
        module._run_proof_steps(
            SimpleNamespace(dbname=_EXPECTED_DB_CANARY),
            connection_factory=lambda t: connection,
            apply_catalog=_noop_applier,
        )
    assert not any(
        sql.startswith("INSERT INTO coref_clusters") for sql, _ in cursor.calls
    )


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
    assert source.index("_entry_authorization") < source.rindex("evidence_writer(")
    assert source.index("_prove_c1_closed") < source.rindex("evidence_writer(")


def test_source_has_main_entry_guard() -> None:
    source = _runner_source()
    assert 'if __name__ == "__main__":' in source
    assert "raise SystemExit(_run_redacted_cli())" in source


def test_source_pins_keyword_only_public_gate_function() -> None:
    source = _runner_source()
    assert "def run_c2_entry_acceptance(" in source
    assert "C2EntryOutcome" in source
    assert "*," in source
    assert "target_uri" in source
    for required in (
        "target_parser",
        "connection_factory",
        "catalog",
        "apply_catalog",
        "resolution_reader",
        "proof_runner",
        "closure_prover",
        "evidence_writer",
        "evidence_path",
    ):
        assert required in source, f"public gate seam missing: {required}"
    for default in (
        "parse_disposable_postgresql_target",
        "FULL_MIGRATION_CATALOG",
        "_apply_catalog",
        "_read_resolved_mentions",
        "_run_proof_steps",
        "_prove_c1_closed",
        "_write_evidence",
        "EVIDENCE_PATH",
    ):
        assert default in source, f"public gate default missing: {default}"


def test_source_pins_dict_row_factory_and_fail_closed_statuses() -> None:
    """FINDING A/B pins: dict-row factory, fail-closed status and exit code."""
    source = _runner_source()
    assert "def _c2_connection_factory(" in source
    assert "row_factory" in source
    assert "dict_row" in source
    assert "executed_failed" in source
    assert "skipped_not_entered" in source
    assert "def _validate_proof_outcomes(" in source
    assert "FAILED_EXIT_CODE" in source
    assert "SKIPPED_EXIT_CODE" in source
    assert "def _entry_authorization(" in source


def test_source_pins_c1_closure_linkage_and_fixture_shape() -> None:
    source = _runner_source()
    assert _C1_HASH in source
    assert _C1_SUCCESS_NAME in source
    assert _C1_PLAIN_NAME in source
    assert "def _prove_c1_closed(" in source
    for marker in ("coref_clusters", "coref_cluster_mentions", "e2b_owner_scope"):
        assert marker in source, f"C2 schema marker missing: {marker}"


def test_source_never_describes_skipped_entry_as_tested() -> None:
    source = _runner_source()
    assert "R-OKF-09" not in source
    assert "def _run_proof_steps(" in source
    assert 'resolver_mode="off"' in source
    assert "resolver_mode=RULES_RESOLVER_MODE" in source
