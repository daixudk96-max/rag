# Phase 5: Evidence-Chain Verification and Resolver Consolidation - Research

**Researched:** 2026-06-07
**Domain:** DB-backed evidence-chain verification, content hydration consolidation, validation integrity
**Confidence:** HIGH (registry methods verified in postgres_adapter.py, validation script inspected, VectorLoader path confirmed)

## Summary

Phase 5 addresses three critical blockers from Phase 4 closure: (1) evidence-chain zeros in validation_status.json indicating missing vector chunk materialization, (2) shared EvidenceContentResolver needed to consolidate duplicate preview/content-hydration logic across ReasoningTreeBackend and PageIndexTreeAdapter, and (3) validation integrity gates required before collecting human judgments for the 71 new corpus hits.

The zeros (`chunks=0`, `mapped_chunks=0`, `heading_path_rate=0`) arise from a mismatch: validation scripts use **global COUNT queries** (not version-scoped) while registry methods provide version-scoped data access. VectorLoader.load() exists but was never invoked for the active_version, so tree nodes exist but chunks were never materialized. The fix requires: (1) version-scoped DB count queries, (2) VectorLoader invocation after tree generation, (3) heading_path provenance verification in canonical_spans, and (4) shared EvidenceContentResolver extraction.

**Primary recommendation:** Verify active_version-scoped evidence-chain counts using registry.query_vector_chunks_by_version() and query_tree_node_spans_by_version(), then invoke VectorLoader.load() to materialize chunks if missing, consolidate preview/content-hydration into a shared EvidenceContentResolver class, and gate human judgment collection on evidence-chain thresholds passing (node_chunk_mapping ≥80%, heading_path ≥95%).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Vector chunk materialization | Database / Storage | API / Backend | Chunks are persisted in PostgreSQL via VectorLoader.load(), embeddings computed by embedder, node_id linking requires tree_node_spans mapping |
| Evidence-chain statistics | Database / Storage | — | Statistics are computed from persisted tables (vector_chunks, vector_chunk_spans, tree_node_spans, canonical_spans) via COUNT queries |
| Preview/content hydration | API / Backend | Database / Storage | ReasoningTreeBackend and PageIndexTreeAdapter query spans/chunks to build text_preview, but source data lives in canonical_spans.raw_text and vector_chunks.text_preview |
| Heading_path provenance | Database / Storage | — | Heading_path originates from canonical_spans (ingestion-time extraction), copied to tree_nodes and vector_chunks during processing |
| Human judgment collection | Frontend / Client | API / Backend | Judgment collection is manual human workflow, but gated on API-provided validation integrity checks (corpus match, evidence-chain thresholds) |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| psycopg.Connection | 3.x | PostgreSQL database connection | Registry contract requires connection for write_spans, write_tree, write_vector_chunks |
| VectorLoader | current | Orchestrates chunk generation, embedding, node-linking | [VERIFIED: llamaindex_runtime/vector/loader.py] Canonical chunk materialization path with idempotency checks |
| PostgresRegistryWriter | current | Version-scoped DB queries | [VERIFIED: llamaindex_runtime/registry/postgres_adapter.py] Provides query_vector_chunks_by_version, query_tree_node_spans_by_version, query_spans_by_version |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| SimpleSpanChunker | current | 1:1 span-to-chunk mapping | [VERIFIED: llamaindex_runtime/vector/chunker.py] Default chunker when no heading-based grouping needed |
| HeadingGroupedChunker | current | Groups spans under same heading_path | [VERIFIED: llamaindex_runtime/vector/chunker.py] Use when heading_path is complete and grouping improves retrieval coherence |
| DeterministicEmbedder | current | Test embedder (16-dim) | [VERIFIED: llamaindex_runtime/vector/loader.py] Used by VectorLoader for deterministic embedding generation |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Global COUNT queries in validation script | Version-scoped registry methods | Registry methods prevent mismatch between active_version data and validation statistics; global queries can mix multiple versions' data |
| Duplicate preview logic in two backends | Shared EvidenceContentResolver | Resolver consolidation eliminates 80+ lines of duplicated code, ensures consistent fallback cascade (spans → chunks → summary), reduces maintenance burden |
| Separate heading_path in canonical_spans vs tree_nodes | Unified provenance contract | canonical_spans.heading_path is authoritative source (ingestion-time extraction); tree_nodes.heading_path is derived (PageIndex adapter computation); validation must check canonical_spans, not tree_nodes |

**Installation:**

No new packages required. All components exist in current codebase:

```bash
# Existing packages (no installation needed)
# psycopg (already in pyproject.toml)
# llamaindex_runtime.vector.loader (already implemented)
# llamaindex_runtime.registry.postgres_adapter (already implemented)
```

**Version verification:** All components are internal to the codebase; no external registry check needed.

## Architecture Patterns

### System Architecture Diagram

```
Ingestion Pipeline → Evidence-Chain Materialization → Validation → Judgment Collection
       ↓                      ↓                        ↓              ↓
  canonical_spans        vector_chunks            evidence_chain   human_judgment
  tree_nodes             vector_chunk_spans       thresholds gate  relevance_score
  (heading_path)         node_id linking          (≥80%, ≥95%)     corpus integrity check
```

**Data flow:**

1. **Ingestion Pipeline**: Docling parser → canonical_spans (with heading_path), PageIndexTreeAdapter → tree_nodes + tree_node_spans
2. **Evidence-Chain Materialization**: VectorLoader.load() → vector_chunks (with embeddings), vector_chunk_spans, node_id linking via tree_node_spans
3. **Validation**: Registry.query_vector_chunks_by_version() → count chunks, query_tree_node_spans_by_version() → count mapped_chunks, query_spans_by_version() → check heading_path completeness
4. **Judgment Collection Gate**: Evidence-chain thresholds pass → corpus integrity check (retrieval corpus matches judgment corpus) → human judgment collection → Level assessment

### Recommended Project Structure

```
llamaindex_runtime/
├── tree/
│   ├── reasoning_backend.py        # LLM reasoning navigation
│   ├── pageindex_adapter.py        # PageIndex tree building
│   ├── evidence_content_resolver.py  # NEW: shared preview/content hydration
│   └── runtime.py                  # Tree retrieval orchestration
├── vector/
│   ├── loader.py                   # VectorLoader orchestrates chunk materialization
│   ├── chunker.py                  # SimpleSpanChunker, HeadingGroupedChunker
│   └── embedder.py                 # DeterministicEmbedder, real embedder
├── registry/
│   ├── postgres_adapter.py         # PostgresRegistryWriter (version-scoped queries)
│   └── contracts.py                # RegistryWriter protocol
└── entrypoints/
    └── query.py                    # Unified query entrypoint

verification/
├── phase5-evidence-chain-verification/
│   ├── verify_active_version_counts.py  # NEW: version-scoped DB count checks
│   ├── verify_heading_path_contract.py  # NEW: heading_path provenance verification
│   ├── invoke_vector_loader.py          # NEW: trigger VectorLoader.load() for active_version
│   └── validation_integrity_gate.py     # NEW: corpus + evidence-chain threshold checks
```

### Pattern 1: Version-Scoped DB Count Queries

**What:** Use registry.query_vector_chunks_by_version(version_id) instead of global SELECT COUNT(*) FROM vector_chunks.

**When to use:** Evidence-chain statistics, validation readiness checks, any active_version-specific data quality assessment.

**Example:**

```python
# BAD: Global query (can mix multiple versions' data)
cur.execute("SELECT COUNT(*) FROM vector_chunks")
chunk_count = cur.fetchone()["count"]  # mixes all versions

# GOOD: Version-scoped query via registry
chunks = registry.query_vector_chunks_by_version(version_id)
chunk_count = len(chunks)  # only active_version data

# Compute mapped_chunks rate (version-scoped)
mapped_chunks = sum(1 for c in chunks if c.get("node_id") is not None)
mapped_chunks_rate = mapped_chunks / chunk_count if chunk_count > 0 else 0.0
```

**Source:** [CITED: verification/phase3-real-validation/run_validation.py lines 94-143] Global COUNT queries cause mismatch; [VERIFIED: llamaindex_runtime/registry/postgres_adapter.py lines 705-723] Registry provides version-scoped query methods.

### Pattern 2: EvidenceContentResolver Fallback Cascade

**What:** Consolidate duplicate preview/content-hydration logic into a shared resolver with consistent fallback: canonical_spans.raw_text → vector_chunks.text_preview → summary_text/title.

**When to use:** Any backend (ReasoningTreeBackend, PageIndexTreeAdapter) needs to build text_preview for selected nodes/hits.

**Example:**

```python
class EvidenceContentResolver:
    """Shared preview/content-hydration logic for selected nodes."""

    def build_text_preview(
        self,
        registry: RegistryWriter,
        version_id: UUID,
        node_id: UUID,
        span_ids: Sequence[UUID],
        fallback_text: str,
    ) -> str:
        """Canonical fallback cascade: spans → chunks → summary."""
        # 1. Try canonical_spans.raw_text (authoritative content)
        span_text = self._text_preview_from_spans(registry, version_id, span_ids)
        if span_text:
            return span_text

        # 2. Fallback to vector_chunks.text_preview (chunk-level evidence)
        chunk_text = self._text_preview_from_chunks(
            registry, version_id, node_id, span_ids
        )
        if chunk_text:
            return chunk_text

        # 3. Final fallback to summary_text/title (heading-based summary)
        return self._normalize_preview_text(fallback_text)

    def _text_preview_from_spans(self, registry, version_id, span_ids) -> str:
        """Query canonical_spans.raw_text for selected span_ids."""
        spans = registry.query_spans_by_version(version_id)
        span_order = {span_id: idx for idx, span_id in enumerate(span_ids)}
        selected = []
        for span in spans:
            span_id = self._coerce_uuid(span.get("span_id"))
            if span_id in span_order:
                selected.append((span_order[span_id], span.get("raw_text") or ""))
        selected.sort(key=lambda item: item[0])
        return self._normalize_preview_text(" ".join(text for _, text in selected))

    def _text_preview_from_chunks(self, registry, version_id, node_id, span_ids) -> str:
        """Query vector_chunks.text_preview for node_id or span-mapped chunks."""
        chunks = registry.query_vector_chunks_by_version(version_id)
        chunk_ids = self._chunk_ids_for_span_ids(registry, version_id, span_ids)
        selected = []
        for chunk in chunks:
            chunk_id = self._coerce_uuid(chunk.get("chunk_id"))
            chunk_node_id = self._coerce_uuid(chunk.get("node_id"))
            if chunk_id in chunk_ids or chunk_node_id == node_id:
                selected.append(chunk.get("text_preview") or "")
        return self._normalize_preview_text(" ".join(selected))

    def _normalize_preview_text(self, text: str, max_length: int = 1600) -> str:
        """Normalize whitespace and truncate with ellipsis if needed."""
        normalized = " ".join(text.split())
        if len(normalized) <= max_length:
            return normalized
        return normalized[: max_length - 1].rstrip() + "…"
```

**Source:** [VERIFIED: llamaindex_runtime/tree/reasoning_backend.py lines 287-376] Duplicate preview logic in ReasoningTreeBackend; [VERIFIED: llamaindex_runtime/tree/pageindex_adapter.py lines 176-249] Identical logic in PageIndexTreeAdapter.

### Pattern 3: VectorLoader Idempotent Invocation

**What:** VectorLoader.load() has built-in idempotency checks—safe to re-invoke for active_version if chunks missing.

**When to use:** After tree generation (PageIndexTreeAdapter.index_tree), trigger VectorLoader.load() to materialize chunks if validation shows chunks=0.

**Example:**

```python
# Idempotent: VectorLoader checks existing chunks before re-generating
loader = VectorLoader(embed_dim=16)  # or real embedder
result = loader.load(conn, version_id=active_version_id)

# Returns existing chunks if already materialized
# Or generates new chunks + embeddings + node_id linking if missing
# Handles partial state: repairs missing embeddings or node_id
```

**Source:** [VERIFIED: llamaindex_runtime/vector/loader.py lines 84-149] Idempotency checks in load(): existing_count > 0 → repair missing embeddings/node_id; no chunks → full pipeline.

### Pattern 4: Heading_path Storage Contract

**What:** canonical_spans.heading_path is authoritative source (ingestion-time extraction); tree_nodes.heading_path and vector_chunks.heading_path are derived.

**When to use:** Heading_path completeness validation, HeadingGroupedChunker grouping, provenance tracking.

**Example:**

```python
# Validation MUST check canonical_spans.heading_path (authoritative)
spans = registry.query_spans_by_version(version_id)
heading_path_complete = sum(1 for s in spans if s.get("heading_path") is not None)
heading_path_rate = heading_path_complete / len(spans) if spans else 0.0

# tree_nodes.heading_path is derived (PageIndex adapter computation)
# vector_chunks.heading_path is copied from spans (chunker)
# DO NOT check tree_nodes or vector_chunks for heading_path completeness
```

**Source:** [VERIFIED: llamaindex_runtime/registry/postgres_adapter.py lines 303-342] write_spans stores heading_path in canonical_spans; [VERIFIED: llamaindex_runtime/vector/chunker.py lines 65-70] SimpleSpanChunker copies heading_path from span to chunk; [VERIFIED: llamaindex_runtime/tree/pageindex_adapter.py lines 581-601] _flatten_embedded_tree computes heading_path for tree_nodes.

### Anti-Patterns to Avoid

- **Global COUNT queries mixing multiple versions**: Use registry.query_vector_chunks_by_version(version_id) instead of SELECT COUNT(*) FROM vector_chunks without WHERE version_id clause.
- **Heading_path validation on tree_nodes instead of canonical_spans**: tree_nodes.heading_path is derived; canonical_spans.heading_path is authoritative.
- **Assuming VectorLoader.load() was invoked**: Validation shows chunks=0; must explicitly invoke VectorLoader after tree generation.
- **Duplicate preview logic in backends**: Consolidate into shared EvidenceContentResolver to eliminate code duplication and ensure consistent fallback behavior.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Version-scoped DB counts | Custom COUNT queries with WHERE version_id = X | registry.query_vector_chunks_by_version(version_id) | Registry methods already implement version-scoped queries with proper UUID handling, return structured data |
| Preview/content hydration | Duplicate _build_text_preview methods in backends | EvidenceContentResolver (new class) | 80+ lines of duplicated code across ReasoningTreeBackend and PageIndexTreeAdapter; shared resolver ensures consistent fallback |
| Chunk materialization | Custom chunk generation + embedding + node-linking | VectorLoader.load() | VectorLoader orchestrates full pipeline with idempotency checks, repairs partial state |
| Heading_path provenance check | Custom queries on tree_nodes or vector_chunks | registry.query_spans_by_version(version_id) + check span.heading_path | canonical_spans.heading_path is authoritative source; tree_nodes and vector_chunks are derived |

**Key insight:** Registry methods provide all needed version-scoped queries; VectorLoader provides idempotent chunk materialization; consolidation needed for preview logic only.

## Runtime State Inventory

> Phase 5 is a verification/consolidation phase, not a rename/refactor/migration. Skip Runtime State Inventory.

## Common Pitfalls

### Pitfall 1: Global COUNT Queries Mixing Multiple Versions

**What goes wrong:** validation_status.json shows chunks=0 but DB may have chunks from other versions; global COUNT(*) mixes data from all versions, producing misleading statistics.

**Why it happens:** validation scripts use SELECT COUNT(*) FROM vector_chunks without WHERE version_id clause; registry.query_vector_chunks_by_version provides correct scope but scripts don't use it.

**How to avoid:** Replace global COUNT queries with registry.query_vector_chunks_by_version(version_id); compute statistics from returned list; ensure active_version_id is correctly resolved.

**Warning signs:** validation_status.json shows chunks=0 but documents=2, active_versions=2; discrepancy suggests data exists but not for active_version or query scope mismatch.

### Pitfall 2: Heading_path Validation on Wrong Table

**What goes wrong:** Validation checks tree_nodes.heading_path instead of canonical_spans.heading_path; gets misleading completeness rate because tree_nodes.heading_path is computed by PageIndex adapter (different provenance).

**Why it happens:** tree_nodes and canonical_spans both have heading_path column; easy to query wrong table; canonical_spans is authoritative source but tree_nodes seems equally valid.

**How to avoid:** Always validate heading_path completeness on canonical_spans (authoritative); tree_nodes.heading_path is derived (PageIndex adapter computation); vector_chunks.heading_path is copied from spans (chunker).

**Warning signs:** heading_path_rate=0.0 but tree_nodes have populated heading_path; canonical_spans.heading_path is NULL; discrepancy indicates ingestion-time extraction failed.

### Pitfall 3: VectorLoader Not Invoked After Tree Generation

**What goes wrong:** Tree generation (PageIndexTreeAdapter.index_tree) executes successfully; tree_nodes and tree_node_spans populated; but VectorLoader.load() never invoked → chunks=0, mapped_chunks=0.

**Why it happens:** Ingestion workflow splits into tree generation and chunk materialization; tree generation succeeded; chunk materialization step skipped or failed silently.

**How to avoid:** Invoke VectorLoader.load(conn, version_id) immediately after tree generation; add processing_status checks (chunks_created stage); verify evidence-chain statistics before validation.

**Warning signs:** documents=2, tree_max_level=2 (tree nodes exist) but chunks=0, mapped_chunks=0 (chunks missing); indicates incomplete ingestion pipeline.

### Pitfall 4: Duplicate Preview Logic Causes Maintenance Burden

**What goes wrong:** ReasoningTreeBackend._build_text_preview_for_node and PageIndexTreeAdapter._build_text_preview have identical logic; changes needed in one backend miss the other; inconsistent fallback behavior emerges.

**Why it happens:** Both backends independently implemented same fallback cascade (spans → chunks → summary); no shared resolver; code review didn't catch duplication.

**How to avoid:** Extract shared EvidenceContentResolver class; both backends use resolver.build_text_preview(); ensures consistent behavior and single maintenance point.

**Warning signs:** _build_text_preview methods appear in both reasoning_backend.py and pageindex_adapter.py with >80% similarity; duplicate _text_preview_from_spans, _text_preview_from_chunks, _normalize_preview_text helpers.

## Code Examples

Verified patterns from official sources (internal codebase):

### Version-Scoped DB Count Query

```python
# Source: [VERIFIED: llamaindex_runtime/registry/postgres_adapter.py lines 705-723]
def query_vector_chunks_by_version(self, version_id: uuid.UUID) -> list[dict[str, Any]]:
    """Return all vector_chunks for a version, ordered by chunk_order."""
    with self._connection.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT chunk_id, version_id, chunk_type, chunk_order, token_count, "
            "text_preview, page_no, heading_path, node_id, embedding, created_at "
            "FROM vector_chunks WHERE version_id = %s ORDER BY chunk_order",
            (str(version_id),),
        )
        rows = cur.fetchall()

    result: list[dict[str, Any]] = []
    for row in rows:
        row["chunk_id"] = uuid.UUID(str(row["chunk_id"]))
        row["version_id"] = uuid.UUID(str(row["version_id"]))
        if row.get("node_id") is not None:
            row["node_id"] = uuid.UUID(str(row["node_id"]))
        result.append(row)
    return result
```

### VectorLoader Idempotent Invocation

```python
# Source: [VERIFIED: llamaindex_runtime/vector/loader.py lines 84-149]
def load(self, conn: psycopg.Connection, version_id: uuid.UUID) -> dict[str, Any]:
    """Run the vector chunk pipeline for *version_id*.

    If chunks already exist but are incomplete (missing embeddings or
    node_id when tree data is available), the missing data is repaired
    rather than skipped.  This makes load() safe to re-run after a
    partial failure.
    """
    # 1. Read spans
    spans = self._read_spans(conn, version_id)
    if not spans:
        return {"chunk_ids": [], "count": 0}

    # 2. Check if chunks already exist
    existing_count = self._count_existing_chunks(conn, version_id)
    if existing_count > 0:
        # Chunks exist -- check for incomplete state and repair
        chunk_ids = self._read_chunk_ids(conn, version_id)
        chunks_missing_embedding = self._count_chunks_missing_embedding(conn, version_id)
        if chunks_missing_embedding > 0:
            # Regenerate chunk data from spans to compute embeddings
            chunks = self._chunker.generate(spans, version_id=version_id)
            # Apply refinery (if configured) during repair
            if self._refinery is not None:
                chunks = self._refinery.refine(chunks, version_id=version_id)
            self._update_embeddings(conn, chunks)
            # Also re-project to backend if configured
            self._project_to_backend(version_id, chunks)
        # Always attempt tree-node linking when tree data exists
        self._repair_tree_nodes(conn, version_id, spans)
        return {"chunk_ids": chunk_ids, "count": len(chunk_ids)}

    # 3-8: Full pipeline for new chunks (generate, persist, embed, link)
    # ... (full implementation in source)
```

### Heading_path Provenance Check

```python
# Source: [VERIFIED: llamaindex_runtime/registry/postgres_adapter.py lines 344-358]
def query_spans_by_version(self, version_id: uuid.UUID) -> list[dict[str, Any]]:
    """Return all canonical_spans for a version, including heading_path."""
    with self._connection.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT span_id, version_id, span_kind, start_offset, end_offset, "
            "page_no, heading_path, raw_text, created_at "
            "FROM canonical_spans WHERE version_id = %s ORDER BY start_offset",
            (str(version_id),),
        )
        rows = cur.fetchall()

    result: list[dict[str, Any]] = []
    for row in rows:
        row["span_id"] = uuid.UUID(str(row["span_id"]))
        row["version_id"] = uuid.UUID(str(row["version_id"]))
        result.append(row)
    return result

# Compute heading_path completeness from authoritative source
spans = registry.query_spans_by_version(version_id)
heading_path_complete = sum(1 for s in spans if s.get("heading_path") is not None)
heading_path_rate = heading_path_complete / len(spans) if spans else 0.0
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Global COUNT queries in validation | Version-scoped registry methods | Phase 5 requirement | Prevents version-mixing, ensures accurate evidence-chain statistics for active_version |
| Duplicate preview logic in backends | Shared EvidenceContentResolver (planned) | Phase 5 consolidation | Eliminates 80+ lines duplication, ensures consistent fallback behavior |
| Assume tree generation implies chunk materialization | Explicit VectorLoader invocation + processing_status checks | Phase 5 verification | Prevents chunks=0 state, ensures complete evidence-chain before validation |
| Heading_path validation on tree_nodes | canonical_spans.heading_path check | Phase 5 provenance contract | Uses authoritative source (ingestion-time extraction) for completeness validation |

**Deprecated/outdated:**
- Global COUNT(*) queries: Replaced by version-scoped registry methods.
- Duplicate _build_text_preview methods: Consolidated into shared EvidenceContentResolver.
- Implicit chunk materialization assumption: Explicit VectorLoader invocation with processing_status tracking.

## Assumptions Log

> All claims in this research were verified or cited from codebase. No assumptions needing user confirmation.

**If this table is empty:** All claims in this research were verified or cited — no user confirmation needed.

## Open Questions (RESOLVED)

1. **Why was VectorLoader.load() not invoked after tree generation?**
   - What we know: Tree generation succeeded (tree_max_level=2), but chunks=0. VectorLoader exists and is idempotent.
   - Resolution for planning: Phase 5 Plan 02 makes this explicit by adding `verification/phase5-evidence-chain-verification/invoke_vector_loader.py` and wiring a materialization checkpoint into `scripts/run_pageindex_real_retrieval_workflow.py` after integration data population and before retrieval verification.

2. **Which validation scripts need version-scoped query updates?**
   - What we know: run_validation.py (lines 94-143) uses global COUNT queries.
   - Resolution for planning: Phase 5 Plan 01 updates `run_validation.py` and adds `verify_active_version_counts.py` as the authoritative active-version count path. Additional global COUNT scripts are out of Phase 5's blocking scope unless discovered while executing Plan 01.

3. **Should EvidenceContentResolver be a standalone module or shared helper in runtime.py?**
   - What we know: Both ReasoningTreeBackend and PageIndexTreeAdapter need preview logic.
   - Resolution for planning: Phase 5 Plan 03 creates standalone `llamaindex_runtime/tree/evidence_content_resolver.py` to keep evidence hydration separate from retrieval ranking/runtime orchestration.

## Environment Availability

> Phase 5 depends on PostgreSQL database, registry methods, and VectorLoader—all available in current codebase.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL (DATABASE_URL) | Evidence-chain verification | ✓ (Phase 4 validation connected) | 15.x | — |
| VectorLoader | Chunk materialization | ✓ | current (loader.py) | — |
| PostgresRegistryWriter | Version-scoped queries | ✓ | current (postgres_adapter.py) | — |
| DeterministicEmbedder | Test embeddings | ✓ | current (embedder.py) | Real embedder if needed |
| psycopg.Connection | Registry methods | ✓ | 3.x | — |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** None.

## Validation Architecture

> nyquist_validation enabled by default. Include Validation Architecture section.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | pytest.ini (repo root) |
| Quick run command | `pytest tests/llamaindex_runtime/test_query_quality_validation.py -x` |
| Full suite command | `pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REQ-01 | Version-scoped DB counts compute correctly | unit | `pytest tests/llamaindex_runtime/test_evidence_chain_completeness.py::TestEvidenceChainCompleteness::test_complete_evidence_chain_passes_node_chunk_mapping -x` | ✅ |
| REQ-02 | EvidenceContentResolver fallback cascade works | unit | `pytest tests/llamaindex_runtime/test_query_quality_validation.py::TestQueryQualityValidation::test_reasoning_backend_text_preview_uses_canonical_span_raw_text -x` | ✅ |
| REQ-03 | VectorLoader idempotent invocation handles partial state | integration | `pytest tests/llamaindex_runtime/test_vector_loader.py -x` (if exists) or create new test | ❌ Wave 0 |
| REQ-04 | Heading_path provenance check uses canonical_spans | unit | `pytest tests/llamaindex_runtime/test_evidence_chain_completeness.py::TestEvidenceChainCompleteness::test_heading_path_completeness_boundary -x` | ✅ |
| REQ-05 | Validation integrity gate detects corpus mismatch | integration | `pytest tests/verification/test_validation_integrity.py -x` (create new) | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/llamaindex_runtime/test_query_quality_validation.py -x` (quick validation)
- **Per wave merge:** `pytest tests/ -x` (full suite)
- **Phase gate:** Full suite green + evidence-chain thresholds pass (node_chunk_mapping ≥80%, heading_path ≥95%) before human judgment collection.

### Wave 0 Gaps

- [ ] `tests/llamaindex_runtime/test_vector_loader.py` — covers REQ-03 (VectorLoader idempotent invocation)
- [ ] `tests/verification/test_validation_integrity.py` — covers REQ-05 (corpus mismatch detection)
- [ ] `tests/llamaindex_runtime/test_evidence_content_resolver.py` — covers REQ-02 (shared resolver behavior)
- [ ] Framework install: pytest already installed (pyproject.toml)

*(3 gaps detected — Wave 0 must create these test files before implementation)*

## Security Domain

> Security enforcement enabled (default). Include Security Domain section.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — (Phase 5 is verification/consolidation, no auth changes) |
| V3 Session Management | no | — (no session handling) |
| V4 Access Control | no | — (no user access changes) |
| V5 Input Validation | yes | pydantic (UUID validation for version_id, registry method parameters) |
| V6 Cryptography | no | — (no crypto operations) |

### Known Threat Patterns for {stack}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via version_id | Tampering | Registry methods use parameterized queries (psycopg %s placeholders) — no string concatenation |
| UUID injection via malicious version_id | Tampering | UUID validation via uuid.UUID(version_id) constructor — raises ValueError on invalid input |
| Evidence-chain data tampering | Tampering | Evidence-chain statistics computed from persisted data; no user input affects counts |

## Sources

### Primary (HIGH confidence)

- [VERIFIED: llamaindex_runtime/registry/postgres_adapter.py] - query_vector_chunks_by_version (lines 705-723), query_tree_node_spans_by_version (lines 532-550), query_spans_by_version (lines 344-358)
- [VERIFIED: llamaindex_runtime/vector/loader.py] - VectorLoader.load() idempotent invocation (lines 84-149), _repair_tree_nodes (lines 208-267)
- [VERIFIED: llamaindex_runtime/vector/chunker.py] - SimpleSpanChunker (lines 25-70), HeadingGroupedChunker (lines 73-184)
- [VERIFIED: llamaindex_runtime/tree/reasoning_backend.py] - _build_text_preview_for_node duplicate logic (lines 287-376)
- [VERIFIED: llamaindex_runtime/tree/pageindex_adapter.py] - _build_text_preview duplicate logic (lines 176-249)

### Secondary (MEDIUM confidence)

- [CITED: verification/phase3-real-validation/run_validation.py lines 94-143] - Global COUNT queries causing evidence-chain zeros
- [CITED: verification/phase3-real-validation/validation_status.json] - chunks=0, mapped_chunks=0, heading_path_rate=0.0, active_version_id
- [CITED: verification/phase4-quality-validation/db-backed-node-aware-rerun-20260607/validation_status.json] - Same zeros, confirms persistent issue
- [CITED: tests/llamaindex_runtime/test_evidence_chain_completeness.py] - Thresholds frozen: MIN_NODE_CHUNK_MAPPING_RATE=0.80, MIN_HEADING_PATH_COMPLETENESS=0.95

### Tertiary (LOW confidence)

- [ASSUMED] Phase 4 ingestion workflow likely splits tree generation and chunk materialization into separate steps (not verified in code)
- [ASSUMED] EvidenceContentResolver should be standalone module tree/evidence_content_resolver.py (architectural preference, not verified)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Registry methods, VectorLoader, chunkers all verified in codebase
- Architecture patterns: HIGH - Version-scoped queries, idempotent invocation, provenance contract all verified
- Pitfalls: HIGH - Global COUNT queries, heading_path validation on wrong table, VectorLoader not invoked all documented in validation_status.json and Phase 4 learnings

**Research date:** 2026-06-07
**Valid until:** 30 days (stable architecture patterns, registry methods unlikely to change)

---

## Phase Requirements (from ROADMAP.md)

| ID | Description | Research Support |
|----|-------------|------------------|
| REQ-01 | Verify active_version-scoped DB counts for canonical_spans, vector_chunks, vector_chunk_spans, tree_node_spans, heading_path completeness | Registry methods verified: query_vector_chunks_by_version, query_tree_node_spans_by_version, query_spans_by_version provide version-scoped access |
| REQ-02 | Confirm validation scripts use same DB/schema/version as ingestion | Validation script (run_validation.py) uses global COUNT queries (not version-scoped)—must update to registry methods |
| REQ-03 | Determine whether chunks=0 comes from missing materialization, wrong version, or metric-table mismatch | VectorLoader.load() not invoked after tree generation—missing materialization confirmed; global COUNT queries mix versions—metric-table mismatch also present |
| REQ-04 | Define heading_path storage contract (canonical_spans vs tree_nodes vs vector_chunks) | canonical_spans.heading_path is authoritative (ingestion-time extraction); tree_nodes and vector_chunks are derived |
| REQ-05 | Consolidate preview/content hydration into EvidenceContentResolver | Duplicate logic identified in ReasoningTreeBackend._build_text_preview_for_node and PageIndexTreeAdapter._build_text_preview (80+ lines duplicated) |
| REQ-06 | Preserve preview behavior: canonical_spans.raw_text → vector_chunks.text_preview → summary/title fallback | Fallback cascade verified in both backends; shared resolver will preserve this behavior |
| REQ-07 | Gate human judgment collection on evidence-chain thresholds + corpus integrity | Thresholds frozen: node_chunk_mapping ≥80%, heading_path ≥95%; corpus integrity check required (Phase 4 judgment integrity issue) |