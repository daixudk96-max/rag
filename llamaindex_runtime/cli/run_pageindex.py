"""PageIndex CLI tool - Workspace-only, non-authoritative consumer.

PageIndex is a CONSUMER of canonical E2a tree data, not an author.
This CLI provides workspace-only indexing with optional canonical data consumption.

Usage Examples:
```bash
# PDF索引（workspace-only）
python run_pageindex.py --pdf_path doc.pdf \
  --workspace ~/.pageindex_workspace

# Markdown索引（workspace-only）
python run_pageindex.py --md_path doc.md

# Consume canonical tree data (--version-id required for registry)
python run_pageindex.py --pdf_path doc.pdf \
  --version-id <canonical-uuid> \
  --workspace ~/.pageindex_workspace

# Note: --write-to-registry is DEPRECATED (backward compatibility only)
```
"""

import argparse
import os
import json
from pathlib import Path

from llamaindex_runtime.client import EnhancedPageIndexClient
from llamaindex_runtime.registry import PostgresRegistryWriter
from llamaindex_runtime.config import RuntimeSettings


def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(
        description="PageIndex document indexing CLI (workspace-only, non-authoritative)"
    )

    # 文档路径（必选）
    parser.add_argument("--pdf_path", type=str, help="Path to the PDF file")
    parser.add_argument("--md_path", type=str, help="Path to the Markdown file")

    # Registry集成参数
    parser.add_argument(
        "--write-to-registry",
        type=str,
        default="no",
        help="[DEPRECATED] Has no effect. PageIndex is a consumer of canonical data, "
        "not an author. This flag is retained for backward compatibility only.",
    )
    parser.add_argument(
        "--version-id",
        type=str,
        default=None,
        help="Registry version ID for querying canonical data (optional)",
    )

    # Workspace配置
    parser.add_argument(
        "--workspace",
        type=str,
        default=None,
        help="PageIndex workspace path (default: RuntimeSettings.pageindex_workspace)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./results",
        help="Output directory for JSON structure (default: ./results)",
    )

    # 模型配置
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="LLM model (overrides RuntimeSettings.llm_model)",
    )

    # PDF参数
    parser.add_argument(
        "--toc-check-pages",
        type=int,
        default=None,
        help="Number of pages to check for table of contents (PDF only)",
    )
    parser.add_argument(
        "--max-pages-per-node",
        type=int,
        default=None,
        help="Maximum number of pages per node (PDF only)",
    )
    parser.add_argument(
        "--max-tokens-per-node",
        type=int,
        default=None,
        help="Maximum number of tokens per node (PDF only)",
    )

    # Node配置
    parser.add_argument(
        "--if-add-node-id",
        type=str,
        default="yes",
        help="Whether to add node id to the node",
    )
    parser.add_argument(
        "--if-add-node-summary",
        type=str,
        default="yes",
        help="Whether to add summary to the node",
    )
    parser.add_argument(
        "--if-add-doc-description",
        type=str,
        default="yes",
        help="Whether to add doc description to the doc",
    )
    parser.add_argument(
        "--if-add-node-text",
        type=str,
        default="yes",
        help="Whether to add text to the node",
    )

    # Markdown参数
    parser.add_argument(
        "--if-thinning",
        type=str,
        default="no",
        help="Whether to apply tree thinning for markdown",
    )
    parser.add_argument(
        "--thinning-threshold",
        type=int,
        default=5000,
        help="Minimum token threshold for thinning (markdown only)",
    )
    parser.add_argument(
        "--summary-token-threshold",
        type=int,
        default=200,
        help="Token threshold for generating summaries (markdown only)",
    )

    args = parser.parse_args()

    # Validate that exactly one file type is specified
    if not args.pdf_path and not args.md_path:
        raise ValueError("Either --pdf_path or --md_path must be specified")
    if args.pdf_path and args.md_path:
        raise ValueError("Only one of --pdf_path or --md_path can be specified")

    # Validate file existence
    file_path = args.pdf_path or args.md_path
    if not os.path.isfile(file_path):
        # SECURITY: Static error (no raw path exposure)
        raise ValueError("Document file not found")

    # Load RuntimeSettings
    settings = RuntimeSettings.from_env()

    # Override settings if CLI args specified
    if args.model:
        settings.llm_model = args.model

    workspace = args.workspace or settings.pageindex_workspace

    # Registry setup
    # PageIndex is consumer-only: never authors canonical E2a data
    # --write-to-registry is DEPRECATED (backward compatibility only)
    # Registry is only initialized when --version-id is provided (canonical consumer request)
    registry = None
    write_to_registry = args.write_to_registry.lower() == "yes"

    # Validate version_id UUID format before registry initialization
    canonical_version_uuid = None
    if args.version_id:
        try:
            import uuid

            canonical_version_uuid = uuid.UUID(args.version_id)
        except (ValueError, AttributeError):
            # SECURITY: Static error (no raw version_id exposure)
            raise ValueError("version_id must be a valid UUID")

    # Only initialize registry when valid version_id provided
    # Without version_id, PageIndex works in workspace-only mode (no registry)
    if canonical_version_uuid:
        if write_to_registry:
            import warnings

            warnings.warn(
                "--write-to-registry has no effect. PageIndex is a consumer of canonical data, "
                "not an author. This flag is deprecated and retained for backward compatibility only.",
                UserWarning,
            )
        print(
            "Initializing Registry connection (read-only for consuming canonical data)..."
        )
        registry = PostgresRegistryWriter(settings)
    elif write_to_registry:
        # write_to_registry=yes but no version_id - warn and continue workspace-only
        import warnings

        warnings.warn(
            "--write-to-registry requires --version-id for canonical data consumption. "
            "Without --version-id, PageIndex operates in workspace-only mode.",
            UserWarning,
        )

    # Initialize PageIndexClient
    client = EnhancedPageIndexClient(
        registry=registry,
        settings=settings,
        workspace=workspace,
        model=args.model,
    )

    # Index document
    # SECURITY: Do not echo raw file paths, version IDs, or document details
    print("PageIndex indexing started")

    doc_id = client.index(
        file_path=file_path,
        mode="auto",
        version_id=args.version_id,
        write_to_registry=write_to_registry,
    )

    print("PageIndex indexing complete")

    # Save structure to JSON (PageIndex原版功能)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Get document structure
    structure_json = client.get_document_structure(doc_id)
    structure = json.loads(structure_json)

    # SECURITY: Do not echo output file paths
    output_file = output_dir / f"{doc_id}_structure.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(structure, f, indent=2, ensure_ascii=False)

    print("Tree structure saved")

    if write_to_registry:
        print(
            "NOTE: --write-to-registry has no effect. PageIndex returns non-authoritative workspace result."
        )

    # Print summary (SECURITY: no raw paths or version IDs)
    metadata_json = client.get_document(doc_id)
    metadata = json.loads(metadata_json)

    print("\n--- Document Metadata ---")
    # SECURITY: Do not print document name, description, or file paths
    print(f"Type: {metadata.get('type', '')}")
    if metadata.get("type") == "pdf":
        print(f"Page count: {metadata.get('page_count', 0)}")
    else:
        print(f"Line count: {metadata.get('line_count', 0)}")
    if metadata.get("canonical_version_id"):
        print("Canonical version: available")


if __name__ == "__main__":
    main()
