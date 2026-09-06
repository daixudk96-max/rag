"""P4 KAG-style schema extraction from existing entity/relation records.

This module provides pure functions for inferring schema constraints
from observed entity and relation records, without touching database
write paths or introducing a full DSL framework.

Key features:
- Statistical inference: required fields from 100% field presence
- Relation constraints: allowed source/target types from observed relations
- Pure, deterministic functions - no database dependencies
"""
from __future__ import annotations

from collections import Counter
from typing import Any
from uuid import UUID

from llamaindex_runtime.registry.contracts import EntityTypeSchema, RelationTypeSchema


def infer_entity_type_schema(
    entities: list[dict[str, Any]],
    entity_type: str,
) -> EntityTypeSchema:
    """Infer entity type schema from observed entity records.

    Args:
        entities: List of entity dicts to analyze
        entity_type: Target entity type name to filter for

    Returns:
        EntityTypeSchema with required_fields marked for 100%-present fields

    Raises:
        ValueError: If entities list is empty
        ValueError: If entity dicts lack entity_type field
        ValueError: If entity_type doesn't match target entity_type

    Example:
        >>> entities = [
        ...     {"entity_id": ..., "entity_key": "concept:a", "entity_type": "concept", "canonical_name": "A"},
        ...     {"entity_id": ..., "entity_key": "concept:b", "entity_type": "concept", "canonical_name": "B"},
        ... ]
        >>> schema = infer_entity_type_schema(entities, "concept")
        >>> assert "canonical_name" in schema.required_fields
    """
    if not entities:
        raise ValueError("Cannot infer schema from empty entity list")

    # Validate that all entities have entity_type field
    for entity in entities:
        if "entity_type" not in entity:
            raise ValueError(f"Entity dict missing required 'entity_type' field: {entity}")

    # Filter entities to only those matching target entity_type
    matching_entities = [e for e in entities if e.get("entity_type") == entity_type]

    if not matching_entities:
        raise ValueError(
            f"No entities found with entity_type '{entity_type}'. "
            f"Available types: {set(e.get('entity_type', 'MISSING') for e in entities)}"
        )

    # Count field presence across all matching entities
    field_counts: Counter[str] = Counter()
    for entity in matching_entities:
        for field_name in entity.keys():
            field_counts[field_name] += 1

    total_entities = len(matching_entities)

    # Mark fields as required if present in 100% of entities
    required_fields = [
        field_name
        for field_name, count in field_counts.items()
        if count == total_entities
    ]

    return EntityTypeSchema(
        entity_type_name=entity_type,
        description=None,  # Not inferred from data
        required_fields=required_fields,
    )


def infer_relation_type_schema(
    relations: list[dict[str, Any]],
    entities: list[dict[str, Any]],
    relation_type: str,
) -> RelationTypeSchema:
    """Infer relation type schema from observed relation and entity records.

    Args:
        relations: List of relation dicts to analyze
        entities: List of entity dicts for type lookup
        relation_type: Target relation type name to filter for

    Returns:
        RelationTypeSchema with allowed_source_types and allowed_target_types

    Raises:
        ValueError: If relations list is empty
        ValueError: If relation dicts lack relation_type field
        ValueError: If relation_type doesn't match target relation_type
        ValueError: If referenced entity IDs not found in entities list

    Example:
        >>> e1, e2 = uuid.uuid4(), uuid.uuid4()
        >>> entities = [
        ...     {"entity_id": e1, "entity_key": "concept:a", "entity_type": "concept"},
        ...     {"entity_id": e2, "entity_key": "metric:b", "entity_type": "metric"},
        ... ]
        >>> relations = [
        ...     {"relation_id": ..., "relation_type": "affects", "source_entity_id": e1, "target_entity_id": e2},
        ... ]
        >>> schema = infer_relation_type_schema(relations, entities, "affects")
        >>> assert schema.allowed_source_types == ["concept"]
        >>> assert schema.allowed_target_types == ["metric"]
    """
    if not relations:
        raise ValueError("Cannot infer schema from empty relation list")

    # Validate that all relations have relation_type field
    for relation in relations:
        if "relation_type" not in relation:
            raise ValueError(f"Relation dict missing required 'relation_type' field: {relation}")

    # Filter relations to only those matching target relation_type
    matching_relations = [r for r in relations if r.get("relation_type") == relation_type]

    if not matching_relations:
        raise ValueError(
            f"No relations found with relation_type '{relation_type}'. "
            f"Available types: {set(r.get('relation_type', 'MISSING') for r in relations)}"
        )

    # Build entity ID -> entity_type lookup
    entity_id_to_type: dict[UUID, str] = {}
    for entity in entities:
        entity_id = entity.get("entity_id")
        entity_type = entity.get("entity_type")
        if entity_id is not None and entity_type is not None:
            entity_id_to_type[UUID(entity_id) if not isinstance(entity_id, UUID) else entity_id] = entity_type

    # Collect observed source and target entity types
    source_types: set[str] = set()
    target_types: set[str] = set()

    for relation in matching_relations:
        source_id = relation.get("source_entity_id")
        target_id = relation.get("target_entity_id")

        if source_id is not None:
            source_uuid = UUID(source_id) if not isinstance(source_id, UUID) else source_id
            if source_uuid not in entity_id_to_type:
                raise ValueError(
                    f"Relation references missing source entity with ID {source_uuid}. "
                    f"Entity not found in provided entities list."
                )
            source_types.add(entity_id_to_type[source_uuid])

        if target_id is not None:
            target_uuid = UUID(target_id) if not isinstance(target_id, UUID) else target_id
            if target_uuid not in entity_id_to_type:
                raise ValueError(
                    f"Relation references missing target entity with ID {target_uuid}. "
                    f"Entity not found in provided entities list."
                )
            target_types.add(entity_id_to_type[target_uuid])

    return RelationTypeSchema(
        relation_type_name=relation_type,
        allowed_source_types=sorted(source_types) if source_types else None,
        allowed_target_types=sorted(target_types) if target_types else None,
    )