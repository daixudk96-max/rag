"""Tests for the minimal incremental processing orchestrator.

These tests verify staged batch processors can:
1. Query versions in the expected processing_status bucket
2. Advance successful versions to the next status
3. Return summary counts of processed versions
4. Mark failed versions on exception
5. Preserve existing document status machinery

Covered stages in this slice:
- registered -> parsed
- parsed -> chunks_created
- chunks_created -> embedded
- embedded -> tree_built
- tree_built -> entities_extracted
- entities_extracted -> complete

This remains a minimal proof-of-concept, NOT a full 7-stage LightRAG pipeline.
"""

from __future__ import annotations

import uuid
from unittest.mock import Mock, patch

import pytest

from llamaindex_runtime.registry.contracts import VersionInfo
from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter


# ===========================================================================
# UNIT TESTS -- Mock-based tests for orchestrator contract
# ===========================================================================


class TestIncrementalProcessorContract:
    """Tests for the IncrementalProcessor contract and behavior."""

    def test_processor_has_process_registered_method(self) -> None:
        """IncrementalProcessor must have process_registered_batch method."""
        # Import will fail initially - this is the RED phase
        try:
            from llamaindex_runtime.processing.orchestrator import IncrementalProcessor

            assert hasattr(IncrementalProcessor, "process_registered_batch")
        except ImportError:
            pytest.fail(
                "IncrementalProcessor not yet implemented - expected RED failure"
            )

    def test_processor_queries_registered_versions(self) -> None:
        """Processor must query all active versions with processing_status='registered'."""
        from llamaindex_runtime.processing.orchestrator import IncrementalProcessor

        # Mock registry
        mock_registry = Mock(spec=PostgresRegistryWriter)

        # Create mock versions in 'registered' status
        version_a = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="hash_a",
            is_active=True,
            status="active",
            processing_status="registered",
        )
        version_b = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="hash_b",
            is_active=True,
            status="active",
            processing_status="registered",
        )

        mock_registry.query_by_processing_status.return_value = [version_a, version_b]

        # Mock processing function that always succeeds
        mock_process_fn = Mock(return_value=None)

        processor = IncrementalProcessor(registry=mock_registry)
        _ = processor.process_registered_batch(process_fn=mock_process_fn)

        # Verify processor queried for 'registered' status
        mock_registry.query_by_processing_status.assert_called_once_with("registered")

    def test_processor_advances_registered_to_parsed(self) -> None:
        """Processor must advance versions from 'registered' to 'parsed' on success."""
        from llamaindex_runtime.processing.orchestrator import IncrementalProcessor

        mock_registry = Mock(spec=PostgresRegistryWriter)

        version_a = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="hash_a",
            is_active=True,
            status="active",
            processing_status="registered",
        )

        mock_registry.query_by_processing_status.return_value = [version_a]
        mock_registry.update_processing_status.return_value = None

        # Mock successful processing
        mock_process_fn = Mock(return_value=None)

        processor = IncrementalProcessor(registry=mock_registry)
        _ = processor.process_registered_batch(process_fn=mock_process_fn)

        # Verify status was advanced to 'parsed'
        mock_registry.update_processing_status.assert_called_once_with(
            version_id=version_a.version_id,
            processing_status="parsed",
        )

    def test_processor_returns_summary_count(self) -> None:
        """Processor must return a summary with count of processed versions."""
        from llamaindex_runtime.processing.orchestrator import IncrementalProcessor

        mock_registry = Mock(spec=PostgresRegistryWriter)

        # Three versions in 'registered' status
        versions = [
            VersionInfo(
                version_id=uuid.uuid4(),
                doc_id=uuid.uuid4(),
                version_no=1,
                content_hash=f"hash_{i}",
                is_active=True,
                status="active",
                processing_status="registered",
            )
            for i in range(3)
        ]

        mock_registry.query_by_processing_status.return_value = versions
        mock_registry.update_processing_status.return_value = None

        mock_process_fn = Mock(return_value=None)

        processor = IncrementalProcessor(registry=mock_registry)
        result = processor.process_registered_batch(process_fn=mock_process_fn)

        # Result must have a 'processed_count' field
        assert hasattr(result, "processed_count")
        assert result.processed_count == 3

    def test_processor_marks_failed_on_exception(self) -> None:
        """Processor must mark version as 'failed' if processing raises exception."""
        from llamaindex_runtime.processing.orchestrator import IncrementalProcessor

        mock_registry = Mock(spec=PostgresRegistryWriter)

        version_a = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="hash_a",
            is_active=True,
            status="active",
            processing_status="registered",
        )

        mock_registry.query_by_processing_status.return_value = [version_a]
        mock_registry.update_processing_status.return_value = None

        # Mock processing function that raises exception
        mock_process_fn = Mock(side_effect=RuntimeError("Processing failed"))

        processor = IncrementalProcessor(registry=mock_registry)
        result = processor.process_registered_batch(process_fn=mock_process_fn)

        # Verify status was marked as 'failed'
        mock_registry.update_processing_status.assert_any_call(
            version_id=version_a.version_id,
            processing_status="failed",
        )

        # Verify result has failed count
        assert hasattr(result, "failed_count")
        assert result.failed_count >= 1

    def test_processor_calls_process_fn_with_version_info(self) -> None:
        """Processor must invoke process_fn with each version's information."""
        from llamaindex_runtime.processing.orchestrator import IncrementalProcessor

        mock_registry = Mock(spec=PostgresRegistryWriter)

        version_a = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="hash_a",
            is_active=True,
            status="active",
            processing_status="registered",
        )

        mock_registry.query_by_processing_status.return_value = [version_a]
        mock_registry.update_processing_status.return_value = None

        mock_process_fn = Mock(return_value=None)

        processor = IncrementalProcessor(registry=mock_registry)
        _ = processor.process_registered_batch(process_fn=mock_process_fn)

        # Verify process_fn was called with version_info
        mock_process_fn.assert_called_once_with(version_info=version_a)


class TestLightRAGCallbackFactories:
    def test_tree_entity_extraction_callback_writes_entities_links_and_evidence(
        self,
    ) -> None:
        from llamaindex_runtime.processing.callbacks import (
            build_tree_entity_extraction_callback,
        )

        version_info = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="hash-a",
            is_active=True,
            status="active",
            processing_status="tree_built",
        )

        mock_registry = Mock(spec=PostgresRegistryWriter)
        node_a = uuid.uuid4()
        node_b = uuid.uuid4()
        span_a = uuid.uuid4()
        span_b = uuid.uuid4()
        mock_registry.query_tree_nodes_by_version.return_value = [
            {
                "node_id": node_a,
                "title": "PM2.5",
                "heading_path": "Concepts > PM2.5",
                "summary_text": "Fine particles",
            },
            {
                "node_id": node_b,
                "title": "AQI",
                "heading_path": "Concepts > AQI",
                "summary_text": "Air quality index",
            },
        ]
        mock_registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": node_a, "span_id": span_a, "ordinal_no": 0},
            {"node_id": node_b, "span_id": span_b, "ordinal_no": 0},
        ]
        mock_registry.query_node_entity_links_by_version.return_value = []
        mock_registry.query_evidence_links_by_version.return_value = []
        mock_registry.transaction = None

        callback = build_tree_entity_extraction_callback(mock_registry)
        callback(version_info=version_info)

        written_entities = mock_registry.write_entities.call_args.kwargs["entities"]
        written_node_links = mock_registry.write_node_entity_links.call_args.kwargs[
            "links"
        ]
        written_evidence = mock_registry.write_evidence_links.call_args.kwargs[
            "evidence_links"
        ]

        assert len(written_entities) == 2
        assert {entity["entity_key"] for entity in written_entities} == {
            "concept:pm25",
            "concept:aqi",
        }
        assert len(written_node_links) == 2
        assert len(written_evidence) == 2

    def test_tree_entity_extraction_callback_merges_duplicate_entity_keys(self) -> None:
        from llamaindex_runtime.processing.callbacks import (
            build_tree_entity_extraction_callback,
        )

        version_info = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="hash-b",
            is_active=True,
            status="active",
            processing_status="tree_built",
        )

        mock_registry = Mock(spec=PostgresRegistryWriter)
        node_a = uuid.uuid4()
        node_b = uuid.uuid4()
        span_a = uuid.uuid4()
        span_b = uuid.uuid4()
        mock_registry.query_tree_nodes_by_version.return_value = [
            {
                "node_id": node_a,
                "title": "PM2.5",
                "heading_path": "Concepts > PM2.5",
                "summary_text": "Fine particles",
            },
            {
                "node_id": node_b,
                "title": "PM2.5",
                "heading_path": "Concepts > PM2.5",
                "summary_text": "Repeated concept",
            },
        ]
        mock_registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": node_a, "span_id": span_a, "ordinal_no": 0},
            {"node_id": node_b, "span_id": span_b, "ordinal_no": 0},
        ]
        mock_registry.query_node_entity_links_by_version.return_value = []
        mock_registry.query_evidence_links_by_version.return_value = []
        mock_registry.transaction = None

        callback = build_tree_entity_extraction_callback(mock_registry)
        callback(version_info=version_info)

        written_entities = mock_registry.write_entities.call_args.kwargs["entities"]
        written_node_links = mock_registry.write_node_entity_links.call_args.kwargs[
            "links"
        ]

        assert len(written_entities) == 1
        assert len(written_node_links) == 2
        assert written_node_links[0]["entity_id"] == written_node_links[1]["entity_id"]

    def test_tree_entity_extraction_callback_is_idempotent_when_outputs_exist(
        self,
    ) -> None:
        from llamaindex_runtime.processing.callbacks import (
            build_tree_entity_extraction_callback,
        )

        version_info = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="hash-idem",
            is_active=True,
            status="active",
            processing_status="tree_built",
        )

        mock_registry = Mock(spec=PostgresRegistryWriter)
        mock_registry.query_node_entity_links_by_version.return_value = [
            {"node_id": uuid.uuid4(), "entity_id": uuid.uuid4()}
        ]
        mock_registry.query_evidence_links_by_version.return_value = [
            {"span_id": uuid.uuid4(), "entity_id": uuid.uuid4()}
        ]

        callback = build_tree_entity_extraction_callback(mock_registry)
        callback(version_info=version_info)

        mock_registry.write_entities.assert_not_called()
        mock_registry.write_node_entity_links.assert_not_called()
        mock_registry.write_evidence_links.assert_not_called()

    def test_tree_entity_extraction_callback_repairs_partial_state(self) -> None:
        from llamaindex_runtime.processing.callbacks import (
            build_tree_entity_extraction_callback,
        )

        version_info = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="hash-partial",
            is_active=True,
            status="active",
            processing_status="tree_built",
        )

        mock_registry = Mock(spec=PostgresRegistryWriter)
        node_id = uuid.uuid4()
        span_id = uuid.uuid4()
        mock_registry.query_tree_nodes_by_version.return_value = [
            {
                "node_id": node_id,
                "title": "PM2.5",
                "heading_path": "Concepts > PM2.5",
                "summary_text": "Fine particles",
            },
        ]
        mock_registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": node_id, "span_id": span_id, "ordinal_no": 0},
        ]
        mock_registry.query_node_entity_links_by_version.return_value = [
            {"node_id": node_id, "entity_id": uuid.uuid4()}
        ]
        mock_registry.query_evidence_links_by_version.return_value = []
        mock_registry.transaction = None

        callback = build_tree_entity_extraction_callback(mock_registry)
        callback(version_info=version_info)

        mock_registry.write_entities.assert_called_once()
        mock_registry.write_node_entity_links.assert_called_once()
        mock_registry.write_evidence_links.assert_called_once()

    def test_finalize_callback_rejects_missing_extraction_outputs(self) -> None:
        from llamaindex_runtime.processing.callbacks import build_finalize_callback

        version_info = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="hash-d",
            is_active=True,
            status="active",
            processing_status="entities_extracted",
        )

        mock_registry = Mock(spec=PostgresRegistryWriter)
        mock_registry.query_node_entity_links_by_version.return_value = []
        mock_registry.query_evidence_links_by_version.return_value = []

        callback = build_finalize_callback(mock_registry)

        with pytest.raises(ValueError, match="extraction outputs"):
            callback(version_info=version_info)


# ===========================================================================
# INTEGRATION TESTS -- Minimal tests with existing pipeline machinery
# ===========================================================================


def test_processor_preserves_existing_status_behavior() -> None:
    """Incremental processor must not break existing document status transitions."""
    # This test verifies that the existing DocumentStatus.valid_transitions()
    # machinery continues to work with the new orchestrator
    from llamaindex_runtime.registry.contracts import DocumentStatus

    # Valid transitions must still be defined
    assert DocumentStatus.REGISTERED.can_transition_to(DocumentStatus.PARSED)
    assert DocumentStatus.REGISTERED.can_transition_to(DocumentStatus.FAILED)

    # Invalid transitions must still be rejected
    assert not DocumentStatus.REGISTERED.can_transition_to(DocumentStatus.COMPLETE)


def test_processor_result_dataclass_has_required_fields() -> None:
    """ProcessingResult must have summary fields."""
    try:
        from llamaindex_runtime.processing.orchestrator import ProcessingResult

        result = ProcessingResult(
            processed_count=1,
            failed_count=0,
            total_count=1,
        )

        assert result.processed_count == 1
        assert result.failed_count == 0
        assert result.total_count == 1
    except ImportError:
        pytest.fail("ProcessingResult not yet implemented - expected RED failure")


# ===========================================================================
# PARSED -> CHUNKS_CREATED STAGE TESTS
# ===========================================================================


class TestParsedToChunksCreatedStage:
    """Tests for the parsed -> chunks_created processing stage."""

    def test_processor_has_process_parsed_method(self) -> None:
        """IncrementalProcessor must have process_parsed_batch method."""
        from llamaindex_runtime.processing.orchestrator import IncrementalProcessor

        assert hasattr(IncrementalProcessor, "process_parsed_batch")

    def test_processor_queries_parsed_versions(self) -> None:
        """Processor must query all active versions with processing_status='parsed'."""
        from llamaindex_runtime.processing.orchestrator import IncrementalProcessor

        mock_registry = Mock(spec=PostgresRegistryWriter)

        version_a = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="hash_a",
            is_active=True,
            status="active",
            processing_status="parsed",
        )
        version_b = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="hash_b",
            is_active=True,
            status="active",
            processing_status="parsed",
        )

        mock_registry.query_by_processing_status.return_value = [version_a, version_b]

        # Mock chunk creation function that always succeeds
        mock_chunk_fn = Mock(return_value=None)

        processor = IncrementalProcessor(registry=mock_registry)
        _ = processor.process_parsed_batch(chunk_fn=mock_chunk_fn)

        # Verify processor queried for 'parsed' status
        mock_registry.query_by_processing_status.assert_called_once_with("parsed")

    def test_processor_advances_parsed_to_chunks_created(self) -> None:
        """Processor must advance versions from 'parsed' to 'chunks_created' on success."""
        from llamaindex_runtime.processing.orchestrator import IncrementalProcessor

        mock_registry = Mock(spec=PostgresRegistryWriter)

        version_a = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="hash_a",
            is_active=True,
            status="active",
            processing_status="parsed",
        )

        mock_registry.query_by_processing_status.return_value = [version_a]
        mock_registry.update_processing_status.return_value = None

        # Mock successful chunk creation
        mock_chunk_fn = Mock(return_value=None)

        processor = IncrementalProcessor(registry=mock_registry)
        _ = processor.process_parsed_batch(chunk_fn=mock_chunk_fn)

        # Verify status was advanced to 'chunks_created'
        mock_registry.update_processing_status.assert_called_once_with(
            version_id=version_a.version_id,
            processing_status="chunks_created",
        )

    def test_processor_returns_summary_count_for_parsed_stage(self) -> None:
        """Processor must return a summary with count of processed versions for parsed stage."""
        from llamaindex_runtime.processing.orchestrator import IncrementalProcessor

        mock_registry = Mock(spec=PostgresRegistryWriter)

        # Three versions in 'parsed' status
        versions = [
            VersionInfo(
                version_id=uuid.uuid4(),
                doc_id=uuid.uuid4(),
                version_no=1,
                content_hash=f"hash_{i}",
                is_active=True,
                status="active",
                processing_status="parsed",
            )
            for i in range(3)
        ]

        mock_registry.query_by_processing_status.return_value = versions
        mock_registry.update_processing_status.return_value = None

        mock_chunk_fn = Mock(return_value=None)

        processor = IncrementalProcessor(registry=mock_registry)
        result = processor.process_parsed_batch(chunk_fn=mock_chunk_fn)

        # Result must have a 'processed_count' field
        assert hasattr(result, "processed_count")
        assert result.processed_count == 3
        assert result.total_count == 3
        assert result.failed_count == 0

    def test_processor_marks_failed_on_chunk_exception(self) -> None:
        """Processor must mark version as 'failed' if chunk creation raises exception."""
        from llamaindex_runtime.processing.orchestrator import IncrementalProcessor

        mock_registry = Mock(spec=PostgresRegistryWriter)

        version_a = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="hash_a",
            is_active=True,
            status="active",
            processing_status="parsed",
        )

        mock_registry.query_by_processing_status.return_value = [version_a]
        mock_registry.update_processing_status.return_value = None

        # Mock chunk creation function that raises exception
        mock_chunk_fn = Mock(side_effect=RuntimeError("Chunk creation failed"))

        processor = IncrementalProcessor(registry=mock_registry)
        result = processor.process_parsed_batch(chunk_fn=mock_chunk_fn)

        # Verify status was marked as 'failed'
        mock_registry.update_processing_status.assert_any_call(
            version_id=version_a.version_id,
            processing_status="failed",
        )

        # Verify result has failed count
        assert hasattr(result, "failed_count")
        assert result.failed_count >= 1

    def test_processor_calls_chunk_fn_with_version_info(self) -> None:
        """Processor must invoke chunk_fn with each version's information."""
        from llamaindex_runtime.processing.orchestrator import IncrementalProcessor

        mock_registry = Mock(spec=PostgresRegistryWriter)

        version_a = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="hash_a",
            is_active=True,
            status="active",
            processing_status="parsed",
        )

        mock_registry.query_by_processing_status.return_value = [version_a]
        mock_registry.update_processing_status.return_value = None

        mock_chunk_fn = Mock(return_value=None)

        processor = IncrementalProcessor(registry=mock_registry)
        _ = processor.process_parsed_batch(chunk_fn=mock_chunk_fn)

        # Verify chunk_fn was called with version_info
        mock_chunk_fn.assert_called_once_with(version_info=version_a)


# ===========================================================================
# CHUNKS_CREATED -> EMBEDDED STAGE TESTS
# ===========================================================================


class TestChunksCreatedToEmbeddedStage:
    """Tests for the chunks_created -> embedded processing stage."""

    def test_processor_has_process_chunks_created_method(self) -> None:
        """IncrementalProcessor must have process_chunks_created_batch method."""
        from llamaindex_runtime.processing.orchestrator import IncrementalProcessor

        assert hasattr(IncrementalProcessor, "process_chunks_created_batch")

    def test_processor_queries_chunks_created_versions(self) -> None:
        """Processor must query all active versions with processing_status='chunks_created'."""
        from llamaindex_runtime.processing.orchestrator import IncrementalProcessor

        mock_registry = Mock(spec=PostgresRegistryWriter)

        version_a = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="hash_a",
            is_active=True,
            status="active",
            processing_status="chunks_created",
        )
        version_b = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="hash_b",
            is_active=True,
            status="active",
            processing_status="chunks_created",
        )

        mock_registry.query_by_processing_status.return_value = [version_a, version_b]

        # Mock validation function that always succeeds
        mock_validate_fn = Mock(return_value=None)

        processor = IncrementalProcessor(registry=mock_registry)
        _ = processor.process_chunks_created_batch(validate_fn=mock_validate_fn)

        # Verify processor queried for 'chunks_created' status
        mock_registry.query_by_processing_status.assert_called_once_with(
            "chunks_created"
        )

    def test_processor_advances_chunks_created_to_embedded(self) -> None:
        """Processor must advance versions from 'chunks_created' to 'embedded' on success."""
        from llamaindex_runtime.processing.orchestrator import IncrementalProcessor

        mock_registry = Mock(spec=PostgresRegistryWriter)

        version_a = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="hash_a",
            is_active=True,
            status="active",
            processing_status="chunks_created",
        )

        mock_registry.query_by_processing_status.return_value = [version_a]
        mock_registry.update_processing_status.return_value = None

        # Mock successful validation
        mock_validate_fn = Mock(return_value=None)

        processor = IncrementalProcessor(registry=mock_registry)
        _ = processor.process_chunks_created_batch(validate_fn=mock_validate_fn)

        # Verify status was advanced to 'embedded'
        mock_registry.update_processing_status.assert_called_once_with(
            version_id=version_a.version_id,
            processing_status="embedded",
        )

    def test_processor_returns_summary_count_for_chunks_created_stage(self) -> None:
        """Processor must return a summary with count of processed versions for chunks_created stage."""
        from llamaindex_runtime.processing.orchestrator import IncrementalProcessor

        mock_registry = Mock(spec=PostgresRegistryWriter)

        # Three versions in 'chunks_created' status
        versions = [
            VersionInfo(
                version_id=uuid.uuid4(),
                doc_id=uuid.uuid4(),
                version_no=1,
                content_hash=f"hash_{i}",
                is_active=True,
                status="active",
                processing_status="chunks_created",
            )
            for i in range(3)
        ]

        mock_registry.query_by_processing_status.return_value = versions
        mock_registry.update_processing_status.return_value = None

        mock_validate_fn = Mock(return_value=None)

        processor = IncrementalProcessor(registry=mock_registry)
        result = processor.process_chunks_created_batch(validate_fn=mock_validate_fn)

        # Result must have a 'processed_count' field
        assert hasattr(result, "processed_count")
        assert result.processed_count == 3
        assert result.total_count == 3
        assert result.failed_count == 0

    def test_processor_marks_failed_on_validation_exception(self) -> None:
        """Processor must mark version as 'failed' if validation raises exception."""
        from llamaindex_runtime.processing.orchestrator import IncrementalProcessor

        mock_registry = Mock(spec=PostgresRegistryWriter)

        version_a = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="hash_a",
            is_active=True,
            status="active",
            processing_status="chunks_created",
        )

        mock_registry.query_by_processing_status.return_value = [version_a]
        mock_registry.update_processing_status.return_value = None

        # Mock validation function that raises exception
        mock_validate_fn = Mock(side_effect=RuntimeError("Validation failed"))

        processor = IncrementalProcessor(registry=mock_registry)
        result = processor.process_chunks_created_batch(validate_fn=mock_validate_fn)

        # Verify status was marked as 'failed'
        mock_registry.update_processing_status.assert_any_call(
            version_id=version_a.version_id,
            processing_status="failed",
        )

        # Verify result has failed count
        assert hasattr(result, "failed_count")
        assert result.failed_count >= 1

    def test_processor_calls_validate_fn_with_version_info(self) -> None:
        """Processor must invoke validate_fn with each version's information."""
        from llamaindex_runtime.processing.orchestrator import IncrementalProcessor

        mock_registry = Mock(spec=PostgresRegistryWriter)

        version_a = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="hash_a",
            is_active=True,
            status="active",
            processing_status="chunks_created",
        )

        mock_registry.query_by_processing_status.return_value = [version_a]
        mock_registry.update_processing_status.return_value = None

        mock_validate_fn = Mock(return_value=None)

        processor = IncrementalProcessor(registry=mock_registry)
        _ = processor.process_chunks_created_batch(validate_fn=mock_validate_fn)

        # Verify validate_fn was called with version_info
        mock_validate_fn.assert_called_once_with(version_info=version_a)


# ===========================================================================
# EMBEDDED -> TREE_BUILT STAGE TESTS
# ===========================================================================


class TestEmbeddedToTreeBuiltStage:
    """Tests for the embedded -> tree_built processing stage."""

    def test_processor_has_process_embedded_method(self) -> None:
        """IncrementalProcessor must have process_embedded_batch method."""
        from llamaindex_runtime.processing.orchestrator import IncrementalProcessor

        assert hasattr(IncrementalProcessor, "process_embedded_batch")

    def test_processor_queries_embedded_versions(self) -> None:
        """Processor must query all active versions with processing_status='embedded'."""
        from llamaindex_runtime.processing.orchestrator import IncrementalProcessor

        mock_registry = Mock(spec=PostgresRegistryWriter)

        version_a = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="hash_a",
            is_active=True,
            status="active",
            processing_status="embedded",
        )
        version_b = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="hash_b",
            is_active=True,
            status="active",
            processing_status="embedded",
        )

        mock_registry.query_by_processing_status.return_value = [version_a, version_b]

        # Mock tree generation function that always succeeds
        mock_tree_fn = Mock(return_value=None)

        processor = IncrementalProcessor(registry=mock_registry)
        _ = processor.process_embedded_batch(tree_fn=mock_tree_fn)

        # Verify processor queried for 'embedded' status
        mock_registry.query_by_processing_status.assert_called_once_with("embedded")

    def test_processor_advances_embedded_to_tree_built(self) -> None:
        """Processor must advance versions from 'embedded' to 'tree_built' on success."""
        from llamaindex_runtime.processing.orchestrator import IncrementalProcessor

        mock_registry = Mock(spec=PostgresRegistryWriter)

        version_a = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="hash_a",
            is_active=True,
            status="active",
            processing_status="embedded",
        )

        mock_registry.query_by_processing_status.return_value = [version_a]
        mock_registry.update_processing_status.return_value = None

        # Mock successful tree generation
        mock_tree_fn = Mock(return_value=None)

        processor = IncrementalProcessor(registry=mock_registry)
        _ = processor.process_embedded_batch(tree_fn=mock_tree_fn)

        # Verify status was advanced to 'tree_built'
        mock_registry.update_processing_status.assert_called_once_with(
            version_id=version_a.version_id,
            processing_status="tree_built",
        )

    def test_processor_returns_summary_count_for_embedded_stage(self) -> None:
        """Processor must return a summary with count of processed versions for embedded stage."""
        from llamaindex_runtime.processing.orchestrator import IncrementalProcessor

        mock_registry = Mock(spec=PostgresRegistryWriter)

        # Three versions in 'embedded' status
        versions = [
            VersionInfo(
                version_id=uuid.uuid4(),
                doc_id=uuid.uuid4(),
                version_no=1,
                content_hash=f"hash_{i}",
                is_active=True,
                status="active",
                processing_status="embedded",
            )
            for i in range(3)
        ]

        mock_registry.query_by_processing_status.return_value = versions
        mock_registry.update_processing_status.return_value = None

        mock_tree_fn = Mock(return_value=None)

        processor = IncrementalProcessor(registry=mock_registry)
        result = processor.process_embedded_batch(tree_fn=mock_tree_fn)

        # Result must have a 'processed_count' field
        assert hasattr(result, "processed_count")
        assert result.processed_count == 3
        assert result.total_count == 3
        assert result.failed_count == 0

    def test_processor_marks_failed_on_tree_exception(self) -> None:
        """Processor must mark version as 'failed' if tree generation raises exception."""
        from llamaindex_runtime.processing.orchestrator import IncrementalProcessor

        mock_registry = Mock(spec=PostgresRegistryWriter)

        version_a = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="hash_a",
            is_active=True,
            status="active",
            processing_status="embedded",
        )

        mock_registry.query_by_processing_status.return_value = [version_a]
        mock_registry.update_processing_status.return_value = None

        # Mock tree generation function that raises exception
        mock_tree_fn = Mock(side_effect=RuntimeError("Tree generation failed"))

        processor = IncrementalProcessor(registry=mock_registry)
        result = processor.process_embedded_batch(tree_fn=mock_tree_fn)

        # Verify status was marked as 'failed'
        mock_registry.update_processing_status.assert_any_call(
            version_id=version_a.version_id,
            processing_status="failed",
        )

        # Verify result has failed count
        assert hasattr(result, "failed_count")
        assert result.failed_count >= 1

    def test_processor_calls_tree_fn_with_version_info(self) -> None:
        """Processor must invoke tree_fn with each version's information."""
        from llamaindex_runtime.processing.orchestrator import IncrementalProcessor

        mock_registry = Mock(spec=PostgresRegistryWriter)

        version_a = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="hash_a",
            is_active=True,
            status="active",
            processing_status="embedded",
        )

        mock_registry.query_by_processing_status.return_value = [version_a]
        mock_registry.update_processing_status.return_value = None

        mock_tree_fn = Mock(return_value=None)

        processor = IncrementalProcessor(registry=mock_registry)
        _ = processor.process_embedded_batch(tree_fn=mock_tree_fn)

        # Verify tree_fn was called with version_info
        mock_tree_fn.assert_called_once_with(version_info=version_a)


# ===========================================================================
# TREE_BUILT -> ENTITIES_EXTRACTED STAGE TESTS
# ===========================================================================


class TestTreeBuiltToEntitiesExtractedStage:
    """Tests for the tree_built -> entities_extracted processing stage."""

    def test_processor_has_process_tree_built_method(self) -> None:
        """IncrementalProcessor must have process_tree_built_batch method."""
        from llamaindex_runtime.processing.orchestrator import IncrementalProcessor

        assert hasattr(IncrementalProcessor, "process_tree_built_batch")

    def test_processor_queries_tree_built_versions(self) -> None:
        """Processor must query all active versions with processing_status='tree_built'."""
        from llamaindex_runtime.processing.orchestrator import IncrementalProcessor

        mock_registry = Mock(spec=PostgresRegistryWriter)

        version_a = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="hash_a",
            is_active=True,
            status="active",
            processing_status="tree_built",
        )
        version_b = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="hash_b",
            is_active=True,
            status="active",
            processing_status="tree_built",
        )

        mock_registry.query_by_processing_status.return_value = [version_a, version_b]

        # Mock entity extraction function that always succeeds
        mock_extract_fn = Mock(return_value=None)

        processor = IncrementalProcessor(registry=mock_registry)
        _ = processor.process_tree_built_batch(extract_fn=mock_extract_fn)

        # Verify processor queried for 'tree_built' status
        mock_registry.query_by_processing_status.assert_called_once_with("tree_built")

    def test_processor_advances_tree_built_to_entities_extracted(self) -> None:
        """Processor must advance versions from 'tree_built' to 'entities_extracted' on success."""
        from llamaindex_runtime.processing.orchestrator import IncrementalProcessor

        mock_registry = Mock(spec=PostgresRegistryWriter)

        version_a = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="hash_a",
            is_active=True,
            status="active",
            processing_status="tree_built",
        )

        mock_registry.query_by_processing_status.return_value = [version_a]
        mock_registry.update_processing_status.return_value = None

        # Mock successful entity extraction
        mock_extract_fn = Mock(return_value=None)

        processor = IncrementalProcessor(registry=mock_registry)
        _ = processor.process_tree_built_batch(extract_fn=mock_extract_fn)

        # Verify status was advanced to 'entities_extracted'
        mock_registry.update_processing_status.assert_called_once_with(
            version_id=version_a.version_id,
            processing_status="entities_extracted",
        )

    def test_processor_returns_summary_count_for_tree_built_stage(self) -> None:
        """Processor must return a summary with count of processed versions for tree_built stage."""
        from llamaindex_runtime.processing.orchestrator import IncrementalProcessor

        mock_registry = Mock(spec=PostgresRegistryWriter)

        # Three versions in 'tree_built' status
        versions = [
            VersionInfo(
                version_id=uuid.uuid4(),
                doc_id=uuid.uuid4(),
                version_no=1,
                content_hash=f"hash_{i}",
                is_active=True,
                status="active",
                processing_status="tree_built",
            )
            for i in range(3)
        ]

        mock_registry.query_by_processing_status.return_value = versions
        mock_registry.update_processing_status.return_value = None

        mock_extract_fn = Mock(return_value=None)

        processor = IncrementalProcessor(registry=mock_registry)
        result = processor.process_tree_built_batch(extract_fn=mock_extract_fn)

        # Result must have a 'processed_count' field
        assert hasattr(result, "processed_count")
        assert result.processed_count == 3
        assert result.total_count == 3
        assert result.failed_count == 0

    def test_processor_marks_failed_on_extract_exception(self) -> None:
        """Processor must mark version as 'failed' if entity extraction raises exception."""
        from llamaindex_runtime.processing.orchestrator import IncrementalProcessor

        mock_registry = Mock(spec=PostgresRegistryWriter)

        version_a = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="hash_a",
            is_active=True,
            status="active",
            processing_status="tree_built",
        )

        mock_registry.query_by_processing_status.return_value = [version_a]
        mock_registry.update_processing_status.return_value = None

        # Mock entity extraction function that raises exception
        mock_extract_fn = Mock(side_effect=RuntimeError("Entity extraction failed"))

        processor = IncrementalProcessor(registry=mock_registry)
        result = processor.process_tree_built_batch(extract_fn=mock_extract_fn)

        # Verify status was marked as 'failed'
        mock_registry.update_processing_status.assert_any_call(
            version_id=version_a.version_id,
            processing_status="failed",
        )

        # Verify result has failed count
        assert hasattr(result, "failed_count")
        assert result.failed_count >= 1

    def test_processor_calls_extract_fn_with_version_info(self) -> None:
        """Processor must invoke extract_fn with each version's information."""
        from llamaindex_runtime.processing.orchestrator import IncrementalProcessor

        mock_registry = Mock(spec=PostgresRegistryWriter)

        version_a = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="hash_a",
            is_active=True,
            status="active",
            processing_status="tree_built",
        )

        mock_registry.query_by_processing_status.return_value = [version_a]
        mock_registry.update_processing_status.return_value = None

        mock_extract_fn = Mock(return_value=None)

        processor = IncrementalProcessor(registry=mock_registry)
        _ = processor.process_tree_built_batch(extract_fn=mock_extract_fn)

        # Verify extract_fn was called with version_info
        mock_extract_fn.assert_called_once_with(version_info=version_a)


# ===========================================================================
# ENTITIES_EXTRACTED -> COMPLETE STAGE TESTS
# ===========================================================================


class TestEntitiesExtractedToCompleteStage:
    """Tests for the entities_extracted -> complete processing stage."""

    def test_processor_has_process_entities_extracted_method(self) -> None:
        """IncrementalProcessor must have process_entities_extracted_batch method."""
        from llamaindex_runtime.processing.orchestrator import IncrementalProcessor

        assert hasattr(IncrementalProcessor, "process_entities_extracted_batch")

    def test_processor_queries_entities_extracted_versions(self) -> None:
        """Processor must query all active versions with processing_status='entities_extracted'."""
        from llamaindex_runtime.processing.orchestrator import IncrementalProcessor

        mock_registry = Mock(spec=PostgresRegistryWriter)

        version_a = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="hash_a",
            is_active=True,
            status="active",
            processing_status="entities_extracted",
        )
        version_b = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="hash_b",
            is_active=True,
            status="active",
            processing_status="entities_extracted",
        )

        mock_registry.query_by_processing_status.return_value = [version_a, version_b]

        # Mock finalization function that always succeeds
        mock_finalize_fn = Mock(return_value=None)

        processor = IncrementalProcessor(registry=mock_registry)
        _ = processor.process_entities_extracted_batch(finalize_fn=mock_finalize_fn)

        # Verify processor queried for 'entities_extracted' status
        mock_registry.query_by_processing_status.assert_called_once_with(
            "entities_extracted"
        )

    def test_processor_advances_entities_extracted_to_complete(self) -> None:
        """Processor must advance versions from 'entities_extracted' to 'complete' on success."""
        from llamaindex_runtime.processing.orchestrator import IncrementalProcessor

        mock_registry = Mock(spec=PostgresRegistryWriter)

        version_a = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="hash_a",
            is_active=True,
            status="active",
            processing_status="entities_extracted",
        )

        mock_registry.query_by_processing_status.return_value = [version_a]
        mock_registry.update_processing_status.return_value = None

        # Mock successful finalization
        mock_finalize_fn = Mock(return_value=None)

        processor = IncrementalProcessor(registry=mock_registry)
        _ = processor.process_entities_extracted_batch(finalize_fn=mock_finalize_fn)

        # Verify status was advanced to 'complete'
        mock_registry.update_processing_status.assert_called_once_with(
            version_id=version_a.version_id,
            processing_status="complete",
        )

    def test_processor_returns_summary_count_for_entities_extracted_stage(self) -> None:
        """Processor must return a summary with count of processed versions for entities_extracted stage."""
        from llamaindex_runtime.processing.orchestrator import IncrementalProcessor

        mock_registry = Mock(spec=PostgresRegistryWriter)

        # Three versions in 'entities_extracted' status
        versions = [
            VersionInfo(
                version_id=uuid.uuid4(),
                doc_id=uuid.uuid4(),
                version_no=1,
                content_hash=f"hash_{i}",
                is_active=True,
                status="active",
                processing_status="entities_extracted",
            )
            for i in range(3)
        ]

        mock_registry.query_by_processing_status.return_value = versions
        mock_registry.update_processing_status.return_value = None

        mock_finalize_fn = Mock(return_value=None)

        processor = IncrementalProcessor(registry=mock_registry)
        result = processor.process_entities_extracted_batch(
            finalize_fn=mock_finalize_fn
        )

        # Result must have a 'processed_count' field
        assert hasattr(result, "processed_count")
        assert result.processed_count == 3
        assert result.total_count == 3
        assert result.failed_count == 0

    def test_processor_marks_failed_on_finalize_exception(self) -> None:
        """Processor must mark version as 'failed' if finalization raises exception."""
        from llamaindex_runtime.processing.orchestrator import IncrementalProcessor

        mock_registry = Mock(spec=PostgresRegistryWriter)

        version_a = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="hash_a",
            is_active=True,
            status="active",
            processing_status="entities_extracted",
        )

        mock_registry.query_by_processing_status.return_value = [version_a]
        mock_registry.update_processing_status.return_value = None

        # Mock finalization function that raises exception
        mock_finalize_fn = Mock(side_effect=RuntimeError("Finalization failed"))

        processor = IncrementalProcessor(registry=mock_registry)
        result = processor.process_entities_extracted_batch(
            finalize_fn=mock_finalize_fn
        )

        # Verify status was marked as 'failed'
        mock_registry.update_processing_status.assert_any_call(
            version_id=version_a.version_id,
            processing_status="failed",
        )

        # Verify result has failed count
        assert hasattr(result, "failed_count")
        assert result.failed_count >= 1

    def test_processor_calls_finalize_fn_with_version_info(self) -> None:
        """Processor must invoke finalize_fn with each version's information."""
        from llamaindex_runtime.processing.orchestrator import IncrementalProcessor

        mock_registry = Mock(spec=PostgresRegistryWriter)

        version_a = VersionInfo(
            version_id=uuid.uuid4(),
            doc_id=uuid.uuid4(),
            version_no=1,
            content_hash="hash_a",
            is_active=True,
            status="active",
            processing_status="entities_extracted",
        )

        mock_registry.query_by_processing_status.return_value = [version_a]
        mock_registry.update_processing_status.return_value = None

        mock_finalize_fn = Mock(return_value=None)

        processor = IncrementalProcessor(registry=mock_registry)
        _ = processor.process_entities_extracted_batch(finalize_fn=mock_finalize_fn)

        # Verify finalize_fn was called with version_info
        mock_finalize_fn.assert_called_once_with(version_info=version_a)
