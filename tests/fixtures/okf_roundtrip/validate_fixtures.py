"""Validate OKF round-trip fixtures.

This script validates that all fixture files:
1. Load successfully (JSON parse)
2. Have valid UUIDs for doc_id, version_id, and all span_ids
3. Have non-empty expected spans
4. Have docling_output.json with correct structure
5. Pass recomputation check

Usage:
    python tests/fixtures/okf_roundtrip/validate_fixtures.py

No Docling dependency required - validates frozen JSON only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TypedDict
from uuid import UUID, NAMESPACE_URL, uuid5

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from llamaindex_runtime.ingestion.docling_ingestor import DoclingIngestor
from llamaindex_runtime.ingestion.normalization import NormalizationContract

FIXTURE_DIR = Path(__file__).parent

FIXTURE_DOC_ID = "00000000-0000-0000-0000-000000000001"
FIXTURE_VERSION_ID = "00000000-0000-0000-0000-000000000003"


class ValidationResult(TypedDict):
    """Result of validating one fixture directory."""

    name: str
    valid: bool
    errors: list[str]
    span_count: int
    node_count: int


def validate_uuid(value: str, field: str) -> None:
    """Validate that a string is a valid UUID."""
    try:
        UUID(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid UUID: {value}") from exc


def recompute_span_id(
    doc_id: str,
    version_id: str,
    page_no: int | None,
    heading_path: list[str],
    offset: int,
    text: str,
) -> str:
    """Recompute span_id using the exact formula."""
    return str(
        uuid5(
            NAMESPACE_URL,
            f"{doc_id}|{version_id}|{page_no}|{'/'.join(heading_path)}|{offset}|{text}",
        )
    )


def validate_fixture(
    fixture_name: str, *, fixture_root: Path = FIXTURE_DIR
) -> ValidationResult:
    """Validate one published or staged fixture directory offline."""
    fixture_dir = fixture_root / fixture_name

    results: ValidationResult = {
        "name": fixture_name,
        "valid": True,
        "errors": [],
        "span_count": 0,
        "node_count": 0,
    }

    # Load expected_span_ids.json
    expected_path = fixture_dir / "expected_span_ids.json"
    if not expected_path.exists():
        results["valid"] = False
        results["errors"].append(f"Missing {expected_path}")
        return results

    try:
        with open(expected_path, encoding="utf-8") as f:
            expected = json.load(f)
    except json.JSONDecodeError as exc:
        results["valid"] = False
        results["errors"].append(f"Invalid JSON in {expected_path}: {exc}")
        return results

    # Validate top-level UUIDs
    try:
        validate_uuid(expected["doc_id"], "doc_id")
        validate_uuid(expected["version_id"], "version_id")
    except ValueError as exc:
        results["valid"] = False
        results["errors"].append(str(exc))
        return results

    # Validate spans
    spans = expected.get("spans", [])
    if not spans:
        results["valid"] = False
        results["errors"].append("Empty spans array")
        return results

    results["span_count"] = len(spans)

    if fixture_name == "sectioned-pdf":
        max_depth = max(len(span.get("heading_path", [])) for span in spans)
        if max_depth < 2:
            results["valid"] = False
            results["errors"].append(
                f"sectioned-pdf requires heading_path depth >= 2, got {max_depth}"
            )

    if fixture_name == "docx":
        document_text = " ".join(
            span.get("text", "") + " " + " ".join(span.get("heading_path", []))
            for span in spans
        )
        if not any("一" <= character <= "鿿" for character in document_text):
            results["valid"] = False
            results["errors"].append("docx requires Chinese characters")
        if not any(ord(character) > 0x1F000 for character in document_text):
            results["valid"] = False
            results["errors"].append("docx requires emoji content")

    for i, span in enumerate(spans):
        try:
            validate_uuid(span["span_id"], f"spans[{i}].span_id")
        except ValueError as exc:
            results["valid"] = False
            results["errors"].append(str(exc))

        for field in ["page_no", "heading_path", "offset", "text"]:
            if field not in span:
                results["valid"] = False
                results["errors"].append(f"spans[{i}] missing required field: {field}")

        if not span.get("text"):
            results["valid"] = False
            results["errors"].append(f"spans[{i}] has empty text")

        if not isinstance(span.get("offset"), int) or span["offset"] < 0:
            results["valid"] = False
            results["errors"].append(
                f"spans[{i}] has invalid offset: {span.get('offset')}"
            )

        if not isinstance(span.get("heading_path"), list):
            results["valid"] = False
            results["errors"].append(
                f"spans[{i}] has invalid heading_path: {span.get('heading_path')}"
            )

    # Load docling_output.json
    nodes_path = fixture_dir / "docling_output.json"
    if not nodes_path.exists():
        results["valid"] = False
        results["errors"].append(f"Missing {nodes_path}")
    else:
        try:
            with open(nodes_path, encoding="utf-8") as f:
                nodes = json.load(f)
            if not isinstance(nodes, list):
                results["valid"] = False
                results["errors"].append("docling_output.json must be a JSON array")
            else:
                results["node_count"] = len(nodes)

                # Validate node structure
                for i, node in enumerate(nodes):
                    if "text" not in node:
                        results["errors"].append(f"nodes[{i}] missing text field")
                    if "metadata" not in node:
                        results["errors"].append(f"nodes[{i}] missing metadata field")

                if fixture_name == "complex-layout-pdf":
                    has_table_provenance = any(
                        isinstance(node, dict)
                        and isinstance(node.get("metadata"), dict)
                        and isinstance(node["metadata"].get("doc_items"), list)
                        and node["metadata"]["doc_items"]
                        and isinstance(node["metadata"]["doc_items"][0], dict)
                        and node["metadata"]["doc_items"][0].get("label") == "table"
                        and isinstance(
                            node["metadata"]["doc_items"][0].get("prov"), list
                        )
                        and node["metadata"]["doc_items"][0].get("prov")
                        and isinstance(
                            node["metadata"]["doc_items"][0]["prov"][0], dict
                        )
                        and "page_no" in node["metadata"]["doc_items"][0]["prov"][0]
                        and "charspan" in node["metadata"]["doc_items"][0]["prov"][0]
                        for node in nodes
                    )
                    if not has_table_provenance:
                        results["valid"] = False
                        results["errors"].append(
                            "complex-layout-pdf requires a table doc_item with provenance page_no and charspan"
                        )

                contract = NormalizationContract()
                recomputed_spans = []
                for ordinal, node in enumerate(nodes):
                    text = node.get("text", "")
                    if not isinstance(text, str) or not text.strip():
                        continue

                    metadata = node.get("metadata", {})
                    if not isinstance(metadata, dict):
                        results["valid"] = False
                        results["errors"].append(
                            f"nodes[{ordinal}].metadata must be an object"
                        )
                        continue

                    flat_metadata = DoclingIngestor._flatten_docling_metadata(metadata)
                    normalized = contract.normalize(
                        raw_text=text,
                        metadata=flat_metadata,
                        ordinal=ordinal,
                    )
                    span_id = recompute_span_id(
                        expected["doc_id"],
                        expected["version_id"],
                        normalized.page_no,
                        list(normalized.headings),
                        normalized.offset,
                        normalized.text,
                    )
                    recomputed_spans.append(
                        {
                            "span_id": span_id,
                            "page_no": normalized.page_no,
                            "heading_path": list(normalized.headings),
                            "offset": normalized.offset,
                            "text": normalized.text,
                        }
                    )

                # Compare recomputed vs expected
                if len(recomputed_spans) != len(spans):
                    results["errors"].append(
                        f"Span count mismatch: recomputed={len(recomputed_spans)}, expected={len(spans)}"
                    )
                else:
                    for i, (rec, exp) in enumerate(zip(recomputed_spans, spans)):
                        for field in (
                            "span_id",
                            "page_no",
                            "heading_path",
                            "offset",
                            "text",
                        ):
                            if rec[field] != exp[field]:
                                results["valid"] = False
                                results["errors"].append(
                                    f"span[{i}] {field} mismatch: "
                                    f"recomputed={rec[field]!r}, expected={exp[field]!r}"
                                )

        except json.JSONDecodeError as exc:
            results["valid"] = False
            results["errors"].append(f"Invalid JSON in {nodes_path}: {exc}")

    # Check README.md exists
    readme_path = fixture_dir / "README.md"
    if not readme_path.exists():
        results["errors"].append(f"Missing {readme_path} (non-blocking)")

    # Set valid=False if any errors
    if results["errors"]:
        # Filter out non-blocking warnings
        blocking_errors = [e for e in results["errors"] if "(non-blocking)" not in e]
        if blocking_errors:
            results["valid"] = False

    return results


def main():
    """Validate all fixtures."""
    fixtures = ["sectioned-pdf", "complex-layout-pdf", "docx"]

    print("Validating OKF round-trip fixtures...")
    print("=" * 60)

    all_valid = True
    total_spans = 0
    total_nodes = 0

    for fixture_name in fixtures:
        results = validate_fixture(fixture_name)

        status = "PASS" if results["valid"] else "FAIL"
        print(f"\n{fixture_name}: {status}")
        print(f"  Nodes: {results['node_count']}")
        print(f"  Spans: {results['span_count']}")
        total_spans += results["span_count"]
        total_nodes += results["node_count"]

        if results["errors"]:
            print("  Issues:")
            for error in results["errors"]:
                print(f"    - {error}")

        if not results["valid"]:
            all_valid = False

    print("\n" + "=" * 60)
    print(f"Total nodes: {total_nodes}")
    print(f"Total spans: {total_spans}")

    if all_valid:
        print("\nAll fixtures VALID!")
        return 0
    else:
        print("\nSome fixtures INVALID!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
