"""FROZEN Phase 16-14 Task 1 RED contract for the E2b migration gate runner.

The future gate is loaded lazily so collection remains valid while its runner is
absent.

The contract pins real production database seams, an explicit keyword-only
target_uri supplied only by a programmatic harness, exact authorization-first
blocking, full-catalog application, migration-020 inventory, and one explicit 020
reapply. Idempotence means zero effective canonical structural snapshot changes;
it does not claim that migration 020 executes zero raw DDL statements. Evidence is
written last and is deterministic and redacted. No live database, Docker, network,
ModelScope, RaNER, or C2 access occurs in this RED selector.
"""

from __future__ import annotations

import hashlib
import inspect
import importlib.util
import json
import os
import subprocess
import sys
import types
from collections.abc import Mapping
from dataclasses import fields
from pathlib import Path
from typing import Callable

import psycopg
import pytest

from llamaindex_runtime.registry.migration_catalog import FULL_MIGRATION_CATALOG

REPO_ROOT = Path(__file__).resolve().parents[3]
VERIFICATION_DIR = REPO_ROOT / "verification" / "phase16-raw-corpus-entity-layer"
RUNNER_PATH = VERIFICATION_DIR / "run_e2b_migration_gate.py"
EVIDENCE_NAME = "e2b_migration_gate_evidence.md"
EVIDENCE_PATH = VERIFICATION_DIR / EVIDENCE_NAME

# The three gate-routing keys -- the ONLY environment allowlist the gate may touch.
AUTH_ENV = "OKF_E2B_MIGRATION_TEST_AUTHORIZED"
DISPOSABLE_ENV = "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE"
EXPECTED_DATABASE_ENV = "OKF_REBUILD_EXPECTED_DATABASE"
_GATE_ROUTING_KEYS = frozenset((AUTH_ENV, DISPOSABLE_ENV, EXPECTED_DATABASE_ENV))

# All twelve routing/authorization switches that must never leak into a gate
# process and must never be read by the gate.
_DATABASE_ROUTING_KEYS = frozenset(
    "DATABASE_URL FORMAL_RUNTIME_DATABASE_URL "
    "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE OKF_REBUILD_EXPECTED_DATABASE "
    "OKF_FAILURE_AUDIT_ACCEPTANCE OKF_REBUILD_DOCKER_ACCEPTANCE "
    "OKF_E2A_DISPOSABLE_TEST_AUTHORIZED OKF_E2B_DISPOSABLE_TEST_AUTHORIZED "
    "OKF_E2B_MIGRATION_TEST_AUTHORIZED OKF_E2B_MODELSCOPE_MIRROR_AUTHORIZED "
    "OKF_E2B_RANER_SMOKE_AUTHORIZED OKF_E2B_C2_ENTRY_AUTHORIZED".split()
)

_CLI_FAILURE_MESSAGE = "E2b migration gate refused; failure details are not disclosed"
_CONNECT_FAILURE_MESSAGE = "Database connection failed; refusing migration gate"
_EXPECTED_DB_CANARY = "okf_e2b_migration_disposable"
_DB_URL = f"postgresql://okf:secret@127.0.0.1:5432/{_EXPECTED_DB_CANARY}"

# The migration 020 contract (from 020_ner_entity_mentions.sql).
_PROVENANCE_COLUMNS = (
    "input_id",
    "input_kind",
    "input_revision",
    "extractor_id",
    "extractor_version",
    "model_id",
    "model_revision",
    "artifact_digest",
    "schema_version",
    "normalization_version",
    "segmentation_version",
    "label_map_digest",
    "runtime_compatibility_id",
    "document_char_start",
    "document_char_end",
    "segment_id",
    "raw_label",
    "entity_type",
    "confidence_kind",
    "e2b_owner_scope",
)
_E2B_CONSTRAINTS = (
    "chk_okf_e2b_mentions_input_kind",
    "chk_okf_e2b_mentions_confidence_kind",
    "chk_okf_e2b_mentions_artifact_digest",
    "chk_okf_e2b_mentions_label_map_digest",
    "chk_okf_e2b_mentions_document_coordinates",
    "chk_okf_e2b_mentions_owner_scope",
)
_E2B_INDEXES = (
    "idx_okf_e2b_failure_audit_occurred_at",
    "idx_okf_e2b_failure_audit_scope",
    "idx_okf_e2b_node_link_ownership_node",
    "idx_okf_e2b_node_link_ownership_version",
)
_OWNERSHIP_UNIQUE = "uq_okf_e2b_node_link_ownership"
_E2B_TABLES = ("okf_e2b_failure_audit", "okf_e2b_node_link_ownership")
_CATALOG_TAIL = ("021_ner_coref_clusters.sql", "022_keyword_fts_indexes.sql")


def _authorized_env() -> dict[str, str]:
    """Explicit authorized gate environment -- never derived from the ambient env."""
    return {
        DISPOSABLE_ENV: "1",
        EXPECTED_DATABASE_ENV: _EXPECTED_DB_CANARY,
        AUTH_ENV: "1",
    }


def _valid_inventory() -> dict[str, object]:
    return {
        "provenance_columns": _PROVENANCE_COLUMNS,
        "constraints": _E2B_CONSTRAINTS,
        "indexes": _E2B_INDEXES,
        "ownership_ledger_unique": _OWNERSHIP_UNIQUE,
        "ownership_ledger_unique_columns": ("node_id", "entity_id", "version_id"),
        "tables": _E2B_TABLES,
    }


def _valid_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "executed",
        "catalog_tail": _CATALOG_TAIL,
        "catalog_apply_count": 1,
        "idempotence_reapply_count": 1,
        "idempotence_ddl_count": 0,
        "provenance_column_count": len(_PROVENANCE_COLUMNS),
        "constraint_inventory": _E2B_CONSTRAINTS,
        "index_inventory": _E2B_INDEXES,
        "ownership_ledger_unique": _OWNERSHIP_UNIQUE,
        "ownership_ledger_unique_columns": ("node_id", "entity_id", "version_id"),
        "tables": _E2B_TABLES,
    }


def _runner() -> types.ModuleType:
    """Lazily load the runner; fail cleanly when the runner file is absent."""
    if not RUNNER_PATH.is_file():
        pytest.fail(f"RED: runner module absent: {RUNNER_PATH}")
    spec = importlib.util.spec_from_file_location(
        "run_e2b_migration_gate", str(RUNNER_PATH)
    )
    if spec is None or spec.loader is None:
        pytest.fail(f"RED: runner module unloadable: {RUNNER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _runner_source() -> str:
    if not RUNNER_PATH.is_file():
        pytest.fail(f"RED: runner source absent: {RUNNER_PATH}")
    return RUNNER_PATH.read_text(encoding="utf-8")


class _FakeConnection:
    """Connection fake tracking close/double-close without any backend."""

    def __init__(self, call_log: list[tuple[object, ...]], label: str) -> None:
        self.call_log = call_log
        self.label = label
        self.closed = False
        self.close_calls = 0

    def close(self) -> None:
        self.closed = True
        self.close_calls += 1
        self.call_log.append(("close", self.label))


class _RecordingEnviron(dict):
    """A dict that records every lookup and every enumeration/copy attempt."""

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


class _HostileTarget:
    """An object whose every read/str raises; proves the gate never touches it."""

    def __init__(self) -> None:
        self.touched: list[str] = []

    def __getattr__(self, name: str) -> object:
        self.touched.append(name)
        raise RuntimeError("hostile target accessed")

    def __str__(self) -> str:
        self.touched.append("__str__")
        raise RuntimeError("hostile target str")

    def __repr__(self) -> str:
        self.touched.append("__repr__")
        raise RuntimeError("hostile target repr")


class _FakeSeams:
    """Pure-fake seams driving the authorized gate path with recorded calls."""

    def __init__(
        self,
        *,
        catalog: tuple[str, ...] | None = None,
        inventory: dict[str, object] | None = None,
        snapshot_delta: tuple[str, ...] = (),
        close_in_snapshot: bool = False,
        apply_error: Exception | None = None,
    ) -> None:
        self.catalog = FULL_MIGRATION_CATALOG if catalog is None else catalog
        self.inventory = _valid_inventory() if inventory is None else inventory
        self.snapshot_delta = snapshot_delta
        self.close_in_snapshot = close_in_snapshot
        self.apply_error = apply_error
        self.call_log: list[tuple[object, ...]] = []
        for name in (
            "target_parser_calls",
            "connect_calls",
            "apply_calls",
            "inventory_calls",
            "snapshot_calls",
            "reapply_calls",
            "write_calls",
        ):
            setattr(self, name, [])
        self.opened: list[_FakeConnection] = []
        self.target: object = None

    def target_parser(self, target_uri: object, expected_database: object) -> object:
        self.target_parser_calls.append((target_uri, expected_database))
        self.target = types.SimpleNamespace(dbname=_EXPECTED_DB_CANARY)
        self.call_log.append(("parse",))
        return self.target

    def connection_factory(self, target: object) -> _FakeConnection:
        self.connect_calls.append(target)
        label = f"connection-{len(self.opened) + 1}"
        connection = _FakeConnection(self.call_log, label)
        self.opened.append(connection)
        self.call_log.append(("open", label))
        return connection

    def apply_catalog(
        self,
        target: object,
        connection_factory: Callable[[object], _FakeConnection],
        filenames: tuple[str, ...],
    ) -> None:
        self.apply_calls.append((target, connection_factory, filenames))
        self.call_log.append(("apply",))
        connection = connection_factory(target)
        if not connection.closed:
            connection.close()
        if self.apply_error is not None:
            raise self.apply_error

    def inventory_schema(self, connection: object) -> dict[str, object]:
        self.inventory_calls.append(connection)
        self.call_log.append(("inventory",))
        return self.inventory

    def snapshot_schema(self, connection: object) -> dict[str, object]:
        self.snapshot_calls.append(connection)
        ordinal = len(self.snapshot_calls)
        self.call_log.append(("snapshot", ordinal))
        if self.close_in_snapshot and not connection.closed:
            connection.close()
        if ordinal == 1:
            return {"objects": ("stable",)}
        return {"objects": ("stable", *self.snapshot_delta)}

    def reapply_020(self, connection: object) -> None:
        self.reapply_calls.append(connection)
        self.call_log.append(("reapply",))

    def evidence_writer(self, payload: object, path: Path) -> str:
        self.write_calls.append((payload, path))
        self.call_log.append(("evidence",))
        text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        path.write_text(text, encoding="utf-8")
        return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _run_gate(
    module: types.ModuleType,
    seams: _FakeSeams,
    *,
    target_uri: object = _DB_URL,
    env: Mapping[str, str] | None = None,
    evidence_path: Path = EVIDENCE_PATH,
) -> object:
    return module.run_migration_gate(
        _authorized_env() if env is None else env,
        target_uri=target_uri,
        target_parser=seams.target_parser,
        connection_factory=seams.connection_factory,
        catalog=seams.catalog,
        apply_catalog=seams.apply_catalog,
        inventory_schema=seams.inventory_schema,
        snapshot_schema=seams.snapshot_schema,
        reapply_020=seams.reapply_020,
        evidence_writer=seams.evidence_writer,
        evidence_path=evidence_path,
    )


_CATALOG_MUTATORS: dict[str, Callable[[], tuple[str, ...]]] = {
    "swapped-020-021": lambda: tuple(
        [
            *FULL_MIGRATION_CATALOG[:-2],
            FULL_MIGRATION_CATALOG[-1],
            FULL_MIGRATION_CATALOG[-2],
        ]
    ),
    "duplicate-021": lambda: FULL_MIGRATION_CATALOG + ("021_ner_coref_clusters.sql",),
    "missing-021": lambda: FULL_MIGRATION_CATALOG[:-1],
    "missing-020-before-021": lambda: FULL_MIGRATION_CATALOG[:-2]
    + (FULL_MIGRATION_CATALOG[-1],),
    "missing-001-head": lambda: FULL_MIGRATION_CATALOG[1:],
}

_INVENTORY_MUTATORS: dict[str, Callable[[dict[str, object]], dict[str, object]]] = {
    "missing-provenance-column": lambda inv: {
        **inv,
        "provenance_columns": inv["provenance_columns"][1:],
    },
    "missing-constraint": lambda inv: {**inv, "constraints": inv["constraints"][1:]},
    "missing-index": lambda inv: {**inv, "indexes": inv["indexes"][1:]},
    "wrong-ownership-unique": lambda inv: {
        **inv,
        "ownership_ledger_unique": "uq_wrong",
    },
    "wrong-ownership-unique-columns": lambda inv: {
        **inv,
        "ownership_ledger_unique_columns": ("entity_id", "node_id", "version_id"),
    },
    "missing-table": lambda inv: {**inv, "tables": inv["tables"][:1]},
    "unknown-field": lambda inv: {
        **inv,
        "target": "postgresql://okf:secret@127.0.0.1:5432/prod",
    },
}

_MISSING = object()


def test_production_db_prerequisites_are_real() -> None:
    from scripts._rebuild_database_connection import (
        parse_disposable_postgresql_target,
        runtime_connection_factory,
    )
    from llamaindex_runtime.okf.e2a_disposable_execution import _apply_catalog

    assert callable(parse_disposable_postgresql_target)
    assert callable(runtime_connection_factory)
    assert callable(_apply_catalog)
    target = parse_disposable_postgresql_target(_DB_URL, _EXPECTED_DB_CANARY)
    assert target.dbname == _EXPECTED_DB_CANARY
    assert FULL_MIGRATION_CATALOG[-2:] == _CATALOG_TAIL
    assert FULL_MIGRATION_CATALOG[-2] == "021_ner_coref_clusters.sql"
    assert FULL_MIGRATION_CATALOG[-1] == "022_keyword_fts_indexes.sql"
    assert FULL_MIGRATION_CATALOG.count("022_keyword_fts_indexes.sql") == 1
    assert FULL_MIGRATION_CATALOG[-3] != "022_keyword_fts_indexes.sql"


def test_runner_defaults_are_exact_production_symbols() -> None:
    from scripts._rebuild_database_connection import (
        parse_disposable_postgresql_target,
        runtime_connection_factory,
    )
    from llamaindex_runtime.okf.e2a_disposable_execution import _apply_catalog

    module = _runner()
    signature = inspect.signature(module.run_migration_gate)
    target_uri = signature.parameters["target_uri"]
    assert target_uri.kind is inspect.Parameter.KEYWORD_ONLY
    assert target_uri.default is None
    assert (
        signature.parameters["target_parser"].default
        is parse_disposable_postgresql_target
    )
    assert (
        signature.parameters["connection_factory"].default is runtime_connection_factory
    )
    assert signature.parameters["catalog"].default is FULL_MIGRATION_CATALOG
    assert signature.parameters["apply_catalog"].default is _apply_catalog
    assert signature.parameters["inventory_schema"].default is module._inventory_020
    assert signature.parameters["snapshot_schema"].default is module._snapshot_020
    assert signature.parameters["reapply_020"].default is module._reapply_020
    assert signature.parameters["evidence_writer"].default is module._write_evidence
    assert signature.parameters["evidence_path"].default is module.EVIDENCE_PATH
    main_signature = inspect.signature(module.main)
    main_target_uri = main_signature.parameters["target_uri"]
    assert main_target_uri.kind is inspect.Parameter.KEYWORD_ONLY
    assert main_target_uri.default is None
    assert [field.name for field in fields(module.GateOutcome)] == [
        "status",
        "catalog_tail",
        "catalog_apply_count",
        "idempotence_reapply_count",
        "idempotence_ddl_count",
        "inventory",
        "evidence_sha256",
    ]


def test_runner_module_must_exist_for_lazy_load() -> None:
    assert RUNNER_PATH.is_file(), f"RED: runner module absent: {RUNNER_PATH}"


def test_runner_constants_pin_gate_contract() -> None:
    module = _runner()
    assert module.AUTH_ENV == AUTH_ENV
    assert module.DISPOSABLE_ENV == DISPOSABLE_ENV
    assert module.EXPECTED_DATABASE_ENV == EXPECTED_DATABASE_ENV
    assert module.BLOCKED_STATUS == "blocked_not_executed"
    assert module.EVIDENCE_NAME == EVIDENCE_NAME
    assert module.CLI_FAILURE_MESSAGE == _CLI_FAILURE_MESSAGE
    assert module.CONNECT_FAILURE_MESSAGE == _CONNECT_FAILURE_MESSAGE
    assert module.GATE_ROUTING_KEYS == _GATE_ROUTING_KEYS


@pytest.mark.parametrize(
    ("key", "value"),
    (
        (DISPOSABLE_ENV, "0"),
        (DISPOSABLE_ENV, "yes"),
        (DISPOSABLE_ENV, ""),
        (DISPOSABLE_ENV, " 1 "),
        (DISPOSABLE_ENV, "01"),
        (AUTH_ENV, "0"),
        (AUTH_ENV, "true"),
        (AUTH_ENV, " 1 "),
        (AUTH_ENV, "01"),
        (AUTH_ENV, "2"),
        (EXPECTED_DATABASE_ENV, ""),
        (EXPECTED_DATABASE_ENV, _MISSING),
    ),
)
def test_main_blocked_on_partial_or_malformed_authorization(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    key: str,
    value: object,
) -> None:
    module = _runner()
    env = _authorized_env()
    if value is _MISSING:
        del env[key]
    else:
        env[key] = value  # type: ignore[index]
    monkeypatch.setattr(os, "environ", env)
    assert module.main() == 1
    captured = capsys.readouterr()
    assert captured.out == "blocked_not_executed\n"
    assert captured.out == f"{module.BLOCKED_STATUS}\n"
    assert captured.err == ""


def test_blocked_main_reads_only_gate_routing_keys(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _runner()
    fake = _RecordingEnviron(
        {"DATABASE_URL": "postgresql://okf:secret@127.0.0.1:5432/prod_db"}
    )
    monkeypatch.setattr(os, "environ", fake)
    assert module.main() == 1
    assert capsys.readouterr().out == "blocked_not_executed\n"
    assert set(fake.get_calls) <= _GATE_ROUTING_KEYS
    assert "DATABASE_URL" not in fake.get_calls
    assert fake.enumeration_calls == []


def test_blocked_main_zero_parser_connect_and_orchestration_attempt(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _runner()
    monkeypatch.setattr(os, "environ", {})
    connect_calls: list[object] = []
    monkeypatch.setattr(psycopg, "connect", lambda *a, **k: connect_calls.append(a))
    gate_calls: list[object] = []
    monkeypatch.setattr(
        module, "run_migration_gate", lambda *a, **k: gate_calls.append((a, k))
    )
    parser_calls: list[object] = []
    monkeypatch.setattr(
        module,
        "parse_disposable_postgresql_target",
        lambda *a, **k: parser_calls.append((a, k)),
    )
    assert not EVIDENCE_PATH.exists()
    assert module.main() == 1
    assert not EVIDENCE_PATH.exists()
    assert parser_calls == [] and connect_calls == [] and gate_calls == []
    assert capsys.readouterr().out == "blocked_not_executed\n"


def test_run_migration_gate_unauthorized_returns_before_parsing_hostile_target(
    tmp_path: Path,
) -> None:
    module = _runner()
    seams = _FakeSeams()
    hostile = _HostileTarget()
    evidence_path = tmp_path / EVIDENCE_NAME
    outcome = _run_gate(
        module, seams, env={}, target_uri=hostile, evidence_path=evidence_path
    )
    assert isinstance(outcome, module.GateOutcome)
    assert outcome.status == "blocked_not_executed"
    assert outcome.catalog_tail == ()
    assert outcome.catalog_apply_count == 0
    assert outcome.idempotence_reapply_count == 0
    assert outcome.idempotence_ddl_count == 0
    assert outcome.inventory == {}
    assert outcome.evidence_sha256 == ""
    assert hostile.touched == []
    for name in (
        "target_parser_calls",
        "connect_calls",
        "apply_calls",
        "inventory_calls",
        "snapshot_calls",
        "reapply_calls",
        "write_calls",
    ):
        assert getattr(seams, name) == []
    assert seams.opened == []
    assert not evidence_path.exists()


def test_main_forwards_only_keyword_programmatic_target_after_authorization(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _runner()
    environ = _authorized_env()
    sentinel = object()
    calls: list[tuple[object, dict[str, object]]] = []
    fake_outcome = module.GateOutcome(
        status="executed",
        catalog_tail=_CATALOG_TAIL,
        catalog_apply_count=1,
        idempotence_reapply_count=1,
        idempotence_ddl_count=0,
        inventory=_valid_inventory(),
        evidence_sha256="0" * 64,
    )

    def _fake_gate(environ_arg: object, **kwargs: object) -> module.GateOutcome:
        calls.append((environ_arg, kwargs))
        return fake_outcome

    monkeypatch.setattr(module, "run_migration_gate", _fake_gate)
    monkeypatch.setattr(os, "environ", environ)
    assert module.main(target_uri=sentinel) == 0
    captured = capsys.readouterr()
    assert captured.out == "executed\n"
    assert captured.err == ""
    assert len(calls) == 1
    assert calls[0][0] is environ
    assert calls[0][1]["target_uri"] is sentinel


def test_main_rejects_target_uri_in_argv_before_gate(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _runner()
    gate_calls: list[object] = []
    monkeypatch.setattr(
        module, "run_migration_gate", lambda *a, **k: gate_calls.append((a, k))
    )
    monkeypatch.setattr(os, "environ", _authorized_env())
    with pytest.raises(ValueError):
        module.main([_DB_URL], target_uri=None)
    assert gate_calls == []


def test_require_gate_authorization_reads_only_allowlist() -> None:
    module = _runner()
    fake = _RecordingEnviron(_authorized_env())
    fake["DATABASE_URL"] = "postgresql://okf:secret@127.0.0.1:5432/other_db"
    fake["OKF_E2B_C2_ENTRY_AUTHORIZED"] = "1"
    module._require_gate_authorization(fake)  # must not raise
    assert set(fake.get_calls) == _GATE_ROUTING_KEYS
    assert "DATABASE_URL" not in fake.get_calls
    assert fake.enumeration_calls == []


@pytest.mark.parametrize("key", (DISPOSABLE_ENV, AUTH_ENV))
@pytest.mark.parametrize("value", ("0", "yes", "", " 1 ", "true", "01", "2"))
def test_guard_requires_exact_value(key: str, value: str) -> None:
    module = _runner()
    env = _authorized_env()
    env[key] = value
    with pytest.raises(ValueError, match=f"{key}=1"):
        module._require_gate_authorization(env)


@pytest.mark.parametrize("value", ("", _MISSING))
def test_guard_requires_nonempty_expected_database(value: object) -> None:
    module = _runner()
    env = _authorized_env()
    if value is _MISSING:
        del env[EXPECTED_DATABASE_ENV]
    else:
        env[EXPECTED_DATABASE_ENV] = value  # type: ignore[index]
    with pytest.raises(ValueError, match="OKF_REBUILD_EXPECTED_DATABASE"):
        module._require_gate_authorization(env)


def test_verify_catalog_tail_accepts_root_catalog() -> None:
    module = _runner()
    module._verify_catalog_tail(FULL_MIGRATION_CATALOG)
    assert FULL_MIGRATION_CATALOG[0] == "001_initial.sql"
    assert FULL_MIGRATION_CATALOG[-2:] == _CATALOG_TAIL


@pytest.mark.parametrize("mutation_name", sorted(_CATALOG_MUTATORS))
def test_verify_catalog_tail_rejects_invalid(mutation_name: str) -> None:
    module = _runner()
    with pytest.raises(ValueError):
        module._verify_catalog_tail(_CATALOG_MUTATORS[mutation_name]())


@pytest.mark.parametrize("mutation_name", sorted(_CATALOG_MUTATORS))
def test_run_migration_gate_wrong_catalog_fails_before_connection(
    tmp_path: Path, mutation_name: str
) -> None:
    module = _runner()
    seams = _FakeSeams(catalog=_CATALOG_MUTATORS[mutation_name]())
    with pytest.raises(ValueError):
        _run_gate(module, seams, evidence_path=tmp_path / "evidence.md")
    assert seams.opened == []


def test_run_migration_gate_full_authorized_path_with_pure_fakes(
    tmp_path: Path,
) -> None:
    module = _runner()
    seams = _FakeSeams()
    evidence_path = tmp_path / EVIDENCE_NAME
    outcome = _run_gate(module, seams, target_uri=_DB_URL, evidence_path=evidence_path)

    assert seams.target_parser_calls == [(_DB_URL, _EXPECTED_DB_CANARY)]
    assert len(seams.connect_calls) == 2
    assert len(seams.opened) == 2
    catalog_connection = seams.opened[0]
    inventory_connection = seams.opened[1]
    assert catalog_connection is not inventory_connection
    target = seams.target
    assert seams.apply_calls == [
        (target, seams.connection_factory, FULL_MIGRATION_CATALOG)
    ]
    assert seams.inventory_calls == [inventory_connection]
    assert seams.snapshot_calls == [inventory_connection, inventory_connection]
    assert seams.reapply_calls == [inventory_connection]
    assert len(seams.write_calls) == 1
    assert seams.write_calls[0][1] is evidence_path
    assert catalog_connection.closed is True
    assert catalog_connection.close_calls == 1
    assert inventory_connection.closed is True
    assert inventory_connection.close_calls == 1
    assert seams.call_log == [
        ("parse",),
        ("apply",),
        ("open", "connection-1"),
        ("close", "connection-1"),
        ("open", "connection-2"),
        ("inventory",),
        ("snapshot", 1),
        ("reapply",),
        ("snapshot", 2),
        ("close", "connection-2"),
        ("evidence",),
    ]
    assert isinstance(outcome, module.GateOutcome)
    assert outcome.status == "executed"
    assert outcome.catalog_tail == _CATALOG_TAIL
    assert outcome.catalog_apply_count == 1
    assert outcome.idempotence_reapply_count == 1
    assert outcome.idempotence_ddl_count == 0
    assert outcome.inventory == _valid_inventory()
    assert (
        outcome.evidence_sha256
        == hashlib.sha256(
            evidence_path.read_text(encoding="utf-8").encode("utf-8")
        ).hexdigest()
    )
    payload = seams.write_calls[0][0]
    assert isinstance(payload, Mapping)
    assert payload["catalog_tail"] == _CATALOG_TAIL
    for forbidden in ("postgresql://", "127.0.0.1", "secret", _EXPECTED_DB_CANARY):
        assert forbidden not in json.dumps(payload, sort_keys=True)
        assert forbidden not in evidence_path.read_text(encoding="utf-8")


def test_run_migration_gate_reads_only_gate_routing_keys(tmp_path: Path) -> None:
    module = _runner()
    fake = _RecordingEnviron(_authorized_env())
    fake["DATABASE_URL"] = "postgresql://okf:secret@127.0.0.1:5432/prod"
    fake["FORMAL_RUNTIME_DATABASE_URL"] = "postgresql://okf:secret@127.0.0.1:5432/prod2"
    seams = _FakeSeams()
    _run_gate(module, seams, env=fake, evidence_path=tmp_path / "evidence.md")
    assert set(fake.get_calls) == _GATE_ROUTING_KEYS
    assert "DATABASE_URL" not in fake.get_calls
    assert "FORMAL_RUNTIME_DATABASE_URL" not in fake.get_calls
    assert fake.enumeration_calls == []


def test_run_migration_gate_evidence_write_is_deterministic(tmp_path: Path) -> None:
    module = _runner()
    outputs: list[tuple[bytes, object]] = []
    for index in range(2):
        seams = _FakeSeams()
        evidence_path = tmp_path / f"evidence_{index}.md"
        _run_gate(module, seams, evidence_path=evidence_path)
        outputs.append((evidence_path.read_bytes(), seams.write_calls[0][0]))
    assert outputs[0][0] == outputs[1][0]
    assert outputs[0][1] == outputs[1][1]


@pytest.mark.parametrize("mutation_name", sorted(_INVENTORY_MUTATORS))
def test_run_migration_gate_rejects_invalid_020_inventory(
    tmp_path: Path, mutation_name: str
) -> None:
    module = _runner()
    seams = _FakeSeams(inventory=_INVENTORY_MUTATORS[mutation_name](_valid_inventory()))
    evidence_path = tmp_path / "evidence.md"
    with pytest.raises(ValueError):
        _run_gate(module, seams, evidence_path=evidence_path)
    assert len(seams.opened) == 2
    assert seams.opened[0].close_calls == 1
    assert seams.opened[1].close_calls == 1
    assert seams.write_calls == []
    assert not evidence_path.exists()


def test_validate_020_inventory_accepts_valid_and_rejects_unknown() -> None:
    module = _runner()
    module._validate_020_inventory(_valid_inventory())
    inventory = _valid_inventory()
    inventory["connection_string"] = "postgresql://okf:secret@127.0.0.1:5432/prod"
    with pytest.raises(ValueError, match="unknown"):
        module._validate_020_inventory(inventory)


@pytest.mark.parametrize(
    "bad_key", ("target", "connection_string", "host", "credential", "database_url")
)
def test_redact_evidence_payload_rejects_unknown_fields(bad_key: str) -> None:
    module = _runner()
    raw = _valid_payload()
    raw[bad_key] = "postgresql://okf:secret@127.0.0.1:5432/prod"
    with pytest.raises(ValueError, match="unknown"):
        module._redact_evidence_payload(raw)


def test_redact_evidence_payload_canonical_and_redacted() -> None:
    module = _runner()
    payload = module._redact_evidence_payload(_valid_payload())
    assert payload["catalog_tail"] == _CATALOG_TAIL
    assert payload["provenance_column_count"] == len(_PROVENANCE_COLUMNS)
    assert tuple(payload["constraint_inventory"]) == _E2B_CONSTRAINTS
    assert tuple(payload["index_inventory"]) == _E2B_INDEXES
    assert payload["ownership_ledger_unique"] == _OWNERSHIP_UNIQUE
    assert tuple(payload["ownership_ledger_unique_columns"]) == (
        "node_id",
        "entity_id",
        "version_id",
    )
    assert payload["idempotence_ddl_count"] == 0
    serialized = json.dumps(payload, sort_keys=True)
    for forbidden in ("postgresql://", "127.0.0.1", "secret", _EXPECTED_DB_CANARY):
        assert forbidden not in serialized


def test_run_migration_gate_snapshot_inequality_fails(tmp_path: Path) -> None:
    module = _runner()
    seams = _FakeSeams(snapshot_delta=("changed",))
    evidence_path = tmp_path / "evidence.md"
    with pytest.raises(ValueError, match="idempotence"):
        _run_gate(module, seams, evidence_path=evidence_path)
    assert len(seams.opened) == 2
    assert seams.opened[0].close_calls == 1
    assert seams.opened[1].close_calls == 1
    assert seams.write_calls == []
    assert not evidence_path.exists()


def test_run_migration_gate_closes_connection_when_apply_raises(tmp_path: Path) -> None:
    module = _runner()
    seams = _FakeSeams(apply_error=ValueError("apply exploded"))
    evidence_path = tmp_path / "evidence.md"
    with pytest.raises(ValueError, match="apply exploded"):
        _run_gate(module, seams, evidence_path=evidence_path)
    assert len(seams.opened) == 1
    assert seams.opened[0].close_calls == 1
    assert seams.write_calls == []
    assert not evidence_path.exists()


def test_run_migration_gate_never_double_closes_already_closed_connection(
    tmp_path: Path,
) -> None:
    module = _runner()
    seams = _FakeSeams(close_in_snapshot=True)
    _run_gate(module, seams, evidence_path=tmp_path / "evidence.md")
    assert len(seams.opened) == 2
    assert seams.opened[0].close_calls == 1
    assert seams.opened[1].close_calls == 1


def test_run_redacted_cli_blocked_returns_nonzero_with_exact_stdout(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _runner()
    monkeypatch.setattr(os, "environ", {})
    assert module._run_redacted_cli([]) == 1
    captured = capsys.readouterr()
    assert captured.out == "blocked_not_executed\n"
    assert captured.err == ""


def test_run_redacted_cli_maps_value_error_to_fixed_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _runner()
    monkeypatch.setattr(os, "environ", dict(_authorized_env()))
    assert not EVIDENCE_PATH.exists()
    code = module._run_redacted_cli([])
    captured = capsys.readouterr()
    assert code == 2 and captured.out == ""
    assert captured.err.strip() == module.CLI_FAILURE_MESSAGE
    for forbidden in (
        "not configured",
        "postgresql://",
        "secret",
        "127.0.0.1",
        _EXPECTED_DB_CANARY,
    ):
        assert forbidden not in captured.err
    assert not EVIDENCE_PATH.exists()


def test_run_redacted_cli_maps_psycopg_error_to_fixed_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _runner()

    def _failing_main(*_a: object, **_k: object) -> int:
        raise psycopg.OperationalError("synthetic connection failure")

    monkeypatch.setattr(module, "main", _failing_main)
    code = module._run_redacted_cli([])
    captured = capsys.readouterr()
    assert code == 2 and captured.out == ""
    assert captured.err.strip() == module.CONNECT_FAILURE_MESSAGE
    assert "synthetic" not in captured.err


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
    assert result.stdout == "blocked_not_executed\n" and result.stderr == ""
    assert not EVIDENCE_PATH.exists()


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
        assert forbidden not in source


def test_source_evidence_writes_only_after_authorization() -> None:
    source = _runner_source()
    # The real default evidence writer is one runner-local function; the
    # orchestration body must delegate to the injected evidence_writer seam.
    assert source.count("def _write_evidence(") == 1
    assert source.count(".write_text(") <= 1
    for forbidden in (".write_bytes(", ".open(", "os.makedirs"):
        assert forbidden not in source, f"direct evidence writer forbidden: {forbidden}"
    assert "evidence_writer(" in source, "injected evidence-writer seam must exist"
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
    assert "def run_migration_gate(" in source
    assert "GateOutcome" in source
    assert "*," in source, "keyword-only target is required"
    assert "target_uri" in source, "explicit programmatic raw target is required"
    for required in (
        "target_parser=",
        "connection_factory=",
        "catalog=",
        "apply_catalog=",
        "inventory_schema=",
        "snapshot_schema=",
        "reapply_020=",
        "evidence_writer=",
        "evidence_path=",
    ):
        assert required in source, f"public gate seam missing: {required}"


def test_source_pins_020_inventory_and_idempotence_snapshot() -> None:
    source = _runner_source()
    for column in _PROVENANCE_COLUMNS:
        assert column in source, f"020 provenance column missing: {column}"
    for constraint in _E2B_CONSTRAINTS:
        assert constraint in source, f"020 constraint missing: {constraint}"
    for index in _E2B_INDEXES:
        assert index in source, f"020 index missing: {index}"
    for table in _E2B_TABLES:
        assert table in source, f"020 table missing: {table}"
    assert _OWNERSHIP_UNIQUE in source
    assert "(node_id, entity_id, version_id)" in source
    for marker in ("pg_constraint", "pg_index", "pg_attribute", "current_schema()"):
        assert marker in source, f"inventory SQL marker missing: {marker}"
    for marker in ("snapshot", "reapply_020", "idempotence"):
        assert marker in source, f"idempotence marker missing: {marker}"
