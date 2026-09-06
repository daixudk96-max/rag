"""Non-live order contract for the E2a v1-to-v2 ownership transition.

Task #88 Stage 2R, Plan A. This module never touches Docker, PostgreSQL, or
the live selector; it inspects production source through the AST only (with
exact source pins where the Stage 2 contracts module already uses that
style). It pins the repository reconcile ordering and the migration 019
foreign-key contract that make the v1-to-v2 ownership transition safe.

Why the ordering is load-bearing
--------------------------------
``E2aOwnershipFact.create`` derives a version-INDEPENDENT ownership identity
(``natural_key`` contains no version component), so materializing version 2
of an already-materialized document UPDATEs the SAME
``okf_manual_fact_ownership`` row, including the mutable ``scope_version_id``
column. Migration 019 installs

    fk_evidence_links_ownership_scope
      FOREIGN KEY (ownership_id, ownership_scope_version_id)
      REFERENCES okf_manual_fact_ownership(ownership_id, scope_version_id)
      ON DELETE RESTRICT

with no ``ON UPDATE`` clause, so PostgreSQL enforces NO ACTION immediately
and non-deferrably at the statement level: the ownership UPDATE fails while
any version-1 ``evidence_links`` row still references the old ownership
scope. Version-1 links are stale in version 2 (their ``evidence_link_id``
embeds the version and span), so ``_delete_stale_evidence`` must run BEFORE
the ownership upsert to remove the referencing rows first. The migration 019
preflight final-catalog contract additionally requires ``confdeltype = 'r'``
(RESTRICT), ``confupdtype = 'a'`` (NO ACTION), and ``NOT condeferrable`` /
``NOT condeferred`` for every evidence_links FK, which is what makes the
ordering load-bearing. No DDL change is proposed; only the call order inside
``reconcile`` is under test.

RED contract: against the pre-fix source, ``_delete_stale_evidence`` sits
AFTER ``_upsert_manual_facts`` and ``_upsert_evidence``, so the ordering
assertions below fail until the production fix moves stale evidence deletion
to directly after the stale link cleanup and before the manual-fact upsert.
"""

from __future__ import annotations

import ast
from pathlib import Path

_OKF = Path(__file__).parents[3] / "llamaindex_runtime" / "okf"
_MIGRATIONS = (
    Path(__file__).parents[3] / "llamaindex_runtime" / "registry" / "migrations"
)


def _read(relative: str) -> str:
    path = _OKF / relative
    assert path.is_file(), f"missing production source: {path}"
    return path.read_text(encoding="utf-8")


def _read_migration(name: str) -> str:
    path = _MIGRATIONS / name
    assert path.is_file(), f"missing migration: {path}"
    return path.read_text(encoding="utf-8")


def _repository_function(function_name: str) -> ast.FunctionDef:
    tree = ast.parse(_read("e2a_materialization_repository.py"))
    repository = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "E2aMaterializationRepository"
    )
    return next(
        node
        for node in repository.body
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    )


def _statement_call_name(statement: ast.AST) -> str | None:
    """Return the outermost module-level call name a statement performs."""
    if isinstance(statement, ast.Expr):
        value = statement.value
    elif isinstance(statement, ast.Assign) and len(statement.targets) == 1:
        value = statement.value
    elif isinstance(statement, ast.AnnAssign):
        value = statement.value
    else:
        return None
    if isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
        return value.func.id
    return None


def _reconcile_call_steps() -> list[str]:
    """Ordered names of the top-level calls inside ``reconcile`` (AST walk).

    Extracted from the method AST, so quoting, comment drift, and line
    movement cannot break the pin. Only calls that ARE a top-level statement
    (or its assigned value) are collected; control-flow bodies, nested
    helpers, and attribute calls such as ``recorder.*`` are ignored.
    """
    reconcile = _repository_function("reconcile")
    return [
        name
        for statement in reconcile.body
        if (name := _statement_call_name(statement)) is not None
    ]


# ---------------------------------------------------------------------------
# Reconcile ordering (the RED contract against the pre-fix source)
# ---------------------------------------------------------------------------


def test_reconcile_orders_stale_evidence_before_manual_fact_upsert() -> None:
    """Stale evidence links are deleted before the ownership row upsert.

    This is the load-bearing ordering: the ownership upsert mutates
    ``scope_version_id`` on the version-independent ``ownership_id`` row, and
    ``fk_evidence_links_ownership_scope`` is enforced immediately (NO ACTION,
    non-deferrable), so any v1 evidence link still referencing the old scope
    aborts the UPDATE with a ForeignKeyViolation.
    """
    steps = _reconcile_call_steps()
    stale_evidence = steps.index("_delete_stale_evidence")
    manual_facts = steps.index("_upsert_manual_facts")
    evidence = steps.index("_upsert_evidence")
    assert stale_evidence < manual_facts, (
        "stale evidence links must be deleted before _upsert_manual_facts: "
        "the v1-to-v2 scope_version_id UPDATE on the shared ownership_id row "
        "is checked immediately by the non-deferrable ownership-scope FK"
    )
    assert (
        stale_evidence < evidence
    ), "stale evidence links must also be deleted before _upsert_evidence"


def test_reconcile_orders_stale_evidence_after_stale_link_cleanup() -> None:
    """Stale evidence deletion runs after both stale link cleanup passes."""
    steps = _reconcile_call_steps()
    last_link_cleanup = max(
        index for index, name in enumerate(steps) if name == "_delete_stale_links"
    )
    assert (
        steps.count("_delete_stale_links") == 2
    ), "expected exactly the tree_node_spans and vector_chunk_spans cleanup"
    assert steps.index("_delete_stale_evidence") > last_link_cleanup


def test_reconcile_keeps_stale_ownership_after_evidence_processing() -> None:
    """Ownership retirement stays after evidence upsert and stale cleanup."""
    steps = _reconcile_call_steps()
    stale_ownership = steps.index("_delete_stale_ownership")
    assert stale_ownership > steps.index("_upsert_evidence")
    assert stale_ownership > steps.index("_delete_stale_evidence")


def test_reconcile_keeps_stale_spans_last() -> None:
    """Stale canonical span deletion remains the final reconcile step."""
    steps = _reconcile_call_steps()
    assert steps[-1] == "_delete_stale_spans"
    assert steps.index("_delete_stale_spans") > steps.index("_delete_stale_ownership")


def test_reconcile_stale_evidence_call_shape_preserved() -> None:
    """The moved call keeps its exact five-argument shape (no re-parametrization)."""
    reconcile = _repository_function("reconcile")
    calls = [
        node
        for node in ast.walk(reconcile)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_delete_stale_evidence"
    ]
    assert len(calls) == 1, "exactly one stale evidence call in reconcile"
    call = calls[0]
    assert not call.keywords, "stale evidence call must stay positional"
    names = [argument.id for argument in call.args if isinstance(argument, ast.Name)]
    assert names == ["cursor", "desired", "existing", "recorder", "stale_counts"]


# ---------------------------------------------------------------------------
# Identity and upsert contracts that make the ordering meaningful
# ---------------------------------------------------------------------------


def test_ownership_identity_is_version_independent() -> None:
    """The ownership natural key contains no version component."""
    source = _read("e2a_contracts.py")
    assert 'natural_key = f"{relative_path}:{fact_kind}:{fact_id}"' in source
    assert 'deterministic_id("ownership", natural_key)' in source
    assert "expected_scope = version_id or E2A_GLOBAL_SCOPE_VERSION_ID" in source
    assert "ownership identity does not match natural key" in source


def test_evidence_link_identity_is_version_dependent() -> None:
    """Evidence link ids embed version and span, so v1 links go stale in v2."""
    source = _read("e2a_contracts.py")
    assert "_manual_evidence_link_identity(" in source
    assert "version_id=self.version_id" in source
    assert "span_id=self.span_id" in source
    assert "ownership_scope_version_id=self.ownership_scope_version_id" in source


def test_ownership_upsert_mutates_scope_version_id() -> None:
    """The v1-to-v2 upsert UPDATEs scope_version_id on the shared row."""
    source = _read("e2a_materialization_upserts.py")
    assert '"scope_version_id": owner.scope_version_id,' in source
    assert '("ownership_id",),' in source
    assert 'tuple(key for key in row if key != "ownership_id")' in source
    assert "okf_manual_fact_ownership" in source


def test_stale_evidence_module_contract_pins_link_deletion_by_id() -> None:
    """Stale cleanup derives link ids from existing scope and desired state."""
    tree = ast.parse(_read("_e2a_materialization_stale_evidence.py"))
    fn = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "delete_stale_evidence"
    )
    stale_calls = [
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "stale_ids"
    ]
    first_args = [
        node.args[0]
        for node in stale_calls
        if isinstance(node.args[0], ast.Subscript)
        and isinstance(node.args[0].value, ast.Name)
        and node.args[0].value.id == "existing"
        and isinstance(node.args[0].slice, ast.Constant)
        and isinstance(node.args[0].slice.value, str)
    ]
    assert sorted(arg.slice.value for arg in first_args) == [
        "evidence",
        "evidence_links",
    ]
    fields = {
        node.args[2].value
        for node in stale_calls
        if len(node.args) >= 3
        and isinstance(node.args[2], ast.Constant)
        and isinstance(node.args[2].value, str)
    }
    assert fields == {"evidence_id", "evidence_link_id"}


def test_stale_evidence_module_uses_manual_okf_link_delete_template() -> None:
    """Stale manual links are deleted by id with the manual_okf filter."""
    tree = ast.parse(_read("_e2a_materialization_stale_evidence.py"))
    helper = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_delete_links_by_id"
    )
    execute_calls = [
        node
        for node in ast.walk(helper)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "execute_template"
    ]
    assert len(execute_calls) == 1
    call = execute_calls[0]
    template = call.args[1]
    assert isinstance(template, ast.Attribute)
    assert template.attr == "DELETE_EVIDENCE_LINKS_BY_IDS"
    parameters = call.args[2]
    assert isinstance(parameters, ast.Tuple) and len(parameters.elts) == 2
    filter_value = parameters.elts[1]
    assert isinstance(filter_value, ast.Constant)
    assert filter_value.value == "manual_okf"


# ---------------------------------------------------------------------------
# Migration 019 foreign-key contract (no DDL change proposed)
# ---------------------------------------------------------------------------


def test_migration_019_preserves_ownership_scope_fk_restrict() -> None:
    """The named ownership-scope FK keeps its ON DELETE RESTRICT form."""
    source = _read_migration("019_e2a_materialization_contract.sql")
    assert (
        "ADD CONSTRAINT fk_evidence_links_ownership_scope "
        "FOREIGN KEY (ownership_id, ownership_scope_version_id) "
        "REFERENCES %s(ownership_id, scope_version_id) ON DELETE RESTRICT"
    ) in source
    assert (
        "ADD CONSTRAINT fk_evidence_links_ownership "
        "FOREIGN KEY (ownership_id) REFERENCES %s(ownership_id) ON DELETE RESTRICT"
    ) in source


def test_migration_019_evidence_fks_nondeferrable_no_action_update() -> None:
    """Final inventory demands RESTRICT delete, NO ACTION update, non-deferrable."""
    source = _read_migration("019_e2a_materialization_contract.sql")
    assert "OR constraint_row.confdeltype <> 'r'" in source
    assert "OR constraint_row.confupdtype <> 'a'" in source
    assert "OR constraint_row.condeferrable" in source
    assert "OR constraint_row.condeferred" in source
    assert (
        "('fk_evidence_links_ownership_scope', evidence_links_oid, ownership_oid)"
        in source
    )


def test_migration_019_legacy_fk_shape_requires_no_action_update() -> None:
    """The pre-replacement FK shape also requires NO ACTION update semantics."""
    source = _read_migration("019_e2a_materialization_contract.sql")
    assert "OR constraint_row.confupdtype <> 'a'" in source
    assert "OR constraint_row.condeferrable" in source
    assert "OR constraint_row.condeferred" in source
    assert "OR NOT (constraint_row.confdeltype IN ('c', 'a'))" in source
