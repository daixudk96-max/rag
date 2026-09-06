"""E2b desired-state materialization repository (Phase 16-09).

``E2bMaterializationRepository.reconcile_document`` performs FULL desired-state
reconciliation per document/version -- never upsert-only. The fixed sequence:

1. Validate the primary connection has ``autocommit is False`` (before any SQL).
2. Acquire the SHARED parent advisory xact lock using E2a's EXACT key string
   ``okf:e2a:parent:{document_id}:{version_id}`` (never ``okf:e2b:parent``).
3. Lock the ``document_versions`` row ``FOR UPDATE``.
4. Load ALL relevant existing state under row locks, in fixed order, BEFORE any
   preflight/DML: same-scope ``entity_mentions`` -> current-version
   ``okf_e2b_node_link_ownership`` ledger rows -> bounded ``tree_node_spans``
   (``span_id = ANY(%s)``) -> bounded desired-ID ``entity_mentions`` read
   (``mention_id = ANY(%s)``) -> bounded ``node_entity_links`` bridge rows
   (``node_id = ANY(%s)``) -> bounded ALL-VERSION ownership proof
   (``okf_e2b_node_link_ownership WHERE node_entity_link_key = ANY(%s) FOR
   UPDATE``). No ownership query may remain after DML begins.
5. Run a full preflight over the desired set -- including the D5 caller-link
   proof against the derived span->node mapping -- AFTER the relevant bridge and
   cross-version ownership rows are loaded/locked; the first invalid span aborts
   the whole document/version with zero writes (before any DML).
6. Stably upsert the desired set (``ON CONFLICT`` with ``IS DISTINCT FROM``
   change detection) so an equivalent rerun issues zero DML. Desired mention ids
   colliding with a manual/legacy/foreign row are preserved and never claimed; a
   desired bridge colliding with an unowned/manual bridge is preserved and never
   assigned ownership; an explicit OTHER-version (non-current) E2b owner is
   schema-inconsistent/foreign proof (migration 003 binds node_id to one version
   and migration 020 enforces ownership version = node version, so legitimate
   same-pair co-ownership is unreachable) and fails closed: the bridge and
   ownership state are preserved with zero bridge/ledger DML.
7. Delete stale E2b-owned mentions ``WHERE e2b_owner_scope = current scope AND
   mention_id NOT IN (desired)`` -- NULL/foreign owner rows are never claimed.
8. Delete stale E2b link ownership (current-version ledger rows whose bridge
   key is no longer desired) even when the bridge itself is retained for an
   other-version owner; this ownership DELETE always precedes any bridge DELETE.
9. Delete a ``node_entity_links`` bridge ONLY when the pre-DML owner proof shows
   an explicit current-version ledger ownership row AND no other owner remains;
   unclear/missing ownership fails closed and preserves the bridge.
10. Commit on success (the caller owns the primary connection, so it is not
    closed). On a commit exception the primary is closed without rollback/audit
    and outcome_unknown preserves the issued recorder DML map. On auditable
    pre-commit repository failures a fresh-connection append-only
    ``okf_e2b_failure_audit`` row is written ONLY after BOTH primary rollback and
    primary close are confirmed; cleanup uncertainty (rollback OR close
    unconfirmed after prior DML) publishes EMPTY public maps instead. D5
    caller-link construction errors (``_E2bLinkProofError``) are rolled back and
    closed then propagated without audit, and durable non-corpus input is
    rejected before any SQL. ``okf_rebuild_failure_audit`` is never written.

Unresolved mentions (``entity_id`` NULL) persist with full provenance;
``node_entity_links`` is written only for resolved entities; ``chunk_entity_links``
is never written.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from ..okf._e2a_postgres_semantics import postgres_values_equal
from ..okf.e2a_contract_primitives import _digest, _uuid
from .contracts import deterministic_id
from .failure_audit import E2bFailureAudit


class _Cursor(Protocol):
    def execute(self, statement: str, parameters: object | None = None) -> None: ...

    def fetchone(self) -> Mapping[str, object] | None: ...

    def fetchall(self) -> Sequence[Mapping[str, object]]: ...


class _Connection(Protocol):
    autocommit: bool

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...


class _CursorWithConnection(Protocol):
    connection: _Connection

    def execute(self, statement: str, parameters: object | None = None) -> None: ...

    def fetchone(self) -> Mapping[str, object] | None: ...

    def fetchall(self) -> Sequence[Mapping[str, object]]: ...


@dataclass(frozen=True)
class E2bDocumentScope:
    """One document/version scope with its stable E2b owner identity."""

    document_id: str
    version_id: str

    def __post_init__(self) -> None:
        _uuid(self.document_id, "document_id")
        _uuid(self.version_id, "version_id")

    @property
    def e2b_owner_scope(self) -> str:
        """Stable E2b owner scope derived from document/version alone."""
        return f"okf:e2b:{self.document_id}:{self.version_id}"

    @property
    def advisory_lock_key(self) -> str:
        """E2a's EXACT shared advisory key (never ``okf:e2b:parent``)."""
        return f"okf:e2a:parent:{self.document_id}:{self.version_id}"


@dataclass(frozen=True)
class E2bDesiredMention:
    """Desired entity_mentions row projection for one document/version."""

    mention_id: str
    span_id: str
    char_start: int
    char_end: int
    mention_text: str
    normalized_text: str
    entity_id: str | None
    source: str
    raw_label: str
    entity_type: str
    extractor_id: str
    extractor_version: str
    confidence: float | None
    confidence_kind: str
    input_id: str
    input_kind: str
    input_revision: str
    document_char_start: int
    document_char_end: int
    segment_id: str | None
    # Migration-020 complete provenance column set owned by this DTO. The
    # schema/normalization/segmentation/label-map provenance must be complete;
    # runtime_compatibility_id may stay None. Model-source mentions additionally
    # require complete model provenance (model_id/model_revision/64-hex
    # artifact_digest), enforced at reconcile preflight time.
    model_id: str | None = None
    model_revision: str | None = None
    artifact_digest: str | None = None
    schema_version: str | None = None
    normalization_version: str | None = None
    segmentation_version: str | None = None
    label_map_digest: str | None = None
    runtime_compatibility_id: str | None = None

    def __post_init__(self) -> None:
        _uuid(self.mention_id, "mention_id")
        _uuid(self.span_id, "span_id")
        if type(self.char_start) is not int or type(self.char_end) is not int:
            raise ValueError("mention coordinates must be integers")
        if not (0 <= self.char_start < self.char_end <= len(self.normalized_text)):
            raise ValueError("mention coordinates are out of range")
        if type(self.mention_text) is not str or not self.mention_text:
            raise ValueError("mention_text must be a non-empty string")


@dataclass(frozen=True)
class E2bDesiredLink:
    """Desired node_entity_links bridge for one resolved entity."""

    node_id: str
    entity_id: str
    ordinal_no: int
    mention_text: str


@dataclass(frozen=True)
class E2bDesiredState:
    """Immutable desired state for one document/version."""

    mentions: tuple[E2bDesiredMention, ...] = ()
    links: tuple[E2bDesiredLink, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "mentions", tuple(self.mentions))
        object.__setattr__(self, "links", tuple(self.links))


@dataclass
class E2bDmlRecorder:
    """Typed counter for E2b DML issued through the repository."""

    primary_dml_by_table: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.primary_dml_by_table = dict(self.primary_dml_by_table or {})

    @property
    def has_dml(self) -> bool:
        return bool(self.primary_dml_by_table)

    def record_issued(self, *, table: str, operation: str) -> None:
        if type(operation) is not str or operation not in {
            "INSERT",
            "UPDATE",
            "DELETE",
        }:
            raise ValueError("DML operation is unsupported")
        self.primary_dml_by_table[table] = self.primary_dml_by_table.get(table, 0) + 1


_STALE_DELETION_TABLES = (
    "entity_mentions",
    "okf_e2b_node_link_ownership",
    "node_entity_links",
)


@dataclass(frozen=True)
class E2bReconciliationResult:
    """Immutable outcome of one per-document/version reconciliation."""

    outcome: str
    primary_dml_by_table: Mapping[str, int]
    stale_deletion_counts: Mapping[str, int]
    failure_audit_outcome: str | None = None
    reconciliation_required: bool = False

    def __post_init__(self) -> None:
        if self.outcome not in {
            "changed",
            "no_op",
            "rolled_back_failure",
            "outcome_unknown",
        }:
            raise ValueError("outcome is unsupported")
        if type(self.reconciliation_required) is not bool:
            raise ValueError("reconciliation_required must be a bool")
        object.__setattr__(
            self, "primary_dml_by_table", dict(self.primary_dml_by_table)
        )
        counts = dict(self.stale_deletion_counts)
        for table in _STALE_DELETION_TABLES:
            counts.setdefault(table, 0)
        object.__setattr__(self, "stale_deletion_counts", counts)


class _E2bLinkProofError(ValueError):
    """A desired link pair is not derivable from any resolved mention span.

    Raised before any DML and propagated loudly (never masked as a
    ``rolled_back_failure``): an unprovable caller-supplied link is a
    desired-state construction bug, not a reconciliation failure to audit.
    """


class E2bMaterializationRepository:
    """Apply one document/version's desired state through a caller-owned cursor."""

    def __init__(
        self,
        *,
        failure_audit_connection_factory: Callable[[], _Connection] | None = None,
    ) -> None:
        self._failure_audit_connection_factory = failure_audit_connection_factory

    def reconcile_document(
        self,
        cursor: _CursorWithConnection,
        scope: E2bDocumentScope,
        *,
        desired: E2bDesiredState,
        recorder: E2bDmlRecorder,
    ) -> E2bReconciliationResult:
        _require_manual_transaction(cursor)
        if type(recorder) is not E2bDmlRecorder:
            raise TypeError("recorder must be E2bDmlRecorder")
        # Durability is corpus-only: a query_text desired mention fails closed
        # BEFORE any SQL/DML is issued (contract-boundary error, not rolled back).
        _preflight_durable_input(desired)
        stale_counts: dict[str, int] = {table: 0 for table in _STALE_DELETION_TABLES}
        try:
            # Fixed reconciliation order: shared parent advisory lock ->
            # document_versions FOR UPDATE -> ALL relevant reads/locks (current
            # mentions, bounded desired-mention-ID reads, current-version ledger,
            # bounded tree_node_spans, bounded bridge rows, and the bounded
            # all-version ownership proof) -> full preflight (incl. the D5
            # caller-link proof) -> DML. No ownership proof query may remain
            # after DML begins.
            self._acquire_locks(cursor, scope)
            existing_mentions = self._load_mentions(cursor, scope)
            existing_ledger = self._load_ledger(cursor, scope)
            span_rows = self._load_tree_node_spans(cursor, desired)
            desired_mention_rows = self._load_desired_mentions(cursor, desired)
            collision_mention_ids = _desired_mention_collisions(
                desired_mention_rows, scope
            )
            derived_pairs, producers = _derive_link_pairs(
                desired.mentions, span_rows, collision_mention_ids
            )
            bridge_node_ids = {node_id for node_id, _ in derived_pairs} | {
                row["node_id"] for row in existing_ledger
            }
            existing_bridges = self._load_bridges(cursor, bridge_node_ids)
            proof_keys = _relevant_pair_keys(
                derived_pairs, existing_ledger, existing_bridges
            )
            owner_proof_rows = self._load_owner_proof(cursor, proof_keys)
            owner_rows_by_key = _owner_rows_by_key(owner_proof_rows)
            _validate_links(desired, derived_pairs)
            effective_links = _effective_links(desired, derived_pairs, producers)
            self._preflight(desired)
            self._reconcile(
                cursor,
                scope,
                desired,
                effective_links,
                existing_mentions,
                existing_ledger,
                existing_bridges,
                owner_rows_by_key,
                collision_mention_ids,
                recorder,
                stale_counts,
            )
            try:
                cursor.connection.commit()
            except Exception:
                # Primary outcome is ambiguous: close the primary, never
                # rollback, never audit, freeze outcome_unknown, and preserve the
                # already-issued recorder DML map plus stale counts.
                _close_quietly(cursor.connection)
                return _commit_outcome_unknown(
                    stale_counts, recorder.primary_dml_by_table
                )
            # Success: the caller owns the primary connection, so it is never
            # closed here.
            return E2bReconciliationResult(
                outcome="changed" if recorder.has_dml else "no_op",
                primary_dml_by_table=dict(recorder.primary_dml_by_table),
                stale_deletion_counts=stale_counts,
                failure_audit_outcome=None,
                reconciliation_required=False,
            )
        except _E2bLinkProofError as failure:
            # D5 hard contract violation: release the primary transaction by
            # rolling back AND closing it (rollback before close), write no
            # audit (no DML was issued), and propagate the ValueError loudly.
            _try_rollback(cursor.connection)
            _try_close(cursor.connection)
            raise failure
        except Exception as failure:
            # Pre-commit failure: attempt primary rollback, then primary close.
            # ONLY when BOTH are confirmed may a fresh-connection audit be
            # written. Cleanup uncertainty (rollback OR close unconfirmed after
            # prior DML) follows the frozen E2a analog: outcome_unknown,
            # reconciliation_required=True, no audit, and EMPTY public maps --
            # even if the recorder internally proves the prior DML.
            rollback_confirmed = _try_rollback(cursor.connection)
            close_confirmed = _try_close(cursor.connection)
            if not (rollback_confirmed and close_confirmed):
                return _cleanup_outcome_unknown()
            if self._failure_audit_connection_factory is None:
                raise failure
            audit_result = E2bFailureAudit().write(
                self._failure_audit_connection_factory, scope, failure
            )
            return E2bReconciliationResult(
                outcome="rolled_back_failure",
                primary_dml_by_table={},
                stale_deletion_counts={table: 0 for table in _STALE_DELETION_TABLES},
                failure_audit_outcome=audit_result.outcome,
                reconciliation_required=False,
            )

    # -- fixed lock order -----------------------------------------------------
    def _acquire_locks(
        self, cursor: _CursorWithConnection, scope: E2bDocumentScope
    ) -> None:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (scope.advisory_lock_key,),
        )
        cursor.execute(
            "SELECT doc_id, version_id FROM document_versions "
            "WHERE version_id = %s FOR UPDATE",
            (scope.version_id,),
        )
        row = cursor.fetchone()
        if not isinstance(row, Mapping):
            raise ValueError("document_versions lock row does not match scope")
        normalized = _normalize_row(row)
        if (
            normalized.get("doc_id") != scope.document_id
            or normalized.get("version_id") != scope.version_id
        ):
            raise ValueError("document_versions lock row does not match scope")

    # -- existing-state loads -------------------------------------------------
    def _load_mentions(
        self, cursor: _CursorWithConnection, scope: E2bDocumentScope
    ) -> list[Mapping[str, object]]:
        cursor.execute(
            "SELECT mention_id, entity_id, span_id, char_start, char_end, "
            "mention_text, confidence, source, input_id, input_kind, input_revision, "
            "extractor_id, extractor_version, raw_label, entity_type, confidence_kind, "
            "document_char_start, document_char_end, segment_id, "
            "model_id, model_revision, artifact_digest, schema_version, "
            "normalization_version, segmentation_version, label_map_digest, "
            "runtime_compatibility_id, e2b_owner_scope "
            "FROM entity_mentions WHERE e2b_owner_scope = %s FOR UPDATE",
            (scope.e2b_owner_scope,),
        )
        return [_normalize_row(row) for row in cursor.fetchall()]

    def _load_desired_mentions(
        self, cursor: _CursorWithConnection, desired: E2bDesiredState
    ) -> list[Mapping[str, object]]:
        """Bounded desired-ID mention read/lock.

        Returns ANY existing entity_mentions row (regardless of owner scope)
        whose mention_id matches a desired id, so legacy/manual/foreign rows can
        never be silently claimed or rewritten by an ON CONFLICT upsert.
        """
        ids = sorted({mention.mention_id for mention in desired.mentions})
        if not ids:
            return []
        cursor.execute(
            "SELECT mention_id, entity_id, span_id, char_start, char_end, "
            "mention_text, confidence, source, input_id, input_kind, input_revision, "
            "extractor_id, extractor_version, raw_label, entity_type, confidence_kind, "
            "document_char_start, document_char_end, segment_id, "
            "model_id, model_revision, artifact_digest, schema_version, "
            "normalization_version, segmentation_version, label_map_digest, "
            "runtime_compatibility_id, e2b_owner_scope "
            "FROM entity_mentions WHERE mention_id = ANY(%s) FOR UPDATE",
            (ids,),
        )
        return [_normalize_row(row) for row in cursor.fetchall()]

    def _load_tree_node_spans(
        self, cursor: _CursorWithConnection, desired: E2bDesiredState
    ) -> list[Mapping[str, object]]:
        span_ids = sorted(
            {
                mention.span_id
                for mention in desired.mentions
                if mention.entity_id is not None
            }
        )
        if not span_ids:
            return []
        cursor.execute(
            "SELECT node_id, span_id FROM tree_node_spans "
            "WHERE span_id = ANY(%s) FOR UPDATE",
            (span_ids,),
        )
        return [_normalize_row(row) for row in cursor.fetchall()]

    def _load_ledger(
        self, cursor: _CursorWithConnection, scope: E2bDocumentScope
    ) -> list[Mapping[str, object]]:
        """Current-version ownership INVENTORY read (no FOR UPDATE).

        This is a plain bounded inventory of the current version's ledger rows.
        The authoritative FOR UPDATE ownership lock is the later bounded
        all-version ``node_entity_link_key = ANY(%s) FOR UPDATE`` proof, which
        runs AFTER bridge locking and reveals every version owner without the
        cross-version deadlock pattern.
        """
        cursor.execute(
            "SELECT node_entity_link_owner_id, node_id, entity_id, version_id, "
            "node_entity_link_key, e2b_run_id "
            "FROM okf_e2b_node_link_ownership WHERE version_id = %s",
            (scope.version_id,),
        )
        return [_normalize_row(row) for row in cursor.fetchall()]

    def _load_bridges(
        self,
        cursor: _CursorWithConnection,
        node_ids: set[str],
    ) -> list[Mapping[str, object]]:
        if not node_ids:
            return []
        cursor.execute(
            "SELECT node_id, entity_id, ordinal_no, mention_text, confidence_score "
            "FROM node_entity_links WHERE node_id = ANY(%s) FOR UPDATE",
            (sorted(node_ids),),
        )
        return [_normalize_row(row) for row in cursor.fetchall()]

    def _load_owner_proof(
        self,
        cursor: _CursorWithConnection,
        pair_keys: set[str],
    ) -> list[Mapping[str, object]]:
        """Bounded all-version ownership proof for the complete relevant pair set.

        Loaded ONCE before any DML and reused by reconciliation. The
        current-version-only ledger read can never see a competing version's
        owner, so this bounded ``node_entity_link_key = ANY(%s) FOR UPDATE``
        query reveals every version owner for the relevant pairs.
        """
        if not pair_keys:
            return []
        cursor.execute(
            "SELECT node_entity_link_owner_id, node_id, entity_id, version_id, "
            "node_entity_link_key, e2b_run_id "
            "FROM okf_e2b_node_link_ownership "
            "WHERE node_entity_link_key = ANY(%s) FOR UPDATE",
            (sorted(pair_keys),),
        )
        return [_normalize_row(row) for row in cursor.fetchall()]

    # -- full preflight before any DML ----------------------------------------
    def _preflight(self, desired: E2bDesiredState) -> None:
        for mention in desired.mentions:
            _preflight_mention(mention)

    # -- full desired-state convergence ----------------------------------------
    def _reconcile(
        self,
        cursor: _CursorWithConnection,
        scope: E2bDocumentScope,
        desired: E2bDesiredState,
        effective_links: Sequence[E2bDesiredLink],
        existing_mentions: Sequence[Mapping[str, object]],
        existing_ledger: Sequence[Mapping[str, object]],
        existing_bridges: Sequence[Mapping[str, object]],
        owner_rows_by_key: Mapping[str, Sequence[Mapping[str, object]]],
        collision_mention_ids: set[str],
        recorder: E2bDmlRecorder,
        stale_counts: dict[str, int],
    ) -> None:
        self._upsert_mentions(
            cursor, scope, desired, existing_mentions, collision_mention_ids, recorder
        )
        self._upsert_links(
            cursor,
            scope,
            effective_links,
            existing_bridges,
            owner_rows_by_key,
            recorder,
        )

        desired_mention_ids = {mention.mention_id for mention in desired.mentions}
        stale_mention_ids = sorted(
            row["mention_id"]
            for row in existing_mentions
            if row.get("e2b_owner_scope") == scope.e2b_owner_scope
            and row["mention_id"] not in desired_mention_ids
        )
        if stale_mention_ids:
            cursor.execute(
                "DELETE FROM entity_mentions "
                "WHERE e2b_owner_scope = %s AND mention_id = ANY(%s)",
                (scope.e2b_owner_scope, stale_mention_ids),
            )
            recorder.record_issued(table="entity_mentions", operation="DELETE")
            stale_counts["entity_mentions"] = len(stale_mention_ids)

        desired_bridge_keys = {
            (link.node_id, link.entity_id) for link in effective_links
        }
        stale_bridge_keys = {
            (row["node_id"], row["entity_id"])
            for row in existing_bridges
            if (row["node_id"], row["entity_id"]) not in desired_bridge_keys
        }
        preserved_bridge_keys = self._bridge_deletion_decision(
            stale_bridge_keys, owner_rows_by_key, scope
        )
        deletable_bridge_keys = stale_bridge_keys - preserved_bridge_keys

        desired_bridge_key_strings = {f"{n}:{e}" for n, e in desired_bridge_keys}
        # Delete every stale CURRENT-version ownership row even when the bridge
        # is preserved for an other-version owner: the current version no longer
        # owns the pair, so its ownership proof is removed. This DELETE precedes
        # any bridge DELETE.
        stale_ledger_keys = sorted(
            {
                row["node_entity_link_key"]
                for row in existing_ledger
                if row.get("version_id") == scope.version_id
                and row["node_entity_link_key"] not in desired_bridge_key_strings
            }
        )
        if stale_ledger_keys:
            cursor.execute(
                "DELETE FROM okf_e2b_node_link_ownership "
                "WHERE version_id = %s AND node_entity_link_key = ANY(%s)",
                (scope.version_id, stale_ledger_keys),
            )
            recorder.record_issued(
                table="okf_e2b_node_link_ownership", operation="DELETE"
            )
            stale_counts["okf_e2b_node_link_ownership"] = len(stale_ledger_keys)

        for node_id, entity_id in sorted(deletable_bridge_keys):
            cursor.execute(
                "DELETE FROM node_entity_links WHERE node_id = %s AND entity_id = %s",
                (node_id, entity_id),
            )
            recorder.record_issued(table="node_entity_links", operation="DELETE")
        stale_counts["node_entity_links"] = len(deletable_bridge_keys)

    def _upsert_mentions(
        self,
        cursor: _CursorWithConnection,
        scope: E2bDocumentScope,
        desired: E2bDesiredState,
        existing_mentions: Sequence[Mapping[str, object]],
        collision_mention_ids: set[str],
        recorder: E2bDmlRecorder,
    ) -> None:
        existing_by_id = {
            row["mention_id"]: row
            for row in existing_mentions
            if row.get("e2b_owner_scope") == scope.e2b_owner_scope
        }
        for mention in desired.mentions:
            if mention.mention_id in collision_mention_ids:
                # Legacy/manual/foreign row with this exact id is preserved and
                # never claimed/rewritten by an ON CONFLICT takeover.
                continue
            projection = _mention_projection(mention, scope)
            existing_row = existing_by_id.get(mention.mention_id)
            if existing_row is not None and _rows_equal(existing_row, projection):
                continue
            _upsert_mention(cursor, projection, recorder)

    def _upsert_links(
        self,
        cursor: _CursorWithConnection,
        scope: E2bDocumentScope,
        links: Sequence[E2bDesiredLink],
        existing_bridges: Sequence[Mapping[str, object]],
        owner_rows_by_key: Mapping[str, Sequence[Mapping[str, object]]],
        recorder: E2bDmlRecorder,
    ) -> None:
        existing_bridge_by_key = {
            (row["node_id"], row["entity_id"]): row for row in existing_bridges
        }
        for link in links:
            pair_key = f"{link.node_id}:{link.entity_id}"
            existing_bridge = existing_bridge_by_key.get((link.node_id, link.entity_id))
            owner_rows = owner_rows_by_key.get(pair_key, ())
            if existing_bridge is None:
                # No pre-existing bridge: materialize the bridge and add the
                # current version's ownership proof.
                _upsert(
                    cursor,
                    "node_entity_links",
                    _bridge_projection(link),
                    ("node_id", "entity_id"),
                    recorder,
                )
                _upsert(
                    cursor,
                    "okf_e2b_node_link_ownership",
                    _ledger_projection(link, scope),
                    ("node_id", "entity_id", "version_id"),
                    recorder,
                )
                continue
            if not owner_rows:
                # Manual/legacy/unowned bridge: the preloaded all-version proof
                # found no E2b owner, so the bridge is preserved as-is and never
                # claimed by a bridge upsert or an ownership INSERT.
                continue
            current_owns = any(
                row.get("version_id") == scope.version_id for row in owner_rows
            )
            other_owns = any(
                row.get("version_id") != scope.version_id for row in owner_rows
            )
            if current_owns and other_owns:
                # Defensive corrupted/schema-inconsistent owner proof (current +
                # another version): migration 003 binds node_id to one version and
                # migration 020's trigger enforces ownership version = node
                # version, so legitimate same-pair co-ownership is unreachable.
                # Fail closed: preserve the shared bridge projection and the
                # ownership state, issue zero bridge/ledger DML.
                continue
            if current_owns:
                # Current-only owner: may rewrite the bridge to the desired
                # projection (the current version exclusively owns it).
                projection = _bridge_projection(link)
                if not _rows_equal(existing_bridge, projection):
                    _upsert(
                        cursor,
                        "node_entity_links",
                        projection,
                        ("node_id", "entity_id"),
                        recorder,
                    )
                continue
            # Only an OTHER-version/foreign version owner exists. Migration 003
            # binds node_id to one version and migration 020's trigger enforces
            # ownership version = node version, so this owner-proof is
            # schema-inconsistent/corrupted for the current node. Fail closed:
            # preserve the bridge and ownership state, issue zero bridge/ledger
            # DML (never insert a current-version ledger row).
            continue

    @staticmethod
    def _bridge_deletion_decision(
        stale_bridge_keys: set[tuple[str, str]],
        owner_rows_by_key: Mapping[str, Sequence[Mapping[str, object]]],
        scope: E2bDocumentScope,
    ) -> set[tuple[str, str]]:
        """Return stale bridge keys that must be PRESERVED (fail closed).

        Consumes the PRE-DML all-version owner proof snapshot loaded once by
        ``_load_owner_proof`` (bounded ``node_entity_link_key = ANY(%s) FOR
        UPDATE``) so no ownership query remains after DML begins. A bridge is
        deleted only when a current-version ledger ownership proof exists AND no
        other version owns that (node_id, entity_id) pair. Unclear/missing
        ownership fails closed and preserves the bridge (and its current-version
        ledger rows).
        """
        preserved: set[tuple[str, str]] = set()
        for node_id, entity_id in stale_bridge_keys:
            pair_rows = owner_rows_by_key.get(f"{node_id}:{entity_id}", ())
            current_proof = any(
                row.get("version_id") == scope.version_id for row in pair_rows
            )
            other_owner_remains = any(
                row.get("version_id") != scope.version_id for row in pair_rows
            )
            if not current_proof or other_owner_remains:
                preserved.add((node_id, entity_id))
        return preserved


def _normalize_value(value: object) -> object:
    """Recursively normalize a psycopg row value for canonical comparison.

    PostgreSQL ``uuid`` columns arrive as ``uuid.UUID`` objects; identity values
    are normalized to their canonical ``str`` form so keys/sorts/comparisons use
    canonical strings (E2a pattern, implemented locally for E2b).
    """
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Mapping):
        return {key: _normalize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_normalize_value(item) for item in value)
    return value


def _normalize_row(row: Mapping[str, object]) -> dict[str, object]:
    """Normalize one fetched row at the repository boundary."""
    return {key: _normalize_value(value) for key, value in row.items()}


def _require_manual_transaction(cursor: _CursorWithConnection) -> None:
    try:
        autocommit = cursor.connection.autocommit
    except AttributeError:
        raise ValueError("connection autocommit must be exactly False") from None
    if type(autocommit) is not bool or autocommit is not False:
        raise ValueError("connection autocommit must be exactly False")


def _preflight_mention(mention: E2bDesiredMention) -> None:
    if (
        type(mention.char_start) is not int
        or type(mention.char_end) is not int
        or not (
            0 <= mention.char_start < mention.char_end <= len(mention.normalized_text)
        )
    ):
        raise ValueError("mention coordinates are out of range")
    if (
        mention.normalized_text[mention.char_start : mention.char_end]
        != mention.mention_text
    ):
        raise ValueError("mention_text does not slice back from normalized_text")
    if mention.input_kind == "corpus_span" and mention.input_id != mention.span_id:
        raise ValueError("corpus mention input_id must equal span_id")
    # Migration-020 document-coordinate contract: both are integers, start >= 0,
    # end > start (no containment relation to the local coordinates is imposed).
    if (
        type(mention.document_char_start) is not int
        or type(mention.document_char_end) is not int
    ):
        raise ValueError("document coordinates must be integers")
    if mention.document_char_start < 0:
        raise ValueError("document_char_start must be >= 0")
    if mention.document_char_start >= mention.document_char_end:
        raise ValueError("document_char_start must be < document_char_end")
    _validate_mention_provenance(mention)


def _validate_mention_provenance(mention: E2bDesiredMention) -> None:
    """Enforce the migration-020 provenance completeness contract.

    Schema/normalization/segmentation/label-map provenance must be complete;
    runtime_compatibility_id may be None. Model-source mentions additionally
    require complete model provenance (model_id, model_revision, 64-hex
    artifact_digest); non-model sources must not carry model provenance.
    """
    for name in ("schema_version", "normalization_version", "segmentation_version"):
        if type(getattr(mention, name)) is not str or not getattr(mention, name):
            raise ValueError(f"{name} must be a non-empty string")
    _digest(mention.label_map_digest, "label_map_digest")
    if mention.source == "model":
        for name in ("model_id", "model_revision"):
            if type(getattr(mention, name)) is not str or not getattr(mention, name):
                raise ValueError(f"model provenance requires {name}")
        _digest(mention.artifact_digest, "artifact_digest")
        if mention.runtime_compatibility_id is not None:
            if (
                type(mention.runtime_compatibility_id) is not str
                or not mention.runtime_compatibility_id
            ):
                raise ValueError("runtime_compatibility_id must be a non-empty string")
    else:
        for name in (
            "model_id",
            "model_revision",
            "artifact_digest",
            "runtime_compatibility_id",
        ):
            if getattr(mention, name) is not None:
                raise ValueError(f"non-model provenance must not carry {name}")


def _preflight_durable_input(desired: E2bDesiredState) -> None:
    """Reject non-corpus durable inputs BEFORE any SQL/DML is issued."""
    for mention in desired.mentions:
        if mention.input_kind != "corpus_span":
            raise ValueError("durable entity mentions require input_kind='corpus_span'")


def _mention_projection(
    mention: E2bDesiredMention, scope: E2bDocumentScope
) -> dict[str, object]:
    return {
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
        "model_id": mention.model_id,
        "model_revision": mention.model_revision,
        "artifact_digest": mention.artifact_digest,
        "schema_version": mention.schema_version,
        "normalization_version": mention.normalization_version,
        "segmentation_version": mention.segmentation_version,
        "label_map_digest": mention.label_map_digest,
        "runtime_compatibility_id": mention.runtime_compatibility_id,
        "e2b_owner_scope": scope.e2b_owner_scope,
    }


def _bridge_projection(link: E2bDesiredLink) -> dict[str, object]:
    return {
        "node_id": link.node_id,
        "entity_id": link.entity_id,
        "ordinal_no": link.ordinal_no,
        "confidence_score": None,
        "mention_text": link.mention_text,
    }


def _ledger_projection(
    link: E2bDesiredLink, scope: E2bDocumentScope
) -> dict[str, object]:
    return {
        "node_entity_link_owner_id": deterministic_id(
            "e2b_link_owner",
            f"{link.node_id}:{link.entity_id}:{scope.version_id}",
        ),
        "node_id": link.node_id,
        "entity_id": link.entity_id,
        "version_id": scope.version_id,
        "node_entity_link_key": f"{link.node_id}:{link.entity_id}",
        "e2b_run_id": deterministic_id(
            "e2b_run", f"{scope.document_id}:{scope.version_id}"
        ),
    }


def _derive_link_pairs(
    mentions: Sequence[E2bDesiredMention],
    span_rows: Sequence[Mapping[str, object]],
    collision_mention_ids: set[str],
) -> tuple[set[tuple[str, str]], dict[tuple[str, str], list[E2bDesiredMention]]]:
    """Map resolved mention spans through tree_node_spans to canonical pairs.

    A resolved mention (``entity_id`` not None) whose span maps to one or more
    tree nodes yields a canonical ``(node_id, entity_id)`` pair per node.
    Unresolved mentions never produce a link. Mentions whose id collides with a
    manual/foreign existing row (``collision_mention_ids``) are excluded so a
    collision-preserved mention can never contribute an E2b bridge/ledger.
    Producers are tracked per pair for deterministic default link generation.
    """
    by_span: dict[str, list[Mapping[str, object]]] = {}
    for row in span_rows:
        by_span.setdefault(str(row["span_id"]), []).append(row)
    pairs: set[tuple[str, str]] = set()
    producers: dict[tuple[str, str], list[E2bDesiredMention]] = {}
    for mention in mentions:
        if mention.entity_id is None:
            continue
        if mention.mention_id in collision_mention_ids:
            continue
        for row in by_span.get(mention.span_id, ()):
            pair = (str(row["node_id"]), mention.entity_id)
            pairs.add(pair)
            producers.setdefault(pair, []).append(mention)
    return pairs, producers


def _validate_links(
    desired: E2bDesiredState, derived_pairs: set[tuple[str, str]]
) -> None:
    """Reject caller-provided links that are not derivable before any DML.

    ``desired.links`` is never an independent proof: every pair must exist in
    the resolved-mention span -> tree_node_spans derived set, otherwise the
    repository fails closed before issuing any DML.
    """
    for link in desired.links:
        if (link.node_id, link.entity_id) not in derived_pairs:
            raise _E2bLinkProofError(
                f"desired link ({link.node_id}, {link.entity_id}) is not derivable "
                "from any resolved mention span mapping"
            )


def _effective_links(
    desired: E2bDesiredState,
    derived_pairs: set[tuple[str, str]],
    producers: dict[tuple[str, str], list[E2bDesiredMention]],
) -> list[E2bDesiredLink]:
    """Materialize links for every derived pair.

    Proven caller-provided links keep their ordinal_no/mention_text; derived
    pairs not explicitly requested use deterministic defaults (ordinal_no 0 and
    the producing mention's mention_text).
    """
    desired_by_pair = {(link.node_id, link.entity_id): link for link in desired.links}
    effective: list[E2bDesiredLink] = []
    for node_id, entity_id in sorted(derived_pairs):
        caller = desired_by_pair.get((node_id, entity_id))
        if caller is not None:
            effective.append(caller)
            continue
        mentions = sorted(
            producers.get((node_id, entity_id), ()), key=lambda m: m.mention_id
        )
        mention_text = mentions[0].mention_text if mentions else ""
        effective.append(
            E2bDesiredLink(
                node_id=node_id,
                entity_id=entity_id,
                ordinal_no=0,
                mention_text=mention_text,
            )
        )
    return effective


def _relevant_pair_keys(
    derived_pairs: set[tuple[str, str]],
    existing_ledger: Sequence[Mapping[str, object]],
    existing_bridges: Sequence[Mapping[str, object]],
) -> set[str]:
    """Collect every pair key that the all-version owner proof must cover.

    The union of the derived desired pairs, every current-version ledger pair,
    and every loaded bridge pair guarantees the pre-DML ``_load_owner_proof``
    query reveals ALL version owners for every pair any DML decision touches.
    """
    keys: set[str] = set()
    for node_id, entity_id in derived_pairs:
        keys.add(f"{node_id}:{entity_id}")
    for row in existing_ledger:
        keys.add(str(row["node_entity_link_key"]))
    for row in existing_bridges:
        keys.add(f"{row['node_id']}:{row['entity_id']}")
    return keys


def _owner_rows_by_key(
    owner_proof_rows: Sequence[Mapping[str, object]],
) -> dict[str, list[Mapping[str, object]]]:
    """Group the pre-DML all-version owner proof by ``node_entity_link_key``."""
    by_key: dict[str, list[Mapping[str, object]]] = {}
    for row in owner_proof_rows:
        key = str(row["node_entity_link_key"])
        by_key.setdefault(key, []).append(row)
    return by_key


def _desired_mention_collisions(
    desired_mention_rows: Sequence[Mapping[str, object]],
    scope: E2bDocumentScope,
) -> set[str]:
    """Return desired mention_ids whose existing row is NOT E2b-owned.

    A bounded desired-ID read may return a row with ``e2b_owner_scope`` NULL
    (manual/legacy) or a foreign scope. Such rows are preserved and never
    claimed/rewritten by an ON CONFLICT takeover, so their ids are excluded from
    entity_mentions upsert processing.
    """
    return {
        str(row["mention_id"])
        for row in desired_mention_rows
        if row.get("e2b_owner_scope") != scope.e2b_owner_scope
    }


def _try_rollback(connection: _Connection) -> bool:
    try:
        connection.rollback()
    except Exception:
        return False
    return True


def _try_close(connection: _Connection) -> bool:
    try:
        connection.close()
    except Exception:
        return False
    return True


def _close_quietly(connection: _Connection) -> None:
    _try_close(connection)


def _commit_outcome_unknown(
    stale_counts: Mapping[str, int],
    primary_dml_by_table: Mapping[str, int],
) -> E2bReconciliationResult:
    """Commit-exception uncertainty result (frozen E2a commit analog).

    The commit result is ambiguous: close the primary, never rollback, never
    audit, freeze outcome_unknown, and PRESERVE the already-issued recorder DML
    map plus stale counts.
    """
    return E2bReconciliationResult(
        outcome="outcome_unknown",
        primary_dml_by_table=dict(primary_dml_by_table),
        stale_deletion_counts=dict(stale_counts),
        failure_audit_outcome=None,
        reconciliation_required=True,
    )


def _cleanup_outcome_unknown() -> E2bReconciliationResult:
    """Cleanup-uncertainty result (frozen E2a cleanup analog).

    Rollback OR primary-close is unconfirmed after a pre-commit failure: publish
    EMPTY public maps and zeroed stale counts even when the recorder itself
    proves prior DML occurred, and require reconciliation.
    """
    return E2bReconciliationResult(
        outcome="outcome_unknown",
        primary_dml_by_table={},
        stale_deletion_counts={table: 0 for table in _STALE_DELETION_TABLES},
        failure_audit_outcome=None,
        reconciliation_required=True,
    )


def _rows_equal(
    existing: Mapping[str, object], projection: Mapping[str, object]
) -> bool:
    for key, value in projection.items():
        existing_value = existing.get(key)
        if not postgres_values_equal(existing_value, value):
            return False
    return True


def _upsert(
    cursor: _CursorWithConnection,
    table: str,
    projection: Mapping[str, object],
    key_columns: tuple[str, ...],
    recorder: E2bDmlRecorder,
) -> None:
    """Issue a stable ON CONFLICT upsert when the persisted projection differs."""
    columns = list(projection.keys())
    column_sql = ", ".join(columns)
    placeholders = ", ".join("%s" for _ in columns)
    mutable = [column for column in columns if column not in key_columns]
    set_sql = ", ".join(f"{column} = EXCLUDED.{column}" for column in mutable)
    where_sql = " OR ".join(
        f"{table}.{column} IS DISTINCT FROM EXCLUDED.{column}" for column in mutable
    )
    cursor.execute(
        f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders}) "
        f"ON CONFLICT ({', '.join(key_columns)}) DO UPDATE SET {set_sql} "
        f"WHERE {where_sql}",
        tuple(projection[column] for column in columns),
    )
    recorder.record_issued(table=table, operation="INSERT")


def _upsert_mention(
    cursor: _CursorWithConnection,
    projection: Mapping[str, object],
    recorder: E2bDmlRecorder,
) -> None:
    """Ownership-safe ``entity_mentions`` upsert.

    The ON CONFLICT UPDATE may only proceed when the existing row is owned by
    the SAME E2b owner scope (``entity_mentions.e2b_owner_scope =
    EXCLUDED.e2b_owner_scope``). A manual (NULL) or foreign-scope row that
    appears at INSERT/conflict time is never claimed or rewritten, closing the
    mention TOCTOU takeover. ``e2b_owner_scope`` is the ownership guard, so it is
    excluded from the change-detection OR.
    """
    columns = list(projection.keys())
    column_sql = ", ".join(columns)
    placeholders = ", ".join("%s" for _ in columns)
    mutable = [column for column in columns if column != "mention_id"]
    set_sql = ", ".join(f"{column} = EXCLUDED.{column}" for column in mutable)
    change_parts = [
        f"entity_mentions.{column} IS DISTINCT FROM EXCLUDED.{column}"
        for column in mutable
        if column != "e2b_owner_scope"
    ]
    where_sql = "entity_mentions.e2b_owner_scope = EXCLUDED.e2b_owner_scope"
    if change_parts:
        where_sql += " AND (" + " OR ".join(change_parts) + ")"
    cursor.execute(
        f"INSERT INTO entity_mentions ({column_sql}) VALUES ({placeholders}) "
        f"ON CONFLICT (mention_id) DO UPDATE SET {set_sql} WHERE {where_sql}",
        tuple(projection[column] for column in columns),
    )
    recorder.record_issued(table="entity_mentions", operation="INSERT")


__all__ = [
    "E2bDesiredLink",
    "E2bDesiredMention",
    "E2bDesiredState",
    "E2bDmlRecorder",
    "E2bDocumentScope",
    "E2bMaterializationRepository",
    "E2bReconciliationResult",
]
