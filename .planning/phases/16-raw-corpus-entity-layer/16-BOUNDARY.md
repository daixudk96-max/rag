# Phase 16 (交接书阶段 C): Raw Corpus Entity Layer — Boundary Document

**Drawn:** 2026-07-12（plan-everything-execute-nothing 指令下的预规划产物）
**Reconciled:** 2026-08-06 — Phase 16 atomic planning COMPLETE：18 个连续原子计划 `16-01-PLAN.md..16-18-PLAN.md`（38 个计划任务），scheduler waves 0..8 / macro waves W0..W7。**EXECUTION NOT AUTHORIZED。** 本文件已由历史输入 reconcile 为最终 planning boundary；与 `16-RESEARCH.md` / `16-PATTERNS.md` / `16-01..16-18-PLAN.md` / `16-VALIDATION.md` 一致。以下任何历史表述（尤其 migration 019/020/021、`node_entity_links`、candidate audit、per-span transaction、Open Questions）与「Reconciled Planning Decisions」冲突时，一律以后者及 PLAN 为准。
**Depth:** 已到原子计划深度。进入 EXECUTE 需要用户显式授权，本文件不构成任何执行授权。
**Authority:** 交接书 §11-C/§11-C2 + 总纲 D7 + ADR T4/T6 + 里程碑边界裁决 2/3/9 + 补充交接书 `.planning/OKF-LOW-TOKEN-GAPS-SUPPLEMENT-HANDOFF-2026-07-12.md` §4（16-C2）+ `.planning/research/PHASE16-CHINESE-NER-MODEL-SELECTION-2026-07-13.md`（C1 精确模型 artifact、适配器契约与验收门）。**对 C1 模型、switch、输出/置信度语义和 fallback 的历史 HanLP/UIE 表述发生冲突时，以该 2026-07-13 模型选型裁决为准；对 C2 则仍以补充交接书 §4 为准。**
**内部结构（2026-07-12 补充）：** 本阶段分两个 wave 组——**C1**（主 wave：抽取/归一/链接，即下文原有内容）与 **C2**（条件性第二 wave：中文局部指代链，见 §16-C2 节）。

## 执行附录（2026-08-06）— 实际执行状态（对上方历史规划事实的补充）

> 上方冻结的规划事实（尤其「EXECUTION NOT AUTHORIZED」、`wave_0_complete:false`、「尚无任何 `16-xx-SUMMARY.md`」、「未运行/通过任何计划测试」）描述的是 2026-08-06 原子规划完成时点的**规划时状态**，予以保留。以下为截至 2026-08-06 的实际执行状态：
>
> - **仅授权静态/纯 Wave 0（plans 16-01/16-02）已实际执行**：control-plane selectors 25 passed；entity contracts 45 passed（`contracts.py` 173 statements、0 missed、100%）；packaging/lazy-import selector 33 passed（2 非致命 deprecation warnings；该 selector 可能在别处 import torch，不构成默认 config/entity 导入边界的证明）；config compatibility 14 passed；affected RuntimeSettings regression 15 passed/6 deselected；scoped whitespace audit clean；一次 stable-delta Sonnet review APPROVE（0 critical/high/medium、4 low non-blocking）。`16-01-SUMMARY.md` 与 `16-02-SUMMARY.md` 已存在；`16-VALIDATION.md` 为 draft 且记录 Wave 0 证据（`wave_0_complete:true`、`nyquist_compliant:false`）。
> - **Marker 注册本身不会把测试排除出默认 pytest 收集**：live 测试排除需显式 `-m` filter；Wave 0 未创建任何 `live_ner`/`disposable_db` 测试模块。
> - **当前 /goal 授权有序非 live C1 推进**（下一 scheduler Wave 1 按序），但**未声称任何后续 wave 已开始**；后续所有工作（Waves 1-4）、五个 live gates（`blocked_not_executed`）与 C2（`skipped_not_entered`，未授权）均保持未执行。
> - 本附录不改变上方任何冻结的 D1-D9 决策、计划数量、验收边界或 Planned Acceptance Criteria（仍为计划中、未达成）。

## Entry Gate

1. **Planning complete (2026-08-06):** 18 个连续原子计划已交付（`16-01-PLAN.md..16-18-PLAN.md`），38 个计划任务；scheduler waves 0..8（wave 0: 16-01,16-02 · wave 1: 16-03,16-04,16-05,16-07 · wave 2: 16-06,16-08,16-12 · wave 3: 16-09,16-10,16-13 · wave 4: 16-11 · wave 5: 16-14 · wave 6: 16-15,16-16 · wave 7: 16-17 · wave 8: 16-18），macro waves W0..W7。尚无任何 `16-xx-SUMMARY.md`。`16-VALIDATION.md` 仍为 draft（`nyquist_compliant:false`、`wave_0_complete:false`），全部 pending；planned files 尚未实现，未运行/通过任何计划测试。
2. **Execution requires explicit user authorization — EXECUTION NOT AUTHORIZED.** Phase 16 implementation、tests、migration、dependency/config、model、Docker/PostgreSQL、C1/C2 live execution 均未授权且未执行。五个 future live gates 全部未授权（disposable migration；ModelScope mirror creation；real local RaNER smoke/resource measurement；disposable full-corpus E2b acceptance；conditional C2 entry/live acceptance）。
3. **C2 子波另需** C1 acceptance CLOSED 后才可条件进入（见 §16-C2）；`skipped_not_entered` 不阻塞基于 C1 的 Phase 16 closure，但不能声称 R-OKF-09 live-tested。

## Goal

**E2b — NER-derived entity-layer materialization, parity, and idempotence.** 用零/低 token 的本地非生成式模型与确定性补充源，从 OKF raw 语料建立 NER-derived 实体层：**固定标签通用中文 NER 负责上下文驱动的词典外 mention 发现**，领域词典、OKF frontmatter 与规则负责高置信补充、领域锚定和归一；产出 `entity_mentions`（字符级坐标）、NER aliases/merge provenance 与 `node_entity_links`。E2b 不重复或改写 Phase 15 E2a 已物化的人工 OKF entities/relations/evidence；两阶段的 evidence 共同构成完整 derived-association parity。C1 唯一主模型 artifact 冻结为 ModelScope `iic/nlp_raner_named-entity-recognition_chinese-large-generic`（XLM-RoBERTa Large + Transformer-CRF，固定六类）；它可直接推理，**项目标注或微调不是初始使用前置条件**。功能总开关默认 off，启用后的基准组合为“RaNER 主识别 + 词典/frontmatter/规则补充”；全程零生成式 LLM token（R-OKF-04）。PaddleNLP `2.8.1` 的 `uie-base` 仅作未来 schema-guided 领域扩展，RaNER `chinese-base-news` 仅作资源受限降级候选，HanLP 仅作研究/评测备用，DeepKE 未达到 artifact 冻结条件。精确 artifact manifest、许可边界、输出契约与证据见 `.planning/research/PHASE16-CHINESE-NER-MODEL-SELECTION-2026-07-13.md`。

## In Scope

- 抽取器接口定义（Protocol 风格，参照仓库 python patterns）：`extract(inputs: Sequence[ExtractionInput]) -> list[MentionCandidate]`，其中 `ExtractionInput = CorpusSpanInput | QueryTextInput`；两者共享 normalized-text 坐标、模型/label-map/provenance 契约，但只有 `CorpusSpanInput` 带 document revision/sidecar projection 并允许持久化，`QueryTextInput` 只带 query-local immutable identity 且禁止进入 corpus evidence 表。首期实现注册 + 总开关固定为 `RAG_ENTITY_EXTRACTOR=off|raner`，默认 off 上线。固定标签 C1 公共接口不接收 UIE 专属 schema；未来 UIE adapter 的版本化 schema 由 adapter 配置持有。不得提前暴露没有可运行 adapter 的 `uie`、`base-news`、`hanlp` 或 `deepke` 值。**C1 验收不得只有接口或纯词典实现：RaNER Large Generic 适配器必须真实可运行。**
- **模型主识别（artifact 已冻结）**：首选为 `iic/nlp_raner_named-entity-recognition_chinese-large-generic`。标准 pipeline 输出 `type/start/end/span`，适配器映射为 `raw_label/char_start/char_end/mention_text` 并断言 `input.normalized_text[start:end] == span`；标准输出无 mention confidence，必须保存 `confidence=None`、`confidence_kind="unavailable"`，不得伪造概率（当前 SDK 默认输出 `prob`，适配器必须显式剥离）。仓库总大小约 **2.26 GB（一律指模型 artifact/weight footprint，不是文本输入预算）**，完整逐文件 SHA-256 manifest 见模型选型研究文档；执行时必须镜像到只读本地缓存、断网加载，并记录实际 snapshot revision。固定标签为 `PER/LOC/CORP/GRP/CW/PROD`，通过版本化 label map 映射到 OKF canonical types。
- **统一 DTO 与判别坐标空间（已冻结）**：`MentionCandidate` 至少包含 `input_id`、`input_kind=corpus_span|query_text`、不可变 `input_revision`、`span_id: str | None`、`mention_text`、`raw_label`、归一化 `entity_type`、`char_start`、`char_end`、`confidence: float | None`、`confidence_kind`、`source`、`extractor_id/version`、`model_id/revision`、`artifact_digest`、`schema_version`，并关联 `normalization_version`、`segmentation_version`、`label_map_digest` 与 runtime compatibility ID。`char_start/char_end` 统一为对应 input 的精确 `normalized_text` 上按 Python `str` Unicode code point 计数的零基、左闭右开 input-local 坐标；不是 UTF-8 byte、UTF-16 code unit、grapheme、token 或 document-global 坐标。`corpus_span` 强制 `input_id == span_id`、`input_revision == document_revision`，并绑定不可变 `document_id/document_revision`、上游 sidecar/span 坐标和版本化 normalized→document 投影，只有它可持久化；`query_text` 强制 `span_id=None`、`input_revision == query_revision`，只绑定 query-local immutable identity，不得伪造文档坐标或写入任何 durable candidate-audit/mention/merge/alias/link/corpus-evidence store。query pre-merge/merger artifact 只允许 request-scoped，最多按查询隐私/保留策略输出有界脱敏观测元数据；query 来源只允许 model/dictionary/rule，不得制造 frontmatter 来源。如规范化发生删除、替换、折叠或重排，必须由 normalizer 预先产生对应变体的版本化映射。模型概率、规则权重、词典 exact match 与 frontmatter 声明不是同一标尺，必须通过 `confidence_kind` 区分；无 offset 的输出或不满足切片/判别不变量的结果拒绝使用。RaNER 的 `schema_version` 表示项目 canonical type/label-map 版本，不表示调用时输入 schema。
- **确定性补充源（不是主召回器）**：领域词典、jieba 分词/关键词、后缀规则和 OKF frontmatter 声明用于补充业务黑话/简称、校正边界、提高置信度与辅助归一。纯 jieba + 词典结果不能单独满足 R-OKF-06 的 C1 验收。
- **候选审计与合并策略**：模型、词典、规则和 frontmatter 的全部有效原始候选（含同源重复、嵌套与重叠）先进入可重放的 pre-merge audit representation，保留原始边界、来源、`confidence_kind` 与不可变 artifact provenance；之后由独立、版本化合并器按稳定排序（`input_kind, input_id, input_revision, segment_id, char_start, char_end, priority_rank(confidence_kind, source), raw_label, extractor_id, model_revision, mention_text`）、同源去重/重叠规则及跨源边界规则产出 selected/suppressed/grouped 结果，不能靠 backend 返回顺序决定结果。**D2 已冻结：corpus 不建 durable raw candidate-audit 表**——raw/duplicate/nested/overlap/selected/suppressed/grouped 决策必须能从 OKF raw + sidecar + versioned sources + extractor/merger versions 确定性重建，只持久化 selected mentions；query 审计与 merger artifact 严格 request-scoped、hard zero persistence（不得进入任何 durable candidate audit、`entity_merge_log`、alias、entity-link 或 corpus-evidence store）。合并不得擦除被抑制候选，也不因模型结果直接永久合并 canonical entity，不得把不同 `confidence_kind` 的数值未经标定直接比较。缺少 RaNER confidence 表示元数据不可用，不表示低置信。adapter 严禁用 `str.find`、substring search 或同义恢复逻辑猜回缺失/冲突坐标；任何契约异常按 input fail-closed、跨 input 可继续，产生带 `input_kind/input_id/input_revision/segment_id/extractor/version/reason` 的结构化错误。corpus span 失败时不得产生部分 `entity_mentions`、alias、merge-log 或 link 写入；query input 失败时不得产生部分 R3 seeds。
- **备用与未采用项**：`iic/nlp_raner_named-entity-recognition_chinese-base-news`（StructBERT + Transformer-CRF，约 409 MB，`PER/ORG/LOC`，MSRA 新闻域）仅为资源受限降级候选，不是通用主模型的等价替代或自动 runtime fallback；只有 Large Generic 超出预先声明的资源预算、且同一项目人工集证明降级质量可接受后，才能另行裁决。PaddleNLP `2.8.1` / `uie-base` 只保留为未来 schema-guided 领域扩展。HanLP `v2.1.1` / `MSRA_NER_ELECTRA_SMALL_ZH` 仅作研究/评测备用：公共输出是 token offsets 且无 mention confidence，模型默认许可含非商业限制。DeepKE 当前缺少同时可核验的固定 checkpoint/checksum、稳定输出 DTO、该 checkpoint benchmark 与独立权重许可，不进入首期 switch。
- 词典本身 OKF 化：领域词典/别名表作为 OKF `entities/` 下的受版本管理文件（人可编辑——符合 T1/T2 的人工编辑分区）。
- entity_mentions 填充管线（批处理脚本，可重跑幂等）；alias 归一与 entity_merge_log 记录（可逆，不破坏性改写）。
- node_entity_links：span→mention→entity 聚合到树节点层。该表**已存在**（`005_kg_extension.sql` 建、`012_mapping_table_enrichment.sql` 扩展），保持 `(node_id, entity_id)` PK、canonical-entity-only；**不创建 `chunk_entity_links`**；pending mention（entity_id=NULL）的 node 关联经 `entity_mentions.span_id -> tree_node_spans.span_id -> tree_node_spans.node_id` 推导（`tree_node_spans` 已建于 003）。**C1 不新建 019 link migration**——`019` 已是 `019_e2a_materialization_contract.sql`（Phase 15 E2a 占用，永不复用）；C1 的 schema-gap migration（provisional `020_ner_entity_mentions.sql`）补齐 typed provenance、stable `e2b_owner_scope` 与 `okf_e2b_node_link_ownership` ledger（UNIQUE `(node_id, entity_id, version_id)`）。
- OKF frontmatter 中人工声明的实体/关系/证据可已由 Phase 15 E2a 物化为高置信来源。Phase 16 可读取其 canonical identity 供 NER normalization 使用，但不得重复 materialize、覆盖或把 E2a 人工 provenance 改标为 NER；本阶段新增/验证的是 NER-derived mention、alias/merge provenance 与 node/entity-link 路径。
- **C1 前向契约约束（来自 C2，2026-07-12）**：`entity_mentions.entity_id` 必须允许 NULL/待决——未归一的候选 mention 可以先于实体解析存在。C1 设计 schema 与填充脚本时必须满足，否则 C2 需要重构迁移。

## Out of Scope（画死）

- 任何 LLM 三元组抽取（R-OKF-04 红线）；关系抽取器（关系只来自 frontmatter 人工声明，机器关系抽取推迟）。
- 检索行为（Phase 17 消费本阶段数据；本阶段不碰 fusion/traversal/selector）。
- relation_mentions 表（ADR T6 明示 post-C 按需，默认不建；**16-C2 不改变此条，也不构成其隐式授权**）。
- 不回头改 Phase 14/15 的 serializer/parser（发现缺陷走缺陷流程，不在本阶段顺手扩契约）。
- E2b 不新建 canonical `entities`（D1）；不建 durable raw candidate-audit 表（D2）；不写 `chunk_entity_links`（D5）。

## §16-C2 子波：中文局部指代链（条件性，默认关闭，2026-07-12 补充）

> 完整契约见补充交接书 §4；本节是其边界级摘要，冲突时以补充交接书为准。

**子入口门（在 Phase 16 内部再设一道）：** C1 的 entity_mentions、provenance、默认关闭开关与 E2b node_entity_links 物化验收关闭后才可开始 C2。C2 可以整体不进入（条件性 wave）——不进入不影响 Phase 16 关闭，但需在 16-VERIFICATION 记录"C2 未进入"及原因。C2 入口 default `skipped_not_entered`；仅在 C1 acceptance CLOSED **且** 单独获得一次性 `OKF_E2B_C2_ENTRY_AUTHORIZED` 授权后才进入。

**C2 In Scope：**
- `coref_clusters` + 规范化 membership 表（**`coref_cluster_mentions`，命名已定稿**，见 PLAN 16-16/16-17）：簇是"文本 mention 间的局部证据连接"，带 provenance（方法/规则 ID、置信度、文档/版本坐标）。
- 规则优先解析链：段落主体继承 → 显式指代表（"该院/其/上述单位"类，词典维护于 OKF）→ 有界零主语；低置信/歧义一律保持未链接。模型辅助只保留未来扩展位，不在 C2 初期冻结或暴露任何模型值。
- C2 初期只支持 `RAG_COREF_RESOLVER=off|rules`，默认 off；如保留 `RAG_COREF_MODEL` 配置占位，其首期唯一合法值为 `off`。任何模型值必须先完成精确 checkpoint、许可、输出契约、fixture 与离线部署审查，不能因 C1 采用 RaNER 或历史提及 HanLP 而隐式启用。
- 删除语义：per-cluster tombstone 软删除，不做破坏性 DELETE；重跑幂等。
- migration：C1 schema 先行（provisional `020_ner_entity_mentions.sql`，补齐 entity_mentions provenance + `e2b_owner_scope` + `okf_e2b_failure_audit` + `okf_e2b_node_link_ownership` ledger；**019 永不复用**）；C2 单一后续 migration（provisional `021_ner_coref_clusters.sql`）同建 `coref_clusters` + `coref_cluster_mentions`（不建 merge-log / canonical-merge 表）——实际编号执行时按 ADR T5 复核 catalog 连续空闲号并显式记录，不得预先声称已分配。

**C2 Out of Scope：** 跨文档实体同一化 / canonical entity 永久合并；relation_mentions；LLM 全库指代；质量调参或默认开启（由 Phase 19 G3 门裁决）；检索侧消费（Phase 17 可选消费，见 17-BOUNDARY）。

**C2 验收分层：** Phase 16 只验收**功能就绪门**——契约完整、安全边界（无合并、可回滚）、幂等重建、双开关 off 时行为与 C1-only 完全一致。净收益与默认开启由 Phase 19 G3 在 D4 解冻后裁决（R-OKF-09）。

## Reconciled Planning Decisions (2026-08-06) — D1-D9 已冻结

> 本节把历史输入 reconcile 为最终 planning boundary。以下决策已在 `16-RESEARCH.md` / `16-PATTERNS.md` / `16-01..16-18-PLAN.md` / `16-VALIDATION.md` 定稿；**EXECUTION NOT AUTHORIZED，这些是计划中的决策，不是已达成事实。**

- **D1 — E2b 不新建 canonical entities（identity）。** NER candidate 只在 exact compatible canonical-name 或 exact OKF alias/dictionary match 时挂到既有 entity；其余 `entity_mentions.entity_id=NULL`（pending）。E2b 全程不 INSERT 新 `entities` 行；人工创建 canonical entity 属未来 adjudication phase。
- **D2 — 不建 durable raw candidate-audit 表。** 只持久化 selected `entity_mentions`；raw/duplicate/nested/overlap/selected/suppressed/grouped 决策必须能从 OKF raw + sidecar + versioned sources + extractor/merger versions 确定性重建。query candidate/pre-merge/merger artifacts 严格 request-scoped、hard zero persistence（不得写入任何 durable candidate-audit/mention/merge/alias/link/corpus-evidence sink）。`okf_e2b_node_link_ownership` ledger 是已持久化 E2b bridge 的 typed ownership/provenance 记录，不是 candidate audit。
- **D3 — 来源优先级已冻结：** `frontmatter_declared > dictionary_exact > rule_weight > model_probability > unavailable`。这是版本化非数值冲突优先级，不是 calibration；`unavailable`（RaNER `confidence=None` / `confidence_kind="unavailable"`）表示元数据缺失，不是低置信；合并器按该优先级裁决跨源冲突，稳定排序键已定稿（`input_kind, input_id, input_revision, segment_id, char_start, char_end, priority_rank(confidence_kind, source), raw_label, extractor_id, model_revision, mention_text`）。
- **D4 — 事务边界 = 每 document/version 一个原子事务，不是 per-span。** 首个 invalid span 在任一 DML 前使该 document/version scope 失败（零净变化：零 mention/alias/merge/link）；primary 连接 rollback+close 后，独立 fresh connection 向全新 append-only `okf_e2b_failure_audit` 追加（绝不复用/扩展 Phase 15 `okf_rebuild_failure_audit`，后者被 migration 019 pin）；随后按确定性顺序继续处理其他 documents。query input 失败零 R3 seeds。
- **D5 — `node_entity_links` 保持 canonical-entity-only、不改 PK `(node_id, entity_id)`。** 表已存在（005 建、012 扩展）；不创建 `chunk_entity_links`；pending mention（entity_id=NULL）的 node 关联经 `entity_mentions.span_id -> tree_node_spans.span_id -> tree_node_spans.node_id` 推导。Phase 16 无 retrieval reader；消费在 Phase 17。
- **D6 — C1 需要 schema-gap migration（provisional `020_ner_entity_mentions.sql`）；019 永不复用。** `019_e2a_materialization_contract.sql` 已被 Phase 15 E2a 占用（owner/targets + append-only audit protection）。`020` 补齐 016 `entity_mentions` 缺的 typed provenance 列（含 stable `e2b_owner_scope`，由 document_id + version_id 单独派生，绝不嵌入 extractor/merger/model version），新增 append-only `okf_e2b_failure_audit` 与 typed bridge ownership ledger `okf_e2b_node_link_ownership`（UNIQUE `(node_id, entity_id, version_id)`）。最终编号执行时按 ADR T5 复核 catalog 连续空闲号并显式记录；不得预先声称已分配。PAGEINDEX curated subset 排除 020。
- **D7 — C2 schema 隔离（条件性、默认 off、仅局部证据）。** conditional C2 使用 `coref_clusters` + `coref_cluster_mentions`（normalized membership）；provisional migration 名 `021_ner_coref_clusters.sql`；**不把 `entity_merge_log` 用作 coref schema，也不创建 canonical-merge 表**；C2 只是文本 mention 间的局部证据连接、默认 off、条件性进入（详见下方「C2（条件性子波）已定稿」与 §16-C2）。
- **D8 — 可选 `ner` 依赖/运行时边界（optional extra / lazy-import / 默认 off）。** `ner` optional extra（`modelscope>=1.39,<2`、`sentencepiece`）；`live_ner`/`disposable_db` pytest markers 默认排除；C1 公共接口 schema-independent、不接收 UIE 专属 schema；**2.26 GB 一律指模型 artifact/weight footprint，不是文本输入预算**。C1 主模型 artifact 冻结为 ModelScope `iic/nlp_raner_named-entity-recognition_chinese-large-generic`；fast-tokenizer 强制（slow path 的 `.index()` 坐标恢复是禁区）；`prob` 显式剥离；`confidence=None`/`confidence_kind="unavailable"`；无 `str.find`/substring recovery；`device='cpu'`；离线只读镜像 + 逐文件 SHA-256 manifest；runtime compatibility tuple 由隔离 smoke 实测冻结成 `runtime_compatibility_id`。`uie/base-news/hanlp/deepke` 不进入首期 switch。
- **D9 — 宏波序 W0-W7（架构阶段序，scheduler waves 0..8 与各 plan `depends_on` 依赖不变）。** W0 控制面与契约基础：16-01（默认 off 控制面 + 测试 marker）、16-02（extractor contracts）、16-03（raw-candidate retention / 版本化 merger 边界）；W1 C1 schema-gap migration：16-04（provisional `020` + `okf_e2b_failure_audit`）；W2 分割/适配/镜像：16-05（owned segmenter）、16-06（RaNER Large Generic adapter）、16-07（只读镜像 + `ner` extra）；W3 补充/合并/runner：16-08（dictionary/frontmatter/rule 补充 + D1/D3 优先级）、16-09（E2b desired-state reconcile）、16-10（统一 extract 管线）、16-11（E2b runner）；W4 live 资源门：16-12（模型 mirror + SHA-256 manifest）、16-13（隔离 smoke + 资源实测冻结 runtime tuple）、16-14（migration gate）；W5 E2b 全语料 live acceptance：16-15；W6 C2 条件 coref：16-16（coref 两表）、16-17（C2 entry acceptance + 021 migration）；W7 聚合 verification：16-18（验收矩阵与 non-claims）。
- **Frozen cross-cutting constraint（R-OKF-04，不编号）— 全程零生成式 LLM token（enabled baseline = RaNER Large Generic + 词典/frontmatter/规则）。** 默认 `RAG_ENTITY_EXTRACTOR=off`；`VALID_ENTITY_EXTRACTORS={"off","raner"}`；off 时任何 modelscope/torch import 不发生（lazy-import）。R-OKF-04 由静态 AST/import + 运行时 LLM spy 双证。
- **Frozen concurrency correction（不编号，E2a/E2b 共享锁）— E2b 与 E2a 使用完全相同 parent advisory key `okf:e2a:parent:{document_id}:{version_id}`（绝不 `okf:e2b:parent`）。** 固定顺序：advisory xact lock → `document_versions` FOR UPDATE → E2b ownership/mention/link row locks → DML。
- **Desired-state convergence（与 D1-D9 一体）：** E2b materialization 是全量 desired-state reconciliation，不是 upsert-only——load existing E2b-owned state → full preflight → stable upsert → 删除同 E2b owner scope 的 stale E2b-owned mentions → 删除 stale E2b link ownership → 仅当 E2b ledger ownership 显式且无剩余 owner 时才删 stale bridge（否则 fail-closed 保留）。manual/legacy/foreign/unowned rows 保留且不认领；equivalent rerun 零 DML；changed-set failure 回滚至原 committed state 后再 fresh-connection audit。
- **C2（条件性子波）已定稿：** schema 用 `coref_clusters` + `coref_cluster_mentions`（normalized membership），migration provisional `021_ner_coref_clusters.sql`，不建 merge-log / canonical-merge 表；`RAG_COREF_RESOLVER=off|rules` 默认 off（`rag_coref_model` 占位唯一合法值 off）；入口 default `skipped_not_entered`，仅在 C1 acceptance CLOSED 且单独获得一次性 `OKF_E2B_C2_ENTRY_AUTHORIZED` 后进入；skipped 不阻塞基于 C1 的 Phase 16 closure，但不声称 R-OKF-09 live-tested。

## Deliverables（已映射为 16-01..16-18 waves）

1. 抽取器 Protocol + 注册/总开关 + **可运行 ModelScope RaNER Large Generic 基准适配器**（TDD；含字符坐标、`confidence=None`、版本化 label map、snapshot/artifact digest provenance 与断网加载）。
2. 模型资源 lock manifest（完整逐文件 SHA-256）与只读离线缓存；隔离 smoke test 后冻结 ModelScope/AdaSeq/PyTorch/Python 兼容 tuple，分别在 Windows 11 CPU 与候选 WSL 环境记录约 2.26 GB artifact 的冷启动、内存、吞吐、p95 延迟与磁盘预算。若超预算，只产出 Base News 降级比较与显式裁决输入，不静默替换。
3. jieba/领域词典/规则/frontmatter 高置信补充层 + 候选确定性合并器；OKF 化词典 + 加载器（词典变更走 canonical hash 同步流 F3）。
4. NER-derived `entity_mentions`/aliases/merge_log 填充脚本（幂等、批量、带统计输出；不重做 E2a manual OKF materialization）。
5. NER-derived `node_entity_links` 聚合（表已存在，保持 `(node_id, entity_id)` PK、canonical-entity-only；C1 provisional `020` 只加 provenance/ownership，不新建 019 link migration）。
6. E2b parity/idempotence evidence：NER-derived mention、alias/merge provenance 与 node/entity-link materialization 在等价重跑下稳定；与 E2a 一起闭合完整 derived-association parity。
6. **（条件性，C2）** `coref_clusters` + `coref_cluster_mentions` migration（provisional 021）、规则解析器、默认关闭开关接线、tombstone/幂等重建脚本、C2 功能就绪门自检（详见 §16-C2；C1 验收关闭前不启动；首期不交付模型辅助 coreference）。
7. 16-VERIFICATION：R-OKF-04（默认路径 token 计数为 0 的证明——无任何 LLM client 调用，静态 + 运行时双证）+ R-OKF-06 + （如 C2 进入）R-OKF-09 功能就绪门；如 C2 未进入，记录原因。

## Planned Acceptance Criteria（计划中 — 未达成）

> 以下是计划中的验收标准，不是已达成事实。达成需要五个 future live gates 在独立授权后实际执行；在未授权/未执行前一律保持 `blocked_not_executed` / `skipped_not_entered`。

- 全语料抽取一遍：entity_mentions 覆盖率/数量统计产出（不在 Phase 16 设最终质量阈值——质量净收益评估属 Phase 19；但必须分别报告模型/词典/规则/frontmatter 的产出与重叠情况）。
- 至少一个本地非生成式中文实体抽取适配器真实可运行；基准固定为 ModelScope `iic/nlp_raner_named-entity-recognition_chinese-large-generic`。只交付 Protocol、mock 或纯 jieba/词典实现不得关闭 C1。
- 无项目标注/微调前置：直接使用发布 checkpoint 对真实中文推理成功。另建中文人工标注小集只用于验收测量，不是训练数据或启动条件；微调只能是 Phase 19 证据支持后的可选优化。
- 用**不在领域词典中的人物、组织机构、地点，以及至少一个 `CW` 或 `PROD` fixture**证明模型从上下文发现 mention，返回正确字符级左闭右开坐标，并完成版本化 label mapping；另用领域简称 fixture 证明词典作为高置信补充源有效。
- 每行 corpus mention 有 `input_id/span_id + input_revision/document_revision + char_start/char_end + mention_text + raw_label/entity_type + source + confidence/confidence_kind + extractor/model/schema/artifact + normalization/segmentation/label-map/runtime provenance`；query candidate 有同一公共 provenance，但 `span_id=None` 且 `input_revision=query_revision`。硬断言 `input.normalized_text[char_start:char_end] == mention_text`。字符坐标使用 Python Unicode code-point 半开区间，fixture 覆盖中文全角标点、重复实体、换行、combining mark 与 astral-plane emoji，并证明 corpus 可经版本化投影回到 immutable document revision/sidecar evidence。未知 label、越界、空 span、切片不一致或 corpus 投影失败必须拒绝并计数，禁止 `str.find`/substring recovery。query fixture 还必须证明 pre-merge/merger artifacts 对所有 durable audit/mention/merge/alias/link/evidence sinks 零写入。
- RaNER 标准输出没有 mention confidence；必须保存 `confidence=None` 与 `confidence_kind="unavailable"`。模型/规则/词典/frontmatter 的置信信息分型保存；不得把 rule weight、exact match 标记或 frontmatter 声明冒充模型概率，也不得未经标定直接跨 `confidence_kind` 比较。
- 同源重复/嵌套/重叠候选必须在 merger 前完整留存；稳定排序和版本化 selected/suppressed/grouped 决策在重跑时一致。partial-batch fixture 证明单个 span 契约失败会产生 typed error 且该 span 对 `entity_mentions`、alias、merge-log、link 零部分写入，其他 span 的继续/失败行为确定且可重试幂等。
- 官方 benchmark 只作外部证据；必须在项目中文人工标注小集报告 precision/recall/F1、按类型 recall、offset exact match、label mapping 和 error counts。MultiCoNER 的半自动/弱监督构造性质必须如实记录。
- 完整模型资源逐项通过本地 SHA-256 校验；断网冷启动/重跑成功；记录 Windows CPU 与候选 WSL 的冷启动、吞吐、p50/p95 span 延迟、峰值内存、磁盘占用，以及长文本分段后的全局 offset round-trip。官方没有给 Large Generic 的 CPU latency/RAM，实测前不得宣称部署成本可接受。
- Large Generic 如超出预声明资源预算，必须产出与 `iic/nlp_raner_named-entity-recognition_chinese-base-news` 在同一人工集上的质量/资源对比，并经显式架构裁决；不得自动或静默降级，也不得提前把 fallback 暴露为已支持 switch 值。
- corpus 实体/alias merge 操作全部见于 entity_merge_log 且可逆；NER 候选不得直接触发 canonical entity 永久合并。query candidate merger 仍严格 request-scoped，不写 entity_merge_log。
- 总开关 off 时系统行为与 Phase 15 结束态完全一致。
- 启用后的基准组合是 RaNER Large Generic 主识别 + 词典/frontmatter/规则补充；默认安装/配置仍不自动启用。
- 默认基准路径零生成式 LLM 调用（测试用 fake client 断言零调用；本地 RaNER 推理不计 LLM token）。
- 模型资产许可是 Phase 20 G6 前置审查项：ModelScope 模型卡 Apache-2.0 标记不自动替代权重/底座/训练数据完整许可链审查；未完成审查不得进入外部或商业试点。
- C2 消费 C1 mention 证据，但不选择、配置或重定义 C1 NER；C1 extractor、label map 或 offset 契约变化后，必须先做 C1 回归，C2 评测才有效。
- （C2 如进入）指代簇零永久合并：coref 数据不改写 entities/entity_mentions 的归一结果；所有 coref 开关 off 时行为与 C1-only 逐位一致；tombstone 可逆；重跑幂等。首期 C2 只允许 rules/off，不暴露未冻结的模型值。

## Key Files / Context Pointers

- `llamaindex_runtime/okf/parser.py`（frontmatter 实体/关系读取，14-03 已保证限定词不丢）
- migrations 016（entity_mentions/entity_aliases/entity_merge_log 已建）；provisional `020_ner_entity_mentions.sql`（provenance + `e2b_owner_scope` + `okf_e2b_failure_audit` + `okf_e2b_node_link_ownership` ledger）/ provisional `021_ner_coref_clusters.sql`（coref 两表）；**019 永不复用**
- ModelScope RaNER Large Generic 模型/适配器（C1 必交付；精确模型 ID、文件级 SHA-256、标准输出与许可边界见模型选型研究文档；PLAN 时通过隔离 smoke test 冻结 runtime tuple 与 CPU/Windows/WSL 资源预算）
- jieba 既有运行时引入点（仅作为关键词/词典/规则补充源参考；Phase 11/12 commits `ae7bd97`, `91182cd` 附近，PLAN 时定位确切模块）
- `.planning/jieba-keyword-extraction-PLAN.md`（关键词与词典补充层的历史设计参考，**不是 C1 实体召回主方案**；权威性低于本裁决）
- **上游参考（研究文档 §6）**：实体/概念页 frontmatter 约定采 OpenKB（Apache-2.0，`E:\github\rag-upstream\OpenKB`）——`type` 用 title-case 实体类型（Organization/Person/…）、`sources: [...]` 多来源追踪（更新时 prepend）、`aliases: [...]`、正文 `[[wikilink]]` 交叉链接；与我们 entity_aliases/entity_mentions 表对齐。其 `frontmatter.py` 助手可移植。
- **open-knowledge（GPL-3.0，用户裁决 2026-07-12 解禁——衍生文件打 GPL 来源头标，绊线见研究文档 §7）**：entity-vault dossier 约定可复制（编译真相区 + `--- timeline ---` + 追加式时间线条目含 source/author/evidence/confidence）；`links.ts` 断链检测与 wikilink 解析可移植。全表见 `.planning/research/UPSTREAM-SOURCE-ANALYSIS-2026-07-12.md`。

## Open Questions — Reconciled（2026-08-06，PLAN 已答）

> 以下原 Open Questions 已由 D1-D9 冻结并进入 16-RESEARCH / 16-PATTERNS / 16-01..16-18-PLAN 定稿，**不再是开放问题**：

1. **实体归一键（原 Q1）→ D1 resolved:** E2b 不新建 canonical entities；仅 exact compatible canonical-name 或 exact OKF alias/dictionary match 挂既有 entity，其余 `entity_mentions.entity_id=NULL` pending。canonical identity 来源：OKF frontmatter 声明优先（Phase 15 E2a 已物化的人工来源，可读取不重写）。
2. **node_entity_links 粒度（原 Q2）→ D5 resolved:** 保持 `(node_id, entity_id)` PK、canonical-entity-only；不写 `chunk_entity_links`；pending mention 的 node 关联经 `entity_mentions.span_id -> tree_node_spans.span_id -> tree_node_spans.node_id` 推导。Phase 17 召回 SQL 不依赖 chunk-level 冗余。
3. **置信度与候选裁决（原 Q3）→ D2/D3 resolved:** 无 durable raw candidate-audit 表；稳定排序键定稿（D3 完整键：`input_kind, input_id, input_revision, segment_id, char_start, char_end, priority_rank(confidence_kind, source), raw_label, extractor_id, model_revision, mention_text`）；来源优先级 `frontmatter_declared > dictionary_exact > rule_weight > model_probability > unavailable` 冻结；`unavailable` ≠ 低置信；typed per-input failure taxonomy / batch continue-abort / retry 在 PLAN 16-02/16-03/16-09/16-10 定稿。
4. **主模型与输出契约（原 Q4）→ 已冻结:** RaNER Large Generic 为 C1 功能主模型；`prob` 显式剥离；`confidence=None`/`confidence_kind="unavailable"`；fast-tokenizer 强制；离线镜像 + SHA-256 manifest。**唯一仍开放的是 live measurement 后的资源裁决**：若 Large Generic 超出预声明资源 envelope，须以同一人工集比较 Base News 质量/资源并产出显式架构裁决，不得自动/静默降级（16-13 smoke benchmark 后裁决）。
5. **C2 membership 表命名与索引（原 Q5）→ resolved:** `coref_clusters` + `coref_cluster_mentions`（normalized membership，PK `(cluster_id, mention_id)`，tombstone 列）；migration provisional `021_ner_coref_clusters.sql`；`RAG_COREF_RESOLVER=off|rules` 默认 off；模型辅助 switch 不暴露未冻结模型值。
6. **C2 显式指代表词典与 C1 词典的 OKF 目录关系（原 Q6）→ resolved:** 都走 OKF `entities/` 下的受版本管理词典分区（C1 domain dictionaries per PLAN 16-08；C2 explicit-reference dictionary 复用同一分区约定），词典变更走 canonical hash 同步流 F3。

**仍需未来 live measurement / explicit adjudication（不重开架构）:**
- Large Generic 的 Windows CPU / WSL 冷启动、峰值内存、吞吐、p95 延迟实测（16-13，独立授权后），以及超预算时的 Base News 降级显式裁决。
- 精确 runtime compatibility tuple（modelscope 1.x / torch CPU-vs-CUDA / transformers / tokenizers / sentencepiece / fast-tokenizer path）由隔离 smoke 实测冻结成 `runtime_compatibility_id`。
- 项目自有中文人工标注小集的规模与划分（只作验收测量，非训练数据）。
- C2 净收益由 Phase 19 G3 在 D4 解冻后裁决（Phase 16 只验收功能就绪门）。

## Risks

| 风险 | 缓解 |
|---|---|
| 纯词典方案漏掉未登记的新实体，导致 R3 种子召回上限过低 | RaNER Large Generic 作为 C1 必交付的固定标签通用中文 NER 主识别器；词典/jieba 降为高置信领域补充；词典外实体 fixture 为硬验收 |
| Large Generic 约 2.26 GB，CPU 冷启动、峰值内存、吞吐或 Windows/离线部署不可接受 | 功能主模型不因未知资源成本而静默改变；PLAN 先声明资源 envelope，再实测 Windows/WSL。超预算时以同一项目人工集比较 Base News 质量/资源并产出显式降级裁决，不能自动 fallback |
| RaNER 标准输出没有 mention confidence，候选排序误把 unavailable 当低分或伪造概率 | DTO 固定 `confidence=None` / `confidence_kind="unavailable"`；来源级确定性规则与独立校准；禁止制造常数概率或跨 confidence_kind 裸比较 |
| 模型误识别或模型/词典候选边界冲突 | 全来源 provenance + 置信度分层 + 确定性候选合并规则；不因 NER 候选直接永久合并 canonical entity |
| 模型仓库 `master` 可变、SDK/runtime tuple 尚未实测 | 完整文件级 SHA-256 manifest + 只读本地镜像 + 实际 snapshot revision + 断网 smoke test；隔离环境通过后再冻结 SDK tuple |
| 词典漂移无版本 | 词典 OKF 化，走 git + canonical hash |
| 抽取脚本重跑产生重复 mention，或 partial-batch 失败留下半写状态 | 幂等 identity 至少包含 `document_revision + span_id + char_start/char_end + normalized entity_type + source + extractor_id + model_revision`；per-document/version 原子事务（D4）+ typed failure report + 稳定排序和 retry fixture；失败 scope 零净变化 |
| （C2）指代误链把不相关 mention 连成簇 | 初期 rules/off，不暴露未冻结模型值；规则优先 + 高阈值 + 低置信保持未链接；簇仅是局部证据连接不做实体合并；per-cluster tombstone 可逆；默认关闭，净收益 G3 裁决 |
| （C2）C1 schema 未预留 nullable entity_id | 已在 C1 In Scope 写入前向契约约束；PLAN 时 schema review 必查（provisional 020 已含 nullable `entity_id` 语义与 `e2b_owner_scope`） |
