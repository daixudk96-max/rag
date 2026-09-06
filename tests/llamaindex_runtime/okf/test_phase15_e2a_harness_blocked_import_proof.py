"""Fresh-process blocked-import proof for Phase 15 E2A harness (Task #132).

This test verifies that importing the test support modules does NOT import
any of the EIGHT blocked modules.

The eight blocked modules are:
1. tests.llamaindex_runtime.okf.test_real_e2a_reconciler_harness_unit
2. tests.llamaindex_runtime.okf.test_real_e2a_reconciler_lifecycle_unit
3. tests.llamaindex_runtime.okf.test_real_e2a_reconciler_acceptance
4. tests.llamaindex_runtime.okf._real_e2a_reconciler_container_cleanup
5. tests.llamaindex_runtime.okf._real_e2a_reconciler_lifecycle
6. tests.llamaindex_runtime.okf._real_e2a_reconciler_types
7. llamaindex_runtime.okf.e2a_disposable_execution
8. verification.phase15-okf-ingestion-pipeline.run_e2a_verification
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BLOCKED_MODULES = [
    "tests.llamaindex_runtime.okf.test_real_e2a_reconciler_harness_unit",
    "tests.llamaindex_runtime.okf.test_real_e2a_reconciler_lifecycle_unit",
    "tests.llamaindex_runtime.okf.test_real_e2a_reconciler_acceptance",
    "tests.llamaindex_runtime.okf._real_e2a_reconciler_container_cleanup",
    "tests.llamaindex_runtime.okf._real_e2a_reconciler_lifecycle",
    "tests.llamaindex_runtime.okf._real_e2a_reconciler_types",
    "llamaindex_runtime.okf.e2a_disposable_execution",
    "verification.phase15-okf-ingestion-pipeline.run_e2a_verification",
]


def test_fresh_process_blocked_import_proof_both_helpers() -> None:
    """Verify importing BOTH helpers does not load blocked modules.

    Uses importlib.util.spec_from_file_location for fresh interpreter import.
    Asserts all eight exact blocked module names absent from sys.modules.
    """
    project_root = Path(__file__).parent.parent.parent.parent

    script = f"""
import sys
import importlib.util
from types import ModuleType
from pathlib import Path

project_root = Path("{project_root.as_posix()}")
sys.path.insert(0, str(project_root))

# Create package chain for relative imports
tests_pkg = ModuleType("tests")
tests_pkg.__path__ = [str(project_root / "tests")]
tests_pkg.__package__ = "tests"
sys.modules["tests"] = tests_pkg

tests_llamaindex_pkg = ModuleType("tests.llamaindex_runtime")
tests_llamaindex_pkg.__path__ = [str(project_root / "tests" / "llamaindex_runtime")]
tests_llamaindex_pkg.__package__ = "tests.llamaindex_runtime"
sys.modules["tests.llamaindex_runtime"] = tests_llamaindex_pkg

tests_okf_pkg = ModuleType("tests.llamaindex_runtime.okf")
tests_okf_pkg.__path__ = [str(project_root / "tests" / "llamaindex_runtime" / "okf")]
tests_okf_pkg.__package__ = "tests.llamaindex_runtime.okf"
sys.modules["tests.llamaindex_runtime.okf"] = tests_okf_pkg

# Import types module using spec_from_file_location
spec_types = importlib.util.spec_from_file_location(
    "tests.llamaindex_runtime.okf._phase15_e2a_harness_types",
    project_root / "tests" / "llamaindex_runtime" / "okf" / "_phase15_e2a_harness_types.py",
    submodule_search_locations=[],
)
types_mod = importlib.util.module_from_spec(spec_types)
types_mod.__package__ = "tests.llamaindex_runtime.okf"
sys.modules["tests.llamaindex_runtime.okf._phase15_e2a_harness_types"] = types_mod
spec_types.loader.exec_module(types_mod)

# Import lifecycle module using spec_from_file_location
spec_lifecycle = importlib.util.spec_from_file_location(
    "tests.llamaindex_runtime.okf._phase15_e2a_harness_lifecycle",
    project_root / "tests" / "llamaindex_runtime" / "okf" / "_phase15_e2a_harness_lifecycle.py",
    submodule_search_locations=[],
)
lifecycle_mod = importlib.util.module_from_spec(spec_lifecycle)
lifecycle_mod.__package__ = "tests.llamaindex_runtime.okf"
sys.modules["tests.llamaindex_runtime.okf._phase15_e2a_harness_lifecycle"] = lifecycle_mod
spec_lifecycle.loader.exec_module(lifecycle_mod)

# Check all eight blocked modules absent
blocked_modules = [
    "tests.llamaindex_runtime.okf.test_real_e2a_reconciler_harness_unit",
    "tests.llamaindex_runtime.okf.test_real_e2a_reconciler_lifecycle_unit",
    "tests.llamaindex_runtime.okf.test_real_e2a_reconciler_acceptance",
    "tests.llamaindex_runtime.okf._real_e2a_reconciler_container_cleanup",
    "tests.llamaindex_runtime.okf._real_e2a_reconciler_lifecycle",
    "tests.llamaindex_runtime.okf._real_e2a_reconciler_types",
    "llamaindex_runtime.okf.e2a_disposable_execution",
    "verification.phase15-okf-ingestion-pipeline.run_e2a_verification",
]

imported_blocked = [mod for mod in blocked_modules if mod in sys.modules]
if imported_blocked:
    sys.exit(1)
sys.exit(0)
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(project_root),
    )

    if result.returncode != 0:
        assert False, "Fresh process blocked-import verification failed"


def test_migration_catalog_import_allowed() -> None:
    """Verify migration_catalog import is allowed (production code, not blocked)."""
    from llamaindex_runtime.registry.migration_catalog import FULL_MIGRATION_CATALOG

    assert len(FULL_MIGRATION_CATALOG) > 0
    assert all(fn.endswith(".sql") for fn in FULL_MIGRATION_CATALOG)

    for blocked in BLOCKED_MODULES:
        assert blocked not in sys.modules
