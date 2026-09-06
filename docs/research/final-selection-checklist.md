# Final Selection Checklist

Generated: 2026-05-08  
Based on: `verified-project-matrix.md` (Sonnet-verified)

## Decision logic

这张清单是用来**直接做选型决策**的，不再是全量核验表。  
判断依据：
- 优先级 = (需求匹配度 × 成熟度 × 开源安全性) 的综合排序
- 淘汰逻辑 = 明确缺口或规则冲突（如 GraphRAG 身份）
- 组合建议 = 哪些项目更适合当主底座，哪些更适合当补件

---

## 1) 最优先选型（推荐做主底座）

### 第一优先级：LlamaIndex
- **定位**：最强模块拼装底座
- **核验覆盖**：KG✅ / Vec✅ / Tree✅ / Parse✅ / Cas✅ / Map✅ / Agent✅
- **决策依据**：
  - 公开 MIT 许可，仓库活跃（2026-04-16）
  - 官方文档明确覆盖所有你关心的维度
  - `PropertyGraphIndex + TreeIndex + RecursiveRetriever + AutoMergingRetriever + ReAct agents` 全部有公开示例
- **适合场景**：
  - 要把 A-F 真正拼全
  - 追求工程控制力和长期可维护性
- **代价**：不是一键成品，要自己拼装和调优

### 第二优先级：KAG
- **定位**：最强 KG + 层级索引主脑
- **核验覆盖**：KG✅ / Vec✅ / Tree◐ / Parse◐ / Cas✅ / Map✅ / Agent◐
- **决策依据**：
  - 公开 Apache-2.0，蚂蚁集团官方
  - `Knowledge and Chunk Mutual Indexing` + `DIKW 层级树` + `逻辑形式引导求解器` 都是硬核特色
  - Tree 被核验为 DIKW/schema hierarchy，不是独立树索引
- **适合场景**：
  - 金融/法务/医疗/政务等逻辑推理优先的场景
  - 想让图谱约束语义，而不是纯向量模糊匹配
- **代价**：
  - Vec 后端配置未钉死
  - 命中分布聚合和自主扩展需要自己补

### 第三优先级：R2R
- **定位**：最强平台/API 型候选
- **核验覆盖**：KG✅ / Vec✅ / Tree❌ / Parse✅ / Cas◐ / Map✅ / Agent✅
- **决策依据**：
  - 公开 MIT，SciPhi-AI 官方
  - `Citation markers in responses`（Map）和 `Deep Research API`（Agent）比很多项目更清晰
  - 核验明确 Tree=no，所以不能当树系统主底座
- **适合场景**：
  - 要一个完整的 API/Agent 平台
  - 不强求 Tree，但看重引用路径和深度推理
- **代价**：Tree 必须外接

---

## 2) 次优先但可作为快速落地的选择

### 第四优先级：NexusRAG
- **定位**：最快 POC 母体
- **核验覆盖**：KG✅ / Vec✅ / Tree❌ / Parse✅ / Cas◐ / Map◐ / Agent✅
- **决策依据**：
  - 公开 MIT，但**个人项目**，不是机构级维护
  - `page-aware citations + heading_path` 是真实存在的
  - Tree=no（核验纠正：不应把 heading path 当成完整树索引）
- **适合场景**：
  - 快速验证原型
  - 文档型问答产品（政策/投标/研究报告）
- **代价**：
  - 长期维护风险高
  - Tree/命中聚合需自研

### 第五优先级：RAGFlow
- **定位**：被低估的完整平台
- **核验覆盖**：KG✅ / Vec✅ / Tree◐ / Parse✅ / Cas◐ / Map✅ / Agent✅
- **决策依据**：
  - 公开 Apache-2.0，infiniflow 官方
  - 核验后发现比之前低置信度判断更强：KG + RAPTOR/tree + agent orchestration 都有明确证据
  - Tree=partial（RAPTOR 风格树检索存在，但不是你要求的非向量树状知识库）
- **适合场景**：
  - 平台化部署
  - 需要完整 KG+Vec+Agent 组合
- **代价**：Tree 仍是 RAPTOR 风格，不是显式层级知识库

---

## 3) 最优补件（不适合当主底座，但适合补能力缺口）

### 树层 + 后处理补件
#### RAPTOR
- **核验覆盖**：KG❌ / Vec◐ / Tree✅ / Parse❌ / Cas❌ / Map❌ / Agent❌
- **定位**：纯递归树检索 + 相似度聚类构建树
- **补件价值**：
  - 补你最缺的 Tree/Map（命中回映父节点）
  - 提供 `cluster_tree_builder + tree_retriever` 思路
- **代价**：无 KG，无 Agent，Parse 弱

#### HIRO
- **核验覆盖**：KG❌ / Vec◐ / Tree✅ / Parse❌ / Cas◐ / Map❌ / Agent❌
- **定位**：RAPTOR 查询优化层（分支剪枝 + 递归相似度评分）
- **补件价值**：
  - 补你要求的“基于命中分布决定重点阅读层”的算法层
  - 提供 `recursive similarity scoring + branch pruning` 思路
- **代价**：无 KG，无 Parse，无 Agent

#### HiSem-RAG
- **核验覆盖**：KG❌ / Vec◐ / Tree✅ / Parse◐ / Cas◐ / Map❌ / Agent❌
- **定位**：第四篇文档最强调的"命中分布聚散统计"补件
- **补件价值**：
  - 提供 `C_V 离散系数 + 动态阈值` 算法思想
  - 最接近你要求的"Map + 重点阅读区决策"补件
- **代价**：
  - 核验状态 partial（repo 状态不明确）
  - 无 KG，无 Agent

#### Psi-RAG
- **核验覆盖**：KG❌ / Vec◐ / Tree✅ / Parse◐ / Cas✅ / Map❌ / Agent✅
- **定位**：强 Tree + Agent 组合，但缺 KG
- **补件价值**：
  - 补你最需要的 Tree + Agent 双轨扩展
  - 提供迭代智能体检索 + 多跳树搜索思路
- **代价**：KG 缺口明显，必须和 KAG 或其他 KG 主底座组合

---

## 4) 明确淘汰项（规则冲突或覆盖缺口过大）

### 按规则直接排除（GraphRAG 身份）
- microsoft/graphrag —— 用户明确排除
- tigergraph/graphrag —— explicit GraphRAG
- flexible-graphrag —— explicit GraphRAG
- graph-rag-agent —— explicit GraphRAG
- ApeRAG —— explicit GraphRAG
- automataIA/graphrag-rs —— GraphRAG-derived（Rust port）
- ms-graphrag-neo4j —— GraphRAG-derived
- repo-graphrag-mcp —— GraphRAG-derived

**判断逻辑**：如果规则是"排除显式 GraphRAG 身份或紧邻变体"，这 8 个都应淘汰；如果不那么严格，后 3 个是 GraphRAG-derived（重实现而非包装），可勉强保留，但不推荐主选。

### 覆盖缺口过大，不建议主选
- **LightRAG** —— KG+Vec 强，但 Tree/Map/Agent 全缺口
- **kg-rag** —— 研究/基线定位，Parse/Tree/Agent 缺口大
- **Cognee** —— Agent memory 方向强，但 Tree 不明确，Parse/Map 弱
- **HippoRAG** —— KG+PageRank 风格，Vec 核验为 no（应纠正为 partial 或 no）
- **trustgraph** —— graph-native context 平台，Tree 缺口
- **autoflow** —— 限制在 Web-crawl，Parse/Tree/Map/Agent 全缺口
- **pdichone/knowledge-graph-rag** —— KG+Vec 存在，但 Tree/Map/Agent 未验证
- **HybridRAG** —— 无权威单仓库，Tree 缺口
- **self-learning-ai-agent** —— 核验无法确认为单一官方项目

---

## 5) 边缘参考项（不建议主选，但可作为研究参考）

### 研究旁支
- **KG2RAG** —— KG 引导 chunk organization/retrieval 研究价值高，但不完整
- **HMRAG** —— Tree/Cas/Agent 覆盖好，但 Parse/Map 缺口，license 不明确
- **A-RAG** —— Tree+Agent 组合，但 KG 缺口
- **context-aware-rag** —— KG+Vec+Cas 存在，但 Tree 缺口，Agent partial
- **HiRAG** —— KG+Vec+Cas+Tree partial，但 Parse/Map/Agent 缺口

### 论文蓝图但不建议主选
- **BookRAG** —— 重要纠正：**公开仓库存在**，但无 license 文件  
  - 核验：KG◐ / Vec❌ / Tree✅ / Parse✅ / Cas◐ / Map❌ / Agent✅  
  - 适合当设计参考，不适合当主代码底座  
  - 法律风险：无 license = all rights reserved，不能安全商用

---

## 6) 组件-only（不是完整平台，只能当工具）

- **MinerU** —— layout-aware parser，但 license 呈现混乱（AGPL vs Apache 附加条款）
- **Docling** —— document parser（MIT），适合接入 ingestion 层
- **Marker** —— PDF-to-Markdown（GPL-3.0 + 商业双许可）
- **LlamaParse** —— 云解析服务（非开源），SDK 公开但 parser 本身是 SaaS
- **LangGraph** —— Agent 编排框架（MIT），不是 parser/RAG 组件

---

## 7) 直接可执行的组合方案

### 方案 A：LlamaIndex-first（控制力最高，覆盖最全）
```
主底座：LlamaIndex
├── KG 层：PropertyGraphIndex + Neo4jPropertyGraphStore
├── Vec 层：Milvus/Qdrant/Chroma 后端
├── Tree 层：HierarchicalNodeParser + AutoMergingRetriever
├── Parse 层：Docling/Marker（结构化摄入）
├── Cas 层：RecursiveRetriever + sub-question query engine
├── Map 层：AutoMergingRetriever 的 child→parent 合并逻辑
└── Agent 层：ReAct agents + Workflow/Planner
```
**适合场景**：追求工程可控、长期维护、全栈拼装  
**工作量**：中高（4-8 周 PoC，8-12 周生产）

### 方案 B：KAG-first（逻辑推理优先，图谱约束语义）
```
主底座：KAG
├── KG+Tree 互索引：KAG 的 Knowledge-Chunk Mutual Indexing
├── Vec 层：外接 Qdrant/Milvus（需自己适配）
├── Parse 层：KAG 已有 layout analysis + extraction
├── Cas 层：kg-builder + kg-solver 的逻辑形式规划
├── Map 层：补一个命中分布聚合统计器（借鉴 HiSem-RAG）
└── Agent 层：MCP/KAG-Thinker 扩展 + 外接 LangGraph 编排
```
**适合场景**：专业域问答、逻辑正确性优先  
**工作量**：中高（2-4 周 PoC，4-8 周生产）

### 方案 C：NexusRAG-first（最快 POC，文档产品）
```
主底座：NexusRAG
├── KG+Vec+Parse：NexusRAG 已有（LightRAG KG + ChromaDB + Docling/Marker）
├── Tree 层：补树节点聚合统计（利用 heading_path）
├── Cas 层：已有多阶段 rerank，需补图优先约束
├── Map 层：已有 inline citations，需补命中分布可视化
└── Agent 层：已有 streaming chat，需补自主扩展逻辑
```
**适合场景**：快速验证原型，文档型问答产品  
**工作量**：低（1-3 周 PoC）

### 方案 D：R2R-first（API/Agent 平台，不强求 Tree）
```
主底座：R2R
├── KG+Vec+Parse：R2R 已有
├── Tree 层：外接 RAPTOR/HIRO 或自定义树索引
├── Cas 层：Deep Research API（多步推理）
├── Map 层：已明确 citation markers
└── Agent 层：已明确 reasoning agent
```
**适合场景**：平台化 API 服务，不把 Tree 当硬约束  
**工作量**：中（3-5 周 PoC）

---

## 8) 最终建议

如果你的首要目标是**覆盖 A-F 全维度 + 工程可控**：  
**选方案 A（LlamaIndex-first）**，补件可选 RAPTOR/HIRO。

如果你的首要目标是**逻辑推理 + 图谱约束语义**：  
**选方案 B（KAG-first）**，补件选 HiSem-RAG（命中分布）+ Psi-RAG（Agent 扩展）。

如果你的首要目标是**最快跑出原型**：  
**选方案 C（NexusRAG-first）**，注意这是个人项目，长期维护风险。

如果你的首要目标是**API/Agent 平台，Tree 不硬性要求**：  
**选方案 D（R2R-first）**。

---

## 9) 不建议的选型

- **不要主选 LightRAG**：Tree/Map/Agent 缺口大，更适合当图+向量内核
- **不要主选 kg-rag**：研究基线定位，不适合生产系统
- **不要主选 BookRAG**：无 license，法律风险高
- **不要主选任何 GraphRAG 系**：如果规则仍然生效，应明确排除

---

## 10) 关键纠正总结

这次核验最关键的纠正点：
1. **BookRAG 实际有公开仓库**，但无 license（风险高）
2. **LlamaParse 不是开源 parser**，是云服务
3. **NexusRAG 是个人项目**，不是机构平台
4. **RAGFlow 比预期强**，覆盖更完整
5. **HippoRAG 的 Vec 不应标 yes**，更偏 KG/PageRank
6. **self-learning-ai-agent 无法核验为单一项目**，更像描述性标签

所以：这张清单是基于 Sonnet 核验后的**修正版选型逻辑**，不再依赖原文档中的过度乐观描述。