---
phase: 10
slug: hotspot-semantic-retrieval-validation
status: verified
threats_open: 0
asvs_level: 1
created: 2026-06-12
updated: 2026-06-12
---

# Phase 10 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail for hotspot semantic retrieval validation.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Demo script → PostgreSQL | `scripts/demo_hotspot_semantic_retrieval.py` reads `DATABASE_URL` and connects to PostgreSQL. | Database connection string from environment; must not be printed or written. |
| QueryHit → backend hit dict | Hotspot/navigation metadata crosses retrieval DTO → runtime mapping boundary. | Node IDs, chunk IDs, span IDs, heading paths, scores, navigation metadata. |
| Hotspot hits → Phase 8 judgments | Phase 10 hotspot output is compared with Phase 8 judged rows for reuse feasibility. | Retrieval hit identity, heading path, text preview, judgment labels. |
| GitNexus → working tree changes | Impact analysis maps dirty-tree changes to indexed symbols/execution flows. | Symbol names, file paths, process/flow metadata. |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-P10-01 | Information Disclosure | Demo output log | mitigate | Demo and artifacts only record `DATABASE_URL` existence/status; raw connection string was not printed or written. | closed |
| T-P10-02 | Tampering | Evidence-chain integrity | mitigate | DB-backed demo asserts `zero_chunk_hits=0`, `parent_only_hits=0`, and returns failure if final hits are not evidence-bearing chunks. | closed |
| T-P10-03 | Tampering | Evidence-chain provenance | mitigate | Final hit construction uses direct `chunk_ids`; runtime filters all-zero `MISSING_CHUNK_ID`; DB-backed and Phase 8 aligned retrieval both produced no all-zero chunks. | closed |
| T-P10-04 | Information Disclosure | Navigation metadata exposure | accept | Navigation metadata is an intended transparency feature and contains structural IDs/paths, not credentials or PII. | closed |
| T-P10-05 | Tampering | Judgment reuse integrity | mitigate | `judgment_reuse_assessment.json` compares query/rank/node/heading/preview identity and blocks reuse when match rate is invalid (`reuse_rate=0.0375`). | closed |
| T-P10-06 | Information Disclosure | Level assessment exposure | accept | Level/quality assessment is project transparency data, not secret or user-sensitive data. | closed |
| T-P10-07 | Denial of Service | Infinite recursion in traversal/subtree aggregation | mitigate | `_MAX_TRAVERSAL_DEPTH = 256` and active-path cycle detection fail fast on corrupt cyclic/deep trees. | closed |
| T-P10-08 | Tampering | Unbounded hotspot selection | mitigate | Hotspot selection is bounded by caller limit; demo and validation use explicit small limits, and runtime only traverses selected hotspots up to the requested retrieval limit. | closed |
| T-P10-09 | Tampering | Embedding dimension mismatch | mitigate | `SubtreeHotspotSelector` validates positive-int tree embedding dimension against query embedding length; tests cover mismatch rejection. | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-P10-01 | T-P10-04 | Navigation metadata exposure is intentional retrieval transparency. It includes structural provenance (node IDs, heading paths, drill depth), not secrets or PII. | Phase 10 security gate | 2026-06-12 |
| AR-P10-02 | T-P10-06 | Level assessment and quality metrics are project validation artifacts intended for planning transparency. They do not contain credentials, PII, or customer data. | Phase 10 security gate | 2026-06-12 |

---

## Mitigation Evidence

| Threat | Evidence |
|--------|----------|
| T-P10-01 | `10-VALIDATION.md` records no raw `DATABASE_URL` exposure; demo output printed source path/query/IDs only, not the connection string. |
| T-P10-02 | `10-01-SUMMARY.md` records demo exit code 0 and assertions: `zero_chunk_hits=0`, `parent_only_hits=0`, `total_hits=3`. |
| T-P10-03 | `10-03-SUMMARY.md` records Phase 8 aligned hotspot retrieval: 20 queries, 80 hits, `zero_chunk_hits=0`, `parent_only_hits=0`, `hotspot_metadata_hits=80`. |
| T-P10-05 | `verification/phase10-hotspot-quality-comparison/judgment_reuse_assessment.json` records `REUSE_BLOCKED`, 3 matched rows, and `reuse_rate=0.0375`. |
| T-P10-07 | `10-CODE-REVIEW.md` and `10-VALIDATION.md` record cycle/depth guard coverage and cyclic-tree regression test. |
| T-P10-08 | `10-VERIFICATION.md` verifies hotspot-scoped traversal and bounded retrieval behavior. |
| T-P10-09 | `10-VALIDATION.md` records positive-int dimension validation and targeted tests. |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-06-12 | 9 | 9 | 0 | Claude / gsd-secure-phase |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-06-12
