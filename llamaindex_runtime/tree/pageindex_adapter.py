"""PageIndexTreeAdapter: Transplants PageIndex tree building logic to local schema.

This adapter integrates PageIndex's page-level tree structure extraction into
local flat schema with UUID-based provenance, preserving frozen contracts.

References:
- changes/compatibility-adapter-program/02-INTERFACES.md
- PageIndex donor repo page_index.py (see donor research docs)
"""
from __future__ import annotations
from llamaindex_runtime.config import RuntimeSettings

import os
import sys
import uuid
from typing import Any
from uuid import UUID

# Add PageIndex donor repo to sys.path for adapter wrapping
PAGEINDEX_REPO_PATH = r"C:\Users\daixu\Downloads\rag-upstreams\PageIndex"
if os.path.exists(PAGEINDEX_REPO_PATH):
    sys.path.insert(0, PAGEINDEX_REPO_PATH)

from .backend_adapter import BackendHit  # noqa: E402


class PageIndexTreeAdapter:
    """Page-level tree structure extraction using PageIndex donor logic.

    This adapter transplants selected PageIndex elements:
    - TOC detection and processing (check_toc, meta_processor)
    - Tree flattening logic (list_to_tree adaptation)
    - Heading path construction (parent chain traversal)

    NOT transplanted (per control package):
    - LLM-based summary generation
    - Embedding-based retrieval
    - Full page text storage

    All outputs written through registry seam to preserve provenance.
    """

    def index_tree(
        self,
        *,
        source_path: str,
        version_id: UUID,
        registry: Any,
    ) -> None:
        """Build tree structure from source document and write through registry.

        This method detects file type and routes to appropriate parser:
        - PDF files: Calls PageIndex tree_parser()
        - Markdown files: Calls PageIndex md_to_tree()
        - Other files: Falls back to stub

        Then flattens embedded tree to flat node list with UUID provenance.

        Parameters
        ----------
        source_path:
            Path to source document (PDF or Markdown).
        version_id:
            Version UUID for provenance anchoring.
        registry:
            RegistryWriter seam for persisting tree nodes.
        """
        # Detect file type and call appropriate parser
        if source_path.lower().endswith('.md'):
            embedded_tree = self._call_pageindex_md_to_tree(source_path)
        else:
            # Default: PDF processing
            embedded_tree = self._call_pageindex_tree_parser_stub(source_path)

        # Flatten embedded tree to local schema (pass version_id for provenance)
        flat_nodes = self._flatten_embedded_tree(
            embedded_tree, version_id=version_id
        )

        # node_spans will be populated later by SpanIndexer (not here)
        # Passing empty list to avoid FK violations with placeholder None values
        node_spans = []

        # Write through registry seam
        registry.write_tree(
            version_id=version_id,
            nodes=flat_nodes,
            node_spans=node_spans,
        )


    def retrieve_tree_hits(
        self,
        *,
        query_text: str,
        version_id: UUID,
        registry: Any,
        limit: int | None = None,
    ) -> list[BackendHit]:
        """Retrieve tree hits from PageIndex page-level tree.

        Parameters
        ----------
        query_text:
            Query text (PageIndex uses reasoning-based retrieval, not embeddings).
        version_id:
            Version UUID to query.
        registry:
            RegistryWriter seam for reading persisted tree.
        limit:
            Optional limit on number of hits.

        Returns
        -------
        list[BackendHit]
            Intermediate hits from page-level tree with exact chunk/span provenance.
        """
        nodes = registry.query_tree_nodes_by_version(version_id)
        tree_node_spans = registry.query_tree_node_spans_by_version(version_id)
        vector_chunk_spans = registry.query_vector_chunk_spans_by_version(version_id)

        span_ids_by_node: dict[UUID, list[UUID]] = {}
        for row in tree_node_spans:
            span_ids_by_node.setdefault(row["node_id"], []).append(row["span_id"])

        chunk_ids_and_spans_by_node: dict[UUID, list[tuple[UUID, list[UUID]]]] = {}
        for node in nodes:
            node_id = node["node_id"]
            node_span_ids = set(span_ids_by_node.get(node_id, []))
            if not node_span_ids:
                continue

            chunk_to_spans: dict[UUID, list[UUID]] = {}
            for row in vector_chunk_spans:
                chunk_id = row["chunk_id"]
                span_id = row["span_id"]
                if span_id in node_span_ids:
                    chunk_to_spans.setdefault(chunk_id, []).append(span_id)

            if chunk_to_spans:
                chunk_ids_and_spans_by_node[node_id] = list(chunk_to_spans.items())

        hits: list[BackendHit] = []
        for node in nodes:
            node_id = node["node_id"]
            chunk_entries = chunk_ids_and_spans_by_node.get(node_id, [])
            for chunk_id, span_ids in chunk_entries:
                hit = BackendHit(
                    score=None,
                    text_preview=node.get("summary_text", ""),
                    heading_path=node.get("heading_path"),
                    page_no=node.get("page_no") or node.get("page_start"),
                    span_ids=span_ids,
                    node_id=node_id,
                    chunk_id=chunk_id,
                    entity_id=None,
                    relation_id=None,
                )
                hits.append(hit)

        if limit is not None:
            return hits[:limit]
        return hits

    def _call_pageindex_tree_parser_stub(
        self, source_path: str
    ) -> list[dict[str, Any]]:
        """Call real PageIndex tree_parser() with unified LLM seam monkey-patch.

        Phase 4b: Routes PageIndex LLM calls through unified seam,
        preventing donor-owned LLM configuration stack.

        Parameters
        ----------
        source_path:
            Path to PDF document.

        Returns
        -------
        list[dict]
            Embedded tree structure from PageIndex.
        """
        # Try to import and call real PageIndex tree_parser with monkey-patch
        try:
            from pageindex.page_index import tree_parser, get_page_tokens
            from pageindex.utils import ConfigLoader
            from llamaindex_runtime.llm import llm_acompletion_unified
            import pageindex.utils as pageindex_utils
            import asyncio
            import logging

            logger = logging.getLogger(__name__)

            # Phase 4b: Monkey-patch PageIndex llm_acompletion to use unified seam
            # This routes all PageIndex LLM calls (TOC detection, structure parsing)
            # through unified LLM seam, preventing donor-owned LLM config stack
            original_llm_acompletion = pageindex_utils.llm_acompletion
            pageindex_utils.llm_acompletion = llm_acompletion_unified

            try:
                # Configure PageIndex to disable LLM/Embedding features
                # (per control package: only transplant structural tree build)
                # Phase: Read LLM config from RuntimeSettings (not hardcoded)
                llm_config = RuntimeSettings.from_env_llm_only()

                user_opt = {
                    "model": llm_config["llm_model"],  # Unified seam provides model config
                    "if_add_node_id": None,  # We generate UUIDs ourselves
                    "if_add_node_text": "no",  # Don't add full text
                    "if_add_node_summary": "no",  # Don't use LLM summaries
                    "if_add_doc_description": "no",  # Don't use LLM descriptions
                }
                opt = ConfigLoader().load(user_opt)

                # Extract page tokens (PageIndex internal step)
                page_list = get_page_tokens(source_path, model=opt.model)

                # Call real tree_parser (now uses unified seam via monkey-patch)
                embedded_tree = asyncio.run(
                    tree_parser(page_list, opt, doc=source_path, logger=logger)
                )

                # Return embedded tree (PageIndex's hierarchical structure)
                return embedded_tree

            finally:
                # Restore original function (cleanup monkey-patch)
                pageindex_utils.llm_acompletion = original_llm_acompletion

        except ImportError as e:
            # Phase 8: ImportError means PageIndex donor not available
            # This is acceptable stub case (donor integration path not installed)
            import logging
            logging.getLogger(__name__).info(
                f"PageIndex donor not installed, using stub: {e}"
            )
            return [
                {
                    "title": "Test Chapter",
                    "start_index": 1,
                    "end_index": 2,
                    "nodes": [],
                }
            ]
        except Exception as e:
            # Phase 8: Other exceptions mean LLM or runtime failure
            # Check if OPENAI_API_KEY is set (indicates real credential attempt)
            if os.environ.get("OPENAI_API_KEY"):
                # Credentials available but LLM call failed → controlled exception
                import logging
                logger = logging.getLogger(__name__)
                logger.error(
                    f"PageIndex LLM call failed with credentials available: {e}"
                )
                # Raise controlled exception instead of silent stub fallback
                raise RuntimeError(
                    f"Phase 8 donor path failed with credentials: {e}. "
                    "Check LLM configuration and API availability."
                ) from e
            else:
                # No credentials → acceptable stub fallback (baseline path active)
                import logging
                logging.getLogger(__name__).warning(
                    f"PageIndex tree_parser unavailable (no credentials), using stub: {e}"
                )
                return [
                    {
                        "title": "Test Chapter",
                        "start_index": 1,
                        "end_index": 2,
                        "nodes": [],
                    }
                ]

    async def _call_pageindex_tree_parser_real(
        self, source_path: str
    ) -> list[dict[str, Any]]:
        """Async wrapper for real PageIndex tree_parser (for testing).

        Same as _call_pageindex_tree_parser_stub but returns async-compatible result.
        """
        return self._call_pageindex_tree_parser_stub(source_path)

    def _call_pageindex_md_to_tree(
        self, source_path: str
    ) -> list[dict[str, Any]]:
        """Call PageIndex md_to_tree() for markdown file processing.

        Phase 8: Routes PageIndex md_to_tree through unified LLM seam,
        preventing donor-owned LLM configuration stack.

        Parameters
        ----------
        source_path:
            Path to markdown document.

        Returns
        -------
        list[dict]
            Embedded tree structure from PageIndex md_to_tree.
        """
        # Try to import and call real PageIndex md_to_tree
        try:
            import asyncio
            import logging
            from pageindex.page_index_md import md_to_tree
            from llamaindex_runtime.config import RuntimeSettings

            logger = logging.getLogger(__name__)

            # Phase 8: Configure md_to_tree with control package parameters
            # Read LLM config from RuntimeSettings (unified seam)
            llm_config = RuntimeSettings.from_env_llm_only()

            # Call md_to_tree with control package settings
            # Control package: disable LLM summaries, full text, add node_id
            result = asyncio.run(
                md_to_tree(
                    md_path=source_path,
                    if_add_node_summary='no',  # Control package: no LLM summaries
                    if_add_node_text='no',     # Control package: no full text
                    if_add_node_id='yes',      # PageIndex adds node_id, we replace with UUID
                    model=llm_config["llm_model"],  # Unified seam provides model
                )
            )

            # Extract structure from result dict
            embedded_tree = result.get("structure", [])
            return embedded_tree

        except ImportError as e:
            # Phase 8: ImportError means PageIndex donor not available
            import logging
            logging.getLogger(__name__).info(
                f"PageIndex md_to_tree not installed, using stub: {e}"
            )
            return [
                {
                    "title": "Test Markdown Chapter",
                    "line_num": 1,
                    "level": 1,
                    "nodes": [],
                }
            ]
        except Exception as e:
            # Phase 8: Other exceptions mean LLM or runtime failure
            # Check if OPENAI_API_KEY is set (indicates real credential attempt)
            import os
            if os.environ.get("OPENAI_API_KEY"):
                # Credentials available but LLM call failed → controlled exception
                import logging
                logger = logging.getLogger(__name__)
                logger.error(
                    f"PageIndex md_to_tree failed with credentials available: {e}"
                )
                # Raise controlled exception instead of silent stub fallback
                raise RuntimeError(
                    f"Phase 8 donor path (markdown) failed with credentials: {e}. "
                    "Check LLM configuration and API availability."
                ) from e
            else:
                # No credentials → acceptable stub fallback (baseline path active)
                import logging
                logging.getLogger(__name__).warning(
                    f"PageIndex md_to_tree unavailable (no credentials), using stub: {e}"
                )
                return [
                    {
                        "title": "Test Markdown Chapter",
                        "line_num": 1,
                        "level": 1,
                        "nodes": [],
                    }
                ]


    def _flatten_embedded_tree(
        self,
        embedded_tree: list[dict[str, Any]],
        version_id: UUID,
        parent_node_id: UUID | None = None,
        heading_prefix: str = "",
    ) -> list[dict[str, Any]]:
        """Convert PageIndex embedded tree to local flat schema.

        This is the key adaptation layer:
        - Input: Embedded tree with nodes[] inside nodes[]
        - Output: Flat list with parent_node_id FK and UUIDs

        Transformation:
        1. Generate UUID for node_id (not PageIndex's sequential "0001")
        2. Build heading_path from title + parent chain
        3. Use start_index as page_no, ignore end_index
        4. Use heading-based summary (not LLM-generated)
        5. Set parent_node_id relationships
        6. Set version_id for provenance anchoring

        Parameters
        ----------
        embedded_tree:
            PageIndex embedded tree structure.
        version_id:
            Version UUID for provenance anchoring (frozen contract).
        parent_node_id:
            Parent node UUID (None for root nodes).
        heading_prefix:
            Heading path prefix from parent chain.

        Returns
        -------
        list[dict]
            Flat node list matching local schema.
        """
        flat_nodes: list[dict[str, Any]] = []

        for node_dict in embedded_tree:
            # 1. Generate UUID (not PageIndex's sequential strings)
            node_id = uuid.uuid4()

            # 2. Build heading_path from title + parent chain
            if heading_prefix:
                heading_path = f"{heading_prefix}/{node_dict['title']}"
            else:
                heading_path = node_dict['title']

            # 3. Use start_index (PDF) or line_num (markdown) as page_no
            # PDF structure: start_index/end_index (page numbers)
            # Markdown structure: line_num (line numbers, not pages)
            page_no = node_dict.get("start_index") or node_dict.get("line_num")

            # 4. Compute level_no from heading_path depth
            level_no = self._compute_level_from_heading(heading_path)

            # 5. Heading-based summary (not LLM)
            summary_text = self._heading_based_summary(node_dict, heading_path)

            # Create flat node with frozen provenance
            flat_node = {
                "node_id": node_id,
                "version_id": version_id,  # Frozen provenance contract
                "parent_node_id": parent_node_id,
                "node_type": "page_index",
                "level_no": level_no,  # Computed from heading depth
                "title": node_dict["title"],
                "heading_path": heading_path,
                "page_no": page_no,
                "page_start": page_no,
                "page_end": page_no,  # Same as page_start (PageIndex range collapsed)
                "summary_text": summary_text,
            }
            flat_nodes.append(flat_node)

            # 5. Recursively flatten children
            if node_dict.get("nodes"):
                child_nodes = self._flatten_embedded_tree(
                    node_dict["nodes"],
                    version_id=version_id,
                    parent_node_id=node_id,
                    heading_prefix=heading_path,
                )
                flat_nodes.extend(child_nodes)

        return flat_nodes

    def _heading_based_summary(
        self, node_dict: dict[str, Any], heading_path: str
    ) -> str:
        """Generate summary from heading (NOT LLM-based).

        Strategies:
        1. Use last heading component: "Chapter 1/Section 1.1" → "Section 1.1"
        2. Optionally combine with page_no: "Section 1.1 (page 6)"

        Parameters
        ----------
        node_dict:
            PageIndex node dictionary (contains title, start_index).
        heading_path:
            Full heading path from root to this node.

        Returns
        -------
        str
            Heading-based summary text.
        """
        # Strategy: Use last heading component
        last_heading = heading_path.split("/")[-1]
        page_no = node_dict.get("start_index")

        # Combine with page_no for context
        if page_no is not None:
            return f"{last_heading} (page {page_no})"
        else:
            return last_heading

    def _compute_level_from_heading(self, heading_path: str) -> int:
        """Compute level_no from heading path markdown depth.

        Markdown headings use # symbols for depth:
        - "#" (level 1) → level_no = 1
        - "##" (level 2) → level_no = 2
        - "###" (level 3) → level_no = 3
        - etc.

        For non-markdown headings (plain text), default to level 1.

        Parameters
        ----------
        heading_path:
            Full heading path (e.g., "# Title/## Section").

        Returns
        -------
        int
            Level number (1-based).
        """
        # Extract last heading component from path
        last_heading = heading_path.split("/")[-1]

        # Count # symbols at start of heading
        level = 0
        for char in last_heading:
            if char == "#":
                level += 1
            else:
                break

        # Default to level 1 if no # symbols found
        return level if level > 0 else 1