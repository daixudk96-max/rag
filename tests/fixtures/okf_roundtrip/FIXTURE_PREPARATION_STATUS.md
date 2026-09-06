# Phase 14-04 Fixture Preparation Summary

## Resolution: Docling 2.109 HeadingHierarchyModel (User-Approved Phase 14 Scope Expansion)

**Previous limitation (docling 2.93.0):** Docling's PDF OCR pipeline flattened all section headers to `level=1`, making multi-level `heading_path` unachievable for PDF fixtures. The earlier version of this document documented that as a hard architectural limitation.

**Resolution (docling 2.109.0):** The user explicitly approved pinning `docling==2.109.0` and enabling Docling's official `HeadingHierarchyModel` in the default production reader (`_build_default_reader`). This model infers section-header levels from PDF bookmarks/outline, numbering patterns, and font style.

### Configured Chain

The default reader (`DoclingIngestor._build_default_reader()`) now constructs:

```
DocumentConverter(format_options={
    InputFormat.PDF: PdfFormatOption(
        pipeline_options=PdfPipelineOptions(
            heading_hierarchy_options=HeadingHierarchyOptions(
                enabled=True,
                use_bookmarks=True,
                use_numbering=True,
                use_style=True,
                max_level=6,
                bookmark_match_threshold=0.8,
            ),
            generate_parsed_pages=True,  # Required for style inference
        )
    )
})
```

This is injected into `DoclingReader(export_type='json', doc_converter=...)`.

### Actual Docling Version

- **docling**: 2.109.0 (pinned in `llamaindex_runtime/pyproject.toml`)
- **llama-index-readers-docling**: 0.4.2
- **llama-index-node-parser-docling**: 0.4.2

### Span-ID Migration Implication

Enabling `HeadingHierarchyModel` changes the `headings` metadata field (the heading_path) for PDF documents. Because `span_id` is computed as `uuid5(NAMESPACE_URL, f"{doc_id}|{version_id}|{page_no}|{'/'.join(headings)}|{offset}|{text}")`, the span_ids for PDF spans with multi-level headings WILL DIFFER from the old flat-reader output.

This is an **intentional migration boundary**, not a regression:
- for spans that align between the flat and hierarchy readers, the production migration test proves `page_no`, `offset`, and `text` match
- heading_path changes from flat (depth=1) to hierarchical (depth>=2) for nested aligned spans; root headings can remain unchanged
- span_id changes as a direct consequence when the heading_path changes
- The `DoclingIngestor(reader=custom_reader)` injection path remains available for rollback

### Fixture Status

| Fixture | Format | Requirement | Status |
|---------|--------|-------------|--------|
| sectioned-pdf | PDF | Multi-level heading_path (depth >= 2) | **PASS** - depth 3 achieved |
| complex-layout-pdf | PDF | Table + provenance/charspan | **PASS** - table with page_no and charspan |
| docx | DOCX | Unicode/Chinese/emoji | **PASS** - CJK + emoji verified |

### T9 Preservation

T9 (span_id round-trip gate) is preserved: the real sectioned PDF exercises multi-level `heading_path` with depth >= 2 (actual depth 3). The fixture generator uses the exact configured default reader/direct chain, and frozen JSON tests run fully offline without invoking Docling conversion.

## Regeneration

```bash
# Must use the isolated 2.109 environment
C:/Users/daixu/AppData/Local/Temp/docling-hierarchy-verify-2109/venv/Scripts/python.exe \
  tests/fixtures/okf_roundtrip/generate_fixtures.py
```

The fixture generator reads the installed Docling version dynamically via
`importlib.metadata.version("docling")` and compares it against the pinned,
hardcoded required version `REQUIRED_DOCLING_VERSION = "2.109.0"`.
