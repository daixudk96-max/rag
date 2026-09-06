# Verified Project Matrix

Updated: 2026-05-08  
Output file: `E:\github\rag\verified-project-matrix.md`

## Scope

This file verifies every named project/framework/repo mentioned across these four local documents:

1. `deep-research-report.md`
2. `deep-research-report (1).md`
3. `# 🔍 混合RAG系统深度搜索报告：从图谱到向量再到树状结构的智能体框架.ini`
4. `结合非向量树状知识库、知识图谱与向量数据库的三合一Agentic RAG架构深度.ini`

Verification method:
- Parallel **Sonnet** subagents
- Official GitHub repos/docs first
- Reputable secondary sources only when needed
- Strict interpretation: only mark `yes` when public docs/repo text clearly support the claim

## Legend

Columns:
- **KG** = explicit knowledge graph construction/retrieval
- **Vec** = explicit vector DB/index support
- **Tree** = explicit non-vector tree/hierarchical KB or stable heading/path hierarchy
- **Parse** = structured ingestion/layout/structure preservation
- **Cas** = multi-stage or graph-constrained retrieval
- **Map** = hit-to-parent/original-position/back-mapping or citation-path support
- **Agent** = autonomous expansion/planning/tool-style retrieval behavior

Values:
- `yes`
- `partial`
- `no`
- `unclear`

## Important corrections

1. **BookRAG is publicly available on GitHub** (`sam234990/BookRAG`), so the earlier claim "未开源" was too strong.  
   But it has **no license file**, so it is **public code, not safely classifiable as open-source**.
2. **LlamaParse is not open-source as a parser service**. The public SDK/client exists, but the parser itself is a proprietary cloud product.
3. **self-learning-ai-agent** could **not** be verified as one single official public repo by that exact name.
4. **RAGFlow** is stronger than the earlier low-confidence classification suggested: public Apache-2.0 repo, with KG, parsing, map/citation behavior, and agent orchestration claims in product/docs.
5. **HippoRAG** should **not** be treated as clear `Vec=yes`; public docs still center on KG/PageRank-style retrieval, not a standard vector DB story.
6. **NexusRAG** is public and useful, but it is a **small personal repo**, not an institutional platform.
7. Several items previously treated as “not found / uncertain” do in fact exist publicly, especially **BookRAG** and **pdichone/knowledge-graph-rag**.

---

## A. Core and near-core RAG platforms

| Project | Verified repo/org | Public repo? | Open-source/license? | KG | Vec | Tree | Parse | Cas | Map | Agent | Verified note |
|---|---|---|---|---|---|---|---|---|---|---|---|
| KAG | `OpenSPG/KAG` | yes | yes / Apache-2.0 | yes | yes | partial | partial | yes | yes | partial | Mutual indexing is confirmed; tree is DIKW/schema hierarchy, not a standalone tree index. |
| NexusRAG | `LeDat98/NexusRAG` | yes | yes / MIT | yes | yes | no | yes | partial | partial | yes | Public personal repo; page-aware citations are real, but tree should not be overstated. |
| LlamaIndex | `run-llama/llama_index` | yes | yes / MIT | yes | yes | yes | yes | yes | yes | yes | Strongest verified modular base across all dimensions. |
| LightRAG | `HKUDS/LightRAG` | yes | yes / MIT | yes | yes | no | partial | partial | partial | no | Dual-level retrieval is real, but not the same as full cascade + agentic system. |
| VectorInstitute/kg-rag | `VectorInstitute/kg-rag` | yes | yes / MIT | yes | yes | no | no | partial | partial | no | Narrower than some summaries suggested; strongly research/baseline-oriented. |
| Cognee | `topoteretes/cognee` | yes | yes / Apache-2.0 | yes | yes | unclear | partial | partial | partial | yes | Strong as agent memory; explicit tree KB is not confirmed. |
| Psi-RAG | `Newiz430/Psi-RAG` | yes | yes / MIT | no | partial | yes | partial | yes | no | yes | Strong tree + agentic retrieval; no verified KG module. |
| BookRAG | `sam234990/BookRAG` | yes | public code / **no license stated** | partial | no | yes | yes | partial | no | yes | Important correction: repo exists publicly, but licensing is unresolved. |
| RAPTOR | `parthsarthi03/raptor` | yes | yes / MIT | no | partial | yes | no | no | no | no | Pure recursive tree retrieval; no KG/agent/citation mapping. |
| HIRO | `krishgoel/hiro` | yes | yes / MIT | no | partial | yes | no | partial | no | no | Query-optimization layer on top of RAPTOR-style tree retrieval. |
| HiRAG | `hhy-huang/HiRAG` | yes | yes / MIT | yes | yes | partial | no | partial | no | no | Uses KG + vector search; hierarchy is more graph-clustered than a stable tree KB. |
| R2R | `SciPhi-AI/R2R` | yes | yes / MIT | yes | yes | no | yes | partial | yes | yes | Strong platform/API with citation behavior; no verified tree index. |

---

## B. Supporting / edge / composite projects

| Project | Verified repo/org | Public repo? | Open-source/license? | KG | Vec | Tree | Parse | Cas | Map | Agent | Verified note |
|---|---|---|---|---|---|---|---|---|---|---|---|
| HiSem-RAG | `CharmingDaiDai/HiSem-RAG` (partial verification) | partial | unclear | no | partial | yes | partial | partial | unclear | no | Appears to be about hierarchical semantic tree retrieval; repo/live-status needs more direct confirmation. |
| self-learning-ai-agent | no exact official repo verified | no | n/a | unclear | unclear | unclear | unclear | unclear | unclear | unclear | Most likely a descriptive label in the local doc, not a cleanly verified single project. |
| HybridRAG | `sarabesh/HybridRAG` (author link uncertain) | partial | unclear | yes | yes | no | no | partial | unclear | no | No authoritative single repo was confirmed as “the” official implementation. |
| RAGFlow | `infiniflow/ragflow` | yes | yes / Apache-2.0 | yes | yes | partial | yes | partial | yes | yes | Stronger and more complete than earlier low-confidence notes implied. |
| KG2RAG | `nju-websoft/KG2RAG` | yes | yes / GPL-3.0 | yes | partial | no | no | yes | partial | no | Strong KG-guided organization/retrieval research component. |
| HippoRAG | `OSU-NLP-Group/HippoRAG` | yes | yes / MIT | yes | no | no | no | partial | partial | no | Public docs do not support a clear vector DB story. |
| trustgraph | `trustgraph-ai/trustgraph` | yes | yes / Apache-2.0 | yes | yes | no | yes | no | partial | yes | Better treated as graph-native context/agent platform than as tree KB system. |
| autoflow | `pingcap/autoflow` | yes | yes / Apache-2.0 | yes | yes | no | no | no | no | no | More limited than a full agentic Graph/KG platform. |
| context-aware-rag | `NVIDIA/context-aware-rag` | yes | yes / Apache-2.0 | yes | yes | no | yes | yes | no | partial | Planner/tool behavior exists, but not a full autonomous expansion story. |
| pdichone/knowledge-graph-rag | `pdichone/knowledge-graph-rag` | yes | yes / license unclear | yes | unclear | no | partial | no | no | no | Important correction: exact repo exists publicly; vector/cascade/agent claims are not verified. |
| HMRAG | `ocean-luna/HMRAG` | yes | yes / MIT | yes | yes | yes | no | yes | no | yes | Better than expected on tree/cascade/agent, but still not a citation-mapping system. |
| A-RAG | `Ayanami0730/arag` | yes | yes / license unclear | no | partial | yes | no | yes | no | yes | Tree + ReAct-style retrieval present; no verified KG layer. |

---

## C. Explicit GraphRAG / GraphRAG-derived line

These projects are public, but exclusion is usually justified if the screening rule is “exclude explicit GraphRAG identity or close GraphRAG-derived variants.”

| Project | Verified repo/org | Public repo? | Open-source/license? | KG | Vec | Tree | Parse | Cas | Map | Agent | Exclude note |
|---|---|---|---|---|---|---|---|---|---|---|---|
| microsoft/graphrag | `microsoft/graphrag` | yes | yes / MIT | yes | yes | partial | yes | no | yes | no | explicit GraphRAG |
| tigergraph/graphrag | `tigergraph/graphrag` | yes | yes / Apache-2.0 | yes | yes | no | yes | no | no | no | explicit GraphRAG |
| automataIA/graphrag-rs | `automataIA/graphrag-rs` | yes | yes / MIT | yes | partial | no | partial | no | partial | no | GraphRAG-derived |
| flexible-graphrag | `stevereiner/flexible-graphrag` | yes | yes / Apache-2.0 | yes | yes | no | yes | no | no | partial | explicit GraphRAG |
| ms-graphrag-neo4j | `neo4j-contrib/ms-graphrag-neo4j` | yes | yes / MIT | yes | partial | partial | yes | no | partial | no | GraphRAG-derived |
| graph-rag-agent | `1517005260/graph-rag-agent` | yes | yes / MIT | yes | partial | no | yes | no | no | yes | explicit GraphRAG |
| repo-graphrag-mcp | `yumeiriowl/repo-graphrag-mcp` | yes | yes / MIT | yes | partial | partial | yes | no | no | partial | GraphRAG-derived |
| apecloud/ApeRAG | `apecloud/ApeRAG` | yes | yes / Apache-2.0 | yes | yes | no | yes | no | no | yes | explicit GraphRAG |

---

## D. Component projects mentioned in the docs

These are real public projects, but they are **components**, not complete RAG platforms.

| Project | Verified repo/org | Public repo? | Open-source/license? | Role | Verified note |
|---|---|---|---|---|---|
| MinerU | `opendatalab/MinerU` | yes | Apache-2.0-style license with extra terms; GitHub metadata may show AGPL mismatch | layout-aware document parser | Important correction: license presentation is messy; repo changed internals partly to avoid AGPL concerns. |
| Docling | `docling-project/docling` | yes | yes / MIT | document parser | Public OSS project; not limited to PDF. |
| Marker | `datalab-to/marker` | yes | yes / GPL-3.0 (commercial dual license available) | PDF-to-Markdown/JSON parser | More specific than “generic parser.” |
| LlamaParse | `run-llama/llama_parse` | partial | proprietary cloud service; SDK/client public | cloud document parsing service | Important correction: this is commonly mislabeled as OSS, but the parser itself is not open-source. |
| LangGraph | `langchain-ai/langgraph` | yes | yes / MIT | agent orchestration framework | Not a parser; should be classified only as an agent/workflow component. |
| **Chonkie** | `chonkie-inc/chonkie` | yes | yes / MIT | **dedicated chunking framework** | Important new finding from latest research: specialized for chunking with SemanticChunker/LateChunker/NeuralChunker/SlumberChunker; has OverlapRefinery; most complete chunking-only solution. |
| **semantic-text-splitter** | `benbrandt/text-splitter` | yes | yes / MIT | **structure-aware chunking library** | New finding: Rust-based; uses semantic hierarchy (sentence/paragraph/heading/tree-sitter) for chunking; strongest strict token control; no retrieval integration. |

---

## Recommended corrected shortlist

### Best primary bases
- KAG
- NexusRAG
- LlamaIndex
- R2R

### Best tree / post-processing supplements
- RAPTOR
- HIRO
- HiSem-RAG (with repo/status caution)
- Psi-RAG

### Best component references
- LightRAG
- RAGFlow
- KG2RAG
- HMRAG
- context-aware-rag
- pdichone/knowledge-graph-rag

### Keep excluded when rule is “no explicit GraphRAG”
- microsoft/graphrag
- tigergraph/graphrag
- flexible-graphrag
- graph-rag-agent
- ApeRAG
- plus the clearly GraphRAG-derived variants

## Net takeaway

The biggest factual correction from the original local writeups is this:
- **Some projects previously treated as “not open source / not found” are actually public**, especially **BookRAG** and **pdichone/knowledge-graph-rag**.
- But “public repo exists” is **not** the same thing as “clean open-source project with verified licensing and full claimed capability set.”

So the corrected hierarchy is:
1. **Public + strong + verified**: KAG, LlamaIndex, R2R, LightRAG, RAGFlow
2. **Public + useful but narrower / more partial than earlier summaries suggested**: NexusRAG, kg-rag, Cognee, HippoRAG, context-aware-rag
3. **Public but should be carefully reclassified**: BookRAG, pdichone/knowledge-graph-rag, HMRAG, A-RAG
4. **Component-only, not full platforms**: MinerU, Docling, Marker, LlamaParse, LangGraph
5. **Explicit GraphRAG / GraphRAG-derived**: keep excluded if that rule still stands
