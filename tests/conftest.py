"""Pytest configuration for worktree testing.

This conftest ensures tests load modules from the worktree, not the main repo.
"""

import sys
from pathlib import Path

# Add worktree root to Python path BEFORE main repo
worktree_root = Path(__file__).parent.parent
if str(worktree_root) not in sys.path:
    sys.path.insert(0, str(worktree_root))


def pytest_configure(config):  # noqa: ANN001
    """Register custom markers for test selection."""
    config.addinivalue_line(
        "markers",
        "live_st: live SentenceTransformers integration tests (model download required)",
    )
    config.addinivalue_line(
        "markers",
        "disposable_db: tests that require a separately authorized disposable PostgreSQL/Docker target",
    )
    config.addinivalue_line(
        "markers", "integration: integration tests requiring external services"
    )
