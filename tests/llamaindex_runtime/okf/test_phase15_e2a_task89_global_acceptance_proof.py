"""Fresh-process positive global-acceptance proof for the Task #89 slice.

Verifies, in a fresh interpreter, that importing the Task #89 live cells
module, the current Phase 15 E2A harness bridge, the ``DisposableE2aSession``
class, and the Task #89 global live acceptance selector does NOT load any
module matching the mandated prohibited naming families, and that:

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
  ``_run_task89_durable_integration_impl(session)`` call, one redacted
  failure raise interpolating only ``observations.error_reason``, and
  exactly 25 success assertions covering every required observation field,
- the live cells helper source pins the exact real production boundaries
  (pipeline, ingestor, serializer/publisher/admission, reconciler/builder,
  registry writer, PageIndex adapter) with no fake/replacement machinery
  and no ``NotImplementedError``,
- the live cells module performs no environment reads, no session
  construction, and no database/Docker at module level.

The pure ``ast`` shape verifiers and parsed-only fixture builders live in
the non-collected helper ``_phase15_e2a_task89_ast_proof.py`` (underscore
prefix; outside default collection and outside the counted
``test_phase15_e2a_task89_*.py`` glob). This proof file stays collected and
the helper never creates sessions, accesses environment variables,
accesses a database or Docker, or alters default collection behavior.

Security correction (post-split): the child environment is built ONLY
from an explicit non-sensitive allowlist via per-key ``os.getenv``; the
builder never enumerates or copies ``os.environ`` and never reads any
sensitive variable. An AST-level guard test pins that behavior.

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

from ._phase15_e2a_task89_ast_proof import (
    HELPER_IMPL_FUNCTION,
    LIVE_CELLS_FILENAME,
    LIVE_SELECTOR_FILENAME,
    METADATA_TEST_NAME,
    SUPPORT_FILENAME,
    _build_env_fixture_with_extra_read,
    _live_acceptance_fixture,
    _single_function_by_name,
    _verify_helper_finally_closes_factory,
    _verify_live_acceptance_body,
    _verify_live_cells_boundaries,
    _verify_live_cells_source,
    _verify_sanitized_env_structure,
    _verify_support_source,
)
from ._phase15_e2a_task89_observer_sql_proof import (
    OBSERVER_DURABLE_FUNCTION,
    _verify_observer_durable_sql,
)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
OKF_DIR = Path(__file__).parent

COLLECTED_TEST_FILENAMES = (
    "test_phase15_e2a_task89_contracts.py",
    "test_phase15_e2a_task89_live_ingestor_loader.py",
)
PROOF_FILENAME = "test_phase15_e2a_task89_global_acceptance_proof.py"

# Mandated prohibited-module families: exact historical module names plus
# family fragments, matched on plain ``sys.modules`` keys in the child.
BLOCKED_EXACT_MODULE_NAMES = frozenset(
    {
        "llamaindex_runtime.okf.e2a_disposable_execution",
        "verification.phase15-okf-ingestion-pipeline.run_e2a_verification",
    }
)
BLOCKED_MODULE_FRAGMENTS = frozenset(
    {
        "real_e2a_reconciler",
        "disposable_acceptance",
        "disposable_postgres",
        "_real_e2a_",
    }
)


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
    "llamaindex_runtime.okf.e2a_disposable_execution",
    "verification.phase15-okf-ingestion-pipeline.run_e2a_verification",
}})
BLOCKED_MODULE_FRAGMENTS = frozenset({{
    "real_e2a_reconciler",
    "disposable_acceptance",
    "disposable_postgres",
    "_real_e2a_",
}})

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

cells = load(
    "tests.llamaindex_runtime.okf._phase15_e2a_task89_live_cells",
    "_phase15_e2a_task89_live_cells.py",
)
harness_types = load(
    "tests.llamaindex_runtime.okf._phase15_e2a_harness_types",
    "_phase15_e2a_harness_types.py",
)
live = load(
    "tests.llamaindex_runtime.okf.phase15_e2a_task89_live_acceptance",
    "phase15_e2a_task89_live_acceptance.py",
)

violations = [name for name in sys.modules if _module_name_is_blocked(name)]
if violations:
    print("prohibited module loaded: " + ", ".join(sorted(violations)), file=sys.stderr)
    sys.exit(1)

if "test_task89_authorized_live_acceptance" not in dir(live):
    sys.exit(2)
if "test_task89_global_acceptance_metadata" not in dir(live):
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
    live.test_task89_global_acceptance_metadata()
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
sys.exit(0)
"""


_EXIT_MESSAGES = {
    1: "a prohibited module was loaded by the Task #89 slice",
    2: "live selector lacks the selected authorized live acceptance test",
    3: "live selector lacks the non-live metadata companion test",
    4: "live selector does not import the DisposableE2aSession class",
    5: "live selector constructs a DisposableE2aSession instance at module level",
    6: "the non-live metadata companion test failed in the fresh process",
    7: "authorization failure message changed from the fixed fails-closed text",
    8: "authorization check passed without the separate authorization flag",
}


def test_fresh_process_global_acceptance_proof() -> None:
    """Verify Task #89 modules import cleanly without blocked modules."""
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
    """The mandated prohibited-module families stay covered."""
    for name in (
        "llamaindex_runtime.okf.e2a_disposable_execution",
        "verification.phase15-okf-ingestion-pipeline.run_e2a_verification",
        "llamaindex_runtime.okf.e2a_disposable_acceptance",
        "tests.llamaindex_runtime.okf._real_e2a_reconciler_testkit",
        "tests.llamaindex_runtime.okf.test_real_e2a_reconciler_harness_unit",
        "tests.llamaindex_runtime.okf._real_e2a_reconciler_types",
        "tests.llamaindex_runtime.okf.disposable_postgres_testkit",
    ):
        assert _module_name_is_blocked(name) is True, name
    for name in (
        "os",
        "sys",
        "pytest",
        "importlib.util",
        "llamaindex_runtime.okf.e2a_contracts",
        "llamaindex_runtime.okf.e2a_reconciler",
        "tests.llamaindex_runtime.okf._phase15_e2a_task89_live_cells",
        "tests.llamaindex_runtime.okf.phase15_e2a_task89_live_acceptance",
        "tests.llamaindex_runtime.okf.test_phase15_e2a_task89_contracts",
        "tests.llamaindex_runtime.okf.test_phase15_e2a_task89_live_ingestor_loader",
        "verification.phase15-okf-ingestion-pipeline",
    ):
        assert _module_name_is_blocked(name) is False, name


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
    """A real pytest collection over the Task #89 glob never lists the live selector."""
    target_paths = sorted(glob.glob(str(OKF_DIR / "test_phase15_e2a_task89_*.py")))
    assert (
        len(target_paths) == len(COLLECTED_TEST_FILENAMES) + 1
    ), f"expected the contracts module plus the proof: {target_paths}"
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
    function = _single_function_by_name(tree, "test_task89_authorized_live_acceptance")

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
    """AST/source proof: the live cells module pins real boundaries.

    The live cells module must reference every real production boundary
    fragment, the scoped-restore instrumentation mechanism, and the
    factory-connection lifecycle, and neither may contain
    ``NotImplementedError`` or any fake/replacement machinery. The core
    helper must also close the factory connection in its ``finally`` block.
    """
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
    _verify_live_cells_boundaries(source)
    _verify_helper_finally_closes_factory(helpers[0])


def test_support_module_source_pins_scoped_loader_and_real_ingestor() -> None:
    """AST/source proof: the extracted support module keeps its guards.

    The support module holds the file-based verification-module loader and
    the real Docling ingestor constructor. Its source must pin the explicit-
    file spec loading, the unique scoped module key, the BaseException
    restore path, the real reader/node-parser loader path, and the bounded
    class/type-only diagnostic, and must never contain environment/secret
    access, mock/fake machinery, sys.path mutation, session/DB construction,
    or unsafe dynamic imports or exec/eval.
    """
    source = (OKF_DIR / SUPPORT_FILENAME).read_text(encoding="utf-8")
    _verify_support_source(source)


def test_spec_loader_script_generates_deterministic_set_literal_frozensets() -> None:
    """The generated child script carries literal set-literal frozensets.

    Regression pin for the reviewed MEDIUM f-string code-generation
    fragility: the single braces in the generated ``frozenset({...})``
    blocks must be escaped so the emitted source is the intended set-literal
    (deterministic across Python versions) rather than a tuple-built
    frozenset that only parses by accident on newer grammars.
    """
    script = _spec_loader_script()
    assert (
        "BLOCKED_EXACT_MODULE_NAMES = frozenset({\n" in script
    ), "generated script must contain the intended set-literal block"
    assert (
        "BLOCKED_MODULE_FRAGMENTS = frozenset({\n" in script
    ), "generated script must contain the intended set-literal block"
    compile(script, "<task89-child>", "exec")


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
        ast.parse(fixture), "test_task89_authorized_live_acceptance"
    )
    with pytest.raises(AssertionError):
        _verify_live_acceptance_body(function)


def test_live_acceptance_verifier_rejects_missing_authorization() -> None:
    """Negative AST fixture: a skipped authorization check must fail."""
    fixture = _live_acceptance_fixture(omit_auth=True)
    function = _single_function_by_name(
        ast.parse(fixture), "test_task89_authorized_live_acceptance"
    )
    with pytest.raises(AssertionError):
        _verify_live_acceptance_body(function)


def test_live_acceptance_verifier_rejects_second_helper_call() -> None:
    """Negative AST fixture: a duplicated helper invocation must fail."""
    fixture = _live_acceptance_fixture(second_helper_call=True)
    function = _single_function_by_name(
        ast.parse(fixture), "test_task89_authorized_live_acceptance"
    )
    with pytest.raises(AssertionError):
        _verify_live_acceptance_body(function)


def test_live_acceptance_verifier_rejects_hardcoded_session_value() -> None:
    """Negative AST fixture: a hardcoded session argument value must fail."""
    fixture = _live_acceptance_fixture(hardcoded_session_value=True)
    function = _single_function_by_name(
        ast.parse(fixture), "test_task89_authorized_live_acceptance"
    )
    with pytest.raises(AssertionError):
        _verify_live_acceptance_body(function)


def _durable_sql_fixture(
    *,
    canonical_sql: str,
    vector_chunks_sql: str,
    vector_chunk_spans_sql: str,
    extract_vector_chunk_spans: bool = False,
    wrap_width: int = 40,
    extra_executes: list[str] | None = None,
) -> str:
    """Source of a _verify_observer_durable-shaped module with given SQL.

    Every SQL statement is emitted as Python implicit-concatenation adjacent
    string literals (word-wrapped), so the rendered source carries NO
    contiguous substring across literal boundaries -- the exact evasion the
    old inspect.getsource substring pins missed. When
    extract_vector_chunk_spans is True, the vector_chunk_spans SQL is bound
    to a module-level constant and referenced by name. extra_executes are
    raw statement lines appended verbatim after the standard counts (used to
    plant hidden direct/unresolved execute calls). The fixture is only ever
    parsed, never executed, and never opens a session.
    """

    def literals(sql: str, indent: str) -> list[str]:
        words = sql.split()
        chunks: list[str] = []
        current = words[0] if words else ""
        for word in words[1:]:
            if len(current) + 1 + len(word) <= wrap_width:
                current = f"{current} {word}"
            else:
                chunks.append(current)
                current = word
        if current:
            chunks.append(current)
        return [
            f'{indent}"{chunk} "' if index < len(chunks) - 1 else f'{indent}"{chunk}"'
            for index, chunk in enumerate(chunks)
        ]

    def execute_call(sql: str, indent: str) -> list[str]:
        literal_lines = literals(sql, indent + "    ")
        literal_lines[-1] = f"{literal_lines[-1]},"
        call = [f"{indent}cursor.execute("]
        call.extend(literal_lines)
        call.append(f"{indent}    (version_str,),")
        call.append(f"{indent})")
        return call

    lines: list[str] = []
    if extract_vector_chunk_spans:
        lines.append("_VECTOR_CHUNK_SPANS_SQL = (")
        lines.extend(literals(vector_chunk_spans_sql, "    "))
        lines.append(")")
        lines.append("")
    lines.append(f"def {OBSERVER_DURABLE_FUNCTION}(cursor, version_id, ingest_result):")
    lines.append("    version_str = str(version_id)")
    lines.extend(execute_call(canonical_sql, "    "))
    lines.extend(execute_call(vector_chunks_sql, "    "))
    if extract_vector_chunk_spans:
        lines.append("    cursor.execute(_VECTOR_CHUNK_SPANS_SQL, (version_str,))")
        lines.append("    cursor.fetchone()")
    else:
        lines.extend(execute_call(vector_chunk_spans_sql, "    "))
    for extra in extra_executes or ():
        lines.append(f"    {extra}")
    return "\n".join(lines) + "\n"


def test_observer_durable_sql_rejects_split_direct_variant() -> None:
    """The old UndefinedColumn bug, split across adjacent literals, is caught.

    The previous buggy query filtered version_id directly on
    vector_chunk_spans. Rendered as adjacent string literals, the contiguous
    substring "FROM vector_chunk_spans WHERE version_id" never appears in
    source, so the old inspect.getsource substring pin passed vacuously. The
    structural verifier must reject it regardless of the literal split.
    """
    source = _durable_sql_fixture(
        canonical_sql="SELECT COUNT(*) FROM canonical_spans WHERE version_id = %s",
        vector_chunks_sql="SELECT COUNT(*) FROM vector_chunks WHERE version_id = %s",
        vector_chunk_spans_sql=(
            "SELECT COUNT(*) FROM vector_chunk_spans WHERE version_id = %s"
        ),
    )
    assert "FROM vector_chunk_spans WHERE version_id" not in source
    with pytest.raises(AssertionError):
        _verify_observer_durable_sql(source)


def test_observer_durable_sql_accepts_renamed_aliases() -> None:
    """A semantically correct joined query with renamed aliases is accepted."""
    source = _durable_sql_fixture(
        canonical_sql="SELECT COUNT(*) FROM canonical_spans WHERE version_id = %s",
        vector_chunks_sql="SELECT COUNT(*) FROM vector_chunks WHERE version_id = %s",
        vector_chunk_spans_sql=(
            "SELECT COUNT(*) FROM vector_chunk_spans AS vs "
            "JOIN vector_chunks AS vk ON vs.chunk_id = vk.chunk_id "
            "WHERE vk.version_id = %s"
        ),
    )
    _verify_observer_durable_sql(source)


def test_observer_durable_sql_accepts_module_constant_reference() -> None:
    """A correct query extracted to a module-level constant is still accepted."""
    source = _durable_sql_fixture(
        canonical_sql="SELECT COUNT(*) FROM canonical_spans WHERE version_id = %s",
        vector_chunks_sql="SELECT COUNT(*) FROM vector_chunks WHERE version_id = %s",
        vector_chunk_spans_sql=(
            "SELECT COUNT(*) FROM vector_chunk_spans vcs "
            "JOIN vector_chunks vc ON vcs.chunk_id = vc.chunk_id "
            "WHERE vc.version_id = %s"
        ),
        extract_vector_chunk_spans=True,
    )
    assert "_VECTOR_CHUNK_SPANS_SQL" in source
    _verify_observer_durable_sql(source)


def test_observer_durable_sql_rejects_aliased_direct_variant() -> None:
    """An aliased but unjoined vector_chunk_spans version filter is rejected."""
    source = _durable_sql_fixture(
        canonical_sql="SELECT COUNT(*) FROM canonical_spans WHERE version_id = %s",
        vector_chunks_sql="SELECT COUNT(*) FROM vector_chunks WHERE version_id = %s",
        vector_chunk_spans_sql=(
            "SELECT COUNT(*) FROM vector_chunk_spans vcs WHERE vcs.version_id = %s"
        ),
    )
    with pytest.raises(AssertionError):
        _verify_observer_durable_sql(source)


def test_observer_durable_sql_fails_closed_on_unresolvable_sql() -> None:
    """A required query the verifier cannot resolve must fail closed."""
    source = (
        "def _verify_observer_durable(cursor, version_id, ingest_result):\n"
        "    version_str = str(version_id)\n"
        '    cursor.execute("SELECT COUNT(*) FROM canonical_spans WHERE version_id = %s", (version_str,))\n'
        "    cursor.fetchone()\n"
        '    cursor.execute("SELECT COUNT(*) FROM vector_chunks WHERE version_id = %s", (version_str,))\n'
        "    cursor.fetchone()\n"
        '    cursor.execute("SELECT COUNT(*) FROM vector_chunk_spans " "WHERE version_id = %s" + tail, (version_str,))\n'
        "    cursor.fetchone()\n"
    )
    with pytest.raises(AssertionError):
        _verify_observer_durable_sql(source)


def test_observer_durable_sql_rejects_hidden_unresolved_direct_filter() -> None:
    """A valid join plus a hidden unresolved direct filter is rejected.

    HIGH-1 regression: _execute_sql_statements silently dropped unresolved
    cursor.execute first arguments. A valid resolvable vector_chunk_spans
    join plus an extra buggy direct query written as a constant + constant
    BinOp (``"SELECT COUNT(*) FROM vector_chunk_spans WHERE " + "version_id
    = %s"``) was accepted because the unresolved BinOp was never counted.
    The verifier must fail closed: every direct cursor.execute must resolve.
    """
    source = _durable_sql_fixture(
        canonical_sql="SELECT COUNT(*) FROM canonical_spans WHERE version_id = %s",
        vector_chunks_sql="SELECT COUNT(*) FROM vector_chunks WHERE version_id = %s",
        vector_chunk_spans_sql=(
            "SELECT COUNT(*) FROM vector_chunk_spans vcs "
            "JOIN vector_chunks vc ON vcs.chunk_id = vc.chunk_id "
            "WHERE vc.version_id = %s"
        ),
        extra_executes=[
            'cursor.execute("SELECT COUNT(*) FROM vector_chunk_spans WHERE " '
            '+ "version_id = %s", (version_str,))'
        ],
    )
    with pytest.raises(AssertionError):
        _verify_observer_durable_sql(source)


@pytest.mark.parametrize(
    "extra_execute",
    [
        'cursor.execute(f"SELECT COUNT(*) FROM vector_chunk_spans WHERE version_id = %s", (version_str,))',
        "cursor.execute(_UNDEFINED_SQL, (version_str,))",
    ],
)
def test_observer_durable_sql_rejects_unresolvable_execute(
    extra_execute: str,
) -> None:
    """An unresolved name/f-string first argument must fail closed."""
    source = _durable_sql_fixture(
        canonical_sql="SELECT COUNT(*) FROM canonical_spans WHERE version_id = %s",
        vector_chunks_sql="SELECT COUNT(*) FROM vector_chunks WHERE version_id = %s",
        vector_chunk_spans_sql=(
            "SELECT COUNT(*) FROM vector_chunk_spans vcs "
            "JOIN vector_chunks vc ON vcs.chunk_id = vc.chunk_id "
            "WHERE vc.version_id = %s"
        ),
        extra_executes=[extra_execute],
    )
    with pytest.raises(AssertionError):
        _verify_observer_durable_sql(source)


def test_observer_durable_sql_rejects_crossed_column_join() -> None:
    """An ON clause equating chunk_id with span_id columns is rejected.

    HIGH-2 regression: the ON validation only checked that both chunk_id
    references and any ``=`` appear, so a crossed-column ON
    (``vcs.chunk_id = vc.span_id AND vc.chunk_id = vcs.span_id``) was
    accepted. The verifier must require an explicit equality whose two
    operands are exactly the two chunk_id references.
    """
    source = _durable_sql_fixture(
        canonical_sql="SELECT COUNT(*) FROM canonical_spans WHERE version_id = %s",
        vector_chunks_sql="SELECT COUNT(*) FROM vector_chunks WHERE version_id = %s",
        vector_chunk_spans_sql=(
            "SELECT COUNT(*) FROM vector_chunk_spans vcs "
            "JOIN vector_chunks vc "
            "ON vcs.chunk_id = vc.span_id AND vc.chunk_id = vcs.span_id "
            "WHERE vc.version_id = %s"
        ),
    )
    with pytest.raises(AssertionError):
        _verify_observer_durable_sql(source)


def test_observer_durable_sql_accepts_reversed_equality_join() -> None:
    """A joined query with the chunk_id equality reversed is accepted.

    Harmless operand order (``vc.chunk_id = vcs.chunk_id``) must remain
    accepted by the exact-equality ON validation.
    """
    source = _durable_sql_fixture(
        canonical_sql="SELECT COUNT(*) FROM canonical_spans WHERE version_id = %s",
        vector_chunks_sql="SELECT COUNT(*) FROM vector_chunks WHERE version_id = %s",
        vector_chunk_spans_sql=(
            "SELECT COUNT(*) FROM vector_chunk_spans vcs "
            "JOIN vector_chunks vc ON vc.chunk_id = vcs.chunk_id "
            "WHERE vc.version_id = %s"
        ),
    )
    _verify_observer_durable_sql(source)
