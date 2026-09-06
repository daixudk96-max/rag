"""Fresh-process positive global-acceptance proof for the Task #88 slice.

Verifies, in a fresh interpreter, that importing the Task #88 cells
module, the shared testkit, the current Phase 15 E2A harness bridge, the
``DisposableE2aSession`` class, and the Task #88 global live acceptance
selector does NOT load any module matching the mandated prohibited naming
families, and that:

- the family guard (``_phase15_e2a_task88_cells.module_name_is_blocked``)
  matches retained exact module names plus the mandated family fragments
  against plain ``sys.modules`` keys in the child; any match exits with a
  failure code and the violating names on stderr, never importing a
  prohibited module to check itself,
- the live selector exposes the shared required-cell id
  (``TASK88_REQUIRED_CELL_ID == "true_late_dml_failure"``), imports the
  ``DisposableE2aSession`` CLASS (permitted), and constructs NO module-level
  session object or instance,
- the live selector fails closed on authorization before anything else
  (exact RuntimeError message, no session created),
- the live selector is NOT collected by default pytest patterns
  (``phase15_`` prefix, matching neither ``test_*.py`` nor ``*_test.py``),
- the selected live test's first statement is the authorization check,
  followed by exactly one ExitStack/session whose three keyword values are
  EXACTLY the approved safe expressions
  (``container_name=_validate_container_name(_generate_safe_container_name())``,
  ``port=_select_ephemeral_port()``,
  ``password=_generate_test_password()``), exactly one direct positional
  ``_run_late_dml_candidate_impl(session)`` call with no candidate
  selector nesting, one redacted failure raise interpolating only
  ``observations.error_reason``, and exactly 12 success assertions,
- the non-live metadata companion test performs no session work.

The pure ``ast`` shape verifiers and parsed-only fixture builders live in
the non-collected helper ``_phase15_e2a_task88_acceptance_ast_proof.py``
(underscore prefix; outside default collection and outside the counted
``test_phase15_e2a_task88_*.py`` glob). This proof file stays collected
and the helper never creates sessions, accesses environment variables,
accesses a database or Docker, or alters default collection behavior.

Security correction (post-split): the child environment is built ONLY
from an explicit non-sensitive allowlist via per-key ``os.getenv``
(PATH plus Windows SystemRoot/PATHEXT and friends when present); the
builder never enumerates or copies ``os.environ`` and never reads any
sensitive variable. An AST-level guard test pins that behavior.

The AST proofs are structural ``ast`` shape checks rather than substring
scans, and negative fixture tests pin the rejection of the malicious
shapes a future intentional edit could try: reading a sensitive variable
indirectly via ``getattr(os, "getenv")``, reading one through an aliased
module attribute (``alias = os`` then ``alias.environ[...]``), hiding a
session-open call in an assignment/attribute statement, skipping the
authorization check, nesting the candidate pytest selector, issuing a
second helper call, and substituting a hardcoded value for a session
argument. Fixtures are parsed only, never executed, and never open a
session.

No database, no Docker, and no authorized live selector invocation is
performed. This module never opens, globs, greps, or imports any
prohibited historical file.
"""

from __future__ import annotations

import ast
import fnmatch
import glob
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ._phase15_e2a_task88_acceptance_ast_proof import (
    CANDIDATE_SELECTOR_MODULE,
    HELPER_IMPL_FUNCTION,
    LIVE_TEST_NAME,
    METADATA_TEST_NAME,
    _build_env_fixture_with_extra_read,
    _live_acceptance_fixture,
    _single_function_by_name,
    _verify_live_acceptance_body,
    _verify_sanitized_env_structure,
)
from ._phase15_e2a_task88_cells import module_name_is_blocked

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
OKF_DIR = Path(__file__).parent

LIVE_SELECTOR_FILENAME = "phase15_e2a_task88_real_acceptance.py"
COLLECTED_TEST_FILENAMES = (
    "test_phase15_e2a_task88_cells_contracts.py",
    "test_phase15_e2a_task88_reconciler_transactions.py",
    "test_phase15_e2a_task88_preflight_guards.py",
)
PROOF_FILENAME = "test_phase15_e2a_task88_global_acceptance_proof.py"

# String pin of the eight module names the previous exact-name guard
# covered. Every entry must remain covered by the family guard (retained
# exact names or mandated fragments); the pin test below enforces that,
# so a future narrowing of the guard fails here.
HISTORICAL_BLOCKED_MODULE_NAMES: tuple[str, ...] = (
    "tests.llamaindex_runtime.okf.test_real_e2a_reconciler_harness_unit",
    "tests.llamaindex_runtime.okf.test_real_e2a_reconciler_lifecycle_unit",
    "tests.llamaindex_runtime.okf.test_real_e2a_reconciler_acceptance",
    "tests.llamaindex_runtime.okf._real_e2a_reconciler_container_cleanup",
    "tests.llamaindex_runtime.okf._real_e2a_reconciler_lifecycle",
    "tests.llamaindex_runtime.okf._real_e2a_reconciler_types",
    "llamaindex_runtime.okf.e2a_disposable_execution",
    "verification.phase15-okf-ingestion-pipeline.run_e2a_verification",
)


def _sanitized_env() -> dict[str, str]:
    """Child env dict: explicit per-key reads of non-sensitive allowlist keys.

    Each key is read individually via ``os.getenv("...")`` with a literal
    allowlist key; the process env container is never enumerated, copied,
    or read as a whole, and no sensitive variable is ever read.
    """
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

cells = load(
    "tests.llamaindex_runtime.okf._phase15_e2a_task88_cells",
    "_phase15_e2a_task88_cells.py",
)
harness_types = load(
    "tests.llamaindex_runtime.okf._phase15_e2a_harness_types",
    "_phase15_e2a_harness_types.py",
)
live = load(
    "tests.llamaindex_runtime.okf.phase15_e2a_task88_real_acceptance",
    "phase15_e2a_task88_real_acceptance.py",
)

violations = [name for name in sys.modules if cells.module_name_is_blocked(name)]
if violations:
    print("prohibited module loaded: " + ", ".join(sorted(violations)), file=sys.stderr)
    sys.exit(1)

if live.TASK88_REQUIRED_CELL_ID != "true_late_dml_failure":
    sys.exit(2)

if "DisposableE2aSession" not in dir(live):
    sys.exit(5)

module_level_instances = [
    value for value in vars(live).values()
    if isinstance(value, live.DisposableE2aSession)
]
if module_level_instances:
    sys.exit(6)

if "test_phase15_e2a_late_dml_candidate_live" in dir(live):
    sys.exit(7)

try:
    live.test_task88_global_acceptance_metadata()
except Exception:
    sys.exit(8)

from tests.llamaindex_runtime.okf._phase15_e2a_harness_types import _require_authorization

try:
    _require_authorization()
except RuntimeError as exc:
    if str(exc) != "E2A disposable test requires separate authorization":
        sys.exit(3)
else:
    sys.exit(4)
sys.exit(0)
"""


_EXIT_MESSAGES = {
    1: "a prohibited module was loaded by the Task #88 slice",
    2: "live selector TASK88_REQUIRED_CELL_ID differs from the mandate",
    3: "authorization failure message changed from the fixed fails-closed text",
    4: "authorization check passed without the separate authorization flag",
    5: "live selector does not import the DisposableE2aSession class",
    6: "live selector constructs a DisposableE2aSession instance at module level",
    7: "live selector nests the candidate pytest selector",
    8: "the non-live metadata companion test failed in the fresh process",
}


def test_fresh_process_global_acceptance_proof() -> None:
    """Verify Task #88 modules import cleanly without blocked modules."""
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


def test_historical_blocked_names_stay_covered_by_family_guard() -> None:
    """Every previously guarded exact name remains covered by the guard."""
    for name in HISTORICAL_BLOCKED_MODULE_NAMES:
        assert module_name_is_blocked(
            name
        ), f"historical blocked module name not covered: {name}"


def test_sanitized_env_builder_never_reads_broad_environment() -> None:
    """AST guard: _sanitized_env reads only explicit allowlist keys.

    The builder must never enumerate, copy, or read ``os.environ`` as a
    container, must never construct ``dict(os.environ)``, and may only
    read individual non-sensitive keys via literal ``os.getenv`` calls.
    """
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
    for filename in COLLECTED_TEST_FILENAMES:
        assert fnmatch.fnmatch(filename, "test_*.py")
    assert fnmatch.fnmatch(PROOF_FILENAME, "test_*.py")


def test_pytest_collect_only_excludes_live_selector() -> None:
    """A real pytest collection over the Task #88 glob never lists the live selector.

    The pattern expands only to the default-collected Task #88 test
    files (three focused unit modules plus this proof), never the live
    selector, never the underscore-prefixed AST helper, and never any
    prohibited historical file.
    """
    target_paths = sorted(glob.glob(str(OKF_DIR / "test_phase15_e2a_task88_*.py")))
    assert (
        len(target_paths) == len(COLLECTED_TEST_FILENAMES) + 1
    ), f"expected the three unit modules plus the proof: {target_paths}"
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
    """The live selector imports the session class but constructs no session.

    Importing the ``DisposableE2aSession`` class is permitted (and
    required); constructing a session or opening a connection at module
    level is forbidden. Any top-level expression, assignment, or annotated
    assignment that builds a session (or calls a session opener) fails
    here.
    """
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
    assert class_imports, (
        "the live selector must import the DisposableE2aSession class"
    )


def test_live_selector_never_imports_candidate_selector() -> None:
    """The live selector must not import or nest the candidate pytest selector."""
    source = (OKF_DIR / LIVE_SELECTOR_FILENAME).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert node.module.rstrip(".") != CANDIDATE_SELECTOR_MODULE, (
                "the live selector must not import the candidate selector module"
            )
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != CANDIDATE_SELECTOR_MODULE, (
                    "the live selector must not import the candidate selector module"
                )


def test_live_selector_selected_test_global_acceptance_body() -> None:
    """Static proof of the selected live test's exact statement ordering.

    The selected live test must be auth-first, open exactly one
    ExitStack/session whose keyword value expressions are exactly the
    three approved safe expressions, call ``_run_late_dml_candidate_impl``
    (session) exactly once as a direct positional call, never nest the
    candidate pytest selector, raise exactly one redacted RuntimeError on
    failure, and assert all 12 observation fields.
    """
    source = (OKF_DIR / LIVE_SELECTOR_FILENAME).read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = _single_function_by_name(tree, LIVE_TEST_NAME)

    _verify_live_acceptance_body(function)


def test_metadata_companion_test_has_no_session() -> None:
    """The non-live metadata companion test performs no session work.

    The companion test pins the cell-plan metadata only: no authorization,
    no session construction, no helper invocation, and no context manager.
    """
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


def test_sanitized_env_verifier_rejects_getattr_indirection() -> None:
    """Negative AST fixture: getattr(os, "getenv") indirection must fail.

    A future intentional edit could read a sensitive variable indirectly
    with ``getattr(os, "getenv")("DATABASE_URL")`` while every direct
    ``os.getenv`` read stays on the allowlist; a naive getenv-attribute
    walk would not see the indirect call and would accept the shape. The
    structural verifier must reject it. The fixture is parsed only and
    never executed; no session is opened.
    """
    fixture = _build_env_fixture_with_extra_read(
        '("DATABASE_URL", getattr(os, "getenv")("DATABASE_URL"))'
    )
    function = _single_function_by_name(ast.parse(fixture), "_sanitized_env")
    with pytest.raises(AssertionError):
        _verify_sanitized_env_structure(function)


def test_sanitized_env_verifier_rejects_aliased_attribute_broad_read() -> None:
    """Negative AST fixture: an aliased module attribute read must fail.

    A future intentional edit could bind ``alias = os`` and then read a
    sensitive variable through ``alias.environ["DATABASE_URL"]`` while
    every direct ``os.getenv`` read stays on the allowlist; the former
    attribute guard only constrained attributes whose base name is
    literally ``os``, so the aliased base was invisible to it. The
    structural verifier must require every attribute access to be
    exactly the direct ``os.getenv`` form. The fixture is parsed only
    and never executed; no session is opened.
    """
    fixture = _build_env_fixture_with_extra_read(
        '("DATABASE_URL", alias.environ["DATABASE_URL"])',
        preamble="alias = os",
    )
    function = _single_function_by_name(ast.parse(fixture), "_sanitized_env")
    with pytest.raises(AssertionError):
        _verify_sanitized_env_structure(function)


def test_live_acceptance_verifier_rejects_assignment_wrapped_session_open() -> None:
    """Negative AST fixture: assignment-wrapped session open must fail.

    A future intentional edit could hide a session-open call in an
    assignment/attribute form
    (``conn = session.open_fresh_attested_connection()``); a bare-call
    filter would not count the assignment statement and name-based checks
    would not see attribute accesses, so the shape would pass. The strict
    body proof must reject it. The fixture is parsed only and never
    executed; no session is opened.
    """
    fixture = _live_acceptance_fixture(session_open_assignment=True)
    function = _single_function_by_name(ast.parse(fixture), LIVE_TEST_NAME)
    with pytest.raises(AssertionError):
        _verify_live_acceptance_body(function)


def test_live_acceptance_verifier_rejects_missing_authorization() -> None:
    """Negative AST fixture: a skipped authorization check must fail.

    A future intentional edit could open the session before (or without)
    the authorization check; the strict body proof requires the bare
    ``_require_authorization()`` call as the first statement. The fixture
    is parsed only and never executed; no session is opened.
    """
    fixture = _live_acceptance_fixture(omit_auth=True)
    function = _single_function_by_name(ast.parse(fixture), LIVE_TEST_NAME)
    with pytest.raises(AssertionError):
        _verify_live_acceptance_body(function)


def test_live_acceptance_verifier_rejects_candidate_selector_nesting() -> None:
    """Negative AST fixture: nesting the candidate selector must fail.

    A future intentional edit could satisfy the session/helper shape and
    still delegate to the standalone candidate pytest selector
    (``test_phase15_e2a_late_dml_candidate_live()``); the strict body
    proof must reject any reference to the candidate selector inside the
    selected live test. The fixture is parsed only and never executed; no
    session is opened.
    """
    fixture = _live_acceptance_fixture(nested_candidate_selector=True)
    function = _single_function_by_name(ast.parse(fixture), LIVE_TEST_NAME)
    with pytest.raises(AssertionError):
        _verify_live_acceptance_body(function)


def test_live_acceptance_verifier_rejects_second_helper_call() -> None:
    """Negative AST fixture: a duplicated helper invocation must fail.

    A future intentional edit could invoke
    ``_run_late_dml_candidate_impl(session)`` more than once; the strict
    body proof requires exactly one direct positional helper call. The
    fixture is parsed only and never executed; no session is opened.
    """
    fixture = _live_acceptance_fixture(second_helper_call=True)
    function = _single_function_by_name(ast.parse(fixture), LIVE_TEST_NAME)
    with pytest.raises(AssertionError):
        _verify_live_acceptance_body(function)


def test_live_acceptance_verifier_rejects_hardcoded_session_value() -> None:
    """Negative AST fixture: a hardcoded session argument value must fail.

    A future intentional edit could keep every keyword NAME but bind
    ``container_name`` to a hardcoded literal (or any substituted value)
    instead of the approved
    ``_validate_container_name(_generate_safe_container_name())``
    expression; a verifier that inspects only keyword names would accept
    the shape. The strict body proof must reject any value expression
    that is not exactly the three approved safe expressions. The fixture
    is parsed only and never executed; no session is opened.
    """
    fixture = _live_acceptance_fixture(hardcoded_session_value=True)
    function = _single_function_by_name(ast.parse(fixture), LIVE_TEST_NAME)
    with pytest.raises(AssertionError):
        _verify_live_acceptance_body(function)
