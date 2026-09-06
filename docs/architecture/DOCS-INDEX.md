# Docs Index

这次重新整理后，`docs/` 不再按我主观发明的语义分组，而是尽量按**原本目录主线**和**文档真实来源**来组织。

## 1. `.planning/`
这是 **GSD / AUTOD 的项目级规划状态**，属于过程性文档。

包含：
- `PROJECT.md`
- `REQUIREMENTS.md`
- `ROADMAP.md`
- `STATE.md`
- `contracts/`
- `phases/`
- `research/`

你如果要看：
- 当前阶段推进到哪
- requirements 怎么拆的
- 每个 phase 的计划和 summary

先看这里。

---

## 2. `plans/`
这是 **路线图与阶段计划的独立规划文档**。

当前主要有：
- `provenance-centric-multi-view-rag-roadmap.md`
- `phase-1-v1-poc-plan.md`

它们更偏“路线图级别”的收束，不是最新执行状态本身。

---

## 3. `research/`
这是 **搜索、调研、比较、核验结果**。

包含：
- `deep-research-report*.md`
- `verified-project-matrix.md`
- `final-selection-checklist.md`
- `technical-questions-verification.md`
- `chunking-strategies-comparison.md`
- 两个 `.ini` 原始调研材料

你如果要追问：
- 某个项目为什么被选 / 没被选
- 某个技术判断外部依据在哪
- 哪个项目贡献了哪部分思路

先看这里。

---

## 4. `architecture/`
这是 **真正的目标架构主线文档**。

重点文件：
- `LLAMAINDEX-TARGET-ARCHITECTURE.md`
- `LLAMAINDEX-PHASE-1-PLAN.md`
- `PROJECT-COMBINATION-MAP.md`
- `decision-llamaindex-first.md`
- `llamaindex-implementation-assessment.md`
- `complete-implementation-roadmap.md`
- `data-model/` 下的存储与 schema 设计

如果你要看：
- 真实项目最终应该长什么样
- 基于 LlamaIndex 的正式主线是什么
- 从哪个项目吸收了哪个部分
- 第一部分真正该怎么做

先看这里。

---

## 5. `diagrams/`
这是 **架构图 / 结构图 / 关系图**。

包含：
- `final-architecture-diagram.html`
- `llamaindex-tool-integration-diagrams.*`
- `storage-alignment-key-diagram.html`

适合快速理解系统结构，但不替代正文说明。

---

## 6. `validation/`
这是 **真实验证报告**。

当前包含：
- `real-validation-report.md`

它属于“验证实现线”的结果说明，不等于正式实现主线。

---

## 7. `verification/`（代码，不在 docs 里）
注意：
- `verification/` 目录里的代码是**验证实现 / 参考实现 / 行为基线**
- 它已经证明主干可行，但它不是最终要交付的 LlamaIndex-first 正式实现

---

## 你现在最该看的顺序

### 如果你要看“真实项目怎么做”
1. `architecture/LLAMAINDEX-TARGET-ARCHITECTURE.md`
2. `architecture/PROJECT-COMBINATION-MAP.md`
3. `architecture/LLAMAINDEX-PHASE-1-PLAN.md`
4. `architecture/decision-llamaindex-first.md`
5. `diagrams/final-architecture-diagram.html`

### 如果你要看“现在验证到什么程度了”
1. `.planning/STATE.md`
2. `.planning/phases/`
3. `validation/real-validation-report.md`
4. `../verification/README.md`

### 如果你要追溯“这些判断依据从哪来”
1. `research/verified-project-matrix.md`
2. `research/final-selection-checklist.md`
3. `research/deep-research-report (3).md`
4. `research/technical-questions-verification.md`

---

## 当前最重要的区分

### 目标架构主线
在：
- `docs/architecture/`

### 验证实现线
在：
- `verification/`
- `docs/validation/`
- `docs/.planning/`

这两条线现在已经明确区分开了。