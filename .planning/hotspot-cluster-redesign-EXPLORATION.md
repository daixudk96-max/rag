# 热点簇重设计探索任务清单

> **背景**：当前热点选择是「单节点评分竞争」，你的设计意图是「子节点都热的父节点才叫热点」。本清单用于让其他人独立探索，产出决策输入。

---

## 核心问题

**当前实现**：
- HybridClusterHotspotSelector 对每个候选节点计算融合评分（vector + keyword + distribution）
- 选 Top K节点作为热点
- Distribution score 只奖励「有子节点击中」，不要求「所有子节点都击中」

**设计意图**：
- 父节点只有当「一条线上的节点都在排名靠前」才叫热点
- 关键词 + 向量都要热，二者缺一不可

**核心差距**：
- 代码锚点：`semantic_distribution.py:858-1013`（select_hotspots 单节点选TopK）
- 代码锚点：`semantic_distribution.py:1161-1226`（distribution score 不检查覆盖率）

---

## 探索任务（共7个）

### E1: 数据流追踪（确认唯一入口）

**目标**：画出从查询到热点选择的完整数据流，确认distribution是唯一引入子节点信息的入口。

**代码锚点**：
- `runtime.py:251-380` — 构建 vector_candidates, keyword_hits, HotspotSelectionContext
- `semantic_distribution.py:858-1013` — select_hotspots 接收 context
- `semantic_distribution.py:1229-1260` — _compute_fusion_score 权重融合

**产出**：
1. 表格：每个节点有哪些信号、在哪个函数计算、如何进入融合评分
2. 确认：distribution score 是否是唯一能表达「子节点」信息的地方

---

### E2: 是否能拿到完整子节点集？（门禁任务）

**目标**：确认selector调用时，能否获取任意节点的「全部子节点」和「从根到叶的完整路径」。

**代码锚点**：
- `semantic_distribution.py:313` — `_build_parent_to_children`
- `semantic_distribution.py:1016-1051` — `_build_path_to_root`
- `runtime.py:251-254` — node_stats传入selector时是全量还是候选集

**产出**：
1. YES/NO：selector能拿到完整树结构吗？
2. 如果NO：缺少什么数据，需要从哪里传入
3. 伪代码草图：如果要补数据，最小改动是什么

**重要性**：如果拿不到完整子节点集，「覆盖率检查」无法实现。这是实现的前提。

---

### E3: 已有簇代码盘点（死活检查）

**目标**：找出已有的簇相关代码，判断哪些是活的、哪些是废弃的、哪些可复用。

**代码锚点**：
- `semantic_distribution.py:547-568` — ClusterCandidate
- `semantic_distribution.py:1054-?` — `_build_ancestor_clusters`
- `semantic_distribution.py:570-?` — SubtreeHotspotSelector
- Phase 11 新增：ClusterHotspotSelector（如果有）

**产出**：
1. 活代码列表：哪些selector实际被调用（通过 get_hotspot_selector）
2. 死代码列表：哪些定义了但从未调用
3. 可复用评估：死代码是否有正确的簇聚合逻辑可复活

---

### E4: 「簇热点」的精确定义（决策输入）

**目标**：用p6文档树做例子，列出2-3种候选定义，对比优劣。

**背景**：你说了两个场景：
- 「一群节点」：兄弟节点组成的簇
- 「一条线」：从根到叶的路径

**产出**：
对于每种定义，给出：
1. 正式描述（数学化或伪代码）
2. 在p6树上的具体例子（画出来）
3. 实现难度（E2的结果会影响这里）
4. 与「关键词+向量都要热」的一致性

候选定义：
- (A) 直接子节点覆盖率≥θ：父节点的直接子节点中有≥θ比例击中
- (B) 路径全热：从根到叶的每个节点都在候选集里
- (C) 子树密度：子树内候选节点密度≥θ

**重要性**：这是设计决策的核心，其他人探索后你需要拍板。

---

### E5: 选择层 vs 遍历层的职责边界

**目标**：确认改动是否只影响「热点选择」，还是也要改「向下钻取策略」。

**代码锚点**：
- `semantic_distribution.py:69-106` — BaselineTreeBranchDecisionPolicy（决策规则）
- `semantic_distribution.py:1412-1570` — `_traverse_from_node`（递归遍历）
- `runtime.py:241-244` — policy初始化（threshold: dispersion>1.0, entropy>0.5）

**产出**：
1. 当前职责分工图：选择层（选谁当热点）vs 遍历层（从热点向下怎么走）
2. 如果改成「簇热点」，遍历层是否也要改（例如只遍历热子节点）
3. 风险评估：两层联动可能导致的「双重计数」或「死分支」

---

### E6: 测试回归面盘点

**目标**：找出哪些测试锁定「单节点热点」行为，需要改写；哪些是不变的真值测试。

**代码锚点**：
- `tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector.py`

**产出**：
1. 需要改写的测试列表（因为它们假设单节点选TopK）
2. 需要保留的测试列表（因为它们验证不变契约，如p6 DNA区域、glued-query修复）
3. 新测试建议（如果引入覆盖率检查，测试矩阵）

---

### E7: p6树结构现实检查

**目标**：确认「所有子节点都热」在真实树结构上是否现实可行。

**任务**：
1. 从DB或文档统计：每个节点有多少子节点（histogram）
2. 从DB或文档统计：树的深度分布
3. 回答：如果节点平均只有1-2个子节点，「覆盖率阈值」是否还有意义

**产出**：
1. 子节点数量分布表
2. 深度分布表
3. 可行性结论：你的设计意图在真实树上是否能实现

---

## 执行建议

**优先级**：
- E2、E4 是**门禁任务**，先做
- E2 决定是否能拿到完整子节点集（实现前提）
- E4 决定采用哪种「簇热点」定义（设计核心）

**交付格式**：
- 每个任务产出一份 markdown，放到 `.planning/hotspot-cluster-redesign-EXPLORATION/E{N}-{标题}.md`
- 包含代码锚点引用（文件+行号）
- 包含伪代码或数据流图（ASCII即可）

**不需要**：
- 不需要改代码
- 不需要写计划
- 只需要探索+记录事实

---

## 文件锚点汇总（供探索者快速定位）

| 文件 | 关键位置 | 作用 |
|------|----------|------|
| `semantic_distribution.py` | L858-1013 | HybridClusterHotspotSelector.select_hotspots |
| `semantic_distribution.py` | L1161-1226 | _compute_child_distribution_score |
| `semantic_distribution.py` | L1229-1260 | _compute_fusion_score |
| `semantic_distribution.py` | L69-106 | BaselineTreeBranchDecisionPolicy |
| `semantic_distribution.py` | L1412-1570 | _traverse_from_node |
| `semantic_distribution.py` | L547-568 | ClusterCandidate |
| `semantic_distribution.py` | L1054-? | _build_ancestor_clusters |
| `semantic_distribution.py` | L313 | _build_parent_to_children |
| `semantic_distribution.py` | L1016-1051 | _build_path_to_root |
| `runtime.py` | L251-380 | 构建 vector_candidates + keyword_hits + context |
| `runtime.py` | L241-244 | policy初始化 |
| `test_tree_hybrid_hotspot_selector.py` | 全文件 | 测试契约盘点 |

---

## 最终决策点（探索完成后你需要拍板）

1. 采用哪种「簇热点」定义（E4的A/B/C）
2. E2结果是否需要补数据传入
3. 改动范围：只选层 vs 选+遍历双层
4. 是否接受「覆盖率阈值」在真实树上可能无意义（E7）
5. 是否需要新建Phase 12还是直接改Phase 11已提交代码

---

**Created**: 2026-06-22
**Status**: READY_FOR_EXPLORATION
**Next**: 交给其他人执行E1-E7，完成后你拍板决策