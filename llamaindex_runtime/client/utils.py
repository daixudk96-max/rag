"""PageIndex utils移植.

移植关键工具函数：
- remove_fields：递归删除字典中的指定字段
- get_number_of_pages：获取PDF页数

其他工具函数（PageIndex原版）暂不移植（LLM调用等）。
"""

import PyPDF2
from typing import Any, List


def get_number_of_pages(pdf_path: str) -> int:
    """Return total page count for a PDF file."""
    pdf_reader = PyPDF2.PdfReader(pdf_path)
    num = len(pdf_reader.pages)
    return num


def remove_fields(data: Any, fields: List[str] = ['text']) -> Any:
    """
    Recursively remove specified fields from a dict/list structure.

    Args:
        data: dict or list structure
        fields: list of field names to remove (default: ['text'])

    Returns:
        Structure with specified fields removed

    Example:
        >>> data = {'a': 1, 'text': 'long text', 'nodes': [{'text': 'nested'}]}
        >>> remove_fields(data, ['text'])
        {'a': 1, 'nodes': []}
    """
    if isinstance(data, dict):
        return {k: remove_fields(v, fields)
            for k, v in data.items() if k not in fields}
    elif isinstance(data, list):
        return [remove_fields(item, fields) for item in data]
    return data