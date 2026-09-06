"""Static source/contract proof for the Phase 15 Task #88 C14 late-DML candidate.

This collected, database-free module pins, by filename identity, ``ast``
shape checks, exact SQL text, and production module source pins, the safety
contracts of the test-only ``PARTIAL(C14-candidate)`` slice: the live
selector is outside default pytest collection and authorization-first; the
helper has no environment access, direct ``psycopg.connect``, Docker, DDL/
trigger/advisory-lock SQL, retries, ``skip``/``xfail``, or fakes; both
parents come from the real registry writer path via
``_register_transition_pair`` with no parent-table seed; the only manual
DML is one parameterized bare ``evidence`` seed (desired V1 evidence ID,
real V2 version ID) committed on a separate fresh connection before any V1
materialization with no evidence-target row; the reconciler receives
``failure_audit_connection_factory=session.open_fresh_attested_connection``;
and the observer normalizes fetched UUID values to strings before comparing
to the seed identifiers. Production pins confirm migration 019 permits
``parent_reconciliation``, the evidence RETURNING guard order, V2 admission
during global preflight, bare-evidence inventory exclusion, repository
stage order before ``_upsert_evidence``, and the exact failure-audit
contract. A pure public-constructor check validates the V1-complete/V2-
empty two-parent shape with an exactly-two-raw-pair manifest. Fixtures are
parsed only, never executed; no database, no Docker, no authorized live
invocation.

Boundary (stated plainly): this proof and the two live modules it pins
produce PARTIAL(C14-candidate) evidence only. Their live rollback/audit/
observer observations form the live component of the approved formal
composed proof behind the Task #88 required cell ``true_late_dml_failure``;
standalone candidate execution does not itself close Task #88, #79, or
Phase 15.
"""

from __future__ import annotations

import ast
import fnmatch
import glob
import hashlib
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path
from types import MappingProxyType

from ._phase15_e2a_task88_cells import module_name_is_blocked

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
OKF_DIR = Path(__file__).parent

HELPER_FILENAME = "_phase15_e2a_late_dml_candidate_cells.py"
SELECTOR_FILENAME = "phase15_e2a_late_dml_candidate.py"
PROOF_FILENAME = "test_phase15_e2a_late_dml_candidate_proof.py"
SELECTED_TEST_NAME = "test_phase15_e2a_late_dml_candidate_live"
OBSERVATIONS_CLASS_NAME = "LateDmlCandidateObservations"
HELPER_IMPL_FUNCTION = "_run_late_dml_candidate_impl"
HELPER_BUILDER_FUNCTION = "_build_two_parent_desired_state"

_SANITIZED_ALLOWLIST = (
    "PATH", "HOME", "SystemRoot", "PATHEXT", "WINDIR", "TEMP", "TMP",
    "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "COMSPEC",
    "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
)
_REQUIRED_OBSERVATION_FIELDS = frozenset({
    "outcome_rolled_back_failure", "failure_maps_empty", "comparator_parity_none",
    "audit_outcome_written", "primary_closed", "both_registry_versions_exist",
    "bare_seed_durable", "v1_materialization_absent", "audit_count_one",
    "audit_fields_match", "audit_scope_manifest_matches", "audit_diagnostic_matches",
})
_FORBIDDEN_IMPORT_MODULES = frozenset({
    "os", "psycopg", "docker", "subprocess", "time", "socket", "signal",
    "select", "multiprocessing", "asyncio", "pytest", "mock",
})
_FORBIDDEN_IDENTIFIERS = frozenset({
    "sleep", "poll", "retry", "skip", "xfail", "environ", "getenv",
    "monkeypatch", "capfd", "conn_factory", "injected",
})
_FORBIDDEN_SQL_FRAGMENTS = (
    "CREATE TABLE", "ALTER TABLE", "CREATE TRIGGER", "CREATE FUNCTION",
    "CREATE VIEW", "DROP ", "pg_advisory", "pg_locks",
)


def _single_function_by_name(tree: ast.Module, function_name: str) -> ast.FunctionDef:
    """Return the single top-level function with the given name."""
    functions = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    ]
    assert len(functions) == 1, f"the {function_name!r} function must exist exactly once"
    return functions[0]


def _single_class_by_name(tree: ast.Module, class_name: str) -> ast.ClassDef:
    """Return the single top-level class with the given name."""
    classes = [
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    ]
    assert len(classes) == 1, f"the {class_name!r} class must exist exactly once"
    return classes[0]


def _helper_source() -> str:
    """Raw helper module source (the file must exist)."""
    return (OKF_DIR / HELPER_FILENAME).read_text(encoding="utf-8")


def _selector_source() -> str:
    """Raw selector module source (the file must exist)."""
    return (OKF_DIR / SELECTOR_FILENAME).read_text(encoding="utf-8")


def _production_source(relative: str) -> str:
    """Raw production module source relative to the repository root."""
    return (PROJECT_ROOT / "llamaindex_runtime" / relative).read_text(encoding="utf-8")


def _def_source(source: str, def_name: str) -> str:
    """Slice one function definition (not its callers/imports).

    The last column-leading ``def <name>(`` is the implementation; a
    Protocol declaration with the same name (as in ``E2aReconciler``) must
    not shadow it.
    """
    matches = [
        match
        for match in re.finditer(
            rf"^[ \t]*def {re.escape(def_name)}\(", source, re.MULTILINE
        )
    ]
    assert matches, f"def {def_name} not found"
    tail = source[matches[-1].start():]
    stop = re.search(r"\n(?=(?:def |class |@))", tail)
    return tail if stop is None else tail[: stop.start()]


def _imported_names_by_module(tree: ast.Module) -> dict[str, set[str]]:
    """Map each imported module path to the names imported from it.

    Relative ``from .x import ...`` statements are keyed with their leading
    dots restored (``node.module`` omits the level).
    """
    result: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                result.setdefault(alias.name, set()).add(
                    alias.asname or alias.name.split(".")[-1]
                )
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            key = "." * node.level + node.module
            result.setdefault(key, set()).update(
                alias.asname or alias.name for alias in node.names
            )
    return result


def _sanitized_env() -> dict[str, str]:
    """Child env dict: explicit per-key reads of non-sensitive allowlist keys."""
    return {
        key: value
        for key in _SANITIZED_ALLOWLIST
        if (value := os.getenv(key)) is not None
    }


# --- Filename / collection identity


def test_live_filenames_not_matched_by_default_pytest_patterns() -> None:
    """The helper and selector must escape default pytest collection."""
    for filename in (SELECTOR_FILENAME, HELPER_FILENAME):
        assert not fnmatch.fnmatch(filename, "test_*.py")
        assert not fnmatch.fnmatch(filename, "*_test.py")
    assert fnmatch.fnmatch(HELPER_FILENAME, "_*.py")
    assert fnmatch.fnmatch(PROOF_FILENAME, "test_*.py")
    for filename in (PROOF_FILENAME, HELPER_FILENAME, SELECTOR_FILENAME):
        assert not fnmatch.fnmatch(filename, "test_phase15_e2a_task88_*.py"), (
            "must never collide with the exact-counted task88 filename family"
        )


def test_live_module_names_not_blocked_by_family_guard() -> None:
    """The candidate slice must never collide with a prohibited naming family."""
    for module_name in (
        "tests.llamaindex_runtime.okf._phase15_e2a_late_dml_candidate_cells",
        "tests.llamaindex_runtime.okf.phase15_e2a_late_dml_candidate",
    ):
        assert not module_name_is_blocked(module_name), (
            f"collides with a prohibited family: {module_name}"
        )


def test_live_source_files_exist_and_parse_as_python() -> None:
    """Both live files must exist and parse; absence fails this proof (RED)."""
    helper_tree = ast.parse(_helper_source())
    selector_tree = ast.parse(_selector_source())
    assert _single_function_by_name(helper_tree, HELPER_IMPL_FUNCTION)
    assert _single_function_by_name(helper_tree, HELPER_BUILDER_FUNCTION)
    assert _single_function_by_name(selector_tree, SELECTED_TEST_NAME)


def test_pytest_collect_only_excludes_live_modules() -> None:
    """A real pytest collection over the Phase 15 glob never lists live modules."""
    target_paths = sorted(glob.glob(str(OKF_DIR / "test_phase15_e2a_*.py")))
    assert PROOF_FILENAME in {Path(path).name for path in target_paths}
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *target_paths],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        env=_sanitized_env(),
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, f"collection failed:\n{output}"
    assert HELPER_FILENAME not in output and SELECTOR_FILENAME not in output
    assert PROOF_FILENAME in output


# --- Authorization-first selector body


def test_selected_live_test_authorization_first_then_session() -> None:
    """The live test's first statement is the bare auth call, before any session."""
    function = _single_function_by_name(ast.parse(_selector_source()), SELECTED_TEST_NAME)
    assert not function.decorator_list, "the selected live test must not be decorated"
    statements = list(function.body)
    if (
        statements
        and isinstance(statements[0], ast.Expr)
        and isinstance(statements[0].value, ast.Constant)
        and isinstance(statements[0].value.value, str)
    ):
        statements = statements[1:]
    assert statements, "the selected live test body must not be empty"
    first = statements[0]
    assert isinstance(first, ast.Expr) and isinstance(first.value, ast.Call), (
        "the first statement must be the bare _require_authorization() call"
    )
    call = first.value
    assert isinstance(call.func, ast.Name), (
        "the first call must be the direct _require_authorization()"
    )
    assert call.func.id == "_require_authorization"
    assert not call.args and not call.keywords
    session_calls = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "DisposableE2aSession"
    ]
    assert session_calls, "the selected live test must construct a session"
    for session_call in session_calls:
        assert session_call.lineno > call.lineno, (
            "no session construction may precede the authorization check"
        )
    assert "open_fresh_attested_connection" not in {
        node.id for node in ast.walk(function) if isinstance(node, ast.Name)
    }


def test_selector_delegates_to_helper_once_and_raises_bounded() -> None:
    """The selector calls the helper once and raises only the bounded reason."""
    function = _single_function_by_name(ast.parse(_selector_source()), SELECTED_TEST_NAME)
    impl_calls = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == HELPER_IMPL_FUNCTION
    ]
    assert len(impl_calls) == 1, "the selector must invoke the helper exactly once"
    assert not impl_calls[0].keywords, "the helper must be invoked positionally"
    assert len(impl_calls[0].args) == 1, "the helper must receive only the session"
    raises = [node for node in ast.walk(function) if isinstance(node, ast.Raise)]
    assert len(raises) == 1, "the selector must raise exactly once"
    exc = raises[0].exc
    assert isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name)
    assert exc.func.id == "RuntimeError" and len(exc.args) == 1
    message = exc.args[0]
    assert isinstance(message, ast.JoinedStr), (
        "the RuntimeError message must be an f-string"
    )
    parts = message.values
    assert isinstance(parts[0], ast.Constant) and isinstance(parts[0].value, str)
    reason = parts[-1]
    assert isinstance(reason, ast.FormattedValue)
    assert isinstance(reason.value, ast.Attribute) and reason.value.attr == "error_reason"
    assert isinstance(reason.value.value, ast.Name)
    assert reason.value.value.id == "observations"
    assert all(isinstance(part, ast.Constant) for part in parts[1:-1]), (
        "only the bounded error_reason may be interpolated"
    )


def test_selector_asserts_every_observation_field() -> None:
    """Every required observation field must be asserted by the selector."""
    cls = _single_class_by_name(ast.parse(_helper_source()), OBSERVATIONS_CLASS_NAME)
    fields = {
        node.target.id
        for node in cls.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    assert _REQUIRED_OBSERVATION_FIELDS <= fields
    selector_source = _selector_source()
    for field in sorted(_REQUIRED_OBSERVATION_FIELDS):
        assert f"assert observations.{field}" in selector_source, (
            f"the selector must assert observations.{field}"
        )


# --- Helper arrangement


def test_observations_class_is_redacted_namedtuple() -> None:
    """The observations class must be a NamedTuple with a redacted repr."""
    source = _helper_source()
    cls = _single_class_by_name(ast.parse(source), OBSERVATIONS_CLASS_NAME)
    assert any(isinstance(base, ast.Name) and base.id == "NamedTuple" for base in cls.bases)
    fields = {
        node.target.id
        for node in cls.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    assert {"success", "error_reason"} <= fields
    assert _REQUIRED_OBSERVATION_FIELDS <= fields
    reprs = [
        node for node in cls.body
        if isinstance(node, ast.FunctionDef) and node.name == "__repr__"
    ]
    assert len(reprs) == 1, "the observations class must define __repr__"
    repr_source = ast.get_source_segment(source, reprs[0])
    assert repr_source is not None and "<redacted>" in repr_source
    assert not any(
        token in repr_source.lower()
        for token in ("password", "token", "uri", "cursor", "connection", "session")
    )


def test_helper_imports_only_the_shared_cell_helpers() -> None:
    """The helper reuses the shared live/transition cell helpers unchanged."""
    imported = _imported_names_by_module(ast.parse(_helper_source()))
    live_cells = imported.get("._phase15_e2a_task88_live_cells", set())
    transition_cells = imported.get("._phase15_e2a_task88_transition_cells", set())
    assert {
        "_SOURCE_RELATIVE_PATH", "_build_foundation_desired_state", "_close_quietly",
        "_error_reason", "_file_sha256", "_open_observer_connection",
        "_open_reconciler_primary_connection", "_open_writer_connection",
    } <= live_cells
    assert {"_open_seed_connection", "_register_transition_pair"} <= transition_cells
    source = _helper_source()
    assert "PostgresRegistryWriter" not in source
    assert "register_document" not in source


def _impl_source() -> str:
    """The helper implementation body (the file must exist)."""
    source = _helper_source()
    segment = ast.get_source_segment(
        source, _single_function_by_name(ast.parse(source), HELPER_IMPL_FUNCTION)
    )
    assert segment is not None
    return segment


def test_helper_registers_pair_without_document_versions_seed() -> None:
    """Both parents come from _register_transition_pair; no direct seed."""
    source = _helper_source()
    builder_segment = ast.get_source_segment(
        source, _single_function_by_name(ast.parse(source), HELPER_BUILDER_FUNCTION)
    )
    assert builder_segment is not None
    impl = _impl_source()
    assert "INSERT INTO document_versions" not in source
    assert impl.count("_register_transition_pair(") == 1
    assert "_build_two_parent_desired_state(" in impl
    assert "_build_foundation_desired_state(" in builder_segment
    assert "first_path, first_registration, second_path, second_registration" in impl


def test_helper_seed_is_parameterized_bare_evidence_only() -> None:
    """The only manual DML is one parameterized bare evidence seed."""
    source = _helper_source()
    assert source.count("INSERT INTO evidence") == 1
    assert "INSERT INTO evidence (evidence_id, version_id) VALUES (%s, %s)" in source
    assert "INSERT INTO okf_manual_evidence_targets" not in source
    assert "seed_conn = _open_seed_connection(session)" in source
    assert "seed_cursor = seed_conn.cursor()" in source
    assert "seed_conn.commit()" in source
    impl = _impl_source()
    assert (
        impl.index("seed_conn.commit()") < impl.index("reconciler = E2aReconciler(")
    ), "the bare evidence seed must be committed before any reconciliation"


def test_helper_normalizes_fetched_evidence_rows_to_strings() -> None:
    """The observer must normalize fetched UUID values before comparing.

    A plain psycopg cursor returns UUID objects, so direct tuple equality
    against the string identifiers is always False even when the seed is
    durable. Every fetched value must pass through str(...).
    """
    impl = _impl_source()
    assert "SELECT evidence_id, version_id FROM evidence ORDER BY evidence_id" in impl
    assert "evidence_rows == [" not in impl, (
        "the raw fetched rows must never be compared directly to strings"
    )
    assert "str(row[0])" in impl and "str(row[1])" in impl
    assert "normalized_rows" in impl
    assert "(evidence.evidence_id, v2_version_id)" in impl


def test_helper_injects_fresh_audit_connection_factory() -> None:
    """The reconciler must receive the fresh-attested audit connection factory."""
    calls = [
        node
        for node in ast.walk(ast.parse(_helper_source()))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "E2aReconciler"
    ]
    assert len(calls) == 1, "the helper must construct exactly one E2aReconciler"
    assert not calls[0].args, "the reconciler must take no positional arguments"
    factory = [
        keyword
        for keyword in calls[0].keywords
        if keyword.arg == "failure_audit_connection_factory"
    ]
    assert len(factory) == 1 and len(calls[0].keywords) == 1
    value = factory[0].value
    assert isinstance(value, ast.Attribute) and value.attr == "open_fresh_attested_connection"
    assert isinstance(value.value, ast.Name) and value.value.id == "session"
    assert _helper_source().count("open_fresh_attested_connection") == 1, (
        "the audit factory must be the only direct fresh-connection reference"
    )


def test_helper_reconciles_once_and_asserts_result_contract() -> None:
    """The helper reconciles the two-parent state once and asserts the result."""
    impl = _impl_source()
    for fragment in (
        "reconciler.reconcile(primary_conn, two_parent_desired)",
        'result.outcome == "rolled_back_failure"',
        "not result.primary_dml_by_table and not result.denylist_dml_counts",
        "result.comparator_parity is None",
        'result.post_rollback_failure_audit_outcome == "written"',
        "primary_conn.closed",
        "primary_conn = _open_reconciler_primary_connection(session)",
    ):
        assert fragment in impl


def test_helper_forbidden_mechanics_absent() -> None:
    """The helper must contain no environment, docker, DDL, or retry mechanics."""
    source = _helper_source()
    imported = _imported_names_by_module(ast.parse(source))
    for module in imported:
        assert not any(
            banned in module.split(".") for banned in _FORBIDDEN_IMPORT_MODULES
        ), f"forbidden import module used: {module!r}"
    referenced = {
        node.id for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Name)
    }
    assert not (_FORBIDDEN_IDENTIFIERS & referenced), (
        "forbidden identifier used in the helper"
    )
    assert not any(fragment in source for fragment in _FORBIDDEN_SQL_FRAGMENTS)
    assert not any(
        token in source for token in ("DATABASE_URL", "PGPASSWORD", "postgres://")
    )


def test_helper_cleans_up_in_finally() -> None:
    """The helper must close every resource and unlink temp files in finally."""
    impl = _impl_source()
    assert "finally:" in impl
    assert impl.count("_close_quietly(") >= 6
    assert "first_path, second_path" in impl
    assert "path.unlink()" in impl
    assert "except Exception:" in impl


def test_docstrings_declare_partial_boundary() -> None:
    """Both live modules must state the PARTIAL boundary honestly.

    The candidate's live rollback/audit/observer observations are the live
    component of the approved formal composed proof; the stale 'cannot
    unblock' / 'deliberately BLOCKED' claims must be gone, and standalone
    candidate execution must still be stated as not itself closing Task
    #88, #79, or Phase 15.
    """
    for filename in (HELPER_FILENAME, SELECTOR_FILENAME):
        doc = ast.get_docstring(
            ast.parse((OKF_DIR / filename).read_text(encoding="utf-8")), clean=False
        ) or ""
        assert "PARTIAL(C14-candidate)" in doc
        assert "true_late_dml_failure" in doc
        assert "does not itself close" in doc
        assert "Task #88" in doc
        assert "Phase 15" in doc
        assert "cannot unblock" not in doc, (
            "the stale 'cannot unblock' claim must be removed"
        )
        assert "deliberately BLOCKED" not in doc, (
            "the stale 'deliberately BLOCKED' claim must be removed"
        )
    selector_doc = ast.get_docstring(ast.parse(_selector_source()), clean=False) or ""
    assert "Task #88" in selector_doc


# --- Production contract pins


def test_production_evidence_upsert_guard_contracts() -> None:
    """The evidence upsert must carry the WHERE guard, RETURNING 1, and _issue order."""
    source = _production_source("okf/e2a_materialization_dml.py")
    assert "INSERT INTO evidence (evidence_id, version_id) VALUES (%s, %s) " in source
    assert (
        "ON CONFLICT (evidence_id) DO UPDATE SET version_id = EXCLUDED.version_id WHERE "
        in source
    )
    assert "evidence.version_id = EXCLUDED.version_id " in source
    assert "RETURNING 1" in source
    issue = _def_source(source, "_issue")
    assert (
        issue.index("cursor.execute(")
        < issue.index("recorder.record_issued(")
        < issue.index("cursor.fetchone()")
    )
    assert "RETURNING" in issue
    assert "_GLOBAL_PRIMARY_KEY_TABLES" in issue


def test_production_migration_019_permits_parent_reconciliation() -> None:
    """The final migration must permit the parent_reconciliation audit phase."""
    source = _production_source(
        "registry/migrations/019_e2a_materialization_contract.sql"
    )
    assert "parent_reconciliation" in source
    assert any(
        "'parent_reconciliation'::text" in line
        for line in source.splitlines()
        if "chk_okf_rebuild_failure_audit_phase" in line and "ARRAY[" in line
    )


def test_production_global_preflight_admits_desired_parent_versions() -> None:
    """Global preflight accepts rows whose version is any admitted parent."""
    source = _production_source("okf/e2a_reconciler.py")
    preflight = _def_source(source, "_preflight_global_primary_keys")
    assert "_check_global_rows(" in preflight
    assert "_check_global_evidence_links(cursor, desired, version_ids, collisions)" in preflight
    assert "if row_version not in version_ids:" in _def_source(source, "_check_global_rows")
    assert "elif row_version not in version_ids:" in _def_source(
        source, "_check_global_evidence_links"
    )


def test_production_evidence_inventory_excludes_bare_evidence() -> None:
    """Evidence inventory joins targets, so a bare seed is not scoped inventory."""
    source = _production_source("okf/_e2a_materialization_inventory.py")
    assert "INNER JOIN okf_manual_evidence_targets" in source
    assert "target.version_id = evidence.version_id" in source


def test_production_repository_orders_evidence_upsert_after_prior_dml() -> None:
    """All earlier production upsert stages precede _upsert_evidence."""
    reconcile = _def_source(
        _production_source("okf/e2a_materialization_repository.py"), "reconcile"
    )
    assert "_validate_desired(desired)" in reconcile
    assert "_existing_scope(cursor, desired)" in reconcile
    stages = (
        "_upsert_canonical_spans(", "_upsert_tree(", "_upsert_chunks(",
        "_delete_stale_evidence(", "_upsert_manual_facts(", "_upsert_evidence(",
        "_upsert_sync_state(",
    )
    positions = [reconcile.index(stage) for stage in stages]
    assert positions == sorted(positions), (
        "the production repository stage order must be preserved"
    )


def test_production_failure_audit_contracts() -> None:
    """The failure audit must record the exact candidate diagnostics."""
    source = _production_source("okf/e2a_reconciler.py")
    reconcile = _def_source(source, "reconcile")
    for fragment in (
        '"rolled_back_failure"', "primary_dml_by_table={}", "denylist_dml_counts={}",
        "comparator_parity=None", "post_rollback_failure_audit_outcome=audit_result.outcome",
    ):
        assert fragment in reconcile
    audit = _def_source(source, "_write_failure_audit")
    for fragment in (
        '"parent_reconciliation"', '"manifest_sha256"', '"parent_count"', '"version_ids"',
        "max(1, len(desired.parents))", '"error_type": type(failure).__name__[:64]',
        "audit_connection.commit()",
    ):
        assert fragment in audit


# --- Two-parent desired-state contract construction (never a fake acceptance test)


def test_two_parent_desired_shape_validates_with_exact_raw_pairs() -> None:
    """Public constructors accept the V1-complete/V2-empty two-parent shape.

    Pure contract test: synthetic identifiers, no database. V2 is an
    admitted parent with no projections and no sync row; V1 keeps its full
    legal graph; the manifest carries exactly two raw-pair artifacts.
    """
    from llamaindex_runtime.okf.e2a_contracts import (
        E2aDesiredState,
        E2aEvidenceObject,
        E2aEvidenceReference,
        E2aManualFact,
        E2aOwnershipFact,
        E2aParent,
        E2aSpan,
        canonical_json,
        canonical_json_sha256,
        deterministic_id,
    )

    rel = "e2a-foundation/source.txt"
    doc = str(uuid.uuid4())
    v1, v2 = str(uuid.uuid4()), str(uuid.uuid4())
    h1 = hashlib.sha256(b"late-dml-candidate-v1").hexdigest()
    h2 = hashlib.sha256(b"late-dml-candidate-v2").hexdigest()
    natural_key = canonical_json({"entity_type": "concept", "title": "Live Foundation"})
    entity = E2aManualFact(
        deterministic_id("entity", natural_key), "entity", rel, h1, {}, natural_key
    )
    ownership = E2aOwnershipFact.create(
        relative_path=rel, fact_kind="entity", fact_id=entity.fact_id,
        source_digest=h1, document_id=doc, version_id=v1,
    )
    evidence = E2aEvidenceObject.create(
        version_id=v1, entity_id=entity.fact_id, relation_id=None
    )
    parent_v1 = E2aParent(doc, v1, rel, h1)
    parent_v2 = E2aParent(doc, v2, rel, h2)
    span_id, node_id, chunk_id = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    span_text = "Live E2A foundation source fixture."
    span = E2aSpan(doc, v1, span_id, 0, span_text)
    node = {
        "node_id": node_id, "version_id": v1, "parent_node_id": None,
        "node_type": "section", "level_no": 1, "title": "Live Foundation Section",
        "heading_path": "/e2a-foundation", "page_start": 1, "page_end": 1,
        "summary_text": "Foundation tree node summary.",
    }
    node_link = {"node_id": node_id, "span_id": span_id, "ordinal_no": 0}
    chunk = {
        "chunk_id": chunk_id, "version_id": v1, "chunk_type": "text",
        "chunk_order": 0, "token_count": len(span_text.split()),
        "text_preview": span_text, "page_no": 1, "heading_path": "/e2a-foundation",
        "node_id": node_id, "embedding": tuple(float(i) for i in range(16)),
    }
    chunk_link = {"chunk_id": chunk_id, "span_id": span_id, "ordinal_no": 0}
    sync_row = {
        "okf_file_path": rel, "doc_id": doc, "version_id": v1,
        "source_checksum": h1, "canonical_hash": h1,
        "status": "materialized", "materialization_owner": "e2a",
    }
    link = E2aEvidenceReference(
        doc, v1, span_id, entity.fact_id, None, evidence.evidence_id,
        ownership.ownership_id, ownership.scope_version_id,
    )

    def build(manifest: dict[str, object], parents: tuple[object, ...]) -> Any:
        return E2aDesiredState(
            manifest, canonical_json_sha256(manifest), parents,
            (span,), (chunk,), (chunk_link,), (node,), (node_link,), (entity,), (),
            (evidence,), (link,), (ownership,), (sync_row,),
            MappingProxyType({}), MappingProxyType({"authority": "okf"}),
        )

    def manifest_for(parents: tuple[object, ...]) -> dict[str, object]:
        artifacts = [
            {
                "kind": "raw_pair", "path": p.relative_path,
                "identity": f"{p.document_id}:{p.version_id}",
                "canonical_hash": p.canonical_hash,
            }
            for p in parents
        ]
        artifacts.append(
            {"kind": "entity", "path": rel, "identity": entity.fact_id, "source_digest": h1}
        )
        return {"artifacts": artifacts}

    state = build(manifest_for((parent_v1, parent_v2)), (parent_v1, parent_v2))
    assert len(state.parents) == 2
    raw_pairs = [a for a in state.corpus_manifest["artifacts"] if a["kind"] == "raw_pair"]
    assert len(raw_pairs) == 2, "the manifest must carry exactly two raw pairs"
    assert {(a["path"], a["identity"], a["canonical_hash"]) for a in raw_pairs} == {
        (rel, f"{doc}:{v1}", h1), (rel, f"{doc}:{v2}", h2),
    }
    assert state.canonical_spans and state.vector_chunks and state.tree_nodes
    assert all(str(s.version_id) == v1 for s in state.canonical_spans)
    assert all(r["version_id"] == v1 for r in state.vector_chunks)
    assert all(r["version_id"] == v1 for r in state.tree_nodes)
    assert all(str(e.version_id) == v1 for e in state.evidence_objects)
    assert len(state.sync_state_rows) == 1
    assert state.sync_state_rows[0]["version_id"] == v1

    # Negative control: one raw pair cannot satisfy two admitted parents.
    try:
        build(manifest_for((parent_v1,)), (parent_v1, parent_v2))
    except ValueError:
        pass
    else:
        raise AssertionError(
            "one raw-pair artifact for two parents must be rejected by the contract"
        )

    # Positive control: one parent with its single raw pair still validates.
    single = build(manifest_for((parent_v1,)), (parent_v1,))
    assert len(single.parents) == 1
