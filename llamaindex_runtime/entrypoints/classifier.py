"""Query classifier for routing queries to the appropriate retrieval backend.

Pure function with no external dependencies. Routes to 'keyword', 'vector',
or 'tree' based on simple heuristics: short/code-like/symbol-heavy queries
go to keyword, structural/hierarchy queries go to tree, and natural-language
queries go to vector.
"""
from __future__ import annotations

import re

# CJK Unified Ideographs range (U+4E00 - U+9FFF) plus common extensions
_CJK_PATTERN = re.compile(r"[一-鿿㐀-䶿]")


def classify_query(query: str) -> str:
    """Classify a query string into a retrieval mode.

    Parameters
    ----------
    query:
        The raw query string. Whitespace is stripped before classification.

    Returns
    -------
    str
        One of ``"keyword"``, ``"vector"``, ``"tree"``.
    """
    q = query.strip()
    if not q:
        return "vector"

    word_count = len(q.split())

    ql = q.lower()

    # Structural / hierarchy queries route to tree
    tree_signals = (
        "section structure",
        "document outline",
        "table of contents",
        "chapter hierarchy",
    )
    if any(signal in ql for signal in tree_signals):
        return "tree"

    # Long natural-language queries (6+ words) route to vector
    # even if they contain digits or symbols -- the semantic intent
    # dominates over code-like tokens in a full sentence.
    if word_count >= 6:
        return "vector"

    # CJK text does not use spaces between words. A string of 6+
    # CJK characters (without spaces) is treated as a natural-language
    # (vector) query, since keyword search on short CJK terms is
    # covered by the code-like heuristics below.
    cjk_char_count = len(_CJK_PATTERN.findall(q))
    if cjk_char_count >= 6 and word_count <= 1:
        return "vector"

    # Code-like / symbol-heavy / very short queries route to keyword
    if any(ch.isdigit() for ch in q):
        return "keyword"
    if any(sym in q for sym in ("-", "/", "_", ".")):
        return "keyword"
    if len(q) <= 16:
        return "keyword"

    # Medium natural-language queries route to vector
    return "vector"
