"""Pytest configuration for worktree testing.

This conftest ensures tests load modules from the worktree, not the main repo.
"""
import sys
from pathlib import Path

# Add worktree root to Python path BEFORE main repo
worktree_root = Path(__file__).parent.parent
if str(worktree_root) not in sys.path:
    sys.path.insert(0, str(worktree_root))