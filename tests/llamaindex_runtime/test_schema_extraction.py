"""Tests for P4 KAG-style schema extraction from existing entity/relation records.

These tests verify:
1. Entity schema inference marks 100%-present fields as required
2. Fields missing from some entities are not required
3. Relation schema inference collects observed allowed source/target types
4. Empty entity/relation lists raise clear ValueError
5. Missing entity_type/relation_type fields are rejected clearly

These are unit tests for pure extraction functions, no database required.
"""
from __future__ import annotations

import uuid

import pytest


class TestInferEntityTypeSchema:
    """Unit tests for infer_entity_type_schema pure function."""

    def test_all_present_fields_marked_as_required(self) -> None:
        """Fields present in all entities should be marked as required."""
        from llamaindex_runtime.schema_extraction import infer_entity_type_schema

        entities = [
            {
                "entity_id": uuid.uuid4(),
                "entity_key": "concept:pm25",
                "entity_type": "concept",
                "canonical_name": "PM2.5",
                "description": "Particulate matter",
            },
            {
                "entity_id": uuid.uuid4(),
                "entity_key": "concept:aqi",
                "entity_type": "concept",
                "canonical_name": "AQI",
                "description": "Air quality index",
            },
        ]

        schema = infer_entity_type_schema(entities, "concept")

        assert schema.entity_type_name == "concept"
        # These fields are present in both entities
        assert "canonical_name" in schema.required_fields
        assert "description" in schema.required_fields
        # These are infrastructure fields, always present
        assert "entity_id" in schema.required_fields
        assert "entity_key" in schema.required_fields
        assert "entity_type" in schema.required_fields

    def test_missing_fields_not_required(self) -> None:
        """Fields missing from some entities should not be marked as required."""
        from llamaindex_runtime.schema_extraction import infer_entity_type_schema

        entities = [
            {
                "entity_id": uuid.uuid4(),
                "entity_key": "concept:pm25",
                "entity_type": "concept",
                "canonical_name": "PM2.5",
                "description": "Particulate matter",
            },
            {
                "entity_id": uuid.uuid4(),
                "entity_key": "concept:aqi",
                "entity_type": "concept",
                "canonical_name": "AQI",
                # Missing description field
            },
        ]

        schema = infer_entity_type_schema(entities, "concept")

        assert schema.entity_type_name == "concept"
        # canonical_name is in both, so required
        assert "canonical_name" in schema.required_fields
        # description is only in one, so NOT required
        assert "description" not in schema.required_fields

    def test_empty_entity_list_raises_value_error(self) -> None:
        """Empty entity list should raise clear ValueError."""
        from llamaindex_runtime.schema_extraction import infer_entity_type_schema

        with pytest.raises(ValueError, match="empty"):
            infer_entity_type_schema([], "concept")

    def test_missing_entity_type_field_rejected(self) -> None:
        """Entity dict without entity_type field should raise clear error."""
        from llamaindex_runtime.schema_extraction import infer_entity_type_schema

        entities = [
            {
                "entity_id": uuid.uuid4(),
                "entity_key": "concept:pm25",
                # Missing entity_type field
                "canonical_name": "PM2.5",
            }
        ]

        with pytest.raises(ValueError, match="entity_type"):
            infer_entity_type_schema(entities, "concept")

    def test_mismatched_entity_type_rejected(self) -> None:
        """Entity with entity_type != target_type should raise error."""
        from llamaindex_runtime.schema_extraction import infer_entity_type_schema

        entities = [
            {
                "entity_id": uuid.uuid4(),
                "entity_key": "metric:pm25",
                "entity_type": "metric",  # Not "concept"
                "canonical_name": "PM2.5",
            }
        ]

        with pytest.raises(ValueError, match="entity_type"):
            infer_entity_type_schema(entities, "concept")

    def test_single_entity_infers_schema(self) -> None:
        """Schema can be inferred from a single entity."""
        from llamaindex_runtime.schema_extraction import infer_entity_type_schema

        entities = [
            {
                "entity_id": uuid.uuid4(),
                "entity_key": "concept:pm25",
                "entity_type": "concept",
                "canonical_name": "PM2.5",
            }
        ]

        schema = infer_entity_type_schema(entities, "concept")

        assert schema.entity_type_name == "concept"
        # All fields in this single entity are "100% present"
        assert "canonical_name" in schema.required_fields


class TestInferRelationTypeSchema:
    """Unit tests for infer_relation_type_schema pure function."""

    def test_collects_allowed_source_types(self) -> None:
        """Schema should collect observed source entity types."""
        from llamaindex_runtime.schema_extraction import infer_relation_type_schema

        e1 = uuid.uuid4()
        e2 = uuid.uuid4()
        e3 = uuid.uuid4()

        entities = [
            {"entity_id": e1, "entity_key": "concept:a", "entity_type": "concept"},
            {"entity_id": e2, "entity_key": "concept:b", "entity_type": "concept"},
            {"entity_id": e3, "entity_key": "metric:c", "entity_type": "metric"},
        ]

        relations = [
            {
                "relation_id": uuid.uuid4(),
                "relation_key": "affects-1",
                "relation_type": "affects",
                "source_entity_id": e1,
                "target_entity_id": e2,
            },
            {
                "relation_id": uuid.uuid4(),
                "relation_key": "affects-2",
                "relation_type": "affects",
                "source_entity_id": e2,
                "target_entity_id": e3,
            },
        ]

        schema = infer_relation_type_schema(relations, entities, "affects")

        assert schema.relation_type_name == "affects"
        # Both relations have source of type "concept"
        assert schema.allowed_source_types == ["concept"]
        # Targets are "concept" and "metric"
        assert set(schema.allowed_target_types) == {"concept", "metric"}

    def test_collects_multiple_source_types(self) -> None:
        """Schema should collect multiple observed source entity types."""
        from llamaindex_runtime.schema_extraction import infer_relation_type_schema

        e1 = uuid.uuid4()
        e2 = uuid.uuid4()
        e3 = uuid.uuid4()

        entities = [
            {"entity_id": e1, "entity_key": "concept:a", "entity_type": "concept"},
            {"entity_id": e2, "entity_key": "metric:b", "entity_type": "metric"},
            {"entity_id": e3, "entity_key": "concept:c", "entity_type": "concept"},
        ]

        relations = [
            {
                "relation_id": uuid.uuid4(),
                "relation_key": "relates-1",
                "relation_type": "relates_to",
                "source_entity_id": e1,
                "target_entity_id": e3,
            },
            {
                "relation_id": uuid.uuid4(),
                "relation_key": "relates-2",
                "relation_type": "relates_to",
                "source_entity_id": e2,
                "target_entity_id": e3,
            },
        ]

        schema = infer_relation_type_schema(relations, entities, "relates_to")

        assert schema.relation_type_name == "relates_to"
        # Sources are "concept" and "metric"
        assert set(schema.allowed_source_types) == {"concept", "metric"}
        # All targets are "concept"
        assert schema.allowed_target_types == ["concept"]

    def test_empty_relation_list_raises_value_error(self) -> None:
        """Empty relation list should raise clear ValueError."""
        from llamaindex_runtime.schema_extraction import infer_relation_type_schema

        entities = [
            {"entity_id": uuid.uuid4(), "entity_key": "concept:a", "entity_type": "concept"}
        ]

        with pytest.raises(ValueError, match="empty"):
            infer_relation_type_schema([], entities, "relates_to")

    def test_missing_relation_type_field_rejected(self) -> None:
        """Relation dict without relation_type field should raise error."""
        from llamaindex_runtime.schema_extraction import infer_relation_type_schema

        e1 = uuid.uuid4()
        e2 = uuid.uuid4()

        entities = [
            {"entity_id": e1, "entity_key": "concept:a", "entity_type": "concept"},
            {"entity_id": e2, "entity_key": "concept:b", "entity_type": "concept"},
        ]

        relations = [
            {
                "relation_id": uuid.uuid4(),
                "relation_key": "missing-type",
                # Missing relation_type field
                "source_entity_id": e1,
                "target_entity_id": e2,
            }
        ]

        with pytest.raises(ValueError, match="relation_type"):
            infer_relation_type_schema(relations, entities, "relates_to")

    def test_mismatched_relation_type_rejected(self) -> None:
        """Relation with relation_type != target_type should raise error."""
        from llamaindex_runtime.schema_extraction import infer_relation_type_schema

        e1 = uuid.uuid4()
        e2 = uuid.uuid4()

        entities = [
            {"entity_id": e1, "entity_key": "concept:a", "entity_type": "concept"},
            {"entity_id": e2, "entity_key": "concept:b", "entity_type": "concept"},
        ]

        relations = [
            {
                "relation_id": uuid.uuid4(),
                "relation_key": "wrong-type",
                "relation_type": "affects",  # Not "relates_to"
                "source_entity_id": e1,
                "target_entity_id": e2,
            }
        ]

        with pytest.raises(ValueError, match="relation_type"):
            infer_relation_type_schema(relations, entities, "relates_to")

    def test_missing_entity_for_relation_raises_error(self) -> None:
        """Relation referencing missing entity should raise error."""
        from llamaindex_runtime.schema_extraction import infer_relation_type_schema

        e1 = uuid.uuid4()
        missing_entity = uuid.uuid4()

        entities = [
            {"entity_id": e1, "entity_key": "concept:a", "entity_type": "concept"},
            # Missing entity for missing_entity ID
        ]

        relations = [
            {
                "relation_id": uuid.uuid4(),
                "relation_key": "missing-source",
                "relation_type": "relates_to",
                "source_entity_id": missing_entity,
                "target_entity_id": e1,
            }
        ]

        with pytest.raises(ValueError, match="entity"):
            infer_relation_type_schema(relations, entities, "relates_to")

    def test_single_relation_infers_schema(self) -> None:
        """Schema can be inferred from a single relation."""
        from llamaindex_runtime.schema_extraction import infer_relation_type_schema

        e1 = uuid.uuid4()
        e2 = uuid.uuid4()

        entities = [
            {"entity_id": e1, "entity_key": "concept:a", "entity_type": "concept"},
            {"entity_id": e2, "entity_key": "metric:b", "entity_type": "metric"},
        ]

        relations = [
            {
                "relation_id": uuid.uuid4(),
                "relation_key": "affects-1",
                "relation_type": "affects",
                "source_entity_id": e1,
                "target_entity_id": e2,
            }
        ]

        schema = infer_relation_type_schema(relations, entities, "affects")

        assert schema.relation_type_name == "affects"
        assert schema.allowed_source_types == ["concept"]
        assert schema.allowed_target_types == ["metric"]