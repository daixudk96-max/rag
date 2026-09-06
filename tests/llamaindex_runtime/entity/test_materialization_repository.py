"""CORRECTIVE RED tests for the E2b materialization repository (Phase 16-09).

These tests run against a predicate-honoring spy cursor and a fake
primary/fresh-audit connection pair; no database, model, or network is touched.

Corrective RED contract (against the CURRENT implementation):

- The spy honors SQL predicates. A current-version ledger SELECT returns ONLY
  current-version rows, so the spy cannot mask a production query that loads
  ``okf_e2b_node_link_ownership WHERE version_id = current`` and then fails to
  see another-version owners. Bridge deletion must issue a SEPARATE bounded
  relevant-pair owner query (``node_entity_link_key = ANY(%s)``) that can see
  other-version owners; the contended bridge (current proof + other-version
  owner) must be PRESERVED, not deleted.
- ``node_entity_links`` keeps its real migration-005/012 shape
  (node_id, entity_id, ordinal_no, confidence_score, mention_text). These tests
  never assert those legal metadata columns are absent.
- Resolved mentions derive node_id through the bounded
  ``entity_mentions.span_id -> tree_node_spans.span_id -> node_id`` mapping; a
  span mapping to two nodes yields canonical links/ownership for both. Arbitrary
  prebuilt node_ids that are not derivable from any span mapping are rejected
  fail-closed (no arbitrary prebuilt node_id is accepted as sole proof).
- Existing-state reads (mentions / bridges) use FOR UPDATE and the bridge read
  is bounded; the current-version ownership inventory (``WHERE version_id = %s``)
  is a plain inventory read without FOR UPDATE, and the bounded all-version
  ``node_entity_link_key = ANY(...)`` proof is the authoritative ownership lock.
  A global ``FROM node_entity_links`` load is explicitly rejected.
- entity_mentions INSERT carries the complete migration-020 provenance column
  set: model_id, model_revision, artifact_digest, schema_version,
  normalization_version, segmentation_version, label_map_digest,
  runtime_compatibility_id. The E2bDesiredMention DTO must explicitly own all
  eight fields (single-point introspection RED). ``_mention``/``_mention_row``
  inject/project them only when the DTO exposes them today, so no other fixture
  construction fails while the fields are absent.
- A durable query_text desired mention is rejected BEFORE any SQL/DML;
  persistence is corpus-only.
- E2a-aligned uncertainty semantics: primary rollback AND close must BOTH be
  confirmed before a fresh-connection audit is written. If rollback raises, or
  primary close raises after a pre-commit failure, close primary, do NOT open
  the audit connection, do NOT claim ``rolled_back_failure``, and freeze
  ``outcome="outcome_unknown"`` with ``reconciliation_required=True``.
- If commit raises: close primary, do NOT audit, NEVER call rollback/audit, and
  freeze ``outcome="outcome_unknown"`` with ``reconciliation_required=True``.
- D5 link derivation: every desired link must be mapped by a same-scope
  resolved mention span through ``tree_node_spans``; a prebuilt node_id that is
  not derivable from any span mapping is rejected fail-closed.
- MentionCandidate rules are preserved: model provenance is complete except
  runtime_compatibility_id may be None; non-model provenance must be all None;
  segment_id fixtures are UUID-compatible or None.
- Kept: exact E2a shared advisory lock + fixed order, autocommit false before
  SQL, preflight before DML, zero-DML rerun, shrink/manual/foreign preservation,
  unresolved mentions, never chunk links, confirmed rollback -> primary close ->
  fresh audit ordering.
"""

from __future__ import annotations

from dataclasses import fields
from decimal import Decimal
from uuid import UUID

import pytest

from llamaindex_runtime.entity.contracts import MentionCandidate, deterministic_id
from llamaindex_runtime.entity.materialization_repository import (
    E2bDesiredLink,
    E2bDesiredMention,
    E2bDesiredState,
    E2bDocumentScope,
    E2bDmlRecorder,
    E2bMaterializationRepository,
    E2bReconciliationResult,
)

_DOC = str(UUID(int=1))
_VER = str(UUID(int=2))
_SPAN = str(UUID(int=3))
_NODE = str(UUID(int=4))
_ENTITY = str(UUID(int=5))
_NODE2 = str(UUID(int=6))
_ENTITY2 = str(UUID(int=7))
_NODE3 = str(UUID(int=8))
_ENTITY3 = str(UUID(int=9))
_OTHER_VER = str(UUID(int=10))
_SEGMENT = str(UUID(int=30))
_DIGEST_A = "a" * 64
_DIGEST_B = "b" * 64
_SCOPE = f"okf:e2b:{_DOC}:{_VER}"
_RUN = deterministic_id("e2b_run", f"{_DOC}:{_VER}")
_NORM = "猫猫今天开会决定"
_DOC_REV = "rev-1"

# Migration-020 complete provenance columns that E2bDesiredMention must own.
_PROVENANCE_COLUMNS = (
    "model_id",
    "model_revision",
    "artifact_digest",
    "schema_version",
    "normalization_version",
    "segmentation_version",
    "label_map_digest",
    "runtime_compatibility_id",
)

_PROVENANCE_DEFAULTS: dict[str, object] = {
    "model_id": "iic/nlp_raner_named-entity-recognition_chinese-large-generic",
    "model_revision": "snapshot-abc123",
    "artifact_digest": _DIGEST_A,
    "schema_version": "okf-entity-v1",
    "normalization_version": "nf-1",
    "segmentation_version": "seg-v1",
    "label_map_digest": _DIGEST_B,
    "runtime_compatibility_id": None,
}

# Fields the CURRENT DTO exposes; provenance fields are injected below only when
# present so fixture construction never fails on unknown kwargs today and
# automatically carries complete provenance after the DTO grows the fields.
_MENTION_FIELD_NAMES = frozenset(field.name for field in fields(E2bDesiredMention))


def _mention_id(span_id: str, start: int, end: int, label: str) -> str:
    return deterministic_id("entity_mention", f"{span_id}:{start}:{end}:{label}")


def _mention(
    start: int = 0,
    end: int = 2,
    *,
    span_id: str = _SPAN,
    entity_id: str | None = _ENTITY,
    mention_text: str | None = None,
    label: str | None = None,
    segment_id: str | None = None,
    **overrides: object,
) -> E2bDesiredMention:
    resolved_text = _NORM[start:end] if mention_text is None else mention_text
    resolved_label = resolved_text if label is None else label
    base: dict[str, object] = {
        "mention_id": _mention_id(span_id, start, end, resolved_label),
        "span_id": span_id,
        "char_start": start,
        "char_end": end,
        "mention_text": resolved_text,
        "normalized_text": _NORM,
        "entity_id": entity_id,
        "source": "model",
        "raw_label": resolved_label,
        "entity_type": "person",
        "extractor_id": "raner-large-generic",
        "extractor_version": "0.1.0",
        "confidence": None,
        "confidence_kind": "unavailable",
        "input_id": span_id,
        "input_kind": "corpus_span",
        "input_revision": _DOC_REV,
        "document_char_start": 0,
        "document_char_end": len(_NORM),
        "segment_id": segment_id,
    }
    for column in _PROVENANCE_COLUMNS:
        if column in _MENTION_FIELD_NAMES:
            base[column] = _PROVENANCE_DEFAULTS[column]
    base.update(overrides)
    return E2bDesiredMention(**base)  # type: ignore[arg-type]


def _link(
    *,
    node_id: str = _NODE,
    entity_id: str = _ENTITY,
    ordinal_no: int = 0,
    mention_text: str | None = None,
) -> E2bDesiredLink:
    return E2bDesiredLink(
        node_id=node_id,
        entity_id=entity_id,
        ordinal_no=ordinal_no,
        mention_text=mention_text or "猫猫",
    )


def _scope(document_id: str = _DOC, version_id: str = _VER) -> E2bDocumentScope:
    return E2bDocumentScope(document_id=document_id, version_id=version_id)


def _desired(*, mentions: tuple = (), links: tuple = ()) -> E2bDesiredState:
    return E2bDesiredState(mentions=tuple(mentions), links=tuple(links))


def _candidate(
    *,
    source: str = "model",
    segment_id: str | None = _SEGMENT,
    model_id: (
        str | None
    ) = "iic/nlp_raner_named-entity-recognition_chinese-large-generic",
    model_revision: str | None = "snapshot-abc123",
    artifact_digest: str | None = _DIGEST_A,
    runtime_compatibility_id: str | None = None,
    **overrides: object,
) -> MentionCandidate:
    data: dict[str, object] = {
        "input_id": _SPAN,
        "input_kind": "corpus_span",
        "input_revision": _DOC_REV,
        "normalized_text": _NORM,
        "span_id": _SPAN,
        "segment_id": segment_id,
        "char_start": 0,
        "char_end": 2,
        "mention_text": _NORM[0:2],
        "raw_label": "PER",
        "canonical_label": "person",
        "entity_type": "person",
        "confidence": None,
        "confidence_kind": "unavailable",
        "source": source,
        "extractor_id": "raner-large-generic",
        "extractor_version": "0.1.0",
        "model_id": model_id,
        "model_revision": model_revision,
        "artifact_digest": artifact_digest,
        "schema_version": "okf-entity-v1",
        "normalization_version": "nf-1",
        "segmentation_version": "seg-v1",
        "label_map_digest": _DIGEST_B,
        "runtime_compatibility_id": runtime_compatibility_id,
        "document_id": _DOC,
        "version_id": _VER,
        "document_revision": _DOC_REV,
        "projection": {"doc_id": _DOC, "version_id": _VER},
    }
    data.update(overrides)
    return MentionCandidate(**data)  # type: ignore[arg-type]


def _mention_row(
    mention: E2bDesiredMention, *, owner_scope: str | None = _SCOPE
) -> dict[str, object]:
    row = {
        "mention_id": mention.mention_id,
        "entity_id": mention.entity_id,
        "span_id": mention.span_id,
        "char_start": mention.char_start,
        "char_end": mention.char_end,
        "mention_text": mention.mention_text,
        "confidence": mention.confidence,
        "source": mention.source,
        "input_id": mention.input_id,
        "input_kind": mention.input_kind,
        "input_revision": mention.input_revision,
        "extractor_id": mention.extractor_id,
        "extractor_version": mention.extractor_version,
        "raw_label": mention.raw_label,
        "entity_type": mention.entity_type,
        "confidence_kind": mention.confidence_kind,
        "document_char_start": mention.document_char_start,
        "document_char_end": mention.document_char_end,
        "segment_id": mention.segment_id,
    }
    for column in _PROVENANCE_COLUMNS:
        if hasattr(mention, column):
            row[column] = getattr(mention, column)
    row["e2b_owner_scope"] = owner_scope
    return row


def _ledger_row(
    node_id: str,
    entity_id: str,
    *,
    version_id: str = _VER,
    owner_id: str | None = None,
) -> dict[str, object]:
    return {
        "node_entity_link_owner_id": owner_id
        or deterministic_id("e2b_link_owner", f"{node_id}:{entity_id}:{version_id}"),
        "node_id": node_id,
        "entity_id": entity_id,
        "version_id": version_id,
        "node_entity_link_key": f"{node_id}:{entity_id}",
        "e2b_run_id": _RUN,
    }


def _bridge_row(
    node_id: str, entity_id: str, *, ordinal_no: int = 0
) -> dict[str, object]:
    # Real migration-005/012 shape: node_id/entity_id/ordinal_no PLUS the legal
    # migration-012 metadata columns confidence_score and mention_text.
    return {
        "node_id": node_id,
        "entity_id": entity_id,
        "ordinal_no": ordinal_no,
        "confidence_score": None,
        "mention_text": "猫猫",
    }


def _span_row(node_id: str, span_id: str, *, ordinal_no: int = 0) -> dict[str, object]:
    return {"node_id": node_id, "span_id": span_id, "ordinal_no": ordinal_no}


def _uuid_row(row: dict[str, object], *, keys: tuple[str, ...]) -> dict[str, object]:
    """Return a copy of ``row`` with the named identity columns as ``uuid.UUID``.

    PostgreSQL ``uuid`` columns are returned by psycopg as ``uuid.UUID`` objects,
    never strings; these helpers simulate that so the production repository must
    normalize raw UUID values instead of comparing them to strings.
    """
    out = dict(row)
    for key in keys:
        value = out.get(key)
        if value is not None:
            out[key] = UUID(str(value))
    return out


def _mention_row_uuid(
    mention: E2bDesiredMention, *, owner_scope: str | None = _SCOPE
) -> dict[str, object]:
    return _uuid_row(
        _mention_row(mention, owner_scope=owner_scope),
        keys=("mention_id", "entity_id", "span_id", "segment_id"),
    )


def _ledger_row_uuid(
    node_id: str, entity_id: str, *, version_id: str = _VER
) -> dict[str, object]:
    return _uuid_row(
        _ledger_row(node_id, entity_id, version_id=version_id),
        keys=(
            "node_entity_link_owner_id",
            "node_id",
            "entity_id",
            "version_id",
            "e2b_run_id",
        ),
    )


def _bridge_row_uuid(
    node_id: str, entity_id: str, *, ordinal_no: int = 0
) -> dict[str, object]:
    return _uuid_row(
        _bridge_row(node_id, entity_id, ordinal_no=ordinal_no),
        keys=("node_id", "entity_id"),
    )


def _span_row_uuid(
    node_id: str, span_id: str, *, ordinal_no: int = 0
) -> dict[str, object]:
    return _uuid_row(
        _span_row(node_id, span_id, ordinal_no=ordinal_no),
        keys=("node_id", "span_id"),
    )


def _mention_row_decimal_confidence(
    mention: E2bDesiredMention, *, owner_scope: str | None = _SCOPE
) -> dict[str, object]:
    """Project a mention row whose NUMERIC confidence is a ``Decimal`` (psycopg)."""
    row = _mention_row(mention, owner_scope=owner_scope)
    if row.get("confidence") is not None:
        row["confidence"] = Decimal(str(row["confidence"]))
    return row


# --------------------------------------------------------------------------- #
# Spy cursor + fake primary/audit connections (no DB)
# --------------------------------------------------------------------------- #
def _normalized(statement: str) -> str:
    return " ".join(statement.lower().split())


def _is_dml(statement: str) -> bool:
    return statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))


def _dml(calls: list[tuple[str, object]]) -> list[tuple[str, object]]:
    return [
        (statement, parameters) for statement, parameters in calls if _is_dml(statement)
    ]


class _PrimaryConnection:
    autocommit = False

    def __init__(
        self,
        events: list[str],
        *,
        fail_rollback: bool = False,
        fail_commit: bool = False,
        fail_close: bool = False,
    ) -> None:
        self.events = events
        self.rolled_back = False
        self.closed = False
        self.committed = False
        self.fail_rollback = fail_rollback
        self.fail_commit = fail_commit
        self.fail_close = fail_close

    def rollback(self) -> None:
        self.events.append("primary.rollback")
        self.rolled_back = True
        if self.fail_rollback:
            raise RuntimeError("injected rollback failure")

    def close(self) -> None:
        self.events.append("primary.close")
        self.closed = True
        if self.fail_close:
            raise RuntimeError("injected close failure")

    def commit(self) -> None:
        self.events.append("primary.commit")
        if self.fail_commit:
            raise RuntimeError("injected commit failure")
        self.committed = True


class _SpyCursor:
    """Predicate-honoring no-DML spy: answers loads from rows filtered by the
    SQL parameters actually bound, so it cannot mask a production query that
    only returns current-version rows."""

    def __init__(
        self,
        connection: _PrimaryConnection,
        *,
        existing_mentions: tuple = (),
        existing_ledger: tuple = (),
        existing_bridges: tuple = (),
        existing_tree_node_spans: tuple = (),
        document_versions: list[dict[str, object]] | None = None,
        fail_statement_substring: str | None = None,
        fail_message: str = "injected changed-set DML failure",
        late_conflict_mention_ids: set[str] | None = None,
    ) -> None:
        self.connection = connection
        self.executed: list[tuple[str, object]] = []
        self.late_conflict_mention_ids = set(late_conflict_mention_ids or ())
        self.conflict_encounters: list[tuple[str, object]] = []
        self.existing_mentions = list(existing_mentions)
        self.existing_ledger = list(existing_ledger)
        self.existing_bridges = list(existing_bridges)
        self.existing_tree_node_spans = list(existing_tree_node_spans)
        self.document_versions = (
            list(document_versions)
            if document_versions is not None
            else [{"doc_id": _DOC, "version_id": _VER}]
        )
        self.fail_statement_substring = fail_statement_substring
        self.fail_message = fail_message

    def execute(self, statement: str, parameters: object | None = None) -> None:
        self.executed.append((statement, parameters))
        if (
            "insert into entity_mentions" in statement.lower()
            and parameters is not None
            and parameters
            and str(parameters[0]) in self.late_conflict_mention_ids
        ):
            # Simulate a manual/foreign row appearing at ON CONFLICT time: the
            # first INSERT parameter is mention_id (the conflict key), and a
            # late-conflicting id means the read-time collision check could not
            # see it. The test asserts the emitted SQL still refuses takeover.
            self.conflict_encounters.append((statement, parameters))
        if self.fail_statement_substring is not None:
            if self.fail_statement_substring in statement.lower():
                raise RuntimeError(self.fail_message)

    def fetchall(self) -> list[dict[str, object]]:
        statement, parameters = self.executed[-1]
        norm = _normalized(statement)
        if "from entity_mentions" in norm:
            if "mention_id = any" in norm:
                ids = {str(mention_id) for mention_id in (parameters[0] or ())}
                return [
                    dict(row)
                    for row in self.existing_mentions
                    if str(row.get("mention_id")) in ids
                ]
            owner_scope = parameters[0]
            return [
                dict(row)
                for row in self.existing_mentions
                if row.get("e2b_owner_scope") == owner_scope
            ]
        if "from okf_e2b_node_link_ownership" in norm:
            if "node_entity_link_key = any" in norm:
                keys = {str(key) for key in (parameters[0] or ())}
                return [
                    dict(row)
                    for row in self.existing_ledger
                    if str(row.get("node_entity_link_key")) in keys
                ]
            if "version_id = %s" in norm:
                version_id = parameters[0]
                return [
                    dict(row)
                    for row in self.existing_ledger
                    if row.get("version_id") == version_id
                ]
            return [dict(row) for row in self.existing_ledger]
        if "from node_entity_links" in norm:
            if "where" in norm and parameters is not None:
                node_ids = parameters[0]
                if isinstance(node_ids, (list, tuple, set, frozenset)):
                    node_set = {str(node) for node in node_ids}
                    return [
                        dict(row)
                        for row in self.existing_bridges
                        if str(row.get("node_id")) in node_set
                    ]
            return [dict(row) for row in self.existing_bridges]
        if "from tree_node_spans" in norm:
            param = parameters[0] if parameters is not None else None
            if isinstance(param, (list, tuple, set, frozenset)):
                spans = {str(span) for span in param}
                return [
                    dict(row)
                    for row in self.existing_tree_node_spans
                    if str(row.get("span_id")) in spans
                ]
            if param is not None:
                return [
                    dict(row)
                    for row in self.existing_tree_node_spans
                    if str(row.get("span_id")) == str(param)
                ]
            return [dict(row) for row in self.existing_tree_node_spans]
        if "from document_versions" in norm:
            return [dict(row) for row in self.document_versions]
        return []

    def fetchone(self) -> dict[str, object] | None:
        rows = self.fetchall()
        return rows[0] if rows else None


class _AuditCursor:
    def __init__(self, connection: _AuditConnection) -> None:
        self.connection = connection
        self.executed: list[tuple[str, object]] = []

    def execute(self, statement: str, parameters: object | None = None) -> None:
        self.executed.append((statement, parameters))
        self.connection.events.append("audit.insert")

    def fetchall(self) -> list[dict[str, object]]:
        return []

    def fetchone(self) -> None:
        return None


class _AuditConnection:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.committed = False
        self.closed = False
        self.cursor_value: _AuditCursor | None = None

    def cursor(self) -> _AuditCursor:
        self.cursor_value = _AuditCursor(self)
        return self.cursor_value

    def commit(self) -> None:
        self.events.append("audit.commit")
        self.committed = True

    def close(self) -> None:
        self.events.append("audit.close")
        self.closed = True


def _cursor(
    events: list[str],
    *,
    existing_mentions: tuple = (),
    existing_ledger: tuple = (),
    existing_bridges: tuple = (),
    existing_tree_node_spans: tuple = (),
    document_versions: list[dict[str, object]] | None = None,
    fail_statement_substring: str | None = None,
    fail_rollback: bool = False,
    fail_commit: bool = False,
    fail_close: bool = False,
    late_conflict_mention_ids: set[str] | None = None,
) -> _SpyCursor:
    return _SpyCursor(
        _PrimaryConnection(
            events,
            fail_rollback=fail_rollback,
            fail_commit=fail_commit,
            fail_close=fail_close,
        ),
        existing_mentions=existing_mentions,
        existing_ledger=existing_ledger,
        existing_bridges=existing_bridges,
        existing_tree_node_spans=existing_tree_node_spans,
        document_versions=document_versions,
        fail_statement_substring=fail_statement_substring,
        late_conflict_mention_ids=late_conflict_mention_ids,
    )


def _repository(
    events: list[str], audit_connection: _AuditConnection
) -> E2bMaterializationRepository:
    def factory() -> _AuditConnection:
        events.append("audit.connect")
        return audit_connection

    return E2bMaterializationRepository(failure_audit_connection_factory=factory)


# --------------------------------------------------------------------------- #
# Spy fidelity: predicates must be honored (spy cannot mask production bugs)
# --------------------------------------------------------------------------- #
def test_spy_ledger_select_honors_version_predicate() -> None:
    ledger = (
        _ledger_row(_NODE, _ENTITY),
        _ledger_row(_NODE, _ENTITY, version_id=_OTHER_VER),
    )
    cursor = _SpyCursor(_PrimaryConnection([]), existing_ledger=ledger)

    cursor.execute(
        "SELECT node_id, entity_id, version_id, node_entity_link_key "
        "FROM okf_e2b_node_link_ownership WHERE version_id = %s",
        (_VER,),
    )
    rows = cursor.fetchall()
    assert [row["version_id"] for row in rows] == [_VER]

    cursor.execute(
        "SELECT node_id, entity_id, version_id, node_entity_link_key "
        "FROM okf_e2b_node_link_ownership WHERE node_entity_link_key = ANY(%s)",
        ([f"{_NODE}:{_ENTITY}"],),
    )
    rows = cursor.fetchall()
    assert len(rows) == 2
    assert {row["version_id"] for row in rows} == {_VER, _OTHER_VER}


# --------------------------------------------------------------------------- #
# Lock sequence / scope / recorder validation
# --------------------------------------------------------------------------- #
def test_reconcile_acquires_e2a_shared_advisory_lock_in_fixed_order() -> None:
    events: list[str] = []
    cursor = _cursor(
        events,
        existing_tree_node_spans=(_span_row(_NODE, _SPAN),),
    )
    repository = _repository(events, _AuditConnection(events))
    scope = _scope()

    result = repository.reconcile_document(
        cursor,
        scope,
        desired=_desired(mentions=(_mention(),), links=(_link(),)),
        recorder=E2bDmlRecorder(),
    )

    assert result.outcome == "changed"
    advisory_statement, advisory_params = cursor.executed[0]
    assert "pg_advisory_xact_lock" in _normalized(advisory_statement)
    assert "hashtextextended" in _normalized(advisory_statement)
    assert advisory_params == (f"okf:e2a:parent:{_DOC}:{_VER}",)
    for _, parameters in cursor.executed:
        if parameters is not None and "okf:e2b:parent" in str(parameters):
            pytest.fail("reconcile_document must never use the okf:e2b:parent lock key")
    doc_lock_index = next(
        i
        for i, (statement, _) in enumerate(cursor.executed)
        if "from document_versions" in _normalized(statement)
        and "for update" in _normalized(statement)
    )
    dml_indexes = [
        i for i, (statement, _) in enumerate(cursor.executed) if _is_dml(statement)
    ]
    assert 0 < doc_lock_index
    assert dml_indexes and all(doc_lock_index < i for i in dml_indexes)
    assert cursor.connection.committed is True
    assert cursor.connection.closed is False


def test_reconcile_rejects_autocommit_true_before_any_statement() -> None:
    class _AutocommitPrimary(_PrimaryConnection):
        autocommit = True

    connection = _AutocommitPrimary([])
    cursor = _SpyCursor(connection)

    with pytest.raises(ValueError, match="autocommit"):
        E2bMaterializationRepository().reconcile_document(
            cursor,
            _scope(),
            desired=_desired(mentions=(_mention(),)),
            recorder=E2bDmlRecorder(),
        )

    assert cursor.executed == []


def test_reconcile_rejects_foreign_recorder_type() -> None:
    events: list[str] = []
    cursor = _cursor(events)

    with pytest.raises(TypeError):
        E2bMaterializationRepository().reconcile_document(
            cursor,
            _scope(),
            desired=_desired(mentions=(_mention(),)),
            recorder="not-an-e2b-recorder",  # type: ignore[arg-type]
        )

    assert cursor.executed == []


# --------------------------------------------------------------------------- #
# Full desired-state reconciliation: idempotence + convergence
# --------------------------------------------------------------------------- #
def test_equivalent_rerun_issues_zero_dml() -> None:
    mention = _mention()
    link = _link()
    events: list[str] = []
    cursor = _cursor(
        events,
        existing_mentions=(_mention_row(mention),),
        existing_ledger=(_ledger_row(link.node_id, link.entity_id),),
        existing_bridges=(_bridge_row(link.node_id, link.entity_id),),
        existing_tree_node_spans=(_span_row(link.node_id, mention.span_id),),
    )
    repository = _repository(events, _AuditConnection(events))

    result = repository.reconcile_document(
        cursor,
        _scope(),
        desired=_desired(mentions=(mention,), links=(link,)),
        recorder=E2bDmlRecorder(),
    )

    assert result.outcome == "no_op"
    assert _dml(cursor.executed) == []


def test_changed_set_shrink_deletes_only_stale_e2b_owned_mentions_and_link_ownership() -> (
    None
):
    surviving = _mention()
    stale = _mention(start=4, end=6)
    manual = _mention(start=6, end=8, entity_id=None)
    foreign = _mention(start=2, end=4, entity_id=None)
    link = _link()
    events: list[str] = []
    cursor = _cursor(
        events,
        existing_mentions=(
            _mention_row(surviving),
            _mention_row(stale),
            _mention_row(manual, owner_scope=None),
            _mention_row(foreign, owner_scope=f"okf:e2b:{_DOC}:{_OTHER_VER}"),
        ),
        existing_ledger=(
            _ledger_row(link.node_id, link.entity_id),
            _ledger_row(_NODE2, _ENTITY2),
        ),
        existing_bridges=(_bridge_row(link.node_id, link.entity_id),),
        existing_tree_node_spans=(_span_row(link.node_id, surviving.span_id),),
    )
    repository = _repository(events, _AuditConnection(events))

    result = repository.reconcile_document(
        cursor,
        _scope(),
        desired=_desired(mentions=(surviving,), links=(link,)),
        recorder=E2bDmlRecorder(),
    )

    dml = _dml(cursor.executed)
    mention_deletes = [
        parameters
        for statement, parameters in dml
        if "delete from entity_mentions" in _normalized(statement)
    ]
    ledger_deletes = [
        parameters
        for statement, parameters in dml
        if "delete from okf_e2b_node_link_ownership" in _normalized(statement)
    ]
    assert len(mention_deletes) == 1
    assert mention_deletes[0][0] == _SCOPE
    stale_ids = mention_deletes[0][1]
    assert stale.mention_id in stale_ids
    assert surviving.mention_id not in stale_ids
    assert manual.mention_id not in stale_ids
    assert foreign.mention_id not in stale_ids
    assert len(ledger_deletes) == 1
    assert ledger_deletes[0][0] == _VER
    stale_keys = ledger_deletes[0][1]
    assert f"{_NODE2}:{_ENTITY2}" in stale_keys
    assert f"{link.node_id}:{link.entity_id}" not in stale_keys
    assert result.stale_deletion_counts["entity_mentions"] == 1
    assert result.stale_deletion_counts["okf_e2b_node_link_ownership"] == 1


def test_unclear_or_missing_ownership_bridges_are_preserved_fail_closed() -> None:
    fresh_mention = _mention(entity_id=_ENTITY2, span_id=_SPAN)
    fresh = _link(node_id=_NODE2, entity_id=_ENTITY2)
    events: list[str] = []
    cursor = _cursor(
        events,
        existing_bridges=(
            _bridge_row(_NODE, _ENTITY),
            _bridge_row(_NODE2, _ENTITY2),
        ),
        existing_ledger=(_ledger_row(_NODE, _ENTITY, version_id=_OTHER_VER),),
        existing_tree_node_spans=(_span_row(_NODE2, _SPAN),),
    )
    repository = _repository(events, _AuditConnection(events))

    result = repository.reconcile_document(
        cursor,
        _scope(),
        desired=_desired(mentions=(fresh_mention,), links=(fresh,)),
        recorder=E2bDmlRecorder(),
    )

    assert result.outcome == "changed"
    assert not any(
        "delete from node_entity_links" in _normalized(statement)
        for statement, _ in _dml(cursor.executed)
    )
    assert not any(
        "delete from okf_e2b_node_link_ownership" in _normalized(statement)
        for statement, _ in _dml(cursor.executed)
    )
    assert result.stale_deletion_counts["node_entity_links"] == 0
    assert result.stale_deletion_counts["okf_e2b_node_link_ownership"] == 0


def test_bridge_deletion_requires_current_proof_and_reveals_other_owners() -> None:
    # (NODE, ENTITY): current-version proof, no other owner -> bridge + ledger deleted.
    # (NODE2, ENTITY2): no proof -> preserved.
    # (NODE3, ENTITY3): current-version proof BUT another-version owner remains.
    # The spy's current-version ledger SELECT returns ONLY current rows; the
    # corrected contract REQUIRES a separate bounded relevant-pair owner query
    # (node_entity_link_key = ANY(%s)) that can SEE the other-version owner, so
    # (NODE3, ENTITY3) must be PRESERVED, never deleted.
    owned = _link(node_id=_NODE, entity_id=_ENTITY)
    manual = _link(node_id=_NODE2, entity_id=_ENTITY2)
    contended = _link(node_id=_NODE3, entity_id=_ENTITY3)
    fresh_mention = _mention(entity_id=_ENTITY2, span_id=_SPAN)
    fresh = _link(node_id=_NODE2, entity_id=_ENTITY2, mention_text="新")
    events: list[str] = []
    cursor = _cursor(
        events,
        existing_bridges=(
            _bridge_row(owned.node_id, owned.entity_id),
            _bridge_row(manual.node_id, manual.entity_id),
            _bridge_row(contended.node_id, contended.entity_id),
        ),
        existing_ledger=(
            _ledger_row(owned.node_id, owned.entity_id),
            _ledger_row(contended.node_id, contended.entity_id),
            _ledger_row(contended.node_id, contended.entity_id, version_id=_OTHER_VER),
        ),
        existing_tree_node_spans=(_span_row(_NODE2, _SPAN),),
    )
    repository = _repository(events, _AuditConnection(events))

    result = repository.reconcile_document(
        cursor,
        _scope(),
        desired=_desired(mentions=(fresh_mention,), links=(fresh,)),
        recorder=E2bDmlRecorder(),
    )

    proof_queries = [
        (statement, parameters)
        for statement, parameters in cursor.executed
        if statement.lstrip().upper().startswith("SELECT")
        and "from okf_e2b_node_link_ownership" in _normalized(statement)
        and "node_entity_link_key = any" in _normalized(statement)
    ]
    assert len(proof_queries) == 1
    contended_key = f"{contended.node_id}:{contended.entity_id}"
    assert contended_key in proof_queries[0][1][0]

    bridge_deletes = [
        (statement, parameters)
        for statement, parameters in _dml(cursor.executed)
        if "delete from node_entity_links" in _normalized(statement)
    ]
    assert bridge_deletes == [
        (
            "DELETE FROM node_entity_links WHERE node_id = %s AND entity_id = %s",
            (owned.node_id, owned.entity_id),
        )
    ]
    assert result.stale_deletion_counts["node_entity_links"] == 1


def test_unresolved_mentions_persist_but_links_are_derived_only_for_resolved_spans() -> (
    None
):
    unresolved = _mention(entity_id=None)
    resolved = _mention(entity_id=_ENTITY, span_id=_SPAN)
    events: list[str] = []
    cursor = _cursor(
        events,
        existing_tree_node_spans=(_span_row(_NODE, _SPAN),),
    )
    repository = _repository(events, _AuditConnection(events))

    result = repository.reconcile_document(
        cursor,
        _scope(),
        desired=_desired(mentions=(unresolved, resolved)),
        recorder=E2bDmlRecorder(),
    )

    assert result.outcome == "changed"
    dml = _dml(cursor.executed)
    assert any(
        "insert into entity_mentions" in _normalized(statement) for statement, _ in dml
    )
    link_inserts = [
        parameters
        for statement, parameters in dml
        if "insert into node_entity_links" in _normalized(statement)
    ]
    assert len(link_inserts) == 1
    assert link_inserts[0][:2] == (_NODE, _ENTITY)
    assert not any(
        "chunk_entity_links" in _normalized(statement)
        for statement, _ in cursor.executed
    )


def test_resolved_mentions_derive_canonical_links_via_tree_node_spans() -> None:
    # A single span maps to TWO tree nodes: both canonical links + ownership
    # must be derived. No prebuilt node_id is accepted as sole proof.
    mention = _mention(entity_id=_ENTITY, span_id=_SPAN)
    events: list[str] = []
    cursor = _cursor(
        events,
        existing_tree_node_spans=(
            _span_row(_NODE, _SPAN),
            _span_row(_NODE2, _SPAN),
        ),
    )
    repository = _repository(events, _AuditConnection(events))

    result = repository.reconcile_document(
        cursor,
        _scope(),
        desired=_desired(mentions=(mention,)),
        recorder=E2bDmlRecorder(),
    )

    assert result.outcome == "changed"
    assert any(
        "from tree_node_spans" in _normalized(statement)
        for statement, _ in cursor.executed
    )
    dml = _dml(cursor.executed)
    link_inserts = [
        parameters
        for statement, parameters in dml
        if "insert into node_entity_links" in _normalized(statement)
    ]
    assert len(link_inserts) == 2
    assert {tuple(params[:2]) for params in link_inserts} == {
        (_NODE, _ENTITY),
        (_NODE2, _ENTITY),
    }
    owner_inserts = [
        parameters
        for statement, parameters in dml
        if "insert into okf_e2b_node_link_ownership" in _normalized(statement)
    ]
    assert len(owner_inserts) == 2
    assert {tuple(params[1:3]) for params in owner_inserts} == {
        (_NODE, _ENTITY),
        (_NODE2, _ENTITY),
    }


def test_arbitrary_node_id_not_derivable_from_span_is_rejected() -> None:
    # NODE3 is not present in any tree_node_spans mapping for the span -> the
    # repository must fail closed (reject) BEFORE any DML rather than write an
    # arbitrary prebuilt node_id.
    mention = _mention(entity_id=_ENTITY, span_id=_SPAN)
    rogue_link = _link(node_id=_NODE3, entity_id=_ENTITY3)
    events: list[str] = []
    cursor = _cursor(
        events,
        existing_tree_node_spans=(_span_row(_NODE, _SPAN),),
    )
    repository = _repository(events, _AuditConnection(events))

    with pytest.raises(ValueError):
        repository.reconcile_document(
            cursor,
            _scope(),
            desired=_desired(mentions=(mention,), links=(rogue_link,)),
            recorder=E2bDmlRecorder(),
        )

    assert _dml(cursor.executed) == []


# --------------------------------------------------------------------------- #
# Read shape: FOR UPDATE reads + bounded bridge query, no global bridge load.
# The current-version ownership inventory (WHERE version_id = %s) is a plain
# inventory read WITHOUT FOR UPDATE; the bounded all-version
# node_entity_link_key = ANY(...) proof is the authoritative ownership lock
# (asserted separately in test_owner_proof_is_authoritative_lock_after_bridge_not_inventory).
# --------------------------------------------------------------------------- #
def test_existing_state_reads_use_for_update_except_ownership_inventory() -> None:
    mention = _mention()
    link = _link()
    events: list[str] = []
    cursor = _cursor(
        events,
        existing_mentions=(_mention_row(mention),),
        existing_ledger=(_ledger_row(link.node_id, link.entity_id),),
        existing_bridges=(_bridge_row(link.node_id, link.entity_id),),
        existing_tree_node_spans=(_span_row(link.node_id, mention.span_id),),
    )
    repository = _repository(events, _AuditConnection(events))

    repository.reconcile_document(
        cursor,
        _scope(),
        desired=_desired(mentions=(mention,), links=(link,)),
        recorder=E2bDmlRecorder(),
    )

    mention_stmt = next(
        statement
        for statement, _ in cursor.executed
        if "from entity_mentions" in _normalized(statement)
    )
    ledger_stmt = next(
        statement
        for statement, _ in cursor.executed
        if "from okf_e2b_node_link_ownership" in _normalized(statement)
        and "node_entity_link_key = any" not in _normalized(statement)
    )
    bridge_stmts = [
        statement
        for statement, _ in cursor.executed
        if "from node_entity_links" in _normalized(statement)
    ]
    assert "for update" in _normalized(mention_stmt)
    # The current-version ownership inventory is a plain bounded inventory read
    # (deadlock-safe); the authoritative FOR UPDATE ownership lock is the later
    # bounded all-version node_entity_link_key = ANY(...) proof.
    assert "for update" not in _normalized(ledger_stmt)
    assert bridge_stmts
    assert all("for update" in _normalized(statement) for statement in bridge_stmts)
    assert all("where" in _normalized(statement) for statement in bridge_stmts)
    assert not any(
        _normalized(statement).startswith(
            "select node_id, entity_id, ordinal_no, confidence_score, "
            "mention_text from node_entity_links"
        )
        for statement in bridge_stmts
    )


# --------------------------------------------------------------------------- #
# Migration-020 complete provenance on entity_mentions
# --------------------------------------------------------------------------- #
def test_mention_insert_carries_complete_migration_020_provenance_columns() -> None:
    mention = _mention(segment_id=_SEGMENT)
    events: list[str] = []
    cursor = _cursor(events)
    repository = _repository(events, _AuditConnection(events))

    repository.reconcile_document(
        cursor,
        _scope(),
        desired=_desired(mentions=(mention,)),
        recorder=E2bDmlRecorder(),
    )

    insert_stmts = [
        statement
        for statement, _ in cursor.executed
        if "insert into entity_mentions" in _normalized(statement)
    ]
    assert insert_stmts
    insert_sql = _normalized(insert_stmts[0])
    for column in (
        "model_id",
        "model_revision",
        "artifact_digest",
        "schema_version",
        "normalization_version",
        "segmentation_version",
        "label_map_digest",
        "runtime_compatibility_id",
    ):
        assert column in insert_sql, f"entity_mentions INSERT must carry {column}"
    assert UUID(_SEGMENT)


def test_desired_mention_dto_exposes_complete_migration_020_provenance_fields() -> None:
    # The E2bDesiredMention DTO must explicitly own all eight migration-020
    # provenance fields so the projection is typed, not hidden. Today this is
    # the single-point RED for the DTO; once the DTO grows the fields, the
    # _mention/_mention_row fixtures carry them automatically.
    mention_field_names = {field.name for field in fields(E2bDesiredMention)}
    for column in _PROVENANCE_COLUMNS:
        assert (
            column in mention_field_names
        ), f"E2bDesiredMention must expose provenance column {column}"
    assert "input_kind" in mention_field_names


def test_query_text_durable_mention_rejected_before_any_sql() -> None:
    # A query_text input with slice-back-valid coordinates must still be
    # rejected as non-durable BEFORE any SQL/DML (corpus-only persistence).
    query_mention = _mention(input_kind="query_text")
    events: list[str] = []
    cursor = _cursor(events)
    repository = _repository(events, _AuditConnection(events))

    with pytest.raises(ValueError):
        repository.reconcile_document(
            cursor,
            _scope(),
            desired=_desired(mentions=(query_mention,)),
            recorder=E2bDmlRecorder(),
        )

    assert cursor.executed == []


# --------------------------------------------------------------------------- #
# Atomic failure isolation + fresh-connection audit
# --------------------------------------------------------------------------- #
def test_first_invalid_span_aborts_before_any_dml_and_audits_fresh() -> None:
    bad = _mention(mention_text="does-not-slice-back")
    events: list[str] = []
    cursor = _cursor(events)
    audit = _AuditConnection(events)
    repository = _repository(events, audit)

    result = repository.reconcile_document(
        cursor,
        _scope(),
        desired=_desired(mentions=(bad,)),
        recorder=E2bDmlRecorder(),
    )

    assert isinstance(result, E2bReconciliationResult)
    assert result.outcome == "rolled_back_failure"
    assert _dml(cursor.executed) == []
    assert cursor.connection.rolled_back is True
    assert cursor.connection.closed is True
    assert events.index("primary.rollback") < events.index("primary.close")
    assert events.index("primary.close") < events.index("audit.connect")
    assert audit.committed is True
    assert audit.closed is True
    assert result.failure_audit_outcome == "written"


def test_changed_set_failure_rolls_back_restores_original_and_audits_fresh() -> None:
    surviving = _mention()
    stale = _mention(start=4, end=6)
    events: list[str] = []
    cursor = _cursor(
        events,
        existing_mentions=(_mention_row(surviving), _mention_row(stale)),
        fail_statement_substring="delete from entity_mentions",
    )
    audit = _AuditConnection(events)
    repository = _repository(events, audit)

    result = repository.reconcile_document(
        cursor,
        _scope(),
        desired=_desired(mentions=(surviving,)),
        recorder=E2bDmlRecorder(),
    )

    assert result.outcome == "rolled_back_failure"
    assert cursor.connection.rolled_back is True
    assert cursor.connection.closed is True
    assert events.index("primary.rollback") < events.index("primary.close")
    assert events.index("primary.close") < events.index("audit.connect")
    audit_statement = audit.cursor_value.executed[0][0]
    assert "insert into okf_e2b_failure_audit" in _normalized(audit_statement)
    assert "okf_rebuild_failure_audit" not in audit_statement.lower()
    assert audit.committed is True
    assert audit.closed is True
    assert result.failure_audit_outcome == "written"


def test_rollback_failure_after_precommit_leaves_outcome_unknown_and_skips_audit() -> (
    None
):
    surviving = _mention()
    stale = _mention(start=4, end=6)
    events: list[str] = []
    cursor = _cursor(
        events,
        existing_mentions=(_mention_row(surviving), _mention_row(stale)),
        fail_statement_substring="delete from entity_mentions",
        fail_rollback=True,
    )
    audit = _AuditConnection(events)
    repository = _repository(events, audit)

    result = repository.reconcile_document(
        cursor,
        _scope(),
        desired=_desired(mentions=(surviving,)),
        recorder=E2bDmlRecorder(),
    )

    assert cursor.connection.closed is True
    assert result.outcome == "outcome_unknown"
    assert result.outcome != "rolled_back_failure"
    assert result.reconciliation_required is True
    assert "audit.connect" not in events
    assert result.failure_audit_outcome is None


def test_commit_exception_leaves_outcome_unknown_without_rollback_or_audit() -> None:
    mention = _mention()
    link = _link()
    events: list[str] = []
    cursor = _cursor(
        events,
        fail_commit=True,
        existing_tree_node_spans=(_span_row(link.node_id, mention.span_id),),
    )
    audit = _AuditConnection(events)
    repository = _repository(events, audit)

    result = repository.reconcile_document(
        cursor,
        _scope(),
        desired=_desired(mentions=(mention,), links=(link,)),
        recorder=E2bDmlRecorder(),
    )

    assert cursor.connection.closed is True
    assert "primary.rollback" not in events
    assert "audit.connect" not in events
    assert result.outcome == "outcome_unknown"
    assert result.outcome != "rolled_back_failure"
    assert result.reconciliation_required is True


def test_primary_close_failure_after_rollback_leaves_outcome_unknown_no_audit() -> None:
    # Rollback succeeded but primary close raises: close is NOT confirmed, so
    # the fresh audit must not be written and the outcome must be uncertain.
    surviving = _mention()
    stale = _mention(start=4, end=6)
    events: list[str] = []
    cursor = _cursor(
        events,
        existing_mentions=(_mention_row(surviving), _mention_row(stale)),
        fail_statement_substring="delete from entity_mentions",
        fail_close=True,
    )
    audit = _AuditConnection(events)
    repository = _repository(events, audit)

    result = repository.reconcile_document(
        cursor,
        _scope(),
        desired=_desired(mentions=(surviving,)),
        recorder=E2bDmlRecorder(),
    )

    assert cursor.connection.rolled_back is True
    assert "primary.rollback" in events
    assert "primary.close" in events
    assert result.outcome == "outcome_unknown"
    assert result.outcome != "rolled_back_failure"
    assert result.reconciliation_required is True
    assert "audit.connect" not in events
    assert result.failure_audit_outcome is None


# --------------------------------------------------------------------------- #
# MentionCandidate provenance rules (contract preserved; regression, not RED)
# --------------------------------------------------------------------------- #
def test_model_mention_candidate_requires_complete_provenance_runtime_may_be_none() -> (
    None
):
    candidate = _candidate(
        source="model",
        artifact_digest=_DIGEST_A,
        runtime_compatibility_id=None,
    )
    assert candidate.segment_id == _SEGMENT
    assert candidate.artifact_digest == _DIGEST_A
    assert candidate.runtime_compatibility_id is None


def test_model_mention_candidate_without_artifact_digest_is_rejected() -> None:
    with pytest.raises(ValueError):
        _candidate(source="model", artifact_digest=None)


def test_non_model_mention_candidate_must_not_carry_model_provenance() -> None:
    with pytest.raises(ValueError):
        _candidate(source="dictionary", model_id="iic/whatever")


# --------------------------------------------------------------------------- #
# Corrective RED round 2 (coordinator-verified plan violations not covered by
# the frozen selector). These freeze additional real-plan contracts:
# 1) fixed lock/load/preflight ordering (preflight runs AFTER locks+loads),
# 2) contended stale current-version ledger deletion BEFORE bridge deletion,
# 3) rogue/unprovable link fail-closed close semantics,
# 4) non-model mentions must not carry ANY model provenance incl.
#    runtime_compatibility_id,
# 5) corpus mentions must satisfy input_id == span_id,
# 6) E2a-aligned commit-outcome preserving the issued recorder DML map,
# 7) per-document document_versions scope enforcement.
# --------------------------------------------------------------------------- #
def test_slice_back_invalid_mention_locks_and_loads_before_any_dml() -> None:
    bad = _mention(mention_text="does-not-slice-back")
    events: list[str] = []
    cursor = _cursor(
        events,
        existing_ledger=(_ledger_row(_NODE, _ENTITY),),
        existing_tree_node_spans=(_span_row(_NODE, _SPAN),),
    )
    audit = _AuditConnection(events)
    repository = _repository(events, audit)

    result = repository.reconcile_document(
        cursor,
        _scope(),
        desired=_desired(mentions=(bad,)),
        recorder=E2bDmlRecorder(),
    )

    # Fixed sequence: advisory lock -> document_versions FOR UPDATE -> the
    # current-scope mention/ledger/span/bridge loads ALL happen BEFORE the
    # slice-back preflight failure (never before any lock/load).
    assert cursor.executed, (
        "a slice-back-invalid corpus mention must still acquire locks and load "
        "existing state before failing preflight"
    )
    lock_index = next(
        i
        for i, (statement, _) in enumerate(cursor.executed)
        if "pg_advisory_xact_lock" in _normalized(statement)
    )
    doc_index = next(
        i
        for i, (statement, _) in enumerate(cursor.executed)
        if "from document_versions" in _normalized(statement)
        and "for update" in _normalized(statement)
    )
    assert lock_index < doc_index
    for table in (
        "entity_mentions",
        "okf_e2b_node_link_ownership",
        "tree_node_spans",
        "node_entity_links",
    ):
        load_index = next(
            (
                i
                for i, (statement, _) in enumerate(cursor.executed)
                if f"from {table}" in _normalized(statement)
                and "for update" in _normalized(statement)
            ),
            None,
        )
        assert load_index is not None, f"{table} load must be FOR UPDATE"
        assert doc_index < load_index
    dml_indexes = [
        i for i, (statement, _) in enumerate(cursor.executed) if _is_dml(statement)
    ]
    assert not dml_indexes or all(doc_index < i for i in dml_indexes)

    assert result.outcome == "rolled_back_failure"
    assert cursor.connection.rolled_back is True
    assert cursor.connection.closed is True
    assert events.index("primary.rollback") < events.index("primary.close")
    assert events.index("primary.close") < events.index("audit.connect")
    assert audit.committed is True
    assert result.failure_audit_outcome == "written"


def test_contended_bridge_preserved_but_current_ledger_deleted_before_bridge() -> None:
    # (NODE, ENTITY): current-only owner, desired no longer wants it -> bridge
    # AND current ledger both deleted.
    # (NODE2, ENTITY2): current + other-version owner-proof (defensive
    # corrupted/schema-inconsistent state), desired no longer wants it -> bridge
    # PRESERVED fail-closed, but the current-version stale ownership ledger IS
    # deleted (the current version no longer owns it). The ownership DELETE must
    # precede the bridge DELETE.
    owned = _link(node_id=_NODE, entity_id=_ENTITY)
    contended = _link(node_id=_NODE2, entity_id=_ENTITY2)
    fresh_mention = _mention(entity_id=_ENTITY3, span_id=_SPAN)
    fresh = _link(node_id=_NODE3, entity_id=_ENTITY3)
    events: list[str] = []
    cursor = _cursor(
        events,
        existing_bridges=(
            _bridge_row(owned.node_id, owned.entity_id),
            _bridge_row(contended.node_id, contended.entity_id),
        ),
        existing_ledger=(
            _ledger_row(owned.node_id, owned.entity_id),
            _ledger_row(contended.node_id, contended.entity_id),
            _ledger_row(contended.node_id, contended.entity_id, version_id=_OTHER_VER),
        ),
        existing_tree_node_spans=(_span_row(_NODE3, _SPAN),),
    )
    repository = _repository(events, _AuditConnection(events))

    result = repository.reconcile_document(
        cursor,
        _scope(),
        desired=_desired(mentions=(fresh_mention,), links=(fresh,)),
        recorder=E2bDmlRecorder(),
    )

    assert result.outcome == "changed"
    bridge_deletes = [
        (statement, parameters)
        for statement, parameters in _dml(cursor.executed)
        if "delete from node_entity_links" in _normalized(statement)
    ]
    ledger_deletes = [
        (statement, parameters)
        for statement, parameters in _dml(cursor.executed)
        if "delete from okf_e2b_node_link_ownership" in _normalized(statement)
    ]
    # The contended bridge (current + other owner) is preserved for the other
    # owner; only the current-only owned bridge is deleted.
    assert bridge_deletes == [
        (
            "DELETE FROM node_entity_links WHERE node_id = %s AND entity_id = %s",
            (owned.node_id, owned.entity_id),
        )
    ]
    # The current-version stale ledger is deleted for BOTH the current-only pair
    # and the contended pair (the current version no longer owns it).
    assert len(ledger_deletes) == 1
    ledger_keys = set(ledger_deletes[0][1][1])
    assert f"{owned.node_id}:{owned.entity_id}" in ledger_keys
    assert f"{contended.node_id}:{contended.entity_id}" in ledger_keys
    # Ownership DELETE must precede the bridge DELETE in statement order.
    ledger_delete_index = next(
        i
        for i, (statement, _) in enumerate(cursor.executed)
        if "delete from okf_e2b_node_link_ownership" in _normalized(statement)
    )
    bridge_delete_index = next(
        i
        for i, (statement, _) in enumerate(cursor.executed)
        if "delete from node_entity_links" in _normalized(statement)
    )
    assert ledger_delete_index < bridge_delete_index


def test_rogue_link_fail_closed_rolls_back_then_closes_no_audit_no_dml() -> None:
    # After SQL locks are acquired, an unprovable desired link fails closed with
    # ValueError: the primary must be rolled back AND closed, rollback before
    # close, no fresh audit, and zero DML. Full preflight includes the D5
    # caller-link proof only AFTER the relevant bridge rows and cross-version
    # ownership rows are loaded/locked.
    mention = _mention(entity_id=_ENTITY, span_id=_SPAN)
    rogue_link = _link(node_id=_NODE3, entity_id=_ENTITY3)
    events: list[str] = []
    cursor = _cursor(
        events,
        existing_tree_node_spans=(_span_row(_NODE, _SPAN),),
    )
    audit = _AuditConnection(events)
    repository = _repository(events, audit)

    with pytest.raises(ValueError):
        repository.reconcile_document(
            cursor,
            _scope(),
            desired=_desired(mentions=(mention,), links=(rogue_link,)),
            recorder=E2bDmlRecorder(),
        )

    # Locks/loads were issued before the fail-closed decision.
    assert any(
        "pg_advisory_xact_lock" in _normalized(statement)
        for statement, _ in cursor.executed
    )
    # Relevant bridge rows are loaded/locked before the D5 caller-link proof.
    bridge_loads = [
        statement
        for statement, _ in cursor.executed
        if "from node_entity_links" in _normalized(statement)
        and "for update" in _normalized(statement)
    ]
    assert (
        bridge_loads
    ), "relevant node_entity_links rows must be loaded/locked before the link proof"
    # Relevant cross-version ownership rows are loaded/locked before the D5
    # caller-link proof (bounded node_entity_link_key = ANY(%s)).
    owner_proofs = [
        (statement, parameters)
        for statement, parameters in cursor.executed
        if "from okf_e2b_node_link_ownership" in _normalized(statement)
        and "node_entity_link_key = any" in _normalized(statement)
    ]
    assert (
        owner_proofs
    ), "relevant cross-version ownership rows must be loaded/locked before the link proof"
    assert cursor.connection.rolled_back is True
    assert cursor.connection.closed is True
    assert events.index("primary.rollback") < events.index("primary.close")
    assert "audit.connect" not in events
    assert _dml(cursor.executed) == []


def test_non_model_mention_must_not_carry_runtime_compatibility_id() -> None:
    # Per contracts._MODEL_PROVENANCE_FIELDS, non-model mentions must carry NO
    # model provenance at all, including runtime_compatibility_id. A dictionary
    # mention with model_id/revision/digest None but a non-None runtime id must
    # fail BEFORE any DML with a confirmed rollback+close and fresh audit.
    bad = _mention(
        source="dictionary",
        model_id=None,
        model_revision=None,
        artifact_digest=None,
        runtime_compatibility_id="rc-1",
    )
    events: list[str] = []
    cursor = _cursor(events)
    audit = _AuditConnection(events)
    repository = _repository(events, audit)

    result = repository.reconcile_document(
        cursor,
        _scope(),
        desired=_desired(mentions=(bad,)),
        recorder=E2bDmlRecorder(),
    )

    assert result.outcome == "rolled_back_failure"
    assert _dml(cursor.executed) == []
    assert cursor.connection.rolled_back is True
    assert cursor.connection.closed is True
    assert events.index("primary.rollback") < events.index("primary.close")
    assert events.index("primary.close") < events.index("audit.connect")
    assert audit.committed is True
    assert result.failure_audit_outcome == "written"


def test_corpus_mention_requires_input_id_equal_span_id() -> None:
    # A corpus_span mention must satisfy input_id == span_id (per the corpus
    # projection contract). A mismatch must fail BEFORE any DML with a confirmed
    # rollback+close and fresh audit.
    bad = _mention(input_id=str(UUID(int=99)))
    events: list[str] = []
    cursor = _cursor(events)
    audit = _AuditConnection(events)
    repository = _repository(events, audit)

    result = repository.reconcile_document(
        cursor,
        _scope(),
        desired=_desired(mentions=(bad,)),
        recorder=E2bDmlRecorder(),
    )

    assert result.outcome == "rolled_back_failure"
    assert _dml(cursor.executed) == []
    assert cursor.connection.rolled_back is True
    assert cursor.connection.closed is True
    assert events.index("primary.rollback") < events.index("primary.close")
    assert events.index("primary.close") < events.index("audit.connect")
    assert audit.committed is True
    assert result.failure_audit_outcome == "written"


def test_commit_exception_preserves_recorder_primary_dml_by_table() -> None:
    # E2a-aligned uncertainty: on a commit exception the already-issued recorder
    # DML map is preserved (not replaced by an empty map), primary is closed,
    # and there is no rollback and no fresh audit.
    mention = _mention()
    link = _link()
    events: list[str] = []
    cursor = _cursor(
        events,
        fail_commit=True,
        existing_tree_node_spans=(_span_row(link.node_id, mention.span_id),),
    )
    recorder = E2bDmlRecorder()
    audit = _AuditConnection(events)
    repository = _repository(events, audit)

    result = repository.reconcile_document(
        cursor,
        _scope(),
        desired=_desired(mentions=(mention,), links=(link,)),
        recorder=recorder,
    )

    assert result.outcome == "outcome_unknown"
    assert result.outcome != "rolled_back_failure"
    assert result.reconciliation_required is True
    assert cursor.connection.closed is True
    assert "primary.rollback" not in events
    assert "audit.connect" not in events
    assert dict(recorder.primary_dml_by_table)
    assert result.primary_dml_by_table == dict(recorder.primary_dml_by_table)


def test_document_versions_scope_mismatch_rejected_with_rollback_and_audit() -> None:
    # Per-document/version scope: the locked document_versions row must match
    # BOTH version_id and document_id. A same-version/different-document row must
    # fail BEFORE any DML with a confirmed rollback+close and fresh audit.
    mention = _mention()
    events: list[str] = []
    cursor = _cursor(
        events,
        document_versions=[{"doc_id": str(UUID(int=99)), "version_id": _VER}],
    )
    audit = _AuditConnection(events)
    repository = _repository(events, audit)

    result = repository.reconcile_document(
        cursor,
        _scope(),
        desired=_desired(mentions=(mention,)),
        recorder=E2bDmlRecorder(),
    )

    assert result.outcome == "rolled_back_failure"
    assert _dml(cursor.executed) == []
    assert cursor.connection.rolled_back is True
    assert cursor.connection.closed is True
    assert events.index("primary.rollback") < events.index("primary.close")
    assert events.index("primary.close") < events.index("audit.connect")
    assert audit.committed is True
    assert result.failure_audit_outcome == "written"


# --------------------------------------------------------------------------- #
# Corrective RED round 3 (coordinator source audit: frozen 16-09 contracts not
# covered by rounds 1-2). These freeze:
# 1) all ownership/mention/span/bridge locks AND the bounded cross-version owner
#    proof precede the first DML,
# 2) D5 caller-link proof runs only AFTER relevant bridge rows and cross-version
#    ownership rows are loaded/locked (strengthened in the rogue-link test),
# 3) cleanup uncertainty after prior DML publishes EMPTY public maps (E2a
#    cleanup analog) while the recorder itself proves the prior DML occurred,
# 4) legacy/manual/foreign mention collisions are never claimed,
# 5) a desired bridge pair colliding with an unowned/manual bridge is preserved
#    and never assigned ownership,
# 6) an explicit other-version E2b owner is schema-inconsistent/foreign ownership
#    proof (migration 003/020 bind one version per node, so legitimate same-pair
#    co-ownership is unreachable): the pair fails closed with the pre-existing
#    bridge preserved and NO current-version ownership ledger INSERT.
# --------------------------------------------------------------------------- #
def test_cross_version_owner_proof_precedes_all_dml() -> None:
    # Valid changed state with a stale bridge ownership decision: the bounded
    # cross-version owner proof (node_entity_link_key = ANY(%s) FOR UPDATE) must
    # occur BEFORE every INSERT/UPDATE/DELETE.
    mention = _mention()
    link = _link()
    stale = _link(node_id=_NODE2, entity_id=_ENTITY2)
    events: list[str] = []
    cursor = _cursor(
        events,
        existing_bridges=(
            _bridge_row(link.node_id, link.entity_id),
            _bridge_row(stale.node_id, stale.entity_id),
        ),
        existing_ledger=(
            _ledger_row(link.node_id, link.entity_id),
            _ledger_row(stale.node_id, stale.entity_id),
        ),
        existing_tree_node_spans=(_span_row(link.node_id, mention.span_id),),
    )
    repository = _repository(events, _AuditConnection(events))

    result = repository.reconcile_document(
        cursor,
        _scope(),
        desired=_desired(mentions=(mention,), links=(link,)),
        recorder=E2bDmlRecorder(),
    )

    assert result.outcome == "changed"
    owner_proof_indexes = [
        i
        for i, (statement, _) in enumerate(cursor.executed)
        if "from okf_e2b_node_link_ownership" in _normalized(statement)
        and "node_entity_link_key = any" in _normalized(statement)
        and "for update" in _normalized(statement)
    ]
    assert owner_proof_indexes, "bounded cross-version owner proof must be issued"
    dml_indexes = [
        i for i, (statement, _) in enumerate(cursor.executed) if _is_dml(statement)
    ]
    assert dml_indexes, "changed-state test must issue DML"
    assert owner_proof_indexes[0] < min(
        dml_indexes
    ), "bounded cross-version owner proof must precede all DML"


def test_cleanup_rollback_failure_after_prior_dml_publishes_empty_maps() -> None:
    # A stale mention DELETE is successfully issued/recorded, then the stale
    # ownership DELETE fails, and primary rollback ALSO fails. Per the frozen E2a
    # cleanup analog the public result must publish EMPTY maps; the recorder
    # itself proves the prior DML occurred.
    surviving = _mention()
    stale = _mention(start=4, end=6)
    link = _link()
    events: list[str] = []
    recorder = E2bDmlRecorder()
    cursor = _cursor(
        events,
        existing_mentions=(_mention_row(surviving), _mention_row(stale)),
        existing_ledger=(
            _ledger_row(link.node_id, link.entity_id),
            _ledger_row(_NODE2, _ENTITY2),
        ),
        existing_bridges=(_bridge_row(link.node_id, link.entity_id),),
        existing_tree_node_spans=(_span_row(link.node_id, surviving.span_id),),
        fail_statement_substring="delete from okf_e2b_node_link_ownership",
        fail_rollback=True,
    )
    audit = _AuditConnection(events)
    repository = _repository(events, audit)

    result = repository.reconcile_document(
        cursor,
        _scope(),
        desired=_desired(mentions=(surviving,), links=(link,)),
        recorder=recorder,
    )

    assert dict(recorder.primary_dml_by_table), "recorder must prove prior DML"
    assert result.outcome == "outcome_unknown"
    assert result.outcome != "rolled_back_failure"
    assert result.reconciliation_required is True
    assert result.primary_dml_by_table == {}
    assert result.stale_deletion_counts["entity_mentions"] == 0
    assert result.stale_deletion_counts["okf_e2b_node_link_ownership"] == 0
    assert result.stale_deletion_counts["node_entity_links"] == 0
    assert cursor.connection.closed is True
    assert "audit.connect" not in events
    assert result.failure_audit_outcome is None


def test_cleanup_close_failure_after_prior_dml_publishes_empty_maps() -> None:
    # A stale mention DELETE is successfully issued/recorded, then the stale
    # ownership DELETE fails, and primary close ALSO fails. Public maps are
    # empty; the recorder proves the prior DML occurred.
    surviving = _mention()
    stale = _mention(start=4, end=6)
    link = _link()
    events: list[str] = []
    recorder = E2bDmlRecorder()
    cursor = _cursor(
        events,
        existing_mentions=(_mention_row(surviving), _mention_row(stale)),
        existing_ledger=(
            _ledger_row(link.node_id, link.entity_id),
            _ledger_row(_NODE2, _ENTITY2),
        ),
        existing_bridges=(_bridge_row(link.node_id, link.entity_id),),
        existing_tree_node_spans=(_span_row(link.node_id, surviving.span_id),),
        fail_statement_substring="delete from okf_e2b_node_link_ownership",
        fail_close=True,
    )
    audit = _AuditConnection(events)
    repository = _repository(events, audit)

    result = repository.reconcile_document(
        cursor,
        _scope(),
        desired=_desired(mentions=(surviving,), links=(link,)),
        recorder=recorder,
    )

    assert dict(recorder.primary_dml_by_table), "recorder must prove prior DML"
    assert cursor.connection.rolled_back is True
    assert result.outcome == "outcome_unknown"
    assert result.outcome != "rolled_back_failure"
    assert result.reconciliation_required is True
    assert result.primary_dml_by_table == {}
    assert result.stale_deletion_counts["entity_mentions"] == 0
    assert result.stale_deletion_counts["okf_e2b_node_link_ownership"] == 0
    assert result.stale_deletion_counts["node_entity_links"] == 0
    assert "audit.connect" not in events
    assert result.failure_audit_outcome is None


def test_manual_and_foreign_mention_collision_is_never_claimed() -> None:
    # The desired mention_ids exactly match existing rows with e2b_owner_scope
    # NULL (manual/legacy) and a foreign scope. A bounded desired-ID mention
    # read/lock must detect the collision; the existing rows are preserved with
    # zero entity_mentions DML (no owner-scope takeover) and no audit.
    desired_a = _mention()
    desired_b = _mention(start=4, end=6)
    manual = _mention_row(desired_a, owner_scope=None)
    foreign = _mention_row(desired_b, owner_scope=f"okf:e2b:{_DOC}:{_OTHER_VER}")
    events: list[str] = []
    cursor = _cursor(events, existing_mentions=(manual, foreign))
    audit = _AuditConnection(events)
    repository = _repository(events, audit)

    result = repository.reconcile_document(
        cursor,
        _scope(),
        desired=_desired(mentions=(desired_a, desired_b)),
        recorder=E2bDmlRecorder(),
    )

    bounded_reads = [
        statement
        for statement, _ in cursor.executed
        if "from entity_mentions" in _normalized(statement)
        and "mention_id = any" in _normalized(statement)
        and "for update" in _normalized(statement)
    ]
    assert bounded_reads, "a bounded desired-ID mention read must be issued"
    assert not any(
        "insert into entity_mentions" in _normalized(statement)
        or "update entity_mentions" in _normalized(statement)
        for statement, _ in cursor.executed
    )
    assert result.outcome == "no_op"
    assert "audit.connect" not in events
    assert result.failure_audit_outcome is None


def test_desired_bridge_colliding_with_unowned_bridge_is_preserved_no_ownership() -> (
    None
):
    # The desired pair collides with an existing node_entity_links bridge that
    # has NO E2b ledger owner (manual/legacy/unowned). The bounded all-owner
    # proof is read, but the bridge is preserved: zero bridge DML, zero
    # ownership-ledger INSERT, and the reconciled outcome is a no-op.
    mention = _mention()
    link = _link(mention_text="different")  # projection differs from the bridge
    events: list[str] = []
    cursor = _cursor(
        events,
        existing_mentions=(_mention_row(mention),),
        existing_bridges=(_bridge_row(link.node_id, link.entity_id),),
        existing_tree_node_spans=(_span_row(link.node_id, mention.span_id),),
    )
    repository = _repository(events, _AuditConnection(events))

    result = repository.reconcile_document(
        cursor,
        _scope(),
        desired=_desired(mentions=(mention,), links=(link,)),
        recorder=E2bDmlRecorder(),
    )

    owner_proofs = [
        (statement, parameters)
        for statement, parameters in cursor.executed
        if "from okf_e2b_node_link_ownership" in _normalized(statement)
        and "node_entity_link_key = any" in _normalized(statement)
    ]
    assert owner_proofs, "the bounded all-owner proof for the desired pair must be read"
    desired_key = f"{link.node_id}:{link.entity_id}"
    assert desired_key in owner_proofs[0][1][0]
    assert not any(
        "insert into node_entity_links" in _normalized(statement)
        or "update node_entity_links" in _normalized(statement)
        for statement, _ in cursor.executed
    )
    assert not any(
        "insert into okf_e2b_node_link_ownership" in _normalized(statement)
        for statement, _ in cursor.executed
    )
    assert result.outcome == "no_op"


def test_other_version_owner_proof_is_schema_inconsistent_fails_closed() -> None:
    # A bridge whose owner-proof shows an explicit OTHER-version E2b owner is a
    # defensive corrupted/schema-inconsistent state (migration 003/020 bind one
    # version per node; legitimate same-pair co-ownership is unreachable). The
    # repository must fail closed: preserve the pre-existing bridge projection,
    # emit NO node_entity_links DML, emit NO okf_e2b_node_link_ownership INSERT,
    # and return a no-op.
    mention = _mention()
    link = _link(mention_text="different")  # projection differs from the bridge
    events: list[str] = []
    cursor = _cursor(
        events,
        existing_mentions=(_mention_row(mention),),
        existing_bridges=(_bridge_row(link.node_id, link.entity_id),),
        existing_ledger=(
            _ledger_row(link.node_id, link.entity_id, version_id=_OTHER_VER),
        ),
        existing_tree_node_spans=(_span_row(link.node_id, mention.span_id),),
    )
    repository = _repository(events, _AuditConnection(events))

    result = repository.reconcile_document(
        cursor,
        _scope(),
        desired=_desired(mentions=(mention,), links=(link,)),
        recorder=E2bDmlRecorder(),
    )

    owner_proofs = [
        (statement, parameters)
        for statement, parameters in cursor.executed
        if "from okf_e2b_node_link_ownership" in _normalized(statement)
        and "node_entity_link_key = any" in _normalized(statement)
    ]
    assert owner_proofs, "the bounded all-owner proof for the desired pair must be read"
    desired_key = f"{link.node_id}:{link.entity_id}"
    assert desired_key in owner_proofs[0][1][0]
    assert not any(
        "insert into node_entity_links" in _normalized(statement)
        or "update node_entity_links" in _normalized(statement)
        for statement, _ in cursor.executed
    )
    assert not any(
        "insert into okf_e2b_node_link_ownership" in _normalized(statement)
        for statement, _ in cursor.executed
    )
    assert result.outcome == "no_op"


# --------------------------------------------------------------------------- #
# Corrective RED round 4 (Task #187 / plan 16-09): source-verified psycopg
# row-typing and lock-ordering defects. These freeze:
# 1) raw psycopg uuid.UUID identity values in document_versions / mentions /
#    ledger / tree_node_spans / bridges / owner-proof normalize so an equivalent
#    rerun is a true no-op (zero DML); UUID-bearing scope/document row
#    comparisons are validated, not string-only,
# 2) a manual/unowned bridge with UUID values is never claimed/rewritten/deleted,
# 3) the current-version ownership inventory read must NOT FOR UPDATE before
#    bridge locking; the bounded all-version node_entity_link_key = ANY(...)
#    proof is the authoritative FOR UPDATE ownership lock after bridge lock and
#    before any DML,
# 4) a bridge whose owner-proof shows the current version AND another version is
#    a defensive corrupted/schema-inconsistent state that fails closed: the
#    shared projection is preserved with no node_entity_links DML and no
#    ownership-ledger INSERT,
# 5) a desired mention colliding with a manual/foreign row must not contribute a
#    derived E2b bridge or ledger,
# 6) the mention upsert ON CONFLICT guard closes the TOCTOU takeover of a
#    manual/foreign row appearing at INSERT/conflict time,
# 7) Decimal NUMERIC confidence compares with PostgreSQL semantics and remains
#    zero-DML,
# 8) invalid document_char_start/document_char_end (negative, equal, inverted,
#    non-integer) fail preflight before DML.
# --------------------------------------------------------------------------- #
def test_document_versions_uuid_values_normalize_for_scope_comparison() -> None:
    # PostgreSQL returns uuid columns as uuid.UUID objects. The locked
    # document_versions row must match scope by normalizing UUID values, not by
    # comparing them to strings (which always differ and would be rejected as a
    # scope mismatch with a rollback + fresh audit).
    mention = _mention()
    events: list[str] = []
    cursor = _cursor(
        events,
        document_versions=[{"doc_id": UUID(int=1), "version_id": UUID(int=2)}],
    )
    audit = _AuditConnection(events)
    repository = _repository(events, audit)

    result = repository.reconcile_document(
        cursor,
        _scope(),
        desired=_desired(mentions=(mention,)),
        recorder=E2bDmlRecorder(),
    )

    assert result.outcome != "rolled_back_failure"
    assert "audit.connect" not in events
    assert cursor.connection.rolled_back is False


def test_uuid_typed_existing_rows_equivalent_rerun_is_true_noop() -> None:
    # Every existing-state row carries raw uuid.UUID identity values (psycopg).
    # An equivalent rerun must normalize them and be a true no-op with zero DML.
    mention = _mention()
    link = _link()
    events: list[str] = []
    cursor = _cursor(
        events,
        existing_mentions=(_mention_row_uuid(mention),),
        existing_ledger=(_ledger_row_uuid(link.node_id, link.entity_id),),
        existing_bridges=(_bridge_row_uuid(link.node_id, link.entity_id),),
        existing_tree_node_spans=(_span_row_uuid(link.node_id, mention.span_id),),
    )
    repository = _repository(events, _AuditConnection(events))

    result = repository.reconcile_document(
        cursor,
        _scope(),
        desired=_desired(mentions=(mention,), links=(link,)),
        recorder=E2bDmlRecorder(),
    )

    assert result.outcome == "no_op"
    assert _dml(cursor.executed) == []


def test_manual_unowned_bridge_uuid_values_never_claimed_rewritten_or_deleted() -> None:
    # A manual/unowned bridge represented with uuid.UUID row values must be
    # preserved: zero node_entity_links DML (no claim/rewrite), zero ownership
    # INSERT, and no bridge DELETE.
    mention = _mention()
    link = _link(mention_text="different")  # projection differs from the bridge
    events: list[str] = []
    cursor = _cursor(
        events,
        existing_mentions=(_mention_row(mention),),
        existing_bridges=(_bridge_row_uuid(link.node_id, link.entity_id),),
        existing_tree_node_spans=(_span_row_uuid(link.node_id, mention.span_id),),
    )
    repository = _repository(events, _AuditConnection(events))

    result = repository.reconcile_document(
        cursor,
        _scope(),
        desired=_desired(mentions=(mention,), links=(link,)),
        recorder=E2bDmlRecorder(),
    )

    assert not any(
        "insert into node_entity_links" in _normalized(statement)
        or "update node_entity_links" in _normalized(statement)
        or "delete from node_entity_links" in _normalized(statement)
        for statement, _ in cursor.executed
    )
    assert not any(
        "insert into okf_e2b_node_link_ownership" in _normalized(statement)
        for statement, _ in cursor.executed
    )
    assert result.outcome == "no_op"


def test_owner_proof_is_authoritative_lock_after_bridge_not_inventory() -> None:
    # The current-version ownership inventory read (version_id = %s) is a plain
    # inventory read and must NOT take a FOR UPDATE lock before bridge locking.
    # The bounded all-version node_entity_link_key = ANY(%s) proof IS the
    # authoritative FOR UPDATE ownership lock: it runs AFTER the bridge lock,
    # before any DML, and covers relevant current and other-version owners.
    mention = _mention()
    link = _link()
    stale = _link(node_id=_NODE2, entity_id=_ENTITY2)
    events: list[str] = []
    cursor = _cursor(
        events,
        existing_bridges=(
            _bridge_row(link.node_id, link.entity_id),
            _bridge_row(stale.node_id, stale.entity_id),
        ),
        existing_ledger=(
            _ledger_row(link.node_id, link.entity_id),
            _ledger_row(stale.node_id, stale.entity_id),
            _ledger_row(stale.node_id, stale.entity_id, version_id=_OTHER_VER),
        ),
        existing_tree_node_spans=(_span_row(link.node_id, mention.span_id),),
    )
    repository = _repository(events, _AuditConnection(events))

    result = repository.reconcile_document(
        cursor,
        _scope(),
        desired=_desired(mentions=(mention,), links=(link,)),
        recorder=E2bDmlRecorder(),
    )

    inventory_stmts = [
        statement
        for statement, _ in cursor.executed
        if "from okf_e2b_node_link_ownership" in _normalized(statement)
        and "node_entity_link_key = any" not in _normalized(statement)
    ]
    assert inventory_stmts, "a current-version ownership inventory read must be issued"
    assert all(
        "for update" not in _normalized(statement) for statement in inventory_stmts
    ), "the current-version ownership inventory must NOT lock before bridge locking"

    proof_query = next(
        (statement, parameters)
        for statement, parameters in cursor.executed
        if "from okf_e2b_node_link_ownership" in _normalized(statement)
        and "node_entity_link_key = any" in _normalized(statement)
    )
    assert "for update" in _normalized(
        proof_query[0]
    ), "the bounded all-version owner proof must be the FOR UPDATE ownership lock"
    stale_key = f"{stale.node_id}:{stale.entity_id}"
    assert (
        stale_key in proof_query[1][0]
    ), "the owner proof must cover relevant stale current and other-version owners"

    bridge_index = next(
        i
        for i, (statement, _) in enumerate(cursor.executed)
        if "from node_entity_links" in _normalized(statement)
    )
    proof_index = next(
        i
        for i, (statement, _) in enumerate(cursor.executed)
        if "from okf_e2b_node_link_ownership" in _normalized(statement)
        and "node_entity_link_key = any" in _normalized(statement)
    )
    assert (
        bridge_index < proof_index
    ), "the authoritative owner lock must follow the bridge lock"
    dml_indexes = [
        i for i, (statement, _) in enumerate(cursor.executed) if _is_dml(statement)
    ]
    assert all(
        proof_index < i for i in dml_indexes
    ), "the authoritative owner lock must precede all DML"
    assert result.outcome in {"changed", "no_op"}


def test_current_and_other_version_owner_proof_preserves_bridge_fail_closed() -> None:
    # A bridge whose owner-proof shows the CURRENT version AND another version is
    # a defensive corrupted/schema-inconsistent state (migration 003/020 bind one
    # version per node). It must fail closed: preserve the existing shared
    # projection with no node_entity_links upsert even when the desired link
    # projection differs, and no ownership INSERT either. The reconciled outcome
    # is a no-op.
    mention = _mention()
    link = _link(mention_text="different")  # projection differs from the bridge
    events: list[str] = []
    cursor = _cursor(
        events,
        existing_mentions=(_mention_row(mention),),
        existing_bridges=(_bridge_row(link.node_id, link.entity_id),),
        existing_ledger=(
            _ledger_row(link.node_id, link.entity_id),
            _ledger_row(link.node_id, link.entity_id, version_id=_OTHER_VER),
        ),
        existing_tree_node_spans=(_span_row(link.node_id, mention.span_id),),
    )
    repository = _repository(events, _AuditConnection(events))

    result = repository.reconcile_document(
        cursor,
        _scope(),
        desired=_desired(mentions=(mention,), links=(link,)),
        recorder=E2bDmlRecorder(),
    )

    assert not any(
        "insert into node_entity_links" in _normalized(statement)
        or "update node_entity_links" in _normalized(statement)
        for statement, _ in cursor.executed
    )
    assert not any(
        "insert into okf_e2b_node_link_ownership" in _normalized(statement)
        for statement, _ in cursor.executed
    )
    assert result.outcome == "no_op"


def test_colliding_desired_mention_does_not_contribute_derived_bridge_or_ledger() -> (
    None
):
    # A desired resolved mention whose mention_id collides with a manual/foreign
    # existing row is never claimed. It must ALSO not contribute a derived E2b
    # bridge or ownership ledger: the span->node derivation for a colliding
    # mention is suppressed.
    mention = _mention(entity_id=_ENTITY, span_id=_SPAN)  # resolved, colliding
    manual = _mention_row(mention, owner_scope=None)
    events: list[str] = []
    cursor = _cursor(
        events,
        existing_mentions=(manual,),
        existing_tree_node_spans=(_span_row(_NODE, _SPAN),),
    )
    repository = _repository(events, _AuditConnection(events))

    result = repository.reconcile_document(
        cursor,
        _scope(),
        desired=_desired(mentions=(mention,)),
        recorder=E2bDmlRecorder(),
    )

    assert not any(
        "insert into entity_mentions" in _normalized(statement)
        or "update entity_mentions" in _normalized(statement)
        for statement, _ in cursor.executed
    )
    assert not any(
        "insert into node_entity_links" in _normalized(statement)
        for statement, _ in cursor.executed
    )
    assert not any(
        "insert into okf_e2b_node_link_ownership" in _normalized(statement)
        for statement, _ in cursor.executed
    )
    assert result.outcome == "no_op"


def test_mention_upsert_conflict_guard_prevents_late_takeover() -> None:
    # TOCTOU: between the bounded desired-ID read (no collision visible) and the
    # actual INSERT, a manual/foreign row with the same mention_id can appear at
    # ON CONFLICT time. The upsert SQL must refuse to take over that row. The
    # spy simulates the late-arriving row by observing the INSERT targeting a
    # late-conflicting mention_id.
    mention = _mention()
    events: list[str] = []
    cursor = _cursor(events, late_conflict_mention_ids={mention.mention_id})
    repository = _repository(events, _AuditConnection(events))

    result = repository.reconcile_document(
        cursor,
        _scope(),
        desired=_desired(mentions=(mention,)),
        recorder=E2bDmlRecorder(),
    )

    assert (
        cursor.conflict_encounters
    ), "the spy must observe a late-arriving conflicting mention at INSERT time"
    insert_sql = _normalized(cursor.conflict_encounters[0][0])
    assert "on conflict" in insert_sql
    # The generic change-detection WHERE ("e2b_owner_scope IS DISTINCT FROM
    # EXCLUDED.e2b_owner_scope") would UPDATE a manual/foreign conflicting row
    # exactly when its owner differs -> TOCTOU takeover. The safe contract must
    # NOT emit that guard for e2b_owner_scope.
    assert (
        "e2b_owner_scope is distinct from excluded.e2b_owner_scope" not in insert_sql
    ), "the conflict guard must not take over a differently-owned conflicting row"
    assert result.outcome == "changed"


def test_decimal_numeric_confidence_equivalent_rerun_is_zero_dml() -> None:
    # entity_mentions.confidence is NUMERIC, so psycopg returns Decimal while the
    # desired projection carries an equivalent float. PostgreSQL semantics treat
    # Decimal(0.95) and 0.95 as equal; the equivalence check must not issue DML.
    mention = _mention(confidence=0.95, confidence_kind="model_probability")
    link = _link()
    events: list[str] = []
    cursor = _cursor(
        events,
        existing_mentions=(_mention_row_decimal_confidence(mention),),
        existing_ledger=(_ledger_row(link.node_id, link.entity_id),),
        existing_bridges=(_bridge_row(link.node_id, link.entity_id),),
        existing_tree_node_spans=(_span_row(link.node_id, mention.span_id),),
    )
    repository = _repository(events, _AuditConnection(events))

    result = repository.reconcile_document(
        cursor,
        _scope(),
        desired=_desired(mentions=(mention,), links=(link,)),
        recorder=E2bDmlRecorder(),
    )

    assert result.outcome == "no_op"
    assert _dml(cursor.executed) == []


@pytest.mark.parametrize(
    "doc_start, doc_end",
    [
        (-1, 2),  # negative start
        (0, 0),  # equal (end not > start)
        (3, 2),  # inverted
        (1.5, 3),  # non-integer start
        (0, 2.5),  # non-integer end
    ],
)
def test_invalid_document_coordinates_fail_preflight_before_dml(
    doc_start: object, doc_end: object
) -> None:
    # Migration-020 schema contract: document_char_start/document_char_end are
    # integers, start >= 0, end > start. Negative, equal, inverted, or
    # non-integer document coordinates must fail preflight BEFORE any DML.
    mention = _mention(document_char_start=doc_start, document_char_end=doc_end)
    events: list[str] = []
    cursor = _cursor(events)
    audit = _AuditConnection(events)
    repository = _repository(events, audit)

    result = repository.reconcile_document(
        cursor,
        _scope(),
        desired=_desired(mentions=(mention,)),
        recorder=E2bDmlRecorder(),
    )

    assert result.outcome == "rolled_back_failure"
    assert _dml(cursor.executed) == []
    assert cursor.connection.rolled_back is True
    assert cursor.connection.closed is True
    assert audit.committed is True
    assert result.failure_audit_outcome == "written"
