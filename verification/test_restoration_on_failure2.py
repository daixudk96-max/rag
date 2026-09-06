#!/usr/bin/env python3
"""Verify monkeypatch/finalizer restoration even on assertion failure - follow-up check."""
import sys
from types import ModuleType
import pytest

# This test must run AFTER the test that fails
def test_verify_monkeypatch_restored_after_failure():
    """Verify monkeypatch restored the module after the previous test failed."""
    # The previous test used monkeypatch to set _test_original
    # After the test (even though it failed), monkeypatch should have restored
    
    # If restoration happened, _test_original should NOT be in sys.modules
    # (because monkeypatch restores the original state, which was that it didn't exist)
    assert "_test_original" not in sys.modules, \
        "monkeypatch must restore sys.modules even after assertion failure"
    
def test_verify_finalizer_ran_after_failure():
    """Verify finalizer ran after previous test failed."""
    # The previous test added _test_leaked_finalizer
    # Even though it failed, the finalizer should have cleaned it up
    assert "_test_leaked_finalizer" not in sys.modules, \
        "Finalizer must run even after assertion failure"
