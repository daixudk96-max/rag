"""Summary index module for P5 multi-view indexing.

Provides a first-class summary view/index separate from tree node summary_text:
- SummaryIndex: builds summary entities from tree nodes
- retrieve_summary_hits: keyword search over summaries
- Registry integration: persist and query summaries
"""
from .index import SummaryIndex, retrieve_summary_hits

__all__ = [
    "SummaryIndex",
    "retrieve_summary_hits",
]