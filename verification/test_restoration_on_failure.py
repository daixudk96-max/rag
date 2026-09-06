#!/usr/bin/env python3
"""Verify monkeypatch/finalizer restoration even on assertion failure."""
import sys
from types import ModuleType
import pytest

import verification.test_pageindex_workflow as mod

# Global to track restoration
_restoration_tracking = {}

def test_monkeypatch_restores_on_assertion_failure(monkeypatch):
    """Verify monkeypatch restores even if assertion fails."""
    # Pre-seed a module
    original = ModuleType("_test_original")
    original.value = "ORIGINAL"
    monkeypatch.setitem(sys.modules, "_test_original", original)
    
    # Modify it (monkeypatch should restore)
    sys.modules["_test_original"].value = "MODIFIED"
    
    # Force assertion failure
    # pytest will catch this and run teardown (monkeypatch restoration)
    pytest.fail("Intentional failure to test restoration")

def test_finalizer_runs_on_assertion_failure(request):
    """Verify finalizer runs even if assertion fails."""
    leaked = "_test_leaked_finalizer"
    
    # Set up finalizer
    def cleanup():
        _restoration_tracking['finalizer_ran'] = True
        sys.modules.pop(leaked, None)
    
    request.addfinalizer(cleanup)
    
    # Add the leaked module
    sys.modules[leaked] = ModuleType(leaked)
    
    # Mark that we reached this point
    _restoration_tracking['test_started'] = True
    
    # Force assertion failure
    pytest.fail("Intentional failure to test finalizer")

def test_verify_restoration_after_previous_failures():
    """Verify restoration happened after previous tests' failures."""
    # If previous tests ran their finalizers, the tracking should be set
    # Note: This test should run after the above tests
    
    # Check that the test started (proves finalizer was registered)
    if 'test_started' in _restoration_tracking:
        # Finalizer should have run
        assert _restoration_tracking.get('finalizer_ran') is True, \
            "Finalizer must run even after assertion failure"
        # And the leaked module should be gone
        assert "_test_leaked_finalizer" not in sys.modules, \
            "Leaked module must be cleaned up even after assertion failure"
    
def test_boundary_restores_on_assertion_failure(request):
    """Verify _synthetic_package_boundary restores even if assertion fails."""
    # Capture state before
    modules_before = set(sys.modules.keys())
    
    # Execute boundary
    try:
        with mod._synthetic_package_boundary() as tracking:
            # Verify we're inside the boundary
            assert mod._SYNTHETIC_PREFIX in sys.modules
            
            # Force an assertion failure inside the boundary
            # The boundary's finally block should still restore state
            pytest.fail("Intentional failure inside boundary")
    except AssertionError:
        # Expected - pytest converts our fail() to AssertionError
        pass
    
    # After the boundary (even with failure), state should be restored
    modules_after = set(sys.modules.keys())
    
    # Synthetic modules should be gone
    synthetic_prefix = mod._SYNTHETIC_PREFIX
    assert not any(synthetic_prefix in key for key in modules_after), \
        f"Synthetic modules leaked: {[k for k in modules_after if synthetic_prefix in k]}"
    
    # Should have same modules as before
    assert modules_after == modules_before, \
        f"Module set changed: added={modules_after - modules_before}, removed={modules_before - modules_after}"
