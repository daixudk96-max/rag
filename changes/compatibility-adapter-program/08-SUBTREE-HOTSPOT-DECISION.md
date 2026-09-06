# Tree Subtree Hotspot Decision Note

## 用户想要的决策层到底是什么

不是“给当前 node 算 embedding 后，直接决定 keep / drill / prune”。

而是：

1. 先对 query 做 embedding
2. 再对树上多个 node / subtree 的语义表示做比较
3. 找出和 query 最相关、最集中的那一片区域
4. 推断这个热点区域共同对应的“头部父节点”
5. 从这个父节点开始，再做逐层下钻
6. 下钻过程中才决定：
   - keep_parent
   - drill_down
   - prune

## 这和当前 baseline 的区别

### 当前 baseline
- root 开始
- 看当前 node 的统计
- 决定往不往 child 走
- 更像“局部递归决策”

### 用户想要的版本
- 先看整层 / 整棵树的语义热点分布
- 先选“最值得开始”的父节点 / 子树头部
- 再从那里开始局部递归决策
- 更像“全局热点定位 + 局部递归决策”

## 新增层的建议命名

### SubtreeHotspotSelector
职责：
- 输入：
  - query embedding
  - tree nodes / parent-child 关系
  - node semantic representation
  - node-level centroid / dispersion / entropy / support_count
- 输出：
  - 最值得开始下钻的父节点 / 子树头部
  - 候选 hotspot 列表

## 推荐输出形状

```python
{
    "hotspot_heads": [
        {
            "node_id": UUID(...),
            "score": 0.91,
            "reason": "high local similarity + concentrated descendants",
            "support_count": 12,
            "dispersion": 0.18,
            "entropy": 0.62,
        }
    ],
    "selection_summary": {...},
}
```

## 推荐顺序

1. build tree
2. build chunk embeddings
3. build node-level semantic statistics
4. run `SubtreeHotspotSelector`
5. choose subtree head(s)
6. run recursive branch decision policy from chosen head(s)

## donor 参考

### 可借 donor
- `Psi-RAG`：tree traversal / node representation / prototype embedding
- `HIRO`：branch decision skeleton / dual-threshold pattern
- `RAPTOR`：cluster-tree / collapsed retrieval ideas

### 当前结论
- `Psi-RAG` / `HIRO` / `RAPTOR` 都没有现成实现这整层
- 这层需要在本地 runtime 自己落地
- donor 更多提供局部强逻辑，而不是完整成品
