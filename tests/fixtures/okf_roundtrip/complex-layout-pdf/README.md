# complex-layout-pdf Fixture

## Description

PDF with a table, complex layout, and heading hierarchy.

## Contents

| File | Description |
|------|-------------|
| source.pdf | Locally authored source document |
| docling_output.json | Frozen `DoclingNodeParser` node sequence |
| expected_span_ids.json | Expected coordinates and span IDs from the production direct chain |

## Fixed UUIDs

- doc_id: `00000000-0000-0000-0000-000000000001`
- version_id: `00000000-0000-0000-0000-000000000003`

## Regeneration

Run from `<repo-root>` with the required isolated environment:

```bash
C:/Users/daixu/AppData/Local/Temp/docling-hierarchy-verify-2109/venv/Scripts/python.exe \
  tests/fixtures/okf_roundtrip/generate_fixtures.py
```

The generator stages all three fixtures, validates all staged outputs, then
atomically swaps complete fixture directories into place. A failure leaves the
published fixture set unchanged when rollback succeeds. If rollback fails, the
generator preserves named stage and backup directories for manual recovery.

**Docling version**: `2.109.0`

## Migration characterization

The hierarchy reader intentionally changes `heading_path` and therefore
`span_id` for aligned nested PDF spans. The production migration test proves
that matching spans retain `page_no`, `offset`, and `text`; root headings can
remain unchanged while nested headings gain hierarchy. A custom reader can be
injected into `DoclingIngestor` for rollback.

## License

Locally authored. Apache-2.0 compatible.
