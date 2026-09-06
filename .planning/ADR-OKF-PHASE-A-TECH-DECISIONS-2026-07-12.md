# ADR: OKF 阶段 A 技术分叉定稿（T1-T9）

> **状态：已定稿（用户逐项拍板，2026-07-12 navigator 会话）**
> **上游文档**：`.planning/OKF-MULTIROUTE-EXECUTION-HANDOFF-2026-07-12.md` 第 9 节（T1-T9 不得静默决定项）
> **架构总纲**：`.planning/UNIFIED-MULTIROUTE-OKF-PLAN.md`（D1-D8 决策不变）
> **效力**：本文件解除交接书对"开始写 migration 或 serializer"的封锁。阶段 A 实施必须遵守本文件；但 raw-pair 的当前生成与生产准入已由 [ADR-OKF-RAW-PAIR-GENERATION-BINDING-2026-07-16.md](ADR-OKF-RAW-PAIR-GENERATION-BINDING-2026-07-16.md) 扩展并取代本文件中的仅 Markdown+sidecar 历史基线。除此项之外，偏离任何一项需重新请求用户确认。

---


## Phase 14 canonical-path ratification (2026-07-17)

This is a dated amendment to the higher-precedence handoff, recorded here for technical-decision consistency; it is not a fourth authority. `OKF_BUNDLE_ROOT` (default `okf_bundle`) is the Phase 14 bundle-root authority. Canonical templates are `okf_bundle/templates/`, and `scripts/rebuild_from_okf.py` is the sole canonical E1 CLI. `scripts/rebuild-from-okf.py` is unsupported, with no compatibility wrapper or duplicate tree required. `okf-bundles/main/entities/e001-内蒙古自治区卫健委.md` remains a legacy sample/test fixture only and is not a canonical root. All active Phase 14 acceptance predicates must use these ratified paths.

---

## 定稿依据：2026-07-12 核验快照中的代码事实

> **历史证据说明**：下表中的 `parser.py` 行号是本 ADR 在 2026-07-12 定稿时的快照，不是当前实现或验收的行号证据。当前实现应按符号定位：`llamaindex_runtime/okf/parser.py` 中的 `OKFParagraph`、`OKFParser.parse_paragraphs`、`OKFParser.compute_hash`、`OKFParser._parse_authorized` 与 `OKFParser._parse_admitted_raw`，以及 `llamaindex_runtime/okf/raw_pair.py::read_raw_pair`。其中 raw 文件的当前准入权威见 [ADR-OKF-RAW-PAIR-GENERATION-BINDING-2026-07-16.md](ADR-OKF-RAW-PAIR-GENERATION-BINDING-2026-07-16.md)。

| 事实 | 位置 | 内容 |
|---|---|---|
| span_id 公式 | `llamaindex_runtime/ingestion/docling_ingestor.py:78-81` | `uuid5(NAMESPACE_URL, f"{doc_id}\|{version_id}\|{page_no}\|{'/'.join(headings)}\|{offset}\|{text}")`，六要素取自 `NormalizationContract.normalize()` 归一化结果 |
| OKFParagraph 字段 | `llamaindex_runtime/okf/parser.py:57-63`（历史快照） | 仅 `id/content/heading/okf_file_path`，无任何 span 坐标 |
| 段落切分 | `parser.py:272`（历史快照） | 裸 `body.split("\n\n")`，排版变化即漂移 |
| 文件 hash | `parser.py:294-304`（历史快照） | 原始 bytes 的 SHA256，空白/YAML 键序敏感 |
| migration 序列 | `llamaindex_runtime/registry/migrations/` | 001-014 连续无缺号 |
| migration 执行方式 1 | `verification/docker-compose.yml:12` | 整目录挂载 `/docker-entrypoint-initdb.d`，PostgreSQL 按字典序执行全部 `.sql` |
| migration 执行方式 2 | `scripts/run_pageindex_real_retrieval_workflow.py:21-26,183-203` | 硬编码子集清单 `MIGRATION_FILES`（001/002/003/007），按清单顺序执行 |
| migration 执行方式 3 | 根目录 `run_migrations.py` | 另一份硬编码 `key_migrations` 清单 |
| evidence_links 现状 | `migrations/005_kg_extension.sql` | 有 span_id + confidence，无字符 offset、无 mention text |
| 融合机制 1 | `llamaindex_runtime/tree/semantic_distribution.py::_compute_fusion_score` | 固定权重 vector 0.40 + keyword 0.30 + rerank 0.20 + distribution 0.10（总和已为 1） |
| 融合机制 2 | `llamaindex_runtime/analysis/fusion.py:40::fuse_candidates` | RRF + multi-path bonus，无固定权重 |

---

## T1 + T2 — raw OKF 的 span 坐标表达：相邻 sidecar JSON ✅

**2026-07-12 历史基线**：本决议最初规定每个合法 raw Markdown 位置配一个相邻的版本化 sidecar 文件；当时的 serializer 目标为零层级 `raw/<slug>.md` 与 `raw/<slug>.spans.json`，安全的 `raw/<safe-relative-directory>/<slug>.*` 也被视为合法位置。sidecar 逐 span 记录：

- `page_no`、`heading_path`、`offset`
- **归一化后的精确 `text`**（即 `NormalizationContract.normalize()` 输出，span_id 的第六要素）
- sidecar 自身带 `schema_version`，随格式演进版本化

**当前生产绑定权威（扩展并取代上述仅 Markdown+sidecar 的生成/准入基线）**：[ADR-OKF-RAW-PAIR-GENERATION-BINDING-2026-07-16.md](ADR-OKF-RAW-PAIR-GENERATION-BINDING-2026-07-16.md) 规定生成 raw 工件集必须为同 slug、相邻的三工件：`<slug>.md`、`<slug>.spans.json`、`<slug>.pair.json`。manifest 为强制性绑定记录；生产准入必须按 manifest 绑定执行 M-D-S-M 读取与校验。当前 serializer 生成零层级三工件，生产 reader 也接受安全嵌套位置；不存在 sidecar-only 或缺失 manifest 的回退路径。

**持续有效的坐标语义**：

1. span 身份（`span_id` 六要素）**只从 sidecar 重建**，绝不从 Markdown 正文重新推导；round-trip 一致性与 Markdown 排版彻底解耦。
2. `raw/` 下的合法 raw Markdown 保持人类可读，标记为机器生成（在 AGENT.md 声明：raw/ 不接受人工编辑，人工知识编辑走 `entities/`、`concepts/`、`synthesis/`）。
3. 文件级 frontmatter 只放文档级溯源：`doc_id`、`version_id`、source checksum、docling 版本、type: raw。
4. 原始二进制归档保留，不销毁（继承交接书 D2 控制措施）。

**否决的备选**：逐段 inline 锚点（污染可读性、人工编辑易破坏）；全量入 frontmatter（YAML 膨胀数百行，工具链体验差）。

## T3 — hash 语义：双层 ✅

**决议**：

- 保留原始文件 bytes 的 SHA256 作为 `source_checksum`（审计用途）；
- 另设 **canonical structural hash**（frontmatter 规范化序列化 + sidecar 的确定性 JSON 序列化）供 `okf_sync_state` 的 sync 比对使用。

语义未变的格式化重写不得触发全量重建。

## T4 — mention 存储模型：新建 entity_mentions 表 ✅

**决议**：新建 `entity_mentions`（`mention_id` PK、`entity_id` FK、`span_id`、`char_start`、`char_end`、`mention_text`、`confidence`、`source`、OKF 溯源字段）。`evidence_links` 保留为高层 entity/relation→span 证据映射，不扩列。

## T5 — migration 编号：从 015 续编 ✅

**决议**：

1. 新 migration 从 `015_*` 起，三位零填充（保证 initdb 字典序正确）。
2. 禁用旧计划的 `001_okf_authoritative.sql` 命名（与 `001_initial.sql` 在 initdb 挂载中冲突）。
3. docker initdb 路径会自动拾取新文件；两处硬编码清单（`run_pageindex_real_retrieval_workflow.py` 的 `MIGRATION_FILES`、根目录 `run_migrations.py`）**需要 OKF 表时必须显式加入新文件**，实施时逐一核对。

## T6 — relation 限定词落点：显式列 + JSONB 兜底 ✅

**决议**：`relations` 表（或阶段 A 定稿的关系持久化目标）为四个已知限定词加显式列：

- `negation` boolean NOT NULL DEFAULT false
- `condition` text NULL
- `direction` text NULL
- `confidence` numeric NULL

另加 `qualifiers` JSONB 容纳未来扩展（时间范围等）。parser 不得无声丢弃 OKF frontmatter 中的限定词字段。独立 `relation_mentions` 表列为 C 阶段后按需插入项，阶段 A 不建。

## T7 — R3 实体信号注入路径：先接 RRF，热点权重延后 ✅

**决议**：阶段 D 将 R3 仅作为额外来源路径接入 `analysis/fusion.py::fuse_candidates`（RRF 路径），保留来源标签与可观测分数。`_compute_fusion_score` 的固定权重（总和已为 1）不在 D 阶段重分配；是否让实体信号进热点加权路径由 F 阶段消融矩阵决定。不伪造"最优权重"。

**注意**：旧计划中的 `_fuse_candidate_scores` 函数**不存在于代码库**，不得按该名称搜索或修改。

## T8 — Agent 回写初始开关：仅 proposal/staging + 人审 ✅

**决议**：阶段 E 初始形态为 proposal/staging + 人工审阅，人类编辑优先。Agent 自动 commit 需单独用户批准并配质量门。即 D8 的正式落地配置。

## T9 — span_id 比对形态：自动化回归 ✅

**决议**：span_id round-trip 比对（`S_direct == S_okf` 100% 一致）实现为：

1. 自动化 pytest 回归测试 + 可重复运行的确定性 CLI 验证命令；
2. fixtures 至少三类：有章节的 PDF、有表格/复杂排版的 PDF、DOCX；
3. 失败报告必须指出**首个不一致的坐标**（span 级 page_no / heading_path / offset / text 对比）;
4. 该回归是阶段 A→B 的硬阻塞门，不是可选质量评测。

---

## 对阶段 A 规划的直接影响

1. 封锁解除：migration（015 起）与 docling→OKF serializer 可以进入规划与 TDD 实施。
2. 阶段 A 交付物清单在 2026-07-12 决策时为：格式契约与 templates、docling→OKF 序列化器（含 sidecar）、parser 补全（sidecar 读取 + 增量/删除 + frontmatter 校验）、migrations（okf_sync_state、okf_rebuild_log、entity_aliases、entity_mentions、entity_merge_log、relation 限定词列）、rebuild-from-okf 脚本、span_id 回归测试。**当前生产的 raw 生成与准入约束以 [ADR-OKF-RAW-PAIR-GENERATION-BINDING-2026-07-16.md](ADR-OKF-RAW-PAIR-GENERATION-BINDING-2026-07-16.md) 为准**：serializer 生成 `.md`、`.spans.json`、`.pair.json` 三工件，manifest 强制且准入必须 manifest-bound；不得实现 sidecar-only 回退。
3. 阶段 A 非目标不变：不做 NER、不调 PageIndex、不动融合权重、不开 Agent 回写、不做 Phase 14 对比。
4. 实施时遵守 CLAUDE.md GitNexus 规则（impact analysis 先行、detect_changes 后提交）与 TDD（测试先红）。

---

## Phase 14 范围扩展：Docling 2.109 HeadingHierarchyModel（用户批准 2026-07-14）

**用户明确批准**将 Phase 14 范围扩展为：
1. 固定 `docling==2.109.0`（pyproject.toml）
2. 在默认生产读取器 `_build_default_reader` 中启用 Docling 官方 `HeadingHierarchyModel`

**T9 保持不变**：真实分层 PDF 必须行使多级 `heading_path`（深度 >= 2）。

**配置**：
- `HeadingHierarchyOptions(enabled=True, use_bookmarks=True, use_numbering=True, use_style=True, max_level=6, bookmark_match_threshold=0.8)`
- `PdfPipelineOptions(generate_parsed_pages=True)` （样式推断所需）
- 注入 `DoclingReader(export_type='json', doc_converter=DocumentConverter(...))`

**Span-ID 迁移影响**：启用 HeadingHierarchyModel 改变了 PDF 文档的 `headings` 元数据字段（heading_path），因为 `span_id` 公式包含 heading_path，PDF span 的 span_id 将与旧 flat-reader 输出不同。这是**有意的迁移边界**，不是回归。page_no/offset/text 坐标保持稳定，`DoclingIngestor(reader=custom_reader)` 注入路径仍可用于回滚。

**授权范围**：`docling_ingestor.py` 从 read-only 变为仅 `_build_default_reader` 的窄授权例外。不改公共接口、归一化、span 公式、调用者或非 PDF 行为。
