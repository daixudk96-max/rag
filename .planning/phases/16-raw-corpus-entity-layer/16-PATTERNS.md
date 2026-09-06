# Phase 16 (E2b): Raw Corpus Entity Layer — Pattern Map

**Mapped:** 2026-08-05
**Files analyzed (new/modified):** 18 (C1) + 2 (C2) classified
**Analogs found:** 16 / 20 (2 net-new adapter/model artifacts have no in-repo analog)
**Authority:** 16-BOUNDARY.md + `.planning/research/PHASE16-CHINESE-NER-MODEL-SELECTION-2026-07-13.md` (C1 model/output contract frozen) + `.planning/OKF-LOW-TOKEN-GAPS-SUPPLEMENT-HANDOFF-2026-07-12.md` §4 (C2).
**Read-only map:** this document only; no runtime/test/SQL/dependency/config file was modified.
**Boundaries (verbatim):** `D4 frozen until Phase 19.` · `Phase 20 needs separate pilot authorization + human G6 Go/No-Go.` · `DATABASE_URL and credentials must never be read/printed/logged/persisted into .planning artifacts.`

---

## 0. Boundary Corrections (must-fix for the planner)

The old boundary's migration pre-planning is stale and **must not** be carried into PLAN:

| Old boundary claim | Actual codebase state | Correction |
|---|---|---|
| "plan migration `019_node_entity_links`" | `019_e2a_materialization_contract.sql` already exists in `llamaindex_runtime/registry/migrations/` and is **used by Phase 15 E2a** (ownership/targets + append-only audit protection). | `019` is **not free** — never reuse it. Do not create `019_node_entity_links`. |
| `node_entity_links` needs a migration | Created in `005_kg_extension.sql:49-56`, extended with `confidence_score` + `mention_text` in `012_mapping_table_enrichment.sql:7-9`. | `node_entity_links` already exists. |
| `entity_mentions`/`entity_aliases`/`entity_merge_log` pending | All created in `016_entity_mentions.sql` (aliases lines 3-10, mentions 12-28, merge_log 30-36). | Already exist. |
| New migration number to be presumed | `FULL_MIGRATION_CATALOG` (`registry/migration_catalog.py:5-25`) ends at `019`. The next consecutive free slot is provisionally `020`. | Per ADR T5, the number is a **provisional-next** slot only, re-verified against `migration_catalog.py` at execution time. Neither `020` nor any C2 slot is irrevocably allocated before that check. C2's coref migration (if any) is a single later migration creating both `coref_clusters` + normalized membership, numbered only after C1's slot is confirmed. |

---

## 1. Existing Pattern Map (concrete analogs)

### 1.1 Config switches / enums / env-var validation

**Analog:** `llamaindex_runtime/config.py` — `RuntimeSettings` (frozen dataclass)

- `VALID_*` ClassVar frozensets at lines 29-46 (`VALID_VECTOR_BACKENDS`, `VALID_TREE_STRATEGIES`, `VALID_EMBEDDING_PROVIDERS`, `VALID_HOTSPOT_SELECTORS`).
- Field defaults at lines 48-65 (e.g. `rag_tree_hotspot_selector: str = "route_subtree"`).
- `__post_init__` fail-fast validation at lines 67-108: membership checks raise `ValueError(f"Unsupported ...")`, then per-backend URL validation.
- `from_env()` at lines 110-144: reads `os.getenv(name, default)`; `.env` file fallback `_load_env_file_fallback` (lines 11-24) fills only absent keys — process env wins.

```python
# config.py:29-46, 85-88
VALID_HOTSPOT_SELECTORS: ClassVar[frozenset[str]] = frozenset(
    {"route_subtree", "cluster", "hybrid_cluster"}
)
...
if self.rag_tree_hotspot_selector not in self.VALID_HOTSPOT_SELECTORS:
    raise ValueError(f"Unsupported hotspot selector: {self.rag_tree_hotspot_selector}.")
```

**Test analog:** `tests/llamaindex_runtime/test_config_llm_settings.py`
- Autouse fixture lines 24-31: `monkeypatch.chdir(tmp_path)` so a project `.env` cannot refill `delenv`-ed keys; default-value and invalid-value assertions (lines 146-154 show `pytest.raises(ValueError, match="Unsupported vector backend")`).

**Phase 16 use:** add `VALID_ENTITY_EXTRACTORS = frozenset({"off", "raner"})` + `rag_entity_extractor: str = "off"` (default OFF); C2 adds `VALID_COREF_RESOLVERS = frozenset({"off", "rules"})` + `rag_coref_resolver: str = "off"` and optional `rag_coref_model: str = "off"` placeholder whose only legal value is `"off"`. No existing `RAG_ENTITY_EXTRACTOR`/`RAG_COREF_RESOLVER`/`RAG_ROUTE_R3` symbol exists anywhere in `llamaindex_runtime/` (verified by grep) — all are net-new.

### 1.2 OKF immutable DTO + `deterministic_id` + `canonical_json`

**Analog:** `llamaindex_runtime/okf/e2a_contracts.py` (the master contract module)

- `E2A_NAMESPACE = uuid5(NAMESPACE_URL, "https://gitnexus.local/okf/e2a")` line 36.
- `canonical_json(value)` lines 47-54: `json.dumps(_canonical_value(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))`.
- `canonical_json_sha256(value)` lines 57-58.
- `deterministic_id(kind, natural_key)` lines 61-69: `str(uuid5(E2A_NAMESPACE, f"{kind}:{natural_key}"))`, rejects non-str/empty.
- Frozen DTOs with identity re-validation in `__post_init__`: `E2aManualFact` lines 105-133, `E2aEvidenceObject.create` lines 144-166, `E2aOwnershipFact.create` lines 256-310.
- `E2aDesiredState` lines 313-405: deep-freezes tuples/mappings, re-checks `canonical_json_sha256(corpus_manifest) == corpus_manifest_sha256`.
- `E2aReconciliationResult` lines 500-537: typed `Outcome` Literal (`changed|no_op|rolled_back_failure|acceptance_blocked|outcome_unknown`) + immutable counters.
- Support primitives `okf/e2a_contract_primitives.py` lines 14-81: `_canonical_value`, `_frozen_mapping`, `_freeze_json`, `_unicode_scalar`, `_tuple`, `_frozen_json_tuple`.

```python
# e2a_contracts.py:47-69
def canonical_json(value: object) -> str:
    return json.dumps(_canonical_value(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def deterministic_id(kind: str, natural_key: str) -> str:
    return str(uuid5(E2A_NAMESPACE, f"{kind}:{natural_key}"))
```

**Phase 16 use:** define `MentionCandidate` as a frozen dataclass in the exact style of `E2aManualFact` (lines 105-133) with provenance fields from the frozen contract (model selection doc §3.2). Reuse `deterministic_id("entity_mention", canonical_json(...))`-style identity for idempotent mention PK (idempotence identity must include `document_revision + span_id + char_start/char_end + normalized entity_type + source + extractor_id + model_revision` per BOUNDARY risk row).

**Overlap priority ladder (versioned, explicitly non-numeric):** `frontmatter_declared` > `dictionary_exact` > `rule_weight` > `model_probability` > `unavailable`. `unavailable` means the extractor emits no confidence — missing metadata, never low confidence. RaNER therefore writes `confidence=None` / `confidence_kind="unavailable"`, and the merger orders by this ladder, never by a fabricated numeric score.

### 1.3 Admission (filesystem-free, fail-closed)

**Analog A:** `llamaindex_runtime/okf/_raw_pair_admission.py`
- `prepare_raw_pair` (lines 44-55) validates bytes and computes the unbound canonical candidate; `confirm_raw_pair` (lines 58-64) binds to the manifest hash; `admit_raw_pair` (lines 67-71) combines both.
- `_freeze_value`/`thaw_frontmatter` (lines 74-104): tuple-backed immutable YAML representation, detached thaw for parser-facing code.

**Analog B:** `llamaindex_runtime/okf/e2a_admission.py`
- Budget constants lines 41-57; `admit_e2a_materialization_input` lines 76-94; `_admit_corpus` lines 114-149 (deterministic `sorted()` walks, `_ReadLedger` byte budgets lines 152-209); `_admit_fact` lines 423-470 (manual entity/relation/concept frontmatter → frozen fact); `_semantic_fact` lines 499-539 (canonical-entity-id natural key + `deterministic_id`).

**Phase 16 use:** a `corpus_span` input admission that reads OKF raw pairs via `BundleAuthority` + `read_raw_pair` and produces `CorpusSpanInput` with immutable `document_id/document_revision`, normalized text, and the resolvable normalized→sidecar projection. The 2.26 GB figure is the **model artifact/weights size**, not the model input size; input admission still follows the budget-ledger pattern for bounded text/segment budgets (never trust unbounded text).

### 1.4 Reconciler / transaction / failure-audit

**Analog:** `llamaindex_runtime/okf/e2a_reconciler.py` — `E2aReconciler`

- `_require_manual_transaction(connection)` lines 296-302: `autocommit` must be exactly `False`.
- `reconcile` lines 132-184: cursor-only; advisory xact locks `_acquire_scope_locks` lines 199-223 (`SELECT pg_advisory_xact_lock(hashtextextended(%s,0))` + `FOR UPDATE` row locks + table locks `_MANUAL_FACT_TABLE_LOCKS` lines 36-40); `_preflight_global_primary_keys` lines 408-534 (reject cross-scope PK takeover before any DML); commit; on failure rollback then `_write_failure_audit`.
- `_write_failure_audit` lines 225-277: writes `okf_rebuild_failure_audit` **through a separate connection** after primary rollback — deliberately not cross-database atomic (see `018_okf_rebuild_failure_audit.sql`).
- Cleanup status dataclasses lines 83-111 and helpers 325-402: every close/rollback confirmed or the outcome degrades (`outcome_unknown`, `reconciliation_required=True`).

**Phase 16 use:** one atomic transaction per **document/version** (not per span). On the first invalid span, abort that document by default (rolling back all of that document's state); later documents continue deterministically. Every failed document writes zero `entity_mentions`/alias/merge-log/link state. Post-rollback failure audit uses a **separate fresh connection**, appending to a **new append-only `okf_e2b_failure_audit`** table — the Phase 15 `okf_rebuild_failure_audit` contract is pinned by migration 019 and must not be reused or extended (see Risk R5). The E2b reconcile transaction acquires the **shared parent advisory xact lock using E2a's EXACT key string `okf:e2a:parent:{document_id}:{version_id}`** (never `okf:e2b:parent`), then locks the `document_versions` row FOR UPDATE, then E2b ownership/mention/link row locks, then DML — the fixed E2a/E2b cross-layer order.

### 1.5 Repository / full desired-state reconciliation / stale-ownership cleanup / DML recorder

**Analog:** `llamaindex_runtime/okf/e2a_materialization_repository.py` — `E2aMaterializationRepository.reconcile` lines 110-183
- Cursor-only; existing-scope load → validate destructive closure → ordered upserts → stale deletion; returns typed `E2aReconciliationResult`.
- `_DENYLIST_TABLES` lines 72-85 **already includes** `entity_mentions`, `entity_aliases`, `entity_merge_log`, `node_entity_links`, `chunk_entity_links`. E2a is forbidden from writing them (`DmlRecorder._validate_table`, `e2a_contracts.py:486-497`). **Phase 16 owns these tables and must NOT route its writes through `E2aMaterializationRepository`** — it needs its own repository that is *not* in E2a's allowlist path.
- Upsert primitive: `okf/e2a_materialization_dml.py` — `_UpsertSpec` lines 26-36; `_UPSERT_SPECS` lines 80-103 show the exact `INSERT ... ON CONFLICT (...) DO UPDATE SET ... WHERE <table>.version_id = EXCLUDED.version_id RETURNING 1` scope-guarded form.
- Deletion guards: `okf/_e2a_materialization_deletion_guards.py` — `validate_destructive_closure` lines 19-86 already probes `entity_mentions` (line 51), `node_entity_links` (line 72), `entity_aliases` (line 121), and `has_external_fact_dependency` lines 89-172 probes aliases/mentions/node-links/chunk-links before deleting a stale entity.

**Phase 16 use:** a new repository for `entity_mentions`/`entity_aliases`/`entity_merge_log`/`node_entity_links` that performs **full desired-state reconciliation, NOT upsert-only**. It reuses `_UpsertSpec`-style `ON CONFLICT ... DO UPDATE ... RETURNING 1` and a `DmlRecorder`-style typed counter, and extends them with a **stable E2b owner scope** (`e2b_owner_scope` derived from `document_id + version_id` alone — never embedding extractor/merger/model version; format `^okf:e2b:[0-9a-fA-F-]{32,36}:[0-9a-fA-F-]{32,36}$`, nullable = legacy/manual/unowned, never deletable or claimable) and an **`okf_e2b_node_link_ownership` ledger** with UNIQUE `(node_id, entity_id, version_id)`. The reconcile flow is: (1) acquire the shared parent advisory xact lock on E2a's exact key `okf:e2a:parent:{document_id}:{version_id}`, then `document_versions` FOR UPDATE, then ownership/mention/link row locks; (2) load existing E2b-owned state (mentions, link ownership ledger, bridges); (3) full preflight; (4) stable upsert of the desired set; (5) delete stale E2b-owned entity_mentions within the same owner scope (`WHERE e2b_owner_scope = current scope AND row NOT IN desired set`) and delete stale E2b link ownership; (6) delete a bridge only when E2b ledger ownership is explicit AND no other owner remains, else fail closed and preserve. **E2b NEVER deletes E2a-owned `canonical_spans`/`tree_nodes` rows** — those are outside E2b's deletion authority — but E2b MUST clean up its own ownership-scoped stale `entity_mentions`/`node_entity_links`. Because `entity_mentions.span_id` FK `ON DELETE CASCADE` and `entity_id` FK `ON DELETE SET NULL` (016), stale E2b-owned mention rows may be removed by E2b; E2a's stale-entity guards remain untouched. An equivalent rerun issues zero DML; a changed desired set (selected-set shrink on a surviving canonical span) deterministically converges; a changed-set failure rolls back ALL insert/update/delete restoring the original committed state before the fresh-connection audit append.

**Canonical-identity rule (D1):** E2b never creates new canonical entities from NER. It attaches an existing OKF entity only on an exact compatible canonical-name match or an exact OKF alias/dictionary match; otherwise `entity_mentions.entity_id` stays NULL. Human-gated entity creation is deferred to a later phase.

**Audit rule (D2):** C1 persists no durable raw candidate-audit table. Raw/duplicate/overlap and selected/suppressed/grouped decisions must be deterministically reconstructable from OKF raw+sidecar, versioned supplementary sources, and extractor/merger versions. Persist only the selected `entity_mentions`. Query artifacts remain request-scoped with a hard zero-persistence guard.

### 1.6 Canonical span / offset normalization

**Analog A:** `llamaindex_runtime/okf/roundtrip.py`
- `recompute_span_id` lines 21-32: `uuid5(NAMESPACE_URL, f"{doc_id}|{version_id}|{page_no}|{'/'.join(heading_path)}|{offset}|{text}")`.
- `validate_span_identity_admission` lines 44-59: rejects duplicate/non-canonical persisted span identities.

**Analog B:** `llamaindex_runtime/ingestion/normalization.py`
- `NormalizationContract` lines 46-116 with frozen `NormalizationRules`/`NormalizedNodeData`; explicit whitespace/heading/offset extraction (note: this normalizer operates on `offset`, not char coordinates — Phase 16's Unicode code-point `char_start/char_end` coordinate layer is net-new; `016_entity_mentions.sql:23-25` CHECK `char_start >= 0 AND char_end > char_start` already matches left-closed/right-open semantics).

**Analog C:** `llamaindex_runtime/interfaces/span.py` — `CanonicalSpan` frozen dataclass lines 7-41 with `coordinate`/`heading_path`.

### 1.7 `node_entity_links` writer (existing runtime seam)

**Analog:** `llamaindex_runtime/registry/postgres_adapter.py`
- `write_node_entity_links` lines 1257-1283: idempotent `INSERT ... ON CONFLICT (node_id, entity_id) DO NOTHING`, columns `(node_id, entity_id, ordinal_no, confidence_score, mention_text)`.
- `query_node_entity_links_by_version` lines 1285-1304 (join to `tree_nodes` on `version_id`), `query_nodes_by_entity` lines 1306-1324, `query_entities_by_node` lines 1326-1341.
- Protocol: `llamaindex_runtime/registry/contracts.py` lines 289-298.

**Phase 16 use (D5 resolution):** the span→mention→entity→node aggregation for NER-derived links can reuse this writer, but the current bridge stores only `node_id/entity_id/ordinal_no/confidence_score/mention_text` — it has no `span_id`/`mention_id` link-back (see Schema Gap Matrix). Populate `node_entity_links` **canonical-entity-only**; do **not** populate `chunk_entity_links`; keep the existing `node_entity_links` shape unless a later schema proof shows an extension is necessary. E2b link rows are tracked in the `okf_e2b_node_link_ownership` ledger (UNIQUE `(node_id, entity_id, version_id)`) so stale E2b-owned links can be cleaned deterministically while manual/legacy/foreign bridges (NULL owner scope) are preserved and never claimed. Pending mention-to-node association is recovered via `entity_mentions.span_id -> tree_node_spans.span_id -> tree_node_spans.node_id` (`tree_node_spans` PK is `(node_id, span_id)` per `003_tree_persistence.sql:22-27`) — no primary-key rewrite. Phase 16 has no retrieval reader; Phase 17 is the first consumer.

### 1.8 E2b runner / rebuild entry

**Analog A:** `scripts/rebuild_from_okf_e2a.py` (E2a CLI; E1 sibling `scripts/rebuild_from_okf.py`)
- `parse_arguments` lines 190-210: `--bundle`, `--verify-roundtrip`, `--fixture`, `--rebuild`; parity with E1 CLI.
- `_require_disposable_rebuild_parameters` lines 377-415: gates `DATABASE_URL` present, `OKF_MIGRATION_TEST_DATABASE_DISPOSABLE=1`, `OKF_REBUILD_EXPECTED_DATABASE` set, plus `OKF_E2A_DISPOSABLE_TEST_AUTHORIZED=1` for the whole-corpus route, and `reject_ambient_service_routing`.
- `_e2a_rebuild_bundle` lines 500-536: `BundleAuthority` → `admit_e2a_materialization_input` → `connection_factory()` → fresh `E2aReconciler` → redacted typed outcome.
- `_redact_reconciliation_outcome` lines 461-497 and `_format_outcome` lines 574-594: only counters/outcome ever surface; never a DSN, manifest body, span text, or row payload.
- Connection guard: `scripts/_rebuild_database_connection.py` — `DisposablePostgresqlTarget` (fully redacted repr/str, lines 59-81), `parse_disposable_postgresql_target` (loopback-only URI, lines 130-153), `reject_ambient_service_routing` (lines 156-160), `runtime_connection_factory` (explicit libpq kwargs, no URI passthrough, lines 202-228).

**Analog B:** `llamaindex_runtime/ingestion/pipeline.py` — `IngestionPipeline._ingest_e2a` lines 57-128: register → get_version → convert → content-hash guard → serialize → admit via `BundleAuthority` → `connection_factory()` with `autocommit is False` check → `reconciler.reconcile`.

**Phase 16 use:** E2b runner/CLI mirrors `rebuild_from_okf_e2a.py` structure (admit bundle → open disposable connection → run repository → redacted typed summary), iterating documents deterministically with one atomic transaction per document/version. **Constraint:** the E2b runner must *read* E2a-materialized manual OKF facts (`entities`/`okf_manual_fact_ownership`/`okf_manual_evidence_targets`) for canonical identity during normalization but must never rewrite or re-materialize E2a manual facts — the two evidence sources remain disjoint.

### 1.9 jieba / keyword reference

**Analog:** `llamaindex_runtime/tree/runtime.py` — `_extract_keywords_from_query` lines 89-113: lazy `import jieba`, `jieba.setLogLevel(logging.WARNING)`, built-in general dictionary only, stopword + token-length + regex filters. jieba is a **runtime dependency already declared** (`pyproject.toml:18`). Per BOUNDARY, jieba is only a supplementary keyword/dictionary source, not the C1 primary recognizer.

### 1.10 Migration catalog registry

**Analog:** `llamaindex_runtime/registry/migration_catalog.py` — `FULL_MIGRATION_CATALOG` lines 5-25 (001-019). Any Phase 16 DDL must be registered here; catalog is authoritative for the disposable acceptance harness (`okf/e2a_disposable_execution.py` `_validate_catalog_filenames` lines 31-46 rejects names outside the catalog).

### 1.11 Test organization, selectors, disposable DB harness, authorization gates

- Worktree/markers: `tests/conftest.py` — inserts worktree root into `sys.path`; registers `live_st` and `integration` markers.
- Authorization gate (the pattern to copy verbatim): `tests/llamaindex_runtime/okf/test_e2a_disposable_postgres.py`
  - `_AUTHORIZATION_FLAG = "OKF_E2A_DISPOSABLE_TEST_AUTHORIZED"` (line 19); `_separately_authorized()` returns True only when env == `"separately-authorized"` (lines 22-24); `pytestmark = pytest.mark.skipif(not _separately_authorized(), reason=...)` (lines 27-30). Module is deliberately inert without the flag.
- Authority-object gate: `llamaindex_runtime/okf/e2a_disposable_acceptance.py` — `run_disposable_migration_acceptance` lines 179-219 requires `authority.authorized is True` (bool), else returns `"blocked_not_executed"`; `run_current_disposable_postgresql_acceptance` lines 222-237.
- Fake-cursor unit tests (no DB): `tests/llamaindex_runtime/okf/test_e2a_wave2_entity_mentions_deletion_guard.py` — `_EntityMentionDependencyCursor` lines 115-167 statement-matching fake; asserts probe ordering and zero forbidden DML.
- Fixture helpers: `tests/llamaindex_runtime/okf/raw_pair_testkit.py` — `write_raw_pair` lines 32-37, `refresh_raw_manifest` lines 13-29, `bind_raw_bytes` lines 40-61.
- Live acceptances are separate scripts (`tests/llamaindex_runtime/okf/phase15_e2a_task*.py`) — keeps the default test run free of DB/live-model work.

**Phase 16 use:** all model-live and disposable-DB tests must sit behind an explicit non-secret authorization flag (same `skipif` + authority-object pattern). The default test collection excludes the extractor-live suite; the `RAG_ENTITY_EXTRACTOR=off` default path must run with zero model imports and zero LLM-client calls (fake/spy client assertion per BOUNDARY acceptance).

---

## 2. File Classification

| New/Modified File (C1) | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `llamaindex_runtime/config.py` (mod) | config | n/a | `config.py` `RuntimeSettings` | exact |
| `llamaindex_runtime/entity/contracts.py` (new) | contracts/DTO | request-response | `okf/e2a_contracts.py` | role-match |
| `llamaindex_runtime/entity/extractor.py` (new) | interface (Protocol) | batch/transform | `okf/e2a_admission.py` + `okf/roundtrip.py` | partial |
| `llamaindex_runtime/entity/raner_adapter.py` (new) | adapter | batch/transform | **none (net-new)** | — |
| `llamaindex_runtime/entity/label_map.py` (new) | config/transform | transform | `okf/canonical_hash.py` (digest pattern) | partial |
| `llamaindex_runtime/entity/segmenter.py` (new) | utility | transform | `okf/roundtrip.py` + `ingestion/normalization.py` | partial |
| `llamaindex_runtime/entity/merger.py` (new) | service | transform/batch | `okf/e2a_admission.py` `_admit_corpus` stable sorts | partial |
| `llamaindex_runtime/entity/dictionary_loader.py` (new) | loader | file-I/O | `okf/parser.py` `OKFParser` | partial |
| `llamaindex_runtime/entity/frontmatter_supplement.py` (new) | loader | file-I/O | `okf/parser.py` + `okf/contracts.py` | role-match |
| `llamaindex_runtime/entity/materialization_repository.py` (new) | repository | CRUD | `okf/e2a_materialization_repository.py` + `okf/e2a_materialization_dml.py` | role-match |
| `llamaindex_runtime/entity/runner.py` (new) | runner/service | batch/CRUD | `scripts/rebuild_from_okf_e2a.py` | exact |
| `llamaindex_runtime/registry/migration_catalog.py` (mod) | config | n/a | `FULL_MIGRATION_CATALOG` | exact |
| `scripts/rebuild_entity_layer.py` (new) | CLI entry | batch | `scripts/rebuild_from_okf_e2a.py` | exact |
| `llamaindex_runtime/entity/failure_audit.py` (new) | utility | event-driven (append-only audit) | `okf/e2a_reconciler.py` `_write_failure_audit` | partial |
| `tests/llamaindex_runtime/entity/test_*.py` (new) | test | n/a | `tests/llamaindex_runtime/okf/` suite | exact |

| New/Modified File (C2, conditional) | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `llamaindex_runtime/entity/coref_resolver.py` (new) | service | transform | `okf/e2a_reconciler.py` (rule ordering) | partial |
| `coref_clusters` + membership migration (new, number TBD at execution) | migration | n/a | `016_entity_mentions.sql` | exact |
| `RAG_COREF_RESOLVER`/`RAG_COREF_MODEL` config (mod) | config | n/a | `config.py` `RuntimeSettings` | exact |

---

## 3. Schema Gap Matrix

### 3.1 `entity_mentions` (created `016_entity_mentions.sql:12-28`) vs frozen `MentionCandidate` (model selection doc §3.2)

| Phase 16 DTO / provenance field | Existing column? | Gap |
|---|---|---|
| `mention_id` | `mention_id UUID PK` | exists; must be `deterministic_id`-derived for idempotence |
| `entity_id` (nullable/pending) | `entity_id UUID REFERENCES entities ON DELETE SET NULL` | **exists and nullable** — satisfies C2 forward contract; stays NULL until an exact canonical-name / OKF alias / dictionary match (canonical-identity rule D1) |
| `span_id` (corpus) | `span_id UUID NOT NULL REFERENCES canonical_spans` | exists |
| `char_start` / `char_end` | `char_start INTEGER`, `char_end INTEGER`, `CHECK (char_start>=0 AND char_end>char_start)` | exists; CHECK already enforces left-closed/right-open, but no Python code-point DTO exists |
| `mention_text` | `mention_text TEXT NOT NULL` | exists; adapter must hard-assert `normalized_text[start:end] == mention_text` |
| `source` (`model/dictionary/rule/frontmatter`) | `source TEXT NOT NULL` | exists as free text; needs a constrained value set or validation |
| `confidence` | `confidence NUMERIC` | exists nullable (holds `None` = unavailable) |
| `confidence_kind` | — | **missing** (see Risk R3) |
| `raw_label` | — | **missing** (only `mention_text` + `source`; `raw_label=PER/CORP/...` not storable) |
| `entity_type` (canonical) | — | **missing** on mentions (exists on `entities.entity_type TEXT`) |
| `input_id` / `input_kind` / `input_revision` / `document_revision` | — | **missing** direct columns; `version_id` reachable only via `span_id → canonical_spans.version_id` |
| `extractor_id` / `extractor_version` | — | **missing** |
| `model_id` / `model_revision` | — | **missing** |
| `artifact_digest` | — | **missing** |
| `schema_version` / `normalization_version` / `segmentation_version` / `label_map_digest` / `runtime_compatibility_id` | — | **missing** |
| `document_char_start` / `document_char_end` (projection) | — | **missing** |
| `segment_id` | — | **missing** |
| `okf_file_path` / `okf_paragraph_id` | `okf_file_path TEXT`, `okf_paragraph_id TEXT` | exists (spillover from E2a) |
| `e2b_owner_scope` (stable owner identity) | — | **missing**; migration 020 adds it derived from `document_id + version_id` alone (never extractor/merger/model version); NULL = legacy/manual/unowned, never deletable or claimable |

### 3.2 `entity_aliases` (016:3-10)

Has `alias_id UUID PK`, `entity_id UUID NOT NULL REFERENCES entities`, `alias TEXT NOT NULL`, `source TEXT`. **Missing:** alias normalization provenance (`normalization_version`, `raw_alias`, `confidence_kind`, extractor/model provenance, deterministic alias identity). `entity_id` NOT NULL means alias rows require a resolved canonical entity — under the canonical-identity rule, NER mentions with NULL `entity_id` cannot produce alias rows until an exact OKF alias/dictionary match resolves them.

### 3.3 `entity_merge_log` (016:30-36)

Has `merge_id UUID PK`, `from_entity_id`, `into_entity_id`, `reason TEXT`, `merged_at`. **Missing:** provenance (`merge_kind`, `confidence_kind`, `source`, `extractor_id`, `model_revision`, reversible marker). BOUNDARY: NER candidates never directly merge canonical entities; `entity_merge_log` is for reversible alias normalization only, and query candidates never write it. NER-only mentions (NULL `entity_id`) never appear here.

### 3.4 `node_entity_links` (005:49-56 + 012:7-9)

Has `node_id UUID NOT NULL REFERENCES tree_nodes`, `entity_id UUID NOT NULL REFERENCES entities`, `ordinal_no`, `confidence_score DOUBLE PRECISION`, `mention_text TEXT`. **Missing:** `span_id`/`mention_id` link-back to the mention row, char coordinates, `source`/provenance. **Resolution (D5):** keep the existing shape canonical-entity-only; do not populate `chunk_entity_links`; do not add link-back columns unless a later schema proof shows an extension is necessary. Add `okf_e2b_node_link_ownership` (ledger, UNIQUE `(node_id, entity_id, version_id)`) in migration 020 so stale E2b-owned links can be cleaned while manual/legacy/foreign bridges (NULL owner scope) are preserved and never claimed. Pending mention-to-node association is recovered via `entity_mentions.span_id -> tree_node_spans.span_id -> tree_node_spans.node_id` — no primary-key rewrite. Phase 16 has no retrieval reader; Phase 17 is the first consumer.

### 3.5 Canonical entity types

`entities.entity_type` is free-form `TEXT` (005:7) — no constraint blocks `Person`/`Location`/`Organization`/`CreativeWork`/`Product`. Research doc §1.4 "if OKF schema lacks CreativeWork/Product, PLAN must align schema first" → **no migration needed** for the canonical type enum; only label-map validation on the write path.

---

## 4. Recommended File Map (new package layout per repo convention)

Existing packages are feature/domain oriented (`okf/`, `registry/`, `analysis/`, `processing/`, `graph/`, `vector/`, `tree/`). A new `llamaindex_runtime/entity/` package matches that convention:

```
llamaindex_runtime/entity/
├── __init__.py
├── contracts.py          # EntityExtractor Protocol, ExtractionInput union,
│                         #   CorpusSpanInput / QueryTextInput, MentionCandidate (frozen),
│                         #   overlap priority ladder (frontmatter_declared > dictionary_exact
│                         #   > rule_weight > model_probability > unavailable)
├── extractor.py          # registry + RAG_ENTITY_EXTRACTOR dispatch (off|raner)
├── raner_adapter.py      # RaNER Large Generic adapter (net-new; ModelScope pipeline)
├── label_map.py          # versioned RaNER label → OKF canonical type map + digest
├── segmenter.py          # deterministic long-text segmentation + versioned offset map
├── merger.py             # deterministic candidate merger (stable sort, selected/suppressed/grouped,
│                         #   ordered by the versioned non-numeric priority ladder)
├── dictionary_loader.py  # OKF-ized domain dictionary loader (git + canonical hash)
├── frontmatter_supplement.py  # reads OKF frontmatter entity declarations (reuse parser/contracts)
├── materialization_repository.py  # full desired-state reconciliation into entity_mentions/aliases/
│                         #   merge_log/node_entity_links (canonical-entity-only; no chunk_entity_links;
│                         #   stable e2b_owner_scope; okf_e2b_node_link_ownership ledger; stale
│                         #   E2b-owned cleanup; bridge deletion only with explicit ownership + no
│                         #   other owner, else fail-closed preserved; rollback on changed-set failure)
├── runner.py             # E2b batch runner (one atomic transaction per document/version, first invalid
│                         #   span aborts that document, deterministic continue to later documents,
│                         #   idempotent, statistics, no E2a rewrite)
└── failure_audit.py      # writer for new append-only okf_e2b_failure_audit (fresh connection after rollback)
```

Tests: `tests/llamaindex_runtime/entity/` (pure unit tests default-off; `test_*_live.py` behind authorization gate). C2 adds `entity/coref_resolver.py` + `entity/coref_contracts.py` (conditional wave).

---

## 5. Reuse vs New

### 5.1 Reuse (copy patterns verbatim)

| Pattern | Source | Copy to |
|---|---|---|
| Frozen DTO + `__post_init__` identity re-check | `okf/e2a_contracts.py` lines 105-133 | `entity/contracts.py` `MentionCandidate`, `CorpusSpanInput`, `QueryTextInput` |
| `deterministic_id` / `canonical_json` / `canonical_json_sha256` | `okf/e2a_contracts.py` lines 47-69 | `entity/contracts.py` (mention/alias/merge identity + manifest hash) |
| Frozen value primitives | `okf/e2a_contract_primitives.py` | `entity/contracts.py` |
| Fail-fast config switch | `config.py` lines 29-108 + `test_config_llm_settings.py` | `RAG_ENTITY_EXTRACTOR`, C2 `RAG_COREF_RESOLVER` |
| Manual transaction + scope locks + failure audit | `okf/e2a_reconciler.py` lines 132-277 | `entity/runner.py` per-document/version atomic boundary + separate fresh audit connection + E2a-shared advisory key `okf:e2a:parent:{document_id}:{version_id}` |
| Scope-guarded upsert (`ON CONFLICT ... DO UPDATE ... RETURNING 1`) | `okf/e2a_materialization_dml.py` lines 80-103 | `entity/materialization_repository.py` |
| Idempotent `node_entity_links` insert (`DO NOTHING`) | `registry/postgres_adapter.py` lines 1257-1283 | NER-derived link aggregation (canonical-entity-only) |
| Disposable DB guard + redacted target | `scripts/_rebuild_database_connection.py` + `rebuild_from_okf_e2a.py` lines 377-415 | `scripts/rebuild_entity_layer.py` |
| Disposable acceptance authority gate | `okf/e2a_disposable_acceptance.py` lines 179-237 + `test_e2a_disposable_postgres.py` | Phase 16 disposable acceptance + tests |
| Deletion guards for entity tables | `okf/_e2a_materialization_deletion_guards.py` lines 19-172 | (already guard Phase 16 tables; verify they cover any new node_entity_links shape) |
| Bundle authority raw-pair admission + budgets | `okf/e2a_admission.py` lines 76-209 | `entity/runner.py` corpus-span admission (bounded text/segment budgets) |
| Deterministic span identity | `okf/roundtrip.py` lines 21-59 | `entity/segmenter.py` segment→parent projection |
| jieba keyword supplement | `tree/runtime.py` lines 89-113 | `entity/dictionary_loader.py` (supplement only) |

### 5.2 New (no in-repo analog — planner uses RESEARCH.md / frozen model doc)

| New artifact | Reason | Authority |
|---|---|---|
| `raner_adapter.py` (ModelScope `iic/nlp_raner_named-entity-recognition_chinese-large-generic`) | no existing local NER adapter; must be real and runnable, offline, `confidence=None`/`confidence_kind="unavailable"`, no `str.find` recovery | model selection doc §1, §3 |
| `MentionCandidate` char-coordinate contract + Unicode code-point offset layer | existing `CanonicalSpan` uses `offset` (int) not char indices; no Python code-point half-open coordinate DTO exists | model doc §3.1-3.2 |
| Per-file SHA-256 artifact lock manifest + offline read-only mirror | no lock-manifest runtime exists (`canonical_hash`/`GenerationManifest` are the nearest structural analog); the lock targets the 2.26 GB **model artifact**, not input | model doc §1.3 |
| `label_map` versioned mapping (PER→Person, CORP/GRP→Organization, LOC→Location, CW→CreativeWork, PROD→Product) | net-new | model doc §1.4 |
| Deterministic segmenter + `segmentation_version` | net-new (model 512-token limit) | model doc §3.1, BOUNDARY |
| Candidate merger (stable sort, selected/suppressed/grouped, ordered by the versioned non-numeric priority ladder, pre-merge audit) | net-new | BOUNDARY In Scope |
| `confidence_kind` typed confidence + `unavailable` semantics (missing metadata, not low confidence) | net-new | BOUNDARY + model doc §3.2 |
| Canonical-identity rule enforcement (D1: exact compatible canonical-name / exact OKF alias/dictionary match only; else `entity_id=NULL`; no NER-derived canonical entity creation) | net-new | BOUNDARY + review correction 4 |
| No durable raw candidate-audit table in C1 (D2: raw/duplicate/overlap and selected/suppressed/grouped decisions reconstructable from OKF raw+sidecar + versioned sources + extractor/merger versions) | net-new | BOUNDARY + review correction 5 |
| Query-text request-scoped isolation (zero durable-sink writes) | net-new contract | BOUNDARY + model doc §3.2 |
| New append-only `okf_e2b_failure_audit` table + writer | net-new; Phase 15 `okf_rebuild_failure_audit` is pinned by migration 019 and must not be reused/extended | review correction 2 |
| E2b materialization repository for the 4 entity tables (separate from E2a allowlist path) | E2a denylists these tables | `e2a_contracts.py` lines 427-440, `e2a_materialization_repository.py` lines 72-85 |
| Stable `e2b_owner_scope` (document_id + version_id only, never extractor/merger/model version) + `okf_e2b_node_link_ownership` ledger (UNIQUE `(node_id, entity_id, version_id)`) | ownership/provenance ledger is NOT a candidate audit (D2); enables stale E2b-owned cleanup while legacy/manual/foreign rows stay preserved and never claimed | A finding, D2, D5 |
| Full desired-state reconciliation (load existing E2b-owned state → preflight → stable upsert → delete stale E2b-owned mentions/links → delete bridge only with explicit ownership AND no other owner, else fail closed) | NOT upsert-only; deterministic convergence + rollback on changed-set failure | A finding |

---

## 6. Future GitNexus Impact Targets

Before any future edit touches these production symbols, run `gitnexus_impact({target, direction: "upstream"})` first (per project CLAUDE.md). **This task performs no edits.**

| Symbol | Location | Why it must be checked |
|---|---|---|
| `RuntimeSettings` / `RuntimeSettings.from_env` | `llamaindex_runtime/config.py` | adding `rag_entity_extractor`/`rag_coref_resolver` fields touches the frozen dataclass + env parsing used by every entrypoint |
| `E2aReconciler.reconcile` | `llamaindex_runtime/okf/e2a_reconciler.py` | transaction/failure-audit orchestration; any shared failure-audit table change ripples here |
| `E2aMaterializationRepository.reconcile` | `llamaindex_runtime/okf/e2a_materialization_repository.py` | its `_DENYLIST_TABLES` includes the 4 Phase 16 tables; adding DML paths must not leak into E2a |
| `E2aDesiredState`, `deterministic_id`, `canonical_json` | `llamaindex_runtime/okf/e2a_contracts.py` | the identity/canonical-json contract Phase 16 reuses; changing namespace breaks all derived ids |
| `DmlRecorder._validate_table` / `_E2A_DENYLIST_TABLES` | `llamaindex_runtime/okf/e2a_contracts.py` | forbid/allow table sets |
| `validate_destructive_closure`, `has_external_fact_dependency` | `llamaindex_runtime/okf/_e2a_materialization_deletion_guards.py` | probes `entity_mentions`/`entity_aliases`/`node_entity_links`; any new link shape must be added here |
| `RegistryWriter.write_node_entity_links` / `query_node_entity_links_by_version` / `query_nodes_by_entity` | `llamaindex_runtime/registry/contracts.py` + `registry/postgres_adapter.py` | existing runtime seam for node→entity links; Phase 16 aggregation may extend the row shape |
| `OKFParser.parse_bundle` / `compute_sync_decision` / `validate_known_frontmatter` | `llamaindex_runtime/okf/parser.py`, `okf/contracts.py` | source of canonical entity identity for normalization |
| `BundleAuthority` / `read_raw_pair` | `llamaindex_runtime/okf/rooted_open.py`, `okf/raw_pair.py` | E2b runner input admission |
| `FULL_MIGRATION_CATALOG` | `llamaindex_runtime/registry/migration_catalog.py` | any new migration must be registered here or disposable acceptance refuses it; re-verify the provisional `020` slot at execution |
| `_extract_keywords_from_query` | `llamaindex_runtime/tree/runtime.py` | the only jieba production reference; if a shared dictionary loader is extracted, upstream callers affected |
| `NormalizationContract` / `NormalizationRules` | `llamaindex_runtime/ingestion/normalization.py` | offset semantics vs new char-coordinate layer; do not coerce char offsets into `offset` |
| `SpanSidecar` / `SpanRecord` / `recompute_span_id` | `llamaindex_runtime/okf/sidecar.py`, `okf/roundtrip.py` | the normalized-text evidence projection Phase 16 must map back to |
| `RawFrontmatterContract` / `validate_known_frontmatter` | `llamaindex_runtime/okf/contracts.py` | entity/relation/concept frontmatter read path |
| `runtime_connection_factory` / `parse_disposable_postgresql_target` | `scripts/_rebuild_database_connection.py` | shared disposable-DB guard used by any E2b rebuild CLI |

---

## 7. Planning Risks

| # | Risk | Pattern-based mitigation |
|---|---|---|
| R1 | Old boundary assumes `019_node_entity_links`; `019` is already E2a's materialization contract and `node_entity_links` already exists (005+012). | Do not issue a `node_entity_links` create migration and never reuse `019`. Any new columns are an `ALTER TABLE` on an existing table, numbered per ADR T5 at execution against `migration_catalog.py` (provisional `020`, not final). |
| R2 | `entity_mentions` is in E2a's denylist; Phase 16 writes must not be routed through `E2aMaterializationRepository`. | Build a separate repository; keep `DmlRecorder`-style typed counters; add the Phase 16 repository to no allowlist E2a consumes. |
| R3 | `confidence NUMERIC` cannot encode `confidence_kind`; RaNER has no mention confidence. | Store `confidence=NULL` + add a `confidence_kind` value (`unavailable` etc.). `unavailable` means missing metadata, not low confidence. Never fabricate a probability; order overlaps by the versioned non-numeric priority ladder (`frontmatter_declared > dictionary_exact > rule_weight > model_probability > unavailable`), never by a numeric score (BOUNDARY + model doc §3.2). |
| R4 | `entity_mentions` has no `raw_label`/`entity_type`/provenance columns; the frozen `MentionCandidate` carries ~15 provenance fields. | Either add columns in the (provisional `020`) migration or persist a compact provenance JSONB. BOUNDARY acceptance requires per-row provenance for every corpus mention. |
| R5 | `018_okf_rebuild_failure_audit` phase CHECK is embedded in migration 019's append-only contract; altering it re-validates the whole 019 catalog. | **Decided:** introduce a new append-only `okf_e2b_failure_audit` table and writer (fresh connection post-rollback). Do not modify or reuse Phase 15's `okf_rebuild_failure_audit`. |
| R6 | Query-text candidates must be request-scoped with zero durable writes. | No schema for query; enforce zero-write via the same fake-cursor/spy test pattern as `test_e2a_wave2_entity_mentions_deletion_guard.py` (assert no INSERT/UPDATE/DELETE into durable sinks). |
| R7 | 2.26 GB **model artifact**; ModelScope `master` is mutable; SDK tuple unverified on Windows/WSL. | Per-file SHA-256 lock manifest + read-only mirror + offline smoke test before freezing the runtime tuple; if over budget, only an explicit Base-News degradation decision (model doc §1.3, §4.7-8). Input admission still uses bounded text/segment budgets. |
| R8 | `entity_aliases.entity_id` is NOT NULL — NER mentions with pending `entity_id` cannot alias until normalized. | Pipeline order: mention rows first (nullable entity), alias rows only after an exact canonical/alias/dictionary resolution; `entity_merge_log` records reversible alias merges only. |
| R9 | `node_entity_links` granularity (node vs chunk) affects Phase 17 recall SQL. | **Decided conservatively:** keep `node_entity_links` canonical-entity-only, do not populate `chunk_entity_links`; recover pending mention-to-node via `entity_mentions.span_id -> tree_node_spans.span_id -> tree_node_spans.node_id` (no PK rewrite). Add `okf_e2b_node_link_ownership` ledger so stale E2b-owned links clean up while manual/legacy/foreign bridges are preserved. Phase 16 has no retrieval reader; Phase 17 is the first consumer. |
| R10 | C2 conditional: `RAG_COREF_RESOLVER=off\|rules`, `RAG_COREF_MODEL` placeholder only `off`; no model value may be exposed before a full freeze. | Gate all coref behind the same config-switch + authorization pattern; C2 migration (if any) is one later migration, numbered only after C1's provisional `020` is confirmed, ordered per ADR T5. |
| R11 | D4 frozen until Phase 19; Phase 20 needs separate pilot authorization + human G6; C2 conditional/default-off. | No default-on claim, no quality/recall claim, no net-benefit adjudication in Phase 16. Verbatim: `D4 frozen until Phase 19.` · `Phase 20 needs separate pilot authorization + human G6 Go/No-Go.` · `DATABASE_URL and credentials must never be read/printed/logged/persisted into .planning artifacts.` |
| R12 | E2b must not create canonical entities from NER. | Enforce canonical-identity rule (D1): only exact compatible canonical-name or exact OKF alias/dictionary match attaches an existing OKF entity; otherwise `entity_mentions.entity_id` stays NULL. Human-gated entity creation deferred. |
| R13 | C1 must not persist a raw candidate-audit table. | Persist only selected `entity_mentions` (D2); raw/duplicate/overlap and selected/suppressed/grouped decisions must be deterministically reconstructable from OKF raw+sidecar, versioned supplementary sources, and extractor/merger versions. |
| R14 | E2b could be read as overall upsert-only and never clean stale rows. | Not upsert-only: full desired-state reconciliation. E2b never deletes E2a-owned `canonical_spans`/`tree_nodes` but MUST clean its own ownership-scoped stale `entity_mentions`/`node_entity_links` (via `e2b_owner_scope` and the `okf_e2b_node_link_ownership` ledger); a bridge is deleted only when E2b ledger ownership is explicit AND no other owner remains, else fail-closed preserved; changed-set failures roll back to the original committed state. |
| R15 | E2b might use its own advisory key instead of E2a's. | Cross-layer lock must reuse E2a's EXACT shared advisory key `okf:e2a:parent:{document_id}:{version_id}` (never `okf:e2b:parent`) in the fixed order: shared parent advisory xact lock → `document_versions` FOR UPDATE → E2b ownership/mention/link row locks → DML. |

---

## 8. No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `llamaindex_runtime/entity/raner_adapter.py` | adapter | batch/transform | No local NER/ModelScope adapter exists anywhere in the repo; follow RESEARCH.md frozen output contract + pytest Protocol style |
| `llamaindex_runtime/entity/merger.py` | service | transform | No deterministic multi-source candidate merger exists; stable-sort inspiration from `okf/e2a_admission.py` `sorted()` walks; overlap ordering by the versioned non-numeric priority ladder |

---

## Metadata

**Analog search scope:** `llamaindex_runtime/` (config, okf/, registry/, ingestion/, tree/, interfaces/, scripts/), `scripts/`, `tests/`, `llamaindex_runtime/registry/migrations/`, `.planning/` (BOUNDARY, ROADMAP, research, supplement handoff).
**Files scanned:** ~45 (read full: config.py, e2a_contracts.py, e2a_contract_primitives.py, e2a_reconciler.py, e2a_materialization_repository.py, e2a_materialization_dml.py, e2a_admission.py, _e2a_materialization_deletion_guards.py, _raw_pair_admission.py, canonical_hash.py, sidecar.py, roundtrip.py, parser.py, _frontmatter.py, e2a_disposable_acceptance.py, e2a_disposable_execution.py, migration_catalog.py, postgres_adapter.py (node_entity_links section), contracts.py (registry), tree/runtime.py (jieba), ingestion/pipeline.py, ingestion/normalization.py, interfaces/span.py, scripts/rebuild_from_okf_e2a.py, scripts/_rebuild_database_connection.py, migrations 003/005/012/016/017/018/019, conftest.py, test_config_llm_settings.py, test_e2a_disposable_postgres.py, test_e2a_wave2_entity_mentions_deletion_guard.py, raw_pair_testkit.py).
**Pattern extraction date:** 2026-08-05
**Review correction applied:** 2026-08-05 (8 items, single review pass; verified `tree_node_spans` columns in `003_tree_persistence.sql:22-27`)
