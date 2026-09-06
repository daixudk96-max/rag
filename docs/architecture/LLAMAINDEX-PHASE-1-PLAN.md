# LlamaIndex 正式实现第一阶段计划

## 这份计划是什么

这不是 `verification/` 的继续扩展计划。  
这是一份**真正面向目标架构**的第一阶段执行计划。

目标是：

> **开始搭建基于 LlamaIndex 的正式项目骨架，并把已经验证通过的思路迁移到 LlamaIndex 原生能力上。**

---

## 冻结输入

这份计划严格受 `docs/PROJECT-FREEZE.md` 约束，先锁定四条前提：

1. 正式主线已经锁定为 **LlamaIndex-first**
2. `verification/` 只保留为参考实现、架构验证器、行为基线
3. PostgreSQL 继续作为 identity / version / provenance 的 source of truth
4. 第一阶段只解决正式骨架、ingestion spine、vector path、tree path，不追求一次做完整 graph / deep hybrid

---

## Phase 1 目标

先做 **LlamaIndex Spine**，不要一上来追求完整功能。

### 第一阶段交付目标

1. 建立正式实现目录
2. 接入 LlamaIndex + Docling
3. 让 PostgreSQL registry 继续作为 source of truth
4. 用 LlamaIndex 原生能力承接：
   - Vector layer
   - Tree layer
5. 给 Graph layer 留清晰接口，但先不把整条 Deep Hybrid 主链一次做完

### 本阶段的核心结果

到第一阶段结束时，项目里应当同时存在两条明确分离的线：

- `verification/`：验证线，继续保留
- 正式运行时目录：正式主线，后续工作都在这里推进

---

## 推荐目录决策

### 推荐采用：`llamaindex_runtime/`

相比通用的 `app/`，`llamaindex_runtime/` 更明确表达了这条线的职责，也能避免未来和 API/UI 目录命名冲突。

### 建议骨架

```text
llamaindex_runtime/
├── config/
├── ingestion/
├── registry/
├── vector/
├── tree/
├── graph/
├── interfaces/
└── entrypoints/
```

### 各目录职责

- `config/`：LlamaIndex、Docling、数据库、向量后端配置
- `ingestion/`：DoclingReader、DoclingNodeParser、canonical span ingestion
- `registry/`：PostgreSQL registry 适配层与写入逻辑
- `vector/`：VectorStoreIndex 路径
- `tree/`：HierarchicalNodeParser、AutoMergingRetriever 路径
- `graph/`：只放 graph seam / adapter contract，不做完整 runtime
- `interfaces/`：统一的 retrieval contract、tool contract
- `entrypoints/`：CLI / API / tool 的正式入口

---

## 第一阶段范围（In Scope）

### 1. 正式项目骨架

- 新建正式实现目录 `llamaindex_runtime/`
- 配好最小可运行的 Python 包结构
- 预留统一入口，但本阶段不要求把所有入口都做完整

### 2. 接入 LlamaIndex 核心依赖

本阶段必须真实接入：

- `VectorStoreIndex`
- `HierarchicalNodeParser`
- `AutoMergingRetriever`
- `DoclingReader`
- `DoclingNodeParser`

本阶段只为 graph 预留接口，不要求完整打通：

- `PropertyGraphIndex`
- `Neo4jPropertyGraphStore`
- `Workflow`
- `ReActAgent`

### 3. Parse 主链迁回正式主线

- 用 Docling 做一次解析
- 产出 canonical spans
- 保留 `page_no`、`headings`、`offset` 等可追溯信息
- 继续写入 PostgreSQL registry

### 4. Vector / Tree 正式迁移

把验证线里现在的：

- `vector_path`
- `tree_path`

迁移成：

- LlamaIndex 原生 `VectorStoreIndex`
- LlamaIndex 原生 `HierarchicalNodeParser + AutoMergingRetriever`

### 5. 统一主入口的最小骨架

第一阶段不要求完整 agent 化，但要先把正式主线的统一入口边界定下来，至少明确：

- ingestion 入口
- retrieval 入口
- query orchestration 入口

---

## 第一阶段明确不做（Out of Scope）

这些先不要碰：

1. 继续扩展 `verification/` 功能
2. 复杂 graph runtime 完整迁移
3. Deep Hybrid 全链一次落地
4. 高级 hit distribution 策略优化
5. 学习型 reranker / cross-encoder
6. 部署、监控、CI 完整化
7. 让正式主线直接替代验证线的全部能力矩阵

---

## 执行原则

### 原则 1：迁移能力，不迁移目录定位

可以复用验证线里的思路、数据契约、测试样例和行为基线，
但不要继续把 `verification/` 当成正式运行时目录去加功能。

### 原则 2：先打通 spine，再补复杂策略

第一阶段优先级是：

1. 目录和模块边界
2. ingestion -> registry 主链
3. vector path
4. tree path
5. graph seam

而不是一开始就做完整 hybrid strategy。

### 原则 3：正式主线只围绕 span 坐标组织

第一阶段所有模块都应围绕以下稳定坐标组织：

- `doc_id`
- `version_id`
- `span_id`

不要把某个局部 index 的 chunk / node 视图当成系统主坐标。

---

## 工作包拆解

### WP1：建立正式运行时骨架

#### 目标
建立 `llamaindex_runtime/` 正式目录，并明确与 `verification/` 的职责分离。

#### 具体任务

1. 创建正式目录骨架
2. 定义配置入口
3. 定义统一的 runtime package 边界
4. 预留 `entrypoints/` 与 `interfaces/`

#### 完成标准

- 正式目录已存在
- 模块边界清晰
- 后续 vector / tree / graph 都有明确落点
- 没有继续把正式代码塞进 `verification/`

---

### WP2：打通 Docling + PostgreSQL registry 主链

#### 目标
把一次解析、canonical spans、registry 写入，迁回正式主线。

#### 具体任务

1. 接入 `DoclingReader`
2. 接入 `DoclingNodeParser`
3. 产出 canonical span 结构
4. 把 span 元数据写入 PostgreSQL registry
5. 确认正式主线与验证线共享同一 source of truth 语义

#### 完成标准

- 正式主线可完成一次解析
- 解析结果保留 provenance 所需字段
- registry 写入链路可跑通
- `doc_id/version_id/span_id` 语义不漂移

---

### WP3：落地 LlamaIndex 原生 Vector Path

#### 目标
用 `VectorStoreIndex` 承接正式向量检索路径。

#### 具体任务

1. 定义正式 vector ingestion 入口
2. 用 LlamaIndex 节点构建向量索引
3. 接上当前可接受的底层后端（PoC 可继续使用 pgvector）
4. 暴露正式 vector retrieval 入口
5. 让返回结果仍然能映射回 registry / provenance 坐标

#### 完成标准

- `VectorStoreIndex` 已实际接入
- 正式主线的 vector query 可跑
- 返回结果可回落到 PostgreSQL registry 坐标
- 不再依赖验证线的自定义 vector 执行主逻辑

---

### WP4：落地 LlamaIndex 原生 Tree Path

#### 目标
用 `HierarchicalNodeParser + AutoMergingRetriever` 承接正式树路径。

#### 具体任务

1. 定义树节点生成流程
2. 接入 `HierarchicalNodeParser`
3. 接入 `AutoMergingRetriever`
4. 让 tree rollup 行为回到 LlamaIndex 原生机制
5. 保留与 canonical spans 的映射关系

#### 完成标准

- 正式主线 tree path 可跑
- tree rollup 不再以验证线自定义逻辑为正式主逻辑
- 树节点与 span 坐标关系可追溯

---

### WP5：定义 Graph 接入点

#### 目标
先把 graph layer 的接口位置定下来，而不是在第一阶段做完整实现。

#### 具体任务

1. 预留 `graph/` 目录
2. 定义 PropertyGraph 接入 contract
3. 明确未来与 Neo4j 的接入边界
4. 明确它与 vector / tree / registry 的数据边界

#### 完成标准

- Graph seam 已存在
- 后续可以在不重拆骨架的前提下接入 `PropertyGraphIndex`
- 第一阶段没有被 graph runtime 拖慢

---

## 执行顺序

### Step 0：定目录和边界

输出：正式目录决策、模块边界、统一入口边界

### Step 1：接基础依赖

输出：LlamaIndex / Docling / PostgreSQL 的最小运行链路

### Step 2：打通 ingestion spine

输出：原文 -> Docling -> canonical spans -> PostgreSQL registry

### Step 3：做正式 vector path

输出：LlamaIndex 原生 vector retrieval 路径

### Step 4：做正式 tree path

输出：LlamaIndex 原生 tree retrieval / rollup 路径

### Step 5：留出 graph seam

输出：可扩展但未过度实现的 graph 接口骨架

---

## 参考映射

第一阶段可以把 `verification/` 当作参考来源，但只用于迁移知识，不用于继续扩正式主线。

### 优先参考的现有部分

- parser 相关：Docling 包装、normalization、span 生成
- registry 相关：PostgreSQL schema / queries / versioning 语义
- vector/tree 相关：当前验证线里的行为基线与回归预期
- tests 相关：把现有验证结果当作行为对照，不当作正式目录承载

### 迁移方式

- 复用契约
- 复用行为基线
- 必要时复用测试样例
- 不直接把验证目录当成正式 runtime 继续长大

---

## 第一阶段产物

### 代码层

- `llamaindex_runtime/` 正式目录骨架
- Docling + PostgreSQL registry 主链
- LlamaIndex 版 vector path
- LlamaIndex 版 tree path
- Graph seam

### 文档层

- 正式主线与验证线职责说明
- 目录边界说明
- 后续 Graph / Hybrid 接入点说明

---

## 第一阶段成功标准

如果下面这些做到，就算 Phase 1 成功：

1. 正式实现目录建立
2. LlamaIndex 已接入项目
3. Docling + PostgreSQL registry 主链打通
4. LlamaIndex 原生 vector path 可跑
5. LlamaIndex 原生 tree rollup 可跑
6. 不再继续依赖 `verification/` 作为正式实现主线

---

## 阶段结束时不应出现的情况

以下任一情况出现，都说明第一阶段没有真正完成：

1. 正式代码仍主要长在 `verification/`
2. vector path 仍然主要靠验证线自定义逻辑驱动
3. tree path 仍然没有迁回 LlamaIndex 原生能力
4. registry 不再是明确的 source of truth
5. graph 需求反向把第一阶段范围拖大

---

## 结论

第一阶段真正要解决的，不是“再补几个能力点”，而是把项目主线重新摆正：

> **验证线继续证明路线可行，正式主线则明确回到 LlamaIndex-first。**

因此第一阶段最重要的不是继续增强验证代码，而是：

> **建立正式运行时骨架，并把已经验证过的 vector / tree / provenance 主干迁回 LlamaIndex 原生体系。**
