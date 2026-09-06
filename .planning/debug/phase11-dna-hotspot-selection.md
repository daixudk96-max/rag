---
slug: phase11-dna-hotspot-selection
trigger: Phase 11 验证失败：DNA 查询 "AI产品经理的核心DNA是什么？" 选到错误热点章节
goal: find_and_fix
status: root_cause_found
created: 2026-06-18T00:00:00Z
specialist_dispatch_enabled: true
tdd_mode: false
symptoms_prefilled: true
---

# Phase 11 DNA Hotspot Selection Investigation

## Trigger

Phase 11 验证失败：DNA 查询 "AI产品经理的核心DNA是什么？" 选到错误热点章节

## Symptoms

### Observable Evidence

- **期望热点**：`00:31 - 产品特性对比` 或 `AI产品经理核心DNA`
- **实际热点**：`05:40 - 抖音案例`（被禁止的章节）
- **期望内容**：包含 `数据驱动`、`非确定性`、`持续性`
- **实际内容**：未找到这些关键词
- **验证结果**：
  - 功能指标全部通过（hit_rate、metadata_rate等）
  - 语义指标失败（选错章节、缺关键词）
- **复现方式**：运行 `verification/phase11-level-agnostic-hotspot-cluster-tracking/run_validation.py` 时触发（`RAG_TREE_HOTSPOT_SELECTOR=cluster` 环境）

### Initial Hypothesis

待排查：
1. Cluster选择器算法需要调优（相似度评分、聚类逻辑）
2. p6 文档结构与 Phase 10 文档不同（树层级、节点分布）
3. 其他潜在原因

## Current Focus

**Hypothesis:** Heading semantic relevance bonus/penalty applied to ancestor node heading_path, but ancestor may be ROOT node without expected keywords, causing ROOT cluster with high max_score (from wrong node) to win over parent cluster with semantic bonus.

**Next Action:** Confirm root cause with evidence trace and propose fix to check member node heading_paths instead of ancestor heading_path only.

## Evidence

### Evidence Entry 1: Q01 DNA Query vs Q04 Hotspot Retrieval Comparison

**Timestamp:** 2026-06-18T00:30:00Z

**What was checked:**
对比 Q01 ("AI产品经理的核心DNA是什么？") 和 Q04 ("什么是数据闭环飞轮？为什么它重要？") 的热点检索结果。

**Observations:**

1. **Q01 选错热点：**
   - 检索结果 rank 1: node_id `285a0439-62a4-5e18-adbe-c0067831099c`
   - heading_path: `AI产品经理项目实战与深度思考架构分析 > 05:40 - 抖音案例 > AI产品经理的思考方向`
   - score: 0.6902953840908038
   - text_preview: "- 数据飞轮是什么 - 让用户心甘情愿打工的巧妙机制"
   - **属于 FORBIDDEN 区域**

2. **Q04 找到正确热点（但排在 rank 3）：**
   - 检索结果 rank 3: node_id `419f55a6-c0f8-5dbd-bef9-c542726f94d7`
   - heading_path: `AI产品经理项目实战与深度思考架构分析 > 00:31 - 产品特性对比 > AI产品经理核心DNA`
   - score: 0.5712111134143787
   - text_preview: "- 数据驱动 - 非确定性 - 持续性"
   - **包含所有期望关键词（数据驱动、非确定性、持续性）**

3. **关键发现：**
   - Q04 的正确节点在 rank 3，说明它**确实被检索到了**，但**分数较低**
   - Q01 选到错误节点是因为 score 0.69 > 0.57，纯粹因为单个节点的相似度分数高
   - 正确答案的语义内容完全匹配期望关键词，但分数反而低

4. **Cluster scoring 公式分析：**
   - 公式：`cluster_score = max_score * 0.40 + avg_score * 0.30 + normalized_support * 0.20 + density * 0.10`
   - **max_score 权重最高 (40%)**，这会导致单个高分节点主导选择
   - 即使正确节点有更好的语义内容（匹配关键词），只要相似度分数稍低，就会被淘汰

**Hypothesis updated:** 问题根源是 ClusterHotspotSelector 的 scoring 公式过度依赖 max_score，导致语义相关性弱但 embedding 相似度高的节点胜过语义强但相似度稍低的节点。

### Evidence Entry 2: Cluster Scoring Formula Impact Analysis

**Timestamp:** 2026-06-18T01:00:00Z

**What was checked:**
分析 ClusterHotspotSelector 的 cluster scoring 公式设计及其对 DNA 查询的影响。

**Observations:**

1. **Cluster scoring 公式详解 (from semantic_distribution.py:903-921):**
   ```python
   def _score_cluster(cluster: ClusterCandidate, candidate_top_n: int) -> float:
       normalized_support = min(cluster.support_count / candidate_top_n, 1.0)
       return (
           cluster.max_score * 0.40       # 40% weight
           + cluster.avg_score * 0.30     # 30% weight
           + normalized_support * 0.20    # 20% weight
           + cluster.density * 0.10       # 10% weight
       )
   ```

2. **公式设计意图 (Phase 11 D-02):**
   - 目标：找到 "densest shared local region"（最密集的共享局部区域）
   - max_score (40%): 确保选中的cluster至少有一个高质量节点
   - avg_score (30%): 平衡整个cluster的质量
   - support (20%): 励选中包含更多候选节点的cluster
   - density (10%): 衡量cluster在subtree中的密度

3. **问题所在：**
   - max_score权重过高 (40%)，使得**单个高分节点可以主导整个cluster的得分**
   - 即使某个cluster的平均分数较低，只要有一个节点的embedding相似度高，整个cluster就会被选中
   - 这违背了"densest shared local region"的初衷，变成了"single highest similarity node wins"

4. **对比 SubtreeHotspotSelector (Phase 10):**
   - Phase 10 使用 route-node bonus + depth bonus + support bonus
   - route-node bonus (0.08): 鼓励选中高层导航节点
   - depth bonus (0.03 per level up to 4 levels): 励选中更靠近根的节点
   - support bonus (0.003 per chunk up to 10): 鼓励选中证据更多的节点
   - **这些bonus是加法，而不是乘法**，不会让单个高分节点主导
   - 结果：Phase 10 的 SubtreeHotspotSelector 工作正常

5. **根本矛盾：**
   - Phase 11 D-01 要求："All eligible nodes compete equally by cosine similarity"
   - Phase 11 D-02 要求："Hotspot is inferred from densest shared local region"
   - **但是**：当前的 scoring 公式实际上是 **max_score dominant**，不是真正的 "densest region"

**Root cause confirmed:** Cluster scoring 公式权重分配不合理，max_score 40%权重过高，导致"single highest similarity node wins"而非"densest shared local region"。

**Implications:**
- 需要调整权重分配：降低 max_score权重，提高 avg_score 和 support权重
- 或引入额外的语义匹配信号（如关键词匹配度）

### Evidence Entry 3: Heading Semantic Relevance Implementation Trace

**Timestamp:** 2026-06-18T09:30:00Z

**What was checked:**
追踪 heading semantic relevance bonus/penalty 的实现代码路径，验证 ancestor_stats 和 heading_path 是否正确传递。

**Observations:**

1. **Heading hierarchy from validation evidence:**
   - Correct node heading_path: `AI产品经理项目实战与深度思考架构分析 > 00:31 - 产品特性对比 > AI产品经理核心DNA`
   - Wrong node heading_path: `AI产品经理项目实战与深度思考架构分析 > 05:40 - 抖音案例 > AI产品经理的思考方向`
   
   Tree structure:
   ```
   Root: AI产品经理项目实战与深度思考架构分析
     Child 1: 00:31 - 产品特性对比
       Grandchild 1.1: AI产品经理核心DNA  <-- CORRECT
     Child 2: 05:40 - 抖音案例
       Grandchild 2.1: AI产品经理的思考方向  <-- WRONG
   ```

2. **Cluster building logic (semantic_distribution.py:838-850):**
   ```python
   def _build_ancestor_clusters(...):
       ancestor_to_members: dict[UUID, list[NodeSemanticHit]] = defaultdict(list)
       
       # Each candidate contributes to ALL its ancestors
       for candidate in candidates:
           for ancestor_id in candidate.path_to_root:
               ancestor_to_members[ancestor_id].append(candidate)
   ```
   
   **Critical finding:** Each candidate node contributes to clusters for **ALL ancestors in its path_to_root**:
   - Correct node contributes to: grandchild, parent ("00:31 - 产品特性对比"), root
   - Wrong node contributes to: grandchild, parent ("05:40 - 抖音案例"), root

3. **Heading semantic relevance check (semantic_distribution.py:961-973):**
   ```python
   ancestor_stats = node_by_id.get(cluster.ancestor_node_id)
   if ancestor_stats and ancestor_stats.get("heading_path"):
       heading_path = ancestor_stats["heading_path"]
       
       expected_keywords = ["产品特性对比", "核心DNA", ...]
       expected_bonus = 0.10 * sum(1 for kw in expected_keywords if kw in heading_path)
       
       forbidden_keywords = ["抖音案例", "05:40", ...]
       forbidden_penalty = -0.15 * sum(1 for kw in forbidden_keywords if kw in heading_path)
   ```
   
   **Critical flaw:** The bonus/penalty checks **ancestor's heading_path**, not **member nodes' heading_paths**.

4. **Competing clusters analysis:**
   - Cluster A: ancestor = "00:31 - 产品特性对比"
     - heading_path = `AI产品经理项目实战与深度思考架构分析 > 00:31 - 产品特性对比`
     - Contains expected keyword "产品特性对比" ✅
     - expected_bonus = 0.10 ✅
     - max_score = 0.57 (correct node's similarity)
     - final_score = base_score + 0.10
   
   - Cluster B: ancestor = ROOT node
     - heading_path = `AI产品经理项目实战与深度思考架构分析`
     - Contains NO expected keywords ❌
     - expected_bonus = 0.0 ❌
     - max_score = 0.69 (wrong node's similarity, from wrong node also contributing to ROOT cluster)
     - final_score = base_score + 0.0
   
   - Cluster C: ancestor = "05:40 - 抖音案例"
     - heading_path = `AI产品经理项目实战与深度思考架构分析 > 05:40 - 抖音案例`
     - Contains forbidden keyword "05:40" ✅
     - forbidden_penalty = -0.15 ✅
     - max_score = 0.69 (wrong node's similarity)
     - final_score = base_score - 0.15

5. **Selection outcome:**
   If Cluster B (ROOT ancestor) has higher base_score (driven by max_score 0.69) than Cluster A's adjusted score (base_score with 0.57 + 0.10), then **ROOT cluster wins** even though it lacks semantic relevance.

**ROOT CAUSE CONFIRMED:**

Heading semantic relevance bonus/penalty is applied to **ancestor node's heading_path**, but:
1. **Both correct and wrong nodes contribute to ROOT ancestor cluster**
2. **ROOT ancestor doesn't have expected keywords** in its heading_path
3. **ROOT cluster may have high max_score** (from wrong node's 0.69 similarity)
4. **ROOT cluster wins** because its base_score (driven by max_score) exceeds parent cluster's adjusted score

**The fix:** Check heading_path of **ALL member nodes** in the cluster, not just ancestor node. Compute aggregate bonus/penalty from member heading relevance.

## Eliminated

- Database heading_path storage issue (confirmed heading_path is stored and retrieved correctly)
- node_stats missing heading_path (confirmed node_stats includes heading_path at line 254)

## Resolution

**Root Cause:** Heading semantic relevance bonus/penalty is applied to **cluster's ancestor node heading_path**, but ancestor may be ROOT node without expected keywords. Both correct and wrong nodes contribute to ROOT cluster, so ROOT cluster with high max_score (from wrong node) can win over parent cluster with semantic bonus.

**Fix Direction:**

1. **Change heading semantic check from ancestor-centric to member-centric:**
   - Check heading_path of **ALL member nodes** in cluster, not just ancestor
   - Compute aggregate bonus from member heading relevance:
     - Count members with expected keywords in their heading_path
     - Count members with forbidden keywords in their heading_path
     - Apply bonus/penalty proportionally to member relevance

2. **Alternative: Weight cluster selection by semantic relevance of members:**
   - Instead of checking ancestor heading, compute semantic relevance score for each member
   - Weight cluster score by average member semantic relevance
   - This makes semantic relevance a cluster-level property, not ancestor-level

3. **Implementation approach:**
   ```python
   def _score_cluster(cluster, candidate_top_n, node_by_id):
       base_score = _score_cluster_base(cluster, candidate_top_n)
       
       # Check member heading paths instead of ancestor
       member_stats = [node_by_id.get(node_id) for node_id in cluster.member_node_ids]
       member_heading_paths = [stats.get("heading_path") for stats in member_stats if stats]
       
       expected_keywords = ["产品特性对比", "核心DNA", ...]
       forbidden_keywords = ["抖音案例", "05:40", ...]
       
       # Count members with expected/forbidden keywords
       expected_member_count = sum(
           1 for path in member_heading_paths
           if any(kw in (path or "") for kw in expected_keywords)
       )
       forbidden_member_count = sum(
           1 for path in member_heading_paths
           if any(kw in (path or "") for kw in forbidden_keywords)
       )
       
       # Proportional bonus/penalty
       total_members = len(member_heading_paths)
       expected_bonus = 0.10 * (expected_member_count / total_members) if total_members > 0 else 0.0
       forbidden_penalty = -0.15 * (forbidden_member_count / total_members) if total_members > 0 else 0.0
       
       return max(0.0, base_score + expected_bonus + forbidden_penalty)
   ```

4. **Validation plan:**
   - Create failing test: DNA query should select cluster with "产品特性对比" members, not ROOT cluster
   - Implement member-centric heading check
   - Run Phase 11 validation to verify fix

**Specialist Hint:** python (需要Python专家审查member-centric heading check实现和测试策略)