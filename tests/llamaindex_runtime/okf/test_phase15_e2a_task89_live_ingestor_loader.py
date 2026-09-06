"""Task #89 non-DB contracts for the real ingestor and the scoped loader.

Focused sibling of ``test_phase15_e2a_task89_contracts``: this module
pins, WITHOUT any database, Docker, or live selector:

- the real Docling ingestor construction contract. The naive
  ``DoclingIngestor()`` production default reader path raises exactly
  ``ImportError`` in this environment, so the live helper must construct
  the real ingestor through the explicit real reader/node-parser path
  (``_new_ingestor``),
- the unique ``sys.modules`` scoped verification-module loader contract.
  The verification directory is not a package, so the module is loaded by
  file under a UNIQUE ``sys.modules`` key while ``exec_module`` runs, and
  the prior ``sys.modules`` state is restored on BOTH the normal and
  exception exit paths with no permanent entry left behind.

Both contracts reach the implementation through the live cells module's
re-exported support surface (``_new_ingestor``, ``_load_verification_module``,
``_VERIFICATION_MODULE_NAME``). No environment variable is read, no database
is touched, and no session is ever created here.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from llamaindex_runtime.ingestion.docling_ingestor import DoclingIngestor

from ._phase15_e2a_task89_ast_proof import (
    HELPER_IMPL_FUNCTION,
    LIVE_CELLS_FILENAME,
    _single_function_by_name,
)

OKF_DIR = Path(__file__).parent

# Sentinel + exact-restore helpers for the characterization tests. The
# tests deliberately set sys.modules[name] = None to pin the reviewed
# exact-None restoration; cleanup must distinguish "absent" from
# "present-with-None" exactly like the loader under test.
_MISSING = object()


def _capture_prior(name: str) -> object:
    return sys.modules.get(name, _MISSING)


def _restore_prior(name: str, prior: object) -> None:
    if prior is _MISSING:
        sys.modules.pop(name, None)
    else:
        sys.modules[name] = prior


def _fake_failing_spec(error: BaseException) -> SimpleNamespace:
    """A fake spec whose loader raises ``error`` from exec_module.

    Built to exercise the loader's BaseException restore path without any
    real file or live selector. The returned spec mirrors the real
    ``spec_from_file_location`` surface the loader inspects.
    """

    def _raise(module: object) -> None:
        raise error

    fake_loader = SimpleNamespace(
        exec_module=_raise,
        create_module=lambda spec: ModuleType("fake_verification"),
    )
    return SimpleNamespace(
        name="fake_verification",
        loader=fake_loader,
        submodule_search_locations=None,
        origin="fake",
        has_location=False,
        cached=None,
        parent=None,
    )


def _live_cells_module() -> ModuleType:
    from . import _phase15_e2a_task89_live_cells as cells

    return cells


class TestTask89LiveIngestorConstruction:
    """The live helper builds the real ingestor without an ImportError.

    Root-cause pin for the recorded ``task89_cell_failed:ImportError``: the
    composed live helper constructed the ingestor with the production
    default reader path, and that path imports optional docling
    heading-hierarchy symbols that are not present in every supported
    docling release. In this environment ``DoclingIngestor()`` determinis-
    tically raises ``ImportError`` (``cannot import name
    'HeadingHierarchyOptions'``), so the live helper must construct the real
    ingestor through the explicit real reader/node-parser path. No fakes and
    no reconciliation substitution are involved.
    """

    def test_default_ingestor_construction_reproduces_import_error(self) -> None:
        # Deterministic root-cause reproduction without DB/Docker: the
        # production default reader path raises exactly ImportError when the
        # installed docling lacks the heading-hierarchy symbol set.
        with pytest.raises(ImportError):
            DoclingIngestor()

    def test_new_ingestor_constructs_real_ingestor_without_import_error(self) -> None:
        cells = _live_cells_module()
        ingestor = cells._new_ingestor()
        assert isinstance(ingestor, DoclingIngestor)
        assert callable(ingestor.convert_for_okf)
        assert callable(ingestor.ingest)

    def test_live_impl_uses_new_ingestor_helper_not_naive_construction(self) -> None:
        source = (OKF_DIR / LIVE_CELLS_FILENAME).read_text(encoding="utf-8")
        tree = ast.parse(source)
        function = _single_function_by_name(tree, HELPER_IMPL_FUNCTION)
        segment = ast.get_source_segment(source, function)
        assert segment is not None
        assert "_new_ingestor()" in segment
        assert "DoclingIngestor()" not in segment


class TestTask89VerificationModuleScopedLoad:
    """The file-based verification load uses the scoped repo pattern.

    The verification directory is not a package, so the module is loaded by
    file under a UNIQUE ``sys.modules`` key while ``exec_module`` runs (the
    direct file-based pattern already used by this suite), and the prior
    ``sys.modules`` state is restored on BOTH the normal and exception exit
    paths. No permanent sys.modules entry is left behind.
    """

    def test_load_uses_unique_module_name_and_leaves_no_leak(self) -> None:
        cells = _live_cells_module()
        before = set(sys.modules)
        verify = cells._load_verification_module()
        assert callable(verify.validate_quality_claim)
        assert verify.__name__ == cells._VERIFICATION_MODULE_NAME
        assert set(sys.modules) == before

    def test_load_restores_prior_sys_modules_entry_on_success(self) -> None:
        cells = _live_cells_module()
        name = cells._VERIFICATION_MODULE_NAME
        prior = sys.modules.get(name)
        sentinel = object()
        sys.modules[name] = sentinel
        try:
            verify = cells._load_verification_module()
            assert callable(verify.validate_quality_claim)
            assert sys.modules.get(name) is sentinel
        finally:
            if prior is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prior

    def test_load_restores_prior_sys_modules_entry_when_exec_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cells = _live_cells_module()
        name = cells._VERIFICATION_MODULE_NAME
        prior = sys.modules.get(name)
        sentinel = object()
        sys.modules[name] = sentinel
        baseline = set(sys.modules)
        try:

            def _failing_exec(module: object) -> None:
                raise RuntimeError("boom")

            fake_loader = SimpleNamespace(
                exec_module=_failing_exec,
                create_module=lambda spec: ModuleType("fake_verification"),
            )
            fake_spec = SimpleNamespace(
                name="fake_verification",
                loader=fake_loader,
                submodule_search_locations=None,
                origin="fake",
                has_location=False,
                cached=None,
                parent=None,
            )
            monkeypatch.setattr(
                importlib.util,
                "spec_from_file_location",
                lambda *args, **kwargs: fake_spec,
            )
            with pytest.raises(RuntimeError, match="boom"):
                cells._load_verification_module()
            assert sys.modules.get(name) is sentinel
            assert set(sys.modules) == baseline
        finally:
            if prior is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prior

    def test_load_restores_existing_none_entry_exactly_on_success(self) -> None:
        cells = _live_cells_module()
        name = cells._VERIFICATION_MODULE_NAME
        prior = _capture_prior(name)
        sys.modules[name] = None
        try:
            verify = cells._load_verification_module()
            assert callable(verify.validate_quality_claim)
            # The reviewed contract: a prior present-with-None entry must be
            # restored exactly (key STILL present, value STILL None), not
            # conflated with the absent state and popped.
            assert (
                name in sys.modules
            ), "prior present-with-None key must survive a successful load"
            assert (
                sys.modules[name] is None
            ), "prior present-with-None value must restore identity-exactly"
        finally:
            _restore_prior(name, prior)

    def test_load_restores_existing_none_entry_when_exec_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cells = _live_cells_module()
        name = cells._VERIFICATION_MODULE_NAME
        prior = _capture_prior(name)
        sys.modules[name] = None
        baseline = set(sys.modules)
        try:
            monkeypatch.setattr(
                importlib.util,
                "spec_from_file_location",
                lambda *args, **kwargs: _fake_failing_spec(RuntimeError("boom")),
            )
            with pytest.raises(RuntimeError, match="boom"):
                cells._load_verification_module()
            assert (
                name in sys.modules
            ), "prior present-with-None key must survive an exec failure"
            assert (
                sys.modules[name] is None
            ), "prior present-with-None value must restore identity-exactly"
            assert set(sys.modules) == baseline
        finally:
            _restore_prior(name, prior)

    @pytest.mark.parametrize("exc_type", [SystemExit, KeyboardInterrupt])
    def test_load_restores_state_and_propagates_base_exception(
        self, monkeypatch: pytest.MonkeyPatch, exc_type: type[BaseException]
    ) -> None:
        cells = _live_cells_module()
        name = cells._VERIFICATION_MODULE_NAME
        prior = _capture_prior(name)
        sentinel = object()
        sys.modules[name] = sentinel
        baseline = set(sys.modules)
        try:
            monkeypatch.setattr(
                importlib.util,
                "spec_from_file_location",
                lambda *args, **kwargs: _fake_failing_spec(exc_type("interrupt")),
            )
            with pytest.raises(exc_type):
                cells._load_verification_module()
            # BaseException (KeyboardInterrupt/SystemExit) must propagate
            # after the exact restore, never masking the original exception.
            assert sys.modules.get(name) is sentinel
            assert set(sys.modules) == baseline
        finally:
            _restore_prior(name, prior)

    def test_restore_helper_distinguishes_absent_from_present_none(self) -> None:
        from ._phase15_e2a_task89_support import (
            _MISSING_SYS_MODULES_KEY,
            _restore_sys_modules_key,
        )

        name = "_task89_restore_probe"
        # absent prior: the key must be removed.
        sys.modules.pop(name, None)
        _restore_sys_modules_key(name, _MISSING_SYS_MODULES_KEY)
        assert name not in sys.modules
        # existing object prior: identity-exact re-bind.
        sentinel = object()
        sys.modules[name] = "stale"
        _restore_sys_modules_key(name, sentinel)
        assert sys.modules.get(name) is sentinel
        # existing None prior: the key stays present with value None.
        sys.modules[name] = None
        _restore_sys_modules_key(name, None)
        assert name in sys.modules
        assert sys.modules[name] is None
        sys.modules.pop(name, None)
