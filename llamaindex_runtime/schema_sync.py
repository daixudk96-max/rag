"""Thin integration helper for KAG-style schema inference and persistence.

This module connects existing registry reads with pure schema extraction functions,
without touching postgres_adapter internals, relation schemas, or DSL/solver work.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import logging
from typing import Any, Protocol

from llamaindex_runtime.schema_extraction import (
    infer_entity_type_schema,
    infer_relation_type_schema,
)

logger = logging.getLogger(__name__)

PERSISTENCE_EXCEPTIONS = (ConnectionError, OSError, RuntimeError, ValueError)


class RegistryReader(Protocol):
    """Minimal registry read interface needed for schema sync."""

    def query_entities(self) -> list[dict[str, Any]]: ...

    def query_relations(self) -> list[dict[str, Any]]: ...


class RegistryWriter(Protocol):
    """Minimal registry write interface needed for schema sync."""

    def write_entity_type_schema(self, *, schema: dict[str, Any]) -> None: ...

    def write_relation_type_schema(self, *, schema: dict[str, Any]) -> None: ...


class RegistryReadWrite(RegistryReader, RegistryWriter, Protocol):
    """Combined read/write interface for registry."""

    pass


@dataclass(frozen=True)
class SchemaSyncResult:
    """Summary of schema synchronization operation."""

    schemas_written: int
    total_entities: int
    entity_types: list[str]
    failed_types: list[str]


@dataclass(frozen=True)
class RelationSchemaSyncResult:
    """Summary of relation schema synchronization operation."""

    schemas_written: int
    total_relations: int
    relation_types: list[str]
    failed_types: list[str]


def infer_and_persist_entity_schemas(
    registry: RegistryReadWrite,
) -> SchemaSyncResult:
    """Infer entity type schemas from observed entities and persist to registry.

    This function:
    1. Queries all entities from registry
    2. Groups entities by entity_type
    3. Infers schema for each group using infer_entity_type_schema
    4. Persists each schema via registry.write_entity_type_schema

    Args:
        registry: Registry with both read and write capabilities

    Returns:
        SchemaSyncResult with summary of the operation

    Note:
        Entities without entity_type field are skipped (not an error).
        This allows graceful handling of partially-formed data.
    """
    # 1. Query all entities
    all_entities = registry.query_entities()

    if not all_entities:
        return SchemaSyncResult(
            schemas_written=0,
            total_entities=0,
            entity_types=[],
            failed_types=[],
        )

    # 2. Group entities by entity_type, skipping entities without entity_type
    entities_by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for entity in all_entities:
        entity_type = entity.get("entity_type")
        if entity_type is not None:
            entities_by_type[entity_type].append(entity)

    # 3. Infer schema for each entity type group
    # 4. Persist each schema
    entity_types_written: list[str] = []
    failed_types: list[str] = []

    for entity_type, entities in entities_by_type.items():
        try:
            schema_obj = infer_entity_type_schema(entities, entity_type)
        except ValueError:
            logger.exception("schema inference failed for entity_type %s", entity_type)
            failed_types.append(entity_type)
            continue

        # Convert EntityTypeSchema dataclass to dict for registry API
        schema_dict: dict[str, Any] = {
            "entity_type_name": schema_obj.entity_type_name,
        }

        if schema_obj.description is not None:
            schema_dict["description"] = schema_obj.description

        if schema_obj.required_fields is not None:
            schema_dict["required_fields"] = schema_obj.required_fields

        try:
            registry.write_entity_type_schema(schema=schema_dict)
            entity_types_written.append(entity_type)
        except PERSISTENCE_EXCEPTIONS:
            logger.exception(
                "schema persistence failed for entity_type %s", entity_type
            )
            failed_types.append(entity_type)
            continue

    return SchemaSyncResult(
        schemas_written=len(entity_types_written),
        total_entities=len(all_entities),
        entity_types=entity_types_written,
        failed_types=failed_types,
    )


def infer_and_persist_relation_schemas(
    registry: RegistryReadWrite,
) -> RelationSchemaSyncResult:
    """Infer relation type schemas from observed relations and persist to registry.

    This function:
    1. Queries all relations and entities from registry
    2. Groups relations by relation_type
    3. Infers schema for each group using infer_relation_type_schema
    4. Persists each schema via registry.write_relation_type_schema

    Args:
        registry: Registry with both read and write capabilities

    Returns:
        RelationSchemaSyncResult with summary of the operation

    Note:
        Relations without relation_type field are skipped (not an error).
        This allows graceful handling of partially-formed data.
    """
    # 1. Query all relations
    all_relations = registry.query_relations()

    if not all_relations:
        return RelationSchemaSyncResult(
            schemas_written=0,
            total_relations=0,
            relation_types=[],
            failed_types=[],
        )

    # Query entities only when relation work actually exists
    all_entities = registry.query_entities()

    # 2. Group relations by relation_type, skipping relations without relation_type
    relations_by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for relation in all_relations:
        relation_type = relation.get("relation_type")
        if relation_type is not None:
            relations_by_type[relation_type].append(relation)

    # 3. Infer schema for each relation type group
    # 4. Persist each schema
    relation_types_written: list[str] = []
    failed_types: list[str] = []

    for relation_type, relations in relations_by_type.items():
        try:
            schema_obj = infer_relation_type_schema(
                relations, all_entities, relation_type
            )
        except ValueError:
            logger.exception(
                "schema inference failed for relation_type %s", relation_type
            )
            failed_types.append(relation_type)
            continue

        # Convert RelationTypeSchema dataclass to dict for registry API
        schema_dict: dict[str, Any] = {
            "relation_type_name": schema_obj.relation_type_name,
        }

        if schema_obj.allowed_source_types is not None:
            schema_dict["allowed_source_types"] = schema_obj.allowed_source_types

        if schema_obj.allowed_target_types is not None:
            schema_dict["allowed_target_types"] = schema_obj.allowed_target_types

        try:
            registry.write_relation_type_schema(schema=schema_dict)
            relation_types_written.append(relation_type)
        except PERSISTENCE_EXCEPTIONS:
            logger.exception(
                "schema persistence failed for relation_type %s", relation_type
            )
            failed_types.append(relation_type)
            continue

    return RelationSchemaSyncResult(
        schemas_written=len(relation_types_written),
        total_relations=len(all_relations),
        relation_types=relation_types_written,
        failed_types=failed_types,
    )