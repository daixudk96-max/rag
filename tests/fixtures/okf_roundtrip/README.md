# OKF Round-Trip Fixtures

| Fixture | Format | Key Test |
|---------|--------|----------|
| sectioned-pdf | PDF | Multi-level heading_path |
| complex-layout-pdf | PDF | Tables and nested structure |
| docx | DOCX | Unicode/Chinese/emoji |

## Validation

From `<repo-root>`:

```bash
python tests/fixtures/okf_roundtrip/validate_fixtures.py
```

## Regeneration

```bash
C:/Users/daixu/AppData/Local/Temp/docling-hierarchy-verify-2109/venv/Scripts/python.exe \
  tests/fixtures/okf_roundtrip/generate_fixtures.py
```
