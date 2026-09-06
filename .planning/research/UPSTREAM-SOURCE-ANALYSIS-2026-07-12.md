# 上游源码分析与改造裁决（Upstream Source Analysis）

**日期：** 2026-07-12
**触发：** 用户指示：不要从头写代码或只借鉴逻辑，把原项目下载下来深读源码，实际改造其代码。
**方法：** 7 个上游仓库浅克隆到 `E:\github\rag-upstream\`（仓库外，不进 git），5 个并行分析代理逐仓深读。
**地位：** 本文件是 v2.0 各阶段 PLAN 的**改造来源权威表**。执行 14-01/14-03/14-04/16/18 前必读对应小节。

> 重新克隆命令（如 rag-upstream 目录丢失）：
> ```bash
> mkdir -p /e/github/rag-upstream && cd /e/github/rag-upstream
> for repo in GoogleCloudPlatform/knowledge-catalog atomicstrata/llm-wiki-compiler VectifyAI/OpenKB ogham-mcp/ogham-mcp thisismydesign/okf-lint inkeep/open-knowledge mchu1966/okf-wiki; do git clone --depth 1 "https://github.com/$repo.git" "$(basename $repo)"; done
> ```

---

## 0. 总裁决表

| 仓库 | 语言 | License | 裁决 | 消费阶段 |
|---|---|---|---|---|
| GoogleCloudPlatform/knowledge-catalog | 规范 + TS 工具 | Apache-2.0 | **ADOPT（规范）** — SPEC.md 为唯一符合性依据；示例 bundle 直接作 parser 符合性 fixture | 14 |
| ogham-mcp/ogham-mcp | **Python 3.13** | MIT | **ADAPT（移植代码）** — serialization/concept/bundle 三模块 + 20+ 往返测试直接移植改造 | 14-01/03/04 |
| thisismydesign/okf-lint | TS (npm) | MIT | **ADOPT（工具原样用）** — CI 符合性门禁，`.okflintrc.json` 配置，不 fork | 14-04, CI |
| mchu1966/okf-wiki | 模板 | MIT | **ADAPT（约定复制）** — bundle 布局/AGENT.md 边界章节/index.md/log.md 约定复制进 14-01 骨架 | 14-01, 18 |
| atomicstrata/llm-wiki-compiler | TS | MIT | **REFERENCE（设计翻译）** — 审阅队列状态机/候选存储/锁与原子性设计翻译为 Python，不搬码 | 18；14 canonical hash 参考 |
| VectifyAI/OpenKB | **Python 3.10+** | Apache-2.0 | **ADAPT（局部移植）** — frontmatter 助手、MutationSnapshot 回滚日志、实体/概念页 schema；转换管线仅 REFERENCE | 15/16/18 |
| inkeep/open-knowledge | TS 单仓 | **GPL-3.0** | **ADAPT（用户裁决 2026-07-12 解禁搬码）** — 项目自用不分发，GPL 私用合规；工具函数移植 + SKILL.md/工作流文本直接复制。绊线见 §7 | 16/18 |

**License 结论：** MIT/Apache-2.0 均允许移植 + 署名（在被移植文件头注明来源仓库与 license）。**open-knowledge（GPL-3.0）经用户裁决解禁**：本项目为私人自用、不分发，GPL 的 copyleft 义务只在分发/传播时触发，私用（含修改后私用）完全合规、无开源义务。**绊线（TRIPWIRE）：将来若把本仓库分发或开源，所有 GPL 衍生文件要么整仓转 GPL-3.0，要么剥离替换**——因此每个从 open-knowledge 移植/复制的文件必须打头标 `# Ported from inkeep/open-knowledge (GPL-3.0) — see UPSTREAM-SOURCE-ANALYSIS tripwire`，保证可 grep 定位、可整体剥离。

---

## 1. OKF v0.1 规范符合性核验（knowledge-catalog）

规范文件：`rag-upstream/knowledge-catalog/okf/SPEC.md`。对我们设计的判定：

| 我们的设计 | 规范判定 |
|---|---|
| frontmatter 只强制 `type` | ✅ 规范唯一强制字段就是非空 `type`；值不注册、自由取 |
| doc_id/version_id/source_checksum/docling_version/generated_by | ✅ 扩展字段明确允许（§4.1：消费者 MUST 保留未知键、MUST NOT 拒绝） |
| okf_bundle/{raw,entities,concepts,synthesis} 布局 | ✅ 规范不强制目录结构（§3 domain-agnostic） |
| sidecar `*.spans.json` | ✅ 非 markdown 文件不在规范辖域（示例 bundle 里也有 viz.html 共存） |
| 机器生成区 | ✅ 规范明确支持 agent 部分生成的 bundle |

**规范新增给我们的义务（此前计划遗漏，已回写 14 计划）：**
1. `index.md` / `log.md` 是**保留文件名**（可选存在）：parser 在任何层级都必须跳过它们、不当 concept 摄入。
2. bundle 根 `index.md` 是唯一允许带 frontmatter 的 index，且 frontmatter 只含 `okf_version: "0.1"`。
3. 除根 index 外，保留文件必须无 frontmatter。

**符合性 fixture（免费测试资产）：** `okf/bundles/{crypto_bitcoin, ga4, stackoverflow}` 三个生产级示例 bundle，2-3 层嵌套 + index.md 链 + 多种 type。14-04 的 parser 符合性测试直接以它们为输入。

---

## 2. ogham-mcp —— Phase 14 的最大改造来源（Python，直接移植）

模块：`src/ogham/okf/{serialization,concept,identity,bundle}.py`。**与我们同语言，MIT，本轮最高价值发现。**

### 移植清单（14-01 / 14-03 执行时按此落地）

| 源文件 | 移植去向 | 移植内容 |
|---|---|---|
| `serialization.py` | `llamaindex_runtime/okf/` | `write_concept`/`read_concept`：`yaml.safe_dump(sort_keys=False, allow_unicode=True)` + 插入序 dict 定序；CRLF 兼容读取；**写恰好一个尾换行 / 读剥恰好一个**（防多轮往返换行累积）；fail-fast 于缺 frontmatter/坏 YAML |
| `concept.py` | parser 字段编组 | `_RECOGNISED_FIELDS` 集合 + 未识别键落 metadata 再回吐的**未知字段零丢失**模式（正是我们 T6"限定词不丢"的现成实现）；timestamp 的 datetime/ISO-string 双态归一 `.isoformat()` |
| `bundle.py` | serializer/rebuild | 同文件系统临时目录 + `shutil.move` 的**原子导出**；`rglob("*.md")` 递归发现 + 保留文件名跳过；malformed 文件 skip+计数（不静默、不崩溃） |
| `tests/test_okf_{roundtrip,serialization,concept,bundle,identity}.py` | 14-04 回归套件 | 20+ 边界用例直接翻译：往返身份保持、**尾换行漂移**、未知键保留、规范推荐字段经 metadata 存活、malformed 计数、保留文件跳过、okf_version 声明、unicode/emoji slug |

### ogham 没有、必须自研的部分（用户问"是否还要自己写"的答案）
- **无内容寻址**：ogham 身份 = UUID 字段，非内容哈希 → 我们的 span_id uuid5 公式与 canonical structural hash **无上游可搬，保持 14-01 自研**。
- **无 sidecar 机制** → `*.spans.json` 设计保持自研。

---

## 3. okf-lint —— CI 符合性门禁（原样采用）

- 调用：`pnpm dlx @thisismydesign/okf-lint ./okf_bundle --max-warnings 0`；退出码 0/1/2。
- 19 条规则（6 error + 13 warning），逐条见其 `src/versions/v0_1/rules.ts`。
- **对我们 bundle 的预判**：error 全过；warning 缺 `title/description/timestamp` 三项 → 裁决：raw 文件 frontmatter **增补 `title`（取首标题或文件名）与 `timestamp`（ISO 8601）**，`description` 规则在 `.okflintrc.json` 降级 off（raw 是机器区，无一句话摘要）。
- `.staging/` 目录本身不触发失败；staging 内 `.md` 若无 frontmatter 会报 → 18 阶段把 `.staging/` 加入 lint 排除或保证提案文件带 frontmatter。
- sidecar `*.spans.json` 不被扫描（只看 .md）。✅

---

## 4. okf-wiki —— bundle 骨架与 AGENT.md 模板（约定复制）

- 其布局 `bundles/main/{raw,sources,entities,concepts,synthesis}` 与我们几乎同构；差异：多一层 `sources/`（人读的来源摘要页）。裁决：**14-01 不加 sources/**（我们 raw 直接被管线消费，来源摘要属 18 的 synthesis 域），但保留其"raw 不可变、机器专属"的边界原话进 AGENT.md。
- **AGENT.md 直接套用其三段边界结构**（✅ Always / ⚠️ Ask first / 🚫 Never），其中 Never 区含"Modify files in raw/"、"Remove or alter the type field"、"Use relative links"。
- index.md（分区链接目录，仅根带 `okf_version` frontmatter）与 log.md（`## YYYY-MM-DD` 新在前）格式照抄。注意其模板用了非标准 `okf_wiki_version` 键——**我们用规范/okf-lint 认可的 `okf_version`**。
- 各 type 的 frontmatter 样例（source-summary/entity/concept/synthesis/query）作为 14-01 templates/ 的底稿。

---

## 5. llm-wiki-compiler —— Phase 18 审阅队列蓝图（设计翻译，TS 不搬码）

Phase 18 进 PLAN 时按以下设计翻译为 Python：

- **候选存储**：`.staging/candidates/<id>.json` 一提案一文件；驳回移入 `archive/`（其 `.llmwiki/candidates/` 模式）。
- **结构化 hold 原因**：`HeldReason` 码表（low-confidence / contradicted / schema-violating / provenance-violating / imported / manual-review-requested）——我们的提案 schema 增补此字段。
- **并发安全**：锁下重读候选（TOCTOU 防护）+ 审阅命令全程持锁。
- **原子性诚实分层**：只有正文写入是原子（journal），索引/状态刷新是 best-effort 可重跑尾段——18 的合入执行器照此分层，不假装全原子。
- **改进点（他们没有、我们要加）**：显式审计字段 `approvedBy/approvedAt/rejectedReason`——他们批准后删候选即无痕，我们的审计 journal 补上。
- **canonical hash 佐证**：其 `canonicalBody()`（剥派生 Citations 节再 sha256）与我们"canonical hash 排除格式性变化"同思想；但其 frontmatter 序列化**不定序**（刻意有损）——反例佐证我们 14-01 必须自己钉死定序。
- 其引用锚是行号区间（无字符偏移）→ 再次确认 span_id 链无上游可搬。

---

## 6. OpenKB —— Phase 15/16/18 的 Python 素材（Apache-2.0，VectifyAI 同门）

- **Python 3.10+，与 PageIndex 同作者**；用 `pageindex==0.3.0.dev3` 库处理 ≥20 页长文档（`if_add_node_summary=True`——注意它默认开摘要，我们 D7 保持关）。
- **可移植**：
  - `frontmatter.py`（kv_line/list_line/block/parse——JSON 转义的 YAML 行渲染，简洁）；
  - `mutation.py::MutationSnapshot`（硬链接快照 + 回滚 journal 的**崩溃安全变更**模式）→ 15 的全量重建演练与 18 的合入执行器采用；
  - `state.py::HashRegistry`（SHA-256 去重注册表）→ 15 的增量同步参考。
- **实体/概念页约定（16/18 采用）**：`type: Organization|Person|...`（title-case 实体类型）、`sources: [...]`（多来源追踪列表，更新时 prepend）、`aliases: [...]`、正文 `[[wikilink]]` 交叉链接。与我们 entity_aliases/entity_mentions 表天然对齐。
- **确认空白**：无字符偏移、无 heading_path 保真（只留页码）→ 我们 sidecar 仍是必要自研。
- 其转换用 markitdown/pymupdf 而非 docling → 转换管线 REFERENCE only（D2 锁定 docling）。

---

## 7. open-knowledge —— GPL-3.0，用户裁决解禁（2026-07-12 二次深读产出文件级移植清单）

> **用户原话裁决：**"open-knowledge这个是我自己使用，我认为你需要突破这个代码限制。"——项目自用不分发，GPL 私用合规，解除搬码禁令。
> **绊线（TRIPWIRE）：** 将来分发/开源本仓库前，必须处置 GPL 衍生部分（整仓转 GPL 或剥离）。所有移植/复制文件打头标（见 §0 License 结论），`grep -r "inkeep/open-knowledge"` 即可枚举剥离清单。

仓库形态：bun/Node 24 TS monorepo（v0.29.1），核心是 Yjs CRDT 协作 + Hocuspocus 服务器 + 19 个 MCP 工具 + 一组随包 SKILL.md。CRDT/服务器/Web UI 与我们无关（SKIP）；价值在纯逻辑工具函数与 agent 指令文本。

### 7a. PORT——TS→Python 翻译移植（打 GPL 头标）

| 源文件 | 内容 | 去向 |
|---|---|---|
| `packages/server/src/content/frontmatter-merge.ts` | **RFC 7396 merge-patch 语义**（patch 值替换、null/''/[] 删键、undefined 保留）——正是 Phase 18"提案 = frontmatter merge-patch + body diff"的现成应用语义 | 18 提案格式/合入执行器 |
| `packages/core/src/util/doc-name.ts` | **写入时准入门**：docName 严格校验（禁 `..` 路径穿越、绝对路径、控制字符、点前缀隐藏段）——合入执行器的白名单前置校验 | 18 合入执行器 |
| `ingest-body.ts:74-78` slug 规则 | kebab-case slug `^[a-z0-9][a-z0-9-]{0,99}$`，日期不进 slug 进 frontmatter | 14-03 serializer 文件名 / 18 |
| `packages/core/src/util/atomic-yaml-write.ts` | tmp+rename 原子写 + **>30s 陈旧 .tmp.* 孤儿自动清扫**（ogham 原子导出之上的补强） | 18 合入执行器 |
| `packages/server/src/mcp/tools/links.ts` + wiki-link 解析 | 相对链接解析归一、**断链检测**（写后返回 brokenLinks 列表）、`[[wikilink]]` 提取 | 16 实体交叉链接 / 18 提案校验 |
| `write.ts` 资产去重段 | SHA-256 字节去重 + 不匹配时日期版本化 re-ingest | 18 来源摄入 |

注意与已有裁决的**去重**：YAML frontmatter 编解码、原子导出、未知字段保留仍以 **ogham-mcp（Python 直搬）为第一来源**——open-knowledge 只补 ogham 没有的（merge-patch、准入校验、断链检测、陈旧 tmp 清扫）。不要双重移植同一功能。

### 7b. COPY——文本/约定原样复制（打 GPL 头标）

- **SKILL.md 三件套**（`packages/server/assets/skills/`）：`project/SKILL.md`（grounding 规则"每个事实声明必须引用本地来源，裸 URL 不是完成的引用"、persist-as-you-go"知识库即 checkpoint"、链接纪律）、`packs/okf/SKILL.md`（type 一条规则 + 保留文件 + log.md 契约原文）、`packs/entity-vault/SKILL.md`（**dossier 约定**：编译真相区 + `--- timeline ---` 分隔 + 追加式时间线 `- **YYYY-MM-DD** | source | @author — evidence. Confidence: …`）→ 摘录进我们的 `okf_bundle/AGENT.md` 与 18 的 agent 提示词。
- **工作流 STOP 门文本**：`consolidate-body.ts:25-35` 的"决策确认门"（写 canonical 前必须确认：决策是什么/否决了哪些备选/理由——决策未定则拒绝固化）→ 18 人审 CLI 的 approve 提示语底稿；`research-body.ts:66-72` 的"边做边写、逐源摄入不批处理"→ 18 agent 指令。
- **log 纪律**：`## YYYY-MM-DD: <summary>` 追加式、新在前 + 每次 write/edit 带 ≤80 字符 user-facing `summary` 字段 → 18 审计 journal 的双层结构（人读 log.md + 机器读 summary 字段）。
- 三层工作流 external-sources→research→articles 的 `status: provisional|canonical` + `sources:[...]` + `supersedes:[...]` frontmatter 溯源链 → 16/18 实体与综合页的状态与溯源字段。

### 7c. SKIP

Yjs/CRDT、Hocuspocus 服务器、@tiptap/ProseMirror、React/Electron UI、Orama 搜索、MCP server 注册基建——全部与我们 headless Python 管线无关。

---

## 8. 对各阶段计划的具体增量（已回写）

| 文件 | 增量 |
|---|---|
| 14-CONTEXT.md | 新增上游事实：规范符合性 5 判定 + 保留文件义务 + license 表 |
| 14-01-PLAN.md | serializer/契约改为"移植 ogham serialization.py 模式"；bundle 骨架增 index.md（含 okf_version）/log.md；AGENT.md 用 okf-wiki 三段边界模板；raw frontmatter 增 title/timestamp |
| 14-03-PLAN.md | parser 增保留文件跳过；未知字段零丢失采用 ogham `_RECOGNISED_FIELDS`+metadata 模式 |
| 14-04-PLAN.md | 回归套件并入 ogham 20+ 用例（尾换行漂移最优先）；新增 okf-lint CI 门禁任务；knowledge-catalog 3 示例 bundle 为 parser 符合性 fixture |
| 15-BOUNDARY.md | 指针：OpenKB MutationSnapshot/HashRegistry 为重建与增量同步参考 |
| 16-BOUNDARY.md | 指针：实体页 frontmatter 采 OpenKB 约定（type title-case / sources / aliases / wikilink）+ open-knowledge entity-vault dossier/timeline 约定与断链检测（§7，解禁后） |
| 18-BOUNDARY.md | 指针：审阅队列按 llm-wiki-compiler 设计翻译 + 显式审计字段增补；open-knowledge 解禁后新增：RFC 7396 merge-patch 提案语义、doc-name 准入校验、STOP 决策门文本、log 纪律 + summary 字段双层审计（§7a/7b） |

## 9. 自研保留区（明确不找上游）

1. span_id uuid5 公式与 NormalizationContract 耦合链（Phase 1-13 验证数据之锚，全生态无同类物）。
2. sidecar `*.spans.json` 契约与 canonical structural hash（ogham 无内容哈希、llm-wiki-compiler 刻意不定序、OpenKB 无偏移）。
3. R3 递归 CTE 多跳（贴我们 schema）；jieba/HanLP/UIE 是 pip 库调用，不涉及搬码。
