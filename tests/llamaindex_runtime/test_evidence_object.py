"""Tests for P4 Evidence Object Slice: Minimal evidence_id layer.

These tests verify:
1. Evidence object exists with minimal fields (evidence_id, version_id, created_at)
2. EvidenceLink has optional evidence_id field referencing evidence table
3. Span_id backbone is preserved - evidence_id is an optional grouping layer
4. Database schema for evidence table with proper FK relationships
5. PostgresRegistryWriter methods handle evidence objects and evidence_id
6. Cascade deletes work properly for evidence -> evidence_links

This slice ONLY adds a minimal evidence grouping layer - no scoring, no deduplication, no EvidenceNet features.
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
# UNIT TESTS -- Evidence contract dataclass (no database required)
# ===========================================================================


class TestEvidenceContract:
    """Evidence frozen dataclass: minimal fields for grouping evidence_links."""

    def test_evidence_dataclass_exists(self) -> None:
        """Evidence dataclass must exist for grouping evidence_links."""
        from llamaindex_runtime.registry.contracts import Evidence

        evidence = Evidence(
            evidence_id=uuid.uuid4(),
            version_id=uuid.uuid4(),
        )
        assert isinstance(evidence.evidence_id, uuid.UUID)
        assert isinstance(evidence.version_id, uuid.UUID)

    def test_evidence_frozen_dataclass(self) -> None:
        """Evidence must be frozen (immutable)."""
        from llamaindex_runtime.registry.contracts import Evidence

        evidence = Evidence(
            evidence_id=uuid.uuid4(),
            version_id=uuid.uuid4(),
        )
        with pytest.raises(AttributeError):
            evidence.version_id = uuid.uuid4()  # type: ignore[misc]

    def test_evidence_required_fields(self) -> None:
        """Evidence must have evidence_id and version_id as required fields."""
        from llamaindex_runtime.registry.contracts import Evidence

        evidence_id = uuid.uuid4()
        version_id = uuid.uuid4()
        evidence = Evidence(
            evidence_id=evidence_id,
            version_id=version_id,
        )
        assert evidence.evidence_id == evidence_id
        assert evidence.version_id == version_id

    def test_evidence_has_dedup_key_field(self) -> None:
        """Evidence must have dedup_key field for idempotent deduplication."""
        from llamaindex_runtime.registry.contracts import Evidence

        evidence = Evidence(
            evidence_id=uuid.uuid4(),
            version_id=uuid.uuid4(),
            dedup_key="test-dedup-key",
        )
        assert hasattr(evidence, "dedup_key")
        assert evidence.dedup_key == "test-dedup-key"

    def test_evidence_dedup_key_optional(self) -> None:
        """dedup_key must be optional for backward compatibility."""
        from llamaindex_runtime.registry.contracts import Evidence

        evidence = Evidence(
            evidence_id=uuid.uuid4(),
            version_id=uuid.uuid4(),
        )
        # dedup_key can be None
        assert evidence.dedup_key is None

    def test_evidence_no_scoring_fields(self) -> None:
        """Evidence must NOT have scoring fields in this minimal slice."""
        from llamaindex_runtime.registry.contracts import Evidence

        evidence = Evidence(
            evidence_id=uuid.uuid4(),
            version_id=uuid.uuid4(),
            dedup_key=None,
        )
        # Minimal slice - no scoring fields
        assert not hasattr(evidence, "confidence_score"), "Evidence must not have scoring in this slice"
        assert not hasattr(evidence, "source_method"), "Evidence must not have EvidenceNet fields in this slice"


class TestEvidenceLinkEvidenceId:
    """EvidenceLink with optional evidence_id field for grouping."""

    def test_evidence_link_has_evidence_id_field(self) -> None:
        """EvidenceLink must have optional evidence_id field."""
        from llamaindex_runtime.registry.contracts import EvidenceLink

        link = EvidenceLink(
            evidence_link_id=uuid.uuid4(),
            version_id=uuid.uuid4(),
            entity_id=uuid.uuid4(),
            relation_id=None,
            span_id=uuid.uuid4(),
            source_kind="ner",
            confidence_score=0.9,
            evidence_id=uuid.uuid4(),
        )
        assert hasattr(link, "evidence_id")
        assert isinstance(link.evidence_id, uuid.UUID)

    def test_evidence_id_optional_can_be_none(self) -> None:
        """evidence_id must be optional - evidence_links can exist without grouping."""
        from llamaindex_runtime.registry.contracts import EvidenceLink

        link = EvidenceLink(
            evidence_link_id=uuid.uuid4(),
            version_id=uuid.uuid4(),
            entity_id=uuid.uuid4(),
            relation_id=None,
            span_id=uuid.uuid4(),
            source_kind="ner",
            confidence_score=None,
            evidence_id=None,
        )
        assert link.evidence_id is None

    def test_span_id_backbone_preserved(self) -> None:
        """EvidenceLink must still have span_id as the provenance anchor."""
        from llamaindex_runtime.registry.contracts import EvidenceLink

        link = EvidenceLink(
            evidence_link_id=uuid.uuid4(),
            version_id=uuid.uuid4(),
            entity_id=uuid.uuid4(),
            relation_id=None,
            span_id=uuid.uuid4(),
            source_kind="ner",
            confidence_score=0.9,
            evidence_id=uuid.uuid4(),
        )
        # span_id must remain as the backbone
        assert hasattr(link, "span_id")
        assert isinstance(link.span_id, uuid.UUID)
        assert link.span_id is not None, "span_id must be required"


# ===========================================================================
# LIVE TESTS -- require FORMAL_RUNTIME_DATABASE_URL
# ===========================================================================


class TestLiveEvidenceSchema:
    """Verify that evidence table exists with correct structure."""

    def test_evidence_table_exists(self, live_db_connection, live_applied_schema, clean_live_db) -> None:
        """evidence table must exist."""
        with live_db_connection.cursor() as cur:
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = 'evidence'")
            row = cur.fetchone()
        assert row is not None, "evidence table must exist"

    def test_evidence_table_has_evidence_id_column(self, live_db_connection, live_applied_schema, clean_live_db) -> None:
        """evidence table must have evidence_id as primary key."""
        with live_db_connection.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'evidence' AND column_name = 'evidence_id'"
            )
            row = cur.fetchone()
        assert row is not None, "evidence table must have evidence_id column"

    def test_evidence_table_has_version_id_fk(self, live_db_connection, live_applied_schema, clean_live_db) -> None:
        """evidence.version_id must reference document_versions."""
        with live_db_connection.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM information_schema.key_column_usage kcu
                JOIN information_schema.table_constraints tc
                    ON kcu.constraint_name = tc.constraint_name AND kcu.table_schema = tc.table_schema
                WHERE kcu.table_name = 'evidence'
                    AND kcu.column_name = 'version_id'
                    AND tc.constraint_type = 'FOREIGN KEY'
                """
            )
            row = cur.fetchone()
        assert row is not None, "evidence.version_id must have a FOREIGN KEY constraint"

    def test_evidence_links_has_evidence_id_column(self, live_db_connection, live_applied_schema, clean_live_db) -> None:
        """evidence_links must have evidence_id column (optional grouping layer)."""
        with live_db_connection.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'evidence_links' AND column_name = 'evidence_id'"
            )
            row = cur.fetchone()
        assert row is not None, "evidence_links must have evidence_id column"

    def test_evidence_links_evidence_id_fk_to_evidence(self, live_db_connection, live_applied_schema, clean_live_db) -> None:
        """evidence_links.evidence_id must be a FK referencing evidence(evidence_id)."""
        with live_db_connection.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM information_schema.key_column_usage kcu
                JOIN information_schema.table_constraints tc
                    ON kcu.constraint_name = tc.constraint_name AND kcu.table_schema = tc.table_schema
                WHERE kcu.table_name = 'evidence_links'
                    AND kcu.column_name = 'evidence_id'
                    AND tc.constraint_type = 'FOREIGN KEY'
                """
            )
            row = cur.fetchone()
        assert row is not None, "evidence_links.evidence_id must have a FOREIGN KEY constraint to evidence table"

    def test_evidence_links_span_id_still_required(self, live_db_connection, live_applied_schema, clean_live_db) -> None:
        """evidence_links.span_id must still be NOT NULL (backbone preserved)."""
        with live_db_connection.cursor() as cur:
            cur.execute(
                "SELECT is_nullable FROM information_schema.columns WHERE table_name = 'evidence_links' AND column_name = 'span_id'"
            )
            row = cur.fetchone()
        assert row is not None and row[0] == "NO", "evidence_links.span_id must remain NOT NULL"

    def test_evidence_links_evidence_id_nullable(self, live_db_connection, live_applied_schema, clean_live_db) -> None:
        """evidence_links.evidence_id must be nullable (optional grouping)."""
        with live_db_connection.cursor() as cur:
            cur.execute(
                "SELECT is_nullable FROM information_schema.columns WHERE table_name = 'evidence_links' AND column_name = 'evidence_id'"
            )
            row = cur.fetchone()
        assert row is not None and row[0] == "YES", "evidence_links.evidence_id must be nullable"


class TestLiveEvidenceCRUD:
    """Live tests for Evidence and evidence_id CRUD operations."""

    def _ingest_and_get_registry(
        self,
        live_db_connection,
        tmp_path: Path,
        title: str = "Evidence test",
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

    def test_write_evidence_persists_evidence_object(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """write_evidence must persist evidence rows."""
        registry, version_id, spans = self._ingest_and_get_registry(live_db_connection, tmp_path, "Evidence persist")

        evidence_id = uuid.uuid4()
        registry.write_evidence(
            evidence=[
                {
                    "evidence_id": evidence_id,
                    "version_id": version_id,
                }
            ]
        )

        persisted = registry.query_evidence_by_version(version_id)
        assert len(persisted) >= 1
        match = [e for e in persisted if e["evidence_id"] == evidence_id]
        assert len(match) == 1
        assert match[0]["version_id"] == version_id

    def test_write_evidence_links_with_evidence_id(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """write_evidence_links must persist links with evidence_id grouping."""
        registry, version_id, spans = self._ingest_and_get_registry(live_db_connection, tmp_path, "Evidence link grouping")

        # Create evidence object
        evidence_id = uuid.uuid4()
        registry.write_evidence(
            evidence=[
                {
                    "evidence_id": evidence_id,
                    "version_id": version_id,
                }
            ]
        )

        # Create entity
        entity_id = uuid.uuid4()
        registry.write_entities(
            entities=[
                {"entity_id": entity_id, "entity_key": "concept:pm25", "entity_type": "concept", "canonical_name": "PM2.5"},
            ]
        )

        # Create evidence_links with evidence_id
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
                    "evidence_id": evidence_id,
                }
            ],
        )

        persisted = registry.query_evidence_links_by_version(version_id)
        match = [el for el in persisted if el["span_id"] == span_id and el["entity_id"] == entity_id]
        assert len(match) == 1
        assert match[0]["evidence_id"] == evidence_id

    def test_evidence_links_without_evidence_id_still_works(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Evidence_links without evidence_id must still persist (backward compatibility)."""
        registry, version_id, spans = self._ingest_and_get_registry(live_db_connection, tmp_path, "Evidence link no group")

        entity_id = uuid.uuid4()
        registry.write_entities(
            entities=[
                {"entity_id": entity_id, "entity_key": "concept:test", "entity_type": "concept", "canonical_name": "Test"},
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
                    "confidence_score": 0.9,
                    "evidence_id": None,  # No grouping
                }
            ],
        )

        persisted = registry.query_evidence_links_by_version(version_id)
        match = [el for el in persisted if el["span_id"] == span_id]
        assert len(match) == 1
        assert match[0]["evidence_id"] is None

    def test_multiple_evidence_links_grouped_by_one_evidence(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Multiple evidence_links can be grouped under one evidence object."""
        registry, version_id, spans = self._ingest_and_get_registry(live_db_connection, tmp_path, "Multi evidence links")

        # Create one evidence object
        evidence_id = uuid.uuid4()
        registry.write_evidence(
            evidence=[
                {
                    "evidence_id": evidence_id,
                    "version_id": version_id,
                }
            ]
        )

        # Create entities
        e1 = uuid.uuid4()
        e2 = uuid.uuid4()
        registry.write_entities(
            entities=[
                {"entity_id": e1, "entity_key": "concept:a", "entity_type": "concept", "canonical_name": "A"},
                {"entity_id": e2, "entity_key": "concept:b", "entity_type": "concept", "canonical_name": "B"},
            ]
        )

        # Create multiple evidence_links for same evidence_id
        span1 = spans[0]["span_id"]
        span2 = spans[1]["span_id"] if len(spans) > 1 else spans[0]["span_id"]

        registry.write_evidence_links(
            version_id=version_id,
            evidence_links=[
                {
                    "entity_id": e1,
                    "relation_id": None,
                    "span_id": span1,
                    "source_kind": "ner",
                    "confidence_score": 0.8,
                    "evidence_id": evidence_id,
                },
                {
                    "entity_id": e2,
                    "relation_id": None,
                    "span_id": span2,
                    "source_kind": "ner",
                    "confidence_score": 0.9,
                    "evidence_id": evidence_id,
                },
            ],
        )

        persisted = registry.query_evidence_links_by_version(version_id)
        grouped_links = [el for el in persisted if el["evidence_id"] == evidence_id]
        assert len(grouped_links) == 2, "Multiple evidence_links should be grouped under one evidence_id"


class TestLiveEvidenceCascade:
    """Verify cascade delete behavior for evidence -> evidence_links."""

    def test_cascade_delete_evidence_removes_evidence_links(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Deleting an evidence object must cascade to evidence_links referencing it."""
        from llamaindex_runtime.ingestion import IngestionPipeline
        from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

        sample_pdf = tmp_path / "evidence-cascade.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Evidence cascade")

        # Create evidence object
        evidence_id = uuid.uuid4()
        registry.write_evidence(
            evidence=[
                {
                    "evidence_id": evidence_id,
                    "version_id": result.version_id,
                }
            ]
        )

        # Create entity and evidence_link
        entity_id = uuid.uuid4()
        registry.write_entities(
            entities=[
                {"entity_id": entity_id, "entity_key": "concept:del", "entity_type": "concept", "canonical_name": "DeleteMe"},
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
                    "evidence_id": evidence_id,
                }
            ],
        )

        # Verify evidence_link exists
        links_before = registry.query_evidence_links_by_version(result.version_id)
        grouped_links = [el for el in links_before if el["evidence_id"] == evidence_id]
        assert len(grouped_links) > 0

        # Delete evidence object
        with live_db_connection.cursor() as cur:
            cur.execute("DELETE FROM evidence WHERE evidence_id = %s", (str(evidence_id),))

        # Evidence_links referencing that evidence_id must be gone
        links_after = registry.query_evidence_links_by_version(result.version_id)
        remaining_grouped = [el for el in links_after if el["evidence_id"] == evidence_id]
        assert len(remaining_grouped) == 0


class TestEvidenceDedupKeyPersistence:
    """Test dedup_key persistence and idempotent deduplication."""

    def test_write_evidence_persists_dedup_key(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """write_evidence must persist dedup_key field."""
        from llamaindex_runtime.ingestion import IngestionPipeline
        from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

        sample_pdf = tmp_path / "dedup-key-persist.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Dedup key persist")

        evidence_id = uuid.uuid4()
        dedup_key = "unique-dedup-key-123"
        registry.write_evidence(
            evidence=[
                {
                    "evidence_id": evidence_id,
                    "version_id": result.version_id,
                    "dedup_key": dedup_key,
                }
            ]
        )

        persisted = registry.query_evidence_by_version(result.version_id)
        match = [e for e in persisted if e["evidence_id"] == evidence_id]
        assert len(match) == 1
        assert match[0]["dedup_key"] == dedup_key

    def test_duplicate_evidence_same_version_dedup_key_collapses(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Evidence with same version_id + dedup_key must collapse idempotently."""
        from llamaindex_runtime.ingestion import IngestionPipeline
        from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

        sample_pdf = tmp_path / "dedup-collapse.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Dedup collapse")

        dedup_key = "shared-dedup-key"
        evidence_id1 = uuid.uuid4()
        evidence_id2 = uuid.uuid4()

        # Write first evidence with dedup_key
        registry.write_evidence(
            evidence=[
                {
                    "evidence_id": evidence_id1,
                    "version_id": result.version_id,
                    "dedup_key": dedup_key,
                }
            ]
        )

        # Write second evidence with SAME dedup_key - should collapse
        registry.write_evidence(
            evidence=[
                {
                    "evidence_id": evidence_id2,
                    "version_id": result.version_id,
                    "dedup_key": dedup_key,
                }
            ]
        )

        persisted = registry.query_evidence_by_version(result.version_id)
        # Only ONE evidence row should exist for this dedup_key within this version
        matching_dedup = [e for e in persisted if e.get("dedup_key") == dedup_key]
        assert len(matching_dedup) == 1, f"Expected 1 evidence with dedup_key={dedup_key}, got {len(matching_dedup)}"
        assert matching_dedup[0]["evidence_id"] == evidence_id1

    def test_distinct_dedup_keys_create_distinct_evidence_rows(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Evidence with different dedup_key values must create distinct rows."""
        from llamaindex_runtime.ingestion import IngestionPipeline
        from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

        sample_pdf = tmp_path / "dedup-distinct.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Dedup distinct")

        dedup_key1 = "dedup-key-A"
        dedup_key2 = "dedup-key-B"
        evidence_id1 = uuid.uuid4()
        evidence_id2 = uuid.uuid4()

        registry.write_evidence(
            evidence=[
                {
                    "evidence_id": evidence_id1,
                    "version_id": result.version_id,
                    "dedup_key": dedup_key1,
                },
                {
                    "evidence_id": evidence_id2,
                    "version_id": result.version_id,
                    "dedup_key": dedup_key2,
                },
            ]
        )

        persisted = registry.query_evidence_by_version(result.version_id)
        assert len(persisted) >= 2, "Distinct dedup_keys must create distinct evidence rows"

        matching_key1 = [e for e in persisted if e.get("dedup_key") == dedup_key1]
        matching_key2 = [e for e in persisted if e.get("dedup_key") == dedup_key2]
        assert len(matching_key1) == 1
        assert len(matching_key2) == 1

    def test_evidence_without_dedup_key_uses_evidence_id_as_unique(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Evidence without dedup_key must still be unique on evidence_id (backward compatibility)."""
        from llamaindex_runtime.ingestion import IngestionPipeline
        from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

        sample_pdf = tmp_path / "dedup-backward.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Dedup backward")

        evidence_id = uuid.uuid4()
        registry.write_evidence(
            evidence=[
                {
                    "evidence_id": evidence_id,
                    "version_id": result.version_id,
                    "dedup_key": None,
                }
            ]
        )

        persisted = registry.query_evidence_by_version(result.version_id)
        match = [e for e in persisted if e["evidence_id"] == evidence_id]
        assert len(match) == 1


class TestLiveEvidenceEdgeCases:
    """Edge cases for evidence and evidence_id persistence."""

    def test_write_evidence_empty_list_is_noop(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Writing an empty evidence list must not raise and must not insert rows."""
        from llamaindex_runtime.ingestion import IngestionPipeline
        from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

        sample_pdf = tmp_path / "empty-evidence.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Empty evidence")

        registry.write_evidence(evidence=[])
        assert len(registry.query_evidence_by_version(result.version_id)) == 0

    def test_evidence_idempotent_write(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Writing evidence twice with ON CONFLICT must not duplicate rows."""
        from llamaindex_runtime.ingestion import IngestionPipeline
        from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

        sample_pdf = tmp_path / "idempotent-evidence.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Idempotent evidence")

        evidence_id = uuid.uuid4()
        evidence_obj = [{"evidence_id": evidence_id, "version_id": result.version_id}]

        registry.write_evidence(evidence=evidence_obj)
        registry.write_evidence(evidence=evidence_obj)

        persisted = registry.query_evidence_by_version(result.version_id)
        match = [e for e in persisted if e["evidence_id"] == evidence_id]
        assert len(match) == 1, "Idempotent write must not duplicate evidence objects"

    def test_evidence_links_mixed_some_with_evidence_id_some_without(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Evidence_links can have mixed evidence_id - some grouped, some not."""
        registry, version_id, spans = self._ingest_and_get_registry(live_db_connection, tmp_path, "Mixed evidence")

        # Create evidence object
        evidence_id = uuid.uuid4()
        registry.write_evidence(
            evidence=[
                {
                    "evidence_id": evidence_id,
                    "version_id": version_id,
                }
            ]
        )

        # Create entities
        e1 = uuid.uuid4()
        e2 = uuid.uuid4()
        registry.write_entities(
            entities=[
                {"entity_id": e1, "entity_key": "concept:grouped", "entity_type": "concept", "canonical_name": "Grouped"},
                {"entity_id": e2, "entity_key": "concept:ungrouped", "entity_type": "concept", "canonical_name": "Ungrouped"},
            ]
        )

        # Create one evidence_link with evidence_id, one without
        span1 = spans[0]["span_id"]
        span2 = spans[1]["span_id"] if len(spans) > 1 else spans[0]["span_id"]

        registry.write_evidence_links(
            version_id=version_id,
            evidence_links=[
                {
                    "entity_id": e1,
                    "relation_id": None,
                    "span_id": span1,
                    "source_kind": "ner",
                    "confidence_score": 0.8,
                    "evidence_id": evidence_id,
                },
                {
                    "entity_id": e2,
                    "relation_id": None,
                    "span_id": span2,
                    "source_kind": "ner",
                    "confidence_score": 0.9,
                    "evidence_id": None,
                },
            ],
        )

        persisted = registry.query_evidence_links_by_version(version_id)
        grouped = [el for el in persisted if el["evidence_id"] == evidence_id]
        ungrouped = [el for el in persisted if el["evidence_id"] is None]
        assert len(grouped) == 1
        assert len(ungrouped) == 1