"""Tests for the Phase 2 Version Lifecycle Slice.

These tests verify:
1. Stable document identity: repeated ingest of the same source_uri reuses doc_id
2. Explainable version behavior:
   - Same content + same normalization contract => no new version (idempotent)
   - Changed content => new version, old version retired
   - Changed normalization contract => new version, old version retired
3. Pipeline integration: pipeline.ingest skips parsing when version already exists

Live tests require FORMAL_RUNTIME_DATABASE_URL to be set.
Unit tests use mocked database connections and run without a real database.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import psycopg
import pytest

from llamaindex_runtime.ingestion import IngestionPipeline
from llamaindex_runtime.ingestion.normalization import NormalizationContract, NormalizationRules
from llamaindex_runtime.interfaces import CanonicalSpan
from llamaindex_runtime.registry.contracts import RegisteredDocument, RegistryWriter, VersionInfo
from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

from okf._e2a_pipeline_testkit import _FakeReconciler


# ---------------------------------------------------------------------------
# Helpers for building minimal PDFs (used by live tests)
# ---------------------------------------------------------------------------


def _build_rich_pdf(pdf_path: Path, text_body: str = "default body") -> None:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (1200, 1600), "white")
    draw = ImageDraw.Draw(image)
    draw.text((80, 80), "Formal Runtime Heading", fill="black")
    draw.text((80, 180), text_body, fill="black")
    draw.text((80, 260), "Second paragraph for the formal runtime live ingestion test.", fill="black")
    image.save(pdf_path, "PDF")


def _build_pdf(pdf_path: Path, text_body: str) -> None:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (800, 600), "white")
    draw = ImageDraw.Draw(image)
    draw.text((40, 40), text_body, fill="black")
    image.save(pdf_path, "PDF")


# ===========================================================================
# UNIT TESTS -- mock database, no PostgreSQL required
# ===========================================================================


class _MockCursor:
    """Minimal mock cursor that tracks execute calls and returns configured results."""

    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple]] = []
        self._results: list[list[dict]] = []
        self._result_index = 0

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.executed.append((sql, params))

    def fetchone(self) -> tuple | None:
        if self._result_index < len(self._results):
            result = self._results[self._result_index]
            self._result_index += 1
            return result[0] if result else None
        return None

    def fetchall(self) -> list[dict]:
        if self._result_index < len(self._results):
            result = self._results[self._result_index]
            self._result_index += 1
            return result
        return []

    def executemany(self, sql: str, params_list: list) -> None:
        for params in params_list:
            self.executed.append((sql, params))

    def set_results(self, results: list[list[dict]]) -> None:
        self._results = results
        self._result_index = 0


class _MockConnection:
    """Minimal mock psycopg connection."""

    def __init__(self) -> None:
        self._cursor = _MockCursor()
        self._in_transaction = False

    def cursor(self, row_factory=None):
        return self._cursor

    def transaction(self):
        return self  # context manager

    def __enter__(self):
        self._in_transaction = True
        return self

    def __exit__(self, *args):
        self._in_transaction = False


# ---------------------------------------------------------------------------
# Unit: RegisteredDocument and VersionInfo contracts
# ---------------------------------------------------------------------------


class TestRegisteredDocumentContract:
    def test_has_doc_id(self) -> None:
        doc = RegisteredDocument(
            doc_id=uuid.uuid4(),
            version_id=uuid.uuid4(),
            source_uri="file:///test.pdf",
            version_no=1,
            is_active=True,
        )
        assert isinstance(doc.doc_id, uuid.UUID)

    def test_has_version_id(self) -> None:
        doc = RegisteredDocument(
            doc_id=uuid.uuid4(),
            version_id=uuid.uuid4(),
            source_uri="file:///test.pdf",
            version_no=1,
            is_active=True,
        )
        assert isinstance(doc.version_id, uuid.UUID)

    def test_has_source_uri(self) -> None:
        doc = RegisteredDocument(
            doc_id=uuid.uuid4(),
            version_id=uuid.uuid4(),
            source_uri="file:///test.pdf",
            version_no=1,
            is_active=True,
        )
        assert doc.source_uri == "file:///test.pdf"

    def test_has_version_no(self) -> None:
        doc = RegisteredDocument(
            doc_id=uuid.uuid4(),
            version_id=uuid.uuid4(),
            source_uri="file:///test.pdf",
            version_no=3,
            is_active=True,
        )
        assert doc.version_no == 3

    def test_has_is_active(self) -> None:
        doc = RegisteredDocument(
            doc_id=uuid.uuid4(),
            version_id=uuid.uuid4(),
            source_uri="file:///test.pdf",
            version_no=1,
            is_active=True,
        )
        assert doc.is_active is True

    def test_is_frozen(self) -> None:
        doc = RegisteredDocument(
            doc_id=uuid.uuid4(),
            version_id=uuid.uuid4(),
            source_uri="file:///test.pdf",
            version_no=1,
            is_active=True,
        )
        with pytest.raises(AttributeError):
            doc.version_no = 2  # type: ignore[misc]


class TestVersionInfoContract:
    def test_has_version_id(self) -> None:
        info = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="abc123",
            is_active=True,
            status="active",
        )
        assert isinstance(info.version_id, uuid.UUID)

    def test_has_content_hash(self) -> None:
        info = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="sha256abc",
            is_active=True,
            status="active",
        )
        assert info.content_hash == "sha256abc"

    def test_has_is_active(self) -> None:
        info = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="abc",
            is_active=False,
            status="retired",
        )
        assert info.is_active is False

    def test_is_frozen(self) -> None:
        info = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="abc",
            is_active=True,
            status="active",
        )
        with pytest.raises(AttributeError):
            info.is_active = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Unit: RegistryWriter protocol has new methods
# ---------------------------------------------------------------------------


class TestRegistryWriterProtocol:
    def test_protocol_has_get_version(self) -> None:
        """RegistryWriter protocol must include get_version method."""
        assert hasattr(RegistryWriter, "get_version")

    def test_protocol_has_list_versions(self) -> None:
        """RegistryWriter protocol must include list_versions method."""
        assert hasattr(RegistryWriter, "list_versions")

    def test_protocol_has_get_active_version(self) -> None:
        """RegistryWriter protocol must include get_active_version method."""
        assert hasattr(RegistryWriter, "get_active_version")


# ---------------------------------------------------------------------------
# Unit: PostgresRegistryWriter._hash_file
# ---------------------------------------------------------------------------


class TestHashFile:
    def test_deterministic_hash(self, tmp_path: Path) -> None:
        file_a = tmp_path / "test.txt"
        file_a.write_text("hello world", encoding="utf-8")
        hash1 = PostgresRegistryWriter._hash_file(file_a)
        hash2 = PostgresRegistryWriter._hash_file(file_a)
        assert hash1 == hash2

    def test_different_content_different_hash(self, tmp_path: Path) -> None:
        file_a = tmp_path / "a.txt"
        file_a.write_text("content a", encoding="utf-8")
        file_b = tmp_path / "b.txt"
        file_b.write_text("content b", encoding="utf-8")
        assert PostgresRegistryWriter._hash_file(file_a) != PostgresRegistryWriter._hash_file(file_b)

    def test_same_content_same_hash(self, tmp_path: Path) -> None:
        file_a = tmp_path / "a.txt"
        file_a.write_text("identical content", encoding="utf-8")
        file_b = tmp_path / "b.txt"
        file_b.write_text("identical content", encoding="utf-8")
        assert PostgresRegistryWriter._hash_file(file_a) == PostgresRegistryWriter._hash_file(file_b)


# ---------------------------------------------------------------------------
# Unit: PostgresRegistryWriter._contract_key
# ---------------------------------------------------------------------------


class TestContractKey:
    def test_same_params_same_key(self) -> None:
        key1 = PostgresRegistryWriter._contract_key("Docling", "1.0", "normalized_char_offset")
        key2 = PostgresRegistryWriter._contract_key("Docling", "1.0", "normalized_char_offset")
        assert key1 == key2

    def test_different_parser_name_different_key(self) -> None:
        key1 = PostgresRegistryWriter._contract_key("Docling", "1.0", "normalized_char_offset")
        key2 = PostgresRegistryWriter._contract_key("Other", "1.0", "normalized_char_offset")
        assert key1 != key2

    def test_different_parser_version_different_key(self) -> None:
        key1 = PostgresRegistryWriter._contract_key("Docling", "1.0", "normalized_char_offset")
        key2 = PostgresRegistryWriter._contract_key("Docling", "2.0", "normalized_char_offset")
        assert key1 != key2

    def test_different_offset_basis_different_key(self) -> None:
        key1 = PostgresRegistryWriter._contract_key("Docling", "1.0", "normalized_char_offset")
        key2 = PostgresRegistryWriter._contract_key("Docling", "1.0", "char_offset")
        assert key1 != key2


# ===========================================================================
# LIVE TESTS -- require FORMAL_RUNTIME_DATABASE_URL
# ===========================================================================


def test_live_pdf_docling_to_postgres(tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db) -> None:
    sample_pdf = tmp_path / "formal-runtime-live.pdf"
    _build_rich_pdf(sample_pdf)
    registry = PostgresRegistryWriter(live_db_connection)
    pipeline = IngestionPipeline(
        registry=registry,
        bundle_root=tmp_path,
        connection_factory=lambda: live_db_connection,
        reconciler=_FakeReconciler(),
    )

    result = pipeline.ingest(sample_pdf, title="Formal runtime live ingestion")
    rows = registry.query_spans_by_version(result.version_id)

    assert result.spans
    assert len(rows) == len(result.spans)
    assert {row["raw_text"] for row in rows} == {span.text for span in result.spans}
    assert {row["version_id"] for row in rows} == {result.version_id}


# ---------------------------------------------------------------------------
# CORE-01: Stable document identity
# ---------------------------------------------------------------------------


def test_live_repeated_ingest_reuses_doc_id(tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db) -> None:
    """Ingesting the same file twice must return the same doc_id."""
    sample_pdf = tmp_path / "stable-identity.pdf"
    _build_pdf(sample_pdf, "Stable identity content")

    registry = PostgresRegistryWriter(live_db_connection)

    first = registry.register_document(
        source_path=sample_pdf,
        source_uri="file:///stable-identity.pdf",
        title="Stable identity test",
    )
    second = registry.register_document(
        source_path=sample_pdf,
        source_uri="file:///stable-identity.pdf",
        title="Stable identity test",
    )

    assert first.doc_id == second.doc_id, "Repeated ingest of same source_uri must return the same doc_id"


def test_live_different_source_uri_gets_different_doc_id(tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db) -> None:
    """Ingesting different source_uris must produce different doc_ids."""
    pdf_a = tmp_path / "doc-a.pdf"
    pdf_b = tmp_path / "doc-b.pdf"
    _build_pdf(pdf_a, "Content A")
    _build_pdf(pdf_b, "Content B")

    registry = PostgresRegistryWriter(live_db_connection)

    reg_a = registry.register_document(source_path=pdf_a, source_uri="file:///doc-a.pdf", title="A")
    reg_b = registry.register_document(source_path=pdf_b, source_uri="file:///doc-b.pdf", title="B")

    assert reg_a.doc_id != reg_b.doc_id


# ---------------------------------------------------------------------------
# CORE-02: Same content + same contract => idempotent
# ---------------------------------------------------------------------------


def test_live_same_content_same_contract_no_new_version(tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db) -> None:
    """Ingesting identical content with the same normalization contract must not create a new version."""
    sample_pdf = tmp_path / "idempotent.pdf"
    _build_pdf(sample_pdf, "Idempotent content")

    registry = PostgresRegistryWriter(live_db_connection)

    first = registry.register_document(
        source_path=sample_pdf,
        source_uri="file:///idempotent.pdf",
        title="Idempotent test",
    )
    second = registry.register_document(
        source_path=sample_pdf,
        source_uri="file:///idempotent.pdf",
        title="Idempotent test",
    )

    assert first.version_id == second.version_id, "Same content + same contract must return same version_id"


# ---------------------------------------------------------------------------
# CORE-02: Changed content => new version, old retired
# ---------------------------------------------------------------------------


def test_live_changed_content_creates_new_version(tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db) -> None:
    """Ingesting changed content must create a new version."""
    pdf_v1 = tmp_path / "changed-v1.pdf"
    _build_pdf(pdf_v1, "Version one content")

    registry = PostgresRegistryWriter(live_db_connection)

    first = registry.register_document(
        source_path=pdf_v1,
        source_uri="file:///changed-content.pdf",
        title="Changed content",
    )

    # Different content, same source_uri
    pdf_v2 = tmp_path / "changed-v2.pdf"
    _build_pdf(pdf_v2, "Version two content is different")

    second = registry.register_document(
        source_path=pdf_v2,
        source_uri="file:///changed-content.pdf",
        title="Changed content",
    )

    assert first.doc_id == second.doc_id, "Same source_uri must keep same doc_id"
    assert first.version_id != second.version_id, "Changed content must produce new version_id"


def test_live_changed_content_retires_old_version(tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db) -> None:
    """When a new version is created, the old version must be retired (is_active=False)."""
    pdf_v1 = tmp_path / "retire-v1.pdf"
    _build_pdf(pdf_v1, "First version")

    registry = PostgresRegistryWriter(live_db_connection)

    first = registry.register_document(
        source_path=pdf_v1,
        source_uri="file:///retire-test.pdf",
        title="Retire test",
    )
    assert first.is_active is True

    pdf_v2 = tmp_path / "retire-v2.pdf"
    _build_pdf(pdf_v2, "Second version different content")

    second = registry.register_document(
        source_path=pdf_v2,
        source_uri="file:///retire-test.pdf",
        title="Retire test",
    )

    first_refreshed = registry.get_version(first.version_id)
    assert first_refreshed.is_active is False, "Old version must be retired when new version is created"
    assert second.is_active is True, "New version must be active"


# ---------------------------------------------------------------------------
# CORE-04: Changed normalization contract => new version
# ---------------------------------------------------------------------------


def test_live_changed_normalization_contract_creates_new_version(tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db) -> None:
    """Same content but different normalization contract must create a new version."""
    sample_pdf = tmp_path / "contract-change.pdf"
    _build_pdf(sample_pdf, "Same content different contract")

    registry_v1 = PostgresRegistryWriter(
        live_db_connection,
        parser_name="Docling",
        parser_version="1.0",
    )

    first = registry_v1.register_document(
        source_path=sample_pdf,
        source_uri="file:///contract-change.pdf",
        title="Contract change test",
    )

    registry_v2 = PostgresRegistryWriter(
        live_db_connection,
        parser_name="Docling",
        parser_version="2.0",
    )

    second = registry_v2.register_document(
        source_path=sample_pdf,
        source_uri="file:///contract-change.pdf",
        title="Contract change test",
    )

    assert first.doc_id == second.doc_id, "Same source_uri must keep same doc_id"
    assert first.version_id != second.version_id, "Different normalization contract must produce new version_id"


def test_live_changed_normalization_contract_retires_old_version(tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db) -> None:
    """When a new version is created due to contract change, old version must be retired."""
    sample_pdf = tmp_path / "contract-retire.pdf"
    _build_pdf(sample_pdf, "Content for contract retire test")

    registry_v1 = PostgresRegistryWriter(
        live_db_connection,
        parser_name="Docling",
        parser_version="1.0",
    )

    first = registry_v1.register_document(
        source_path=sample_pdf,
        source_uri="file:///contract-retire.pdf",
        title="Contract retire test",
    )

    registry_v2 = PostgresRegistryWriter(
        live_db_connection,
        parser_name="Docling",
        parser_version="2.0",
    )

    second = registry_v2.register_document(
        source_path=sample_pdf,
        source_uri="file:///contract-retire.pdf",
        title="Contract retire test",
    )

    first_refreshed = registry_v1.get_version(first.version_id)
    assert first_refreshed.is_active is False, "Old version must be retired after contract change"
    assert second.is_active is True


# ---------------------------------------------------------------------------
# CORE-02: Version numbering
# ---------------------------------------------------------------------------


def test_live_version_no_increments_on_new_version(tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db) -> None:
    """Each new version for the same document must increment version_no."""
    pdf_v1 = tmp_path / "seq-v1.pdf"
    _build_pdf(pdf_v1, "Sequential version 1")

    registry = PostgresRegistryWriter(live_db_connection)

    first = registry.register_document(
        source_path=pdf_v1,
        source_uri="file:///sequential.pdf",
        title="Sequential test",
    )

    pdf_v2 = tmp_path / "seq-v2.pdf"
    _build_pdf(pdf_v2, "Sequential version 2")

    second = registry.register_document(
        source_path=pdf_v2,
        source_uri="file:///sequential.pdf",
        title="Sequential test",
    )

    assert first.version_no == 1
    assert second.version_no == 2


# ---------------------------------------------------------------------------
# Pipeline integration
# ---------------------------------------------------------------------------


def test_live_pipeline_idempotent_ingest_skips_parsing(tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db) -> None:
    """Calling pipeline.ingest twice on the same file must not re-parse or re-write spans."""
    sample_pdf = tmp_path / "pipeline-idempotent.pdf"
    _build_rich_pdf(sample_pdf)

    registry = PostgresRegistryWriter(live_db_connection)
    pipeline = IngestionPipeline(
        registry=registry,
        bundle_root=tmp_path,
        connection_factory=lambda: live_db_connection,
        reconciler=_FakeReconciler(),
    )

    result1 = pipeline.ingest(sample_pdf, title="Pipeline idempotent")
    result2 = pipeline.ingest(sample_pdf, title="Pipeline idempotent")

    assert result1.doc_id == result2.doc_id
    assert result1.version_id == result2.version_id
    assert {
        (span.span_id, span.text, span.page_no, span.heading_path, span.offset)
        for span in result1.spans
    } == {
        (span.span_id, span.text, span.page_no, span.heading_path, span.offset)
        for span in result2.spans
    }


def test_live_pipeline_changed_content_creates_new_version(tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db) -> None:
    """Ingesting changed content through the pipeline creates a new version.

    Uses the same file path (overwriting content) so the source_uri stays
    stable, which is required for doc_id reuse.
    """
    shared_pdf = tmp_path / "pipeline-shared.pdf"
    _build_rich_pdf(shared_pdf, text_body="Pipeline version one")

    registry = PostgresRegistryWriter(live_db_connection)
    pipeline = IngestionPipeline(
        registry=registry,
        bundle_root=tmp_path,
        connection_factory=lambda: live_db_connection,
        reconciler=_FakeReconciler(),
    )

    result1 = pipeline.ingest(shared_pdf, title="Pipeline versioning")

    # Overwrite the same file with different content
    _build_rich_pdf(shared_pdf, text_body="Pipeline version two is different")

    result2 = pipeline.ingest(shared_pdf, title="Pipeline versioning")

    assert result1.doc_id == result2.doc_id, "Same source_uri must keep same doc_id"
    assert result1.version_id != result2.version_id, "Changed content must produce new version_id"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_live_register_nonexistent_file_raises(live_db_connection, live_applied_schema, clean_live_db) -> None:
    """Registering a file that does not exist must raise FileNotFoundError."""
    registry = PostgresRegistryWriter(live_db_connection)
    with pytest.raises(FileNotFoundError):
        registry.register_document(
            source_path=Path("/nonexistent/file.pdf"),
            source_uri="file:///nonexistent/file.pdf",
        )


def test_live_three_versions_in_sequence(tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db) -> None:
    """Creating three sequential versions must retire v1 and v2, leaving only v3 active."""
    pdf_v1 = tmp_path / "three-v1.pdf"
    _build_pdf(pdf_v1, "Version one")

    registry = PostgresRegistryWriter(live_db_connection)

    v1 = registry.register_document(
        source_path=pdf_v1,
        source_uri="file:///three-versions.pdf",
        title="Three versions",
    )

    pdf_v2 = tmp_path / "three-v2.pdf"
    _build_pdf(pdf_v2, "Version two different")

    v2 = registry.register_document(
        source_path=pdf_v2,
        source_uri="file:///three-versions.pdf",
        title="Three versions",
    )

    pdf_v3 = tmp_path / "three-v3.pdf"
    _build_pdf(pdf_v3, "Version three different again")

    v3 = registry.register_document(
        source_path=pdf_v3,
        source_uri="file:///three-versions.pdf",
        title="Three versions",
    )

    assert v1.doc_id == v2.doc_id == v3.doc_id
    assert v1.version_no == 1
    assert v2.version_no == 2
    assert v3.version_no == 3

    assert registry.get_version(v1.version_id).is_active is False
    assert registry.get_version(v2.version_id).is_active is False
    assert registry.get_version(v3.version_id).is_active is True


def test_live_list_versions_for_document(tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db) -> None:
    """list_versions must return all versions for a document ordered by version_no."""
    pdf_v1 = tmp_path / "list-v1.pdf"
    _build_pdf(pdf_v1, "List version 1")

    registry = PostgresRegistryWriter(live_db_connection)

    v1 = registry.register_document(
        source_path=pdf_v1,
        source_uri="file:///list-versions.pdf",
        title="List versions",
    )

    pdf_v2 = tmp_path / "list-v2.pdf"
    _build_pdf(pdf_v2, "List version 2")

    v2 = registry.register_document(
        source_path=pdf_v2,
        source_uri="file:///list-versions.pdf",
        title="List versions",
    )

    versions = registry.list_versions(v1.doc_id)
    assert len(versions) == 2
    assert versions[0].version_no == 1
    assert versions[1].version_no == 2
    assert versions[0].version_id == v1.version_id
    assert versions[1].version_id == v2.version_id


def test_live_get_active_version(tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db) -> None:
    """get_active_version must return the single active version for a document."""
    pdf_v1 = tmp_path / "active-v1.pdf"
    _build_pdf(pdf_v1, "Active version 1")

    registry = PostgresRegistryWriter(live_db_connection)

    v1 = registry.register_document(
        source_path=pdf_v1,
        source_uri="file:///active-version.pdf",
        title="Active version test",
    )

    active = registry.get_active_version(v1.doc_id)
    assert active is not None
    assert active.version_id == v1.version_id
    assert active.is_active is True

    pdf_v2 = tmp_path / "active-v2.pdf"
    _build_pdf(pdf_v2, "Active version 2 different")

    v2 = registry.register_document(
        source_path=pdf_v2,
        source_uri="file:///active-version.pdf",
        title="Active version test",
    )

    active = registry.get_active_version(v1.doc_id)
    assert active is not None
    assert active.version_id == v2.version_id
    assert active.is_active is True


def test_live_get_active_version_returns_none_for_unknown_doc(live_db_connection, live_applied_schema, clean_live_db) -> None:
    """get_active_version must return None for a doc_id that does not exist."""
    registry = PostgresRegistryWriter(live_db_connection)
    unknown_id = uuid.uuid4()
    assert registry.get_active_version(unknown_id) is None


# ===========================================================================
# LIVE PROVENANCE VALIDATION SLICE
# ===========================================================================
#
# These tests verify that provenance fields from real Docling output are
# persisted correctly in the canonical_spans table:
# - page_no: which PDF page the span came from
# - heading_path: hierarchical heading structure from Docling
# - start_offset/end_offset: character offsets in the normalized text
# - row counts: exact number of spans persisted
# - repeat-ingest: provenance preserved on idempotent re-ingest
#
# ===========================================================================


def test_live_provenance_page_no_persisted(tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db) -> None:
    """Docling must emit page_no metadata and it must be persisted in canonical_spans.page_no."""
    sample_pdf = tmp_path / "provenance-page.pdf"
    _build_rich_pdf(sample_pdf)

    registry = PostgresRegistryWriter(live_db_connection)
    pipeline = IngestionPipeline(
        registry=registry,
        bundle_root=tmp_path,
        connection_factory=lambda: live_db_connection,
        reconciler=_FakeReconciler(),
    )

    result = pipeline.ingest(sample_pdf, title="Provenance page test")
    rows = registry.query_spans_by_version(result.version_id)

    # Verify at least one span has page_no persisted
    assert len(rows) > 0, "Must have at least one span"
    spans_with_page_no = [row for row in rows if row["page_no"] is not None]
    assert len(spans_with_page_no) > 0, "At least one span must have page_no persisted from Docling"

    # Verify the page_no values match the CanonicalSpan objects
    for row in spans_with_page_no:
        matching_span = next((s for s in result.spans if s.span_id == row["span_id"]), None)
        assert matching_span is not None, f"Span {row['span_id']} must exist in result"
        assert row["page_no"] == matching_span.page_no, f"page_no must match: DB={row['page_no']}, Span={matching_span.page_no}"


def test_live_provenance_heading_path_persisted(tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db) -> None:
    """Docling must emit heading metadata and it must be persisted in canonical_spans.heading_path."""
    sample_pdf = tmp_path / "provenance-heading.pdf"
    _build_rich_pdf(sample_pdf)

    registry = PostgresRegistryWriter(live_db_connection)
    pipeline = IngestionPipeline(
        registry=registry,
        bundle_root=tmp_path,
        connection_factory=lambda: live_db_connection,
        reconciler=_FakeReconciler(),
    )

    result = pipeline.ingest(sample_pdf, title="Provenance heading test")
    rows = registry.query_spans_by_version(result.version_id)

    # Verify spans have heading_path persisted (may be NULL for spans without headings)
    assert len(rows) > 0, "Must have at least one span"

    # Check that heading_path is persisted as a string with " > " separator
    for row in rows:
        matching_span = next((s for s in result.spans if s.span_id == row["span_id"]), None)
        assert matching_span is not None

        # Convert tuple to expected string format
        expected_heading_path = " > ".join(matching_span.headings) if matching_span.headings else None
        assert row["heading_path"] == expected_heading_path, \
            f"heading_path must match: DB={row['heading_path']}, Expected={expected_heading_path}"


def test_live_provenance_offsets_persisted(tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db) -> None:
    """Character offsets (start_offset, end_offset) must be persisted correctly."""
    sample_pdf = tmp_path / "provenance-offset.pdf"
    _build_rich_pdf(sample_pdf)

    registry = PostgresRegistryWriter(live_db_connection)
    pipeline = IngestionPipeline(
        registry=registry,
        bundle_root=tmp_path,
        connection_factory=lambda: live_db_connection,
        reconciler=_FakeReconciler(),
    )

    result = pipeline.ingest(sample_pdf, title="Provenance offset test")
    rows = registry.query_spans_by_version(result.version_id)

    assert len(rows) > 0, "Must have at least one span"

    # Verify start_offset and end_offset match the CanonicalSpan
    for row in rows:
        matching_span = next((s for s in result.spans if s.span_id == row["span_id"]), None)
        assert matching_span is not None

        expected_start = matching_span.offset
        expected_end = matching_span.offset + len(matching_span.text)

        assert row["start_offset"] == expected_start, \
            f"start_offset must match: DB={row['start_offset']}, Expected={expected_start}"
        assert row["end_offset"] == expected_end, \
            f"end_offset must match: DB={row['end_offset']}, Expected={expected_end}"
        assert row["end_offset"] > row["start_offset"], \
            "end_offset must be greater than start_offset (database constraint)"


def test_live_provenance_row_count_matches_spans(tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db) -> None:
    """The number of rows persisted must exactly match the number of spans produced by Docling."""
    sample_pdf = tmp_path / "provenance-count.pdf"
    _build_rich_pdf(sample_pdf)

    registry = PostgresRegistryWriter(live_db_connection)
    pipeline = IngestionPipeline(
        registry=registry,
        bundle_root=tmp_path,
        connection_factory=lambda: live_db_connection,
        reconciler=_FakeReconciler(),
    )

    result = pipeline.ingest(sample_pdf, title="Provenance count test")
    rows = registry.query_spans_by_version(result.version_id)

    # Exact match required
    assert len(rows) == len(result.spans), \
        f"Row count must match span count: rows={len(rows)}, spans={len(result.spans)}"

    # Each span must have a corresponding row
    span_ids_in_db = {row["span_id"] for row in rows}
    span_ids_in_result = {span.span_id for span in result.spans}
    assert span_ids_in_db == span_ids_in_result, "All span_ids must be present in database"


def test_live_provenance_repeat_ingest_preserves_all_fields(tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db) -> None:
    """Re-ingesting the same document must preserve all provenance fields exactly."""
    sample_pdf = tmp_path / "provenance-repeat.pdf"
    _build_rich_pdf(sample_pdf)

    registry = PostgresRegistryWriter(live_db_connection)
    pipeline = IngestionPipeline(
        registry=registry,
        bundle_root=tmp_path,
        connection_factory=lambda: live_db_connection,
        reconciler=_FakeReconciler(),
    )

    # First ingest
    result1 = pipeline.ingest(sample_pdf, title="Provenance repeat test")
    rows1 = registry.query_spans_by_version(result1.version_id)

    # Second ingest (idempotent - should skip parsing and reuse existing spans)
    result2 = pipeline.ingest(sample_pdf, title="Provenance repeat test")
    rows2 = registry.query_spans_by_version(result2.version_id)

    # Must reuse the same version
    assert result1.version_id == result2.version_id, "Idempotent ingest must reuse version_id"

    # Must preserve all provenance fields exactly
    assert len(rows1) == len(rows2), "Row count must be identical on repeat ingest"

    # Sort by start_offset for deterministic comparison
    rows1_sorted = sorted(rows1, key=lambda r: r["start_offset"])
    rows2_sorted = sorted(rows2, key=lambda r: r["start_offset"])

    for row1, row2 in zip(rows1_sorted, rows2_sorted):
        assert row1["span_id"] == row2["span_id"], "span_id must be preserved"
        assert row1["page_no"] == row2["page_no"], "page_no must be preserved"
        assert row1["heading_path"] == row2["heading_path"], "heading_path must be preserved"
        assert row1["start_offset"] == row2["start_offset"], "start_offset must be preserved"
        assert row1["end_offset"] == row2["end_offset"], "end_offset must be preserved"
        assert row1["raw_text"] == row2["raw_text"], "raw_text must be preserved"


def test_live_provenance_span_text_matches_raw_text(tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db) -> None:
    """The raw_text column must exactly match the normalized span text."""
    sample_pdf = tmp_path / "provenance-text.pdf"
    _build_rich_pdf(sample_pdf)

    registry = PostgresRegistryWriter(live_db_connection)
    pipeline = IngestionPipeline(
        registry=registry,
        bundle_root=tmp_path,
        connection_factory=lambda: live_db_connection,
        reconciler=_FakeReconciler(),
    )

    result = pipeline.ingest(sample_pdf, title="Provenance text test")
    rows = registry.query_spans_by_version(result.version_id)

    assert len(rows) > 0, "Must have at least one span"

    for row in rows:
        matching_span = next((s for s in result.spans if s.span_id == row["span_id"]), None)
        assert matching_span is not None
        assert row["raw_text"] == matching_span.text, \
            f"raw_text must match span.text: DB={row['raw_text']}, Span={matching_span.text}"


def test_live_provenance_multiple_pages_distinct_page_numbers(tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db) -> None:
    """A PDF with multiple pages must result in spans with distinct page_no values."""
    from PIL import Image, ImageDraw

    # Create a multi-page PDF
    sample_pdf = tmp_path / "provenance-multi-page.pdf"

    # Create first page
    image1 = Image.new("RGB", (1200, 1600), "white")
    draw1 = ImageDraw.Draw(image1)
    draw1.text((80, 80), "Page One Heading", fill="black")
    draw1.text((80, 180), "Content on page one.", fill="black")

    # Create second page
    image2 = Image.new("RGB", (1200, 1600), "white")
    draw2 = ImageDraw.Draw(image2)
    draw2.text((80, 80), "Page Two Heading", fill="black")
    draw2.text((80, 180), "Content on page two.", fill="black")

    # Save as multi-page PDF
    image1.save(sample_pdf, "PDF", save_all=True, append_images=[image2])

    registry = PostgresRegistryWriter(live_db_connection)
    pipeline = IngestionPipeline(
        registry=registry,
        bundle_root=tmp_path,
        connection_factory=lambda: live_db_connection,
        reconciler=_FakeReconciler(),
    )

    result = pipeline.ingest(sample_pdf, title="Provenance multi-page test")
    rows = registry.query_spans_by_version(result.version_id)

    # Verify spans came from multiple pages
    page_numbers = {row["page_no"] for row in rows if row["page_no"] is not None}
    assert len(page_numbers) > 1, "Multi-page PDF must produce spans from multiple pages"


def test_live_provenance_heading_hierarchy_preserved(tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db) -> None:
    """Heading hierarchy from Docling must be preserved as a flat string with ' > ' separator."""
    sample_pdf = tmp_path / "provenance-hierarchy.pdf"
    _build_rich_pdf(sample_pdf)

    registry = PostgresRegistryWriter(live_db_connection)
    pipeline = IngestionPipeline(
        registry=registry,
        bundle_root=tmp_path,
        connection_factory=lambda: live_db_connection,
        reconciler=_FakeReconciler(),
    )

    result = pipeline.ingest(sample_pdf, title="Provenance hierarchy test")
    rows = registry.query_spans_by_version(result.version_id)

    # Check that heading_path uses the correct separator
    for row in rows:
        if row["heading_path"]:
            # Should contain " > " separator if there are multiple levels
            parts = row["heading_path"].split(" > ")
            # Verify it matches the headings tuple from the span
            matching_span = next((s for s in result.spans if s.span_id == row["span_id"]), None)
            assert matching_span is not None
            assert tuple(parts) == matching_span.headings, \
                f"Heading hierarchy must match: DB={parts}, Span={matching_span.headings}"


# ===========================================================================
# CONCURRENCY SAFETY TESTS
# ===========================================================================
#
# These tests verify that the registry is safe under concurrent writes.
# The races identified:
# 1. register_document: read-then-write race on documents and version_no
#    - Two concurrent calls both SELECT for same source_uri, both see None,
#      both INSERT -> one hits UNIQUE violation on source_uri
#    - Two concurrent calls both compute MAX(version_no)+1, get same value,
#      both INSERT -> one hits UNIQUE(doc_id, version_no) violation
# 2. write_spans: idempotency check outside transaction, no ON CONFLICT
#    - Two concurrent calls both COUNT canonical_spans, both see 0,
#      both INSERT -> duplicate span_id or silent duplicate rows
#
# ===========================================================================


class TestConcurrencySqlPatterns:
    """Static tests that verify the SQL patterns used are concurrency-safe.

    These inspect the source code of PostgresRegistryWriter to confirm that
    INSERT statements use ON CONFLICT handling and that idempotency checks
    occur inside transactions. This is the most reliable way to unit-test
    concurrency safety without a live database.
    """

    def test_documents_insert_uses_on_conflict(self) -> None:
        """INSERT INTO documents must use ON CONFLICT (source_uri) to handle concurrent creation."""
        import inspect
        import textwrap

        source = inspect.getsource(PostgresRegistryWriter.register_document)
        # The INSERT INTO documents statement must include ON CONFLICT handling
        # to prevent IntegrityError when two concurrent calls both see no existing doc
        assert "ON CONFLICT" in source, (
            "register_document INSERT INTO documents must use ON CONFLICT "
            "to handle concurrent creation of same source_uri"
        )

    def test_normalization_contracts_insert_uses_on_conflict(self) -> None:
        """INSERT INTO normalization_contracts must use ON CONFLICT to handle concurrent creation."""
        import inspect

        source = inspect.getsource(PostgresRegistryWriter.register_document)
        # The INSERT INTO normalization_contracts must include ON CONFLICT
        # to prevent IntegrityError when two concurrent calls both see no existing contract
        assert source.count("ON CONFLICT") >= 2, (
            "register_document must use ON CONFLICT for both documents and normalization_contracts "
            "INSERT statements to handle concurrent creation"
        )

    def test_document_versions_insert_uses_on_conflict(self) -> None:
        """INSERT INTO document_versions must use ON CONFLICT to handle version_no race."""
        import inspect

        source = inspect.getsource(PostgresRegistryWriter.register_document)
        # The INSERT INTO document_versions must include ON CONFLICT handling
        # to prevent IntegrityError when two concurrent calls compute same version_no
        assert source.count("ON CONFLICT") >= 3, (
            "register_document must use ON CONFLICT for documents, normalization_contracts, "
            "AND document_versions INSERT statements to handle all concurrent races"
        )

    def test_write_spans_idempotency_check_inside_transaction(self) -> None:
        """write_spans must perform its idempotency check inside the same transaction as the INSERT."""
        import inspect

        source = inspect.getsource(PostgresRegistryWriter.write_spans)
        # The idempotency COUNT check must be inside the transaction block,
        # not before it. Currently the code does:
        #   with conn.cursor() as cur:  <-- outside transaction
        #       cur.execute("SELECT COUNT(*) ...")
        #   ...
        #   with conn.transaction() ...  <-- separate transaction
        #
        # This is a race: two concurrent calls both see COUNT=0, both insert.
        # The fix: the check and insert must be in the same transaction.
        # We verify this by checking there is only ONE transaction context
        # and the COUNT query is within it.
        lines = source.split("\n")
        transaction_depth = 0
        count_inside_transaction = False

        for line in lines:
            if ".transaction()" in line:
                transaction_depth += 1
            if "COUNT" in line and transaction_depth > 0:
                count_inside_transaction = True

        assert count_inside_transaction, (
            "write_spans idempotency check (SELECT COUNT) must be inside the "
            "transaction block, not outside it, to prevent TOCTOU race"
        )

    def test_write_spans_insert_uses_on_conflict(self) -> None:
        """INSERT INTO canonical_spans must use ON CONFLICT to handle duplicate span_id."""
        import inspect

        source = inspect.getsource(PostgresRegistryWriter.write_spans)
        # Even with the check inside the transaction, ON CONFLICT provides defense-in-depth
        # against concurrent inserts that both pass the COUNT check
        assert "ON CONFLICT" in source, (
            "write_spans INSERT INTO canonical_spans must use ON CONFLICT "
            "to handle duplicate span_id from concurrent writes"
        )


class TestConcurrencySafetyLive:
    """Live tests that verify concurrent writes are safe using real database.

    These use threading to simulate concurrent calls and verify that neither
    call raises an IntegrityError and that the final state is consistent.
    """

    def test_concurrent_register_same_source_uri(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Two concurrent register_document calls with same source_uri must both succeed."""
        import concurrent.futures

        sample_pdf = tmp_path / "concurrent-register.pdf"
        _build_pdf(sample_pdf, "Concurrent registration content")

        results: list[RegisteredDocument] = []
        errors: list[Exception] = []

        def register() -> RegisteredDocument:
            # Each thread needs its own connection for true concurrency
            import os

            db_url = os.environ.get("FORMAL_RUNTIME_DATABASE_URL")
            if not db_url:
                pytest.skip("FORMAL_RUNTIME_DATABASE_URL not set")

            with psycopg.connect(db_url) as conn:
                registry = PostgresRegistryWriter(conn)
                return registry.register_document(
                    source_path=sample_pdf,
                    source_uri="file:///concurrent-register.pdf",
                    title="Concurrent register test",
                )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(register) for _ in range(2)]
            for future in concurrent.futures.as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as exc:
                    errors.append(exc)

        # Both calls must succeed (no IntegrityError)
        assert len(errors) == 0, f"Concurrent register_document raised errors: {errors}"
        assert len(results) == 2, f"Expected 2 results, got {len(results)}"

        # Both must return the same doc_id
        assert results[0].doc_id == results[1].doc_id, (
            "Concurrent registers of same source_uri must return same doc_id"
        )

        # Verify database state: exactly one document row for this source_uri
        with live_db_connection.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM documents WHERE source_uri = %s",
                ("file:///concurrent-register.pdf",),
            )
            count = cur.fetchone()[0]
        assert count == 1, f"Expected exactly 1 document row, got {count}"

    def test_concurrent_register_different_content_same_doc(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Two concurrent register_document calls with different content for same source_uri.

        Both must succeed: one creates version_no=1, the other creates version_no=2.
        No IntegrityError on UNIQUE(doc_id, version_no).
        """
        import concurrent.futures

        pdf_v1 = tmp_path / "concurrent-v1.pdf"
        _build_pdf(pdf_v1, "Concurrent version one content")

        pdf_v2 = tmp_path / "concurrent-v2.pdf"
        _build_pdf(pdf_v2, "Concurrent version two content is different")

        results: list[RegisteredDocument] = []
        errors: list[Exception] = []

        def register(pdf_path: Path) -> RegisteredDocument:
            import os

            db_url = os.environ.get("FORMAL_RUNTIME_DATABASE_URL")
            if not db_url:
                pytest.skip("FORMAL_RUNTIME_DATABASE_URL not set")

            with psycopg.connect(db_url) as conn:
                registry = PostgresRegistryWriter(conn)
                return registry.register_document(
                    source_path=pdf_path,
                    source_uri="file:///concurrent-versions.pdf",
                    title="Concurrent versions test",
                )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(register, pdf_v1),
                executor.submit(register, pdf_v2),
            ]
            for future in concurrent.futures.as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as exc:
                    errors.append(exc)

        # Both calls must succeed (no IntegrityError)
        assert len(errors) == 0, f"Concurrent register_document raised errors: {errors}"
        assert len(results) == 2, f"Expected 2 results, got {len(results)}"

        # Both must return same doc_id
        assert results[0].doc_id == results[1].doc_id, (
            "Same source_uri must produce same doc_id"
        )

        # version_no values must be distinct (1 and 2)
        version_nos = sorted([r.version_no for r in results])
        assert version_nos == [1, 2], f"Expected version_nos [1, 2], got {version_nos}"

    def test_concurrent_write_spans_same_version(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Two concurrent write_spans calls with same version_id must be idempotent."""
        import concurrent.futures
        import os

        sample_pdf = tmp_path / "concurrent-spans.pdf"
        _build_pdf(sample_pdf, "Concurrent spans content")

        # First, register the document to get a version_id
        registry = PostgresRegistryWriter(live_db_connection)
        registered = registry.register_document(
            source_path=sample_pdf,
            source_uri="file:///concurrent-spans.pdf",
            title="Concurrent spans test",
        )

        # Create test spans
        span = CanonicalSpan(
            doc_id=registered.doc_id,
            span_id=uuid.uuid4(),
            version_id=registered.version_id,
            text="Concurrent span text",
            offset=0,
            page_no=1,
            headings=(),
        )

        errors: list[Exception] = []

        def write_spans() -> None:
            db_url = os.environ.get("FORMAL_RUNTIME_DATABASE_URL")
            if not db_url:
                pytest.skip("FORMAL_RUNTIME_DATABASE_URL not set")

            with psycopg.connect(db_url) as conn:
                writer = PostgresRegistryWriter(conn)
                writer.write_spans(version_id=registered.version_id, spans=[span])

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(write_spans) for _ in range(2)]
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as exc:
                    errors.append(exc)

        # Both calls must succeed (no IntegrityError)
        assert len(errors) == 0, f"Concurrent write_spans raised errors: {errors}"

        # Verify database state: exactly one row per span (no duplicates)
        with live_db_connection.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM canonical_spans WHERE version_id = %s",
                (str(registered.version_id),),
            )
            count = cur.fetchone()[0]
        assert count == 1, f"Expected exactly 1 span row (idempotent), got {count}"
