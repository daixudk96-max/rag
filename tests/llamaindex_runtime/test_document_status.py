"""Tests for the P4 LightRAG-style Document Status Slice.

These tests verify:
1. Document processing status tracking beyond active/retired
2. Processing stages: registered -> parsed -> chunks_created -> embedded -> tree_built -> entities_extracted -> complete
3. Ability to query documents by status for incremental processing
4. Status transitions are valid and trackable
5. Status timestamps are persisted
6. Existing version/provenance behavior remains intact

Live tests require FORMAL_RUNTIME_DATABASE_URL to be set.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import psycopg
import pytest

from llamaindex_runtime.registry.contracts import RegisteredDocument, RegistryWriter, VersionInfo, DocumentStatus
from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter


# ===========================================================================
# UNIT TESTS -- mock database, no PostgreSQL required
# ===========================================================================


class TestDocumentStatusContract:
    """Tests for the DocumentStatus dataclass contract."""

    def test_status_enum_has_required_stages(self) -> None:
        """DocumentStatus must have all processing pipeline stages."""
        # These are the LightRAG-style processing stages
        assert hasattr(DocumentStatus, "REGISTERED")
        assert hasattr(DocumentStatus, "PARSED")
        assert hasattr(DocumentStatus, "CHUNKS_CREATED")
        assert hasattr(DocumentStatus, "EMBEDDED")
        assert hasattr(DocumentStatus, "TREE_BUILT")
        assert hasattr(DocumentStatus, "ENTITIES_EXTRACTED")
        assert hasattr(DocumentStatus, "COMPLETE")
        assert hasattr(DocumentStatus, "FAILED")

    def test_status_is_enum(self) -> None:
        """DocumentStatus must be an enum for type safety."""
        from enum import Enum
        assert issubclass(DocumentStatus, Enum)

    def test_failed_is_valid_target_from_any_stage(self) -> None:
        """FAILED should be a legal terminal status from every processing stage."""
        statuses = [
            DocumentStatus.REGISTERED,
            DocumentStatus.PARSED,
            DocumentStatus.CHUNKS_CREATED,
            DocumentStatus.EMBEDDED,
            DocumentStatus.TREE_BUILT,
            DocumentStatus.ENTITIES_EXTRACTED,
            DocumentStatus.COMPLETE,
        ]
        for status in statuses:
            assert status.can_transition_to(DocumentStatus.FAILED) is True


class TestVersionInfoHasStatusField:
    """Tests for VersionInfo including the new processing_status field."""

    def test_version_info_has_processing_status(self) -> None:
        """VersionInfo must have a processing_status field."""
        info = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="abc123",
            is_active=True,
            status="active",
            processing_status="registered",
        )
        assert hasattr(info, "processing_status")

    def test_processing_status_defaults_to_registered(self) -> None:
        """New versions must default to 'registered' status."""
        info = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="abc123",
            is_active=True,
            status="active",
        )
        # Should default to "registered" if not provided
        assert info.processing_status == "registered"


class TestRegistryWriterHasStatusMethods:
    """Tests for RegistryWriter protocol having document status methods."""

    def test_protocol_has_update_processing_status(self) -> None:
        """RegistryWriter protocol must include update_processing_status method."""
        assert hasattr(RegistryWriter, "update_processing_status")

    def test_protocol_has_query_by_processing_status(self) -> None:
        """RegistryWriter protocol must include query_by_processing_status method."""
        assert hasattr(RegistryWriter, "query_by_processing_status")


# ===========================================================================
# LIVE TESTS -- require FORMAL_RUNTIME_DATABASE_URL
# ===========================================================================


def test_live_register_document_defaults_to_registered_status(
    tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
) -> None:
    """Registering a new document must set processing_status='registered'."""
    from tests.llamaindex_runtime.test_live_ingestion_postgres import _build_pdf

    sample_pdf = tmp_path / "status-registered.pdf"
    _build_pdf(sample_pdf, "Status tracking content")

    registry = PostgresRegistryWriter(live_db_connection)

    registered = registry.register_document(
        source_path=sample_pdf,
        source_uri="file:///status-registered.pdf",
        title="Status tracking test",
    )

    # Verify the version has processing_status='registered'
    version_info = registry.get_version(registered.version_id)
    assert version_info.processing_status == "registered"


def test_live_update_processing_status_advances_stage(
    tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
) -> None:
    """update_processing_status must advance the processing stage."""
    from tests.llamaindex_runtime.test_live_ingestion_postgres import _build_pdf

    sample_pdf = tmp_path / "status-advance.pdf"
    _build_pdf(sample_pdf, "Status advancement content")

    registry = PostgresRegistryWriter(live_db_connection)

    registered = registry.register_document(
        source_path=sample_pdf,
        source_uri="file:///status-advance.pdf",
        title="Status advancement test",
    )

    # Advance to 'parsed'
    registry.update_processing_status(
        version_id=registered.version_id,
        processing_status="parsed",
    )

    version_info = registry.get_version(registered.version_id)
    assert version_info.processing_status == "parsed"


def test_live_query_by_processing_status_returns_matching_versions(
    tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
) -> None:
    """query_by_processing_status must return versions with specified status."""
    from tests.llamaindex_runtime.test_live_ingestion_postgres import _build_pdf

    pdf_a = tmp_path / "query-a.pdf"
    _build_pdf(pdf_a, "Query status A")
    pdf_b = tmp_path / "query-b.pdf"
    _build_pdf(pdf_b, "Query status B")

    registry = PostgresRegistryWriter(live_db_connection)

    # Register two documents
    reg_a = registry.register_document(
        source_path=pdf_a,
        source_uri="file:///query-a.pdf",
        title="Query A",
    )
    reg_b = registry.register_document(
        source_path=pdf_b,
        source_uri="file:///query-b.pdf",
        title="Query B",
    )

    # Advance A to 'parsed', keep B at 'registered'
    registry.update_processing_status(
        version_id=reg_a.version_id,
        processing_status="parsed",
    )

    # Query for 'registered' status
    registered_versions = registry.query_by_processing_status("registered")
    registered_version_ids = {v.version_id for v in registered_versions}

    # Should include reg_b but not reg_a
    assert reg_b.version_id in registered_version_ids
    assert reg_a.version_id not in registered_version_ids


def test_live_processing_status_preserves_existing_version_behavior(
    tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
) -> None:
    """Adding processing_status must not break existing version lifecycle."""
    from tests.llamaindex_runtime.test_live_ingestion_postgres import _build_pdf

    pdf_v1 = tmp_path / "preserve-v1.pdf"
    _build_pdf(pdf_v1, "Preserve version 1")

    registry = PostgresRegistryWriter(live_db_connection)

    v1 = registry.register_document(
        source_path=pdf_v1,
        source_uri="file:///preserve-test.pdf",
        title="Preserve test",
    )

    # Advance v1 to 'parsed'
    registry.update_processing_status(
        version_id=v1.version_id,
        processing_status="parsed",
    )

    # Create a new version (changed content)
    pdf_v2 = tmp_path / "preserve-v2.pdf"
    _build_pdf(pdf_v2, "Preserve version 2 different content")

    v2 = registry.register_document(
        source_path=pdf_v2,
        source_uri="file:///preserve-test.pdf",
        title="Preserve test",
    )

    # v1 must be retired, v2 must be active
    assert v1.doc_id == v2.doc_id, "Same source_uri must keep same doc_id"
    assert v1.version_id != v2.version_id, "Changed content must produce new version_id"

    v1_refreshed = registry.get_version(v1.version_id)
    assert v1_refreshed.is_active is False, "Old version must be retired"
    assert v2.is_active is True, "New version must be active"

    # v2 should start at 'registered' (new version resets processing status)
    assert v2.version_no == 2
    v2_info = registry.get_version(v2.version_id)
    assert v2_info.processing_status == "registered", "New version must start at 'registered'"


def test_live_processing_status_timestamps_persisted(
    tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
) -> None:
    """Processing status transitions must persist timestamps."""
    from tests.llamaindex_runtime.test_live_ingestion_postgres import _build_pdf

    sample_pdf = tmp_path / "timestamps.pdf"
    _build_pdf(sample_pdf, "Timestamp content")

    registry = PostgresRegistryWriter(live_db_connection)

    registered = registry.register_document(
        source_path=sample_pdf,
        source_uri="file:///timestamps.pdf",
        title="Timestamp test",
    )

    # Advance status and check timestamps
    registry.update_processing_status(
        version_id=registered.version_id,
        processing_status="parsed",
    )

    # Query version to check parsed_at timestamp exists
    version_info = registry.get_version(registered.version_id)
    assert hasattr(version_info, "parsed_at")
    assert version_info.parsed_at is not None


def test_live_invalid_status_transition_rejected(
    tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
) -> None:
    """Invalid status transitions must be rejected."""
    from tests.llamaindex_runtime.test_live_ingestion_postgres import _build_pdf

    sample_pdf = tmp_path / "invalid-transition.pdf"
    _build_pdf(sample_pdf, "Invalid transition content")

    registry = PostgresRegistryWriter(live_db_connection)

    registered = registry.register_document(
        source_path=sample_pdf,
        source_uri="file:///invalid-transition.pdf",
        title="Invalid transition test",
    )

    # Try invalid transition: registered -> complete (skipping intermediate stages)
    with pytest.raises(ValueError, match="Invalid status transition"):
        registry.update_processing_status(
            version_id=registered.version_id,
            processing_status="complete",
        )


def test_live_status_transition_ordering_enforced(
    tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
) -> None:
    """Status transitions must follow correct ordering: registered -> parsed -> chunks_created -> embedded -> tree_built -> entities_extracted -> complete."""
    from tests.llamaindex_runtime.test_live_ingestion_postgres import _build_pdf

    sample_pdf = tmp_path / "ordering.pdf"
    _build_pdf(sample_pdf, "Ordering content")

    registry = PostgresRegistryWriter(live_db_connection)

    registered = registry.register_document(
        source_path=sample_pdf,
        source_uri="file:///ordering.pdf",
        title="Ordering test",
    )

    # Valid sequence: registered -> parsed -> chunks_created
    registry.update_processing_status(
        version_id=registered.version_id,
        processing_status="parsed",
    )

    registry.update_processing_status(
        version_id=registered.version_id,
        processing_status="chunks_created",
    )

    version_info = registry.get_version(registered.version_id)
    assert version_info.processing_status == "chunks_created"