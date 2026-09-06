# PageIndex双重调用修复计划

## 问题诊断

**核心问题：**
PageIndexClient.index()方法调用PageIndex donor两次

**调用链分析：**
```
PageIndexClient.index() (llamaindex_runtime/client/pageindex_client.py)
├─ 第205-222行：调用PageIndex donor的md_to_tree → 获取tree_structure ✅ 正确
└─ 第238-242行：调用adapter.index_tree() → 内部再次调用md_to_tree ❌ 重复
```

**证据：**
- 数据库heading_path = "(root)"（说明数据来自TreeGenerator，不是PageIndex）
- verification/pageindex-whitebox-20260527/03-EVIDENCE.md显示树结构只有root节点

## 修复目标

✓ PageIndex donor只被调用一次
✓ tree_nodes使用PageIndex donor的heading_path（不是"(root)"）
✓ 树结构有完整层级（level 0, 1, 2...）
✓ 所有现有测试通过

## TDD验证策略

### 测试1：验证双重调用存在（RED）
```python
# tests/llamaindex_runtime/test_pageindex_double_call.py
def test_pageindex_donor_called_twice_before_fix():
    """证明bug存在：PageIndex donor被调用两次"""
    with mock.patch('pageindex.page_index_md.md_to_tree') as mock_md:
        mock_md.return_value = {'structure': [...], 'doc_name': 'test'}
        
        client.index(file_path='test.md', write_to_registry=True)
        
        # bug状态：应该被调用2次
        assert mock_md.call_count == 2
```

### 测试2：验证修复后只调用一次（GREEN）
```python
def test_pageindex_donor_called_once_after_fix():
    """证明修复成功：PageIndex donor只被调用一次"""
    with mock.patch('pageindex.page_index_md.md_to_tree') as mock_md:
        mock_md.return_value = {'structure': [...]}
        
        client.index(file_path='test.md', write_to_registry=True)
        
        # 修复后：应该只被调用1次
        assert mock_md.call_count == 1
```

### 测试3：验证真实树结构（GREEN）
```python
def test_real_markdown_produces_complete_tree():
    """验证真实Markdown产生完整树结构"""
    # 运行真实入库
    version_id = client.index(file_path=real_md_file, write_to_registry=True)
    
    # 查询数据库
    nodes = registry.query_tree_nodes_by_version(version_id)
    
    # 验证树结构
    assert len(nodes) > 2  # 不是只有root节点
    assert any(n['level_no'] > 0 for n in nodes)  # 有子节点
    assert all(n['heading_path'] != '(root)' for n in nodes)  # 不是"(root)"
```

## 修复方案

**方案：移除第二次调用**

文件：`llamaindex_runtime/client/pageindex_client.py`
位置：第224-244行（Markdown处理路径）

**修改前：**
```python
tree_structure = result.get('structure', [])

if write_to_registry and self.registry:
    registered_doc = self.registry.register_document(...)
    registry_version_id = registered_doc.version_id

    # ❌ 第二次调用PageIndex donor
    self.adapter.index_tree(
        source_path=file_path,  # 这里会再次调用md_to_tree
        version_id=registry_version_id,
        registry=self.registry,
    )
```

**修改后：**
```python
tree_structure = result.get('structure', [])

if write_to_registry and self.registry:
    registered_doc = self.registry.register_document(...)
    registry_version_id = registered_doc.version_id

    # ✅ 直接使用首次获取的tree_structure，不再二次调用
    flat_nodes = self.adapter._flatten_embedded_tree(
        tree_structure,
        version_id=registry_version_id
    )

    # ✅ 直接写入Registry
    self.registry.write_tree(
        version_id=registry_version_id,
        nodes=flat_nodes,
        node_spans=[],  # SpanIndexer后续填充
    )
```

**关键改动：**
- 移除`adapter.index_tree()`调用（消除第二次PageIndex donor调用）
- 直接调用`adapter._flatten_embedded_tree()`（使用首次tree_structure）
- 直接调用`registry.write_tree()`（写入Registry）

## 执行步骤

### Step 1: 创建TDD测试（RED）
```bash
# 创建测试文件
touch tests/llamaindex_runtime/test_pageindex_double_call.py

# 编写测试验证双重调用存在
# 运行测试，确认通过（证明bug存在）
pytest tests/llamaindex_runtime/test_pageindex_double_call.py -v
```

### Step 2: 实现修复
```bash
# 编辑pageindex_client.py
# 移除第238-242行的adapter.index_tree()调用
# 直接使用flatten + write_tree
```

### Step 3: 验证修复（GREEN）
```bash
# 修改测试期望：call_count == 1
# 运行测试，确认通过（证明修复成功）
pytest tests/llamaindex_runtime/test_pageindex_double_call.py -v
```

### Step 4: 真实入库验证
```bash
# 启动PostgreSQL
python scripts/run_pageindex_real_retrieval_workflow.py

# 运行真实入库测试
pytest test_real_integration.py -v

# 查询数据库验证树结构
python -c "
from llamaindex_runtime.config import RuntimeSettings
import psycopg
settings = RuntimeSettings.from_env()
conn = psycopg.connect(settings.database_url)
cursor = conn.cursor()
cursor.execute('SELECT level_no, heading_path FROM tree_nodes ORDER BY level_no')
for row in cursor.fetchall():
    print(f'level={row[0]}, heading={row[1]}')
"
```

**期望结果：**
- level_no有多个值（0, 1, 2...）
- heading_path包含章节标题（如"# 市场概况", "## 竞品分析"）
- 不是"(root)"

### Step 5: 运行现有测试
```bash
# 运行所有PageIndex测试
pytest tests/llamaindex_runtime/test_pageindex*.py -v

# 运行树结构测试
pytest tests/llamaindex_runtime/test_tree*.py -v

# 运行retrieval测试
pytest tests/llamaindex_runtime/test_reasoning_backend_provenance.py -v
pytest test_retrieve_real.py -v
```

### Step 6: 提交修复
```bash
git add llamaindex_runtime/client/pageindex_client.py
git add tests/llamaindex_runtime/test_pageindex_double_call.py

git commit -m "fix(pageindex): eliminate double-call of PageIndex donor

- Remove adapter.index_tree() call in PageIndexClient.index()
- Directly use first tree_structure result
- PageIndex donor now called exactly once
- TDD test proves single call after fix
- Real validation produces complete tree hierarchy"
```

## 验证清单

✓ TDD测试通过（PageIndex donor只调用一次）
✓ 真实入库产生完整树结构（level_no多个值）
✓ heading_path包含真实章节（不是"(root)"）
✓ 所有现有测试通过（功能未破坏）
✓ Git commit成功

## 失败处理

**测试失败：**
- 检查修改是否正确
- 回退git diff重新分析

**真实入库失败：**
- 验证PageIndex donor调用次数
- 检查数据库状态

**现有测试失败：**
- 分析破坏的功能
- 调整修复方案

## 成功标准

最终验证：
1. PageIndex donor只被调用一次（TDD证明）
2. 真实树结构完整（level 0, 1, 2...）
3. heading_path真实章节（不是"(root)"）
4. 所有测试通过