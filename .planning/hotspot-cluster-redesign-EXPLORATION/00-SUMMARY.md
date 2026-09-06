# 热点簇重设计探索综合报告

> 范围：只读探索。未修改运行代码。  
> 来源：E3、E5 子代理报告 + 主会话对 E1/E2/E4/E6/E7 的代码/测试/数据核验。  
> 生成日期：2026-06-22

---

## 0. 一句话结论

当前 `hybrid_cluster` 实现确实是 **单节点候选集合 Top-K 融合排序**，不是“兄弟簇整体热 / 路径整体热后推父节点为热点”。

- `HybridClusterHotspotSelector.select_hotspots()` 构造 `candidate_node_ids = vector_by_node ∪ keyword_by_node`，然后逐节点计算 fusion，排序取 `fusion_scores[:limit]`：`llamaindex_runtime/tree/semantic_distribution.py:954`、`llamaindex_runtime/tree/semantic_distribution.py:968`、`llamaindex_runtime/tree/semantic_distribution.py:993`。
- 子节点信息在 `hybrid_cluster` 融合中只以 `distribution_score` 的 0.10 权重进入：`llamaindex_runtime/tree/semantic_distribution.py:981`、`llamaindex_runtime/tree/semantic_distribution.py:989`。
- `_compute_child_distribution_score()` 统计 sibling hits / child hits 数量，但没有检查“全部子节点覆盖率”，也没有要求“关键词和向量双热”：`llamaindex_runtime/tree/semantic_distribution.py:1194`、`llamaindex_runtime/tree/semantic_distribution.py:1203`、`llamaindex_runtime/tree/semantic_distribution.py:1220`、`llamaindex_runtime/tree/semantic_distribution.py:1223`。
- 已有 `ClusterHotspotSelector` 才有真正的祖先簇聚合 `_build_ancestor_clusters()`，但 `hybrid_cluster` 没有复用它：`llamaindex_runtime/tree/semantic_distribution.py:744`、`llamaindex_runtime/tree/semantic_distribution.py:954`。

---

## 1. E1：从 query 到 hotspot selection 的数据流

### 1.1 数据流图

```text
retrieve_tree_hits_from_pdf(...)
  └─ _retrieve_tree_hits_from_backend(...)
       ├─ adapter.analyze_tree_semantic_distribution(...)
       │    └─ distribution_report = { node_stats, tree_signals }
       │
       ├─ get_hotspot_selector(hotspot_strategy)
       │
       ├─ if hotspot_strategy == "hybrid_cluster":
       │    ├─ node_by_id_lookup = {stats["node_id"]: stats}
       │    ├─ vector_candidates = cosine(query_embedding, prototype/centroid) for each node_stats
       │    ├─ keyword_hits = heading keyword match from jieba query keywords
       │    ├─ context = HotspotSelectionContext(...)
       │    └─ HybridClusterHotspotSelector.select_hotspots(context, limit)
       │         ├─ normalize vector scores
       │         ├─ normalize keyword scores + term coverage
       │         ├─ optional rerank scores
       │         ├─ distribution_scores[node_id] = _compute_child_distribution_score(...)
       │         ├─ fusion = _compute_fusion_score(...)
       │         └─ sort fusion_scores desc, return top limit SubtreeHotspot(node_id=...)
       │
       └─ for hotspot in hotspots:
            runner.traverse_tree_for_query(start_node_id=hotspot.node_id, hotspot_node_id=hotspot.node_id)
```

锚点：
- selector 实例化：`llamaindex_runtime/tree/runtime.py:248`
- `hybrid_cluster` 分支：`llamaindex_runtime/tree/runtime.py:251`
- `node_by_id_lookup` 由 `distribution_report["node_stats"]` 构建：`llamaindex_runtime/tree/runtime.py:253`
- `vector_candidates` 构建：`llamaindex_runtime/tree/runtime.py:256`、`llamaindex_runtime/tree/runtime.py:264`、`llamaindex_runtime/tree/runtime.py:273`
- `keyword_hits` 构建：`llamaindex_runtime/tree/runtime.py:285`、`llamaindex_runtime/tree/runtime.py:296`、`llamaindex_runtime/tree/runtime.py:305`
- `HotspotSelectionContext` 构建：`llamaindex_runtime/tree/runtime.py:316`
- selector 调用：`llamaindex_runtime/tree/runtime.py:326`
- traversal 连接：`llamaindex_runtime/tree/runtime.py:342`、`llamaindex_runtime/tree/runtime.py:349`

### 1.2 每个节点进入 fusion 的信号表

| 信号 | 计算位置 | 数据结构 | 进入 fusion 的方式 | 子节点信息 |
|---|---|---|---|---|
| vector score | `runtime.py` 对每个 `node_stats` 的 `prototype_embedding`/`centroid` 做 cosine | `NodeSemanticHit.similarity` | 在 selector 内归一化成 `vector_by_node[node_id]` | 不表达子节点；父节点 embedding 已由 `_build_node_stats()` 聚合子树向量 |
| keyword score | `runtime.py` 用 query keywords 匹配 `heading_path` | `KeywordSpanHit(score=0.6, matched_terms=...)` | 在 selector 内归一化并合并 term coverage 为 `keyword_by_node[node_id]` | 不表达子节点；只看当前节点 heading_path |
| exact keyword promotion | selector 内统计所有 matched_terms 与节点 matched_terms | `exact_keyword_nodes` | 将 keyword weight 从 `0.30` 提升到 `2.00` | 不表达子节点 |
| rerank score | `HotspotSelectionContext.rerank_scores` | `dict[UUID, float]  None` | 存在时归一化并进入 `_compute_fusion_score()` | 未在已读代码中确认子节点来源 |
| distribution score | `_compute_child_distribution_score()` | `distribution_scores[node_id]` | 以 `distribution_weight=0.10` 进入 `_compute_fusion_score()`；rerank 缺省时权重重新归一 | 表达 sibling hits / child hits 数量，但不检查完整覆盖率 |

锚点：
- `HotspotSelectionContext` 字段：`llamaindex_runtime/tree/semantic_distribution.py:511`
- `NodeSemanticHit` 字段含 `path_to_root`：`llamaindex_runtime/tree/semantic_distribution.py:528`
- vector 归一化与映射：`llamaindex_runtime/tree/semantic_distribution.py:902`
- keyword term coverage：`llamaindex_runtime/tree/semantic_distribution.py:920`、`llamaindex_runtime/tree/semantic_distribution.py:928`
- candidate 并集：`llamaindex_runtime/tree/semantic_distribution.py:954`
- distribution 调用：`llamaindex_runtime/tree/semantic_distribution.py:960`
- fusion 调用：`llamaindex_runtime/tree/semantic_distribution.py:981`
- Top-K 单节点选择：`llamaindex_runtime/tree/semantic_distribution.py:993`

### 1.3 E1 结论

- 在 `HybridClusterHotspotSelector` 的 fusion 评分中，**唯一显式表达 sibling/child 结构的入口是 `distribution_score`**。
- `NodeSemanticHit.path_to_root` 在类型上存在，但 `HybridClusterHotspotSelector.select_hotspots()` 已读代码未使用 `path_to_root` 聚合祖先簇；该字段在 `ClusterHotspotSelector` 路径中被 `_build_ancestor_clusters()` 使用：`llamaindex_runtime/tree/semantic_distribution.py:718`、`llamaindex_runtime/tree/semantic_distribution.py:744`。
- `node_stats` 中的 `prototype_embedding` / `centroid` 对 route parent 来自子树向量，因此 vector score 间接包含子树内容；这不是“子节点覆盖率”逻辑，且无法判断哪些直接子节点都热。锚点：`llamaindex_runtime/tree/semantic_distribution.py:221`、`llamaindex_runtime/tree/semantic_distribution.py:228`、`llamaindex_runtime/tree/semantic_distribution.py:240`。

---

## 2. E2：selector 是否能拿到完整子节点集

### 2.1 YES/NO

**NO：`hybrid_cluster` selector 不能拿到完整树结构。**

它能拿到的是 `node_stats` 字典，不是完整 `tree_nodes`。`node_stats` 只包含有 direct vectors 或 subtree vectors 的节点；没有任何向量支撑的节点会被跳过。

事实锚点：
- `HotspotSelectionContext.node_stats` 类型是 `dict[UUID, dict[str, Any]]`，没有 `tree_nodes` 或 `parent_to_children` 字段：`llamaindex_runtime/tree/semantic_distribution.py:519`、`llamaindex_runtime/tree/semantic_distribution.py:521`。
- runtime 构建 context 时只传 `node_by_id_lookup`，来源是 `distribution_report["node_stats"]`：`llamaindex_runtime/tree/runtime.py:253`、`llamaindex_runtime/tree/runtime.py:316`、`llamaindex_runtime/tree/runtime.py:319`。
- `_build_node_stats()` 对每个 tree node 取 direct/subtree vectors；`if not vectors: continue` 会跳过无向量节点：`llamaindex_runtime/tree/semantic_distribution.py:237`、`llamaindex_runtime/tree/semantic_distribution.py:240`、`llamaindex_runtime/tree/semantic_distribution.py:243`。
- `_build_report()` 返回 `node_stats` 与 `tree_signals`，不返回完整 `tree_nodes`：`llamaindex_runtime/tree/semantic_distribution.py:322`、`llamaindex_runtime/tree/semantic_distribution.py:330`。

### 2.2 它已经能拿到什么

- 每个已分析节点的 `parent_node_id`、`level_no`：`llamaindex_runtime/tree/semantic_distribution.py:253`、`llamaindex_runtime/tree/semantic_distribution.py:255`、`llamaindex_runtime/tree/semantic_distribution.py:256`。
- 每个已分析节点的 `subtree_chunk_ids`、`support_count`、`direct_support_count`、`is_route_node`：`llamaindex_runtime/tree/semantic_distribution.py:257`、`llamaindex_runtime/tree/semantic_distribution.py:259`、`llamaindex_runtime/tree/semantic_distribution.py:264`、`llamaindex_runtime/tree/semantic_distribution.py:266`。
- 可基于 `node_stats` parent chain 构建节点到根路径：`llamaindex_runtime/tree/semantic_distribution.py:1016`、`llamaindex_runtime/tree/semantic_distribution.py:1032`、`llamaindex_runtime/tree/semantic_distribution.py:1045`。

### 2.3 它缺少什么

- 完整 `tree_nodes` 列表。
- 完整 `parent_to_children` 映射。
- 每个父节点的 direct child 总数（用于覆盖率分母）。
- 未入 `node_stats` 的无向量节点是否也应计入覆盖率分母的设计决策。

### 2.4 最小补数据草图

```python
@dataclass(frozen=True)
class HotspotSelectionContext:
    query_text: str
    query_embedding: list[float]
    node_stats: dict[UUID, dict[str, Any]]
    tree_signals: dict[str, Any]
    vector_candidates: list[NodeSemanticHit]
    keyword_hits: list[KeywordSpanHit]
    rerank_scores: dict[UUID, float] | None = None
    parent_to_children: dict[UUID | None, tuple[UUID, ...]] = field(default_factory=dict)
```

最小数据源有两条路线：

1. 在 `distribution_report` 增加从完整 `tree_nodes` 生成的 `parent_to_children`。
   - 已有 `_build_parent_to_children(tree_nodes)` 可用：`llamaindex_runtime/tree/semantic_distribution.py:313`。
   - `_build_report()` 当前拿到 `tree_nodes` 参数，可在这里附加结构信息：`llamaindex_runtime/tree/semantic_distribution.py:322`。
2. 不改 context 结构，在 `_build_node_stats()` 给每个 stats 增加 `direct_child_node_ids` / `direct_child_count`。
   - `_build_node_stats()` 已能访问完整 `tree_nodes`：`llamaindex_runtime/tree/semantic_distribution.py:214`。
   - 该路线可满足覆盖率分母，但不能让 selector 遍历未入 stats 的 child 详情。

---

## 3. E3：已有簇代码盘点

子代理结论已收录。

### 3.1 活代码

- `SubtreeHotspotSelector`：默认 `route_subtree` 路径活代码。定义：`llamaindex_runtime/tree/semantic_distribution.py:570`；工厂返回：`llamaindex_runtime/tree/semantic_distribution.py:1708`；默认策略来源：`llamaindex_runtime/tree/runtime.py:421`。
- `ClusterHotspotSelector`：`RAG_TREE_HOTSPOT_SELECTOR=cluster` 路径活代码。定义：`llamaindex_runtime/tree/semantic_distribution.py:654`；工厂返回：`llamaindex_runtime/tree/semantic_distribution.py:1710`。
- `HybridClusterHotspotSelector`：`RAG_TREE_HOTSPOT_SELECTOR=hybrid_cluster` 路径活代码。定义：`llamaindex_runtime/tree/semantic_distribution.py:835`；工厂返回：`llamaindex_runtime/tree/semantic_distribution.py:1712`；runtime V2 context 分支：`llamaindex_runtime/tree/runtime.py:251`。
- `ClusterCandidate` 与 `_build_ancestor_clusters()`：在 `ClusterHotspotSelector` 路径活。定义：`llamaindex_runtime/tree/semantic_distribution.py:547`、`llamaindex_runtime/tree/semantic_distribution.py:1054`；调用：`llamaindex_runtime/tree/semantic_distribution.py:744`。

### 3.2 死代码

未在已读代码中确认存在死的 selector 定义。

### 3.3 可复用代码

- 可复用：`ClusterHotspotSelector` 的 `_build_path_to_root()` + `_build_ancestor_clusters()` + `_score_cluster()` 祖先簇聚合框架。
- 不足：这套代码目前只吃 vector similarity，不吃 `keyword_hits`，也不要求“关键词+向量双热”。锚点：`llamaindex_runtime/tree/semantic_distribution.py:703`、`llamaindex_runtime/tree/semantic_distribution.py:744`。
- `hybrid_cluster` 可复用 V2 context 的 vector/keyword 输入，但需要接入祖先簇聚合逻辑。锚点：`llamaindex_runtime/tree/semantic_distribution.py:511`、`llamaindex_runtime/tree/runtime.py:316`。

---

## 4. E4：“簇热点”的候选定义

### 定义 A：直接子节点覆盖率 ≥ θ

**正式描述**

```text
给定父节点 P，direct_children(P) = {c1..cn}
child_hot(c) = vector_hot(c) AND keyword_hot(c)
coverage(P) = count(child_hot(c) for c in direct_children(P)) / n
P 是热点 ⇔ coverage(P) ≥ θ 且 count(child_hot) ≥ min_support
```

补充：
- `vector_hot(c)` 来自 vector candidate 分数阈值或 Top-N。
- `keyword_hot(c)` 来自 keyword hit term coverage 或 BM25/exact match。
- `AND` 对齐用户要求“关键词 + 向量都要热”。

**p6 例子**

```text
AI产品经理项目实战与深度思考架构分析
└─ 04:13 - 数据处理
   ├─ 数据处理步骤
   ├─ 数据清洗标注
   └─ 菜品清洗比喻
```

来源：`verification/p6_validation/p6_final_sample_structured.md:101`、`verification/p6_validation/p6_final_sample_structured.md:102`、`verification/p6_validation/p6_final_sample_structured.md:106`、`verification/p6_validation/p6_final_sample_structured.md:109`。

对 query `数据清洗标注的具体方法是什么？`，现有运行结果 rank1 是 `04:13 - 数据处理 > 数据清洗标注`，`drill_depth=0`，span 有值：`test_remaining_queries_result.json:3`、`test_remaining_queries_result.json:8`、`test_remaining_queries_result.json:10`、`test_remaining_queries_result.json:15`。

在定义 A 下：
- 如果只有 `数据清洗标注` 双热，`04:13 - 数据处理` 覆盖率为 `1/3`。
- 如果 `数据清洗标注` 与 `菜品清洗比喻` 都双热，覆盖率为 `2/3`。
- 如果三个 direct children 都双热，覆盖率为 `1.0`。

**实现难度**

- 需要完整 direct child 分母；当前 `HotspotSelectionContext` 不提供完整 `parent_to_children`：`llamaindex_runtime/tree/semantic_distribution.py:511`、`llamaindex_runtime/tree/runtime.py:316`。
- 可复用 `_build_parent_to_children()`：`llamaindex_runtime/tree/semantic_distribution.py:313`。

**一致性**

- 与“兄弟节点组成一群节点”的场景一致。
- 与“关键词+向量都要热”一致。

### 定义 B：路径全热

**正式描述**

```text
给定叶子/命中节点 L，path(L) = [root, ..., L]
node_hot(x) = vector_hot(x) AND keyword_hot(x)
path_hot(L) = all(node_hot(x) for x in path(L))
hotspot = highest ancestor A on path(L) that satisfies path_hot suffix/prefix rule
```

**p6 例子**

```text
AI产品经理项目实战与深度思考架构分析
└─ 00:31 - 产品特性对比
   └─ AI产品经理核心DNA
      ├─ 数据驱动
      ├─ 非确定性
      └─ 持续性
```

来源：`verification/p6_validation/p6_final_sample_structured.md:1`、`verification/p6_validation/p6_final_sample_structured.md:18`、`verification/p6_validation/p6_final_sample_structured.md:38`、`verification/p6_validation/p6_final_sample_structured.md:39`。

现有验证中 query `AI产品经理的核心DNA是什么？` 命中 DNA 节点并返回证据 `数据驱动 - 非确定性 - 持续性`：`verification/phase11-level-agnostic-hotspot-cluster-tracking/05_hotspot_retrieval_results.json:10`、`verification/phase11-level-agnostic-hotspot-cluster-tracking/05_hotspot_retrieval_results.json:25`、`verification/phase11-level-agnostic-hotspot-cluster-tracking/05_hotspot_retrieval_results.json:26`。

**实现难度**

- `path_to_root` 已存在且 `ClusterHotspotSelector` 使用：`llamaindex_runtime/tree/semantic_distribution.py:1016`、`llamaindex_runtime/tree/semantic_distribution.py:720`。
- 对每个 ancestor 要求 keyword_hot 会很严格；root/title 类节点的 heading 通常不含查询全部关键词。
- 已读代码未提供 path 上每一层的 keyword hit 双热判定函数，需要新增。

**一致性**

- 与“一条线上的节点都热”一致。
- 对 focused leaf query 会比定义 A 更严格。

### 定义 C：子树密度

**正式描述**

```text
subtree(P) = P 的所有后代节点集合 + P
hot_nodes(P) = {x in subtree(P) | vector_hot(x) AND keyword_hot(x)}
density(P) = len(hot_nodes(P)) / len(subtree(P))
P 是热点 ⇔ density(P) ≥ θ 且 len(hot_nodes(P)) ≥ min_support
```

**p6 例子**

```text
AI产品经理项目实战与深度思考架构分析
└─ 06:29 - 特斯拉案例
   ├─ 摄像头配置
   ├─ 数据收集机制
   ├─ AB test 预演
   ├─ 闭环流程
   └─ 核心思维要求
```

来源：`verification/p6_validation/p6_final_sample_structured.md:150`、`verification/p6_validation/p6_final_sample_structured.md:151`、`verification/p6_validation/p6_final_sample_structured.md:154`、`verification/p6_validation/p6_final_sample_structured.md:158`、`verification/p6_validation/p6_final_sample_structured.md:166`、`verification/p6_validation/p6_final_sample_structured.md:173`。

**实现难度**

- 已有 `_count_subtree_candidates()` 与 `ClusterCandidate.density`，但 denominator 是 candidate subtree scope，不是完整树节点总数：`llamaindex_runtime/tree/semantic_distribution.py:1076`、`llamaindex_runtime/tree/semantic_distribution.py:1092`、`llamaindex_runtime/tree/semantic_distribution.py:1110`。
- 要实现完整子树密度，需要 E2 的完整树结构补数据。

**一致性**

- 与“子树整体热”一致。
- 比定义 A 更适合深树；p6 现有样本主要是 3 层，A 的解释性更直接。

### E4 推荐

**第一版采用定义 A：直接子节点覆盖率 ≥ θ + 每个热子节点必须 vector_hot AND keyword_hot。**

原因：
1. 直接表达用户说的“一群节点”。
2. p6 真实结构以 H2→H3 为主，直接子节点覆盖率可解释。统计见 E7。
3. 改动边界比 C 小，设计语义比当前 `_compute_child_distribution_score()` 明确。
4. B 作为补充规则用于“路径全热”，不作为第一版唯一规则。

---

## 5. E5：选择层 vs 遍历层职责边界

子代理结论已收录。

### 5.1 当前边界

```text
选择层：hotspot_selector.select_hotspots(...) -> list[SubtreeHotspot(node_id=...)]
遍历层：runner.traverse_tree_for_query(start_node_id=hotspot.node_id, hotspot_node_id=hotspot.node_id)
```

锚点：
- runtime 每个 hotspot 独立 traversal：`llamaindex_runtime/tree/runtime.py:341`。
- start_node_id/hotspot_node_id 都等于 `hotspot.node_id`：`llamaindex_runtime/tree/runtime.py:349`、`llamaindex_runtime/tree/runtime.py:350`。
- traversal 接口只接收单个 start node：`llamaindex_runtime/tree/semantic_distribution.py:1412`。

### 5.2 改动边界结论

- 如果第一版簇热点仍输出 `SubtreeHotspot(node_id=代表节点)`，遍历层接口不需要改。
- 如果目标是“ancestor + member set 一起约束召回”，当前 traversal 不支持，需要扩展 runtime 调度或 traversal 参数。

### 5.3 风险

- 重复召回：`ClusterHotspotSelector` 返回 ancestor 后会追加 member：`llamaindex_runtime/tree/semantic_distribution.py:803`、`llamaindex_runtime/tree/semantic_distribution.py:815`。
- 死分支：policy 对 route node 直接 drill_down；叶子没有 child 时返回空：`llamaindex_runtime/tree/semantic_distribution.py:91`、`llamaindex_runtime/tree/semantic_distribution.py:1484`、`llamaindex_runtime/tree/semantic_distribution.py:1494`。
- 漏召回：keep_parent 不访问 children；evaluate_children 路径只递归 selected_child：`llamaindex_runtime/tree/semantic_distribution.py:1469`、`llamaindex_runtime/tree/semantic_distribution.py:1547`。

---

## 6. E6：测试回归面盘点

### 6.1 需要改写的测试

| 测试区域 | 锚点 | 原因 | 改写方向 |
|---|---:|---|---|
| `TestChildDistributionScoring.test_parent_with_multiple_child_hits_beats_isolated_high_score_node` | `tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector.py:195` | 当前只要求“多个 child hits 打败孤立高分”，没有覆盖率分母，也没有 keyword+vector 双热 | 改为 direct child coverage gate；构造 1/3、2/3、3/3 覆盖案例 |
| `_compute_child_distribution_score` 单元契约 | `tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector.py:231` | 当前直接调用旧 helper；helper 无完整子节点分母 | 新 helper 接收 `parent_to_children` 或 `direct_child_count` |
| `test_selector_prefers_multi_term_heading_match_over_broad_single_term` | `tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector.py:359` | 锁定单节点 exact heading 优先；簇版需要同时验证 exact leaf 保留与 parent 覆盖率不误升 | 改为 leaf exact match 可作为结果，但 parent 必须通过 coverage gate 才成热点 |
| `test_selector_prioritizes_exact_heading_match_over_high_vector_broad_match` | `tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector.py:447` | 同上，当前验证单节点排序 | 加入 sibling/parent 结构，断言 broad high-vector 不越过覆盖率规则 |
| hybrid selector top-k 结果形态 | `llamaindex_runtime/tree/semantic_distribution.py:993` | 当前实现按 `fusion_scores[:limit]`，测试缺少 cluster-aware 期望 | 新增 cluster-aware order 与 overlap 去重测试 |

### 6.2 需要保留的测试

| 测试区域 | 锚点 | 保留原因 |
|---|---:|---|
| selector registration / rollback | `tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector.py:20` | 策略开关和回滚安全不变 |
| `HotspotSelectionContext` 基础字段 | `tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector.py:62` | V2 context 仍可扩展保留 |
| `KeywordSpanHit` 合同 | `tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector.py:141` | keyword hit 输入仍需要 |
| score normalization | `tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector.py:164` | vector/keyword/rerank 归一化仍需要 |
| fusion weighted sum helper | `tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector.py:334` | 若保留 fusion 作为子组件，该 helper 仍可测 |
| default-off reranker seam | `tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector.py:536` | 外部 rerank 默认关闭合同不变 |
| anti-hardcode | `tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector.py:587` | 不能引入 p6 专用关键词 |
| jieba keyword extraction | `tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector.py:643` | 跨中英文 query 分词合同不变 |
| runtime config registration | `tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector.py:737` | selector 配置合法性不变 |
| `ClusterHotspotSelector` D-02 densest shared ancestor | `tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py:182` | 与簇热点目标一致 |
| root avoidance | `tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py:354` | 防止 root bias 不变 |
| p6 DNA regression | `tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py:656`、`tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py:915` | p6 真值区域不变 |

### 6.3 新测试矩阵

| 维度 | Case | 输入结构 | 期望 |
|---|---|---|---|
| 覆盖率 | 1/3 child 双热 | parent 有 3 child，仅 1 child 同时 vector+keyword 命中 | parent 不成为 cluster hotspot |
| 覆盖率 | 2/3 child 双热 | parent 有 3 child，2 child 双热 | θ=0.67 时 parent 成为 cluster hotspot |
| 覆盖率 | 3/3 child 双热 | parent 有 3 child，3 child 双热 | parent 稳定胜过 isolated high-vector leaf |
| 双热门槛 | vector-only child | child vector 高、无 keyword | 不计入 coverage |
| 双热门槛 | keyword-only child | child heading 命中、vector 低/无 | 不计入 coverage |
| 路径全热 | root→section→leaf 全部双热 | 构造 path 全热 | 返回最高合法 ancestor 或路径热点 |
| sibling overlap | ancestor + member 同时入选 | parent 通过覆盖率，child 也高分 | runtime 不重复返回同一 span/chunk |
| fallback | focused leaf query | 仅 leaf 双热，parent 覆盖率不足 | leaf 仍可作为 result/hotspot，不强推 parent |
| p6 regression | `AI产品经理核心DNA` | p6 产品特性对比区域 | 仍返回 DNA 证据，拒绝抖音/特斯拉作为 primary |
| cross-domain | medical/legal English | 非 p6 heading | 不依赖 p6 专用词表 |

---

## 7. E7：p6 树结构现实检查

### 7.1 数据来源

- 结构源：`verification/p6_validation/p6_final_sample_structured.md`。
- 统计方法：按 Markdown heading 层级 `# / ## / ###` 构树。
- 该文件自述为 200 行样本，含 12 个 `## heading`、30+ `### heading`：`verification/p6_validation/p6_final_sample_structured.md:199`。

### 7.2 深度分布

| Heading level | 节点数 |
|---:|---:|
| H1 | 1 |
| H2 | 13 |
| H3 | 33 |
| 总计 | 47 |

来源锚点样例：
- H1 root：`verification/p6_validation/p6_final_sample_structured.md:1`
- H2 `00:31 - 产品特性对比`：`verification/p6_validation/p6_final_sample_structured.md:18`
- H3 `AI产品经理核心DNA`：`verification/p6_validation/p6_final_sample_structured.md:38`

### 7.3 子节点数量分布

| direct child count | 节点数 |
|---:|---:|
| 0 | 34 |
| 2 | 5 |
| 3 | 6 |
| 5 | 1 |
| 13 | 1 |

解释：
- 34 个叶子节点没有 direct child。
- H2 章节多数有 2 或 3 个 H3 子节点。
- root 有 13 个 H2 子节点。
- `06:29 - 特斯拉案例` 有 5 个 H3 子节点：`verification/p6_validation/p6_final_sample_structured.md:150`、`verification/p6_validation/p6_final_sample_structured.md:151`、`verification/p6_validation/p6_final_sample_structured.md:154`、`verification/p6_validation/p6_final_sample_structured.md:158`、`verification/p6_validation/p6_final_sample_structured.md:166`、`verification/p6_validation/p6_final_sample_structured.md:173`。

### 7.4 可行性结论

- “所有 direct children 都热”（θ=1.0）在 p6 上很严格：H2 节点通常有 2-3 个 H3 子节点，focused query 命中单个 H3 时，父节点覆盖率为 1/2 或 1/3。
- “覆盖率阈值”（θ < 1.0）有意义：p6 的非叶父节点 child_count 集中在 2、3、5，阈值可以区分单点命中和兄弟簇命中。
- root 的 child_count=13；root 需要单独排除或强惩罚，已有 `ClusterHotspotSelector` 有 root alternatives 过滤：`llamaindex_runtime/tree/semantic_distribution.py:757`、`llamaindex_runtime/tree/semantic_distribution.py:770`。
- 对 leaf query，簇热点规则需要 leaf fallback；否则 `数据清洗标注的具体方法是什么？` 这类精确 leaf query 会因父节点覆盖率不足而无法返回当前位置。现有 leaf 返回结果见 `test_remaining_queries_result.json:7`、`test_remaining_queries_result.json:10`、`test_remaining_queries_result.json:15`。

---

## 8. 最终决策点

### D1：采用哪个“簇热点”定义

推荐：**A 直接子节点覆盖率 ≥ θ + child 必须 vector_hot AND keyword_hot**。

补充：B 路径全热作为第二阶段或 tie-breaker；C 子树密度复用现有 ClusterCandidate 思路但依赖完整树 denominator。

### D2：E2 是否需要补数据

需要。若要做真实覆盖率检查，必须把完整 child denominator 传入 selector。当前 context 只有 `node_stats`，会漏掉无向量节点。

### D3：改动范围

第一版只改选择层：让 `hybrid_cluster` 使用 cluster-aware coverage scoring 后仍输出 `SubtreeHotspot(node_id=...)`。

不改 traversal 接口，除非目标升级为“ancestor + member set 约束召回”。

### D4：覆盖率阈值现实性

p6 支持覆盖率阈值；不适合把 θ 固定为 1.0。第一版使用可配置阈值，并保留 leaf fallback。

### D5：Phase 12 还是改 Phase 11

推荐新建 Phase 12：`hybrid_cluster` 当前已属于 Phase 11 闭环后的新设计纠偏，变更会影响 selector 合同、测试合同和真实检索行为。

---

## 9. 最小实现路线草图（不执行）

1. 扩展 `HotspotSelectionContext`：加入 `parent_to_children` 或 `direct_child_count`。
2. runtime 从完整 `tree_nodes` 或 `distribution_report` 传入 child denominator。
3. 把 `HybridClusterHotspotSelector` 从“node fusion Top-K”改为：

```text
vector_hot_nodes = normalized vector candidates over threshold/topN
keyword_hot_nodes = keyword hits over term coverage threshold
both_hot_nodes = vector_hot_nodes ∩ keyword_hot_nodes
for parent in candidate parents:
    coverage = count(child in both_hot_nodes for child in direct_children(parent)) / len(direct_children(parent))
    if coverage >= θ and support >= min_support:
        score parent by coverage + avg vector + avg keyword + support
fallback:
    keep exact leaf matches / strong both-hot leaves
```

4. 保留 `ClusterHotspotSelector` 祖先聚合代码作为复用参考。
5. 先写覆盖率与双热门槛测试，再改 selector。
