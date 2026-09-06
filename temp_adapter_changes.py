import re

# Read original file
with open('llamaindex_runtime/tree/pageindex_adapter.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Update the docstring and method implementation
new_index_tree = '''    def index_tree(
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

        # Build node_spans (placeholder - will be filled by SpanIndexer)
        node_spans = []
        for node_dict in flat_nodes:
            # span_ids will be populated later when spans are indexed
            node_spans.append(
                {
                    "node_id": node_dict["node_id"],
                    "span_id": None,  # Placeholder
                    "ordinal_no": 0,
                }
            )

        # Write through registry seam
        registry.write_tree(
            version_id=version_id,
            nodes=flat_nodes,
            node_spans=node_spans,
        )'''

# Find the index_tree method and replace it
pattern = r'    def index_tree\([\s\S]*?\n        \)'
match = re.search(pattern, content)
if match:
    # Replace the method
    new_content = content[:match.start()] + new_index_tree + content[match.end():]
    
    # Write back
    with open('llamaindex_runtime/tree/pageindex_adapter.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Updated index_tree method")
else:
    print("Could not find index_tree method")
