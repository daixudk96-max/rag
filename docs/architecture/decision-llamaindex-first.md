# 最终决策：选择 LlamaIndex-first 方案

> 这份文档属于“目标架构主线”，不是 `verification/` 里的验证实现主线。

决策时间：2026-05-08  
决策依据：`verified-project-matrix.md` + `llamaindex-implementation-assessment.md`

---

## 一、核心决策：选择 LlamaIndex-first

### 决策理由（三个关键维度）

#### 1. 需求覆盖完整性
- **LlamaIndex**：KG✅ / Vec✅ / Tree✅ / Parse✅ / Cas✅ / Map✅ / Agent✅（全覆盖）
- **KAG**：KG✅ / Vec✅ / Tree◐ / Parse◐ / Cas✅ / Map✅ / Agent◐（Tree/Parse/Agent 为 partial）

**判断**：你的需求是"三合一混合架构 + Agent 自主扩展"，LlamaIndex 的组件覆盖比 KAG 更完整。

#### 2. 工程控制力
- **LlamaIndex**：
  - MIT 许可 + 活跃维护（2026-04-16）
  - 模块化设计（可按需替换 KG/Vec/Tree/Agent 各层）
  - 官方扩展点清晰（CustomPGRetriever、BaseRetriever、Workflow、Agent tools）
  
- **KAG**：
  - Apache-2.0 许可 + 蚂蚁集团维护
  - OpenSPG 引擎绑定（KG 层不可替换）
  - 逻辑求解器固化（kg-solver 的逻辑形式固定）

**判断**：如果你追求"长期可维护 + 后端可替换"，LlamaIndex 控制力更高。

#### 3. 改动量 vs ROI

| 方案 | 改动量 | 获得能力 | ROI |
|---|---|---|---|
| **LlamaIndex-first** | 1000-1700行 | KG+Vec+Tree+Agent全栈 + 完全自主策略控制 | **高**（全栈能力 + 高控制力） |
| **KAG-first** | 200-600行 | KG+Vec强推理 + mutual indexing + 部分 Tree/Agent | **中高**（推理强，但Tree/Agent受限） |

**判断**：改动量差异（400-1100行）换取的是 Tree/Agent 的完整控制权。  
如果你"Tree + Agent 自主扩展"是硬需求，LlamaIndex 的 ROI 更高。

---

## 二、决策结论

### 选择 LlamaIndex-first 的核心逻辑

**如果你的首要目标是**：
1. **三合一架构完整落地**（KG+Vec+Tree 全覆盖）
2. **Agent 自主扩展完全可控**（父节点/兄弟节点/相邻chunk 的扩展策略由你定义）
3. **长期工程可维护**（MIT 许可 + 模块化 + 后端可替换）

**选择 LlamaIndex-first，接受 1000-1700行策略代码自研。**

---

### 不选 KAG-first 的核心逻辑

**虽然 KAG 有优势**：
- KG 推理能力更强（OpenSPG + kg-solver）
- mutual indexing 已实现（省去 KG-Tree 桥接代码）
- 改动量更低（200-600行）

**但不选的理由**：
- Tree 是 DIKW/schema hierarchy，不是独立树索引（你的 Tree 需求是显式层级树 + 命中回映）
- Agent 是 MCP/Thinker，不是自主扩展策略（你的 Agent 需求是基于命中分布决策扩展）
- Parse 是 layout analysis + extraction，不是结构化文档保留（你需要 Docling 的 page_no + heading_path）

**判断**：KAG 的 Tree/Agent/Parse 都标记为 partial，这三个 partial 正是你需求中的核心差异化能力。

---

## 三、实施路径决策

### LlamaIndex-first 的三阶段实施

#### Stage 1：基础集成（2-3周）
- KG：PropertyGraphIndex + Neo4jPropertyGraphStore
- Vec：MilvusVectorStore + VectorStoreIndex
- Tree：HierarchicalNodeParser + AutoMergingRetriever
- Parse：DoclingReader + DoclingNodeParser（保留 page_no + headings）
- Agent：ReActAgent + Workflow 基础框架

#### Stage 2：核心策略自研（3-4周）
- 级联 retriever：CascadeKGVecTreeRetriever（250-300行）
- 命中分布分析器：analyze_hit_distribution（200-400行）
- Agent 扩展决策：decide_expansion + expansion tools（300-500行）

#### Stage 3：工程化（4-6周）
- 性能优化：缓存、并发、预计算
- 可观测性：日志、监控、命中分布可视化
- 错误处理：重试、降级、边界处理

---

## 四、关键决策点

### 决策点 1：KG 后端选择

**推荐：Neo4j**
- 原生图遍历/图算法（PageRank/社区发现/子图匹配）
- Cypher 查询语言成熟
- LlamaIndex 有官方 Neo4jPropertyGraphStore

**备选：如果不想维护 Neo4j**
- 用 KAG 的 OpenSPG（但绑定了 KAG 生态）
- 或用 vector-graph-rag 的"向量+元数据"模式（但图能力受限）

### 决策点 2：Vec 后端选择

**推荐：Milvus**
- 高性能 ANN（适合大规模）
- 元数据过滤能力强（支持你的 neighborhood-first retriever）
- LlamaIndex 官方集成

**备选：Qdrant/Chroma**
- Qdrant：单机部署简单，适合中小规模
- Chroma：轻量级，适合 PoC 验证

### 决策点 3：Parse 后端选择

**推荐：Docling**
- MIT 许可 + 原生 LlamaIndex 集成
- 保留 page_no + headings（你的 citation-path 基础）
- 支持 PDF/DOCX/PPTX/HTML

**不推荐：Marker**
- GPL-3.0（商业需双许可）
- 仅输出 Markdown，结构元数据丢失
- 需完全自研 adapter（改动 heavy）

---

## 五、风险决策

### LlamaIndex-first 的主要风险

| 风险 | 应对策略 |
|---|---|
| **策略逻辑复杂**（600-1100行） | 分阶段实施：PoC 先验证核心逻辑，生产化再优化 |
| **多阶段级联性能**（KG→Vec→Tree） | 预计算子图索引 + 缓存 + 异步并发管线 |
| **Agent 扩展决策不稳定** | 定义明确的决策规则 + fallback 机制 + 测试覆盖 |
| **多数据库运维成本**（Neo4j+Milvus） | 用统一监控面板 + 定期健康检查 + 自动备份 |

---

## 六、最终执行建议

### 立即可执行的决策

1. **选定主底座**：LlamaIndex
2. **选定 KG 后端**：Neo4j（原生图能力）
3. **选定 Vec 后端**：Milvus（高性能 + 元数据过滤）
4. **选定 Parse 后端**：Docling（结构保留 + MIT 许可）
5. **接受改动量**：1000-1700行策略代码（这是正常的，你的需求已超出标准 RAG）

### 第一周可落地的任务

- Day 1-2：安装 LlamaIndex + Neo4j + Milvus + Docling
- Day 3-4：跑通 PropertyGraphIndex + VectorStoreIndex + HierarchicalNodeParser 基础示例
- Day 5：验证 DoclingReader 保留 page_no + headings 元数据
- Day 6-7：测试 AutoMergingRetriever 的 child→parent 合并行为

---

## 七、决策总结

**选择 LlamaIndex-first 不是因为它改动量最低，而是因为**：
1. 它是唯一一个**全组件覆盖**的方案
2. 它给你**完整的策略控制权**（Tree/Agent 的自主扩展逻辑）
3. 它的**工程可控性最高**（MIT 许可 + 模块化 + 后端可替换）

**这是"控制力 vs 改动量"的决策**：  
你愿意多投入 400-1100行代码，换取 Tree+Agent 的完整自主权。

**如果你接受这个决策**，下一步的关键技术问题是：
1. "命中分布聚散算法"是否有现成实现？
2. "自适应滑动切片"能否接入？

（这些问题将并行核验）