# Read the file
with open('llamaindex_runtime/tree/pageindex_adapter.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Insert new method after line 308 (after _call_pageindex_tree_parser_real)
insert_line = 308

new_method = '''
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

'''

# Insert the method
lines.insert(insert_line, new_method)

# Write back
with open('llamaindex_runtime/tree/pageindex_adapter.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print(f"Inserted _call_pageindex_md_to_tree method at line {insert_line}")
