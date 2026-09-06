"""Workflow primitives for Phase 1 control-plane orchestration.

This module provides minimal Workflow abstractions that wrap existing data-plane
retrieval paths without reimplementing retrieval logic.
"""
from __future__ import annotations

from .hybrid_retrieval_workflow import HybridRetrievalWorkflow

__all__ = ["HybridRetrievalWorkflow"]