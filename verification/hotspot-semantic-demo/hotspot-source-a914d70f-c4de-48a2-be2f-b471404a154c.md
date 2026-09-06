# PageIndex 完整功能分析与集成方案

## PageIndex vs 当前实现对比

### 功能矩阵
PageIndex 当前实现 功能矩阵 对比：PageIndex 支持目录树导航、页面级结构、LLM 选择节点；当前实现需要保留 provenance、tree_node_spans、vector_chunks 和 evidence chain。

### Token 消耗对比
PageIndex 当前实现 Token 消耗对比：热点子树先定位父节点，然后多跳下钻，只返回有 chunk evidence 的叶子内容，避免返回父节点全文。

## 无关章节
这部分讨论部署清单、环境变量和日志格式，和 PageIndex 功能矩阵对比无关。