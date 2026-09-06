"""Minimal incremental processing orchestrator for LightRAG-style status stages.

This is a proof-of-concept slice demonstrating that the existing processing_status
state machine can drive a real batch/update pipeline. NOT a full 7-stage LightRAG pipeline.

Scope:
- Query active versions in 'registered' status and advance to 'parsed'
- Query active versions in 'parsed' status and advance to 'chunks_created'
- Query active versions in 'chunks_created' status and advance to 'embedded'
- Query active versions in 'embedded' status and advance to 'tree_built'
- Query active versions in 'tree_built' status and advance to 'entities_extracted'
- Query active versions in 'entities_extracted' status and advance to 'complete'
- Mark failures as 'failed'
- Return summary counts
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Protocol
from uuid import UUID

from llamaindex_runtime.registry.contracts import VersionInfo

logger = logging.getLogger(__name__)

STAGE_PROCESSING_EXCEPTIONS = (ConnectionError, OSError, RuntimeError, ValueError)


@dataclass(frozen=True)
class ProcessingResult:
    """Summary of batch processing operation."""

    processed_count: int
    failed_count: int
    total_count: int


class RegistryWriterProtocol(Protocol):
    """Minimal protocol for registry operations needed by processor."""

    def query_by_processing_status(self, processing_status: str) -> list[VersionInfo]: ...

    def update_processing_status(self, *, version_id: UUID, processing_status: str) -> None: ...


class ProcessFn(Protocol):
    """Processing callback for a single version."""

    def __call__(self, *, version_info: VersionInfo) -> None: ...


class IncrementalProcessor:
    """Minimal batch processor for six LightRAG-style status transitions.

    Supported transitions:
    - registered -> parsed
    - parsed -> chunks_created
    - chunks_created -> embedded
    - embedded -> tree_built
    - tree_built -> entities_extracted
    - entities_extracted -> complete
    """

    def __init__(self, *, registry: RegistryWriterProtocol) -> None:
        self._registry = registry

    def process_registered_batch(
        self,
        *,
        process_fn: ProcessFn,
    ) -> ProcessingResult:
        """Process all active versions in 'registered' status.

        Parameters
        ----------
        process_fn:
            Function to process each version. Receives version_info as kwarg.
            Should return None on success, or raise exception on failure.

        Returns
        -------
        ProcessingResult
            Summary with processed_count, failed_count, total_count
        """
        # Query all active versions in 'registered' status
        registered_versions = self._registry.query_by_processing_status("registered")

        processed_count = 0
        failed_count = 0
        total_count = len(registered_versions)

        for version_info in registered_versions:
            try:
                # Invoke processing function with version_info
                process_fn(version_info=version_info)

                # Success: advance to 'parsed'
                self._registry.update_processing_status(
                    version_id=version_info.version_id,
                    processing_status="parsed",
                )
                processed_count += 1

            except STAGE_PROCESSING_EXCEPTIONS:
                logger.exception(
                    "incremental processing failed for version %s",
                    version_info.version_id,
                )
                # Failure: mark as 'failed'
                self._registry.update_processing_status(
                    version_id=version_info.version_id,
                    processing_status="failed",
                )
                failed_count += 1

        return ProcessingResult(
            processed_count=processed_count,
            failed_count=failed_count,
            total_count=total_count,
        )

    def process_parsed_batch(
        self,
        *,
        chunk_fn: ProcessFn,
    ) -> ProcessingResult:
        """Process all active versions in 'parsed' status to create chunks.

        Parameters
        ----------
        chunk_fn:
            Function to create chunks for each version. Receives version_info as kwarg.
            Should return None on success, or raise exception on failure.

        Returns
        -------
        ProcessingResult
            Summary with processed_count, failed_count, total_count
        """
        # Query all active versions in 'parsed' status
        parsed_versions = self._registry.query_by_processing_status("parsed")

        processed_count = 0
        failed_count = 0
        total_count = len(parsed_versions)

        for version_info in parsed_versions:
            try:
                # Invoke chunk creation function with version_info
                chunk_fn(version_info=version_info)

                # Success: advance to 'chunks_created'
                self._registry.update_processing_status(
                    version_id=version_info.version_id,
                    processing_status="chunks_created",
                )
                processed_count += 1

            except STAGE_PROCESSING_EXCEPTIONS:
                logger.exception(
                    "chunk creation failed for version %s",
                    version_info.version_id,
                )
                # Failure: mark as 'failed'
                self._registry.update_processing_status(
                    version_id=version_info.version_id,
                    processing_status="failed",
                )
                failed_count += 1

        return ProcessingResult(
            processed_count=processed_count,
            failed_count=failed_count,
            total_count=total_count,
        )

    def process_chunks_created_batch(
        self,
        *,
        validate_fn: ProcessFn,
    ) -> ProcessingResult:
        """Process all active versions in 'chunks_created' status to validate and embed.

        Parameters
        ----------
        validate_fn:
            Function to validate vector-related artifacts for each version. Receives version_info as kwarg.
            Should return None on success, or raise exception on failure.

        Returns
        -------
        ProcessingResult
            Summary with processed_count, failed_count, total_count
        """
        # Query all active versions in 'chunks_created' status
        chunks_created_versions = self._registry.query_by_processing_status("chunks_created")

        processed_count = 0
        failed_count = 0
        total_count = len(chunks_created_versions)

        for version_info in chunks_created_versions:
            try:
                # Invoke validation function with version_info
                validate_fn(version_info=version_info)

                # Success: advance to 'embedded'
                self._registry.update_processing_status(
                    version_id=version_info.version_id,
                    processing_status="embedded",
                )
                processed_count += 1

            except STAGE_PROCESSING_EXCEPTIONS:
                logger.exception(
                    "validation/embedding failed for version %s",
                    version_info.version_id,
                )
                # Failure: mark as 'failed'
                self._registry.update_processing_status(
                    version_id=version_info.version_id,
                    processing_status="failed",
                )
                failed_count += 1

        return ProcessingResult(
            processed_count=processed_count,
            failed_count=failed_count,
            total_count=total_count,
        )

    def process_embedded_batch(
        self,
        *,
        tree_fn: ProcessFn,
    ) -> ProcessingResult:
        """Process all active versions in 'embedded' status to generate tree structures.

        Parameters
        ----------
        tree_fn:
            Function to generate tree structures for each version. Receives version_info as kwarg.
            Should return None on success, or raise exception on failure.

        Returns
        -------
        ProcessingResult
            Summary with processed_count, failed_count, total_count
        """
        # Query all active versions in 'embedded' status
        embedded_versions = self._registry.query_by_processing_status("embedded")

        processed_count = 0
        failed_count = 0
        total_count = len(embedded_versions)

        for version_info in embedded_versions:
            try:
                # Invoke tree generation function with version_info
                tree_fn(version_info=version_info)

                # Success: advance to 'tree_built'
                self._registry.update_processing_status(
                    version_id=version_info.version_id,
                    processing_status="tree_built",
                )
                processed_count += 1

            except STAGE_PROCESSING_EXCEPTIONS:
                logger.exception(
                    "tree generation failed for version %s",
                    version_info.version_id,
                )
                # Failure: mark as 'failed'
                self._registry.update_processing_status(
                    version_id=version_info.version_id,
                    processing_status="failed",
                )
                failed_count += 1

        return ProcessingResult(
            processed_count=processed_count,
            failed_count=failed_count,
            total_count=total_count,
        )

    def process_tree_built_batch(
        self,
        *,
        extract_fn: ProcessFn,
    ) -> ProcessingResult:
        """Process all active versions in 'tree_built' status to extract entities.

        Parameters
        ----------
        extract_fn:
            Function to extract entities for each version. Receives version_info as kwarg.
            Should return None on success, or raise exception on failure.

        Returns
        -------
        ProcessingResult
            Summary with processed_count, failed_count, total_count
        """
        # Query all active versions in 'tree_built' status
        tree_built_versions = self._registry.query_by_processing_status("tree_built")

        processed_count = 0
        failed_count = 0
        total_count = len(tree_built_versions)

        for version_info in tree_built_versions:
            try:
                # Invoke entity extraction function with version_info
                extract_fn(version_info=version_info)

                # Success: advance to 'entities_extracted'
                self._registry.update_processing_status(
                    version_id=version_info.version_id,
                    processing_status="entities_extracted",
                )
                processed_count += 1

            except STAGE_PROCESSING_EXCEPTIONS:
                logger.exception(
                    "entity extraction failed for version %s",
                    version_info.version_id,
                )
                # Failure: mark as 'failed'
                self._registry.update_processing_status(
                    version_id=version_info.version_id,
                    processing_status="failed",
                )
                failed_count += 1

        return ProcessingResult(
            processed_count=processed_count,
            failed_count=failed_count,
            total_count=total_count,
        )

    def process_entities_extracted_batch(
        self,
        *,
        finalize_fn: ProcessFn,
    ) -> ProcessingResult:
        """Process all active versions in 'entities_extracted' status to finalize and complete.

        Parameters
        ----------
        finalize_fn:
            Function to perform final validation/cleanup for each version. Receives version_info as kwarg.
            Should return None on success, or raise exception on failure.

        Returns
        -------
        ProcessingResult
            Summary with processed_count, failed_count, total_count
        """
        # Query all active versions in 'entities_extracted' status
        entities_extracted_versions = self._registry.query_by_processing_status("entities_extracted")

        processed_count = 0
        failed_count = 0
        total_count = len(entities_extracted_versions)

        for version_info in entities_extracted_versions:
            try:
                # Invoke finalization function with version_info
                finalize_fn(version_info=version_info)

                # Success: advance to 'complete'
                self._registry.update_processing_status(
                    version_id=version_info.version_id,
                    processing_status="complete",
                )
                processed_count += 1

            except STAGE_PROCESSING_EXCEPTIONS:
                logger.exception(
                    "finalization failed for version %s",
                    version_info.version_id,
                )
                # Failure: mark as 'failed'
                self._registry.update_processing_status(
                    version_id=version_info.version_id,
                    processing_status="failed",
                )
                failed_count += 1

        return ProcessingResult(
            processed_count=processed_count,
            failed_count=failed_count,
            total_count=total_count,
        )