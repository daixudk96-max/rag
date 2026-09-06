from __future__ import annotations

from contextlib import nullcontext
import re
import uuid
from typing import Any, Protocol

from llamaindex_runtime.registry.contracts import VersionInfo

class ExtractionRegistryProtocol(Protocol):
    def query_tree_nodes_by_version(self, version_id: uuid.UUID) -> list[dict[str, Any]]: ...
    def query_tree_node_spans_by_version(self, version_id: uuid.UUID) -> list[dict[str, Any]]: ...
    def write_entities(self, *, entities: list[dict[str, Any]]) -> None: ...
    def write_node_entity_links(self, *, version_id: uuid.UUID, links: list[dict[str, Any]]) -> None: ...
    def write_evidence_links(self, *, version_id: uuid.UUID, evidence_links: list[dict[str, Any]]) -> None: ...
    def query_node_entity_links_by_version(self, version_id: uuid.UUID) -> list[dict[str, Any]]: ...
    def query_evidence_links_by_version(self, version_id: uuid.UUID) -> list[dict[str, Any]]: ...


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized.replace("-", "")


def _derive_entity_name(node: dict[str, Any]) -> str | None:
    title = (node.get("title") or "").strip()
    if title:
        return title

    heading_path = (node.get("heading_path") or "").strip()
    if heading_path:
        parts = [part.strip() for part in heading_path.split(">") if part.strip()]
        if parts:
            return parts[-1]

    summary_text = (node.get("summary_text") or "").strip()
    if summary_text:
        return " ".join(summary_text.split()[:4])
    return None


def build_tree_entity_extraction_callback(
    registry: ExtractionRegistryProtocol,
    *,
    entity_type: str = "concept",
    source_kind: str = "tree_summary",
    confidence_score: float = 0.7,
):
    def callback(*, version_info: VersionInfo) -> None:
        existing_node_links = registry.query_node_entity_links_by_version(version_info.version_id)
        existing_evidence_links = registry.query_evidence_links_by_version(version_info.version_id)
        if existing_node_links and existing_evidence_links:
            return

        nodes = registry.query_tree_nodes_by_version(version_info.version_id)
        node_span_rows = registry.query_tree_node_spans_by_version(version_info.version_id)
        first_span_by_node: dict[uuid.UUID, uuid.UUID] = {}
        for row in node_span_rows:
            first_span_by_node.setdefault(row["node_id"], row["span_id"])

        entities_by_key: dict[str, dict[str, Any]] = {}
        node_links: list[dict[str, Any]] = []
        evidence_links: list[dict[str, Any]] = []

        for node in nodes:
            entity_name = _derive_entity_name(node)
            span_id = first_span_by_node.get(node["node_id"])
            if not entity_name or span_id is None:
                continue

            entity_key = f"{entity_type}:{_slugify(entity_name)}"
            entity = entities_by_key.get(entity_key)
            if entity is None:
                entity_id = uuid.uuid5(uuid.NAMESPACE_URL, entity_key)
                entity = {
                    "entity_id": entity_id,
                    "entity_key": entity_key,
                    "entity_type": entity_type,
                    "canonical_name": entity_name,
                    "description": node.get("summary_text"),
                }
                entities_by_key[entity_key] = entity
            entity_id = entity["entity_id"]

            node_links.append(
                {
                    "node_id": node["node_id"],
                    "entity_id": entity_id,
                    "ordinal_no": 0,
                    "confidence_score": confidence_score,
                    "mention_text": entity_name,
                }
            )
            evidence_links.append(
                {
                    "entity_id": entity_id,
                    "relation_id": None,
                    "span_id": span_id,
                    "source_kind": source_kind,
                    "confidence_score": confidence_score,
                }
            )

        transaction_factory = getattr(registry, "transaction", None)
        transaction_context = transaction_factory() if callable(transaction_factory) else nullcontext()
        with transaction_context:
            if entities_by_key:
                registry.write_entities(entities=list(entities_by_key.values()))
            if node_links:
                registry.write_node_entity_links(version_id=version_info.version_id, links=node_links)
            if evidence_links:
                registry.write_evidence_links(version_id=version_info.version_id, evidence_links=evidence_links)

    return callback


def build_finalize_callback(
    registry: ExtractionRegistryProtocol,
):
    def callback(*, version_info: VersionInfo) -> None:
        node_links = registry.query_node_entity_links_by_version(version_info.version_id)
        evidence_links = registry.query_evidence_links_by_version(version_info.version_id)
        if not node_links and not evidence_links:
            raise ValueError("No extraction outputs available for finalize step")
    return callback
