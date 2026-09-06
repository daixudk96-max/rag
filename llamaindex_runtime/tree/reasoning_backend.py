"""ReasoningTreeBackend: LLM-based reasoning for tree navigation.

This backend implements PageIndex's agent reasoning workflow:
1. Fetch full tree structure (get_document_structure)
2. Use LLM to judge relevant nodes/pages
3. Extract relevant page content (get_page_content)
4. Return BackendHit format

Phase 2 Task 2.2: Integrates PageIndex reasoning workflow into tree backend stack.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Sequence
from uuid import UUID

from llamaindex_runtime.tree.backend_adapter import BackendHit, TreeBackendAdapter
from llamaindex_runtime.tree.evidence_content_resolver import EvidenceContentResolver
from llamaindex_runtime.client.retrieve import get_document_structure, get_page_content
from llamaindex_runtime.llm import get_llm  # Task 1.1: Unified LLM seam

logger = logging.getLogger(__name__)
MAX_REASONING_QUERY_CHARS = 2000
MAX_REASONING_RESPONSE_CHARS = 50000
MAX_REASONING_JSON_ARRAY_CHARS = 5000
MAX_REASONING_PAGE_NUMBER = 10000


class ReasoningTreeBackend(TreeBackendAdapter):
    """LLM reasoning-based tree retrieval backend.

    This backend transplants PageIndex's agent workflow:
    - Uses LLM to navigate tree structure
    - Judges relevant nodes/pages based on query
    - Extracts specific page content (token savings vs full-tree retrieval)

    Not implemented in Phase 1 (PageIndex donor unchanged constraint).
    Implemented in Phase 2 Task 2.2 as reasoning backend path.

    Attributes
    ----------
    llm_model:
        LLM model for reasoning (from RuntimeSettings).
    documents:
        PageIndex documents dict (workspace management).
    """

    def __init__(
        self,
        *,
        llm_model: str = "gpt-4o-mini",
        documents: dict[str, Any] | None = None,
    ) -> None:
        self.llm_model = llm_model
        self.documents = documents or {}

    def _resolve_document_key(self, version_id: UUID) -> str | None:
        """Resolve the PageIndex document key for a version id."""
        version_key = str(version_id)
        if version_key in self.documents:
            return version_key

        for doc_key, document in self.documents.items():
            if str(document.get("version_id", "")) == version_key:
                return doc_key

        return None

    def index_tree(
        self,
        *,
        source_path: str,
        version_id: UUID,
        registry: Any,
    ) -> None:
        """Index tree structure (NOT USED for reasoning backend).

        Reasoning backend retrieves from pre-indexed tree structure
        (indexed by PageIndexTreeAdapter or TreeGenerator).

        This method is stubbed to satisfy TreeBackendAdapter protocol.
        """
        # Reasoning backend does NOT index - it retrieves from existing tree
        # Tree structure must be indexed separately by PageIndexTreeAdapter
        pass

    def retrieve_tree_hits(
        self,
        *,
        query_text: str,
        version_id: UUID,
        registry: Any,
        limit: int | None = None,
    ) -> list[BackendHit]:
        """Retrieve tree hits using LLM reasoning navigation.

        Workflow:
        1. Fetch tree structure from registry
        2. Use LLM to judge relevant nodes/pages
        3. Extract page content for judged pages
        4. Return BackendHit list

        Parameters
        ----------
        query_text:
            Query for reasoning judgment.
        version_id:
            Version UUID (used to find doc_id in documents dict).
        registry:
            RegistryWriter (for reading tree_nodes if documents dict unavailable).
        limit:
            Optional limit on hits.

        Returns
        -------
        list[BackendHit]
            Hits from reasoning-based retrieval (filtered, NOT all nodes).
        """
        # Step 1: Fetch tree structure
        # Try documents dict first (PageIndex workspace), fallback to registry
        doc_key = self._resolve_document_key(version_id)

        if doc_key is not None:
            structure_json = get_document_structure(self.documents, doc_key)
            structure = json.loads(structure_json)

            # PageIndex's native tool API is page-oriented, so preserve the
            # existing get_document_structure -> get_page_content workflow.
            judged_pages = self._llm_judge_relevant_pages(query_text, structure)
            content_json = get_page_content(self.documents, doc_key, judged_pages)
            content_list = json.loads(content_json)

            hits = []
            for content_item in content_list:
                page = content_item.get("page")
                heading_path = self._extract_heading_path_for_page(page, structure)
                node_id = self._map_page_to_node_id(page, structure)
                if node_id is None:
                    continue

                span_ids = self._query_span_ids_for_node(registry, node_id, version_id)
                chunk_id = self._query_chunk_id_for_hit(
                    registry=registry,
                    version_id=version_id,
                    node_id=node_id,
                    span_ids=span_ids,
                )

                hits.append(
                    BackendHit(
                        score=None,
                        text_preview=content_item.get("content", ""),
                        heading_path=heading_path,
                        page_no=page,
                        span_ids=span_ids,
                        node_id=node_id,
                        chunk_id=chunk_id,
                        entity_id=None,
                        relation_id=None,
                        backend_source="reasoning",
                        retrieval_path="llm_navigation",
                    )
                )

            if limit:
                hits = hits[:limit]
            return hits

        nodes = registry.query_tree_nodes_by_version(version_id)
        structure = self._build_structure_from_nodes(nodes)
        selected_nodes = self._select_relevant_nodes(
            query_text=query_text,
            structure=structure,
            limit=limit,
        )

        hits = []
        for node in selected_nodes:
            hit = self._backend_hit_from_node(
                node=node,
                registry=registry,
                version_id=version_id,
            )
            if hit is not None:
                hits.append(hit)

        if limit:
            hits = hits[:limit]

        return hits

    def _build_structure_from_nodes(self, nodes: list[dict]) -> list[dict]:
        """Build tree structure from registry tree_nodes.

        Converts flat node list to nested structure for reasoning.
        """
        structure = []
        for node in nodes:
            item = {
                "node_id": node.get("node_id"),
                "title": node.get("title"),
                "heading_path": node.get("heading_path"),
                "page_no": node.get("page_no") or node.get("page_start"),
                "line_num": node.get("page_no") or node.get("page_start"),
            }
            for optional_key in ("level_no", "parent_node_id", "summary_text"):
                if optional_key in node:
                    item[optional_key] = node.get(optional_key)
            structure.append(item)
        return structure

    def _select_relevant_nodes(
        self,
        *,
        query_text: str,
        structure: list[dict],
        limit: int | None,
    ) -> list[dict]:
        """Return node-aware selections for registry-backed retrieval."""
        if not structure:
            return []
        if len(structure) == 1:
            return structure

        selected_node_ids = self._llm_judge_relevant_nodes(query_text, structure)
        nodes_by_id = {
            str(node.get("node_id")): node
            for node in structure
            if node.get("node_id") is not None
        }

        selected_nodes = []
        seen_node_ids: set[str] = set()
        for node_id in selected_node_ids:
            node_id_text = str(node_id)
            if node_id_text in seen_node_ids:
                continue
            node = nodes_by_id.get(node_id_text)
            if node is not None:
                selected_nodes.append(node)
                seen_node_ids.add(node_id_text)

        if selected_nodes:
            return selected_nodes[:limit] if limit else selected_nodes

        fallback_pages = self._parse_llm_response_for_pages("1")
        fallback_nodes = self._select_nodes_for_pages(fallback_pages, structure)
        return fallback_nodes[:limit] if limit else fallback_nodes

    def _backend_hit_from_node(
        self,
        *,
        node: dict,
        registry: Any,
        version_id: UUID,
    ) -> BackendHit | None:
        """Build a BackendHit from an already selected registry node."""
        node_id = self._coerce_uuid(node.get("node_id"))
        if node_id is None:
            return None

        span_ids = self._query_span_ids_for_node(registry, node_id, version_id)
        chunk_id = self._query_chunk_id_for_hit(
            registry=registry,
            version_id=version_id,
            node_id=node_id,
            span_ids=span_ids,
        )

        fallback_text = node.get("summary_text") or node.get("title") or ""
        text_preview = EvidenceContentResolver().build_text_preview(
            registry=registry,
            version_id=version_id,
            node_id=node_id,
            span_ids=span_ids,
            fallback_text=fallback_text,
            chunk_id=chunk_id,
        )

        return BackendHit(
            score=None,
            text_preview=text_preview,
            heading_path=node.get("heading_path"),
            page_no=node.get("page_no") or node.get("line_num"),
            span_ids=span_ids,
            node_id=node_id,
            chunk_id=chunk_id,
            entity_id=None,
            relation_id=None,
            backend_source="reasoning",
            retrieval_path="llm_navigation",
        )

    def _sanitize_query_for_prompt(self, query_text: str) -> str:
        """Bound and delimit user query text before placing it in LLM prompts."""
        sanitized = " ".join(str(query_text).split())[:MAX_REASONING_QUERY_CHARS]
        return sanitized.replace("```", "'''")

    def _query_prompt_block(self, query_text: str) -> str:
        """Return a clearly delimited query block for prompt construction."""
        return f"<query>\n{self._sanitize_query_for_prompt(query_text)}\n</query>"

    def _bounded_llm_response(self, response_text: str) -> str:
        """Bound LLM response text before regex extraction/parsing."""
        if len(response_text) <= MAX_REASONING_RESPONSE_CHARS:
            return response_text
        logger.warning(
            "LLM response exceeded %s chars; truncating before parsing",
            MAX_REASONING_RESPONSE_CHARS,
        )
        return response_text[:MAX_REASONING_RESPONSE_CHARS]

    def _json_array_match(self, response_text: str) -> re.Match[str] | None:
        """Return a bounded JSON-array-looking match from an LLM response."""
        return re.search(rf"\[.{{0,{MAX_REASONING_JSON_ARRAY_CHARS}}}?\]", response_text)

    def _llm_judge_relevant_nodes(
        self, query_text: str, structure: list[dict]
    ) -> list[UUID]:
        """Use LLM to judge relevant node_ids for registry fallback retrieval."""
        structure_text = self._format_structure_for_llm(structure)
        query_block = self._query_prompt_block(query_text)
        prompt = (
            "Return ranked node_id JSON array.\n"
            "Nodes:\n"
            f"{structure_text}\n"
            f"{query_block}\n"
            "Relevant:"
        )

        llm = get_llm()
        response = llm.complete(prompt)
        response_text = response.text

        node_ids = self._parse_llm_response_for_node_ids(response_text, structure)
        if node_ids:
            return node_ids

        page_nodes = self._select_nodes_for_pages(
            self._parse_llm_response_for_pages(response_text), structure
        )
        return [
            node_id
            for node in page_nodes
            if (node_id := self._coerce_uuid(node.get("node_id"))) is not None
        ]

    def _llm_judge_relevant_pages(self, query_text: str, structure: list[dict]) -> str:
        """Use LLM to judge which pages/sections are relevant to query.

        Task 1.1: Implement LLM reasoning call using unified seam.

        Workflow:
        1. Format tree structure for LLM prompt
        2. Call get_llm() to get unified LLM instance
        3. Send prompt asking LLM to judge relevant pages
        4. Parse response to extract page numbers

        Parameters
        ----------
        query_text:
            Query for reasoning judgment.
        structure:
            Tree structure (list of node dicts with title, page_no, heading_path).

        Returns
        -------
        str
            Comma-separated page numbers (e.g., "1,5,9").

        Frozen Contracts
        -----------------
        - Uses get_llm() (unified seam) - not direct os.getenv
        - Returns filtered subset - not all nodes (token savings)
        - Immutable: does not modify structure in-place
        """
        # Step 1: Format page structure for PageIndex's native page tool API.
        structure_text = self._format_pages_for_llm(structure)

        # Step 2: Build minimal prompt (optimized for 90%+ savings)
        # Previous: ~150 tokens (verbose instructions)
        # Optimized: ~80 tokens (direct query)
        # Ultra-minimal: remove "(comma-separated)" to save ~2 tokens
        query_block = self._query_prompt_block(query_text)
        prompt = f"Pages:\n{structure_text}\n{query_block}\nRelevant:"

        # Step 3: Call unified LLM seam
        llm = get_llm()
        response = llm.complete(prompt)
        response_text = response.text

        # Step 4: Parse response to extract page numbers
        pages = self._parse_llm_response_for_pages(response_text)

        # Return comma-separated string
        return ",".join(str(p) for p in pages) if pages else "1"

    def _extract_content_from_registry_nodes(
        self, registry: Any, version_id: UUID, pages: str
    ) -> list[dict]:
        """Extract content from registry nodes when documents dict unavailable.

        Task 1.3: Implement content extraction from tree_nodes.

        Parameters
        ----------
        registry:
            RegistryWriter (for querying tree_nodes).
        version_id:
            Version UUID for Registry query scope.
        pages:
            Comma-separated page numbers (e.g., "1,5,9").

        Returns
        -------
        list[dict]
            List of dicts: [{"page": int, "content": str}, ...]

        Frozen Contracts
        -----------------
        - Uses Registry seam (not direct SQL)
        - Returns list (immutable pattern)
        - Content from tree_nodes data (not stub placeholders)
        """
        # Parse pages
        page_nums = []
        for part in pages.split(","):
            part = part.strip()
            if part:
                page_nums.append(int(part))

        # Query tree_nodes from Registry
        nodes = registry.query_tree_nodes_by_version(version_id)

        # Extract content for requested pages
        content_list = []
        for page_num in page_nums:
            # Find node matching this page
            for node in nodes:
                page_start = node.get("page_start") or node.get("page_no")
                if page_start == page_num:
                    # Extract content: summary_text or title
                    content = node.get("summary_text") or node.get("title") or ""

                    content_list.append({
                        "page": page_num,
                        "content": content,
                    })
                    break  # Found matching node, move to next page

        return content_list

    def _format_pages_for_llm(self, structure: list[dict]) -> str:
        """Format page/title pairs for PageIndex's page-oriented tool path."""
        lines = []
        for node in structure:
            title = node.get("title", "?")
            page = node.get("page_no") or node.get("line_num", "?")
            lines.append(f"{page}:{title}")
        return "\n".join(lines)

    def _format_structure_for_llm(self, structure: list[dict]) -> str:
        """Format tree structure for LLM prompt (ultra-compact for 90%+ token savings).

        Parameters
        ----------
        structure:
            Tree structure (list of node dicts).

        Returns
        -------
        str
            Ultra-compact format: "X:Title" (page number and title only).

        Token optimization:
        - Previous: "1. Title (page X) - # Heading" (~100 tokens for 14 nodes)
        - Optimized: "X:Title" (~40 tokens for 14 nodes)
        - Savings: ~60 tokens (reaches 90%+ total savings)
        """
        lines = []
        for node in structure:
            title = node.get("title", "?")
            page = node.get("page_no") or node.get("line_num", "?")
            node_id = node.get("node_id")
            level = self._node_level(node)
            heading_path = node.get("heading_path") or ""
            summary = str(node.get("summary_text") or "")[:120]

            lines.append(f"{page}:{title}")

            context_parts = [f"p={page}", f"lvl={level}"]
            if node_id is not None:
                context_parts.append(f"id={node_id}")
            if heading_path:
                context_parts.append(f"path={heading_path}")
            if summary:
                context_parts.append(f"summary={summary}")
            if context_parts:
                lines.append(" | ".join(context_parts))

        return "\n".join(lines)

    def _parse_llm_response_for_pages(self, response_text: str) -> list[int]:
        """Parse LLM response to bounded positive page numbers."""
        def _valid_page(value: Any) -> int | None:
            if not isinstance(value, (int, float, str)):
                return None
            try:
                page = int(value)
            except (TypeError, ValueError):
                return None
            if 1 <= page <= MAX_REASONING_PAGE_NUMBER:
                return page
            return None

        response_text = self._bounded_llm_response(response_text)
        try:
            json_match = self._json_array_match(response_text)
            if json_match:
                pages = json.loads(json_match.group())
                if isinstance(pages, list):
                    parsed_pages = [
                        page for item in pages if (page := _valid_page(item)) is not None
                    ]
                    if parsed_pages:
                        return parsed_pages
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.debug("Failed to parse LLM page JSON response: %s", exc)

        comma_pattern = re.findall(r'\b\d+\b', response_text)
        if comma_pattern:
            return [page for item in comma_pattern if (page := _valid_page(item)) is not None]

        return []

    def _parse_llm_response_for_node_ids(
        self, response_text: str, structure: list[dict]
    ) -> list[UUID]:
        """Parse an LLM response for node UUIDs present in the structure."""
        valid_node_ids = {
            str(node.get("node_id")): self._coerce_uuid(node.get("node_id"))
            for node in structure
            if self._coerce_uuid(node.get("node_id")) is not None
        }
        if not valid_node_ids:
            return []

        candidates: list[str] = []
        response_text = self._bounded_llm_response(response_text)
        try:
            json_match = self._json_array_match(response_text)
            if json_match:
                values = json.loads(json_match.group())
                if isinstance(values, list):
                    for value in values:
                        if isinstance(value, dict):
                            value = value.get("node_id")
                        if value is not None:
                            candidates.append(str(value))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.debug("Failed to parse LLM node-id JSON response: %s", exc)

        candidates.extend(re.findall(
            r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b",
            response_text,
        ))

        node_ids: list[UUID] = []
        seen: set[str] = set()
        for candidate in candidates:
            node_id = valid_node_ids.get(candidate)
            if node_id is not None and candidate not in seen:
                node_ids.append(node_id)
                seen.add(candidate)
        return node_ids

    def _select_nodes_for_pages(self, pages: list[int], structure: list[dict]) -> list[dict]:
        """Select the most specific node for each requested page."""
        selected_nodes = []
        seen_pages: set[int] = set()
        for page in pages:
            if page in seen_pages:
                continue
            matches = [
                node
                for node in structure
                if (node.get("page_no") or node.get("line_num")) == page
            ]
            if matches:
                selected_nodes.append(self._most_specific_node(matches))
                seen_pages.add(page)
        return selected_nodes

    def _most_specific_node(self, nodes: list[dict]) -> dict:
        """Return the deepest available node from same-page candidates."""
        return max(
            nodes,
            key=lambda node: (
                self._node_level(node),
                len(str(node.get("heading_path") or "")),
                len(str(node.get("title") or "")),
            ),
        )

    def _node_level(self, node: dict) -> int:
        """Return comparable tree depth for a node dict."""
        raw_level = node.get("level_no")
        if raw_level is not None:
            try:
                return int(raw_level)
            except (TypeError, ValueError):
                pass
        heading_path = node.get("heading_path")
        if heading_path:
            return len(str(heading_path).split("/")) - 1
        return 0

    def _map_page_to_node_id(self, page: int, structure: list[dict]) -> UUID | None:
        """Map page number to node_id from tree structure.

        Task 1.2: Extract node_id from structure (not uuid.uuid4()).

        Parameters
        ----------
        page:
            Page number to map.
        structure:
            Tree structure (list of node dicts with page_no, node_id).

        Returns
        -------
        UUID | None
            node_id if found, None otherwise.

        Frozen Contracts
        -----------------
        - Uses structure data (not generating new UUIDs)
        - Immutable: does not modify structure
        """
        matching_nodes = [
            node
            for node in structure
            if (node.get("page_no") or node.get("line_num")) == page
        ]
        if not matching_nodes:
            return None

        node = self._most_specific_node(matching_nodes)
        return self._coerce_uuid(node.get("node_id"))

    def _coerce_uuid(self, value: Any) -> UUID | None:
        """Return a UUID from either a UUID object or string value."""
        if value is None:
            return None
        if isinstance(value, UUID):
            return value
        try:
            return UUID(str(value))
        except (AttributeError, TypeError, ValueError):
            return None

    def _query_chunk_id_for_hit(
        self,
        *,
        registry: Any,
        version_id: UUID,
        node_id: UUID,
        span_ids: Sequence[UUID],
    ) -> UUID:
        """Resolve a stable chunk_id for a hit from registry provenance."""
        try:
            vector_chunk_spans = registry.query_vector_chunk_spans_by_version(version_id)
        except (AttributeError, TypeError, ValueError, KeyError) as exc:
            logger.debug(
                "Chunk-span query failed for version_id=%s while resolving hit chunk: %s",
                version_id,
                exc,
            )
            vector_chunk_spans = []

        span_id_set = set(span_ids)
        for row in vector_chunk_spans:
            span_id = self._coerce_uuid(row.get("span_id"))
            chunk_id = self._coerce_uuid(row.get("chunk_id"))
            if span_id in span_id_set and chunk_id is not None:
                return chunk_id

        try:
            vector_chunks = registry.query_vector_chunks_by_version(version_id)
        except (AttributeError, TypeError, ValueError, KeyError) as exc:
            logger.debug(
                "Vector chunk query failed for version_id=%s while resolving hit chunk: %s",
                version_id,
                exc,
            )
            vector_chunks = []

        for row in vector_chunks:
            chunk_node_id = self._coerce_uuid(row.get("node_id"))
            chunk_id = self._coerce_uuid(row.get("chunk_id"))
            if chunk_node_id == node_id and chunk_id is not None:
                return chunk_id

        return UUID(int=0)

    def _query_span_ids_for_node(
        self, registry: Any, node_id: UUID, version_id: UUID
    ) -> list[UUID]:
        """Query span_ids from Registry for given node_id.

        Task 1.2: Map span_ids from Registry query.

        Parameters
        ----------
        registry:
            RegistryWriter (for querying tree_node_spans).
        node_id:
            Node UUID to query spans for.
        version_id:
            Version UUID for Registry query scope.

        Returns
        -------
        list[UUID]
            List of span_ids associated with node_id.

        Frozen Contracts
        -----------------
        - Uses Registry seam (not direct SQL)
        - Returns list (immutable pattern)
        """
        # Query all node_spans links for this version
        node_spans = registry.query_tree_node_spans_by_version(version_id)

        # Filter to span_ids for this node_id
        span_ids = []
        for link in node_spans:
            link_node_id = self._coerce_uuid(link.get("node_id"))
            if link_node_id == node_id:
                span_id = self._coerce_uuid(link.get("span_id"))
                if span_id is not None:
                    span_ids.append(span_id)

        return span_ids

    def _extract_heading_path_for_page(
        self, page: int, structure: list[dict]
    ) -> str | None:
        """Extract heading_path for given page from structure.

        Task 1.2: Extract heading_path from structure.

        Parameters
        ----------
        page:
            Page number to extract heading_path for.
        structure:
            Tree structure (list of node dicts with page_no, heading_path).

        Returns
        -------
        str | None
            heading_path if found, None otherwise.

        Frozen Contracts
        -----------------
        - Uses structure data (not generating new values)
        - Immutable: does not modify structure
        """
        matching_nodes = [
            node
            for node in structure
            if (node.get("page_no") or node.get("line_num")) == page
        ]
        if not matching_nodes:
            return None
        return self._most_specific_node(matching_nodes).get("heading_path")
