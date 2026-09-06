"""Separately-authorized disposable PostgreSQL acceptance specification.

This module is deliberately inert in the Wave 2 RED run.  It has no database
imports, no connection factory, and no credential-environment dereference.
A later, separately authorized task may enable it with the explicit non-secret
acknowledgement flag documented below.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
from types import ModuleType

import pytest

_MODULE = "llamaindex_runtime.okf.e2a_reconciler"
_AUTHORIZATION_FLAG = "OKF_E2A_DISPOSABLE_TEST_AUTHORIZED"


def _separately_authorized() -> bool:
    """Require an explicit non-secret acknowledgement before any acceptance work."""
    return os.environ.get(_AUTHORIZATION_FLAG) == "separately-authorized"


pytestmark = pytest.mark.skipif(
    not _separately_authorized(),
    reason="disposable PostgreSQL acceptance requires separate active authorization",
)


def _wave2_reconciler() -> ModuleType:
    specification = importlib.util.find_spec(_MODULE)
    assert specification is not None, (
        "Wave 2 disposable acceptance requires e2a_reconciler only after "
        "separate authorization"
    )
    return importlib.import_module(_MODULE)


def test_disposable_acceptance_requires_an_explicit_authority_object_before_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _wave2_reconciler()
    calls: list[str] = []

    class Unauthorized:
        authorized = False

    def connector(*_: object, **__: object) -> object:
        calls.append("connector")
        raise AssertionError("connector must not run before authorization")

    monkeypatch.setattr(module, "connect_disposable_postgresql", connector)

    result = module.run_disposable_e2a_reconciliation_acceptance(
        Unauthorized(), connector
    )

    assert result == "blocked_not_executed"
    assert calls == []


def test_disposable_authorization_is_not_implied_by_database_environment_presence() -> (
    None
):
    assert _separately_authorized() is True
