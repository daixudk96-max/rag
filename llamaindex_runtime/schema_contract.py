"""Schema contract helper layer for KAG DSL.

Pure functions for dict/YAML round-trip and structural validation
of EntityTypeSchema and RelationTypeSchema dataclasses.

No registry writes, no adapters, no DSL solver.
"""

from __future__ import annotations

from dataclasses import asdict, fields
from pathlib import Path
from typing import Any, get_origin, get_args, get_type_hints

import yaml

from llamaindex_runtime.registry.contracts import EntityTypeSchema, RelationTypeSchema


def _validate_sequence_items(field_name: str, value: Any, item_type: Any) -> None:
    if not isinstance(value, list):
        raise ValueError(
            f"Field '{field_name}' expected type list, got {type(value).__name__}"
        )
    for item in value:
        _validate_field_type(field_name, item, item_type)


def _validate_field_type(field_name: str, value: Any, expected_type: Any) -> None:
    """Validate that a value matches the expected type annotation.

    Args:
        field_name: Name of the field being validated
        value: The value to check
        expected_type: The expected type annotation (resolved from get_type_hints)

    Raises:
        ValueError: If type mismatch detected
    """
    # Handle None values - they're valid for optional fields
    if value is None:
        return

    # Handle Union types (e.g., str | None, list[str] | None)
    origin = get_origin(expected_type)
    if origin is not None:
        from typing import Union

        # Check if this is a Union type (Python 3.10+ uses types.UnionType)
        try:
            import types
            is_union = origin is Union or origin is types.UnionType
        except AttributeError:
            is_union = origin is Union

        if is_union:
            args = get_args(expected_type)
            # Check against all types in the union (except None which we already handled)
            valid_types = [t for t in args if t is not type(None)]

            for valid_type in valid_types:
                valid_origin = get_origin(valid_type)
                if valid_origin is list:
                    item_types = get_args(valid_type)
                    item_type = item_types[0] if item_types else Any
                    try:
                        _validate_sequence_items(field_name, value, item_type)
                        return
                    except ValueError:
                        pass
                elif valid_origin is not None:
                    if isinstance(value, valid_origin):
                        return
                elif isinstance(value, valid_type):
                    return

            # If none matched, raise error
            type_names = []
            for t in valid_types:
                t_origin = get_origin(t)
                if t_origin is not None:
                    type_names.append(str(t))
                else:
                    type_names.append(t.__name__ if hasattr(t, '__name__') else str(t))
            raise ValueError(
                f"Field '{field_name}' expected one of types ({', '.join(type_names)}), got {type(value).__name__}"
            )
        else:
            # It's a generic type but not a Union (e.g., list[str])
            if origin is list:
                item_types = get_args(expected_type)
                item_type = item_types[0] if item_types else Any
                _validate_sequence_items(field_name, value, item_type)
                return
            if isinstance(value, origin):
                return
            raise ValueError(
                f"Field '{field_name}' expected type {expected_type}, got {type(value).__name__}"
            )

    # Handle simple types (non-generic, non-union)
    if not isinstance(value, expected_type):
        raise ValueError(
            f"Field '{field_name}' expected type {expected_type.__name__}, got {type(value).__name__}"
        )


def schema_to_dict(schema: EntityTypeSchema | RelationTypeSchema) -> dict[str, Any]:
    """Convert a schema dataclass instance to a dictionary.

    Args:
        schema: EntityTypeSchema or RelationTypeSchema instance

    Returns:
        Dictionary representation with all fields (None preserved as null)

    Example:
        >>> schema = EntityTypeSchema(entity_type_name="Person")
        >>> schema_to_dict(schema)
        {'entity_type_name': 'Person', 'description': None, 'required_fields': None}
    """
    return asdict(schema)


def schema_from_dict(
    data: dict[str, Any],
    schema_type: type[EntityTypeSchema] | type[RelationTypeSchema],
) -> EntityTypeSchema | RelationTypeSchema:
    """Load a schema dataclass from a dictionary with validation.

    Args:
        data: Dictionary with schema fields
        schema_type: EntityTypeSchema or RelationTypeSchema class

    Returns:
        Schema dataclass instance

    Raises:
        ValueError: Missing required fields, unknown fields, or invalid types

    Example:
        >>> data = {"entity_type_name": "Person"}
        >>> schema_from_dict(data, EntityTypeSchema)
        EntityTypeSchema(entity_type_name='Person', description=None, required_fields=None)
    """
    # Get expected fields and resolved type hints from the dataclass
    expected_fields = {f.name for f in fields(schema_type)}
    required_fields_names = {f.name for f in fields(schema_type) if f.default == f.default_factory}

    # Resolve string annotations to actual types
    type_hints = get_type_hints(schema_type)

    # Check for missing required fields
    missing_required = required_fields_names - set(data.keys())
    if missing_required:
        raise ValueError(
            f"Schema dict missing required field(s): {', '.join(sorted(missing_required))}"
        )

    # Check for unknown fields (strict validation)
    unknown_fields = set(data.keys()) - expected_fields
    if unknown_fields:
        raise ValueError(
            f"Schema dict contains unknown field(s): {', '.join(sorted(unknown_fields))}"
        )

    # Validate types for provided fields using resolved type hints
    for field_obj in fields(schema_type):
        if field_obj.name in data:
            value = data[field_obj.name]
            resolved_type = type_hints[field_obj.name]
            _validate_field_type(field_obj.name, value, resolved_type)

    # Build the schema instance, filling missing optional fields with None
    try:
        full_data = {f.name: data.get(f.name, None) for f in fields(schema_type)}
        return schema_type(**full_data)
    except (TypeError, AttributeError) as e:
        raise ValueError(f"Invalid schema data: {e}") from e


def load_schema_yaml(
    yaml_path: Path | str,
    schema_type: type[EntityTypeSchema] | type[RelationTypeSchema],
) -> EntityTypeSchema | RelationTypeSchema:
    """Load a single schema from a YAML file.

    Args:
        yaml_path: Path to YAML file
        schema_type: EntityTypeSchema or RelationTypeSchema class

    Returns:
        Schema dataclass instance

    Raises:
        ValueError: Empty file, invalid YAML, or schema validation failure

    Example:
        >>> schema = load_schema_yaml("entity.yaml", EntityTypeSchema)
    """
    yaml_path = Path(yaml_path)

    try:
        with yaml_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in {yaml_path}: {e}") from e

    if data is None or not isinstance(data, dict):
        raise ValueError(f"YAML file {yaml_path} is empty or invalid (expected dict)")

    return schema_from_dict(data, schema_type)


def load_schemas_yaml(
    yaml_path: Path | str,
    schema_type: type[EntityTypeSchema] | type[RelationTypeSchema],
) -> list[EntityTypeSchema] | list[RelationTypeSchema]:
    """Load multiple schemas from a YAML file with a 'schemas' key.

    Args:
        yaml_path: Path to YAML file
        schema_type: EntityTypeSchema or RelationTypeSchema class

    Returns:
        List of schema dataclass instances

    Raises:
        ValueError: Empty file, invalid YAML, missing 'schemas' key, or validation failure

    Example:
        >>> schemas = load_schemas_yaml("entities.yaml", EntityTypeSchema)
    """
    yaml_path = Path(yaml_path)

    try:
        with yaml_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in {yaml_path}: {e}") from e

    if data is None or not isinstance(data, dict):
        raise ValueError(f"YAML file {yaml_path} is empty or invalid (expected dict)")

    if "schemas" not in data:
        raise ValueError(f"YAML file {yaml_path} missing 'schemas' key for multi-schema load")

    schema_list = data["schemas"]
    if not isinstance(schema_list, list):
        raise ValueError(f"'schemas' key in {yaml_path} must be a list")

    return [schema_from_dict(item, schema_type) for item in schema_list]