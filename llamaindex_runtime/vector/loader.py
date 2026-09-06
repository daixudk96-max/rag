"""Orchestrate vector chunk creation, persistence, and embedding.

VectorLoader reads canonical spans from the database, generates chunks
via a configurable chunker strategy, persists them, computes embeddings
via DeterministicEmbedder, and optionally links chunks to tree nodes.

When a VectorBackend is provided, vectors are also projected to the
backend store (e.g. Qdrant) in addition to PostgreSQL.  PostgreSQL
remains source-of-truth for provenance and mappings.

Chunker strategies:
- SimpleSpanChunker (default): 1:1 span-to-chunk mapping
- HeadingGroupedChunker: groups spans under same heading_path
- Custom chunkers: any class implementing generate(spans, version_id)
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import psycopg
from psycopg.rows import dict_row

from .embedder import DeterministicEmbedder
from .exceptions import VectorLoaderError

if TYPE_CHECKING:
    from .backend import VectorBackend


def _to_vector_literal(values: list[float]) -> str:
    """Format a float list as a PostgreSQL vector literal."""
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


class VectorLoader:
    """Orchestrate the full vector chunk pipeline for a version.

    Steps:
    1. Read canonical_spans for the version
    2. Generate 1:1 chunks via SimpleSpanChunker
    3. Persist vector_chunks and vector_chunk_spans
    4. Compute embeddings and update vector_chunks.embedding
    5. If tree data exists, populate vector_chunks.node_id

    Idempotency and Recovery:
    - If chunks do not exist, run the full pipeline.
    - If chunks exist but have NULL embeddings or NULL node_id (when tree data exists),
      repair the missing data instead of returning early.
    - This handles partial prior runs that crashed after step 3 but before steps 4/5.
    """

    def __init__(
        self,
        embed_dim: int = 16,
        vector_backend: VectorBackend | None = None,
        chunker: Any | None = None,
        refinery: Any | None = None,
        embedder: Any | None = None,
    ) -> None:
        """Initialize VectorLoader with optional custom chunker, refinery, and embedder.

        Parameters
        ----------
        embed_dim : int
            Embedding dimension (default 16 for deterministic test embedder)
        vector_backend : VectorBackend | None
            Optional backend store (e.g., Qdrant) for vector projection
        chunker : Any | None
            Custom chunker instance (default: SimpleSpanChunker)
            Must implement generate(spans, version_id) -> list[dict]
        refinery : Any | None
            Optional refinery instance to apply overlap/context enhancement
            Must implement refine(chunks, version_id) -> list[dict]
        embedder : Any | None
            Custom embedder instance (default: DeterministicEmbedder)
            Must implement embed_text(text) -> list[float]
        """
        if chunker is None:
            from .chunker import SimpleSpanChunker
            self._chunker = SimpleSpanChunker()
        else:
            self._chunker = chunker
        self._refinery = refinery
        if embedder is None:
            self._embedder = DeterministicEmbedder(dim=embed_dim)
        else:
            self._embedder = embedder
        self._vector_backend = vector_backend

    def load(
        self,
        conn: psycopg.Connection,
        version_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Run the vector chunk pipeline for *version_id*.

        If chunks already exist but are incomplete (missing embeddings or
        node_id when tree data is available), the missing data is repaired
        rather than skipped.  This makes load() safe to re-run after a
        partial failure.

        Returns a dict with keys ``chunk_ids`` and ``count``.
        """
        # 1. Read spans
        spans = self._read_spans(conn, version_id)
        if not spans:
            return {"chunk_ids": [], "count": 0}

        # 2. Check if chunks already exist
        existing_count = self._count_existing_chunks(conn, version_id)
        if existing_count > 0:
            # Chunks exist -- check for incomplete state and repair
            chunk_ids = self._read_chunk_ids(conn, version_id)
            chunks_missing_embedding = self._count_chunks_missing_embedding(conn, version_id)
            if chunks_missing_embedding > 0:
                # Regenerate chunk data from spans to compute embeddings
                chunks = self._chunker.generate(spans, version_id=version_id)
                # Apply refinery (if configured) during repair
                if self._refinery is not None:
                    chunks = self._refinery.refine(chunks, version_id=version_id)
                self._update_embeddings(conn, chunks)
                # Also re-project to backend if configured
                self._project_to_backend(version_id, chunks)
            # Always attempt tree-node linking when tree data exists
            # (node_id may be NULL from a partial run before tree was created)
            self._repair_tree_nodes(conn, version_id, spans)
            return {"chunk_ids": chunk_ids, "count": len(chunk_ids)}

        # 3. Generate chunks
        chunks = self._chunker.generate(spans, version_id=version_id)

        # 4. Apply refinery (if configured) to add overlap/context enhancement
        if self._refinery is not None:
            chunks = self._refinery.refine(chunks, version_id=version_id)

        # 5. Persist chunks
        self._write_chunks(conn, version_id, chunks)

        # 5. Persist chunk-span mappings
        mappings: list[tuple[uuid.UUID, uuid.UUID, int]] = []
        for chunk in chunks:
            for idx, span_id in enumerate(chunk["span_ids"]):
                mappings.append((chunk["chunk_id"], span_id, idx))
        self._write_chunk_span_mappings(conn, mappings)

        # 6. Compute and persist embeddings
        self._update_embeddings(conn, chunks)

        # 7. Project vectors to backend store (e.g. Qdrant) if configured
        self._project_to_backend(version_id, chunks)

        # 8. Link to tree nodes if tree data exists
        self._link_tree_nodes(conn, version_id, chunks)

        return {"chunk_ids": [c["chunk_id"] for c in chunks], "count": len(chunks)}

    def _read_spans(
        self,
        conn: psycopg.Connection,
        version_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT span_id, version_id, span_kind, start_offset, end_offset, "
                "page_no, heading_path, raw_text "
                "FROM canonical_spans WHERE version_id = %s ORDER BY start_offset",
                (str(version_id),),
            )
            rows = cur.fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            row["span_id"] = uuid.UUID(str(row["span_id"]))
            row["version_id"] = uuid.UUID(str(row["version_id"]))
            result.append(row)
        return result

    def _count_existing_chunks(
        self,
        conn: psycopg.Connection,
        version_id: uuid.UUID,
    ) -> int:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM vector_chunks WHERE version_id = %s",
                (str(version_id),),
            )
            return int(cur.fetchone()["cnt"])

    def _read_chunk_ids(
        self,
        conn: psycopg.Connection,
        version_id: uuid.UUID,
    ) -> list[uuid.UUID]:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT chunk_id FROM vector_chunks WHERE version_id = %s ORDER BY chunk_order",
                (str(version_id),),
            )
            return [uuid.UUID(str(row[0])) for row in cur.fetchall()]

    def _count_chunks_missing_embedding(
        self,
        conn: psycopg.Connection,
        version_id: uuid.UUID,
    ) -> int:
        """Count vector_chunks for this version that have NULL embedding."""
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM vector_chunks WHERE version_id = %s AND embedding IS NULL",
                (str(version_id),),
            )
            return int(cur.fetchone()["cnt"])

    def _repair_tree_nodes(
        self,
        conn: psycopg.Connection,
        version_id: uuid.UUID,
        spans: list[dict[str, Any]],
    ) -> None:
        """Link vector_chunks to tree nodes for chunks that have NULL node_id.

        This is the repair counterpart of _link_tree_nodes.  It only
        updates chunks where node_id IS NULL, so it is safe to call
        repeatedly (idempotent for already-linked chunks).
        """
        # Check if any tree nodes exist for this version
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM tree_nodes WHERE version_id = %s",
                (str(version_id),),
            )
            if int(cur.fetchone()["cnt"]) == 0:
                return

        # Check if any chunks are actually missing node_id
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM vector_chunks WHERE version_id = %s AND node_id IS NULL",
                (str(version_id),),
            )
            if int(cur.fetchone()["cnt"]) == 0:
                return

        # Build span -> node_id lookup from tree_node_spans + tree_nodes
        span_to_node: dict[uuid.UUID, uuid.UUID] = {}
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT tns.span_id, tns.node_id "
                "FROM tree_node_spans tns "
                "JOIN tree_nodes tn ON tns.node_id = tn.node_id "
                "WHERE tn.version_id = %s",
                (str(version_id),),
            )
            for row in cur.fetchall():
                span_to_node[uuid.UUID(str(row["span_id"]))] = uuid.UUID(str(row["node_id"]))

        if not span_to_node:
            return

        # Regenerate chunk data from spans to get chunk_id -> span_ids mapping
        chunks = self._chunker.generate(spans, version_id=version_id)

        # For each chunk missing node_id, find and set it
        with conn.transaction(), conn.cursor() as cur:
            for chunk in chunks:
                for span_id in chunk["span_ids"]:
                    node_id = span_to_node.get(span_id)
                    if node_id is not None:
                        cur.execute(
                            "UPDATE vector_chunks SET node_id = %s WHERE chunk_id = %s AND node_id IS NULL",
                            (str(node_id), str(chunk["chunk_id"])),
                        )
                        break  # First matching node is sufficient

    def _write_chunks(
        self,
        conn: psycopg.Connection,
        version_id: uuid.UUID,
        chunks: list[dict[str, Any]],
    ) -> None:
        with conn.transaction(), conn.cursor() as cur:
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

    def _write_chunk_span_mappings(
        self,
        conn: psycopg.Connection,
        mappings: list[tuple[uuid.UUID, uuid.UUID, int]],
    ) -> None:
        with conn.transaction(), conn.cursor() as cur:
            for chunk_id, span_id, ordinal_no in mappings:
                cur.execute(
                    "INSERT INTO vector_chunk_spans (chunk_id, span_id, ordinal_no) "
                    "VALUES (%s, %s, %s) "
                    "ON CONFLICT (chunk_id, span_id) DO NOTHING",
                    (str(chunk_id), str(span_id), ordinal_no),
                )

    def _update_embeddings(
        self,
        conn: psycopg.Connection,
        chunks: list[dict[str, Any]],
    ) -> None:
        """Compute and persist embeddings for all chunks.

        Raises
        ------
        VectorLoaderError
            If embedding generation fails for any chunk.
        """
        try:
            with conn.transaction(), conn.cursor() as cur:
                for chunk in chunks:
                    text = chunk.get("text_preview") or ""
                    embedding = self._embedder.embed_text(text)
                    cur.execute(
                        "UPDATE vector_chunks SET embedding = %s::vector WHERE chunk_id = %s",
                        (_to_vector_literal(embedding), str(chunk["chunk_id"])),
                    )
        except (RuntimeError, ValueError, AttributeError) as exc:
            raise VectorLoaderError(f"embedding generation failed: {exc}") from exc

    def _link_tree_nodes(
        self,
        conn: psycopg.Connection,
        version_id: uuid.UUID,
        chunks: list[dict[str, Any]],
    ) -> None:
        """If tree_node_spans exist for this version, set node_id on vector_chunks.

        For each chunk, find the tree node that covers the same span via
        tree_node_spans, and set vector_chunks.node_id to that node_id.
        """
        # Check if any tree nodes exist for this version
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM tree_nodes WHERE version_id = %s",
                (str(version_id),),
            )
            if int(cur.fetchone()["cnt"]) == 0:
                return

        # Build span -> node_id lookup from tree_node_spans + tree_nodes
        span_to_node: dict[uuid.UUID, uuid.UUID] = {}
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT tns.span_id, tns.node_id "
                "FROM tree_node_spans tns "
                "JOIN tree_nodes tn ON tns.node_id = tn.node_id "
                "WHERE tn.version_id = %s",
                (str(version_id),),
            )
            for row in cur.fetchall():
                span_to_node[uuid.UUID(str(row["span_id"]))] = uuid.UUID(str(row["node_id"]))

        # For each chunk, find the node_id from its first span
        with conn.transaction(), conn.cursor() as cur:
            for chunk in chunks:
                for span_id in chunk["span_ids"]:
                    node_id = span_to_node.get(span_id)
                    if node_id is not None:
                        cur.execute(
                            "UPDATE vector_chunks SET node_id = %s WHERE chunk_id = %s",
                            (str(node_id), str(chunk["chunk_id"])),
                        )
                        break  # First matching node is sufficient

    def _project_to_backend(
        self,
        version_id: uuid.UUID,
        chunks: list[dict[str, Any]],
    ) -> None:
        """Project vectors to the backend store (e.g. Qdrant) if configured.

        No-op when no vector backend is set (backward compatible).

        Raises
        ------
        VectorLoaderError
            If embedding generation fails or backend projection fails.
        """
        if self._vector_backend is None:
            return

        from .backend import VectorPoint
        from .exceptions import VectorBackendError

        points: list[VectorPoint] = []
        try:
            for chunk in chunks:
                text = chunk.get("text_preview") or ""
                embedding = self._embedder.embed_text(text)
                points.append(
                    VectorPoint(
                        id=chunk["chunk_id"],
                        vector=embedding,
                        payload={
                            "version_id": str(version_id),
                            "text_preview": text,
                            "chunk_type": chunk.get("chunk_type", ""),
                            "chunk_order": chunk.get("chunk_order", 0),
                            "page_no": chunk.get("page_no"),
                            "heading_path": chunk.get("heading_path"),
                        },
                    )
                )
        except (RuntimeError, ValueError, AttributeError) as exc:
            raise VectorLoaderError(f"embedding generation failed: {exc}") from exc

        collection_name = f"version_{version_id}"
        try:
            self._vector_backend.upsert_vectors(collection_name, points)
        except Exception as exc:
            # Catch all exceptions from backend (VectorBackendError, RuntimeError, etc.)
            raise VectorLoaderError(f"vector projection failed: {exc}") from exc
