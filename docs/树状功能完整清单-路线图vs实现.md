# 树状功能完整清单（路线图 vs 实现）

## 路线图规划的树状功能

### Phase 6 — Tree Formal Rollup（已实现）

**规划内容**：
- tree_nodes / tree_node_spans migration
- tree generator（从heading_path生成树）
- tree loader（写入registry）
- tree query / rollup（leaf → parent回并）
- vector_chunks.node_id关联

**实际实现**：
- ✓ `src/registry/migrations/004_tree_extension.sql`（迁移到llamaindex_runtime）
- ✓ `llamaindex_runtime/registry/tree_generator.py`（TreeGenerator已实现）
- ✓ `llamaindex_runtime/tree/runtime.py`（检索逻辑）
- ✓ `llamaindex_runtime/tree/backend_adapter.py`（BackendHit协议）

**状态**：✓ **DONE（Phase 6已完成）**

---

### Phase 8 — HitDistributionAnalyzer（已实现）

**规划内容**：
- hit_distribution types / analyzer / decision / collector
- `/query/analyze` API
- Vector→Tree单路命中分布分析

**实际实现**：
- ✓ `llamaindex_runtime/analysis/types.py`（NodeHit, AncestorScore, ExpansionDecision）
- ✓ `llamaindex_runtime/analysis/analyzer.py`（CV + Shannon Entropy计算）
- ✓ `llamaindex_runtime/analysis/decision.py`（集中/分散/中等决策）
- ✓ `llamaindex_runtime/analysis/fusion.py`（Hit融合）

**状态**：✓ **DONE（Phase 8已完成）**

---

### Phase 9 — Deep Hybrid Path（部分实现）

**规划内容**：
- HybridHit统一命中结构
- collect_all_paths（收集Graph/Keyword/Vector/Tree）
- aggregate_hits（聚合多路结果）
- expand_by_decision（根据决策扩展）
- hybrid_query orchestrator

**实际实现**：
- ⚠ `llamaindex_runtime/workflow/hybrid_retrieval_workflow.py`（部分）
- ⚠ `llamaindex_runtime/entrypoints/query.py`（统一入口）
- ⚠ 多路收集未完全实现（只有tree/vector）

**状态**：⚠ **部分实现（Phase 9进行中）**

---

### Phase 7 — Graph Path（未实现）

**规划内容**：
- Neo4j独立图层
- 实体/关系/evidence links
- Graph查询回到span_id

**实际实现**：
- ⚠ `llamaindex_runtime/graph/`目录存在
- ⚠ KG backend部分实现（未完整Neo4j集成）

**状态**：⚠ **部分实现**

---

## 当前树状功能完整清单

### 1. **Tree结构相关**（Phase 6）

| 功能 | 文件 | 状态 |
|------|------|------|
| **TreeGenerator** | `registry/tree_generator.py` | ✓ 已实现 |
| **TreeBackendAdapter** | `tree/backend_adapter.py` | ✓ 协议已定义 |
| **PageIndexTreeAdapter** | `tree/pageindex_adapter.py` | ✓ 基础实现 |
| **BackendHit** | `tree/backend_adapter.py` | ✓ 数据结构 |
| **retrieve_tree_hits** | `tree/runtime.py` | ✓ 完整逻辑 |
| **RecursiveTreeTraversalRunner** | `tree/semantic_distribution.py` | ✓ 已实现 |
| **TreeNode schema** | PostgreSQL migration | ✓ 已实现 |

---

### 2. **语义分布与决策**（Phase 6/8）

| 功能 | 文件 | 状态 |
|------|------|------|
| **PersistedTreeSemanticDistributionAdapter** | `tree/semantic_distribution.py` | ✓ 已实现 |
| **BaselineTreeBranchDecisionPolicy** | `tree/semantic_distribution.py` | ✓ 已实现 |
| **HIROEnhancedTreeBranchDecisionPolicy** | `tree/hiro_decision_policy.py` | ✓ HIRO移植 |
| **TreeScoring** | `tree/scoring.py` | ✓ Jaccard评分 |

---

### 3. **命中分布分析**（Phase 8）

| 功能 | 文件 | 状态 |
|------|------|------|
| **NodeHit / AncestorScore** | `analysis/types.py` | ✓ 类型定义 |
| **HitDistributionAnalyzer** | `analysis/analyzer.py` | ✓ CV + Entropy |
| **ExpansionDecision** | `analysis/decision.py` | ✓ 三态决策 |
| **HitCollector** | `analysis/fusion.py` | ✓ 收集逻辑 |

---

### 4. **Hybrid检索**（Phase 9部分）

| 功能 | 文件 | 状态 |
|------|------|------|
| **HybridRetrievalWorkflow** | `workflow/hybrid_retrieval_workflow.py` | ⚠ 部分实现 |
| **UnifiedQueryEntry** | `entrypoints/query.py` | ⚠ 部分实现 |
| **多路收集** | - | ❌ 未完整实现 |
| **expand_by_decision** | - | ❌ 未实现 |

---

### 5. **Graph相关**（Phase 7部分）

| 功能 | 文件 | 状态 |
|------|------|------|
| **GraphBackendAdapter** | `graph/query.py` | ⚠ 部分实现 |
| **KG extraction** | - | ⚠ 未完整Neo4j集成 |

---

### 6. **PageIndex donor移植**

| 功能 | 文件 | 状态 |
|------|------|------|
| **PageIndexTreeAdapter** | `tree/pageindex_adapter.py` | ✓ 已移植 |
| **tree_parser移植** | `tree/pageindex_adapter.py` | ✓ PDF TOC |
| **md_to_tree移植** | `tree/pageindex_adapter.py` | ✓ Markdown |
| **HIRO决策移植** | `tree/hiro_decision_policy.py` | ✓ 已移植 |
| **Workspace管理** | - | ❌ 未移植 |
| **CLI工具** | - | ❌ 未移植 |
| **Agent reasoning** | - | ❌ 未移植 |

---

## 已实现 vs 未实现对比

### ✓ 已完整实现（Phase 6 + 8）

1. **Tree结构生成**：
   - TreeGenerator（heading_path → 树节点）
   - TreeNode schema（PostgreSQL）
   - BackendHit协议

2. **树检索逻辑**：
   - retrieve_tree_hits_from_backend（runtime.py）
   - RecursiveTreeTraversalRunner
   - Embedding-based检索

3. **决策策略**：
   - BaselineTreeBranchDecisionPolicy（dispersion + entropy）
   - HIROEnhancedTreeBranchDecisionPolicy（HIRO移植）

4. **命中分布分析**：
   - HitDistributionAnalyzer
   - CV + Shannon Entropy
   - ExpansionDecision（集中/分散/中等）

---

### ⚠ 部分实现（Phase 7 + 9）

1. **Deep Hybrid**：
   - HybridRetrievalWorkflow框架存在
   - 但多路收集未完整（只有tree + vector）
   - expand_by_decision未实现

2. **Graph path**：
   - graph/query.py存在
   - 但未完整Neo4j集成

---

### ❌ 未实现（PageIndex完整移植）

1. **PageIndex workspace/CLI**：
   - PageIndexClient移植
   - run_pageindex.py CLI
   - 文档持久化

2. **Agent reasoning检索**：
   - OpenAI Agents SDK集成
   - LLM导航树检索

3. **工具函数**：
   - get_document
   - get_document_structure
   - get_page_content

---

## 移植策略建议

### **方案：整体移植PageIndex，融入现有逻辑**

**移植范围**：

```
PageIndex完整移植：
├── PageIndexClient（workspace管理）
│   - 新增功能，不替换现有
│
├── CLI工具（run_pageindex.py）
│   - 新增功能
│
├── 工具函数（get_page_content等）
│   - 新增功能，补充现有
│
└── 检索增强：
    - Agent reasoning（可选backend）
    - 保留runtime.py逻辑（不替换）
    - 保留HIRO决策（不替换）
    - 保留HitDistributionAnalyzer（不替换）
```

**不替换现有逻辑**：
- ❌ runtime.py保留（核心检索）
- ❌ semantic_distribution保留（决策策略）
- ❌ hiro_decision_policy保留（HIRO移植）
- ❌ analyzer保留（命中分布）
- ❌ TreeGenerator保留（Spans→Tree）

**增强部分**：
- ✓ PageIndex workspace/CLI（新增）
- ✓ 预计算embedding（加速runtime.py）
- ✓ Agent reasoning backend（可选）

---

## 工程量重新评估

### **完整移植PageIndex（包含所有功能）**

```
Phase 1：PageIndex workspace/CLI（3天）
  - PageIndexClient移植
  - 文档持久化
  - CLI工具

Phase 2：工具函数移植（2天）
  - get_document
  - get_document_structure
  - get_page_content

Phase 3：Agent reasoning移植（3天）
  - OpenAI Agents SDK集成
  - LLM导航树检索
  - 作为可选backend

Phase 4：配置统一（1天）
  - OpenAI接口 → RuntimeSettings
  - .env参数统一

Phase 5：预计算加速（2天）
  - 预计算embedding
  - 加速runtime.py决策

总计：11天（完整移植）
```

---

## 结论

### **现有树状功能非常完整**

**已实现**：
- ✓ Phase 6完整（Tree Formal Rollup）
- ✓ Phase 8完整（HitDistributionAnalyzer）
- ⚠ Phase 9部分（Deep Hybrid）
- ⚠ Phase 7部分（Graph）

**未实现**：
- ❌ PageIndex完整移植（workspace/CLI/Agent reasoning）

### **移植策略**

**推荐：整体移植PageIndex，不替换现有逻辑**

- **保留**：runtime.py + semantic_distribution + hiro_decision_policy + analyzer
- **新增**：PageIndexClient + CLI + Agent reasoning + 工具函数
- **融合**：预计算加速 + 多backend路由

**工程量**：11天（完整移植所有PageIndex功能）

**不推荐：先移植部分再增加**
- ❌ 会重复工作
- ❌ 不完整移植无法利用PageIndex workspace等基础设施

---

## 决策确认

**是否同意整体移植PageIndex（11天）？**

- ✓ 保留所有现有逻辑（Phase 6/8已完成）
- ✓ 新增PageIndex完整功能
- ✓ 融合增强（预计算 + 多backend）

完整清单见本文档。