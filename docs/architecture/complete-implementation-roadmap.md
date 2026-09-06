# LlamaIndex-first 完整实施路线图

生成时间：2026-05-08  
决策依据：Sonnet 核验 + verified-project-matrix.md + llamaindex-implementation-assessment.md

---

## 一、核心决策（最终锁定）

### 术语对齐（基于最新外部参照）

这套方案更适合对外描述为：
- **provenance-centric multi-view RAG index**
- **versioned provenance mapping layer for hybrid / agentic RAG**

这里强调的重点不是“某一种 chunking 策略”，而是：
- provenance / evidence
- multi-view indexing
- hierarchical retrieval
- versioned mapping

### 选择：LlamaIndex-first

**决策理由**（三个关键维度）：

#### 1. 需求覆盖完整性
- **LlamaIndex**：KG✅ / Vec✅ / Tree✅ / Parse✅ / Cas✅ / Map✅ / Agent✅（**全覆盖**）
- **KAG**：KG✅ / Vec✅ / Tree◐ / Parse◐ / Cas✅ / Map✅ / Agent◐（Tree/Parse/Agent 为 partial）

**你的需求是"三合一混合架构 + Agent 自主扩展"，只有 LlamaIndex 全覆盖。**

#### 2. 工程控制力
- **LlamaIndex**：
  - MIT 许可 + 活跃维护（2026-04-16）
  - 模块化设计（可按需替换 KG/Vec/Tree/Agent 各层）
  - 官方扩展点清晰（CustomPGRetriever、BaseRetriever、Workflow、Agent tools）
  
- **KAG**：
  - OpenSPG 引擎绑定（KG 层不可替换）
  - 逻辑求解器固化（kg-solver 的逻辑形式固定）

**如果你追求"长期可维护 + 后端可替换"，LlamaIndex 控制力更高。**

#### 3. 改动量 vs ROI

| 方案 | 改动量 | 获得能力 | ROI |
|---|---|---|---|
| **LlamaIndex-first** | 1000-1700行 | KG+Vec+Tree+Agent全栈 + **完全自主策略控制** | **高**（全栈 + 高控制力） |
| **KAG-first** | 200-600行 | KG+Vec强推理 + mutual indexing + 部分 Tree/Agent | 中高（推理强，但Tree/Agent受限） |

**判断**：改动量差异（400-1100行）换取的是 Tree/Agent 的完整控制权。  
如果你的"Tree + Agent 自主扩展"是硬需求，LlamaIndex ROI 更高。

---

## 二、技术栈选择（后端锁定）

### 技术栈总览

| 层 | 选定技术 | 核验依据 | 改动量 |
|---|---|---|---|
| **Keyword 层** | PostgreSQL FTS / trigram / BM25 类路径 | 精确术语 / 指标 / 编码 / 节目名检索 | 80-150行（keyword path + 路由） |
| **KG 层** | LlamaIndex PropertyGraphIndex + **Neo4j** | 原生图遍历/图算法 + Cypher 成熟 | 250-500行（级联retriever） |
| **Vec 层** | LlamaIndex VectorStoreIndex + **Milvus** | 高性能 ANN + 元数据过滤强 | 50-100行（neighborhood-first retriever） |
| **Tree 层** | LlamaIndex HierarchicalNodeParser + AutoMergingRetriever | 子节点命中超阈值自动上卷到父节点 | 70-130行（命中分布统计） |
| **Parse 层** | DoclingReader + DoclingNodeParser（HybridChunker） | 自动保留 page_no + headings | 20-50行（citation 组合） |
| **Agent 层** | LlamaIndex ReActAgent + Workflow | 基于命中分布决策扩展策略 | 600-1100行（决策策略 + tools） |
| **Rerank 层** | 轻量融合排序（先） + 独立 reranker（后） | 多路召回后的质量提升 | 80-180行（第二阶段加入） |

**总改动量**：1180-2080行

---

### 后端详细选择理由

#### KG 后端：选择 Neo4j

**推荐理由**：
- ✅ 原生图遍历/图算法（PageRank/社区发现/子图匹配）
- ✅ Cypher 查询语言成熟
- ✅ LlamaIndex 有官方 Neo4jPropertyGraphStore

**备选（不推荐）**：
- KAG OpenSPG（绑定 KAG 生态）
- vector-graph-rag（图能力受限）

#### Vec 后端：选择 Milvus

**推荐理由**：
- ✅ 高性能 ANN（适合大规模）
- ✅ 元数据过滤能力强（支持你的 neighborhood-first retriever）
- ✅ LlamaIndex 官方集成

**备选**：
- Qdrant（单机部署简单，适合中小规模）
- Chroma（轻量级，适合 PoC 验证）

#### Parse 后端：选择 Docling

**推荐理由**：
- ✅ MIT 许可 + 原生 LlamaIndex 集成
- ✅ 自动保留 page_no + headings（你的 citation-path 基础）
- ✅ 支持 PDF/DOCX/PPTX/HTML

**不推荐**：
- Marker（GPL-3.0 商业需双许可 + 结构元数据丢失）

---

## 三、实施阶段划分（时间线）

### 路径层升级说明

系统现在应按 **四条路径** 组织，而不是三条：
1. **Keyword path**：精确术语 / 指标 / 缩写 / 标准号 / 节目名等
2. **Vector path**：轻量语义检索
3. **Graph path**：概念关系 / 实体关系
4. **Deep Hybrid path**：KG → Keyword/Vec → Tree → 聚合 → 扩展

### Stage 1：基础集成（2-3周）

#### Stage 0：先冻结 identity / normalization contract（建议 1-2 天）
**目标**：在真正接库前，先锁定主键策略与规范化契约，避免后面 `span_id` 漂移。

**先做的决定**：
- `doc_id / version_id / span_id / node_id / chunk_id / entity_id / relation_id` 的责任边界
- `span_id` 的 offset_basis（raw_char / normalized_char / token）
- OCR / 清洗 / heading 归一化规则
- `entity_key / alias normalization / mention -> entity` 规则

**理由**：
- `span_id` 的稳定性不只取决于表结构，还取决于 parser / cleaning contract
- `entity_id` 的稳定性不只取决于 evidence span，还取决于单独的 canonicalization 规则

#### Week 1：环境搭建 + 基础验证
**目标**：跑通 LlamaIndex 基础组件 + 验证元数据保留

**任务清单**：
- Day 1-2：安装依赖
  ```bash
  pip install llama-index llama-index-graph-stores-neo4j llama-index-vector-stores-milvus
  pip install docling llama-index-readers-docling llama-index-node-parser-docling
  ```
  
- Day 3-4：跑通基础示例
  - PropertyGraphIndex + Neo4jPropertyGraphStore（KG 基础）
  - VectorStoreIndex + MilvusVectorStore（Vec 基础）
  - HierarchicalNodeParser + AutoMergingRetriever（Tree 基础）
  
- Day 5：验证 Docling 元数据保留
  ```python
  from llama_index.readers.docling import DoclingReader
  reader = DoclingReader(export_type=JSON)
  docs = reader.load_data(file_path)
  # 验证：docs[0].metadata["page_no"] + docs[0].metadata["headings"]
  ```
  
- Day 6-7：测试 AutoMergingRetriever
  - 验证子节点命中后自动上卷到父节点行为
  - 测试 threshold 阈值调整

**交付物**：
- 基础组件跑通截图
- Docling 元数据保留验证报告

#### Week 2-3：核心组件集成
**目标**：KG + Vec + Tree + Parse 四层打通

**任务清单**：
- KG 层集成（3天）：
  - Neo4j 部署 + schema 定义
  - PropertyGraphIndex.from_documents 构建图谱索引
  - 验证图查询（Cypher + VectorContextRetriever）
  
- Vec 层集成（2天）：
  - Milvus 部署 + collection 创建
  - VectorStoreIndex 构建向量索引
  - 验证元数据过滤（MetadataFilters）
  
- Tree 层集成（2天）：
  - HierarchicalNodeParser 构建三层树
  - AutoMergingRetriever 验证父块回并
  - 元数据注入（parent_id/tree_path）
  
- Parse 层集成（2天）：
  - DoclingReader + DoclingNodeParser 集成
  - citation_path 组合（heading + page_no）
  - 与 Tree 层桥接（元数据传播）

**交付物**：
- 四层打通的完整 pipeline 代码
- 端到端 ingestion 流程验证报告

---

### Stage 2：核心策略自研（3-4周）

#### Week 4-5：命中分布聚散算法（200-400行）

**目标**：实现命中分数沿树层级向上聚合 + 离散度计算 + 决策规则

**算法实现**：

```python
# 1. 向上聚合逻辑
def aggregate_to_ancestors(retrieved_nodes, tree_nodes_dict):
    ancestor_scores = defaultdict(float)
    for node in retrieved_nodes:
        score = node.metadata["score"]
        for ancestor_id in node.metadata["ancestor_ids"]:
            ancestor_scores[ancestor_id] += score
    return ancestor_scores

# 2. 离散度计算（Shannon Entropy + CV）
def compute_dispersion_and_decide(ancestor_scores):
    hit_counts = list(ancestor_scores.values())
    cv = stdev(hit_counts) / mean(hit_counts)  # Coefficient of Variation
    entropy = shannon_entropy(hit_counts)      # Shannon Entropy
    
    # 3. 决策规则
    if cv > 0.8:
        decision = "high_concentration → extract_top_nodes_only"
    elif cv < 0.3:
        decision = "high_dispersion → extract_parent_plus_neighbors"
    else:
        decision = "moderate → extract_hits_and_parents"
    
    return {"distribution": ancestor_scores, "cv": cv, "entropy": entropy, "decision": decision}
```

**任务清单**：
- Day 1-3：向上聚合逻辑实现 + 单元测试
- Day 4-6：离散度计算实现（CV + Entropy）
- Day 7-10：决策规则定义 + 测试验证

**交付物**：
- HitDistributionAnalyzer 完整代码（~200-400行）
- 单元测试覆盖率 >80%
- 决策规则文档 + 测试案例

#### Week 6-7：级联 Retriever（250-300行）

**目标**：实现 KG → Vec → Tree 三阶段级联检索

**实现框架**：

```python
class CascadeKGVecTreeRetriever(BaseRetriever):
    def retrieve(self, query_str):
        # Stage 1: KG 检索 → 实体ID列表
        kg_nodes = self.kg_retriever.retrieve(query_str)
        entity_ids = [n.metadata["entity_id"] for n in kg_nodes]
        
        # Stage 2: 向量检索（仅在这些实体的chunk内）
        filters = MetadataFilters(filters=[
            MetadataFilter(key="entity_id", value=entity_ids)
        ])
        vec_nodes = self.vec_retriever.retrieve(query_str, filters=filters)
        
        # Stage 3: Tree 合并（AutoMergingRetriever）
        merged_nodes = self.tree_retriever.retrieve(vec_nodes)
        
        # Stage 4: 命中分布统计
        distribution = analyze_distribution(merged_nodes)
        
        return merged_nodes, distribution
```

**任务清单**：
- Day 1-4：KG retriever 集成 + 实体ID提取逻辑
- Day 5-7：Vec retriever + MetadataFilters 过滤
- Day 8-10：Tree retriever + 命中分布统计包装

**交付物**：
- CascadeKGVecTreeRetriever 完整代码（~250-300行）
- 级联流程性能测试（延迟 <500ms）

#### Week 8：Agent 扩展决策策略（600-1100行）

**目标**：基于命中分布自主决策扩展（父节点/兄弟节点/相邻chunk）

**实现框架**：

```python
class ExpansionAgent:
    tools = [
        Tool.from_defaults(analyze_hit_distribution),  # 命中分布分析
        Tool.from_defaults(expand_parent_node),        # 向上扩展父节点
        Tool.from_defaults(expand_sibling_branch),     # 向下展开兄弟分支
        Tool.from_defaults(expand_adjacent_chunks),    # 相邻 chunk 扩展
    ]
    
    agent = ReActAgent.from_tools(tools, llm=llm)
    
    def decide(self, distribution):
        # Agent 根据分布自主决定扩展策略
        return agent.chat(f"命中分布：{distribution}，下一步该扩展什么？")
```

**决策规则**（示例）：
- 规则1：`>3 child hits in a parent` → expand_parent_node（父节点摘要）
- 规则2：`hits cluster on one branch` → expand_sibling_branch（兄弟分支）
- 规则3：`single hit` → expand_adjacent_chunks（相邻 800 字符）

**任务清单**：
- Day 1-3：扩展 tools 实现（4个工具）
- Day 4-6：Agent 决策策略定义 + Workflow 编排
- Day 7-10：测试验证 + fallback 机制

**交付物**：
- ExpansionAgent 完整代码（~600-1100行）
- 决策规则文档 + 测试案例

---

### Stage 3：工程化（4-6周）

#### Week 9-10：性能优化

**目标**：级联检索延迟优化 + 并发管线

**优化策略**：
1. **预计算子图索引**（KG层）
   - 在 ingestion 时预计算常见实体的 1-2 hop 子图
   - 存入缓存（Redis/Memory）
   
2. **异步并发管线**（Agent层）
   - 命中分布分析后并行触发多个微型智能体
   - 每个智能体独立负责一个扩展方向
   - 最终汇总到主线程
   
3. **命中分布缓存**（Tree层）
   - 在写入阶段预计算层级质心向量
   - 查询时粗粒度估算，仅在临界区精确计算

**任务清单**：
- Day 1-5：预计算子图索引实现
- Day 6-10：异步并发管线实现
- Day 11-15：命中分布缓存优化

**交付物**：
- 性能测试报告（延迟 <300ms）
- 缓存命中率 >70%

#### Week 11-12：可观测性

**目标**：日志 + 监控 + 命中分布可视化

**监控指标**：
- KG 查询延迟（ms）
- Vec 查询延迟（ms）
- Tree 合并延迟（ms）
- Agent 扩展轮次（count）
- 命中分布熵值（float）
- 扩展决策类型（枚举）

**可视化方案**：
- 命中分布树可视化（markmap/Mermaid）
- 决策策略热力图
- 级联流程延迟分布

**任务清单**：
- Day 1-5：日志系统搭建（结构化日志）
- Day 6-10：监控指标采集（Prometheus + Grafana）
- Day 11-15：命中分布可视化（markmap）

**交付物**：
- Grafana 监控面板
- 命中分布可视化截图

#### Week 13-14：错误处理与部署

**目标**：重试机制 + 降级策略 + 生产部署

**错误处理策略**：
- KG 查询失败 → fallback 到纯 Vec 检索
- Vec 查询超时 → 重试 3 次 + exponential backoff
- Agent 决策异常 → fallback 到默认扩展策略（父节点）

**部署方案**：
- Neo4j + Milvus 容器化部署
- LlamaIndex 服务容器化
- 监控 + 日志 + 告警系统部署

**任务清单**：
- Day 1-5：错误处理 + 重试机制
- Day 6-10：降级策略 + fallback 逻辑
- Day 11-15：生产部署 + 健康检查

**交付物**：
- 错误处理文档
- 生产部署清单
- 健康检查脚本

---

## 四、改动量详细清单

### 改动量总览（按层）

| 层 | 自研组件 | 改动量 | 集成难度 |
|---|---|---|---|
| **KG层** | CascadeKGVecTreeRetriever（级联 retriever）+ KG-Tree 桥接 | 250-500行 | MODERATE |
| **Vec层** | neighborhood-first retriever（图邻域约束） | 50-100行 | MODERATE |
| **Tree层** | 命中分布统计包装器 + 元数据注入 | 70-130行 | MODERATE |
| **Parse层** | citation 组合 + 元数据配置 | 20-50行 | TRIVIAL |
| **Agent层** | ExpansionAgent + 决策策略 + 扩展 tools | 600-1100行 | MODERATE |
| **工程化** | 性能优化 + 可观测性 + 错误处理 | 300-500行 | MODERATE |
| **总计** | — | **1020-1750行** | **MODERATE** |

---

### 改动量细分（核心策略逻辑）

**核心策略逻辑**（Stage 2）：
- 命中分布聚散算法：200-400行
- 级联 retriever：250-300行
- Agent 扩展决策：600-1100行
- **小计**：1050-1800行

**工程化逻辑**（Stage 3）：
- 性能优化：150-250行
- 可观测性：100-150行
- 错误处理：50-100行
- **小计**：300-500行

---

## 五、备选方案对比

### 如果你要快速验证（PoC 优先）

**推荐：NexusRAG-first**
- 改动量：20-50行（citation 组合）
- 时间：1-3周
- 适合：快速验证原型，文档型问答产品
- 缺陷：个人项目（长期维护风险），Tree/命中聚合需自研

### 如果你要逻辑推理优先（KG 强）

**推荐：KAG-first**
- 改动量：200-600行（Vec 后端 + Tree 补件）
- 时间：2-4周 PoC，4-8周生产
- 适合：金融/法务/医疗等逻辑推理场景
- 缺陷：Tree/Agent 都是 partial（受限）

### 如果你要平台化部署（API 服务）

**推荐：R2R-first**
- 改动量：300-500行（外接 Tree + Agent）
- 时间：3-5周 PoC
- 适合：平台化 API 服务
- 缺陷：Tree=no（必须外接）

---

## 六、风险应对策略

### 主要风险与应对

| 风险 | 应对策略 | 验证标准 |
|---|---|---|
| **策略逻辑复杂**（600-1100行） | 分阶段实施：PoC 先验证核心逻辑，生产化再优化 | 单元测试覆盖率 >80% |
| **多阶段级联性能**（KG→Vec→Tree） | 预计算子图索引 + 缓存 + 异步并发管线 | 延迟 <300ms |
| **Agent 扩展决策不稳定** | 定义明确的决策规则 + fallback 机制 + 测试覆盖 | 决策准确率 >85% |
| **多数据库运维成本**（Neo4j+Milvus） | 统一监控面板 + 定期健康检查 + 自动备份 | 健康检查成功率 >99% |
| **元数据丢失**（citation_path） | Docling HybridChunker 自动保留 + 验证测试 | citation 保留率 >95% |

---

## 七、第一周可落地任务（直接可执行）

### Day 1-2：安装依赖

**任务**：安装所有必要依赖并验证版本

```bash
# Core dependencies
pip install llama-index==0.10.67
pip install llama-index-graph-stores-neo4j
pip install llama-index-vector-stores-milvus

# Docling integration
pip install docling
pip install llama-index-readers-docling
pip install llama-index-node-parser-docling

# Neo4j + Milvus (需要单独部署)
docker run -d --name neo4j -p 7474:7474 -p 7687:7687 neo4j:latest
docker run -d --name milvus -p 19530:19530 milvusdb/milvus:latest

# Verify versions
python -c "import llama_index; print(llama_index.__version__)"
python -c "from docling import DoclingReader; print('Docling OK')"
```

**验收标准**：
- 所有依赖安装成功
- Neo4j + Milvus 容器运行正常
- 版本号确认（记录到文档）

---

### Day 3-4：跑通基础示例

**任务**：验证 LlamaIndex 核心组件基础功能

**KG 层验证**：
```python
from llama_index.graph_stores.neo4j import Neo4jPropertyGraphStore
from llama_index.core import PropertyGraphIndex

# Neo4j connection
graph_store = Neo4jPropertyGraphStore(
    username="neo4j", password="password", url="bolt://localhost:7687"
)

# Build KG index
index = PropertyGraphIndex.from_documents(
    [Document(text="Example text about AI and ML")],
    property_graph_store=graph_store
)

# Verify
query_engine = index.as_query_engine()
response = query_engine.query("What is AI?")
print(response)
```

**Vec 层验证**：
```python
from llama_index.vector_stores.milvus import MilvusVectorStore
from llama_index.core import VectorStoreIndex

# Milvus connection
vector_store = MilvusVectorStore(uri="http://localhost:19530")

# Build Vec index
index = VectorStoreIndex.from_documents(
    [Document(text="Example text")],
    vector_store=vector_store
)

# Verify
query_engine = index.as_query_engine()
response = query_engine.query("Example query")
print(response)
```

**Tree 层验证**：
```python
from llama_index.core.node_parser import HierarchicalNodeParser
from llama_index.retrievers import AutoMergingRetriever

# Build tree
hier_parser = HierarchicalNodeParser.from_defaults(chunk_sizes=[2048, 512, 128])
nodes = hier_parser.get_nodes_from_documents([Document(text="Long text...")])

# Verify AutoMergingRetriever
retriever = AutoMergingRetriever(vector_retriever, storage_context)
retrieved_nodes = retriever.retrieve("test query")
print(f"Retrieved {len(retrieved_nodes)} nodes")
```

**验收标准**：
- KG 查询返回结果
- Vec 查询返回结果
- Tree 合并行为验证（子节点 → 父节点）

---

### Day 5：验证 Docling 元数据保留

**任务**：验证 DoclingReader 是否保留 page_no + headings

```python
from llama_index.readers.docling import DoclingReader
from llama_index.node_parser.docling import DoclingNodeParser

# Load document
reader = DoclingReader(export_type=JSON)
docs = reader.load_data("example.pdf")

# Verify metadata
for doc in docs:
    print(f"Page: {doc.metadata.get('page_no')}")
    print(f"Headings: {doc.metadata.get('headings')}")

# Parse to nodes
node_parser = DoclingNodeParser()
nodes = node_parser.get_nodes_from_documents(docs)

# Verify node metadata
for node in nodes[:5]:
    print(f"Node metadata: {node.metadata}")
```

**验收标准**：
- page_no 存在且准确
- headings 列表存在且准确
- 元数据传播到所有节点

---

### Day 6-7：测试 AutoMergingRetriever

**任务**：验证子节点命中后自动上卷到父节点行为

**测试场景**：
```python
# 创建测试文档（明确层级结构）
test_doc = Document(text="""
Chapter 1: Introduction
This is the introduction content.

Chapter 2: Methods
This chapter describes methods.
Method A is important.
Method B is also important.
""")

# 构建树
hier_parser = HierarchicalNodeParser.from_defaults(chunk_sizes=[512, 128])
nodes = hier_parser.get_nodes_from_documents([test_doc])

# 构建索引
index = VectorStoreIndex(nodes)
vector_retriever = index.as_retriever()

# 测试 AutoMergingRetriever
auto_retriever = AutoMergingRetriever(
    vector_retriever, 
    storage_context,
    simple_ratio_thresh=0.5  # 阈值
)

# 测试查询（应该命中多个子节点）
retrieved_nodes = auto_retriever.retrieve("What are the methods?")

# 验证：是否自动合并到父节点
for node in retrieved_nodes:
    print(f"Node level: {node.metadata.get('level')}")
    print(f"Node text length: {len(node.text)}")
```

**验收标准**：
- 子节点命中时，自动上卷到父节点
- threshold 阈值可调且生效
- 合并行为稳定可重现

---

## 八、总时间线与里程碑

### 时间线总览（9-14周）

| 阶段 | 时间 | 核心交付物 | 验收标准 |
|---|---|---|---|
| **Stage 1**（基础集成） | 2-3周 | 四层打通 pipeline + 基础验证报告 | 元数据保留 >95% |
| **Stage 2**（核心策略） | 3-4周 | 命中分布算法 + 级联 retriever + Agent 决策 | 测试覆盖率 >80% |
| **Stage 3**（工程化） | 4-6周 | 性能优化 + 监控 + 生产部署 | 延迟 <300ms |

### 里程碑

| 里程碑 | 时间点 | 验收标准 |
|---|---|---|
| **M1：环境搭建完成** | Week 1 结束 | 所有依赖安装 + 基础示例跑通 |
| **M2：四层打通验证** | Week 3 结束 | KG+Vec+Tree+Parse 集成完成 + 元数据验证 |
| **M3：核心策略完成** | Week 8 结束 | 命中分布算法 + 级联 retriever + Agent 决策实现 |
| **M4：工程化完成** | Week 14 结束 | 性能优化 + 监控 + 生产部署完成 |

---

## 九、成功标准（验收清单）

### PoC 成功标准

- ✅ 四层打通（KG+Vec+Tree+Parse）运行正常
- ✅ 元数据保留率 >95%（page_no + heading_path）
- ✅ 命中分布算法计算准确（CV + Entropy）
- ✅ Agent 扩展决策稳定可重现
- ✅ 端到端延迟 <500ms（PoC 验证）

### 生产成功标准

- ✅ 性能优化达标（延迟 <300ms）
- ✅ 监控面板完整（指标采集 + 可视化）
- ✅ 错误处理完备（重试 + 降级 + fallback）
- ✅ 测试覆盖率 >80%（单元 + 集成）
- ✅ 健康检查成功率 >99%

---

## 十、最终执行建议

### 立即执行路径

**第一周任务**（Day 1-7）：
- Day 1-2：安装依赖 + 验证版本
- Day 3-4：跑通 KG/Vec/Tree 基础示例
- Day 5：验证 Docling 元数据保留
- Day 6-7：测试 AutoMergingRetriever 行为

**验收清单**：
- [ ] 所有依赖安装成功
- [ ] Neo4j + Milvus 容器运行正常
- [ ] KG/Vec/Tree 基础示例跑通
- [ ] Docling 元数据保留验证通过
- [ ] AutoMergingRetriever 合并行为验证

---

### 关键决策确认

**如果你确认以下决策，立即开始 Week 1**：

1. ✅ 选择 LlamaIndex-first（全栈覆盖 + 高控制力）
2. ✅ 选择 Neo4j（KG 后端）
3. ✅ 选择 Milvus（Vec 后端）
4. ✅ 选择 Docling（Parse 后端）
5. ✅ 接受改动量：1020-1750行

**这是"控制力 vs 改动量"的最终决策：你愿意多投入 400-1100行代码，换取 Tree+Agent 的完整自主权。**

---

### 下一步行动

**如果你确认路线图，下一步**：
1. 执行 Week 1 任务（Day 1-7）
2. 验收 M1 里程碑（环境搭建完成）
3. 继续 Stage 1 基础集成（Week 2-3）

**如果需要调整路线图**：
- 回退到备选方案（NexusRAG/KAG/R2R）
- 或调整改动量预算
- 或调整时间线