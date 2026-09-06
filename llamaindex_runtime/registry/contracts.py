from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence
from uuid import UUID

from llamaindex_runtime.interfaces import CanonicalSpan


class DocumentStatus(str, Enum):
    """LightRAG-style document processing status tracking.

    This enum defines the stages of document processing in the incremental pipeline.
    Each stage represents a milestone in the extraction and indexing process.
    """

    REGISTERED = "registered"
    PARSED = "parsed"
    CHUNKS_CREATED = "chunks_created"
    EMBEDDED = "embedded"
    TREE_BUILT = "tree_built"
    ENTITIES_EXTRACTED = "entities_extracted"
    COMPLETE = "complete"
    FAILED = "failed"

    @classmethod
    def valid_transitions(cls) -> dict[str, list[str]]:
        """Define valid status transitions to enforce ordering."""
        return {
            cls.REGISTERED: [cls.PARSED, cls.FAILED],
            cls.PARSED: [cls.CHUNKS_CREATED, cls.FAILED],
            cls.CHUNKS_CREATED: [cls.EMBEDDED, cls.FAILED],
            cls.EMBEDDED: [cls.TREE_BUILT, cls.FAILED],
            cls.TREE_BUILT: [cls.ENTITIES_EXTRACTED, cls.FAILED],
            cls.ENTITIES_EXTRACTED: [cls.COMPLETE, cls.FAILED],
            cls.COMPLETE: [cls.FAILED],
            cls.FAILED: [],
        }

    def can_transition_to(self, target: str | DocumentStatus) -> bool:
        """Check if transition from current status to target is valid."""
        target_str = target if isinstance(target, str) else target.value
        valid_targets = self.valid_transitions().get(self.value, [])
        return target_str in [
            t.value if isinstance(t, DocumentStatus) else t for t in valid_targets
        ]


@dataclass(frozen=True)
class RegisteredDocument:
    doc_id: UUID
    version_id: UUID
    source_uri: str
    version_no: int = 1
    is_active: bool = True


@dataclass(frozen=True)
class VersionInfo:
    version_id: UUID
    doc_id: UUID
    version_no: int
    content_hash: str
    is_active: bool
    status: str
    processing_status: str = (
        "registered"  # LightRAG-style incremental processing status
    )
    registered_at: Any | None = None  # Timestamp when registered
    parsed_at: Any | None = None  # Timestamp when parsed
    chunks_created_at: Any | None = None  # Timestamp when chunks created
    embedded_at: Any | None = None  # Timestamp when embedded
    tree_built_at: Any | None = None  # Timestamp when tree built
    entities_extracted_at: Any | None = None  # Timestamp when entities extracted
    completed_at: Any | None = None  # Timestamp when complete
    processing_status_updated_at: Any | None = None  # Last status update timestamp


@dataclass(frozen=True)
class TreeNode:
    node_id: UUID
    version_id: UUID
    parent_node_id: UUID | None
    node_type: str
    level_no: int
    title: str
    heading_path: str
    page_start: int | None
    page_end: int | None
    summary_text: str | None = None


@dataclass(frozen=True)
class TreeNodeSpan:
    node_id: UUID
    span_id: UUID
    ordinal_no: int


@dataclass(frozen=True)
class Entity:
    entity_id: UUID
    entity_key: str
    entity_type: str | None
    canonical_name: str | None
    description: str | None = None  # GraphRAG-style entity description
    community_id: UUID | None = None  # GraphRAG-style community detection


@dataclass(frozen=True)
class Relation:
    relation_id: UUID
    relation_key: str
    relation_type: str
    source_entity_id: UUID
    target_entity_id: UUID
    description: str | None = None  # GraphRAG-style relationship description
    negation: bool = False
    condition: str | None = None
    direction: str | None = None
    confidence: float | None = None
    qualifiers: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class EvidenceLink:
    evidence_link_id: UUID
    version_id: UUID
    entity_id: UUID | None
    relation_id: UUID | None
    span_id: UUID
    source_kind: str
    confidence_score: float | None
    evidence_id: UUID | None = None  # P4: Optional grouping layer

    def __post_init__(self) -> None:
        if self.entity_id is None and self.relation_id is None:
            raise ValueError(
                "At least one of entity_id or relation_id must be set on EvidenceLink"
            )


@dataclass(frozen=True)
class Evidence:
    """P4 evidence object: minimal grouping layer for evidence_links.

    EvidenceNet follow-up: dedup_key enables idempotent deduplication at version scope.
    """

    evidence_id: UUID
    version_id: UUID
    dedup_key: str | None = None  # Idempotent deduplication key within version scope


@dataclass(frozen=True)
class ChunkEntityLink:
    chunk_id: UUID
    entity_id: UUID
    ordinal_no: int
    confidence_score: float | None = None
    mention_text: str | None = None


@dataclass(frozen=True)
class NodeEntityLink:
    node_id: UUID
    entity_id: UUID
    ordinal_no: int
    confidence_score: float | None = None
    mention_text: str | None = None


@dataclass(frozen=True)
class EntityTypeSchema:
    """KAG-style entity type schema definition.

    Defines constraints and requirements for a specific entity type.
    """

    entity_type_name: str
    description: str | None = None
    required_fields: list[str] | None = None


@dataclass(frozen=True)
class RelationTypeSchema:
    """KAG-style relation type schema definition.

    Defines constraints on relation types, including allowed source/target entity types.
    """

    relation_type_name: str
    allowed_source_types: list[str] | None = None
    allowed_target_types: list[str] | None = None


class RegistryWriter(Protocol):
    def register_document(
        self,
        *,
        source_path: Path,
        source_uri: str,
        title: str | None = None,
    ) -> RegisteredDocument: ...

    def write_spans(
        self, *, version_id: UUID, spans: Sequence[CanonicalSpan]
    ) -> None: ...

    def query_spans_by_version(self, version_id: UUID) -> list[dict[str, Any]]: ...

    def get_version(self, version_id: UUID) -> VersionInfo: ...

    def list_versions(self, doc_id: UUID) -> list[VersionInfo]: ...

    def get_active_version(self, doc_id: UUID) -> VersionInfo | None: ...

    def write_tree(
        self,
        *,
        version_id: UUID,
        nodes: Sequence[dict[str, Any]],
        node_spans: Sequence[dict[str, Any]],
    ) -> None: ...

    def query_tree_nodes_by_version(self, version_id: UUID) -> list[dict[str, Any]]: ...

    def query_tree_node_spans_by_version(
        self, version_id: UUID
    ) -> list[dict[str, Any]]: ...

    def query_doc_id_by_version(self, version_id: UUID) -> UUID: ...

    def write_vector_chunks(
        self,
        *,
        version_id: UUID,
        chunks: Sequence[dict[str, Any]],
    ) -> None: ...

    def query_vector_chunks_by_version(
        self, version_id: UUID
    ) -> list[dict[str, Any]]: ...

    def query_vector_chunk_spans_by_version(
        self, version_id: UUID
    ) -> list[dict[str, Any]]: ...

    # -- KG (Phase 5) methods --

    def write_entities(self, *, entities: Sequence[dict[str, Any]]) -> None: ...

    def query_entities(self) -> list[dict[str, Any]]: ...

    def write_relations(self, *, relations: Sequence[dict[str, Any]]) -> None: ...

    def query_relations(self) -> list[dict[str, Any]]: ...

    def write_evidence_links(
        self,
        *,
        version_id: UUID,
        evidence_links: Sequence[dict[str, Any]],
    ) -> None: ...

    def query_evidence_links_by_version(
        self, version_id: UUID
    ) -> list[dict[str, Any]]: ...

    # -- Evidence object (P4) methods --

    def write_evidence(self, *, evidence: Sequence[dict[str, Any]]) -> None: ...

    def query_evidence_by_version(self, version_id: UUID) -> list[dict[str, Any]]: ...

    def write_chunk_entity_links(
        self,
        *,
        version_id: UUID,
        links: Sequence[dict[str, Any]],
    ) -> None: ...

    def query_chunk_entity_links_by_version(
        self, version_id: UUID
    ) -> list[dict[str, Any]]: ...

    def write_node_entity_links(
        self,
        *,
        version_id: UUID,
        links: Sequence[dict[str, Any]],
    ) -> None: ...

    def query_node_entity_links_by_version(
        self, version_id: UUID
    ) -> list[dict[str, Any]]: ...

    def query_spans_by_keyword(
        self,
        *,
        query: str,
        version_id: UUID | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]: ...

    # -- Summary index methods (P5 multi-view indexing) --

    def write_summaries(
        self,
        *,
        version_id: UUID,
        summaries: Sequence[dict[str, Any]],
    ) -> None: ...

    def query_summaries_by_version(self, version_id: UUID) -> list[dict[str, Any]]: ...

    def query_summaries_by_keyword(
        self,
        *,
        query: str,
        version_id: UUID | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]: ...

    # -- Document processing status (P4 LightRAG-style incremental) --

    def update_processing_status(
        self,
        *,
        version_id: UUID,
        processing_status: str,
    ) -> None: ...

    def query_by_processing_status(
        self,
        processing_status: str,
    ) -> list[VersionInfo]: ...

    # -- KAG-style schema methods (P4) --

    def write_entity_type_schema(self, *, schema: dict[str, Any]) -> None: ...

    def query_entity_type_schemas(self) -> list[dict[str, Any]]: ...

    def write_relation_type_schema(self, *, schema: dict[str, Any]) -> None: ...

    def query_relation_type_schemas(self) -> list[dict[str, Any]]: ...

    def healthcheck(self) -> bool: ...
