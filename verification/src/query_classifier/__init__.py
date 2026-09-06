from __future__ import annotations


def classify_query(query: str) -> str:
    q = query.strip()
    if not q:
        return "vector"
    if any(ch.isdigit() for ch in q):
        return "keyword"
    if any(sym in q for sym in ("-", "/", "_", ".")):
        return "keyword"
    if len(q) <= 8:
        return "keyword"
    return "vector"
