#!/usr/bin/env python
"""Measure keyword extraction latency."""

import time
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from llamaindex_runtime.tree.runtime import _extract_keywords_from_query

# Test queries
queries = [
    "为什么数据对AI产品如此重要？",
    "AI产品经理的核心DNA是什么？",
    "什么是数据闭环飞轮？为什么它重要？",
    "抖音如何利用用户行为数据优化推荐？",
]

# Measure current regex-based approach
print("Current regex approach:")
start = time.time()
for _ in range(100):  # 100 iterations
    for query in queries:
        keywords = _extract_keywords_from_query(query)
elapsed_regex = time.time() - start
print(f"  Total time (400 calls): {elapsed_regex:.4f}s")
print(f"  Per call: {elapsed_regex / 400:.4f}s")
print(f"  Per call (ms): {elapsed_regex / 400 * 1000:.2f}ms")
print()

# Try jieba if available
try:
    import jieba

    print("jieba approach:")
    # Initialize jieba (lazy load happens on first call)
    _ = jieba.cut("测试初始化")

    # Measure jieba keyword extraction
    def extract_with_jieba(query: str) -> list[str]:
        """Extract keywords using jieba."""
        stopwords = {"的", "是", "什么", "有", "在", "和", "了", "与", "及", "等",
                     "为什么", "如何", "怎么", "如此"}
        words = jieba.cut(query)
        keywords = []
        for word in words:
            token = word.strip()
            if len(token) >= 2 and token not in stopwords and token not in keywords:
                keywords.append(token)
        return keywords

    start = time.time()
    for _ in range(100):  # 100 iterations
        for query in queries:
            keywords = extract_with_jieba(query)
    elapsed_jieba = time.time() - start
    print(f"  Total time (400 calls): {elapsed_jieba:.4f}s")
    print(f"  Per call: {elapsed_jieba / 400:.4f}s")
    print(f"  Per call (ms): {elapsed_jieba / 400 * 1000:.2f}ms")
    print()

    # Compare
    print("Comparison:")
    print(f"  jieba overhead: {(elapsed_jieba - elapsed_regex):.4f}s for 400 calls")
    print(f"  jieba overhead per call: {(elapsed_jieba - elapsed_regex) / 400 * 1000:.2f}ms")
    print(f"  jieba is {elapsed_jieba / elapsed_regex:.2f}x slower than regex")
    print()

    # Show actual extraction results
    print("Example extraction results:")
    for query in queries:
        regex_kw = _extract_keywords_from_query(query)
        jieba_kw = extract_with_jieba(query)
        print(f"  Query: {query}")
        print(f"    Regex: {regex_kw}")
        print(f"    jieba:  {jieba_kw}")
        print()

except ImportError:
    print("jieba not installed, skipping jieba measurement")
    print("To install: pip install jieba")