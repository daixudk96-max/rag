# Phase 16-C1: Raw Corpus Entity Layer — Implementation Research

**Researched:** 2026-08-05 (修订对齐已冻结的 Phase 16 架构裁决 D1-D9)
**Domain:** Local fixed-label Chinese NER (ModelScope RaNER), deterministic span merge, idempotent PostgreSQL materialization
**Confidence:** HIGH for ModelScope runtime mechanics; MEDIUM for dependency-version tuple (must freeze via smoke test)
**Scope:** 只做规划研究。不改 runtime/tests/SQL/config/dependencies，不安装/不下载/不执行模型，不跑 tests/DB/Docker，不 commit。本文事实研究保留，但全部建议与已接受的 D1-D9 对齐；已关闭事项（D1/D2/D3/D4/D5/D6 的迁移需要、D5 的 node 关联、C2 条件性）不再列为 PLAN open question。C2 不在本研究内启动，仅在 C1 acceptance close 后条件进入；D4 保持冻结至 Phase 19；Phase 20 仍需独立 pilot 授权 + 人工 G6。**2.26 GB 一律指模型 artifact/weight footprint，不是文本输入预算。**

---

## Executive Findings

1. **[VERIFIED: modelscope GitHub master] AdaSeq 不是 RaNER 推理的运行时前置。** 主模型 `iic/nlp_raner_named-entity-recognition_chinese-large-generic` 的 `configuration.json` 是 `{"framework":"pytorch","task":"named-entity-recognition","model_type":"transformer-crf"}`。模型类 `ModelForTokenClassificationWithCRF` 内置于 modelscope 核心（`modelscope/models/nlp/task_models/token_classification.py`），注册于 `Tasks.named_entity_recognition / Tasks.transformer_crf / Tasks.token_classification`。官方 NER 测试（`tests/pipelines/test_named_entity_recognition.py`）用 `modelscope.models.nlp.ModelForTokenClassificationWithCRF` 直接离线推理，不 import AdaSeq。AdaSeq 是训练/配置框架，仅在与 training 相关的路径需要。

2. **[VERIFIED: modelscope GitHub builder.py + pipeline test] 本地路径离线加载是一等路径。** `pipeline(task, model=<local_dir>)` 在 `is_official_hub_path()` 判定本地目录存在且含 `configuration.json` 时直接使用该目录，不触发下载。官方测试 `test_run_tcrf_by_direct_model_download` 即：`snapshot_download(model_id)` → `ModelForTokenClassificationWithCRF.from_pretrained(cache_path)` + `TokenClassificationTransformersPreprocessor(cache_path)` → `pipeline(Tasks.named_entity_recognition, model=model, preprocessor=tokenizer)`。运行时断网加载的推荐形态：一次性用 `snapshot_download(model_id, revision=<冻结>, local_dir=<只读镜像>)` 建镜像，之后 `pipeline(task, model=<镜像路径>)` 完全离线。

3. **[VERIFIED: modelscope GitHub token_classification_pipeline.py] 当前 SDK 默认会输出 `prob` 字段，适配器必须主动剥离。** `TokenClassificationPipeline._chunk_process` 默认 `return_prob=True`，且当模型 forward 返回 `logits` 时计算 `probs = logits.softmax(-1)` 并把 `chunk['prob'] = probs[i][predictions[i]]` 写入输出。`ModelForTokenClassificationWithCRF.forward` 返回 `AttentionTokenClassificationModelOutput(logits=logits, ...)`，因此当前 modelscope 版本下 RaNER pipeline 输出**很可能包含 `prob`**。该值是逐 token 对 CRF logits 的 softmax，不是标定的 mention 置信度。冻结契约（`confidence=None` / `confidence_kind="unavailable"`，见 2026-07-13 模型选型裁决 §3.2）是**有意的契约选择**：适配器必须显式丢弃 `prob`，不能假设输出里没有它，更不能把 `prob` 当模型概率。PLAN 必须加一条断言测试锁定该行为。

4. **[VERIFIED: modelscope GitHub token_classification_preprocessor.py] offset 语义与冻结契约一致（fast tokenizer 路径），但 slow 路径是禁区。** 预处理器 `SequenceLabelingPreprocessor._tokenize_text_with_fast_tokenizer` 用 HF fast tokenizer 的 `offset_mapping`（Python `str` 字符/code-point 坐标），与冻结契约的 Unicode code-point 半开区间一致。但 `_tokenize_text_with_slow_tokenizer` 走 `get_label_mask_and_offset_mapping_<Tokenizer>`，其中 Bert 变体用 `text[offset:].index(token)` 猜回坐标——这正是契约禁止的 `str.find`/substring 恢复，重复实体文本下不确定。**适配器必须强制 fast tokenizer 路径并在断言 `input.normalized_text[char_start:char_end] == mention_text`**；smoke test 必须显式验证走的是 fast 路径。

5. **[VERIFIED: modelscope GitHub token_classification_pipeline.py] 512-token 截断是真实风险；pipeline 自带 `split_max_length` 不可作为分段主方案。** 默认 `sequence_length=512`，超长输入被截断，>512 token 的 mention 直接丢失。`_process_single(split_max_length=...)` 按**原始字符数**（`len(text)`）切分并在 join 时按 char offset 平移——不是 token 感知，且不产生带 `segment_id/parent interval/segmentation_version` 的版本化坐标，跨段实体还会被切碎。C1 适配器必须自带 token 感知的确定性分段层（每段留 [CLS]/[SEP] 余量），回写段内局部坐标到 parent 后再断言切片不变量。

6. **[VERIFIED: PyPI + 本机环境] 依赖面比预期小。** `modelscope` 1.39.1（Apache-2.0，Python>=3.10）裸装只拉 `requirements/hub.txt`（filelock/modelscope-hub/packaging/requests/setuptools/tqdm/urllib3）。torch 2.5.1+cu124 与 transformers 4.57.3 已在当前环境（经 sentence-transformers 间接依赖）。XLM-R 需要 `sentencepiece`（**当前未装**）。`modelscope[nlp]` extra 极重（datasets<=4.8.4、spacy<=3.7.0、stanza、pandas、sklearn、seqeval…），但因 `modelscope.models.nlp` 用 `LazyImportModule` 且 token-classification 只 import `task_models` 子模块，**裸 modelscope + sentencepiece 很可能足以推理**——这是待 smoke 验证的假设，失败则退到隔离 venv 装 `modelscope[nlp]`。

7. **[VERIFIED: 仓库 migrations 目录 + migration_catalog.py] 019 已被 E2a 占用且永不复用；`node_entity_links`/`tree_node_spans` 已存在；C1 确实需要一个 schema-gap migration（D6）。** `migration_catalog.py` 的 `FULL_MIGRATION_CATALOG` 当前末尾是 `019_e2a_materialization_contract.sql`，BOUNDARY 中"预留 019_node_entity_links"已过期。`node_entity_links(node_id, entity_id, ordinal_no)` 在 `005_kg_extension.sql` 已建成；`tree_node_spans(node_id, span_id, ordinal_no, PK(node_id,span_id))` 在 `003_tree_persistence.sql` 已建成；`entity_mentions/entity_aliases/entity_merge_log` 已在 `016_entity_mentions.sql` 建成。**但 016 的 `entity_mentions` 缺少冻结的 provenance 字段**（无 model_id/model_revision/artifact_digest/schema_version/normalization_version/segmentation_version/label_map_digest/runtime_compatibility_id/input_revision 等），且 D4 需要新的 append-only `okf_e2b_failure_audit` 表。因此 **C1 需要一个 schema-gap migration**（概念上当前 provisional `020_ner_entity_mentions.sql`；编号必须在执行时复核 catalog，不能声称已分配）；conditional C2 后续一个 migration（概念上 provisional `021_*`）创建 `coref_clusters` + `coref_cluster_mentions`。**019 永不复用。**

8. **[VERIFIED: 仓库 okf/e2a_contracts.py + e2a_materialization_dml.py] 幂等物化的既有模式可整体复用。** E2a 用确定性 `uuid5(E2A_NAMESPACE, f"{kind}:{natural_key}")` 生成稳定主键，配合 `INSERT ... ON CONFLICT (xxx) DO UPDATE` 实现可重跑幂等。C1 的 `entity_mentions` 应复用同一模式：确定性 `mention_id = uuid5(C1_NAMESPACE, f"{document_revision}:{span_id}:{char_start}:{char_end}:{entity_type}:{source}:{extractor_id}:{model_revision}")`，并建唯一约束支撑 `ON CONFLICT DO NOTHING/UPDATE`；事务边界按 D4 取 **per document/version 原子**（见 Finding #11）。

9. **[VERIFIED: 本机探测] 环境现状。** Python 3.11.9（满足 modelscope>=3.10）；torch 2.5.1+cu124（CUDA 版，CPU 可跑但约 2.5 GB 磁盘）；transformers 4.57.3；jieba 0.42.1（已装，项目基依赖）；modelscope / adaseq / sentencepiece **未装**；`wsl.exe` 存在（WSL 候选环境可用）。模型镜像磁盘预算约 **2.26 GB 权重/artifact footprint** + 2.5 GB torch。

10. **[VERIFIED: modelscope 文件 API] 冻结 manifest 与官方文件 API 一致。** `pytorch_model.bin` 2,239,833,895 B / SHA-256 `62fbd5ca…412b`、`config.json` 1,207 B、`sentencepiece.bpe.model` 5,069,051 B 等逐项与 2026-07-13 裁决 §1.3 完全吻合；文件 revision 含 `4d15e5b…` 与 `e260704…`。`config.json` 确认 `model_type=xlm-roberta`、`hidden_size=1024`、`num_hidden_layers=24`（XLM-R Large）、`num_labels=25`（BIOES × 6 类 + O）、`vocab_size=250002`、`max_position_embeddings=514`、`transformers_version=4.19.2`。

11. **[FROZEN D4] 事务边界 = 每 document/version 一个原子事务，不是 per-span。** 首个 invalid span 默认使该 document/version 全部回滚为零 mention/alias/merge/link；之后按确定性顺序继续处理其他 documents。失败审计写入全新的 append-only `okf_e2b_failure_audit` 表：主事务 rollback/close 后用独立 fresh connection 追加写入；**绝不扩展/复用 Phase 15 的 `okf_rebuild_failure_audit`**。

12. **[FROZEN D1] E2b 绝不从 NER candidate 新建 canonical `entities`。** 仅 exact compatible canonical-name 或 exact OKF alias/dictionary match 可挂到既有 entity；其余 `entity_mentions.entity_id=NULL`。人工创建 canonical entity 属于未来 adjudication phase。E2b 交付的是 mention/alias/merge provenance 与 node/entity-link 路径，不交付新 canonical entity。

13. **[FROZEN D2] C1 不建 durable raw candidate-audit 表。** raw duplicates/overlaps/nested/selected/suppressed/grouped 必须由 OKF raw + sidecar + versioned sources + extractor/merger versions 确定性重建（继承 D1 可重建性纪律）；只持久化 selected mentions。query artifacts 严格 request-scoped 且硬零持久化（不得写入任何 durable candidate-audit/mention/merge/alias/link/corpus-evidence store）。

14. **[FROZEN D3] 来源优先级已冻结：`frontmatter_declared > dictionary_exact > rule_weight > model_probability > unavailable`。** 这是版本化非数值冲突优先级，不是 calibration；`unavailable` 不表示低置信（与 2026-07-13 裁决 §3.2 的 `confidence=None`/`confidence_kind="unavailable"` 一致）。合并器按该优先级裁决跨源冲突，不得对 `confidence_kind` 数值未经标定直接比较。

15. **[FROZEN D5] 不写 `chunk_entity_links`；`node_entity_links` 保持 canonical-entity-only、不改 PK。** pending mention（entity_id=NULL）的 node 关联由 `entity_mentions.span_id -> tree_node_spans.span_id -> tree_node_spans.node_id` 推导（`tree_node_spans` 已存在于 003）。Phase 16 无 retrieval reader；消费在 Phase 17。

16. **[FROZEN D-series/C2 条件性] C2 仅在 C1 acceptance close 后条件进入**，可整体跳过且不阻塞 Phase 16 closure；default off；输出 local coref cluster evidence，不做 canonical merge。C2 schema 使用 provisional 021 migration（概念上），实际编号执行时按 ADR T5 核对。

**Primary recommendation:** 以"裸 modelscope + 已装 torch/transformers + sentencepiece"的最小隔离 extra、只读本地镜像路径 + 逐文件 SHA-256 锁、显式 `device='cpu'`、适配器主动剥离 `prob` 并断言切片不变量，作为 C1 的运行时基线；先做隔离 smoke test 冻结精确 tuple，再展开全量实现。全部实现遵循已冻结 D1-D9：per-document/version 原子事务 + `okf_e2b_failure_audit`（D4）、E2b 不新建 canonical entities（D1）、不建 durable candidate-audit（D2）、冻结来源优先级（D3）、`node_entity_links` 保持 canonical-entity-only（D5）、C1 需要一个 schema-gap migration 且 019 永不复用（D6）。

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| NER mention discovery | API/Backend (adapter) | — | RaNER 是本地非生成式模型，属后端离线批处理/查询侧工具 |
| Character-coordinate contract | API/Backend (DTO) | Database/Storage | 坐标定义在 DTO；持久化只发生在 corpus_span 路径 |
| Corpus mention materialization | Database/Storage | API/Backend | 每 document/version 原子事务 + 确定性 `uuid5` + `ON CONFLICT`；只持久化 selected mentions（D2/D4） |
| Entity resolution boundary | API/Backend | Database/Storage | 仅 exact compatible canonical-name / exact OKF alias/dictionary match 挂既有 entity，其余 `entity_id=NULL`；E2b 不新建 canonical entities（D1） |
| Failure audit | Database/Storage | API/Backend | 全新 append-only `okf_e2b_failure_audit`，主事务 rollback/close 后用独立 fresh connection 写；绝不复用 `okf_rebuild_failure_audit`（D4） |
| Query-text mention (R3 seeds) | API/Backend (request-scoped) | — | 只用于当前请求，禁止任何 durable sink 写入（D2） |
| Dictionary/rule/frontmatter supplement | API/Backend | Browser none | 本地确定性来源，补充而非主召回 |
| Deterministic candidate merge | API/Backend | — | 独立版本化合并器，稳定排序 + 版本化非数值来源优先级（D3）；pre-merge audit 不落库，raw 候选确定性重建（D2） |
| node_entity_links association | Database/Storage | — | 既有 005 表保持 canonical-entity-only、不改 PK；pending mention 的 node 关联经 `entity_mentions.span_id -> tree_node_spans` 推导（D5）；Phase 16 无 retrieval reader |
| LLM zero-token guarantee | API/Backend (seam) | — | `get_llm()`/FunctionAgent 不参与 NER 默认路径；spy 断言零调用 |

---

## Primary Sources

访问日期均为 **2026-08-05**。

### HIGH confidence（源码/官方/实测）
- [ModelScope 模型卡（iic/nlp_raner_named-entity-recognition_chinese-large-generic）](https://modelscope.cn/models/iic/nlp_raner_named-entity-recognition_chinese-large-generic) — license Apache-2.0、task named-entity-recognition、tags ACL2021/SemEval2022。页面为 JS 渲染，正文需经 API。
- [ModelScope 模型文件 API（files + SHA-256）](https://modelscope.cn/api/v1/models/iic/nlp_raner_named-entity-recognition_chinese-large-generic/repo/files) — 逐文件 SHA-256 与 2026-07-13 冻结 manifest 一致。
- [ModelScope 仓库 `configuration.json`](https://modelscope.cn/models/iic/nlp_raner_named-entity-recognition_chinese-large-generic/resolve/master/configuration.json) — `framework=pytorch, task=named-entity-recognition, model_type=transformer-crf`。
- [ModelScope 仓库 `config.json`](https://modelscope.cn/models/iic/nlp_raner_named-entity-recognition_chinese-large-generic/resolve/master/config.json) — xlm-roberta, 1024/24, num_labels=25, vocab 250002, transformers_version 4.19.2。
- [modelscope/modelscope GitHub (master)](https://github.com/modelscope/modelscope) — 默认分支 master；`pipelines/builder.py`（本地路径解析）、`pipelines/nlp/token_classification_pipeline.py`（`_chunk_process`、`return_prob`、`_auto_split`）、`preprocessors/nlp/token_classification_preprocessor.py`（fast/slow offset）、`models/nlp/task_models/token_classification.py`（tcrf 注册）、`hub/snapshot_download.py`（local_dir/local_files_only/revision）、`pyproject.toml`（extras：`[nlp]`=framework+nlp；torch 不在任何 requirements 文件）、`modelscope/models/nlp/__init__.py`（LazyImportModule）。
- [modelscope 官方 NER 测试 `tests/pipelines/test_named_entity_recognition.py`](https://github.com/modelscope/modelscope/blob/master/tests/pipelines/test_named_entity_recognition.py) — `test_run_tcrf_by_direct_model_download` 展示本地路径离线推理形态。
- [ModelScope 1.39.1 PyPI JSON](https://pypi.org/pypi/modelscope/json) — 版本 1.39.1、Apache-2.0、Python>=3.10、requires_dist 不含 torch/adaseq。
- 本机探测（read-only）：Python 3.11.9、torch 2.5.1+cu124、transformers 4.57.3、jieba 0.42.1、modelscope/adaseq/sentencepiece 未装、wsl.exe 存在。
- 仓库内（read-only）：`llamaindex_runtime/registry/migration_catalog.py`、`migrations/003_tree_persistence.sql`（`tree_node_spans`）、`005_kg_extension.sql`（`node_entity_links`、`entities.entity_type TEXT`）、`016_entity_mentions.sql`（缺少 provenance 字段的事实核对）、`okf/e2a_contracts.py`、`okf/e2a_materialization_dml.py`、`.planning/phases/16-raw-corpus-entity-layer/16-PATTERNS.md`（§3.5 canonical entity types：free-form TEXT，enum 不需 migration）。

### MEDIUM confidence（官方文档/成熟实现，经交叉确认）
- [PostgreSQL INSERT ON CONFLICT 官方文档](https://www.postgresql.org/docs/current/sql-insert.html) — `ON CONFLICT` upsert 语义（本项目 E2a 已在用）。
- [spaCy Doc.char_span API](https://spacy.io/api/doc#char_span) — MIT；`alignment_mode=strict/contract/expand` 作为"边界验证纪律"参考实现，不是运行时依赖。
- [seqeval PyPI](https://pypi.org/pypi/seqeval/json) — MIT、v1.2.2；**仅 token 级**，无字符 offset，不满足契约的 offset-exact-match 度量需求。
- [portion PyPI](https://pypi.org/pypi/portion/json) — v2.6.2、LGPL-3.0；区间代数（union/intersect/overlap），仅建议测试期交叉验证合并规则，不建议进运行时依赖。

### LOW / 需 PLAN 验证
- 模型卡报告 P/R/F1 91.55/91.33/91.44 与按类型 F1（2026-07-13 裁决 §1.2 已如实标注：仅代表该模型卡验证设置，非本项目质量证据；MultiCoNER 构造是半自动/弱监督）。官方没有给该 **2.26 GB（权重/artifact footprint）** 模型 CPU latency/RAM，**实测前不得宣称部署成本可接受**。

---

## Reusable Implementations

### 可直接复用的仓库内模式（HIGH）
| 模式 | 出处 | C1 用法 |
|---|---|---|
| 确定性主键 `uuid5(NAMESPACE, f"{kind}:{natural_key}")` | `llamaindex_runtime/okf/e2a_contracts.py:36,69` | `mention_id` 确定性生成，支撑幂等重跑 |
| 幂等 upsert `INSERT … ON CONFLICT (key) DO UPDATE/NOTHING` | `llamaindex_runtime/okf/e2a_materialization_dml.py`（span_id/chunk_id/entity_id/evidence_id…） | `entity_mentions/aliases/merge_log` 填充脚本；外包 per-document/version 原子事务（D4） |
| 懒加载可选重依赖 | `llamaindex_runtime/tree/runtime.py:95-100`（`import jieba` 在函数内） | 默认 off 时**绝不 import modelscope/torch** |
| 配置开关 + 合法值 fail-closed | `llamaindex_runtime/config.py`（`VALID_VECTOR_BACKENDS`/`VALID_EMBEDDING_PROVIDERS` 等 ClassVar + `__post_init__` 校验） | 新增 `VALID_ENTITY_EXTRACTORS = {"off","raner"}`，未知值启动即报错 |
| Unicode 边界/非字符 fixtures | `tests/llamaindex_runtime/okf/test_e2a_desired_state.py`（`￾`）、`test_e2a_wave1_twelfth_acceptance.py`（unicode separators） | C1 全角标点/combining/astral emoji fixtures 的既有风格 |
| 零 LLM 调用证明 seam | `llamaindex_runtime/llm/__init__.py`（`get_llm()` 单例）+ `agent/query_agent.py`（FunctionAgent 注入 LLM） | spy/零调用断言挂在 LLM seam，不 import 生成式 client |
| append-only failure audit 纪律 | Phase 15 `okf_rebuild_failure_audit` 的审计纪律（**表本身不复用**） | D4 要求全新 `okf_e2b_failure_audit`；主事务失败后用独立 fresh connection 追加写入 |

### 可借鉴的外部模式（注意许可边界）
| 来源 | 许可 | 可移植内容 | 边界 |
|---|---|---|---|
| ModelScope 官方 NER 离线测试 | Apache-2.0 | 本地路径 `pipeline(task, model=local_dir)` 的调用形态 | 只参考调用形态，不复制其测试代码进项目 |
| spaCy `Doc.char_span` | MIT | "边界对齐即失败"的校验纪律（strict alignment） | **不引入 spaCy 运行时依赖**；C1 用硬断言 + fail-closed 替代 |
| PostgreSQL `ON CONFLICT` | 开放 | 幂等物化语义 | 项目已用，无新依赖 |
| `portion` 区间代数 | LGPL-3.0 | 合并器 overlap/nested 规则的**测试期**交叉验证 | 不加入 runtime 依赖；运行时合并器按确定性规则手写 |
| `seqeval` | MIT | token 级分类报告的参考 | **不足**：契约要求 `(start,end,type)` 字符级 offset exact match，需自写小型 span 级指标 |

**关键结论：** offset 校验、确定性合并、mention provenance 都是"小而自写 + 契约测试"的性质；**没有成熟的 MIT 库**直接提供"字符级 offset exact-match mention 评测"或"带来源优先级的 NER 候选合并器"。不要为合并器引入通用区间库（LGPL 污染 + 规则不匹配），应手写确定性规则（稳定排序 + 同源去重 + 嵌套/重叠裁决 + **冻结来源优先级 D3**），用 property/确定性 fixture 锁定。幂等物化**必须**复用 E2a 的 `uuid5 + ON CONFLICT` 模式，不得另造。**pre-merge audit 不落库（D2）**：raw duplicates/overlaps/nested/selected/suppressed/grouped 由 OKF raw + sidecar + versioned sources + extractor/merger versions 确定性重建，只持久化 selected mentions。

---

## Dependency/Runtime Strategy

### 核心原则（全部来自冻结边界 + D-series，研究给出实现路径）
1. **默认 off，绝不 import/load 模型。** `RAG_ENTITY_EXTRACTOR=off`（默认）时，任何 `modelscope`/`torch` import 都不发生。实现为注册表 + 懒加载工厂：只有 `=raner` 且首次调用时才 import 并构造 pipeline（复用 `tree/runtime.py` 的 jieba 懒加载模式）。
2. **Fail-closed unknown switch。** `RuntimeSettings` 增加 `rag_entity_extractor: str = "off"` + `VALID_ENTITY_EXTRACTORS = {"off","raner"}`，在 `__post_init__` 校验，未知值启动即抛 `ValueError`（对齐 `VALID_VECTOR_BACKENDS` 风格）。`uie/base-news/hanlp/deepke` 不在合法集合内。
3. **最小 optional extra。** 在 `llamaindex_runtime/pyproject.toml` 增加 `[project.optional-dependencies] ner = [...]`，内容建议为：`modelscope>=1.39,<2`、`sentencepiece`（transformers/tokenizers/torch 已随 sentence-transformers 存在，但 PLAN 应显式列出并让 smoke 验证）。**不要**把 ner 加入 base dependencies。
   - 假设（待 smoke 验证）：裸 `modelscope` + `sentencepiece` + 已装 torch/transformers 足以推理。若 `import modelscope.pipelines` 触发缺失可选依赖，退路是隔离 venv 装 `modelscope[nlp]`（此时承受 datasets<=4.8.4 / spacy<=3.7.0 / pandas / sklearn 的重量）。
   - torch 构建选择：本机 torch 2.5.1+cu124 是 CUDA 版（~2.5 GB）。若目标是 Windows CPU 瘦部署，PLAN 可评估 CPU-only wheel（~200 MB）；这是资源预算的一部分，由 smoke 实测数据驱动裁决。
4. **只读 artifact mirror + 完整 SHA-256 lock manifest。** 
   - 镜像：`snapshot_download(model_id, revision=<冻结commit>, local_dir=<短路径只读镜像>)` 一次性构建；运行时 `pipeline(task, model=<镜像路径>)` 全离线，绝不依赖首次联网。
   - 锁：镜像内逐文件 SHA-256 校验（用 2026-07-13 裁决 §1.3 的 manifest 作为基准），`artifact_digest` 指向锁 manifest 摘要；任一文件不匹配即 fail-closed（结构化错误，不降级、不重建）。
   - Windows 长路径：镜像路径建议放在短路径（如 `C:\ms_raner_artifacts\raner_lg` 或项目 artifacts 根），避免 `~/.cache/modelscope/hub/models/iic/nlp_raner…/<revision>/…` 接近 260 字符上限。
   - `local_files_only=True` 也可用，但依赖 hub 缓存布局且跨 modelscope 版本脆弱；**首选本地路径直载**（`is_official_hub_path` 对存在的本地目录直接放行）。
5. **显式 `device='cpu'`。** pipeline 默认 `device='gpu'`；适配器必须传 `device='cpu'` 保证 Windows CPU 确定性 + 可复现的 benchmark。
6. **版本冻结。** modelscope 1.x 锁定 + transformers（当前 4.57.3，远新于模型导出时的 4.19.2）+ torch + tokenizers + sentencepiece 的精确组合，一律由隔离 smoke test 冻结成 `runtime_compatibility_id` 后写入文档；**不在 smoke 前把任何 tuple 写成已验证生产配置**。

### 备选：隔离环境边界
- 如果 PLAN 判定与 llama-index/sentence-transformers 的 transformers 版本存在升级冲突风险，则把整个 `ner` 运行时放进**独立 venv**，通过子进程/独立 entrypoint 暴露抽取，进程间只传 `MentionCandidate` 结构化 JSON。这是成本更高的隔离档，默认不选，仅在 smoke 暴露冲突时启用。

---

## Testing Strategy

按 pure / unit / integration / live one-shot 分层；live one-shot 必须有显式授权门（延续 Phase 15 的授权纪律）。所有持久化测试以 **per-document/version 原子事务（D4）** 为边界语义。

### pure / unit（无模型、无 DB，秒级）
- **DTO 判别不变式**：`input.normalized_text[char_start:char_end] == mention_text`；`corpus_span => span_id is not None and input_id==span_id and input_revision==document_revision`；`query_text => span_id is None and input_revision==query_revision`；越界/空 span/未知 label/切片不一致 → typed per-input error（该 input 归入 document 级原子失败，D4）。
- **Unicode offset fixtures**：中文全角标点、重复实体文本、换行/空白折叠、combining mark（如 `é`）、astral-plane emoji（如 `😀`）、`￾` 非字符；断言坐标是 Python code-point 而非 byte/UTF-16/token。
- **确定性合并器**：同源重复/嵌套/重叠在 **in-memory pre-merge audit** 全量保留（不落库，D2）；稳定排序键（`input_kind/input_id/input_revision/segment_id/char_start/char_end/raw_label/source`）；重跑输出一致；跨源冲突按**冻结来源优先级 `frontmatter_declared > dictionary_exact > rule_weight > model_probability > unavailable`（D3）**裁决；`unavailable` 不表示低置信。
- **label map**：版本化映射（PER→Person、LOC→Location、CORP/GRP→Organization 保留 raw_label、CW→CreativeWork、PROD→Product）。`entities.entity_type` 是 free-form TEXT（005:7），canonical type enum **不需 migration**（16-PATTERNS §3.5）；CW/PROD 的 label-map 写路径只做**版本化校验**（映射合法性由 label_map_digest + schema_version 校验），**不把 schema 支持重新列为 PLAN open question，也不授权新建 canonical entity（D1）**。
- **provenance 不可变**：`model_revision/artifact_digest/label_map_digest/runtime_compatibility_id` 一经写入不可被合并/投影改写。
- **零生成式 LLM spy**：在 `get_llm()`/FunctionAgent LLM seam 注入 spy，断言 C1 默认路径对 `.complete()/.acomplete()` 零调用（R-OKF-04 运行时半证；静态半证为 AST/import 审查）。

### integration（fake backend + DB，含一次性 disposable DB）
- **fake backend contract tests**：`FakeRaNERBackend` 实现与真实 adapter 相同的输入/输出契约（`type/start/end/span` + 可选 `prob`），驱动适配器层验证剥离 `prob`、切片断言、坐标回写、provenance 组装；不依赖真实权重。
- **query zero-durable-write**：`QueryTextInput` 走完整 extract→audit→merge 后，断言 `entity_mentions/entity_merge_log/entity_aliases/node_entity_links/evidence` 以及任何 durable raw candidate-audit sink 全部零写入（D2；可对真实 disposable DB 做 row-count 快照对比）。
- **per-document/version 原子性 + 失败审计（D4）**（复用 Phase 15 `_phase15_e2a_task88_*` 的 disposable 授权风格）：
  - **单个 invalid span → 该 document/version 全部回滚为零 mention/alias/merge/link**；随后其他 documents 按确定性顺序继续。
  - 失败记录写入全新 append-only `okf_e2b_failure_audit`（主事务 rollback/close 后用独立 fresh connection 追加）；断言**绝不写 `okf_rebuild_failure_audit`**。
  - 全语料等价重跑两次 → `entity_mentions/aliases/merge_log/node_entity_links` 行集逐位一致（确定性 `mention_id` + `ON CONFLICT DO NOTHING`）；`okf_e2b_failure_audit` 只追加、不重写既有条目。
  - concurrency：两并发回写同一 document/version 集不产生重复行/唯一键冲突死锁，失败审计独立连接可用。
- **D1 实体挂接测试**：exact compatible canonical-name 或 exact OKF alias/dictionary match → 挂既有 `entity_id`；否则 `entity_id=NULL`；断言 E2b 全程**不 INSERT 新 `entities` 行**。
- **D2 可重建性测试**：仅持久化 selected mentions；raw duplicates/overlaps/nested/selected/suppressed/grouped 在无 durable audit 表的情况下由 OKF raw + sidecar + versioned sources + extractor/merger versions 确定性重建并逐位一致。
- **D5 node 关联测试**：pending mention（entity_id=NULL）的 node 关联经 `entity_mentions.span_id -> tree_node_spans.span_id -> tree_node_spans.node_id` 推导成立；`node_entity_links` 表不被 pending mention 写入、PK 不变、不写 `chunk_entity_links`。
- **segmentation round-trip**：长文本分段 → 段内坐标回写 parent → `normalized_text[start:end] == mention_text` 全程成立；segment 带 `segment_id/parent interval/segmentation_version`。

### live one-shot（需授权；只做测量与证据，不设最终质量阈值）
- **离线 smoke**：断网冷启动 + 重复加载成功；`pipeline(task, model=镜像路径)` 对真实中文（含词典外 PER/LOC/ORG + 至少一个 CW/PROD fixture）返回正确坐标；记录实际 snapshot revision 与 fast-tokenizer 路径。
- **资源 benchmark**：Windows 11 CPU 与候选 WSL 分别记录冷启动秒数、p50/p95 span 延迟、吞吐、峰值 RAM、磁盘占用（镜像 **2.26 GB 权重/artifact footprint** + torch）、失败恢复；与预声明资源 envelope 对照；若 Large Generic 超预算，产出 Base News 同人工集质量/资源对比供显式裁决，**不自动降级**。
- **人工小集 metrics**：项目自有中文人工标注小集报告 precision/recall/F1、按类型 recall、offset exact match、label mapping、error counts；如实记录 MultiCoNER 半自动/弱监督构造性质。官方 benchmark 只作外部证据。
- **manifest 校验**：镜像逐文件 SHA-256 与冻结 manifest 全对。

### 测试框架落点（参考现有）
- 框架 pytest（已配 `integration`/`live_st` markers，conftest 已注册）；新增 marker 建议 `live_ner`（需离线镜像）与 `disposable_db`（需一次性 DB 授权），沿用 `test_live_sentence_transformers.py` 的 `pytestmark` 风格。
- fixtures 目录：`tests/llamaindex_runtime/fixtures/`（E2a 已有先例）；中文人工标注小集只用于验收测量，**不是训练数据或启动前置**。

---

## Licensing Boundary

- **模型卡 Apache-2.0 标记 ≠ 完整资产链。** 2026-07-13 裁决 §5/§6 与 BOUNDARY 均已冻结：`iic/nlp_raner_named-entity-recognition_chinese-large-generic` 仓库标注 Apache-2.0，但 Phase 20 G6 前必须复核仓库代码、权重、底座模型（XLM-RoBERTa，transformers 内 MIT 权重）与训练数据（MultiCoNER 半自动构造）的完整许可链。本研究**不做**最终法务判定。
- **HanLP 不进入 C1**：官方预训练模型默认 CC BY-NC-SA 4.0，外部/商业不能安全假定（2026-07-13 裁决 §2.3）。
- **portion (LGPL-3.0)**：仅测试期交叉验证可选，不进入运行时依赖，避免 LGPL 传染。
- **seqeval (MIT)**：如需 token 级参考可用，但契约度量是字符级 offset exact match，seqeval 不够。
- **spaCy (MIT)**：只借鉴 `char_span` 边界纪律，不引入运行时依赖。
- **本仓库 open-knowledge (GPL-3.0) 解禁**（2026-07-12 用户裁决）：entity-vault dossier 约定可复制，衍生文件打 GPL 来源头标；**不是 C1 模型/依赖路径，不相关**，仅提醒 PLAN 若移植其 `links.ts`/`frontmatter.py` 时遵守头标纪律。
- **不得复制受限许可代码**：所有外部示例只作调用形态参考，实现为项目自有代码。

---

## Environment Availability

> Step 2.6 审计结果（read-only 探测，2026-08-05）。

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | modelscope >=3.10 | ✓ | 3.11.9 | — |
| torch | RaNER 推理 | ✓（已装） | 2.5.1+cu124 | CPU-only wheel（瘦部署评估） |
| transformers | 模型加载 | ✓（已装） | 4.57.3 | 冻结 tuple 后定 |
| tokenizers | fast tokenizer offset | ✓（随 transformers） | — | — |
| sentencepiece | XLM-R BPE | ✗ | — | `ner` extra 增加（需装） |
| modelscope | pipeline | ✗ | — | `ner` extra 增加（需装） |
| adaseq | 训练（C1 不需要） | ✗ | — | 不装（推理用 modelscope 核心） |
| jieba | 词典/关键词补充 | ✓（已装） | 0.42.1 | — |
| WSL (wsl.exe) | 候选 WSL benchmark | ✓ | 存在 | 仅记录，不阻塞 Windows 主路径 |
| PostgreSQL | 一次性 DB 集成测试 | 需授权 | — | 沿用 Phase 15 disposable 授权流程 |
| 网络 | 一次性镜像构建 | 需授权 | — | 运行时断网；构建时一次性下载 |

**Missing with fallback:** sentencepiece / modelscope（经 `ner` extra 或隔离 venv）。
**Missing, blocking:** 无。唯一阻塞点是一性次模型镜像构建需网络 + 后续 disposable DB 集成测试需授权，均归 PLAN 授权门。

---

## Common Pitfalls

1. **把 pipeline 输出的 `prob` 当模型置信度。** 当前 SDK 默认 `return_prob=True`，`prob`=CRF logits 逐 token softmax，非标定 mention 概率。适配器必须固定 `confidence=None`/`confidence_kind="unavailable"` 并显式丢弃 `prob`；测试锁定。
2. **slow tokenizer 路径的 `.index()` 猜坐标。** 重复实体文本下 offset 不确定。强制 fast tokenizer；断言切片不变量；smoke 验证路径。
3. **512-token 静默截断丢 mention。** 长 span（>512 token）在 pipeline 默认下被截断；`split_max_length` 按字符数切、不 token 感知、无版本化段身份。适配器必须自带分段层。
4. **迁移编号幻觉。** BOUNDARY 的"预留 019_node_entity_links"已过期（019=E2a，**永不复用**）；`node_entity_links`/`tree_node_spans` 已存在。**016 的 `entity_mentions` 缺 provenance 字段且 D4 需要 `okf_e2b_failure_audit`，因此 C1 确实需要 schema-gap migration（概念上 provisional `020_ner_entity_mentions.sql`）**；conditional C2 后续一个（provisional 021）建 coref 两表。最终编号执行时按 ADR T5 核对 catalog 连续空闲号并显式记录，**不得预先声称已分配**。
5. **首次联网下载被当作可用。** `pipeline(model_id)` 会联网；运行时必须 `model=<本地镜像>` 且镜像经 SHA-256 校验，断网 smoke 为硬门。
6. **Windows 长路径。** modelscope 默认 cache 路径嵌套深；用短 `local_dir` 镜像避免 MAX_PATH。
7. **modelscope[nlp] 的版本约束传染。** `datasets<=4.8.4`/`spacy<=3.7.0` 可能与既有依赖冲突；优先裸 modelscope 最小集，冲突时隔离 venv 而非污染 base。
8. **把官方 benchmark 当项目质量证据。** 模型卡 P/R/F1 91+ 是外部证据；项目必须报告自有中文人工小集指标 + offset exact match。
9. **E2b 从 NER candidate 新建 canonical `entities`（D1 禁止）。** 仅 exact compatible canonical-name / exact OKF alias/dictionary match 可挂既有 entity，其余 `entity_id=NULL`；人工建 canonical entity 属未来 adjudication phase。
10. **用 per-span 事务当失败边界（D4 要求 per-document/version 原子）。** 首个 invalid span 应使该 document/version 全部回滚为零 mention/alias/merge/link，之后按确定性顺序继续其他 documents。
11. **复用/扩展 Phase 15 `okf_rebuild_failure_audit`（D4 禁止）。** 失败审计必须写全新 append-only `okf_e2b_failure_audit`，主事务 rollback/close 后用独立 fresh connection 追加。
12. **把 2.26 GB 当文本输入预算。** **2.26 GB 始终指模型 artifact/weight footprint**（权重 + 分词器等仓库文件），不是 text input budget、不是上下文长度。
13. **把 CW/PROD 等 canonical type 当成需要 schema enum/migration 的开放问题。** `entities.entity_type` 是 free-form TEXT（005:7），canonical type enum **不需 migration**（16-PATTERNS §3.5）；CW/PROD 的 label-map 写路径只做版本化校验即可。**不要重新把"CW/PROD 是否在 OKF schema"列为 PLAN open question，也不要借它授权新建 canonical entity（D1）。**

---

## Unknowns for PLAN（不得由本研究擅自冻结）

> 下列已冻结事项**不再**列入 open questions：D1（E2b 不新建 canonical entities）、D2（不建 durable candidate-audit 表）、D3（来源优先级已冻结）、D4（per-document/version 原子事务 + `okf_e2b_failure_audit`）、D5（node_entity_links 保持 canonical-entity-only + span_id 链推导）、D6（C1 需要 schema-gap migration）、C2（仅 C1 验收关闭后条件进入，默认 off）、canonical type enum（`entities.entity_type` free-form TEXT，不需 migration，写路径版本化校验，16-PATTERNS §3.5）。

| # | 事项 | 现状 | 为何不能本研究定 |
|---|---|---|---|
| U1 | 精确版本 tuple（modelscope 1.x / torch CPU-vs-CUDA / transformers 4.57.3 与模型导出 4.19.2 兼容性 / tokenizers / sentencepiece） | 假设可行，未实测 | 必须隔离 smoke 实测后冻结成 `runtime_compatibility_id` |
| U2 | 裸 modelscope + sentencepiece 是否足以推理（还是需要 `[nlp]` extra） | 假设可行（LazyImportModule） | import 链依赖具体版本，smoke 决定 |
| U3 | 当前 SDK 对该模型实际是否输出 `prob`（以及 `return_prob=False` 是否兼容） | 源码推断会输出 | 运行时行为以 smoke 为准，测试必须覆盖两种形态 |
| U4 | `id2label` 的 25 标签具体顺序 | 仅知 BIOES × 6 + O | 运行时从模型 config 读取，label map 版本化 |
| U5 | Large Generic 的 Windows CPU 冷启动/延迟/RAM/磁盘是否在预算内 | 无官方数据 | 实测 benchmark 后裁决；超预算才评 Base News 降级 |
| U6 | 迁移最终编号与命名（C1 schema-gap provisional `020_ner_entity_mentions.sql` / C2 provisional `021_*`） | 编号未分配 | "是否需要 migration"已由 D6 决定；**唯一待定是执行时按 ADR T5 核对 catalog 的连续空闲号并显式记录** |
| U7 | 人工小集规模与划分（只作验收测量） | 未建 | PLAN 定义最小集与采样协议 |
| U8 | `prob` 剥离位置（adapter 内剥 vs `return_prob=False` 关闭） | 推荐 adapter 内剥（鲁棒） | 实现细节，PLAN 选型 |

---

## Recommended Research-to-Plan Decisions

1. **运行基准确认**：C1 用"裸 `modelscope` + `sentencepiece` + 已装 torch/transformers/tokenizers"的最小 `ner` extra，隔离 smoke 冻结 tuple；失败退隔离 venv `modelscope[nlp]`。
2. **离线形态确认为本地路径直载**：`snapshot_download(revision=<冻结>, local_dir=<短只读镜像>)` → `pipeline(task, model=<镜像路径>, device='cpu')`；运行时零网络；逐文件 SHA-256 锁。
3. **适配器契约实现顺序**：①DTO 判别不变式 + fast-tokenizer 切片断言 → ②`prob` 剥离 + `confidence=None` 锁定 → ③自有 token 感知分段层 → ④确定性合并器（含冻结来源优先级 D3）→ ⑤corpus/query 持久化判别 + per-document/version 原子事务（D4）。
4. **幂等物化复用 E2a 模式**：确定性 `uuid5` + `ON CONFLICT`；`mention_id` 自然键含 `document_revision/span_id/char_start/char_end/entity_type/source/extractor_id/model_revision`；事务外包 per-document/version（D4）。
5. **迁移策略冻结（D6）**：C1 需要一个 schema-gap migration（概念上 provisional `020_ner_entity_mentions.sql`，补齐 016 缺的 provenance 字段并创建 append-only `okf_e2b_failure_audit`）；conditional C2 后续一个 migration（provisional 021）建 `coref_clusters` + `coref_cluster_mentions`；**019 永不复用**。最终编号执行时按 ADR T5 核对 catalog 连续空闲号并显式记录，不得预先声称已分配。
6. **测试分层落地**：pure/unit 秒级 + fake-backend integration + disposable DB 幂等/原子/并发 + 授权 live one-shot（smoke/benchmark/人工小集）；零 LLM spy 挂 `get_llm()` seam。
7. **许可证**：模型卡 Apache-2.0 只作仓库级标记；完整资产链审查留给 Phase 20 G6，本研究与 PLAN 不得宣称法务通过。
8. **D1-D5 已冻结实现约束**（直接进 PLAN 任务，不重开讨论）：每 document/version 原子事务 + 全新 `okf_e2b_failure_audit`（D4）；E2b 不新建 canonical entities（D1）；不建 durable candidate-audit 表（D2）；来源优先级 `frontmatter_declared > dictionary_exact > rule_weight > model_probability > unavailable`（D3）；`node_entity_links` 保持 canonical-entity-only、pending mention 经 `entity_mentions.span_id -> tree_node_spans` 推导、不写 `chunk_entity_links`（D5）。
9. **术语纪律**：文档/代码/验收中 **2.26 GB 一律指模型 artifact/weight footprint**，不得与文本输入预算混淆。
10. **canonical type enum 关闭（16-PATTERNS §3.5）**：`entities.entity_type` 是 free-form TEXT，CW/PROD 等 label-map 写路径做版本化校验即可；不把 schema 支持重新列为 PLAN open question，也不授权新建 canonical entity（D1）。

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | 裸 modelscope + sentencepiece 足以 RaNER 推理（无需 `[nlp]` extra） | Dependency/Runtime Strategy | import 链拉起重依赖或缺包 → 退隔离 venv，tuple 冻结延迟 |
| A2 | 当前 modelscope 对该模型实际输出 `prob` | Executive Findings #3 | 若版本不同不输出，测试仍须覆盖剥离逻辑（契约不变） |
| A3 | 本机 CUDA 版 torch 2.5.1+cu124 可跑 CPU 推理 | Environment Availability | 一般成立；实测确认 |
| A4 | 迁移**最终编号/命名**（C1 provisional 020 / C2 provisional 021）可在执行时按 ADR T5 确定 | Executive Findings #7, U6 | 若后续 phase 占用号段，按 ADR T5 取下一连续空闲号并显式记录；**"需要 migration"本身已由 D6 决定，非假设** |
| A5 | transformers 4.57.3 能加载 `transformers_version=4.19.2` 导出的 XLM-R config | Dependency/Runtime Strategy | 不兼容则需按 smoke 冻结兼容版本 |
| A6 | wsl.exe 可用作 WSL benchmark 环境 | Environment Availability | 仅记录项；不可用则只报 Windows |
| A7 | `entities.entity_type` free-form TEXT 且 canonical type enum 不需 migration（16-PATTERNS §3.5） | Testing Strategy / label map | 已由仓库 005:7 与 16-PATTERNS §3.5 核实；若未来加 constraint 需另行裁决，当前不属 C1 |

以上 A1/A2/A3/A5 均由隔离 smoke test 验证后提升为 HIGH；A4 为执行时核对项；A6/A7 由 PLAN 核对。

---

## Sources

### Primary（HIGH）
- ModelScope 模型卡 / 文件 API / configuration.json / config.json（访问 2026-08-05）
- modelscope/modelscope GitHub master 源码：builder.py、token_classification_pipeline.py、token_classification_preprocessor.py、task_models/token_classification.py、snapshot_download.py、pyproject.toml、tests/pipelines/test_named_entity_recognition.py
- PyPI JSON：modelscope 1.39.1、seqeval 1.2.2、portion 2.6.2、spacy 3.8.14
- 本机 read-only 探测（2026-08-05）
- 仓库内：`.planning/phases/16-raw-corpus-entity-layer/16-BOUNDARY.md`、`.planning/research/PHASE16-CHINESE-NER-MODEL-SELECTION-2026-07-13.md`、`llamaindex_runtime/registry/migration_catalog.py`、`llamaindex_runtime/registry/migrations/003_tree_persistence.sql`、`005_kg_extension.sql`、`016_entity_mentions.sql`、`llamaindex_runtime/okf/e2a_contracts.py`、`llamaindex_runtime/okf/e2a_materialization_dml.py`、`llamaindex_runtime/config.py`、`llamaindex_runtime/pyproject.toml`、`.planning/OKF-LOW-TOKEN-GAPS-SUPPLEMENT-HANDOFF-2026-07-12.md`、`.planning/phases/16-raw-corpus-entity-layer/16-PATTERNS.md`（§3.5）

### Secondary（MEDIUM）
- PostgreSQL `INSERT ... ON CONFLICT` 官方文档
- spaCy `Doc.char_span` API

### Tertiary（LOW，供验证）
- 模型卡 benchmark 数值与 MultiCoNER 构造性质（2026-07-13 裁决 §1.2 已如实标注口径）

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — ModelScope 运行时机制与离线路径经源码/官方测试验证；tuple 精确版本为 MEDIUM（待 smoke）。
- Architecture: HIGH — 已按 D1-D9 对齐（per-document/version 原子事务、不新建 canonical entities、不建 durable candidate-audit、冻结来源优先级、node_entity_links canonical-entity-only、C1 schema-gap migration）+ 仓库内既有模式（E2a/lazy-import/switch）给出实现路径。
- Pitfalls: HIGH — 基于源码行为的确定性陷阱（prob/slow tokenizer/512 截断）+ D-series 边界（迁移号/事务粒度/audit 复用/2.26 GB 术语/canonical type enum 不需 migration）。

**Research date:** 2026-08-05（修订对齐 D1-D9；label-map 修正 2026-08-06 依据 16-PATTERNS §3.5）
**Valid until:** 2026-09-05（30 天；ModelScope SDK 与 migration 目录属快变项，PLAN 时先复核 master 与 catalog 尾部）
