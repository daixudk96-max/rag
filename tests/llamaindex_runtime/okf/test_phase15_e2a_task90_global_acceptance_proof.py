"""Fresh-process global-acceptance proof for the Task #90 slice.

Verifies, in a fresh interpreter, that importing the Task #90 support,
types, live cells, the current Phase 15 E2A harness bridge, the
``DisposableE2aSession`` class, and the Task #90 global live acceptance
selector does NOT load the protected historical verification runner, and
that:

- the live selector exposes the selected live test and the non-live
  metadata companion, constructs NO module-level session object or
  instance, and never opens a connection at module level,
- the live selector fails closed on authorization before anything else
  (exact RuntimeError message, no session created),
- the live selector is NOT collected by default pytest patterns
  (``phase15_`` prefix, matching neither ``test_*.py`` nor ``*_test.py``),
- the selected live test's first statement is the authorization check,
  followed by exactly one ExitStack/session whose three keyword values are
  EXACTLY the approved safe expressions, exactly one direct positional
  ``_run_task90_live_proof(session)`` call, one redacted failure raise
  interpolating only ``observations.error_reason``, and exactly 14 success
  assertions covering every required observation field,
- the live cells helper source pins the real production boundaries (default
  ``E2aReconciler()`` with no injected repository or builder, real strict
  E2A admission, the full-collection scope snapshot, the single-use
  producer token, and the binding build/verify/artifact surface) with no
  fake/replacement machinery and no ``NotImplementedError``,
- the binding/serializer support module pins the runtime
  ``dataclasses.fields`` digest derivation and the redacted artifact
  surface, and performs no environment/secret access, no database/Docker
  import, no session construction, no mock/fake machinery, no unsafe
  dynamic import or exec/eval/subprocess, and never imports the protected
  historical runner,
- the live cells module performs no environment reads, no session
  construction, and no database/Docker at module level,
- the protected historical runner is NEVER imported or executed; the only
  contact is ``read_bytes()`` used to pin its SHA-256 and size, which are
  byte-identical to the pinned baseline.

The pure ``ast`` shape verifiers and parsed-only fixture builders live in
the non-collected helper ``_phase15_e2a_task90_ast_proof.py`` (underscore
prefix; outside default collection and outside the counted
``test_phase15_e2a_task90_*.py`` glob). This proof file stays collected and
the helper never creates sessions, accesses environment variables,
accesses a database or Docker, or alters default collection behavior.

Security correction: the child environment is built ONLY from an explicit
non-sensitive allowlist via per-key ``os.getenv``; the builder never
enumerates or copies ``os.environ`` and never reads any sensitive
variable. An AST-level guard test pins that behavior.

The Task #90 live cells legitimately REUSE the ``_real_e2a_reconciler_*``
lifecycle/testkit primitives (mandated by the Task #90 brief), which
transitively import the production OKF acceptance/execution helpers
(``e2a_disposable_acceptance``, ``e2a_disposable_execution``). Those are
legitimate production dependencies of the mandated reuse surface, so they
are deliberately NOT in the blocked-module set; only the protected
historical verification runner is blocked.

No database, no Docker, and no authorized live selector invocation is
performed. The protected historical runner is NEVER imported or executed;
the only contact is ``read_bytes()`` to pin its SHA-256 and size. This
module never globs, greps, or imports any prohibited historical file.
"""

from __future__ import annotations

import ast
import fnmatch
import glob
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ._phase15_e2a_task90_ast_proof import (
    HELPER_IMPL_FUNCTION,
    LIVE_CELLS_FILENAME,
    LIVE_SELECTOR_FILENAME,
    METADATA_TEST_NAME,
    SUPPORT_FILENAME,
    _build_env_fixture_with_extra_read,
    _live_acceptance_fixture,
    _single_function_by_name,
    _task90_registration_pin_fixture,
    _verify_live_acceptance_body,
    _verify_live_cells_source,
    _verify_sanitized_env_structure,
    _verify_support_source,
    _verify_task90_parent_registration_pin,
)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
OKF_DIR = Path(__file__).parent

COLLECTED_TEST_FILENAMES = (
    "test_phase15_e2a_task90_contracts.py",
    "test_phase15_e2a_task90_binding.py",
    "test_phase15_e2a_task90_corpus.py",
)
PROOF_FILENAME = "test_phase15_e2a_task90_global_acceptance_proof.py"

# Mandated prohibited-module families: the protected historical verification
# runner. The ``_real_e2a_*`` lifecycle/testkit families and their production
# dependency on the OKF acceptance/execution helpers are deliberately NOT
# blocked (Task #90 is mandated to reuse the ``_real_e2a_*`` primitives).
BLOCKED_EXACT_MODULE_NAMES = frozenset(
    {
        "verification.phase15-okf-ingestion-pipeline.run_e2a_verification",
    }
)
BLOCKED_MODULE_FRAGMENTS = frozenset()

HISTORICAL_RUNNER_SHA256 = (
    "c084486411506b5cd07bb81816e998634a7686d8b1c2d7437e11dce652827e60"
)
HISTORICAL_RUNNER_SIZE = 42167


def _module_name_is_blocked(name: str) -> bool:
    return name in BLOCKED_EXACT_MODULE_NAMES or any(
        fragment in name for fragment in BLOCKED_MODULE_FRAGMENTS
    )


def _sanitized_env() -> dict[str, str]:
    """Child env dict: explicit per-key reads of non-sensitive allowlist keys."""
    env: dict[str, str] = {}
    for key, value in (
        ("PATH", os.getenv("PATH")),
        ("HOME", os.getenv("HOME")),
        ("SystemRoot", os.getenv("SystemRoot")),
        ("PATHEXT", os.getenv("PATHEXT")),
        ("WINDIR", os.getenv("WINDIR")),
        ("TEMP", os.getenv("TEMP")),
        ("TMP", os.getenv("TMP")),
        ("USERPROFILE", os.getenv("USERPROFILE")),
        ("HOMEDRIVE", os.getenv("HOMEDRIVE")),
        ("HOMEPATH", os.getenv("HOMEPATH")),
        ("COMSPEC", os.getenv("COMSPEC")),
        ("NUMBER_OF_PROCESSORS", os.getenv("NUMBER_OF_PROCESSORS")),
        ("PROCESSOR_ARCHITECTURE", os.getenv("PROCESSOR_ARCHITECTURE")),
    ):
        if value is not None:
            env[key] = value
    return env


def _spec_loader_script() -> str:
    """Fresh-process script: package chain + spec loads of the slice modules."""
    return f"""
import os
import sys
import importlib.util
from types import ModuleType
from pathlib import Path

project_root = Path("{PROJECT_ROOT.as_posix()}")
sys.path.insert(0, str(project_root))

for var in (
    "OKF_E2A_DISPOSABLE_TEST_AUTHORIZED",
    "DATABASE_URL",
    "FORMAL_RUNTIME_DATABASE_URL",
    "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE",
    "OKF_REBUILD_EXPECTED_DATABASE",
    "OKF_FAILURE_AUDIT_ACCEPTANCE",
    "OKF_REBUILD_DOCKER_ACCEPTANCE",
    "PGSERVICE",
    "PGSERVICEFILE",
    "PGSYSCONFDIR",
    "PGHOST",
    "PGPORT",
    "PGUSER",
    "PGPASSWORD",
    "PGDATABASE",
):
    os.environ.pop(var, None)

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

BLOCKED_EXACT_MODULE_NAMES = frozenset({{
    "verification.phase15-okf-ingestion-pipeline.run_e2a_verification",
}})
BLOCKED_MODULE_FRAGMENTS = frozenset()

def _module_name_is_blocked(name):
    return name in BLOCKED_EXACT_MODULE_NAMES or any(
        fragment in name for fragment in BLOCKED_MODULE_FRAGMENTS
    )

def load(module_name, file_name):
    spec = importlib.util.spec_from_file_location(
        module_name,
        project_root / "tests" / "llamaindex_runtime" / "okf" / file_name,
        submodule_search_locations=[],
    )
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "tests.llamaindex_runtime.okf"
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

types = load(
    "tests.llamaindex_runtime.okf._phase15_e2a_task90_types",
    "_phase15_e2a_task90_types.py",
)
support = load(
    "tests.llamaindex_runtime.okf._phase15_e2a_task90_support",
    "_phase15_e2a_task90_support.py",
)
cells = load(
    "tests.llamaindex_runtime.okf._phase15_e2a_task90_live_cells",
    "_phase15_e2a_task90_live_cells.py",
)
harness_types = load(
    "tests.llamaindex_runtime.okf._phase15_e2a_harness_types",
    "_phase15_e2a_harness_types.py",
)
harness_lifecycle = load(
    "tests.llamaindex_runtime.okf._phase15_e2a_harness_lifecycle",
    "_phase15_e2a_harness_lifecycle.py",
)
live = load(
    "tests.llamaindex_runtime.okf.phase15_e2a_task90_live_acceptance",
    "phase15_e2a_task90_live_acceptance.py",
)

violations = [name for name in sys.modules if _module_name_is_blocked(name)]
if violations:
    print("prohibited module loaded: " + ", ".join(sorted(violations)), file=sys.stderr)
    sys.exit(1)

if "test_task90_authorized_live_acceptance" not in dir(live):
    sys.exit(2)
if "test_task90_live_acceptance_metadata" not in dir(live):
    sys.exit(3)

if "DisposableE2aSession" not in dir(live):
    sys.exit(4)

module_level_instances = [
    value for value in vars(live).values()
    if isinstance(value, live.DisposableE2aSession)
]
if module_level_instances:
    sys.exit(5)

try:
    live.test_task90_live_acceptance_metadata()
except Exception:
    sys.exit(6)

from tests.llamaindex_runtime.okf._phase15_e2a_harness_types import _require_authorization

try:
    _require_authorization()
except RuntimeError as exc:
    if str(exc) != "E2A disposable test requires separate authorization":
        sys.exit(7)
else:
    sys.exit(8)

if "acquire_build_token" not in dir(support):
    sys.exit(9)
if "Task90EvidenceBinding" not in dir(support):
    sys.exit(10)
sys.exit(0)
"""


_EXIT_MESSAGES = {
    1: "a prohibited module was loaded by the Task #90 slice",
    2: "live selector lacks the selected authorized live acceptance test",
    3: "live selector lacks the non-live metadata companion test",
    4: "live selector does not import the DisposableE2aSession class",
    5: "live selector constructs a DisposableE2aSession instance at module level",
    6: "the non-live metadata companion test failed in the fresh process",
    7: "authorization failure message changed from the fixed fails-closed text",
    8: "authorization check passed without the separate authorization flag",
    9: "support module lacks the single-use producer build token surface",
    10: "support module lacks the Task90EvidenceBinding class",
}


def test_fresh_process_global_acceptance_proof() -> None:
    """Verify Task #90 modules import cleanly without blocked modules."""
    result = subprocess.run(
        [sys.executable, "-c", _spec_loader_script()],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        env=_sanitized_env(),
    )

    if result.returncode != 0:
        message = _EXIT_MESSAGES.get(result.returncode, "unexpected failure")
        assert False, f"fresh-process verification failed: {message}\n{result.stderr}"


def test_blocked_module_families_are_pinned() -> None:
    """The protected runner stays blocked; mandated reuse surface is allowed."""
    assert (
        _module_name_is_blocked(
            "verification.phase15-okf-ingestion-pipeline.run_e2a_verification"
        )
        is True
    )
    # Task #90 is mandated to reuse the _real_e2a_* lifecycle/testkit
    # primitives and the disposable acceptance/corpus machinery; those
    # families (and their production OKF execution dependencies) must remain
    # unblocked.
    for name in (
        "os",
        "sys",
        "pytest",
        "importlib.util",
        "llamaindex_runtime.okf.e2a_contracts",
        "llamaindex_runtime.okf.e2a_reconciler",
        "llamaindex_runtime.okf.e2a_materialization_repository",
        "llamaindex_runtime.okf.e2a_admission",
        "llamaindex_runtime.okf.e2a_disposable_acceptance",
        "llamaindex_runtime.okf.e2a_disposable_execution",
        "tests.llamaindex_runtime.okf._phase15_e2a_task90_live_cells",
        "tests.llamaindex_runtime.okf._phase15_e2a_task90_support",
        "tests.llamaindex_runtime.okf._phase15_e2a_task90_types",
        "tests.llamaindex_runtime.okf.phase15_e2a_task90_live_acceptance",
        "tests.llamaindex_runtime.okf._real_e2a_reconciler_testkit",
        "tests.llamaindex_runtime.okf._real_e2a_reconciler_lifecycle",
        "tests.llamaindex_runtime.okf._real_e2a_reconciler_types",
    ):
        assert _module_name_is_blocked(name) is False, name


def test_historical_runner_hash_and_size_unchanged() -> None:
    """The protected historical runner is byte-identical to the pinned baseline.

    The only contact with the protected runner is ``read_bytes()`` for the
    SHA-256/size pin; it is never imported, parsed, or executed here.
    """
    runner = (
        PROJECT_ROOT
        / "verification"
        / "phase15-okf-ingestion-pipeline"
        / "run_e2a_verification.py"
    )
    payload = runner.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == HISTORICAL_RUNNER_SHA256
    assert len(payload) == HISTORICAL_RUNNER_SIZE


def test_sanitized_env_builder_never_reads_broad_environment() -> None:
    """AST guard: _sanitized_env reads only explicit allowlist keys."""
    source = (OKF_DIR / PROOF_FILENAME).read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = _single_function_by_name(tree, "_sanitized_env")
    segment = ast.get_source_segment(source, function)
    assert segment is not None

    for forbidden in (
        "os.environ",
        "environ",
        "dict(",
        "__import__",
        ".items(",
        ".keys(",
        ".values(",
        ".copy(",
        ".get(",
    ):
        assert (
            forbidden not in segment
        ), f"_sanitized_env must not use broad environment access: {forbidden!r}"

    _verify_sanitized_env_structure(function)


def test_live_selector_not_matched_by_default_pytest_patterns() -> None:
    """phase15_ filename prefix must escape default pytest collection."""
    assert not fnmatch.fnmatch(LIVE_SELECTOR_FILENAME, "test_*.py")
    assert not fnmatch.fnmatch(LIVE_SELECTOR_FILENAME, "*_test.py")
    for filename in COLLECTED_TEST_FILENAMES + (PROOF_FILENAME,):
        assert fnmatch.fnmatch(filename, "test_*.py")


def test_pytest_collect_only_excludes_live_selector() -> None:
    """A real pytest collection over the Task #90 glob never lists the live selector."""
    target_paths = sorted(glob.glob(str(OKF_DIR / "test_phase15_e2a_task90_*.py")))
    assert (
        len(target_paths) == len(COLLECTED_TEST_FILENAMES) + 1
    ), f"expected the three collected modules plus the proof: {target_paths}"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *target_paths],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        env=_sanitized_env(),
    )

    output = result.stdout + result.stderr
    assert result.returncode == 0, f"collection failed:\n{output}"
    assert LIVE_SELECTOR_FILENAME not in output
    for filename in COLLECTED_TEST_FILENAMES:
        assert filename in output
    assert PROOF_FILENAME in output


def test_live_selector_forbids_module_level_session_construction() -> None:
    """The live selector imports the session class but constructs no session."""
    source = (OKF_DIR / LIVE_SELECTOR_FILENAME).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for statement in tree.body:
        if isinstance(statement, (ast.Expr, ast.Assign, ast.AnnAssign)):
            for node in ast.walk(statement):
                if isinstance(node, ast.Call) and (
                    (
                        isinstance(node.func, ast.Name)
                        and node.func.id == "DisposableE2aSession"
                    )
                    or (
                        isinstance(node.func, ast.Attribute)
                        and node.func.attr == "open_fresh_attested_connection"
                    )
                ):
                    raise AssertionError(
                        "module-level session construction or connection "
                        "opening is forbidden"
                    )
    class_imports = [
        node
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module is not None
        and "harness_lifecycle" in node.module
        and any(alias.name == "DisposableE2aSession" for alias in node.names)
    ]
    assert class_imports, "the live selector must import the DisposableE2aSession class"


def test_live_selector_selected_test_global_acceptance_body() -> None:
    """Static proof of the selected live test's exact statement ordering."""
    source = (OKF_DIR / LIVE_SELECTOR_FILENAME).read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = _single_function_by_name(tree, "test_task90_authorized_live_acceptance")

    _verify_live_acceptance_body(function)


def test_metadata_companion_test_has_no_session() -> None:
    """The non-live metadata companion test performs no session work."""
    source = (OKF_DIR / LIVE_SELECTOR_FILENAME).read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = _single_function_by_name(tree, METADATA_TEST_NAME)
    referenced = {node.id for node in ast.walk(function) if isinstance(node, ast.Name)}
    assert "DisposableE2aSession" not in referenced
    assert "open_fresh_attested_connection" not in referenced
    assert HELPER_IMPL_FUNCTION not in referenced
    assert not any(
        isinstance(node, ast.With) for node in ast.walk(function)
    ), "the metadata companion test must not open a context manager"


def test_live_cells_helper_source_pins_real_boundaries_no_fakes() -> None:
    """AST/source proof: the live cells module pins the real producer boundaries."""
    source = (OKF_DIR / LIVE_CELLS_FILENAME).read_text(encoding="utf-8")
    tree = ast.parse(source)
    _verify_live_cells_source(source)
    helpers = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == HELPER_IMPL_FUNCTION
    ]
    assert (
        len(helpers) == 1
    ), "the live helper must exist exactly once at module top level"


def test_live_cells_source_default_reconciler_no_injection() -> None:
    """The live cells construct the default E2aReconciler() with no injection.

    AST-based: the observation field
    ``default_reconciler_default_repository`` legitimately contains the
    substring ``repository=``, so a naive source-substring guard is
    unreliable. Every ``E2aReconciler(...)`` call must be the zero-argument
    form (default repository and builder only).
    """
    source = (OKF_DIR / LIVE_CELLS_FILENAME).read_text(encoding="utf-8")
    assert "E2aReconciler()" in source
    tree = ast.parse(source)
    reconciler_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "E2aReconciler"
    ]
    assert (
        len(reconciler_calls) == 1
    ), "the live cells must construct E2aReconciler() once"
    for call in reconciler_calls:
        assert (
            not call.args
        ), "E2aReconciler must be constructed with no positional args"
        assert (
            not call.keywords
        ), "E2aReconciler must be constructed with no injected repository/builder keyword"


def test_live_cells_register_parents_before_reconcile_and_cleanup() -> None:
    """The live proof registers admitted parents before reconcile and cleans up.

    Production ``E2aReconciler._acquire_scope_locks`` fail-closes unless every
    admitted parent has exactly one ``document_versions`` row. The live proof
    must call ``_register_task90_parents`` on a named fresh connection before
    the first ``reconcile`` and close that connection in the ``finally`` block.
    """
    source = (OKF_DIR / LIVE_CELLS_FILENAME).read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = _single_function_by_name(tree, HELPER_IMPL_FUNCTION)
    _verify_task90_parent_registration_pin(function)


def test_task90_registration_pin_accepts_baseline_fixture() -> None:
    """Positive AST fixture: the approved registration/cleanup skeleton passes."""
    fixture = _task90_registration_pin_fixture()
    function = _single_function_by_name(ast.parse(fixture), HELPER_IMPL_FUNCTION)
    _verify_task90_parent_registration_pin(function)


def test_task90_registration_pin_rejects_stale_connection_source() -> None:
    """Negative AST fixture: a stale/non-session connection source must fail.

    The registration connection must be assigned from
    ``session.open_fresh_attested_connection()`` in the live proof, never
    reused from a prior/stale binding.
    """
    fixture = _task90_registration_pin_fixture(stale_connection_source=True)
    function = _single_function_by_name(ast.parse(fixture), HELPER_IMPL_FUNCTION)
    with pytest.raises(AssertionError):
        _verify_task90_parent_registration_pin(function)


def test_task90_registration_pin_rejects_fake_reconcile_receiver() -> None:
    """Negative AST fixture: a non-reconciler .reconcile receiver must fail.

    The real reconcile calls must be exactly ``reconciler.reconcile(...)``;
    a look-alike receiver that merely exposes ``.reconcile`` must be rejected.
    """
    fixture = _task90_registration_pin_fixture(fake_reconcile_receiver=True)
    function = _single_function_by_name(ast.parse(fixture), HELPER_IMPL_FUNCTION)
    with pytest.raises(AssertionError):
        _verify_task90_parent_registration_pin(function)


def test_task90_registration_pin_rejects_duplicate_registration() -> None:
    """Negative AST fixture: more than one registration call must fail.

    Exactly one ``_register_task90_parents(conn_parents, desired)`` call and
    exactly one fresh session-factory assignment are required; a duplicated
    registration is rejected.
    """
    fixture = _task90_registration_pin_fixture(second_register_call=True)
    function = _single_function_by_name(ast.parse(fixture), HELPER_IMPL_FUNCTION)
    with pytest.raises(AssertionError):
        _verify_task90_parent_registration_pin(function)


def test_task90_registration_pin_rejects_fresh_assignment_after_registration() -> None:
    """Negative AST fixture: a fresh assignment AFTER registration must fail.

    The registration variable is bound to a stale source first and the direct
    ``session.open_fresh_attested_connection()`` assignment appears only after
    ``_register_task90_parents``, so the fresh-source pin must reject it on
    ordering grounds even though the assignment count is exactly one.
    """
    fixture = _task90_registration_pin_fixture(fresh_assignment_after_registration=True)
    function = _single_function_by_name(ast.parse(fixture), HELPER_IMPL_FUNCTION)
    with pytest.raises(AssertionError):
        _verify_task90_parent_registration_pin(function)


def test_support_module_source_pins_binding_and_serializer() -> None:
    """AST/source proof: the binding/serializer support module keeps its guards."""
    source = (OKF_DIR / SUPPORT_FILENAME).read_text(encoding="utf-8")
    _verify_support_source(source)


def test_spec_loader_script_generates_deterministic_set_literal_frozensets() -> None:
    """The generated child script carries literal set-literal frozensets."""
    script = _spec_loader_script()
    assert (
        "BLOCKED_EXACT_MODULE_NAMES = frozenset({\n" in script
    ), "generated script must contain the intended set-literal block"
    assert (
        "BLOCKED_MODULE_FRAGMENTS = frozenset()" in script
    ), "generated script must contain the intended empty frozenset"
    compile(script, "<task90-child>", "exec")


def test_sanitized_env_verifier_rejects_getattr_indirection() -> None:
    """Negative AST fixture: getattr(os, "getenv") indirection must fail."""
    fixture = _build_env_fixture_with_extra_read(
        '("DATABASE_URL", getattr(os, "getenv")("DATABASE_URL"))'
    )
    function = _single_function_by_name(ast.parse(fixture), "_sanitized_env")
    with pytest.raises(AssertionError):
        _verify_sanitized_env_structure(function)


def test_sanitized_env_verifier_rejects_aliased_attribute_broad_read() -> None:
    """Negative AST fixture: an aliased module attribute read must fail."""
    fixture = _build_env_fixture_with_extra_read(
        '("DATABASE_URL", alias.environ["DATABASE_URL"])',
        preamble="alias = os",
    )
    function = _single_function_by_name(ast.parse(fixture), "_sanitized_env")
    with pytest.raises(AssertionError):
        _verify_sanitized_env_structure(function)


def test_live_acceptance_verifier_rejects_assignment_wrapped_session_open() -> None:
    """Negative AST fixture: assignment-wrapped session open must fail."""
    fixture = _live_acceptance_fixture(session_open_assignment=True)
    function = _single_function_by_name(
        ast.parse(fixture), "test_task90_authorized_live_acceptance"
    )
    with pytest.raises(AssertionError):
        _verify_live_acceptance_body(function)


def test_live_acceptance_verifier_rejects_missing_authorization() -> None:
    """Negative AST fixture: a skipped authorization check must fail."""
    fixture = _live_acceptance_fixture(omit_auth=True)
    function = _single_function_by_name(
        ast.parse(fixture), "test_task90_authorized_live_acceptance"
    )
    with pytest.raises(AssertionError):
        _verify_live_acceptance_body(function)


def test_live_acceptance_verifier_rejects_second_helper_call() -> None:
    """Negative AST fixture: a duplicated helper invocation must fail."""
    fixture = _live_acceptance_fixture(second_helper_call=True)
    function = _single_function_by_name(
        ast.parse(fixture), "test_task90_authorized_live_acceptance"
    )
    with pytest.raises(AssertionError):
        _verify_live_acceptance_body(function)


def test_live_acceptance_verifier_rejects_hardcoded_session_value() -> None:
    """Negative AST fixture: a hardcoded session argument value must fail."""
    fixture = _live_acceptance_fixture(hardcoded_session_value=True)
    function = _single_function_by_name(
        ast.parse(fixture), "test_task90_authorized_live_acceptance"
    )
    with pytest.raises(AssertionError):
        _verify_live_acceptance_body(function)


def test_live_acceptance_verifier_rejects_missing_assertion() -> None:
    """Negative AST fixture: a missing success assertion must fail."""
    fixture = _live_acceptance_fixture(omitted_assertion_field="rerun_no_op")
    function = _single_function_by_name(
        ast.parse(fixture), "test_task90_authorized_live_acceptance"
    )
    with pytest.raises(AssertionError):
        _verify_live_acceptance_body(function)


def test_live_cells_source_rejects_fake_machinery() -> None:
    """Negative source pin: fake/stub machinery must fail the live-cells guard."""
    source = (OKF_DIR / LIVE_CELLS_FILENAME).read_text(encoding="utf-8")
    forged = source.replace("admit_e2a_corpus", "admit_corpus_fake")
    with pytest.raises(AssertionError):
        _verify_live_cells_source(forged)


def test_support_source_rejects_env_secret_access() -> None:
    """Negative source pin: env/secret access must fail the support guard."""
    source = (OKF_DIR / SUPPORT_FILENAME).read_text(encoding="utf-8")
    forged = source + "\n_DATABASE_URL = os.environ['DATABASE_URL']\n"
    with pytest.raises(AssertionError):
        _verify_support_source(forged)
