"""PageIndex client integration.

提供EnhancedPageIndexClient - PageIndex workspace consumer (non-authoritative).

核心功能：
- PageIndexClient移植（workspace管理、lazy-load）
- Registry读取（消费canonical tree nodes/spans/chunks）
- 工具函数移植（get_document, get_document_structure, get_page_content）

SECURITY CONSUMER BOUNDARY:
- PageIndex is a CONSUMER of canonical E2a tree data, NOT an author
- Client.index() CANNOT write canonical tree to registry
- Use E2a ingestion pipeline for canonical tree authoring
- When version_id provided, client queries canonical state (read-only)

使用示例：
```python
from llamaindex_runtime.client import EnhancedPageIndexClient
from llamaindex_runtime.registry import PostgresRegistry
from llamaindex_runtime.config import RuntimeSettings

registry = PostgresRegistry(settings)
client = EnhancedPageIndexClient(registry, settings)

# 索引文档（workspace-only, non-authoritative）
doc_id = client.index("doc.pdf", write_to_registry=False)  # write_to_registry has NO effect

# 获取文档元数据
metadata = client.get_document(doc_id)

# 获取树结构
structure = client.get_document_structure(doc_id)

# 提取页面内容
content = client.get_page_content(doc_id, pages="5-7")
```
"""

from .pageindex_client import EnhancedPageIndexClient
from .retrieve import get_document, get_document_structure, get_page_content
from .utils import remove_fields, get_number_of_pages

__all__ = [
    'EnhancedPageIndexClient',
    'get_document',
    'get_document_structure',
    'get_page_content',
    'remove_fields',
    'get_number_of_pages',
]