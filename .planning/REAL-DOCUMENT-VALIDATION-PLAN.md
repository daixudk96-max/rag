# 真实文档验证计划 — PageIndex 质量目标达成度验证

> 状态：DRAFT（待用户审批后执行）
> 创建：2026-06-23
> 目的：填补"当前生产 selector（hybrid_cluster）的真实检索质量从未被测量"这一核心缺口，给出项目根本质量目标（Level 3/4 就绪）的诚实达成度结论。

---

## 0. 为什么需要这个计划（缺口诊断）

12 个 Phase 全部跑完了 GSD 流程，工程基础设施完整且诚实，但**项目的根本质量目标尚未验证达成**：

| 事实 | 证据 |
|------|------|
| 唯一有真实质量数字的是 Phase 8（hit_rate 0.70 / top1 0.59 / stability 0.65），三项全部未达标 | `verification/phase8-matched-validation-rerun/level_assessment.json` |
| **但 Phase 8 用的不是当前线上 selector** | Phase 8 走旧路径；`.env` 现为 `RAG_TREE_HOTSPOT_SELECTOR=hybrid_cluster` |
| 当前生产 selector（hybrid_cluster）的 hit_rate/top1/stability **一次都没算过** | Phase 10/11/12 质量指标全为 `null`，状态 `NOT_CALCULATED_PENDING_JUDGMENTS` |
| 旧 Phase 8 judgments 无法复用到 hotspot 检索 | `phase10_quality_metrics.json`：`reuse_rate=0.0375`（95 行只匹配 3 行） |
| 现有"真实文档"语料是窄样本 | `p6_final_sample_structured.md`：3.7 KB / 10 条查询 / 单一 DNA 案例主题 |
| DNA 查询"通过"只是单点语义路由回归，≠ 质量阈值达标 | `validation_status.json`：`passed:true` 仅指功能+DNA |

**一句话**：当前权威基线仍是 **Level 2（能查但质量未验证）**，且现网 selector 的真实质量是一个**未测量的黑盒**。本计划负责把这个黑盒打开。

---

## 1. 目标与非目标

### 目标
1. 用 **hybrid_cluster（当前生产 selector）** 在**真实、足量、有代表性的业务文档**上跑端到端检索。
2. 收集 **hotspot-specific 人工判断**，让 hit_rate / top1_relevance / stability 三项指标能被**诚实计算**（不再是 `null`）。
3. 产出一个对当前 selector 有效的 `level_assessment.json`，明确回答：**Level 2 维持，还是可以晋升 Level 3/4？**
4. 若未达标，给出**带证据的失败模式分析**（哪些查询失败、为什么、是检索召回问题还是排序问题）。

### 非目标
- 不在本计划中修改检索算法（先测量，再决定是否优化 → 留给后续 Phase）。
- 不做 commit/tag/push/milestone 归档（Phase 9 的关闭门仍需单独审批）。
- 不复用任何旧 corpus 的 judgments（reuse 已证明不可行，会污染指标）。

---

## 2. 冻结的验收阈值（不可在跑分后修改）

| 指标 | 阈值 | 来源 |
|------|------|------|
| hit_rate | ≥ 0.80 | Phase 2 冻结阈值 |
| top1_relevance | ≥ 0.90 | Phase 2 冻结阈值 |
| stability | ≥ 0.85 | Phase 2 冻结阈值 |
| 辅助：tree_depth | ≥ 3 | Phase 2 |
| 辅助：node_chunk_mapping | ≥ 0.80 | Phase 2 |
| 辅助：heading_path_rate | ≥ 0.95 | Phase 2 |

**等级判定**：三项核心指标全过 → 可议 Level 3/4；任一未过 → Level 2 维持（保守原则，沿用全程纪律）。

---

## 3. 语料策略（关键改进点）

现有 p6 窄样本不足以代表"真实文档检索质量"。本计划要求 **2 档语料**：

### 档位 A — p6 回归基线（必跑，保证可比性）
- 文档：`verification/p6_validation/p6_final_sample_structured.md`
- 查询：现有 10 条（含 DNA 查询）
- 作用：与 Phase 11 功能验证结果直接对齐，确认 hybrid_cluster 在已知样本上不回归。

### 档位 B — 真实业务文档（新增，本计划的核心）
- 文档要求：
  - **真实来源**（非为测试构造），建议从真实 DOCX/PDF 业务文档经现有 ingestion pipeline 入库；
  - **规模**：≥ 30 KB 正文，≥ 3 层标题层级，≥ 40 个 tree node（避免单案例主导）；
  - **多主题**：覆盖 ≥ 3 个不相关主题域（检验跨主题区分能力，而非单一 DNA 案例）。
- 查询集：**15–20 条**业务查询，覆盖：
  - 事实型（答案在单一节点）
  - 对比型（答案需跨节点聚合）
  - 边界型（文档中不存在答案 → 检验是否诚实返回低分/空，而非幻觉命中）
- **来源待用户确认**：是复用某个已有真实 DOCX（如历史 `PageIndex完整功能分析与集成方案.md` 域），还是提供新文档。详见 §7 开放问题。

---

## 4. 执行管线（复用现有基础设施，零新造轮子）

直接复用 `verification/phase11-.../run_validation.py` 作为模板（它已封装：强制 selector、ingestion、tree/vector 物化、检索、证据链报告、judgment 模板生成、fail-closed）。

```
Step 1  环境门         DATABASE_URL 可达 + RAG_TREE_HOTSPOT_SELECTOR=hybrid_cluster
                       → 01_environment_check.json
Step 2  入库           真实文档经 IngestionPipeline → TreeGenerator → VectorLoader
                       → 02_document_ingestion_status.json / 03_tree_vector_status.json
Step 3  检索           对每条查询跑 retrieve_tree_hits_from_pdf（top_k=5）
                       → 04_query_set.json / 05_hotspot_retrieval_results.json
Step 4  证据链门       校验 hotspot_metadata_rate / navigation_path_rate / 0 空 preview
                       → 06_evidence_chain_report.json
Step 5  判断模板       自动生成空 judgment CSV（relevance/evidence_quality/answer_support 待填）
                       → 07_judgment_template.csv
Step 6  人工判断       【人工门】对每个 hit 标注 relevance（0/1/2）等 → 07_judgment_completed.csv
Step 7  完整性门       fail-closed 校验：检索行数 == 判断行数、无 corpus 错配、无 unknown_hit
Step 8  指标计算       仅在完整性门通过后计算 hit_rate/top1/stability
                       → 08_quality_metrics.json
Step 9  等级评估       对照冻结阈值判定 Level
                       → 09_level_assessment.json
Step 10 总结           → 10_validation_summary.md（含失败模式分析）
```

**安全约束（沿用全程纪律）**：
- 任何 JSON 产物**不得写入原始 `DATABASE_URL`**。
- 不做 commit/tag/push；产物落在 `verification/` 目录作为开发日志。
- 完整性门未过 → 退出码非零，指标保持 `null`，**绝不宣称 Level 晋升**。

---

## 5. 输出产物清单

落地目录：`verification/real-document-validation-<date>/`

| 文件 | 内容 |
|------|------|
| `01_environment_check.json` | DB 可达性 + selector 确认（hybrid_cluster） |
| `02_document_ingestion_status.json` | 真实文档入库状态 + 层级 |
| `03_tree_vector_status.json` | tree/vector 物化计数 |
| `04_query_set.json` | 15–20 条业务查询定义 |
| `05_hotspot_retrieval_results.json` | 每查询命中 + hotspot/navigation 元数据 |
| `06_evidence_chain_report.json` | 元数据/provenance 率 |
| `07_judgment_template.csv` | 待填人工判断模板 |
| `07_judgment_completed.csv` | **人工填写后**的判断 |
| `08_quality_metrics.json` | hit_rate / top1 / stability（真实计算） |
| `09_level_assessment.json` | 等级判定 + blocking_factors |
| `10_validation_summary.md` | 结论 + 失败模式分析 + 与 Phase 8 对比 |

---

## 6. 验收标准（本验证计划自身的"做完了"定义）

- [ ] 档位 A（p6）功能回归通过，DNA 查询语义路由不回归。
- [ ] 档位 B（真实文档）成功入库，tree_depth ≥ 3，node_chunk_mapping ≥ 0.80。
- [ ] 15–20 条查询全部检索成功（query_failures = 0）。
- [ ] 人工判断完整收集，完整性门通过（检索行数 == 判断行数）。
- [ ] `08_quality_metrics.json` 三项指标为**真实数字**（非 null）。
- [ ] `09_level_assessment.json` 给出明确等级结论。
- [ ] `10_validation_summary.md` 包含：与 Phase 8（0.70/0.59/0.65）的对比、失败查询逐条归因。

**通过路径**：三项达标 → 启动 Level 3/4 晋升讨论（新 Phase）。
**未通过路径**：指标 + 失败模式 → 作为检索算法优化的输入（新 Phase），Level 2 维持。

---

## 7. 开放问题（需用户决策后才能执行）

1. **真实文档来源**：复用历史 `PageIndex完整功能分析与集成方案.md` 域文档？还是你提供一份新的真实 DOCX/PDF？还是用某个真实业务文档？
2. **人工判断由谁做**：你本人标注，还是需要我先生成一版"自动初判 + 你复核"的草稿来降低工作量？
3. **DATABASE_URL / Docker**：当前 PostgreSQL/pgvector 环境是否可用？（Phase 7/8/10 多次因 DB 不可达走 fail-closed，需先确认环境就绪。）
4. **是否纳入 GSD Phase**：把本计划登记为正式 Phase 13（走完整 plan→execute→verify→close），还是作为一次性验证任务直接执行？

---

## 8. 建议的下一步

待你回答 §7 的 4 个问题（尤其是 **1 文档来源** 和 **3 DB 环境**）后，我可以：
- **方案 A**：登记为 Phase 13，用 `/gsd-plan-phase 13` 走完整 GSD 流程（推荐，与全程一致）。
- **方案 B**：直接基于 phase11 的 `run_validation.py` 改造出新 runner，一次性执行档位 A + B。

> 在 §7 决策明确前，本计划保持 DRAFT，不执行任何入库/检索/commit 动作。
