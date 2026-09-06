# Traverse 逻辑重设计：实现 Hotspot 返回真实文档内容（Waypoint + Child Chunks）

## Context（为什么做这件事）

Q18 检索结果返回 chunk_id=null 的空证据 hit，根因分析发现 traverse 逻辑存在设计缺陷：

**用户期望的设计原理**：
- "热点总结节点本身一定是小节点，需要下钻"
- "默认热点返回逻辑就是要带小节点的"
- "至少会出一层子节点，以便根据这层子节点判断是否获得了足够的信息"

**代码实际实现**：
- Traverse 从 hotspot node 开始，policy.decide_branch_action 在父节点上立即调用
- 可能返回 "keep_parent"，只返回父节点本身（不带子节点）
- 父节点可能是纯 route node（自身无 chunk），导致 fallback 触发
- Fallback dict 缺少 chunk_id 字段 → chunk_id=null

**核心矛盾**：两种逻辑被混淆了：
1. **热点返回逻辑**（应该返回 hotspot + 子节点）→ **没有实现**
2. **下钻决策逻辑**（应该在子节点层面决策）→ **在父节点上立即决策**

用户已确认的设计意图（AskUserQuestion 结果）：
- **Hotspot 返回内容**：返回 hotspot 本身（作为 waypoint）+ 一层子节点的 chunks（真实证据）
- **Policy 决策时机**：拿到 hotspot + 子节点后，在子节点层面决策（不是 hotspot 父节点上）

---

## 关键技术发现（Phase 1-2 探索结果）

### ReasoningTreeBackend（对比参考）

- **不返回子节点**：只返回 LLM 直接判定的节点
- **LLM-as-navigator**：没有"至少一层子节点"的逻辑
- **可能返回 route nodes**：如果 LLM 选中 route node，可能 chunk_id 缺失

### HybridClusterHotspotSelector（当前 hotspot 选择器）

- **返回 SubtreeHotspot**（node_id + metadata），不包含 chunks
- **通常选择父节点**（可能是 route node）
- **子节点 chunks 在 traverse 阶段获取**

### Node Stats 过滤（Bug #1）

- `semantic_distribution.py:243-244`：父节点可能被过滤（vectors=[]）
- 导致 traverse 找不到 node_stats → 返回空列表 → 触发 fallback

### Fallback 机制（直接根因）

- `runtime.py:374`：backend_hits=[] 触发 fallback
- `runtime.py:487-494`：Fallback dict **没有 chunk_id 字段**
- Verification 脚本映射 → chunk_id=null（违反 BackendHit schema）

### Policy 接口缺失（Bug #2）

- `BaselineTreeBranchDecisionPolicy` **没有 evaluate_children 接口**
- `HIROEnhancedTreeBranchDecisionPolicy` **有 evaluate_children**（hiro_decision_policy.py:110-157）
- Traverse 有两个分支（有/无 evaluate_children），Baseline 走 fallback 递归

### QueryHit Schema（约束）

- `semantic_distribution.py:487`：chunk_id: UUID（不可为 None）
- **MISSING_CHUNK_ID = UUID(int=0)**（runtime.py:86）已存在，可作为占位符

---

## 实现方案（Phase 2 设计结果）

### 方案概述

**核心策略**：新增 `_traverse_hotspot_with_children` 函数，实现"hotspot 强制返回 waypoint + 一层子节点 chunks"

**设计要点**：
1. Hotspot traversal 检测：判断当前 traverse 是 hotspot start（不是 root start）
2. 强制 drill_down：从 hotspot node 直接收集一层子节点（不调用 policy）
3. Waypoint hit：hotspot 本身返回 waypoint（chunk_id=MISSING_CHUNK_ID，作为导航标记）
4. Evidence hits：子节点返回真实 chunks（chunk_id 来自子节点的 chunk_ids）
5. Policy 在子节点层面决策：调用 evaluate_children（如果有）判断是否继续深入

---

### Phase 1：修改 traverse 入口逻辑

**文件**：`llamaindex_runtime/tree/semantic_distribution.py`

**修改位置**：Line 1627-1690（RecursiveTreeTraversalRunner.traverse_tree_for_query）

**新增逻辑**：

```python
# Line 1640（在 start_nodes 解析后）
is_hotspot_traversal = (
    hotspot_node_id is not None
    and start_node_id is not None
    and hotspot_node_id == start_node_id
)

if is_hotspot_traversal:
    # Hotspot special handling: force one-level drill-down
    return self._traverse_hotspot_with_children(
        hotspot_node=start_nodes[0] if start_nodes else None,
        version_id=version_id,
        query_embedding=query_embedding,
        node_stats_list=node_stats_list,
        node_by_id=node_by_id,
        tree_signals=tree_signals,
        policy=policy,
        registry=registry,
        doc_id=doc_id,
        chunk_to_span_ids=chunk_to_span_ids,
        max_depth=max_depth,
    )

# 原有的 root traversal 逻辑保持不变
```

---

### Phase 2：新增 `_traverse_hotspot_with_children` 函数

**文件**：`llamaindex_runtime/tree/semantic_distribution.py`

**插入位置**：Line 1690 之后（新增函数）

**函数逻辑**：

```python
def _traverse_hotspot_with_children(
    self,
    *,
    hotspot_node: dict[str, Any] | None,
    version_id: UUID,
    query_embedding: list[float],
    node_stats_list: list[dict[str, Any]],
    node_by_id: dict[UUID, dict[str, Any]],
    tree_signals: dict[str, Any],
    policy: TreeBranchDecisionPolicy,
    registry: SemanticDistributionRegistry,
    doc_id: UUID,
    chunk_to_span_ids: dict[UUID, list[UUID]],
    max_depth: int | None,
) -> list[QueryHit]:
    """Hotspot traversal: return hotspot waypoint + one-level child chunks.

    Design principle: "热点总结节点本身一定是小节点，需要下钻，默认热点返回逻辑就是要带小节点的"

    Workflow:
    1. Collect one-level children (direct children, NOT descendants)
    2. Build waypoint hit from hotspot node (navigation marker, chunk_id=MISSING_CHUNK_ID)
    3. Build evidence hits from children with real chunk_ids
    4. Apply policy.evaluate_children on children (if available) to decide further drilling
    """
    if hotspot_node is None:
        return []

    hotspot_node_id = hotspot_node["node_id"]

    # Step 1: Collect one-level children
    child_nodes = [
        node_by_id[child_id]
        for child_id in node_by_id
        if node_by_id[child_id].get("parent_node_id") == hotspot_node_id
    ]

    if not child_nodes:
        # Edge case: hotspot has no children - return waypoint only
        return _build_waypoint_hit(
            node=hotspot_node,
            version_id=version_id,
            doc_id=doc_id,
            chunk_to_span_ids=chunk_to_span_ids,
            hotspot_node_id=hotspot_node_id,
            navigation_node_ids=(hotspot_node_id,),
        )

    # Step 2: Find stats for children (skip route nodes without stats)
    child_stats_with_similarity: list[dict[str, Any]] = []
    for child_node in child_nodes:
        child_node_stats = next(
            (stats for stats in node_stats_list if stats["node_id"] == child_node["node_id"]),
            None,
        )

        if child_node_stats is not None:
            child_prototype = child_node_stats.get("prototype_embedding") or child_node_stats.get("centroid", [])
            if child_prototype:
                child_similarity = _cosine_similarity(query_embedding, child_prototype)
                child_stats_with_similarity.append({
                    **child_node_stats,
                    "query_distance": 1.0 - child_similarity,
                    "similarity": child_similarity,
                    "parent_query_distance": None,  # Not applicable for hotspot level
                })

    # Step 3: Build waypoint hit (navigation marker)
    waypoint_hits = _build_waypoint_hit(
        node=hotspot_node,
        version_id=version_id,
        doc_id=doc_id,
        chunk_to_span_ids=chunk_to_span_ids,
        hotspot_node_id=hotspot_node_id,
        navigation_node_ids=(hotspot_node_id,),
    )

    # Step 4: Build evidence hits from children with direct chunks
    evidence_hits: list[QueryHit] = []
    for child_stats in child_stats_with_similarity:
        child_chunk_ids = child_stats.get("chunk_ids", [])
        if child_chunk_ids:  # Only evidence-bearing children
            evidence_hits.extend(
                _build_hits_from_node(
                    node_stats=child_stats,
                    version_id=version_id,
                    doc_id=doc_id,
                    similarity=child_stats["similarity"],
                    chunk_to_span_ids=chunk_to_span_ids,
                    hotspot_node_id=hotspot_node_id,
                    navigation_node_ids=(hotspot_node_id, child_stats["node_id"]),
                    drill_depth=1,
                )
            )

    # Step 5: Policy decision on children (if evaluate_children available)
    if hasattr(policy, "evaluate_children") and child_stats_with_similarity:
        child_result = policy.evaluate_children(
            child_stats=child_stats_with_similarity,
            tree_signals=tree_signals,
        )

        aggregate_decision = child_result.get("decision")
        selected_child_id = child_result.get("selected_child_id")

        if aggregate_decision == "drill_down" and selected_child_id is not None:
            # Recursively drill into selected child
            selected_child_node = node_by_id.get(selected_child_id)
            if selected_child_node:
                further_hits = self._traverse_from_node(
                    node=selected_child_node,
                    version_id=version_id,
                    query_embedding=query_embedding,
                    node_stats_list=node_stats_list,
                    node_by_id=node_by_id,
                    tree_signals=tree_signals,
                    policy=policy,
                    registry=registry,
                    doc_id=doc_id,
                    chunk_to_span_ids=chunk_to_span_ids,
                    parent_query_distance=None,
                    navigation_node_ids=(hotspot_node_id, selected_child_id),
                    hotspot_node_id=hotspot_node_id,
                    current_depth=2,
                    max_depth=max_depth,
                )
                evidence_hits.extend(further_hits)

    # Return waypoint + evidence hits
    return waypoint_hits + evidence_hits
```

---

### Phase 3：新增 `_build_waypoint_hit` 函数

**文件**：`llamaindex_runtime/tree/semantic_distribution.py`

**插入位置**：Line 1971 之后（新增函数）

**函数逻辑**：

```python
def _build_waypoint_hit(
    *,
    node: dict[str, Any],
    version_id: UUID,
    doc_id: UUID,
    chunk_to_span_ids: dict[UUID, list[UUID]],
    hotspot_node_id: UUID | None,
    navigation_node_ids: tuple[UUID, ...],
) -> list[QueryHit]:
    """Build waypoint hit (navigation marker) from hotspot node.

    Waypoint hit represents a traversal path node, not real evidence content.
    Uses MISSING_CHUNK_ID as placeholder (runtime.py:86).
    """
    from llamaindex_runtime.tree.runtime import MISSING_CHUNK_ID

    node_id = node["node_id"]

    # Waypoint hit has:
    # - Real node_id (navigation provenance)
    # - MISSING_CHUNK_ID (placeholder, not real content)
    # - hotspot_node_id (hotspot provenance)
    # - navigation_node_ids (path provenance)

    # Placeholder span_id (deterministic from node_id)
    span_id_placeholder = UUID(int=node_id.int & (2**63 - 1))

    return [
        QueryHit(
            doc_id=doc_id,
            version_id=version_id,
            span_id=span_id_placeholder,
            chunk_id=MISSING_CHUNK_ID,
            node_id=node_id,
            similarity_score=0.0,  # Waypoint has no similarity (navigation only)
            hotspot_node_id=hotspot_node_id,
            navigation_node_ids=navigation_node_ids,
            drill_depth=0,  # Waypoint is depth 0 (hotspot itself)
        )
    ]
```

---

### Phase 4：Baseline policy 新增 `evaluate_children` 接口

**文件**：`llamaindex_runtime/tree/semantic_distribution.py`

**修改位置**：Line 70-106（BaselineTreeBranchDecisionPolicy 类）

**新增方法**：

```python
def evaluate_children(
    self,
    *,
    child_stats: list[dict[str, Any]],
    tree_signals: dict[str, Any],
) -> dict[str, Any]:
    """Aggregate per-child baseline decisions into a selection result.

    Baseline strategy: select child with best similarity (simple heuristic).
    Does NOT implement HIRO's distance+delta logic.
    """
    if not child_stats:
        return {
            "decision": "prune",
            "selected_child_id": None,
            "child_decisions": {},
        }

    # Select child with highest similarity (lowest query_distance)
    best_child = min(child_stats, key=lambda c: c.get("query_distance", 1.0))
    selected_child_id = best_child.get("node_id")

    # Check if best child meets baseline thresholds
    best_decision = self.decide_branch_action(
        node_stats=best_child,
        tree_signals=tree_signals,
    )

    if best_decision == "keep_parent":
        return {
            "decision": "keep_parent",
            "selected_child_id": None,
            "child_decisions": {selected_child_id: "keep_parent"},
        }

    if best_decision == "drill_down":
        return {
            "decision": "drill_down",
            "selected_child_id": selected_child_id,
            "child_decisions": {selected_child_id: "drill_down"},
        }

    return {
        "decision": "prune",
        "selected_child_id": None,
        "child_decisions": {selected_child_id: "prune"},
    }
```

**注意**：HIRO policy 已有 evaluate_children（hiro_decision_policy.py:110-157），无需修改。

---

### Phase 5：Fallback dict 添加 chunk_id 字段（可选修复）

**文件**：`llamaindex_runtime/tree/runtime.py`

**修改位置**：Line 487-494（_score_tree_nodes_with_fallback 函数）

**修改代码**：

```python
scored_nodes.append({
    "node_id": node["node_id"],
    "chunk_id": MISSING_CHUNK_ID,  # NEW: Add placeholder chunk_id
    "score": score,
    "text_preview": node.get("summary_text") or node.get("title") or "",
    "heading_path": node.get("heading_path"),
    "span_ids": span_ids_by_node.get(node["node_id"], []),
})
```

**说明**：这是兜底修复（如果 traverse 仍然返回空，fallback 至少提供占位符 chunk_id）。但 Phase 1-4 修复后，fallback 触发频率应大幅降低。

---

## 关键修改文件清单

| 文件 | 行号 | 修改内容 |
|------|------|----------|
| `semantic_distribution.py` | 1640 | 新增 hotspot traversal 检测逻辑 |
| `semantic_distribution.py` | 1690+ | 新增 `_traverse_hotspot_with_children` 函数（~70 行） |
| `semantic_distribution.py` | 1971+ | 新增 `_build_waypoint_hit` 函数（~30 行） |
| `semantic_distribution.py` | 70-106 | Baseline policy 新增 `evaluate_children` 方法（~30 行） |
| `runtime.py` | 487-494 | Fallback dict 添加 `chunk_id` 字段（可选） |

---

## 数据结构变更

### Waypoint hit vs Evidence hit 区分

| 字段 | Waypoint hit | Evidence hit |
|------|--------------|--------------|
| chunk_id | MISSING_CHUNK_ID (UUID(int=0)) | Real UUID (from child chunks) |
| span_id | Placeholder (synthetic) | Real UUID (from chunk_to_span_ids) |
| similarity_score | 0.0 | Computed cosine similarity |
| drill_depth | 0 (hotspot itself) | >= 1 (one level down) |
| node_id | Hotspot node | Child node |

---

## 验证方案

### 单元测试

**新增测试文件**：`tests/llamaindex_runtime/test_hotspot_traversal_logic.py`

**测试场景**：

1. **Hotspot traversal 返回 waypoint + child chunks**
   - Mock hotspot selector 返回父节点
   - Verify traverse 返回 waypoint（chunk_id=MISSING_CHUNK_ID）+ evidence hits（真实 chunk_id）

2. **Hotspot 无子节点**
   - Mock hotspot 无 children
   - Verify traverse 只返回 waypoint hit

3. **Hotspot 子节点都是 route nodes**
   - Mock children 无 chunk_ids
   - Verify traverse 返回 waypoint only（无 evidence hits）

4. **Baseline policy evaluate_children**
   - Verify Baseline 选择最佳 similarity child
   - Verify 决策逻辑正确（keep_parent / drill_down / prune）

5. **HIRO policy evaluate_children**
   - Verify HIRO 距离+delta 逻辑在 child 层面应用
   - Verify selected_child 决策

### 集成测试

**修改现有测试**：`tests/llamaindex_runtime/test_tree_semantic_hotspot.py`

**新增场景**：验证 hotspot traversal 返回 waypoint + child chunks

### E2E 验证（Q18 特定）

**验证脚本**：重新运行 `verification/real-document-validation-2026-06-23/run_validation.py`

**验证点**：
1. Q18 的 chunk_id != null（至少有 waypoint 的 MISSING_CHUNK_ID）
2. 如果 hotspot 有子节点，返回真实 evidence chunks
3. 证据链报告：zero_chunk_hits 减少，chunk_id_present_rate 提升

---

## 验证命令

```bash
# Unit tests
pytest tests/llamaindex_runtime/test_hotspot_traversal_logic.py -v

# Integration tests
pytest tests/llamaindex_runtime/test_tree_semantic_hotspot.py::TestRecursiveTreeTraversalRunnerStartNodeId -v

# E2E validation (Q18 specific)
python verification/real-document-validation-2026-06-23/run_validation.py --phase retrieve
```

---

## 风险与缓解

### 风险 1：Placeholder span_id 的影响

**问题**：Waypoint hit 使用 synthetic span_id（可能不在 vector_chunks 表中）

**缓解**：
- EvidenceContentResolver 应跳过 span_id 不存在的情况（使用 fallback_text）
- Verification 脚本映射时检查 span_id 是否有效

### 风险 2：Hotspot 无 node_stats

**问题**：如果 hotspot 本身被 node stats 过滤，无法构建 waypoint hit

**缓解**：
- `_build_waypoint_hit` 不依赖 node_stats（直接使用 tree_nodes 数据）
- 即使无 node_stats，也能返回 waypoint（作为纯导航标记）

### 风险 3：Baseline evaluate_children 简化逻辑

**问题**：Baseline 选择最佳 similarity child，可能不如 HIRO 的距离+delta 逻辑精准

**缓解**：
- Baseline 是简化版本（快速修复）
- 用户可切换到 HIRO policy 使用完整逻辑
- 不影响 waypoint + child chunks 的基本返回机制

---

## 不修复的 Bug（设计决策）

### Bug #1: Node Stats 过滤逻辑（保留）

**原因**：
- Hotspot traversal 通过 `_traverse_hotspot_with_children` 绕过 node_stats 缺失问题
- Hotspot 节点本身不依赖 node_stats（waypoint 返回）
- 避免引入 placeholder embedding 的复杂度

### Bug #4: Traverse 与 Hotspot Selection 的逻辑混淆（已解决）

**解决方案**：Phase 1-4 实现了用户期望的设计（hotspot 返回 waypoint + child chunks）

---

## 预期成果

1. **Q18 的 chunk_id 不再是 null**（至少有 waypoint 的 MISSING_CHUNK_ID）
2. **如果 hotspot 有子节点，返回真实 evidence chunks**（不是占位符）
3. **Policy 在子节点层面决策**（符合用户期望）
4. **Evidence chain 质量提升**（zero_chunk_hits 减少）
5. **设计原理实现**："热点总结节点本身一定是小节点，需要下钻，默认热点返回逻辑就是要带小节点的"

---

## Caveats

- **Waypoint hit 不是真实文档内容**：chunk_id=MISSING_CHUNK_ID，仅作为导航标记
- **Evidence hits 必须有真实 chunk_id**：从子节点的 chunk_ids 获取
- **Policy 决策依赖 evaluate_children 接口**：Baseline 简化逻辑，HIRO 完整逻辑
- **Fallback 仍然可能触发**：极端情况（hotspot 无 children + traverse 失败），但频率大幅降低

---

## 相关文档

- **根因分析**：`verification/real-document-validation-2026-06-23/BUG_ANALYSIS_Q18_TRAVERSE_LOGIC.md`
- **Plan 文件**：`C:\Users\daixu\.claude\plans\prancy-napping-nest.md`
- **验证产物目录**：`verification/real-document-validation-2026-06-23/`

---

## 时间戳

**创建时间**：2026-06-24
**状态**：Approved（已通过 Plan Mode 审批）
**下一步**：实施 Phase 1-5 代码修改