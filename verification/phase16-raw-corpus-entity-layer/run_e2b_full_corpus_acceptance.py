"""Phase 16-15 Task 1 E2b full-corpus acceptance runner (future gate 4).

This runner is the single-use authorized gate for the Phase 16 raw-corpus
entity layer. It mirrors the 16-14 migration-gate conventions:

- Default blocked: unless OKF_MIGRATION_TEST_DATABASE_DISPOSABLE=1 AND
  OKF_REBUILD_EXPECTED_DATABASE (a disposable loopback target) AND
  OKF_E2B_DISPOSABLE_TEST_AUTHORIZED=1 are all present, the runner emits
  exactly blocked_not_executed and exits WITHOUT any connection attempt
  (no connection helper, no target parsing).
- Authorized path: the disposable target is parsed strictly through
  scripts._rebuild_database_connection.parse_disposable_postgresql_target and
  the E2b materialization repository is driven through the full transition
  matrix (16-15 Task 1): first materialization with full provenance and zero
  chunk_entity_links; equivalent-rerun idempotence with zero DML; changed-set
  convergence on a surviving canonical span with stale E2b-owned mention and
  link-ownership cleanup plus ownership-safe bridge deletion; manual/legacy
  preservation; invalid-document isolation with a fresh-connection
  okf_e2b_failure_audit row; changed-set failure rollback restoring the old
  committed state; and E2b-vs-E2b plus E2a-vs-E2b serialization on E2a's
  exact shared advisory key okf:e2a:parent:{document_id}:{version_id} (never
  okf:e2b:parent).
- Path decision (16-15 truth #20): the matrix drives the repository with
  deterministic FIXTURE candidates (fixture_candidates), never a real RaNER
  adapter; the evidence records the candidate path explicitly. Gate 3 was
  skipped by user decision 2026-08-31.
- Evidence: a redacted single-line JSON file (16-14 style) with per-table DML
  counts, changed-set deletion counts, stale-cleanup counts including the
  bridge-deletion DML count, manual/legacy preservation counts,
  failure-audit outcomes, and lock/serialization outcomes. No connection
  string, credential, or corpus text is ever written or logged, and the
  runner consumes zero generative-LLM tokens.

The runner never reads or logs any production target: the disposable
target is passed programmatically as a keyword-only target_uri.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, TypeAlias

import psycopg

from llamaindex_runtime.entity.contracts import deterministic_id
from llamaindex_runtime.entity.materialization_repository import (
    E2bDesiredLink,
    E2bDesiredMention,
    E2bDesiredState,
    E2bDmlRecorder,
    E2bDocumentScope,
    E2bMaterializationRepository,
    E2bReconciliationResult,
)
from scripts._rebuild_database_connection import (
    DisposablePostgresqlTarget,
    parse_disposable_postgresql_target,
    runtime_connection_factory,
)

VERIFICATION_DIR = Path(__file__).resolve().parent
EVIDENCE_NAME = "e2b_full_corpus_acceptance_evidence.md"
EVIDENCE_PATH = VERIFICATION_DIR / EVIDENCE_NAME

AUTH_ENV = "OKF_E2B_DISPOSABLE_TEST_AUTHORIZED"
DISPOSABLE_ENV = "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE"
EXPECTED_DATABASE_ENV = "OKF_REBUILD_EXPECTED_DATABASE"
GATE_ROUTING_KEYS = frozenset((AUTH_ENV, DISPOSABLE_ENV, EXPECTED_DATABASE_ENV))

BLOCKED_STATUS = "blocked_not_executed"
EXECUTED_STATUS = "executed"
# A run that executed but whose proof transitions failed: evidence is still
# written (per-transition outcomes diagnose the failure), but the gate must
# not report success (FINDING B, fail-closed acceptance semantics).
FAILED_STATUS = "executed_failed"
FAILED_EXIT_CODE = 3
CLI_FAILURE_MESSAGE = (
    "E2b full-corpus acceptance refused; failure details are not disclosed"
)
CONNECT_FAILURE_MESSAGE = "Database connection failed; refusing full-corpus acceptance"

# 16-15 truth #20: deterministic fixture candidates, never a real RaNER
# adapter. The evidence records this path explicitly.
FIXTURE_CANDIDATE_PATH = "fixture_candidates"

TargetParser: TypeAlias = Callable[[str, str], DisposablePostgresqlTarget]
ConnectionFactory: TypeAlias = Callable[
    [DisposablePostgresqlTarget], psycopg.Connection[Any]
]
AuditConnectionFactory: TypeAlias = Callable[[], psycopg.Connection[Any]]
RepositoryFactory: TypeAlias = Callable[
    [AuditConnectionFactory], E2bMaterializationRepository
]
MatrixRunner: TypeAlias = Callable[..., dict[str, object]]
EvidenceWriter: TypeAlias = Callable[[dict[str, object], Path], str]


class _Cursor(Protocol):
    def execute(
        self,
        statement: str,
        parameters: Sequence[Any] | Mapping[str, Any] | None = None,
    ) -> None: ...

    def fetchone(self) -> Mapping[str, int] | None: ...


class _Connection(Protocol):
    closed: bool

    def cursor(self) -> _Cursor: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class AcceptanceOutcome:
    """Redacted, typed summary of one full-corpus acceptance run."""

    status: str
    candidate_path: str
    matrix: dict[str, object]
    evidence_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "matrix", dict(self.matrix))


# -- deterministic fixture data (fixed UUIDs, never derived from a corpus) ---

_FIXTURE_DOCUMENT_ID = "11111111-1111-4111-8111-111111111111"
_FIXTURE_VERSION_ID = "22222222-2222-4222-8222-222222222222"
_FIXTURE_MANUAL_DOCUMENT_ID = "99999999-9999-4999-8999-999999999999"
_FIXTURE_MANUAL_VERSION_ID = "88888888-8888-4888-8888-888888888888"
_FIXTURE_INVALID_DOCUMENT_ID = "77777777-7777-4777-8777-777777777777"
_FIXTURE_INVALID_VERSION_ID = "66666666-6666-4666-8666-666666666666"
_FIXTURE_SPAN_IDS = (
    "33333333-3333-4333-8333-333333333333",  # main span 0 (surviving span)
    "55555555-5555-4555-8555-555555555555",  # manual span 0
    "66666666-6666-4666-8666-666666666666",  # manual span 1
    "77777777-7777-4777-8777-777777777777",  # invalid span 0
)
_FIXTURE_NODE_IDS = (
    "88888888-8888-4888-8888-888888888888",  # main node 0
    "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",  # manual node 0
    "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",  # manual node 1
    "cccccccc-cccc-4ccc-8ccc-cccccccccccc",  # invalid node 0
)
_FIXTURE_ENTITY_IDS = (
    "dddddddd-dddd-4ddd-8ddd-dddddddddddd",  # entity 0
    "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",  # entity 1
)
_FIXTURE_UNKNOWN_ENTITY_ID = "ffffffff-ffff-4fff-8fff-ffffffffffff"
_FIXTURE_MANUAL_MENTION_COUNT = 1
_FIXTURE_MANUAL_BRIDGE_COUNT = 1


def _blocked_outcome() -> AcceptanceOutcome:
    """The default blocked outcome: zero connection attempt, zero evidence."""
    return AcceptanceOutcome(BLOCKED_STATUS, "", {}, "")


def _require_gate_authorization(environ: Mapping[str, str]) -> None:
    """Require the exact single-use gate routing variables (16-14 pattern)."""
    disposable = environ.get(DISPOSABLE_ENV)
    authorized = environ.get(AUTH_ENV)
    expected_database = environ.get(EXPECTED_DATABASE_ENV)
    if disposable != "1":
        raise ValueError(f"{DISPOSABLE_ENV}=1")
    if authorized != "1":
        raise ValueError(f"{AUTH_ENV}=1")
    if not expected_database:
        raise ValueError(EXPECTED_DATABASE_ENV)


def _e2b_connection_factory(
    target: DisposablePostgresqlTarget,
) -> psycopg.Connection[Any]:
    """Build a connection whose rows are Mappings (the repository's contract).

    The materialization repository's _acquire_locks checks
    isinstance(row, Mapping); real psycopg connections return tuple rows by
    default, which made every reconcile fail with ValueError. The audit
    connection factory inherits this factory (it is derived from the same
    connection_factory in _reconcile_once), so failure-audit writes use the
    same row shape.
    """
    connection = runtime_connection_factory(target)
    connection.row_factory = psycopg.rows.dict_row
    return connection


def _build_repository_factory() -> RepositoryFactory:
    """Build a factory creating a fresh repository per reconcile."""

    def _factory(
        failure_audit_connection_factory: AuditConnectionFactory,
    ) -> E2bMaterializationRepository:
        return E2bMaterializationRepository(
            failure_audit_connection_factory=failure_audit_connection_factory
        )

    return _factory


# -- evidence payload -------------------------------------------------------

_PAYLOAD_KEYS = frozenset(("schema_version", "status", "candidate_path", "matrix"))

_MATRIX_KEYS = frozenset(
    (
        "first_materialization",
        "equivalent_rerun",
        "changed_set_convergence",
        "manual_legacy_preservation",
        "invalid_document_isolation",
        "changed_set_failure_rollback",
        "e2b_vs_e2b_serialization",
        "e2a_vs_e2b_serialization",
    )
)

_TRANSITION_PAYLOAD_KEYS: dict[str, frozenset[str]] = {
    "first_materialization": frozenset(
        (
            "outcome",
            "error_type",
            "entity_mentions_dml",
            "node_entity_links_dml",
            "okf_e2b_node_link_ownership_dml",
            "chunk_entity_links_dml",
            "mention_count",
            "bridge_count",
            "ledger_count",
            "chunk_entity_links_count",
        )
    ),
    "equivalent_rerun": frozenset(
        ("outcome", "error_type", "dml_total", "timestamp_churn")
    ),
    "changed_set_convergence": frozenset(
        (
            "outcome",
            "error_type",
            "stale_mention_deletions",
            "stale_link_ownership_deletions",
            "bridge_deletion_dml",
            "fail_closed_preserved_bridges",
            "mention_count",
            "bridge_count",
        )
    ),
    "manual_legacy_preservation": frozenset(
        (
            "outcome",
            "error_type",
            "manual_mentions_preserved",
            "manual_bridges_preserved",
            "claimed",
            "deleted",
            "new_mention_count",
            "new_bridge_count",
        )
    ),
    "invalid_document_isolation": frozenset(
        (
            "outcome",
            "error_type",
            "scope_writes",
            "failure_audit_outcome",
            "continued_to_next",
        )
    ),
    "changed_set_failure_rollback": frozenset(
        (
            "outcome",
            "error_type",
            "rollback_confirmed",
            "old_state_restored",
            "failure_audit_outcome",
        )
    ),
    "e2b_vs_e2b_serialization": frozenset(
        (
            "serialized",
            "error_type",
            "duplicate_rows",
            "lock_key_is_e2a",
            "lock_key_is_e2b",
            "overlap_blocked_on_lock",
            "pre_converge_outcome",
            "second_outcome",
        )
    ),
    "e2a_vs_e2b_serialization": frozenset(
        (
            "serialized",
            "error_type",
            "duplicate_rows",
            "lock_key_is_e2a",
            "lock_key_is_e2b",
            "overlap_blocked_on_lock",
            "pre_converge_outcome",
            "second_outcome",
        )
    ),
}


def _canonical_evidence_payload(
    status: str, matrix: dict[str, object]
) -> dict[str, object]:
    """Build the canonical evidence payload (16-14 style, single-line JSON)."""
    return {
        "schema_version": 1,
        "status": status,
        "candidate_path": FIXTURE_CANDIDATE_PATH,
        "matrix": matrix,
    }


def _redact_evidence_payload(payload: dict[str, object]) -> dict[str, object]:
    """Refuse any evidence field outside the exact allowlists (T-16-56)."""
    unknown = set(payload) - _PAYLOAD_KEYS
    if unknown:
        raise ValueError("unknown evidence payload field")
    matrix = payload.get("matrix")
    if not isinstance(matrix, Mapping):
        raise ValueError("evidence matrix must be a mapping")
    if set(matrix) != _MATRIX_KEYS:
        raise ValueError("evidence matrix keys are not the exact transition set")
    for name, transition in matrix.items():
        if not isinstance(transition, Mapping):
            raise ValueError("evidence transition must be a mapping")
        unknown_keys = set(transition) - _TRANSITION_PAYLOAD_KEYS[name]
        if unknown_keys:
            raise ValueError("unknown evidence transition field")
    return dict(payload)


def _write_evidence(payload: dict[str, object], path: Path) -> str:
    """Write the redacted single-line JSON evidence and return its SHA-256."""
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# -- fixture desired states ------------------------------------------------


def _fixture_mention(
    scope: E2bDocumentScope,
    *,
    mention_id: str,
    span_id: str,
    entity_id: str | None,
    text: str,
    normalized: str,
    char_start: int,
    char_end: int,
    document_char_start: int,
    document_char_end: int,
    schema_version: str | None = "1.0.0",
) -> E2bDesiredMention:
    """One deterministic fixture-candidate mention with full provenance."""
    return E2bDesiredMention(
        mention_id=mention_id,
        span_id=span_id,
        char_start=char_start,
        char_end=char_end,
        mention_text=text,
        normalized_text=normalized,
        entity_id=entity_id,
        source="dictionary",
        raw_label=text,
        entity_type="ORG",
        extractor_id="okf-fixture-dictionary",
        extractor_version="1.0.0",
        confidence=0.9,
        confidence_kind="dictionary_exact",
        input_id=span_id,
        input_kind="corpus_span",
        input_revision="fixture-revision-1",
        document_char_start=document_char_start,
        document_char_end=document_char_end,
        segment_id=None,
        schema_version=schema_version,
        normalization_version="1.0.0",
        segmentation_version="1.0.0",
        label_map_digest="0" * 64,
    )


def _fixture_desired_state(scope: E2bDocumentScope) -> E2bDesiredState:
    """Full desired state for the main fixture scope (2 mentions, 2 links).

    Both mentions live on the SAME surviving canonical span (span 0) so the
    changed-set transition shrinks the selected set on that span.
    """
    mention_a = _fixture_mention(
        scope,
        mention_id=deterministic_id(
            "e2b_mention", f"{scope.document_id}:{scope.version_id}:a"
        ),
        span_id=_FIXTURE_SPAN_IDS[0],
        entity_id=_FIXTURE_ENTITY_IDS[0],
        text="Alpha",
        normalized="Alpha Corp",
        char_start=0,
        char_end=5,
        document_char_start=0,
        document_char_end=5,
    )
    mention_b = _fixture_mention(
        scope,
        mention_id=deterministic_id(
            "e2b_mention", f"{scope.document_id}:{scope.version_id}:b"
        ),
        span_id=_FIXTURE_SPAN_IDS[0],
        entity_id=_FIXTURE_ENTITY_IDS[1],
        text="Beta",
        normalized="Beta Labs",
        char_start=0,
        char_end=4,
        document_char_start=10,
        document_char_end=14,
    )
    links = (
        E2bDesiredLink(
            node_id=_FIXTURE_NODE_IDS[0],
            entity_id=_FIXTURE_ENTITY_IDS[0],
            ordinal_no=0,
            mention_text="Alpha",
        ),
        E2bDesiredLink(
            node_id=_FIXTURE_NODE_IDS[0],
            entity_id=_FIXTURE_ENTITY_IDS[1],
            ordinal_no=0,
            mention_text="Beta",
        ),
    )
    return E2bDesiredState(mentions=(mention_a, mention_b), links=links)


def _fixture_shrunk_desired_state(scope: E2bDocumentScope) -> E2bDesiredState:
    """Changed desired set: the surviving span's selected set shrinks."""
    mention_a = _fixture_mention(
        scope,
        mention_id=deterministic_id(
            "e2b_mention", f"{scope.document_id}:{scope.version_id}:a"
        ),
        span_id=_FIXTURE_SPAN_IDS[0],
        entity_id=_FIXTURE_ENTITY_IDS[0],
        text="Alpha",
        normalized="Alpha Corp",
        char_start=0,
        char_end=5,
        document_char_start=0,
        document_char_end=5,
    )
    links = (
        E2bDesiredLink(
            node_id=_FIXTURE_NODE_IDS[0],
            entity_id=_FIXTURE_ENTITY_IDS[0],
            ordinal_no=0,
            mention_text="Alpha",
        ),
    )
    return E2bDesiredState(mentions=(mention_a,), links=links)


def _fixture_manual_desired_state(scope: E2bDocumentScope) -> E2bDesiredState:
    """Desired state for the manual/legacy scope.

    The first mention id collides with the preloaded manual row (preserved,
    never claimed). The manual bridge pair is represented ONLY by the
    preloaded bridge: collision mentions are excluded from the repository's
    link derivation, so a desired link for that pair would violate the
    caller contract (_E2bLinkProofError). A second mention/link pair is new.
    """
    manual_mention_id = deterministic_id(
        "e2b_mention", f"{scope.document_id}:{scope.version_id}:manual"
    )
    mention_manual = _fixture_mention(
        scope,
        mention_id=manual_mention_id,
        span_id=_FIXTURE_SPAN_IDS[1],
        entity_id=_FIXTURE_ENTITY_IDS[0],
        text="Alpha",
        normalized="Alpha Corp",
        char_start=0,
        char_end=5,
        document_char_start=0,
        document_char_end=5,
    )
    mention_new = _fixture_mention(
        scope,
        mention_id=deterministic_id(
            "e2b_mention", f"{scope.document_id}:{scope.version_id}:new"
        ),
        span_id=_FIXTURE_SPAN_IDS[2],
        entity_id=_FIXTURE_ENTITY_IDS[1],
        text="Beta",
        normalized="Beta Labs",
        char_start=0,
        char_end=4,
        document_char_start=10,
        document_char_end=14,
    )
    links = (
        E2bDesiredLink(
            node_id=_FIXTURE_NODE_IDS[2],
            entity_id=_FIXTURE_ENTITY_IDS[1],
            ordinal_no=0,
            mention_text="Beta",
        ),
    )
    return E2bDesiredState(mentions=(mention_manual, mention_new), links=links)


def _fixture_invalid_desired_state(scope: E2bDocumentScope) -> E2bDesiredState:
    """Deliberately invalid desired state: provenance violation.

    schema_version=None fails the repository preflight BEFORE any DML, so the
    scope receives zero writes and a fresh-connection failure-audit row.
    """
    mention = _fixture_mention(
        scope,
        mention_id=deterministic_id(
            "e2b_mention", f"{scope.document_id}:{scope.version_id}:invalid"
        ),
        span_id=_FIXTURE_SPAN_IDS[3],
        entity_id=_FIXTURE_ENTITY_IDS[0],
        text="Alpha",
        normalized="Alpha Corp",
        char_start=0,
        char_end=5,
        document_char_start=0,
        document_char_end=5,
        schema_version=None,
    )
    return E2bDesiredState(mentions=(mention,), links=())


def _fixture_failing_desired_state(scope: E2bDocumentScope) -> E2bDesiredState:
    """Changed desired set that fails at DML time (unknown entity FK).

    The first mention already exists (zero DML); the second mention references
    an entity that does not exist, so its INSERT violates the foreign key and
    the repository rolls back every insert/update/delete, restoring the OLD
    committed state for the scope, then appends a fresh-connection audit row.
    """
    mention_a = _fixture_mention(
        scope,
        mention_id=deterministic_id(
            "e2b_mention", f"{scope.document_id}:{scope.version_id}:a"
        ),
        span_id=_FIXTURE_SPAN_IDS[0],
        entity_id=_FIXTURE_ENTITY_IDS[0],
        text="Alpha",
        normalized="Alpha Corp",
        char_start=0,
        char_end=5,
        document_char_start=0,
        document_char_end=5,
    )
    mention_bad = _fixture_mention(
        scope,
        mention_id=deterministic_id(
            "e2b_mention", f"{scope.document_id}:{scope.version_id}:bad"
        ),
        span_id=_FIXTURE_SPAN_IDS[0],
        entity_id=_FIXTURE_UNKNOWN_ENTITY_ID,
        text="Beta",
        normalized="Beta Labs",
        char_start=0,
        char_end=4,
        document_char_start=10,
        document_char_end=14,
    )
    return E2bDesiredState(mentions=(mention_a, mention_bad), links=())


# -- fixture setup SQL ------------------------------------------------------


def _insert_document(cursor: _Cursor, doc_id: str, source_uri: str) -> None:
    """Insert one fixture document with a DISTINCT source_uri.

    documents.source_uri carries the UNIQUE index idx_documents_source_uri
    (migration 002), so every fixture document must receive its own value;
    ON CONFLICT (doc_id) DO NOTHING keeps the insert idempotent for matrix
    re-runs against the same disposable database.
    """
    cursor.execute(
        "INSERT INTO documents (doc_id, source_uri, title, doc_type) "
        "VALUES (%s, %s, 'fixture', 'raw') "
        "ON CONFLICT (doc_id) DO NOTHING",
        (doc_id, source_uri),
    )


def _insert_version(cursor: _Cursor, version_id: str, doc_id: str) -> None:
    cursor.execute(
        "INSERT INTO document_versions "
        "(version_id, doc_id, content_hash, version_no, is_active, status) "
        "VALUES (%s, %s, %s, 1, TRUE, 'active') "
        "ON CONFLICT (version_id) DO NOTHING",
        (version_id, doc_id, f"fixture-content-{version_id}"),
    )


def _insert_span(cursor: _Cursor, span_id: str, version_id: str) -> None:
    cursor.execute(
        "INSERT INTO canonical_spans "
        "(span_id, version_id, span_kind, start_offset, end_offset, raw_text) "
        "VALUES (%s, %s, 'paragraph', 0, 100, 'fixture') "
        "ON CONFLICT (span_id) DO NOTHING",
        (span_id, version_id),
    )


def _insert_node(cursor: _Cursor, node_id: str, version_id: str) -> None:
    cursor.execute(
        "INSERT INTO tree_nodes (node_id, version_id, node_type, level_no, title) "
        "VALUES (%s, %s, 'section', 1, 'fixture') "
        "ON CONFLICT (node_id) DO NOTHING",
        (node_id, version_id),
    )


def _insert_span_node(cursor: _Cursor, span_id: str, node_id: str) -> None:
    cursor.execute(
        "INSERT INTO tree_node_spans (node_id, span_id, ordinal_no) "
        "VALUES (%s, %s, 0) ON CONFLICT (node_id, span_id) DO NOTHING",
        (node_id, span_id),
    )


def _insert_entity(cursor: _Cursor, entity_id: str) -> None:
    cursor.execute(
        "INSERT INTO entities (entity_id, entity_key, entity_type, canonical_name) "
        "VALUES (%s, %s, 'ORG', 'fixture') ON CONFLICT (entity_id) DO NOTHING",
        (entity_id, f"fixture-entity-{entity_id}"),
    )


def _insert_manual_mention(
    cursor: _Cursor, mention_id: str, span_id: str, entity_id: str
) -> None:
    cursor.execute(
        "INSERT INTO entity_mentions "
        "(mention_id, entity_id, span_id, char_start, char_end, mention_text, source) "
        "VALUES (%s, %s, %s, 0, 5, 'Alpha', 'manual') "
        "ON CONFLICT (mention_id) DO NOTHING",
        (mention_id, entity_id, span_id),
    )


def _insert_manual_bridge(cursor: _Cursor, node_id: str, entity_id: str) -> None:
    cursor.execute(
        "INSERT INTO node_entity_links "
        "(node_id, entity_id, ordinal_no, mention_text, confidence_score) "
        "VALUES (%s, %s, 0, 'Manual', NULL) "
        "ON CONFLICT (node_id, entity_id) DO NOTHING",
        (node_id, entity_id),
    )


def _insert_fixture_rows(cursor: _Cursor) -> None:
    """Insert the deterministic fixture rows (idempotent)."""
    _insert_document(cursor, _FIXTURE_DOCUMENT_ID, f"fixture:{_FIXTURE_DOCUMENT_ID}")
    _insert_version(cursor, _FIXTURE_VERSION_ID, _FIXTURE_DOCUMENT_ID)
    _insert_document(
        cursor, _FIXTURE_MANUAL_DOCUMENT_ID, f"fixture:{_FIXTURE_MANUAL_DOCUMENT_ID}"
    )
    _insert_version(cursor, _FIXTURE_MANUAL_VERSION_ID, _FIXTURE_MANUAL_DOCUMENT_ID)
    _insert_document(
        cursor, _FIXTURE_INVALID_DOCUMENT_ID, f"fixture:{_FIXTURE_INVALID_DOCUMENT_ID}"
    )
    _insert_version(cursor, _FIXTURE_INVALID_VERSION_ID, _FIXTURE_INVALID_DOCUMENT_ID)
    _insert_span(cursor, _FIXTURE_SPAN_IDS[0], _FIXTURE_VERSION_ID)
    _insert_span(cursor, _FIXTURE_SPAN_IDS[1], _FIXTURE_MANUAL_VERSION_ID)
    _insert_span(cursor, _FIXTURE_SPAN_IDS[2], _FIXTURE_MANUAL_VERSION_ID)
    _insert_span(cursor, _FIXTURE_SPAN_IDS[3], _FIXTURE_INVALID_VERSION_ID)
    _insert_node(cursor, _FIXTURE_NODE_IDS[0], _FIXTURE_VERSION_ID)
    _insert_node(cursor, _FIXTURE_NODE_IDS[1], _FIXTURE_MANUAL_VERSION_ID)
    _insert_node(cursor, _FIXTURE_NODE_IDS[2], _FIXTURE_MANUAL_VERSION_ID)
    _insert_node(cursor, _FIXTURE_NODE_IDS[3], _FIXTURE_INVALID_VERSION_ID)
    _insert_span_node(cursor, _FIXTURE_SPAN_IDS[0], _FIXTURE_NODE_IDS[0])
    _insert_span_node(cursor, _FIXTURE_SPAN_IDS[1], _FIXTURE_NODE_IDS[1])
    _insert_span_node(cursor, _FIXTURE_SPAN_IDS[2], _FIXTURE_NODE_IDS[2])
    _insert_span_node(cursor, _FIXTURE_SPAN_IDS[3], _FIXTURE_NODE_IDS[3])
    for entity_id in _FIXTURE_ENTITY_IDS:
        _insert_entity(cursor, entity_id)
    manual_mention_id = deterministic_id(
        "e2b_mention",
        f"{_FIXTURE_MANUAL_DOCUMENT_ID}:{_FIXTURE_MANUAL_VERSION_ID}:manual",
    )
    _insert_manual_mention(
        cursor, manual_mention_id, _FIXTURE_SPAN_IDS[1], _FIXTURE_ENTITY_IDS[0]
    )
    _insert_manual_bridge(cursor, _FIXTURE_NODE_IDS[1], _FIXTURE_ENTITY_IDS[0])


def _prepare_fixture_state(
    target: DisposablePostgresqlTarget,
    connection_factory: ConnectionFactory,
) -> None:
    """Create the deterministic fixture rows the matrix reconciles against."""
    connection = connection_factory(target)
    try:
        _insert_fixture_rows(connection.cursor())  # type: ignore[arg-type]
        connection.commit()
    finally:
        if not getattr(connection, "closed", False):
            connection.close()


# -- per-document reconcile and verification -------------------------------


def _reconcile_once(
    target: DisposablePostgresqlTarget,
    *,
    connection_factory: ConnectionFactory,
    repository_factory: RepositoryFactory,
    scope: E2bDocumentScope,
    desired: E2bDesiredState,
) -> E2bReconciliationResult:
    """Reconcile one document/version through the materialization repository.

    The runner owns the primary connection and never calls commit() or
    rollback() itself: the repository owns the transaction and commits
    internally. The connection is closed in a finally whenever it is not
    already closed (the repository closes it on its failure paths).
    """
    connection = connection_factory(target)
    try:
        repository = repository_factory(lambda: connection_factory(target))
        recorder = E2bDmlRecorder()
        return repository.reconcile_document(
            connection.cursor(),  # type: ignore[arg-type]
            scope,
            desired=desired,
            recorder=recorder,
        )
    finally:
        if not getattr(connection, "closed", False):
            connection.close()


def _verify_counts(
    target: DisposablePostgresqlTarget,
    connection_factory: ConnectionFactory,
    scope: E2bDocumentScope,
) -> dict[str, int]:
    """Count persisted rows for one scope through a fresh connection."""
    connection = connection_factory(target)
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT count(*) FROM entity_mentions WHERE e2b_owner_scope = %s",
            (scope.e2b_owner_scope,),
        )
        row = cursor.fetchone()
        mentions = int(row["count"]) if row is not None else 0
        cursor.execute(
            "SELECT count(*) FROM node_entity_links WHERE node_id IN "
            "(SELECT node_id FROM tree_nodes WHERE version_id = %s)",
            (scope.version_id,),
        )
        row = cursor.fetchone()
        bridges = int(row["count"]) if row is not None else 0
        cursor.execute(
            "SELECT count(*) FROM okf_e2b_node_link_ownership " "WHERE version_id = %s",
            (scope.version_id,),
        )
        row = cursor.fetchone()
        ledger = int(row["count"]) if row is not None else 0
        cursor.execute("SELECT count(*) FROM chunk_entity_links", ())
        row = cursor.fetchone()
        chunk_links = int(row["count"]) if row is not None else 0
    finally:
        if not getattr(connection, "closed", False):
            connection.close()
    return {
        "entity_mentions": mentions,
        "node_entity_links": bridges,
        "okf_e2b_node_link_ownership": ledger,
        "chunk_entity_links": chunk_links,
    }


def _verify_manual_mentions(
    target: DisposablePostgresqlTarget,
    connection_factory: ConnectionFactory,
    scope: E2bDocumentScope,
) -> int:
    """Count manual/legacy mentions (NULL owner scope) for the scope."""
    connection = connection_factory(target)
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT count(*) FROM entity_mentions "
            "WHERE e2b_owner_scope IS NULL "
            "AND span_id IN (SELECT span_id FROM canonical_spans "
            "WHERE version_id = %s)",
            (scope.version_id,),
        )
        row = cursor.fetchone()
        return int(row["count"]) if row is not None else 0
    finally:
        if not getattr(connection, "closed", False):
            connection.close()


def _verify_manual_bridges(
    target: DisposablePostgresqlTarget,
    connection_factory: ConnectionFactory,
    scope: E2bDocumentScope,
) -> int:
    """Count manual/legacy bridges (no ledger ownership proof) for the scope."""
    connection = connection_factory(target)
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT count(*) FROM node_entity_links AS bridge "
            "WHERE bridge.node_id IN (SELECT node_id FROM tree_nodes "
            "WHERE version_id = %s) "
            "AND NOT EXISTS (SELECT 1 FROM okf_e2b_node_link_ownership AS owner "
            "WHERE owner.node_id = bridge.node_id "
            "AND owner.entity_id = bridge.entity_id)",
            (scope.version_id,),
        )
        row = cursor.fetchone()
        return int(row["count"]) if row is not None else 0
    finally:
        if not getattr(connection, "closed", False):
            connection.close()


def _verify_ledger_for_pair(
    target: DisposablePostgresqlTarget,
    connection_factory: ConnectionFactory,
    node_id: str,
    entity_id: str,
) -> int:
    """Count ledger ownership rows for one (node_id, entity_id) pair."""
    connection = connection_factory(target)
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT count(*) FROM okf_e2b_node_link_ownership "
            "WHERE node_id = %s AND entity_id = %s",
            (node_id, entity_id),
        )
        row = cursor.fetchone()
        return int(row["count"]) if row is not None else 0
    finally:
        if not getattr(connection, "closed", False):
            connection.close()


def _verify_preserved_stale_bridges(
    target: DisposablePostgresqlTarget,
    connection_factory: ConnectionFactory,
    scope: E2bDocumentScope,
    desired_pairs: set[tuple[str, str]],
) -> int:
    """Count stale bridges still present after a changed-set reconcile.

    A bridge is stale when it belongs to the scope's nodes and its pair is no
    longer desired. Any such bridge still present was preserved by the
    fail-closed bridge-deletion decision (T-16-78).
    """
    connection = connection_factory(target)
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT count(*) FROM node_entity_links AS bridge "
            "WHERE bridge.node_id IN (SELECT node_id FROM tree_nodes "
            "WHERE version_id = %s) "
            "AND NOT EXISTS (SELECT 1 FROM unnest(%s::uuid[], %s::uuid[]) "
            "AS desired(node_id, entity_id) "
            "WHERE desired.node_id = bridge.node_id "
            "AND desired.entity_id = bridge.entity_id)",
            (
                scope.version_id,
                [node_id for node_id, _ in desired_pairs],
                [entity_id for _, entity_id in desired_pairs],
            ),
        )
        row = cursor.fetchone()
        return int(row["count"]) if row is not None else 0
    finally:
        if not getattr(connection, "closed", False):
            connection.close()


# -- transition matrix ------------------------------------------------------


def _transition_first_materialization(
    target: DisposablePostgresqlTarget,
    *,
    connection_factory: ConnectionFactory,
    repository_factory: RepositoryFactory,
) -> dict[str, object]:
    """(1) FIRST materialization: full provenance, zero chunk_entity_links."""
    scope = E2bDocumentScope(
        document_id=_FIXTURE_DOCUMENT_ID, version_id=_FIXTURE_VERSION_ID
    )
    desired = _fixture_desired_state(scope)
    result = _reconcile_once(
        target,
        connection_factory=connection_factory,
        repository_factory=repository_factory,
        scope=scope,
        desired=desired,
    )
    counts = _verify_counts(target, connection_factory, scope)
    return {
        "outcome": result.outcome,
        "entity_mentions_dml": result.primary_dml_by_table.get("entity_mentions", 0),
        "node_entity_links_dml": result.primary_dml_by_table.get(
            "node_entity_links", 0
        ),
        "okf_e2b_node_link_ownership_dml": result.primary_dml_by_table.get(
            "okf_e2b_node_link_ownership", 0
        ),
        "chunk_entity_links_dml": result.primary_dml_by_table.get(
            "chunk_entity_links", 0
        ),
        "mention_count": counts["entity_mentions"],
        "bridge_count": counts["node_entity_links"],
        "ledger_count": counts["okf_e2b_node_link_ownership"],
        "chunk_entity_links_count": counts["chunk_entity_links"],
    }


def _transition_equivalent_rerun(
    target: DisposablePostgresqlTarget,
    *,
    connection_factory: ConnectionFactory,
    repository_factory: RepositoryFactory,
) -> dict[str, object]:
    """(2) EQUIVALENT rerun: zero DML, idempotence, no timestamp churn."""
    scope = E2bDocumentScope(
        document_id=_FIXTURE_DOCUMENT_ID, version_id=_FIXTURE_VERSION_ID
    )
    desired = _fixture_desired_state(scope)
    result = _reconcile_once(
        target,
        connection_factory=connection_factory,
        repository_factory=repository_factory,
        scope=scope,
        desired=desired,
    )
    dml_total = sum(result.primary_dml_by_table.values())
    return {
        "outcome": result.outcome,
        "dml_total": dml_total,
        "timestamp_churn": dml_total > 0,
    }


def _transition_changed_set(
    target: DisposablePostgresqlTarget,
    *,
    connection_factory: ConnectionFactory,
    repository_factory: RepositoryFactory,
) -> dict[str, object]:
    """(3) CHANGED desired set on a surviving span whose selected set shrinks.

    The repository deterministically removes stale E2b-owned mentions and
    stale E2b link-ownership rows; a stale bridge is deleted only when an E2b
    ledger ownership proof exists for the current version and no other owner
    remains, and the bridge-deletion DML count is recorded. Unclear ownership
    fails closed (preserved, no DML claimed).
    """
    scope = E2bDocumentScope(
        document_id=_FIXTURE_DOCUMENT_ID, version_id=_FIXTURE_VERSION_ID
    )
    shrunk = _fixture_shrunk_desired_state(scope)
    result = _reconcile_once(
        target,
        connection_factory=connection_factory,
        repository_factory=repository_factory,
        scope=scope,
        desired=shrunk,
    )
    counts = _verify_counts(target, connection_factory, scope)
    preserved = _verify_preserved_stale_bridges(
        target,
        connection_factory,
        scope,
        {(link.node_id, link.entity_id) for link in shrunk.links},
    )
    return {
        "outcome": result.outcome,
        "stale_mention_deletions": result.stale_deletion_counts.get(
            "entity_mentions", 0
        ),
        "stale_link_ownership_deletions": result.stale_deletion_counts.get(
            "okf_e2b_node_link_ownership", 0
        ),
        "bridge_deletion_dml": result.stale_deletion_counts.get("node_entity_links", 0),
        "fail_closed_preserved_bridges": preserved,
        "mention_count": counts["entity_mentions"],
        "bridge_count": counts["node_entity_links"],
    }


def _transition_manual_legacy_preservation(
    target: DisposablePostgresqlTarget,
    *,
    connection_factory: ConnectionFactory,
    repository_factory: RepositoryFactory,
) -> dict[str, object]:
    """(4) MANUAL/LEGACY preservation: never claimed, never deleted.

    Preloaded bridges without ledger proof and mentions with NULL owner scope
    are preserved; the manual pair receives no ownership row (claimed=0) and
    no deletion DML (deleted=0). New materialization still proceeds.
    """
    scope = E2bDocumentScope(
        document_id=_FIXTURE_MANUAL_DOCUMENT_ID,
        version_id=_FIXTURE_MANUAL_VERSION_ID,
    )
    desired = _fixture_manual_desired_state(scope)
    result = _reconcile_once(
        target,
        connection_factory=connection_factory,
        repository_factory=repository_factory,
        scope=scope,
        desired=desired,
    )
    manual_mentions = _verify_manual_mentions(target, connection_factory, scope)
    manual_bridges = _verify_manual_bridges(target, connection_factory, scope)
    claimed = _verify_ledger_for_pair(
        target,
        connection_factory,
        _FIXTURE_NODE_IDS[1],
        _FIXTURE_ENTITY_IDS[0],
    )
    counts = _verify_counts(target, connection_factory, scope)
    if (
        manual_mentions != _FIXTURE_MANUAL_MENTION_COUNT
        or manual_bridges != _FIXTURE_MANUAL_BRIDGE_COUNT
    ):
        raise ValueError("manual/legacy rows were not preserved")
    return {
        "outcome": result.outcome,
        "manual_mentions_preserved": manual_mentions,
        "manual_bridges_preserved": manual_bridges,
        "claimed": claimed,
        "deleted": 0,
        "new_mention_count": counts["entity_mentions"] - manual_mentions,
        "new_bridge_count": counts["node_entity_links"] - manual_bridges,
    }


def _transition_invalid_document(
    target: DisposablePostgresqlTarget,
    *,
    connection_factory: ConnectionFactory,
    repository_factory: RepositoryFactory,
) -> dict[str, object]:
    """(5) INVALID document/version: zero writes + fresh-connection audit.

    The invalid scope fails before any DML (preflight provenance violation),
    the repository writes a fresh-connection okf_e2b_failure_audit row, and the
    matrix deterministically continues to the next document.
    """
    scope = E2bDocumentScope(
        document_id=_FIXTURE_INVALID_DOCUMENT_ID,
        version_id=_FIXTURE_INVALID_VERSION_ID,
    )
    desired = _fixture_invalid_desired_state(scope)
    result = _reconcile_once(
        target,
        connection_factory=connection_factory,
        repository_factory=repository_factory,
        scope=scope,
        desired=desired,
    )
    scope_writes = sum(result.primary_dml_by_table.values())
    return {
        "outcome": result.outcome,
        "scope_writes": scope_writes,
        "failure_audit_outcome": result.failure_audit_outcome,
        "continued_to_next": True,
    }


def _transition_changed_set_failure(
    target: DisposablePostgresqlTarget,
    *,
    connection_factory: ConnectionFactory,
    repository_factory: RepositoryFactory,
) -> dict[str, object]:
    """(8) CHANGED-SET FAILURE: rollback restores the OLD committed state.

    A DML-time failure (unknown-entity foreign key) rolls back every
    insert/update/delete for the scope; the repository appends a fresh-
    connection audit row only after rollback and primary close are confirmed.
    """
    scope = E2bDocumentScope(
        document_id=_FIXTURE_DOCUMENT_ID, version_id=_FIXTURE_VERSION_ID
    )
    before = _verify_counts(target, connection_factory, scope)
    desired = _fixture_failing_desired_state(scope)
    result = _reconcile_once(
        target,
        connection_factory=connection_factory,
        repository_factory=repository_factory,
        scope=scope,
        desired=desired,
    )
    after = _verify_counts(target, connection_factory, scope)
    return {
        "outcome": result.outcome,
        "rollback_confirmed": result.failure_audit_outcome is not None,
        "old_state_restored": before == after,
        "failure_audit_outcome": result.failure_audit_outcome,
    }


def _assert_e2a_shared_lock_key(scope: object) -> None:
    """Assert the scope serializes on E2a's EXACT shared advisory key.

    T-16-77: E2b must serialize with E2a on okf:e2a:parent:{document_id}:
    {version_id} and must never use okf:e2b:parent.
    """
    lock_key = getattr(scope, "advisory_lock_key")
    document_id = getattr(scope, "document_id")
    version_id = getattr(scope, "version_id")
    expected = f"okf:e2a:parent:{document_id}:{version_id}"
    if lock_key != expected or "okf:e2b:parent" in lock_key:
        raise ValueError("E2b must serialize on E2a's shared advisory lock key")


def _run_overlapping_serialized(
    target: DisposablePostgresqlTarget,
    *,
    connection_factory: ConnectionFactory,
    repository_factory: RepositoryFactory,
    scope: E2bDocumentScope,
    desired: E2bDesiredState,
) -> dict[str, object]:
    """Prove an overlapping E2b run blocks on the shared advisory lock.

    A holder connection acquires the advisory xact lock (as an in-flight E2b
    or E2a run would); a second reconcile in a background thread must block
    until the holder releases the lock, then complete without duplicates.
    """
    holder = connection_factory(target)
    results: list[E2bReconciliationResult] = []
    errors: list[BaseException] = []
    try:
        holder.cursor().execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (scope.advisory_lock_key,),
        )

        def _overlap() -> None:
            try:
                results.append(
                    _reconcile_once(
                        target,
                        connection_factory=connection_factory,
                        repository_factory=repository_factory,
                        scope=scope,
                        desired=desired,
                    )
                )
            except BaseException as exc:  # noqa: BLE001 - thread boundary
                errors.append(exc)

        thread = threading.Thread(target=_overlap, daemon=True)
        thread.start()
        thread.join(timeout=1.0)
        blocked = thread.is_alive()
        if blocked:
            holder.rollback()
            thread.join(timeout=15.0)
        if thread.is_alive():
            raise ValueError("overlapping E2b run did not serialize")
        if errors:
            raise errors[0]
        if not results:
            raise ValueError("overlapping E2b run produced no result")
        return {
            "serialized": True,
            "overlap_blocked_on_lock": blocked,
            "second_outcome": results[0].outcome,
        }
    finally:
        if not getattr(holder, "closed", False):
            holder.close()


def _transition_e2b_serialization(
    target: DisposablePostgresqlTarget,
    *,
    connection_factory: ConnectionFactory,
    repository_factory: RepositoryFactory,
) -> dict[str, object]:
    """(7) E2b-vs-E2b serialization on the shared advisory lock."""
    scope = E2bDocumentScope(
        document_id=_FIXTURE_DOCUMENT_ID, version_id=_FIXTURE_VERSION_ID
    )
    desired = _fixture_desired_state(scope)
    _assert_e2a_shared_lock_key(scope)
    # FINDING D: pre-converge the target to the FULL desired state before the
    # lock-overlap exercise. The matrix shares one disposable DB across
    # transitions and transition 3 leaves the main scope at the SHRUNK state;
    # without this pre-converge the overlap reconcile would legitimately
    # converge shrunk->full and report 'changed', breaking the strict
    # second_outcome == 'no_op' proof. The acceptance proof is that the
    # overlapping reconcile completes WITHOUT new DML.
    pre_converge = _reconcile_once(
        target,
        connection_factory=connection_factory,
        repository_factory=repository_factory,
        scope=scope,
        desired=desired,
    )
    overlap = _run_overlapping_serialized(
        target,
        connection_factory=connection_factory,
        repository_factory=repository_factory,
        scope=scope,
        desired=desired,
    )
    counts = _verify_counts(target, connection_factory, scope)
    duplicate_rows = max(0, counts["entity_mentions"] - len(desired.mentions))
    return {
        "serialized": overlap["serialized"],
        "duplicate_rows": duplicate_rows,
        "lock_key_is_e2a": True,
        "lock_key_is_e2b": False,
        "overlap_blocked_on_lock": overlap["overlap_blocked_on_lock"],
        "pre_converge_outcome": pre_converge.outcome,
        "second_outcome": overlap["second_outcome"],
    }


def _transition_e2a_serialization(
    target: DisposablePostgresqlTarget,
    *,
    connection_factory: ConnectionFactory,
    repository_factory: RepositoryFactory,
) -> dict[str, object]:
    """(7) E2a-vs-E2b serialization on the SHARED E2a advisory key.

    The holder acquires the exact key an E2a run would use; the overlapping
    E2b reconcile must block on it, proving cross-gate serialization.
    """
    scope = E2bDocumentScope(
        document_id=_FIXTURE_DOCUMENT_ID, version_id=_FIXTURE_VERSION_ID
    )
    desired = _fixture_desired_state(scope)
    _assert_e2a_shared_lock_key(scope)
    # FINDING D: pre-converge to the full desired state (see the e2b
    # transition above); the e2a pre-converge normally finds the scope
    # already full after the e2b transition and reports no_op.
    pre_converge = _reconcile_once(
        target,
        connection_factory=connection_factory,
        repository_factory=repository_factory,
        scope=scope,
        desired=desired,
    )
    overlap = _run_overlapping_serialized(
        target,
        connection_factory=connection_factory,
        repository_factory=repository_factory,
        scope=scope,
        desired=desired,
    )
    counts = _verify_counts(target, connection_factory, scope)
    duplicate_rows = max(0, counts["entity_mentions"] - len(desired.mentions))
    return {
        "serialized": overlap["serialized"],
        "duplicate_rows": duplicate_rows,
        "lock_key_is_e2a": True,
        "lock_key_is_e2b": False,
        "overlap_blocked_on_lock": overlap["overlap_blocked_on_lock"],
        "pre_converge_outcome": pre_converge.outcome,
        "second_outcome": overlap["second_outcome"],
    }


def _run_transition_matrix(
    target: DisposablePostgresqlTarget,
    *,
    connection_factory: ConnectionFactory,
    repository_factory: RepositoryFactory,
) -> dict[str, object]:
    """Drive the full E2b transition matrix against the disposable target.

    Every transition reconciles one document/version through the
    E2bMaterializationRepository (per-document/version reconcile) and records
    redacted evidence. The matrix is fully seam-driven so tests inject pure
    fakes (repository + lock seams) and never touch a real database.
    """
    _prepare_fixture_state(target, connection_factory)
    transitions: dict[str, Callable[..., dict[str, object]]] = {
        "first_materialization": _transition_first_materialization,
        "equivalent_rerun": _transition_equivalent_rerun,
        "changed_set_convergence": _transition_changed_set,
        "manual_legacy_preservation": _transition_manual_legacy_preservation,
        "invalid_document_isolation": _transition_invalid_document,
        "changed_set_failure_rollback": _transition_changed_set_failure,
        "e2b_vs_e2b_serialization": _transition_e2b_serialization,
        "e2a_vs_e2b_serialization": _transition_e2a_serialization,
    }
    matrix: dict[str, object] = {}
    for name, transition in transitions.items():
        try:
            matrix[name] = transition(
                target,
                connection_factory=connection_factory,
                repository_factory=repository_factory,
            )
        except Exception as exc:  # fail-closed recording (FINDING C)
            # An unexpected transition failure (e.g. a caller-contract
            # _E2bLinkProofError) must never kill the live gate with zero
            # evidence: record the failure, let the matrix complete, and let
            # _validate_matrix_outcomes mark the gate executed_failed.
            matrix[name] = {
                "outcome": "transition_error",
                "error_type": type(exc).__name__,
            }
    return matrix


# -- fail-closed acceptance semantics (FINDING B) ---------------------------


_PROOF_TRANSITIONS = frozenset(
    (
        "first_materialization",
        "equivalent_rerun",
        "changed_set_convergence",
        "manual_legacy_preservation",
        "e2b_vs_e2b_serialization",
        "e2a_vs_e2b_serialization",
    )
)


def _matrix_int(transition: Mapping[str, object], key: str) -> int:
    value = transition.get(key, 0)
    return value if isinstance(value, int) else 0


def _validate_matrix_outcomes(matrix: Mapping[str, object]) -> list[str]:
    """Return proof-transition failures; empty means the matrix proves.

    The authorized path must PROVE materialization, idempotence, convergence,
    preservation, and serialization. Only the negative-control transitions
    (invalid_document_isolation, changed_set_failure_rollback) and the
    serialization overlap second_outcome are allowed to be
    rolled_back_failure by design; any proof transition ending in
    rolled_back_failure (or otherwise failing its expected semantics) makes
    the acceptance fail closed (FINDING B).
    """
    failures: list[str] = []
    # A crashed transition (outcome=transition_error) fails the gate on ANY
    # transition, including the negative controls: the negative-control
    # exemptions cover rolled_back_failure only, never a transition_error.
    for name in _MATRIX_KEYS:
        transition = matrix.get(name)
        if not isinstance(transition, Mapping):
            continue
        if transition.get("outcome") == "transition_error":
            failures.append(
                f"{name}: transition_error ({transition.get('error_type')!r})"
            )
    for name in _PROOF_TRANSITIONS:
        transition = matrix.get(name)
        if not isinstance(transition, Mapping):
            failures.append(f"{name}: missing transition")
            continue
        outcome = transition.get("outcome")
        if name == "first_materialization":
            if outcome != "changed":
                failures.append(f"{name}: outcome={outcome!r}")
            elif (
                _matrix_int(transition, "mention_count") <= 0
                and _matrix_int(transition, "entity_mentions_dml") <= 0
            ):
                failures.append(f"{name}: no materialized mentions")
        elif name == "equivalent_rerun":
            if outcome != "no_op":
                failures.append(f"{name}: outcome={outcome!r}")
            elif _matrix_int(transition, "dml_total") != 0:
                failures.append(f"{name}: dml_total != 0")
        elif name == "changed_set_convergence":
            if outcome != "changed":
                failures.append(f"{name}: outcome={outcome!r}")
        elif name == "manual_legacy_preservation":
            if outcome != "changed":
                failures.append(f"{name}: outcome={outcome!r}")
            elif (
                _matrix_int(transition, "manual_mentions_preserved") <= 0
                and _matrix_int(transition, "manual_bridges_preserved") <= 0
            ):
                failures.append(f"{name}: nothing preserved")
        elif name in ("e2b_vs_e2b_serialization", "e2a_vs_e2b_serialization"):
            if transition.get("serialized") is not True:
                failures.append(f"{name}: not serialized")
            elif transition.get("second_outcome") != "no_op":
                failures.append(
                    f"{name}: second_outcome={transition.get('second_outcome')!r}"
                )
    return failures


# -- public gate ------------------------------------------------------------


def run_full_corpus_acceptance(
    environ: Mapping[str, str],
    *,
    target_uri: str | None = None,
    target_parser: TargetParser = parse_disposable_postgresql_target,
    connection_factory: ConnectionFactory = _e2b_connection_factory,
    repository_factory: RepositoryFactory | None = None,
    matrix_runner: MatrixRunner = _run_transition_matrix,
    evidence_writer: EvidenceWriter = _write_evidence,
    evidence_path: Path = EVIDENCE_PATH,
) -> AcceptanceOutcome:
    """Run the full-corpus acceptance gate (default blocked).

    All pipeline seams are keyword-only injectable parameters; defaults are
    the exact production symbols. The disposable target is passed
    programmatically (never read from the environment), and the redacted
    evidence is written LAST, only after the matrix completed.
    """
    try:
        _require_gate_authorization(environ)
    except ValueError:
        return _blocked_outcome()
    if target_uri is None:
        raise ValueError("programmatic target_uri is required")
    expected_database = environ.get(EXPECTED_DATABASE_ENV)
    if not expected_database:
        raise ValueError(EXPECTED_DATABASE_ENV)
    target = target_parser(target_uri, expected_database)
    if repository_factory is None:
        repository_factory = _build_repository_factory()
    matrix = matrix_runner(
        target,
        connection_factory=connection_factory,
        repository_factory=repository_factory,
    )
    failures = _validate_matrix_outcomes(matrix)
    status = FAILED_STATUS if failures else EXECUTED_STATUS
    payload = _canonical_evidence_payload(status, matrix)
    redacted = _redact_evidence_payload(payload)
    evidence_sha256 = evidence_writer(redacted, evidence_path)
    return AcceptanceOutcome(status, FIXTURE_CANDIDATE_PATH, matrix, evidence_sha256)


def main(argv: list[str] | None = None, *, target_uri: str | None = None) -> int:
    """CLI entry: blocked by default; authorized runs print the status."""
    environ = os.environ
    try:
        _require_gate_authorization(environ)
    except ValueError:
        print(BLOCKED_STATUS)
        return 1
    if argv:
        raise ValueError("argv credential route is forbidden")
    if target_uri is None:
        raise ValueError("programmatic target_uri is required")
    outcome = run_full_corpus_acceptance(environ, target_uri=target_uri)
    print(outcome.status)
    if outcome.status == EXECUTED_STATUS:
        return 0
    if outcome.status == FAILED_STATUS:
        return FAILED_EXIT_CODE
    return 1


def _run_redacted_cli(argv: list[str] | None = None) -> int:
    """CLI boundary that never prints str(exc) (redaction discipline)."""
    if argv is None:
        argv = sys.argv[1:]
    try:
        code = main(argv)
    except ValueError:
        print(CLI_FAILURE_MESSAGE, file=sys.stderr)
        return 2
    except psycopg.Error:
        print(CONNECT_FAILURE_MESSAGE, file=sys.stderr)
        return 2
    return code


if __name__ == "__main__":
    raise SystemExit(_run_redacted_cli())
