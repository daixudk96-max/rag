"""
Phase 14 Business Queries — 基于 deep-research-report (1).md 的真实业务问题

文档主题：混合 RAG 开源项目深度研究（排除 GraphRAG）
涵盖项目：KAG、NexusRAG、LlamaIndex、LightRAG、RAPTOR/HIRO、R2R、Cognee
核心维度：A-F 六项能力（知识图谱、向量数据库、树状层级索引、多阶段检索、命中回映、Agent扩展）
"""

BUSINESS_QUERIES = [
    # Q1: 核心结论类
    {
        "id": "Q1",
        "query": "研究报告的核心结论是什么？哪个项目最接近完整需求？",
        "expected_focus": ["执行摘要", "NexusRAG", "最接近开箱即用"],
        "level": "L1_summary",
    },
    # Q2: 项目对比类
    {
        "id": "Q2",
        "query": "KAG 和 NexusRAG 在知识图谱能力上有什么区别？",
        "expected_focus": ["KAG", "NexusRAG", "知识图谱", "mutual indexing"],
        "level": "L2_comparison",
    },
    # Q3: 能力维度类
    {
        "id": "Q3",
        "query": "A-F 六项能力中，哪几项在开源生态里最稀缺？为什么？",
        "expected_focus": ["C", "E", "F", "树状层级", "命中回映", "Agent扩展"],
        "level": "L2_capability",
    },
    # Q4: 技术架构类
    {
        "id": "Q4",
        "query": "LlamaIndex 如何实现向量命中回映到树节点？",
        "expected_focus": ["LlamaIndex", "AutoMergingRetriever", "RecursiveRetriever", "parent node"],
        "level": "L3_technical",
    },
    # Q5: 实施建议类
    {
        "id": "Q5",
        "query": "如果要快速做 POC，应该选择哪个项目？需要补哪些模块？",
        "expected_focus": ["NexusRAG", "POC", "5-10人日", "图优先约束", "树节点聚合"],
        "level": "L2_recommendation",
    },
    # Q6: 项目细节类
    {
        "id": "Q6",
        "query": "LightRAG 支持哪些向量数据库后端？",
        "expected_focus": ["LightRAG", "FAISS", "Milvus", "Qdrant", "OpenSearch", "Postgres"],
        "level": "L2_detail",
    },
    # Q7: 模块拼接类
    {
        "id": "Q7",
        "query": "模块拼接蓝图中的图触发向量检索策略是什么？",
        "expected_focus": ["图触发", "向量检索", "过滤条件", "图先约束"],
        "level": "L3_architecture",
    },
    # Q8: 项目评价类
    {
        "id": "Q8",
        "query": "RAPTOR 和 HIRO 的核心贡献是什么？它们适合作为什么角色？",
        "expected_focus": ["RAPTOR", "HIRO", "树构建", "分支剪枝", "结构后处理层"],
        "level": "L2_role",
    },
    # Q9: 工程量估算类
    {
        "id": "Q9",
        "query": "KAG 增强实现需要多少人日？适合什么场景？",
        "expected_focus": ["KAG", "20-35人日", "专业域问答", "逻辑推理"],
        "level": "L2_estimation",
    },
    # Q10: 互索引机制类
    {
        "id": "Q10",
        "query": "KAG 的 mutual indexing 结构是什么？它如何连接图谱和原文？",
        "expected_focus": ["KAG", "mutual indexing", "Knowledge and Chunk", "图文互索引"],
        "level": "L3_mechanism",
    },
    # Q11: NexusRAG 结构保留类
    {
        "id": "Q11",
        "query": "NexusRAG 如何保留文档结构？它保留了哪些元数据？",
        "expected_focus": ["NexusRAG", "heading path", "page number", "结构化分块"],
        "level": "L2_metadata",
    },
    # Q12: Agent 扩展类
    {
        "id": "Q12",
        "query": "Agent 自主扩展机制的建议顺序是什么？",
        "expected_focus": ["Agent", "父节点摘要", "子节点展开", "兄弟节点", "相邻扩展"],
        "level": "L3_workflow",
    },
    # Q13: 判定标准类
    {
        "id": "Q13",
        "query": "A-F 六项能力的判定标准是什么？E 项必须看到什么机制才判为是？",
        "expected_focus": ["判定标准", "E项", "向量命中回映", "后处理机制"],
        "level": "L2_criteria",
    },
    # Q14: 项目成熟度类
    {
        "id": "Q14",
        "query": "从仓库成熟度来看，哪个项目最稳？哪个最适合当主底座？",
        "expected_focus": ["LlamaIndex", "LightRAG", "成熟度", "主底座"],
        "level": "L1_maturity",
    },
    # Q15: 检索范围类
    {
        "id": "Q15",
        "query": "本次检索排除了哪些 GraphRAG 项目？为什么排除？",
        "expected_focus": ["GraphRAG", "microsoft/graphrag", "排除", "显式排除"],
        "level": "L1_scope",
    },
    # Q16: 向量库对比类
    {
        "id": "Q16",
        "query": "NexusRAG 和 LightRAG 分别使用什么向量数据库？",
        "expected_focus": ["NexusRAG", "ChromaDB", "LightRAG", "FAISS/Milvus/Qdrant"],
        "level": "L2_backend",
    },
    # Q17: 树节点聚合公式类
    {
        "id": "Q17",
        "query": "向量命中回映树节点的聚合公式建议是什么？",
        "expected_focus": ["node_score", "depth_weight", "coverage_weight", "聚合公式"],
        "level": "L3_formula",
    },
    # Q18: 四个自研模块类
    {
        "id": "Q18",
        "query": "必须自研的四个模块是什么？按什么顺序优先排？",
        "expected_focus": ["四个模块", "chunk映射", "图触发路由", "树节点聚合", "Agent扩展器"],
        "level": "L2_priority",
    },
    # Q19: 最终执行顺序类
    {
        "id": "Q19",
        "query": "最终执行顺序建议是什么？",
        "expected_focus": ["NexusRAG验证", "KAG提升", "LlamaIndex平台化", "执行顺序"],
        "level": "L1_sequence",
    },
    # Q20: 贴合度排序类
    {
        "id": "Q20",
        "query": "需求贴合度综合判断的排序是什么？依据是什么？",
        "expected_focus": ["贴合度排序", "NexusRAG", "KAG", "LlamaIndex", "依据"],
        "level": "L1_ranking",
    },
]