# Phase 17 (交接书阶段 D): Graph Recall R3 + Four-Route Fusion — Boundary Document

**Drawn:** 2026-07-12（plan-everything-execute-nothing 指令下的预规划产物）
**Depth:** 边界级。进入 PLAN 时由 `/gsd-plan-phase 17` 细化——本文件即其输入。
**Authority:** 交接书 §11-D + 总纲三联用机制 + ADR T7 + 里程碑边界裁决 3/4 + 补充交接书 §4（coref 消费接口，2026-07-12）。

## Entry Gate

1. Phase 16 关闭；entity_mentions 与 node_entity_links 有全语料数据。
2. 用户明确放行执行。

## Goal

新增第四条检索路 R3（实体/图谱多跳召回：query→实体识别→entities/relations/entity_mentions 多跳→span 证据），并按 T7 只注入 `analysis/fusion.py::fuse_candidates`（RRF 路径），带来源标签与可观测分数。四路（R1 纯向量 / R2a 默认树 / R2b 热点 / R3 图谱）成为共享证据坐标上的并行可融合视图。

## In Scope

- R3 召回实现：查询侧实体识别通过 C1 同一 `EntityExtractor` adapter 的判别联合 `QueryTextInput` 变体调用，复用 label map、normalized-text Unicode code-point 坐标、失败语义和 provenance 输出契约；query 只带显式 query-local immutable `input_id/query_revision`，输出 `MentionCandidate.input_revision=query_revision`、`span_id=None`。query candidates 及 pre-merge/merger artifacts 严格 request-scoped，不得伪造 corpus document/sidecar projection，也不得写入 durable candidate audit、`entity_mentions`、`entity_merge_log`、alias、link 或 corpus-evidence store → 图谱 N 跳扩展（N 可配，默认 2）→ 经已持久化的 corpus entity_mentions 落到 span/chunk 证据坐标。
- **开关依赖矩阵（已冻结，fail-closed）**：合法组合仅 `(RAG_ROUTE_R3=off, RAG_ENTITY_EXTRACTOR=off|raner)` 与 `(RAG_ROUTE_R3=on, RAG_ENTITY_EXTRACTOR=raner)`。`R3=on + extractor=off` 必须在启动/配置校验阶段给出确定性错误，不能自动加载约 2.26 GB 模型、不能切换为纯词典/query-only fallback、不能在请求时才失败，也不能伪装成正常空路。
- R3 独立运行入口（可单独调用、单独观测——调试与 19 消融的前提）。
- fuse_candidates 注入：R3 作为新增来源路径进 RRF + multi-path bonus，`source` 标签可见（PLAN 时先 `gitnexus_impact` fuse_candidates 上游）。
- 跨路增强（总纲机制 2）：node_entity_links 为 R2b 热点选择提供实体信号的读取通道——但只读不改权重（见红线）。
- 开关：`RAG_ROUTE_R3=on|off`，默认 off 上线，验证后由用户决定默认值；它不自动控制 extractor。R3 启用的前置配置固定为 `RAG_ENTITY_EXTRACTOR=raner`，非法 `on/off` 组合按上面的配置矩阵 fail-closed。
- 观测：融合输出带 per-route 分数明细（为 19 消融铺数据面）。
- **（条件性，仅当 Phase 16 交付了 C2）coref 可选消费**（2026-07-12 补充）：R3 扩展时可将 coref_clusters 作为受限扩展信号（同簇 mention 视为局部同指），要求：(a) 走可解释路径——每次 coref 扩展在证据链上留簇 ID 与规则来源；(b) 计入既有跳数/扇出/候选预算，不另开预算；(c) 独立开关（消费开关独立于 `RAG_COREF_RESOLVER` 生成开关与 `RAG_ROUTE_R3` 路由开关）；(d) 低优先级——不阻塞 R3 主线交付。

## Out of Scope（红线，违者作废）

- `_compute_fusion_score` 固定权重（vector 0.40 / keyword 0.30 / rerank 0.20 / distribution 0.10，和为 1）不动——实体信号是否进热点加权由 Phase 19 消融矩阵决定（T7）。
- `_fuse_candidate_scores` **不存在于代码库**（ADR 核验）——任何计划/搜索引用该名称即无效。
- 不改 R1/R2a/R2b 自身行为；R3=off 时输出必须与 Phase 16 结束态逐位一致。
- 不做质量宣称（D4 仍冻结）；不调 PageIndex 配置。
- 不引入新存储（图查询走 PostgreSQL 递归 CTE 或应用层多跳，PLAN 时定，默认递归 CTE）。
- （coref 消费如实现）coref 链接不得产出无 span 证据的 QueryHit——所有经 coref 扩展的候选仍必须落到 canonical_spans 坐标；coref 消费开关 off 时行为与"无 coref 构建"逐位一致（该回归独立于 `RAG_ROUTE_R3=off` 的逐位一致性承诺，两者分别测试）。

## Deliverables（PLAN 时映射为 waves）

1. R3 召回模块（TDD；含多跳深度/扇出上限防爆炸参数）。
2. fuse_candidates 注入 + 来源标签 + per-route 观测输出。
3. 开关与 rollback 验证（`R3=off` 逐位一致性 + `R3=on/extractor=off` 启动配置 fail-closed 测试）。
4. 四路并行运行的集成冒烟（固定查询集跑通，只记录不评分）。
5. 17-VERIFICATION：R-OKF-05 goal-backward。

## Draft Acceptance Criteria

- R3 standalone 与 fused 两种运行方式在合法 `R3=on/extractor=raner` 配置下皆可用；fused 输出可追溯每条证据来自哪些路。
- 配置矩阵测试覆盖全部四种 `R3 on|off × extractor off|raner` 组合：三种合法组合按定义运行；`R3=on/extractor=off` 在启动/配置校验阶段确定性失败，且不自动加载模型、不降级词典、不产生任何 query 持久化副作用。
- `RAG_ROUTE_R3=off` 时全部既有检索测试逐位绿（含 p6 DNA 回归）。
- 多跳查询有上限保护（深度、节点扇出、超时），无界查询不可能发生。
- `_compute_fusion_score` 无 diff（grep/git 证明）。

## Key Files / Context Pointers

- `llamaindex_runtime/analysis/fusion.py:40::fuse_candidates`（唯一注入点，RRF + multi-path bonus）
- `llamaindex_runtime/tree/semantic_distribution.py::_compute_fusion_score`（只读禁区，写进计划的 non-goal）
- `llamaindex_runtime/tree/runtime.py`（四路编排落点，PLAN 时定注入层级）
- migrations 005/016（图数据面）

## Open Questions（进 PLAN 时必须先答）

1. R3 的证据粒度：直接返回 span 还是聚合到 chunk 再进融合？（需与 fuse_candidates 现有 candidate 形状对齐——PLAN 时读 fusion.py 全文定）
2. 查询侧实体识别失败（无实体命中）时 R3 的空路语义：静默空集 vs 显式 no-op 标记？（倾向显式标记，利于 19 消融统计）
3. 多跳边的方向语义如何用 relations.direction（017 migration 列）？
4. （2026-07-12 补充）coref 消费的注入点：在多跳扩展的种子层（query 实体→簇成员扩种）还是证据聚合层（同簇 span 合并计分）？（PLAN 时定，倾向种子层——可解释性更好）
5. （2026-07-12 补充，Phase 20 前向钩子）**corpus/scope 过滤参数**：本边界目前四路召回均无语料范围/权限过滤入参，而 Phase 20 要求权限/隔离在候选生成层强制。PLAN 时必须回答：R3 召回 SQL 与 fuse_candidates 候选形状是否预留 `scope`/`corpus_id` 类过滤参数（默认全量、无行为变化）？现在只留接口位，不实现权限逻辑——四路建成后再追加会贵得多。

## Risks

| 风险 | 缓解 |
|---|---|
| R3 噪声拉低融合质量 | 默认 off + 来源标签可单独降权/关停；质量裁决留给 19 |
| 多跳查询性能爆炸 | 深度/扇出/超时三重上限 + 递归 CTE LIMIT |
| 注入改坏 RRF 既有行为 | off 逐位一致性测试 + gitnexus_impact 前置 |
| coref 误链经 R3 扩散放大 | coref 消费独立开关默认 off + 可解释路径（簇 ID 入证据链）+ 共享候选预算；净收益 G3 裁决 |
