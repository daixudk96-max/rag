> **Phase 14 path amendment (2026-07-17):** For active implementation and acceptance, `OKF_BUNDLE_ROOT` (default `okf_bundle`) is authoritative, templates are `okf_bundle/templates/`, and `scripts/rebuild_from_okf.py` is the only canonical E1 CLI. The former hyphenated CLI is unsupported. The historical `okf-bundles/main/entities/e001-内蒙古自治区卫健委.md` is a legacy sample/test fixture only.

> **Supersession and historical-design notice (2026-07-17, controlling for this document).** Everything below is retained as historical ideation from the v2.0 design; it is **not** a current acceptance predicate, executable instruction, or authorization. This scope expressly includes every legacy `okf-bundles` path; `migrations/001_okf_authoritative.sql`; all destructive, `DROP`, truncate, full-rebuild, or full-index-rebuild pseudocode; Git/post-commit hooks; automatic `git add`/`git commit` operations and Agent commits; and every DB operation. This historical design document grants no authority by itself: current Phase 15 routing and authorization defer to the active [OKF execution handoff](OKF-MULTIROUTE-EXECUTION-HANDOFF-2026-07-12.md), including its Phase 14/E1 and Phase 15/E2a–E2b boundaries and accepted-ADR references. Its destructive migration, Git, and legacy-path content remains non-executable historical material. No Git or DB authorization is inferred from this historical document.

# LLM Wiki 接入 rag项目实施计划 v2.0（历史设计，已被当前权威路径取代）

**项目**: E:\github\rag
**目标**: 以OKF为权威源，建立OKF↔DB双向闭环
**工期**: 8-10周（4个Phase）
**日期**: 2026-07-02
**版本**: v2.0（修正v1.0单向问题）

---

## v1.0 问题反思

### v1.0 的根本缺陷

| 问题 | v1.0做法 | 后果 |
|------|---------|------|
| **单向流动** | 仅OKF→DB摄入 | 检索发现的新关系无法回写OKF |
| **DB为中心** | DB是存储，OKF是输入 | OKF沦为"导入格式"，不是基础 |
| **Agent无角色** | Agent没有维护OKF职责 | OKF内容静态，无法自演化 |
| **无闭环** | 摄入是一次性动作 | 知识库无法自我增厚 |
| **DB不可重建** | DB独立存储，与OKF脱钩 | 数据一致性无法保证 |

### v2.0 核心修正

```
v1.0:  OKF ──→ DB（存储）──→ 检索 ──→ 结果（丢弃）
                  ↑ 单向，DB为中心

v2.0:  OKF（权威）⟷ DB（缓存）──→ 检索 ──→ Agent分析 ──→ 回写OKF
              ↑ 双向，OKF为中心，闭环
```

---

## 核心理念（v2.0）

### 原则1: OKF为唯一权威源（Single Source of Truth）

- **所有持久化知识**存储在OKF的`.md`文件中
- DB**不是存储**，是OKF的派生索引（rebuildable cache）
- DB可以随时`DROP`并从OKF全量重建，不丢失任何知识
- 任何写操作都**通过OKF**，禁止直接写DB（DB只由摄入管道写）

### 原则2: 双向同步（OKF ⟷ DB）

**方向1: OKF → DB（摄入）**
- 触发：Git post-commit hook
- 执行者：摄入管道（Parser + Processor + Indexer）
- 场景：人类/Agent编辑OKF后，DB重建

**方向2: DB → OKF（回写）**
- 触发：检索发现新知识（关系/alias/concept）
- 执行者：LLM Agent（分析QueryHit → 生成OKF → 写文件）
- 场景：系统发现的新关系回写到OKF，知识库自增厚

### 原则3: LLM Agent为回写桥梁

- Agent**读取**DB检索结果（QueryHit）
- Agent**分析**实体关系、聚类、新概念
- Agent**生成**OKF Markdown内容（YAML frontmatter + body）
- Agent**写入**okf_bundle/{entities,relations,concepts}/
- Agent**提交**Git commit → 触发方向1重建DB
- 闭环完成：知识库自演化

### 原则4: Git为版本控制+触发器

- Git管理OKF版本（人类可review Agent的commit）
- post-commit hook触发DB重建
- Commit message区分人类编辑 vs Agent编辑
- 冲突通过Git merge解决（人类优先）

---

## 闭环架构图

```
┌──────────────────────────────────────────────────────────┐
│  编辑层                                                  │
│  ┌──────────────┐    ┌──────────────────────────────┐   │
│  │ 人类         │    │ LLM Agent                    │   │
│  │ (Obsidian)   │    │ - 读写OKF                    │   │
│  │ - 可视化编辑 │    │ - 分析检索结果               │   │
│  │ - Graph view │    │ - 发现新关系/概念            │   │
│  └──────┬───────┘    └──────┬───────────────────────┘   │
│         │ 编辑               │ 回写                      │
│         ↓                    ↓                           │
├──────────────────────────────────────────────────────────┤
│  权威层：OKF bundles（.md文件，Git版本控制）            │
│  ┌──────────────────────────────────────────────────┐    │
│  │ okf_bundle/                                │    │
│  │  ├── entities/    ← 实体页面（canonical_id+aliases）│   │
│  │  ├── relations/   ← 关系页面（含negation/condition）│   │
│  │  ├── concepts/    ← 概念页面                       │    │
│  │  ├── synthesis/   ← 综合分析                       │    │
│  │  ├── raw/         ← 原始文档                       │    │
│  │  └── AGENT.md     ← Agent指令                      │    │
│  └────────────────────┬─────────────────────────────┘    │
│                       │ git commit                       │
│                       ↓                                  │
├──────────────────────────────────────────────────────────┤
│  摄入层：post-commit hook → 摄入管道                    │
│  ┌──────────────────────────────────────────────────┐    │
│  │ OKF Parser → EntityProcessor → RelationProcessor │    │
│  │              → VectorIndexer → TreeBuilder        │    │
│  └────────────────────┬─────────────────────────────┘    │
│                       ↓ 重建（可DROP重建）              │
├──────────────────────────────────────────────────────────┤
│  缓存层：DB（派生索引，非存储）                         │
│  ┌──────────────────────────────────────────────────┐    │
│  │ tree_nodes | vector_chunks | entities             │    │
│  │ entity_aliases | entity_mentions | high_value_relations │
│  │ okf_sync_state（版本哈希、可重建标记）            │    │
│  └────────────────────┬─────────────────────────────┘    │
│                       ↓ 查询                             │
├──────────────────────────────────────────────────────────┤
│  检索层：向量召回 + KG多跳查询                          │
│  └────────────────────┬─────────────────────────────┘    │
│                       ↓ QueryHit（含okf_file_path）      │
│                       ↓                                  │
│              ┌────────┴────────┐                         │
│              │ LLM Agent分析   │ ← 回到编辑层（闭环）   │
│              │ 发现新关系      │                         │
│              │ → 写OKF → commit│                         │
│              └─────────────────┘                         │
└──────────────────────────────────────────────────────────┘
```

---

## 双向数据流详解

### 方向1: OKF → DB（摄入）

```
触发: git commit（修改okf-bundles/*.md）
  ↓
post-commit hook 检测变更文件
  ↓
Sync Service 增量分析（版本哈希对比）
  ↓
分类处理:
  - 新增文件 → 全量摄入
  - 修改文件 → 删除旧索引 + 重建
  - 删除文件 → 标记deleted
  ↓
EntityProcessor → entities, entity_aliases, entity_mentions
RelationProcessor → high_value_relations
VectorIndexer → vector_chunks（含okf_file_path溯源）
TreeBuilder → tree_nodes
  ↓
更新 okf_sync_state（版本哈希、时间戳）
  ↓
DB重建完成
```

### 方向2: DB → OKF（回写，v2.0新增）

```
触发: 检索服务返回QueryHit
  ↓
LLM Agent 分析检索结果:
  - 识别未归一的实体提及 → 新alias候选
  - 识别未记录的实体关系 → 新relation候选
  - 识别聚类形成的新概念 → 新concept候选
  ↓
Agent 生成 OKF 内容:
  - YAML frontmatter（含canonical_entity_id, aliases, relations）
  - Markdown body（含evidence_paragraph引用）
  - 标记 author: agent, generated_at: timestamp
  ↓
OKF Writer 写入文件:
  - 更新 entities/*.md（追加aliases）
  - 新建 relations/*.md（新关系）
  - 新建 concepts/*.md（新概念）
  ↓
Agent Git commit:
  - commit message: "agent: discovered relation E001→E005 from query Q123"
  - 触发 post-commit hook
  ↓
方向1执行: DB重建（包含新知识）
  ↓
闭环完成: 知识库自增厚
```

---

## Phase 设计（v2.0；历史草案，非当前阶段授权）

### Phase 1: OKF为权威源的基础设施（2周）

**目标**: 建立OKF权威源地位，DB可从OKF全量重建。

**核心任务**:

#### 1.1 OKF Bundle完善

**位置**: `okf_bundle/`

```
okf_bundle/
  ├── .obsidian/         # Obsidian配置
  ├── raw/               # 原始文档（immutable）
  ├── entities/          # 实体页面 ✓已有示例
  ├── relations/         # 关系页面
  ├── concepts/          # 概念页面
  ├── synthesis/         # 综合分析
  ├── templates/         # 模板（entity/relation/concept）
  ├── index.md           # Bundle索引
  ├── log.md             # 操作日志
  └── AGENT.md           # Agent职责指令
```

**AGENT.md 关键内容**:
```markdown
# Agent 职责
- 读取DB检索结果（QueryHit）
- 分析实体关系、聚类、新概念
- 生成OKF内容写入对应目录
- Git commit（message标记`agent:`）
- 禁止直接写DB，所有写入通过OKF
```

**待完成**:
- ⏸️ 复制`.obsidian/`配置
- ⏸️ 创建`templates/`（entity/relation/concept模板）
- ⏸️ 创建`AGENT.md`
- ⏸️ 创建`index.md`、`log.md`

#### 1.2 OKF Parser ✓（已完成，需完善）

**位置**: `llamaindex_runtime/okf/parser.py`

**已有**:
- ✓ OKFParser, OKFDocument, OKFFrontmatter, OKFParagraph
- ✓ parse_bundle(), parse_document()
- ✓ 哈希计算

**待完善**:
- ⏸️ 增量解析（仅解析变更文件）
- ⏸️ 删除检测（对比上次同步状态）
- ⏸️ 单元测试

#### 1.3 DB Schema（历史草案；非现行 migration 或 DB 操作授权）

**位置**: `migrations/001_okf_authoritative.sql`

**关键设计**: 增加`okf_sync_state`表，记录同步状态，支持重建。

```sql
-- 溯源字段（所有派生表）
ALTER TABLE tree_nodes
  ADD COLUMN okf_file_path TEXT,
  ADD COLUMN okf_version_hash TEXT;

ALTER TABLE vector_chunks
  ADD COLUMN okf_file_path TEXT,
  ADD COLUMN okf_paragraph_id TEXT,
  ADD COLUMN okf_version_hash TEXT;

-- 同步状态表（核心：支持重建）
CREATE TABLE okf_sync_state (
  okf_file_path TEXT PRIMARY KEY,
  okf_version_hash TEXT NOT NULL,
  file_type TEXT NOT NULL,  -- entity/relation/concept/raw
  last_synced_at TIMESTAMP DEFAULT NOW(),
  last_sync_commit TEXT,    -- Git commit hash
  is_deleted BOOLEAN DEFAULT false,
  db_record_count INTEGER   -- 派生记录数（校验用）
);

-- 重建日志（审计）
CREATE TABLE okf_rebuild_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  rebuild_type TEXT,        -- full / incremental
  started_at TIMESTAMP,
  completed_at TIMESTAMP,
  files_processed INTEGER,
  records_rebuilt INTEGER,
  status TEXT,
  error_detail TEXT
);
```

**待完成**:
- ⏸️ 编写迁移SQL
- ⏸️ 执行迁移

#### 1.4 全量重建脚本（历史伪代码；不构成 E1 全量重建或 DB 操作授权）

**位置**: `scripts/rebuild_from_okf.py`

**功能**:
- DROP所有派生表数据（保留表结构）
- 从OKF bundle全量重建
- 验证重建一致性（记录数对比）
- 记录rebuild_log

**伪代码**:
```python
def rebuild_from_okf(bundle_path: Path):
    # 1. 记录重建开始
    log = start_rebuild_log("full")

    # 2. 清空派生表（事务）
    with transaction():
        truncate_derived_tables()  # tree_nodes, vector_chunks, entities等

    # 3. 全量摄入
    docs = OKFParser.parse_bundle(bundle_path)
    for doc in docs:
        EntityProcessor.process(doc)
        RelationProcessor.process(doc)
        VectorIndexer.index(doc)
        TreeBuilder.build(doc)

    # 4. 一致性校验
    verify_consistency(bundle_path)

    # 5. 记录重建完成
    complete_rebuild_log(log)
```

**待完成**:
- ⏸️ 编写rebuild脚本
- ⏸️ 测试全量重建

#### 1.5 测试

**测试文件**: `tests/test_okf_parser.py`, `tests/test_rebuild.py`

**测试用例**:
- Parser解析正确性
- 全量重建一致性
- 重建后数据完整性

**待完成**:
- ⏸️ 编写测试

**Phase 1 交付物**:
- ⏸️ 完善的OKF bundle结构
- ⏸️ migrations/001_okf_authoritative.sql
- ⏸️ scripts/rebuild_from_okf.py
- ⏸️ tests/test_okf_parser.py
- ⏸️ tests/test_rebuild.py

**Phase 1 验收**:
- ⏸️ OKF Parser解析正确
- ⏸️ DB可从OKF全量重建
- ⏸️ 重建后数据一致
- ⏸️ Obsidian能打开bundle

---

### Phase 2: 摄入管道 OKF → DB（历史草案；hook/自动执行不获授权）

**目标**: 实现OKF→DB摄入管道，Git hook自动触发。

**核心任务**:

#### 2.1 Entity Processor

**位置**: `llamaindex_runtime/okf/entity_processor.py`

**功能**:
- 解析entities/*.md
- 实体归一（canonical_entity_id + aliases）
- mentions提取（从body paragraphs）
- 写入entities, entity_aliases, entity_mentions表
- 记录okf_file_path溯源

**待完成**:
- ⏸️ 编写entity_processor.py
- ⏸️ 实体归一逻辑

#### 2.2 Relation Processor

**位置**: `llamaindex_runtime/okf/relation_processor.py`

**功能**:
- 解析relations/*.md
- 解析relations字段（保留negation/condition）
- evidence_paragraph → chunk_id绑定
- 写入high_value_relations表

**待完成**:
- ⏸️ 编写relation_processor.py

#### 2.3 Vector Indexer

**位置**: `llamaindex_runtime/okf/vector_indexer.py`

**功能**:
- OKF paragraphs → vector_chunks
- 计算embedding（复用现有embedder）
- 关联tree_nodes（heading_path映射）
- 填充okf_file_path, okf_paragraph_id

**待完成**:
- ⏸️ 编写vector_indexer.py

#### 2.4 Tree Builder

**位置**: `llamaindex_runtime/okf/tree_builder.py`

**功能**:
- OKF目录层级 → tree_nodes
- heading_path构建
- summary生成
- okf_file_path溯源

**待完成**:
- ⏸️ 编写tree_builder.py

#### 2.5 Git Hook + Sync Service（历史草案；不获 Git hook 或自动执行授权）

**位置**: `.git/hooks/post-commit`, `llamaindex_runtime/okf/sync_service.py`

**post-commit hook**:
```bash
#!/bin/bash
changed_okf=$(git diff --name-only HEAD~1 HEAD | grep 'okf-bundles/')
if [ -n "$changed_okf" ]; then
  python scripts/sync-okf-bundle.py --files "$changed_okf"
fi
```

**Sync Service（摄入方向）**:
```python
class OKFSyncService:
    def sync_incremental(changed_files: List[Path]):
        # 1. 解析变更文件
        # 2. 对比okf_sync_state版本哈希
        # 3. 分类处理：新增/修改/删除
        # 4. 调用对应Processor
        # 5. 更新okf_sync_state
        # 6. 记录rebuild_log

    def detect_changes(bundle_path: Path) -> List[ChangeRecord]
    def reconcile_deletes(deleted_files: List[Path])
```

**待完成**:
- ⏸️ 编写post-commit hook
- ⏸️ 编写sync_service.py（摄入方向）
- ⏸️ 编写scripts/sync-okf-bundle.py入口

#### 2.6 测试

**测试文件**:
- `tests/test_entity_processor.py`
- `tests/test_relation_processor.py`
- `tests/test_sync_service_ingest.py`

**Phase 2 交付物**:
- ⏸️ entity_processor.py, relation_processor.py
- ⏸️ vector_indexer.py, tree_builder.py
- ⏸️ sync_service.py（摄入方向）
- ⏸️ post-commit hook
- ⏸️ 测试文件

**Phase 2 验收**:
- ⏸️ Git commit → DB自动同步
- ⏸️ 实体归一准确率≥85%
- ⏸️ 版本一致性≥99%
- ⏸️ 测试覆盖率≥80%

---

### Phase 3: 回写管道 DB → OKF（2-3周）⭐ v2.0核心

**目标**: 实现 DB→OKF 回写，Agent 自动维护OKF，形成闭环。

**这是v2.0相比v1.0最关键的Phase，实现双向闭环。**

**核心任务**:

#### 3.1 OKF Writer 模块

**位置**: `llamaindex_runtime/okf/okf_writer.py`

**功能**:
- 生成OKF Markdown内容
- YAML frontmatter生成（含扩展字段）
- Markdown body生成（含evidence引用）
- 文件写入okf_bundle/{entities,relations,concepts}/
- 保持OKF格式规范
- 不破坏人类编辑的文件（追加而非覆盖）

**关键方法**:
```python
class OKFWriter:
    def write_entity(entity: EntityRecord) -> Path:
        """写入或更新entity文件（保留人类编辑内容）"""

    def write_relation(relation: RelationRecord) -> Path:
        """新建relation文件"""

    def write_concept(concept: ConceptRecord) -> Path:
        """新建concept文件"""

    def update_entity_aliases(entity_id: str, new_aliases: List[str]):
        """追加aliases到现有entity文件（不覆盖）"""

    def _generate_frontmatter(record) -> str
    def _generate_body(record) -> str
    def _preserve_human_edits(file_path: Path, new_content: str) -> str
```

**关键设计: 保留人类编辑**
- 读取现有文件内容
- 仅更新frontmatter的特定字段（aliases, relations）
- body部分追加`## Agent Discovered (timestamp)`段落
- 不删除人类编写的内容

**待完成**:
- ⏸️ 编写okf_writer.py
- ⏸️ 实现保留人类编辑逻辑

#### 3.2 关系发现服务

**位置**: `llamaindex_runtime/okf/discovery_services.py`

**功能**:
- 分析QueryHit结果
- LLM分析实体关系（调用现有LLM）
- 生成新关系proposal
- 返回RelationRecord供Writer使用

**关键方法**:
```python
class RelationDiscoveryService:
    def discover_from_query(self, query_hit: QueryHit) -> List[RelationProposal]:
        """
        分析检索结果，发现未记录的实体关系
        1. 提取QueryHit中的实体提及
        2. LLM分析实体间关系
        3. 对比现有high_value_relations
        4. 返回新关系proposal
        """

class AliasDiscoveryService:
    def discover_aliases(self, entity_id: str) -> List[str]:
        """发现实体的新别名（从mentions中聚类）"""

class ConceptDiscoveryService:
    def discover_concepts(self, cluster_id: str) -> List[ConceptProposal]:
        """从向量聚类发现新概念"""
```

**待完成**:
- ⏸️ 编写discovery_services.py
- ⏸️ 集成LLM分析

#### 3.3 Agent Commit 服务（历史草案；不获自动 Git 操作授权）

**位置**: `llamaindex_runtime/okf/agent_committer.py`

**功能**:
- Agent写入OKF文件后，自动Git commit
- Commit message规范（标记Agent生成）
- 触发post-commit hook → DB重建
- 闭环完成

**关键方法**:
```python
class AgentCommitter:
    def commit_discoveries(self, discoveries: List[Discovery]):
        """
        1. 调用OKFWriter写入文件
        2. git add okf-bundles/
        3. git commit -m "agent: discovered N relations, M aliases"
        4. 触发post-commit hook → DB重建
        5. 记录log.md
        """

    def _generate_commit_message(self, discoveries) -> str
    def _update_log_md(self, discoveries)
```

**Commit message规范**:
```
agent: discovered 3 relations, 2 aliases from query Q123

- relation: E001 (卫健委) -[监管]-> E005 (某医院)
- relation: E005 (某医院) -[属于]-> E003 (医疗集团)
- alias: E001 += "自治区卫健委"
- source_query: Q123
- generated_at: 2026-07-02T10:30:00Z
```

**待完成**:
- ⏸️ 编写agent_committer.py
- ⏸️ Git commit自动化

#### 3.4 冲突解决机制

**位置**: `llamaindex_runtime/okf/conflict_resolver.py`

**功能**:
- 人类编辑优先
- Agent编辑标记`author: agent`
- 版本哈希校验（OKF文件 vs okf_sync_state）
- 冲突时保留人类版本，Agent版本暂存待review

**冲突场景处理**:

| 场景 | 处理 |
|------|------|
| 人类编辑 vs Agent同时编辑 | 人类优先，Agent变更暂存`staging/` |
| Agent发现的关系与人类冲突 | 保留人类版本，Agent标记`conflict: true` |
| 版本哈希不一致 | 触发全量重建 |

**待完成**:
- ⏸️ 编写conflict_resolver.py
- ⏸️ 冲突检测逻辑

#### 3.5 回写触发集成

**位置**: `llamaindex_runtime/tree/runtime.py`

**改动**:
- 检索完成后，可选触发回写
- QueryHit返回后，调用DiscoveryService
- Agent分析并写入OKF

```python
# runtime.py 扩展
def query_with_discovery(query: str) -> QueryHit:
    hit = self.query(query)

    # 触发回写（可选，基于配置）
    if config.enable_agent_discovery:
        discoveries = discovery_service.discover_from_query(hit)
        if discoveries:
            agent_committer.commit_discoveries(discoveries)
            # 触发DB重建后，hit可能已更新

    return hit
```

**待完成**:
- ⏸️ 集成回写触发
- ⏸️ 配置开关

#### 3.6 测试

**测试文件**:
- `tests/test_okf_writer.py`
- `tests/test_discovery_services.py`
- `tests/test_agent_committer.py`
- `tests/test_conflict_resolver.py`
- `tests/test_closed_loop.py`（闭环集成测试）

**闭环测试用例**:
```python
def test_closed_loop():
    """验证完整闭环：编辑OKF → DB重建 → 检索 → Agent回写 → DB重建"""
    # 1. 人类编辑OKF（添加entity）
    write_okf_entity("E006-某医院.md")
    git_commit("human: add hospital entity")

    # 2. 验证DB重建
    assert db_has_entity("E006")

    # 3. 检索（触发Agent发现）
    hit = query_with_discovery("卫健委监管的医院")

    # 4. 验证Agent回写OKF
    assert okf_has_relation("E001", "监管", "E006")
    assert last_commit_is_agent()

    # 5. 验证DB再次重建（包含新关系）
    assert db_has_relation("E001", "监管", "E006")
```

**Phase 3 交付物**:
- ⏸️ okf_writer.py
- ⏸️ discovery_services.py
- ⏸️ agent_committer.py
- ⏸️ conflict_resolver.py
- ⏸️ runtime.py回写集成
- ⏸️ 测试文件（含闭环测试）

**Phase 3 验收**:
- ⏸️ Agent能从检索结果发现新关系
- ⏸️ 回写OKF不破坏人类编辑
- ⏸️ Git commit自动触发DB重建
- ⏸️ 闭环测试通过
- ⏸️ 冲突解决正确

---

### Phase 4: 闭环验证 + KG查询（1-2周）

**目标**: 验证双向闭环稳定性，实现KG查询服务。

**核心任务**:

#### 4.1 双向一致性校验

**位置**: `llamaindex_runtime/okf/consistency_checker.py`

**功能**:
- OKF文件 vs okf_sync_state版本哈希
- DB记录数 vs okf_sync_state.db_record_count
- 定期全量校验（Cron）
- 不一致自动触发重建

**待完成**:
- ⏸️ 编写consistency_checker.py
- ⏸️ 定期校验任务

#### 4.2 KG Query Service

**位置**: `llamaindex_runtime/tree/kg_query.py`

**功能**:
- Entity-centric SQL多跳查询
- Entity → Chunks（1-hop）
- Entity → 共现实体 → Chunks（2-hop）
- 返回QueryHit含okf_file_path溯源

**关键方法**:
```python
class KGQueryService:
    def entity_multihop_query(self, entity_id: str, hops: int) -> List[QueryHit]:
        """Entity多跳查询，返回含OKF溯源的QueryHit"""

    def entity_to_chunks(self, entity_id: str) -> List[ChunkID]
    def co_occurrence_query(self, entity_id: str) -> List[Entity]
```

**待完成**:
- ⏸️ 编写kg_query.py

#### 4.3 OKF溯源集成

**位置**: `llamaindex_runtime/tree/runtime.py`

**改动**:
- QueryHit增加`okf_file_path`, `okf_paragraph_id`
- 检索结果溯源到OKF原文
- 用户可在Obsidian直接查看原文

**待完成**:
- ⏸️ 扩展QueryHit结构
- ⏸️ 溯源逻辑

#### 4.4 闭环监控

**功能**:
- 摄入成功率（方向1）
- 回写成功率（方向2）
- 闭环延迟（commit→重建→检索→回写→commit）
- 一致性监控
- Agent发现质量监控

**待完成**:
- ⏸️ monitoring_dashboard.py
- ⏸️ 告警机制

#### 4.5 生产试点

**流程**:
- 创建真实OKF bundle
- 运行7天闭环稳定验收
- 性能基准测试
- 用户验收

**待完成**:
- ⏸️ 真实bundle测试
- ⏸️ Phase4-VERIFICATION.md

**Phase 4 交付物**:
- ⏸️ consistency_checker.py
- ⏸️ kg_query.py
- ⏸️ runtime.py溯源扩展
- ⏸️ monitoring_dashboard.py
- ⏸️ Phase4-VERIFICATION.md

**Phase 4 验收**:
- ⏸️ 双向一致性≥99%
- ⏸️ 闭环延迟P95≤30秒
- ⏸️ Entity多跳Recall提升
- ⏸️ 生产稳定运行7天

---

## v1.0 vs v2.0 对比

| 维度 | v1.0 | v2.0 |
|------|------|------|
| **数据流** | 单向 OKF→DB | 双向 OKF⟷DB |
| **OKF地位** | 输入格式 | 权威源（SSOT） |
| **DB地位** | 存储 | 派生缓存（可重建） |
| **Agent角色** | 无 | 回写桥梁 |
| **闭环** | 无 | 完整闭环 |
| **知识自增厚** | 否 | 是 |
| **重建能力** | 无 | 全量重建脚本 |
| **冲突处理** | 无 | 人类优先 + Agent暂存 |
| **Phase 3** | Git同步（单向） | **回写管道（双向核心）** |

---

## 风险与回退路径

### Risk 1: Agent回写质量不稳定

**风险**: Agent发现的关系质量低、噪声大
**缓解**:
- Phase 3先人工review Agent的commit
- 逐步过渡到自动commit
- Agent标记`confidence`字段，低置信度待review
**回退**: 关闭自动回写，Agent仅生成proposal供人工确认

### Risk 2: 双向同步死循环

**风险**: Agent回写 → DB重建 → 检索 → 又回写 → 死循环
**缓解**:
- 回写触发条件设置阈值（仅新关系，不重复发现）
- 记录已发现关系，去重
- 单次查询最多触发1次回写
**回退**: 回写改为手动触发

### Risk 3: 冲突解决失败

**风险**: 人类与Agent同时编辑导致冲突
**缓解**:
- Agent写入`staging/`目录，不直接覆盖
- 人类review后merge
- Git merge机制兜底
**回退**: Agent仅追加内容，不修改现有字段

### Risk 4: DB重建性能

**风险**: 全量重建耗时长
**缓解**:
- 增量摄入为主（Phase 2）
- 全量重建仅用于一致性修复
- 重建时保持旧DB可读（蓝绿部署）
**回退**: 仅增量同步，不做全量重建

### Risk 5: OKF文件爆炸

**风险**: Agent回写导致OKF文件数量爆炸
**缓解**:
- 关系按entity聚合（一个entity文件含多关系）
- 定期归档低频关系
- 设置文件数量上限
**回退**: 关系存DB，不回写OKF

---

## 关键决策点

### Decision Gate 1: Phase 1验收

**验收标准**:
- ⏸️ DB可从OKF全量重建
- ⏸️ 重建一致性100%
- ⏸️ Obsidian能打开bundle

**失败回退**: 保持DB-centric，OKF仅作导出格式（退回v1.0）

### Decision Gate 2: Phase 2验收

**验收标准**:
- ⏸️ Git commit → DB自动同步
- ⏸️ 实体归一准确率≥85%

**失败回退**: 手动触发同步

### Decision Gate 3: Phase 3验收 ⭐ 关键

**验收标准**:
- ⏸️ Agent能发现新关系并回写OKF
- ⏸️ 回写不破坏人类编辑
- ⏸️ 闭环测试通过

**失败回退**:
- 关闭自动回写，改为人工触发
- Agent仅生成proposal，人类确认后写入
- 严重情况退回单向架构（v1.0）

### Decision Gate 4: Phase 4验收

**验收标准**:
- ⏸️ 双向一致性≥99%
- ⏸️ 闭环延迟可接受
- ⏸️ 生产稳定运行7天

---

## 实施优先级建议

**必须实现（核心闭环）**:
1. Phase 1: 全量重建脚本（DB为缓存的保证）
2. Phase 2: 摄入管道 + Git hook
3. Phase 3: OKF Writer + Agent Committer（回写核心）

**可延后（增强功能）**:
- KG查询服务（Phase 4.2）
- 监控仪表盘（Phase 4.4）
- Concept聚类回写（Phase 3.4）

**建议**: Phase 1-3是闭环的最小可行实现，优先完成。Phase 4可迭代增强。

---

## 总结

**v2.0核心改进**:
- ✅ **双向闭环**: OKF⟷DB，Agent回写桥梁
- ✅ **OKF为权威源**: DB可重建，不是存储
- ✅ **知识自增厚**: Agent发现新关系回写OKF
- ✅ **冲突解决**: 人类优先，Agent暂存
- ✅ **完整闭环测试**: 验证全流程

**关键Phase**: Phase 3（回写管道）是v2.0相比v1.0的核心创新，实现双向闭环。

**已完成工作**（可复用）:
- ✓ okf_bundle/目录结构
- ✓ entities/e001示例文件
- ✓ llamaindex_runtime/okf/parser.py
- ✓ llamaindex_runtime/okf/__init__.py

**下一步**: 等待您审批v2.0计划，确认后启动Phase 1（全量重建脚本 + DB schema）。

---

**文档版本**: v2.0
**创建日期**: 2026-07-02
**核心修正**: 单向→双向，DB为中心→OKF为权威源
**作者**: Claude Code
