# 检索内容相关性分析报告

## 核心发现：返回内容与查询意图不符

查询："KAG 与 NexusRAG 在知识图谱方面的核心功能区别是什么"

返回内容：仓库元数据和技术路径，未讨论知识图谱功能对比

---

## 一、原文内容分析

### 文档结构（10个节点）

包含项目名称的节点：10个（100%）
包含"知识图谱"的节点：4个（40%）
包含功能讨论的节点：0个（0%）
包含对比分析的节点：3个（30%）

**结论：文档缺乏深入的功能对比内容**

文档性质：
- 标题："排除 GraphRAG 后的混合 RAG 开源项目深度研究"
- 定位：项目评估与选择建议
- 不是功能对比文档

### 高相关节点（存在于文档中但未被返回）

| Node ID | Title | 为什么更相关 | 是否命中 dual-hot |
|---------|-------|-------------|------------------|
| 9cc55cf5... | 最接近需求的项目深度分析 | 同时提到 KAG/NexusRAG/知识图谱，讨论各项目定位 | ✓ 是 (similarity=0.5459, keyword_score=0.75) |
| 5805bd22... | 模块拼接蓝图 | 讨论如何融合各项目功能，包含实现细节 | ✓ 是 (keyword_score=0.75) |
| 56707d27... | 执行摘要 | 核心结论，"NexusRAG最接近开箱即用" | ✓ 是 (similarity=0.5480, keyword_score=0.75) |
| 1c55cbcb... | 实施建议 | 具体建议"优先选择 NexusRAG"，包含理由 | ✓ 是 (similarity=0.6144, keyword_score=0.75) |

**关键发现：高相关节点全部命中 dual-hot 集合，但未被 parent coverage selection 选为 hotspot**

---

## 二、检索系统偏差分析

### Hotspot Selection 流程回顾

```
STEP 1: Vector Candidates (8 nodes)
  - Top similarity: 0.6144 (实施建议)
  - 高相关节点全部通过 VECTOR_HOT_THRESHOLD=0.35

STEP 2: Keyword Hits (8 nodes)
  - Query terms: {'kag', 'nexusrag', '和', '知识图谱的核心功能是什么'}
  - 高相关节点全部 keyword_hot (matched=['kag', 'nexusrag', '和'])

STEP 3: Dual-hot Intersection (7 nodes)
  - 高相关节点全部在 dual_hot 集合中

STEP 4: Parent Coverage Selection
  - 计算每个父节点的 coverage_ratio（dual_hot children占比）
  - 选择 coverage_ratio 最高、support 最高的父节点

结果：
  Hotspot #1: "GitHub 候选项目比较" (coverage_ratio=1.00, support=2)
    - 子节点："仓库元数据与关键路径"（低相关）
    - 子节点："候选项目总表"（低相关）

  Hotspot #2: "排除 GraphRAG 后的混合 RAG 开源项目深度研究" (coverage_ratio=0.71, support=5)
    - 包含所有高相关节点（实施建议、执行摘要、最接近需求分析等）
    - 但被排为第二优先级
```

### 根本原因：Parent Coverage Selection 算法偏差

**算法逻辑：**
```python
score = parent_avg_similarity × coverage_ratio
coverage_ratio = dual_hot_children / total_children
```

**偏差表现：**

1. **优先选择"窄覆盖"父节点**
   - "GitHub 候选项目比较"只有2个子节点，全部 dual_hot → coverage_ratio=1.00
   - "文档根节点"有7个子节点，5个 dual_hot → coverage_ratio=0.71

2. **忽略子节点内容相关性**
   - coverage_ratio 只统计 dual_hot 数量
   - 不区分"仓库元数据"和"实施建议"的内容质量差异

3. **父节点自身相关性未考虑**
   - 算法只看子节点的 dual_hot 覆盖率
   - 不考虑父节点标题是否匹配查询意图
   - "GitHub 候选项目比较"标题吸引关键词，但子节点内容是技术元数据

---

## 三、关键词提取问题

### 实际提取结果

```python
Query terms: {'kag', 'nexusrag', '和', '知识图谱的核心功能是什么'}
```

**问题分析：**

1. **jieba 过度聚合**
   - 将"知识图谱的核心功能是什么"整体作为一个关键词
   - 应该拆分为：["知识图谱", "核心功能", "区别"]
   - 导致无法匹配单独的"知识图谱"、"功能"等词

2. **缺失关键概念**
   - 用户查询意图："功能区别"
   - 提取结果缺少"区别"、"对比"、"差异"等对比性词汇
   - 无法精确匹配对比分析类节点

---

## 四、综合结论

### 检索失败的多层次原因

| 层级 | 问题 | 影响 |
|------|------|------|
| **文档层** | 文档本身缺乏功能对比内容 | 无完美答案可检索 |
| **关键词层** | jieba 过度聚合，缺失对比性关键词 | 精确匹配不足 |
| **Vector层** | 高相关节点相似度偏低（0.54 vs 0.61） | 排名不优先 |
| **Hotspot层** | Parent coverage prioritization 偏差 | 选错父节点 |
| **Traverse层** | 按父节点返回子节点 chunks | 返回低相关内容 |

### 系统改进建议

**短期修复：**

1. **调整关键词提取策略**
   ```python
   # 修改 runtime.py: _extract_keywords_from_query
   # 增加对比性词汇权重
   COMPARISON_TERMS = {'区别', '对比', '差异', '不同', '比较'}
   if term in COMPARISON_TERMS:
       keywords.append(term)  # 强制保留对比词
   ```

2. **降低 Parent Coverage 权重**
   ```python
   # 修改 semantic_distribution.py: HybridClusterHotspotSelector
   # 增加 parent自身相关性评分
   score = parent_avg_similarity × coverage_ratio × parent_keyword_score
   ```

**长期优化：**

1. **引入语义相关性判定**
   - 检查 chunk 内容是否真正回答查询意图
   - 使用 LLM 判定 evidence 质量后再返回

2. **多维度 Hotspot Ranking**
   - 不仅看 coverage_ratio
   - 还要看：
     - 子节点内容相关性（通过 semantic similarity + keyword coverage）
     - 父节点标题匹配度
     - 证据链完整性（是否有足够 chunks 支撑回答）

---

## 五、验证证据

### 高相关节点内容示例（未被返回）

**Node: "最接近需求的项目深度分析"**
```
Summary: "下面我选择 KAG、NexusRAG、LlamaIndex、LightRAG、RAPTOR/HIRO 五条线做深入分析。
原因很简单：这五条线几乎覆盖了你要的全部能力，只是分布在不同层面上——
KAG 偏推理和多索引，NexusRAG 偏结构保留和端到端..."
```

✓ 讨论了 KAG 与 NexusRAG 的定位差异
✓ 提到了核心能力分布
**相关性：高**（直接回答查询意图）

**Node: "模块拼接蓝图"**
```
Summary: "把 KAG/NexusRAG/LightRAG/LlamaIndex/RAPTOR-HIRO 的长项拼起来...
KAG 提供'图谱—文本互索引'和逻辑推理能力...
NexusRAG 已经具备了图谱、向量库、结构化 chunk、页码/标题路径..."
```

✓ 详细描述了各项目的核心功能
✓ 提到了"图谱"能力
**相关性：高**（包含功能细节）

### 低相关节点内容（实际返回）

**Node: "仓库元数据与关键路径"**
```
Content: "`kag/` 、 `knext/` 、 `docs/` 、 `tests/` ..."
```

✗ 仅仓库目录结构
✗ 无功能讨论
**相关性：低**

---

## 六、问题总结

**回答用户原始问题："返回了，但实际内容是否相符？"**

**答案：不相符。**

原因：
1. **文档本身**就不包含完整的知识图谱功能对比内容
2. **检索系统**选错了 hotspot（优先选择了覆盖率高的父节点，忽略了内容相关性）
3. **高相关节点**虽然命中 dual-hot，但被 parent coverage selection 排除
4. **关键词提取**不够精确，缺失对比性词汇

**核心矛盾：**
- 检索系统找到的是"文档中关键词匹配度最高的父节点"
- 但该父节点的子节点内容是技术元数据，不回答用户查询意图
- 真正相关的节点（"最接近需求的项目深度分析"）虽然命中 dual-hot，但未成为 hotspot