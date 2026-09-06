"""Cursor-only reconciliation for the E2a PostgreSQL materialization cache."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import cast

from ._e2a_materialization_values import (
    CACHE_MEASUREMENT_STATEMENTS,
    CacheMeasurementTemplate,
)
from .e2a_contracts import (
    DmlRecorder,
    E2aDesiredState,
    E2aManualFact,
    E2aReconciliationResult,
    canonical_json_sha256,
)
from .e2a_materialization_dml import (
    DmlTemplate,
    execute_template as _execute_template,
    upsert_if_changed as _upsert_if_changed,
)
from ._e2a_materialization_stale_evidence import (
    delete_stale_evidence as _delete_stale_evidence,
)
from ._e2a_sync_state_operations import (
    delete_stale_sync_state as _delete_stale_sync_state,
    ensure_sync_path_ownership as _ensure_sync_path_ownership,
    upsert_sync_state as _upsert_sync_state,
)
from ._e2a_materialization_inventory import (
    Cursor as _Cursor,
    Scope as _Scope,
    fields as _fields,
    load_existing_scope as _existing_scope,
    mapping as _mapping,
    stale_ids as _stale_ids,
    string as _string,
    string_or_none as _string_or_none,
    validate_destructive_closure as _validate_destructive_closure,
)
from .e2a_materialization_upserts import (
    _canonical_spans as _upsert_canonical_spans_impl,
    _chunks as _upsert_chunks_impl,
    _manual_facts as _upsert_manual_facts_impl,
    _tree as _upsert_tree_impl,
)

_PRIMARY_TABLES = frozenset(
    {
        "canonical_spans",
        "vector_chunks",
        "vector_chunk_spans",
        "tree_nodes",
        "tree_node_spans",
        "entities",
        "relations",
        "evidence",
        "evidence_links",
        "okf_manual_fact_ownership",
        "okf_manual_evidence_targets",
        "okf_sync_state",
        "summaries",
        "node_embeddings",
        "semantic_distribution",
    }
)
_DENYLIST_TABLES = frozenset(
    {
        "chunk_entity_links",
        "node_entity_links",
        "entity_mentions",
        "entity_aliases",
        "entity_merge_log",
        "ner_entities",
        "ner_relations",
        "fusion_state",
        "r3_state",
        "external_projection_status",
    }
)
_CACHE_TABLES = ("summaries", "node_embeddings", "semantic_distribution")
_CACHE_REPAIR_TEMPLATES: Mapping[str, tuple[CacheMeasurementTemplate, DmlTemplate]] = (
    MappingProxyType(
        {
            "summaries": (
                CacheMeasurementTemplate.SUMMARIES,
                DmlTemplate.DELETE_SUMMARIES_BY_NODE_IDS,
            ),
            "node_embeddings": (
                CacheMeasurementTemplate.NODE_EMBEDDINGS,
                DmlTemplate.DELETE_NODE_EMBEDDINGS_BY_NODE_IDS,
            ),
            "semantic_distribution": (
                CacheMeasurementTemplate.SEMANTIC_DISTRIBUTION,
                DmlTemplate.DELETE_SEMANTIC_DISTRIBUTION_BY_NODE_IDS,
            ),
        }
    )
)


class E2aMaterializationRepository:
    """Apply a complete desired state through the caller-owned cursor only."""

    def reconcile(
        self,
        cursor: _Cursor,
        desired: E2aDesiredState,
        *,
        recorder: DmlRecorder,
    ) -> E2aReconciliationResult:
        _validate_desired(desired)
        if type(recorder) is not DmlRecorder:
            raise TypeError("recorder must be DmlRecorder")
        existing = _existing_scope(cursor, desired)
        _ensure_sync_path_ownership(cursor, desired)
        closure = _validate_destructive_closure(cursor, desired, existing)
        stale_counts: dict[str, int] = {}
        cache_counts: dict[str, int] = {}
        _upsert_canonical_spans(cursor, desired, existing, recorder)
        _upsert_tree(cursor, desired, existing, recorder)
        _delete_stale_links(
            cursor,
            "tree_node_spans",
            existing["tree_node_spans"],
            desired.tree_node_span_links,
            ("node_id", "span_id"),
            recorder,
            stale_counts,
        )
        _upsert_chunks(cursor, desired, existing, recorder)
        _delete_stale_links(
            cursor,
            "vector_chunk_spans",
            existing["vector_chunk_spans"],
            desired.vector_chunk_span_links,
            ("chunk_id", "span_id"),
            recorder,
            stale_counts,
        )
        # Stale evidence links must be deleted before the ownership upsert:
        # fk_evidence_links_ownership_scope is non-deferrable NO ACTION, so a
        # v1-to-v2 scope_version_id UPDATE on the shared ownership_id row is
        # checked immediately while any v1 evidence link still references the
        # old ownership scope.
        _delete_stale_evidence(cursor, desired, existing, recorder, stale_counts)
        _upsert_manual_facts(cursor, desired, existing, recorder)
        _upsert_evidence(cursor, desired, existing, recorder)
        _upsert_sync_state(cursor, desired, existing, recorder)
        stale_tree_node_ids = _repair_stale_tree_nodes(
            cursor, desired, existing, recorder, cache_counts
        )
        _delete_stale_chunks(cursor, desired, existing, recorder, stale_counts)
        _delete_stale_tree_nodes(cursor, stale_tree_node_ids, recorder, stale_counts)
        _delete_stale_ownership(
            cursor, desired, existing, closure, recorder, stale_counts
        )
        _delete_stale_sync_state(cursor, desired, existing, recorder, stale_counts)
        _delete_stale_spans(cursor, desired, existing, recorder, stale_counts)
        primary_counts = {
            table: recorder.primary_dml_by_table.get(table, 0)
            for table in sorted(_PRIMARY_TABLES)
        }
        denylist_counts = {
            table: recorder.denylist_dml_counts.get(table, 0)
            for table in sorted(_DENYLIST_TABLES)
        }
        return E2aReconciliationResult(
            outcome="changed" if any(primary_counts.values()) else "no_op",
            manifest_sha256=desired.corpus_manifest_sha256,
            primary_dml_by_table=primary_counts,
            denylist_dml_counts=denylist_counts,
            comparator_parity=True,
            stale_deletion_counts=stale_counts,
            cache_invalidation_counts=cache_counts,
            failure_audit_outcome=None,
            post_rollback_failure_audit_outcome=None,
        )


def _validate_desired(desired: E2aDesiredState) -> None:
    if type(desired) is not E2aDesiredState:
        raise TypeError("desired state must be E2aDesiredState")
    if canonical_json_sha256(desired.corpus_manifest) != desired.corpus_manifest_sha256:
        raise ValueError("desired state manifest hash is invalid")
    if not desired.parents and any(
        (
            desired.canonical_spans,
            desired.vector_chunks,
            desired.vector_chunk_span_links,
            desired.tree_nodes,
            desired.tree_node_span_links,
            desired.evidence_objects,
            desired.evidence_links,
            desired.sync_state_rows,
        )
    ):
        raise ValueError("parentless desired state contains parent-scoped rows")
    if not desired.parents and any(
        ownership.version_id is not None or ownership.document_id is not None
        for ownership in desired.ownership_facts
    ):
        raise ValueError("parentless desired state contains scoped ownership facts")
    _finite_json(desired.corpus_manifest)
    for collection in (
        desired.vector_chunks,
        desired.vector_chunk_span_links,
        desired.tree_nodes,
        desired.tree_node_span_links,
        desired.sync_state_rows,
    ):
        _finite_json(collection)
    for relation in desired.manual_relations:
        _relation_payload(relation)
    for link in desired.evidence_links:
        if link.confidence is not None:
            raise ValueError("manual evidence confidence must be None")


def _finite_json(value: object) -> None:
    if value is None or type(value) in {bool, int}:
        return
    if type(value) is str:
        if "\x00" in value:
            raise ValueError("JSON values must not contain NUL characters")
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("JSON values must be finite")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if type(key) is not str:
                raise ValueError("JSON keys must be strings")
            if "\x00" in key:
                raise ValueError("JSON values must not contain NUL characters")
            _finite_json(item)
        return
    if type(value) in {tuple, list}:
        sequence = cast(Sequence[object], value)
        for item in sequence:
            _finite_json(item)
        return
    raise ValueError("desired state contains a non-JSON value")


def _upsert_canonical_spans(
    cursor: _Cursor,
    desired: E2aDesiredState,
    existing: Mapping[str, tuple[Mapping[str, object], ...]],
    recorder: DmlRecorder,
) -> None:
    _upsert_canonical_spans_impl(
        cursor,
        desired,
        existing,
        recorder,
        span_metadata=_span_metadata,
        indexed=_indexed,
        upsert=_upsert_if_changed,
    )


def _span_metadata(desired: E2aDesiredState) -> Mapping[str, tuple[object, object]]:
    chunks = _indexed_mappings(desired.vector_chunks, "chunk_id")
    metadata: dict[str, tuple[object, object]] = {}
    for value in desired.vector_chunk_span_links:
        row = _mapping(value)
        chunk = chunks.get(_string(row.get("chunk_id")))
        span_id = _string(row.get("span_id"))
        if chunk is not None:
            metadata[span_id] = (chunk.get("page_no"), chunk.get("heading_path"))
    return metadata


def _upsert_tree(
    cursor: _Cursor,
    desired: E2aDesiredState,
    existing: Mapping[str, tuple[Mapping[str, object], ...]],
    recorder: DmlRecorder,
) -> None:
    _upsert_tree_impl(
        cursor,
        desired,
        existing,
        recorder,
        parent_first=_parent_first,
        mapping=_mapping,
        fields=_fields,
        string=_string,
        indexed=_indexed,
        upsert=_upsert_if_changed,
        upsert_links=_upsert_links,
    )


def _upsert_chunks(
    cursor: _Cursor,
    desired: E2aDesiredState,
    existing: Mapping[str, tuple[Mapping[str, object], ...]],
    recorder: DmlRecorder,
) -> None:
    _upsert_chunks_impl(
        cursor,
        desired,
        existing,
        recorder,
        mapping=_mapping,
        fields=_fields,
        string=_string,
        indexed=_indexed,
        upsert=_upsert_if_changed,
        upsert_links=_upsert_links,
    )


def _upsert_manual_facts(
    cursor: _Cursor,
    desired: E2aDesiredState,
    existing: Mapping[str, tuple[Mapping[str, object], ...]],
    recorder: DmlRecorder,
) -> None:
    _upsert_manual_facts_impl(
        cursor,
        desired,
        existing,
        recorder,
        natural_object=_natural_object,
        relation_payload=_relation_payload,
        indexed=_indexed,
        upsert=_upsert_if_changed,
    )


def _upsert_evidence(
    cursor: _Cursor,
    desired: E2aDesiredState,
    existing: Mapping[str, tuple[Mapping[str, object], ...]],
    recorder: DmlRecorder,
) -> None:
    old_evidence = _indexed(existing["evidence"], "evidence_id")
    for evidence in desired.evidence_objects:
        evidence_row = {
            "evidence_id": evidence.evidence_id,
            "version_id": evidence.version_id,
        }
        _upsert_if_changed(
            cursor,
            "evidence",
            evidence_row,
            ("evidence_id",),
            ("version_id",),
            old_evidence.get(evidence.evidence_id),
            recorder,
        )
    target_rows = tuple(
        {
            "version_id": evidence.version_id,
            "evidence_id": evidence.evidence_id,
            "entity_id": evidence.entity_id,
            "relation_id": evidence.relation_id,
        }
        for evidence in desired.evidence_objects
    )
    _upsert_links(
        cursor,
        "okf_manual_evidence_targets",
        target_rows,
        existing["okf_manual_evidence_targets"],
        ("version_id", "evidence_id"),
        ("entity_id", "relation_id"),
        recorder,
    )
    old_links = _indexed(existing["evidence_links"], "evidence_link_id")
    for link in desired.evidence_links:
        link_row: Mapping[str, object] = {
            "evidence_link_id": link.evidence_link_id,
            "version_id": link.version_id,
            "entity_id": link.entity_id,
            "relation_id": link.relation_id,
            "span_id": link.span_id,
            "source_kind": link.source_kind,
            "confidence_score": link.confidence,
            "evidence_id": link.evidence_id,
            "ownership_id": link.ownership_id,
            "ownership_scope_version_id": link.ownership_scope_version_id,
            "manual_entity_id": link.manual_entity_id,
            "manual_relation_id": link.manual_relation_id,
        }
        _upsert_if_changed(
            cursor,
            "evidence_links",
            link_row,
            ("evidence_link_id",),
            tuple(key for key in link_row if key != "evidence_link_id"),
            old_links.get(link.evidence_link_id),
            recorder,
        )


def _upsert_links(
    cursor: _Cursor,
    table: str,
    values: Sequence[object],
    existing: Sequence[Mapping[str, object]],
    key_fields: tuple[str, ...],
    mutable_fields: tuple[str, ...],
    recorder: DmlRecorder,
) -> None:
    old = {
        tuple(_string(row.get(field)) for field in key_fields): row for row in existing
    }
    for value in values:
        row = _fields(_mapping(value), *key_fields, *mutable_fields)
        key = tuple(_string(row[field]) for field in key_fields)
        _upsert_if_changed(
            cursor,
            table,
            row,
            key_fields,
            mutable_fields,
            old.get(key),
            recorder,
        )


def _delete_stale_links(
    cursor: _Cursor,
    table: str,
    existing: Sequence[Mapping[str, object]],
    desired: Sequence[object],
    key_fields: tuple[str, str],
    recorder: DmlRecorder,
    stale_counts: dict[str, int],
) -> None:
    desired_keys = {
        tuple(_string(_mapping(value).get(field)) for field in key_fields)
        for value in desired
    }
    stale_keys = sorted(
        {tuple(_string(row.get(field)) for field in key_fields) for row in existing}
        - desired_keys
    )
    if not stale_keys:
        return
    templates = {
        (
            "tree_node_spans",
            ("node_id", "span_id"),
        ): DmlTemplate.DELETE_TREE_NODE_SPAN_BY_PAIR,
        (
            "vector_chunk_spans",
            ("chunk_id", "span_id"),
        ): DmlTemplate.DELETE_VECTOR_CHUNK_SPAN_BY_PAIR,
    }
    template = templates.get((table, key_fields))
    if template is None:
        raise ValueError("stale link projection is invalid")
    for key in stale_keys:
        _execute_template(cursor, template, key, recorder)
    stale_counts[table] = len(stale_keys)


def _repair_stale_tree_nodes(
    cursor: _Cursor,
    desired: E2aDesiredState,
    existing: _Scope,
    recorder: DmlRecorder,
    cache_counts: dict[str, int],
) -> tuple[str, ...]:
    stale_ids = _stale_ids(existing["tree_nodes"], desired.tree_nodes, "node_id")
    if not stale_ids:
        return ()
    targets = _tree_repair_targets(desired.tree_nodes)
    retained_chunk_ids = {
        _string(_mapping(value).get("chunk_id")) for value in desired.vector_chunks
    }
    for chunk in existing["vector_chunks"]:
        chunk_id = _string(chunk.get("chunk_id"))
        if chunk_id not in retained_chunk_ids:
            continue
        old_node = chunk.get("node_id")
        if _string_or_none(old_node) not in stale_ids:
            continue
        target = targets.get(_string(chunk.get("version_id")))
        if target is None:
            continue
        _execute_template(
            cursor,
            DmlTemplate.UPDATE_VECTOR_CHUNK_NODE,
            (target, chunk_id, _string_or_none(old_node)),
            recorder,
        )
    for table in _CACHE_TABLES:
        measurement_template, delete_template = _CACHE_REPAIR_TEMPLATES[table]
        affected_rows = _cache_rows_for_stale_nodes(
            cursor, measurement_template, stale_ids
        )
        _execute_template(
            cursor,
            delete_template,
            (list(stale_ids),),
            recorder,
        )
        recorder.record_cache_effect(table=table, count=affected_rows)
        cache_counts[table] = affected_rows
    return tuple(stale_ids)


def _delete_stale_tree_nodes(
    cursor: _Cursor,
    stale_ids: Sequence[str],
    recorder: DmlRecorder,
    stale_counts: dict[str, int],
) -> None:
    if not stale_ids:
        return
    _execute_template(
        cursor,
        DmlTemplate.DELETE_TREE_NODE_SPANS_BY_NODE_IDS,
        (list(stale_ids),),
        recorder,
    )
    _execute_template(
        cursor,
        DmlTemplate.DELETE_TREE_NODES_BY_NODE_IDS,
        (list(stale_ids),),
        recorder,
    )
    stale_counts["tree_nodes"] = len(stale_ids)


def _cache_rows_for_stale_nodes(
    cursor: _Cursor,
    template: CacheMeasurementTemplate,
    stale_ids: Sequence[str],
) -> int:
    """Measure cache rows through a closed static query template."""
    if type(template) is not CacheMeasurementTemplate:
        raise ValueError("cache measurement template is invalid")
    cursor.execute(
        CACHE_MEASUREMENT_STATEMENTS[template],
        (list(stale_ids),),
    )
    rows = cursor.fetchall()
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        raise ValueError("cache state query returned an invalid result set")
    for row in rows:
        if not isinstance(row, Mapping) or "node_id" not in row:
            raise ValueError("cache state query returned a malformed row")
        _string(row["node_id"])
    return len(rows)


def _delete_stale_chunks(
    cursor: _Cursor,
    desired: E2aDesiredState,
    existing: Mapping[str, tuple[Mapping[str, object], ...]],
    recorder: DmlRecorder,
    stale_counts: dict[str, int],
) -> None:
    stale_ids = _stale_ids(existing["vector_chunks"], desired.vector_chunks, "chunk_id")
    if not stale_ids:
        return
    _execute_template(
        cursor,
        DmlTemplate.DELETE_VECTOR_CHUNK_SPANS_BY_CHUNK_IDS,
        (list(stale_ids),),
        recorder,
    )
    _execute_template(
        cursor,
        DmlTemplate.DELETE_VECTOR_CHUNKS_BY_CHUNK_IDS,
        (list(stale_ids),),
        recorder,
    )
    stale_counts["vector_chunks"] = len(stale_ids)


def _delete_stale_ownership(
    cursor: _Cursor,
    desired: E2aDesiredState,
    existing: _Scope,
    preserve: Mapping[tuple[str, str], bool],
    recorder: DmlRecorder,
    stale_counts: dict[str, int],
) -> None:
    desired_ids = {owner.ownership_id for owner in desired.ownership_facts}
    stale = [
        row
        for row in existing["okf_manual_fact_ownership"]
        if _string(row.get("ownership_id")) not in desired_ids
    ]
    if not stale:
        return
    facts = {
        (_string(row.get("fact_kind")), _string(row.get("fact_id"))) for row in stale
    }
    if any(kind not in {"entity", "relation"} for kind, _ in facts):
        raise ValueError("ownership fact kind is invalid")
    retiring_facts = tuple(
        (kind, fact_id)
        for kind, fact_id in facts
        if not preserve.get((kind, fact_id), False)
    )
    owner_ids = sorted(_string(row.get("ownership_id")) for row in stale)
    _execute_template(
        cursor,
        DmlTemplate.DELETE_OWNERSHIP_BY_IDS,
        (list(owner_ids),),
        recorder,
    )
    stale_counts["okf_manual_fact_ownership"] = len(owner_ids)
    templates = {
        ("relation", "relations", "relation_id"): DmlTemplate.DELETE_RELATION_BY_ID,
        ("entity", "entities", "entity_id"): DmlTemplate.DELETE_ENTITY_BY_ID,
    }
    for kind, table, identifier in (
        ("relation", "relations", "relation_id"),
        ("entity", "entities", "entity_id"),
    ):
        template = templates[(kind, table, identifier)]
        for fact_id in sorted(
            fact_id for fact_kind, fact_id in retiring_facts if fact_kind == kind
        ):
            _execute_template(cursor, template, (fact_id,), recorder)


def _delete_stale_spans(
    cursor: _Cursor,
    desired: E2aDesiredState,
    existing: Mapping[str, tuple[Mapping[str, object], ...]],
    recorder: DmlRecorder,
    stale_counts: dict[str, int],
) -> None:
    stale_ids = _stale_ids(
        existing["canonical_spans"], desired.canonical_spans, "span_id"
    )
    if not stale_ids:
        return
    _execute_template(
        cursor,
        DmlTemplate.DELETE_TREE_NODE_SPANS_BY_SPAN_IDS,
        (list(stale_ids),),
        recorder,
    )
    _execute_template(
        cursor,
        DmlTemplate.DELETE_VECTOR_CHUNK_SPANS_BY_SPAN_IDS,
        (list(stale_ids),),
        recorder,
    )
    _execute_template(
        cursor,
        DmlTemplate.DELETE_CANONICAL_SPANS_BY_IDS,
        (list(stale_ids),),
        recorder,
    )
    stale_counts["canonical_spans"] = len(stale_ids)


def _relation_payload(fact: E2aManualFact) -> Mapping[str, object]:
    natural = _natural_object(fact)
    qualifiers = fact.qualifiers
    raw_confidence = qualifiers.get("confidence")
    confidence: int | float | None
    if raw_confidence is None:
        confidence = None
    elif isinstance(raw_confidence, (int, float)) and type(raw_confidence) is not bool:
        if not math.isfinite(raw_confidence):
            raise ValueError("finite confidence is required")
        confidence = raw_confidence
    else:
        raise ValueError("finite confidence is required")
    nested = qualifiers.get("qualifiers", {})
    if not isinstance(nested, Mapping):
        raise ValueError("relation qualifiers must be an object")
    _finite_json(nested)
    subject = natural.get("subject_entity_id")
    predicate = natural.get("predicate")
    object_id = natural.get("object_entity_id")
    if (
        type(subject) is not str
        or type(predicate) is not str
        or type(object_id) is not str
    ):
        raise ValueError("relation natural key is invalid")
    negation = qualifiers.get("negation", False)
    if type(negation) is not bool:
        raise ValueError("relation negation is invalid")
    condition = qualifiers.get("condition")
    direction = qualifiers.get("direction")
    if condition is not None and type(condition) is not str:
        raise ValueError("relation condition is invalid")
    if direction is not None and type(direction) is not str:
        raise ValueError("relation direction is invalid")
    return {
        "relation_id": fact.fact_id,
        "relation_key": fact.natural_key,
        "relation_type": predicate,
        "source_entity_id": subject,
        "target_entity_id": object_id,
        "negation": negation,
        "condition": condition,
        "direction": direction,
        "confidence": confidence,
        "qualifiers": nested,
    }


def _natural_object(fact: E2aManualFact) -> Mapping[str, object]:
    try:
        value = json.loads(fact.natural_key)
    except json.JSONDecodeError:
        raise ValueError("manual fact natural key is invalid") from None
    if not isinstance(value, Mapping):
        raise ValueError("manual fact natural key is invalid")
    return value


def _indexed(
    values: Sequence[Mapping[str, object]], field: str
) -> Mapping[str, Mapping[str, object]]:
    return {_string(value.get(field)): value for value in values}


def _indexed_mappings(
    values: Sequence[object], field: str
) -> Mapping[str, Mapping[str, object]]:
    return {_string(_mapping(value).get(field)): _mapping(value) for value in values}


def _parent_first(values: Sequence[object]) -> tuple[object, ...]:
    pending = {_string(_mapping(value).get("node_id")): value for value in values}
    ordered: list[object] = []
    emitted: set[str] = set()
    while pending:
        ready = [
            (node_id, value)
            for node_id, value in pending.items()
            if _string_or_none(_mapping(value).get("parent_node_id"))
            in {None, *emitted}
        ]
        if not ready:
            raise ValueError("tree nodes do not form a parent-first forest")
        for node_id, value in sorted(ready):
            ordered.append(value)
            emitted.add(node_id)
            del pending[node_id]
    return tuple(ordered)


def _tree_repair_targets(values: Sequence[object]) -> Mapping[str, str]:
    rows = [_mapping(value) for value in values]
    roots = [row for row in rows if row.get("parent_node_id") is None]
    candidates = roots or rows
    targets: dict[str, str] = {}
    for row in sorted(
        candidates,
        key=lambda item: (
            _string(item.get("version_id")),
            _string(item.get("node_id")),
        ),
    ):
        targets.setdefault(_string(row.get("version_id")), _string(row.get("node_id")))
    return targets


__all__ = ["DmlRecorder", "E2aMaterializationRepository"]
