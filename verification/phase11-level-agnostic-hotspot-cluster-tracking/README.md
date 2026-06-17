# Phase 11 Level-Agnostic Hotspot Cluster Tracking Validation

## Validation Runner

### Command

```bash
rtk test python verification/phase11-level-agnostic-hotspot-cluster-tracking/run_validation.py
```

### Required Environment Variables

- `DATABASE_URL` — PostgreSQL connection string (not printed in artifacts)
- `RAG_TREE_HOTSPOT_SELECTOR=cluster` — Set automatically by the runner; forces cluster-based hotspot selection

### Corpus

- Source: `verification/p6_validation/p6_final_sample_structured.md`
- Theme: AI产品经理项目实战与深度思考架构分析
- Structure: Transcript with time-coded sections and nested headings

### Query Set

The validation includes exactly 10 queries from 11-04-PLAN.md:

1. AI产品经理的核心DNA是什么？
2. 传统软件和AI产品的输出特点有什么区别？
3. AI产品的智能来源是什么？
4. 什么是数据闭环飞轮？为什么它重要？
5. 抖音如何利用用户行为数据优化推荐？
6. 特斯拉如何收集自动驾驶数据？
7. AI产品落地时第一个要思考的问题是什么？
8. 如何处理不干净的数据？
9. 李菲菲在AI 1.0时代遇到了什么数据问题？
10. 独家数据为什么是真正的护城河？

### Pass Criteria

#### Functional

- `query_failures = 0`
- `total_hits > 0`
- `hotspot_metadata_rate >= 0.90`
- `navigation_path_rate >= 0.90`
- `empty_preview_hits = 0`

#### Semantic (DNA Query)

For query "AI产品经理的核心DNA是什么？":

- Evidence must contain: `数据驱动`, `非确定性`, `持续性`
- Primary hotspot must be: `00:31 - 产品特性对比` or `AI产品经理核心DNA` itself
- Primary hotspot must **NOT** be: `05:40 - 抖音案例`, `04:40 - 数据工作重要性`, `06:29 - 特斯拉案例`

### Output Artifacts

- `validation_status.json` — Functional pass status and DNA query validation
- `evidence_chain_report.json` — Metadata/provenance rates (hotspot_metadata_rate, navigation_path_rate, drill_depth_rate)
- `05_hotspot_retrieval_results.json` — Per-query hits with hotspot/navigation metadata
- `01_environment_check.json` — DB reachability and selector configuration
- `02_document_ingestion_status.json` — Corpus ingestion and hierarchy status
- `03_tree_vector_status.json` — Tree/vector materialization
- `04_query_set.json` — Query definitions
- `07_judgment_template.csv` — Optional judgment collection (not required for functional validation)
- `08_quality_metrics.json` — Placeholder (metrics require human judgments)
- `09_level_assessment.json` — Level 2 preserved unless judgments collected

### Security

- No raw `DATABASE_URL` is written to JSON artifacts
- Runner uses p6 corpus from local verification directory
- No network access required beyond local PostgreSQL

### Fail-Closed Behavior

If validation fails:

- Runner exits with nonzero status (1 or 2)
- `validation_status.json` contains `passed: false`
- `evidence_chain_report.json` contains explicit blocker reason
- No Level promotion is claimed

### GitNexus Gate

Before committing Phase 11 changes:

```bash
rtk proxy npx gitnexus detect-changes --repo rag
```

Report CRITICAL/HIGH risk to user before staging.

### Selector Switch

Runner enforces `RAG_TREE_HOTSPOT_SELECTOR=cluster` at import time.

Fallback behavior (if cluster selector regresses):

```bash
RAG_TREE_HOTSPOT_SELECTOR=route_subtree rtk test python verification/phase11-level-agnostic-hotspot-cluster-tracking/run_validation.py
```

Restores Phase 10 behavior.

### Last Updated

2026-06-17 — Phase 11 Plan 04