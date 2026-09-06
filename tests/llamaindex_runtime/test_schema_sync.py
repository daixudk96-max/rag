"""Tests for schema_sync module - infer-and-persist integration helper.

This module tests the thin integration layer that:
1. Reads entities from registry
2. Groups by entity_type
3. Infers schema for each group
4. Persists schemas back to registry

Also tests relation schema sync:
1. Reads relations and entities from registry
2. Groups relations by relation_type
3. Infers schema for each group
4. Persists relation schemas back to registry
"""

from unittest.mock import Mock, patch
from uuid import uuid4

from llamaindex_runtime.schema_sync import (
    infer_and_persist_entity_schemas,
    infer_and_persist_relation_schemas,
)


class TestInferAndPersistEntitySchemas:
    """Test the main integration function."""

    def test_empty_entity_list_results_in_zero_writes(self):
        """When no entities exist, no schema writes should occur."""
        registry = Mock()
        registry.query_entities.return_value = []

        result = infer_and_persist_entity_schemas(registry)

        assert result is not None
        assert result.schemas_written == 0
        registry.query_entities.assert_called_once()
        registry.write_entity_type_schema.assert_not_called()

    def test_single_entity_type_writes_one_schema(self):
        """When all entities share one type, one schema should be written."""
        entity_type = "concept"
        entities = [
            {
                "entity_id": uuid4(),
                "entity_key": "concept:a",
                "entity_type": entity_type,
                "canonical_name": "A",
            },
            {
                "entity_id": uuid4(),
                "entity_key": "concept:b",
                "entity_type": entity_type,
                "canonical_name": "B",
            },
        ]

        registry = Mock()
        registry.query_entities.return_value = entities

        result = infer_and_persist_entity_schemas(registry)

        assert result is not None
        assert result.schemas_written == 1
        registry.write_entity_type_schema.assert_called_once()

        # Verify the schema structure passed to write_entity_type_schema
        call_args = registry.write_entity_type_schema.call_args
        schema = call_args[1]["schema"]

        assert schema["entity_type_name"] == entity_type
        assert "canonical_name" in schema["required_fields"]
        assert "entity_type" in schema["required_fields"]

    def test_multiple_entity_types_write_multiple_schemas(self):
        """When entities have different types, each type gets its own schema."""
        entities = [
            {
                "entity_id": uuid4(),
                "entity_key": "concept:a",
                "entity_type": "concept",
                "canonical_name": "A",
            },
            {
                "entity_id": uuid4(),
                "entity_key": "metric:b",
                "entity_type": "metric",
                "value": 42,
            },
        ]

        registry = Mock()
        registry.query_entities.return_value = entities

        result = infer_and_persist_entity_schemas(registry)

        assert result is not None
        assert result.schemas_written == 2
        assert registry.write_entity_type_schema.call_count == 2

        # Verify both schemas were written
        calls = registry.write_entity_type_schema.call_args_list
        schema_names = {call[1]["schema"]["entity_type_name"] for call in calls}

        assert schema_names == {"concept", "metric"}

    def test_entities_without_entity_type_are_ignored(self):
        """Entities lacking entity_type field should be skipped, not crash."""
        entities = [
            {
                "entity_id": uuid4(),
                "entity_key": "concept:a",
                "entity_type": "concept",
                "canonical_name": "A",
            },
            {
                "entity_id": uuid4(),
                "entity_key": "orphan",
                # Missing entity_type
                "name": "Orphan",
            },
        ]

        registry = Mock()
        registry.query_entities.return_value = entities

        result = infer_and_persist_entity_schemas(registry)

        # Should not crash, should write one schema for the valid entity
        assert result is not None
        assert result.schemas_written == 1
        registry.write_entity_type_schema.assert_called_once()

        schema = registry.write_entity_type_schema.call_args[1]["schema"]
        assert schema["entity_type_name"] == "concept"

    def test_required_fields_persisted_through_registry(self):
        """Verify that required_fields from infer_entity_type_schema are persisted."""
        entities = [
            {
                "entity_id": uuid4(),
                "entity_key": "concept:a",
                "entity_type": "concept",
                "canonical_name": "A",
                "optional_field": "present_in_first",
            },
            {
                "entity_id": uuid4(),
                "entity_key": "concept:b",
                "entity_type": "concept",
                "canonical_name": "B",
                # optional_field is missing here
            },
        ]

        registry = Mock()
        registry.query_entities.return_value = entities

        result = infer_and_persist_entity_schemas(registry)

        assert result.schemas_written == 1

        schema = registry.write_entity_type_schema.call_args[1]["schema"]

        # Fields present in 100% of entities should be required
        assert "entity_id" in schema["required_fields"]
        assert "entity_key" in schema["required_fields"]
        assert "entity_type" in schema["required_fields"]
        assert "canonical_name" in schema["required_fields"]

        # Optional field (present in only 50%) should not be required
        assert "optional_field" not in schema["required_fields"]

    def test_returns_summary_with_entity_counts(self):
        """Result should include helpful summary information."""
        entities = [
            {
                "entity_id": uuid4(),
                "entity_key": "concept:a",
                "entity_type": "concept",
            },
            {
                "entity_id": uuid4(),
                "entity_key": "concept:b",
                "entity_type": "concept",
            },
            {
                "entity_id": uuid4(),
                "entity_key": "metric:x",
                "entity_type": "metric",
            },
        ]

        registry = Mock()
        registry.query_entities.return_value = entities

        result = infer_and_persist_entity_schemas(registry)

        assert result is not None
        assert result.schemas_written == 2
        assert result.total_entities == 3
        assert "concept" in result.entity_types
        assert "metric" in result.entity_types

    def test_failed_entity_type_is_reported_in_summary(self):
        """Failed schema persistence should be recorded in the result summary."""
        entities = [
            {
                "entity_id": uuid4(),
                "entity_key": "concept:a",
                "entity_type": "concept",
                "canonical_name": "A",
            },
        ]

        registry = Mock()
        registry.query_entities.return_value = entities
        registry.write_entity_type_schema.side_effect = RuntimeError("write failed")

        result = infer_and_persist_entity_schemas(registry)

        assert result.schemas_written == 0
        assert result.failed_types == ["concept"]

    @patch("llamaindex_runtime.schema_sync.infer_entity_type_schema")
    def test_inference_failure_is_reported_in_summary(self, mock_infer):
        """Failed schema inference should be recorded in the result summary."""
        entities = [
            {
                "entity_id": uuid4(),
                "entity_key": "concept:a",
                "entity_type": "concept",
                "canonical_name": "A",
            },
        ]

        registry = Mock()
        registry.query_entities.return_value = entities
        mock_infer.side_effect = ValueError("inference failed")

        result = infer_and_persist_entity_schemas(registry)

        assert result.schemas_written == 0
        assert result.failed_types == ["concept"]
        registry.write_entity_type_schema.assert_not_called()


class TestInferAndPersistRelationSchemas:
    """Test the relation schema integration function."""

    def test_empty_relation_list_results_in_zero_writes(self):
        """When no relations exist, no schema writes should occur."""
        registry = Mock()
        registry.query_relations.return_value = []
        registry.query_entities.return_value = []

        result = infer_and_persist_relation_schemas(registry)

        assert result is not None
        assert result.schemas_written == 0
        registry.query_relations.assert_called_once()
        registry.query_entities.assert_not_called()
        registry.write_relation_type_schema.assert_not_called()

    def test_single_relation_type_writes_one_schema(self):
        """When all relations share one type, one schema should be written."""
        source_id = uuid4()
        target_id = uuid4()
        entities = [
            {
                "entity_id": source_id,
                "entity_key": "concept:a",
                "entity_type": "concept",
            },
            {
                "entity_id": target_id,
                "entity_key": "metric:b",
                "entity_type": "metric",
            },
        ]
        relations = [
            {
                "relation_id": uuid4(),
                "relation_type": "affects",
                "source_entity_id": source_id,
                "target_entity_id": target_id,
            },
        ]

        registry = Mock()
        registry.query_relations.return_value = relations
        registry.query_entities.return_value = entities

        result = infer_and_persist_relation_schemas(registry)

        assert result is not None
        assert result.schemas_written == 1
        registry.write_relation_type_schema.assert_called_once()

        # Verify the schema structure passed to write_relation_type_schema
        call_args = registry.write_relation_type_schema.call_args
        schema = call_args[1]["schema"]

        assert schema["relation_type_name"] == "affects"
        assert schema["allowed_source_types"] == ["concept"]
        assert schema["allowed_target_types"] == ["metric"]

    def test_multiple_relation_types_write_multiple_schemas(self):
        """When relations have different types, each type gets its own schema."""
        e1, e2, e3 = uuid4(), uuid4(), uuid4()
        entities = [
            {"entity_id": e1, "entity_key": "concept:a", "entity_type": "concept"},
            {"entity_id": e2, "entity_key": "metric:b", "entity_type": "metric"},
            {"entity_id": e3, "entity_key": "concept:c", "entity_type": "concept"},
        ]
        relations = [
            {
                "relation_id": uuid4(),
                "relation_type": "affects",
                "source_entity_id": e1,
                "target_entity_id": e2,
            },
            {
                "relation_id": uuid4(),
                "relation_type": "relates_to",
                "source_entity_id": e1,
                "target_entity_id": e3,
            },
        ]

        registry = Mock()
        registry.query_relations.return_value = relations
        registry.query_entities.return_value = entities

        result = infer_and_persist_relation_schemas(registry)

        assert result is not None
        assert result.schemas_written == 2
        assert registry.write_relation_type_schema.call_count == 2

        # Verify both schemas were written
        calls = registry.write_relation_type_schema.call_args_list
        schema_names = {call[1]["schema"]["relation_type_name"] for call in calls}

        assert schema_names == {"affects", "relates_to"}

    def test_relations_without_relation_type_are_ignored(self):
        """Relations lacking relation_type field should be skipped, not crash."""
        e1, e2 = uuid4(), uuid4()
        entities = [
            {"entity_id": e1, "entity_key": "concept:a", "entity_type": "concept"},
            {"entity_id": e2, "entity_key": "metric:b", "entity_type": "metric"},
        ]
        relations = [
            {
                "relation_id": uuid4(),
                "relation_type": "affects",
                "source_entity_id": e1,
                "target_entity_id": e2,
            },
            {
                "relation_id": uuid4(),
                # Missing relation_type
                "source_entity_id": e1,
                "target_entity_id": e2,
            },
        ]

        registry = Mock()
        registry.query_relations.return_value = relations
        registry.query_entities.return_value = entities

        result = infer_and_persist_relation_schemas(registry)

        # Should not crash, should write one schema for the valid relation
        assert result is not None
        assert result.schemas_written == 1
        registry.write_relation_type_schema.assert_called_once()

        schema = registry.write_relation_type_schema.call_args[1]["schema"]
        assert schema["relation_type_name"] == "affects"

    def test_allowed_source_and_target_types_persisted(self):
        """Verify that allowed_source_types and allowed_target_types are persisted."""
        e1, e2, e3 = uuid4(), uuid4(), uuid4()
        entities = [
            {"entity_id": e1, "entity_key": "concept:a", "entity_type": "concept"},
            {"entity_id": e2, "entity_key": "metric:b", "entity_type": "metric"},
            {"entity_id": e3, "entity_key": "concept:c", "entity_type": "concept"},
        ]
        relations = [
            {
                "relation_id": uuid4(),
                "relation_type": "affects",
                "source_entity_id": e1,
                "target_entity_id": e2,
            },
            {
                "relation_id": uuid4(),
                "relation_type": "affects",
                "source_entity_id": e3,
                "target_entity_id": e2,
            },
        ]

        registry = Mock()
        registry.query_relations.return_value = relations
        registry.query_entities.return_value = entities

        result = infer_and_persist_relation_schemas(registry)

        assert result.schemas_written == 1

        schema = registry.write_relation_type_schema.call_args[1]["schema"]

        # Both concept entities should be in allowed_source_types
        assert "concept" in schema["allowed_source_types"]
        # Target is always metric
        assert schema["allowed_target_types"] == ["metric"]

    def test_returns_summary_with_relation_counts(self):
        """Result should include helpful summary information."""
        e1, e2, e3 = uuid4(), uuid4(), uuid4()
        entities = [
            {"entity_id": e1, "entity_key": "concept:a", "entity_type": "concept"},
            {"entity_id": e2, "entity_key": "metric:b", "entity_type": "metric"},
            {"entity_id": e3, "entity_key": "concept:c", "entity_type": "concept"},
        ]
        relations = [
            {
                "relation_id": uuid4(),
                "relation_type": "affects",
                "source_entity_id": e1,
                "target_entity_id": e2,
            },
            {
                "relation_id": uuid4(),
                "relation_type": "affects",
                "source_entity_id": e3,
                "target_entity_id": e2,
            },
            {
                "relation_id": uuid4(),
                "relation_type": "relates_to",
                "source_entity_id": e1,
                "target_entity_id": e3,
            },
        ]

        registry = Mock()
        registry.query_relations.return_value = relations
        registry.query_entities.return_value = entities

        result = infer_and_persist_relation_schemas(registry)

        assert result is not None
        assert result.schemas_written == 2
        assert result.total_relations == 3
        assert "affects" in result.relation_types
        assert "relates_to" in result.relation_types

    def test_failed_relation_type_is_reported_in_summary(self):
        """Failed schema persistence should be recorded in the result summary."""
        e1, e2 = uuid4(), uuid4()
        entities = [
            {"entity_id": e1, "entity_key": "concept:a", "entity_type": "concept"},
            {"entity_id": e2, "entity_key": "metric:b", "entity_type": "metric"},
        ]
        relations = [
            {
                "relation_id": uuid4(),
                "relation_type": "affects",
                "source_entity_id": e1,
                "target_entity_id": e2,
            },
        ]

        registry = Mock()
        registry.query_relations.return_value = relations
        registry.query_entities.return_value = entities
        registry.write_relation_type_schema.side_effect = RuntimeError("write failed")

        result = infer_and_persist_relation_schemas(registry)

        assert result.schemas_written == 0
        assert result.failed_types == ["affects"]

    @patch("llamaindex_runtime.schema_sync.infer_relation_type_schema")
    def test_inference_failure_is_reported_in_summary(self, mock_infer):
        """Failed schema inference should be recorded in the result summary."""
        e1, e2 = uuid4(), uuid4()
        entities = [
            {"entity_id": e1, "entity_key": "concept:a", "entity_type": "concept"},
            {"entity_id": e2, "entity_key": "metric:b", "entity_type": "metric"},
        ]
        relations = [
            {
                "relation_id": uuid4(),
                "relation_type": "affects",
                "source_entity_id": e1,
                "target_entity_id": e2,
            },
        ]

        registry = Mock()
        registry.query_relations.return_value = relations
        registry.query_entities.return_value = entities
        mock_infer.side_effect = ValueError("inference failed")

        result = infer_and_persist_relation_schemas(registry)

        assert result.schemas_written == 0
        assert result.failed_types == ["affects"]
        registry.write_relation_type_schema.assert_not_called()
