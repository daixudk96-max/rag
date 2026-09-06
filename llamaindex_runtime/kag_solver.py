from __future__ import annotations

from typing import Any
from uuid import UUID


def solve_relation_candidates(
    relation_candidates: list[dict[str, Any]],
    entities: list[dict[str, Any]],
    relation_type_schemas: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    entity_types: dict[UUID, str] = {}
    for entity in entities:
        entity_id = entity.get("entity_id")
        entity_type = entity.get("entity_type")
        if entity_id is None or entity_type is None:
            continue
        entity_uuid = entity_id if isinstance(entity_id, UUID) else UUID(str(entity_id))
        entity_types[entity_uuid] = entity_type

    schema_by_type = {
        schema["relation_type_name"]: schema
        for schema in relation_type_schemas
        if schema.get("relation_type_name") is not None
    }

    solved: list[dict[str, Any]] = []
    for candidate in relation_candidates:
        source_id = candidate.get("source_entity_id")
        target_id = candidate.get("target_entity_id")
        if source_id is None or target_id is None:
            continue

        source_uuid = source_id if isinstance(source_id, UUID) else UUID(str(source_id))
        target_uuid = target_id if isinstance(target_id, UUID) else UUID(str(target_id))
        source_type = entity_types.get(source_uuid)
        target_type = entity_types.get(target_uuid)
        if source_type is None or target_type is None:
            continue

        relation_type = candidate.get("relation_type")
        schema = schema_by_type.get(relation_type)
        if schema is None:
            solved.append(candidate)
            continue

        allowed_source_types = schema.get("allowed_source_types")
        if allowed_source_types and source_type not in allowed_source_types:
            continue

        allowed_target_types = schema.get("allowed_target_types")
        if allowed_target_types and target_type not in allowed_target_types:
            continue

        solved.append(candidate)

    return solved
