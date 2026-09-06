# 系统搭建流程（实施版）

生成时间：2026-05-09  
目标：从 0 开始把当前方案搭起来，最终得到一个 **provenance-centric multi-view RAG** 系统。  
最终产物：
- 统一身份层 / 版本层 / 证据层
- Keyword / Vector / Graph / Deep Hybrid 四条查询路径
- 可对外暴露成 Tool / API / CLI

---

# 0. 先说最终要搭成什么

你最终要搭出来的不是“一个向量检索项目”，也不是“一个知识图谱项目”，而是一个完整内核：

## 最终系统
- **原文只解析一次**
- 生成一套稳定的 `canonical spans`
- 从 spans 派生四种视图：
  1. Keyword view
  2. Vector view
  3. Tree view
  4. Graph evidence view
- 用 **LlamaIndex** 做统一查询编排
- 对外暴露成：
  - Tool
  - API
  - CLI

---

# 1. 总体搭建顺序

## 一句话顺序

> **先定规则，再建账本，再接三层存储，再接 LlamaIndex 编排，最后做复杂路径。**

## 实际顺序
1. 冻结 identity / normalization / entity canonicalization 规则
2. 搭 PostgreSQL registry
3. 跑一次文档解析，生成 canonical spans
4. 建 Tree 视图
5. 建 Keyword 视图
6. 建 Vector 视图
7. 建 Graph 视图
8. 接 LlamaIndex，做四条路径
9. 做 Deep Hybrid 主链
10. 做版本切换、缓存、重排、监控

---

# 2. Phase 0：先锁规则（先于所有编码）

这一阶段非常关键，必须先完成。

## 2.1 锁主键体系

你要先定义清楚：
- `doc_id`：逻辑文档身份
- `version_id`：文档版本身份
- `span_id`：规范证据身份
- `node_id`：树节点身份
- `chunk_id`：向量块身份
- `entity_id`：实体身份
- `relation_id`：关系身份

## 2.2 锁 normalization contract

先定死：
- parser 用哪个（Docling）
- OCR 配置
- 清洗规则
- 标题归一化规则
- offset_basis（raw_char / normalized_char / token）
- page_no 的生成规则

## 2.3 锁 entity canonicalization contract

先定死：
- `entity_key` 怎么生成
- alias / mention normalization 怎么做
- 同一个实体多个别名如何归并
- mention 和 entity 如何分开建模

## 为什么这一步必须先做

因为如果不先定这些规则，后面会出现：
- `span_id` 漂移
- 同一个实体跨版本不稳定
- chunk 变了以后所有映射断裂
- 更新策略完全失效

---

# 3. Phase 1：先搭基础环境

## 3.1 语言和运行环境

建议：
- Python 3.11+
- Poetry 或 uv（任选其一）
- Docker（用于数据库本地启动）

## 3.2 依赖清单

核心依赖：
- `llama-index`
- `llama-index-graph-stores-neo4j`
- `llama-index-vector-stores-milvus` 或 Qdrant 对应包
- `docling`
- `llama-index-readers-docling`
- `llama-index-node-parser-docling`
- PostgreSQL 驱动
- Neo4j 驱动
- 向量库 SDK

## 3.3 数据库准备

要准备 3 个数据库：

### A. PostgreSQL
负责：
- registry / mapping / provenance / versioning
- keyword path（第一阶段可直接先用它）

### B. Neo4j
负责：
- graph path
- entity / relation / evidence links 的图层执行

### C. Milvus 或 Qdrant（二选一）
负责：
- vector path
- 向量召回和 metadata 过滤

## 3.4 第一阶段推荐选择

### 推荐默认选择
- PostgreSQL
- Neo4j
- **Qdrant**（如果你想 metadata-heavy 更舒服）

### 另一种选择
- PostgreSQL
- Neo4j
- **Milvus**（如果你更在意大规模性能）

---

# 4. Phase 2：先建 PostgreSQL 台账（最先落地）

## 4.1 为什么先建它

因为它是总账本。  
如果没有 registry，三层（图 / 向量 / 树）会各写各的，一旦重切片就全乱。

## 4.2 先建哪些表

优先建：
- `documents`
- `document_versions`
- `normalization_contracts`
- `canonical_spans`
- `tree_nodes`
- `tree_node_spans`
- `vector_chunks`
- `vector_chunk_spans`
- `entities`
- `entity_aliases`
- `entity_mentions`
- `relations`
- `evidence_links`
- `chunk_entity_links`
- `node_entity_links`

> 这些表的草案已经写在：`storage-schema-draft.md`

## 4.3 这一步的验收标准

验收通过标准：
- 你能创建一篇文档的 `doc_id`
- 你能创建一个新 `version_id`
- 你能往 `canonical_spans` 里写入一批基础单元
- 这些 span 能按 `version_id` 查询出来

---

# 5. Phase 3：先做一次解析，生成 canonical spans

## 5.1 用哪个项目
- **Docling**

## 5.2 这一步做什么

原始文档 → Docling 一次解析 → 产出：
- 页码
- 标题层级
- 段落 / 小文本块
- offset
- normalized text

然后把这些内容转成：
- `span_id`
- `version_id`
- `start_offset`
- `end_offset`
- `page_no`
- `heading_path`

## 5.3 关键原则

这一层不是最终 chunk。  
它只是：

> **统一的底层原文坐标系**

## 5.4 这一步的验收标准

验收通过标准：
- 每个 span 都能回到原文
- 每个 span 都带 page_no + heading_path
- 同一版本内 spans 稳定可复现
- 相同 normalization contract 下，重复解析结果一致

---

# 6. Phase 4：派生 Tree 视图

## 6.1 用哪个项目
- **LlamaIndex HierarchicalNodeParser**
- **AutoMergingRetriever**

## 6.2 这一步做什么

从 canonical spans 派生：
- chapter nodes
- section nodes
- paragraph-group nodes
- summary nodes

并建立：
- `node_id`
- `parent_node_id`
- `tree_node_spans`

## 6.3 关键原则

树层不是重新读全文。  
是：

> **从 spans 重新组合结构视图**

## 6.4 这一步的验收标准

验收通过标准：
- 每个 tree node 都能回到 span
- parent-child 关系稳定
- 能从 leaf 命中回并到 parent

---

# 7. Phase 5：派生 Keyword 视图

## 7.1 为什么先做它

因为你已经明确需要 `PM2.5`、标准号、节目名、人名、型号这种精确检索。  
纯向量检索对这些不稳。

## 7.2 第一阶段怎么做

先别上重系统。  
直接在 PostgreSQL 里做：
- FTS
- trigram
- BM25 类路径

## 7.3 输入是什么

Keyword view 不需要重新切全文。  
直接基于：
- canonical spans
- 或 tree leaf / paragraph 级 span 组合

## 7.4 这一步的输出

返回：
- `span_id`
- `node_id`
- `chunk_id`（如果已有）
- `page_no`
- `heading_path`

## 7.5 这一步的验收标准

验收通过标准：
- 像 `PM2.5`、节目名、标准号能被精确查到
- 返回结果可以回到 span / node / page

---

# 8. Phase 6：派生 Vector 视图

## 8.1 用哪个项目
- **LlamaIndex VectorStoreIndex**
- 向量库：Milvus 或 Qdrant
- 可选：LlamaIndex SemanticSplitter

## 8.2 这一步做什么

从基础 spans 派生 embedding-friendly chunks：
- 相邻 spans 合并
- 控制 token 大小
- 必要时做 overlap / semantic merge

然后写入向量库，并在 metadata 中带上：
- `doc_id`
- `version_id`
- `chunk_id`
- `node_id`
- `page_no`
- `heading_path`
- `entity_ids[]`（后续补）

## 8.3 关键原则

向量 chunk 不是底层真相，  
它只是：

> **一个为了 embedding 检索服务的派生视图**

## 8.4 验收标准

验收通过标准：
- 轻量语义问题能召回合理 chunk
- chunk 能回映到 `span_id / node_id`
- metadata 过滤可正常使用

---

# 9. Phase 7：派生 Graph Evidence 视图

## 9.1 用哪个项目
- **Neo4j**
- **LlamaIndex PropertyGraphIndex**

## 9.2 这一步做什么

从 spans 或 span window 抽：
- entity
- relation
- evidence

并写入：
- `entities`
- `relations`
- `evidence_links`
- Neo4j graph projection

## 9.3 关键原则

图谱证据不要直接依赖向量 chunk。  
应该依赖：
- `span_id`
- mention → entity
- evidence → relation

也就是说：

> **图谱层的证据真相在 span，不在 chunk。**

## 9.4 验收标准

验收通过标准：
- entity / relation 可查
- evidence 能回到 span
- 能通过 registry 找到相关 chunk / node

---

# 10. Phase 8：接上 LlamaIndex 的四条路径

## 10.1 路径一：Keyword path
- 适合精确词问题
- 直接走 PostgreSQL 关键词检索

## 10.2 路径二：Vector path
- 适合轻量语义问题
- 直接走向量检索

## 10.3 路径三：Graph path
- 适合概念关系问题
- 直接走知识图谱

## 10.4 路径四：Deep Hybrid path
- 适合复杂问题
- 流程：
  - 先知识图谱锁定概念
  - 再 registry 找相关 span / chunk / node
  - 再关键词 / 向量检索
  - 再树回并
  - 再命中分布分析
  - 再扩展上下文

## 10.5 这一步的输出

最后应该统一返回结构化结果：
- `route`
- `answer`
- `evidence`
- `expansion_trace`
- `confidence`

---

# 11. Phase 9：做 Deep Hybrid 主链

这是最核心、也是最晚做的一条。

## 11.1 你真正要自研的东西

- query classifier
- graph-first constrained retrieval
- keyword / vector 融合
- tree rollup
- hit distribution analyzer
- expansion policy

## 11.2 先做什么

第一版先做最简单：
- 规则式 query classifier
- 简单分数融合
- 固定扩展策略

## 11.3 后面再做什么

第二版再加：
- 更强 reranker
- 更复杂 query classification
- 更复杂 entity resolution
- 更复杂 graph constraints

---

# 12. Phase 10：封成对外接口

## 12.1 推荐对外形式

### 方案 A（推荐）
一个总 Tool：
- `knowledge_router_tool`

### 方案 B
一个统一 API：
- `/query`

### 方案 C
一个 CLI：
- `knowledge-router`

## 12.2 为什么推荐一个总入口

因为外部系统不应该知道你内部有四条路径。  
外部只需要知道：

> 问一个问题，系统自己决定怎么查。

---

# 13. Phase 11：更新机制与版本切换

## 推荐流程

文档变动时：
1. 新建 `version_id`
2. 重新解析文档
3. 生成新 spans
4. 重新派生 tree / keyword / vector / graph 视图
5. 校验一致性
6. 切 active version / alias
7. 回收旧版本

## 不要做
- 不要原地覆盖旧 chunk
- 不要原地覆盖图谱证据
- 不要先删旧版再建新版

---

# 14. 第一阶段最值得先落地的版本

如果你想先做最小可运行系统，我建议顺序是：

## MVP 顺序
1. PostgreSQL registry
2. Docling + canonical spans
3. Tree view
4. Keyword view
5. Vector view
6. Graph view
7. 最后再接 Deep Hybrid

### 为什么这样排
因为这样你能先拿到：
- 原文可追溯
- 精确检索
- 轻量语义检索
- 基本结构回并

而最复杂的 Deep Hybrid 可以后置。

---

# 15. 你最终会得到什么

最终你得到的不是一个“向量问答系统”，而是一个：

> **统一身份层、版本层、证据层驱动的多视图知识检索与推理内核**

它内部：
- 有四条路径
- 有统一 provenance / mapping
- 有稳定更新机制
- 有图、向量、树三层协作

它对外：
- 可以作为 Tool
- 可以作为 API
- 可以作为 CLI
- 可以挂到 LangChain / langclaw / Claude 上

---

# 16. 一句话最终结论

如果你问“搭建流程到底怎么做”，最准确的答案就是：

> **先建账本（PostgreSQL registry），再建四个视图（Keyword / Vector / Tree / Graph），最后让 LlamaIndex 把它们编排成一个统一的知识路由器。**