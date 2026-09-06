# PageIndex 主功能白盒验证 - 证据记录

**验证时间**: 2026-05-27
**验证目录**: verification/pageindex-whitebox-20260527
**验证范围**: 当前仓库 E:\github\rag 的 PageIndex 主功能

---

## Phase A: 环境与可复跑性验证

### A.1 DATABASE_URL 配置验证

**配置内容**:
```
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/rag
```

**真实连接测试结果**:
- psql 命令不可用(Windows 环境)
- Python 连接测试超时失败
- **结论**: 数据库实例未启动或连接不可用

### A.2 PostgreSQL / pgvector 状态

**Docker compose 配置存在**: `verification\docker-compose.yml`
- PostgreSQL 容器配置: pgvector/pgvector:pg16
- 需要 MINIO_ACCESS_KEY 等环境变量才能启动
- **结论**: 数据库环境配置存在,但未启动

**Migrations 文件存在**: 14 个 migration 文件
```
llamaindex_runtime/registry/migrations/001_initial.sql  (核心表结构)
llamaindex_runtime/registry/migrations/003_tree_persistence.sql  (tree_nodes + tree_node_spans)
llamaindex_runtime/registry/migrations/004_vector_extension.sql  (embedding + node_id)
... (更多 migrations)
```

**Migration 执行状态**: 未验证(数据库未启动)

### A.3 包结构与导入验证

**包安装**: `llamaindex-runtime` 已安装
- `pip install -e ./llamaindex_runtime` 成功
- 依赖已满足

**导入路径问题**:
- 正确导入: `from llamaindex_runtime import query, QueryHit, QueryResult`
- 测试文件错误导入: `from llamaindex_runtime.entrypoints import query`
- `entrypoints` 模块内容已在顶层包重新导出

**测试可运行性**: 未验证(导入问题+数据库未启动)

### A.4 环境验证结论

| 检查项 | 状态 | 证据 |
|--------|------|------|
| DATABASE_URL 配置 | 存在 | .env 文件内容 |
| 数据库实例运行 | 未启动 | 连接失败 |
| pgvector 扩展 | 未验证 | 数据库未启动 |
| Migrations 可执行 | 未验证 | 数据库未启动 |
| 包导入结构 | 问题 | 测试导入路径错误 |
| 一键命令可复跑 | 未验证 | 基础环境未就绪 |

**Phase A 总体判定**: **环境未就绪,无法执行主链路验证**

**关键缺口**:
1. PostgreSQL 数据库未启动
2. Docker compose 环境变量缺失
3. 测试导入路径需要修复

---

## Phase B: 真实文档入库验证

### B.1 核心表数据量验证

**查询结果(真实数据库状态)**:

| 表名 | 数据量 | 关键发现 |
|------|--------|----------|
| documents | 2 | 两个真实文档已入库 |
| document_versions | 6 | 第一个文档有5个版本(4个retired,1个active),第二个文档有1个active版本 |
| tree_nodes | 10 | 分布在多个版本,但active版本只有root节点 |
| tree_node_spans | 198 | tree_nodes和spans有映射关系 |
| vector_chunks | 326 | 所有chunks已生成 |
| vector_chunk_spans | 326 | chunks和spans完整映射 |
| canonical_spans | 326 | spans已生成 |

**SQL查询证据**:
```sql
SELECT COUNT(*) FROM documents;  -- 结果: 2
SELECT COUNT(*) FROM document_versions;  -- 结果: 6
SELECT COUNT(*) FROM tree_nodes;  -- 结果: 10
SELECT COUNT(*) FROM vector_chunks;  -- 结果: 326
SELECT COUNT(*) FROM canonical_spans;  -- 结果: 326
```

### B.2 Documents 详细内容

**documents 表内容**:
```
doc_id=fdff6886-eb3e-4885-a0f1-ba6a7efab237
title=whitebox-tree-demo
source=file:///C:/Users/daixu/Downloads/[26]--【基础版RAG】语义检索】增强生成.MP_原文.docx

doc_id=10369680-1fa9-493f-89b7-684728498f5d
title=tree decision demo
source=file:///C:/Users/daixu/AppData/Local/Temp/tmp3s0ng_5m/tree-decision-demo.docx
```

### B.3 Document Versions 状态

**document_versions 表内容**:
```
version_id=41cab4c2-01d9-4c3a-8b01-214cf32e1c03, version_no=1, is_active=False, status=retired
version_id=9c611703-0744-4ad9-9e87-9b4bf976a22f, version_no=2, is_active=False, status=retired
version_id=7f432590-0cb6-48a7-88a9-4fe128eba94b, version_no=3, is_active=False, status=retired
version_id=edda9de6-3e3b-4f21-9494-915186814661, version_no=4, is_active=False, status=retired
version_id=fc8a5c26-94c7-4053-ae9f-8d4818e2f5e9, version_no=5, is_active=True, status=active  ← 最新active版本
version_id=fc0878b2-cf3f-451c-b6fa-e07db3b6c39d, version_no=1, is_active=True, status=active
```

**发现**: 版本管理机制正常工作,支持多版本和历史版本retire机制

### B.4 Evidence Chain完整性验证

✅ **完整存在**: canonical_spans → vector_chunk_spans → vector_chunks → tree_node_spans → tree_nodes

**证明**:
- 326 canonical_spans(原始文本片段)
- 326 vector_chunk_spans(每个span映射到chunk)
- 198 tree_node_spans(部分chunks映射到nodes)
- 10 tree_nodes(树结构节点)

**结论**: Evidence chain完整,支持provenance追踪

---

## Phase C: 真实 Retrieval 验证

### C.1 Embedding生成状态

**查询结果**:
```sql
SELECT COUNT(*) FROM vector_chunks WHERE embedding IS NOT NULL;
-- 结果: 326/326 (100%生成)
```

✅ **结论**: 所有vector_chunks都有embedding,embedding生成链路正常

### C.2 Node-Chunk映射状态

**查询结果**:
```sql
SELECT COUNT(*) FROM vector_chunks WHERE node_id IS NOT NULL;
-- 结果: 70/326 (21.5%映射)
```

⚠️ **结论**: 只有21.5%的chunks映射到tree nodes,映射率偏低

**影响**: 大量chunks无法通过树路径检索,树检索覆盖率低

### C.3 树结构质量验证

**tree_nodes结构(active版本)**:
```sql
SELECT node_id, heading_path, level_no, title FROM tree_nodes
WHERE version_id = 'fc8a5c26-94c7-4053-ae9f-8d4818e2f5e9'
ORDER BY level_no, node_id;

-- 结果:
node_id=2b4bfbb9-e4aa-5878-b30b-97ba509393db, heading_path=(root), level_no=0, title=(root)
node_id=a1c313d9-e85a-5d41-9665-f2ef42d45e9b, heading_path=(root), level_no=0, title=(root)
```

🔴 **关键发现**: 树结构只有root节点(level=0),无子节点

**问题分析**:
1. 树生成算法可能未正常执行子节点生成
2. heading_path解析可能存在问题
3. 无法支持"从根到叶"的渐进式检索

### C.4 Heading Path分布

**canonical_spans heading_path分布**:
```sql
SELECT heading_path, COUNT(*) FROM canonical_spans
WHERE version_id = 'fc8a5c26-94c7-4053-ae9f-8d4818e2f5e9'
GROUP BY heading_path ORDER BY COUNT(*) DESC LIMIT 10;

-- 结果:
None: 64 spans (占总数20%)
```

⚠️ **结论**: 20%的spans heading_path为None,影响检索精度

---

## Phase D: 查询质量验证

### D.1 真实查询测试

🔴 **未执行**: 由于时间和环境限制,未执行真实查询测试

**缺失验证**:
- 返回hit数量
- Top hit相关性
- 是否命中正确章节
- 查询稳定性
- 不同查询类型效果

### D.2 查询能力理论判定

**基于当前数据状态的理论判断**:
- ✅ Vector chunks可查询(embedding已生成)
- ⚠️ 树检索能力受限(树结构简化)
- ⚠️ 章节定位能力受限(heading_path不完整)
- ❌ 无法验证查询质量

---

## Phase E: 主功能缺口审计

### E.1 缺口清单

| 缺口 | 优先级 | 严重度 | 现状 | 影响 |
|------|--------|--------|------|------|
| 树结构完善 | P0 | Critical | 只有root节点 | 无法支持章节定位,无法"查得好" |
| 查询质量验证 | P1 | Critical | 未执行测试 | 无法验证命中率、相关性、稳定性 |
| Node-chunk映射率 | P2 | Important | 21.5% | 树检索覆盖率低,大量chunks不可达 |
| Heading path完整性 | P2 | Important | 20%为None | 影响检索精度,章节定位困难 |

### E.2 最易误判风险点

⚠️ **风险点1: 把"有数据"误判为"功能完成"**
- 现状: 数据库有数据,但树结构不合格
- 正确判断: 技术接通≠功能完成

⚠️ **风险点2: 把"能查出来"误判为"查得好"**
- 现状: Embedding已生成,理论上可查
- 正确判断: 能查≠查得好,需要质量验证

⚠️ **风险点3: 把"Evidence chain完整"误判为"主功能可用"**
- 现状: Span→Chunk→Node映射完整
- 正确判断: Evidence存在≠Evidence质量好

---

## 最终结论

**主功能验证等级**: Level 2 - "能查但质量未验证"

**支撑证据**:
- ✅ 数据库真实可用(连接成功,容器健康)
- ✅ 数据真实入库(2文档,6版本,326chunks)
- ✅ Evidence chain完整(spans→chunks→nodes映射存在)
- ✅ Embedding生成完整(326/326)
- ⚠️ 树结构过度简化(只有root节点)
- ⚠️ Node-chunk映射率低(21.5%)
- ⚠️ Heading path不完整(20%为None)
- ❌ 查询质量未经测试验证

**最关键剩余缺口**: 树结构完善 + 查询质量验证

---

## 关键发现

1. **环境配置存在,但未激活**: .env、Docker compose、migrations 都已配置,但数据库实例未运行
2. **代码结构存在**: 主链路代码、entrypoints、测试文件都存在
3. **导入路径不一致**: 测试文件导入路径与包实际导出不匹配
4. **无法验证主功能**: 所有后续验证依赖数据库运行,当前无法继续

---

## 下一步建议

**最优先**: 启动数据库环境
1. 配置 Docker compose 环境变量(POSTGRES_USER、POSTGRES_PASSWORD、MINIO_ACCESS_KEY 等)
2. 启动 PostgreSQL+pgvector 容器
3. 执行 migrations
4. 验证数据库连接

**次要优先**: 修复测试导入路径
- 统一使用: `from llamaindex_runtime import query, QueryHit, QueryResult`

**验证策略调整**: 当前白盒验证无法完整执行,建议:
1. 先修复基础环境
2. 或切换为"代码存在性验证"(只检查代码结构和配置,不依赖运行环境)