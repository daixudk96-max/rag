# Phase 14: OKF Foundation - Context

**Gathered:** 2026-07-12
**Status:** BOUNDED CLOSED/PASS (current-status overlay, 2026-07-17). [Artifact 13](../../../verification/phase14-okf-foundation/13-final-authority-evidence-closure-review.md) records **APPROVE_FOR_FORMAL_CLOSURE** with no CRITICAL/HIGH findings. Phase 14/E1 is formally CLOSED for its bounded A–F acceptance scope. Gates A–E have PASS execution evidence and APPROVE independent reviews. Gate F is PASS only within the declared Phase 14 non-goal scope, with an APPROVE independent review. This closure is not a clean-worktree, full-worktree, intended-commit-scope, security, production-readiness, or full-derived-database-rebuild PASS. E1 remains limited to admitted raw-sidecar-to-`canonical_spans` reconciliation for registered/protected parents. **Historical/as-of-closeout:** Phase 15/E2a was unstarted and Gate 3 authorization was unsatisfied. **Current routing (later):** the interactive selection `授权规划和实施（推荐）` satisfies Gate 3; Phase 15 is authorized/planned/execution-unstarted pending approved plan execution. This routing grants no later-phase, Git, production, or disposable-acceptance authority. See the [evidence index](../../../verification/phase14-okf-foundation/README.md).
**Source:** `OKF-MULTIROUTE-EXECUTION-HANDOFF-2026-07-12.md` §5.1/§10 + `ADR-OKF-PHASE-A-TECH-DECISIONS-2026-07-12.md` (T1-T9 ratified) + this-session code verification

<domain>
## Phase Boundary

**What this phase delivers:** The provable OKF SSOT foundation for a single document: (1) format contracts — spans sidecar JSON schema v1, raw-file frontmatter contract, canonical structural hash; (2) docling→OKF serializer emitting `raw/*.md` + `*.spans.json`; (3) parser completion — sidecar reading, fail-fast frontmatter validation, canonical-hash incremental sync + delete detection, no silent relation-qualifier drop; (4) migrations 015-017; (5) `rebuild_from_okf.py`; (6) the span_id round-trip regression gate (`S_direct == S_okf` 100%), which is the hard A→B blocker.

**In scope:**
- New modules under `llamaindex_runtime/okf/` (contracts/sidecar/canonical hash/serializer) + extension of `okf/parser.py`.
- `OKF_BUNDLE_ROOT` configuration in `llamaindex_runtime/config.py` (implemented in 14-01).
- Registered migrations `015_okf_sync_state.sql`, `016_entity_mentions.sql`, `017_relation_qualifiers.sql`, and `018_okf_rebuild_failure_audit.sql`; hardcoded migration-list adjudication is outside this documentation update.
- `scripts/rebuild_from_okf.py` + pytest regression + deterministic CLI check.
- Bundle templates + bundle-level `AGENT.md` declaring `raw/` machine-generated (no hand edits).

**Out of scope (do NOT touch):**
- Any existing ingestion CALLER — no caller is switched to the OKF path (that is Phase 15). `docling_ingestor.py` is read-only EXCEPT for `_build_default_reader`, which is the narrow authorized exception per the user-approved Phase 14 scope expansion (docling 2.109 + HeadingHierarchyModel). No other function, the public interface, normalization, span formula, or caller is modified.
- NER/entity extraction (Phase 16) — tables are created empty in 016, nothing populates them.
- PageIndex config, fusion weights, retrieval behavior (Phases 17/19).
- Agent writeback (Phase 18). Level assessment claims (Phase 19, D4 frozen).
- The dirty working tree: pre-existing modified files (config.py, semantic_distribution.py, tests/, verification/…) are NOT part of this phase and must never be swept into its commits.

</domain>

<decisions>
## Implementation Decisions (all LOCKED via ADR — deviation requires user re-approval)

- **T1/T2 [LOCKED] Sidecar span identity.** Each `raw/<name>.md` has adjacent `<name>.spans.json` carrying per-span `page_no`, `heading_path`, `offset`, exact normalized `text` (the six span_id elements minus doc_id/version_id which live in file frontmatter), plus recorded `span_id` for cross-check and a top-level `schema_version`. Span identity is rebuilt ONLY from the sidecar — never re-derived from Markdown body. `raw/*.md` stays human-readable, machine-generated.
- **T3 [LOCKED] Dual hash.** `source_checksum` = SHA256 of raw file bytes (audit); `canonical_hash` = SHA256 over canonically-serialized frontmatter + deterministic JSON serialization of sidecar spans (sync comparison). Format-only rewrites must not change `canonical_hash`.
- **T4 [LOCKED] entity_mentions table.** New table (mention_id PK, entity_id FK, span_id, char_start, char_end, mention_text, confidence, source, OKF provenance). `evidence_links` unchanged.
- **T5 [LOCKED] Migrations 015+.** Three-digit zero-padded; `001_okf_authoritative.sql` naming BANNED (initdb lexicographic collision). Docker initdb picks up new files automatically; the two hardcoded lists (`scripts/run_pageindex_real_retrieval_workflow.py::MIGRATION_FILES` at lines 21-26, root `run_migrations.py::key_migrations`) must be explicitly reviewed — added only where the runner needs OKF tables, with the decision recorded either way.
- **T6 [LOCKED] Relation qualifiers.** Explicit columns `negation boolean NOT NULL DEFAULT false`, `condition text`, `direction text`, `confidence numeric` + `qualifiers JSONB` spillover on the relation table defined in `005_kg_extension.sql` (executor verifies exact table name by reading 005 first). Parser must not silently drop frontmatter qualifier fields. No relation_mentions table in this phase.
- **T9 [LOCKED] Round-trip gate form.** Automated pytest regression + deterministic CLI command; ≥3 fixture classes (sectioned PDF, table/complex-layout PDF, DOCX); failure report names the FIRST mismatching coordinate (span-level page_no/heading_path/offset/text diff). Hard A→B gate.
- **Serializer normalization reuse [LOCKED by risk register].** The serializer imports and calls `NormalizationContract` from the existing ingestion path — never copies its logic. Any divergence in normalization = permanent round-trip failure.
- **Claude's discretion at execution time:** exact sidecar field ordering, module file names within `llamaindex_runtime/okf/`, fixture document choice (must satisfy the three classes), pytest organization, CLI arg surface of `rebuild_from_okf.py`.

</decisions>

<verified_code_facts>
## Historical Preimplementation Code Snapshot (verified 2026-07-12 — superseded where noted below)

**Do not treat this table as current implementation state.** It records the pre-14-01 baseline used to make the Phase 14 decisions; assertions such as "only," "no," and "next free" are historical as of 2026-07-12.

| Historical fact (2026-07-12) | Location at verification |
|---|---|
| span_id formula: `uuid5(NAMESPACE_URL, f"{doc_id}\|{version_id}\|{page_no}\|{'/'.join(headings)}\|{offset}\|{text}")` | `llamaindex_runtime/ingestion/docling_ingestor.py:78-81` |
| Six elements came from `NormalizationContract.normalize(raw_text, metadata, ordinal)` | same module, lines 40-77 |
| docling nested metadata flattening (`doc_items[0]['prov'][0]` → page_no/charspan) | `docling_ingestor.py::_flatten_docling_metadata` |
| `OKFParagraph` had only `id/content/heading/okf_file_path` — no span coordinates | `llamaindex_runtime/okf/parser.py:57-63` |
| Paragraph splitting was naive `body.split("\n\n")` and layout-fragile | `parser.py:272` |
| `compute_hash` was SHA256 of raw file bytes and whitespace/key-order sensitive | `parser.py:294-304` |
| `OKFFrontmatter` supported aliases/canonical_entity_id/entity_type/relations/mentions | `parser.py` |
| Migrations 001-014 existed continuously; 015 was the next free number | `llamaindex_runtime/registry/migrations/` |
| initdb mounted the whole migrations directory for lexicographic execution | `verification/docker-compose.yml:12` |
| Hardcoded list 1 was `MIGRATION_FILES = ("001…","002…","003…","007…")` | `scripts/run_pageindex_real_retrieval_workflow.py:21-26,183-203` |
| Hardcoded list 2 was `key_migrations` | root `run_migrations.py` |
| `evidence_links` had span_id + confidence, with no char offsets or mention text | `migrations/005_kg_extension.sql` |
| No OKF config key existed in `llamaindex_runtime/config.py` | grep verified 2026-07-12 |
| No OKF tests existed under `tests/` | glob verified 2026-07-12 |
| `llamaindex_runtime/okf/` contained only `parser.py` + `__init__.py` | glob verified 2026-07-12 |

### Current functional-delivery and authority status (2026-07-17; all four plan execution records)

- Phase 14/E1 functional delivery and canonical-path ratification are recorded. Gates C/E have fresh PASS execution artifacts 09/11 and APPROVE reviews; Gate F artifact 12 is **PASS within declared Phase 14 non-goal scope**, and review 12 is **APPROVE** with no CRITICAL/HIGH findings. [Artifact 13](../../../verification/phase14-okf-foundation/13-final-authority-evidence-closure-review.md) records **APPROVE_FOR_FORMAL_CLOSURE**; Phase 14/E1 is bounded CLOSED/PASS, without expanding E1 scope or authorizing Phase 15.
- Artifacts 04–07 retain their PASS/WARN distinctions: 04 is index freshness PASS; 05–07 retain tracked-diff-only, HIGH/CRITICAL impact-warning, and non-exhaustive untracked-coverage limitations. Gate F is not a clean-worktree, full-worktree, commit-scope, security, or production PASS.
- The current Phase 14 closeout/verification artifacts contain no credential values; protected variables were isolated as recorded. This statement does not cover all historical planning artifacts.
- **Historical/as-of-closeout:** Phase 15/E2a was unstarted and Gate 3 authorization was unsatisfied. **Current routing (later):** the interactive selection `授权规划和实施（推荐）` satisfies Gate 3; Phase 15 is authorized/planned/execution-unstarted pending approved plan execution. This routing grants no later-phase, Git, production, or disposable-acceptance authority.

- `OKF_BUNDLE_ROOT` now exists in `llamaindex_runtime/config.py`.
- Registered migration files now include `015_okf_sync_state.sql`, `016_entity_mentions.sql`, `017_relation_qualifiers.sql`, and `018_okf_rebuild_failure_audit.sql`.
- `llamaindex_runtime/okf/` now includes the implemented contracts, sidecar, canonical-hash, serializer, raw-pair, and round-trip modules; focused OKF tests now exist under `tests/llamaindex_runtime/okf/`.
- The current raw input is the admitted Markdown-plus-adjacent-sidecar pair, not body-derived span identity. The parser's current DTO surface includes sidecar `SpanRecord` values and the canonical hash on `OKFDocument`, alongside typed raw provenance fields on `OKFFrontmatter`.
- The historical hardcoded runner-list observations above are preserved only as a preimplementation snapshot. This document makes no claim about migration-list resolution; that adjudication remains outside this documentation update.

</verified_code_facts>

<upstream_sources>
## Upstream Sources（2026-07-12 补充 — 源码级分析结论，全文见 `.planning/research/UPSTREAM-SOURCE-ANALYSIS-2026-07-12.md`）

克隆位置：`E:\github\rag-upstream\`（仓库外）。本阶段执行者必读研究文档 §1/§2/§3/§4。

| 来源 | License | 本阶段用法 |
|---|---|---|
| ogham-mcp（Python 3.13, MIT） | MIT | **移植改造**：`src/ogham/okf/{serialization,concept,bundle}.py` 的定序 frontmatter 写入、尾换行归一、未知字段零丢失（`_RECOGNISED_FIELDS`+metadata）、原子导出；其 `tests/test_okf_*.py` 20+ 用例翻译进 14-04 回归 |
| knowledge-catalog（Apache-2.0） | Apache-2.0 | **规范权威** `okf/SPEC.md`；示例 bundle（crypto_bitcoin/ga4/stackoverflow）作 parser 符合性 fixture |
| okf-lint（MIT） | MIT | **原样采用**为 CI 符合性门禁（`--max-warnings 0` + `.okflintrc.json`），不 fork |
| okf-wiki（MIT） | MIT | **约定复制**：AGENT.md 三段边界模板（Always/Ask first/Never）、index.md/log.md 格式（注意用 `okf_version` 而非其 `okf_wiki_version`） |
| llm-wiki-compiler（MIT） | MIT | canonical hash 思想佐证（其 frontmatter 刻意不定序 = 反例，我们必须钉死定序）；主要消费在 Phase 18 |
| open-knowledge（**GPL-3.0**） | GPL-3.0 | **用户裁决解禁（2026-07-12，项目自用不分发）**：可移植/复制，但每个衍生文件必须打 GPL 来源头标（绊线：将来分发前须整仓转 GPL 或剥离——研究文档 §7） |

**规范新增义务（此前遗漏，已并入 14-01/14-03 计划）：** `index.md`/`log.md` 是保留文件名——parser 必须在所有层级跳过、不作 concept 摄入；bundle 根 `index.md` 是唯一可带 frontmatter 的 index，且只含 `okf_version: "0.1"`。span_id/sidecar/canonical hash 无上游可搬（全生态无内容寻址身份），保持自研。

</upstream_sources>

<requirements>
## Phase Requirements (P14-xx)

- P14-01 sidecar schema v1 defined + schema-validated (fail-fast on unknown schema_version)
- P14-02 raw frontmatter contract defined + validated (doc_id/version_id/source_checksum/docling version/type: raw)
- P14-03 canonical structural hash deterministic; format-only rewrite leaves it unchanged
- P14-04 migrations 015-017 apply cleanly on fresh initdb AND on an existing 001-014 database
- P14-05 serializer produces raw/*.md + sidecar from docling output, reusing NormalizationContract
- P14-06 parser reads sidecar; frontmatter validation fail-fast
- P14-07 parser incremental sync via canonical hash (no rebuild on format-only rewrite)
- P14-08 parser delete detection (file removed from bundle → derived rows marked/removed)
- P14-09 rebuild-from-okf produces S_okf from bundle alone
- P14-10 span_id round-trip S_direct == S_okf 100% across 3 fixture classes
- P14-11 first-mismatch coordinate reporting on round-trip failure
- P14-12 relation qualifiers never silently dropped by parser

</requirements>

<canonical_refs>
## Canonical References

**Downstream executors MUST read these before implementing.**

### Authority chain (order = precedence)
- `.planning/OKF-MULTIROUTE-EXECUTION-HANDOFF-2026-07-12.md` — §5.1 Phase A scope, §10 hard acceptance checklist A-F
- `.planning/UNIFIED-MULTIROUTE-OKF-PLAN.md` — D1-D8 architecture rulings
- `.planning/ADR-OKF-PHASE-A-TECH-DECISIONS-2026-07-12.md` — T1-T9 ratified decisions + code-fact table
- `.planning/v2.0-MILESTONE-OKF-MULTIROUTE.md` — milestone map, six flows (F1-F6), cross-phase boundary rulings
- `.planning/research/UPSTREAM-SOURCE-ANALYSIS-2026-07-12.md` — upstream adopt/adapt rulings（本阶段的移植来源与规范符合性依据）

### Primary code targets
- `llamaindex_runtime/okf/parser.py` — current parser for admitted raw/sidecar pairs, including `OKFDocument.spans`, canonical-hash sync state, and fail-fast raw-frontmatter validation.
- `llamaindex_runtime/ingestion/docling_ingestor.py` — span_id/normalization reference; import NormalizationContract from here (or its actual home module — verify import path at execution). `_build_default_reader` is the narrow authorized exception (Phase 14 scope expansion: docling 2.109 + HeadingHierarchyModel).
- `llamaindex_runtime/registry/migrations/` — registered 015-018 OKF migrations; hardcoded runner-list adjudication is intentionally not stated here.
- `llamaindex_runtime/config.py` — current `OKF_BUNDLE_ROOT` setting (note: file has unrelated dirty-tree modifications; edit surgically, never revert others' hunks).

### Repo rules (MANDATORY)
- `CLAUDE.md` GitNexus rules: `gitnexus_impact` before editing ANY existing symbol; `gitnexus_detect_changes()` before commit; warn on HIGH/CRITICAL
- TDD: tests first (RED) → implement (GREEN); ≥80% coverage on new modules
- No commit/push without explicit user request; dirty-tree files stay out of staged scope; DATABASE_URL never enters planning artifacts

</canonical_refs>
