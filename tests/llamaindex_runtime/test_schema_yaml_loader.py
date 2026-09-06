"""Tests for schema_yaml_loader module - KAG YAML load-and-persist integration.

TDD RED phase: Tests written FIRST before any implementation.
This module tests the thin helper layer that:
1. Loads entity/relation schemas from YAML using existing schema_contract helpers
2. Converts dataclasses to dicts
3. Persists via registry write_entity_type_schema / write_relation_type_schema
4. Returns a summary result object
"""

from unittest.mock import Mock

import pytest

from llamaindex_runtime.registry.contracts import EntityTypeSchema, RelationTypeSchema


class TestLoadSingleEntitySchemaYAML:
    """Test loading and persisting a single entity schema from YAML."""

    def test_single_entity_schema_yaml_persists_via_registry_writer(self, tmp_path):
        """Load single entity schema YAML and persist via registry writer."""
        yaml_content = """
entity_type_name: Person
description: A human being
required_fields:
  - name
  - age
"""
        yaml_file = tmp_path / "person_entity.yaml"
        yaml_file.write_text(yaml_content)

        # Mock registry
        registry = Mock()

        # Import and execute - will fail in RED phase
        from llamaindex_runtime.schema_yaml_loader import load_entity_schema_yaml_and_persist

        result = load_entity_schema_yaml_and_persist(yaml_file, registry)

        # Verify registry write was called
        registry.write_entity_type_schema.assert_called_once()

        # Verify schema dict passed to registry
        call_args = registry.write_entity_type_schema.call_args
        schema_dict = call_args[1]["schema"]

        assert schema_dict["entity_type_name"] == "Person"
        assert schema_dict["description"] == "A human being"
        assert schema_dict["required_fields"] == ["name", "age"]

        # Verify summary result
        assert result is not None
        assert result.schemas_written == 1
        assert result.schemas_failed == 0
        assert result.total_schemas == 1

    def test_single_entity_schema_minimal_fields(self, tmp_path):
        """Load minimal entity schema (only required field) and persist."""
        yaml_content = """
entity_type_name: Organization
"""
        yaml_file = tmp_path / "org_entity.yaml"
        yaml_file.write_text(yaml_content)

        registry = Mock()

        from llamaindex_runtime.schema_yaml_loader import load_entity_schema_yaml_and_persist

        result = load_entity_schema_yaml_and_persist(yaml_file, registry)

        registry.write_entity_type_schema.assert_called_once()

        call_args = registry.write_entity_type_schema.call_args
        schema_dict = call_args[1]["schema"]

        assert schema_dict["entity_type_name"] == "Organization"
        assert schema_dict["description"] is None
        assert schema_dict["required_fields"] is None

        assert result.schemas_written == 1


class TestLoadMultipleEntitySchemasYAML:
    """Test loading and persisting multiple entity schemas from one YAML file."""

    def test_multiple_entity_schemas_from_one_yaml_file_persist(self, tmp_path):
        """Load multiple entity schemas from YAML with 'schemas' key and persist all."""
        yaml_content = """
schemas:
  - entity_type_name: Person
    description: A human being
    required_fields:
      - name
  - entity_type_name: Organization
    description: A company or institution
    required_fields:
      - name
      - industry
"""
        yaml_file = tmp_path / "entities.yaml"
        yaml_file.write_text(yaml_content)

        registry = Mock()

        from llamaindex_runtime.schema_yaml_loader import load_entity_schemas_yaml_and_persist

        result = load_entity_schemas_yaml_and_persist(yaml_file, registry)

        # Verify registry write called twice
        assert registry.write_entity_type_schema.call_count == 2

        # Verify both schemas were written
        calls = registry.write_entity_type_schema.call_args_list
        schema_names = [call[1]["schema"]["entity_type_name"] for call in calls]

        assert "Person" in schema_names
        assert "Organization" in schema_names

        # Verify summary result
        assert result.schemas_written == 2
        assert result.schemas_failed == 0
        assert result.total_schemas == 2

    def test_multiple_entity_schemas_empty_list(self, tmp_path):
        """Handle empty schemas list in YAML gracefully."""
        yaml_content = """
schemas: []
"""
        yaml_file = tmp_path / "empty_entities.yaml"
        yaml_file.write_text(yaml_content)

        registry = Mock()

        from llamaindex_runtime.schema_yaml_loader import load_entity_schemas_yaml_and_persist

        result = load_entity_schemas_yaml_and_persist(yaml_file, registry)

        # No writes should occur
        registry.write_entity_type_schema.assert_not_called()

        # Summary should reflect zero schemas
        assert result.schemas_written == 0
        assert result.total_schemas == 0


class TestLoadRelationSchemaYAML:
    """Test loading and persisting relation schemas from YAML."""

    def test_relation_schema_yaml_persists_via_relation_writer(self, tmp_path):
        """Load relation schema YAML and persist via registry relation writer."""
        yaml_content = """
relation_type_name: WORKS_FOR
allowed_source_types:
  - Person
allowed_target_types:
  - Organization
"""
        yaml_file = tmp_path / "works_for_relation.yaml"
        yaml_file.write_text(yaml_content)

        registry = Mock()

        from llamaindex_runtime.schema_yaml_loader import load_relation_schema_yaml_and_persist

        result = load_relation_schema_yaml_and_persist(yaml_file, registry)

        # Verify registry relation write was called
        registry.write_relation_type_schema.assert_called_once()

        # Verify schema dict passed to registry
        call_args = registry.write_relation_type_schema.call_args
        schema_dict = call_args[1]["schema"]

        assert schema_dict["relation_type_name"] == "WORKS_FOR"
        assert schema_dict["allowed_source_types"] == ["Person"]
        assert schema_dict["allowed_target_types"] == ["Organization"]

        # Verify summary result
        assert result.schemas_written == 1
        assert result.schemas_failed == 0
        assert result.total_schemas == 1

    def test_relation_schema_minimal_fields(self, tmp_path):
        """Load minimal relation schema (only required field) and persist."""
        yaml_content = """
relation_type_name: KNOWS
"""
        yaml_file = tmp_path / "knows_relation.yaml"
        yaml_file.write_text(yaml_content)

        registry = Mock()

        from llamaindex_runtime.schema_yaml_loader import load_relation_schema_yaml_and_persist

        result = load_relation_schema_yaml_and_persist(yaml_file, registry)

        registry.write_relation_type_schema.assert_called_once()

        call_args = registry.write_relation_type_schema.call_args
        schema_dict = call_args[1]["schema"]

        assert schema_dict["relation_type_name"] == "KNOWS"
        assert schema_dict["allowed_source_types"] is None
        assert schema_dict["allowed_target_types"] is None

        assert result.schemas_written == 1

    def test_multiple_relation_schemas_from_one_yaml_file(self, tmp_path):
        """Load multiple relation schemas from YAML and persist all."""
        yaml_content = """
schemas:
  - relation_type_name: WORKS_FOR
    allowed_source_types:
      - Person
    allowed_target_types:
      - Organization
  - relation_type_name: KNOWS
    allowed_source_types:
      - Person
    allowed_target_types:
      - Person
"""
        yaml_file = tmp_path / "relations.yaml"
        yaml_file.write_text(yaml_content)

        registry = Mock()

        from llamaindex_runtime.schema_yaml_loader import load_relation_schemas_yaml_and_persist

        result = load_relation_schemas_yaml_and_persist(yaml_file, registry)

        # Verify registry write called twice
        assert registry.write_relation_type_schema.call_count == 2

        # Verify both schemas were written
        calls = registry.write_relation_type_schema.call_args_list
        relation_names = [call[1]["schema"]["relation_type_name"] for call in calls]

        assert "WORKS_FOR" in relation_names
        assert "KNOWS" in relation_names

        # Verify summary result
        assert result.schemas_written == 2
        assert result.schemas_failed == 0
        assert result.total_schemas == 2


class TestWriteFailureHandling:
    """Test handling of write failures and error surfacing."""

    def test_registry_write_failure_surfaces_in_summary(self, tmp_path):
        """When registry write fails, failure is recorded in summary."""
        yaml_content = """
entity_type_name: Person
description: A human being
"""
        yaml_file = tmp_path / "person.yaml"
        yaml_file.write_text(yaml_content)

        # Mock registry that raises exception on write
        registry = Mock()
        registry.write_entity_type_schema.side_effect = RuntimeError("Database connection failed")

        from llamaindex_runtime.schema_yaml_loader import load_entity_schema_yaml_and_persist

        result = load_entity_schema_yaml_and_persist(yaml_file, registry)

        # Write was attempted
        registry.write_entity_type_schema.assert_called_once()

        # Failure is recorded
        assert result.schemas_written == 0
        assert result.schemas_failed == 1
        assert result.total_schemas == 1
        assert len(result.failures) == 1

        # Failure contains error message
        failure = result.failures[0]
        assert "Person" in failure.schema_name
        assert "Database connection failed" in failure.error_message

    def test_partial_failure_in_multiple_schemas(self, tmp_path):
        """When one of multiple schemas fails, others still persist."""
        yaml_content = """
schemas:
  - entity_type_name: Person
    description: First schema
  - entity_type_name: Organization
    description: Second schema
  - entity_type_name: Location
    description: Third schema
"""
        yaml_file = tmp_path / "mixed_entities.yaml"
        yaml_file.write_text(yaml_content)

        # Mock registry that fails on second write only
        registry = Mock()
        registry.write_entity_type_schema.side_effect = [
            None,  # First succeeds
            RuntimeError("Write failed for Organization"),  # Second fails
            None,  # Third succeeds
        ]

        from llamaindex_runtime.schema_yaml_loader import load_entity_schemas_yaml_and_persist

        result = load_entity_schemas_yaml_and_persist(yaml_file, registry)

        # Three writes attempted
        assert registry.write_entity_type_schema.call_count == 3

        # Two succeeded, one failed
        assert result.schemas_written == 2
        assert result.schemas_failed == 1
        assert result.total_schemas == 3

        # Failure details
        assert len(result.failures) == 1
        failure = result.failures[0]
        assert "Organization" in failure.schema_name
        assert "Write failed" in failure.error_message


class TestYAMLParsingErrors:
    """Test handling of YAML parsing errors."""

    def test_invalid_yaml_raises_clear_error(self, tmp_path):
        """Malformed YAML raises ValueError with clear message."""
        yaml_content = """
entity_type_name: [invalid
  unclosed bracket
"""
        yaml_file = tmp_path / "malformed.yaml"
        yaml_file.write_text(yaml_content)

        registry = Mock()

        from llamaindex_runtime.schema_yaml_loader import load_entity_schema_yaml_and_persist

        with pytest.raises(ValueError, match="Invalid YAML|YAML"):
            load_entity_schema_yaml_and_persist(yaml_file, registry)

        # No registry write should occur
        registry.write_entity_type_schema.assert_not_called()

    def test_schema_validation_error_propagates(self, tmp_path):
        """Schema contract validation errors propagate clearly."""
        yaml_content = """
entity_type_name: Person
unknown_field: invalid
"""
        yaml_file = tmp_path / "invalid_schema.yaml"
        yaml_file.write_text(yaml_content)

        registry = Mock()

        from llamaindex_runtime.schema_yaml_loader import load_entity_schema_yaml_and_persist

        with pytest.raises(ValueError, match="unknown field"):
            load_entity_schema_yaml_and_persist(yaml_file, registry)

        registry.write_entity_type_schema.assert_not_called()


class TestResultSummaryContract:
    """Test the summary result object contract."""

    def test_result_object_has_required_fields(self, tmp_path):
        """Result summary must have schemas_written, schemas_failed, total_schemas, failures."""
        yaml_content = """
entity_type_name: TestEntity
"""
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(yaml_content)

        registry = Mock()

        from llamaindex_runtime.schema_yaml_loader import load_entity_schema_yaml_and_persist

        result = load_entity_schema_yaml_and_persist(yaml_file, registry)

        # Required fields present
        assert hasattr(result, "schemas_written")
        assert hasattr(result, "schemas_failed")
        assert hasattr(result, "total_schemas")
        assert hasattr(result, "failures")

        # Types are correct
        assert isinstance(result.schemas_written, int)
        assert isinstance(result.schemas_failed, int)
        assert isinstance(result.total_schemas, int)
        assert isinstance(result.failures, list)

    def test_failure_object_contract(self, tmp_path):
        """Failure entry must have schema_name, schema_type, error_message."""
        yaml_content = """
entity_type_name: FailingEntity
"""
        yaml_file = tmp_path / "fail.yaml"
        yaml_file.write_text(yaml_content)

        registry = Mock()
        registry.write_entity_type_schema.side_effect = RuntimeError("Test error")

        from llamaindex_runtime.schema_yaml_loader import load_entity_schema_yaml_and_persist

        result = load_entity_schema_yaml_and_persist(yaml_file, registry)

        assert len(result.failures) == 1
        failure = result.failures[0]

        # Required fields present
        assert hasattr(failure, "schema_name")
        assert hasattr(failure, "schema_type")
        assert hasattr(failure, "error_message")

        # Types are correct
        assert isinstance(failure.schema_name, str)
        assert isinstance(failure.schema_type, str)
        assert isinstance(failure.error_message, str)