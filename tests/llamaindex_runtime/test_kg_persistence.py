"""Tests for Phase 5 Slice: KG (Knowledge Graph) Registry Layer.

These tests verify:
1. KG tables exist: entities, relations, evidence_links, chunk_entity_links, node_entity_links
2. evidence_links references span_id (not chunk_id) as the provenance anchor
3. Bridge tables chunk_entity_links and node_entity_links provide chunk/entity and node/entity links
4. PostgresRegistryWriter KG methods persist and query correctly
5. Cascade deletes propagate through KG tables
6. Edge cases: null optional fields, batch validation, idempotency

Live tests require FORMAL_RUNTIME_DATABASE_URL to be set.
Unit tests run without a database.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock

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
# UNIT TESTS -- KG contract dataclasses (no database required)
# ===========================================================================


class TestEntityContract:
    """Entity frozen dataclass: required and optional fields, immutability."""

    def test_frozen_dataclass(self) -> None:
        from llamaindex_runtime.registry.contracts import Entity

        entity = Entity(
            entity_id=uuid.uuid4(),
            entity_key="concept:pm25",
            entity_type="concept",
            canonical_name="PM2.5",
        )
        with pytest.raises(AttributeError):
            entity.entity_key = "modified"  # type: ignore[misc]

    def test_required_fields(self) -> None:
        from llamaindex_runtime.registry.contracts import Entity

        entity = Entity(
            entity_id=uuid.uuid4(),
            entity_key="concept:pm25",
            entity_type="concept",
            canonical_name="PM2.5",
        )
        assert isinstance(entity.entity_id, uuid.UUID)
        assert entity.entity_key == "concept:pm25"

    def test_optional_fields_can_be_none(self) -> None:
        from llamaindex_runtime.registry.contracts import Entity

        entity = Entity(
            entity_id=uuid.uuid4(),
            entity_key="concept:pm25",
            entity_type=None,
            canonical_name=None,
        )
        assert entity.entity_type is None
        assert entity.canonical_name is None


class TestRelationContract:
    """Relation frozen dataclass: required fields, immutability."""

    def test_frozen_dataclass(self) -> None:
        from llamaindex_runtime.registry.contracts import Relation

        rel = Relation(
            relation_id=uuid.uuid4(),
            relation_key="pm25-affects-aq",
            relation_type="affects",
            source_entity_id=uuid.uuid4(),
            target_entity_id=uuid.uuid4(),
        )
        with pytest.raises(AttributeError):
            rel.relation_type = "modified"  # type: ignore[misc]

    def test_required_fields(self) -> None:
        from llamaindex_runtime.registry.contracts import Relation

        src = uuid.uuid4()
        tgt = uuid.uuid4()
        rel = Relation(
            relation_id=uuid.uuid4(),
            relation_key="pm25-affects-aq",
            relation_type="affects",
            source_entity_id=src,
            target_entity_id=tgt,
        )
        assert isinstance(rel.relation_id, uuid.UUID)
        assert rel.source_entity_id == src
        assert rel.target_entity_id == tgt


class TestEvidenceLinkContract:
    """EvidenceLink frozen dataclass: span_id (not chunk_id), entity_id or relation_id required."""

    def test_frozen_dataclass(self) -> None:
        from llamaindex_runtime.registry.contracts import EvidenceLink

        link = EvidenceLink(
            evidence_link_id=uuid.uuid4(),
            version_id=uuid.uuid4(),
            entity_id=uuid.uuid4(),
            relation_id=None,
            span_id=uuid.uuid4(),
            source_kind="ner",
            confidence_score=0.9,
        )
        with pytest.raises(AttributeError):
            link.source_kind = "modified"  # type: ignore[misc]

    def test_span_id_field_exists_not_chunk_id(self) -> None:
        """EvidenceLink must have span_id, not chunk_id."""
        from llamaindex_runtime.registry.contracts import EvidenceLink

        link = EvidenceLink(
            evidence_link_id=uuid.uuid4(),
            version_id=uuid.uuid4(),
            entity_id=uuid.uuid4(),
            relation_id=None,
            span_id=uuid.uuid4(),
            source_kind="ner",
            confidence_score=None,
        )
        assert hasattr(link, "span_id")
        assert not hasattr(link, "chunk_id"), "EvidenceLink must not have chunk_id field"

    def test_entity_id_or_relation_id_required(self) -> None:
        """At least one of entity_id or relation_id must be set."""
        from llamaindex_runtime.registry.contracts import EvidenceLink

        # Both entity_id and relation_id is None should raise
        with pytest.raises((ValueError, TypeError)):
            EvidenceLink(
                evidence_link_id=uuid.uuid4(),
                version_id=uuid.uuid4(),
                entity_id=None,
                relation_id=None,
                span_id=uuid.uuid4(),
                source_kind="ner",
                confidence_score=None,
            )

    def test_confidence_score_optional(self) -> None:
        from llamaindex_runtime.registry.contracts import EvidenceLink

        link = EvidenceLink(
            evidence_link_id=uuid.uuid4(),
            version_id=uuid.uuid4(),
            entity_id=uuid.uuid4(),
            relation_id=None,
            span_id=uuid.uuid4(),
            source_kind="ner",
            confidence_score=None,
        )
        assert link.confidence_score is None


class TestChunkEntityLinkContract:
    """ChunkEntityLink frozen dataclass: chunk_id + entity_id bridge."""

    def test_frozen_dataclass(self) -> None:
        from llamaindex_runtime.registry.contracts import ChunkEntityLink

        link = ChunkEntityLink(
            chunk_id=uuid.uuid4(),
            entity_id=uuid.uuid4(),
            ordinal_no=0,
        )
        with pytest.raises(AttributeError):
            link.ordinal_no = 5  # type: ignore[misc]

    def test_required_fields(self) -> None:
        from llamaindex_runtime.registry.contracts import ChunkEntityLink

        cid = uuid.uuid4()
        eid = uuid.uuid4()
        link = ChunkEntityLink(chunk_id=cid, entity_id=eid, ordinal_no=3)
        assert isinstance(link.chunk_id, uuid.UUID)
        assert isinstance(link.entity_id, uuid.UUID)
        assert link.ordinal_no == 3

    def test_optional_graph_mapping_fields(self) -> None:
        from llamaindex_runtime.registry.contracts import ChunkEntityLink

        cid = uuid.uuid4()
        eid = uuid.uuid4()
        link = ChunkEntityLink(
            chunk_id=cid,
            entity_id=eid,
            ordinal_no=3,
            confidence_score=0.95,
            mention_text="PM2.5",
        )
        assert link.confidence_score == pytest.approx(0.95)
        assert link.mention_text == "PM2.5"

    def test_optional_graph_mapping_fields_can_be_none(self) -> None:
        from llamaindex_runtime.registry.contracts import ChunkEntityLink

        link = ChunkEntityLink(
            chunk_id=uuid.uuid4(),
            entity_id=uuid.uuid4(),
            ordinal_no=0,
            confidence_score=None,
            mention_text=None,
        )
        assert link.confidence_score is None
        assert link.mention_text is None


class TestNodeEntityLinkContract:
    """NodeEntityLink frozen dataclass: node_id + entity_id bridge."""

    def test_frozen_dataclass(self) -> None:
        from llamaindex_runtime.registry.contracts import NodeEntityLink

        link = NodeEntityLink(
            node_id=uuid.uuid4(),
            entity_id=uuid.uuid4(),
            ordinal_no=0,
        )
        with pytest.raises(AttributeError):
            link.ordinal_no = 5  # type: ignore[misc]

    def test_required_fields(self) -> None:
        from llamaindex_runtime.registry.contracts import NodeEntityLink

        nid = uuid.uuid4()
        eid = uuid.uuid4()
        link = NodeEntityLink(node_id=nid, entity_id=eid, ordinal_no=2)
        assert isinstance(link.node_id, uuid.UUID)
        assert isinstance(link.entity_id, uuid.UUID)
        assert link.ordinal_no == 2

    def test_optional_graph_mapping_fields(self) -> None:
        from llamaindex_runtime.registry.contracts import NodeEntityLink

        nid = uuid.uuid4()
        eid = uuid.uuid4()
        link = NodeEntityLink(
            node_id=nid,
            entity_id=eid,
            ordinal_no=2,
            confidence_score=0.87,
            mention_text="Air Quality",
        )
        assert link.confidence_score == pytest.approx(0.87)
        assert link.mention_text == "Air Quality"

    def test_optional_graph_mapping_fields_can_be_none(self) -> None:
        from llamaindex_runtime.registry.contracts import NodeEntityLink

        link = NodeEntityLink(
            node_id=uuid.uuid4(),
            entity_id=uuid.uuid4(),
            ordinal_no=0,
            confidence_score=None,
            mention_text=None,
        )
        assert link.confidence_score is None
        assert link.mention_text is None


class TestMutualIndexingQueries:
    def test_query_chunks_by_entity_returns_chunk_rows(self) -> None:
        from unittest.mock import patch
        from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

        entity_id = uuid.uuid4()
        chunk_id = uuid.uuid4()
        version_id = uuid.uuid4()

        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.__exit__.return_value = False
        cursor.fetchall.return_value = [
            {
                "chunk_id": str(chunk_id),
                "entity_id": str(entity_id),
                "ordinal_no": 0,
                "confidence_score": 0.9,
                "mention_text": "PM2.5",
                "version_id": str(version_id),
            }
        ]

        connection = MagicMock()
        connection.autocommit = False  # Required by PostgresRegistryWriter.__init__
        connection.cursor.return_value = cursor

        # Patch register_vector to bypass psycopg type checking
        with patch('llamaindex_runtime.registry.postgres_adapter.register_vector'):
            registry = PostgresRegistryWriter(connection)
            result = registry.query_chunks_by_entity(entity_id)

            assert result == [
                {
                    "chunk_id": chunk_id,
                    "entity_id": entity_id,
                    "ordinal_no": 0,
                    "confidence_score": 0.9,
                    "mention_text": "PM2.5",
                    "version_id": version_id,
                }
            ]

    def test_query_entities_by_chunk_returns_entity_rows(self) -> None:
        from unittest.mock import patch
        from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

        entity_id = uuid.uuid4()
        chunk_id = uuid.uuid4()

        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.__exit__.return_value = False
        cursor.fetchall.return_value = [
            {
                "chunk_id": str(chunk_id),
                "entity_id": str(entity_id),
                "ordinal_no": 1,
                "confidence_score": None,
                "mention_text": None,
            }
        ]

        connection = MagicMock()
        connection.autocommit = False  # Required by PostgresRegistryWriter.__init__
        connection.cursor.return_value = cursor

        # Patch register_vector to bypass psycopg type checking
        with patch('llamaindex_runtime.registry.postgres_adapter.register_vector'):
            registry = PostgresRegistryWriter(connection)
            result = registry.query_entities_by_chunk(chunk_id)

            assert result == [
                {
                    "chunk_id": chunk_id,
                    "entity_id": entity_id,
                    "ordinal_no": 1,
                    "confidence_score": None,
                    "mention_text": None,
                }
            ]

    def test_query_nodes_by_entity_returns_node_rows(self) -> None:
        from unittest.mock import patch
        from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

        entity_id = uuid.uuid4()
        node_id = uuid.uuid4()
        version_id = uuid.uuid4()

        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.__exit__.return_value = False
        cursor.fetchall.return_value = [
            {
                "node_id": str(node_id),
                "entity_id": str(entity_id),
                "ordinal_no": 0,
                "confidence_score": 0.4,
                "mention_text": "Air Quality",
                "version_id": str(version_id),
            }
        ]

        connection = MagicMock()
        connection.autocommit = False  # Required by PostgresRegistryWriter.__init__
        connection.cursor.return_value = cursor

        # Patch register_vector to bypass psycopg type checking
        with patch('llamaindex_runtime.registry.postgres_adapter.register_vector'):
            registry = PostgresRegistryWriter(connection)
            result = registry.query_nodes_by_entity(entity_id)

            assert result == [
                {
                    "node_id": node_id,
                    "entity_id": entity_id,
                    "ordinal_no": 0,
                    "confidence_score": 0.4,
                    "mention_text": "Air Quality",
                    "version_id": version_id,
                }
            ]

    def test_query_entities_by_node_returns_entity_rows(self) -> None:
        from unittest.mock import patch
        from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

        entity_id = uuid.uuid4()
        node_id = uuid.uuid4()

        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.__exit__.return_value = False
        cursor.fetchall.return_value = [
            {
                "node_id": str(node_id),
                "entity_id": str(entity_id),
                "ordinal_no": 1,
                "confidence_score": None,
                "mention_text": None,
            }
        ]

        connection = MagicMock()
        connection.autocommit = False  # Required by PostgresRegistryWriter.__init__
        connection.cursor.return_value = cursor

        # Patch register_vector to bypass psycopg type checking
        with patch('llamaindex_runtime.registry.postgres_adapter.register_vector'):
            registry = PostgresRegistryWriter(connection)
            result = registry.query_entities_by_node(node_id)

            assert result == [
                {
                    "node_id": node_id,
                    "entity_id": entity_id,
                    "ordinal_no": 1,
                    "confidence_score": None,
                    "mention_text": None,
                }
            ]


# ===========================================================================
# LIVE TESTS -- require FORMAL_RUNTIME_DATABASE_URL
# ===========================================================================


class TestLiveKGSchema:
    """Verify that all KG tables exist with correct structure."""

    def test_entities_table_exists(self, live_db_connection, live_applied_schema, clean_live_db) -> None:
        with live_db_connection.cursor() as cur:
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = 'entities'")
            row = cur.fetchone()
        assert row is not None, "entities table must exist"

    def test_relations_table_exists(self, live_db_connection, live_applied_schema, clean_live_db) -> None:
        with live_db_connection.cursor() as cur:
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = 'relations'")
            row = cur.fetchone()
        assert row is not None, "relations table must exist"

    def test_evidence_links_table_exists(self, live_db_connection, live_applied_schema, clean_live_db) -> None:
        with live_db_connection.cursor() as cur:
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = 'evidence_links'")
            row = cur.fetchone()
        assert row is not None, "evidence_links table must exist"

    def test_chunk_entity_links_table_exists(self, live_db_connection, live_applied_schema, clean_live_db) -> None:
        with live_db_connection.cursor() as cur:
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = 'chunk_entity_links'")
            row = cur.fetchone()
        assert row is not None, "chunk_entity_links table must exist"

    def test_node_entity_links_table_exists(self, live_db_connection, live_applied_schema, clean_live_db) -> None:
        with live_db_connection.cursor() as cur:
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = 'node_entity_links'")
            row = cur.fetchone()
        assert row is not None, "node_entity_links table must exist"

    def test_chunk_entity_links_has_confidence_score_column(
        self, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        with live_db_connection.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'chunk_entity_links' AND column_name = 'confidence_score'"
            )
            row = cur.fetchone()
        assert row is not None, "chunk_entity_links must have confidence_score column"

    def test_chunk_entity_links_has_mention_text_column(
        self, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        with live_db_connection.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'chunk_entity_links' AND column_name = 'mention_text'"
            )
            row = cur.fetchone()
        assert row is not None, "chunk_entity_links must have mention_text column"

    def test_node_entity_links_has_confidence_score_column(
        self, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        with live_db_connection.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'node_entity_links' AND column_name = 'confidence_score'"
            )
            row = cur.fetchone()
        assert row is not None, "node_entity_links must have confidence_score column"

    def test_node_entity_links_has_mention_text_column(
        self, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        with live_db_connection.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'node_entity_links' AND column_name = 'mention_text'"
            )
            row = cur.fetchone()
        assert row is not None, "node_entity_links must have mention_text column"

    def test_evidence_links_has_span_id_column(self, live_db_connection, live_applied_schema, clean_live_db) -> None:
        """evidence_links must have a span_id column referencing canonical_spans."""
        with live_db_connection.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'evidence_links' AND column_name = 'span_id'"
            )
            row = cur.fetchone()
        assert row is not None, "evidence_links must have span_id column"

    def test_evidence_links_has_no_chunk_id_column(self, live_db_connection, live_applied_schema, clean_live_db) -> None:
        """evidence_links must NOT have a chunk_id column -- evidence anchors on span_id."""
        with live_db_connection.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'evidence_links' AND column_name = 'chunk_id'"
            )
            row = cur.fetchone()
        assert row is None, "evidence_links must NOT have chunk_id column; evidence anchors on span_id"

    def test_evidence_links_span_id_fk_to_canonical_spans(self, live_db_connection, live_applied_schema, clean_live_db) -> None:
        """evidence_links.span_id must be a FK referencing canonical_spans(span_id)."""
        with live_db_connection.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM information_schema.key_column_usage kcu
                JOIN information_schema.table_constraints tc
                    ON kcu.constraint_name = tc.constraint_name AND kcu.table_schema = tc.table_schema
                WHERE kcu.table_name = 'evidence_links'
                    AND kcu.column_name = 'span_id'
                    AND tc.constraint_type = 'FOREIGN KEY'
                """
            )
            row = cur.fetchone()
        assert row is not None, "evidence_links.span_id must have a FOREIGN KEY constraint"

    def test_chunk_entity_links_has_chunk_id_fk(self, live_db_connection, live_applied_schema, clean_live_db) -> None:
        """chunk_entity_links.chunk_id must reference vector_chunks(chunk_id)."""
        with live_db_connection.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM information_schema.key_column_usage kcu
                JOIN information_schema.table_constraints tc
                    ON kcu.constraint_name = tc.constraint_name AND kcu.table_schema = tc.table_schema
                WHERE kcu.table_name = 'chunk_entity_links'
                    AND kcu.column_name = 'chunk_id'
                    AND tc.constraint_type = 'FOREIGN KEY'
                """
            )
            row = cur.fetchone()
        assert row is not None, "chunk_entity_links.chunk_id must have a FOREIGN KEY constraint"

    def test_chunk_entity_links_has_entity_id_fk(self, live_db_connection, live_applied_schema, clean_live_db) -> None:
        """chunk_entity_links.entity_id must reference entities(entity_id)."""
        with live_db_connection.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM information_schema.key_column_usage kcu
                JOIN information_schema.table_constraints tc
                    ON kcu.constraint_name = tc.constraint_name AND kcu.table_schema = tc.table_schema
                WHERE kcu.table_name = 'chunk_entity_links'
                    AND kcu.column_name = 'entity_id'
                    AND tc.constraint_type = 'FOREIGN KEY'
                """
            )
            row = cur.fetchone()
        assert row is not None, "chunk_entity_links.entity_id must have a FOREIGN KEY constraint"

    def test_node_entity_links_has_node_id_fk(self, live_db_connection, live_applied_schema, clean_live_db) -> None:
        """node_entity_links.node_id must reference tree_nodes(node_id)."""
        with live_db_connection.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM information_schema.key_column_usage kcu
                JOIN information_schema.table_constraints tc
                    ON kcu.constraint_name = tc.constraint_name AND kcu.table_schema = tc.table_schema
                WHERE kcu.table_name = 'node_entity_links'
                    AND kcu.column_name = 'node_id'
                    AND tc.constraint_type = 'FOREIGN KEY'
                """
            )
            row = cur.fetchone()
        assert row is not None, "node_entity_links.node_id must have a FOREIGN KEY constraint"

    def test_node_entity_links_has_entity_id_fk(self, live_db_connection, live_applied_schema, clean_live_db) -> None:
        """node_entity_links.entity_id must reference entities(entity_id)."""
        with live_db_connection.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM information_schema.key_column_usage kcu
                JOIN information_schema.table_constraints tc
                    ON kcu.constraint_name = tc.constraint_name AND kcu.table_schema = tc.table_schema
                WHERE kcu.table_name = 'node_entity_links'
                    AND kcu.column_name = 'entity_id'
                    AND tc.constraint_type = 'FOREIGN KEY'
                """
            )
            row = cur.fetchone()
        assert row is not None, "node_entity_links.entity_id must have a FOREIGN KEY constraint"


class TestLiveKGCrd:
    """Live tests for KG CRUD operations via PostgresRegistryWriter."""

    def _ingest_and_get_registry(
        self,
        live_db_connection,
        tmp_path: Path,
        title: str = "KG test",
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

    def test_write_entities_persists_entities(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """write_entities must persist entity rows."""
        registry, version_id, spans = self._ingest_and_get_registry(live_db_connection, tmp_path, "KG entity persist")

        entity_id = uuid.uuid4()
        registry.write_entities(
            entities=[
                {
                    "entity_id": entity_id,
                    "entity_key": "concept:pm25",
                    "entity_type": "concept",
                    "canonical_name": "PM2.5",
                }
            ]
        )

        persisted = registry.query_entities()
        assert len(persisted) >= 1
        match = [e for e in persisted if e["entity_id"] == entity_id]
        assert len(match) == 1
        assert match[0]["entity_key"] == "concept:pm25"
        assert match[0]["canonical_name"] == "PM2.5"

    def test_write_relations_persists_relations(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """write_relations must persist relation rows between entities."""
        registry, version_id, spans = self._ingest_and_get_registry(live_db_connection, tmp_path, "KG relation persist")

        e1 = uuid.uuid4()
        e2 = uuid.uuid4()
        rel_id = uuid.uuid4()
        registry.write_entities(
            entities=[
                {"entity_id": e1, "entity_key": "concept:pm25", "entity_type": "concept", "canonical_name": "PM2.5"},
                {"entity_id": e2, "entity_key": "concept:aqi", "entity_type": "concept", "canonical_name": "AQI"},
            ]
        )
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
        assert match[0]["relation_type"] == "affects"
        assert match[0]["source_entity_id"] == e1
        assert match[0]["target_entity_id"] == e2

    def test_write_evidence_links_persists_span_id_links(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """write_evidence_links must persist evidence_links anchored on span_id."""
        registry, version_id, spans = self._ingest_and_get_registry(live_db_connection, tmp_path, "KG evidence link")

        entity_id = uuid.uuid4()
        registry.write_entities(
            entities=[
                {"entity_id": entity_id, "entity_key": "concept:pm25", "entity_type": "concept", "canonical_name": "PM2.5"},
            ]
        )

        span_id = spans[0]["span_id"]
        registry.write_evidence_links(
            version_id=version_id,
            evidence_links=[
                {
                    "entity_id": entity_id,
                    "relation_id": None,
                    "span_id": span_id,
                    "source_kind": "ner",
                    "confidence_score": 0.85,
                }
            ],
        )

        persisted = registry.query_evidence_links_by_version(version_id)
        assert len(persisted) >= 1
        match = [el for el in persisted if el["span_id"] == span_id and el["entity_id"] == entity_id]
        assert len(match) == 1
        assert match[0]["source_kind"] == "ner"
        assert abs(match[0]["confidence_score"] - 0.85) < 1e-6

    def test_evidence_link_with_relation_id(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """write_evidence_links must persist links that reference relation_id instead of entity_id."""
        registry, version_id, spans = self._ingest_and_get_registry(live_db_connection, tmp_path, "KG evidence rel")

        e1 = uuid.uuid4()
        e2 = uuid.uuid4()
        rel_id = uuid.uuid4()
        registry.write_entities(
            entities=[
                {"entity_id": e1, "entity_key": "concept:pm25", "entity_type": "concept", "canonical_name": "PM2.5"},
                {"entity_id": e2, "entity_key": "concept:aqi", "entity_type": "concept", "canonical_name": "AQI"},
            ]
        )
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

        span_id = spans[0]["span_id"]
        registry.write_evidence_links(
            version_id=version_id,
            evidence_links=[
                {
                    "entity_id": None,
                    "relation_id": rel_id,
                    "span_id": span_id,
                    "source_kind": "manual",
                    "confidence_score": None,
                }
            ],
        )

        persisted = registry.query_evidence_links_by_version(version_id)
        match = [el for el in persisted if el["relation_id"] == rel_id]
        assert len(match) == 1
        assert match[0]["entity_id"] is None
        assert match[0]["confidence_score"] is None

    def test_evidence_link_rejects_both_null_entity_and_relation(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """evidence_links with both entity_id and relation_id NULL must be rejected by the DB CHECK constraint."""
        registry, version_id, spans = self._ingest_and_get_registry(live_db_connection, tmp_path, "KG evidence null")

        span_id = spans[0]["span_id"]
        with pytest.raises(Exception):
            registry.write_evidence_links(
                version_id=version_id,
                evidence_links=[
                    {
                        "entity_id": None,
                        "relation_id": None,
                        "span_id": span_id,
                        "source_kind": "ner",
                        "confidence_score": None,
                    }
                ],
            )

    def test_write_chunk_entity_links(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """write_chunk_entity_links must persist chunk -> entity bridge rows."""
        from llamaindex_runtime.vector.chunker import SimpleSpanChunker

        registry, version_id, spans = self._ingest_and_get_registry(live_db_connection, tmp_path, "KG chunk entity")

        # Create chunks
        chunker = SimpleSpanChunker()
        chunks = chunker.generate(spans, version_id=version_id)
        registry.write_vector_chunks(version_id=version_id, chunks=chunks)

        # Create entity
        entity_id = uuid.uuid4()
        registry.write_entities(
            entities=[
                {"entity_id": entity_id, "entity_key": "concept:pm25", "entity_type": "concept", "canonical_name": "PM2.5"},
            ]
        )

        # Link chunk to entity
        chunk_id = chunks[0]["chunk_id"]
        registry.write_chunk_entity_links(
            version_id=version_id,
            links=[
                {"chunk_id": chunk_id, "entity_id": entity_id, "ordinal_no": 0},
            ],
        )

        persisted = registry.query_chunk_entity_links_by_version(version_id)
        match = [l for l in persisted if l["chunk_id"] == chunk_id and l["entity_id"] == entity_id]
        assert len(match) == 1
        assert match[0]["ordinal_no"] == 0

    def test_write_node_entity_links(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """write_node_entity_links must persist node -> entity bridge rows."""
        from llamaindex_runtime.registry.tree_generator import TreeGenerator

        registry, version_id, spans = self._ingest_and_get_registry(live_db_connection, tmp_path, "KG node entity")

        # Create tree
        tree = TreeGenerator().generate(spans, version_id=version_id)
        registry.write_tree(version_id=version_id, nodes=tree["nodes"], node_spans=tree["node_spans"])

        # Create entity
        entity_id = uuid.uuid4()
        registry.write_entities(
            entities=[
                {"entity_id": entity_id, "entity_key": "concept:aq", "entity_type": "concept", "canonical_name": "Air Quality"},
            ]
        )

        # Link tree node to entity
        node_id = tree["nodes"][0]["node_id"]
        registry.write_node_entity_links(
            version_id=version_id,
            links=[
                {"node_id": node_id, "entity_id": entity_id, "ordinal_no": 0},
            ],
        )

        persisted = registry.query_node_entity_links_by_version(version_id)
        match = [l for l in persisted if l["node_id"] == node_id and l["entity_id"] == entity_id]
        assert len(match) == 1
        assert match[0]["ordinal_no"] == 0

    def test_write_chunk_entity_links_persists_optional_fields(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """write_chunk_entity_links must persist optional GraphRAG mapping fields."""
        from llamaindex_runtime.vector.chunker import SimpleSpanChunker

        registry, version_id, spans = self._ingest_and_get_registry(live_db_connection, tmp_path, "KG chunk mapping fields")

        chunker = SimpleSpanChunker()
        chunks = chunker.generate(spans, version_id=version_id)
        registry.write_vector_chunks(version_id=version_id, chunks=chunks)

        entity_id = uuid.uuid4()
        registry.write_entities(
            entities=[
                {"entity_id": entity_id, "entity_key": "concept:pm25-map", "entity_type": "concept", "canonical_name": "PM2.5 Map"},
            ]
        )

        chunk_id = chunks[0]["chunk_id"]
        registry.write_chunk_entity_links(
            version_id=version_id,
            links=[
                {
                    "chunk_id": chunk_id,
                    "entity_id": entity_id,
                    "ordinal_no": 0,
                    "confidence_score": 0.95,
                    "mention_text": "PM2.5",
                },
            ],
        )

        persisted = registry.query_chunk_entity_links_by_version(version_id)
        match = [l for l in persisted if l["chunk_id"] == chunk_id and l["entity_id"] == entity_id]
        assert len(match) == 1
        assert match[0]["confidence_score"] == pytest.approx(0.95)
        assert match[0]["mention_text"] == "PM2.5"

    def test_write_node_entity_links_persists_optional_fields(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """write_node_entity_links must persist optional GraphRAG mapping fields."""
        from llamaindex_runtime.registry.tree_generator import TreeGenerator

        registry, version_id, spans = self._ingest_and_get_registry(live_db_connection, tmp_path, "KG node mapping fields")

        tree = TreeGenerator().generate(spans, version_id=version_id)
        registry.write_tree(version_id=version_id, nodes=tree["nodes"], node_spans=tree["node_spans"])

        entity_id = uuid.uuid4()
        registry.write_entities(
            entities=[
                {"entity_id": entity_id, "entity_key": "concept:aq-map", "entity_type": "concept", "canonical_name": "Air Quality Map"},
            ]
        )

        node_id = tree["nodes"][0]["node_id"]
        registry.write_node_entity_links(
            version_id=version_id,
            links=[
                {
                    "node_id": node_id,
                    "entity_id": entity_id,
                    "ordinal_no": 0,
                    "confidence_score": 0.87,
                    "mention_text": "Air Quality",
                },
            ],
        )

        persisted = registry.query_node_entity_links_by_version(version_id)
        match = [l for l in persisted if l["node_id"] == node_id and l["entity_id"] == entity_id]
        assert len(match) == 1
        assert match[0]["confidence_score"] == pytest.approx(0.87)
        assert match[0]["mention_text"] == "Air Quality"

    def test_write_chunk_entity_links_without_optional_fields_returns_none_values(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Backward compatibility: omitted optional mapping fields must round-trip as None."""
        from llamaindex_runtime.vector.chunker import SimpleSpanChunker

        registry, version_id, spans = self._ingest_and_get_registry(live_db_connection, tmp_path, "KG chunk mapping backward")

        chunker = SimpleSpanChunker()
        chunks = chunker.generate(spans, version_id=version_id)
        registry.write_vector_chunks(version_id=version_id, chunks=chunks)

        entity_id = uuid.uuid4()
        registry.write_entities(
            entities=[
                {"entity_id": entity_id, "entity_key": "concept:pm25-back", "entity_type": "concept", "canonical_name": "PM2.5 Backward"},
            ]
        )

        chunk_id = chunks[0]["chunk_id"]
        registry.write_chunk_entity_links(
            version_id=version_id,
            links=[
                {"chunk_id": chunk_id, "entity_id": entity_id, "ordinal_no": 0},
            ],
        )

        persisted = registry.query_chunk_entity_links_by_version(version_id)
        match = [l for l in persisted if l["chunk_id"] == chunk_id and l["entity_id"] == entity_id]
        assert len(match) == 1
        assert match[0]["confidence_score"] is None
        assert match[0]["mention_text"] is None

    def test_query_chunks_by_entity_returns_links_across_versions(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Mutual indexing: entity -> chunks lookup should span multiple versions."""
        from llamaindex_runtime.vector.chunker import SimpleSpanChunker

        registry_a, version_a, spans_a = self._ingest_and_get_registry(live_db_connection, tmp_path, "KG mutual chunk A")
        registry_b, version_b, spans_b = self._ingest_and_get_registry(live_db_connection, tmp_path, "KG mutual chunk B")

        chunker = SimpleSpanChunker()
        chunks_a = chunker.generate(spans_a, version_id=version_a)
        chunks_b = chunker.generate(spans_b, version_id=version_b)
        registry_a.write_vector_chunks(version_id=version_a, chunks=chunks_a)
        registry_b.write_vector_chunks(version_id=version_b, chunks=chunks_b)

        entity_id = uuid.uuid4()
        registry_a.write_entities(
            entities=[
                {"entity_id": entity_id, "entity_key": "concept:mutual-chunk", "entity_type": "concept", "canonical_name": "MutualChunk"},
            ]
        )

        registry_a.write_chunk_entity_links(
            version_id=version_a,
            links=[{"chunk_id": chunks_a[0]["chunk_id"], "entity_id": entity_id, "ordinal_no": 0}],
        )
        registry_b.write_chunk_entity_links(
            version_id=version_b,
            links=[{"chunk_id": chunks_b[0]["chunk_id"], "entity_id": entity_id, "ordinal_no": 0}],
        )

        links = registry_a.query_chunks_by_entity(entity_id)
        chunk_ids = {link["chunk_id"] for link in links}
        version_ids = {link["version_id"] for link in links}

        assert chunk_ids == {chunks_a[0]["chunk_id"], chunks_b[0]["chunk_id"]}
        assert version_ids == {version_a, version_b}

    def test_query_entities_by_chunk_returns_entity_links(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Mutual indexing: chunk -> entities lookup should return linked entities."""
        from llamaindex_runtime.vector.chunker import SimpleSpanChunker

        registry, version_id, spans = self._ingest_and_get_registry(live_db_connection, tmp_path, "KG mutual entities by chunk")

        chunker = SimpleSpanChunker()
        chunks = chunker.generate(spans, version_id=version_id)
        registry.write_vector_chunks(version_id=version_id, chunks=chunks)

        entity_a = uuid.uuid4()
        entity_b = uuid.uuid4()
        registry.write_entities(
            entities=[
                {"entity_id": entity_a, "entity_key": "concept:chunk-a", "entity_type": "concept", "canonical_name": "ChunkA"},
                {"entity_id": entity_b, "entity_key": "concept:chunk-b", "entity_type": "concept", "canonical_name": "ChunkB"},
            ]
        )

        chunk_id = chunks[0]["chunk_id"]
        registry.write_chunk_entity_links(
            version_id=version_id,
            links=[
                {"chunk_id": chunk_id, "entity_id": entity_a, "ordinal_no": 0},
                {"chunk_id": chunk_id, "entity_id": entity_b, "ordinal_no": 1},
            ],
        )

        links = registry.query_entities_by_chunk(chunk_id)
        entity_ids = {link["entity_id"] for link in links}
        assert entity_ids == {entity_a, entity_b}

    def test_query_nodes_by_entity_returns_links(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Mutual indexing: entity -> nodes lookup should return linked tree nodes."""
        from llamaindex_runtime.registry.tree_generator import TreeGenerator

        registry, version_id, spans = self._ingest_and_get_registry(live_db_connection, tmp_path, "KG mutual nodes by entity")

        tree = TreeGenerator().generate(spans, version_id=version_id)
        registry.write_tree(version_id=version_id, nodes=tree["nodes"], node_spans=tree["node_spans"])

        entity_id = uuid.uuid4()
        registry.write_entities(
            entities=[
                {"entity_id": entity_id, "entity_key": "concept:mutual-node", "entity_type": "concept", "canonical_name": "MutualNode"},
            ]
        )

        node_id = tree["nodes"][0]["node_id"]
        registry.write_node_entity_links(
            version_id=version_id,
            links=[{"node_id": node_id, "entity_id": entity_id, "ordinal_no": 0}],
        )

        links = registry.query_nodes_by_entity(entity_id)
        assert len(links) == 1
        assert links[0]["node_id"] == node_id
        assert links[0]["version_id"] == version_id

    def test_query_entities_by_node_returns_entity_links(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Mutual indexing: node -> entities lookup should return linked entities."""
        from llamaindex_runtime.registry.tree_generator import TreeGenerator

        registry, version_id, spans = self._ingest_and_get_registry(live_db_connection, tmp_path, "KG mutual entities by node")

        tree = TreeGenerator().generate(spans, version_id=version_id)
        registry.write_tree(version_id=version_id, nodes=tree["nodes"], node_spans=tree["node_spans"])

        entity_id = uuid.uuid4()
        registry.write_entities(
            entities=[
                {"entity_id": entity_id, "entity_key": "concept:node-entity", "entity_type": "concept", "canonical_name": "NodeEntity"},
            ]
        )

        node_id = tree["nodes"][0]["node_id"]
        registry.write_node_entity_links(
            version_id=version_id,
            links=[{"node_id": node_id, "entity_id": entity_id, "ordinal_no": 0}],
        )

        links = registry.query_entities_by_node(node_id)
        assert len(links) == 1
        assert links[0]["entity_id"] == entity_id


class TestLiveKGCascade:
    """Verify cascade delete behavior for KG tables."""

    def test_cascade_delete_version_removes_evidence_links(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Deleting a version must cascade to evidence_links."""
        from llamaindex_runtime.ingestion import IngestionPipeline
        from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

        sample_pdf = tmp_path / "kg-cascade-ev.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="KG cascade evidence")

        entity_id = uuid.uuid4()
        registry.write_entities(
            entities=[
                {"entity_id": entity_id, "entity_key": "concept:test", "entity_type": "concept", "canonical_name": "Test"},
            ]
        )

        spans = registry.query_spans_by_version(result.version_id)
        registry.write_evidence_links(
            version_id=result.version_id,
            evidence_links=[
                {
                    "entity_id": entity_id,
                    "relation_id": None,
                    "span_id": spans[0]["span_id"],
                    "source_kind": "ner",
                    "confidence_score": 0.5,
                }
            ],
        )

        # Verify evidence link exists
        assert len(registry.query_evidence_links_by_version(result.version_id)) > 0

        # Delete version
        with live_db_connection.cursor() as cur:
            cur.execute("DELETE FROM document_versions WHERE version_id = %s", (str(result.version_id),))

        # Evidence links must be gone
        assert len(registry.query_evidence_links_by_version(result.version_id)) == 0

    def test_cascade_delete_entity_removes_chunk_entity_links(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Deleting an entity must cascade to chunk_entity_links."""
        from llamaindex_runtime.ingestion import IngestionPipeline
        from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter
        from llamaindex_runtime.vector.chunker import SimpleSpanChunker

        sample_pdf = tmp_path / "kg-cascade-chunk.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="KG cascade chunk entity")

        spans = registry.query_spans_by_version(result.version_id)
        chunker = SimpleSpanChunker()
        chunks = chunker.generate(spans, version_id=result.version_id)
        registry.write_vector_chunks(version_id=result.version_id, chunks=chunks)

        entity_id = uuid.uuid4()
        registry.write_entities(
            entities=[
                {"entity_id": entity_id, "entity_key": "concept:del", "entity_type": "concept", "canonical_name": "DeleteMe"},
            ]
        )

        chunk_id = chunks[0]["chunk_id"]
        registry.write_chunk_entity_links(
            version_id=result.version_id,
            links=[{"chunk_id": chunk_id, "entity_id": entity_id, "ordinal_no": 0}],
        )

        # Verify link exists
        assert len(registry.query_chunk_entity_links_by_version(result.version_id)) > 0

        # Delete entity
        with live_db_connection.cursor() as cur:
            cur.execute("DELETE FROM entities WHERE entity_id = %s", (str(entity_id),))

        # chunk_entity_links must be gone
        assert len(registry.query_chunk_entity_links_by_version(result.version_id)) == 0

    def test_cascade_delete_entity_removes_node_entity_links(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Deleting an entity must cascade to node_entity_links."""
        from llamaindex_runtime.ingestion import IngestionPipeline
        from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter
        from llamaindex_runtime.registry.tree_generator import TreeGenerator

        sample_pdf = tmp_path / "kg-cascade-node.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="KG cascade node entity")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate(spans, version_id=result.version_id)
        registry.write_tree(version_id=result.version_id, nodes=tree["nodes"], node_spans=tree["node_spans"])

        entity_id = uuid.uuid4()
        registry.write_entities(
            entities=[
                {"entity_id": entity_id, "entity_key": "concept:del2", "entity_type": "concept", "canonical_name": "DeleteMe2"},
            ]
        )

        node_id = tree["nodes"][0]["node_id"]
        registry.write_node_entity_links(
            version_id=result.version_id,
            links=[{"node_id": node_id, "entity_id": entity_id, "ordinal_no": 0}],
        )

        # Verify link exists
        assert len(registry.query_node_entity_links_by_version(result.version_id)) > 0

        # Delete entity
        with live_db_connection.cursor() as cur:
            cur.execute("DELETE FROM entities WHERE entity_id = %s", (str(entity_id),))

        # node_entity_links must be gone
        assert len(registry.query_node_entity_links_by_version(result.version_id)) == 0

    def test_cascade_delete_entity_removes_relations_and_evidence_links(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Deleting an entity must cascade to: relations referencing it, evidence_links referencing those relations."""
        from llamaindex_runtime.ingestion import IngestionPipeline
        from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

        sample_pdf = tmp_path / "kg-cascade-full.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="KG cascade full")

        e1 = uuid.uuid4()
        e2 = uuid.uuid4()
        rel_id = uuid.uuid4()
        registry.write_entities(
            entities=[
                {"entity_id": e1, "entity_key": "concept:a", "entity_type": "concept", "canonical_name": "A"},
                {"entity_id": e2, "entity_key": "concept:b", "entity_type": "concept", "canonical_name": "B"},
            ]
        )
        registry.write_relations(
            relations=[
                {
                    "relation_id": rel_id,
                    "relation_key": "a-relates-b",
                    "relation_type": "relates_to",
                    "source_entity_id": e1,
                    "target_entity_id": e2,
                }
            ]
        )

        spans = registry.query_spans_by_version(result.version_id)
        registry.write_evidence_links(
            version_id=result.version_id,
            evidence_links=[
                {
                    "entity_id": None,
                    "relation_id": rel_id,
                    "span_id": spans[0]["span_id"],
                    "source_kind": "manual",
                    "confidence_score": None,
                }
            ],
        )

        # Verify
        assert len(registry.query_relations()) >= 1
        assert len(registry.query_evidence_links_by_version(result.version_id)) >= 1

        # Delete source entity -> cascades to relation -> cascades to evidence_link
        with live_db_connection.cursor() as cur:
            cur.execute("DELETE FROM entities WHERE entity_id = %s", (str(e1),))

        # Relation must be gone (source_entity_id FK cascade)
        remaining_rels = [r for r in registry.query_relations() if r["relation_id"] == rel_id]
        assert len(remaining_rels) == 0

        # Evidence link for that relation must also be gone
        remaining_ev = [el for el in registry.query_evidence_links_by_version(result.version_id) if el["relation_id"] == rel_id]
        assert len(remaining_ev) == 0


class TestLiveKGEdgeCases:
    """Edge cases for KG persistence."""

    def test_write_entities_empty_list_is_noop(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Writing an empty entities list must not raise and must not insert rows."""
        from llamaindex_runtime.ingestion import IngestionPipeline
        from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

        sample_pdf = tmp_path / "kg-empty-entities.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="KG empty entities")

        registry.write_entities(entities=[])
        assert len(registry.query_entities()) == 0

    def test_write_evidence_links_null_confidence_score(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """evidence_links with confidence_score=NULL must be persisted correctly."""
        from llamaindex_runtime.ingestion import IngestionPipeline
        from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

        sample_pdf = tmp_path / "kg-null-confidence.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="KG null confidence")

        entity_id = uuid.uuid4()
        registry.write_entities(
            entities=[
                {"entity_id": entity_id, "entity_key": "concept:nullconf", "entity_type": "concept", "canonical_name": "NullConf"},
            ]
        )

        spans = registry.query_spans_by_version(result.version_id)
        registry.write_evidence_links(
            version_id=result.version_id,
            evidence_links=[
                {
                    "entity_id": entity_id,
                    "relation_id": None,
                    "span_id": spans[0]["span_id"],
                    "source_kind": "ner",
                    "confidence_score": None,
                }
            ],
        )

        persisted = registry.query_evidence_links_by_version(result.version_id)
        match = [el for el in persisted if el["entity_id"] == entity_id]
        assert len(match) == 1
        assert match[0]["confidence_score"] is None

    def test_entity_key_uniqueness_enforced(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Inserting two entities with the same entity_key must raise a uniqueness violation."""
        from llamaindex_runtime.ingestion import IngestionPipeline
        from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

        sample_pdf = tmp_path / "kg-unique-key.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        pipeline.ingest(sample_pdf, title="KG unique key")

        registry.write_entities(
            entities=[
                {"entity_id": uuid.uuid4(), "entity_key": "concept:duplicate", "entity_type": "concept", "canonical_name": "First"},
            ]
        )

        with pytest.raises(Exception):
            registry.write_entities(
                entities=[
                    {"entity_id": uuid.uuid4(), "entity_key": "concept:duplicate", "entity_type": "concept", "canonical_name": "Second"},
                ]
            )

    def test_write_chunk_entity_links_idempotent(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Writing chunk_entity_links twice with ON CONFLICT must not duplicate rows."""
        from llamaindex_runtime.ingestion import IngestionPipeline
        from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter
        from llamaindex_runtime.vector.chunker import SimpleSpanChunker

        sample_pdf = tmp_path / "kg-chunk-idempotent.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="KG chunk idempotent")

        spans = registry.query_spans_by_version(result.version_id)
        chunker = SimpleSpanChunker()
        chunks = chunker.generate(spans, version_id=result.version_id)
        registry.write_vector_chunks(version_id=result.version_id, chunks=chunks)

        entity_id = uuid.uuid4()
        registry.write_entities(
            entities=[
                {"entity_id": entity_id, "entity_key": "concept:idem", "entity_type": "concept", "canonical_name": "Idempotent"},
            ]
        )

        chunk_id = chunks[0]["chunk_id"]
        links = [{"chunk_id": chunk_id, "entity_id": entity_id, "ordinal_no": 0}]

        registry.write_chunk_entity_links(version_id=result.version_id, links=links)
        registry.write_chunk_entity_links(version_id=result.version_id, links=links)

        persisted = registry.query_chunk_entity_links_by_version(result.version_id)
        match = [l for l in persisted if l["chunk_id"] == chunk_id and l["entity_id"] == entity_id]
        assert len(match) == 1, "Idempotent write must not duplicate chunk_entity_links"

    def test_write_node_entity_links_idempotent(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Writing node_entity_links twice with ON CONFLICT must not duplicate rows."""
        from llamaindex_runtime.ingestion import IngestionPipeline
        from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter
        from llamaindex_runtime.registry.tree_generator import TreeGenerator

        sample_pdf = tmp_path / "kg-node-idempotent.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="KG node idempotent")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate(spans, version_id=result.version_id)
        registry.write_tree(version_id=result.version_id, nodes=tree["nodes"], node_spans=tree["node_spans"])

        entity_id = uuid.uuid4()
        registry.write_entities(
            entities=[
                {"entity_id": entity_id, "entity_key": "concept:nidem", "entity_type": "concept", "canonical_name": "NodeIdempotent"},
            ]
        )

        node_id = tree["nodes"][0]["node_id"]
        links = [{"node_id": node_id, "entity_id": entity_id, "ordinal_no": 0}]

        registry.write_node_entity_links(version_id=result.version_id, links=links)
        registry.write_node_entity_links(version_id=result.version_id, links=links)

        persisted = registry.query_node_entity_links_by_version(result.version_id)
        match = [l for l in persisted if l["node_id"] == node_id and l["entity_id"] == entity_id]
        assert len(match) == 1, "Idempotent write must not duplicate node_entity_links"

    def test_multiple_entities_per_chunk(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """A single chunk can be linked to multiple entities."""
        from llamaindex_runtime.ingestion import IngestionPipeline
        from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter
        from llamaindex_runtime.vector.chunker import SimpleSpanChunker

        sample_pdf = tmp_path / "kg-multi-entity.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="KG multi entity")

        spans = registry.query_spans_by_version(result.version_id)
        chunker = SimpleSpanChunker()
        chunks = chunker.generate(spans, version_id=result.version_id)
        registry.write_vector_chunks(version_id=result.version_id, chunks=chunks)

        e1 = uuid.uuid4()
        e2 = uuid.uuid4()
        registry.write_entities(
            entities=[
                {"entity_id": e1, "entity_key": "concept:multi1", "entity_type": "concept", "canonical_name": "Multi1"},
                {"entity_id": e2, "entity_key": "concept:multi2", "entity_type": "concept", "canonical_name": "Multi2"},
            ]
        )

        chunk_id = chunks[0]["chunk_id"]
        registry.write_chunk_entity_links(
            version_id=result.version_id,
            links=[
                {"chunk_id": chunk_id, "entity_id": e1, "ordinal_no": 0},
                {"chunk_id": chunk_id, "entity_id": e2, "ordinal_no": 1},
            ],
        )

        persisted = registry.query_chunk_entity_links_by_version(result.version_id)
        chunk_links = [l for l in persisted if l["chunk_id"] == chunk_id]
        assert len(chunk_links) == 2
        linked_entity_ids = {l["entity_id"] for l in chunk_links}
        assert linked_entity_ids == {e1, e2}
