# Q18 Traverse 逻辑根因分析报告

## Systematic Debugging Phase 1: Root Cause Investigation

### 错误现象

Q18 检索结果包含 5 个 chunk_id=null 的 hit，这些 hit 的父节点都是文档结构中的关键章节（如 "Phase 2：检索backend增强"、"Token消耗对比" 等），但返回的证据链为空，导致检索质量下降。

### 初步假设

用户提出的设计原理：

| 你期望的设计 | 代码的实际实现 |
|------------|--------------|
| **热点返回逻辑**：hotspot selector 返回父节点时，**至少带一层子节点** | **没有实现**：traverse 从 hotspot node 开始，policy 立即决策 |
| **下钻决策逻辑**：拿到 hotspot + 子节点后，policy 判断是否继续深入 | **混淆了**：policy 有两个接口：<br>- decide_branch_action（在父节点上直接决策）<br>- evaluate_children（在子节点集合上决策） |

**核心矛盾**：设计期望 hotspot 返回时带子节点，但代码却在父节点上立即决策，可能导致父节点本身被返回（不带子节点）。

---

## Phase 1: Root Cause Evidence Chain

通过代码追踪和证据收集，发现 **chunk_id=null 的完整生成路径**：

### 证据链（7 步）

| 步骤 | 代码位置 | 行为 | 影响 |
|------|----------|------|------|
| **1. Hotspot selection** | `runtime.py:340-353` | HybridClusterHotspotSelector 返回父节点（如 "Phase 2"） | ✓ 正确 |
| **2. Traverse start** | `semantic_distribution.py:1661-1663` | 从 hotspot node 开始 traverse | ✓ 正确 |
| **3. Node stats lookup** | `semantic_distribution.py:1716-1721` | 查找父节点的 node_stats | ⚠ 可能失败 |
| **4. Node stats construction** | `semantic_distribution.py:243-244` | **关键过滤**：<br>`if not vectors: continue` | ✗ **父节点被过滤** |
| **5. Traverse returns empty** | `semantic_distribution.py:1720-1721` | node_stats=None → 返回空列表 | ✗ **backend_hits=[]** |
| **6. Fallback triggered** | `runtime.py:374` | backend_hits=[] → `_score_tree_nodes_with_fallback()` | ✗ **走 fallback 路径** |
| **7. Fallback dict** | `runtime.py:487-494` | 返回 dict **没有 chunk_id 字段** | ✗ **chunk_id=null** |

### 关键代码片段

#### Node stats 过滤逻辑（semantic_distribution.py:243-244）

```python
vectors = direct_vectors or subtree_vectors
if not vectors:
    continue  # ← KEY: 父节点既无 direct_vectors 也无 subtree_vectors，被过滤
```

**影响**：父节点不在 `node_stats_list` 中，traverse 在 line 1720 找不到 node_stats，返回空列表。

#### Traverse 空结果处理（semantic_distribution.py:1720-1721）

```python
node_stats = next(
    (stats for stats in node_stats_list if stats["node_id"] == node_id),
    None,
)
if node_stats is None:
    return []  # ← KEY: traverse 返回空列表
```

#### Fallback 路径（runtime.py:374）

```python
if not backend_hits:
    return _score_tree_nodes_with_fallback(...)  # ← KEY: backend_hits=[] 触发 fallback
```

#### Fallback dict 没有 chunk_id（runtime.py:487-494）

```python
scored_nodes.append(
    {
        "node_id": node["node_id"],
        "score": score,
        "text_preview": node.get("summary_text") or node.get("title") or "",
        "heading_path": node.get("heading_path"),
        "span_ids": span_ids_by_node.get(node["node_id"], []),
        # ← KEY: 没有 "chunk_id" 字段
    }
)
```

#### Verification 脚本映射（run_validation.py:347）

```python
normalized = {
    "hit_rank": rank,
    "node_id": hit.get("node_id"),
    "chunk_id": hit.get("chunk_id"),  # ← KEY: fallback dict 没有 chunk_id，get() 返回 None
    ...
}
```

---

## 根因假设验证

### 假设 1：父节点的子节点都是纯 route 节点（没有 leaf chunks）

**验证方法**：检查父节点的 `subtree_vectors` 是否为空。

**诊断脚本**：`phase1_validate_fallback_hypothesis.py`

**结果**：无法验证（Q18 的 node_ids 属于旧 version_id，不在当前 tree_nodes 表中）。

### 假设 2：Fallback 路径缺少 chunk_id 字段

**验证方法**：代码阅读 + 证据链追踪。

**结果**：✓ **已验证**（证据链步骤 6-7）。

---

## 关键发现（Bug 报告）

### Bug #1: Node Stats 过滤导致父节点缺失

**位置**：`semantic_distribution.py:243-244`

**问题描述**：

```python
vectors = direct_vectors or subtree_vectors
if not vectors:
    continue  # ← 父节点被过滤
```

父节点本身无 direct_vectors（自身无 chunk），如果子节点都是纯 route 节点（没有 leaf chunks），则 subtree_vectors=[]，导致父节点被过滤，不在 node_stats_list 中。

**影响**：
- Traverse 找不到父节点的 node_stats → 返回空列表
- Backend_hits=[] → 触发 fallback
- Fallback dict 没有 chunk_id → chunk_id=null

**修复方向**：
- **Option 1**：保留父节点在 node_stats_list 中（即使 vectors=[]），让 policy 决策
- **Option 2**：修改 traverse 在 node_stats=None 时尝试继续（不立即返回空列表）

---

### Bug #2: BaselineTreeBranchDecisionPolicy 缺少 evaluate_children 接口

**位置**：`semantic_distribution.py:70-106`

**问题描述**：

```python
class BaselineTreeBranchDecisionPolicy:
    dispersion_threshold: float
    entropy_threshold: float
    min_support_threshold: int = 1

    def decide_branch_action(...):
        # 只有这一个方法，没有 evaluate_children
```

但 traverse 代码期望 policy 有两个接口：

| 接口 | 用途 | 调用位置 |
|------|------|----------|
| `decide_branch_action` | 在父节点上直接决策（是否 drill_down） | line 1741-1744 |
| `evaluate_children` | 在子节点集合上决策（选择哪个子节点） | line 1784-1809（需 hasattr 检查） |

**影响**：
- Baseline policy 没有 evaluate_children → traverse 走 fallback（line 1857-1895，递归访问所有子节点）
- **混淆了两种决策逻辑**：设计期望"先返回 hotspot + 子节点，再决策"，但代码"在父节点上立即决策"

**修复方向**：
- **Option 1**：Baseline policy 实现 evaluate_children 接口
- **Option 2**：修改 traverse 流程，先返回 hotspot + 子节点，再调用 policy

---

### Bug #3: Fallback dict 缺少 chunk_id 字段

**位置**：`runtime.py:487-494`

**问题描述**：

Fallback 路径返回的 dict 没有 chunk_id 字段，导致 verification 脚本映射时 chunk_id=null。

**影响**：
- Q18 的 chunk_id=null hit 来自 fallback，不是 traverse
- 违反 BackendHit schema（chunk_id 应为 UUID）

**修复方向**：
- **Option 1**：Fallback dict 添加 chunk_id=MISSING_CHUNK_ID（占位符）
- **Option 2**：Fallback 完全移除，强制 traverse 产生有效 QueryHit

---

### Bug #4: Traverse 与 Hotspot Selection 的逻辑混淆

**位置**：`semantic_distribution.py:1741-1762`

**问题描述**：

```python
# Line 1741-1744: 在 hotspot node 上立即调用 policy.decide_branch_action
decision = policy.decide_branch_action(
    node_stats=enriched_node_stats,
    tree_signals=tree_signals,
)

# Line 1749-1762: 如果返回 "keep_parent"，只返回父节点本身
if decision == "keep_parent":
    hits.extend(_build_hits_from_node(...))
```

**违反设计原理**：

| 设计期望 | 代码实际 |
|----------|----------|
| Hotspot 返回时**至少带一层子节点** | Policy 在父节点上立即决策，可能只返回父节点本身 |
| 拿到 hotspot + 子节点后，**再决策是否继续深入** | Policy.decide_branch_action 在父节点上调用（不是在子节点集合上） |

**影响**：
- 用户期望："热点总结节点本身一定是小节点，需要下钻，默认热点返回逻辑就是要带小节点的"
- 实际代码：Policy 可能返回 "keep_parent"（不带子节点）

**修复方向**：
- **Option 1**：Traverse 从 hotspot 开始时，强制返回 hotspot + 一层子节点（无论 policy 决策）
- **Option 2**：修改 Baseline policy 的 decide_branch_action，对 hotspot node 特殊处理（强制 drill_down）

---

## 代码差距总结

| 你期望的设计 | 代码的实际实现 | 影响 |
|------------|--------------|------|
| **热点返回逻辑**：返回 hotspot + 至少一层子节点 | **没有实现**：<br>1. Node stats 过滤父节点（Bug #1）<br>2. Policy 立即决策（Bug #4）<br>3. Baseline 缺少 evaluate_children（Bug #2） | Q18 chunk_id=null（fallback 路径） |
| **下钻决策逻辑**：拿到 hotspot + 子节点后，policy 判断是否继续深入 | **混淆了**：<br>1. Policy.decide_branch_action 在父节点上调用（不是子节点）<br>2. Policy.evaluate_children 存在但 Baseline 未实现<br>3. Traverse 有两个分支（有/无 evaluate_children） | 逻辑不一致，fallback 路径未覆盖 |

---

## Next Steps（Phase 2-4）

### Phase 2: Pattern Analysis

**需要分析**：
1. HIROEnhancedTreeBranchDecisionPolicy 是否有 evaluate_children？
2. 其他 selector（如 pure_cluster、pure_vector）是否有同样问题？
3. ReasoningTreeBackend 是否走 traverse 还是完全不同路径？

### Phase 3: Hypothesis Testing

**验证假设**：
- **假设 A**：Node stats 过滤父节点 → traverse 返回空 → fallback
- **假设 B**：Baseline policy.decide_branch_action 返回 "keep_parent" → 只返回父节点本身

### Phase 4: Implementation

**修复方案**：
- 优先级 1：修复 Bug #3（Fallback dict 添加 chunk_id）
- 优先级 2：修复 Bug #1（保留父节点在 node_stats）
- 优先级 3：修复 Bug #4（Traverse 先返回 hotspot + 子节点）
- 优先级 4：修复 Bug #2（Baseline 实现 evaluate_children）

---

## 附录：关键代码位置

| 文件 | 行号 | 功能 |
|------|------|------|
| `semantic_distribution.py` | 243-244 | Node stats 过滤（Bug #1） |
| `semantic_distribution.py` | 1716-1721 | Traverse node_stats lookup（证据链步骤 3-5） |
| `semantic_distribution.py` | 1741-1762 | Policy.decide_branch_action 调用（Bug #4） |
| `semantic_distribution.py` | 1784-1809 | Policy.evaluate_children 检查（Bug #2） |
| `semantic_distribution.py` | 70-106 | BaselineTreeBranchDecisionPolicy（Bug #2） |
| `semantic_distribution.py` | 266 | is_route_node 定义 |
| `runtime.py` | 340-353 | Hotspot traverse 连接（证据链步骤 1-2） |
| `runtime.py` | 374 | Fallback 触发（Bug #3） |
| `runtime.py` | 487-494 | Fallback dict（Bug #3） |
| `run_validation.py` | 347 | Verification 映射（证据链步骤 7） |