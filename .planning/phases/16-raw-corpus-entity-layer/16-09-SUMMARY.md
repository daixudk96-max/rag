---
phase: 16-raw-corpus-entity-layer
plan: 09
subsystem: entity
tags: [desired-state-reconciliation, materialization, failure-audit, e2b, owner-scope, advisory-lock, fail-closed, tdd, review-finding, psycopg-row-normalization]
type: tdd
wave: 3
macro_wave: W3
depends_on: [16-02, 16-04]
requires:
  - phase: 16-02
    provides: Frozen CorpusSpanInput/MentionCandidate with full provenance and conditional nullable model provenance.
  - phase: 16-04
    provides: Deterministic E2b identity helpers (deterministic_id) and pure contract primitives.
provides:
  - Per-document/version atomic FULL desired-state reconciliation of entity_mentions + node_entity_links (stable upsert + ownership-scoped stale deletion + bridge ownership ledger) under the E2a-shared advisory lock.
  - Append-only okf_e2b_failure_audit writer via a fresh connection after primary rollback+close.
  - RED tests for reconciliation, convergence, stale cleanup, manual/legacy preservation, shared-lock ordering, atomic isolation, idempotence, psycopg row-typing, and failure audit.
affects: [16-10, 16-13]
requirements: [R-OKF-01, R-OKF-06]

tech-stack:
  added: []
  patterns:
    - "FULL desired-state reconciliation per document/version, never upsert-only: load existing E2b-owned state -> full preflight -> stable ON CONFLICT upsert -> ownership-scoped stale mention deletion -> stale link-ownership deletion -> ownership-safe bridge deletion (fail closed otherwise)."
    - "E2a-shared parent advisory xact lock key okf:e2a:parent:{document_id}:{version_id} (never okf:e2b:parent) in fixed order: advisory lock -> document_versions FOR UPDATE -> bounded row reads/locks -> preflight (incl. D5 span proof) -> DML."
    - "Bounded all-version owner proof (okf_e2b_node_link_ownership WHERE node_entity_link_key = ANY(%s) FOR UPDATE) is the authoritative ownership lock after bridge locking and before any DML; the current-version ownership inventory (WHERE version_id = %s) is a plain inventory read WITHOUT FOR UPDATE (deadlock-safe)."
    - "Recursive psycopg row normalization at the repository boundary (uuid.UUID -> canonical str); PostgreSQL NUMERIC equality via postgres_values_equal (Decimal vs finite float); mention ON CONFLICT guard owned-by-same-scope (TOCTOU-safe)."
    - "Migration-003/020 schema consistency: tree_nodes.node_id binds one version and the ownership trigger enforces ownership version = node version, so same-pair cross-version co-ownership is unreachable; an explicit other-version owner proof is schema-inconsistent and fails closed."

key-files:
  created:
    - llamaindex_runtime/entity/materialization_repository.py
    - llamaindex_runtime/entity/failure_audit.py
    - tests/llamaindex_runtime/entity/test_materialization_repository.py
    - tests/llamaindex_runtime/entity/test_failure_audit.py
  modified:
    - llamaindex_runtime/entity/__init__.py  # additive facade exports
  summary:
    - .planning/phases/16-raw-corpus-entity-layer/16-09-SUMMARY.md

key-decisions:
  - "D4/D5 frozen: preflight-first document/version abort with zero writes; node_entity_links written only for resolved entities with (node_id, entity_id) PK via span_id -> tree_node_spans mapping; chunk_entity_links never written."
  - "Split uncertainty semantics: commit exception preserves the issued recorder DML map (outcome_unknown); rollback OR primary-close unconfirmed after prior DML publishes EMPTY public maps and requires reconciliation."
  - "The current-version ownership inventory read must NOT FOR UPDATE before bridge locking; the bounded all-version node_entity_link_key = ANY(...) proof is the single authoritative ownership FOR UPDATE lock after bridge lock, avoiding the cross-version deadlock pattern."
  - "Legacy/manual/foreign mention and bridge rows are preserved and never claimed/rewritten/deleted; desired mention IDs colliding with manual/foreign rows are excluded from link derivation and caller-link validation so they cannot contribute E2b bridge/ledger rows."
  - "Schema-consistency review remediation: an explicit OTHER-version (non-current) E2b owner proof is schema-inconsistent/foreign for the current node (migration 003/020), so the repository fails closed: preserve bridge + ownership state, zero bridge/ledger DML, never insert a current-version ledger row."

requirements-completed: [R-OKF-01, R-OKF-06]

duration: "multi-round TDD (RED -> corrective RED/GREEN -> refactor -> round-4 -> review-finding corrective RED/GREEN) + coordinator review, all recorded below"
completed: 2026-08-08
---

# Phase 16: Plan 09 Summary

**E2b Materialization Repository + Failure Audit（local/static implementation COMPLETE；Phase 16 仍 OPEN/EXECUTING）**

## 状态边界（Status Boundaries）

- **16-09 local/static implementation COMPLETE**：`materialization_repository.py`、`failure_audit.py` 及两份 RED test 已按 frozen contract 实现并通过 TDD / coverage / review / final verification。
- **Phase 16 仍 OPEN/EXECUTING**。本文件仅为 16-09 completion；16-09 本身不执行任何后续 plan。**静态 Wave 3 已获人类授权**：下一 authorized 工作为 **16-10** 与 **bounded static 16-13 范围**（Task 1 default-blocked runner + Task 3 unauthorized/deferred branch）；真实 16-13 Task 2 RaNER smoke、live gates、PostgreSQL/Docker/ModelScope/model/network/C2 仍未授权。不宣称 Phase 16 closure。
- **纯 fake/spy 测试**：仅 spy cursor + fake primary/fresh-audit connection；**无 PostgreSQL、Docker、网络、ModelScope、模型加载/推理、RaNER inference、generative LLM、C2、commit/push**。
- **未提交**：全部 16-09 生产/测试/`__init__.py` 文件保持 uncommitted（commit/push 未授权）；本文件不宣称 git cleanliness。
- **无凭据**：未读取/打印/记录/持久化任何 credential value、connection URI、target、username 或 password；任何环境值均不写入本文件。

## TDD Evidence

所有 selector 均为纯两文件或聚焦 selector，使用完整 12-variable env-clean guards 与 `rtk proxy pytest`（launcher 在 `pytest` / `python -m pytest` / `rtk proxy pytest` 间变化，语义等价；变量名仅以守卫约束文字出现在 canonical selector，不在此复述）。

| Stage | Result | Detail |
|---|---|---|
| **Initial RED** | missing modules（`ModuleNotFoundError`） | `materialization_repository.py` 与 `failure_audit.py` 尚不存在，collection 阶段即失败。 |
| **Corrective RED rounds 1-2** | coordinator-reproduced failures（Round 1 7 failed / Round 2 7 failed，各独立记录） | 对 frozen 16-09 plan 违约的追加 corrective RED：fixed lock/load/preflight 顺序、contended stale ledger DELETE 先于 bridge DELETE、rogue/unprovable link fail-closed、non-model provenance、commit 不确定态保留 recorder map、document_versions scope 强制等。 |
| **Corrective GREEN（round 3）** | `47 passed` | 完成所有 reads/locks（含 bounded desired-ID mention read 与 all-version owner proof）先于首个 DML；split uncertainty semantics；collision/co-owned 分类。 |
| **Accepted behavior-preserving REFACTOR** | `47 passed`（coordinator 独立接受） | 移除未用 import、重写 module docstring、`_outcome_unknown` → `_commit_outcome_unknown`。后经 Black 机械格式化四文件；**Black 格式化后 AST 与格式化前完全等价**（未伪造未给出的 hash；当时冻结的 AST hashes 由协调器持有并确认 byte-identical），随后协调器修正两处 docstring-only 表述。 |
| **Round-4 RED** | `13 failed, 36 passed` | Task #187 source-verified 缺陷分类：**(1) UUID 归一化**（psycopg `uuid.UUID` identity 值在 document_versions/mentions/ledger/tree_node_spans/bridges/owner-proof 中需归一化为 canonical str，等价 rerun 为 true no-op）；**(2) deadlock-safe lock order**（current-version ownership inventory 不得 FOR UPDATE 先于 bridge locking；bounded all-version owner proof 是 bridge lock 后、DML 前的权威 FOR UPDATE lock）；**(3) collision link derivation**（manual/foreign collision mention 不得贡献 derived bridge/ledger）；**(4) ownership-safe mention conflict handling**（ON CONFLICT 不得 takeover 迟到 manual/foreign 行）；**(5) PostgreSQL NUMERIC equivalence**（Decimal vs finite float 语义相等、零 DML）；**(6) document-coordinate validation**（negative/equal/inverted/non-integer 在 preflight 前 fail）。 |
| **Round-4 GREEN + 对齐 obsolete ledger-lock assertion** | `49 passed` | 生产实现全部 7 项修正（row normalization、inventory 去 FOR UPDATE、collision 排除、co-owned projection 保留、mention conflict guard、postgres_values_equal、document-coordinate preflight）；随后将 legacy 测试中一条与 frozen deadlock-safe contract 直接矛盾的过时 ledger-lock 断言对齐（`WHERE version_id = %s` inventory 断言 `for update` NOT in），聚焦 selector 达 `49 passed`。 |
| **One-time Sonnet review** | **0 CRITICAL / 0 HIGH / 1 MEDIUM / 2 LOW** | MEDIUM：schema-unreachable 的 same-pair cross-version co-ownership 假设——migrations 003/020 证明 node/version ownership 一致性（tree_nodes.node_id 绑定一个 version；ownership trigger 强制 ownership version = node version），故合法 co-owned state 不可达。LOW：spy-only 的 ON CONFLICT guard 证明（无 live DB）与未来 runner Mapping/dict row-factory 集成。 |
| **Schema-consistency corrective RED** | `1 failed, 48 passed` | 仅 `test_other_version_owner_proof_is_schema_inconsistent_fails_closed` 失败：production 在 other-version-only/foreign owner proof 下尝试插入 current-version ownership ledger 并返回 changed，而 frozen contract 要求 fail-closed preserve、零 bridge/ledger DML、no_op。 |
| **Schema-consistency corrective GREEN（minimal production）** | `49 passed` | `_upsert_links` 中 other-version-only/foreign owner proof 现 fail closed：preserve bridge + ownership state、emit zero bridge/ledger DML、永不插入 current-version ledger row；current-only owner 行为不变；current+other defensive inconsistent 保留不变；unowned/manual preserve 不变。final `materialization_repository.py` SHA-256：`3831a725a8aa92c25f343f3fa7dc7bea7f27a45985c669f1dbc2b1a476c9d932`。 |

**Frozen test hashes / stable unchanged fingerprints（final production-only GREEN 后）：**

- `test_materialization_repository.py` — sha256 `a578b7598ad4a15a94d30bbb3c1d591e86c70aa1b140e1a2dd3b5d9c1b58815a`
- `failure_audit.py` — sha256 `1f9049e765549ed66db46731774b8691ec2c78ac10499f6285666f24f3946978`（coordinator 标注的疑似值未采用；以上为 verified 值）
- `test_failure_audit.py` — sha256 `6abd0f367343699806a4a7833c88a9a9823d02d8f745c86bdf71efaec567b4be`

## 最终验证（Independent Final Evidence，all fresh after the last production change）

- **Focused repository selector**：`49 passed in 1.13s`。
- **Repository + failure audit coverage**：`60 passed in 1.79s`；`failure_audit.py` **100%**、`materialization_repository.py` **95%**、combined **95%**。
- **Full pure entity suite**：`572 passed, 1 skipped in 6.49s`。
- **Black**：5 files unchanged。
- **Ruff**：all checks passed。
- **py_compile**：success（no output）。

## 实现 Contract

- **FULL desired-state reconciliation**：load existing E2b-owned mentions + current ledger + bounded tree_node_spans + bounded desired-ID mention read + bounded bridges + bounded all-version owner proof（全部先于 preflight/DML）；full preflight（含 D5 caller-link span proof）；stable ON CONFLICT upsert（equivalent rerun 零 DML）；ownership-scoped stale mention DELETE（同 scope 仅）；stale link-ownership DELETE（当前 version 仅）；bridge DELETE 仅当 owner proof 显示 current-version ownership 且无 other owner，否则 fail-closed preserve。
- **Lock order（deadlock-safe）**：`SELECT pg_advisory_xact_lock(hashtextextended(%s,0))` 使用 E2a 精确 key `okf:e2a:parent:{document_id}:{version_id}`（永不 `okf:e2b:parent`）→ `document_versions` FOR UPDATE → bounded row reads（mentions/tree_node_spans/bridges FOR UPDATE；**current-version ledger inventory 无 FOR UPDATE**）→ bounded all-version `node_entity_link_key = ANY(%s) FOR UPDATE` owner proof（bridge lock 后、DML 前、唯一权威 ownership lock）→ preflight → DML。
- **Row normalization**：repository 边界对所有 fetch 递归归一化 `uuid.UUID → canonical str`；document_versions scope 比较、mentions、ledger、tree_node_spans、bridges、owner-proof 均归一化。
- **PostgreSQL semantics**：`_rows_equal` 使用 `postgres_values_equal`（复用 `llamaindex_runtime/okf/_e2a_postgres_semantics.py`，未修改）；Decimal vs finite float NUMERIC 相等，零 DML。
- **Ownership safety**：manual/legacy/foreign mention/bridge 永不 claim/rewrite/delete；collision mention 排除于 link derivation 与 caller-link validation；mention ON CONFLICT 仅在 `entity_mentions.e2b_owner_scope = EXCLUDED.e2b_owner_scope` 时 UPDATE（TOCTOU-safe）。
- **Schema-inconsistent owner proof**：other-version-only/foreign owner proof fail closed（preserve bridge + ownership state，零 bridge/ledger DML，不插入 current-version ledger row）。
- **Failure audit**：auditable pre-commit failure 在 primary rollback+close 均确认后经 fresh connection 写一条 append-only `okf_e2b_failure_audit`（rollback_confirmed、redacted error_type）；commit exception → close + `outcome_unknown`（保留 recorder map）；cleanup uncertainty（rollback 或 close 未确认且已有 DML）→ 空 public map + `reconciliation_required=True`；`_E2bLinkProofError` → rollback+close + re-raise（无 audit）；durable non-corpus input → SQL 前 reject；`okf_rebuild_failure_audit` 永不写入；`chunk_entity_links` 永不写入。

## 审核与 Hardening（Review Findings）

- **One-time stable-implementation Sonnet review**：**0 CRITICAL / 0 HIGH / 1 MEDIUM / 2 LOW**。
- **MEDIUM（已修复）**：schema-unreachable same-pair cross-version co-ownership 假设。migrations 003/020 证明 node/version ownership 一致性（`tree_nodes.node_id` 绑定一个 version；`validate_okf_e2b_node_link_ownership_version` 拒绝 ownership version 与 node version 不同的行），故合法 co-owned state 不可达；frozen plan 要求 unclear/inconsistent ownership fail closed preserve，而非创建不可能的 co-ownership。correction：other-version-only/foreign owner proof fail closed。
- **LOW（记录，不阻塞）**：spy-only 的 ON CONFLICT guard 证明（无 live DB，运行时行为 deferred）与 runner Mapping/dict row-factory 集成（当前 fake cursor 用 dict；live runner 需在集成时接入 row factory）。
- **修复方式**：确认的 MEDIUM 经 strict corrective TDD（schema-consistency corrective RED → minimal production GREEN）与 fresh final gates 修复；**未运行第二次 broad review**（遵循不重复 review 相同内容的指示）。

## Deviations / Decisions / Limitations

- **Deviations**：无实现/契约 deviation；strict scope 各阶段仅允许编辑指定的生产或测试文件。一次 legacy 测试断言对齐（obsolete contradictory ledger-lock assertion）为测试契约修正，非生产行为变更。
- **Decisions**：all-version owner proof 为唯一权威 ownership FOR UPDATE lock；current-version ledger inventory 去 FOR UPDATE（deadlock-safe）；collision mention 排除于 link derivation；mention ON CONFLICT 增加 same-scope guard；other-version-only owner proof fail closed。
- **Limitations**：纯 fake/spy 测试，未 live 验证；**PostgreSQL ON CONFLICT runtime 行为与 runner dict_row 集成未在 live DB 证明**——不宣称 live-tested；`runtime_compatibility_id` 保持 `None`；无 real mirror smoke / C2。

## 文件清单（Files Created / Modified）

- `llamaindex_runtime/entity/materialization_repository.py`（new production）——desired-state reconciliation repository（final SHA-256 `3831a725a8aa92c25f343f3fa7dc7bea7f27a45985c669f1dbc2b1a476c9d932`）。
- `llamaindex_runtime/entity/failure_audit.py`（new production）——append-only fresh-connection failure-audit writer。
- `tests/llamaindex_runtime/entity/test_materialization_repository.py`（new RED test，frozen hash 见上）。
- `tests/llamaindex_runtime/entity/test_failure_audit.py`（new RED test，frozen hash 见上）。
- `llamaindex_runtime/entity/__init__.py`（additive modified）——facade exports。
- 本 SUMMARY 为唯一新建文档。全部文件保持 uncommitted（commit/push 未授权）。

## Boundary Compliance

- 无 DB/Docker/PostgreSQL/network/model download/live gate/C2/commit/push；每条 Bash 命令经完整 env-clean guards 运行；未读取/打印/持久化任何 credential value 或 connection URI。
- 纯 fake/spy：spy cursor 按 SQL 谓词过滤预置行（无法掩盖生产查询 bug），fake primary/audit connection 注入 rollback/commit/close 失败。
- 无 generative LLM / SQL DML（repository 经 spy 记录语句，不触 live execute 语义）；无 substring recovery。
- 测试断言冻结：RED 后生产-only GREEN；final production change 后聚焦 selector `49 passed`；两份测试 hash 在 final GREEN 后保持不变。

## Next Integration Notes

- `materialization_repository.py` 的 `reconcile_document` 供 16-10/16-13 消费；runner 集成需接入 Mapping/dict row-factory（LOW，deferred）。
- **PostgreSQL ON CONFLICT 运行时行为与 live gate 未证明**：separate authorized live gate 是唯一 live 验证点；本 plan 不宣称 live-tested。
- **Phase 16 仍 OPEN/EXECUTING**：16-09 本身不执行任何后续 plan；**静态 Wave 3 已获人类授权**，下一 authorized 静态工作为 **16-10** 与 **bounded static 16-13**（Task 1 default-blocked runner + Task 3 unauthorized/deferred branch）。真实 16-13 Task 2 RaNER smoke、live gates、PostgreSQL/Docker/ModelScope/model/network/C2 仍未授权、需独立人类授权。

---

*Phase: 16-raw-corpus-entity-layer*
*Plan: 09*
*Completed: 2026-08-08*
