# v2.0 规划缺口补充交接书：中文指代链与试点生产化

> **状态：PLANNING-ONLY / HANDOFF INPUT — 禁止执行。**
>
> 本文只授权接手会话补齐、校准和交叉链接 `.planning/` 中的规划文档；它**不授权**修改运行时代码、SQL migration、测试、配置、数据库、OKF bundle，也不授权 commit/push。
>
> **补充定位：** 这是对已确认的两处计划归属缺口的接口说明，不替代或重写既有权威链。它不改变 D1–D8、ADR T1–T9、Phase 14–19 的既定边界。发生冲突时，以本文第 2 节的优先级链为准。
>
> **待关闭的缺口：**
> 1. 中文跨句指代、主体继承和 `coref_clusters` 尚未被明确分配到可执行的 v2.0 阶段；
> 2. 源路线图的阶段 6（试点、运维、权限、监控、灰度、回滚、生产 Go/No-Go）尚未被明确分配到 v2.0 阶段。

---

## 1. 本次交接的唯一目标与完成定义

接手会话必须把下面两个能力写入现有计划权威链，使其具有明确的**所有者、前置条件、输入/输出契约、功能验收、评估门、回退路径和后续消费者**。

| 工作包 | 推荐归属 | 计划完成时必须清楚回答的问题 |
|---|---|---|
| **C2：中文指代链** | **Phase 16（阶段 C）的条件性第二 wave，记为 16-C2）** | 哪些 mention 可被归成同一局部指代链？它们如何保留原文证据、置信度和可重建性？Phase 17 如何在开关开启时消费它，而不把错误指代扩散为实体合并？ |
| **G：受限业务试点与生产就绪** | **新增 Phase 20（阶段 G），紧接在 Phase 19 之后** | 在一个受控业务知识库中，四路检索、OKF 更新、权限、隔离、可观测性、灰度与回退如何安全运行？谁有权作生产 Go/No-Go？ |

### 完成定义（仅指规划完成，不是实现完成）

完成本交接后，必须同时满足：

1. `coref_clusters` 不再仅写作“C 后按需插入”；它明确属于 **Phase 16-C2 的条件性 wave**，且 Phase 17 对它的可选消费边界已写明。16-C2 可规划、可实现为默认关闭的功能，但只有 Phase 19 在 D4 解冻后以 G3 证据确认净收益，才可建议把它纳入默认路径。
2. Phase 19 具有来源路线图要求的评估输入、指代/多跳相关的消融位置，以及 G3/G4/G5 的裁决语义；**D4 冻结仍然有效**。
3. 新增 Phase 20 边界文档，且 `ROADMAP.md`、v2.0 milestone、主交接书都能定位它。
4. `LOW-TOKEN-GRAPHRAG-UPGRADE-PLAN.md` 保留为 DOCX 详细来源；只添加 reconciliation 注记，不删除或改写它的原始研究细节。
5. 文档明确写出：本补充没有批准任何代码实施，也没有把用户的“先规划、后执行”要求改成可自动开始。

---

## 2. 必读权威链与冲突裁决

接手会话先读，且不得只读其中一份：

1. `.planning/OKF-MULTIROUTE-EXECUTION-HANDOFF-2026-07-12.md` — D1–D8、A–F 阶段、T1–T9 前的已验证事实与全局边界；
2. `.planning/UNIFIED-MULTIROUTE-OKF-PLAN.md` — 架构总纲；
3. `.planning/ADR-OKF-PHASE-A-TECH-DECISIONS-2026-07-12.md` — 已定稿的 T1–T9；
4. `.planning/v2.0-MILESTONE-OKF-MULTIROUTE.md` — R-OKF 登记、Phase 14–19 和跨阶段流；
5. `.planning/LOW-TOKEN-GRAPHRAG-UPGRADE-PLAN.md` — 中文低 Token DOCX 的详细来源映射；
6. `.planning/phases/16-raw-corpus-entity-layer/16-BOUNDARY.md`；
7. `.planning/phases/17-graph-recall-multiroute-fusion/17-BOUNDARY.md`；
8. `.planning/phases/19-evaluation-tuning/19-BOUNDARY.md`；
9. `.planning/ROADMAP.md` 的 Phase 16–19 定义。

### 冲突优先级

1. 已获用户确认的 D1–D8；
2. ADR T1–T9；
3. 主交接书；
4. 本补充交接书；
5. 里程碑、Roadmap、阶段边界文档；
6. 低 Token 研究映射文档中的历史 WS0–WS4 表述。

`LOW-TOKEN-GRAPHRAG-UPGRADE-PLAN.md` 是**必须保留的源级细节**，但其中下列历史性技术表述不得重新成为实施依据：

- `_fuse_candidate_scores` 不是仓库符号；有效的 R3 注入点只有 `llamaindex_runtime/analysis/fusion.py::fuse_candidates`（ADR T7）；
- 其中的 `migration 017/018` 是旧的逻辑工作包编号，不能越过 ADR T5 指定的实际迁移序列；新 migration 必须从当时实际的下一个未占用号码续编；
- WS0–WS4 的质量门不能绕过 D4。质量、消融、300–500 题扩建和任何“净收益”宣称只能在 Phase 19 解冻后进行。

---

## 3. 不可变约束（两项工作都必须继承）

### 3.1 体系与数据边界

- **D1/D2：** OKF 是唯一持久知识 SSOT；PostgreSQL 是从 OKF 和其可追溯输入重建的派生层。`raw/` 与相邻 span sidecar 仍是证据身份来源。
- **D3：** 实体层不能抢跑 OKF 基础设施；16-C2 只能在 Phase 15 与 Phase 16-C1 的实体 mention 契约可用后执行。
- **D4：** 在 14–18 阶段只允许功能正确性与回归测试；不能以命中率、All-Evidence Recall、P95、质量提升为由提前调参、开放功能或作生产声明。
- **D5/D6/T7：** R3 只能接入 `analysis/fusion.py::fuse_candidates` 的 RRF 路径。不得动 `_compute_fusion_score` 的固定热点权重；它的任何重分配留在 Phase 19。
- **D7：** 入库默认不使用全量生成式 LLM 三元组、指代或关系抽取。规则、词典、jieba、以及可选的本地非生成式模型才是允许的升级路径。
- **D8/T8：** 任何由检索或试点发现的知识修订只能走 Phase 18 proposal/staging + 人审流程。没有 Agent 自动 merge、自动 Git commit 或对 `raw/`/sidecar 的写权限。

### 3.2 当前冻结内容

- `relation_mentions` 仍遵从 ADR T6：它是 C 后按需能力，**不是**本次将 `coref_clusters` 分配给 16-C2 的隐式授权。
- Neo4j 或其他新图数据库仍不在 MVP 范围；多跳继续以 PostgreSQL 派生数据和受限递归 CTE 为方向。
- 指代链、R3 和生产试点都不得被描述为“已实现”或“已启用”。
- 既有脏工作区不属于本交接范围；不做 `git add -A`，不撤销或混入既有改动。

---

## 4. 工作包 A：Phase 16-C2 中文指代链 / `coref_clusters`

### 4.1 归属和顺序

将 Phase 16 明确拆成两个顺序 wave：

```text
16-C1  非生成式实体抽取、别名归一、entity_mentions、node_entity_links
  ↓（mention 契约、实体 provenance 和开关已存在）
16-C2  条件性中文局部指代链、主体继承、coref_clusters；功能默认关闭
  ↓（只在 D4 解冻后的 Phase 19 通过 G3 才建议进入默认路径）
17-D   R3 读取 entity links；只有开关开启时才可将 coref 作为受限扩展信号
```

- 16-C2 是 Phase 16 的**条件性**必规划组成，不另起并打乱当前 14–19 编号的独立阶段；是否实施该 wave 由明确触发决策和用户执行授权决定，是否纳入默认路径由 G3 决定。
- **16-C2 子入口门：** 16-C1 的 `entity_mentions`、provenance、默认关闭开关与必要的 `node_entity_links` 已关闭验收；并已为未来 G3 建立、版本化但尚未运行评分的指代/零指代查询子集及人工标注 schema。该准备工作不是 D4 质量评估，不能声明召回增益或决定功能默认值。
- Phase 17 的核心实体路线不得依赖指代功能一定开启；R3 在 coref 开关关闭时必须仍能依据 `entity_mentions`、`node_entity_links` 和确定性实体边工作。
- 只有 Phase 19 的匹配评估能决定 coref 是否产生净收益、能否从默认关闭转为默认开启；此前的 16-C2 验收只证明契约、安全边界和可重复性。

### 4.2 解决范围

16-C2 需要规划下列**局部、保守、可解释**的中文现象：

1. 段落/局部章节的主体继承；
2. 显式描述性指代，例如“该院”“该委员会”“上述单位”“本项目”“其”；
3. 在严格窗口和明确候选存在时才允许的零主语延续；
4. 每条指代连接的原始 mention、span、规则/模型来源、候选、置信度和局部文本证据；
5. 失败或歧义时保持未链接，而不是猜测性合并。

### 4.3 明确非目标

16-C2 不得被扩展为：

- 跨文档的开放式实体同一化；
- 对 `entity_aliases`、`entity_merge_log` 或 canonical entity 的自动破坏性改写；
- 全量关系抽取、全量三元组、`relation_mentions` 落库，或用指代功能偷渡关系建模；
- LLM 驱动的全库指代解析；
- 质量调参、默认开启、All-Evidence Recall 宣称或与基线的性能比较；
- 对 Phase 14/15 serializer、sidecar 或 `NormalizationContract` 的顺手改造。

### 4.4 数据与接口契约（计划时必须定稿）

接手会话应在 Phase 16 的 future atomic PLAN 中要求以下最小契约，并在实施前由 migration/设计 ADR 定稿：

| 契约项 | 必须具备的内容 | 目的 |
|---|---|---|
| 输入 | `entity_mentions` 的 `mention_id`、`entity_id`（允许未归一候选时为空/待决）、`span_id`、字符坐标、原始 mention 文本、source、confidence；字符坐标继承 C1 的 exact normalized span / Python Unicode code-point 半开区间契约，并保留 document revision、normalization/segmentation 版本及可解析的 sidecar/raw 证据投影；C2 不得把 token offset 当字符坐标，也不得从格式化 Markdown 或 substring search 猜回边界 | 不能从格式化 Markdown 猜回证据边界，也不能在 C2 重新解释 C1 坐标 |
| cluster 主记录 | `cluster_id`、文档/版本作用域、可为空的 `anchor_entity_id`、resolver 名称与版本、cluster confidence、创建/重建 provenance | 指代簇可重建、可定位、不会无意跨版本污染 |
| membership 记录 | 推荐规范化 `coref_cluster_mentions(cluster_id, mention_id, role, confidence, evidence)`；禁止只用不可查询的 `mention_ids` JSON/数组作为唯一关系 | 支持索引、审计、局部重建和 R3 受限消费 |
| 删除/回退 | cluster 及 membership 采用可审计的 per-cluster tombstone/soft-delete + 可重派生语义；不得通过破坏性 DELETE 或 entity merge 回滚来处理单一错误指代链 | 错误 cluster 不会孤立 mention，也不会污染 canonical entity |
| 证据 | 所有成员都可反查至 `span_id` 和字符级原文；规则/模型所依据的局部窗口必须可解释 | 防止“看似同一实体”但无法验证 |
| 可重建性 | 结果只能由 OKF raw/span sidecar、版本化词典/人工声明、resolver 版本和确定性配置重建；DB 不得保存唯一事实 | 继承 D1 |
| 开关 | C2 初期只支持 `RAG_COREF_RESOLVER=off|rules`，默认 `off`；如保留 `RAG_COREF_MODEL` 配置占位，其首期唯一合法值为 `off`。任何模型值必须先完成精确 checkpoint、许可、输出契约、fixture 与离线部署审查 | 规则路径零生成式 token、零新增模型依赖；未冻结模型不得通过配置面伪装成已支持能力 |

**迁移顺序约束：** Phase 16-C1 的既有边界文件已预留“必要时 migration 018 起”给 `node_entity_links`。16-C2 不得复用或抢占 C1 的 migration；若 C1 实际使用 `018_*`，**16-C2 预期以单一 `019_*` migration 同时建立 `coref_clusters` 及其规范化 membership 表**。若前置 Phase 实际占用该号码，仍须按 ADR T5 使用当时下一个连续空闲编号，但必须保持“C1 schema 先于 C2 schema”的顺序并在 atomic PLAN 中记录最终编号。`relation_mentions` 仍不是 16-C2 的隐含迁移目标。

**关键语义：** 指代簇是“文本 mention 之间的局部证据连接”，不是“这些 canonical entity 已被永久合并”的证明。`anchor_entity_id` 只在存在高置信人工声明或满足既有 EntityResolver 高阈值时使用；歧义候选保持未决或没有 anchor。

### 4.5 算法与安全边界

规划必须以如下保守顺序约束实现：

```text
规则优先（段落主体 → 显式指代表 → 有界零主语）
  → 低置信或冲突结果不写连接
  → 仅把已保存、带证据的连接提供给 R3
```

模型辅助只保留未来扩展位，不属于 C2 初期交付；不得因 C1 使用 RaNER 或历史候选中出现 HanLP 而推导出 coreference 模型已经冻结。

必须写入未来 PLAN 的约束：

- 默认仅在同一文档版本、受限段落/章节窗口中解析；任何跨文档能力另立 roadmap evolution。
- 每类规则须有允许、拒绝和歧义 fixture；例如“该院”“其”“上述单位”、同名机构、跨章节断开、否定或条件语句、无法确认的零主语。
- 用户/人工在 OKF 中声明的实体信息可作为高置信 anchor，但不得把机器推断回写为人工知识。
- resolver 重跑必须幂等；文档版本删除/重建不得留下孤儿 membership 或旧版本 cluster。
- 如未来引入本地模型，必须先单独冻结精确模型 artifact，并记录模型/规则版本、许可、输出契约、Windows/WSL 可行性、执行成本和 source label；模型输出不得伪装成确定事实。规则路径是初期唯一实现基线，默认零生成式 token、零新增模型依赖。

### 4.6 与 Phase 17 的接口

Phase 17 文档应补充以下消费规则：

1. R3 默认只使用实体-证据确定性边；coref 只能作为**可关闭的、低优先级、有预算的扩展信号**。
2. coref expansion 必须保留“经由哪个 cluster、从哪个 mention、位于哪个 span”的路径解释。
3. 不允许 coref 单独创造无原始 evidence span 的 QueryHit；最终候选仍必须是可引用的 canonical span/chunk。
4. `RAG_COREF_RESOLVER=off` 时，R3 的基础实体路径必须与无 coref 数据状态一致；这与 `RAG_ROUTE_R3=off` 是**两个独立开关**。后者的“R1/R2a/R2b 输出逐位一致”回归承诺仅适用于关闭整个 R3 路由，不能被误读为 coref 开关的承诺。coref 仅改变已启用 R3 的受限图遍历候选，且必须可观测为独立维度。
5. coref 不改变 T7：R3 最终只在 `fuse_candidates` 作为来源路接入，且不得触碰热点固定权重。

### 4.7 两级验收门与回退

| 门 | 所在阶段 | 允许验证的内容 | 失败处理 |
|---|---|---|---|
| **C2 功能就绪** | Phase 16 | schema/删除语义、provenance、幂等重建、规则 fixture、默认 off、零 LLM 调用、禁用时回归不变；它不裁决是否默认启用 | 保持 feature off；关闭模型补充；仅保留 C1 实体倒排能力 |
| **G3 指代净收益裁决** | Phase 19，且 D4 已由用户解冻 | 匹配人工标注的指代类别、All-Evidence Recall、误连接、延迟/成本；与无 coref 的相同预算对照 | 不默认启用 coref；回退为仅实体/KU 确定性边；记录失败类型，不以调参绕过证据 |

Phase 16 不得自行把“fixture 正确”叙述成“指代提高召回”。Phase 19 之前没有任何 G3 通过声明。

---

## 5. 工作包 B：新增 Phase 20（阶段 G）受限业务试点与生产就绪

### 5.1 归属、入口与裁决顺序

新增：

```text
Phase 19（F）：D4 解冻后的评估、消融、架构取舍
  ↓ G5：试点价值是否成立（质量/成本/延迟/维护的证据）
Phase 20（G）：单一受控业务库试点、运行安全、运维与 Go/No-Go
  ↓ G6：由业务与技术负责人明确批准或拒绝扩大范围
```

Phase 20 的入口必须同时具备**三重门**，且不能由本阶段自行授予：

1. **继承的 D4 门：** D4 已由用户为 Phase 19 明确解冻，且 Phase 19 已关闭并留下匹配评估、消融与成本/延迟证据；Phase 20 继承这一状态，不重新解释或自动解冻 D4；
2. **独立试点授权门：** 用户/项目负责人明确确认 G5 通过并单独授权进入试点规划/执行。该授权落实仓库对外部/难回退行动必须确认的规则；
3. **语料一致性与 P0 门：** 已定义一个边界明确的业务知识库、允许用户、数据分类和责任人；试点 corpus 必须是 Phase 19 已评估 corpus 的同版本子集或全体，并在进入任何灰度或真实查询前完成真实语料的 `S_direct == S_okf` round-trip 验证；不能仅凭 Phase 14 fixtures 通过；
4. 不可把“代码可运行”视为满足入口，也不可把 Phase 20 自动接在 Phase 19 后执行。

### 5.2 试点范围

Phase 20 只针对**一个**资料结构较清晰、问题可标注、价值可验证的业务知识库。必须规划：

| 能力域 | Phase 20 必须具备的计划结果 |
|---|---|
| 范围与数据治理 | 试点 corpus、数据所有者、允许用途、保留/删除、OKF/原始二进制版本、敏感数据分类和变更责任 |
| 授权与隔离 | 检索候选生成、RRF 融合、上下文组装和响应前均执行同一权限策略；多租户/知识库隔离不能只靠 UI 筛选 |
| 索引运行 | 入库、增量同步、删除/tombstone、失败重试、任务状态、陈旧索引检测、重建及演练的责任边界 |
| 可观测性 | 每路召回、R3/coref 开关、路径预算、延迟 P50/P95/P99、错误率、陈旧率、成本/资源与审计事件；日志按最小化原则处理原文/PII；复用确定性 verification/运行产物模式，**不得引入 LLM 监控** |
| 灰度与回退 | 明确的 feature flag、百分比/用户组灰度、停止条件、R3/coref kill switch、回退到 R1/R2a/R2b、派生 DB 重建和 OKF Git 恢复程序 |
| 人工纠错闭环 | 反馈分流为 retrieval issue、数据问题或受控 OKF proposal；必须经 Phase 18 人审。**Agent writeback 在试点默认 off**；若要在试点启用 proposal/staging，需要在三重门之外取得单独的第四项用户授权，仍不得自动学习/自动写回 |
| 运维与安全 | 值守与升级路径、告警阈值、备份/恢复演练、最小权限、密钥仅来自环境/secret manager、安全审查和上线检查表 |

### 5.3 明确非目标

Phase 20 不得自动扩大为：

- 全公司、多业务域或无限租户生产铺开；
- 借试点重做 Phase 14–18 的功能设计；
- 未经 D4/Phase 19 证据就调参、默认开启 R3/coref 或作质量营销；
- 引入全量 LLM GraphRAG、图数据库或 Agent 自动写入；
- 将数据库、日志、评测产物当作 OKF SSOT 的替代品；
- 以试点反馈为由重做 Phase 14–18 或 Phase 19 已裁决的架构；重大功能缺陷、新存储需求或新路线必须走 roadmap evolution 新 phase，不能在试点期间顺手实现。

### 5.4 G5 与 G6 的验收门

| 门 | 责任 | 最小证据 | 失败/未通过处理 |
|---|---|---|---|
| **P0：真实语料 SSOT 就绪** | Phase 20 启动前 | 试点 corpus 的 `S_direct == S_okf`、来源/版本边界和可回滚数据清单；不能只复用 Phase 14 fixture 结论 | 暂停试点；若是新增文档类型或 round-trip 漂移，按 **Phase 14 serializer/parser 契约缺陷** 路由，不把它伪装成 Phase 20 失败或在试点中规避 span identity |
| **P1：派生层可恢复** | Phase 20 灰度前 | 在试点 corpus 上完成幂等 rebuild；`okf_rebuild_log` 及比较结果证明派生层无不可恢复数据丢失 | 停止灰度，修复对应所有者阶段；不得以手工 DB 修补代替 OKF 重建 |
| **P2：可观测试运行** | 约定试点周期内 | 全周期确定性遥测已采集，且形成送回 Phase 19 backlog 的反馈报告；不作新的 Level 宣称 | 延长/暂停试点，补齐遥测和反馈，不扩大范围 |
| **P3：真实语料回退演练** | G6 前 | 在试点 corpus 上执行派生 DB 清空/重建 + OKF Git 状态恢复演练；重建等价集至少覆盖 `canonical_spans`、`vector_chunks`、`tree_nodes`、entities/aliases/mentions、`node_entity_links`，以及已启用时的 `coref_clusters` 与 membership | 回退未通过则 No-Go；修复后重演，不扩大范围 |
| **G5：试点价值成立** | Phase 19 评估负责人 + 项目负责人 | 已解冻 D4 下的匹配评测；八类中文问题覆盖；模块消融；质量-成本-延迟 Pareto；已知失败与适用范围 | 不进入生产试点；维持研究原型或关闭无收益模块 |
| **G6：生产 Go/No-Go** | 业务 owner、技术 owner、安全/运维责任人，必要时用户明确批准 | P0–P3 全绿、权限与隔离测试、故障与告警演练、灰度结果、SLO/容量证据、审计/反馈闭环、安全审查、运维手册；Go 仅表示完成约定试点与受控扩大决策，不是新的 Level 宣称 | No-Go 或保持有限灰度；按缺陷所有者路由（14 span identity、17 R3、18 writeback、19 质量）；关闭 R3/coref，回退至经验证的 R1/R2 路径，不扩大用户或资料范围 |

DOCX 中“查询 P95 ≤5 秒（目标 ≤2 秒）”是源级**目标线**，不是在未知语料规模上可直接承诺的硬编码值。Phase 20 PLAN 必须基于试点数据规模、并发、硬件、回答模型是否计入，明确实际 SLO 与测量方法；不得把该目标改写成无条件承诺。

### 5.5 必须输出的 Phase 20 规划工件

未来 Phase 20 的边界文档至少要列出：

1. 试点范围与数据处理说明；
2. 访问控制/租户隔离决策和测试矩阵；
3. 路由与 feature-flag 操作手册（R3/coref 独立 kill switch）；
4. 入库、同步、删除、重建与回退 runbook；
5. 仪表盘/告警/日志数据最小集和敏感数据处理规则；
6. 人工反馈到 Phase 18 proposal 的闭环规则；
7. 灰度计划、停止条件、incident 升级路径；
8. G6 上线检查表及清晰的决策签署责任。

---

## 6. 接手会话必须完成的文档变更矩阵

下表指定**规划层**的编辑位置。接手会话应先读全文再编辑；每个变更应保持已有措辞与格式，不可用全局替换破坏旧计划。

| 文件 | 必须新增/修正的内容 |
|---|---|
| `.planning/OKF-MULTIROUTE-EXECUTION-HANDOFF-2026-07-12.md` | 在 §5 路线表中把 C 拆清 `C1 实体层 / C2 指代链`，新增 G “受限业务试点与生产就绪”；在 §6.3 将 `coref_clusters` 从“C 后按需插入”更新为 “Phase 16-C2”；在 §11 新增 C2 及 G 边界摘要；在 F 中明确来源路线图的八类问题、消融阶梯和 G5 输出；保持 D4 文字不变。 |
| `.planning/v2.0-MILESTONE-OKF-MULTIROUTE.md` | 增加 R-OKF-09（保守、可关闭、带 provenance 的中文 coref clusters）和 R-OKF-10（单一业务库试点的权限/隔离/回退/运维就绪）；阶段映射新增 C1/C2 说明与 Phase 20（G）；F6 后增加 F7 试点流；补充 16/17、19/20 边界裁决。所有阶段仍须写为 planned，不能暗示已开始。 |
| `.planning/ROADMAP.md` | 扩展 Phase 16 的目标、依赖和 success criteria，明确 16-C2；为 Phase 17 增加可选 coref 消费和 disabled fallback；扩展 Phase 19 为来源级评估/消融/G5 产物；新增 Phase 20 标题、状态、入口、依赖、边界文档和 G6 success criteria。 |
| `.planning/phases/16-raw-corpus-entity-layer/16-BOUNDARY.md` | 在 In Scope、Acceptance、Open Questions、Risks 中纳入 16-C2 的子入口门、局部 coref 契约、默认 off、per-cluster tombstone 与 migration 顺序；Deliverables 中以独立 **16-C2 sub-wave block** 插入，保持现有“16-VERIFICATION”作为末项。`relation_mentions` 仍为明确 Out of Scope/C 后按需项；不得为 coref 偷渡关系抽取。 |
| `.planning/phases/17-graph-recall-multiroute-fusion/17-BOUNDARY.md` | 明确 R3 可选消费 `coref_clusters`，需要可解释路径、预算和独立 coref `off` 回退；区分 coref 开关与 `RAG_ROUTE_R3=off` 的逐位一致回归承诺；不得改变 T7 的 RRF-only 接入点或热点权重冻结。 |
| `.planning/phases/19-evaluation-tuning/19-BOUNDARY.md` | 将 DOCX 的八类问题、All-Evidence Recall、A–G/H 消融顺序、coref 的 G3、动态多跳的 G4 和试点价值 G5 写为 D4 解冻后的工作；保持“无新功能开发”边界，并明确 19 只产生 G5/Level 评估，不部署试点。 |
| **新建** `.planning/phases/20-pilot-productionization/20-BOUNDARY.md` | 使用第 5 节完整定义 Phase 20：继承 D4 解冻 + 19 closed + 单独 pilot sign-off 的三重门，且要求同版本评估 corpus/P0；Goal、In/Out of Scope、P0–P3/G6 Acceptance、Open Questions、Risks/rollback、与 Phase 18/19 的接口。Agent writeback 默认 off；文件开头必须写 planning-only、需用户授权执行。 |
| `.planning/LOW-TOKEN-GRAPHRAG-UPGRADE-PLAN.md` | 在标题后增加简短的“2026-07-12 v2.0 reconciliation”注记：WS2 由 Phase 16-C2 承接；阶段 6 由 Phase 20 承接；实际 migration 编号和 R3 注入符号以 ADR T5/T7 为准；G3–G5 在 D4 解冻前不执行。保留原 WS 表、八类评测、A–G/H 消融、风险/回退和试点细节。 |
| `.planning/STATE.md` 与 `.planning/workspace-memory.json` | **仅在项目现有状态管理流程要求时**更新为“两个缺口的规划已分配，未执行”。不要把任何 Phase 标为实施中，也不要覆盖其他会话现有状态。 |

### 文档变更后的自检

接手会话应在不运行实现的前提下核验：

- 从主交接书、milestone、Roadmap 都能追到 16-C2 和 Phase 20；
- `coref_clusters` 出现时，总能看到“局部、可追溯、默认 off、非实体合并、D4 前不评估收益”的边界；
- “试点/生产”出现时，总能看到“Phase 19/G5 后、继承 D4 解冻、同版本评估 corpus、单一业务库、权限/隔离、Agent writeback 默认 off、P0–P3、灰度/回退、G6 人工决策”的边界；
- Phase 20 的 Go 必须只表示已完成约定试点和受控扩大决策，不得被描述为新的 Level 宣称；
- 不再存在 `_fuse_candidate_scores` 作为拟修改符号的表述；
- 不存在 “migration 017 必须创建 coref_clusters” 这类会与实际编号冲突的表述；
- 没有新增的自动 commit、自动 merge、自动写 `raw/` 或 sidecar 的路径；
- 既有 D4 冻结和 Phase 14 的 `S_direct == S_okf` 硬门没有被削弱。

---

## 7. 建议接手流程（仅规划）

1. 先完成第 2 节的阅读并记录实际行号/现有措辞；
2. 用本文第 6 节作为变更清单，先更新权威链和 milestone，再更新 Roadmap 与 phase boundaries；
3. 对 `LOW-TOKEN-GRAPHRAG-UPGRADE-PLAN.md` 只增加 reconciliation 注记，保留它的源证据细节；
4. 不创建 runtime task、迁移、代码 stub、测试 stub 或数据库对象；
5. 用全仓规划文档搜索核验两个 gap 的旧表述已被准确限定，而不是被删除后遗失；
6. 产出简短的 planning-diff summary，逐项说明第 6 节每个文件的变更与未改动的硬约束；
7. 由于用户尚未授权执行，不提交、不推送，也不声称准备开始 Phase 14。

---

## 8. 来源证据索引

| 证据 | 位置 | 对本补充的意义 |
|---|---|---|
| 两项缺口的直接列示 | `.planning/OKF-MULTIROUTE-EXECUTION-HANDOFF-2026-07-12.md:198-214` | `coref_clusters` 仍是“C 后按需插入”，试点未列为阶段 |
| D4 冻结 | `OKF-MULTIROUTE-EXECUTION-HANDOFF-2026-07-12.md:54-65`；`v2.0-MILESTONE-OKF-MULTIROUTE.md:20, 65-66` | 说明 G3/G4/G5 不可抢跑 |
| 当前 C 边界 | `OKF-MULTIROUTE-EXECUTION-HANDOFF-2026-07-12.md:379-388`；`phases/16-raw-corpus-entity-layer/16-BOUNDARY.md:12-46` | 当前拥有 entity layer，但未拥有 coref |
| 当前 F 边界 | `OKF-MULTIROUTE-EXECUTION-HANDOFF-2026-07-12.md:411-419`；`phases/19-evaluation-tuning/19-BOUNDARY.md:13-44` | 当前评测存在，但没有阶段 6 生产化所有者 |
| R3 正确接入符号 | `ADR-OKF-PHASE-A-TECH-DECISIONS-2026-07-12.md:77-81`；`v2.0-MILESTONE-OKF-MULTIROUTE.md:59-60, 72-75` | 保护 `fuse_candidates` / 禁止改热点权重 |
| 关系限定词与 relation_mentions 边界 | `ADR-OKF-PHASE-A-TECH-DECISIONS-2026-07-12.md:66-75`；`16-BOUNDARY.md:25-30` | 防止 coref work package 擅自扩大为关系抽取 |
| 源 DOCX 对 C2/试点的原始要求 | `LOW-TOKEN-GRAPHRAG-UPGRADE-PLAN.md:78-99`；源 DOCX §6.4、§6.7、§7、§8、§10 | 指代簇、G3、G5/G6、八类评估、试点运维与回退的来源 |
| 源数据模型 | `LOW-TOKEN-GRAPHRAG-UPGRADE-PLAN.md:21-35` | `coref_clusters` 是来源路线图明确要求，非新发明 |

---

## 9. 可直接交给下一会话的任务指令

```text
你只接手 E:\github\rag 的 v2.0 规划补齐，不执行运行时代码。

先完整阅读：
1. .planning/OKF-LOW-TOKEN-GAPS-SUPPLEMENT-HANDOFF-2026-07-12.md
2. .planning/OKF-MULTIROUTE-EXECUTION-HANDOFF-2026-07-12.md
3. .planning/UNIFIED-MULTIROUTE-OKF-PLAN.md
4. .planning/ADR-OKF-PHASE-A-TECH-DECISIONS-2026-07-12.md
5. .planning/v2.0-MILESTONE-OKF-MULTIROUTE.md
6. .planning/LOW-TOKEN-GRAPHRAG-UPGRADE-PLAN.md
7. .planning/phases/16-raw-corpus-entity-layer/16-BOUNDARY.md
8. .planning/phases/17-graph-recall-multiroute-fusion/17-BOUNDARY.md
9. .planning/phases/19-evaluation-tuning/19-BOUNDARY.md
10. .planning/ROADMAP.md

唯一任务：按补充交接书第 6 节的文件矩阵，完成规划文档更新：
- 把中文 coreference / coref_clusters 明确归属为 Phase 16-C2；
- 新增 Phase 20 受限业务试点与生产就绪边界；
- 把 Phase 19 的来源级评估、G3/G4/G5 与 Phase 20 的 G6 接口接上；
- 在低 Token 源计划中只添加 reconciliation 注记，保留其细节。

硬约束：
- 这是 planning-only。不要创建或修改 Python/SQL/测试/配置/OKF 数据；不要执行 migration、数据库或入库流程；不要 commit/push。
- D1–D8、ADR T1–T9、D4 冻结、T7 的 fuse_candidates-only 接入、T8 人审回写不可改变。
- relation_mentions 仍是 C 后按需项；16-C2 不建该表，也不借 coref 添加关系抽取。若未来存在独立触发条件，须以新的 C 后按需规划明确处理。
- 16-C2 的 C1→C2 migration 顺序、coref 与 R3 两个独立开关、以及 Phase 20 的三重门/P0–P3 不可弱化。
- 任何代码实现未来仍须先遵守仓库 CLAUDE.md（GitNexus impact、TDD、review/security 等）。

完成后报告：每个修改文件、coref 的精确 Phase 16-C2 边界、Phase 20 的 G5/G6 门、以及你没有执行任何运行时代码的确认。
```
