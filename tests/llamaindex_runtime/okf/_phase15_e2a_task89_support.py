"""Scoped Task #89 support: verification-module loader and real ingestor.

Non-collected (underscore prefix) support shared by the Task #89 live
cells and their contract suites. This module owns two focused concerns that
were split out of ``_phase15_e2a_task89_live_cells`` to keep every Task #89
file under the project <800 physical-line limit:

- the file-based verification-module loader: the verification directory is
  not a package, so ``run_e2a_verification.py`` is loaded by file under a
  UNIQUE ``sys.modules`` key while ``exec_module`` runs, and the prior
  ``sys.modules`` state is restored on BOTH normal and exception exit
  paths with no ``sys.path`` mutation and no permanent ``sys.modules``
  entry left behind,
- the real Docling ingestor constructor: built through the explicit real
  ``DoclingReader`` / ``DoclingNodeParser`` path because the production
  default reader constructor imports optional docling heading-hierarchy
  symbols that are not present in every supported docling release (the
  naive ``DoclingIngestor()`` construction deterministically raises
  ``ImportError`` in this environment).

The small resource-close / bounded-diagnostic / source-fixture helpers the
live cells rely on are also kept here so the live cells module stays
focused on the composed proof itself.

Security contract: no environment reads, no connection target or secret
named, no URI/credential/target/corpus text in any repr, no test-framework
machinery, no fake/replacement of any production symbol; instrumentation
wrappers ALWAYS call the original and restore identity-exactly on every
exit path.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

from llamaindex_runtime.ingestion.docling_ingestor import DoclingIngestor

from ._phase15_e2a_task89_types import SOURCE_PDF_RELATIVE

# Worktree root: this file is at <root>/tests/llamaindex_runtime/okf/.
PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Unique sys.modules key for the file-based verification load. The
# verification directory is not a package, so the module can never be
# package-imported; a spec load by explicit file path is the only safe
# route. The key exists only while ``exec_module`` runs and is restored on
# every exit path so no sys.modules leakage remains.
_VERIFICATION_MODULE_NAME = "_track_c_e2a_task89_verification_module"

# Sentinel distinguishing "the sys.modules key is absent" from "the key is
# present with value None". ``dict.get`` conflates the two; restoration must
# preserve the exact prior presence bit plus identity so every prior state
# (absent, present module/object, present None) restores precisely.
_MISSING_SYS_MODULES_KEY = object()


def _restore_sys_modules_key(name: str, prior: Any) -> None:
    """Restore a sys.modules key to its exact prior state.

    ``prior`` is either ``_MISSING_SYS_MODULES_KEY`` (the key was absent,
    so it is removed) or the exact prior value (a module/object, or ``None``
    when the key was present-with-None); the key is re-bound identity-exactly
    so every prior state restores precisely.
    """
    if prior is _MISSING_SYS_MODULES_KEY:
        sys.modules.pop(name, None)
    else:
        sys.modules[name] = prior


def _load_verification_module() -> Any:
    """Load the verification module by file (its directory is not a package).

    ``verification/phase15-okf-ingestion-pipeline/`` has no ``__init__.py``,
    so the module is never package-importable; a spec load by explicit file
    path is the only safe import route. The module is registered under a
    unique ``sys.modules`` key while ``exec_module`` runs (so its absolute
    ``llamaindex_runtime`` import resolves through the import system, the
    direct file-based pattern already used elsewhere in this suite), then
    the prior ``sys.modules`` state is restored on BOTH the normal and
    exception exit paths. Restoration preserves the exact prior state: an
    absent key is removed, and a present key (a module/object, or ``None``)
    is re-bound identity-exactly (``_MISSING_SYS_MODULES_KEY`` keeps
    "absent" distinct from "present-with-None").
    """
    path = (
        PROJECT_ROOT
        / "verification"
        / "phase15-okf-ingestion-pipeline"
        / "run_e2a_verification.py"
    )
    spec = importlib.util.spec_from_file_location(_VERIFICATION_MODULE_NAME, path)
    if spec is None or spec.loader is None:
        raise ImportError("task89_verification_spec_unavailable")
    module = importlib.util.module_from_spec(spec)
    prior = sys.modules.get(_VERIFICATION_MODULE_NAME, _MISSING_SYS_MODULES_KEY)
    sys.modules[_VERIFICATION_MODULE_NAME] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        _restore_sys_modules_key(_VERIFICATION_MODULE_NAME, prior)
        raise
    _restore_sys_modules_key(_VERIFICATION_MODULE_NAME, prior)
    return module


def _new_ingestor() -> DoclingIngestor:
    """Build the real DoclingIngestor on the explicit real reader path.

    The production default reader construction imports optional docling
    heading-hierarchy symbols that are not present in every supported
    docling release, so the naive ``DoclingIngestor()`` construction can
    raise ``ImportError`` before any document work begins. Constructing the
    real ``DoclingReader`` / ``DoclingNodeParser`` classes directly keeps
    the live proof on the real conversion path without depending on that
    optional symbol set.
    """
    from llamaindex_runtime.integration import (
        load_docling_node_parser_class,
        load_docling_reader_class,
    )

    reader = load_docling_reader_class()(export_type="json")
    node_parser = load_docling_node_parser_class()()
    return DoclingIngestor(reader=reader, node_parser=node_parser)


def _resolve_source_pdf() -> Path:
    """Resolve the frozen sectioned-pdf source fixture against the worktree root."""
    path = PROJECT_ROOT.joinpath(*SOURCE_PDF_RELATIVE)
    if not path.is_file():
        raise RuntimeError("task89_source_fixture_missing")
    return path


def _close_quietly(value: Any) -> None:
    """Close a resource in a finally path without masking an in-flight error."""
    if value is None:
        return
    try:
        value.close()
    except Exception:
        pass


def _error_reason(prefix: str, failure: Exception) -> str:
    """Bounded class/type-only diagnostic; never message, args, or repr."""
    error_type = type(failure).__name__
    return f"{prefix}:{error_type[:64]}"
