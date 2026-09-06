"""E2b runner CLI contracts for scripts/rebuild_from_okf_e2b.py (Phase 16-11).

RED-only task: the runner script does not exist yet, so every test that loads
``scripts/rebuild_from_okf_e2b.py`` fails/errors for exactly that reason. A
small set of production pins (the E2b document scope advisory key, the E2b
repository no-second-audit-channel contract, the E2b repository lock order, and
the shared connection-support redaction rule) pass immediately because the
underlying production modules already exist.

Frozen contracts covered:

1. The runner reads ``RAG_ENTITY_EXTRACTOR`` directly, defaults off, fails
   closed before any connection, and never uses ``RuntimeSettings.from_env()``.
2. ``_E2bRebuildOutcome`` has exactly five dataclass fields and never carries
   ``reconciliation_required``.
3. The existing repository has no second audit channel: an accepted typed
   outcome must have ``post_rollback_failure_audit_outcome is None`` and
   non-None raw second-audit evidence must fail closed.
4. The runner exposes the five frozen injected seams: ``_build_e2b_corpus_input_factory``,
   ``_build_e2b_desired_state_factory``, ``_build_e2b_extractor_factory``,
   ``_build_e2b_repository_factory``, and ``_build_e2b_connection_factory``.
5. The runner issues no advisory-lock/transaction SQL, commit, or rollback; it
   delegates the exact E2a-shared key, rollback, and fresh failure audit to
   ``E2bMaterializationRepository.reconcile_document``.
6. Connection support is freshly loaded from ``scripts/_rebuild_database_connection.py``
   despite a poisoned ``sys.modules`` entry (prior slot restored), and a raw URI
   is never passed positionally to ``psycopg.connect``.
7. ``--verify-roundtrip`` is parser-only / no DB / no model and works without
   ``RAG_ENTITY_EXTRACTOR`` or ``DATABASE_URL`` and without any connection.
8. Processing and the manifest are deterministic over ``(document_id, version_id)``
   and the manifest is redacted.
9. Outcome redaction whitelists only the three E2b tables and the five audit
   statuses, and rejects unknown/adversarial strings plus any corpus/span/DSN
   leakage from hostile extra attributes.
10. A fresh-process import guard proves no modelscope/torch/transformers/
    tokenizers/sentencepiece/jieba/raner_adapter/offline_mirror/llm/generative-LLM
    modules are loaded, and a source guard rejects ``FunctionAgent`` and
    ``get_llm(``.
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import json
import re
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

from ._rebuild_cli_testkit import bundle_result, make_bundle

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "rebuild_from_okf_e2b.py"
CONNECTION_HELPER_MODULE_NAME = "_okf_rebuild_database_connection"
CONNECTION_HELPER_PATH = REPO_ROOT / "scripts" / "_rebuild_database_connection.py"
DOC_ID = "00000000-0000-0000-0000-000000000001"
VERSION_ID = "00000000-0000-0000-0000-000000000003"
SECOND_DOC_ID = "00000000-0000-0000-0000-000000000002"
SECOND_VERSION_ID = "00000000-0000-0000-0000-000000000004"
_GUARDED_REBUILD_ENV: Mapping[str, str] = {
    "RAG_ENTITY_EXTRACTOR": "raner",
    "DATABASE_URL": "postgresql://okf:secret@127.0.0.1:5432/okf_task34",
    "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE": "1",
    "OKF_REBUILD_EXPECTED_DATABASE": "okf_task34",
    "OKF_E2B_DISPOSABLE_TEST_AUTHORIZED": "1",
}


def _load_runner_module() -> types.ModuleType:
    """Load scripts/rebuild_from_okf_e2b.py as an isolated module.

    RED: this raises FileNotFoundError until the runner script exists.
    """
    spec = importlib.util.spec_from_file_location("rebuild_from_okf_e2b", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _with_scope(document: Any, doc_id: str, version_id: str) -> Any:
    return dataclasses.replace(
        document,
        frontmatter=dataclasses.replace(
            document.frontmatter, doc_id=doc_id, version_id=version_id
        ),
    )


class _SpyCursor:
    """In-memory cursor recording executed SQL with a fake lock row."""

    def __init__(
        self,
        connection: "_SpyConnection",
        *,
        lock_row: Mapping[str, object] | None = None,
    ) -> None:
        self._connection = connection
        self._lock_row = lock_row
        self._lock_row_consumed = False
        self.executed: list[tuple[str, object | None]] = []

    @property
    def connection(self) -> "_SpyConnection":
        return self._connection

    def execute(self, statement: str, parameters: object | None = None) -> None:
        self.executed.append((statement, parameters))

    def fetchone(self) -> Mapping[str, object] | None:
        if self._lock_row is not None and not self._lock_row_consumed:
            self._lock_row_consumed = True
            return self._lock_row
        return None

    def fetchall(self) -> list[Mapping[str, object]]:
        return []


class _SpyConnection:
    """In-memory connection fake tracking commit/rollback/close counts."""

    def __init__(self, *, lock_row: Mapping[str, object] | None = None) -> None:
        self.autocommit = False
        self.commits = 0
        self.rollbacks = 0
        self.closes = 0
        self._cursor = _SpyCursor(self, lock_row=lock_row)

    def cursor(self) -> _SpyCursor:
        return self._cursor

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closes += 1


# ---------------------------------------------------------------------------
# Production pins (PASS at RED -- the underlying modules already exist).
# ---------------------------------------------------------------------------


def test_e2b_document_scope_advisory_lock_key_pins_e2a_shared_parent_key() -> None:
    scope = E2bDocumentScope(document_id=DOC_ID, version_id=VERSION_ID)
    assert scope.advisory_lock_key == f"okf:e2a:parent:{DOC_ID}:{VERSION_ID}"
    assert scope.advisory_lock_key != f"okf:e2b:parent:{DOC_ID}:{VERSION_ID}"
    assert "okf:e2b:parent" not in scope.advisory_lock_key


def test_e2b_repository_result_carries_no_second_audit_channel() -> None:
    field_names = {
        field_.name for field_ in dataclasses.fields(E2bReconciliationResult)
    }
    assert "failure_audit_outcome" in field_names
    assert "post_rollback_failure_audit_outcome" not in field_names


def test_e2b_repository_acquires_e2a_shared_advisory_lock_through_reconcile_document() -> (
    None
):
    scope = E2bDocumentScope(document_id=DOC_ID, version_id=VERSION_ID)
    connection = _SpyConnection(lock_row={"doc_id": DOC_ID, "version_id": VERSION_ID})
    cursor = connection.cursor()

    result = E2bMaterializationRepository().reconcile_document(
        cursor, scope, desired=E2bDesiredState(), recorder=E2bDmlRecorder()
    )

    assert result.outcome == "no_op"
    assert cursor.executed[0] == (
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (f"okf:e2a:parent:{DOC_ID}:{VERSION_ID}",),
    )
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert not any("okf:e2b:parent" in query for query, _ in cursor.executed)


def test_connection_support_never_passes_raw_uri_positionally() -> None:
    source = CONNECTION_HELPER_PATH.read_text(encoding="utf-8")
    assert re.search(r"psycopg\.connect\(\s*\*\*", source) is not None
    assert re.search(r"psycopg\.connect\(\s*(['\"]|[a-zA-Z])", source) is None


# ---------------------------------------------------------------------------
# Runner contracts (RED -- scripts/rebuild_from_okf_e2b.py is absent).
# ---------------------------------------------------------------------------


def test_e2b_rebuild_outcome_dto_has_exactly_five_fields() -> None:
    module = _load_runner_module()
    field_names = tuple(
        field_.name for field_ in dataclasses.fields(module._E2bRebuildOutcome)
    )
    assert field_names == (
        "outcome",
        "manifest_sha256",
        "primary_dml_by_table",
        "failure_audit_outcome",
        "post_rollback_failure_audit_outcome",
    )
    assert "reconciliation_required" not in field_names


@pytest.mark.parametrize(
    "extractor_env",
    (
        {},
        {"RAG_ENTITY_EXTRACTOR": "off"},
        {"RAG_ENTITY_EXTRACTOR": ""},
        {"RAG_ENTITY_EXTRACTOR": "invented"},
    ),
)
def test_runner_rebuild_fails_closed_before_connect_unless_raner(
    extractor_env: Mapping[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The CLI ``--rebuild`` path refuses non-raner before any connection."""
    module = _load_runner_module()
    bundle = make_bundle(tmp_path, "sectioned-pdf")
    for key, value in _GUARDED_REBUILD_ENV.items():
        if key == "RAG_ENTITY_EXTRACTOR":
            continue
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("RAG_ENTITY_EXTRACTOR", raising=False)
    for key, value in extractor_env.items():
        monkeypatch.setenv(key, value)
    connect_calls: list[object] = []

    def _fail_connection_factory(*_a: object, **_k: object) -> object:
        pytest.fail("connection factory must not be built before switch gating")

    monkeypatch.setattr(
        module, "_build_e2b_connection_factory", _fail_connection_factory
    )
    monkeypatch.setattr(
        module.psycopg, "connect", lambda *_a, **_k: connect_calls.append("connect")
    )

    with pytest.raises(ValueError):
        module.main(["--bundle", str(bundle), "--rebuild"])

    assert connect_calls == []


def test_runner_pins_require_raner_extractor_and_rejects_runtime_settings() -> None:
    module = _load_runner_module()
    source = SCRIPT.read_text(encoding="utf-8")
    assert "RAG_ENTITY_EXTRACTOR" in source
    assert "RuntimeSettings" not in source
    assert "from_env" not in source
    assert callable(module._require_raner_extractor)
    module._require_raner_extractor({"RAG_ENTITY_EXTRACTOR": "raner"})
    for environ in (
        {},
        {"RAG_ENTITY_EXTRACTOR": "off"},
        {"RAG_ENTITY_EXTRACTOR": ""},
        {"RAG_ENTITY_EXTRACTOR": "invented"},
    ):
        with pytest.raises(ValueError):
            module._require_raner_extractor(environ)


def test_redact_outcome_accepts_repository_result_with_none_second_audit() -> None:
    module = _load_runner_module()
    result = E2bReconciliationResult(
        outcome="rolled_back_failure",
        primary_dml_by_table={},
        stale_deletion_counts={},
        failure_audit_outcome="written",
    )

    outcome = module._redact_rebuild_outcome(result, manifest_sha256="a" * 64)

    assert outcome.outcome == "rolled_back_failure"
    assert outcome.manifest_sha256 == "a" * 64
    assert outcome.primary_dml_by_table == {}
    assert outcome.failure_audit_outcome == "written"
    assert outcome.post_rollback_failure_audit_outcome is None


def test_redact_outcome_fails_closed_on_non_none_second_audit_evidence() -> None:
    module = _load_runner_module()
    hostile = types.SimpleNamespace(
        outcome="rolled_back_failure",
        primary_dml_by_table={},
        failure_audit_outcome="written",
        post_rollback_failure_audit_outcome="written",
    )
    with pytest.raises(ValueError):
        module._redact_rebuild_outcome(hostile, manifest_sha256="a" * 64)


def test_redact_outcome_accepts_whitelisted_tables_and_statuses() -> None:
    module = _load_runner_module()
    raw = types.SimpleNamespace(
        outcome="changed",
        primary_dml_by_table={
            "entity_mentions": 2,
            "okf_e2b_node_link_ownership": 1,
            "node_entity_links": 3,
        },
        failure_audit_outcome="outcome_unknown",
    )

    outcome = module._redact_rebuild_outcome(raw, manifest_sha256="a" * 64)

    assert outcome.primary_dml_by_table == {
        "entity_mentions": 2,
        "okf_e2b_node_link_ownership": 1,
        "node_entity_links": 3,
    }
    assert outcome.failure_audit_outcome == "outcome_unknown"
    assert outcome.post_rollback_failure_audit_outcome is None


@pytest.mark.parametrize(
    "outcome, primary, status",
    (
        ("changed", {"chunk_entity_links": 1}, None),
        ("changed", {"okf_rebuild_failure_audit": 1}, None),
        ("changed", {"mystery_table": 1}, None),
        ("changed", {"entity_mentions": 1, "chunk_entity_links": 1}, None),
        ("changed", {}, "wrote_to_db"),
        ("changed", {}, "okf_rebuild_failure_audit"),
        ("changed", {}, "written_cleanup_unconfirmed "),
        ("okf_rebuild_failure_audit", {}, None),
        ("I-am-adversarial", {}, None),
    ),
)
def test_redact_outcome_rejects_disallowed_fields(
    outcome: str, primary: Mapping[str, int], status: str | None
) -> None:
    module = _load_runner_module()
    raw = types.SimpleNamespace(
        outcome=outcome,
        primary_dml_by_table=dict(primary),
        failure_audit_outcome=status,
    )
    with pytest.raises(ValueError):
        module._redact_rebuild_outcome(raw, manifest_sha256="a" * 64)


def test_format_outcome_never_leaks_dsn_credential_corpus_or_span() -> None:
    """A valid raw result with hostile extra attrs must redact all of them."""
    module = _load_runner_module()
    canaries = {
        "dsn": "postgresql://okf:hunter2-secret@127.0.0.1:5432/okf_task34",
        "credential": "hunter2-secret",
        "corpus": "canary-corpus-body-秘密",
        "span": "canary-span-text-秘密",
    }
    raw = types.SimpleNamespace(
        outcome="changed",
        primary_dml_by_table={
            "entity_mentions": 1,
            "okf_e2b_node_link_ownership": 2,
            "node_entity_links": 3,
        },
        failure_audit_outcome=None,
        post_rollback_failure_audit_outcome=None,
        database_url=canaries["dsn"],
        credential=canaries["credential"],
        corpus_body=canaries["corpus"],
        span_text=canaries["span"],
    )

    outcome = module._redact_rebuild_outcome(raw, manifest_sha256="a" * 64)
    formatted = module._format_outcome(outcome)

    for canary in canaries.values():
        assert canary not in formatted
    assert "entity_mentions=1" in formatted
    assert "okf_e2b_node_link_ownership=2" in formatted
    assert "node_entity_links=3" in formatted
    assert "manifest_sha256=aaaaaaaa" in formatted


def test_connection_support_loads_fresh_despite_poisoned_sys_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A poisoned slot with a matching ``__file__`` is bypassed and restored."""
    poisoned = types.ModuleType(CONNECTION_HELPER_MODULE_NAME)
    poisoned.__file__ = str(CONNECTION_HELPER_PATH)
    monkeypatch.setitem(sys.modules, CONNECTION_HELPER_MODULE_NAME, poisoned)

    module = _load_runner_module()

    assert sys.modules[CONNECTION_HELPER_MODULE_NAME] is poisoned
    support = module._connection_support
    assert support is not poisoned
    assert support.__file__ == str(CONNECTION_HELPER_PATH)
    assert hasattr(support, "runtime_connection_kwargs")
    assert hasattr(support, "DisposablePostgresqlTarget")


def test_runner_exposes_injectable_pipeline_seams() -> None:
    module = _load_runner_module()
    for name in (
        "_build_e2b_corpus_input_factory",
        "_build_e2b_desired_state_factory",
        "_build_e2b_extractor_factory",
        "_build_e2b_repository_factory",
        "_build_e2b_connection_factory",
    ):
        assert callable(getattr(module, name))


def test_runner_delegates_lock_commit_and_fresh_audit_to_repository_seam(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Full fake pipeline proves deterministic order, seam wiring, fresh audit factories, zero runner SQL."""
    module = _load_runner_module()
    bundle = make_bundle(tmp_path, "sectioned-pdf")
    document = OKFParser().parse_bundle(bundle)[0]
    earlier = _with_scope(document, DOC_ID, VERSION_ID)
    later = _with_scope(document, SECOND_DOC_ID, SECOND_VERSION_ID)

    class _ReverseParser:
        def parse_bundle(self, _: Path) -> object:
            return bundle_result(later, earlier)

    processed: list[tuple[str, str, str]] = []
    extractor_inputs: list[list[object]] = []
    desired_calls: list[tuple[str, str, tuple[object, ...]]] = []
    failure_audit_factories: list[object] = []
    opened_connections: list[_SpyConnection] = []

    def _connection_factory() -> _SpyConnection:
        connection = _SpyConnection()
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

    class _FakeRepository:
        def __init__(self, failure_audit_connection_factory: object) -> None:
            failure_audit_factories.append(failure_audit_connection_factory)

        def reconcile_document(
            self,
            cursor: object,
            scope: E2bDocumentScope,
            *,
            desired: E2bDesiredState,
            recorder: E2bDmlRecorder,
        ) -> E2bReconciliationResult:
            assert type(recorder) is E2bDmlRecorder
            assert isinstance(desired, E2bDesiredState)
            processed.append(
                (scope.document_id, scope.version_id, scope.advisory_lock_key)
            )
            return E2bReconciliationResult(
                outcome="no_op", primary_dml_by_table={}, stale_deletion_counts={}
            )

    def _repository_factory(
        failure_audit_connection_factory: object,
    ) -> _FakeRepository:
        return _FakeRepository(failure_audit_connection_factory)

    monkeypatch.setattr(module, "OKFParser", _ReverseParser)
    monkeypatch.setattr(
        module,
        "_build_e2b_corpus_input_factory",
        lambda *_a, **_k: _corpus_input_factory,
    )
    monkeypatch.setattr(
        module,
        "_build_e2b_desired_state_factory",
        lambda *_a, **_k: _desired_state_factory,
    )
    monkeypatch.setattr(
        module,
        "_build_e2b_extractor_factory",
        lambda *_a, **_k: lambda: _RecordingExtractor(),
    )
    monkeypatch.setattr(
        module, "_build_e2b_repository_factory", lambda *_a, **_k: _repository_factory
    )
    monkeypatch.setattr(
        module, "_build_e2b_connection_factory", lambda *_a, **_k: _connection_factory
    )

    outcome = module.rebuild_bundle(bundle, environ=dict(_GUARDED_REBUILD_ENV))

    assert processed == [
        (DOC_ID, VERSION_ID, f"okf:e2a:parent:{DOC_ID}:{VERSION_ID}"),
        (
            SECOND_DOC_ID,
            SECOND_VERSION_ID,
            f"okf:e2a:parent:{SECOND_DOC_ID}:{SECOND_VERSION_ID}",
        ),
    ]
    assert extractor_inputs == [
        [f"corpus-{DOC_ID}"],
        [f"corpus-{SECOND_DOC_ID}"],
    ]
    assert [call[:2] for call in desired_calls] == [
        (DOC_ID, VERSION_ID),
        (SECOND_DOC_ID, SECOND_VERSION_ID),
    ]
    assert all(len(call[2]) == 1 for call in desired_calls)
    assert len(failure_audit_factories) == 2
    # Snapshot the primary connections first so audit-created connections are
    # tracked separately from the two primary connections.
    primary_connections = list(opened_connections)
    assert len(primary_connections) == 2
    audit_connections: list[_SpyConnection] = []
    for factory in failure_audit_factories:
        assert callable(factory)
        first = factory()
        second = factory()
        assert type(first) is _SpyConnection
        assert type(second) is _SpyConnection
        assert first is not second
        assert first not in primary_connections
        assert second not in primary_connections
        audit_connections.extend((first, second))
    assert len({connection for connection in audit_connections}) == len(
        audit_connections
    )
    for connection in primary_connections:
        assert connection.closes == 1
        assert connection.commits == 0
        assert connection.rollbacks == 0
        assert connection.cursor().executed == []
    for connection in audit_connections:
        assert connection.closes == 0
        assert connection.commits == 0
        assert connection.rollbacks == 0
        connection.close()
    assert isinstance(outcome, module._E2bRebuildOutcome)
    assert outcome.outcome == "no_op"
    assert outcome.primary_dml_by_table == {}
    assert outcome.post_rollback_failure_audit_outcome is None


def test_verify_roundtrip_works_without_rag_entity_extractor_or_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for key in (
        "RAG_ENTITY_EXTRACTOR",
        "DATABASE_URL",
        "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE",
        "OKF_REBUILD_EXPECTED_DATABASE",
        "OKF_E2B_DISPOSABLE_TEST_AUTHORIZED",
    ):
        monkeypatch.delenv(key, raising=False)
    bundle = make_bundle(tmp_path, "sectioned-pdf")
    module = _load_runner_module()

    monkeypatch.setattr(
        module.psycopg,
        "connect",
        lambda *_a, **_k: pytest.fail("verify-roundtrip must never connect"),
    )

    assert (
        module.main(
            [
                "--bundle",
                str(bundle),
                "--verify-roundtrip",
                "--fixture",
                "sectioned-pdf",
            ]
        )
        == 0
    )


def test_manifest_sha256_is_deterministic_and_redacted() -> None:
    module = _load_runner_module()
    documents = (
        module._E2bAdmittedRawDocument(
            doc_id=SECOND_DOC_ID,
            version_id=SECOND_VERSION_ID,
            canonical_hash="d" * 64,
            spans=(),
            verification_path="raw/second.md",
        ),
        module._E2bAdmittedRawDocument(
            doc_id=DOC_ID,
            version_id=VERSION_ID,
            canonical_hash="c" * 64,
            spans=(
                module._E2bAdmittedSpan(
                    span_id="11111111-1111-1111-1111-111111111111",
                    page_no=1,
                    heading_path=("a",),
                    offset=0,
                    text="canary-span-text-秘密",
                ),
            ),
            verification_path="raw/first.md",
        ),
    )
    admitted = module._E2bAdmittedBundle(documents)

    manifest_one, sha_one = module._scope_manifest(admitted)
    manifest_two, sha_two = module._scope_manifest(admitted)

    assert sha_one == sha_two
    assert manifest_one["schema_version"] == 1
    encoded = json.dumps(
        manifest_one, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    assert hashlib.sha256(encoded).hexdigest() == sha_one
    scopes = [
        f"{item['doc_id']}:{item['version_id']}" for item in manifest_one["scopes"]
    ]
    assert scopes == sorted(scopes)
    assert scopes == [
        f"{DOC_ID}:{VERSION_ID}",
        f"{SECOND_DOC_ID}:{SECOND_VERSION_ID}",
    ]
    for item in manifest_one["scopes"]:
        assert set(item) == {"doc_id", "version_id", "canonical_hash", "span_count"}
    body = json.dumps(manifest_one)
    assert "canary-span-text" not in body
    assert "postgresql" not in body
    assert "first.md" not in body


def test_fresh_process_import_guard_proves_no_model_modules_loaded() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "FunctionAgent" not in source
    assert "get_llm(" not in source
    blocked = (
        "modelscope",
        "torch",
        "transformers",
        "tokenizers",
        "sentencepiece",
        "jieba",
        "llamaindex_runtime.entity.raner_adapter",
        "llamaindex_runtime.entity.offline_mirror",
        "llamaindex_runtime.llm",
        "openai",
        "anthropic",
    )
    script = (
        "import importlib.util\n"
        "import sys\n"
        "from pathlib import Path\n"
        f"project_root = Path({str(REPO_ROOT)!r})\n"
        "sys.path.insert(0, str(project_root))\n"
        "script_path = project_root / 'scripts' / 'rebuild_from_okf_e2b.py'\n"
        "spec = importlib.util.spec_from_file_location('rebuild_from_okf_e2b', script_path)\n"
        "assert spec is not None and spec.loader is not None\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n"
        f"blocked = {list(blocked)!r}\n"
        "loaded = [name for name in blocked if name in sys.modules]\n"
        "if loaded:\n"
        "    sys.stderr.write('loaded=' + ','.join(sorted(loaded)))\n"
        "    sys.exit(1)\n"
        "sys.exit(0)\n"
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )

    assert result.returncode == 0, result.stderr
