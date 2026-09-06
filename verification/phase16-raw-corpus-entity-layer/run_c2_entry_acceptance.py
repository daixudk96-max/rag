"""C2 entry acceptance gate: conditional coref-cluster entry after C1 closed.

Phase 16-17 Task 3 runner. When the single-use authorization
(OKF_E2B_C2_ENTRY_AUTHORIZED=1) and the C1 CLOSED precondition both hold, the
gate applies the root migration catalog on a disposable loopback database,
runs the coref rules engine over selected resolved mentions from the
materialized corpus, proves default-off parity, materializes normalized
coref clusters and exercises the per-cluster tombstone, then writes redacted
evidence. Otherwise it records exactly skipped_not_entered with a redacted
reason and zero connections or model loads; a skipped C2 is never described
as tested.

Design discipline (16-15 live rounds, non-negotiable):
* any PostgreSQL connection factory must bind row_factory=psycopg.rows.dict_row;
* proof-stage failures => gate status executed_failed with evidence ALWAYS
  written (never executed);
* unexpected exceptions inside a proof step are recorded as proof_error and
  the gate still fails closed WITH evidence (a live gate never dies with
  zero evidence);
* C1 CLOSED is proven by reading and hashing the archived 16-15 success
  evidence; the sha256 below is recorded in the 16-15 summary as the final
  round-5 artifact. Missing or contradictory evidence fails closed;
* evidence is allowlist-validated and redacted: no connection string, no
  credential, no corpus text, never the deployment connection-string env;
* single-use disposable target; the gate never repeats itself.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

import psycopg
import psycopg.rows

from llamaindex_runtime.entity.contracts import (
    ConfidenceKind,
    MentionCandidate,
    canonical_json,
    deterministic_id,
)
from llamaindex_runtime.entity.coref_rules import (
    COREF_CLUSTER_ID_KIND,
    RULES_RESOLVER_MODE,
    CorefCluster,
    CorefClusterSet,
    build_coref_clusters,
)
from llamaindex_runtime.entity.merger import OccurrenceKey
from llamaindex_runtime.entity.resolution import ResolutionDecision, ResolutionResult
from llamaindex_runtime.registry.migration_catalog import FULL_MIGRATION_CATALOG
from scripts._rebuild_database_connection import (
    DisposablePostgresqlTarget,
    parse_disposable_postgresql_target,
    runtime_connection_factory,
)

VERIFICATION_DIR = Path(__file__).resolve().parent
MIGRATION_ROOT = (
    Path(__file__).resolve().parents[2]
    / "llamaindex_runtime"
    / "registry"
    / "migrations"
)
EVIDENCE_NAME = "c2_entry_evidence.md"
EVIDENCE_PATH = VERIFICATION_DIR / EVIDENCE_NAME

AUTH_ENV = "OKF_E2B_C2_ENTRY_AUTHORIZED"
DISPOSABLE_ENV = "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE"
EXPECTED_DATABASE_ENV = "OKF_REBUILD_EXPECTED_DATABASE"
GATE_ROUTING_KEYS = frozenset({AUTH_ENV, DISPOSABLE_ENV, EXPECTED_DATABASE_ENV})

SKIPPED_STATUS = "skipped_not_entered"
EXECUTED_STATUS = "executed"
FAILED_STATUS = "executed_failed"
SKIPPED_EXIT_CODE = 1
FAILED_EXIT_CODE = 3

CLI_FAILURE_MESSAGE = "C2 entry acceptance refused; failure details are not disclosed"
CONNECT_FAILURE_MESSAGE = "Database connection failed; refusing C2 entry acceptance"

FIXTURE_CANDIDATE_PATH = "fixture_candidates"

C2_EVIDENCE_SCHEMA_VERSION = 1

SKIP_REASONS = frozenset(
    {"authorization_missing", "disposable_target_gate_missing", "c1_not_closed"}
)

# C1 CLOSED precondition. The sha256 below is the final round-5 artifact of
# the 16-15 full-corpus acceptance, recorded in the 16-15 summary. The
# archived evidence is verified by reading and hashing the file; a matching
# hash plus status executed plus the full 8-transition matrix proves closure.
C1_SUCCESS_EVIDENCE_SHA256 = (
    "53ae99b6e4f85223ccbfe99910a13a711d12d033670db4a408eb532068a412e3"
)
C1_EVIDENCE_CANDIDATE_NAMES = (
    "e2b_full_corpus_acceptance_evidence_executed_SUCCESS_2026-08-31.md",
    "e2b_full_corpus_acceptance_evidence_executed_2026-08-31.md",
)
C1_MATRIX_KEYS = frozenset(
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
C1_EVIDENCE_SCHEMA_VERSION = 1

COREF_RULES_VERSION = "coref-rules-1"
_C1_RESOLUTION_PRIORITY_VERSION = "e2b-resolve-v1"

_FIXTURE_DOCUMENT_ID = "c2e1d0c2-0000-4000-8000-0000c1c10001"
_FIXTURE_VERSION_ID = "c2e1d0c2-0000-4000-8000-0000c1c10002"
_FIXTURE_SPAN_IDS = (
    "c2e1d0c2-0000-4000-8000-0000c1c10003",
    "c2e1d0c2-0000-4000-8000-0000c1c10004",
)
_FIXTURE_MENTION_IDS = (
    "c2e1d0c2-0000-4000-8000-0000c1c10005",
    "c2e1d0c2-0000-4000-8000-0000c1c10006",
)
_FIXTURE_ENTITY_IDS = (
    "c2e1d0c2-0000-4000-8000-0000c1c10007",
    "c2e1d0c2-0000-4000-8000-0000c1c10008",
)
_FIXTURE_OWNER_SCOPE = f"okf:e2b:{_FIXTURE_DOCUMENT_ID}:{_FIXTURE_VERSION_ID}"
_FIXTURE_MENTION_TEXT = "Acme"
_FIXTURE_ENTITY_TYPE = "ORG"
_FIXTURE_LABEL_MAP_DIGEST = "0" * 64
_FIXTURE_CONTENT_HASH = "c2-fixture-content-hash"

_CATALOG_TAIL = ("021_ner_coref_clusters.sql", "022_keyword_fts_indexes.sql")

_SKIPPED_PAYLOAD_KEYS = frozenset({"schema_version", "status", "reason"})
_AUTHORIZED_PAYLOAD_KEYS = frozenset(
    {"schema_version", "status", "candidate_path", "c1_closure", "proof"}
)
_C1_CLOSURE_KEYS = frozenset({"status", "hash_matched", "evidence_name", "matrix_keys"})
_PROOF_STEP_KEYS = frozenset(
    {
        "catalog_applied",
        "default_off_parity",
        "rules_materialization",
        "tombstone",
        "proof_error",
    }
)
_CATALOG_APPLIED_KEYS = frozenset({"outcome", "migrations", "tail_includes_021"})
_PARITY_KEYS = frozenset(
    {"outcome", "cluster_count", "membership_count", "c2_dml_total"}
)
_MATERIALIZATION_KEYS = frozenset(
    {"outcome", "cluster_count", "membership_count", "deterministic_ids_verified"}
)
_TOMBSTONE_KEYS = frozenset(
    {"outcome", "cluster_count_tombstoned", "membership_preserved"}
)
_PROOF_ERROR_KEYS = frozenset({"outcome", "error_type"})
_PROOF_PAYLOAD_KEYS_BY_STEP = {
    "catalog_applied": _CATALOG_APPLIED_KEYS,
    "default_off_parity": _PARITY_KEYS,
    "rules_materialization": _MATERIALIZATION_KEYS,
    "tombstone": _TOMBSTONE_KEYS,
    "proof_error": _PROOF_ERROR_KEYS,
}

TargetParser = Callable[[str, str], DisposablePostgresqlTarget]
ConnectionFactory = Callable[[DisposablePostgresqlTarget], psycopg.Connection[Any]]
CatalogApplier = Callable[
    [DisposablePostgresqlTarget, ConnectionFactory, tuple[str, ...]], None
]
ResolutionReader = Callable[["ConnectionLike", str], ResolutionResult]
ProofRunner = Callable[..., dict[str, object]]
EvidenceWriter = Callable[[Mapping[str, object], Path], str]
C1ClosureProver = Callable[[Path], "C1ClosureProof"]


class ConnectionLike(Protocol):
    """Minimal database connection surface used by the proof orchestration."""

    closed: bool

    def cursor(self) -> CursorLike: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...


class CursorLike(Protocol):
    """dict-row cursor surface; fetch results are mappings (dict_row)."""

    def execute(self, query: str, params: object = ...) -> object: ...

    def fetchone(self) -> Mapping[str, Any] | None: ...

    def fetchall(self) -> list[Mapping[str, Any]]: ...


@dataclass(frozen=True)
class C1ClosureProof:
    """Result of verifying the archived 16-15 C1 success evidence."""

    closed: bool
    reason: str
    evidence_name: str = ""
    evidence_sha256: str = ""


@dataclass(frozen=True)
class C2EntryOutcome:
    """Immutable gate outcome; mirrors the 16-15 AcceptanceOutcome shape."""

    status: str
    candidate_path: str
    proof: dict[str, object]
    evidence_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "proof", dict(self.proof))


# -- C1 CLOSED precondition ------------------------------------------------


def _prove_c1_closed(verification_dir: Path) -> C1ClosureProof:
    """Prove the C1 CLOSED precondition from the archived 16-15 evidence.

    Candidate evidence names are probed in pinned order; a present candidate
    whose bytes do not hash to the recorded artifact, or whose payload is
    contradictory, fails closed IMMEDIATELY and never falls through to a
    later candidate (a present contradictory file is never shadowed). Only
    absence probes the next candidate.
    """
    for name in C1_EVIDENCE_CANDIDATE_NAMES:
        path = verification_dir / name
        if not path.is_file():
            continue
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != C1_SUCCESS_EVIDENCE_SHA256:
            return C1ClosureProof(False, "c1_evidence_contradictory", name, digest)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return C1ClosureProof(False, "c1_evidence_contradictory", name, digest)
        if not isinstance(payload, Mapping):
            return C1ClosureProof(False, "c1_evidence_contradictory", name, digest)
        if payload.get("schema_version") != C1_EVIDENCE_SCHEMA_VERSION:
            return C1ClosureProof(False, "c1_evidence_contradictory", name, digest)
        if payload.get("status") != EXECUTED_STATUS:
            return C1ClosureProof(False, "c1_evidence_not_success", name, digest)
        matrix = payload.get("matrix")
        if not isinstance(matrix, Mapping) or not C1_MATRIX_KEYS.issubset(
            matrix.keys()
        ):
            return C1ClosureProof(False, "c1_evidence_not_success", name, digest)
        return C1ClosureProof(True, "closed", name, digest)
    return C1ClosureProof(False, "c1_evidence_missing", "", "")


# -- entry gate ------------------------------------------------------------


def _entry_authorization(
    environ: Mapping[str, str], *, closure_prover: C1ClosureProver
) -> tuple[str | None, C1ClosureProof | None]:
    """Return (skip reason, closure proof); None reason means authorized.

    Deterministic precondition order: single-use authorization first, then
    the disposable-target gate, then the C1 CLOSED proof. The first failing
    precondition names the redacted skip reason; nothing else is touched.
    """
    if environ.get(AUTH_ENV) != "1":
        return "authorization_missing", None
    if environ.get(DISPOSABLE_ENV) != "1" or not environ.get(EXPECTED_DATABASE_ENV):
        return "disposable_target_gate_missing", None
    closure = closure_prover(VERIFICATION_DIR)
    if not closure.closed:
        return "c1_not_closed", closure
    return None, closure


# -- evidence --------------------------------------------------------------


def _canonical_skipped_payload(reason: str) -> dict[str, object]:
    return {
        "schema_version": C2_EVIDENCE_SCHEMA_VERSION,
        "status": SKIPPED_STATUS,
        "reason": reason,
    }


def _canonical_proof_payload(
    status: str,
    proof: Mapping[str, object],
    closure: C1ClosureProof,
) -> dict[str, object]:
    return {
        "schema_version": C2_EVIDENCE_SCHEMA_VERSION,
        "status": status,
        "candidate_path": FIXTURE_CANDIDATE_PATH,
        "c1_closure": {
            "status": EXECUTED_STATUS,
            "hash_matched": closure.closed,
            "evidence_name": closure.evidence_name,
            "matrix_keys": len(C1_MATRIX_KEYS),
        },
        "proof": dict(proof),
    }


def _redact_evidence_payload(
    payload: Mapping[str, object], *, skipped: bool = False
) -> dict[str, object]:
    """Allowlist-validate and redact an evidence payload before writing."""
    if not isinstance(payload, Mapping):
        raise ValueError("evidence payload must be a mapping")
    if skipped:
        if set(payload) != _SKIPPED_PAYLOAD_KEYS:
            raise ValueError("unexpected skipped evidence fields")
        if payload.get("schema_version") != C2_EVIDENCE_SCHEMA_VERSION:
            raise ValueError("unsupported skipped evidence schema")
        if payload.get("status") != SKIPPED_STATUS:
            raise ValueError("skipped evidence status mismatch")
        if payload.get("reason") not in SKIP_REASONS:
            raise ValueError("unsupported skip reason")
        return dict(payload)
    if set(payload) != _AUTHORIZED_PAYLOAD_KEYS:
        raise ValueError("unexpected evidence fields")
    if payload.get("schema_version") != C2_EVIDENCE_SCHEMA_VERSION:
        raise ValueError("unsupported evidence schema")
    if payload.get("status") not in {EXECUTED_STATUS, FAILED_STATUS}:
        raise ValueError("unsupported evidence status")
    if payload.get("candidate_path") != FIXTURE_CANDIDATE_PATH:
        raise ValueError("unexpected candidate path")
    closure = payload.get("c1_closure")
    if not isinstance(closure, Mapping) or set(closure) != _C1_CLOSURE_KEYS:
        raise ValueError("unexpected c1_closure fields")
    if (
        closure.get("status") != EXECUTED_STATUS
        or closure.get("hash_matched") is not True
    ):
        raise ValueError("c1 closure evidence is contradictory")
    if type(closure.get("evidence_name")) is not str or not closure["evidence_name"]:
        raise ValueError("c1 closure evidence name is missing")
    if closure.get("matrix_keys") != len(C1_MATRIX_KEYS):
        raise ValueError("c1 closure matrix keys mismatch")
    proof = payload.get("proof")
    if not isinstance(proof, Mapping):
        raise ValueError("proof must be a mapping")
    for step_name, step_payload in proof.items():
        if step_name not in _PROOF_STEP_KEYS:
            raise ValueError("unexpected proof step")
        allowed = _PROOF_PAYLOAD_KEYS_BY_STEP[step_name]
        if not isinstance(step_payload, Mapping) or set(step_payload) != allowed:
            raise ValueError("unexpected proof step fields")
    return dict(payload)


def _write_evidence(payload: Mapping[str, object], evidence_path: Path) -> str:
    """Write single-line canonical JSON evidence and return its sha256."""
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    evidence_path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _validate_proof_outcomes(proof: Mapping[str, object]) -> list[str]:
    """Fail-closed proof validation; returns a list of failure strings."""
    failures: list[str] = []
    if "proof_error" in proof:
        return ["proof step raised an unexpected error"]
    for step in (
        "catalog_applied",
        "default_off_parity",
        "rules_materialization",
        "tombstone",
    ):
        if step not in proof:
            failures.append(f"{step} missing")
    catalog_step = proof.get("catalog_applied")
    if isinstance(catalog_step, Mapping):
        if catalog_step.get("outcome") != "applied":
            failures.append("catalog_applied outcome must be applied")
        if catalog_step.get("tail_includes_021") is not True:
            failures.append("catalog_applied must prove migration 021 in the tail")
    parity = proof.get("default_off_parity")
    if isinstance(parity, Mapping):
        if parity.get("outcome") != "no_op":
            failures.append("default_off_parity outcome must be no_op")
        for key in ("cluster_count", "membership_count", "c2_dml_total"):
            if parity.get(key) != 0:
                failures.append(f"default_off_parity {key} must be zero")
    materialization = proof.get("rules_materialization")
    if isinstance(materialization, Mapping):
        if materialization.get("outcome") != "materialized":
            failures.append("rules_materialization outcome must be materialized")
        if (
            not isinstance(materialization.get("cluster_count"), int)
            or materialization["cluster_count"] < 1
        ):
            failures.append("rules_materialization cluster_count must be >= 1")
        if (
            not isinstance(materialization.get("membership_count"), int)
            or materialization["membership_count"] < 2
        ):
            failures.append("rules_materialization membership_count must be >= 2")
        if materialization.get("deterministic_ids_verified") is not True:
            failures.append("rules_materialization deterministic ids must be verified")
    tombstone = proof.get("tombstone")
    if isinstance(tombstone, Mapping):
        if tombstone.get("outcome") != "tombstoned":
            failures.append("tombstone outcome must be tombstoned")
        if (
            not isinstance(tombstone.get("cluster_count_tombstoned"), int)
            or tombstone["cluster_count_tombstoned"] < 1
        ):
            failures.append("tombstone cluster_count_tombstoned must be >= 1")
        if (
            not isinstance(tombstone.get("membership_preserved"), int)
            or tombstone["membership_preserved"] < 1
        ):
            failures.append("tombstone membership_preserved must be >= 1")
        if (
            isinstance(materialization, Mapping)
            and isinstance(materialization.get("cluster_count"), int)
            and tombstone.get("cluster_count_tombstoned")
            != materialization["cluster_count"]
        ):
            failures.append("tombstone rows must cover every materialized cluster")
    return failures


# -- migration catalog -----------------------------------------------------


def _apply_catalog(
    target: DisposablePostgresqlTarget,
    connection_factory: ConnectionFactory,
    catalog: tuple[str, ...],
) -> None:
    """Apply the ordered migration catalog on the disposable target."""
    for name in catalog:
        connection = connection_factory(target)
        try:
            cursor = connection.cursor()
            cursor.execute((MIGRATION_ROOT / name).read_text(encoding="utf-8"))
            connection.commit()
        finally:
            if not connection.closed:
                connection.close()


def _verify_catalog_tail(catalog: tuple[str, ...]) -> None:
    if catalog[-2:] != _CATALOG_TAIL or catalog.count(_CATALOG_TAIL[1]) != 1:
        raise ValueError("migration catalog tail must end with 021 and 022")


# -- fixture corpus (C1 materialized shape) --------------------------------


def _insert_fixture_document(cursor: CursorLike) -> None:
    cursor.execute(
        "INSERT INTO documents (doc_id, source_uri, title, doc_type) "
        "VALUES (%s, %s, 'fixture', 'raw') "
        "ON CONFLICT (doc_id) DO NOTHING",
        (_FIXTURE_DOCUMENT_ID, f"fixture:{_FIXTURE_DOCUMENT_ID}"),
    )
    cursor.execute(
        "INSERT INTO document_versions "
        "(version_id, doc_id, content_hash, version_no, is_active, status) "
        "VALUES (%s, %s, %s, 1, TRUE, 'active') "
        "ON CONFLICT (version_id) DO NOTHING",
        (_FIXTURE_VERSION_ID, _FIXTURE_DOCUMENT_ID, _FIXTURE_CONTENT_HASH),
    )


def _insert_fixture_span(cursor: CursorLike, span_id: str) -> None:
    cursor.execute(
        "INSERT INTO canonical_spans "
        "(span_id, version_id, span_kind, start_offset, end_offset, raw_text) "
        "VALUES (%s, %s, 'paragraph', 0, 4, 'Acme') "
        "ON CONFLICT (span_id) DO NOTHING",
        (span_id, _FIXTURE_VERSION_ID),
    )


def _insert_fixture_entity(cursor: CursorLike, entity_id: str) -> None:
    cursor.execute(
        "INSERT INTO entities (entity_id, entity_key, entity_type, canonical_name) "
        "VALUES (%s, %s, 'ORG', 'Acme') ON CONFLICT (entity_id) DO NOTHING",
        (entity_id, f"fixture-entity-{entity_id}"),
    )


def _insert_fixture_mention(
    cursor: CursorLike, mention_id: str, span_id: str, entity_id: str
) -> None:
    cursor.execute(
        "INSERT INTO entity_mentions "
        "(mention_id, entity_id, span_id, char_start, char_end, mention_text, "
        "confidence, source, input_id, input_kind, input_revision, extractor_id, "
        "extractor_version, model_id, model_revision, artifact_digest, "
        "schema_version, normalization_version, segmentation_version, "
        "label_map_digest, runtime_compatibility_id, segment_id, raw_label, "
        "entity_type, confidence_kind, e2b_owner_scope) "
        "VALUES (%s, %s, %s, 0, 4, 'Acme', NULL, 'dictionary', %s, 'corpus_span', "
        "%s, 'e2b-c2-fixture', '1.0.0', NULL, NULL, NULL, '1.0.0', '1.0.0', "
        "'1.0.0', %s, NULL, NULL, 'Acme', 'ORG', 'unavailable', %s) "
        "ON CONFLICT (mention_id) DO NOTHING",
        (
            mention_id,
            entity_id,
            span_id,
            span_id,
            _FIXTURE_CONTENT_HASH,
            _FIXTURE_LABEL_MAP_DIGEST,
            _FIXTURE_OWNER_SCOPE,
        ),
    )


def _prepare_fixture_state(connection: ConnectionLike) -> None:
    """Insert the C1-materialized-shape fixture corpus (idempotent)."""
    cursor = connection.cursor()
    _insert_fixture_document(cursor)
    for span_id, mention_id, entity_id in zip(
        _FIXTURE_SPAN_IDS, _FIXTURE_MENTION_IDS, _FIXTURE_ENTITY_IDS
    ):
        _insert_fixture_span(cursor, span_id)
        _insert_fixture_entity(cursor, entity_id)
        _insert_fixture_mention(cursor, mention_id, span_id, entity_id)
    connection.commit()


# -- resolution reader -----------------------------------------------------


def _read_resolved_mentions(
    connection: ConnectionLike, owner_scope: str
) -> ResolutionResult:
    """Read selected resolved corpus mentions into a ResolutionResult.

    The reader only consumes entity_mentions rows that carry the C2 fixture
    e2b_owner_scope, a corpus_span input kind and a resolved entity, joined
    to the span/version/document/entity provenance. Candidate invariants
    (coordinates slicing raw_text, non-model provenance, digest fields) are
    enforced by the MentionCandidate constructor, so a malformed materialized
    corpus fails closed instead of fabricating candidates.
    """
    cursor = connection.cursor()
    cursor.execute(
        "SELECT em.mention_id, em.span_id, em.entity_id, em.char_start, "
        "em.char_end, em.mention_text, em.confidence, em.source, em.input_id, "
        "em.input_kind, em.input_revision, em.extractor_id, em.extractor_version, "
        "em.model_id, em.model_revision, em.artifact_digest, em.schema_version, "
        "em.normalization_version, em.segmentation_version, em.label_map_digest, "
        "em.runtime_compatibility_id, em.segment_id, em.raw_label, em.entity_type, "
        "em.confidence_kind, cs.raw_text, dv.doc_id, cs.version_id, ent.canonical_name "
        "FROM entity_mentions AS em "
        "JOIN canonical_spans AS cs ON cs.span_id = em.span_id "
        "JOIN document_versions AS dv ON dv.version_id = cs.version_id "
        "JOIN entities AS ent ON ent.entity_id = em.entity_id "
        "WHERE em.e2b_owner_scope = %s "
        "AND em.input_kind = 'corpus_span' AND em.entity_id IS NOT NULL",
        (owner_scope,),
    )
    rows = cursor.fetchall()
    resolved: list[ResolutionDecision] = []
    chosen_priority: dict[OccurrenceKey, ConfidenceKind] = {}
    for row in rows:
        # FINDING A (live R1): psycopg3 dict_row returns uuid.UUID objects for
        # UUID columns; the entity contracts require canonical Unicode scalar
        # strings, so every UUID column value is normalized with str() (the
        # lossless canonical str(uuid) form) before it reaches any constructor
        # or occurrence key. str() on an already-str value is the identity.
        span_id = str(row["span_id"])
        segment_id = row["segment_id"]
        if segment_id is not None:
            segment_id = str(segment_id)
        entity_id = row["entity_id"]
        if entity_id is not None:
            entity_id = str(entity_id)
        candidate = MentionCandidate(
            input_id=span_id,
            input_kind="corpus_span",
            input_revision=row["input_revision"],
            normalized_text=row["raw_text"],
            span_id=span_id,
            segment_id=segment_id,
            char_start=row["char_start"],
            char_end=row["char_end"],
            mention_text=row["mention_text"],
            raw_label=row["raw_label"],
            canonical_label=row["canonical_name"],
            entity_type=row["entity_type"],
            confidence=row["confidence"],
            confidence_kind=row["confidence_kind"],
            source=row["source"],
            extractor_id=row["extractor_id"],
            extractor_version=row["extractor_version"],
            model_id=row["model_id"],
            model_revision=row["model_revision"],
            artifact_digest=row["artifact_digest"],
            schema_version=row["schema_version"],
            normalization_version=row["normalization_version"],
            segmentation_version=row["segmentation_version"],
            label_map_digest=row["label_map_digest"],
            runtime_compatibility_id=row["runtime_compatibility_id"],
            document_id=str(row["doc_id"]),
            version_id=str(row["version_id"]),
            document_revision=row["input_revision"],
            projection={"origin": "entity_mentions"},
        )
        resolved.append(ResolutionDecision(candidate=candidate, entity_id=entity_id))
        chosen_priority[
            (
                candidate.input_kind,
                span_id,
                candidate.input_revision,
                candidate.char_start,
                candidate.char_end,
                candidate.mention_text,
            )
        ] = candidate.confidence_kind
    return ResolutionResult(
        priority_version=_C1_RESOLUTION_PRIORITY_VERSION,
        resolved=tuple(resolved),
        pending=(),
        chosen_priority=chosen_priority,
    )


# -- proof steps -----------------------------------------------------------


def _fetch_row_count(cursor: CursorLike) -> int:
    """Fetch a single count(*) result; a missing row fails closed."""
    row = cursor.fetchone()
    if row is None:
        raise ValueError("verification query returned no rows")
    return int(row["row_count"])


def _count_coref_rows(connection: ConnectionLike) -> dict[str, int]:
    cursor = connection.cursor()
    cursor.execute("SELECT count(*) AS row_count FROM coref_clusters")
    clusters = _fetch_row_count(cursor)
    cursor.execute("SELECT count(*) AS row_count FROM coref_cluster_mentions")
    membership = _fetch_row_count(cursor)
    return {"clusters": clusters, "membership": membership}


def _insert_cluster_rows(connection: ConnectionLike, cluster: CorefCluster) -> None:
    """Persist one normalized cluster; plain inserts (single-use, fail closed)."""
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO coref_clusters "
        "(cluster_id, version_id, coref_rules_version, tombstoned) "
        "VALUES (%s, %s, %s, %s)",
        (
            cluster.cluster_id,
            cluster.version_id,
            COREF_RULES_VERSION,
            cluster.tombstoned,
        ),
    )
    for ordinal_no, member_span_id in enumerate(cluster.member_mention_ids):
        cursor.execute(
            "INSERT INTO coref_cluster_mentions (cluster_id, mention_id, ordinal_no) "
            "SELECT %s, em.mention_id, %s FROM entity_mentions AS em "
            "WHERE em.span_id = %s",
            (cluster.cluster_id, ordinal_no, member_span_id),
        )
    connection.commit()


def _verify_cluster_membership(
    connection: ConnectionLike, clusters: CorefClusterSet
) -> int:
    """Verify materialized rows equal the engine clusters (span mapping)."""
    total = 0
    for cluster in clusters.clusters:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT em.mention_id, em.span_id "
            "FROM coref_cluster_mentions AS ccm "
            "JOIN entity_mentions AS em ON em.mention_id = ccm.mention_id "
            "WHERE ccm.cluster_id = %s ORDER BY em.span_id",
            (cluster.cluster_id,),
        )
        rows = cursor.fetchall()
        # FINDING A parity: live dict_row yields uuid.UUID span_id values;
        # normalize to canonical str(uuid) before comparing with the engine
        # cluster members (which are canonical strings).
        actual = tuple(str(row["span_id"]) for row in rows)
        expected = tuple(sorted(cluster.member_mention_ids))
        if actual != expected:
            raise ValueError("normalized membership rows do not match cluster members")
        recomputed = deterministic_id(
            COREF_CLUSTER_ID_KIND,
            canonical_json(
                {
                    "coref_rules_version": COREF_RULES_VERSION,
                    "member_mention_ids": list(expected),
                    "version_id": cluster.version_id,
                }
            ),
        )
        if recomputed != cluster.cluster_id:
            raise ValueError("materialized cluster id is not deterministic")
        total += len(rows)
    return total


def _apply_tombstone(connection: ConnectionLike, cluster_id: str) -> None:
    cursor = connection.cursor()
    cursor.execute(
        "UPDATE coref_clusters SET tombstoned = TRUE WHERE cluster_id = %s",
        (cluster_id,),
    )
    connection.commit()


def _verify_tombstone_state(
    connection: ConnectionLike, clusters: CorefClusterSet
) -> int:
    """Verify every cluster row is soft-deleted and membership is preserved."""
    cursor = connection.cursor()
    cursor.execute(
        "SELECT cluster_id, tombstoned FROM coref_clusters ORDER BY cluster_id"
    )
    rows = cursor.fetchall()
    expected = {cluster.cluster_id for cluster in clusters.clusters}
    # FINDING A parity: live dict_row yields uuid.UUID cluster_id values;
    # normalize to canonical str(uuid) before comparing with the engine ids.
    actual = {str(row["cluster_id"]) for row in rows}
    if actual != expected:
        raise ValueError("tombstone rows do not match the cluster set")
    if any(not row["tombstoned"] for row in rows):
        raise ValueError("not every cluster row is tombstoned")
    cursor.execute("SELECT count(*) AS row_count FROM coref_cluster_mentions")
    membership = _fetch_row_count(cursor)
    expected_membership = sum(
        len(cluster.member_mention_ids) for cluster in clusters.clusters
    )
    if membership != expected_membership:
        raise ValueError("tombstone must preserve cluster membership")
    return membership


def _run_proof_steps(
    target: DisposablePostgresqlTarget,
    *,
    connection_factory: ConnectionFactory,
    catalog: tuple[str, ...] = FULL_MIGRATION_CATALOG,
    apply_catalog: CatalogApplier = _apply_catalog,
    resolution_reader: ResolutionReader = _read_resolved_mentions,
) -> dict[str, object]:
    """Run the four authorized proof steps exactly once (never repeated)."""
    apply_catalog(target, connection_factory, catalog)
    connection = connection_factory(target)
    try:
        _prepare_fixture_state(connection)
        resolved = resolution_reader(connection, _FIXTURE_OWNER_SCOPE)
        if not resolved.resolved:
            raise ValueError("no resolved mentions in the materialized corpus")
        off_set = build_coref_clusters(
            resolved,
            coref_rules_version=COREF_RULES_VERSION,
            resolver_mode="off",
        )
        if off_set.clusters:
            raise ValueError("coref rules produced clusters while resolver is off")
        parity_counts = _count_coref_rows(connection)
        if parity_counts["clusters"] != 0 or parity_counts["membership"] != 0:
            raise ValueError(
                "default-off parity violated: C2 rows exist while resolver is off"
            )
        parity = {
            "outcome": "no_op",
            "cluster_count": parity_counts["clusters"],
            "membership_count": parity_counts["membership"],
            "c2_dml_total": 0,
        }
        on_set = build_coref_clusters(
            resolved,
            coref_rules_version=COREF_RULES_VERSION,
            resolver_mode=RULES_RESOLVER_MODE,
        )
        if not on_set.clusters:
            raise ValueError("coref rules produced no clusters while resolver is on")
        for cluster in on_set.clusters:
            _insert_cluster_rows(connection, cluster)
        membership_count = _verify_cluster_membership(connection, on_set)
        materialization = {
            "outcome": "materialized",
            "cluster_count": len(on_set.clusters),
            "membership_count": membership_count,
            "deterministic_ids_verified": True,
        }
        tombstoned_set: CorefClusterSet = on_set
        for cluster in on_set.clusters:
            tombstoned_set = tombstoned_set.tombstone(cluster.cluster_id)
        tombstoned_count = 0
        for cluster in tombstoned_set.clusters:
            _apply_tombstone(connection, cluster.cluster_id)
            tombstoned_count += 1
        preserved = _verify_tombstone_state(connection, tombstoned_set)
        tombstone = {
            "outcome": "tombstoned",
            "cluster_count_tombstoned": tombstoned_count,
            "membership_preserved": preserved,
        }
        return {
            "catalog_applied": {
                "outcome": "applied",
                "migrations": len(catalog),
                "tail_includes_021": True,
            },
            "default_off_parity": parity,
            "rules_materialization": materialization,
            "tombstone": tombstone,
        }
    finally:
        if not connection.closed:
            connection.close()


# -- public gate -----------------------------------------------------------


def _c2_connection_factory(
    target: DisposablePostgresqlTarget,
) -> psycopg.Connection[Any]:
    """dict-row connection factory; every C2 connection binds dict_row."""
    connection = runtime_connection_factory(target)
    connection.row_factory = psycopg.rows.dict_row
    return connection


def run_c2_entry_acceptance(
    environ: Mapping[str, str],
    *,
    target_uri: str | None = None,
    target_parser: TargetParser = parse_disposable_postgresql_target,
    connection_factory: ConnectionFactory = _c2_connection_factory,
    catalog: tuple[str, ...] = FULL_MIGRATION_CATALOG,
    apply_catalog: CatalogApplier = _apply_catalog,
    resolution_reader: ResolutionReader = _read_resolved_mentions,
    proof_runner: ProofRunner = _run_proof_steps,
    closure_prover: C1ClosureProver = _prove_c1_closed,
    evidence_writer: EvidenceWriter = _write_evidence,
    evidence_path: Path = EVIDENCE_PATH,
) -> C2EntryOutcome:
    """Run the C2 entry gate: authorize, prove C1 CLOSED, proof, evidence."""
    skip_reason, closure = _entry_authorization(environ, closure_prover=closure_prover)
    if skip_reason is not None:
        payload = _canonical_skipped_payload(skip_reason)
        redacted = _redact_evidence_payload(payload, skipped=True)
        evidence_sha256 = evidence_writer(redacted, evidence_path)
        return C2EntryOutcome(SKIPPED_STATUS, "", {}, evidence_sha256)
    assert closure is not None, "authorized entry requires a closure proof"
    if target_uri is None:
        raise ValueError("programmatic target_uri is required")
    _verify_catalog_tail(catalog)
    expected_database = environ.get(EXPECTED_DATABASE_ENV)
    assert expected_database, "authorized entry requires the expected database"
    target = target_parser(target_uri, expected_database)
    try:
        proof = proof_runner(
            target,
            connection_factory=connection_factory,
            catalog=catalog,
            apply_catalog=apply_catalog,
            resolution_reader=resolution_reader,
        )
    except Exception as exc:  # FINDING C: never die with zero evidence
        proof = {
            "proof_error": {"outcome": "proof_error", "error_type": type(exc).__name__}
        }
    failures = _validate_proof_outcomes(proof)
    status = FAILED_STATUS if failures else EXECUTED_STATUS
    payload = _canonical_proof_payload(status, proof, closure)
    redacted = _redact_evidence_payload(payload)
    evidence_sha256 = evidence_writer(redacted, evidence_path)
    return C2EntryOutcome(status, FIXTURE_CANDIDATE_PATH, proof, evidence_sha256)


# -- CLI -------------------------------------------------------------------


def main(argv: object = None, *, target_uri: str | None = None) -> int:
    """Programmatic-only CLI entry; the target never travels through argv."""
    if argv:
        raise ValueError("argv credential route is forbidden")
    environ = os.environ
    outcome = run_c2_entry_acceptance(environ, target_uri=target_uri)
    print(outcome.status)
    if outcome.status == SKIPPED_STATUS:
        return SKIPPED_EXIT_CODE
    if outcome.status == FAILED_STATUS:
        return FAILED_EXIT_CODE
    return 0


def _run_redacted_cli(argv: object = None) -> int:
    try:
        return main(argv)
    except ValueError:
        print(CLI_FAILURE_MESSAGE, file=sys.stderr)
        return 2
    except psycopg.Error:
        print(CONNECT_FAILURE_MESSAGE, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(_run_redacted_cli())
