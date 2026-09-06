"""Private immutable values shared by E2a DML and inventory paths."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from types import MappingProxyType
from typing import Mapping


class _SqlNull:
    __slots__ = ()


SQL_NULL = _SqlNull()


class DmlTemplate(Enum):
    DELETE_TREE_NODE_SPAN_BY_PAIR = auto()
    DELETE_VECTOR_CHUNK_SPAN_BY_PAIR = auto()
    UPDATE_VECTOR_CHUNK_NODE = auto()
    DELETE_SUMMARIES_BY_NODE_IDS = auto()
    DELETE_NODE_EMBEDDINGS_BY_NODE_IDS = auto()
    DELETE_SEMANTIC_DISTRIBUTION_BY_NODE_IDS = auto()
    DELETE_TREE_NODE_SPANS_BY_NODE_IDS = auto()
    DELETE_TREE_NODES_BY_NODE_IDS = auto()
    DELETE_VECTOR_CHUNK_SPANS_BY_CHUNK_IDS = auto()
    DELETE_VECTOR_CHUNKS_BY_CHUNK_IDS = auto()
    DELETE_OWNERSHIP_BY_IDS = auto()
    DELETE_RELATION_BY_ID = auto()
    DELETE_ENTITY_BY_ID = auto()
    DELETE_TREE_NODE_SPANS_BY_SPAN_IDS = auto()
    DELETE_VECTOR_CHUNK_SPANS_BY_SPAN_IDS = auto()
    DELETE_CANONICAL_SPANS_BY_IDS = auto()
    DELETE_EVIDENCE_BY_IDS = auto()
    DELETE_EVIDENCE_LINKS_BY_IDS = auto()
    DELETE_EVIDENCE_LINKS_BY_EVIDENCE_IDS = auto()
    DELETE_EVIDENCE_TARGETS_BY_EVIDENCE_IDS = auto()
    DELETE_SYNC_STATE_BY_PATHS = auto()
    UPSERT_SYNC_STATE = auto()


class CacheMeasurementTemplate(Enum):
    SUMMARIES = auto()
    NODE_EMBEDDINGS = auto()
    SEMANTIC_DISTRIBUTION = auto()


@dataclass(frozen=True)
class DmlCommand:
    table: str
    operation: str
    statement: str


COMMANDS: Mapping[DmlTemplate, DmlCommand] = MappingProxyType(
    {
        DmlTemplate.DELETE_TREE_NODE_SPAN_BY_PAIR: DmlCommand(
            "tree_node_spans",
            "DELETE",
            "DELETE FROM tree_node_spans WHERE node_id = %s AND span_id = %s",
        ),
        DmlTemplate.DELETE_VECTOR_CHUNK_SPAN_BY_PAIR: DmlCommand(
            "vector_chunk_spans",
            "DELETE",
            "DELETE FROM vector_chunk_spans WHERE chunk_id = %s AND span_id = %s",
        ),
        DmlTemplate.UPDATE_VECTOR_CHUNK_NODE: DmlCommand(
            "vector_chunks",
            "UPDATE",
            "UPDATE vector_chunks SET node_id = %s WHERE chunk_id = %s "
            "AND node_id IS NOT DISTINCT FROM %s",
        ),
        DmlTemplate.DELETE_SUMMARIES_BY_NODE_IDS: DmlCommand(
            "summaries", "DELETE", "DELETE FROM summaries WHERE node_id = ANY(%s)"
        ),
        DmlTemplate.DELETE_NODE_EMBEDDINGS_BY_NODE_IDS: DmlCommand(
            "node_embeddings",
            "DELETE",
            "DELETE FROM node_embeddings WHERE node_id = ANY(%s)",
        ),
        DmlTemplate.DELETE_SEMANTIC_DISTRIBUTION_BY_NODE_IDS: DmlCommand(
            "semantic_distribution",
            "DELETE",
            "DELETE FROM semantic_distribution WHERE node_id = ANY(%s)",
        ),
        DmlTemplate.DELETE_TREE_NODE_SPANS_BY_NODE_IDS: DmlCommand(
            "tree_node_spans",
            "DELETE",
            "DELETE FROM tree_node_spans WHERE node_id = ANY(%s)",
        ),
        DmlTemplate.DELETE_TREE_NODES_BY_NODE_IDS: DmlCommand(
            "tree_nodes", "DELETE", "DELETE FROM tree_nodes WHERE node_id = ANY(%s)"
        ),
        DmlTemplate.DELETE_VECTOR_CHUNK_SPANS_BY_CHUNK_IDS: DmlCommand(
            "vector_chunk_spans",
            "DELETE",
            "DELETE FROM vector_chunk_spans WHERE chunk_id = ANY(%s)",
        ),
        DmlTemplate.DELETE_VECTOR_CHUNKS_BY_CHUNK_IDS: DmlCommand(
            "vector_chunks",
            "DELETE",
            "DELETE FROM vector_chunks WHERE chunk_id = ANY(%s)",
        ),
        DmlTemplate.DELETE_OWNERSHIP_BY_IDS: DmlCommand(
            "okf_manual_fact_ownership",
            "DELETE",
            "DELETE FROM okf_manual_fact_ownership WHERE ownership_id = ANY(%s)",
        ),
        DmlTemplate.DELETE_RELATION_BY_ID: DmlCommand(
            "relations", "DELETE", "DELETE FROM relations WHERE relation_id = %s"
        ),
        DmlTemplate.DELETE_ENTITY_BY_ID: DmlCommand(
            "entities", "DELETE", "DELETE FROM entities WHERE entity_id = %s"
        ),
        DmlTemplate.DELETE_TREE_NODE_SPANS_BY_SPAN_IDS: DmlCommand(
            "tree_node_spans",
            "DELETE",
            "DELETE FROM tree_node_spans WHERE span_id = ANY(%s)",
        ),
        DmlTemplate.DELETE_VECTOR_CHUNK_SPANS_BY_SPAN_IDS: DmlCommand(
            "vector_chunk_spans",
            "DELETE",
            "DELETE FROM vector_chunk_spans WHERE span_id = ANY(%s)",
        ),
        DmlTemplate.DELETE_CANONICAL_SPANS_BY_IDS: DmlCommand(
            "canonical_spans",
            "DELETE",
            "DELETE FROM canonical_spans WHERE span_id = ANY(%s)",
        ),
        DmlTemplate.DELETE_EVIDENCE_BY_IDS: DmlCommand(
            "evidence", "DELETE", "DELETE FROM evidence WHERE evidence_id = ANY(%s)"
        ),
        DmlTemplate.DELETE_EVIDENCE_LINKS_BY_IDS: DmlCommand(
            "evidence_links",
            "DELETE",
            "DELETE FROM evidence_links WHERE evidence_link_id = ANY(%s) "
            "AND source_kind = %s",
        ),
        DmlTemplate.DELETE_EVIDENCE_LINKS_BY_EVIDENCE_IDS: DmlCommand(
            "evidence_links",
            "DELETE",
            "DELETE FROM evidence_links WHERE evidence_id = ANY(%s) "
            "AND source_kind = %s",
        ),
        DmlTemplate.DELETE_EVIDENCE_TARGETS_BY_EVIDENCE_IDS: DmlCommand(
            "okf_manual_evidence_targets",
            "DELETE",
            "DELETE FROM okf_manual_evidence_targets WHERE evidence_id = ANY(%s)",
        ),
        DmlTemplate.DELETE_SYNC_STATE_BY_PATHS: DmlCommand(
            "okf_sync_state",
            "DELETE",
            "DELETE FROM okf_sync_state WHERE okf_file_path = ANY(%s) "
            "AND materialization_owner = %s",
        ),
        DmlTemplate.UPSERT_SYNC_STATE: DmlCommand(
            "okf_sync_state",
            "INSERT",
            "INSERT INTO okf_sync_state (okf_file_path, doc_id, version_id, "
            "source_checksum, canonical_hash, status, materialization_owner) VALUES "
            "(%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (okf_file_path) DO UPDATE SET "
            "doc_id = EXCLUDED.doc_id, version_id = EXCLUDED.version_id, "
            "source_checksum = EXCLUDED.source_checksum, "
            "canonical_hash = EXCLUDED.canonical_hash, status = EXCLUDED.status "
            "WHERE okf_sync_state.materialization_owner = %s AND ("
            "okf_sync_state.doc_id IS DISTINCT FROM EXCLUDED.doc_id OR "
            "okf_sync_state.version_id IS DISTINCT FROM EXCLUDED.version_id OR "
            "okf_sync_state.source_checksum IS DISTINCT FROM EXCLUDED.source_checksum OR "
            "okf_sync_state.canonical_hash IS DISTINCT FROM EXCLUDED.canonical_hash OR "
            "okf_sync_state.status IS DISTINCT FROM EXCLUDED.status) "
            "RETURNING okf_file_path",
        ),
    }
)


CACHE_MEASUREMENT_STATEMENTS: Mapping[CacheMeasurementTemplate, str] = MappingProxyType(
    {
        CacheMeasurementTemplate.SUMMARIES: (
            "SELECT cache.node_id FROM summaries AS cache "
            "JOIN tree_nodes AS node ON node.node_id = cache.node_id "
            "WHERE cache.node_id = ANY(%s)"
        ),
        CacheMeasurementTemplate.NODE_EMBEDDINGS: (
            "SELECT cache.node_id FROM node_embeddings AS cache "
            "JOIN tree_nodes AS node ON node.node_id = cache.node_id "
            "WHERE cache.node_id = ANY(%s)"
        ),
        CacheMeasurementTemplate.SEMANTIC_DISTRIBUTION: (
            "SELECT cache.node_id FROM semantic_distribution AS cache "
            "JOIN tree_nodes AS node ON node.node_id = cache.node_id "
            "WHERE cache.node_id = ANY(%s)"
        ),
    }
)
