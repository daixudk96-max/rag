---
type: documentation
title: OKF Template Contract
description: Contract for OKF v0.1 document templates.
timestamp: "<ISO-8601-timestamp>"
---

# OKF template contract

The authoritative template path is `<OKF_BUNDLE_ROOT>/templates`; this repository's default examples live in `okf_bundle/templates`. These templates target OKF v0.1. `type` is required and must be one of the template's declared values. ISO-8601 timestamps are quoted strings so YAML retains their original producer representation. UUID placeholders denote canonical UUID values. Entity, relation, and concept persisted knowledge pages must replace the `"<ISO-8601-timestamp>"` sentinel with a valid ISO-8601 timestamp before admission. Raw `timestamp` is optional template/lint metadata, is not emitted by the deterministic serializer, and is not a raw-pair admission requirement.

## Raw

`raw.md` is the machine-generated raw-document contract. Required frontmatter: `type: raw`, `doc_id`, `version_id`, `source_checksum`, `docling_version`, and `generated_by`. The template's `description` and `timestamp` are optional template/lint metadata; the current deterministic serializer does not emit them. Its adjacent `.spans.json` sidecar is the authority for `page_no`, `heading_path`, `offset`, normalized text, and recorded `span_id`; do not hand-edit either file.

## Entity

`entity.md` requires `type: entity`, `title`, `timestamp`, `canonical_entity_id`, and `entity_type`. Optional extensions are `tags`, `aliases`, `relations`, and `mentions`. `tags` and `aliases` are lists of non-empty strings. `relations` is a list of relation objects using the relation contract. `mentions` is a list of span-backed mention mappings; each must retain span provenance and character offsets when it is persisted. These fields are the formal contract, not sample-only inference.

For the existing `okf-bundles/main/entities/e001-...` sample and its mentions only, legacy `E001` was migrated once and deterministically to `uuid5(uuid.NAMESPACE_URL, "E001") = 31c6abd8-ee07-5706-8e64-838909674dfc`. This is not a new-entity or Phase 16 `canonical_entity_id` generation algorithm; Phase 16 rules remain open and governed by its boundary decisions.

## Relation

`relation.md` requires `type: relation`, `subject_entity_id`, `predicate`, `object_entity_id`, and `timestamp`. `title` is optional but recommended for a human-readable relation page. Optional top-level qualifiers are `negation` (boolean), `condition` (string or null), `direction` (string or null), `confidence` (a finite number from 0 through 1 or null), and `qualifiers` (a mapping). Use `qualifiers.valid_time` for relation time: it may contain any non-empty subset of `start`, `end`, and `expression`; omitted keys are equivalent to null. Bounds are null or valid ISO-8601 strings, `expression` is null or non-empty text, and at least one value must be non-null. If both time bounds are present, they must be comparable and `start` must not be after `end`. Other qualifier keys are preserved for future extensions; unknown keys inside `valid_time` are rejected.

## Concept

`concept.md` requires `type: concept`, `title`, and `timestamp`. Optional extensions are `tags`, `aliases`, `relations`, and `mentions`, with the same meanings and provenance obligations as the entity template.

## Parser resource budgets

Untrusted Markdown is rejected before reading when its stat size exceeds 64 MiB. Extracted frontmatter is limited to 1 MiB, YAML composition depth to 64, YAML nodes to 10,000, and aliases to 32. Parsing uses SafeLoader semantics; budget and malformed-YAML errors intentionally do not include source content or file paths.

Parser behavior is fail-fast for invalid raw and known non-raw frontmatter, and malformed YAML. Unknown document types retain legacy behavior. Unknown non-raw top-level extensions are retained in `extra_fields`; consumers must reject unsupported semantics explicitly rather than discard them.
