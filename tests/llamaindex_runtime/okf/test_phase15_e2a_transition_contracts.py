"""Non-live contract pins for the Task #88 Stage 2 transition cells.

This module never touches Docker, PostgreSQL, or the live selector; it reads
production source text and exercises a fake-connection double only. It pins:

- C2 source-derived fixed projection: the corpus manifest hash appears in no
  sync-state field and in no DML template, the repository outcome formula is
  ``changed`` iff any primary count is positive, and the contract graph
  validates only the ``artifacts`` manifest key (AST-verified, quote-agnostic,
  catching subscript/attribute/dynamic-key drift), so a contract-valid
  manifest-only mutation must project exactly ``outcome == "no_op"`` with
  ``comparator_parity is True`` and zero primary DML.
- C3/C4: the full global canonical_spans collision template anchored to the
  production f-string AST (prefix, id field/value, incompatible-scope phrase)
  and rendered by the helper from one single-source template, the
  canonical_spans check order, the default reconciler's null audit factory,
  and the unwrapped-exception object identity contract through a cursor
  double (identity and exact message are non-live assertions, never
  fabricated live observations).
- C5: the migration 018 audit columns, append-only trigger names, the
  migration 019 ``parent_reconciliation`` phase rewrite, the entities seed
  columns, the exact durable ``scope_manifest`` body (manifest_sha256,
  parent_count, version_ids), and the incompatible-material preflight path.

The RED phase for this tranche is carried by the sibling proof module
(``test_phase15_e2a_transition_proof.py``), which fails until the Stage 2
live modules exist; this module pins production invariants that must hold
regardless of the implementation delta.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from llamaindex_runtime.okf.e2a_contracts import (
    E2aDesiredState,
    E2aParent,
    canonical_json,
    canonical_json_sha256,
)
from llamaindex_runtime.okf.e2a_reconciler import E2aReconciler

from ._phase15_e2a_task88_live_cells import (
    _build_foundation_desired_state,
    _create_source_fixture,
)

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


def _manifest_reads(tree: ast.Module) -> tuple[set[str], list[str]]:
    """Return (literal keys, violations) for every read of the corpus manifest.

    Quote-style agnostic: ``manifest.get`` keys are collected from the AST as
    literal string constants regardless of quoting. Direct subscripting,
    non-get attribute access, dynamic keys, and bare-name escapes to unknown
    sinks are all reported, so a contract-graph drift cannot slip through a
    regex.
    """
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    keys: set[str] = set()
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Name) or node.id != "manifest":
            continue
        parent = parents.get(node)
        if isinstance(parent, ast.Attribute) and parent.value is node:
            if parent.attr != "get":
                violations.append(f"manifest.{parent.attr} attribute read")
        elif isinstance(parent, ast.Subscript) and parent.value is node:
            slice_node = parent.slice
            if isinstance(slice_node, ast.Constant) and isinstance(
                slice_node.value, str
            ):
                violations.append(f"manifest[{slice_node.value!r}] subscript read")
            else:
                violations.append("dynamic manifest subscript read")
        elif (
            isinstance(parent, ast.Call)
            and isinstance(parent.func, ast.Name)
            and parent.func.id == "_artifacts"
            and parent.args
            and parent.args[0] is node
        ):
            continue  # in-module sink, itself pinned to the artifacts key
        else:
            violations.append("bare manifest reference escapes to an unknown sink")
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "manifest"
            and node.func.attr == "get"
        ):
            if (
                node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                keys.add(node.args[0].value)
            else:
                violations.append("manifest.get with a non-literal key")
    return keys, violations


def _reconstruct_joined_template(joined: ast.JoinedStr) -> str:
    """Reconstruct the exact template text from a production f-string AST."""
    parts: list[str] = []
    for value in joined.values:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            parts.append(value.value)
        elif isinstance(value, ast.FormattedValue) and isinstance(
            value.value, ast.Name
        ):
            parts.append("{" + value.value.id + "}")
        else:
            raise AssertionError("unexpected collision template part")
    return "".join(parts)


# ---------------------------------------------------------------------------
# C2: source-derived fixed projection for a manifest-only mutation
# ---------------------------------------------------------------------------


def test_c2_manifest_hash_absent_from_sync_fields() -> None:
    source = _read("_e2a_sync_state_operations.py")
    start = source.index("_SYNC_FIELDS = (")
    end = source.index(")", start)
    fields = source[start:end]
    assert "manifest" not in fields, "manifest must not be a sync-state field"
    assert "last_synced_at" not in fields
    assert "now(" not in fields


def test_c2_manifest_absent_from_dml_templates() -> None:
    dml_source = _read("e2a_materialization_dml.py")
    assert "manifest" not in dml_source, "no DML template may persist the manifest"
    values_source = _read("_e2a_materialization_values.py")
    start = values_source.index("DmlTemplate.UPSERT_SYNC_STATE")
    end = values_source.index("CACHE_MEASUREMENT_STATEMENTS", start)
    segment = values_source[start:end]
    assert "manifest" not in segment
    assert "last_synced_at" not in segment
    assert "now(" not in segment


def test_c2_repository_outcome_formula_source_pinned() -> None:
    source = _read("e2a_materialization_repository.py")
    assert 'outcome="changed" if any(primary_counts.values()) else "no_op"' in source
    assert "comparator_parity=True" in source


def test_c2_contract_graph_validates_only_artifacts_key() -> None:
    source = _read("e2a_contract_graph.py")
    assert 'manifest.get("artifacts")' in source
    keys, violations = _manifest_reads(ast.parse(source))
    assert violations == [], f"unexpected manifest reads: {violations}"
    assert keys == {"artifacts"}, f"unexpected manifest keys read: {keys}"


def test_c2_manifest_read_checker_catches_quote_and_access_drift() -> None:
    """The AST checker catches quote variants and direct access on real source."""
    canonical_source = _read("e2a_contract_graph.py")
    keys, violations = _manifest_reads(ast.parse(canonical_source))
    assert keys == {"artifacts"} and not violations

    single_quote = ast.parse("value = manifest.get('artifacts')\n")
    keys_single, violations_single = _manifest_reads(single_quote)
    assert keys_single == {"artifacts"} and not violations_single

    quoted_drift = canonical_source.replace(
        'manifest.get("artifacts")', "manifest.get('artifacts')"
    )
    keys_quoted, violations_quoted = _manifest_reads(ast.parse(quoted_drift))
    assert keys_quoted == {"artifacts"} and not violations_quoted

    subscript_drift = canonical_source.replace(
        'manifest.get("artifacts")', 'manifest["artifacts"]'
    )
    _, subscript_violations = _manifest_reads(ast.parse(subscript_drift))
    assert any(
        "subscript read" in item for item in subscript_violations
    ), "direct manifest subscripting must be caught"

    dynamic = ast.parse("value = manifest.get(key)\n")
    _, dynamic_violations = _manifest_reads(dynamic)
    assert any(
        "non-literal key" in item for item in dynamic_violations
    ), "dynamic manifest.get keys must be caught"

    attribute = ast.parse("value = manifest.artifacts\n")
    _, attribute_violations = _manifest_reads(attribute)
    assert any(
        "attribute read" in item for item in attribute_violations
    ), "manifest attribute access must be caught"


def test_c2_desired_state_manifest_hash_is_the_only_validation() -> None:
    source = _read("e2a_contracts.py")
    assert "corpus manifest hash does not match canonical manifest" in source
    manifest = {"artifacts": [], "stage2_mutation": "c2-extra-manifest-key"}
    digest = canonical_json_sha256(manifest)
    assert len(digest) == 64
    assert "stage2_mutation" in canonical_json(manifest)


# ---------------------------------------------------------------------------
# C3/C4: exact preflight template, ordering, and unwrapped identity
# ---------------------------------------------------------------------------


def test_c3_c4_global_collision_template_full_source_anchor() -> None:
    """Pin the FULL current global collision f-string to the production AST."""
    source = _read("e2a_reconciler.py")
    tree = ast.parse(source)
    fn = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_check_global_rows"
    )
    templates = [
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.JoinedStr)
        and any(
            isinstance(value, ast.Constant)
            and isinstance(value.value, str)
            and "incompatible scope version" in value.value
            for value in node.values
        )
    ]
    assert len(templates) == 1, "expected exactly one global collision template"
    reconstructed = _reconstruct_joined_template(templates[0])
    assert reconstructed == (
        "global {table} {id_field}={row_id} is owned by incompatible "
        "scope version {row_version}"
    ), "production collision template drifted"
    assert reconstructed.startswith("global "), "template prefix must survive"
    assert "{id_field}=" in reconstructed, "id field/value form must survive"
    assert (
        "is owned by incompatible scope version " in reconstructed
    ), "incompatible scope phrase must survive"
    assert 'table="canonical_spans"' in source
    assert 'id_field="span_id"' in source
    assert "raise ValueError(collisions[0])" in source


def test_c3_c4_helper_collision_message_single_source() -> None:
    """The helper renders one source-anchored template, not a reconstruction."""
    from ._phase15_e2a_task88_transition_cells import (
        _GLOBAL_PREFLIGHT_COLLISION_TEMPLATE,
        _expected_span_collision_message,
    )

    bound_production = (
        "global canonical_spans span_id={span_id} is owned by incompatible "
        "scope version {version_id}"
    )
    assert (
        _GLOBAL_PREFLIGHT_COLLISION_TEMPLATE == bound_production
    ), "helper template must equal the canonical_spans-bound production template"
    rendered = _expected_span_collision_message("span-id-dummy", "version-id-dummy")
    assert rendered == (
        "global canonical_spans span_id=span-id-dummy is owned by incompatible "
        "scope version version-id-dummy"
    )


def test_c3_c4_canonical_spans_checked_first() -> None:
    source = _read("e2a_reconciler.py")
    span_index = source.index('table="canonical_spans"')
    chunk_index = source.index('table="vector_chunks"')
    assert span_index < chunk_index, "canonical_spans must be preflighted first"


def test_c4_default_reconciler_has_null_audit_factory() -> None:
    assert E2aReconciler()._failure_audit_connection_factory is None


class _FakeAdapters:
    """Minimal adaptation-context double satisfying register_loader."""

    def register_loader(self, type_name: object, loader: object) -> None:
        return None


class _FakeCursor:
    """Cursor double that raises the sentinel at the canonical_spans preflight."""

    def __init__(self, parent: E2aParent, sentinel: Exception) -> None:
        self.connection: _FakeConnection | None = None
        self.adapters = _FakeAdapters()
        self._parent = parent
        self._sentinel = sentinel
        self._lock_rows: list[dict[str, str]] = []
        self.close_called = False

    def execute(self, statement: str, parameters: object | None = None) -> None:
        if "FROM canonical_spans" in statement:
            raise self._sentinel
        if "FROM document_versions" in statement:
            self._lock_rows = [
                {
                    "doc_id": self._parent.document_id,
                    "version_id": self._parent.version_id,
                }
            ]

    def fetchall(self) -> object:
        return list(self._lock_rows)

    def close(self) -> None:
        self.close_called = True


class _FakeConnection:
    """Connection double with autocommit exactly False, like the real role."""

    autocommit = False

    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor
        self.rollback_called = False
        self.close_called = False

    def cursor(self, *, row_factory: object = None) -> _FakeCursor:
        return self._cursor

    def rollback(self) -> None:
        self.rollback_called = True

    def close(self) -> None:
        self.close_called = True


def _dummy_desired_state() -> E2aDesiredState:
    """Build a contract-valid single-parent state with dummy identities."""
    registration = SimpleNamespace(doc_id=uuid4(), version_id=uuid4())
    source_path = _create_source_fixture()
    try:
        return _build_foundation_desired_state(registration, source_path)
    finally:
        try:
            source_path.unlink()
        except OSError:
            pass


def test_c4_unwrapped_exception_object_identity_preserved() -> None:
    desired = _dummy_desired_state()
    parent = desired.parents[0]
    expected_message = (
        "global canonical_spans span_id="
        + desired.canonical_spans[0].span_id
        + " is owned by incompatible scope version "
        + parent.version_id
    )
    sentinel = ValueError(expected_message)
    cursor = _FakeCursor(parent, sentinel)
    connection = _FakeConnection(cursor)
    cursor.connection = connection
    with pytest.raises(ValueError) as exc_info:
        E2aReconciler().reconcile(connection, desired)
    assert exc_info.value is sentinel, "the exact exception object must propagate"
    assert exc_info.value.args == (expected_message,)
    assert connection.rollback_called, "primary must be rolled back"
    assert connection.close_called, "primary must be closed"
    assert cursor.close_called, "primary cursor must be closed"


# ---------------------------------------------------------------------------
# C5: audit and seed schema contracts
# ---------------------------------------------------------------------------


def test_c5_audit_migration_018_columns_and_constraints() -> None:
    source = _read_migration("018_okf_rebuild_failure_audit.sql")
    for column in (
        "audit_id UUID PRIMARY KEY",
        "rebuild_run_id UUID NOT NULL UNIQUE",
        "occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()",
        "failure_category TEXT NOT NULL",
        "failure_code TEXT NOT NULL",
        "failure_phase TEXT NOT NULL",
        "rollback_confirmed BOOLEAN NOT NULL CHECK (rollback_confirmed)",
        "scope_count INTEGER NOT NULL CHECK (scope_count >= 1)",
        "scope_manifest JSONB NOT NULL",
        "scope_manifest_sha256 CHAR(64) NOT NULL",
        "failing_doc_id UUID",
        "failing_version_id UUID",
        "diagnostic JSONB NOT NULL",
    ):
        assert column in source, f"missing audit column/constraint: {column}"


def test_c5_audit_append_only_triggers_present() -> None:
    source = _read_migration("018_okf_rebuild_failure_audit.sql")
    assert "prevent_okf_rebuild_failure_audit_mutation" in source
    assert "trg_okf_rebuild_failure_audit_append_only" in source
    assert "trg_okf_rebuild_failure_audit_no_truncate" in source


def test_c5_audit_phase_parent_reconciliation_allowed_by_019() -> None:
    source = _read_migration("019_e2a_materialization_contract.sql")
    assert "chk_okf_rebuild_failure_audit_phase" in source
    assert "parent_reconciliation" in source


def test_c5_entities_seed_columns_exist() -> None:
    source_005 = _read_migration("005_kg_extension.sql")
    for column in ("entity_id", "entity_key", "entity_type", "canonical_name"):
        assert column in source_005, f"missing entities column: {column}"
    source_006 = _read_migration("006_kg_graphrag_enrichment.sql")
    assert "description" in source_006
    assert "community_id" in source_006


def test_c5_incompatible_material_preflight_path_pinned() -> None:
    source = _read("_e2a_manual_fact_collision_preflight.py")
    assert "manual fact base row has incompatible material" in source
    assert '"entity_key"' in source


def test_c5_audit_insert_column_set_matches_reconciler() -> None:
    reconciler = _read("e2a_reconciler.py")
    assert "INSERT INTO okf_rebuild_failure_audit (" in reconciler
    for column in (
        "audit_id",
        "rebuild_run_id",
        "failure_category",
        "failure_code",
        "failure_phase",
        "rollback_confirmed",
        "scope_count",
        "scope_manifest",
        "scope_manifest_sha256",
        "failing_doc_id",
        "failing_version_id",
        "diagnostic",
    ):
        assert column in reconciler, f"missing audit insert column: {column}"


def test_c5_audit_scope_manifest_body_source_pinned() -> None:
    """The durable scope_manifest body is source-pinned to the reconciler."""
    source = _read("e2a_reconciler.py")
    assert '"manifest_sha256": desired.corpus_manifest_sha256' in source
    assert '"parent_count": len(desired.parents)' in source
    assert (
        '"version_ids": [parent.version_id for parent in desired.parents[:100]]'
        in source
    )


def test_c5_audit_diagnostic_is_bounded_error_type() -> None:
    source = _read("e2a_reconciler.py")
    assert '{"error_type": type(failure).__name__[:64]}' in source
