from __future__ import annotations

import hashlib
import uuid
from collections.abc import Mapping
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from typing import Any, Sequence

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from llamaindex_runtime.interfaces import CanonicalSpan
from llamaindex_runtime.okf.contracts import validate_relation_qualifiers

from .contracts import RegisteredDocument, RegistryWriter, VersionInfo

DEFAULT_PARSER_NAME = "Docling"
DEFAULT_OFFSET_BASIS = "normalized_char_offset"


class PostgresRegistryWriter(RegistryWriter):
    def __init__(
        self,
        connection: psycopg.Connection,
        *,
        parser_name: str = DEFAULT_PARSER_NAME,
        parser_version: str | None = None,
        offset_basis: str = DEFAULT_OFFSET_BASIS,
    ) -> None:
        self._connection = connection
        self._parser_name = parser_name
        self._parser_version = parser_version or self._detect_parser_version()
        self._offset_basis = offset_basis

        # Ensure autocommit for tree_nodes persistence
        # Without autocommit, transaction rollback on connection close causes data loss
        # Can only set autocommit when connection is in IDLE status (not in transaction)
        try:
            if not self._connection.autocommit:
                self._connection.autocommit = True
        except psycopg.ProgrammingError as e:
            # Connection is in transaction status, can't change autocommit
            # This is a critical error - data will not persist without autocommit
            raise RuntimeError(
                f"Cannot enable autocommit on connection in transaction status. "
                f"Data writes will not persist. Connection must be in IDLE status. "
                f"Original error: {e}"
            ) from e

        # Register pgvector adapter for VECTOR column type
        register_vector(self._connection)

    def healthcheck(self) -> bool:
        with self._connection.cursor() as cur:
            cur.execute("SELECT 1")
            return cur.fetchone() == (1,)

    def transaction(self):
        return self._connection.transaction()

    def register_document(
        self,
        *,
        source_path: Path,
        source_uri: str,
        title: str | None = None,
    ) -> RegisteredDocument:
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")
        content_hash = self._hash_file(source_path)
        document_title = title or source_path.stem

        with self._connection.transaction(), self._connection.cursor(
            row_factory=dict_row
        ) as cur:
            # 1. Insert document with ON CONFLICT to handle concurrent creation of same source_uri.
            #    If another transaction already inserted this source_uri, we reuse its doc_id.
            doc_id = uuid.uuid4()
            cur.execute(
                "INSERT INTO documents (doc_id, source_uri, title, doc_type) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (source_uri) DO UPDATE SET title = COALESCE(EXCLUDED.title, documents.title) "
                "RETURNING doc_id",
                (str(doc_id), source_uri, document_title, "document"),
            )
            doc_id = uuid.UUID(str(cur.fetchone()["doc_id"]))

            # 2. Insert normalization contract with ON CONFLICT to handle concurrent creation.
            normalization_contract_id = uuid.uuid4()
            cur.execute(
                "INSERT INTO normalization_contracts (normalization_contract_id, parser_name, parser_version, offset_basis, notes) VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (parser_name, parser_version, offset_basis) DO NOTHING "
                "RETURNING normalization_contract_id",
                (
                    str(normalization_contract_id),
                    self._parser_name,
                    self._parser_version,
                    self._offset_basis,
                    "formal-runtime-ingestion",
                ),
            )
            contract_row = cur.fetchone()
            if contract_row is not None:
                normalization_contract_id = uuid.UUID(
                    str(contract_row["normalization_contract_id"])
                )
            else:
                # ON CONFLICT DO NOTHING => another transaction won; look up existing
                cur.execute(
                    "SELECT normalization_contract_id FROM normalization_contracts WHERE parser_name = %s AND parser_version = %s AND offset_basis = %s",
                    (self._parser_name, self._parser_version, self._offset_basis),
                )
                normalization_contract_id = uuid.UUID(
                    str(cur.fetchone()["normalization_contract_id"])
                )

            # 3. Insert version with concurrency-safe handling.
            #    We use a retry loop because:
            #    a) Two concurrent calls with same content+contract may both compute
            #       the same version_no; ON CONFLICT (doc_id, version_no) catches this.
            #    b) Two concurrent calls with different content may also compute the
            #       same version_no; ON CONFLICT catches this too, and we retry with
            #       a fresh version_no computed from the now-committed data.
            #    c) A concurrent call may commit our same content+contract between our
            #       check and INSERT; re-checking at the top of each iteration handles this.
            #
            #    P4: Initialize processing_status='registered' for new versions.
            max_attempts = 3
            version_id = uuid.uuid4()  # will be overwritten in the loop
            version_no = 1  # will be overwritten in the loop

            for _attempt in range(max_attempts):
                # Re-check for existing version with same content + same contract.
                # In READ COMMITTED, each statement gets a fresh snapshot, so this
                # catches versions committed by concurrent transactions since the
                # last iteration.
                cur.execute(
                    "SELECT version_id, version_no, is_active, processing_status FROM document_versions "
                    "WHERE doc_id = %s AND content_hash = %s AND normalization_contract_id = %s",
                    (str(doc_id), content_hash, str(normalization_contract_id)),
                )
                existing_version = cur.fetchone()

                if existing_version is not None:
                    # Idempotent: same content + same contract => return existing version
                    return RegisteredDocument(
                        doc_id=doc_id,
                        version_id=uuid.UUID(str(existing_version["version_id"])),
                        source_uri=source_uri,
                        version_no=existing_version["version_no"],
                        is_active=existing_version["is_active"],
                    )

                # Retire the current active version(s) before inserting a new active one.
                # This satisfies the partial unique index requiring at most one
                # active version per doc_id.
                cur.execute(
                    "UPDATE document_versions SET is_active = FALSE, status = 'retired', retired_at = now() "
                    "WHERE doc_id = %s AND is_active = TRUE",
                    (str(doc_id),),
                )

                # Compute version_no atomically via subquery, and use ON CONFLICT
                # to handle the race where two concurrent calls both get the same value.
                # P4: Initialize processing_status='registered' and registered_at=now()
                version_id = uuid.uuid4()
                cur.execute(
                    "INSERT INTO document_versions (version_id, doc_id, content_hash, version_no, normalization_contract_id, is_active, status, processing_status, registered_at, activated_at) "
                    "VALUES (%s, %s, %s, (SELECT COALESCE(MAX(v.version_no), 0) + 1 FROM document_versions v WHERE v.doc_id = %s), %s, %s, %s, %s, now(), now()) "
                    "ON CONFLICT (doc_id, version_no) DO UPDATE SET version_no = document_versions.version_no "
                    "RETURNING version_id, version_no",
                    (
                        str(version_id),
                        str(doc_id),
                        content_hash,
                        str(doc_id),
                        str(normalization_contract_id),
                        True,
                        "active",
                        "registered",  # P4: LightRAG-style initial processing status
                    ),
                )
                inserted_version = cur.fetchone()
                returned_version_id = uuid.UUID(str(inserted_version["version_id"]))
                version_no = inserted_version["version_no"]

                if returned_version_id == version_id:
                    # Our INSERT succeeded (no conflict)
                    break
                # ON CONFLICT fired: another transaction won the version_no race.
                # Loop back to re-check content+contract and retry.
            else:
                # All attempts exhausted (extremely unlikely under normal load).
                # Re-check content+contract one final time: a concurrent call may
                # have committed our exact content+contract between attempts.
                cur.execute(
                    "SELECT version_id, version_no, is_active, processing_status FROM document_versions "
                    "WHERE doc_id = %s AND content_hash = %s AND normalization_contract_id = %s",
                    (str(doc_id), content_hash, str(normalization_contract_id)),
                )
                final_existing = cur.fetchone()
                if final_existing is not None:
                    return RegisteredDocument(
                        doc_id=doc_id,
                        version_id=uuid.UUID(str(final_existing["version_id"])),
                        source_uri=source_uri,
                        version_no=final_existing["version_no"],
                        is_active=final_existing["is_active"],
                    )
                # Extremely rare: concurrent contention with different content on
                # every attempt. The last ON CONFLICT result is a version with
                # different content. We cannot claim it as ours. Raise a clear error.
                raise RuntimeError(
                    f"Failed to register version for doc_id={doc_id} after {max_attempts} "
                    f"attempts due to concurrent contention. Retry the operation."
                )

        return RegisteredDocument(
            doc_id=doc_id,
            version_id=version_id,
            source_uri=source_uri,
            version_no=version_no,
            is_active=True,
        )

    def update_processing_status(
        self,
        *,
        version_id: uuid.UUID,
        processing_status: str,
    ) -> None:
        """Update the processing status of a version.

        P4 LightRAG-style incremental processing status tracking.
        Validates that the transition follows the correct ordering.

        Parameters
        ----------
        version_id:
            The version to update.
        processing_status:
            The new processing status (must be a valid DocumentStatus value).

        Raises
        ------
        ValueError
            If the version doesn't exist or the transition is invalid.
        """
        from .contracts import DocumentStatus

        # Get current status to validate transition
        current_info = self.get_version(version_id)
        current_status = DocumentStatus(current_info.processing_status)

        # Validate the new status is a valid DocumentStatus enum value
        try:
            new_status = DocumentStatus(processing_status)
        except ValueError:
            raise ValueError(
                f"Invalid processing_status '{processing_status}'. "
                f"Must be one of: {[s.value for s in DocumentStatus]}"
            )

        # Validate transition ordering (except FAILED which can be set from any stage)
        if (
            new_status != DocumentStatus.FAILED
            and not current_status.can_transition_to(new_status)
        ):
            raise ValueError(
                f"Invalid status transition from '{current_status.value}' to '{new_status.value}'. "
                f"Valid transitions: {DocumentStatus.valid_transitions()}"
            )

        with self._connection.transaction(), self._connection.cursor(
            row_factory=dict_row
        ) as cur:
            cur.execute(
                "UPDATE document_versions SET processing_status = %s "
                "WHERE version_id = %s",
                (processing_status, str(version_id)),
            )

    def query_by_processing_status(
        self,
        processing_status: str,
    ) -> list[VersionInfo]:
        """Query all active versions with a specific processing status.

        P4 LightRAG-style incremental processing: enables batch processing
        of documents at the same stage (e.g., all documents needing parsing).

        Parameters
        ----------
        processing_status:
            The processing status to query for.

        Returns
        -------
        list of VersionInfo
            All active versions with the specified processing status.
        """
        with self._connection.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT version_id, doc_id, version_no, content_hash, is_active, status, "
                "processing_status, registered_at, parsed_at, chunks_created_at, embedded_at, "
                "tree_built_at, entities_extracted_at, completed_at, processing_status_updated_at "
                "FROM document_versions "
                "WHERE is_active = TRUE AND processing_status = %s "
                "ORDER BY registered_at DESC",
                (processing_status,),
            )
            rows = cur.fetchall()

        return [
            VersionInfo(
                version_id=uuid.UUID(str(row["version_id"])),
                doc_id=uuid.UUID(str(row["doc_id"])),
                version_no=row["version_no"],
                content_hash=row["content_hash"],
                is_active=row["is_active"],
                status=row["status"],
                processing_status=row["processing_status"],
                registered_at=row["registered_at"],
                parsed_at=row["parsed_at"],
                chunks_created_at=row["chunks_created_at"],
                embedded_at=row["embedded_at"],
                tree_built_at=row["tree_built_at"],
                entities_extracted_at=row["entities_extracted_at"],
                completed_at=row["completed_at"],
                processing_status_updated_at=row["processing_status_updated_at"],
            )
            for row in rows
        ]

    def write_spans(
        self, *, version_id: uuid.UUID, spans: Sequence[CanonicalSpan]
    ) -> None:
        if not spans:
            return

        values: list[tuple[str, str, str, int, int, int | None, str | None, str]] = []
        for span in spans:
            if span.version_id != version_id:
                raise ValueError(
                    "span version_id does not match the registered version"
                )
            values.append(
                (
                    str(span.span_id),
                    str(version_id),
                    "paragraph",
                    span.offset,
                    span.offset + len(span.text),
                    span.page_no,
                    span.heading_path if span.headings else None,
                    span.text,
                )
            )

        with self._connection.transaction(), self._connection.cursor(
            row_factory=dict_row
        ) as cur:
            # Check if spans already exist for this version (idempotent).
            # This check is inside the transaction to prevent TOCTOU race:
            # without this, two concurrent calls both see COUNT=0 and both insert.
            cur.execute(
                "SELECT COUNT(*) AS span_count FROM canonical_spans WHERE version_id = %s",
                (str(version_id),),
            )
            row = cur.fetchone()
            if row and row["span_count"] > 0:
                return

            # ON CONFLICT DO NOTHING on span_id (PRIMARY KEY) provides defense-in-depth
            # against concurrent inserts that both pass the COUNT check.
            cur.executemany(
                "INSERT INTO canonical_spans (span_id, version_id, span_kind, start_offset, end_offset, page_no, heading_path, raw_text) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (span_id) DO NOTHING",
                values,
            )

    def query_spans_by_version(self, version_id: uuid.UUID) -> list[dict[str, Any]]:
        with self._connection.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT span_id, version_id, span_kind, start_offset, end_offset, page_no, heading_path, raw_text, created_at FROM canonical_spans WHERE version_id = %s ORDER BY start_offset",
                (str(version_id),),
            )
            rows = cur.fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            row["span_id"] = uuid.UUID(str(row["span_id"]))
            row["version_id"] = uuid.UUID(str(row["version_id"]))
            result.append(row)
        return result

    def get_version(self, version_id: uuid.UUID) -> VersionInfo:
        with self._connection.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT version_id, doc_id, version_no, content_hash, is_active, status, "
                "processing_status, registered_at, parsed_at, chunks_created_at, embedded_at, "
                "tree_built_at, entities_extracted_at, completed_at, processing_status_updated_at "
                "FROM document_versions WHERE version_id = %s",
                (str(version_id),),
            )
            row = cur.fetchone()

        if row is None:
            raise ValueError(f"Version not found: {version_id}")

        return VersionInfo(
            version_id=uuid.UUID(str(row["version_id"])),
            doc_id=uuid.UUID(str(row["doc_id"])),
            version_no=row["version_no"],
            content_hash=row["content_hash"],
            is_active=row["is_active"],
            status=row["status"],
            processing_status=row["processing_status"],
            registered_at=row["registered_at"],
            parsed_at=row["parsed_at"],
            chunks_created_at=row["chunks_created_at"],
            embedded_at=row["embedded_at"],
            tree_built_at=row["tree_built_at"],
            entities_extracted_at=row["entities_extracted_at"],
            completed_at=row["completed_at"],
            processing_status_updated_at=row["processing_status_updated_at"],
        )

    def list_versions(self, doc_id: uuid.UUID) -> list[VersionInfo]:
        with self._connection.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT version_id, doc_id, version_no, content_hash, is_active, status, "
                "processing_status, registered_at, parsed_at, chunks_created_at, embedded_at, "
                "tree_built_at, entities_extracted_at, completed_at, processing_status_updated_at "
                "FROM document_versions WHERE doc_id = %s ORDER BY version_no",
                (str(doc_id),),
            )
            rows = cur.fetchall()

        return [
            VersionInfo(
                version_id=uuid.UUID(str(row["version_id"])),
                doc_id=uuid.UUID(str(row["doc_id"])),
                version_no=row["version_no"],
                content_hash=row["content_hash"],
                is_active=row["is_active"],
                status=row["status"],
                processing_status=row["processing_status"],
                registered_at=row["registered_at"],
                parsed_at=row["parsed_at"],
                chunks_created_at=row["chunks_created_at"],
                embedded_at=row["embedded_at"],
                tree_built_at=row["tree_built_at"],
                entities_extracted_at=row["entities_extracted_at"],
                completed_at=row["completed_at"],
                processing_status_updated_at=row["processing_status_updated_at"],
            )
            for row in rows
        ]

    def get_active_version(self, doc_id: uuid.UUID) -> VersionInfo | None:
        with self._connection.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT version_id, doc_id, version_no, content_hash, is_active, status, "
                "processing_status, registered_at, parsed_at, chunks_created_at, embedded_at, "
                "tree_built_at, entities_extracted_at, completed_at, processing_status_updated_at "
                "FROM document_versions WHERE doc_id = %s AND is_active = TRUE",
                (str(doc_id),),
            )
            row = cur.fetchone()

        if row is None:
            return None

        return VersionInfo(
            version_id=uuid.UUID(str(row["version_id"])),
            doc_id=uuid.UUID(str(row["doc_id"])),
            version_no=row["version_no"],
            content_hash=row["content_hash"],
            is_active=row["is_active"],
            status=row["status"],
            processing_status=row["processing_status"],
            registered_at=row["registered_at"],
            parsed_at=row["parsed_at"],
            chunks_created_at=row["chunks_created_at"],
            embedded_at=row["embedded_at"],
            tree_built_at=row["tree_built_at"],
            entities_extracted_at=row["entities_extracted_at"],
            completed_at=row["completed_at"],
            processing_status_updated_at=row["processing_status_updated_at"],
        )

    def write_tree(
        self,
        *,
        version_id: uuid.UUID,
        nodes: Sequence[dict[str, Any]],
        node_spans: Sequence[dict[str, Any]],
    ) -> None:
        """Persist tree_nodes and tree_node_spans for a version.

        Idempotent: if tree_nodes already exist for this version, the call
        is a no-op (same pattern as write_spans).
        """
        if not nodes:
            return

        with self._connection.transaction(), self._connection.cursor(
            row_factory=dict_row
        ) as cur:
            # Idempotency check inside the transaction to prevent TOCTOU race
            cur.execute(
                "SELECT COUNT(*) AS node_count FROM tree_nodes WHERE version_id = %s",
                (str(version_id),),
            )
            row = cur.fetchone()
            if row and row["node_count"] > 0:
                return

            # ON CONFLICT DO NOTHING on node_id (PRIMARY KEY) provides
            # defense-in-depth against concurrent inserts.
            for node in nodes:
                cur.execute(
                    "INSERT INTO tree_nodes (node_id, version_id, parent_node_id, node_type, level_no, title, heading_path, page_start, page_end, summary_text) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (node_id) DO NOTHING",
                    (
                        str(node["node_id"]),
                        str(node["version_id"]),
                        str(node["parent_node_id"]) if node["parent_node_id"] else None,
                        node["node_type"],
                        node["level_no"],
                        node["title"],
                        node["heading_path"],
                        node["page_start"],
                        node["page_end"],
                        node["summary_text"],
                    ),
                )

            for mapping in node_spans:
                cur.execute(
                    "INSERT INTO tree_node_spans (node_id, span_id, ordinal_no) VALUES (%s, %s, %s) "
                    "ON CONFLICT (node_id, span_id) DO NOTHING",
                    (
                        str(mapping["node_id"]),
                        str(mapping["span_id"]),
                        mapping["ordinal_no"],
                    ),
                )

    def query_tree_nodes_by_version(
        self, version_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        """Return all tree_nodes for a version, ordered by level_no then heading_path."""
        with self._connection.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT node_id, version_id, parent_node_id, node_type, level_no, title, heading_path, "
                "page_start, page_end, summary_text, created_at "
                "FROM tree_nodes WHERE version_id = %s ORDER BY level_no, heading_path",
                (str(version_id),),
            )
            rows = cur.fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            row["node_id"] = uuid.UUID(str(row["node_id"]))
            row["version_id"] = uuid.UUID(str(row["version_id"]))
            if row["parent_node_id"] is not None:
                row["parent_node_id"] = uuid.UUID(str(row["parent_node_id"]))
            result.append(row)
        return result

    def query_tree_node_spans_by_version(
        self, version_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        """Return all tree_node_spans for a version, ordered by ordinal_no."""
        with self._connection.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT tns.node_id, tns.span_id, tns.ordinal_no "
                "FROM tree_node_spans tns "
                "JOIN tree_nodes tn ON tns.node_id = tn.node_id "
                "WHERE tn.version_id = %s ORDER BY tns.node_id, tns.ordinal_no",
                (str(version_id),),
            )
            rows = cur.fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            row["node_id"] = uuid.UUID(str(row["node_id"]))
            row["span_id"] = uuid.UUID(str(row["span_id"]))
            result.append(row)
        return result

    def write_node_embeddings(
        self,
        *,
        node_embeddings: Sequence[dict[str, Any]],
    ) -> None:
        """Persist precomputed embeddings for tree nodes.

        Phase 2 Task 2.1: Stores embedding vectors for similarity search acceleration.

        Parameters
        ----------
        node_embeddings:
            List of dicts with keys:
            - node_id: UUID
            - embedding_model: str (e.g., "all-MiniLM-L6-v2")
            - embedding_vector: list[float] (dimension must match model)

        Idempotent: Uses ON CONFLICT DO NOTHING on (node_id, embedding_model) PRIMARY KEY.
        """
        if not node_embeddings:
            return

        with self._connection.transaction(), self._connection.cursor(
            row_factory=dict_row
        ) as cur:
            for emb in node_embeddings:
                # pgvector adapter registered in __init__ handles list[float] → VECTOR conversion
                cur.execute(
                    "INSERT INTO node_embeddings (node_id, embedding_model, embedding_vector) "
                    "VALUES (%s, %s, %s) "
                    "ON CONFLICT (node_id, embedding_model) DO NOTHING",
                    (
                        str(emb["node_id"]),
                        emb["embedding_model"],
                        emb[
                            "embedding_vector"
                        ],  # list[float] automatically adapted to VECTOR
                    ),
                )

    def write_semantic_distribution(
        self,
        *,
        version_id: uuid.UUID,
        node_stats: Sequence[dict[str, Any]],
    ) -> None:
        """Persist precomputed semantic distribution stats for tree nodes.

        Phase 4 Task 4.1: Stores distribution statistics for query-time acceleration.

        Parameters
        ----------
        version_id:
            Version UUID for provenance anchoring.
        node_stats:
            List of dicts with keys:
            - node_id: UUID
            - support_count: int (number of hits supporting this node)
            - dispersion: float (coefficient of variation)
            - entropy: float (Shannon entropy)
            - max_entropy: float (optional, log2(ancestor_count))
            - depth: int (optional, heading path depth)

        Idempotent: Uses ON CONFLICT DO NOTHING on (node_id, version_id) PRIMARY KEY.
        """
        if not node_stats:
            return

        with self._connection.transaction(), self._connection.cursor(
            row_factory=dict_row
        ) as cur:
            for stats in node_stats:
                cur.execute(
                    "INSERT INTO semantic_distribution "
                    "(node_id, version_id, support_count, dispersion, entropy, max_entropy, depth) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (node_id, version_id) DO NOTHING",
                    (
                        str(stats["node_id"]),
                        str(version_id),
                        stats.get("support_count", 0),
                        stats.get("dispersion", 0.0),
                        stats.get("entropy", 0.0),
                        stats.get("max_entropy", 0.0),
                        stats.get("depth", 0),
                    ),
                )

    def write_vector_chunks(
        self,
        *,
        version_id: uuid.UUID,
        chunks: Sequence[dict[str, Any]],
    ) -> None:
        """Persist vector_chunks and vector_chunk_spans for a version.

        Idempotent: if vector_chunks already exist for this version, the call
        is a no-op (same pattern as write_spans and write_tree).
        """
        if not chunks:
            return

        with self._connection.transaction(), self._connection.cursor(
            row_factory=dict_row
        ) as cur:
            # Idempotency check inside the transaction to prevent TOCTOU race
            cur.execute(
                "SELECT COUNT(*) AS chunk_count FROM vector_chunks WHERE version_id = %s",
                (str(version_id),),
            )
            row = cur.fetchone()
            if row and row["chunk_count"] > 0:
                return

            # ON CONFLICT DO NOTHING on chunk_id (PRIMARY KEY) provides
            # defense-in-depth against concurrent inserts.
            for chunk in chunks:
                cur.execute(
                    "INSERT INTO vector_chunks "
                    "(chunk_id, version_id, chunk_type, chunk_order, token_count, text_preview, page_no, heading_path) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (chunk_id) DO NOTHING",
                    (
                        str(chunk["chunk_id"]),
                        str(version_id),
                        chunk["chunk_type"],
                        chunk["chunk_order"],
                        chunk["token_count"],
                        chunk["text_preview"],
                        chunk["page_no"],
                        chunk["heading_path"],
                    ),
                )

            for chunk in chunks:
                for idx, span_id in enumerate(chunk["span_ids"]):
                    cur.execute(
                        "INSERT INTO vector_chunk_spans (chunk_id, span_id, ordinal_no) "
                        "VALUES (%s, %s, %s) "
                        "ON CONFLICT (chunk_id, span_id) DO NOTHING",
                        (
                            str(chunk["chunk_id"]),
                            str(span_id),
                            idx,
                        ),
                    )

    def query_doc_id_by_version(self, version_id: uuid.UUID) -> uuid.UUID:
        """Resolve the owning doc_id for a version_id."""
        with self._connection.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT doc_id FROM document_versions WHERE version_id = %s",
                (str(version_id),),
            )
            row = cur.fetchone()

        if row is None:
            raise KeyError(f"No document version found for version_id={version_id}")
        return uuid.UUID(str(row["doc_id"]))

    def query_vector_chunks_by_version(
        self, version_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        """Return all vector_chunks for a version, ordered by chunk_order."""
        with self._connection.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT chunk_id, version_id, chunk_type, chunk_order, token_count, "
                "text_preview, page_no, heading_path, node_id, embedding, created_at "
                "FROM vector_chunks WHERE version_id = %s ORDER BY chunk_order",
                (str(version_id),),
            )
            rows = cur.fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            row["chunk_id"] = uuid.UUID(str(row["chunk_id"]))
            row["version_id"] = uuid.UUID(str(row["version_id"]))
            if row.get("node_id") is not None:
                row["node_id"] = uuid.UUID(str(row["node_id"]))
            result.append(row)
        return result

    def query_vector_chunk_spans_by_version(
        self, version_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        """Return all vector_chunk_spans for a version, ordered by ordinal_no."""
        with self._connection.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT vcs.chunk_id, vcs.span_id, vcs.ordinal_no "
                "FROM vector_chunk_spans vcs "
                "JOIN vector_chunks vc ON vcs.chunk_id = vc.chunk_id "
                "WHERE vc.version_id = %s ORDER BY vcs.chunk_id, vcs.ordinal_no",
                (str(version_id),),
            )
            rows = cur.fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            row["chunk_id"] = uuid.UUID(str(row["chunk_id"]))
            row["span_id"] = uuid.UUID(str(row["span_id"]))
            result.append(row)
        return result

    def query_node_embeddings_by_version(
        self, version_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        """Return all node_embeddings for a version.

        Phase 14 FIX: Query node-level prototype embeddings for semantic_distribution.
        """
        with self._connection.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT ne.node_id, ne.embedding_model, ne.embedding_vector "
                "FROM node_embeddings ne "
                "JOIN tree_nodes tn ON ne.node_id = tn.node_id "
                "WHERE tn.version_id = %s",
                (str(version_id),),
            )
            rows = cur.fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            row["node_id"] = uuid.UUID(str(row["node_id"]))
            # embedding_vector is already list[float] (pgvector adapter handles conversion)
            result.append(row)
        return result

    # -- KG (Phase 5) methods --

    def write_entities(self, *, entities: Sequence[dict[str, Any]]) -> None:
        """Persist entity rows.

        Idempotent: ON CONFLICT on entity_id (PRIMARY KEY) does nothing.
        GraphRAG-style: includes description and community_id fields.
        KAG-style: validates against entity_type_schemas if defined.
        """
        if not entities:
            return

        # Validate entities against schemas
        self._validate_entities_against_schemas(entities)

        with self._connection.transaction(), self._connection.cursor() as cur:
            for entity in entities:
                cur.execute(
                    "INSERT INTO entities (entity_id, entity_key, entity_type, canonical_name, description, community_id) "
                    "VALUES (%s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (entity_id) DO NOTHING",
                    (
                        str(entity["entity_id"]),
                        entity["entity_key"],
                        entity.get("entity_type"),
                        entity.get("canonical_name"),
                        entity.get("description"),  # GraphRAG-style
                        (
                            str(entity["community_id"])
                            if entity.get("community_id")
                            else None
                        ),  # GraphRAG-style
                    ),
                )

    def _validate_entities_against_schemas(
        self, entities: Sequence[dict[str, Any]]
    ) -> None:
        """Validate entities against entity_type_schemas.

        Raises ValueError if validation fails.
        Skips validation if no schema is defined for the entity_type (backward compatibility).
        """
        if not entities:
            return

        # Get all schemas
        schemas = self.query_entity_type_schemas()
        schema_map = {s["entity_type_name"]: s for s in schemas}

        for entity in entities:
            entity_type = entity.get("entity_type")
            if entity_type is None:
                continue  # No type, skip validation

            schema = schema_map.get(entity_type)
            if schema is None:
                continue  # No schema defined, backward compatibility

            # Check required fields
            required_fields = schema.get("required_fields")
            if required_fields:
                for field_name in required_fields:
                    if field_name not in entity or entity.get(field_name) is None:
                        raise ValueError(
                            f"Entity of type '{entity_type}' missing required field '{field_name}'. "
                            f"Schema definition: {schema['entity_type_name']}"
                        )

    def query_entities(self) -> list[dict[str, Any]]:
        """Return all entities including GraphRAG-style fields."""
        with self._connection.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT entity_id, entity_key, entity_type, canonical_name, description, community_id, created_at "
                "FROM entities ORDER BY entity_key"
            )
            rows = cur.fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            row["entity_id"] = uuid.UUID(str(row["entity_id"]))
            if row["community_id"] is not None:
                row["community_id"] = uuid.UUID(str(row["community_id"]))
            result.append(row)
        return result

    def write_relations(self, *, relations: Sequence[dict[str, Any]]) -> None:
        """Persist relation rows and replace all payload fields on ID collisions."""
        if not relations:
            return

        qualifier_payloads = tuple(
            self._relation_qualifier_payload(relation) for relation in relations
        )
        self._validate_relations_against_schemas(relations)

        with self._connection.transaction(), self._connection.cursor() as cur:
            for relation, payload in zip(relations, qualifier_payloads, strict=True):
                cur.execute(
                    "INSERT INTO relations "
                    "(relation_id, relation_key, relation_type, source_entity_id, target_entity_id, "
                    "description, negation, condition, direction, confidence, qualifiers) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (relation_id) DO UPDATE SET "
                    "relation_key = EXCLUDED.relation_key, relation_type = EXCLUDED.relation_type, "
                    "source_entity_id = EXCLUDED.source_entity_id, "
                    "target_entity_id = EXCLUDED.target_entity_id, description = EXCLUDED.description, "
                    "negation = EXCLUDED.negation, condition = EXCLUDED.condition, "
                    "direction = EXCLUDED.direction, confidence = EXCLUDED.confidence, "
                    "qualifiers = EXCLUDED.qualifiers",
                    (
                        str(relation["relation_id"]),
                        relation["relation_key"],
                        relation["relation_type"],
                        str(relation["source_entity_id"]),
                        str(relation["target_entity_id"]),
                        relation.get("description"),
                        *payload,
                    ),
                )

    @staticmethod
    def _relation_qualifier_payload(
        relation: Mapping[str, Any],
    ) -> tuple[bool, str | None, str | None, Any | None, Jsonb]:
        """Validate and normalize optional relation qualifiers for persistence."""
        validate_relation_qualifiers(
            relation,
            allow_none_negation=True,
            allow_none_qualifiers=True,
        )
        qualifiers = relation.get("qualifiers")
        qualifier_snapshot = {} if qualifiers is None else deepcopy(qualifiers)
        return (
            False if relation.get("negation") is None else relation["negation"],
            relation.get("condition"),
            relation.get("direction"),
            relation.get("confidence"),
            Jsonb(qualifier_snapshot),
        )

    def _validate_relations_against_schemas(
        self, relations: Sequence[dict[str, Any]]
    ) -> None:
        """Validate relations against relation_type_schemas.

        Raises ValueError if validation fails.
        Skips validation if no schema is defined for the relation_type (backward compatibility).
        """
        if not relations:
            return

        # Get all relation schemas
        rel_schemas = self.query_relation_type_schemas()
        rel_schema_map = {s["relation_type_name"]: s for s in rel_schemas}

        # Get all entities to check their types
        existing_entities = self.query_entities()
        entity_map = {e["entity_id"]: e for e in existing_entities}

        for rel in relations:
            relation_type = rel.get("relation_type")
            if relation_type is None:
                continue  # No type, skip validation

            schema = rel_schema_map.get(relation_type)
            if schema is None:
                continue  # No schema defined, backward compatibility

            # Check source entity existence and type
            source_entity_id = rel.get("source_entity_id")
            source_entity = entity_map.get(source_entity_id)
            if source_entity is None:
                raise ValueError(
                    f"Relation type '{relation_type}' references non-existent source entity: {source_entity_id}"
                )
            source_type = source_entity.get("entity_type")
            allowed_source_types = schema.get("allowed_source_types")
            if allowed_source_types and source_type not in allowed_source_types:
                raise ValueError(
                    f"Relation type '{relation_type}' does not allow source entity type '{source_type}'. "
                    f"Allowed source types: {allowed_source_types}"
                )

            # Check target entity existence and type
            target_entity_id = rel.get("target_entity_id")
            target_entity = entity_map.get(target_entity_id)
            if target_entity is None:
                raise ValueError(
                    f"Relation type '{relation_type}' references non-existent target entity: {target_entity_id}"
                )
            target_type = target_entity.get("entity_type")
            allowed_target_types = schema.get("allowed_target_types")
            if allowed_target_types and target_type not in allowed_target_types:
                raise ValueError(
                    f"Relation type '{relation_type}' does not allow target entity type '{target_type}'. "
                    f"Allowed target types: {allowed_target_types}"
                )

    def query_relations(self) -> list[dict[str, Any]]:
        """Return all relations, including explicit and JSONB qualifier fields."""
        with self._connection.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT relation_id, relation_key, relation_type, source_entity_id, target_entity_id, "
                "description, negation, condition, direction, confidence, qualifiers, created_at "
                "FROM relations ORDER BY relation_key"
            )
            rows = cur.fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            row["relation_id"] = uuid.UUID(str(row["relation_id"]))
            row["source_entity_id"] = uuid.UUID(str(row["source_entity_id"]))
            row["target_entity_id"] = uuid.UUID(str(row["target_entity_id"]))
            row["negation"] = bool(row.get("negation"))
            if isinstance(row.get("confidence"), Decimal):
                row["confidence"] = float(row["confidence"])
            row["qualifiers"] = deepcopy(row.get("qualifiers") or {})
            result.append(row)
        return result

    def write_evidence_links(
        self,
        *,
        version_id: uuid.UUID,
        evidence_links: Sequence[dict[str, Any]],
    ) -> None:
        """Persist evidence_link rows anchored on span_id.

        Idempotent: ON CONFLICT on evidence_link_id (PRIMARY KEY) does nothing.
        P4: evidence_id is optional grouping layer.
        """
        if not evidence_links:
            return

        with self._connection.transaction(), self._connection.cursor() as cur:
            for link in evidence_links:
                evidence_link_id = uuid.uuid4()
                cur.execute(
                    "INSERT INTO evidence_links "
                    "(evidence_link_id, version_id, entity_id, relation_id, span_id, source_kind, confidence_score, evidence_id) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (evidence_link_id) DO NOTHING",
                    (
                        str(evidence_link_id),
                        str(version_id),
                        str(link["entity_id"]) if link.get("entity_id") else None,
                        str(link["relation_id"]) if link.get("relation_id") else None,
                        str(link["span_id"]),
                        link["source_kind"],
                        link.get("confidence_score"),
                        str(link["evidence_id"]) if link.get("evidence_id") else None,
                    ),
                )

    def query_evidence_links_by_version(
        self, version_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        """Return all evidence_links for a version, ordered by span_id.

        P4: Includes evidence_id field.
        """
        with self._connection.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT evidence_link_id, version_id, entity_id, relation_id, span_id, source_kind, confidence_score, evidence_id, created_at "
                "FROM evidence_links WHERE version_id = %s ORDER BY span_id",
                (str(version_id),),
            )
            rows = cur.fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            row["evidence_link_id"] = uuid.UUID(str(row["evidence_link_id"]))
            row["version_id"] = uuid.UUID(str(row["version_id"]))
            if row["entity_id"] is not None:
                row["entity_id"] = uuid.UUID(str(row["entity_id"]))
            if row["relation_id"] is not None:
                row["relation_id"] = uuid.UUID(str(row["relation_id"]))
            row["span_id"] = uuid.UUID(str(row["span_id"]))
            if row["evidence_id"] is not None:
                row["evidence_id"] = uuid.UUID(str(row["evidence_id"]))
            result.append(row)
        return result

    # -- P4: Evidence object methods --

    def write_evidence(self, *, evidence: Sequence[dict[str, Any]]) -> None:
        """Persist evidence rows for grouping evidence_links.

        Idempotent deduplication strategy:
        - If dedup_key is provided: ON CONFLICT on (version_id, dedup_key) reuse existing evidence_id
        - If dedup_key is None: ON CONFLICT on evidence_id (PRIMARY KEY) does nothing

        This enables EvidenceNet-style deduplication at version scope without full scoring framework.
        """
        if not evidence:
            return

        with self._connection.transaction(), self._connection.cursor() as cur:
            for ev in evidence:
                dedup_key = ev.get("dedup_key")

                if dedup_key is not None:
                    # Idempotent deduplication: same version_id + dedup_key keeps the
                    # original row and ignores duplicates.
                    cur.execute(
                        "INSERT INTO evidence (evidence_id, version_id, dedup_key) "
                        "VALUES (%s, %s, %s) "
                        "ON CONFLICT (version_id, dedup_key) WHERE dedup_key IS NOT NULL "
                        "DO NOTHING",
                        (
                            str(ev["evidence_id"]),
                            str(ev["version_id"]),
                            dedup_key,
                        ),
                    )
                else:
                    # No dedup_key: idempotent on evidence_id only (backward compatibility)
                    cur.execute(
                        "INSERT INTO evidence (evidence_id, version_id, dedup_key) "
                        "VALUES (%s, %s, %s) "
                        "ON CONFLICT (evidence_id) DO NOTHING",
                        (
                            str(ev["evidence_id"]),
                            str(ev["version_id"]),
                            None,
                        ),
                    )

    def query_evidence_by_version(self, version_id: uuid.UUID) -> list[dict[str, Any]]:
        """Return all evidence objects for a version."""
        with self._connection.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT evidence_id, version_id, dedup_key, created_at "
                "FROM evidence WHERE version_id = %s ORDER BY created_at",
                (str(version_id),),
            )
            rows = cur.fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            row["evidence_id"] = uuid.UUID(str(row["evidence_id"]))
            row["version_id"] = uuid.UUID(str(row["version_id"]))
            result.append(row)
        return result

    def write_chunk_entity_links(
        self,
        *,
        version_id: uuid.UUID,
        links: Sequence[dict[str, Any]],
    ) -> None:
        """Persist chunk -> entity bridge rows.

        Idempotent: ON CONFLICT on (chunk_id, entity_id) does nothing.
        """
        if not links:
            return

        with self._connection.transaction(), self._connection.cursor() as cur:
            for link in links:
                cur.execute(
                    "INSERT INTO chunk_entity_links (chunk_id, entity_id, ordinal_no, confidence_score, mention_text) "
                    "VALUES (%s, %s, %s, %s, %s) "
                    "ON CONFLICT (chunk_id, entity_id) DO NOTHING",
                    (
                        str(link["chunk_id"]),
                        str(link["entity_id"]),
                        link["ordinal_no"],
                        link.get("confidence_score"),
                        link.get("mention_text"),
                    ),
                )

    def query_chunk_entity_links_by_version(
        self, version_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        """Return all chunk_entity_links for a version, ordered by chunk_id then ordinal_no."""
        with self._connection.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT cel.chunk_id, cel.entity_id, cel.ordinal_no, cel.confidence_score, cel.mention_text "
                "FROM chunk_entity_links cel "
                "JOIN vector_chunks vc ON cel.chunk_id = vc.chunk_id "
                "WHERE vc.version_id = %s ORDER BY cel.chunk_id, cel.ordinal_no",
                (str(version_id),),
            )
            rows = cur.fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            row["chunk_id"] = uuid.UUID(str(row["chunk_id"]))
            row["entity_id"] = uuid.UUID(str(row["entity_id"]))
            result.append(row)
        return result

    def query_chunks_by_entity(self, entity_id: uuid.UUID) -> list[dict[str, Any]]:
        """Return all chunk links for an entity across versions."""
        with self._connection.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT cel.chunk_id, cel.entity_id, cel.ordinal_no, cel.confidence_score, cel.mention_text, vc.version_id "
                "FROM chunk_entity_links cel "
                "JOIN vector_chunks vc ON cel.chunk_id = vc.chunk_id "
                "WHERE cel.entity_id = %s ORDER BY vc.version_id, cel.chunk_id, cel.ordinal_no",
                (str(entity_id),),
            )
            rows = cur.fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            row["chunk_id"] = uuid.UUID(str(row["chunk_id"]))
            row["entity_id"] = uuid.UUID(str(row["entity_id"]))
            row["version_id"] = uuid.UUID(str(row["version_id"]))
            result.append(row)
        return result

    def query_entities_by_chunk(self, chunk_id: uuid.UUID) -> list[dict[str, Any]]:
        """Return all entity links for a chunk."""
        with self._connection.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT chunk_id, entity_id, ordinal_no, confidence_score, mention_text "
                "FROM chunk_entity_links WHERE chunk_id = %s ORDER BY ordinal_no",
                (str(chunk_id),),
            )
            rows = cur.fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            row["chunk_id"] = uuid.UUID(str(row["chunk_id"]))
            row["entity_id"] = uuid.UUID(str(row["entity_id"]))
            result.append(row)
        return result

    def write_node_entity_links(
        self,
        *,
        version_id: uuid.UUID,
        links: Sequence[dict[str, Any]],
    ) -> None:
        """Persist node -> entity bridge rows.

        Idempotent: ON CONFLICT on (node_id, entity_id) does nothing.
        """
        if not links:
            return

        with self._connection.transaction(), self._connection.cursor() as cur:
            for link in links:
                cur.execute(
                    "INSERT INTO node_entity_links (node_id, entity_id, ordinal_no, confidence_score, mention_text) "
                    "VALUES (%s, %s, %s, %s, %s) "
                    "ON CONFLICT (node_id, entity_id) DO NOTHING",
                    (
                        str(link["node_id"]),
                        str(link["entity_id"]),
                        link["ordinal_no"],
                        link.get("confidence_score"),
                        link.get("mention_text"),
                    ),
                )

    def query_node_entity_links_by_version(
        self, version_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        """Return all node_entity_links for a version, ordered by node_id then ordinal_no."""
        with self._connection.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT nel.node_id, nel.entity_id, nel.ordinal_no, nel.confidence_score, nel.mention_text "
                "FROM node_entity_links nel "
                "JOIN tree_nodes tn ON nel.node_id = tn.node_id "
                "WHERE tn.version_id = %s ORDER BY nel.node_id, nel.ordinal_no",
                (str(version_id),),
            )
            rows = cur.fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            row["node_id"] = uuid.UUID(str(row["node_id"]))
            row["entity_id"] = uuid.UUID(str(row["entity_id"]))
            result.append(row)
        return result

    def query_nodes_by_entity(self, entity_id: uuid.UUID) -> list[dict[str, Any]]:
        """Return all node links for an entity across versions."""
        with self._connection.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT nel.node_id, nel.entity_id, nel.ordinal_no, nel.confidence_score, nel.mention_text, tn.version_id "
                "FROM node_entity_links nel "
                "JOIN tree_nodes tn ON nel.node_id = tn.node_id "
                "WHERE nel.entity_id = %s ORDER BY tn.version_id, nel.node_id, nel.ordinal_no",
                (str(entity_id),),
            )
            rows = cur.fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            row["node_id"] = uuid.UUID(str(row["node_id"]))
            row["entity_id"] = uuid.UUID(str(row["entity_id"]))
            row["version_id"] = uuid.UUID(str(row["version_id"]))
            result.append(row)
        return result

    def query_entities_by_node(self, node_id: uuid.UUID) -> list[dict[str, Any]]:
        """Return all entity links for a tree node."""
        with self._connection.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT node_id, entity_id, ordinal_no, confidence_score, mention_text "
                "FROM node_entity_links WHERE node_id = %s ORDER BY ordinal_no",
                (str(node_id),),
            )
            rows = cur.fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            row["node_id"] = uuid.UUID(str(row["node_id"]))
            row["entity_id"] = uuid.UUID(str(row["entity_id"]))
            result.append(row)
        return result

    # -- KAG-style schema methods (P4) --

    def write_entity_type_schema(self, *, schema: dict[str, Any]) -> None:
        """Persist or update an entity type schema definition.

        Idempotent: ON CONFLICT on entity_type_name updates existing schema.
        """
        with self._connection.transaction(), self._connection.cursor() as cur:
            cur.execute(
                "INSERT INTO entity_type_schemas (entity_type_name, description, required_fields) "
                "VALUES (%s, %s, %s) "
                "ON CONFLICT (entity_type_name) DO UPDATE SET "
                "description = EXCLUDED.description, "
                "required_fields = EXCLUDED.required_fields, "
                "updated_at = now()",
                (
                    schema["entity_type_name"],
                    schema.get("description"),
                    schema.get("required_fields"),
                ),
            )

    def query_entity_type_schemas(self) -> list[dict[str, Any]]:
        """Return all entity type schema definitions."""
        with self._connection.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT entity_type_schema_id, entity_type_name, description, required_fields, created_at, updated_at "
                "FROM entity_type_schemas ORDER BY entity_type_name"
            )
            rows = cur.fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            row["entity_type_schema_id"] = uuid.UUID(str(row["entity_type_schema_id"]))
            result.append(row)
        return result

    def write_relation_type_schema(self, *, schema: dict[str, Any]) -> None:
        """Persist or update a relation type schema definition.

        Idempotent: ON CONFLICT on relation_type_name updates existing schema.
        """
        with self._connection.transaction(), self._connection.cursor() as cur:
            cur.execute(
                "INSERT INTO relation_type_schemas (relation_type_name, allowed_source_types, allowed_target_types) "
                "VALUES (%s, %s, %s) "
                "ON CONFLICT (relation_type_name) DO UPDATE SET "
                "allowed_source_types = EXCLUDED.allowed_source_types, "
                "allowed_target_types = EXCLUDED.allowed_target_types, "
                "updated_at = now()",
                (
                    schema["relation_type_name"],
                    schema.get("allowed_source_types"),
                    schema.get("allowed_target_types"),
                ),
            )

    def query_relation_type_schemas(self) -> list[dict[str, Any]]:
        """Return all relation type schema definitions."""
        with self._connection.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT relation_type_schema_id, relation_type_name, allowed_source_types, allowed_target_types, created_at, updated_at "
                "FROM relation_type_schemas ORDER BY relation_type_name"
            )
            rows = cur.fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            row["relation_type_schema_id"] = uuid.UUID(
                str(row["relation_type_schema_id"])
            )
            result.append(row)
        return result

    def query_spans_by_keyword(
        self,
        *,
        query: str,
        version_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Search canonical spans by keyword using ILIKE and full-text search.

        Parameters
        ----------
        query:
            The keyword search string.
        version_id:
            Optional version filter. If provided, only spans from this
            version are searched. Otherwise, only active versions are searched.
        limit:
            Maximum number of results.

        Returns
        -------
        list of dict
            Matching span rows with span_id, doc_id, version_id, page_no,
            heading_path, raw_text, and match_score.
        """
        where_version = "dv.is_active = TRUE"
        params: dict[str, Any] = {
            "query": query,
            "pattern": f"%{query}%",
            "limit": limit,
        }
        if version_id is not None:
            where_version = "cs.version_id = %(version_id)s"
            params["version_id"] = str(version_id)

        sql = f"""
            SELECT
                cs.span_id,
                dv.doc_id,
                cs.version_id,
                cs.page_no,
                cs.heading_path,
                cs.raw_text,
                GREATEST(
                    CASE WHEN cs.raw_text ILIKE %(pattern)s THEN 1.0 ELSE 0.0 END,
                    similarity(cs.raw_text, %(query)s)
                ) AS match_score
            FROM canonical_spans cs
            JOIN document_versions dv ON cs.version_id = dv.version_id
            WHERE {where_version}
            AND (
                cs.raw_text ILIKE %(pattern)s
                OR cs.raw_text_tsvector @@ websearch_to_tsquery('simple', %(query)s)
            )
            ORDER BY match_score DESC, cs.page_no NULLS LAST, cs.start_offset ASC
            LIMIT %(limit)s
        """
        with self._connection.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            result.append(
                {
                    "span_id": uuid.UUID(str(row["span_id"])),
                    "doc_id": uuid.UUID(str(row["doc_id"])),
                    "version_id": uuid.UUID(str(row["version_id"])),
                    "page_no": row["page_no"],
                    "heading_path": row["heading_path"],
                    "raw_text": row["raw_text"],
                    "match_score": float(row["match_score"]),
                }
            )
        return result

    # -- Summary index methods (P5 multi-view indexing) --

    def write_summaries(
        self,
        *,
        version_id: uuid.UUID,
        summaries: Sequence[dict[str, Any]],
    ) -> None:
        """Persist summary entities to summaries table.

        Parameters
        ----------
        version_id:
            Document version UUID.
        summaries:
            Sequence of summary dicts from SummaryIndex.build_from_tree().
            Each must have summary_id, version_id, node_id, summary_text.

        Raises
        ------
        ValueError
            If summaries is non-empty but missing required fields.
            Empty summaries return without error for idempotent callers.
        """
        if not summaries:
            return

        with self._connection.transaction(), self._connection.cursor(
            row_factory=dict_row
        ) as cur:
            for summary in summaries:
                required_fields = [
                    "summary_id",
                    "version_id",
                    "node_id",
                    "summary_text",
                ]
                for field in required_fields:
                    if field not in summary:
                        raise ValueError(f"Summary missing required field: {field}")

                cur.execute(
                    """
                    INSERT INTO summaries (summary_id, version_id, node_id, summary_text)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (summary_id) DO UPDATE SET summary_text = EXCLUDED.summary_text
                    """,
                    (
                        str(summary["summary_id"]),
                        str(summary["version_id"]),
                        str(summary["node_id"]),
                        summary["summary_text"],
                    ),
                )

    def query_summaries_by_version(self, version_id: uuid.UUID) -> list[dict[str, Any]]:
        """Query summary entities by version_id.

        Parameters
        ----------
        version_id:
            Document version UUID.

        Returns
        -------
        list of dict
            Summary rows with summary_id, version_id, node_id, summary_text,
            and heading_path (from tree_nodes join).
        """
        sql = """
            SELECT
                s.summary_id,
                s.version_id,
                s.node_id,
                s.summary_text,
                tn.heading_path
            FROM summaries s
            JOIN tree_nodes tn ON s.node_id = tn.node_id
            WHERE s.version_id = %s
            ORDER BY tn.level_no ASC, tn.heading_path ASC
        """
        with self._connection.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, (str(version_id),))
            rows = cur.fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            result.append(
                {
                    "summary_id": uuid.UUID(str(row["summary_id"])),
                    "version_id": uuid.UUID(str(row["version_id"])),
                    "node_id": uuid.UUID(str(row["node_id"])),
                    "summary_text": row["summary_text"],
                    "heading_path": row["heading_path"],
                }
            )
        return result

    def query_summaries_by_keyword(
        self,
        *,
        query: str,
        version_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Search summaries by keyword using ILIKE and full-text search.

        Parameters
        ----------
        query:
            The keyword search string.
        version_id:
            Optional version filter. If provided, only summaries from this
            version are searched. Otherwise, only active versions are searched.
        limit:
            Maximum number of results.

        Returns
        -------
        list of dict
            Matching summary rows with summary_id, version_id, node_id,
            summary_text, heading_path, and match_score.
        """
        where_version = "dv.is_active = TRUE"
        params: dict[str, Any] = {
            "query": query,
            "pattern": f"%{query}%",
            "limit": limit,
        }
        if version_id is not None:
            where_version = "s.version_id = %(version_id)s"
            params["version_id"] = str(version_id)

        sql = f"""
            SELECT
                s.summary_id,
                s.version_id,
                s.node_id,
                s.summary_text,
                tn.heading_path,
                GREATEST(
                    CASE WHEN s.summary_text ILIKE %(pattern)s THEN 1.0 ELSE 0.0 END,
                    similarity(s.summary_text, %(query)s)
                ) AS match_score
            FROM summaries s
            JOIN document_versions dv ON s.version_id = dv.version_id
            JOIN tree_nodes tn ON s.node_id = tn.node_id
            WHERE {where_version}
            AND (
                s.summary_text ILIKE %(pattern)s
                OR to_tsvector('simple', s.summary_text) @@ websearch_to_tsquery('simple', %(query)s)
            )
            ORDER BY match_score DESC, tn.level_no ASC
            LIMIT %(limit)s
        """
        with self._connection.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            result.append(
                {
                    "summary_id": uuid.UUID(str(row["summary_id"])),
                    "version_id": uuid.UUID(str(row["version_id"])),
                    "node_id": uuid.UUID(str(row["node_id"])),
                    "summary_text": row["summary_text"],
                    "heading_path": row["heading_path"],
                    "match_score": float(row["match_score"]),
                }
            )
        return result

    @staticmethod
    def _hash_file(source_path: Path) -> str:
        digest = hashlib.sha256()
        with source_path.open("rb") as file_handle:
            while chunk := file_handle.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _detect_parser_version() -> str:
        try:
            import docling
        except ModuleNotFoundError:
            return "unknown"
        return str(getattr(docling, "__version__", "unknown"))

    @staticmethod
    def _contract_key(parser_name: str, parser_version: str, offset_basis: str) -> str:
        """Compute a deterministic key for a normalization contract configuration.

        This is used for deduplication and debugging. The actual database lookup
        uses the three columns directly.
        """
        return f"{parser_name}|{parser_version}|{offset_basis}"
