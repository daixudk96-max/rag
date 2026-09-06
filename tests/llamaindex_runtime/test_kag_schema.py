"""Tests for P4 KAG-style Schema/Constraint Layer.

These tests verify:
1. entity_type_schemas table exists with type name and constraints
2. relation_type_schemas table exists with type name and allowed source/target types
3. PostgresRegistryWriter validates entities against entity_type_schemas before persisting
4. PostgresRegistryWriter validates relations against relation_type_schemas before persisting
5. Schema definitions can be created, queried, and updated
6. Validation rejects invalid entity/relation types
7. Validation rejects invalid relation source/target type combinations
8. Backward compatibility: entities/relations without schema enforcement still work

Live tests require FORMAL_RUNTIME_DATABASE_URL to be set.
Unit tests run without a database.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from okf._e2a_pipeline_testkit import _FakeReconciler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_rich_pdf(pdf_path: Path, text_body: str = "default body") -> None:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (1200, 1600), "white")
    draw = ImageDraw.Draw(image)
    draw.text((80, 80), "Formal Runtime Heading", fill="black")
    draw.text((80, 180), text_body, fill="black")
    draw.text((80, 260), "Second paragraph for the formal runtime live ingestion test.", fill="black")
    image.save(pdf_path, "PDF")


# ===========================================================================
# UNIT TESTS -- Schema contract dataclasses (no database required)
# ===========================================================================


class TestEntityTypeSchemaContract:
    """EntityTypeSchema frozen dataclass: entity type definition with constraints."""

    def test_frozen_dataclass(self) -> None:
        """EntityTypeSchema must be frozen."""
        from llamaindex_runtime.registry.contracts import EntityTypeSchema

        schema = EntityTypeSchema(
            entity_type_name="concept",
            description="A conceptual entity",
            required_fields=["canonical_name"],
        )
        with pytest.raises(AttributeError):
            schema.entity_type_name = "modified"  # type: ignore[misc]

    def test_required_fields(self) -> None:
        """EntityTypeSchema must have entity_type_name field."""
        from llamaindex_runtime.registry.contracts import EntityTypeSchema

        schema = EntityTypeSchema(
            entity_type_name="concept",
            description="A conceptual entity",
        )
        assert schema.entity_type_name == "concept"

    def test_optional_fields_can_be_none(self) -> None:
        """EntityTypeSchema optional fields (description, constraints) can be None."""
        from llamaindex_runtime.registry.contracts import EntityTypeSchema

        schema = EntityTypeSchema(
            entity_type_name="concept",
            description=None,
            required_fields=None,
        )
        assert schema.description is None
        assert schema.required_fields is None


class TestRelationTypeSchemaContract:
    """RelationTypeSchema frozen dataclass: relation type definition with constraints."""

    def test_frozen_dataclass(self) -> None:
        """RelationTypeSchema must be frozen."""
        from llamaindex_runtime.registry.contracts import RelationTypeSchema

        schema = RelationTypeSchema(
            relation_type_name="affects",
            allowed_source_types=["concept"],
            allowed_target_types=["concept", "metric"],
        )
        with pytest.raises(AttributeError):
            schema.relation_type_name = "modified"  # type: ignore[misc]

    def test_required_fields(self) -> None:
        """RelationTypeSchema must have relation_type_name field."""
        from llamaindex_runtime.registry.contracts import RelationTypeSchema

        schema = RelationTypeSchema(
            relation_type_name="affects",
        )
        assert schema.relation_type_name == "affects"

    def test_optional_constraints_can_be_none(self) -> None:
        """RelationTypeSchema optional constraint fields can be None (no constraints)."""
        from llamaindex_runtime.registry.contracts import RelationTypeSchema

        schema = RelationTypeSchema(
            relation_type_name="relates_to",
            allowed_source_types=None,
            allowed_target_types=None,
        )
        assert schema.allowed_source_types is None
        assert schema.allowed_target_types is None


class TestKAGSolver:
    def test_solver_keeps_relations_matching_schema_constraints(self) -> None:
        from llamaindex_runtime.kag_solver import solve_relation_candidates

        source_id = uuid.uuid4()
        target_id = uuid.uuid4()
        entities = [
            {"entity_id": source_id, "entity_type": "concept"},
            {"entity_id": target_id, "entity_type": "metric"},
        ]
        candidates = [
            {
                "relation_id": uuid.uuid4(),
                "relation_type": "affects",
                "source_entity_id": source_id,
                "target_entity_id": target_id,
            }
        ]
        schemas = [
            {
                "relation_type_name": "affects",
                "allowed_source_types": ["concept"],
                "allowed_target_types": ["metric"],
            }
        ]

        assert solve_relation_candidates(candidates, entities, schemas) == candidates

    def test_solver_filters_relations_with_invalid_source_type(self) -> None:
        from llamaindex_runtime.kag_solver import solve_relation_candidates

        source_id = uuid.uuid4()
        target_id = uuid.uuid4()
        candidate = {
            "relation_id": uuid.uuid4(),
            "relation_type": "affects",
            "source_entity_id": source_id,
            "target_entity_id": target_id,
        }
        entities = [
            {"entity_id": source_id, "entity_type": "metric"},
            {"entity_id": target_id, "entity_type": "metric"},
        ]
        schemas = [
            {
                "relation_type_name": "affects",
                "allowed_source_types": ["concept"],
                "allowed_target_types": ["metric"],
            }
        ]

        assert solve_relation_candidates([candidate], entities, schemas) == []

    def test_solver_filters_relations_with_missing_entities(self) -> None:
        from llamaindex_runtime.kag_solver import solve_relation_candidates

        candidate = {
            "relation_id": uuid.uuid4(),
            "relation_type": "affects",
            "source_entity_id": uuid.uuid4(),
            "target_entity_id": uuid.uuid4(),
        }

        assert solve_relation_candidates([candidate], [], []) == []

    def test_solver_preserves_backward_compatible_relations_without_schema(self) -> None:
        from llamaindex_runtime.kag_solver import solve_relation_candidates

        source_id = uuid.uuid4()
        target_id = uuid.uuid4()
        candidate = {
            "relation_id": uuid.uuid4(),
            "relation_type": "legacy_relation",
            "source_entity_id": source_id,
            "target_entity_id": target_id,
        }
        entities = [
            {"entity_id": source_id, "entity_type": "legacy"},
            {"entity_id": target_id, "entity_type": "legacy"},
        ]

        assert solve_relation_candidates([candidate], entities, []) == [candidate]


# ===========================================================================
# LIVE TESTS -- require FORMAL_RUNTIME_DATABASE_URL
# ===========================================================================


class TestLiveKAGSchemaTables:
    """Verify that KAG schema tables exist with correct structure."""

    def test_entity_type_schemas_table_exists(
        self, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """entity_type_schemas table must exist."""
        with live_db_connection.cursor() as cur:
            cur.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = 'entity_type_schemas'"
            )
            row = cur.fetchone()
        assert row is not None, "entity_type_schemas table must exist"

    def test_relation_type_schemas_table_exists(
        self, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """relation_type_schemas table must exist."""
        with live_db_connection.cursor() as cur:
            cur.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = 'relation_type_schemas'"
            )
            row = cur.fetchone()
        assert row is not None, "relation_type_schemas table must exist"

    def test_entity_type_schemas_has_entity_type_name_column(
        self, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """entity_type_schemas must have entity_type_name column."""
        with live_db_connection.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'entity_type_schemas' AND column_name = 'entity_type_name'"
            )
            row = cur.fetchone()
        assert row is not None, "entity_type_schemas must have entity_type_name column"

    def test_relation_type_schemas_has_relation_type_name_column(
        self, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """relation_type_schemas must have relation_type_name column."""
        with live_db_connection.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'relation_type_schemas' AND column_name = 'relation_type_name'"
            )
            row = cur.fetchone()
        assert row is not None, "relation_type_schemas must have relation_type_name column"


class TestLiveKAGSchemaCRUD:
    """Live tests for KAG schema definition CRUD operations."""

    def _ingest_and_get_registry(
        self,
        live_db_connection,
        tmp_path: Path,
        title: str = "KAG schema test",
    ) -> tuple:
        """Helper: ingest a PDF and return (registry, version_id, span_ids)."""
        from llamaindex_runtime.ingestion import IngestionPipeline
        from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

        sample_pdf = tmp_path / f"{title.replace(' ', '-')}.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title=title)

        spans = registry.query_spans_by_version(result.version_id)
        return registry, result.version_id, spans

    def test_write_entity_type_schema_persists_schema(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """write_entity_type_schema must persist schema definition."""
        registry, version_id, spans = self._ingest_and_get_registry(
            live_db_connection, tmp_path, "KAG entity schema"
        )

        registry.write_entity_type_schema(
            schema={
                "entity_type_name": "concept",
                "description": "A conceptual entity",
                "required_fields": ["canonical_name"],
            }
        )

        persisted = registry.query_entity_type_schemas()
        match = [s for s in persisted if s["entity_type_name"] == "concept"]
        assert len(match) == 1
        assert match[0]["description"] == "A conceptual entity"
        assert match[0]["required_fields"] == ["canonical_name"]

    def test_write_relation_type_schema_persists_schema(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """write_relation_type_schema must persist schema definition."""
        registry, version_id, spans = self._ingest_and_get_registry(
            live_db_connection, tmp_path, "KAG relation schema"
        )

        registry.write_relation_type_schema(
            schema={
                "relation_type_name": "affects",
                "allowed_source_types": ["concept"],
                "allowed_target_types": ["concept", "metric"],
            }
        )

        persisted = registry.query_relation_type_schemas()
        match = [s for s in persisted if s["relation_type_name"] == "affects"]
        assert len(match) == 1
        assert match[0]["allowed_source_types"] == ["concept"]
        assert match[0]["allowed_target_types"] == ["concept", "metric"]

    def test_entity_type_schema_unique_enforced(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Inserting duplicate entity_type_name must be handled via ON CONFLICT."""
        registry, version_id, spans = self._ingest_and_get_registry(
            live_db_connection, tmp_path, "KAG schema unique"
        )

        # First insert
        registry.write_entity_type_schema(
            schema={
                "entity_type_name": "concept",
                "description": "First definition",
            }
        )

        # Second insert with same type_name should be idempotent (ON CONFLICT)
        registry.write_entity_type_schema(
            schema={
                "entity_type_name": "concept",
                "description": "Second definition",
            }
        )

        persisted = registry.query_entity_type_schemas()
        match = [s for s in persisted if s["entity_type_name"] == "concept"]
        # Should have exactly one entry (idempotent)
        assert len(match) == 1


class TestLiveKAGSchemaValidation:
    """Live tests for entity/relation validation against schemas."""

    def _setup_registry_with_schemas(
        self,
        live_db_connection,
        tmp_path: Path,
    ) -> tuple:
        """Helper: create registry and setup schemas for validation tests."""
        from llamaindex_runtime.ingestion import IngestionPipeline
        from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

        sample_pdf = tmp_path / "validation-test.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="KAG validation")

        # Setup schemas
        registry.write_entity_type_schema(
            schema={
                "entity_type_name": "concept",
                "description": "A conceptual entity",
                "required_fields": ["canonical_name"],
            }
        )
        registry.write_entity_type_schema(
            schema={
                "entity_type_name": "metric",
                "description": "A quantitative metric",
            }
        )
        registry.write_relation_type_schema(
            schema={
                "relation_type_name": "affects",
                "allowed_source_types": ["concept"],
                "allowed_target_types": ["concept", "metric"],
            }
        )

        spans = registry.query_spans_by_version(result.version_id)
        return registry, result.version_id, spans

    def test_entity_with_valid_type_and_required_fields_is_accepted(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Entity matching schema should be persisted successfully."""
        registry, version_id, spans = self._setup_registry_with_schemas(
            live_db_connection, tmp_path
        )

        entity_id = uuid.uuid4()
        registry.write_entities(
            entities=[
                {
                    "entity_id": entity_id,
                    "entity_key": "concept:pm25",
                    "entity_type": "concept",
                    "canonical_name": "PM2.5",  # Required by schema
                }
            ]
        )

        persisted = registry.query_entities()
        match = [e for e in persisted if e["entity_id"] == entity_id]
        assert len(match) == 1

    def test_entity_with_invalid_type_is_rejected(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Entity with entity_type not in schema should raise validation error."""
        registry, version_id, spans = self._setup_registry_with_schemas(
            live_db_connection, tmp_path
        )

        entity_id = uuid.uuid4()
        with pytest.raises(ValueError, match="entity_type"):
            registry.write_entities(
                entities=[
                    {
                        "entity_id": entity_id,
                        "entity_key": "invalid:foo",
                        "entity_type": "invalid_type",  # Not in schema
                        "canonical_name": "Foo",
                    }
                ]
            )

    def test_entity_missing_required_field_is_rejected(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Entity missing required field from schema should raise validation error."""
        registry, version_id, spans = self._setup_registry_with_schemas(
            live_db_connection, tmp_path
        )

        entity_id = uuid.uuid4()
        with pytest.raises(ValueError, match="required field"):
            registry.write_entities(
                entities=[
                    {
                        "entity_id": entity_id,
                        "entity_key": "concept:missing_field",
                        "entity_type": "concept",
                        # Missing canonical_name (required by schema)
                    }
                ]
            )

    def test_relation_with_valid_types_is_accepted(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Relation matching schema should be persisted successfully."""
        registry, version_id, spans = self._setup_registry_with_schemas(
            live_db_connection, tmp_path
        )

        e1 = uuid.uuid4()
        e2 = uuid.uuid4()
        registry.write_entities(
            entities=[
                {
                    "entity_id": e1,
                    "entity_key": "concept:pm25",
                    "entity_type": "concept",
                    "canonical_name": "PM2.5",
                },
                {
                    "entity_id": e2,
                    "entity_key": "metric:aqi",
                    "entity_type": "metric",
                },
            ]
        )

        rel_id = uuid.uuid4()
        registry.write_relations(
            relations=[
                {
                    "relation_id": rel_id,
                    "relation_key": "pm25-affects-aqi",
                    "relation_type": "affects",
                    "source_entity_id": e1,
                    "target_entity_id": e2,
                }
            ]
        )

        persisted = registry.query_relations()
        match = [r for r in persisted if r["relation_id"] == rel_id]
        assert len(match) == 1

    def test_relation_with_invalid_source_type_is_rejected(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Relation with source entity type not allowed by schema should raise."""
        registry, version_id, spans = self._setup_registry_with_schemas(
            live_db_connection, tmp_path
        )

        e1 = uuid.uuid4()
        e2 = uuid.uuid4()
        registry.write_entities(
            entities=[
                {
                    "entity_id": e1,
                    "entity_key": "metric:pm25",
                    "entity_type": "metric",  # Not allowed as source by "affects" schema
                },
                {
                    "entity_id": e2,
                    "entity_key": "concept:aqi",
                    "entity_type": "concept",
                    "canonical_name": "AQI",
                },
            ]
        )

        rel_id = uuid.uuid4()
        with pytest.raises(ValueError, match="source entity type"):
            registry.write_relations(
                relations=[
                    {
                        "relation_id": rel_id,
                        "relation_key": "invalid-source",
                        "relation_type": "affects",
                        "source_entity_id": e1,
                        "target_entity_id": e2,
                    }
                ]
            )

    def test_relation_with_invalid_target_type_is_rejected(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Relation with target entity type not allowed by schema should raise."""
        registry, version_id, spans = self._setup_registry_with_schemas(
            live_db_connection, tmp_path
        )

        e1 = uuid.uuid4()
        e2 = uuid.uuid4()
        registry.write_entities(
            entities=[
                {
                    "entity_id": e1,
                    "entity_key": "concept:pm25",
                    "entity_type": "concept",
                    "canonical_name": "PM2.5",
                },
                {
                    "entity_id": e2,
                    "entity_key": "person:john",
                    "entity_type": "person",  # Not in allowed_target_types
                },
            ]
        )

        rel_id = uuid.uuid4()
        with pytest.raises(ValueError, match="target entity type"):
            registry.write_relations(
                relations=[
                    {
                        "relation_id": rel_id,
                        "relation_key": "invalid-target",
                        "relation_type": "affects",
                        "source_entity_id": e1,
                        "target_entity_id": e2,
                    }
                ]
            )

    def test_relation_with_missing_source_entity_is_rejected(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Relation referencing a non-existent source entity should raise."""
        registry, version_id, spans = self._setup_registry_with_schemas(
            live_db_connection, tmp_path
        )

        existing_target = uuid.uuid4()
        missing_source = uuid.uuid4()
        registry.write_entities(
            entities=[
                {
                    "entity_id": existing_target,
                    "entity_key": "concept:aqi",
                    "entity_type": "concept",
                    "canonical_name": "AQI",
                }
            ]
        )

        with pytest.raises(ValueError, match="source entity"):
            registry.write_relations(
                relations=[
                    {
                        "relation_id": uuid.uuid4(),
                        "relation_key": "missing-source",
                        "relation_type": "affects",
                        "source_entity_id": missing_source,
                        "target_entity_id": existing_target,
                    }
                ]
            )

    def test_relation_with_missing_target_entity_is_rejected(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Relation referencing a non-existent target entity should raise."""
        registry, version_id, spans = self._setup_registry_with_schemas(
            live_db_connection, tmp_path
        )

        existing_source = uuid.uuid4()
        missing_target = uuid.uuid4()
        registry.write_entities(
            entities=[
                {
                    "entity_id": existing_source,
                    "entity_key": "concept:pm25",
                    "entity_type": "concept",
                    "canonical_name": "PM2.5",
                }
            ]
        )

        with pytest.raises(ValueError, match="target entity"):
            registry.write_relations(
                relations=[
                    {
                        "relation_id": uuid.uuid4(),
                        "relation_key": "missing-target",
                        "relation_type": "affects",
                        "source_entity_id": existing_source,
                        "target_entity_id": missing_target,
                    }
                ]
            )


class TestBackwardCompatibilityWithKAG:
    """Backward compatibility: entities/relations without schema enforcement."""

    def test_entity_without_schema_validation_still_works(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Entities can still be persisted without schema defined (backward compat)."""
        from llamaindex_runtime.ingestion import IngestionPipeline
        from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

        sample_pdf = tmp_path / "backward-compat-entity.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Backward compat entity")

        # No schema defined for "legacy_type"
        entity_id = uuid.uuid4()
        registry.write_entities(
            entities=[
                {
                    "entity_id": entity_id,
                    "entity_key": "legacy:foo",
                    "entity_type": "legacy_type",
                }
            ]
        )

        persisted = registry.query_entities()
        match = [e for e in persisted if e["entity_id"] == entity_id]
        assert len(match) == 1

    def test_relation_without_schema_validation_still_works(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Relations can still be persisted without schema defined (backward compat)."""
        from llamaindex_runtime.ingestion import IngestionPipeline
        from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

        sample_pdf = tmp_path / "backward-compat-rel.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Backward compat relation")

        e1 = uuid.uuid4()
        e2 = uuid.uuid4()
        registry.write_entities(
            entities=[
                {
                    "entity_id": e1,
                    "entity_key": "legacy:a",
                    "entity_type": "legacy_a",
                },
                {
                    "entity_id": e2,
                    "entity_key": "legacy:b",
                    "entity_type": "legacy_b",
                },
            ]
        )

        # No schema defined for "legacy_relation"
        rel_id = uuid.uuid4()
        registry.write_relations(
            relations=[
                {
                    "relation_id": rel_id,
                    "relation_key": "legacy-rel",
                    "relation_type": "legacy_relation",
                    "source_entity_id": e1,
                    "target_entity_id": e2,
                }
            ]
        )

        persisted = registry.query_relations()
        match = [r for r in persisted if r["relation_id"] == rel_id]
        assert len(match) == 1