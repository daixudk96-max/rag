# Phase 10 Real DOCX Retrieval Validation Summary

**Status:** PASS
**Generated:** 2026-06-16T17:39:37Z

## Source Document

- Path: `ANONYMIZED_LOCAL_DOCX` (local user path redacted)
- Theme: 进阶版 RAG / 混合检索 / 结构化数据检索

## Environment

- document_exists: `True`
- database_url_configured: `True` (raw value not printed)
- db_reachable: `True`

## Ingestion

- doc_id: `6d742c06-3c5a-4996-ac36-614510bd729f`
- version_id: `a287ec5a-604b-416e-8ec5-a541d3d23cbe`
- canonical_spans: `34`
- spans_with_heading_path: `34`
- heading_path_rate: `1.0`
- dropped_nodes: `0`
- hierarchy_precondition_status: `PASS`

## Tree / Vector Status

- tree_nodes: `47`
- non_root_nodes: `46`
- tree_node_spans: `34`
- vector_chunks: `34`
- vector_chunk_spans: `34`
- vector_chunks_with_node_id: `34`
- vector_chunks_with_embedding: `34`

## Retrieval Evidence Chain

- query_count: `12`
- query_failures: `0`
- total_hits: `60`
- zero_chunk_hits: `0`
- parent_only_hits: `0`
- hotspot_metadata_hits: `60`
- navigation_path_hits: `60`
- subtree_hotspot_traversal_hits: `60`

## Functional Decision

- functional_status: `PASS`
- rationale: All queries returned evidence-bearing hits with hotspot/navigation metadata preserved.

## Quality / Level Decision

- Quality metrics are not calculated because hotspot-specific human judgments are pending and this run produced no retrievable hits.
- `Level_2` remains authoritative.

## Generated Artifacts

- `01_environment_check.json`
- `02_document_ingestion_status.json`
- `03_tree_vector_status.json`
- `04_query_set.json`
- `05_hotspot_retrieval_results.json`
- `06_evidence_chain_report.json`
- `07_judgment_template.csv`
- `07_judgment_template_metadata.json`
- `08_quality_metrics.json`
- `09_level_assessment.json`
- `10_validation_summary.md`
- `11_failure_diagnosis.json` (if diagnosis is run)
