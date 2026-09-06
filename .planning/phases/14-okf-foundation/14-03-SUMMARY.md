---
phase: 14-okf-foundation
plan: 03
subsystem: okf
tags: [serializer, parser, raw-pair-manifest, mdsm-admission, sync-decision, delete-detection, tdd]
requires: [14-01, 14-02]
provides:
  - Docling→OKF serializer producing `raw/<slug>.md`, `raw/<slug>.spans.json`, and mandatory `raw/<slug>.pair.json`
  - Parser completion: shared M-D-S-M manifest admission for raw files, fail-fast frontmatter validation
  - Sync decision DTO/function for incremental sync
  - Delete detection via path comparison
  - Relation qualifier passthrough (no silent drops)
affects:
  - llamaindex_runtime/okf/serializer.py
  - llamaindex_runtime/okf/parser.py
  - tests/llamaindex_runtime/okf/test_okf_serializer_*.py
  - tests/llamaindex_runtime/okf/test_okf_parser_completion.py
tech-stack:
  added: []
  patterns:
    - import NormalizationContract (never reimplement normalization)
    - frozen dataclass DTOs for immutable results
    - fail-fast boundary validation for raw files
    - sidecar as source of truth for span identity
key-files:
  created:
    - llamaindex_runtime/okf/serializer.py
    - tests/llamaindex_runtime/okf/test_okf_serializer_*.py
    - tests/llamaindex_runtime/okf/test_okf_parser_completion.py
  modified:
    - llamaindex_runtime/okf/parser.py
key-decisions:
  - "Serializer imports and uses NormalizationContract from ingestion module — never copies logic"
  - "Raw files: span identity comes only from the sidecar admitted through the mandatory shared M-D-S-M manifest contract, never from the Markdown body"
  - "Raw frontmatter validated via RawFrontmatterContract with fail-fast on missing fields"
  - "Non-raw files pass through without RawFrontmatterContract validation"
  - "SyncDecision frozen dataclass: doc_id, status, canonical_hash, okf_file_path"
  - "compute_deleted_paths returns frozenset(previous_paths - current_paths)"
  - "Relation qualifiers preserved in frontmatter.relations without silent drops"
duration: "2026-07-14 execution and verification"
completed: 2026-07-14
---

# Phase 14 Plan 03: OKF Serializer + Parser Completion Summary

Docling→OKF serializer and parser completion enabling manifest-bound raw-file round-trip with sidecar-sourced span identity.

All production raw reads use one shared M-D-S-M admission: the authority/capability is opened on the configured bundle root and read resolution is constrained to its logical `<bundle-root>/raw/` subtree. The serializer emits zero-depth files; the reader accepts safe nested raw descendants. The three adjacent same-slug artifacts are `raw/<slug>.md`, `raw/<slug>.spans.json`, and mandatory `raw/<slug>.pair.json`; manifest member references are plain filenames, it is published last, and production parsing has no legacy or sidecar-only fallback.

## One-Liner

Serializer imports NormalizationContract (no reimplementation), emits mandatory manifest-bound Markdown/sidecar/manifest raw sets, and parser accepts raw spans only after shared M-D-S-M admission; frontmatter remains fail-fast, sync decisions computed, deletions detected, and relation qualifiers preserved.

## Deliverables

### Task 2: Serializer (RED → GREEN)

**Status:** COMPLETE

- Created split serializer test modules (`tests/llamaindex_runtime/okf/test_okf_serializer_*.py`) covering:
  - Module imports NormalizationContract (no reimplementation)
  - serialize_document API shape and return type
  - Output file locations: `raw/<slug>.md`, `raw/<slug>.spans.json`, and mandatory `raw/<slug>.pair.json`
  - Manifest is adjacent, same-slug, plain-filename-bound, deterministic, and published last; production parsing requires it
  - Serializer emits only zero-depth files; reader accepts safe nested descendants under logical `raw/`
  - Frontmatter passes RawFrontmatterContract
  - Sidecar spans match NormalizationContract output
  - span_id uses uuid5 six-element formula
  - Determinism: same input yields byte-identical output
  - Slug validation and path containment
  - Human-readable markdown body
  - Optional title derivation

- Implemented `llamaindex_runtime/okf/serializer.py`:
  - `SerializedRawFile` frozen dataclass with `dropped_node_count` field (immutable result)
  - `serialize_document()` function accepting docling-output-shaped `Sequence[object]`
  - Imports `NormalizationContract` from ingestion module (single source of truth)
  - Calls `DoclingIngestor._flatten_docling_metadata(metadata)` directly (imported, not copied)
  - Reads normalization metadata only from `node.metadata` (matching direct chain)
  - Produces the zero-depth `raw/<slug>.md`, `raw/<slug>.spans.json`, and mandatory `raw/<slug>.pair.json`
  - Builds the adjacent same-slug manifest with plain member filenames, byte hashes, and frozen canonical-v1 hash; publisher validates all three and publishes the manifest last
  - Deterministic output: same input yields byte-identical artifacts

### Task 3: Parser Completion (RED → GREEN)

**Status:** COMPLETE

- Created `tests/llamaindex_runtime/okf/test_okf_parser_completion.py` with tests covering:
  - Raw file with mandatory manifest and sidecar is admitted by shared M-D-S-M before spans are exposed
  - Missing/invalid manifest, member-hash mismatch, or canonical-v1 mismatch fails closed; there is no sidecar-only fallback
  - Markdown reflow does not affect the frozen canonical-v1 hash
  - Serializer zero-depth files and safe nested reader inputs are both covered
  - Raw file missing doc_id raises named error
  - Non-raw type parses successfully (no RawFrontmatterContract validation)
  - Sync decisions: unchanged→skip, changed→resync, new→synced
  - Delete detection via path comparison
  - Known qualifiers preserved
  - Unknown future qualifiers preserved (spillover)
  - Bundle skips index.md/log.md at all depths
  - Bundle skips .obsidian directory
  - Malformed file skip with stats (bundle scan)
  - Legacy paragraph parsing preserved for non-raw files
  - OKFParagraph constructor unchanged

- Extended `llamaindex_runtime/okf/parser.py`:
  - `SyncDecision` frozen dataclass: `doc_id`, `status`, `canonical_hash`, `okf_file_path`
  - `compute_sync_decision(*, doc_id, okf_file_path, current_canonical_hash, previous_state)` keyword-only
  - `compute_deleted_paths(previous_paths, current_paths)` returns `frozenset[str]`
  - `OKFDocument.spans: tuple[SpanRecord, ...]` using sidecar's frozen type directly
  - Raw file frontmatter validation occurs within the shared manifest-bound admission path
  - Manifest/Markdown/sidecar byte hashes and the frozen canonical-v1 hash are verified before exposing sidecar spans
  - Span identity is sourced from the admitted sidecar (not derived from body)
  - Relation qualifiers preserved without silent drops via `extra_fields` spillover

## Verification Results

The numeric results below are retained as the historical Phase 14-03 record. They predate the mandatory manifest-bound M-D-S-M production-admission contract and are not evidence that a sidecar-only raw input is currently valid. Current raw-path verification must require all three artifacts, verify the manifest's same-directory plain-filename binding and frozen canonical-v1/sidecar-v1 semantics, verify manifest-last publication without claiming cross-file atomicity, reject missing manifests and legacy fallbacks, and cover both zero-depth serializer output and safe nested reader input.

### Focused Serializer + Parser Tests

```
python -m pytest tests/llamaindex_runtime/okf/test_okf_serializer_*.py tests/llamaindex_runtime/okf/test_okf_parser_completion.py -q
107 passed, 2 warnings
```

### Serializer-Only Tests

```
python -m pytest tests/llamaindex_runtime/okf/test_okf_serializer_*.py -q
33 passed, 2 warnings
```

### Full Non-Live OKF Suite

```
python -m pytest tests/llamaindex_runtime/okf/ -q
179 passed, 5 skipped, 2 warnings
```

### Normalization + Docling Regression Tests

```
python -m pytest tests/llamaindex_runtime/test_normalization_contract.py tests/llamaindex_runtime/test_docling_ingestion.py -q
82 passed, 2 warnings
```

### Static Verification

- **mypy** (scoped: `--follow-imports=skip` on parser.py/serializer.py): success, no issues
- **Ruff** (4 Phase 14-03 files): all checks passed
- **py_compile** (4 files): passed
- **git diff --check** (4 files): passed (no whitespace issues)

### Branch Coverage

```
parser.py + serializer.py (focused tests): 89% total
  - parser.py: 86%
  - serializer.py: 94%
```

## Review Results

### Security Review

**Verdict:** APPROVE — 0 CRITICAL, 0 HIGH

**Future Hardening (MEDIUM):**
- Symlink scan during bundle traversal
- No span/docling count/size caps

**LOW:** YAML exception/log messages may expose YAML content snippets

Note: These hardening items were NOT fixed in this phase; they are documented for future work.

### Python Review

**Verdict:** APPROVE — 0 CRITICAL, 0 HIGH

Only non-blocking maintainability notes (e.g., consider extracting helper functions for readability).

### General Review

**Initial Findings:** 2 HIGH issues identified:
1. Root headings enrichment divergence: serializer-only enrichment code path
2. Root doc_items lift: metadata source mismatch

**Resolution:** Both issues fixed by:
- Deleting serializer-only enrichment code
- Adding four direct-chain-equivalent regression tests proving `S_direct == S_okf`

**Final Re-Review:** APPROVE — 0 CRITICAL, 0 HIGH

## GitNexus Impact Analysis

### Initial Pre-Edit Impacts (all LOW)

| Symbol | Impact | Call Chain |
|--------|--------|------------|
| OKFParser.parse_paragraphs | LOW, 3 impacted | direct caller `parse_document`, then `parse_bundle`/`main` |
| OKFParser.compute_hash | LOW, 3 impacted | same chain as parse_paragraphs |
| OKFParagraph | LOW, 1 impacted | `okf/__init__.py` import only |
| NormalizationContract | LOW, 15 impacted | 2 direct imports, 0 affected process |
| DoclingIngestor._flatten_docling_metadata | LOW, 5 impacted | direct caller `_build_span`, then `ingest`/`verification` |

### After Final Review Finding and Forced Reindex

| Symbol | Impact | Details |
|--------|--------|---------|
| serialize_document (upstream) | HIGH, 23 impacted | All direct test callers; 0 affected production processes; 1 module (Okf). HIGH risk was broad regression surface, warned before edit, all callers covered by full serializer tests. |
| _extract_metadata (upstream) | LOW, 24 impacted | 1 direct caller `serialize_document`; 0 affected processes |

**Note:** No HIGH/CRITICAL production execution flow was reported. The HIGH risk on `serialize_document` was due to broad test-caller surface, all of which were covered by the full serializer test suite.

## Key Implementation Details

### Serializer Normalization Import

The serializer explicitly imports and reuses the direct chain's normalization:

```python
from llamaindex_runtime.ingestion.normalization import NormalizationContract
from llamaindex_runtime.ingestion.docling_ingestor import DoclingIngestor

# Call the EXACT shared flattening helper from DoclingIngestor.
flat_metadata = DoclingIngestor._flatten_docling_metadata(metadata)

# Apply normalization contract (single source of truth).
contract = NormalizationContract()
normalized = contract.normalize(
    raw_text=raw_text,
    metadata=flat_metadata,
    ordinal=ordinal,
)
```

This is the critical constraint from the plan — any reimplementation would eventually diverge and break round-trip. The code reads normalization metadata only from `node.metadata`, matching the direct chain.

### Manifest-Bound Raw Span Identity

For raw files, span identity is sourced ONLY from the sidecar in a `RawPairSnapshot` returned after one stable shared M-D-S-M admission:

```python
snapshot = read_raw_pair(bundle_authority, markdown_parts)
spans = snapshot.sidecar.spans  # tuple[SpanRecord, ...]
```

`read_raw_pair` uses the authority/capability opened on the configured bundle root and constrains reads to the logical `<bundle-root>/raw/` subtree. It reads manifest → Markdown → sidecar → manifest, verifies exact byte hashes and frozen canonical-v1 semantics, and accepts only adjacent same-slug artifacts whose manifest member names are plain filenames in that same directory. Missing manifests, legacy sidecar-only input, cross-directory binding, and invalid sidecar-v1 data fail closed. The serializer emits zero-depth sets; the reader also accepts safe nested descendants. Publishing the manifest last is a visibility protocol, not a cross-file atomicity claim.

The `OKFDocument.spans` field is typed as `tuple[SpanRecord, ...]` — no separate `OKFSpan` DTO exists. The Markdown body is NOT used to derive span coordinates.

### Dual Hash

- `OKFParser.compute_hash()` computes raw-byte SHA256 → `OKFDocument.version_hash` (legacy raw markdown hash)
- Structural canonical hash → `OKFDocument.canonical_hash` (excludes body for reflow stability)
- `source_checksum` is the serializer caller-provided original source file checksum, passed through `RawFrontmatterContract` into `OKFFrontmatter.source_checksum`

### Typed Provenance

Typed raw provenance fields are on `OKFFrontmatter`:
- `doc_id: str | None`
- `version_id: str | None`
- `source_checksum: str | None`
- `docling_version: str | None`
- `generated_by: str | None`

These are populated for raw files and `None` otherwise. There is no separate `OKFDocument.provenance` field.

### Timestamp Handling

`_parse_timestamp()` handles `OKFFrontmatter.timestamp` robustly:
- `datetime` returned as-is
- `date` converted to midnight `datetime`
- `str` parsed via `datetime.fromisoformat()` after normalizing trailing `Z` (UTC) suffix
- Invalid strings or other types log warning and return `None`

### Sync Decision Logic

Pure function with keyword-only arguments:

```python
@dataclass(frozen=True)
class SyncDecision:
    doc_id: str
    status: str  # "synced" | "skipped" | "resynced"
    canonical_hash: str
    okf_file_path: str

def compute_sync_decision(
    *,
    doc_id: str,
    okf_file_path: str,
    current_canonical_hash: str,
    previous_state: Mapping[str, Any] | None,
) -> SyncDecision:
    # previous_state is used ONLY for hash comparison.
    # Current identity (doc_id, okf_file_path) is always preserved.
```

Delete detection uses frozenset arithmetic:

```python
def compute_deleted_paths(
    previous_paths: AbstractSet[str],
    current_paths: AbstractSet[str],
) -> frozenset[str]:
    return frozenset(previous_paths - current_paths)
```

### Logical Raw-Subtree Boundary

Raw-pair enforcement applies when the bundle-relative path begins with `raw`:
- The authority/capability is opened on the configured bundle root; raw-pair reads are constrained to the logical `<bundle-root>/raw/` subtree, which includes safe nested descendants
- A nested directory named `raw` outside that logical subtree (for example, `entities/raw/`) does NOT trigger raw-pair admission
- The serializer writes only the zero-depth form; this is not a direct-child-only reader restriction

### Parser Implementation Details

- **Raw admission authority:** `read_raw_pair` uses the authority/capability opened on the configured bundle root; all M-D-S-M reads are constrained to its logical `raw/` subtree
- **Manifest-bound sidecar identity:** `snapshot.sidecar.spans` is exposed only after adjacent same-slug Markdown, sidecar-v1, and mandatory manifest pass byte-hash and frozen canonical-v1 admission; no legacy/sidecar-only fallback
- **Manifest publication:** serializer emits zero-depth plain-filename members and publishes the manifest last; this makes no cross-file atomicity claim
- **Relation/unknown field fidelity:** `extra_fields` dict preserves unknown frontmatter keys
- **BundleDocuments canonical class + BundleResult alias:** Clean return types
- **Stats:** `BundleStats` with `parsed`, `skipped`, `malformed` counts
- **Keyword-only sync decisions:** `compute_sync_decision` uses keyword-only args
- **Frozenset delete detection:** Path comparison uses immutable set operations
- **POSIX paths:** `okf_file_path` uses POSIX separators for OS-independent sync state
- **Sorted scan:** `bundle_path.rglob("*.md")` wrapped in `sorted()` for deterministic ordering
- **Legacy non-raw paragraphs:** The `split("\n\n")` path remains for files without sidecars

## Deviations from Plan

Implementation-time review deviations corrected before closure:
1. Initial serializer-only root headings enrichment code deleted
2. Root doc_items metadata source fixed to match direct chain

No planned deviations remain.

## Known Stubs

None. All planned functionality implemented.

## Non-Goals Honored

- No database persistence (deferred to 14-04)
- No production caller switch (direct chain unchanged)
- No NER, no PageIndex tuning, no fusion-weight change
- No agent writeback, no Level claims

## Threat Model Compliance

| Threat ID | Category | Disposition | Evidence |
|-----------|----------|-------------|----------|
| T-14-05 | Tampering (normalization divergence) | mitigate | Serializer imports NormalizationContract and calls `DoclingIngestor._flatten_docling_metadata(metadata)` directly; grep confirms no `def normalize` or flattening reimplementation in serializer.py |
| T-14-06 | DoS/corruption (malformed manifest/sidecar/frontmatter) | mitigate | Shared M-D-S-M admission through the bundle-root authority/capability validates the mandatory adjacent manifest, exact member bytes, sidecar-v1, frozen canonical-v1, and raw frontmatter before exposing a raw document; malformed bundle candidates are skipped with stats (not silent, not crash) |

## Output

Files created/modified:
- `llamaindex_runtime/okf/serializer.py` — serializer emitting zero-depth Markdown, sidecar-v1, and mandatory pair manifest
- `llamaindex_runtime/okf/parser.py` — bundle-root-authority M-D-S-M raw admission, sync types, and delete detection
- `tests/llamaindex_runtime/okf/test_okf_serializer_*.py` — split serializer test modules
- `tests/llamaindex_runtime/okf/test_okf_parser_completion.py` — new test file

No commit made; unrelated dirty working-tree files remain untouched.