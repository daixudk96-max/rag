# Tree目录完整功能清单（不废弃）

## 已实现的重要逻辑

### 1. **runtime.py** - 树检索主逻辑

```python
def retrieve_tree_hits_from_backend(query_text, version_id, registry, embed_model, decision_policy):
    """完整的树检索逻辑（已实现）"""

    # 1. 加载nodes和spans
    nodes = registry.query_tree_nodes_by_version(version_id)

    # 2. 计算query embedding
    query_embedding = embed_model.get_query_embedding(query_text)

    # 3. 决策策略选择
    if decision_policy == "hiro":
        policy = HIROEnhancedTreeBranchDecisionPolicy(...)
    else:
        policy = BaselineTreeBranchDecisionPolicy(...)

    # 4. 递归树遍历
    runner = RecursiveTreeTraversalRunner()
    query_hits = runner.traverse_tree_for_query(
        version_id, query_embedding, registry, policy, adapter
    )

    # 5. 返回BackendHit
    return backend_hits
```

**关键逻辑**：
- ✓ Embedding-based检索（已有）
- ✓ 决策策略（HIRO + Baseline）
- ✓ 递归树遍历
- ✓ BackendHit输出

---

### 2. **semantic_distribution.py** - 语义分布分析

```python
class PersistedTreeSemanticDistributionAdapter:
    """语义分布适配器（已实现）"""

    def analyze_tree_semantic_distribution(version_id, registry):
        # 分析每个节点的语义分布
        # 计算dispersion（分散度）
        # 计算entropy（熵）
        # 返回统计信息

class BaselineTreeBranchDecisionPolicy:
    """基线决策策略（已实现）"""

    def decide_branch_action(node_stats, tree_signals):
        # 根据dispersion和entropy决定：
        # - drill_down：高分散+高熵 → 往下钻
        # - keep_parent：低分散+低熵 → 保留父节点
        # - prune：中等 → 剪枝
```

**关键逻辑**：
- ✓ Semantic分布分析
- ✓ Dispersion/Entropy计算
- ✓ 决策策略协议

---

### 3. **hiro_decision_policy.py** - HIRO donor移植

```python
class HIROEnhancedTreeBranchDecisionPolicy:
    """HIRO donor移植的决策逻辑（已实现）"""

    def decide_branch_action(node_stats, tree_signals):
        # HIRO双阈值逻辑：
        # delta = query_distance - parent_query_distance
        # should_drill = (delta > delta_threshold) AND (query_distance > selection_threshold)

        # 参数：
        # - selection_threshold: 最小相关性阈值
        # - delta_threshold: 相对父节点的改进阈值
```

**关键逻辑**：
- ✓ HIRO donor移植（已移植）
- ✓ 双阈值决策机制
- ✓ Query distance计算

---

### 4. **scoring.py** - 节点评分

```python
class TreeScoring:
    """节点评分逻辑（已实现）"""

    def score_node(node, query):
        # Jaccard相似度计算
        # Query terms vs summary_text
        # 多term匹配boost（20%加成）

        # 返回：0.0-1.0评分
```

**关键逻辑**：
- ✓ Term frequency评分
- ✓ Jaccard相似度
- ✓ Fallback评分（无embedding时）

---

### 5. **factory.py** - 树节点构建

```python
def build_tree_nodes(markdown_documents, chunk_sizes):
    """构建LlamaIndex树节点（已实现）"""

    # Auto-merging retriever支持
    # 层级节点构建
    # Leaf nodes筛选

def create_auto_merging_retriever(retriever, storage_context):
    """Auto-merging retriever（已实现）"""
```

**关键逻辑**：
- ✓ LlamaIndex集成
- ✓ Auto-merging retriever
- ✓ 层级节点构建

---

### 6. **其他文件**

- **query.py**: TreeRollupQuery（聚合查询）
- **pruning.py**: 树剪枝逻辑
- **backend_adapter.py**: BackendHit协议（已看过）

---

## 功能价值矩阵

| 功能 | 实现状态 | 用途 | 是否废弃 |
|------|----------|------|----------|
| **runtime.py检索逻辑** | ✓ 完整 | 树检索主流程 | ❌ **不废弃，核心逻辑** |
| **semantic_distribution** | ✓ 完整 | 语义分布分析 | ❌ **不废弃，决策依据** |
| **hiro_decision_policy** | ✓ 完整 | HIRO donor移植 | ❌ **不废弃，高级策略** |
| **scoring.py** | ✓ 完整 | 节点评分 | ❌ **不废弃，fallback逻辑** |
| **factory.py** | ✓ 完整 | LlamaIndex集成 | ⚠ **可选保留** |
| **TreeGenerator** | ✓ 完整 | Spans→Tree | ❌ **不废弃，vector backend依赖** |
| **PageIndexTreeAdapter** | ⚠ 基础 | PDF/Markdown直接树 | ✓ **改造增强** |

---

## 关键发现：已有完整的树检索逻辑！

**runtime.py已经实现了**：
```python
retrieve_tree_hits_from_backend():
  1. 加载nodes
  2. 计算query embedding
  3. 选择决策策略（HIRO/Baseline）
  4. 递归树遍历
  5. 返回BackendHit
```

**这已经是你想要的"聚类检索"逻辑**：

- ✓ Embedding计算（已有）
- ✓ 决策策略（已有HIRO + Baseline）
- ✓ 递归导航（已有RecursiveTreeTraversalRunner）
- ✓ BackendHit输出（已有）

---

## PageIndex改造的正确方向

### **不是替换现有逻辑，而是增强**

**当前runtime.py逻辑**：
```
Query → Embedding → 决策策略 → 递归遍历 → BackendHit
```

**PageIndex改造应该**：
```
PageIndex完整功能：
  ├── index_tree增强：
  │   - PageIndex workspace/CLI（新增）
  │   - 预计算embedding（新增，加速runtime.py）
  │
  └── retrieve_tree_hits增强：
      - 使用runtime.py已有逻辑（保留）
      - 增加聚类索引（预计算，加速决策）
      - 增加Agent reasoning（可选backend）
```

---

## 整合方案：保留 + 增强

### Phase 1：PageIndex workspace/CLI（3天）

**新增功能**：
- PageIndexClient移植（workspace管理）
- CLI工具（run_pageindex.py）
- get_page_content（页面提取）

**保留功能**：
- runtime.py检索逻辑（不改）
- semantic_distribution（不改）
- hiro_decision_policy（不改）

---

### Phase 2：预计算加速（3天）

**新增功能**：
```python
class PageIndexTreeAdapter:
    def index_tree(self, source_path, version_id, registry):
        # 1. PageIndex树提取（已有）
        nodes = md_to_tree(source_path)

        # 2. 预计算embedding（新增）
        embeddings = compute_embeddings(nodes)
        registry.write_node_embeddings(embeddings)

        # 3. 预计算semantic distribution（新增）
        distribution = analyze_semantic_distribution(nodes)
        registry.write_semantic_distribution(distribution)

    def retrieve_tree_hits(self, query_text, version_id, registry):
        # 直接调用runtime.py已有逻辑（不改）
        # 但registry已有预计算数据（加速）
        return retrieve_tree_hits_from_backend(
            query_text,
            version_id,
            registry,
            embed_model=embed_model,
            decision_policy="hiro"
        )
```

**效果**：
- runtime.py逻辑不变（保留）
- 但registry有预计算数据（加速决策）

---

### Phase 3：多backend路由（2天）

**新增功能**：
```python
# 配置驱动选择backend
TREE_BACKEND=pageindex  # pageindex | runtime | hybrid

# runtime backend：使用runtime.py现有逻辑
# pageindex backend：PageIndex完整功能 + runtime.py逻辑
# hybrid backend：两者融合
```

---

## 总结：不废弃，增强整合

### **核心结论**

1. ❌ **不废弃现有逻辑**：
   - runtime.py检索逻辑（核心，保留）
   - semantic_distribution（决策依据，保留）
   - hiro_decision_policy（HIRO移植，保留）
   - scoring.py（fallback评分，保留）

2. ✓ **PageIndex改造是增强**：
   - 新增：workspace/CLI
   - 新增：预计算加速
   - 保留：runtime.py逻辑不变

3. ✓ **TreeGenerator保留**：
   - Vector backend依赖
   - Spans→Tree路径

### **正确架构**

```
树状检索架构：
├── runtime.py（核心逻辑，保留）
│   ├── retrieve_tree_hits_from_backend
│   ├── RecursiveTreeTraversalRunner
│   ├── 决策策略选择
│
├── PageIndexTreeAdapter（增强层）
│   ├── index_tree增强：
│   │   - PageIndex workspace（新增）
│   │   - 预计算embedding（新增）
│   │   - 预计算distribution（新增）
│   │
│   └── retrieve_tree_hits：
│       - 调用runtime.py逻辑（不变）
│       - registry有预计算数据（加速）
│
├── semantic_distribution（决策依据，保留）
├── hiro_decision_policy（HIRO移植，保留）
├── scoring.py（fallback评分，保留）
└── TreeGenerator（Spans→Tree，保留）
```

---

## 下一步：PageIndex增强改造

**立即行动**：
1. PageIndex workspace/CLI移植（Phase 1）
2. 预计算embedding加速（Phase 2）
3. **保留runtime.py等现有逻辑**

**不废弃任何功能**，PageIndex是在现有逻辑基础上增加功能层。