# 第一阶段可执行规划（AUTOD / v1 收缩版）

生成时间：2026-05-11  
模式：策划，不进入实现  
目标：在 **2~4 周内** 搭出一个**可运行 PoC**，验证以下核心假设：

1. 原文只解析一次是可行的
2. `span_id` 可以作为稳定坐标
3. Keyword path 与 Vector path 可以共用同一套 registry / provenance
4. 文档版本化更新可以不打断查询与引用回链
5. 对外可以先只暴露一个统一 query 入口

---

# 0. 本阶段边界

## 纳入范围
- PostgreSQL registry / mapping / provenance
- canonical spans
- Keyword path
- Vector path
- 统一 query 入口
- Docling 一次解析
- 单 PostgreSQL 方案（registry + keyword path + pgvector）

## 不纳入范围（明确后置）
- Neo4j 独立图层
- Qdrant / Milvus 独立向量库
- Deep Hybrid 主链
- HitDistributionAnalyzer
- 独立 reranker
- 复杂 entity alias resolution
- 多通道 agent 接入（langclaw / Claude / LangChain Tool）

---

# 1. 第一阶段必须先确认的内容

## 1.1 identity contract（最小版）

第一阶段只锁下面这些 ID：

- `doc_id`：逻辑文档身份，跨版本稳定
- `version_id`：文档版本身份
- `span_id`：规范证据身份
- `chunk_id`：向量视图身份

第一阶段**不强制**锁：
- `node_id`（树层可以后置）
- `entity_id`
- `relation_id`

### 验收标准
- 团队能用一句话解释这 4 个 ID 的职责边界
- 不再把 `chunk_id` 当全局主身份

---

## 1.2 normalization contract（最小版）

第一阶段只定最少 5 项：

1. parser 名称：`Docling`
2. parser / OCR 版本号怎么记录
3. 文本清洗规则：
   - 空白怎么规整
   - 换行怎么处理
   - 特殊字符是否保留
4. `offset_basis`：统一采用哪种 offset（建议：`normalized_char_offset`）
5. page_no / heading_path 的生成规则

### 验收标准
- 能写成一页文档
- 同一文档在同一 contract 下重复解析，两次 span 的 offset 一致

---

## 1.3 entity canonicalization contract（最小版）

第一阶段只做最小占位，不做复杂实体归并。

先定：
- 未来 `entity_key` 需要独立于 `chunk_id`
- 第一阶段即便还没做图谱，也要在设计上保留 mention → entity 分层

### 第一阶段决策
- **只保留原则，不实现复杂规则**
- 即：在文档和表结构里保留未来扩展位，但本阶段不做实体解析主链

---

# 2. PostgreSQL registry 的最小表结构（v1 版）

第一阶段不建全量表，只建最小 6 张表。

## 2.1 documents
作用：逻辑文档台账。

字段最小集：
- `doc_id`
- `source_uri`
- `title`
- `doc_type`
- `created_at`

---

## 2.2 document_versions
作用：版本台账。

字段最小集：
- `version_id`
- `doc_id`
- `content_hash`
- `version_no`
- `normalization_contract_id`
- `is_active`
- `status`
- `created_at`

### 关键约束
- `(doc_id, version_no)` 唯一
- `(doc_id, content_hash)` 唯一

---

## 2.3 normalization_contracts
作用：保证 span 生成契约可追溯。

字段最小集：
- `normalization_contract_id`
- `parser_name`
- `parser_version`
- `text_cleaning_profile`
- `heading_normalization_profile`
- `offset_basis`

---

## 2.4 canonical_spans
作用：统一原文坐标层。

字段最小集：
- `span_id`
- `version_id`
- `start_offset`
- `end_offset`
- `page_no`
- `heading_path`
- `raw_text`

### 第一阶段原则
- span 不追求“最终最优检索块”
- 只追求：稳定、可回原文、可组合

---

## 2.5 vector_chunks
作用：向量检索视图。

字段最小集：
- `chunk_id`
- `version_id`
- `chunk_type`
- `chunk_order`
- `token_count`
- `text_preview`
- `page_no`
- `heading_path`

---

## 2.6 vector_chunk_spans
作用：Chunk ↔ Span 回链。

字段最小集：
- `chunk_id`
- `span_id`
- `ordinal_no`

### 为什么 v1 必须有它
因为这是证明“统一 span 而不是统一 chunk”能跑通的关键桥表。

---

# 3. canonical spans 生成流程

## 3.1 总原则

原文只解析一次，不反复切全文。  
第一阶段的输出不是最终检索块，而是一层：

> 稳定、可回原文、可组合的基础 spans

## 3.2 生成步骤

### Step 1：Docling 一次解析
输出：
- page_no
- headings
- 段落 / 小文本块
- offset
- normalized text

### Step 2：标准化
按 normalization contract 处理：
- 空白规整
- heading 归一化
- offset_basis 固定

### Step 3：生成 canonical spans
第一阶段建议：
- 以“句组 / 小段窗”为主
- 目标粒度：可引用、不过大、不过碎
- 每个 span 带 page_no + heading_path + offset

### Step 4：写入 canonical_spans 表
并绑定：
- `doc_id`
- `version_id`
- `normalization_contract_id`

---

## 3.3 验收标准

第一阶段 spans 通过的标准：
1. 每个 span 能回到原文
2. 每个 span 有 `page_no` 和 `heading_path`
3. 相同 contract 下重复生成结果稳定
4. 文档改动后，新 `version_id` 能生成新 spans，不覆盖旧版

---

# 4. Keyword path 与 Vector path 的落地顺序

## 4.1 顺序结论

### 先做：Keyword path
### 再做：Vector path

### 为什么这么排
因为 Keyword path：
- 更简单
- 更确定
- 不依赖 embedding 质量
- 更容易验证 registry / span 回链是否正确

而 Vector path：
- 还涉及 embedding
- 还涉及 chunk 组合策略
- 一旦结果不好，不容易判断是 mapping 问题还是 embedding 问题

所以：

> **第一阶段先用 Keyword path 证明“坐标和台账是对的”，再上 Vector path 证明“语义检索可用”。**

---

## 4.2 Keyword path 的接口边界

### 输入
- query
- active version（默认 current active）

### 输出
- `span_id`
- `doc_id`
- `version_id`
- `page_no`
- `heading_path`
- `raw_text` 或 text snippet

### 第一阶段不要求
- 不需要复杂 rerank
- 不需要 graph 约束

---

## 4.3 Vector path 的接口边界

### 输入
- query
- active version

### 输出
- `chunk_id`
- `span_ids[]`
- `doc_id`
- `version_id`
- `page_no`
- `heading_path`
- similarity score

### 关键要求
- 一定能从 `chunk_id` 回映到 `span_id`
- 一定能知道命中的 chunk 属于哪个版本

---

## 4.4 统一 query 入口

第一阶段建议只做一个统一入口：

- `/query`
- 或 `knowledge_router(query)`

### 内部逻辑（v1 简版）
1. 如果 query 明显是精确术语 / 指标 / 型号 / 节目名 → Keyword path
2. 否则 → Vector path

### 第一阶段不做
- Graph path
- Deep Hybrid path
- 多路融合

---

# 5. 第一阶段任务拆解

## Phase 0：规则冻结

### Task 0.1
写出 identity contract 文档

### Task 0.2
写出 normalization contract 文档

### Task 0.3
写出 entity canonicalization 最小原则文档

### 验收
- 三份规则文档存在
- 规则之间没有冲突

---

## Phase 1：Registry 建库

### Task 1.1
建 `documents`

### Task 1.2
建 `document_versions`

### Task 1.3
建 `normalization_contracts`

### Task 1.4
建 `canonical_spans`

### Task 1.5
建 `vector_chunks`

### Task 1.6
建 `vector_chunk_spans`

### 验收
- 可以插入一份文档、一份版本、一批 spans、一批 chunks
- 约束不冲突
- 可以按 `version_id` 查询完整链路

---

## Phase 2：Docling → spans

### Task 2.1
接 Docling 解析器

### Task 2.2
把解析结果转成 spans

### Task 2.3
绑定 normalization_contract_id

### Task 2.4
写入 canonical_spans

### 验收
- 同一文档可重复解析
- span 可回原文
- page_no / heading_path 正确

---

## Phase 3：Keyword path

### Task 3.1
为 spans 建关键词检索能力

### Task 3.2
定义 Keyword path 输出结构

### Task 3.3
验证 `PM2.5`、标准号、节目名这类 query

### 验收
- 精确词可查
- 返回结果能回 span / page / heading

---

## Phase 4：Vector path

### Task 4.1
从 spans 组合出 vector chunks

### Task 4.2
写入 pgvector / PostgreSQL 向量层

### Task 4.3
建立 chunk ↔ span 回链

### Task 4.4
定义 Vector path 输出结构

### 验收
- 轻量语义 query 能查到内容
- 能回到 chunk / span / page / heading

---

## Phase 5：统一 query 入口

### Task 5.1
定义 query classifier 的最小规则

### Task 5.2
Keyword / Vector 二选一路由

### Task 5.3
统一返回结构

### 验收
- 一个 query 入口即可跑通
- query 能稳定落到正确路径

---

# 6. 依赖顺序

## 强依赖顺序
1. 规则冻结
2. PostgreSQL 最小 schema
3. Docling → spans
4. Keyword path
5. Vector path
6. 统一 query 入口

## 不能颠倒的地方
- **不能先做向量检索，再补 registry**
- **不能先做 chunk，再补 version_id**
- **不能先做 query router，再没有 spans / mappings**

---

# 7. 第一阶段验收标准

## 必须满足
1. 原文只解析一次
2. 有 active version 概念
3. span 稳定可回原文
4. Keyword path 可用
5. Vector path 可用
6. 两条路径共用同一套 provenance / mapping
7. 统一 query 入口可用

## 可以暂时不满足
- 图谱独立查询
- tree 回并
- Deep Hybrid
- 命中分布分析
- reranker

---

# 8. 风险点

## 风险 1：span 粒度太大
后果：
- keyword 不够精确
- graph evidence 以后不好挂

## 风险 2：span 粒度太碎
后果：
- vector chunk 组合成本高
- query 返回过碎

## 风险 3：normalization contract 没冻结
后果：
- span_id 漂移
- registry 失真

## 风险 4：一上来就做 graph path
后果：
- 第一阶段复杂度爆炸
- 很难判断问题到底出在 registry 还是 graph

## 风险 5：PoC 还没验证，就先引入独立向量库
后果：
- 数据同步和调试复杂度显著上升

---

# 9. 明确后置项

第一阶段明确后置：
- Neo4j 独立图层
- Qdrant / Milvus 独立向量库
- Tree 层正式回并机制
- Deep Hybrid 主链
- HitDistributionAnalyzer
- Reranker
- 复杂 entity resolution
- 多通道 Tool / API / CLI 接入

---

# 10. 第一阶段最小成功定义

如果 2~4 周后，系统能做到下面这些，就算第一阶段成功：

1. 上传一篇文档
2. Docling 一次解析
3. 生成 `canonical_spans`
4. 写入 PostgreSQL registry
5. 同时支持：
   - Keyword path
   - Vector path
6. 一个统一 query 入口
7. 返回结果能回到：
   - 文档
   - 版本
   - span
   - 页码
   - heading

也就是说：

> **第一阶段的成功，不是“做出了最终系统”，而是“证明统一 span / version / provenance 这条主干能跑通”。**