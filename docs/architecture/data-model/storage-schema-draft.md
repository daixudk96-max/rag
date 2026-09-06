# 三库对齐实施版表结构草案

生成时间：2026-05-09  
用途：给当前 KG + Vec + Tree 架构做**真正可落地**的表结构与主键设计草案。  
范围：
- PostgreSQL registry / mapping / provenance 层
- Neo4j 图层建模草案
- 向量库（Milvus / Qdrant）metadata schema 草案

---

## 一、设计目标

这份草案不是为了“把所有数据都塞进一个库”，而是为了实现四个目标：

1. **统一身份层**：`doc_id / version_id / span_id / node_id / chunk_id / entity_id / relation_id`
2. **统一版本层**：任何重切片、重 embedding、重抽图谱都按版本化处理
3. **统一证据层**：图谱证据、树节点、向量 chunk 都能回到原文跨度
4. **统一更新层**：幂等写入、回滚、激活新版本、回收旧版本

---

## 二、总体原则

### 1. 统一的东西
统一：
- `doc_id`
- `version_id`
- `span_id`
- 版本切换流程
- provenance / evidence link

### 2. 不统一的东西
不强行统一：
- 向量 chunk 的切法
- 树节点的切法
- 图谱证据跨度

### 3. 推荐模式

> **一个 canonical span 标准 + 多个 derived views（派生视图）**

也就是：
- `canonical_spans` 是底层稳定坐标
- `vector_chunks` 是检索视图
- `tree_nodes` 是结构视图
- `evidence_links` 是图谱证据视图

### 4. 外部术语对齐

根据最新外部参照，这套架构更适合对外描述为：
- **provenance-centric multi-view RAG index**
- **versioned provenance mapping layer for hybrid / agentic RAG**

这比单纯说“chunking strategy”更准确，因为它强调的是：
- provenance / evidence
- multi-view indexing
- hierarchical retrieval
- versioned mapping

---

## 三、PostgreSQL：推荐作为系统事实层（source of truth）

## 3.1 documents

```sql
CREATE TABLE documents (
    doc_id              UUID PRIMARY KEY,
    source_uri          TEXT,
    source_type         TEXT,
    title               TEXT,
    doc_type            TEXT,
    language_code       TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at          TIMESTAMPTZ
);
```

### 说明
- 一篇文档只有一个 `doc_id`
- 不直接在这里放切片信息
- `deleted_at` 用于软删除

---

## 3.2 document_versions

```sql
CREATE TABLE document_versions (
    version_id          UUID PRIMARY KEY,
    doc_id              UUID NOT NULL REFERENCES documents(doc_id),
    content_hash        TEXT NOT NULL,
    version_no          INTEGER NOT NULL,
    ingestion_strategy  TEXT,
    parsing_strategy    TEXT,
    chunking_profile    TEXT,
    graph_extraction_profile TEXT,
    normalization_contract_id UUID,
    is_active           BOOLEAN NOT NULL DEFAULT FALSE,
    status              TEXT NOT NULL DEFAULT 'staging',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    activated_at        TIMESTAMPTZ,
    retired_at          TIMESTAMPTZ,
    UNIQUE (doc_id, version_no),
    UNIQUE (doc_id, content_hash)
);

CREATE INDEX idx_document_versions_doc_id ON document_versions(doc_id);
CREATE INDEX idx_document_versions_active ON document_versions(doc_id, is_active);
```

### 说明
- `content_hash` 用来做幂等去重
- `chunking_profile` 记录这一版切片配置
- `normalization_contract_id` 记录这一版 offsets / headings / clean text 的生成契约
- **重切片 = 新 version_id，不覆盖老版本**

---

## 3.2A normalization_contracts

```sql
CREATE TABLE normalization_contracts (
    normalization_contract_id  UUID PRIMARY KEY,
    parser_name                TEXT NOT NULL,
    parser_version             TEXT,
    ocr_profile                TEXT,
    text_cleaning_profile      TEXT,
    heading_normalization_profile TEXT,
    offset_basis               TEXT NOT NULL,
    notes                      TEXT,
    created_at                 TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 说明
- 这是保证 `span_id` 真正稳定的关键表
- `offset_basis` 必须明确，例如：`normalized_char_offset` / `raw_char_offset` / `token_offset`
- 如果 contract 改了，即便原文没变，也应该允许生成新 `version_id`

---

## 3.3 canonical_spans

```sql
CREATE TABLE canonical_spans (
    span_id             UUID PRIMARY KEY,
    version_id          UUID NOT NULL REFERENCES document_versions(version_id),
    span_kind           TEXT NOT NULL,
    start_offset        INTEGER NOT NULL,
    end_offset          INTEGER NOT NULL,
    page_no             INTEGER,
    heading_path        TEXT,
    raw_text            TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (end_offset > start_offset)
);

CREATE INDEX idx_canonical_spans_version_id ON canonical_spans(version_id);
CREATE INDEX idx_canonical_spans_page_no ON canonical_spans(version_id, page_no);
CREATE INDEX idx_canonical_spans_offset_range ON canonical_spans(version_id, start_offset, end_offset);
```

### 说明
- `span_kind` 可以是：`paragraph` / `sentence_window` / `table_cell` / `figure_caption` / `graph_evidence`
- 这是底层稳定坐标，不是最终给向量检索直接用的 chunk
- 同一 version 内，所有上层视图都回到它

---

## 3.4 tree_nodes

```sql
CREATE TABLE tree_nodes (
    node_id             UUID PRIMARY KEY,
    version_id          UUID NOT NULL REFERENCES document_versions(version_id),
    parent_node_id      UUID REFERENCES tree_nodes(node_id),
    node_type           TEXT NOT NULL,
    level_no            INTEGER NOT NULL,
    title               TEXT,
    heading_path        TEXT,
    page_start          INTEGER,
    page_end            INTEGER,
    summary_text        TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_tree_nodes_version_id ON tree_nodes(version_id);
CREATE INDEX idx_tree_nodes_parent ON tree_nodes(parent_node_id);
CREATE INDEX idx_tree_nodes_level ON tree_nodes(version_id, level_no);
```

### 说明
- `node_type` 例如：`root` / `chapter` / `section` / `paragraph_group` / `summary_anchor`
- 树层不一定与向量 chunk 一一对应

---

## 3.5 tree_node_spans

```sql
CREATE TABLE tree_node_spans (
    node_id             UUID NOT NULL REFERENCES tree_nodes(node_id),
    span_id             UUID NOT NULL REFERENCES canonical_spans(span_id),
    ordinal_no          INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (node_id, span_id)
);

CREATE INDEX idx_tree_node_spans_span ON tree_node_spans(span_id);
```

### 说明
- 一个树节点可能覆盖多个 span
- 一个 span 也可能被多个上层摘要节点复用

---

## 3.6 vector_chunks

```sql
CREATE TABLE vector_chunks (
    chunk_id            UUID PRIMARY KEY,
    version_id          UUID NOT NULL REFERENCES document_versions(version_id),
    node_id             UUID REFERENCES tree_nodes(node_id),
    chunk_type          TEXT NOT NULL,
    chunk_order         INTEGER,
    token_count         INTEGER,
    text_preview        TEXT,
    page_no             INTEGER,
    heading_path        TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_vector_chunks_version_id ON vector_chunks(version_id);
CREATE INDEX idx_vector_chunks_node_id ON vector_chunks(node_id);
```

### 说明
- `chunk_type` 可用于标记：`semantic_leaf` / `window_chunk` / `late_chunked_leaf`
- `text_preview` 只做调试，不是权威文本来源

---

## 3.7 vector_chunk_spans

```sql
CREATE TABLE vector_chunk_spans (
    chunk_id            UUID NOT NULL REFERENCES vector_chunks(chunk_id),
    span_id             UUID NOT NULL REFERENCES canonical_spans(span_id),
    ordinal_no          INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (chunk_id, span_id)
);

CREATE INDEX idx_vector_chunk_spans_span ON vector_chunk_spans(span_id);
```

### 说明
- 一个 chunk 可以覆盖多个 span
- 这是 Vec → Span 的回映入口

---

## 3.8 entities

```sql
CREATE TABLE entities (
    entity_id           UUID PRIMARY KEY,
    entity_key          TEXT NOT NULL,
    entity_type         TEXT,
    canonical_name      TEXT,
    normalized_value    TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (entity_key)
);
```

### 说明
- `entity_key` 应尽量稳定，比如：`company:abc_bank`、`concept:risk_exposure`
- 不要让 chunk_id 参与实体主身份
- `entity_id` 稳定依赖单独的 canonicalization / resolution 策略，而不是只靠 span

---

## 3.8A entity_aliases

```sql
CREATE TABLE entity_aliases (
    entity_alias_id     UUID PRIMARY KEY,
    entity_id           UUID NOT NULL REFERENCES entities(entity_id),
    alias_text          TEXT NOT NULL,
    alias_norm          TEXT NOT NULL,
    alias_type          TEXT,
    source_version_id   UUID REFERENCES document_versions(version_id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (entity_id, alias_norm)
);

CREATE INDEX idx_entity_aliases_norm ON entity_aliases(alias_norm);
```

### 说明
- 用来承载 mention normalization / alias normalization
- 这是跨版本保持 `entity_id` 稳定的关键补充层

---

## 3.8B entity_mentions

```sql
CREATE TABLE entity_mentions (
    mention_id          UUID PRIMARY KEY,
    version_id          UUID NOT NULL REFERENCES document_versions(version_id),
    span_id             UUID NOT NULL REFERENCES canonical_spans(span_id),
    entity_id           UUID NOT NULL REFERENCES entities(entity_id),
    mention_text        TEXT NOT NULL,
    confidence_score    DOUBLE PRECISION,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_entity_mentions_entity ON entity_mentions(entity_id);
CREATE INDEX idx_entity_mentions_span ON entity_mentions(span_id);
```

### 说明
- `mention` 与 `entity` 明确分层，不要让 evidence mention 直接等于 entity 本体
- 这样图谱重抽取、别名变化、chunk 变化时，仍能维持稳定实体身份

---

## 3.9 relations

```sql
CREATE TABLE relations (
    relation_id         UUID PRIMARY KEY,
    relation_key        TEXT NOT NULL,
    relation_type       TEXT NOT NULL,
    source_entity_id    UUID NOT NULL REFERENCES entities(entity_id),
    target_entity_id    UUID NOT NULL REFERENCES entities(entity_id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (relation_key)
);
```

### 说明
- `relation_key` 建议由 `(source_entity_key, relation_type, target_entity_key)` 稳定派生

---

## 3.10 evidence_links

```sql
CREATE TABLE evidence_links (
    evidence_link_id    UUID PRIMARY KEY,
    version_id          UUID NOT NULL REFERENCES document_versions(version_id),
    entity_id           UUID REFERENCES entities(entity_id),
    relation_id         UUID REFERENCES relations(relation_id),
    span_id             UUID NOT NULL REFERENCES canonical_spans(span_id),
    source_kind         TEXT NOT NULL,
    confidence_score    DOUBLE PRECISION,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((entity_id IS NOT NULL) OR (relation_id IS NOT NULL))
);

CREATE INDEX idx_evidence_links_entity ON evidence_links(entity_id);
CREATE INDEX idx_evidence_links_relation ON evidence_links(relation_id);
CREATE INDEX idx_evidence_links_span ON evidence_links(span_id);
CREATE INDEX idx_evidence_links_version ON evidence_links(version_id);
```

### 说明
- 图谱证据与向量 chunk / 树节点分离，**不要强行让图证据贴合 chunk 边界**
- `source_kind` 可标明：`graph_extraction` / `manual_label` / `llm_extractor`

---

## 3.11 chunk_entity_links（可选但强烈推荐）

```sql
CREATE TABLE chunk_entity_links (
    chunk_id            UUID NOT NULL REFERENCES vector_chunks(chunk_id),
    entity_id           UUID NOT NULL REFERENCES entities(entity_id),
    version_id          UUID NOT NULL REFERENCES document_versions(version_id),
    link_role           TEXT,
    PRIMARY KEY (chunk_id, entity_id, version_id)
);

CREATE INDEX idx_chunk_entity_links_entity ON chunk_entity_links(entity_id);
```

### 说明
- 这是 KG → Vec 约束检索最直接的桥表

---

## 3.12 node_entity_links（可选）

```sql
CREATE TABLE node_entity_links (
    node_id             UUID NOT NULL REFERENCES tree_nodes(node_id),
    entity_id           UUID NOT NULL REFERENCES entities(entity_id),
    version_id          UUID NOT NULL REFERENCES document_versions(version_id),
    PRIMARY KEY (node_id, entity_id, version_id)
);
```

### 说明
- 这是 KG → Tree / Tree → KG 的桥表

---

## 四、Neo4j 图层建模草案

### 推荐图模型

#### 节点标签
- `:Entity { entity_id, entity_key, entity_type, canonical_name }`
- `:Document { doc_id, title }`
- `:Version { version_id, content_hash, version_no }`
- `:TreeNode { node_id, level_no, heading_path, page_start, page_end }`（可选）
- `:Chunk { chunk_id, page_no, heading_path }`（可选，仅做回链，不做主事实源）

#### 关系类型
- `(:Entity)-[:RELATION { relation_id, relation_type }]->(:Entity)`
- `(:Entity)-[:SUPPORTED_BY { version_id, span_id, confidence_score }]->(:Version)`
- `(:Version)-[:HAS_CHUNK]->(:Chunk)`（可选）
- `(:TreeNode)-[:HAS_CHILD]->(:TreeNode)`（如你想把树也部分投影到 Neo4j）

### 推荐原则
- 图层主身份：`entity_id / relation_id`
- 证据链接：优先指向 `version_id + span_id`
- `Chunk` / `TreeNode` 可进图，但**不要让图成为 chunk / tree 的主存储层**

### 约束建议
- `Entity(entity_id)` 唯一
- `Document(doc_id)` 唯一
- `Version(version_id)` 唯一
- `Chunk(chunk_id)` 唯一（如果你投影 chunk）
- `TreeNode(node_id)` 唯一（如果你投影 tree）

---

## 五、Milvus / Qdrant metadata schema 草案

## 5.1 向量记录的统一 metadata 字段

建议无论用 Milvus 还是 Qdrant，都统一带这些 metadata：

```json
{
  "doc_id": "...",
  "version_id": "...",
  "chunk_id": "...",
  "node_id": "...",
  "parent_id": "...",
  "heading_path": "...",
  "page_no": 12,
  "entity_ids": ["...", "..."],
  "chunk_type": "semantic_leaf",
  "token_count": 428,
  "content_hash": "..."
}
```

### 推荐索引优先级
优先做 filter/index 的字段：
1. `version_id`
2. `doc_id`
3. `chunk_id`
4. `node_id`
5. `entity_ids`
6. `page_no`

### 为什么
因为最常见约束查询是：
- “只查 active version”
- “只查某篇文档”
- “只查这些 entity 对应的 chunk”
- “命中后回映某个 tree node”

---

## 5.2 Milvus 使用建议

### 推荐 schema
- 向量字段：embedding
- 标量字段：`doc_id`, `version_id`, `chunk_id`, `node_id`, `page_no`
- JSON / ARRAY 字段：`entity_ids`, `heading_path`（也可以拆成 text 标量）

### 推荐更新策略
- 新版本新 collection / 新分区
- alias 切换
- 旧版 delete

### 不推荐
- 一代和二代 chunk 混在同一 active collection
- 没有 `version_id` 的 upsert

---

## 5.3 Qdrant 使用建议

### 推荐 payload
- 全部 metadata 进 payload
- 给 `version_id`, `doc_id`, `chunk_id`, `node_id`, `page_no` 做 payload index

### 推荐更新策略
- 新 collection 写入
- alias switch
- 旧 collection 回收

### 判断
如果你偏 metadata-heavy、过滤复杂、开发灵活：**Qdrant 更舒服**。  
如果你偏高规模 ANN 性能：**Milvus 更强**。

---

## 六、推荐的更新顺序（实施版）

## 6.1 文档新版本写入顺序

```text
1. 写 documents
2. 写 document_versions（staging）
3. 生成 canonical_spans
4. 生成 tree_nodes + tree_node_spans
5. 生成 vector_chunks + vector_chunk_spans
6. 写 vector DB
7. 跑图谱抽取
8. 写 entities / relations / evidence_links
9. 写 chunk_entity_links / node_entity_links
10. 一致性校验
11. version 激活 + alias 切换
12. 清理旧版本
```

---

## 6.2 为什么这样做

因为一旦重切片：
- `chunk_id` 会变
- 向量 embedding 会变
- 图谱证据回链可能会变
- tree node 覆盖范围可能会变

所以必须把这一切放在一个新版本里，而不是原地更新。

---

## 七、切片标准到底要不要统一？

## 结论：不要统一 chunk，统一 span

### 推荐模式

#### canonical span（统一）
- 作用：稳定证据坐标
- 粒度：句子窗 / 段落窗 / 最小证据片段

#### vector chunk（派生）
- 作用：embedding / ANN 检索
- 标准：语义友好，可 overlap

#### tree node（派生）
- 作用：层级结构 / 父块回并
- 标准：结构友好（章/节/段/摘要）

#### graph evidence span（派生）
- 作用：实体关系证据
- 标准：证据友好，不强行贴合 vector chunk

### 一句话判断

> 向量层、树层、图层可以用**不同切法**，但必须共享同一个 `span_id` 坐标系。

---

## 八、最容易出错的地方

### 1. 用 chunk_id 当全局主身份
最危险，会导致重切片后全链路断裂。

### 2. 没有 version_id 就直接重写
更新会越来越脏，旧证据无法回收。

### 3. 图证据强行贴 chunk 边界
会损伤图谱抽取质量。

### 4. 没有 registry
三库各写各的，后面无法稳定对齐。

### 5. 直接删除旧版再切换
切换失败就无法回滚。

---

## 九、最终推荐（实施级）

### 最推荐架构

- **PostgreSQL**：source of truth
  - 身份层
  - 版本层
  - provenance 层
  - chunk/tree/entity 映射层

- **Neo4j**：graph projection
  - 实体 / 关系 / 图遍历 / 图算法

- **Milvus 或 Qdrant**：vector retrieval
  - embedding 检索
  - metadata 过滤

- **Tree/docstore**：hierarchy projection
  - parent-child
  - hit rollup

### 最终原则

> **不要统一 chunk，要统一 span。**  
> **不要统一三层结构，要统一三层主键和版本。**

---

## 十、相关文件

可直接打开的图：
- `E:\github\rag\storage-alignment-key-diagram.html`

相关结论文档：
- `E:\github\rag\storage-alignment-and-update-strategy.md`
- `E:\github\rag\complete-implementation-roadmap.md`
- `E:\github\rag\storage-schema-draft.md`