"""Tests for schema_contract module - TDD RED phase."""

import pytest

from llamaindex_runtime.registry.contracts import EntityTypeSchema, RelationTypeSchema


class TestEntityTypeSchemaRoundTrip:
    """Test entity schema dict/dataclass round-trip."""

    def test_entity_schema_to_dict_minimal(self):
        """Convert minimal entity schema to dict."""
        schema = EntityTypeSchema(entity_type_name="Person")
        from llamaindex_runtime.schema_contract import schema_to_dict

        result = schema_to_dict(schema)

        assert result == {
            "entity_type_name": "Person",
            "description": None,
            "required_fields": None,
        }

    def test_entity_schema_to_dict_full(self):
        """Convert full entity schema to dict."""
        schema = EntityTypeSchema(
            entity_type_name="Person",
            description="A human being",
            required_fields=["name", "age"],
        )
        from llamaindex_runtime.schema_contract import schema_to_dict

        result = schema_to_dict(schema)

        assert result == {
            "entity_type_name": "Person",
            "description": "A human being",
            "required_fields": ["name", "age"],
        }

    def test_entity_schema_from_dict_minimal(self):
        """Load minimal entity schema from dict."""
        data = {"entity_type_name": "Person"}
        from llamaindex_runtime.schema_contract import schema_from_dict

        result = schema_from_dict(data, EntityTypeSchema)

        assert result == EntityTypeSchema(entity_type_name="Person")

    def test_entity_schema_from_dict_full(self):
        """Load full entity schema from dict."""
        data = {
            "entity_type_name": "Person",
            "description": "A human being",
            "required_fields": ["name", "age"],
        }
        from llamaindex_runtime.schema_contract import schema_from_dict

        result = schema_from_dict(data, EntityTypeSchema)

        assert result == EntityTypeSchema(
            entity_type_name="Person",
            description="A human being",
            required_fields=["name", "age"],
        )

    def test_entity_schema_round_trip(self):
        """Round-trip entity schema through dict."""
        original = EntityTypeSchema(
            entity_type_name="Organization",
            description="A company or institution",
            required_fields=["name"],
        )
        from llamaindex_runtime.schema_contract import schema_to_dict, schema_from_dict

        data = schema_to_dict(original)
        result = schema_from_dict(data, EntityTypeSchema)

        assert result == original


class TestRelationTypeSchemaRoundTrip:
    """Test relation schema dict/dataclass round-trip."""

    def test_relation_schema_to_dict_minimal(self):
        """Convert minimal relation schema to dict."""
        schema = RelationTypeSchema(relation_type_name="WORKS_FOR")
        from llamaindex_runtime.schema_contract import schema_to_dict

        result = schema_to_dict(schema)

        assert result == {
            "relation_type_name": "WORKS_FOR",
            "allowed_source_types": None,
            "allowed_target_types": None,
        }

    def test_relation_schema_to_dict_full(self):
        """Convert full relation schema to dict."""
        schema = RelationTypeSchema(
            relation_type_name="WORKS_FOR",
            allowed_source_types=["Person"],
            allowed_target_types=["Organization"],
        )
        from llamaindex_runtime.schema_contract import schema_to_dict

        result = schema_to_dict(schema)

        assert result == {
            "relation_type_name": "WORKS_FOR",
            "allowed_source_types": ["Person"],
            "allowed_target_types": ["Organization"],
        }

    def test_relation_schema_from_dict_minimal(self):
        """Load minimal relation schema from dict."""
        data = {"relation_type_name": "WORKS_FOR"}
        from llamaindex_runtime.schema_contract import schema_from_dict

        result = schema_from_dict(data, RelationTypeSchema)

        assert result == RelationTypeSchema(relation_type_name="WORKS_FOR")

    def test_relation_schema_from_dict_full(self):
        """Load full relation schema from dict."""
        data = {
            "relation_type_name": "WORKS_FOR",
            "allowed_source_types": ["Person"],
            "allowed_target_types": ["Organization"],
        }
        from llamaindex_runtime.schema_contract import schema_from_dict

        result = schema_from_dict(data, RelationTypeSchema)

        assert result == RelationTypeSchema(
            relation_type_name="WORKS_FOR",
            allowed_source_types=["Person"],
            allowed_target_types=["Organization"],
        )

    def test_relation_schema_round_trip(self):
        """Round-trip relation schema through dict."""
        original = RelationTypeSchema(
            relation_type_name="EMPLOYS",
            allowed_source_types=["Organization"],
            allowed_target_types=["Person"],
        )
        from llamaindex_runtime.schema_contract import schema_to_dict, schema_from_dict

        data = schema_to_dict(original)
        result = schema_from_dict(data, RelationTypeSchema)

        assert result == original


class TestSchemaValidation:
    """Test schema validation and error handling."""

    def test_entity_schema_missing_required_field(self):
        """Reject entity schema missing entity_type_name."""
        data = {"description": "Missing name field"}
        from llamaindex_runtime.schema_contract import schema_from_dict

        with pytest.raises(ValueError, match="missing required field.*entity_type_name"):
            schema_from_dict(data, EntityTypeSchema)

    def test_relation_schema_missing_required_field(self):
        """Reject relation schema missing relation_type_name."""
        data = {"allowed_source_types": ["Person"]}
        from llamaindex_runtime.schema_contract import schema_from_dict

        with pytest.raises(ValueError, match="missing required field.*relation_type_name"):
            schema_from_dict(data, RelationTypeSchema)

    def test_entity_schema_unknown_field_rejected(self):
        """Reject entity schema with unknown field in strict mode."""
        data = {
            "entity_type_name": "Person",
            "unknown_field": "should_fail",
        }
        from llamaindex_runtime.schema_contract import schema_from_dict

        with pytest.raises(ValueError, match="unknown field.*unknown_field"):
            schema_from_dict(data, EntityTypeSchema)

    def test_relation_schema_unknown_field_rejected(self):
        """Reject relation schema with unknown field in strict mode."""
        data = {
            "relation_type_name": "WORKS_FOR",
            "invalid_field": 123,
        }
        from llamaindex_runtime.schema_contract import schema_from_dict

        with pytest.raises(ValueError, match="unknown field.*invalid_field"):
            schema_from_dict(data, RelationTypeSchema)

    def test_entity_schema_invalid_type(self):
        """Reject entity schema with wrong type for field."""
        data = {
            "entity_type_name": "Person",
            "required_fields": "should_be_list",  # Should be list, not string
        }
        from llamaindex_runtime.schema_contract import schema_from_dict

        with pytest.raises((ValueError, TypeError)):
            schema_from_dict(data, EntityTypeSchema)

    def test_entity_schema_invalid_list_element_type(self):
        """Reject entity schema with non-string elements in required_fields."""
        data = {
            "entity_type_name": "Person",
            "required_fields": ["name", 123],
        }
        from llamaindex_runtime.schema_contract import schema_from_dict

        with pytest.raises((ValueError, TypeError), match="required_fields"):
            schema_from_dict(data, EntityTypeSchema)


class TestYAMLLoading:
    """Test YAML file loading for schemas."""

    def test_load_single_entity_schema_yaml(self, tmp_path):
        """Load a single entity schema from YAML file."""
        yaml_content = """
entity_type_name: Person
description: A human being
required_fields:
  - name
  - age
"""
        yaml_file = tmp_path / "entity_schema.yaml"
        yaml_file.write_text(yaml_content)

        from llamaindex_runtime.schema_contract import load_schema_yaml

        result = load_schema_yaml(yaml_file, EntityTypeSchema)

        assert result == EntityTypeSchema(
            entity_type_name="Person",
            description="A human being",
            required_fields=["name", "age"],
        )

    def test_load_single_relation_schema_yaml(self, tmp_path):
        """Load a single relation schema from YAML file."""
        yaml_content = """
relation_type_name: WORKS_FOR
allowed_source_types:
  - Person
allowed_target_types:
  - Organization
"""
        yaml_file = tmp_path / "relation_schema.yaml"
        yaml_file.write_text(yaml_content)

        from llamaindex_runtime.schema_contract import load_schema_yaml

        result = load_schema_yaml(yaml_file, RelationTypeSchema)

        assert result == RelationTypeSchema(
            relation_type_name="WORKS_FOR",
            allowed_source_types=["Person"],
            allowed_target_types=["Organization"],
        )

    def test_load_multiple_schemas_yaml(self, tmp_path):
        """Load multiple schemas from YAML with document list."""
        yaml_content = """
schemas:
  - entity_type_name: Person
    description: A human being
    required_fields:
      - name
  - entity_type_name: Organization
    description: A company
    required_fields:
      - name
"""
        yaml_file = tmp_path / "schemas.yaml"
        yaml_file.write_text(yaml_content)

        from llamaindex_runtime.schema_contract import load_schemas_yaml

        result = load_schemas_yaml(yaml_file, EntityTypeSchema)

        assert len(result) == 2
        assert result[0] == EntityTypeSchema(
            entity_type_name="Person",
            description="A human being",
            required_fields=["name"],
        )
        assert result[1] == EntityTypeSchema(
            entity_type_name="Organization",
            description="A company",
            required_fields=["name"],
        )

    def test_load_empty_yaml_file(self, tmp_path):
        """Handle empty YAML file gracefully."""
        yaml_file = tmp_path / "empty.yaml"
        yaml_file.write_text("")

        from llamaindex_runtime.schema_contract import load_schema_yaml

        with pytest.raises(ValueError, match="empty or invalid"):
            load_schema_yaml(yaml_file, EntityTypeSchema)

    def test_load_malformed_yaml(self, tmp_path):
        """Reject malformed YAML with clear error."""
        yaml_content = """
entity_type_name: [invalid
  unclosed bracket
"""
        yaml_file = tmp_path / "malformed.yaml"
        yaml_file.write_text(yaml_content)

        from llamaindex_runtime.schema_contract import load_schema_yaml

        with pytest.raises((ValueError, Exception)):  # YAML parse error
            load_schema_yaml(yaml_file, EntityTypeSchema)


class TestOptionalFields:
    """Test handling of optional fields."""

    def test_entity_schema_none_preserved(self):
        """Preserve None values for optional fields."""
        schema = EntityTypeSchema(
            entity_type_name="Event",
            description=None,
            required_fields=None,
        )
        from llamaindex_runtime.schema_contract import schema_to_dict, schema_from_dict

        data = schema_to_dict(schema)
        result = schema_from_dict(data, EntityTypeSchema)

        assert result.description is None
        assert result.required_fields is None

    def test_relation_schema_empty_list_vs_none(self):
        """Distinguish empty list from None."""
        schema_none = RelationTypeSchema(
            relation_type_name="KNOWS",
            allowed_source_types=None,
            allowed_target_types=None,
        )
        schema_empty = RelationTypeSchema(
            relation_type_name="KNOWS",
            allowed_source_types=[],
            allowed_target_types=[],
        )
        from llamaindex_runtime.schema_contract import schema_to_dict, schema_from_dict

        data_none = schema_to_dict(schema_none)
        data_empty = schema_to_dict(schema_empty)

        # None should serialize to null
        assert data_none["allowed_source_types"] is None
        assert data_none["allowed_target_types"] is None

        # Empty list should serialize to []
        assert data_empty["allowed_source_types"] == []
        assert data_empty["allowed_target_types"] == []

        # Round-trip both
        result_none = schema_from_dict(data_none, RelationTypeSchema)
        result_empty = schema_from_dict(data_empty, RelationTypeSchema)

        assert result_none.allowed_source_types is None
        assert result_empty.allowed_source_types == []