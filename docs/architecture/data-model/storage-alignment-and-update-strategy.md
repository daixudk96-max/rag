# 三层存储对齐与更新策略结论

生成时间：2026-05-08  
范围：KG（Neo4j / PostgreSQL+AGE）、Vec（Milvus / Qdrant）、Tree / Registry（PostgreSQL / docstore）

---

## 一、执行摘要

这次调研的结论非常明确：

1. **三类数据库都能存你要的数据**，但职责不同：
   - **Neo4j** 最适合图结构、实体关系、证据回链
   - **Milvus / Qdrant** 最适合向量和 metadata 检索
   - **PostgreSQL** 最适合做统一身份层、版本层、映射层、幂等更新层

2. **真正要统一的不是 chunk 标准，而是身份与版本坐标**。  
   推荐统一：`doc_id / version_id / span_id`。  
   不推荐统一：向量 chunk、树节点、图谱证据跨度。

3. **最稳的更新方式是版本化写入，不是原地覆盖**。  
   推荐流程：新版本写入 → 校验 → 切 active version / alias → 回收旧版本。

4. **不要让 chunk_id 成为全局主身份**。  
   一旦重切片，chunk_id 很容易全部失效，图谱证据、树回映、缓存都会跟着断。

5. **推荐架构是：一个 canonical span 标准 + 多个派生视图**。  
   也就是：
   - 向量层按 embedding 友好切
   - 树层按结构友好切
   - 图层按证据友好切
   - 三者通过 registry 的 `span_id` 稳定对齐

6. **从外部术语看，这更接近 `provenance-centric multi-view RAG`，而不是单一 chunking 策略。**  
   公开资料里最接近的表达是：
   - `versioned provenance mapping layer for multi-view RAG`
   - `provenance-centric multi-view RAG index`
   - `evidence-centric retrieval`
   - `hierarchical document indexing / Parent-Child / Small2Big`

7. **要让 `span_id` 真正稳定，必须补一层 normalization contract；要让 `entity_id` 真正稳定，必须补一层 entity canonicalization。**  
   也就是说：
   - `span_id` 不能只靠表结构，还依赖固定的 OCR / 清洗 / 偏移规则
   - `entity_id` 不能只靠 chunk/span 推出来，还要有别名、规范名、归一化规则

---

## 二、外部参照与推荐命名

### 最接近的外部术语

根据最新外部检索结果，这套设计**没有单一标准行业名**，但与下面几类模式高度同构：

- **provenance / provenance-aware**：强调 `wasDerivedFrom`、`wasRevisionOf`、`specializationOf`
- **multi-view indexing**：同一源内容派生多个检索视图
- **hierarchical document indexing / Parent-Child / Small2Big**：不同粒度视图并存
- **evidence-centric retrieval / evidence carrier**：把可回溯证据对象，而不是 chunk 本身，作为稳定引用对象

### 对外推荐命名

如果需要在文档、架构图、评审材料里对外描述，我建议用这两个说法：

1. **provenance-centric multi-view RAG index**
2. **versioned provenance mapping layer for hybrid / agentic RAG**

### 为什么不继续强调“统一 chunk”

因为外部参照里，成熟系统更常见的做法是：
- GraphRAG / LightRAG：图层和检索层做派生对齐
- LlamaIndex / Haystack / LangChain：leaf 检索视图与 parent 文档视图分离
- CogitoRAG / EvidenceNet：evidence / passage 才是稳定证据对象

所以更准确的表述是：

> 这首先是**数据谱系与证据建模问题**，其次才是 chunking 问题。

---

## 三、三个存储层分别能不能存这些字段？

目标字段：
- `doc_id`
- `version_id` / `content_hash`
- `node_id`
- `parent_id`
- `chunk_id`
- `entity_id`
- `relation_id`
- `heading_path`
- `page_no`
- `source_chunk_ids[]`
- `source_node_ids[]`
- `entity_ids[]`

### 1. Neo4j：支持，且适合图层

**事实**：
- 支持节点属性与关系属性
- 支持 list 属性
- 支持约束与唯一键
- 支持 `MERGE`
- 新版支持 vector property / vector index

**结论**：
上述字段都能放，但更推荐这样使用：
- `entity_id` / `relation_id` 作为图层主身份
- `doc_id` / `version_id` 作为图层 provenance
- `source_chunk_ids[]` / `source_node_ids[]` 作为证据回链字段
- `parent_id` 能存，但若是层级关系，**更推荐用真正的边**

**推荐定位**：
- Neo4j 做 **图投影视图**
- 不建议 Neo4j 做系统事实源（source of truth）

---

### 2. PostgreSQL + Apache AGE：支持，但最优解是 Postgres 主、AGE 辅

**事实**：
- PostgreSQL 支持事务、foreign key、`jsonb`、`INSERT ... ON CONFLICT`
- Apache AGE 支持 vertex/edge + `agtype` 属性（map/list）

**结论**：
- PostgreSQL 本体非常适合做：
  - 文档表
  - 版本表
  - canonical span 表
  - tree node 表
  - mapping / provenance 表
- AGE 可以承担图查询，但更推荐作为 Postgres 之上的图视图，而不是承担全部版本与幂等控制

**推荐定位**：
- **PostgreSQL = 系统事实层**
- **AGE = 图补充层（可选）**

---

### 3. Milvus：支持，适合大规模高性能向量检索

**事实**：
- 支持 scalar fields、JSON、ARRAY
- 支持 metadata filtering
- 支持 upsert / delete
- 支持 alias

**可放字段**：
- `doc_id`
- `version_id`
- `chunk_id`
- `node_id`
- `parent_id`
- `heading_path`
- `page_no`
- `entity_ids[]`

**限制与注意**：
- metadata-heavy 方案可做，但 schema 要提前设计好
- 复杂过滤性能需要谨慎（官方明确区分 standard filtering 与 iterative filtering）

**推荐定位**：
- 高规模向量层
- 如果 metadata 查询很重，需更仔细做 schema 和过滤设计

---

### 4. Qdrant：支持，metadata-heavy 体验更友好

**事实**：
- 每个 point 都支持 JSON payload
- 支持 nested object、array
- 支持 payload index
- 支持 alias switch
- 支持 delete by filter

**可放字段**：
同 Milvus，一样都能放。

**推荐定位**：
- 如果你 metadata 过滤非常重、开发阶段希望灵活性高
- Qdrant 的开发体验通常优于 Milvus

---

## 三、更新应该怎么做？

### 核心原则：版本化写入，不要原地覆盖

推荐模式：

```text
新版本写入 → 校验成功 → 切 active version / alias → 回收旧版本
```

### 推荐写入顺序

1. 写 `documents`
2. 写 `document_versions`
3. 生成 `canonical_spans`
4. 派生 `tree_nodes`
5. 派生 `vector_chunks`
6. 写向量库
7. 运行图谱抽取
8. 写实体与关系
9. 写 `evidence_links`
10. 校验端到端一致性
11. 切换 active version / alias
12. 清理旧版本

### 为什么要这样做？

因为一旦你：
- 重新切片
- 重新 embedding
- 重新抽实体关系

旧的这些引用就可能全部失效：
- `source_chunk_ids`
- `source_node_ids`
- 向量命中回映
- 父子树关系
- 缓存

所以不能边改边查，更不能直接覆盖老数据。

---

## 四、三层各自怎么更新？

### 1. 图层（Neo4j）

**推荐策略**：
- `entity_id` / `relation_id` 尽量稳定
- 证据链接（evidence edges）按 `version_id` 版本化
- 新版图谱写入后，再移除旧版 evidence

**推荐做法**：
- 实体本体：idempotent upsert
- 证据边：按版本新增
- 旧证据：切换成功后按版本清理

**不要做**：
- 不要让 `chunk_id` 成为图层主身份
- 不要在一堆可变字段上做 `MERGE`

---

### 2. 向量层（Milvus / Qdrant）

**推荐策略**：
- 每次重切片 / 重 embedding 都视为新版本
- 先写新 collection / 新分区 / 新版本 payload
- 校验后做 alias switch
- 再删除旧版本

**Milvus 推荐**：
- collection rotation + alias

**Qdrant 推荐**：
- collection rotation + alias switch（更自然）

**不要做**：
- 不要把两代 chunk 混在同一个 active collection 里
- 不要没有 `version_id` 就做 upsert

---

### 3. Tree / Registry 层（PostgreSQL）

**推荐策略**：
- PostgreSQL registry 作为 source of truth
- 所有 `doc_id/version_id/span_id/node_id/chunk_id` 的关系都先写这里
- 三层数据（Graph / Vec / Tree）都以这里为准

**这层负责**：
- 主键分配
- 幂等更新
- 版本切换
- provenance
- 删除回收

---

## 五、三层切片标准必须一致吗？

## 结论：不必须，而且不建议强行一致

### 为什么不能强行一致？

#### 向量层需要的是 embedding-friendly chunks
适合：
- 300~800 token
- 语义连贯
- 可带 overlap

#### 树层需要的是 structure-friendly nodes
适合：
- 章 / 节 / 段 / 摘要层
- parent-child 稳定
- 便于命中回并

#### 图谱层需要的是 evidence-friendly spans
适合：
- 一句
- 两句
- 一个实体窗口
- 一个关系证据窗口

**结论**：
图谱证据跨度通常比向量 chunk 更小，也经常与树节点边界不一致。  
这是正常现象，不应该强行抹平。

#### entity_id 的稳定性是另一套问题
即使 `span_id` 稳定了，`entity_id` 也不一定自动稳定。因为：
- 同一实体可能有多个 mention
- 不同版本里 mention 位置会变化
- 图谱重抽取后，实体聚合边界也可能变化

所以建议把实体稳定性拆成单独一层：
- `entity_key`：稳定业务键 / 规范键
- `canonical_name`：规范名
- `alias / mention normalization`：别名和表述归一化
- `mention -> entity`：用关系对齐，而不是让 mention 本身就是 entity_id

---

## 六、如果切片逻辑不一致，怎么对齐？

## 推荐：用 canonical span 作为统一坐标系

### 什么是 canonical span？

它不是向量 chunk，也不是树节点，也不是图实体。  
它是：

> **文档版本内最小稳定证据坐标**

例如：
- `doc_id = D1`
- `version_id = V3`
- `span_id = S102`
- `start_offset = 12840`
- `end_offset = 13120`

然后：
- 向量 chunk 覆盖哪些 `span_id`
- 树节点覆盖哪些 `span_id`
- 图谱实体/关系证据落在哪些 `span_id`

都可以稳定对齐。

---

## 七、推荐的数据模型

### 0. 先有 normalization contract，再谈稳定 span

为了保证 `span_id = (version_id, start_offset, end_offset)` 真正可长期使用，必须先冻结一份 **normalization contract**。最少要明确：

- OCR / parser 的版本
- 文本清洗规则（空白、换行、全半角、特殊字符）
- heading/path 归一化规则
- page_no 的生成规则
- offset 以什么为准（原文字符、规范化后字符、token offset）

如果这份 contract 改了，就应该视为新的解析基线；即便原始文档没变，也要允许生成新的 `version_id`。

### 1. `documents`
- `doc_id`
- `source_uri`
- `title`
- `doc_type`

### 2. `document_versions`
- `version_id`
- `doc_id`
- `content_hash`
- `created_at`
- `active_flag`

### 3. `canonical_spans`
- `span_id`
- `version_id`
- `start_offset`
- `end_offset`
- `page_no`

### 4. `tree_nodes`
- `node_id`
- `version_id`
- `parent_node_id`
- `span_id` 或 `span_start/span_end`
- `heading_path`
- `node_type`

### 5. `vector_chunks`
- `chunk_id`
- `version_id`
- `node_id`
- `span_ids[]`
- `embedding_payload_ref`

### 6. `entities`
- `entity_id`
- `entity_key`
- `entity_type`

### 7. `relations`
- `relation_id`
- `source_entity_id`
- `target_entity_id`
- `relation_type`

### 8. `evidence_links`
- `entity_id` 或 `relation_id`
- `span_id`
- `version_id`
- `evidence_role`

---

## 八、到底用一个标准切，还是多个标准切？

## 最终建议：一个 canonical 标准 + 多个派生标准

### 不推荐
- 三层完全统一一个 chunk 标准  
  → 太僵硬，检索质量差

### 也不推荐
- 三层完全各切各的、没有统一坐标  
  → 后期对齐与更新会很痛苦

### 推荐
- **统一底层证据坐标（canonical span）**
- **上层按用途派生不同切片视图**

#### 向量层
- 按 embedding 友好切
- 可语义切分
- 可 overlap

#### 树层
- 按结构友好切
- 章/节/段/摘要层

#### 图谱层
- 按证据友好切
- 不强行贴合向量 chunk

---

## 九、最容易出错的点

### 1. 把 `chunk_id` 当全局主身份
后果：
- 一旦重切片，chunk_id 全变
- 图谱证据断
- 树回映断
- 缓存断

### 2. 没有 `version_id`
后果：
- 无法判断哪些实体属于旧版
- 无法清理旧 chunk / 旧 node / 旧 evidence
- 更新会越来越脏

### 3. 想让三层共用同一种切法
后果：
- 向量召回质量下降
- 图谱抽取证据不准确
- 树结构稳定性变差

### 4. 没有一个薄 registry
后果：
- 三库相互引用失控
- 无法做幂等更新
- 很难做端到端校验

---

## 十、最终工程建议

### 最推荐方案

**三层存储 + 一个薄 registry**

- **PostgreSQL registry**
  - 身份层
  - 版本层
  - provenance 层
  - mapping 层

- **Neo4j**
  - 实体 / 关系 / 图遍历 / 图算法

- **Milvus / Qdrant**
  - 向量召回

- **Tree / docstore**
  - 树结构与命中回并关系

### 一句话总结

> **不要统一 chunk，要统一 span。**  
> **不要统一三层结构，要统一三层主键和版本。**

---

## 十一、推荐落地顺序

### 先做
1. 定义 `doc_id / version_id / span_id / node_id / chunk_id / entity_id / relation_id`
2. 先落 PostgreSQL registry schema
3. 设计写入顺序与版本切换流程
4. 让 Neo4j 和向量库都只引用 registry 中的稳定 ID

### 再做
5. 设计向量 chunk 规则
6. 设计 tree node 规则
7. 设计 graph evidence span 规则
8. 建 evidence_link / chunk_to_span / node_to_span 对齐关系

### 最后做
9. 实现查询时的跨层回链
10. 做增量更新和旧版本回收
11. 加监控与一致性校验

---

## 十二、配套图文件

可直接打开查看主键关系图：

- `E:\github\rag\storage-alignment-key-diagram.html`

这个图展示了：
- PostgreSQL registry
- Neo4j
- Milvus / Qdrant
- Tree/docstore
之间如何通过 `doc_id / version_id / span_id / node_id / chunk_id / entity_id` 串起来。