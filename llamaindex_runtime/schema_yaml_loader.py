"""KAG YAML load-and-persist helper layer.

Connects existing schema_contract YAML helpers to registry persistence.
No YAML parsing duplication, no registry internals modification.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TypeVar

from llamaindex_runtime.registry.contracts import EntityTypeSchema, RelationTypeSchema, RegistryWriter
from llamaindex_runtime.schema_contract import (
    load_schema_yaml,
    load_schemas_yaml,
    schema_to_dict,
)

SchemaT = TypeVar("SchemaT", EntityTypeSchema, RelationTypeSchema)
PERSIST_EXCEPTIONS = (ConnectionError, OSError, RuntimeError, ValueError)


@dataclass(frozen=True)
class SchemaLoadFailure:
    """Details of a single schema load/persist failure."""

    schema_name: str
    schema_type: str
    error_message: str


@dataclass(frozen=True)
class SchemaLoadSummary:
    """Summary result of YAML schema load-and-persist operation."""

    schemas_written: int
    schemas_failed: int
    total_schemas: int
    failures: list[SchemaLoadFailure]


def _persist_single_schema(
    schema: SchemaT,
    *,
    schema_type: str,
    writer: Callable[[dict[str, Any]], None],
) -> SchemaLoadSummary:
    schema_dict = schema_to_dict(schema)
    schema_name = _schema_name(schema)

    try:
        writer(schema_dict)
        return SchemaLoadSummary(
            schemas_written=1,
            schemas_failed=0,
            total_schemas=1,
            failures=[],
        )
    except PERSIST_EXCEPTIONS as exc:
        return SchemaLoadSummary(
            schemas_written=0,
            schemas_failed=1,
            total_schemas=1,
            failures=[
                SchemaLoadFailure(
                    schema_name=schema_name,
                    schema_type=schema_type,
                    error_message=str(exc),
                )
            ],
        )


def _persist_many_schemas(
    schemas: list[SchemaT],
    *,
    schema_type: str,
    writer: Callable[[dict[str, Any]], None],
) -> SchemaLoadSummary:
    schemas_written = 0
    failures: list[SchemaLoadFailure] = []

    for schema in schemas:
        schema_dict = schema_to_dict(schema)
        schema_name = _schema_name(schema)
        try:
            writer(schema_dict)
            schemas_written += 1
        except PERSIST_EXCEPTIONS as exc:
            failures.append(
                SchemaLoadFailure(
                    schema_name=schema_name,
                    schema_type=schema_type,
                    error_message=str(exc),
                )
            )

    return SchemaLoadSummary(
        schemas_written=schemas_written,
        schemas_failed=len(failures),
        total_schemas=len(schemas),
        failures=failures,
    )


def _schema_name(schema: SchemaT) -> str:
    if isinstance(schema, EntityTypeSchema):
        return schema.entity_type_name
    return schema.relation_type_name


def load_entity_schema_yaml_and_persist(
    yaml_path: Path | str,
    registry: RegistryWriter,
) -> SchemaLoadSummary:
    """Load single entity schema from YAML and persist to registry."""
    schema = load_schema_yaml(Path(yaml_path), EntityTypeSchema)
    return _persist_single_schema(
        schema,
        schema_type="entity",
        writer=lambda schema_dict: registry.write_entity_type_schema(schema=schema_dict),
    )


def load_entity_schemas_yaml_and_persist(
    yaml_path: Path | str,
    registry: RegistryWriter,
) -> SchemaLoadSummary:
    """Load multiple entity schemas from YAML and persist to registry."""
    schemas = load_schemas_yaml(Path(yaml_path), EntityTypeSchema)
    return _persist_many_schemas(
        schemas,
        schema_type="entity",
        writer=lambda schema_dict: registry.write_entity_type_schema(schema=schema_dict),
    )


def load_relation_schema_yaml_and_persist(
    yaml_path: Path | str,
    registry: RegistryWriter,
) -> SchemaLoadSummary:
    """Load single relation schema from YAML and persist to registry."""
    schema = load_schema_yaml(Path(yaml_path), RelationTypeSchema)
    return _persist_single_schema(
        schema,
        schema_type="relation",
        writer=lambda schema_dict: registry.write_relation_type_schema(schema=schema_dict),
    )


def load_relation_schemas_yaml_and_persist(
    yaml_path: Path | str,
    registry: RegistryWriter,
) -> SchemaLoadSummary:
    """Load multiple relation schemas from YAML and persist to registry."""
    schemas = load_schemas_yaml(Path(yaml_path), RelationTypeSchema)
    return _persist_many_schemas(
        schemas,
        schema_type="relation",
        writer=lambda schema_dict: registry.write_relation_type_schema(schema=schema_dict),
    )
