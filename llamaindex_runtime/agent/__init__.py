"""Agent orchestration primitives for Phase 1 control-plane.

This module provides minimal tool-facing orchestration that enables
LlamaIndex FunctionAgent to use retrieval workflows as tools.
"""
from __future__ import annotations

from .query_agent import QueryAgent
from .retrieval_tool import RetrievalTool

__all__ = ["QueryAgent", "RetrievalTool"]