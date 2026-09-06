---
phase: 16-raw-corpus-entity-layer
plan: 10
subsystem: entity
tags: [entity-extractor, composition, dispatch, query-guard, request-scoped, hard-zero-persistence, lazy-gate, fail-closed, tdd, review]
type: tdd
wave: 3
macro_wave: W3
depends_on: [16-02, 16-06, 16-08]
requires:
  - phase: 16-02
    provides: Frozen CorpusSpanInput/QueryTextInput/ExtractionInput/MentionCandidate contracts and pure contract primitives.
  - phase: 16-06
    provides: Per-parent ModelScope RaNER adapter (extract_segment) with fast-tokenizer offset path and full candidate provenance.
  - phase: 16-08
    provides: Corpus-only dictionary/frontmatter supplement loaders and the pure immutable D3/D1 resolution engine.
provides:
  - EntityExtractor composition that dispatches corpus and query inputs through one shared pre-bound adapter/segmenter/merge/resolve pipeline and returns a plain list[MentionCandidate].
  - Query request-scoped hard-zero durable persistence surface: the extractor holds no cursor/connection/repository/DML capability.
  - Lazy build_entity_extractor registry gate: off builds nothing (proven by a raising spy), raner invokes the factory exactly once, unexpected values fail closed.
  - Zero generative-LLM baseline (R-OKF-04) enforced by static source guards and sys.modules import guards; pipeline behavior is exercised through injected pure fakes (no LLM spy).
affects: [16-13]
requirements: [R-OKF-04, R-OKF-06]

tech-stack:
  added: []
  patterns:
    - "Shared pre-bound orchestration: EntityExtractor(adapter, segmenter, merger, resolver, *, extractor_id, extractor_version, schema_version); injected seams are pre-configured callables that never receive invented model/version/authority parameters."
    - "Prevalidate the entire nonempty union before any seam work: non-Sequence / str / bytes / empty / non-ExtractionInput entries reject before any pipeline call."
    - "Corpus-only supplement: the frontmatter/dictionary supplement seam runs only for CorpusSpanInput; query inputs share the same adapter/segmenter/merge/resolve orchestration but never run supplements and never carry a frontmatter source."
    - "Merger then resolver: merged.selected feeds the resolver; returned candidates are a plain list of decision.candidate across (*resolved, *pending)."
    - "Query request-scoped hard-zero persistence: query-derived candidates and audit/merger artifacts expose no durable-write surface; the extractor holds no cursor/connection/repository."
    - "Lazy build_entity_extractor: 'off' returns None without calling the factory (proven by a raising spy); 'raner' calls the factory exactly once; any other value raises ValueError (fails closed)."

key-files:
  created:
    - llamaindex_runtime/entity/extractor.py
    - tests/llamaindex_runtime/entity/test_extractor.py  # created/frozen during RED
  modified:
    - llamaindex_runtime/entity/__init__.py  # additive facade exports only
  summary:
    - .planning/phases/16-raw-corpus-entity-layer/16-10-SUMMARY.md

key-decisions:
  - "Frozen contract overrides stale plan-action prose: extract returns a plain list[MentionCandidate] (never a tuple, never a public wrapper DTO); query request-scoped hard-zero persistence is a composition/API surface contract, not a mutable request-scoped wrapper."
  - "Injected seams are pre-bound/pre-configured callables typed object; the extractor never validates callability and never invents model/tokenizer/merger_version/authority parameters."
  - "Registry gate fails closed on unexpected switch values; the default-off path builds nothing and pulls in no heavy dependency."
  - "The frozen test file was intentionally frozen byte-for-byte after an earlier Black check reported it would reformat; it is excluded from the final Black gate but covered by Ruff and py_compile (documented non-behavioral formatting limitation)."

requirements-completed: [R-OKF-04, R-OKF-06]

duration: "test-contract hardening -> final accepted RED -> minimal GREEN -> behavior-preserving REFACTOR -> comment-only cleanup + one-time Sonnet broad review (0 CRITICAL / 0 HIGH / 0 MEDIUM / 5 LOW, APPROVE, no second review)"
completed: 2026-08-08
---

# Phase 16: Plan 10 Summary

**EntityExtractor 组合 + Query hard-zero-persistence guard（local/static implementation COMPLETE；Phase 16 仍 OPEN/EXECUTING）**

## 状态边界（Status Boundaries）

- **16-10 local/static implementation COMPLETE**：`extractor.py`、`entity/__init__.py` 增量导出、RED test 已按 frozen contract 实现并通过 TDD / coverage / review / final verification。
- **Phase 16 仍 OPEN/EXECUTING**。本文件仅为 16-10 completion；不宣称 Phase 16 closure。**静态 Wave 3 已获人类授权**：下一 authorized 静态工作为 **bounded static 16-13 Task 1 + Task 3**；真实 16-13 Task 2 RaNER smoke、live gates、PostgreSQL/Docker/ModelScope/model/network/C2 仍为 blocked_not_executed / unapproved。
- **纯注入 fake**：仅 fake adapter/segmenter/merger/resolver + spy；**无 real RaNER model loading/inference、无 mirror/smoke、无 live persistence 执行、无 ModelScope 访问、无 DB/Docker/network、无 generative LLM、无 C2、无 commit/push**。
- **未提交**：全部 16-10 生产/测试/`__init__.py` 文件保持 uncommitted（commit/push 未授权）；**仓库存在 pre-existing 不相关 dirty/untracked 状态，不宣称 git cleanliness**。
- **无凭据**：未读取/打印/记录/持久化任何 credential value、connection URI 或 token；任何环境值均不写入本文件。

## TDD Evidence

所有 selector 均为聚焦 selector，使用完整 12-variable env-clean guards 与 `rtk`（launcher 在 `pytest` / `python -m pytest` / `rtk proxy pytest` 间变化，语义等价；变量名仅以守卫约束文字出现在 canonical selector，不在此复述）。

| Stage | Result | Detail |
|---|---|---|
| **Final accepted RED** | extractor 缺失；coordinator RED = collection `ModuleNotFoundError`，**1 error in 1.42s** | `tests/llamaindex_runtime/entity/test_extractor.py`（766 lines）在 `extractor.py` 不存在时 collection 即失败；无生产文件被写入。 |
| **Minimal GREEN** | agent = `19 passed in 1.23s`；coordinator independent GREEN = `19 passed in 1.13s` | 最小实现满足 frozen contract：plain-list 返回、prevalidate 整个非空 union、共享 pre-bound corpus/query 编排、corpus-only supplement、merger→resolver、lazy gate。 |
| **Accepted behavior-preserving REFACTOR** | agent = `19 passed in 2.39s`；coordinator independent = `19 passed in 1.36s` | 将 final result loop 改为 list comprehension；随后一次 comment-only cleanup（无 executable 变更），agent = `19 passed in 1.09s`。断言在 GREEN 与 REFACTOR 之间未改动。 |

**Frozen test hash（RED 阶段冻结，此后未改动）：**

- `test_extractor.py` — sha256 `38d86138c7582ea613f62aab50230bc2e4e44a845dd0e8d358c5867dbd902836`（766 lines）

## 最终验证（Independent Final Evidence，all fresh after the last change）

- **Focused selector**：`19 passed in 0.94s`。
- **Coverage**：`19 passed in 1.47s`；`extractor.py` **93%**（45 statements, 3 missed；80% threshold met）。
- **Full pure entity suite**：`591 passed, 1 skipped in 6.42s`。
- **Black**：two production files = `2 unchanged`。
- **Ruff**：production + frozen test = all checks passed。
- **py_compile**：production + frozen test = success（no output）。
- **明确限制**：frozen test file **未纳入最终 Black gate**——更早一次 Black 检查报告它会 reformat，且其已接受 byte hash 被有意冻结；Ruff 与 py_compile 覆盖了它。此为一处已记录的 non-behavioral formatting limitation；**不宣称三个文件均 Black-clean**。

## 实现 Contract

- **`extract(inputs: Sequence[ExtractionInput]) -> list[MentionCandidate]`**：公共返回为 plain `list`，永不 tuple、永无公共 wrapper DTO。
- **Prevalidate 整个非空 union**：任何 seam 工作前拒绝非 Sequence / str / bytes / 空 / 非 ExtractionInput 条目。
- **共享 pre-bound corpus/query 编排**：单一 adapter factory（per-input）+ 单一 union segmenter dispatcher + merge + resolve；注入 seams 为 pre-configured callables，extractor 从不 invent model/tokenizer/version/authority 参数。
- **Corpus-only supplement**：frontmatter/dictionary supplement seam 仅对 `CorpusSpanInput` 运行；query input 永不运行 supplement、结果永不携带 frontmatter source。
- **Merger 然后 Resolver**：`merged.selected` 进 resolver，返回 `[decision.candidate for decision in (*resolution.resolved, *resolution.pending)]`。
- **Query request-scoped hard-zero durable persistence surface**：extractor 持有零 cursor/connection/repository/DML capability；query-derived candidates 与 audit/merger artifacts 无 durable-write surface。
- **Lazy `build_entity_extractor`**：`off` 不调用 factory 直接返回 None（raising spy 证明）；`raner` 恰好一次调用 factory；任何其他值 `ValueError` fail closed。
- **零 generative-LLM / 零 heavy import**：无 config/heavy/model/network/DB/persistence/generative-LLM import 或 call；source guards + `sys.modules` import guard 通过（no modelscope/torch/jieba/sentencepiece）。
- **Additive package export only**：`entity/__init__.py` 仅追加导出 `EntityExtractor` 与 `build_entity_extractor`，未移除任何既有符号。

## 审核与 Hardening（Review Findings）

- **One-time Sonnet broad review**：**0 CRITICAL / 0 HIGH / 0 MEDIUM / 5 LOW；verdict APPROVE**；**未运行第二次 review**。
- **LOW（非阻塞，仅记录，未修复）**：
  1. injected seams 类型为 `object`，构造器无 callable 校验；
  2. unexpected build switch fail-closed 分支缺少 frozen regression test；
  3. determinism test 复用单个 stateful harness，而非每例 fresh harnesses；
  4. fake segmenter 仅覆盖恰好一个 segment，未覆盖 zero/multiple segments；
  5. 16-10-PLAN action prose 仍含 stale tuple/request-scoped-wrapper 措辞，而 objective/must-have/frozen override 与实现正确使用 plain list。
- **明确**：以上 LOW 均未被修复；本 summary 仅如实记录。

## Deviations / Decisions / Limitations

- **Deviations**：无实现/契约 deviation；唯一注意点为 plan action prose 中 stale tuple/wrapper 措辞被 objective/must-have/frozen override 取代，实现与 frozen contract 一致。
- **Decisions**：plain list 公共返回；lazy gate `off`/`raner`/fail-closed；pre-bound seams；corpus-only supplement；frozen test 字节级冻结并排除于最终 Black gate（已记录）。
- **Limitations**：纯注入 fake，无 live 验证；**query hard-zero 为 composition/API surface contract，非 live DB 测试**；无 real RaNER loading/inference、无 ModelScope 访问、无 mirror/smoke；无 credentials 读取/打印/持久化。

## 文件清单（Files Created / Modified）

- `llamaindex_runtime/entity/extractor.py`（created，132 lines，SHA-256 `911ac6a74f3713af0650c450c64740acbb37710e86e30ed2925f32c496b26979`）。
- `llamaindex_runtime/entity/__init__.py`（modified，additive exports，107 lines，SHA-256 `8a6b04008c02d19600b983a839971c6e0cb0e6c290c65c65667610d7013fea63`）。
- `tests/llamaindex_runtime/entity/test_extractor.py`（created/frozen during RED，766 lines，SHA-256 `38d86138c7582ea613f62aab50230bc2e4e44a845dd0e8d358c5867dbd902836`）。
- 本 SUMMARY 为唯一新建文档。全部文件保持 uncommitted；**仓库存在 pre-existing 不相关 dirty/untracked 状态，不宣称 git cleanliness**。

## Boundary Compliance

- 无 DB/Docker/PostgreSQL/network/model download/live gate/C2/commit/push；每条 Bash 命令经完整 12-variable env-clean guards + `rtk` 运行；未读取/打印/持久化任何 credential value 或 connection URI。
- 纯注入 fake/spy：无 real RaNER model、无 live persistence 执行；无 generative LLM references/imports；无 heavy imports；source/import guards 通过。

## Next Integration Notes

- **Phase 16 仍 OPEN/EXECUTING**：本文件仅为 16-10 completion；不宣称 Phase 16 closure。**静态 Wave 3 已获人类授权**：下一 authorized 静态工作为 **bounded static 16-13 Task 1 + Task 3**；**16-13 Task 2 / live gates 仍 blocked_not_executed / unapproved**，需独立人类授权。
- **requirements-completed**：R-OKF-04（enabled baseline zero generative-LLM）、R-OKF-06（`extract` plain-list contract + query hard-zero）。
- `EntityExtractor` / `build_entity_extractor` 供 16-13 runner 消费；live persistence 与真实 RaNER 集成仍需独立 authorized gate。

---

*Phase: 16-raw-corpus-entity-layer*
*Plan: 10*
*Completed: 2026-08-08*
