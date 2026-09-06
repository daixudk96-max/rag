# 混合 RAG 中统一身份层、版本层与证据层的外部参照

## 核心判断

你的思路——**不强迫图、向量、树/文档三层共享同一种 chunk 标准，而是把“稳定对齐”下沉到统一的身份层、版本层、证据层**——在我检索到的公开资料里，**没有一个单一、被普遍采用的标准名字**；但它与几类已经存在的主流模式高度同构：一类叫 **provenance / provenance-aware**，强调派生关系、修订关系和可追溯性；一类叫 **multi-view indexing**，强调同一源内容上派生多个索引视图；一类叫 **hierarchical document indexing / Parent-Child / Small2Big**，强调不同粒度的父子视图；还有一类叫 **evidence-centric retrieval / evidence-centric graph**，强调把“证据单元”而不是 chunk 本身作为最终可引用对象。把这些术语拼起来，你的方案最接近的表述不是“another chunking strategy”，而是**一个 versioned provenance mapping layer，服务于 multi-view RAG / GraphRAG**。citeturn8view9turn8view10turn31view4turn30search1turn32view0turn32view1turn8view13

更直接地说：**这更像“数据谱系与证据建模问题”，而不是“该选哪种 chunk 切法”的问题。** urlW3C PROV-Ohttps://www.w3.org/TR/prov-o/ 明确定义了 `wasDerivedFrom`、`wasRevisionOf`、`specializationOf`、`alternateOf` 这类关系；它本身不是 RAG 规范，但它正好提供了你所需的“源对象—版本—派生视图—修订历史”语义骨架。citeturn37view1turn37view2turn37view3turn37view4

## 这个架构最接近的名字

如果一定要给你的模式找一个最贴切、又尽量贴近外部术语的名字，我会把候选词按贴近度排成下面这一组。

**最贴近的总称**，我建议叫 **versioned provenance mapping layer for multi-view RAG**。原因是：`versioned` 对应你关心的 `version_id / content_hash`；`provenance` 对应证据追溯和派生关系；`mapping layer` 对应你要维护的 doc/span/chunk/node/entity 映射；`multi-view RAG` 则准确描述了向量视图、树视图、图证据视图并行存在的现实。这个组合词不是现成标准名，但它和已存在术语最一致。支撑它的术语来源分别来自 PROV、MC-indexing、GraphRAG、以及 evidence-centric / provenance-preserving 论文。citeturn8view9turn37view1turn31view4turn30search1turn32view0turn32view1

**如果偏学术检索术语**，最接近的是 **multi-view indexing**。EMNLP 2024 的 MC-indexing 论文不是图数据库论文，但它非常明确地提出：先按文档内容结构做 chunk，再为同一内容块建立 **raw-text / keywords / summary** 三个视图；检索时不同视图提供互补信号。这个术语和你的“统一底层身份层，上层派生多视图”最接近。citeturn31view1turn31view3turn31view4

**如果偏文档工程与引用稳定性**，最接近的是 **provenance-preserving evidence carrier** 或 **evidence-centric**。urlCogitoRAG 论文页https://arxiv.org/html/2602.15895v1 明说“passages serve as the provenance-preserving evidence carrier”，并把 memory、facts、graph 都建立在 passage 之上；urlEvidenceNet 论文页https://arxiv.org/html/2603.28325v2 则把 evidence record 作为主对象，并用稳定 `evidence_id` 把 record-layer 和 graph-layer 对齐。citeturn32view0turn32view1

**如果偏 GraphRAG/检索系统术语**，最接近的是 **graph-enhanced text indexing**、**structured hierarchical RAG**、或 **hierarchical document indexing**。urlMicrosoft GraphRAGhttps://github.com/microsoft/graphrag 的官方文档把 GraphRAG定义为“structured, hierarchical approach”；urlLightRAGhttps://github.com/HKUDS/LightRAG 论文把自己的方法叫 “graph-enhanced text indexing”；而 urlHaystackhttps://github.com/deepset-ai/haystack 与 urlLlamaIndexhttps://github.com/run-llama/llama_index 的公开文档则明确使用 hierarchical document structure / hierarchical node parser 这套说法。citeturn30search1turn35view1turn39view2turn12view0

我**没有在高置信度的一手资料里看到** `canonical span architecture`、`unified provenance layer`、`versioned provenance mapping for RAG` 被广泛拿来当固定术语；相反，公开资料更常把这件事拆开表述：**provenance**、**multi-view indexing**、**hierarchical retrieval**、**evidence-centric graph**。因此，如果你要给自己的方案命名，最好使用这些外界已经认识的词来组合，而不是押注一个尚未成型的行业定名。citeturn31view4turn30search1turn32view0turn32view1turn8view9turn8view10

## 最接近的公开系统与实现模式

### urlMicrosoft GraphRAGhttps://github.com/microsoft/graphrag

这是我看到的、**离“registry / mapping layer”最近**的公开实现之一。它的索引流水线是可配置工作流，默认输出一组 Parquet 表，同时把 embeddings 写入配置好的 vector store。更关键的是，它公开了**整套映射表 schema**：`documents` 表保存 `text_unit_ids`；`text_units` 表保存 `document_id`，并列出 `entity_ids`、`relationship_ids`、`covariate_ids`；`entities` 和 `relationships` 反过来又保存 `text_unit_ids` 作为证据链接；`communities` 与 `community_reports` 则形成显式层级，并通过 `period` / `size` 字段支持 incremental update merges。换句话说，GraphRAG 的“统一层”不是单个 registry 服务，而是**一组公开的 mapping tables**。citeturn11view2turn9view2turn9view5turn10view0turn10view2

它的强项在于：**文档—文本单元—实体/关系—社区/报告** 这条链路是公开、可遍历、可落地的；图检索、社区层级和向量索引可以同时存在。它的弱项也很清楚：官方输出字段把 `text_unit` 作为证据基本粒度，但**没有把字符级/字节级 canonical span 作为一等公民公开建模**。因此，它更接近“以 text unit 为 canonical evidence unit 的系统”，而不是你设想的“更低一层 span_id 作为所有视图公共锚点”的最终形态。citeturn30search1turn9view2turn10view0

### urlNeo4j LLM Graph Builderhttps://neo4j.com/labs/genai-ecosystem/llm-graph-builder/ 与 urlNeo4j Graph Data Models for RAG Applicationshttps://neo4j.com/blog/developer/graph-data-models-rag-applications/

这套公开资料给出的不是“registry service”，而是**把 registry 直接内嵌进图数据模型**。LLM Graph Builder 明说会把输入文档转成 **lexical graph（documents + chunks）** 与 **entity graph（entities + relationships）**，并在聊天时展示检索所使用的 documents、chunks 和 entities；GraphRAG 模式下，它使用 vector index 找 chunk，再沿实体关系继续扩展。也就是说，它把“文档层 + chunk 层 + 图层 + 向量检索”统一到了一个图底座上。citeturn27view0turn8view7

更重要的是，Neo4j 官方博客进一步把这种统一底座拆成多个**可组合的数据视图**：`Parent-Child` 视图用更小的 child 做 embedding，再返回 parent 文本；`Questions` 视图给 Document 关联“它能回答的问题”；`Topics & Summaries` 视图再从文档相似图上派生社区摘要与主题节点，而且官方明确写了这些模型“can perform individually or in combination”。这非常接近你的“**底层统一身份，上层派生 vector chunks / tree nodes / graph evidence spans**”的路数，只不过 Neo4j 的公开示例通常把这一切都建在图中，而不是拆成你说的三类独立存储。citeturn26view0turn26view1turn26view4

### urlLightRAGhttps://github.com/HKUDS/LightRAG

LightRAG 的论文和部分公开实现线索很接近你的“图+向量对齐、支持增量更新”的目标。论文明确说它采用 **graph-enhanced text indexing** 与 **dual-level retrieval paradigm**，并且重点强调 **incremental update algorithm**：对新文档执行同样的图索引步骤，然后把新旧图做并集，目标是“不需要重建整个索引”。这回答了你问题中的一部分：**图层与检索层不一定要随着每次变更全量重建**。citeturn35view0turn35view1

更有价值的是公开实现线索。Neo4j 的技术拆解文章展示了 LightRAG 会把 chunk embeddings 连同 `full_doc_id`、`file_path`、`content` 一起写入向量索引；GitHub issue 里的实现片段进一步显示，chunk 常用 `compute_mdhash_id(..., prefix="chunk-")` 生成内容哈希式 ID，并在每个 chunk 上保存 `full_doc_id`、`chunk_order_index` 等元数据，甚至允许用户传入**预切片数据**。这说明 LightRAG 事实上已经在做一种“**doc 级稳定锚点 + view-local chunk id + 元数据回链**”的工程模式。它离你差的一步，是**没有把 span_id 明确提升为跨视图、跨重切片的公共键**。citeturn22search12turn36view1turn36view2

### urlLlamaIndexhttps://github.com/run-llama/llama_index

如果看“**一份源文档如何派生出多个层级检索视图，同时保留回溯关系**”，LlamaIndex 是最接近公开工程模板的系统之一。它的 `HierarchicalNodeParser` 明确会把文档切成一组“平铺的层级节点”，同一份文档默认会生成 2048 / 512 / 128 三层 chunk；`AutoMergingRetriever` 则把 **leaf nodes 放在 vector store**，把较大节点放在 **docstore**，检索时根据命中情况递归 merge 回父节点。这个“叶子做召回、父节点做上下文回收”的思路，和你设想的“不同视图可以有不同粒度，但必须统一回到同一身份/证据层”高度一致。citeturn14view0turn14view1

更关键的是它公开了**节点关系与位置锚点**。`NodeRelationship` 包含 `SOURCE`、`PARENT`、`CHILD`、`PREVIOUS`、`NEXT`；`TextNode` 有 `start_char_idx` / `end_char_idx`；节点后处理逻辑会跟踪文档内搜索位置并把 start/end offset 写回节点；而文档管理文档与 API 还说明 `refresh_ref_docs()` 会按 `doc id_` 和 hash 增量刷新，只更新文本或元数据发生变化的文档。换句话说，LlamaIndex 已经把**doc_id、节点关系、字符偏移、内容刷新**这几个关键钩子都公开出来了。citeturn12view3turn12view2turn13view2turn34search6turn34search7

### urlHaystackhttps://github.com/deepset-ai/haystack

Haystack 的价值在于它把你关心的数据模型**写得非常明白**。`HierarchicalDocumentSplitter` 的官方示例直接展示了每个文档块携带 `parent_id`、`children_ids`、`level`、`source_id`、`split_id`、`split_idx_start`。这些字段几乎就是一个现成的“source-to-chunk-to-parent mapping schema”。如果你正在设计 registry/mapping layer，这个 schema 值得直接借鉴。citeturn39view0

它的 `AutoMergingRetriever` 则假设 leaf 节点被索引在 document store / vector store 中，命中多个 sibling leaf 后按阈值直接返回 parent，并且支持的后端包括 PGVector 与 Qdrant。也就是说，Haystack 给出的不是一个抽象概念，而是一个可落地的模式：**leaf 检索视图与 parent 文档视图可以分层存储，通过 parent/children/source 元数据对齐。** citeturn39view1turn39view3

### urlLangChainhttps://github.com/langchain-ai/langchain 的 ParentDocumentRetriever / MultiVectorRetriever

LangChain 的 `ParentDocumentRetriever` 也是典型的“不同 chunk 标准，共享父文档身份”的方案。官方教程明确写道：检索器会先取回小块，再查找这些小块的 parent ID，并返回更大的父文档；parent 可以是整个原文，也可以是更大的分块。它本质上是一种**child embedding view + parent context view**。citeturn8view5

如果看更具体的实现线索，LangChain 的 MultiVector 示例和 issue 讨论里直接出现了 `id_key = "doc_id"`、子文档 `metadata={id_key: doc_ids[i]}`、以及 `docstore.mset(list(zip(doc_ids, docs)))` 这样的模式。这表明 LangChain 默认把**doc_id 作为父子对齐键**，但把更完整的版本层/证据层留给用户自己做。它的公开 issue 也暴露了一个重要现实：重索引时如果 child UIDs 和 parent 更新不同步，父文档可能保持过时状态。这个问题恰好说明你为什么需要把“可引用对象”从视图级 chunk_id 往下沉到更稳定的身份层。citeturn16view3turn15search9

## 这些系统如何处理 doc_id、version_id、span_id、chunk_id、entity_id 对齐

把上面的系统横向比较后，可以看到一个相当清晰的规律：**公开系统几乎都承认需要稳定的上游锚点，但它们把“锚点放在哪一层”做法不同。** GraphRAG 把 `document_id` 与 `text_unit_id` 作为核心映射键，再从 `text_unit` 回链 `entity_ids` 与 `relationship_ids`；Haystack 把 `source_id / parent_id / children_ids / split_idx_start` 暴露到 metadata；LlamaIndex 用 `doc id_`、`source` 关系和 char offsets 把节点绑回源文档；LightRAG 用 `full_doc_id` 把 chunk view 绑回完整文档；LangChain 用 `doc_id` 作为 child-to-parent 的对齐键。citeturn10view2turn39view0turn12view3turn13view2turn22search12turn16view3

**版本层**在公开资料里通常不是通过“统一 version store”呈现，而是通过更新策略、哈希或 PROV 关系表达。urlMicrosoft Learn 的 Advanced RAG 文档https://learn.microsoft.com/en-us/azure/developer/ai/advanced-retrieval-augmented-generation 明确建议跟踪内容版本、做 selective reindexing、delta encoding、snapshotting 和 document version control；LlamaIndex 的 `refresh_ref_docs()` 通过 `document.id_` 配合 hash 判断是否更新；LightRAG 则强调 incremental update 而非全量重建。换言之，**工程上主流做法不是让视图 ID 永久不变，而是让“版本识别”和“受影响对象选择”更稳定**。citeturn38view1turn38view3turn34search7turn35view1

**证据层**的成熟做法，越来越不是“引用 chunk”，而是“引用 passage / text unit / evidence record / source span”。GraphRAG 的 entity 与 relationship 显式保存 `text_unit_ids`；CogitoRAG 把 passage 定义为 provenance-preserving evidence carrier，并要求 memories 与 facts 显式映射回原 passage；EvidenceNet 则把 graph-level 和 record-level 用稳定 `evidence_id` 与 normalized entity id 连接起来。这个趋势很重要：**真正该稳定的是证据对象，不是检索视图对象。** citeturn10view0turn32view0turn32view1

如果把这套经验翻译成你关心的 ID 体系，我会这样理解：

`doc_id` 应该是**逻辑文档身份**，跨版本稳定；  
`version_id` 应该是**文档版本身份**，通常可由规范化内容 hash 或外部版本号给出；  
`span_id` 应该是**证据身份**，绑定到某个文档版本和该版本上的 offset/range；  
`chunk_id` / `tree_node_id` / `graph_evidence_id` 应该是**派生视图身份**，它们都 `wasDerivedFrom` 一个或多个 `span_id`；  
`entity_id` 则不应直接等同于 mention/span，而应通过 mention-to-entity / evidence-to-entity 关系连接。这个结构，与 PROV 的 `wasDerivedFrom`、`wasRevisionOf`、`specializationOf`、`alternateOf` 语义非常吻合。citeturn37view1turn37view2turn37view3turn37view4

## 是否必须统一 chunk 标准

公开资料给出的答案很明确：**不必须，而且大量高质量实现都明确不这么做。** urlMicrosoft Learn 的 Advanced RAG 文档https://learn.microsoft.com/en-us/azure/developer/ai/advanced-retrieval-augmented-generation 直接把 chunking 策略分成按章节、段落、句子、滑窗等多种方式，并单独提出 **Small2Big**：如果按句切，就还要组织好附近句子或整段，以便在召回后补充更大上下文。这本身就说明“检索粒度”和“交给 LLM 的上下文粒度”可以不同。citeturn38view4turn8view6

LangChain 的 `ParentDocumentRetriever` 用小 child 做检索、大 parent 做返回；LlamaIndex 默认就有 2048/512/128 三层 chunk，并把 leaf 节点放进 vector store，父层放进 docstore；Haystack 通过 `block_sizes` 构造多层树，再让 AutoMergingRetriever 在命中多个 leaf 时返回 parent。它们都不是“统一 chunk 标准”，而是**多粒度派生视图**。citeturn8view5turn14view1turn39view0turn39view3

更进一步，Neo4j 官方 RAG 数据模型已经把“存储视图不止一种”说得非常直白：除了 Parent-Child，还有 Questions、Topics & Summaries，而且这些模型可以组合。MC-indexing 论文则从另一个方向说明：先得到一个内容感知的 section chunk，再为同一个 chunk 建立 raw-text、keywords、summary 三个并行视图，不同视图对相关性排序提供互补信息。这个模式几乎就是你说的 **one canonical segmentation + multiple derived views**。citeturn26view0turn26view4turn31view1turn31view3

真正值得注意的不是“能不能多标准切片”，而是**多标准切片时，引用应该绑定到哪一层**。CogitoRAG 和 EvidenceNet 给出的答案都偏向同一方向：**把 passage / evidence record 当成可追溯证据载体，然后从它派生 memories、facts、graph nodes、vector entries。** 所以，如果你问“不同切法如何稳定对齐”，最稳妥的工程答案不是统一所有 chunk，而是**统一可回溯的证据锚点**。citeturn32view0turn32view1

## 对你的方案的判断

我的判断是：**你的“统一身份层 + 版本层 + 证据层”方案是合理的，而且有充分的外部参照依据；它不仅合理，而且比“强行统一 chunk 标准”更接近现在公开系统已经在演化出的方向。** 这点的外部依据主要来自四条线索：一是 PROV 这类成熟的 provenance/version 语义模型；二是 GraphRAG/LightRAG 这类把图层和检索层做派生对齐的系统；三是 LlamaIndex/Haystack/LangChain 这类把叶子检索视图与父文档/层级视图分开的系统；四是 CogitoRAG/EvidenceNet 这类把 evidence/passage 作为稳定证据载体的论文。citeturn8view9turn37view1turn30search1turn35view1turn14view1turn39view0turn8view5turn32view0turn32view1

如果要把你的方案再往“更稳”的方向收敛，我建议采用下面这套最小数据模型。

首先，保留一个**逻辑文档层**：`doc_id` 跨生命周期稳定，不受重切片、重 embedding、重抽图谱影响。其次，单独建一个**版本层**：`version_id` 绑定到规范化后的源文本/源文档内容，并通过 `wasRevisionOf` 保留版本历史；真正的增量刷新以 `doc_id + version_id` 作为入口。再次，把**证据层**下沉到 canonical span：`span_id = (doc_version_id, start_offset, end_offset)`，必要时再附一个 span-level normalized text hash。然后，所有视图对象都只是派生物：`vector_chunk_id`、`tree_node_id`、`graph_evidence_id`、`mention_id` 都只负责服务某种检索/推理视图，并通过映射表连接到一个或多个 `span_id`。这个设计和 PROV、LlamaIndex 的 char offsets、Haystack 的 `split_idx_start`、GraphRAG 的 text-unit evidence links 是一致的。citeturn37view1turn37view2turn13view2turn39view0turn10view0

这会带来一个非常重要的工程效果：**引用永远不指向 chunk_id，而指向 span_id 或 evidence_id。** 这样一来，重切片只会改变 `vector_chunk_id` / `tree_node_id`；重 embedding 只会改变向量索引内容；重抽图谱只会改变 entity/relationship/claim 的派生物；但只要 `doc_version_id` 和 `span_id` 还在，旧引用就不会断。你要维护的只是“派生视图 → canonical span”的映射是否重建成功，而不是“旧 chunk_id 还能不能继续代表证据”。这正是 EvidenceNet 的 record-level 与 graph-level 双层同步、以及 CogitoRAG 的 passage-to-memory/fact 映射想解决的问题。citeturn32view0turn32view1

从存储实现上看，这种架构也完全可行。向量库本身就支持**稳定外部 ID + metadata/payload**：Qdrant 的 point 由 unique ID、vector、payload 组成，upsert 会按相同 ID 覆写；Milvus 的 upsert 要求包含 primary key，而且不会更新主键本身。也就是说，`vector_chunk_id` 可以是向量库主键，但 `doc_id/version_id/span_id` 完全可以作为 payload 或旁路映射表，由你自己的 registry 层统一维护。citeturn28search8turn28search0turn28search2turn28search3turn28search5turn28search9

如果你需要一个对外可沟通、同时又不“发明术语过度”的命名，我建议优先考虑下面两个说法：

**provenance-centric multi-view RAG index**；  
**versioned provenance mapping layer for hybrid RAG / agentic RAG**。  

前者更适合写技术博客和架构图标题，后者更适合写设计文档、schema 文档和实现说明。它们都比 `canonical span architecture` 更容易让外部读者联想到已有文献与工程实践。citeturn31view4turn8view9turn32view0turn32view1

## 开放问题与局限

公开资料里，**真正把“图数据库 + 向量数据库 + 树/文档层 + 独立 registry/mapping layer”四者都作为一等公民、并且完整公开 schema 的系统并不多**。更常见的是两层组合：GraphRAG/LightRAG 强在图+向量，ParentDocument/AutoMerging 强在树+向量，Neo4j LLM Graph Builder 则把 document/chunk/entity 统一放进单图底座，而不是单独抽出 registry 服务。citeturn30search1turn35view1turn39view3turn8view5turn27view0

另外，**跨 parser / OCR / normalization 版本保持 span_id 稳定**，在公开系统里仍然不是被完全解决的标准问题。LlamaIndex 和 Haystack 已经暴露了字符偏移与 split 起点，但它们默认都依赖“当前版本文本”的位置；一旦文本规范化策略改变，你仍然需要额外的 old-span → new-span 对齐策略。也就是说，你的 `span_id` 设计要成功，前提不是只有 span schema，还包括一份**严格的规范化契约**。citeturn13view2turn39view0

最后，**entity_id 的稳定性不能只靠 chunk/span 层解决**。EvidenceNet 之所以能把 record-level 和 graph-level 稳定连起来，是因为它除了 evidence_id 之外，还做了 normalized entity identifiers；GraphRAG、LightRAG 这类系统如果要跨重抽图谱保持 entity_id 稳定，最终仍然需要一层明确的 entity resolution / canonicalization 策略。换句话说，`span_id` 解决的是“证据稳定引用”，而 `entity_id` 稳定还需要另一套规范。citeturn32view1turn10view0turn22search12