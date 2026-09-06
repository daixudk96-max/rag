OKF / Open Knowledge Format开源支持项目总览
按高星项目、支持方式、适用场景与优先级整理
整理日期：2026-07-02｜说明：星数会持续变化，本文以检索时区间和约数为准。
核心判断： OKF 已经从单一规范发展出一批可用工具链，但生态仍处于早期。优先关注能实际完成“生成、读取、导入导出、MCP 服务、编辑器集成或校验”的项目，而不是只在 README 中提到 OKF 的仓库。
# 一、优先级建议
• 想做长期 LLM Wiki：优先看 llm-wiki-compiler、OpenKB、OpenKnowledge。
• 想把第三方文档喂给 Claude/Codex/Cursor：优先看 OKFy、docmd OKF 插件、Ogham MCP。
• 想把代码仓库自动变成知识库：优先看 superops-team/okf。
• 想做数据模型和表关系知识库：优先看 OWOX Model Canvas 与 Google Knowledge Catalog。
• 想做格式校验和 CI 门禁：优先看 okf-lint。
• 想在 Obsidian/Gemini 中直接使用：优先看 Obsidian Gemini Helper。
# 二、1,000 Stars 以上或高关注度核心项目
项目
仓库
星数
链接
OKF 支持方式
适用场景
优先级
OpenKB
VectifyAI/OpenKB
约 1.9k
打开
生成 OKF-ready Wiki 页面；支持概念页、实体页、交叉链接、图谱和 Obsidian。
大量 PDF、Word、PPT、Excel、网页资料编译成长期知识库。
高
llm-wiki-compiler
atomicstrata/llm-wiki-compiler
约 1.4k
打开
OKF Producer + Consumer；支持 export/import OKF、MCP Server、SDK、引用追踪、审核队列。
构建可持续维护的 LLM Wiki，做知识编译、检索和 Agent 上下文。
最高
ArcKit
tractorjuice/arc-kit
约 1.1k
打开
/arckit:export-okf 与 /arckit:import-okf；企业架构文档可与 OKF 互通。
企业架构治理、需求、设计、风险、方案评审。
高
OpenKnowledge
inkeep/open-knowledge
1k+
打开
OKF Starter Pack；concepts/references/notes/index.md/log.md；MCP 与 Claude/Codex/Cursor 集成。
人工编辑 + Agent 共同维护 Markdown Wiki。
高
docmd
docmd-io/docmd
1k+
打开
@docmd/plugin-okf；文档站构建时输出 OKF Bundle、manifest、lint report、可选 graph viewer。
已有 Markdown 技术文档站，希望同步产出 LLM 可读知识包。
高
Knowledge Catalog
GoogleCloudPlatform/knowledge-catalog
1k+
打开
OKF v0.1 规范、参考 Agent、示例 Bundle、可视化工具。
查规范、做兼容实现、测试 OKF 样例。
基准
# 三、其他已确认有实质 OKF 支持的项目
项目
仓库
级别
链接
OKF 支持方式
适用场景
Ogham MCP
ogham-mcp/ogham-mcp
100-999 Stars
打开
src/ogham/okf 下有 bundle、concept、identity、serialization、viewer 模块；有导入导出和 round-trip 测试。
MCP 长期记忆、Agent 持久知识后端。
Obsidian Gemini Helper
takeshy/obsidian-gemini-helper
100-999 Stars
打开
支持将 OKF Bundle 作为 Gemini 聊天知识源；递归读取 type/title/description/tags/path/excerpt。
Obsidian + Gemini 本地知识源。
Claude Skills Journalism / okf-wiki
jamditis/claude-skills-journalism
100-999 Stars
打开
包含 OKF Wiki Skill、脚手架、validate.py、hooks、示例 bundle。
Claude Code 自动维护结构化 Wiki。
OKFy
0dust/OKFy
工具型项目
打开
文档站/Markdown 转 OKF Bundle；提供 MCP Server、search_concepts、read_concept、get_neighbors、Inspector。
把 Stripe/Clerk 等第三方文档转成本地 Agent 可检索知识源。
superops-team/okf
superops-team/okf
工具型项目
打开
Go CLI/SDK；Git 仓库扫描、自动生成知识库、增量更新、Git Hook、搜索、Lint。
代码仓库自动生成 OKF 知识库。
OWOX Model Canvas
OWOX/owox-model-canvas
专业场景
打开
OKF import/export；ModelGraph ⇄ OKF Markdown Bundle；可视化数据模型。
数据模型、数据集、表关系、ERD 和指标体系。
okf-viewer / okf-ui
nsoybean/okf-ui
辅助工具
打开
本地 OKF Bundle 图谱浏览器；live reload、backlinks、type filter、conformance overlay。
检查和浏览 OKF Bundle。
okf-lint
thisismydesign/okf-lint
辅助工具
打开
OKF v0.1 Linter；校验 frontmatter、type、index/log、链接、时间戳等。
CI、格式校验、质量门禁。
OKF Wiki
mchu1966/okf-wiki
模板项目
打开
Obsidian-backed、LLM-maintained Wiki 模板；bundles/main 下 raw/sources/entities/concepts/synthesis。
个人知识库、Obsidian + Agent 维护 Wiki。
# 四、推荐工具链组合
通用 LLM Wiki：llm-wiki-compiler 或 OpenKB → okf-lint → OKFy/Ogham MCP → okf-viewer
团队 Markdown 知识库：OpenKnowledge → OKF Starter Pack → Git 同步 → Claude/Codex/Cursor 使用
技术文档站：docmd → @docmd/plugin-okf → site/okf → Agent 或静态文件服务读取
代码仓库知识化：superops-team/okf → Git Hook 增量更新 → okf-lint → MCP/Viewer
数据模型知识库：OWOX Model Canvas → OKF import/export → Knowledge Catalog 示例校验
# 五、常用命令速查
llm-wiki-compiler 导出 OKF
llmwiki export --target okf --out ./dist/okf
llm-wiki-compiler 导入 OKF
llmwiki import --okf ./dist/okf --dry-run
OpenKB 初始化与添加文档
openkb initopenkb add paper.pdfopenkb query "What are the main findings?"
OKFy 文档转 OKF + MCP
npx -y okfy-ai init stripe https://docs.stripe.com/checkoutnpx -y okfy-ai serve stripe --mcp --auto-refresh
superops-team/okf 初始化
okf initokf search -q "database"okf lint
okf-lint 校验
pnpm dlx @thisismydesign/okf-lint ./my-bundle
okf-viewer 浏览
npx okf-viewer ./path/to/bundle
# 六、规范与关键文档链接
• OKF v0.1 SPEC — https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md
• Google OKF examples — https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf/bundles
• llm-wiki-compiler OKF guide — https://github.com/atomicstrata/llm-wiki-compiler/blob/main/docs/guides/open-knowledge-format.mdx
• docmd OKF plugin — https://github.com/docmd-io/docmd/tree/main/packages/plugins/okf
• OpenKnowledge OKF skill — https://github.com/inkeep/open-knowledge/blob/main/packages/server/assets/skills/packs/okf/SKILL.md
• Obsidian Gemini Helper OKF docs — https://github.com/takeshy/obsidian-gemini-helper/blob/master/docs/OKF.md
# 七、注意事项
• OKF v0.1 目前仍可视为早期草案，项目之间会有扩展字段和严格度差异。
• 基础 OKF 规范中，非保留 Markdown 文档最核心的强制字段是 YAML Frontmatter 的 type。某些工具会额外要求 title、description、timestamp 等字段。
• “支持 OKF”不等于成熟生产级兼容。优先看是否有实际 parser、serializer、import/export、lint、viewer 或 MCP 工具。
• 大型知识库应配合 Git、CI Lint、审核队列和来源引用，避免 Agent 自动生成内容不可追溯。