# Phase 14 权重修复报告

## 修复时间
2026-06-29

## 问题描述

**症状：** Q2 检索返回低相关性内容（仓库元数据），未返回高相关性节点（实施建议、执行摘要）

**根本原因：** Parent Coverage Selection 权重分配偏差
- coverage_ratio 权重过高 (0.50) → 偏向"小而全"父节点
- support_bonus 权重过低 (0.20) → 限制"大而多"父节点优势

---

## 修复方案

### 代码修改

**文件：** `llamaindex_runtime/tree/semantic_distribution.py`

**修改位置：** Line 990-992 (权重常量定义)

**修改内容：**
```python
# 修改前
_COVERAGE_WEIGHT: float = 0.50
_COVERAGE_VECTOR_WEIGHT: float = 0.30
_COVERAGE_SUPPORT_WEIGHT: float = 0.20

# 修改后
_COVERAGE_WEIGHT: float = 0.40  # Phase 14 fix: lowered from 0.50
_COVERAGE_VECTOR_WEIGHT: float = 0.30
_COVERAGE_SUPPORT_WEIGHT: float = 0.30  # Phase 14 fix: raised from 0.20
```

---

## 修复效果验证

### Phase 14 验证结果对比

| 指标 | 修复前 | 修复后 | 改进 |
|------|--------|--------|------|
| Total hits | 59 | 100 | +68% |
| Evidence chunk hits | 0 | 100 | 从0到100 ✓ |
| Missing chunk hits | 59 | 0 | 从59到0 ✓ |
| Queries with hits | 13/20 | 20/20 | 100%覆盖 ✓ |

**结论：** 修复成功，所有查询返回真实证据内容

---

### Hotspot Selection 理论计算对比

#### Parent Score 重新计算（Q2 示例）

```
Parent A: "GitHub 候选项目比较"
  coverage_ratio = 1.00 (2 dual_hot / 2 children)
  avg_child_vector = 0.5288
  support_bonus = 0.4 (hot_count=2)

修复前评分：
  score = 1.00 * 0.50 + 0.5288 * 0.30 + 0.4 * 0.20
        = 0.50 + 0.1586 + 0.08 = 0.7386

修复后评分：
  score = 1.00 * 0.40 + 0.5288 * 0.30 + 0.4 * 0.30
        = 0.40 + 0.1586 + 0.12 = 0.6786

Parent B: "文档根节点"
  coverage_ratio = 0.71 (5 dual_hot / 7 children)
  avg_child_vector = 0.5662
  support_bonus = 1.0 (hot_count=5, 封顶)

修复前评分：
  score = 0.71 * 0.50 + 0.5662 * 0.30 + 1.0 * 0.20
        = 0.355 + 0.1699 + 0.20 = 0.7120

修复后评分：
  score = 0.71 * 0.40 + 0.5662 * 0.30 + 1.0 * 0.30
        = 0.284 + 0.1699 + 0.30 = 0.7539 ✓
```

**排序结果：**
- 修复前：Parent A (0.7386) > Parent B (0.7120) → 选择低相关父节点 ✗
- 修复后：Parent B (0.7539) > Parent A (0.6786) → 选择高相关父节点 ✓

**排序反转成功！**

---

## 核心机制解析

### 两阶段架构保持不变

**阶段1：Dual-hot Intersection Gate（硬过滤）**
- 目的：防止"单维度高分节点"污染
- 机制：要求节点同时满足 vector_hot AND keyword_hot
- 未修改（无需修改）

**阶段2：Parent Coverage Score（软评分）**
- 目的：在高质量候选集合中选择最优父节点
- 机制：综合评分 coverage_ratio + avg_child_vector + support_bonus
- 已修改权重分配

---

### 权重调整的合理性

#### coverage_ratio 降低 (0.50 → 0.40)

**原因：**
- 原权重过高，导致过度偏向"小集合完美覆盖率"
- Parent A 只有2个子节点，容易达到 coverage_ratio=1.00
- 降低权重后，覆盖率不再是绝对主导因素

#### support_bonus 提高 (0.20 → 0.30)

**原因：**
- 原权重过低，无法充分奖励"更多高质量子节点"
- Parent B 有5个 dual_hot 子节点，但优势被封顶机制限制
- 提高权重后，子节点数量的优势得到体现

---

## 设计偏差分析

### 原设计的隐含假设 vs 实际情况

| 原设计假设 | 实际情况 | 偏差后果 |
|------------|----------|----------|
| coverage_ratio 高 → 父节点质量好 | 小集合容易达到高覆盖率，但子节点质量可能低 | 选择低质量父节点 |
| support_bonus 封顶防止偏向大集合 | 大集合的高质量子节点优势被限制 | 忽略高质量父节点 |
| coverage_ratio 主导评分 | 忽略了子节点数量的绝对优势 | 权重失衡 |

---

## 修复后的行为变化

### 选择策略转变

**修复前：偏向"小而全"**
- 选择 coverage_ratio 完美的父节点
- 忽略子节点数量和质量差异
- 结果：返回低相关性内容

**修复后：偏向"大而优"**
- 选择 dual_hot 子节点数量多的父节点
- coverage_ratio 仍重要但非绝对主导
- 结果：返回高相关性内容

---

## 关键改进

### 1. 子节点数量优势得到体现

```
Parent B 的优势（5个 dual_hot 子节点）：
  修复前：support_bonus = 1.0（封顶），权重 0.20 → 贡献 0.20
  修复后：support_bonus = 1.0（封顶），权重 0.30 → 贡献 0.30

增幅：+50%（0.20 → 0.30）
```

### 2. 覆盖率不再是绝对主导

```
Parent A 的优势（coverage_ratio=1.00）：
  修复前：权重 0.50 → 贡献 0.50
  修复后：权重 0.40 → 贡献 0.40

降幅：-20%（0.50 → 0.40）
```

### 3. 权重平衡性提升

```
修复前权重分配：
  coverage_ratio：50%（主导）
  avg_child_vector：30%
  support_bonus：20%（弱势）

修复后权重分配：
  coverage_ratio：40%（降低）
  avg_child_vector：30%
  support_bonus：30%（提升）

平衡性：更合理的权重分配
```

---

## 影响范围

### 不影响的功能

✓ Dual-hot intersection 计算（阶段1）
✓ Vector candidates 计算
✓ Keyword hits 计算
✓ Traverse 逻辑（waypoint + evidence）
✓ EvidenceContentResolver

### 改变的功能

仅改变 Parent Coverage Selection 的排序结果

---

## 测试验证

### Phase 14 完整验证

```bash
python verification/phase14-new-doc-validation/run_validation.py --phase retrieve
```

**结果：**
```
[Phase 1 COMPLETE] Retrieve pipeline finished
  - Total hits: 100
  - Queries with hits: 20/20
  - Evidence chunk hits: 100
  - Missing chunk hits: 0 (target: 0)
  [PASS] Phase 13 validation: hotspot traverse returns real evidence
```

### 白盒测试验证

```bash
python verification/phase14-new-doc-validation/whitebox_retrieval_demo.py
```

**预期结果：**
- Q2 应返回 Parent B 的子节点（实施建议、执行摘要）
- 不再返回 Parent A 的子节点（仓库元数据）

---

## 结论

### 修复成功

✓ Phase 14 验证通过（100 evidence, 0 missing）
✓ 排序逻辑反转（选择高相关父节点）
✓ 权重分配合理化

### 改动最小

- 只修改2个数值（权重常量）
- 不改变两阶段架构
- 不影响核心检索逻辑

### 解决根本问题

**问题本质：** 不是两阶段架构设计缺陷，而是阶段2评分权重的分配偏差

**修复效果：** 保留两阶段架构的优点，纠正权重分配的偏差

---

## 后续优化方向（可选）

### 1. 引入子节点质量评分

```python
# 更精细的评分（考虑子节点内容相关性）
child_quality_score = (
    child_similarity * 0.4 +
    child_keyword_coverage * 0.3 +
    child_feature_match * 0.3
)
parent_quality_avg = avg(child_quality_scores)
```

### 2. 移除 support_bonus 封顶

```python
# 允许大集合的线性优势
support_bonus = hot_count / 5.0  # 无封顶
```

### 3. 动态权重调整

```python
# 根据文档结构动态调整权重
if len(children) < 3:
    # 小集合：提高 coverage_ratio 权重
    coverage_weight = 0.50
else:
    # 大集合：提高 support_bonus 权重
    coverage_weight = 0.40
```

**当前修复已足够，后续优化可根据实际效果决定是否实施。**