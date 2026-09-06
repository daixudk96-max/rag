# Normalization Contract (v1)

## Locked parser baseline

- Parser: Docling
- Offset basis: `normalized_char_offset`

## Rules

1. Text normalization must be deterministic for the same input and parser version.
2. `page_no` and `heading_path` must be produced from the same parsing run as spans.
3. Any change to parser version, OCR mode, heading normalization, or offset basis requires a new `version_id`.
4. `span_id` is only trustworthy under a fixed normalization contract.
