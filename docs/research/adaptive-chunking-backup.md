# 自适应切片相关内容备份

备份时间：2026-05-08  
来源：之前的核验和技术问答记录

---

## 一、自适应切片的概念澄清

### 两种不同的自适应切片定义

**核验发现：自适应切片有两个分支概念**

| 类型 | 定义 | 实现项目 | 切片依据 |
|---|---|---|---|
| **语义自适应切片** | 检测相邻句子语义相似度下降点，在语义断点切割 | LlamaIndex SemanticSplitter | embedding 相似度 |
| **结构自适应切片** | 按文档结构边界（heading/section）切，保留结构元数据 | Docling HybridChunker | heading 层级边界 |

### 与 Late Chunking 的区别

**核验澄清**：
- **自适应切片**：仍预切片，但切片边界更智能（语义/结构）
- **Late Chunking**：全文先过 transformer 再切片，embedding 带全文上下文

---

## 二、你之前核验项目中的自适应切片能力

### 有自适应切片的项目（仅2个）

#### 1) LlamaIndex —— 语义自适应切片

**组件**：`SemanticSplitterNodeParser`
- 原理：相邻句子 embedding 相似度低于 `breakpoint_percentile_threshold` 时切割
- 特点：语义连贯优先，chunk 大小随内容密度变化
- 元数据：需手动传播 page_no/heading_path（不自动保留）
- 核验状态：原生支持（trivial-moderate 改动）

**代码示例**：
```python
from llama_index.core.node_parser.text import SemanticSplitterNodeParser

semantic_parser = SemanticSplitterNodeParser.from_defaults(
    buffer_size=1,
    breakpoint_percentile_threshold=95,  # 相似度下降阈值
    embed_model=embed_model,
)
```

#### 2) Docling —— 结构自适应切片

**组件**：`HybridChunker` + `HierarchicalChunker`
- 原理：按 heading/section 边界切，保留文档结构
- 特点：结构优先，自动保留 page_no + headings 元数据
- 元数据：自动保留，无需手动传播
- 核验状态：原生支持（trivial 改动）

**代码示例**：
```python
from docling.chunking import HybridChunker
from llama_index.node_parser.docling import DoclingNodeParser

chunker = HybridChunker()  # 结构自适应 + 元数据保留
node_parser = DoclingNodeParser(chunker=chunker)
nodes = node_parser.get_nodes_from_documents(docs)
# 自动带 page_no + headings
```

### 其他项目：都没有自适应切片

**核验清单中的其他项目全部是预切片**：
- KAG：预切片（固定策略）
- NexusRAG：预切片
- LightRAG：预切片
- kg-rag：预切片
- Cognee：预切片
- Psi-RAG：预切片
- RAPTOR：预切片
- HIRO：预切片
- R2R：预切片
- HiRAG：预切片

---

## 三、自适应切片与树索引的兼容性

### LlamaIndex 的两条集成路径

**路径 A：Docling + HierarchicalNodeParser（推荐）**
```
DoclingReader → DoclingNodeParser(HybridChunker) → 
结构化节点（带 page_no + headings） → 
HierarchicalNodeParser → 树层级
```
- Docling HybridChunker：结构自适应
- 自动保留元数据
- HierarchicalNodeParser：复制元数据到子节点
- 改动量：~20-30行（citation 组合）

**路径 B：SemanticSplitter + HierarchicalNodeParser（备选）**
```
HierarchicalNodeParser.from_defaults(
    node_parser_map={
        "leaf": SemanticSplitterNodeParser(...),  # 语义自适应
        "parent": SentenceSplitter(...)          # 固定大小
    }
)
```
- 叶子层用语义自适应切片
- 父节点层用固定大小（保证树层级稳定）
- 元数据需手动传播
- 改动量：~30-50行

---

## 四、元数据保留的关键问题

### SemanticSplitter 的风险

**核心风险**：语义切片可能跨 heading 边界
- 一个 heading 的内容可能被切成多个 chunk
- 需手动把原 Document 的 page_no + heading_path 复制到每个 Node

**解决方案**：
```python
for node in semantic_chunked_nodes:
    node.metadata["page_no"] = source_document.metadata["page_no"]
    node.metadata["heading_path"] = source_document.metadata["heading_path"]
```

### Docling HybridChunker 的优势

**自动保留机制**：
- `page_no`：页码
- `headings`：标题层级列表
- `doc_items`：文档元素引用

**只需组合 citation_path**：
```python
node.metadata["citation_path"] = " > ".join(node.metadata["headings"]) + f" (p.{node.metadata['page_no']})"
```

---

## 五、直接可执行的集成建议

### 推荐方案：Docling HybridChunker + HierarchicalNodeParser

**理由**：
1. 结构自适应（按标题层级切）
2. 自动保留元数据（你需要的 citation 基础）
3. 改动量最小（trivial）
4. 与树索引兼容

**代码框架**：
```python
from llama_index.readers.docling import DoclingReader
from llama_index.node_parser.docling import DoclingNodeParser
from docling.chunking import HybridChunker
from llama_index.core.node_parser import HierarchicalNodeParser

# Step 1: Docling 解析 + 结构自适应切片
reader = DoclingReader(export_type=JSON)
docs = reader.load_data(file_path)

chunker = HybridChunker()
node_parser = DoclingNodeParser(chunker=chunker)
nodes = node_parser.get_nodes_from_documents(docs)

# Step 2: 组合 citation_path
for node in nodes:
    node.metadata["citation_path"] = " > ".join(node.metadata["headings"]) + f" (p.{node.metadata['page_no']})"

# Step 3: 构建树层级
hier_parser = HierarchicalNodeParser.from_defaults(chunk_sizes=[2048, 512, 128])
tree_nodes = hier_parser.get_nodes_from_documents(nodes)
```

---

## 六、自适应切片 vs Late Chunking 对比

| 维度 | 自适应切片（预切片） | Late Chunking（晚切片） |
|---|---|---|
| **切片时机** | 索引前预切片 | embedding 后再切片 |
| **上下文保留** | 边界切断上下文 | embedding 带全文上下文 |
| **更新成本** | 只重新 embedding 该 chunk | 必须重新 embedding 整篇文档 |
| **实现难度** | 低（LlamaIndex/Docling 原生支持） | 高（需长文本模型 + 自研 adapter） |
| **与你方案的关系** | 可直接接入 | 可选优化（ROI 不高） |

---

## 七、总改动量估算

### 自适应切片集成的改动量

| 方案 | 改动量 | 集成难度 |
|---|---|---|
| Docling HybridChunker（推荐） | ~20-30行 | TRIVIAL |
| LlamaIndex SemanticSplitter（备选） | ~30-50行 | TRIVIAL-MODERATE |

### 与其他改动的关系

**自适应切片是你总改动量中最小的一部分**：
- 命中分布算法：200-400行
- Agent 扩展策略：300-500行
- 自适应切片：20-50行
- **总计：1020-1750行**

---

## 八、关键技术判断

### 判断 1：自适应切片有原生支持，不需要自研

**核验明确**：
- LlamaIndex 有语义自适应（SemanticSplitter）
- Docling 有结构自适应（HybridChunker）
- 两者都是原生支持，改动 trivial

### 判断 2：自适应切片与你核心策略逻辑正交

**核验判断**：
- 自适应切片在 ingestion 层
- 命中分布聚合在 retrieval 层
- Agent 扩展在 orchestration 层
- 三者正交，可并行实施

### 判断 3：推荐 Docling HybridChunker

**核验推荐理由**：
- 自动保留你需要的 citation 元数据
- 结构自适应比语义自适应更稳定
- 改动量最小（20-30行）
- 已核验与树索引兼容

---

## 九、与 Late Chunking 的 ROI 对比

| 项目 | 改动量 | 获益 | ROI | 建议 |
|---|---|---|---|---|
| **自适应切片（Docling）** | 20-30行 | 元数据保留 + 结构自适应 | **高** | **立即实施** |
| **自适应切片（Semantic）** | 30-50行 | 语义连贯 | 中 | 备选 |
| **Late Chunking** | 100-200行 | embedding 带上下文 | **低** | **后置** |

---

## 十、保存原因说明

**这个备份保存的是**：
1. 你之前核验的自适应切片概念澄清
2. LlamaIndex/Docling 的原生能力分析
3. 与树索引的集成路径对比
4. 元数据保留的关键问题
5. 直接可执行的代码框架

**保存理由**：
- 新报告（deep-research-report (2).md）提供了更详细的对比
- 但之前的技术判断和集成建议仍有价值
- 避免被新报告覆盖而丢失之前的精炼结论

**下一步行动**：
- 整合新报告的关键发现（特别是 Chonkie 项目）
- 保持之前的技术判断和推荐方案
- 更新到现有文档体系