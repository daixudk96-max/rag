"""E2b runner default seams, injection surface, and fail-closed branches (Phase 16-11).

Companion to the frozen ``test_rebuild_from_okf_e2b_cli.py``. Adds non-live
coverage for the keyword-only injection surface on ``rebuild_bundle`` (defaults
remain the fail-closed seam builders), the ``_rebuild_one`` connection
lifecycle (primary closed in a finally, never double-closed, never
committed/rolled back, no runner SQL), the fixed redacted CLI error output
(never ``str(exc)``, deterministic exit code), and fail-closed branches for
connection-factory authorization, outcome redaction/formatting, default seams,
bundle admission, and CLI surfaces. No live database/model/network access.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import os
import subprocess
import sys
import types
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from llamaindex_runtime.entity.materialization_repository import (
    E2bDesiredState,
    E2bDmlRecorder,
    E2bDocumentScope,
    E2bMaterializationRepository,
    E2bReconciliationResult,
)
from llamaindex_runtime.okf.parser import OKFParser

from ._rebuild_cli_testkit import make_bundle

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "rebuild_from_okf_e2b.py"
DOC_ID = "00000000-0000-0000-0000-000000000001"
VERSION_ID = "00000000-0000-0000-0000-000000000003"
_SHA64 = "a" * 64
_GUARDED_REBUILD_ENV: Mapping[str, str] = {
    "RAG_ENTITY_EXTRACTOR": "raner",
    "DATABASE_URL": "postgresql://okf:secret@127.0.0.1:5432/okf_task34",
    "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE": "1",
    "OKF_REBUILD_EXPECTED_DATABASE": "okf_task34",
    "OKF_E2B_DISPOSABLE_TEST_AUTHORIZED": "1",
}
_DATABASE_ROUTING_KEYS = frozenset(
    "DATABASE_URL FORMAL_RUNTIME_DATABASE_URL "
    "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE OKF_REBUILD_EXPECTED_DATABASE "
    "OKF_FAILURE_AUDIT_ACCEPTANCE OKF_REBUILD_DOCKER_ACCEPTANCE "
    "OKF_E2A_DISPOSABLE_TEST_AUTHORIZED OKF_E2B_DISPOSABLE_TEST_AUTHORIZED "
    "OKF_E2B_MIGRATION_TEST_AUTHORIZED OKF_E2B_MODELSCOPE_MIRROR_AUTHORIZED "
    "OKF_E2B_RANER_SMOKE_AUTHORIZED OKF_E2B_C2_ENTRY_AUTHORIZED".split()
)
_RepoCall = tuple[Any, E2bDocumentScope, E2bDesiredState, E2bDmlRecorder]


def _load_runner_module() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(
        "rebuild_from_okf_e2b_default_seams", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _verify_args(bundle: Path) -> list[str]:
    """Return deterministic ``--verify-roundtrip`` CLI arguments for a bundle."""
    return [
        "--bundle",
        str(bundle),
        "--verify-roundtrip",
        "--fixture",
        "sectioned-pdf",
    ]


class _SpyCursor:
    def __init__(self, connection: "_FakeConnection") -> None:
        self._connection = connection
        self.executed: list[tuple[str, object | None]] = []

    @property
    def connection(self) -> "_FakeConnection":
        return self._connection

    def execute(self, statement: str, parameters: object | None = None) -> None:
        self.executed.append((statement, parameters))


class _FakeConnection:
    """Connection fake tracking close/commit/rollback without any backend."""

    def __init__(self) -> None:
        self.autocommit = False
        self.closed = False
        self.close_calls = 0
        self.commits = 0
        self.rollbacks = 0
        self._cursor = _SpyCursor(self)

    def cursor(self) -> _SpyCursor:
        return self._cursor

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True
        self.close_calls += 1


class _FakeRepository:
    """Pure repository fake recording reconciliation, optionally failing/closing."""

    def __init__(self, failure_audit_connection_factory: object) -> None:
        self.failure_audit_connection_factory = failure_audit_connection_factory
        self.calls: list[_RepoCall] = []
        self.error: Exception | None = None
        self.close_connection = False

    def reconcile_document(
        self,
        cursor: Any,
        scope: E2bDocumentScope,
        *,
        desired: E2bDesiredState,
        recorder: E2bDmlRecorder,
    ) -> E2bReconciliationResult:
        self.calls.append((cursor, scope, desired, recorder))
        if self.close_connection:
            cursor.connection.close()
        if self.error is not None:
            raise self.error
        return E2bReconciliationResult(
            outcome="no_op", primary_dml_by_table={}, stale_deletion_counts={}
        )


def test_rebuild_bundle_explicit_injection_drives_deterministic_orchestration(
    tmp_path: Path,
) -> None:
    module = _load_runner_module()
    bundle = make_bundle(tmp_path, "sectioned-pdf")
    extractor_inputs: list[list[object]] = []
    desired_calls: list[tuple[str, str, tuple[object, ...]]] = []
    opened_connections: list[_FakeConnection] = []
    failure_audit_factories: list[object] = []
    repositories: list[_FakeRepository] = []

    def _connection_factory() -> _FakeConnection:
        connection = _FakeConnection()
        opened_connections.append(connection)
        return connection

    class _RecordingExtractor:
        def extract(self, inputs: object) -> list[object]:
            extractor_inputs.append(list(inputs))  # type: ignore[arg-type]
            return [types.SimpleNamespace(candidate="candidate")]

    def _corpus_input_factory(document: object) -> list[object]:
        return [f"corpus-{document.doc_id}"]  # type: ignore[attr-defined]

    def _desired_state_factory(document: object, candidates: object) -> E2bDesiredState:
        desired_calls.append(
            (
                document.doc_id,  # type: ignore[attr-defined]
                document.version_id,  # type: ignore[attr-defined]
                tuple(candidates),  # type: ignore[arg-type]
            )
        )
        return E2bDesiredState()

    def _repository_factory(
        failure_audit_connection_factory: object,
    ) -> _FakeRepository:
        # The runner passes the primary connection factory as the failure-audit
        # factory (frozen seam wiring); record it for the fresh-factory proof.
        failure_audit_factories.append(failure_audit_connection_factory)
        repository = _FakeRepository(failure_audit_connection_factory)
        repositories.append(repository)
        return repository

    outcome = module.rebuild_bundle(
        bundle,
        environ=dict(_GUARDED_REBUILD_ENV),
        connection_factory=_connection_factory,
        repository_factory=_repository_factory,
        extractor_factory=lambda: _RecordingExtractor(),
        corpus_input_factory=_corpus_input_factory,
        desired_state_factory=_desired_state_factory,
    )

    assert len(repositories) == 1
    scope = repositories[0].calls[0][1]
    assert (scope.document_id, scope.version_id) == (DOC_ID, VERSION_ID)
    assert extractor_inputs == [[f"corpus-{DOC_ID}"]]
    assert desired_calls == [
        (DOC_ID, VERSION_ID, (types.SimpleNamespace(candidate="candidate"),))
    ]
    # Snapshot primaries first so audit-created connections stay separate.
    primary_connections = list(opened_connections)
    assert len(primary_connections) == 1
    audit_connections: list[_FakeConnection] = []
    for factory in failure_audit_factories:
        assert callable(factory)
        fresh = factory()  # type: ignore[operator]
        assert type(fresh) is _FakeConnection
        assert fresh not in primary_connections
        audit_connections.append(fresh)
    assert len(audit_connections) == 1
    assert isinstance(outcome, module._E2bRebuildOutcome)
    assert outcome.outcome == "no_op"
    assert outcome.primary_dml_by_table == {}
    assert outcome.post_rollback_failure_audit_outcome is None

    # Runner owns the primary connection: closes once, never commits/rolls back,
    # never executes SQL. Fresh failure-audit connections are never closed.
    primary = primary_connections[0]
    assert primary.close_calls == 1
    assert primary.commits == 0
    assert primary.rollbacks == 0
    assert primary.cursor().executed == []
    assert audit_connections[0].close_calls == 0


def test_rebuild_bundle_defaults_remain_fail_closed_before_any_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without injection, rebuild_bundle still uses the fail-closed seams."""
    module = _load_runner_module()
    bundle = make_bundle(tmp_path, "sectioned-pdf")
    connect_calls: list[object] = []

    monkeypatch.setattr(
        module.psycopg,
        "connect",
        lambda *_a, **_k: connect_calls.append("connect"),
    )

    with pytest.raises(ValueError, match="not configured"):
        module.rebuild_bundle(bundle, environ=dict(_GUARDED_REBUILD_ENV))

    assert connect_calls == []


@pytest.mark.parametrize(
    ("factory_name", "args"),
    (
        ("_build_e2b_extractor_factory", ()),
        ("_build_e2b_corpus_input_factory", (object(),)),
        ("_build_e2b_desired_state_factory", (object(), object())),
    ),
)
def test_default_pipeline_factories_fail_closed(
    factory_name: str, args: tuple[object, ...]
) -> None:
    module = _load_runner_module()
    factory = getattr(module, factory_name)()
    with pytest.raises(ValueError, match="not configured"):
        factory(*args)


def test_default_repository_factory_builds_real_repository() -> None:
    module = _load_runner_module()
    factory = module._build_e2b_repository_factory()
    repository = factory(_FakeConnection)
    assert isinstance(repository, E2bMaterializationRepository)
    assert callable(repository.reconcile_document)


@pytest.mark.parametrize(
    ("key", "value", "match"),
    (
        (
            "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE",
            "0",
            "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE=1",
        ),
        (
            "OKF_E2B_DISPOSABLE_TEST_AUTHORIZED",
            "0",
            "OKF_E2B_DISPOSABLE_TEST_AUTHORIZED=1",
        ),
        (
            "OKF_REBUILD_EXPECTED_DATABASE",
            "",
            "OKF_REBUILD_EXPECTED_DATABASE is required",
        ),
    ),
)
def test_connection_factory_requires_authorization(
    key: str, value: str, match: str
) -> None:
    module = _load_runner_module()
    env = dict(_GUARDED_REBUILD_ENV)
    env[key] = value
    with pytest.raises(ValueError, match=match):
        module._build_e2b_connection_factory(env)


@pytest.mark.parametrize("service_key", ("PGSERVICE", "PGSERVICEFILE", "PGSYSCONFDIR"))
def test_connection_factory_refuses_ambient_service_routing(
    service_key: str,
) -> None:
    module = _load_runner_module()
    env = dict(_GUARDED_REBUILD_ENV)
    env[service_key] = "ambient-canary"
    with pytest.raises(ValueError, match="service routing"):
        module._build_e2b_connection_factory(env)


@pytest.mark.parametrize(
    "database_url",
    (
        "postgresql://okf:secret@localhost:5432/okf_task34",
        "postgresql://okf:secret@127.0.0.1/okf_task34",
        "postgresql://okf:secret@127.0.0.1:5432/other_database",
    ),
)
def test_connection_factory_rejects_invalid_target_before_connecting(
    database_url: str,
) -> None:
    module = _load_runner_module()
    env = dict(_GUARDED_REBUILD_ENV)
    env["DATABASE_URL"] = database_url
    with pytest.raises(ValueError, match="Invalid disposable PostgreSQL target"):
        module._build_e2b_connection_factory(env)


def test_connection_factory_valid_env_returns_callable_without_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_runner_module()
    connect_calls: list[object] = []
    monkeypatch.setattr(
        module.psycopg,
        "connect",
        lambda *_a, **_k: connect_calls.append("connect"),
    )
    factory = module._build_e2b_connection_factory(dict(_GUARDED_REBUILD_ENV))
    assert callable(factory)
    assert connect_calls == []


def test_connection_factory_closure_routes_through_runtime_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The returned zero-arg factory delegates to the runtime factory only when invoked."""
    module = _load_runner_module()
    sentinel = object()
    captured: list[object] = []

    def _fake_runtime_factory(target: object) -> object:
        captured.append(target)
        return sentinel

    monkeypatch.setattr(module, "_runtime_connection_factory", _fake_runtime_factory)
    factory = module._build_e2b_connection_factory(dict(_GUARDED_REBUILD_ENV))
    assert callable(factory)
    assert captured == []
    assert factory() is sentinel
    assert len(captured) == 1


def _admitted_document(module: types.ModuleType, tmp_path: Path) -> Any:
    document = OKFParser().parse_bundle(make_bundle(tmp_path, "sectioned-pdf"))[0]
    return module._freeze_raw_document(document)


def _drive_rebuild_one(
    module: types.ModuleType,
    document: Any,
    connection: _FakeConnection,
    repository: _FakeRepository,
) -> E2bReconciliationResult:
    return module._rebuild_one(
        document,
        connection_factory=lambda: connection,
        repository_factory=lambda _audit: repository,
        extractor_factory=lambda: types.SimpleNamespace(extract=lambda _inputs: []),
        corpus_input_factory=lambda _doc: [],
        desired_state_factory=lambda _doc, _cands: E2bDesiredState(),
    )


@pytest.mark.parametrize(
    ("close_connection", "message"),
    (
        (False, "pre-transaction contract error"),
        (True, "link-proof style failure already closed"),
    ),
)
def test_rebuild_one_closes_primary_connection_on_repository_error(
    tmp_path: Path, close_connection: bool, message: str
) -> None:
    module = _load_runner_module()
    document = _admitted_document(module, tmp_path)
    connection = _FakeConnection()
    repository = _FakeRepository(lambda: _FakeConnection())
    repository.close_connection = close_connection
    repository.error = ValueError(message)

    with pytest.raises(ValueError, match=message):
        _drive_rebuild_one(module, document, connection, repository)

    assert connection.close_calls == 1
    assert connection.closed is True
    assert connection.commits == 0
    assert connection.rollbacks == 0


@pytest.mark.parametrize("close_connection", (False, True))
def test_rebuild_one_success_closes_primary_without_double_close(
    tmp_path: Path, close_connection: bool
) -> None:
    module = _load_runner_module()
    document = _admitted_document(module, tmp_path)
    connection = _FakeConnection()
    repository = _FakeRepository(lambda: _FakeConnection())
    repository.close_connection = close_connection

    result = _drive_rebuild_one(module, document, connection, repository)

    assert result.outcome == "no_op"
    assert len(repository.calls) == 1
    scope = repository.calls[0][1]
    assert (scope.document_id, scope.version_id) == (DOC_ID, VERSION_ID)
    assert connection.close_calls == 1
    assert connection.closed is True
    assert connection.commits == 0
    assert connection.rollbacks == 0
    assert connection.cursor().executed == []


def test_redact_rejects_invalid_manifest_sha256() -> None:
    module = _load_runner_module()
    raw = types.SimpleNamespace(outcome="no_op", primary_dml_by_table={})
    for bad in ("a" * 63, "A" * 64, "", 123, None):
        with pytest.raises(ValueError, match="manifest_sha256"):
            module._redact_rebuild_outcome(raw, manifest_sha256=bad)


@pytest.mark.parametrize(
    ("raw", "match"),
    (
        (None, "invalid result"),
        (
            types.SimpleNamespace(outcome=123, primary_dml_by_table={}),
            "outcome is invalid",
        ),
        (
            types.SimpleNamespace(
                outcome="no_op", primary_dml_by_table=[("entity_mentions", 1)]
            ),
            "primary_dml_by_table is invalid",
        ),
    ),
)
def test_redact_rejects_invalid_raw_result(raw: object, match: str) -> None:
    module = _load_runner_module()
    with pytest.raises(ValueError, match=match):
        module._redact_rebuild_outcome(raw, manifest_sha256=_SHA64)


@pytest.mark.parametrize("count", (-1, "2", 2.5, True))
def test_redact_rejects_invalid_dml_count(count: object) -> None:
    module = _load_runner_module()
    raw = types.SimpleNamespace(
        outcome="changed", primary_dml_by_table={"entity_mentions": count}
    )
    with pytest.raises(ValueError, match="nonnegative integer"):
        module._redact_rebuild_outcome(raw, manifest_sha256=_SHA64)


def test_merge_outcomes_rejects_empty() -> None:
    module = _load_runner_module()
    with pytest.raises(ValueError, match="no E2b reconciliation outcomes"):
        module._merge_outcomes([], _SHA64)


def test_merge_outcomes_aggregates_priority_counts_and_audit() -> None:
    module = _load_runner_module()
    changed = module._E2bRebuildOutcome(
        outcome="changed",
        manifest_sha256=_SHA64,
        primary_dml_by_table={"entity_mentions": 1, "node_entity_links": 2},
        failure_audit_outcome="written",
        post_rollback_failure_audit_outcome=None,
    )
    rolled_back = module._E2bRebuildOutcome(
        outcome="rolled_back_failure",
        manifest_sha256=_SHA64,
        primary_dml_by_table={"entity_mentions": 3},
        failure_audit_outcome=None,
        post_rollback_failure_audit_outcome=None,
    )
    merged = module._merge_outcomes([changed, rolled_back], "b" * 64)
    assert merged.outcome == "rolled_back_failure"
    assert merged.primary_dml_by_table == {
        "entity_mentions": 4,
        "node_entity_links": 2,
    }
    assert merged.failure_audit_outcome == "written"
    assert merged.manifest_sha256 == "b" * 64
    assert merged.post_rollback_failure_audit_outcome is None


@pytest.mark.parametrize(
    ("primary", "outcome", "expected"),
    (
        (
            {"node_entity_links": 2, "entity_mentions": 1},
            "changed",
            "entity_mentions=1, node_entity_links=2",
        ),
        ({}, "no_op", "primary_dml=none"),
    ),
)
def test_format_outcome_single_line_sorted_and_redacted(
    primary: Mapping[str, int], outcome: str, expected: str
) -> None:
    module = _load_runner_module()
    formatted = module._format_outcome(
        module._E2bRebuildOutcome(
            outcome=outcome,
            manifest_sha256=_SHA64,
            primary_dml_by_table=primary,
            failure_audit_outcome=None,
            post_rollback_failure_audit_outcome=None,
        )
    )
    assert formatted.count("\n") == 0
    assert expected in formatted
    assert "manifest_sha256=" + _SHA64 in formatted


def test_freeze_raw_document_rejects_missing_canonical_hash(tmp_path: Path) -> None:
    module = _load_runner_module()
    document = OKFParser().parse_bundle(make_bundle(tmp_path, "sectioned-pdf"))[0]
    bad = dataclasses.replace(document, canonical_hash="")
    with pytest.raises(ValueError, match="admitted raw pair"):
        module._freeze_raw_document(bad)


def test_ensure_unique_raw_document_versions_rejects_duplicates(tmp_path: Path) -> None:
    module = _load_runner_module()
    document = OKFParser().parse_bundle(make_bundle(tmp_path, "sectioned-pdf"))[0]
    with pytest.raises(ValueError, match="Duplicate raw OKF document version"):
        module._ensure_unique_raw_document_versions([document, document])


@pytest.mark.parametrize(
    ("malformed", "match"),
    (
        (1, "malformed OKF documents"),
        (0, "No raw OKF documents"),
    ),
)
def test_validate_rebuild_admission_rejects_invalid(malformed: int, match: str) -> None:
    module = _load_runner_module()
    admitted = module._E2bAdmittedBundle((), malformed=malformed)
    with pytest.raises(ValueError, match=match):
        module._validate_rebuild_admission(admitted)


def test_rebuild_bundle_rejects_non_path() -> None:
    module = _load_runner_module()
    with pytest.raises(TypeError, match="bundle path"):
        module.rebuild_bundle("not-a-path")  # type: ignore[arg-type]


def test_load_connection_support_fails_closed_on_missing_spec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_runner_module()
    monkeypatch.setattr(module, "spec_from_file_location", lambda *_a, **_k: None)
    with pytest.raises(ImportError, match="Unable to load"):
        module._load_connection_support()


def test_fixture_failure_messages_are_redacted() -> None:
    module = _load_runner_module()
    malformed = module._fixture_failure("some-fixture")
    unavailable = module._fixture_failure("some-fixture", unavailable=True)
    assert "are malformed" in str(malformed)
    assert "unavailable" in str(unavailable)
    # The raw fixture path never appears: diagnostic_safe_path summarizes it.
    assert "some-fixture" not in str(malformed)
    assert "some-fixture" not in str(unavailable)


@pytest.mark.parametrize(
    "loaded",
    (
        "[]",
        {"doc_id": "not-a-uuid", "version_id": "also-bad", "spans": []},
    ),
)
def test_validate_expected_spans_rejects_invalid(loaded: object) -> None:
    module = _load_runner_module()
    with pytest.raises(ValueError):
        module._validate_expected_spans(loaded, "fixture")


def test_load_expected_spans_rejects_non_str_and_missing_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_runner_module()
    with pytest.raises(ValueError):
        module._load_expected_spans(123)
    monkeypatch.setattr(module, "FIXTURE_ROOT", tmp_path)
    with pytest.raises(ValueError, match="unavailable"):
        module._load_expected_spans("does-not-exist")


def test_verify_fixture_document_count_mismatch() -> None:
    module = _load_runner_module()
    expected = {
        "doc_id": "00000000-0000-0000-0000-000000000099",
        "version_id": "00000000-0000-0000-0000-000000000098",
        "spans": [],
    }
    admitted = module._E2bAdmittedBundle(())
    mismatch = module._verify_fixture(admitted, expected, "some-fixture")
    assert mismatch is not None
    assert "document_count" in mismatch


def test_parse_arguments_rejects_invalid_surfaces(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_runner_module()
    with pytest.raises(SystemExit, match="2"):
        module.parse_arguments(["--bundle", "bundle"])
    assert (
        "one of --verify-roundtrip or --rebuild is required" in capsys.readouterr().err
    )
    with pytest.raises(SystemExit, match="2"):
        module.parse_arguments(["--bundle", "bundle", "--rebuild", "--fixture", "docx"])
    assert "--fixture requires --verify-roundtrip" in capsys.readouterr().err


def test_main_verify_roundtrip_requires_fixture(tmp_path: Path) -> None:
    module = _load_runner_module()
    bundle = make_bundle(tmp_path, "sectioned-pdf")
    with pytest.raises(ValueError, match="--fixture is required"):
        module.main(["--bundle", str(bundle), "--verify-roundtrip"])


def test_main_verify_roundtrip_mismatch_prints_and_returns_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_runner_module()
    bundle = make_bundle(tmp_path, "sectioned-pdf")
    fixture_root = tmp_path / "fixture_root"
    (fixture_root / "sectioned-pdf").mkdir(parents=True)
    (fixture_root / "sectioned-pdf" / "expected_span_ids.json").write_text(
        '{"doc_id": "00000000-0000-0000-0000-000000000099", '
        '"version_id": "00000000-0000-0000-0000-000000000098", "spans": []}',
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "FIXTURE_ROOT", fixture_root)
    assert module.main(_verify_args(bundle)) == 1


def test_main_rebuild_path_uses_runner_and_logs_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_runner_module()
    bundle = make_bundle(tmp_path, "sectioned-pdf")
    monkeypatch.setenv("RAG_ENTITY_EXTRACTOR", "raner")
    calls: list[tuple[Any, Any]] = []

    def _fake_rebuild(*args: object, **kwargs: object) -> Any:
        calls.append((args, kwargs))
        return module._E2bRebuildOutcome(
            outcome="no_op",
            manifest_sha256=_SHA64,
            primary_dml_by_table={},
            failure_audit_outcome=None,
            post_rollback_failure_audit_outcome=None,
        )

    monkeypatch.setattr(module, "rebuild_bundle", _fake_rebuild)
    assert module.main(["--bundle", str(bundle), "--rebuild"]) == 0
    assert len(calls) == 1


def test_run_redacted_cli_maps_value_error_to_fixed_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load_runner_module()
    monkeypatch.delenv("RAG_ENTITY_EXTRACTOR", raising=False)
    code = module._run_redacted_cli(
        ["--bundle", str(tmp_path / "does-not-matter"), "--rebuild"]
    )
    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert captured.err.strip() == module._E2B_CLI_FAILURE_MESSAGE
    assert "RAG_ENTITY_EXTRACTOR" not in captured.err
    assert "raner" not in captured.err.lower()


def test_run_redacted_cli_success_path_returns_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_runner_module()
    bundle = make_bundle(tmp_path, "sectioned-pdf")
    for key in _DATABASE_ROUTING_KEYS | {"RAG_ENTITY_EXTRACTOR"}:
        monkeypatch.delenv(key, raising=False)
    assert module._run_redacted_cli(_verify_args(bundle)) == 0


def test_run_redacted_cli_maps_psycopg_error_to_fixed_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load_runner_module()

    def _failing_main(*_a: object, **_k: object) -> int:
        raise module.psycopg.OperationalError("synthetic connection failure")

    monkeypatch.setattr(module, "main", _failing_main)
    code = module._run_redacted_cli([])
    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert captured.err.strip() == "Database connection failed; refusing rebuild"
    assert "synthetic" not in captured.err


def test_cli_subprocess_value_error_is_fixed_redacted_message(
    tmp_path: Path,
) -> None:
    module = _load_runner_module()
    # Explicit minimal non-sensitive allowlist only: no ambient environment is
    # enumerated or copied. The child never sees the DB/auth switches (all 12
    # keys) or the extractor gate.
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "COMSPEC": os.environ.get("COMSPEC", ""),
        "TEMP": os.environ.get("TEMP", ""),
    }
    assert not (_DATABASE_ROUTING_KEYS | {"RAG_ENTITY_EXTRACTOR"}) & env.keys()
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--bundle",
            str(tmp_path / "does-not-matter"),
            "--rebuild",
        ],
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.strip() == module._E2B_CLI_FAILURE_MESSAGE
    assert "RAG_ENTITY_EXTRACTOR" not in result.stderr
    assert "postgresql" not in result.stderr
    assert "secret" not in result.stderr
