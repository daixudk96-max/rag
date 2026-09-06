# 计划：jieba 关键词提取接入（增强 Phase 11 HybridClusterHotspotSelector）

> 轻量计划文档（非 GSD 里程碑流程）。经用户明确授权直接编写。
> **已选定方案：方案 B（纯 jieba 替换）+ jieba 进主依赖。接受 B 的全部代价。**
> 状态：**计划已定稿 — 执行前停止**。开工需你单独发话。

---

## 1. 问题与真实证据

热点检索的融合评分由四部分加权组成：

| 成分 | 权重 | 作用 |
|------|------|------|
| 向量相似度（sentence-transformers） | 0.40 | 语义相似 |
| **关键词匹配** | 0.30（全覆盖时 **2.00**） | 字面词命中 heading |
| 重排序 | 0.20 | 默认关闭 |
| 子节点分布 | 0.10 | 多子证据 |

关键词这一层依赖 `_extract_keywords_from_query`（`llamaindex_runtime/tree/runtime.py:40`）。当前是「停用词/连接词 replace + 正则取词」实现。实测它在复杂句式上**把整句粘连成一个伪关键词**：

| 查询 | 当前 regex 结果 | 评价 |
|------|----------------|------|
| `AI产品经理的核心DNA是什么？` | `['AI产品经理', '核心DNA']` | ✅ 恰好正确 |
| `为什么数据对AI产品如此重要？` | `['数据对AI产品如此重要']` | ❌ 整句粘连 |
| `什么是数据闭环飞轮？` | `['数据闭环飞轮']` | ❌ 整块未拆 |
| `cardiac arrhythmia diagnosis` | `['cardiac','arrhythmia','diagnosis']` | ✅ |

整句粘连的关键词几乎不可能命中任何 heading 子串 → 关键词层贡献 0 → 该走的段落（如 `04:40 - 数据工作重要性`）拿不到关键词加分 → 排名下沉（参见 `test_single_query_result.json`，期望区落到第 4/5 名）。

### 根因
`replace` 只能切掉**枚举到的**连接词（`的/是/为什么/什么是/…`）。句中 `对`、`如此`、`重要` 等没被枚举，于是 `数据对AI产品如此重要` 整段残留，正则 `[A-Za-z0-9一-鿿]+` 把它当成一个 token。本质是「黑名单式切词」覆盖不全。

---

## 2. 选定方案 B：纯 jieba 替换（实测输出）

用 `jieba.cut` 全量分词取代现有 `replace`+正则逻辑，配通用停用词表过滤虚词。实测输出：

| 查询 | 方案 B 关键词 | 评价 |
|------|--------------|------|
| `AI产品经理的核心DNA是什么？` | `['AI','产品','经理','核心','DNA']` | 复合词拆碎（B 的已知代价） |
| `为什么数据对AI产品如此重要？` | `['数据','AI','产品','重要']` | ✅ 粘连修复 |
| `什么是数据闭环飞轮？` | `['数据','闭环','飞轮']` | ✅ 拆开 |
| `cardiac arrhythmia diagnosis` | `['cardiac','arrhythmia','diagnosis']` | ✅ 不变 |

**为什么选 B 而非分层方案 A**：B 实现最干净（单一分词路径，无长度阈值魔法数），跨领域行为一致、可解释。代价是 `AI产品经理`→`AI/产品/经理`、`核心DNA`→`核心/DNA`，需改写现有测试断言并复验 p6 DNA 回归。用户已明确接受全部代价。

**不引入专有名词词典**（你的硬约束）：B 完全依赖 jieba 内置词典，复合词被拆碎正是「无专有词典」的直接结果，符合约束。

---

## 3. 这是关键词对比，不是向量对比（回答你的反复确认）

本计划只动「拆词 → heading 关键词匹配」这一层。向量层（`_cosine_similarity` + sentence-transformers）完全不碰。jieba 仅改善 `keyword_hits` 的 `matched_terms` 质量，进而影响 `semantic_distribution.py` 里的 `term_coverage = 本节点匹配词数 / 全部匹配词数` 与「全覆盖 → 2.00 权重」判定。

---

## 4. 方案 B 的连带影响（必须正视，已纳入执行步骤）

jieba 把复合词拆细 → 单次查询的关键词**数量变多、粒度变碎**，对融合评分有两层传导：

1. **term_coverage 分母变化**：`AI产品经理的核心DNA是什么？` 的匹配词集从 `{AI产品经理, 核心DNA}`(2) 变成 `{AI, 产品, 经理, 核心, DNA}`(5)。「全覆盖→2.00 权重」的达成条件随之改变。
2. **碎词更易误命中**：`AI`、`产品` 等短词可能命中无关 heading，稀释精确性。这正是 term_coverage 机制要对冲的，但分母变大后单个精确锚点（原 `核心DNA`）的独占优势消失。

→ 因此 **p6 DNA 语义回归（`数据驱动 / 非确定性 / 持续性`）必须复验**，必要时在 `HybridClusterHotspotSelector` 调整 `_KEYWORD_WEIGHT / _EXACT_KEYWORD_WEIGHT`。这一项作为第 6 节的显式验证步骤 + 第 5 节的潜在改动点。

---

## 5. 具体改动点（方案 B）

1. **依赖声明** — `llamaindex_runtime/pyproject.toml`
   `dependencies` 增加 `"jieba>=0.42.1"`（系统环境已装 0.42.1，补声明保证可复现）。

2. **核心实现** — `llamaindex_runtime/tree/runtime.py::_extract_keywords_from_query`
   - 顶部惰性 `import jieba` + `jieba.setLogLevel(logging.WARNING)`（压制首次加载日志）。
   - **删除** 现有 `split_terms` replace 逻辑，改为 `jieba.cut(query_text)` 全量分词。
   - 扩展通用停用词表（仅虚词/疑问词，**非领域专有词**）：在现有 `{的,是,什么,有,在,和,了,与,及,等}` 基础上补 `为什么 / 如何 / 怎么 / 如此 / 对 / 这个 / 那个 / 之 / 中 / 吗 / 呢 / 会 / 被 / 并 / 也`。
   - 过滤规则维持现契约：`token.strip()`、长度 ≥ 2、去重、保序、至少含一个 `[A-Za-z0-9一-鿿]` 字符。
   - 返回类型 `list[str]` 不变 → 调用方 `_retrieve_tree_hits_from_backend` 无需改动。

3. **改写现有测试断言** — `tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector.py::TestHybridRuntimeKeywordExtraction`（第 643–667 行）
   - `test_extract_keywords_splits_mixed_cjk_latin_query`：断言改为 jieba 碎词契约 —— `"AI" in keywords`、`"产品" in keywords`、`"DNA" in keywords`，并保留 `"AI产品经理的核心DNA是什么" not in keywords`（整句不粘连这条仍成立）。
   - `test_extract_keywords_match_expected_dna_heading`：`matched_keywords` 期望从 `["AI产品经理","核心DNA"]` 改为 jieba 实测的 `["AI","产品","经理","核心","DNA"]`（均命中 DNA heading）。
   - 在测试 docstring 注明：契约已从「复合词完整」迁移到「jieba 内置词典碎词」，因放弃专有词典。

4. **新增测试** — 同文件
   - `test_extract_keywords_splits_glued_why_query`：`为什么数据对AI产品如此重要？` → 含 `数据`、`AI`、`产品`、`重要`，且 `数据对AI产品如此重要` **不**在结果中（核心修复锚点）。
   - `test_extract_keywords_handles_pure_latin_unchanged`：英文查询 `cardiac arrhythmia diagnosis` 行为不回归。
   - `test_extract_keywords_no_domain_dictionary`：非 p6 领域查询验证仅靠内置词典正常分词。

5. **（条件性）调权** — `llamaindex_runtime/tree/semantic_distribution.py::HybridClusterHotspotSelector`
   仅当第 6 节 step 3 的 p6 DNA 复验显示排序回归时，才微调 `_KEYWORD_WEIGHT` / `_EXACT_KEYWORD_WEIGHT`，并补一条针对新 term_coverage 行为的回归测试。若不回归则不动，保持改动最小。

---

## 6. 验证计划（真实文档，非历史结果）

1. **关键词单元测试**：`python -m pytest tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector.py::TestHybridRuntimeKeywordExtraction -q` —— 改写后的断言 + 3 个新增用例全绿。
2. **全量回归**：`python -m pytest tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector.py -q` —— 22 条（含融合评分/选择器）全通过。
3. **p6 DNA 语义回归复验（B 的强制步骤）**：复跑 DNA 查询 `AI产品经理的核心DNA是什么？`，确认期望热点区（`产品特性对比`）仍被选中、证据仍含 `数据驱动 / 非确定性 / 持续性`。**若回归 → 执行 step 5 调权 → 复验直至通过。**
4. **目标查询真实复跑**：`python test_single_query_live.py`（`为什么数据对AI产品如此重要？`），核对 `04:40 - 数据工作重要性` 区段排名较改前上升，结果写入 `test_single_query_result.json` 供肉眼判读。
5. **延时复核**：`python measure_keyword_latency.py` 确认 jieba 开销仍在 ~1.65ms/次量级。

---

## 7. 安全门（遵守项目 CLAUDE.md）

- 改 `_extract_keywords_from_query` 前，先 `gitnexus_impact({target:"_extract_keywords_from_query", direction:"upstream"})`，blast radius 报你。预估：模块私有、仅 1 处调用，风险 **LOW**。
- 若触发 step 5 调权，改 `HybridClusterHotspotSelector` 相关符号前同样先跑 `gitnexus_impact`（该类已知 HIGH/CRITICAL 关联，需谨慎、增量、开关可回滚）。
- 改动后 `gitnexus_detect_changes()` 核对影响范围只限预期符号。
- 不提交、不打 tag、不 push（沿用当前会话约束，等你单独批准）。

---

## 8. 风险与回滚

| 风险 | 处理 |
|------|------|
| jieba 碎词改变 term_coverage 分母，p6 DNA 排序回归 | 第 6 节 step 3 强制复验；step 5 条件性调权兜底 |
| 碎短词（`AI`/`产品`）误命中无关 heading | term_coverage 机制对冲；全量回归 step 2 把关 |
| 改写测试断言削弱 Phase 11 关键词回归锚点 | 用户已接受；新增 glued-query 用例补强新锚点 |
| jieba 首次加载延时 | 已测 +1.65ms/次，可忽略；惰性 import |
| 回滚 | 改动集中在单函数 + 一行依赖（+ 可选调权）；`git checkout` 单文件即可恢复 |

---

## 9. 决策记录（已定，无未决项）

| 决策 | 选定 |
|------|------|
| 切词方案 | **方案 B：纯 jieba 替换** |
| 现有两个关键词测试 | **改写断言为 jieba 碎词契约**（接受 B 全部代价） |
| p6 DNA 连带影响 | **作为第 6 节 step 3 强制复验步骤 + 第 5 节 step 5 条件性调权** |
| jieba 依赖位置 | **主依赖** `llamaindex_runtime/pyproject.toml` `dependencies` |
| 专有名词词典 | **不引入**（硬约束，B 天然满足） |

---

## 10. 执行顺序（开工后照此走，当前不执行）

1. `gitnexus_impact` on `_extract_keywords_from_query` → 报 blast radius。
2. 改 `pyproject.toml` 加 `jieba>=0.42.1`。
3. 改写 `_extract_keywords_from_query` 为纯 jieba（第 5 节 step 2）。
4. 改写 2 个现有测试断言 + 新增 3 个测试（第 5 节 step 3-4）。
5. 跑第 6 节 step 1-2（单元 + 全量回归）。
6. 跑第 6 节 step 3（p6 DNA 复验）；若回归 → 第 5 节 step 5 调权 → 复验。
7. 跑第 6 节 step 4-5（真实查询 + 延时）。
8. `gitnexus_detect_changes()` 核对范围。
9. 汇报结果，**停在提交前**等你批准。

> 以上为定稿计划。**现在不执行任何一步**，等你单独发话开工。
