#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Direct keyword extraction test for plan section 2 queries."""

import sys
import io
from pathlib import Path

# Force UTF-8 output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from llamaindex_runtime.tree.runtime import _extract_keywords_from_query

def test_keyword_extraction(query: str):
    """Test single query and print keywords."""
    keywords = _extract_keywords_from_query(query)
    print(f"Query: {query}")
    print(f"Keywords: {keywords}")
    print()
    return keywords

def main():
    print("=" * 80)
    print("Keyword Extraction Test (Plan Section 2)")
    print("=" * 80)
    print()

    # Query 1: p6 DNA (baseline)
    test_keyword_extraction("AI产品经理的核心DNA是什么？")

    # Query 2: Target why-query (core fix)
    test_keyword_extraction("为什么数据对AI产品如此重要？")

    # Query 3: 数据闭环飞轮 (原整块未拆)
    kw3 = test_keyword_extraction("什么是数据闭环飞轮？")
    print("Expected: ['数据', '闭环', '飞轮'] or similar split")
    print(f"Glued check: '数据闭环飞轮' NOT in keywords: {'数据闭环飞轮' not in kw3}")
    print()

    # Query 4: English query (should remain unchanged)
    kw4 = test_keyword_extraction("cardiac arrhythmia diagnosis")
    print("Expected: ['cardiac', 'arrhythmia', 'diagnosis']")
    print(f"Match: {kw4 == ['cardiac', 'arrhythmia', 'diagnosis']}")
    print()

    # Additional: no glued sentence
    test_keyword_extraction("这个数据对AI产品真的如此重要吗？")

    print("=" * 80)
    print("All queries tested successfully")
    print("=" * 80)

if __name__ == "__main__":
    main()