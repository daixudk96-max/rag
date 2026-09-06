---
type: documentation
title: OKF Bundle Agent Instructions
description: Instructions for maintaining this OKF bundle.
timestamp: "<ISO-8601-timestamp>"
---

# OKF Bundle Agent Instructions

## Always do

- Keep valid YAML frontmatter on editable OKF Markdown pages.
- Treat `raw/` as machine-generated output from the docling-to-OKF serializer.
- Treat adjacent `*.spans.json` sidecars as the sole source of span identity.
- Make human knowledge edits in `entities/`, `concepts/`, and `synthesis/`.
- Use bundle-relative absolute links for cross-page references.

## Ask first

- Before deleting or substantially restructuring knowledge pages.
- Before changing this bundle's directory structure or type taxonomy.
- Before changing raw-document provenance or regenerating an existing raw document.

## Never

- Modify files in `raw/` by hand.
- Modify a raw document's adjacent `*.spans.json` sidecar by hand.
- Remove or alter the `type` field in an existing editable OKF page.
- Use relative links (`./`) for cross-page references.
