"""Immutable, deterministic contracts for E2a corpus admission."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from .e2a_contract_graph import (
    _evidence_target,
    _manual_evidence_link_id as _manual_evidence_link_identity,
    _validate_evidence_graph as _validate_evidence_graph_impl,
    _validate_ownership_fields,
    _validate_ownership_graph,
)
from ._e2a_desired_projection_validation import validate_projection_graph
from .e2a_contract_primitives import (
    _canonical_value,
    _counts,
    _digest,
    _frozen_json_tuple,
    _frozen_mapping,
    _path,
    _tuple,
    _typed,
    _unicode_scalar,
    _unique,
    _uuid,
    _string_key as _string_key,
    _freeze_json as _freeze_json,
)

E2A_NAMESPACE = uuid5(NAMESPACE_URL, "https://gitnexus.local/okf/e2a")
E2A_GLOBAL_SCOPE_VERSION_ID = "00000000-0000-0000-0000-000000000000"
Outcome = Literal[
    "changed",
    "no_op",
    "rolled_back_failure",
    "acceptance_blocked",
    "outcome_unknown",
]


def canonical_json(value: object) -> str:
    """Encode only recursively immutable, finite JSON values deterministically."""
    return json.dumps(
        _canonical_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_json_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def deterministic_id(kind: str, natural_key: str) -> str:
    if (
        type(kind) is not str
        or type(natural_key) is not str
        or not kind
        or not natural_key
    ):
        raise ValueError("deterministic identity requires a kind and natural key")
    return str(uuid5(E2A_NAMESPACE, f"{kind}:{natural_key}"))


@dataclass(frozen=True)
class E2aParent:
    document_id: str
    version_id: str
    relative_path: str
    canonical_hash: str

    def __post_init__(self) -> None:
        _uuid(self.document_id, "document_id")
        _uuid(self.version_id, "version_id")
        _path(self.relative_path)
        _digest(self.canonical_hash, "canonical_hash")


@dataclass(frozen=True)
class E2aSpan:
    document_id: str
    version_id: str
    span_id: str
    offset: int
    text: str

    def __post_init__(self) -> None:
        _uuid(self.document_id, "document_id")
        _uuid(self.version_id, "version_id")
        _uuid(self.span_id, "span_id")
        if type(self.offset) is not int or self.offset < 0:
            raise ValueError("canonical span has invalid coordinates")
        if type(self.text) is not str or not self.text:
            raise ValueError("canonical span has invalid coordinates")
        _unicode_scalar(self.text, "span text")


@dataclass(frozen=True)
class E2aManualFact:
    fact_id: str
    fact_kind: Literal["entity", "relation", "concept"]
    relative_path: str
    source_digest: str
    qualifiers: Mapping[str, object] = field(default_factory=dict)
    natural_key: str = ""

    def __post_init__(self) -> None:
        _uuid(self.fact_id, "fact_id")
        if type(self.fact_kind) is not str or self.fact_kind not in {
            "entity",
            "relation",
            "concept",
        }:
            raise ValueError("manual fact kind is unsupported")
        _path(self.relative_path)
        _digest(self.source_digest, "source_digest")
        if type(self.natural_key) is not str or not self.natural_key:
            raise ValueError("manual fact natural key must be a non-empty string")
        _unicode_scalar(self.natural_key, "manual fact natural key")
        expected = deterministic_id(self.fact_kind, self.natural_key)
        if self.fact_id != expected:
            raise ValueError("manual fact identity does not match natural key")
        object.__setattr__(
            self, "qualifiers", _frozen_mapping(self.qualifiers, "qualifiers")
        )


@dataclass(frozen=True)
class E2aEvidenceObject:
    """One deterministic manual evidence object per target/version group."""

    evidence_id: str
    version_id: str
    entity_id: str | None
    relation_id: str | None

    @classmethod
    def create(
        cls,
        *,
        version_id: str,
        entity_id: str | None,
        relation_id: str | None,
    ) -> E2aEvidenceObject:
        target_kind, target_id = _evidence_target(entity_id, relation_id)
        _uuid(version_id, "version_id")
        natural_key = canonical_json(
            {
                "target_kind": target_kind,
                "target_id": target_id,
                "version_id": version_id,
            }
        )
        return cls(
            deterministic_id("manual_evidence", natural_key),
            version_id,
            entity_id,
            relation_id,
        )

    def __post_init__(self) -> None:
        _uuid(self.evidence_id, "evidence_id")
        _uuid(self.version_id, "version_id")
        target_kind, target_id = _evidence_target(self.entity_id, self.relation_id)
        expected = deterministic_id(
            "manual_evidence",
            canonical_json(
                {
                    "target_kind": target_kind,
                    "target_id": target_id,
                    "version_id": self.version_id,
                }
            ),
        )
        if self.evidence_id != expected:
            raise ValueError("manual evidence identity does not match target version")


@dataclass(frozen=True)
class E2aEvidenceReference:
    """One deterministic manual evidence link and its future cursor projection."""

    document_id: str
    version_id: str
    span_id: str | None
    entity_id: str | None
    relation_id: str | None
    evidence_id: str
    ownership_id: str
    ownership_scope_version_id: str
    source_kind: Literal["manual_okf"] = field(init=False, default="manual_okf")
    confidence: None = field(init=False, default=None)
    target_kind: Literal["entity", "relation"] = field(init=False)
    target_id: str = field(init=False)
    manual_entity_id: str | None = field(init=False)
    manual_relation_id: str | None = field(init=False)
    evidence_link_id: str = field(init=False)

    def __post_init__(self) -> None:
        _uuid(self.document_id, "document_id")
        _uuid(self.version_id, "version_id")
        if self.span_id is None:
            raise ValueError("manual evidence requires span_id")
        _uuid(self.span_id, "span_id")
        target_kind, target_id = _evidence_target(self.entity_id, self.relation_id)
        _uuid(self.evidence_id, "evidence_id")
        _uuid(self.ownership_id, "ownership_id")
        _uuid(self.ownership_scope_version_id, "ownership_scope_version_id")
        object.__setattr__(self, "target_kind", target_kind)
        object.__setattr__(self, "target_id", target_id)
        object.__setattr__(
            self,
            "manual_entity_id",
            target_id if target_kind == "entity" else None,
        )
        object.__setattr__(
            self,
            "manual_relation_id",
            target_id if target_kind == "relation" else None,
        )
        object.__setattr__(
            self,
            "evidence_link_id",
            _manual_evidence_link_identity(
                evidence_id=self.evidence_id,
                ownership_id=self.ownership_id,
                ownership_scope_version_id=self.ownership_scope_version_id,
                span_id=self.span_id,
                target_id=target_id,
                target_kind=target_kind,
                version_id=self.version_id,
                canonical_json=canonical_json,
                deterministic_id=deterministic_id,
            ),
        )


@dataclass(frozen=True)
class E2aOwnershipFact:
    ownership_id: str
    relative_path: str
    fact_kind: Literal["entity", "relation"]
    fact_id: str
    source_digest: str
    document_id: str | None = None
    version_id: str | None = None
    scope_version_id: str = E2A_GLOBAL_SCOPE_VERSION_ID

    @classmethod
    def create(
        cls,
        *,
        relative_path: str,
        fact_kind: Literal["entity", "relation"],
        fact_id: str,
        source_digest: str,
        document_id: str | None = None,
        version_id: str | None = None,
        scope_version_id: str | None = None,
    ) -> E2aOwnershipFact:
        _validate_ownership_fields(
            relative_path,
            fact_kind,
            fact_id,
            source_digest,
            document_id,
            version_id,
        )
        expected_scope = version_id or E2A_GLOBAL_SCOPE_VERSION_ID
        if scope_version_id is not None and scope_version_id != expected_scope:
            raise ValueError("ownership scope does not match document version")
        # This exact delimiter form is the established ownership identity contract.
        natural_key = f"{relative_path}:{fact_kind}:{fact_id}"
        return cls(
            deterministic_id("ownership", natural_key),
            relative_path,
            fact_kind,
            fact_id,
            source_digest,
            document_id,
            version_id,
            expected_scope,
        )

    def __post_init__(self) -> None:
        _uuid(self.ownership_id, "ownership_id")
        _validate_ownership_fields(
            self.relative_path,
            self.fact_kind,
            self.fact_id,
            self.source_digest,
            self.document_id,
            self.version_id,
        )
        expected_scope = self.version_id or E2A_GLOBAL_SCOPE_VERSION_ID
        _uuid(self.scope_version_id, "scope_version_id")
        if self.scope_version_id != expected_scope:
            raise ValueError("ownership scope does not match document version")
        expected_id = deterministic_id(
            "ownership", f"{self.relative_path}:{self.fact_kind}:{self.fact_id}"
        )
        if self.ownership_id != expected_id:
            raise ValueError("ownership identity does not match natural key")


@dataclass(frozen=True)
class E2aDesiredState:
    corpus_manifest: Mapping[str, object]
    corpus_manifest_sha256: str
    parents: tuple[E2aParent, ...]
    canonical_spans: tuple[E2aSpan, ...]
    vector_chunks: tuple[object, ...]
    vector_chunk_span_links: tuple[object, ...]
    tree_nodes: tuple[object, ...]
    tree_node_span_links: tuple[object, ...]
    manual_entities: tuple[E2aManualFact, ...]
    manual_relations: tuple[E2aManualFact, ...]
    evidence_objects: tuple[E2aEvidenceObject, ...]
    evidence_links: tuple[E2aEvidenceReference, ...]
    ownership_facts: tuple[E2aOwnershipFact, ...]
    sync_state_rows: tuple[object, ...]
    validation_metadata: Mapping[str, object]
    provenance_metadata: Mapping[str, object]
    manual_concepts: tuple[E2aManualFact, ...] = ()

    def __post_init__(self) -> None:
        _digest(self.corpus_manifest_sha256, "corpus_manifest_sha256")
        for name in ("corpus_manifest", "validation_metadata", "provenance_metadata"):
            object.__setattr__(self, name, _frozen_mapping(getattr(self, name), name))
        for name in (
            "parents",
            "canonical_spans",
            "manual_entities",
            "manual_relations",
            "manual_concepts",
            "evidence_objects",
            "evidence_links",
            "ownership_facts",
        ):
            object.__setattr__(self, name, _tuple(getattr(self, name), name))
        for name in (
            "vector_chunks",
            "vector_chunk_span_links",
            "tree_nodes",
            "tree_node_span_links",
            "sync_state_rows",
        ):
            object.__setattr__(
                self, name, _frozen_json_tuple(getattr(self, name), name)
            )
        if canonical_json_sha256(self.corpus_manifest) != self.corpus_manifest_sha256:
            raise ValueError("corpus manifest hash does not match canonical manifest")
        _typed(self.parents, E2aParent, "parents")
        _typed(self.canonical_spans, E2aSpan, "canonical_spans")
        _typed(self.manual_entities, E2aManualFact, "manual_entities")
        _typed(self.manual_relations, E2aManualFact, "manual_relations")
        _typed(self.manual_concepts, E2aManualFact, "manual_concepts")
        _typed(self.evidence_objects, E2aEvidenceObject, "evidence_objects")
        _typed(self.evidence_links, E2aEvidenceReference, "evidence_links")
        _typed(self.ownership_facts, E2aOwnershipFact, "ownership_facts")
        if (
            any(item.fact_kind != "entity" for item in self.manual_entities)
            or any(item.fact_kind != "relation" for item in self.manual_relations)
            or any(item.fact_kind != "concept" for item in self.manual_concepts)
        ):
            raise ValueError("manual facts are in the wrong collection")
        _unique(self.parents, lambda value: value.version_id, "parent version")
        _unique(self.canonical_spans, lambda value: value.span_id, "span")
        _validate_parent_span_closure(self.parents, self.canonical_spans)
        validate_projection_graph(
            self.parents,
            self.canonical_spans,
            self.vector_chunks,
            self.vector_chunk_span_links,
            self.tree_nodes,
            self.tree_node_span_links,
            self.sync_state_rows,
        )
        _unique(self.ownership_facts, lambda value: value.ownership_id, "ownership")
        facts = (*self.manual_entities, *self.manual_relations, *self.manual_concepts)
        _unique(facts, lambda value: value.fact_id, "manual fact")
        _validate_ownership_graph(
            self.corpus_manifest,
            self.parents,
            facts,
            self.ownership_facts,
        )
        _validate_evidence_graph_impl(
            parents=self.parents,
            spans=self.canonical_spans,
            facts=facts,
            ownership=self.ownership_facts,
            objects=self.evidence_objects,
            links=self.evidence_links,
            canonical_json=canonical_json,
            deterministic_id=deterministic_id,
            global_scope_version_id=E2A_GLOBAL_SCOPE_VERSION_ID,
        )


_E2A_PRIMARY_TABLES = frozenset(
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
_E2A_DENYLIST_TABLES = frozenset(
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
_E2A_CACHE_TABLES = frozenset({"summaries", "node_embeddings", "semantic_distribution"})


@dataclass
class DmlRecorder:
    """Record direct E2a DML separately from explicitly measured effects."""

    primary_dml_by_table: dict[str, int] = field(default_factory=dict)
    denylist_dml_counts: dict[str, int] = field(default_factory=dict)
    measured_cache_effects: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.primary_dml_by_table = dict(_counts(self.primary_dml_by_table))
        self.denylist_dml_counts = dict(_counts(self.denylist_dml_counts))
        self.measured_cache_effects = dict(_counts(self.measured_cache_effects))

    @property
    def issued_dml_by_table(self) -> Mapping[str, int]:
        return _counts(self.primary_dml_by_table)

    def record_issued(self, *, table: str, operation: str) -> None:
        if type(operation) is not str or operation not in {
            "INSERT",
            "UPDATE",
            "DELETE",
        }:
            raise ValueError("DML operation is unsupported")
        self._validate_table(table=table, count=1, forbidden_message="forbidden DML")
        self.primary_dml_by_table[table] = self.primary_dml_by_table.get(table, 0) + 1

    def record_measured_effect(self, *, table: str, count: int, origin: str) -> None:
        if type(origin) is not str or not origin:
            raise ValueError("measured effect origin is required")
        self._validate_table(
            table=table, count=count, forbidden_message="forbidden cascade"
        )

    def record_cache_effect(self, *, table: str, count: int) -> None:
        if table not in _E2A_CACHE_TABLES:
            raise ValueError("cache effect table is unsupported")
        self.record_measured_effect(table=table, count=count, origin="cache")
        self.measured_cache_effects[table] = (
            self.measured_cache_effects.get(table, 0) + count
        )

    def _validate_table(
        self, *, table: str, count: int, forbidden_message: str
    ) -> None:
        if type(table) is not str or type(count) is not int or count < 0:
            raise ValueError("DML record is invalid")
        if table in _E2A_DENYLIST_TABLES:
            self.denylist_dml_counts[table] = (
                self.denylist_dml_counts.get(table, 0) + count
            )
            raise ValueError(f"{forbidden_message} table: {table}")
        if table not in _E2A_PRIMARY_TABLES:
            raise ValueError(f"DML table is outside the E2a allowlist: {table}")


@dataclass(frozen=True)
class E2aReconciliationResult:
    outcome: Outcome
    manifest_sha256: str
    primary_dml_by_table: Mapping[str, int]
    denylist_dml_counts: Mapping[str, int]
    comparator_parity: bool | None
    stale_deletion_counts: Mapping[str, int]
    cache_invalidation_counts: Mapping[str, int]
    failure_audit_outcome: str | None
    post_rollback_failure_audit_outcome: str | None
    reconciliation_required: bool = False

    def __post_init__(self) -> None:
        if self.outcome not in {
            "changed",
            "no_op",
            "rolled_back_failure",
            "acceptance_blocked",
            "outcome_unknown",
        }:
            raise ValueError("outcome is unsupported")
        if type(self.reconciliation_required) is not bool:
            raise ValueError("reconciliation_required must be a boolean")
        _digest(self.manifest_sha256, "manifest_sha256")
        if (
            self.comparator_parity is not None
            and type(self.comparator_parity) is not bool
        ):
            raise ValueError("comparator parity must be a boolean")
        for name in (
            "primary_dml_by_table",
            "denylist_dml_counts",
            "stale_deletion_counts",
            "cache_invalidation_counts",
        ):
            object.__setattr__(self, name, _counts(getattr(self, name)))


def _validate_parent_span_closure(
    parents: tuple[E2aParent, ...], spans: tuple[E2aSpan, ...]
) -> None:
    parent_keys = {(parent.document_id, parent.version_id) for parent in parents}
    if any((span.document_id, span.version_id) not in parent_keys for span in spans):
        raise ValueError("canonical span does not match an admitted parent")


__all__ = [
    "DmlRecorder",
    "E2A_GLOBAL_SCOPE_VERSION_ID",
    "E2aDesiredState",
    "E2aEvidenceObject",
    "E2aEvidenceReference",
    "E2aManualFact",
    "E2aOwnershipFact",
    "E2aParent",
    "E2aReconciliationResult",
    "E2aSpan",
    "canonical_json",
    "canonical_json_sha256",
    "deterministic_id",
]
