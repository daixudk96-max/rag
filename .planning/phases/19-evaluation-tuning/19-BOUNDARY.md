# Phase 19 (交接书阶段 F): Evaluation & Tuning — Boundary Document

**Drawn:** 2026-07-12（plan-everything-execute-nothing 指令下的预规划产物）
**Depth:** 边界级。进入 PLAN 时由 `/gsd-plan-phase 19` 细化——本文件即其输入。
**Authority:** 交接书 §11-F + 总纲 D4 + ADR T7（权重裁决权在此）+ 里程碑边界裁决 6/10 + 补充交接书 §4/§5（八类题集、消融阶梯、G3/G4/G5，2026-07-12）。
**双重门：** 本阶段除了依赖 18 关闭，还需用户**明确解冻 D4**（用户原话："这个诊断再说吧，后续怎么提高再说，我们先把功能的计划实现。"——解冻权在用户）。

## Entry Gate

1. Phase 18 关闭（全功能面就绪：四路检索 + 回写闭环）。
2. 用户明确解除 D4 冻结并放行执行。

## Goal

对完整的四路 + OKF 体系做诚实的质量评估与调优：消融矩阵（每路开/关、融合变体、节点摘要开关、实体信号进热点加权与否）、匹配的人工判定收集、对照冻结阈值（hit_rate ≥0.80 / top1_relevance ≥0.90 / stability ≥0.85）做 Level 评估。所有 14-18 期间被禁止的"调质量"动作在此集中裁决。

## In Scope

- 消融矩阵设计与运行：R1/R2a/R2b/R3 的 2^4 子集中有意义的组合 + 关键开关维度（`if_add_node_summary`、实体信号进 `_compute_fusion_score` 与否——T7 遗留裁决在此了结）。
- 匹配判定收集：同语料、同查询集、同 hits 的人工判定（Phase 4/10 的教训是里程碑级红线：**绝不复用错配标签**——判定必须对本轮 hits 收集）。
- 指标计算与 Level 评估（复用 verification/ 既有管线：judgment_template、quality_metrics、level_assessment 产物链）。
- 权重调整决策：若消融显示实体信号应进热点加权，在此阶段实施并重新归一（权重和=1 约束保持）。
- Level 2 基线的最终对照：v2.0 全体系 vs Phase 8 权威基线（hit_rate 0.70 / top1 0.59 / stability 0.65）。
- **源头级题集分层（2026-07-12 补充）**：查询集扩充按 DOCX 八类中文难点组织——全称-简称、同名消歧、显式指代、零指代、否定、条件/例外、跨章节/跨文档多跳、不可回答；主指标 **All-Evidence Recall**（一题所有必要证据 span 全召回才计通过），与既有 hit_rate/top1/stability 并行报告。
- **消融阶梯（2026-07-12 补充）**：按 DOCX 顺序 A 基线 → B 实体倒排 → C KU 多索引 → D 归一化 → E 指代（16-C2）→ F 语义边 → G 高价值 qualifiers（如已存在），每级只开一个增量；与四路 2^4 矩阵互补，不互相替代。
- **三个专项裁决门（2026-07-12 补充）**：
  - **G3 指代净收益门**：16-C2 在显式指代/零指代两类题上的收益 vs 误链风险与维护成本 → 裁决"默认开启 / 保持关闭 / 移除"（R-OKF-09 的裁决地）；
  - **G4 动态多跳门**：R3 跳数/预算是否需要 query 自适应策略；
  - **G5 试点价值门**：面向业务的价值评估，产出交 Phase 20 G6 作 Go/No-Go 输入。

## Out of Scope

- 新功能开发（发现功能缺陷记 backlog，重大者走 roadmap evolution 立新 phase）。
- 无消融证据的参数改动（"感觉更好"不是依据——不伪造最优权重，T7 原则）。
- 用不匹配判定做任何 Level 宣称。
- **试点部署与权限/隔离实现（里程碑边界裁决 10）**：19 只产出评测与 G3/G4/G5 裁决——G5 是评估产物不是部署动作；任何试点上线、权限强制、运维建设属 Phase 20，且 19 通过不自动构成 20 的试点授权。

## Deliverables（PLAN 时映射为 waves）

1. 消融矩阵规格（组合清单 + 固定查询集 + 运行脚本）。
2. 矩阵运行产物（per-combination 检索结果，进 verification/ 新目录，不覆盖历史）。
3. 匹配人工判定（模板生成 → 用户判定 → 完整性门）。
4. 指标 + Level 评估 + 调优决策记录（每个权重/开关变化附消融证据引用）。
5. G3/G4/G5 裁决记录（每门一份带证据引用的裁决文档；G5 产物显式标注"供 Phase 20 G6 使用"）。
6. 19-VERIFICATION + 里程碑收尾评估（v2.0 是否达成 R-OKF-01..09 总检；R-OKF-10 属 Phase 20）。

## Draft Acceptance Criteria

- 每个调优决策可追溯到具体消融对比数据。
- 判定完整性门通过（判定行与 hits 行 100% 匹配——Phase 8 的 matched validation 标准）。
- Level 评估基于有效匹配判定；若未达 Level 3/4，如实记录并给出瓶颈归因（此时才允许质量归因）。
- 权重变化后 `_compute_fusion_score` 权重和仍为 1（回归测试）。

## Key Files / Context Pointers

- `verification/` 既有评估管线（judgment/quality_metrics/level_assessment 产物链，Phase 8 形态为准）
- `llamaindex_runtime/tree/semantic_distribution.py::_compute_fusion_score`（本阶段唯一允许动权重的地方）
- `llamaindex_runtime/analysis/fusion.py::fuse_candidates`（per-route 观测数据来自 17）
- 冻结阈值定义（STATE.md：hit_rate ≥0.80 / top1 ≥0.90 / stability ≥0.85 / tree_depth ≥3 / node_chunk_mapping ≥0.80 / heading_path ≥0.95）

## Open Questions（进 PLAN 时必须先答）

1. 消融矩阵规模控制：全组合 vs 关键子集？（判定成本随组合数线性涨——需要用户对判定工作量表态）
2. 查询集：沿用 Phase 8 的 20 查询还是扩充覆盖实体型查询？（R3 的价值不体现在旧查询集上——倾向扩充，需用户认可新集；八类分层题集即扩充方案的组织框架）
3. Level 门是否对"四路全开"单一配置评，还是对最优消融组合评？
4. （2026-07-12 补充）All-Evidence Recall 的"必要证据 span 集合"标注方式：随题集人工标注还是判定阶段回溯标注？（影响判定工作量与模板设计）
5. （2026-07-12 补充）八类题集与既有 95 题/20 查询集的关系：并集扩充还是重新构建？（Phase 4/10 错配教训——新题集必须配新判定）

## Risks

| 风险 | 缓解 |
|---|---|
| 判定工作量超预期 | 矩阵子集化 + 分批判定；先跑自动指标筛掉明显劣势组合 |
| 错配标签复用惯性 | 完整性门 fail-closed（Phase 5 已实现的机制沿用） |
| 调优过拟合固定查询集 | stability 指标 + 查询集扩充；结论标注适用范围 |
