#!/usr/bin/env python3
"""Diagnostic: PageIndex consumer-boundary smoke test.

Phase 15: Safe diagnostic script. NOT ACCEPTANCE EVIDENCE. No artifacts written.

SECURITY: Synthetic package boundary - NO real llamaindex_runtime imports.
- Actual source files loaded under synthetic prefix with sealed dependencies
- NO os.environ mutation (snapshot before, verify identity after)
- NO real pageindex/litellm/dotenv/torch imports
- Full sys.modules restoration (synthetic prefix modules removed)
- Narrow exception handling (no broad catch hiding failures)
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
import tempfile
import uuid
import warnings
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Iterator, Sequence
from unittest.mock import MagicMock


# ============================================================================
# Sentinel exceptions (narrow handling)
# ============================================================================


class _DonorImportBlockedError(RuntimeError):
    """Sentinel: unexpected real donor import detected."""

    pass


class _GlobalMutationError(RuntimeError):
    """Sentinel: process globals mutated during diagnostic.

    MUST propagate to caller - do not hide.
    """

    pass


class _DiagnosticFailureError(RuntimeError):
    """Sentinel: expected diagnostic failure (for classified handling)."""

    pass


# ============================================================================
# TDD Internal Check Functions (safe, no imports)
# ============================================================================


def _check_env_unchanged(env_keys_before: frozenset[str]) -> bool:
    """Internal check: os.environ key set unchanged (no add/remove).

    RED-proves no environment mutation from diagnostic path.

    SECURITY (defect 1): NEVER reads environment values - not even
    transiently for hashing/comparison. Only the key SET is compared.
    Value mutation cannot be detected without reading values, which the
    hard rule forbids; the diagnostic itself never mutates values.
    """
    env_keys_after = frozenset(os.environ.keys())
    return env_keys_after == env_keys_before


def _check_no_forbidden_tokens(text: str) -> bool:
    """Internal check: no acceptance-like tokens in text.

    RED-proves no PASS/FAIL/SUCCESS/PROOF/VERIFIED/OK/NOT_OK wording.
    Uses word-boundary matching.
    Exception: "NOT ACCEPTANCE EVIDENCE" is allowed as negation.
    """
    forbidden = {
        "PASS",
        "FAIL",
        "SUCCESS",
        "PROOF",
        "VERIFIED",
        "OK",
        "NOT_OK",
    }
    # Check for standalone ACCEPTANCE (not as part of "NOT ACCEPTANCE EVIDENCE")
    words = set(re.findall(r"\b\w+\b", text.upper()))
    if "ACCEPTANCE" in words:
        # Allow if it's specifically "NOT ACCEPTANCE EVIDENCE"
        if "NOT ACCEPTANCE EVIDENCE" not in text.upper():
            return False
    return not (forbidden & words)


def _check_no_real_modules_loaded(snapshot_before: set[str]) -> bool:
    """Internal check: no new modules loaded after cleanup.

    RED-proves synthetic boundary prevented real dependency imports.
    Post-cleanup invariant: NO introduced module key is legitimate.
    Call sites are after sys.modules restoration; the delta must be empty.
    """
    current_modules = set(sys.modules.keys())
    new_modules = current_modules - snapshot_before

    # Post-cleanup invariant: any new module is a leak
    # (Call sites are after sys.modules restoration)
    if new_modules:
        return False

    return True


# ============================================================================
# Synthetic Package Boundary
# ============================================================================


_SYNTHETIC_PREFIX = "_diag_rag"


@dataclass(frozen=True)
class _FakeBackendHit:
    """Fake BackendHit for synthetic tree adapter."""

    score: float | None
    text_preview: str
    heading_path: str | None
    page_no: int | None
    span_ids: Sequence[uuid.UUID]
    node_id: uuid.UUID
    chunk_id: uuid.UUID
    entity_id: uuid.UUID | None
    relation_id: uuid.UUID | None
    backend_source: str | None = None
    retrieval_path: str | None = None


def _create_fake_backend_hit_module() -> ModuleType:
    """Create fake backend_adapter module with BackendHit class."""
    mod = ModuleType(
        f"{_SYNTHETIC_PREFIX}.tree.backend_adapter", doc="Fake backend adapter"
    )
    mod.BackendHit = _FakeBackendHit  # type: ignore[attr-defined]
    return mod


def _create_fake_config_module() -> ModuleType:
    """Create fake config module with RuntimeSettings class."""
    mod = ModuleType(f"{_SYNTHETIC_PREFIX}.config", doc="Fake config")

    class _FakeRuntimeSettings:
        """Fake RuntimeSettings - returns MagicMock values for all attrs."""

        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

        @classmethod
        def from_env(cls):
            # Return mock settings that don't trigger DB/LLM imports
            return cls(
                database_url="",
                pageindex_workspace="",
                llm_model="mock-model",
            )

    mod.RuntimeSettings = _FakeRuntimeSettings  # type: ignore[attr-defined]
    return mod


def _create_fake_registry_module() -> ModuleType:
    """Create fake registry module with RegistryWriter protocol."""
    mod = ModuleType(f"{_SYNTHETIC_PREFIX}.registry", doc="Fake registry")

    # Provide empty protocol-like class
    class _FakeRegistryWriter:
        """Fake RegistryWriter - all methods are MagicMock."""

        def __init__(self):
            self.write_tree = MagicMock(return_value=None)
            self.read_tree = MagicMock(return_value=None)

    mod.RegistryWriter = _FakeRegistryWriter  # type: ignore[attr-defined]
    return mod


def _create_fake_retrieve_module() -> ModuleType:
    """Create fake retrieve module with stub functions."""
    mod = ModuleType(
        f"{_SYNTHETIC_PREFIX}.client.retrieve", doc="Fake retrieve functions"
    )

    def _stub_get_document(*args, **kwargs):
        return "{}"

    def _stub_get_document_structure(*args, **kwargs):
        return "{}"

    def _stub_get_page_content(*args, **kwargs):
        return "{}"

    mod.get_document = _stub_get_document
    mod.get_document_structure = _stub_get_document_structure
    mod.get_page_content = _stub_get_page_content
    return mod


def _create_fake_utils_module() -> ModuleType:
    """Create fake utils module."""
    mod = ModuleType(f"{_SYNTHETIC_PREFIX}.client.utils", doc="Fake client utils")

    def _stub_remove_fields(data, fields):
        return data

    mod.remove_fields = _stub_remove_fields
    return mod


def _create_fake_pageindex_md(
    tracking: dict[str, int],
) -> tuple[ModuleType, ModuleType]:
    """Create fake pageindex.page_index_md with async md_to_tree stub."""

    async def _fake_md_to_tree(*args: Any, **kwargs: Any) -> dict[str, Any]:
        """Deterministic async stub proving donor code was bypassed."""
        tracking["md_to_tree_calls"] += 1
        return {
            "structure": [{"title": "DIAGNOSTIC_STUB_NODE", "node_id": "stub-001"}],
            "doc_name": "DIAGNOSTIC_DOC",
            "doc_description": "DIAGNOSTIC_DESCRIPTION",
            "line_count": 10,
        }

    # Create pageindex package
    fake_pageindex = ModuleType("pageindex")
    fake_pageindex.__path__ = []  # type: ignore[attr-defined]
    fake_pageindex.__package__ = "pageindex"  # type: ignore[attr-defined]

    # Create pageindex.page_index_md module
    fake_pageindex_md = ModuleType("pageindex.page_index_md")
    fake_pageindex_md.__package__ = "pageindex.page_index_md"  # type: ignore[attr-defined]
    fake_pageindex_md.md_to_tree = _fake_md_to_tree  # type: ignore[attr-defined]

    return fake_pageindex, fake_pageindex_md


def _load_source_as_module(
    module_name: str, file_path: Path, fake_modules: dict[str, ModuleType]
) -> ModuleType:
    """Load actual source file as module under synthetic prefix.

    The module's relative imports will resolve to fake_modules.

    SECURITY (defect 2): registration in sys.modules happens before
    exec_module (so recursive imports resolve), but on ANY exception
    during exec the half-initialized module is removed so it cannot leak.
    Static error message only - no paths in raised diagnostics.
    """
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        raise _DiagnosticFailureError("Could not create module spec")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        # Do not leave a half-initialized module in sys.modules.
        sys.modules.pop(module_name, None)
        raise
    return module


@contextmanager
def _synthetic_package_boundary() -> Iterator[dict[str, Any]]:
    """Synthetic package boundary - loads actual source under sealed prefix.

    NEVER imports real llamaindex_runtime. Loads source files with
    importlib.util.spec_from_file_location under _diag_rag prefix,
    with all dependencies sealed to fakes.

    Yields tracking dict with call counters and references to loaded modules.
    """
    tracking: dict[str, Any] = {"md_to_tree_calls": 0}

    # Snapshot os.environ BEFORE any operation.
    # SECURITY (defect 1): KEYS ONLY - never read values (not even for hashing).
    env_keys_before = frozenset(os.environ.keys())

    # Snapshot sys.modules BEFORE
    modules_before = set(sys.modules.keys())
    modules_snapshot = sys.modules.copy()

    # Track synthetic modules we create
    synthetic_modules: list[str] = []

    try:
        # =================================================================
        # Create synthetic package structure
        # =================================================================

        # Root package
        root_pkg = ModuleType(_SYNTHETIC_PREFIX)
        root_pkg.__path__ = []  # type: ignore[attr-defined]
        root_pkg.__package__ = _SYNTHETIC_PREFIX  # type: ignore[attr-defined]
        sys.modules[_SYNTHETIC_PREFIX] = root_pkg
        synthetic_modules.append(_SYNTHETIC_PREFIX)

        # tree package
        tree_pkg = ModuleType(f"{_SYNTHETIC_PREFIX}.tree")
        tree_pkg.__path__ = []  # type: ignore[attr-defined]
        tree_pkg.__package__ = f"{_SYNTHETIC_PREFIX}.tree"  # type: ignore[attr-defined]
        sys.modules[f"{_SYNTHETIC_PREFIX}.tree"] = tree_pkg
        synthetic_modules.append(f"{_SYNTHETIC_PREFIX}.tree")

        # client package
        client_pkg = ModuleType(f"{_SYNTHETIC_PREFIX}.client")
        client_pkg.__path__ = []  # type: ignore[attr-defined]
        client_pkg.__package__ = f"{_SYNTHETIC_PREFIX}.client"  # type: ignore[attr-defined]
        sys.modules[f"{_SYNTHETIC_PREFIX}.client"] = client_pkg
        synthetic_modules.append(f"{_SYNTHETIC_PREFIX}.client")

        # =================================================================
        # Install fake llamaindex_runtime namespace (redirects to synthetic)
        # This allows source files to import from llamaindex_runtime.*
        # and get our fake modules instead of real ones.
        # =================================================================

        # Create llamaindex_runtime root package
        llamaindex_root = ModuleType("llamaindex_runtime")
        llamaindex_root.__path__ = []  # type: ignore[attr-defined]
        llamaindex_root.__package__ = "llamaindex_runtime"  # type: ignore[attr-defined]
        sys.modules["llamaindex_runtime"] = llamaindex_root
        synthetic_modules.append("llamaindex_runtime")

        # Create llamaindex_runtime.tree package
        llamaindex_tree = ModuleType("llamaindex_runtime.tree")
        llamaindex_tree.__path__ = []  # type: ignore[attr-defined]
        llamaindex_tree.__package__ = "llamaindex_runtime.tree"  # type: ignore[attr-defined]
        sys.modules["llamaindex_runtime.tree"] = llamaindex_tree
        synthetic_modules.append("llamaindex_runtime.tree")

        # Create llamaindex_runtime.client package
        llamaindex_client = ModuleType("llamaindex_runtime.client")
        llamaindex_client.__path__ = []  # type: ignore[attr-defined]
        llamaindex_client.__package__ = "llamaindex_runtime.client"  # type: ignore[attr-defined]
        sys.modules["llamaindex_runtime.client"] = llamaindex_client
        synthetic_modules.append("llamaindex_runtime.client")

        # =================================================================
        # Install fake dependencies (before loading actual source)
        # =================================================================

        # config - install under both synthetic and llamaindex_runtime prefixes
        fake_config = _create_fake_config_module()
        sys.modules[f"{_SYNTHETIC_PREFIX}.config"] = fake_config
        sys.modules["llamaindex_runtime.config"] = fake_config
        synthetic_modules.append(f"{_SYNTHETIC_PREFIX}.config")
        synthetic_modules.append("llamaindex_runtime.config")

        # registry
        fake_registry = _create_fake_registry_module()
        sys.modules[f"{_SYNTHETIC_PREFIX}.registry"] = fake_registry
        synthetic_modules.append(f"{_SYNTHETIC_PREFIX}.registry")

        # tree.backend_adapter - install under both prefixes
        fake_backend = _create_fake_backend_hit_module()
        sys.modules[f"{_SYNTHETIC_PREFIX}.tree.backend_adapter"] = fake_backend
        sys.modules["llamaindex_runtime.tree.backend_adapter"] = fake_backend
        synthetic_modules.append(f"{_SYNTHETIC_PREFIX}.tree.backend_adapter")
        synthetic_modules.append("llamaindex_runtime.tree.backend_adapter")

        # client.retrieve - install under both prefixes
        fake_retrieve = _create_fake_retrieve_module()
        sys.modules[f"{_SYNTHETIC_PREFIX}.client.retrieve"] = fake_retrieve
        sys.modules["llamaindex_runtime.client.retrieve"] = fake_retrieve
        synthetic_modules.append(f"{_SYNTHETIC_PREFIX}.client.retrieve")
        synthetic_modules.append("llamaindex_runtime.client.retrieve")

        # client.utils - install under both prefixes
        fake_utils = _create_fake_utils_module()
        sys.modules[f"{_SYNTHETIC_PREFIX}.client.utils"] = fake_utils
        sys.modules["llamaindex_runtime.client.utils"] = fake_utils
        synthetic_modules.append(f"{_SYNTHETIC_PREFIX}.client.utils")
        synthetic_modules.append("llamaindex_runtime.client.utils")

        # =================================================================
        # Seal pageindex donor package (before loading source that imports it)
        # =================================================================

        fake_pageindex, fake_pageindex_md = _create_fake_pageindex_md(tracking)
        sys.modules["pageindex"] = fake_pageindex
        synthetic_modules.append("pageindex")
        sys.modules["pageindex.page_index_md"] = fake_pageindex_md
        synthetic_modules.append("pageindex.page_index_md")

        # Import guard for any other pageindex.* attempts
        class _PageindexGuard:
            """Meta path finder blocking unexpected pageindex imports."""

            def find_spec(self, fullname: str, _path: Any, _target: Any = None) -> Any:
                if fullname.startswith("pageindex.") and fullname not in (
                    "pageindex",
                    "pageindex.page_index_md",
                ):
                    raise _DonorImportBlockedError(
                        f"BLOCKED: Unexpected donor import {fullname}"
                    )
                return None

        guard = _PageindexGuard()
        sys.meta_path.insert(0, guard)

        # =================================================================
        # Load actual source files under synthetic prefix
        # =================================================================
        # SECURITY (defect 3): guard removal is in an inner try/finally so a
        # source-load failure cannot leak the finder into sys.meta_path. It is
        # still removed BEFORE yield, preserving the md-mode safety property
        # (defect 7): the fake donor is preinstalled, so the md path never
        # needs the guard during the yielded test.
        try:
            project_root = Path(__file__).parent.parent
            llamaindex_src = project_root / "llamaindex_runtime"

            # Load pageindex_adapter
            adapter_path = llamaindex_src / "tree" / "pageindex_adapter.py"
            _load_source_as_module(
                f"{_SYNTHETIC_PREFIX}.tree.pageindex_adapter",
                adapter_path,
                {},
            )
            synthetic_modules.append(f"{_SYNTHETIC_PREFIX}.tree.pageindex_adapter")

            # Load pageindex_client
            client_path = llamaindex_src / "client" / "pageindex_client.py"
            _load_source_as_module(
                f"{_SYNTHETIC_PREFIX}.client.pageindex_client",
                client_path,
                {},
            )
            synthetic_modules.append(f"{_SYNTHETIC_PREFIX}.client.pageindex_client")
        finally:
            try:
                sys.meta_path.remove(guard)
            except ValueError:
                pass

        yield tracking

    finally:
        # =================================================================
        # Exact restoration of sys.modules (defect 4).
        # Remove EVERY module introduced during the boundary (synthetic prefix
        # modules, alias packages, AND any non-synthetic module imported as a
        # side effect of source-load), then restore pre-existing modules to
        # their original objects (undoing any in-place replacement). Keys are
        # materialized first so no mutation-during-iteration can occur, and
        # pre-existing modules are never deleted.
        # =================================================================
        snapshot_keys = modules_snapshot.keys()
        for mod_name in list(sys.modules.keys()):
            if mod_name not in snapshot_keys:
                sys.modules.pop(mod_name, None)
        for mod_name, mod_obj in modules_snapshot.items():
            sys.modules[mod_name] = mod_obj

        # =================================================================
        # Verify no os.environ KEY mutation (defect 1: keys-only, never read
        # values). Value mutation is undetectable without reading values,
        # which the hard rule forbids; the diagnostic itself never mutates
        # values. Treat any key-set change as a hard failure.
        # =================================================================
        env_keys_after = frozenset(os.environ.keys())
        if env_keys_after != env_keys_before:
            raise _GlobalMutationError(
                "BLOCKED: os.environ keys mutated "
                f"(added={len(env_keys_after - env_keys_before)}, "
                f"removed={len(env_keys_before - env_keys_after)})"
            )

        # Store verification data for internal checks (no value hash stored)
        tracking["_env_unchanged"] = env_keys_after == env_keys_before
        tracking["_modules_clean"] = _check_no_real_modules_loaded(modules_before)
        tracking["_env_keys_before"] = env_keys_before


# ============================================================================
# Main Diagnostic
# ============================================================================


def smoke_test_pageindex_consumer_boundary() -> bool:
    """Verify PageIndex consumer-boundary enforcement.

    NOT ACCEPTANCE EVIDENCE - diagnostic signal only. No artifacts written.
    Uses synthetic package boundary to load actual source under sealed deps.
    """
    # Capture output for token check
    output_lines: list[str] = []

    def _emit(msg: str) -> None:
        """Print and capture output."""
        print(msg)
        output_lines.append(msg)

    # Pre-import stdlib modules that might be loaded during tests
    import json  # noqa: F401 (pre-import to avoid false positive in module check)

    # Snapshot state before diagnostic.
    # SECURITY (defect 1): KEYS ONLY - never read env values (not even for hashing).
    env_keys_before = frozenset(os.environ.keys())
    modules_before = set(sys.modules.keys())

    _emit("=== PageIndex Consumer-Boundary Diagnostic ===")
    _emit("NOT ACCEPTANCE EVIDENCE - diagnostic signal only")
    _emit("NOT ACCEPTANCE EVIDENCE - synthetic package boundary")
    _emit("")

    # TemporaryDirectory with static-safe cleanup
    tmpdir: tempfile.TemporaryDirectory | None = None
    tmpdir_path: Path | None = None

    try:
        tmpdir = tempfile.TemporaryDirectory()
        tmpdir_path = Path(tmpdir.name)
    except OSError:
        _emit("DIAGNOSTIC ISSUE: Could not create temporary directory")
        return False

    test1_result: str = "NOT RUN"
    test2_result: str = "NOT RUN"
    test3_result: str = "NOT RUN"
    cleanup_result: str = "NOT RUN"
    md_to_tree_called = False
    tracking_container: list[dict[str, Any]] = []  # Mutable container for tracking

    try:
        test_doc = tmpdir_path / "test_doc.md"
        test_doc.write_text("# Test Document\n\nTest content.\n")
        workspace_dir = tmpdir_path / "pageindex_workspace"

        # =================================================================
        # ALL operations inside synthetic boundary
        # =================================================================
        with _synthetic_package_boundary() as tracking:
            # Store reference for post-exit verification
            tracking_container.append(tracking)
            # =============================================================
            # Test 1: PageIndexTreeAdapter.index_tree() forbidden boundary
            # =============================================================
            _emit(
                "[1/3] Testing PageIndexTreeAdapter.index_tree() forbidden boundary..."
            )

            # Import from synthetic prefix
            PageIndexTreeAdapter = sys.modules[
                f"{_SYNTHETIC_PREFIX}.tree.pageindex_adapter"
            ].PageIndexTreeAdapter

            adapter = PageIndexTreeAdapter()
            registry = MagicMock()
            version_id = uuid.uuid4()

            try:
                adapter.index_tree(
                    source_path=str(test_doc),
                    version_id=version_id,
                    registry=registry,
                )
                _emit(
                    "  DIAGNOSTIC ISSUE: index_tree() did not raise FORBIDDEN RuntimeError"
                )
                test1_result = "ISSUE"
            except RuntimeError as e:
                if "FORBIDDEN" in str(e):
                    _emit(
                        "  DIAGNOSTIC OBSERVATION: FORBIDDEN RuntimeError raised as expected"
                    )
                    test1_result = "OBSERVATION"
                else:
                    _emit("  DIAGNOSTIC ISSUE: Unexpected RuntimeError message")
                    test1_result = "ISSUE"
            except Exception:
                _emit("  DIAGNOSTIC ISSUE: Unexpected exception type")
                test1_result = "ISSUE"

            if registry.write_tree.called:
                _emit("  DIAGNOSTIC ISSUE: registry.write_tree was called")
                test1_result = "ISSUE"
            else:
                _emit("  DIAGNOSTIC OBSERVATION: registry.write_tree never called")

            # =============================================================
            # Test 2: EnhancedPageIndexClient.index() donor isolation
            # =============================================================
            _emit("")
            _emit("[2/3] Testing EnhancedPageIndexClient.index() donor isolation...")

            EnhancedPageIndexClient = sys.modules[
                f"{_SYNTHETIC_PREFIX}.client.pageindex_client"
            ].EnhancedPageIndexClient

            # Create mock settings (avoid from_env which triggers DB check)
            settings_mock = MagicMock()
            settings_mock.pageindex_workspace = str(workspace_dir)
            settings_mock.llm_model = "mock-model"

            registry2 = MagicMock()

            try:
                client = EnhancedPageIndexClient(
                    registry=registry2,
                    settings=settings_mock,
                    workspace=str(workspace_dir),
                )
            except Exception:
                _emit("  DIAGNOSTIC ISSUE: Client initialization failed")
                test2_result = "ISSUE"
                raise _DiagnosticFailureError("Client init failed")

            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                try:
                    client.index(
                        file_path=str(test_doc),
                        mode="md",
                        write_to_registry=True,
                    )

                    # Check if fake md_to_tree was called
                    if tracking.get("md_to_tree_calls", 0) > 0:
                        _emit(
                            "  DIAGNOSTIC OBSERVATION: Fake md_to_tree called (donor isolated)"
                        )
                        md_to_tree_called = True
                    else:
                        _emit("  DIAGNOSTIC ISSUE: Fake md_to_tree was not called")

                    # Check for forbidden write warning
                    if any(
                        "cannot write canonical tree" in str(wm.message) for wm in w
                    ):
                        _emit(
                            "  DIAGNOSTIC OBSERVATION: Forbidden write warning issued"
                        )
                        test2_result = "OBSERVATION"
                    else:
                        _emit(
                            "  DIAGNOSTIC ISSUE: Expected forbidden write warning not issued"
                        )
                        test2_result = "ISSUE"

                except _DonorImportBlockedError:
                    # Unexpected donor import attempted - fail closed, static msg.
                    _emit(
                        "  DIAGNOSTIC ISSUE: Import guard blocked an unexpected donor import"
                    )
                    test2_result = "ISSUE"
                except _GlobalMutationError:
                    # MUST propagate - do not hide
                    raise
                except RuntimeError:
                    # SECURITY (defect 5): client.index(mode='md') must NEVER
                    # raise the expected FORBIDDEN RuntimeError (that belongs
                    # only to PageIndexTreeAdapter.index_tree() in Test 1).
                    # Any RuntimeError here is unexpected -> fail closed with a
                    # static message. No exception repr/type in output.
                    _emit(
                        "  DIAGNOSTIC ISSUE: Unexpected RuntimeError during client.index()"
                    )
                    test2_result = "ISSUE"
                except Exception:
                    # Narrow handling: only catch truly unexpected, static msg.
                    _emit("  DIAGNOSTIC ISSUE: Unexpected error during client.index()")
                    test2_result = "ISSUE"

            if registry2.write_tree.called:
                _emit("  DIAGNOSTIC ISSUE: registry.write_tree was called")
                test2_result = "ISSUE"
            else:
                _emit("  DIAGNOSTIC OBSERVATION: registry.write_tree never called")

        # =================================================================
        # Test 3: Workspace artifacts and fake md_to_tree response flow
        # =================================================================
        _emit("")
        _emit("[3/3] Testing workspace artifact and response flow...")

        # Verify workspace artifacts exist (proves client code ran)
        if workspace_dir.exists():
            json_files = list(workspace_dir.glob("*.json"))
            if json_files and md_to_tree_called:
                # Read one file to prove fake md_to_tree response flowed through
                import json

                doc_file = json_files[0]
                try:
                    with open(doc_file) as f:
                        doc_data = json.load(f)
                    # Verify diagnostic stub node present (proves fake response)
                    if (
                        doc_data.get("structure")
                        and doc_data["structure"][0].get("title")
                        == "DIAGNOSTIC_STUB_NODE"
                    ):
                        _emit(
                            "  DIAGNOSTIC OBSERVATION: Workspace artifacts created with fake response"
                        )
                        test3_result = "OBSERVATION"
                    else:
                        _emit(
                            "  DIAGNOSTIC ISSUE: Workspace artifacts missing fake response"
                        )
                        test3_result = "ISSUE"
                except (json.JSONDecodeError, KeyError):
                    _emit("  DIAGNOSTIC ISSUE: Workspace artifact malformed")
                    test3_result = "ISSUE"
            elif json_files:
                _emit(
                    "  DIAGNOSTIC ISSUE: Workspace artifacts created but fake not called"
                )
                test3_result = "ISSUE"
            else:
                _emit("  DIAGNOSTIC ISSUE: No workspace artifacts created")
                test3_result = "ISSUE"
        else:
            _emit("  DIAGNOSTIC ISSUE: Workspace directory not created")
            test3_result = "ISSUE"

    except _GlobalMutationError:
        _emit("DIAGNOSTIC ISSUE: Global mutation detected - aborting")
        return False
    except _DiagnosticFailureError:
        _emit("DIAGNOSTIC ISSUE: Expected failure in diagnostic")
        return False
    finally:
        # Cleanup with explicit issue tracking (contract: must not swallow)
        if tmpdir is not None:
            try:
                tmpdir.cleanup()
            except OSError:
                # Fail-closed: cleanup failure is a hard issue, static message only.
                _emit("  DIAGNOSTIC ISSUE: Temporary directory cleanup failed")
                cleanup_result = "ISSUE"
                # Prevent later "cleaned up" observation since it failed
                tmpdir_path = None

    # =================================================================
    # Verify cleanup
    # =================================================================
    _emit("")
    _emit("[Cleanup] Checking workspace removal...")
    if tmpdir_path is not None and not tmpdir_path.exists():
        _emit("  DIAGNOSTIC OBSERVATION: Temporary directory cleaned up")
        cleanup_result = "OBSERVATION"
    elif cleanup_result == "NOT RUN":
        # Either tmpdir_path is None (creation failed) or directory still exists
        _emit("  DIAGNOSTIC ISSUE: Temporary directory still exists")
        cleanup_result = "ISSUE"

    # =================================================================
    # Internal TDD checks
    # =================================================================
    _emit("")
    _emit("[Internal Checks] Checking boundary integrity...")

    # Check 1: Environment unchanged
    env_unchanged = _check_env_unchanged(env_keys_before)
    if env_unchanged:
        _emit("  DIAGNOSTIC OBSERVATION: No os.environ mutation detected")
    else:
        _emit("  DIAGNOSTIC ISSUE: os.environ was mutated")

    # Check 2: No forbidden tokens in output
    all_output = "\n".join(output_lines)
    tokens_clean = _check_no_forbidden_tokens(all_output)
    if tokens_clean:
        _emit("  DIAGNOSTIC OBSERVATION: No acceptance-like tokens in output")
    else:
        _emit("  DIAGNOSTIC ISSUE: Acceptance-like tokens found in output")

    # Check 3: No real unsafe modules loaded
    modules_clean = _check_no_real_modules_loaded(modules_before)
    if modules_clean:
        _emit("  DIAGNOSTIC OBSERVATION: No unsafe real modules loaded")
    else:
        _emit("  DIAGNOSTIC ISSUE: Unsafe real modules were loaded")

    # =================================================================
    # Summary
    # =================================================================
    _emit("")
    _emit("=== Summary ===")

    all_observations = (
        test1_result == "OBSERVATION"
        and test2_result == "OBSERVATION"
        and test3_result == "OBSERVATION"
        and cleanup_result == "OBSERVATION"
        and env_unchanged
        and tokens_clean
        and modules_clean
    )

    if all_observations:
        _emit("DIAGNOSTIC OBSERVATION: Consumer-boundary diagnostic complete")
        _emit(
            "DIAGNOSTIC SIGNAL: Fake md_to_tree called, no donor imports, no global mutation"
        )
        _emit("NOT ACCEPTANCE EVIDENCE - diagnostic only, no artifacts written")
        return True
    else:
        _emit("DIAGNOSTIC ISSUE: Consumer-boundary diagnostic incomplete")
        _emit("NOT ACCEPTANCE EVIDENCE - diagnostic only, no artifacts written")
        return False


# ============================================================================
# TDD Regression Checks (Phase 15 Wave 1 Track B)
#
# Focused regression coverage for confirmed defects 1-7. Run under pytest
# only; the standalone diagnostic (main) does not invoke them. Each test
# isolates sys.modules / sys.meta_path / os.environ and uses finalizers so
# RED-phase leaks cannot pollute sibling tests.
# ============================================================================


def test_regression_check_env_unchanged_keys_only_no_value_reads():
    """Defect 1: env check must use keys-only; must never read env values."""
    import verification.test_pageindex_workflow as mod

    class _EnvValueTrap:
        """Proxies os.environ, recording value-retrieving reads.

        Writes/deletes pass through to the real environ so concurrent plugin
        teardown that sets env vars cannot break. Only value *reads* count.
        """

        def __init__(self, real):
            self._real = real
            self.value_reads = 0

        # Key-only operations (allowed by the hard rule)
        def keys(self):
            return self._real.keys()

        def __iter__(self):
            return iter(self._real.keys())

        def __contains__(self, key):
            return key in self._real

        def __len__(self):
            return len(self._real)

        # Value-retrieving operations (forbidden - counted)
        def __getitem__(self, key):
            self.value_reads += 1
            return self._real[key]

        def get(self, key, default=None):
            self.value_reads += 1
            return self._real.get(key, default)

        def items(self):
            self.value_reads += 1
            return self._real.items()

        def values(self):
            self.value_reads += 1
            return self._real.values()

        # Write-through (never counted; keeps external code functional)
        def __setitem__(self, key, value):
            self._real[key] = value

        def __delitem__(self, key):
            del self._real[key]

        def setdefault(self, key, default=None):
            self.value_reads += 1
            return self._real.setdefault(key, default)

        def pop(self, key, *args):
            self.value_reads += 1
            return self._real.pop(key, *args)

        def __getattr__(self, name):
            return getattr(self._real, name)

    real_environ = os.environ
    keys_before = frozenset(real_environ.keys())
    trap = _EnvValueTrap(real_environ)
    # Direct setattr + try/finally guarantees restore even on RED failure.
    os.environ = trap  # type: ignore[assignment]
    try:
        result = mod._check_env_unchanged(keys_before)
        value_reads = trap.value_reads
    finally:
        os.environ = real_environ  # type: ignore[assignment]

    assert result is True
    assert value_reads == 0, "os.environ values were read (forbidden)"


def test_regression_boundary_does_not_store_value_hash():
    """Defect 1: boundary must not compute/store an env-values hash."""
    import verification.test_pageindex_workflow as mod

    received: list[dict] = []
    with mod._synthetic_package_boundary() as tracking:
        received.append(tracking)
    assert received
    # Inspect only the tracking dict's KEY NAMES (never its values, which under
    # old code include a frozenset of env key names).
    stored_key_names = set(received[0].keys())
    assert "_env_values_hash_before" not in stored_key_names


def test_regression_load_source_no_leak_on_exec_failure(tmp_path, request):
    """Defect 2: failed exec_module must not leave module in sys.modules."""
    import pytest
    import verification.test_pageindex_workflow as mod

    mod_name = "_test_leak_mod_xyz"
    request.addfinalizer(lambda: sys.modules.pop(mod_name, None))

    bad_file = tmp_path / "bad_module.py"
    bad_file.write_text("raise RuntimeError('exec failure')\n")

    with pytest.raises(RuntimeError, match="exec failure"):
        mod._load_source_as_module(mod_name, bad_file, {})

    modules_after = set(sys.modules.keys())
    assert mod_name not in modules_after


def test_regression_guard_removed_on_source_load_failure(monkeypatch, request):
    """Defect 3: source-load failure must not leak _PageindexGuard in meta_path."""
    import pytest
    import verification.test_pageindex_workflow as mod

    def _cleanup_meta():
        sys.meta_path[:] = [
            f for f in sys.meta_path if type(f).__name__ != "_PageindexGuard"
        ]

    request.addfinalizer(_cleanup_meta)

    def _raising_loader(name, path, fakes):
        raise RuntimeError("simulated source-load failure")

    monkeypatch.setattr(mod, "_load_source_as_module", _raising_loader)

    with pytest.raises(RuntimeError, match="simulated"):
        with mod._synthetic_package_boundary():
            pass

    leaked_guards = [f for f in sys.meta_path if type(f).__name__ == "_PageindexGuard"]
    assert not leaked_guards


def test_regression_leaked_non_synthetic_module_removed(request):
    """Defect 4: non-synthetic module introduced during boundary must be removed."""
    import verification.test_pageindex_workflow as mod

    leaked = "_test_leaked_real_module_xyz"
    request.addfinalizer(lambda: sys.modules.pop(leaked, None))

    with mod._synthetic_package_boundary():
        # Simulate a real (non-synthetic) module imported as a side effect.
        sys.modules[leaked] = ModuleType(leaked)

    modules_after = set(sys.modules.keys())
    assert leaked not in modules_after


def test_regression_pre_existing_modules_preserved():
    """Defect 4: pre-existing modules must not be deleted or corrupted."""
    import verification.test_pageindex_workflow as mod

    assert "os" in sys.modules
    os_before = sys.modules["os"]

    with mod._synthetic_package_boundary():
        pass

    assert "os" in sys.modules
    assert sys.modules["os"] is os_before


def test_regression_cleanup_on_source_load_failure_no_leak(monkeypatch, request):
    """Defects 3,4: failure path must remove guard + leaked modules exactly.

    Covers the full unsafe-runtime package-root policy (litellm, pageindex,
    torch, llama_index, docling, llamaindex_runtime) plus synthetic prefix.
    """
    import pytest
    import verification.test_pageindex_workflow as mod

    leaked = "_test_force_leak_during_failure"

    # Capture baseline before context-manager execution (handles pre-imported modules).
    # Note: baseline is captured here, not before all pytest/test setup.
    modules_before_test = set(sys.modules.keys())

    def _cleanup():
        sys.modules.pop(leaked, None)
        sys.meta_path[:] = [
            f for f in sys.meta_path if type(f).__name__ != "_PageindexGuard"
        ]

    request.addfinalizer(_cleanup)

    def _raising_loader(name, path, fakes):
        # Simulate partial import leaking a real module before failure.
        sys.modules[leaked] = ModuleType(leaked)
        raise RuntimeError("simulated source-load failure")

    monkeypatch.setattr(mod, "_load_source_as_module", _raising_loader)

    with pytest.raises(RuntimeError, match="simulated"):
        with mod._synthetic_package_boundary():
            pass

    # Defect 3: guard removed
    assert not [f for f in sys.meta_path if type(f).__name__ == "_PageindexGuard"]
    # Defect 4: leaked module removed
    modules_after = set(sys.modules.keys())
    assert leaked not in modules_after

    # No NEW modules leaked beyond baseline (delta check using actual helper).
    # Post-cleanup invariant: no introduced module key is legitimate.
    modules_clean = mod._check_no_real_modules_loaded(modules_before_test)
    assert (
        modules_clean
    ), "No synthetic/unsafe-runtime modules should remain after cleanup"


def test_regression_cleanup_detects_leaked_unsafe_root_submodule(monkeypatch):
    """Coverage gap: detect newly leaked forbidden-root submodule even if root was pre-imported.

    This regression proves the delta-based detection would catch a leak like
    'litellm.newly_leaked_submodule' even if 'litellm' was already in sys.modules
    from earlier suite tests. Uses monkeypatch for safe sys.modules restoration.
    Uses ModuleType fakes only - no real unsafe imports.

    Key: Baseline is captured AFTER a pre-existing root is established, proving
    that a NEWLY leaked submodule under that root is detected.
    """
    import verification.test_pageindex_workflow as mod

    # Capture pre-existing litellm if any (before any test modifications)
    litellm_before = sys.modules.get("litellm")

    # Ensure a litellm root exists BEFORE baseline capture
    if litellm_before is None:
        # Root not pre-existing; create it via monkeypatch
        fake_root = ModuleType("litellm")
        monkeypatch.setitem(sys.modules, "litellm", fake_root)
    else:
        # Root pre-existing; save its identity for post-test verification
        fake_root = litellm_before

    # Capture baseline AFTER root is established
    baseline = set(sys.modules.keys())

    # Simulate leak: a NEW submodule under the pre-existing root
    monkeypatch.setitem(
        sys.modules,
        "litellm.newly_leaked_submodule",
        ModuleType("litellm.newly_leaked_submodule"),
    )

    # Use actual helper to detect the leak (no duplicated predicate)
    result = mod._check_no_real_modules_loaded(baseline)
    # The leak MUST be detected
    assert (
        result is False
    ), "Delta detection must catch newly leaked unsafe-root submodule"

    # Verify root identity is unchanged (monkeypatch handles restoration)
    assert (
        sys.modules.get("litellm") is fake_root
    ), "Root module identity must be unchanged after leak detection"


def test_regression_unexpected_runtimeerror_fails_closed(monkeypatch, capsys):
    """Defect 5: unexpected RuntimeError in client.index() must fail closed."""
    import verification.test_pageindex_workflow as mod

    real_creator = mod._create_fake_pageindex_md

    def _raising_creator(tracking):
        fake_pageindex, fake_pageindex_md = real_creator(tracking)

        async def _raising_md_to_tree(*args, **kwargs):
            raise RuntimeError("unexpected simulated fault")

        fake_pageindex_md.md_to_tree = _raising_md_to_tree  # type: ignore[attr-defined]
        return fake_pageindex, fake_pageindex_md

    monkeypatch.setattr(mod, "_create_fake_pageindex_md", _raising_creator)

    result = mod.smoke_test_pageindex_consumer_boundary()
    out = capsys.readouterr().out

    # Must fail closed (return False), never pass.
    assert result is False
    # Unexpected RuntimeError must NOT be classified as observation.
    assert "OBSERVATION: RuntimeError raised" not in out
    # Must surface as an explicit issue with a static message.
    assert "Unexpected RuntimeError" in out


def test_regression_real_source_bodies_execute_and_stub_flows(capsys):
    """Defect 6: real source method bodies execute; fake donor stub flows through."""
    import verification.test_pageindex_workflow as mod

    result = mod.smoke_test_pageindex_consumer_boundary()
    out = capsys.readouterr().out

    assert result is True
    # Real PageIndexTreeAdapter.index_tree() body executed (FORBIDDEN from source).
    assert "FORBIDDEN RuntimeError raised as expected" in out
    # Fake donor md_to_tree was called (donor isolated, real client body ran).
    assert "Fake md_to_tree called" in out
    # Stub returned by fake md_to_tree flowed through real client.index() body.
    assert "Workspace artifacts created with fake response" in out


def test_regression_guard_removed_before_yield_for_md_mode():
    """Defect 7: guard removed before yield; md mode safe (fake preinstalled)."""
    import verification.test_pageindex_workflow as mod

    with mod._synthetic_package_boundary():
        guards = [f for f in sys.meta_path if type(f).__name__ == "_PageindexGuard"]
        assert not guards, "Guard must be removed before yield for md mode"
        # Fake donor preinstalled - md path resolves without meta_path lookup.
        assert "pageindex.page_index_md" in sys.modules


def test_regression_cleanup_failure_fails_closed(request, monkeypatch, capsys):
    """Contract bug: TemporaryDirectory cleanup OSError must fail closed."""
    import verification.test_pageindex_workflow as mod
    import tempfile

    # Force cleanup to raise OSError (simulating permission/disk error)
    original_cleanup = tempfile.TemporaryDirectory.cleanup
    cleanup_called = []

    def _raising_cleanup(self):
        cleanup_called.append(True)
        raise OSError("simulated cleanup failure")

    monkeypatch.setattr(tempfile.TemporaryDirectory, "cleanup", _raising_cleanup)
    # Restore even if test asserts fail
    request.addfinalizer(
        lambda: setattr(tempfile.TemporaryDirectory, "cleanup", original_cleanup)
    )

    result = mod.smoke_test_pageindex_consumer_boundary()
    out = capsys.readouterr().out

    # Cleanup failure must NOT cause function to pass
    assert result is False
    # Must emit explicit issue for cleanup, not swallow silently
    assert "DIAGNOSTIC ISSUE: Temporary directory cleanup failed" in out
    # No exception repr or path in output (static message only)
    assert "simulated cleanup failure" not in out
    assert "OSError" not in out
    # Cannot report complete successful diagnostic
    assert "DIAGNOSTIC OBSERVATION: Consumer-boundary diagnostic complete" not in out
    # Strengthened (LOW gap): assert the patched cleanup was actually invoked,
    # proving the fail-closed branch was reached and not bypassed.
    assert cleanup_called, "Patched TemporaryDirectory.cleanup was never invoked"


def test_regression_constructor_failure_fails_closed(monkeypatch, capsys):
    """Contract: TemporaryDirectory constructor OSError must fail closed, static msg.

    Monkeypatches ``tempfile.TemporaryDirectory`` construction to raise a hostile
    ``OSError`` carrying leakable content (exception message/detail, path, UUID,
    secret token, type word), invokes the REAL
    ``smoke_test_pageindex_consumer_boundary``, and asserts it returns False with
    only static diagnostic-safe wording - no exception repr/type/message, path,
    secret/UUID, forbidden acceptance-like token, or completion-like claim.
    """
    import tempfile
    import verification.test_pageindex_workflow as mod

    # Hostile payload spanning every category of leakable content.
    hostile_detail = "hostile-construction-detail"
    hostile_path = "/top/secret/leak/abc"
    hostile_uuid = "550e8400-e29b-41d4-a716-446655440000"
    hostile_token = "SUPER_SECRET_TOKEN_123"

    class _HostileTempDir:
        """Replacement whose construction raises a hostile OSError."""

        def __init__(self, *args, **kwargs):
            raise OSError(
                f"{hostile_detail} "
                f"path={hostile_path} "
                f"id={hostile_uuid} "
                f"token={hostile_token}"
            )

        def cleanup(self):
            """Never reached; provided for shape parity only."""

        @property
        def name(self):
            """Never reached; provided for shape parity only."""
            return hostile_path

    monkeypatch.setattr(tempfile, "TemporaryDirectory", _HostileTempDir)

    result = mod.smoke_test_pageindex_consumer_boundary()
    out = capsys.readouterr().out

    # Must fail closed (return False), never pass.
    assert result is False
    # Static diagnostic-safe wording must be present.
    assert "DIAGNOSTIC ISSUE: Could not create temporary directory" in out
    # No exception repr/type/message leaked.
    assert "OSError" not in out
    assert hostile_detail not in out
    # No path leaked.
    assert hostile_path not in out
    # No secret/UUID leaked.
    assert hostile_uuid not in out
    assert hostile_token not in out
    # No forbidden acceptance-like tokens (reuses module's own vocabulary check,
    # which permits the "NOT ACCEPTANCE EVIDENCE" negation).
    assert mod._check_no_forbidden_tokens(out) is True
    # No completion-like claim.
    assert "Consumer-boundary diagnostic complete" not in out


def test_regression_llamaindex_path_sealed():
    """Defect 7: fake llamaindex_runtime.__path__ remains [] (fs fallback sealed)."""
    import verification.test_pageindex_workflow as mod

    with mod._synthetic_package_boundary():
        lr = sys.modules.get("llamaindex_runtime")
        assert lr is not None
        assert list(lr.__path__) == []


def test_regression_check_detects_new_synthetic_submodule_leak(request):
    """Track B Defect 1: _check_no_real_modules_loaded must fail closed on newly leaked synthetic.

    RED-proves that a synthetic submodule absent from baseline (e.g., '_diag_rag.leaked')
    returns False. Call sites are post-cleanup; no introduced module key is legitimate.
    """
    import verification.test_pageindex_workflow as mod

    # Baseline does NOT include '_diag_rag.leaked'
    baseline = set(sys.modules.keys())
    # Introduce leak
    leaked = f"{mod._SYNTHETIC_PREFIX}.leaked"
    request.addfinalizer(lambda: sys.modules.pop(leaked, None))
    sys.modules[leaked] = ModuleType(leaked)

    # MUST detect the leak (return False)
    result = mod._check_no_real_modules_loaded(baseline)
    assert result is False, "Newly leaked synthetic submodule must fail closed"


def main() -> None:
    """Run diagnostic and report result."""
    success = smoke_test_pageindex_consumer_boundary()
    if not success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
