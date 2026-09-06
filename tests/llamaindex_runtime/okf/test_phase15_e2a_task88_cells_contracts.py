"""Task #88 non-live cell contracts and validation helper pins.

This module is one of three focused Task #88 unit modules split from the
original oversized single-file RED surface. It pins the cells helper
``_phase15_e2a_task88_cells``:

- the single SHARED required-cell id ``TASK88_REQUIRED_CELL_ID``
  (``true_late_dml_failure``) behind the approved formal composed proof,
  with NO parallel blocked definition: every stale Task #88 blocker API
  name (``TASK88_BLOCKED_*``, ``Task88BlockedStatus``,
  ``require_blocked_late_dml_proof``) must be absent,
- the exact 10-key all-zero denylist map and typed validator,
- the strengthened ``E2aReconciliationResult`` field contract: primary
  DML must carry the FULL canonical key set with non-negative exact-int
  values, the denylist stays an exact 10-key map, and the
  stale-deletion / cache-invalidation maps reject non-string / non-int /
  negative values and keys outside their canonical production domains
  while permitting production's intentional sparsity,
- the ``comparator_parity`` contract accepting exactly ``bool`` or
  ``None`` (production emits ``None`` for rolled-back / unknown
  outcomes) while still rejecting every other runtime type,
- the mandated prohibited-module family guard: retained exact module
  names plus family fragments, matched on plain strings (never an
  import),
- the immutable cell-plan metadata with the three plan-gate corrections,
  including the fifth (required-cell) descriptor carrying non-empty
  concrete source-supported facts for the approved composed proof.

Shared support (narrow recording doubles, desired-state builders) lives
in ``_phase15_e2a_task88_testkit``. No database, no Docker, and no live
selector is exercised here.
"""

from __future__ import annotations

import dataclasses
from dataclasses import FrozenInstanceError
from types import MappingProxyType

import pytest

from llamaindex_runtime.okf import e2a_contracts as contracts
from llamaindex_runtime.okf.e2a_contracts import (
    _E2A_CACHE_TABLES,
    _E2A_DENYLIST_TABLES,
    _E2A_PRIMARY_TABLES,
    E2aReconciliationResult,
)

from ._phase15_e2a_task88_testkit import (
    _DIGEST,
    _cells_module,
    _desired_empty,
    _no_op_result,
)


class TestTask88RequiredCellId:
    """Single shared Task #88 required-cell id (approved composed proof)."""

    def test_required_cell_id_exact_value(self) -> None:
        cells = _cells_module()
        assert cells.TASK88_REQUIRED_CELL_ID == "true_late_dml_failure"

    def test_required_cell_id_single_shared_definition_no_parallel_blocked_api(
        self,
    ) -> None:
        """No parallel blocked definition may exist alongside the shared id."""
        cells = _cells_module()
        for stale_name in (
            "TASK88_BLOCKED_REQUIRED_CELL",
            "TASK88_BLOCKED_PROOF_MESSAGE",
            "TASK88_BLOCKED_STATUS",
            "Task88BlockedStatus",
            "require_blocked_late_dml_proof",
        ):
            assert not hasattr(cells, stale_name), (
                f"stale Task #88 blocker API must not exist: {stale_name}"
            )


class TestDenylistContractHelpers:
    """Exact 10-key denylist map and typed validator (RED until helper exists)."""

    def test_denylist_map_exact_ten_keys_all_zero(self) -> None:
        cells = _cells_module()
        mapping = cells.E2A_DENYLIST_TABLES_ALL_ZERO
        assert len(mapping) == 10
        assert set(mapping) == {
            "chunk_entity_links",
            "node_entity_links",
            "entity_mentions",
            "entity_aliases",
            "entity_merge_log",
            "ner_entities",
            "ner_relations",
            "fusion_state",
            "r3_state",
            "external_projection_status",
        }
        assert all(count == 0 for count in mapping.values())

    def test_denylist_map_matches_canonical_production_constant(self) -> None:
        cells = _cells_module()
        assert set(cells.E2A_DENYLIST_TABLES_ALL_ZERO) == set(_E2A_DENYLIST_TABLES)

    def test_denylist_map_is_immutable(self) -> None:
        cells = _cells_module()
        assert isinstance(cells.E2A_DENYLIST_TABLES_ALL_ZERO, MappingProxyType)
        with pytest.raises(TypeError):
            cells.E2A_DENYLIST_TABLES_ALL_ZERO["entity_mentions"] = 1  # type: ignore[index]

    def test_validate_denylist_accepts_canonical_map(self) -> None:
        cells = _cells_module()
        validated = cells.validate_denylist_dml_counts(
            cells.E2A_DENYLIST_TABLES_ALL_ZERO
        )
        assert validated == cells.E2A_DENYLIST_TABLES_ALL_ZERO
        assert isinstance(validated, MappingProxyType)

    def test_validate_denylist_rejects_missing_key(self) -> None:
        cells = _cells_module()
        missing = dict(cells.E2A_DENYLIST_TABLES_ALL_ZERO)
        del missing["entity_mentions"]
        with pytest.raises(ValueError, match="missing denylist key"):
            cells.validate_denylist_dml_counts(missing)

    def test_validate_denylist_never_silently_defaults_missing_keys(self) -> None:
        cells = _cells_module()
        partial = {table: 0 for table in ("chunk_entity_links", "ner_entities")}
        with pytest.raises(ValueError, match="missing denylist key"):
            cells.validate_denylist_dml_counts(partial)

    def test_validate_denylist_rejects_extra_key(self) -> None:
        cells = _cells_module()
        extra = dict(cells.E2A_DENYLIST_TABLES_ALL_ZERO)
        extra["unlisted_table"] = 0
        with pytest.raises(ValueError, match="unexpected denylist key"):
            cells.validate_denylist_dml_counts(extra)

    def test_validate_denylist_rejects_non_integer_value(self) -> None:
        cells = _cells_module()
        invalid = dict(cells.E2A_DENYLIST_TABLES_ALL_ZERO)
        invalid["entity_mentions"] = "3"
        with pytest.raises(ValueError, match="non-negative integer"):
            cells.validate_denylist_dml_counts(invalid)

    def test_validate_denylist_rejects_negative_value(self) -> None:
        cells = _cells_module()
        invalid = dict(cells.E2A_DENYLIST_TABLES_ALL_ZERO)
        invalid["entity_mentions"] = -1
        with pytest.raises(ValueError, match="non-negative integer"):
            cells.validate_denylist_dml_counts(invalid)

    def test_validate_denylist_rejects_non_mapping(self) -> None:
        cells = _cells_module()
        with pytest.raises(ValueError, match="must be a mapping"):
            cells.validate_denylist_dml_counts(["chunk_entity_links"])  # type: ignore[arg-type]


class TestResultFieldContractHelper:
    """E2aReconciliationResult field contract helper (RED until helper exists)."""

    def test_result_field_contract_has_exact_ten_fields(self) -> None:
        cells = _cells_module()
        assert set(cells.RESULT_FIELD_CONTRACT) == {
            "outcome",
            "manifest_sha256",
            "primary_dml_by_table",
            "denylist_dml_counts",
            "comparator_parity",
            "stale_deletion_counts",
            "cache_invalidation_counts",
            "failure_audit_outcome",
            "post_rollback_failure_audit_outcome",
            "reconciliation_required",
        }

    def test_result_field_contract_validates_real_result(self) -> None:
        cells = _cells_module()
        cells.validate_result_field_contract(_no_op_result(_desired_empty()))

    def test_result_field_contract_rejects_wrong_runtime_type(self) -> None:
        cells = _cells_module()
        malformed = object.__new__(E2aReconciliationResult)
        for name, value in (
            ("outcome", "no_op"),
            ("manifest_sha256", _DIGEST),
            ("primary_dml_by_table", None),
            ("denylist_dml_counts", MappingProxyType({})),
            ("comparator_parity", True),
            ("stale_deletion_counts", MappingProxyType({})),
            ("cache_invalidation_counts", MappingProxyType({})),
            ("failure_audit_outcome", None),
            ("post_rollback_failure_audit_outcome", None),
            ("reconciliation_required", False),
        ):
            object.__setattr__(malformed, name, value)
        with pytest.raises(
            ValueError, match="primary_dml_by_table has an unexpected runtime type"
        ):
            cells.validate_result_field_contract(malformed)

    def test_result_field_contract_rejects_non_result_object(self) -> None:
        cells = _cells_module()
        with pytest.raises(ValueError, match="applies to E2aReconciliationResult"):
            cells.validate_result_field_contract(object())

    def test_primary_dml_requires_full_canonical_key_set(self) -> None:
        cells = _cells_module()
        result = _no_op_result(_desired_empty())
        object.__setattr__(result, "primary_dml_by_table", {})
        with pytest.raises(ValueError, match="full E2a primary table key set"):
            cells.validate_result_field_contract(result)

    def test_primary_dml_rejects_extra_key_outside_canonical_primary(self) -> None:
        cells = _cells_module()
        result = _no_op_result(_desired_empty())
        primary = dict(result.primary_dml_by_table)
        primary["random_table"] = 1
        object.__setattr__(result, "primary_dml_by_table", primary)
        with pytest.raises(ValueError, match="full E2a primary table key set"):
            cells.validate_result_field_contract(result)

    def test_primary_dml_rejects_non_int_and_negative_values(self) -> None:
        cells = _cells_module()
        result = _no_op_result(_desired_empty())
        primary = dict(result.primary_dml_by_table)
        primary["canonical_spans"] = "1"
        object.__setattr__(result, "primary_dml_by_table", primary)
        with pytest.raises(ValueError, match="non-negative integer mapping"):
            cells.validate_result_field_contract(result)
        negative = _no_op_result(_desired_empty())
        primary = dict(negative.primary_dml_by_table)
        primary["canonical_spans"] = -1
        object.__setattr__(negative, "primary_dml_by_table", primary)
        with pytest.raises(ValueError, match="non-negative integer mapping"):
            cells.validate_result_field_contract(negative)

    def test_denylist_field_validated_exact_canonical_key_set(self) -> None:
        cells = _cells_module()
        result = _no_op_result(_desired_empty())
        object.__setattr__(result, "denylist_dml_counts", {})
        with pytest.raises(ValueError, match="missing denylist key"):
            cells.validate_result_field_contract(result)

    def test_stale_deletion_counts_sparse_domain_contract(self) -> None:
        cells = _cells_module()
        result = _no_op_result(_desired_empty())
        object.__setattr__(result, "stale_deletion_counts", {"tree_nodes": 2})
        cells.validate_result_field_contract(result)
        object.__setattr__(result, "stale_deletion_counts", {})
        cells.validate_result_field_contract(result)

    def test_stale_deletion_counts_reject_outside_domain(self) -> None:
        cells = _cells_module()
        result = _no_op_result(_desired_empty())
        object.__setattr__(result, "stale_deletion_counts", {"random_table": 1})
        with pytest.raises(ValueError, match="outside the allowed domain"):
            cells.validate_result_field_contract(result)

    def test_stale_deletion_counts_reject_bad_values(self) -> None:
        cells = _cells_module()
        result = _no_op_result(_desired_empty())
        object.__setattr__(result, "stale_deletion_counts", {"tree_nodes": "2"})
        with pytest.raises(ValueError, match="non-negative integer mapping"):
            cells.validate_result_field_contract(result)
        negative = _no_op_result(_desired_empty())
        object.__setattr__(negative, "stale_deletion_counts", {"tree_nodes": -2})
        with pytest.raises(ValueError, match="non-negative integer mapping"):
            cells.validate_result_field_contract(negative)

    def test_cache_invalidation_counts_domain_and_values(self) -> None:
        cells = _cells_module()
        result = _no_op_result(_desired_empty())
        object.__setattr__(result, "cache_invalidation_counts", {"summaries": 1})
        cells.validate_result_field_contract(result)
        object.__setattr__(result, "cache_invalidation_counts", {"entity_mentions": 1})
        with pytest.raises(ValueError, match="outside the allowed domain"):
            cells.validate_result_field_contract(result)
        float_count = _no_op_result(_desired_empty())
        object.__setattr__(float_count, "cache_invalidation_counts", {"summaries": 1.5})
        with pytest.raises(ValueError, match="non-negative integer mapping"):
            cells.validate_result_field_contract(float_count)

    def test_count_map_domains_are_canonical_production_constants(self) -> None:
        cells = _cells_module()
        assert set(cells.E2A_STALE_DELETION_TABLES) == {
            "tree_node_spans",
            "vector_chunk_spans",
            "tree_nodes",
            "vector_chunks",
            "evidence",
            "evidence_links",
            "okf_manual_fact_ownership",
            "okf_sync_state",
            "canonical_spans",
        }
        assert set(cells.E2A_STALE_DELETION_TABLES) <= set(_E2A_PRIMARY_TABLES)
        assert set(_E2A_CACHE_TABLES) <= set(_E2A_PRIMARY_TABLES)
        assert set(_E2A_CACHE_TABLES) == set(contracts._E2A_CACHE_TABLES)
        assert set(_E2A_CACHE_TABLES) == {
            "summaries",
            "node_embeddings",
            "semantic_distribution",
        }
        assert set(_E2A_DENYLIST_TABLES) == set(contracts._E2A_DENYLIST_TABLES)
        assert set(_E2A_PRIMARY_TABLES) == set(contracts._E2A_PRIMARY_TABLES)


class TestComparatorParityFieldContract:
    """comparator_parity accepts exactly bool | None (production emits None)."""

    def test_result_field_contract_pins_comparator_parity_bool_or_none(self) -> None:
        cells = _cells_module()
        assert cells.RESULT_FIELD_CONTRACT["comparator_parity"] == "bool or None"

    def test_result_field_contract_accepts_comparator_parity_none(self) -> None:
        cells = _cells_module()
        result = _no_op_result(_desired_empty())
        object.__setattr__(result, "comparator_parity", None)
        cells.validate_result_field_contract(result)

    def test_result_field_contract_still_accepts_boolean_parity(self) -> None:
        cells = _cells_module()
        result = _no_op_result(_desired_empty())
        object.__setattr__(result, "comparator_parity", False)
        cells.validate_result_field_contract(result)
        object.__setattr__(result, "comparator_parity", True)
        cells.validate_result_field_contract(result)

    def test_result_field_contract_rejects_invalid_comparator_parity(self) -> None:
        cells = _cells_module()
        invalid_values: tuple[object, ...] = (1, 0, 1.0, "true", "", [], {})
        for invalid in invalid_values:
            result = _no_op_result(_desired_empty())
            object.__setattr__(result, "comparator_parity", invalid)
            with pytest.raises(
                ValueError, match="comparator_parity has an unexpected runtime type"
            ):
                cells.validate_result_field_contract(result)


class TestBlockedModuleFamilyGuard:
    """Mandated prohibited-module family guard (string-input matcher)."""

    def test_exact_blocked_module_names_are_pinned(self) -> None:
        cells = _cells_module()
        assert cells.BLOCKED_EXACT_MODULE_NAMES == frozenset(
            {
                "llamaindex_runtime.okf.e2a_disposable_execution",
                "verification.phase15-okf-ingestion-pipeline.run_e2a_verification",
            }
        )

    def test_blocked_family_fragments_are_pinned(self) -> None:
        cells = _cells_module()
        assert cells.BLOCKED_MODULE_FRAGMENTS == frozenset(
            {
                "real_e2a_reconciler",
                "disposable_acceptance",
                "disposable_postgres",
                "_real_e2a_",
            }
        )

    def test_exact_names_and_future_family_members_are_blocked(self) -> None:
        cells = _cells_module()
        for name in (
            "llamaindex_runtime.okf.e2a_disposable_execution",
            "verification.phase15-okf-ingestion-pipeline.run_e2a_verification",
            "llamaindex_runtime.okf.e2a_disposable_acceptance",
            "tests.llamaindex_runtime.okf._real_e2a_reconciler_testkit",
            "tests.llamaindex_runtime.okf.test_real_e2a_reconciler_harness_unit",
            "tests.llamaindex_runtime.okf._real_e2a_reconciler_types",
            "tests.llamaindex_runtime.okf.disposable_postgres_testkit",
        ):
            assert cells.module_name_is_blocked(name) is True, name

    def test_unrelated_module_names_are_allowed(self) -> None:
        cells = _cells_module()
        # The verification namespace itself is guarded exactly (the runner
        # module name), never as a family fragment.
        for name in (
            "os",
            "sys",
            "pytest",
            "importlib.util",
            "llamaindex_runtime.okf.e2a_contracts",
            "llamaindex_runtime.okf.e2a_reconciler",
            "llamaindex_runtime.okf.e2a_materialization_repository",
            "tests.llamaindex_runtime.okf._phase15_e2a_task88_cells",
            "tests.llamaindex_runtime.okf._phase15_e2a_task88_testkit",
            "tests.llamaindex_runtime.okf.phase15_e2a_task88_real_acceptance",
            "tests.llamaindex_runtime.okf.test_phase15_e2a_task88_cells_contracts",
            "verification.phase15-okf-ingestion-pipeline",
        ):
            assert cells.module_name_is_blocked(name) is False, name


class TestCellPlanMetadata:
    """Cell-plan descriptors with the three plan-gate corrections."""

    def test_live_gate_order_requires_reviews_before_live(self) -> None:
        cells = _cells_module()
        assert cells.LIVE_GATE_ORDER == (
            "unit_green",
            "general_review",
            "db_security_review",
            "authorized_live",
        )

    def test_every_live_cell_requires_reviews_before_live(self) -> None:
        cells = _cells_module()
        assert cells.CELL_PLAN
        for plan in cells.CELL_PLAN:
            assert plan.requires_reviews_before_live is True

    def test_cell_ids_are_unique(self) -> None:
        cells = _cells_module()
        ids = [plan.cell_id for plan in cells.CELL_PLAN]
        assert len(ids) == len(set(ids))

    def test_parent_bearing_cells_declare_parent_provenance(self) -> None:
        cells = _cells_module()
        plans = {plan.cell_id: plan for plan in cells.CELL_PLAN}
        assert cells.PARENT_BEARING_CELL_IDS
        for cell_id in cells.PARENT_BEARING_CELL_IDS:
            assert cell_id in plans
            assert plans[
                cell_id
            ].required_parent_provenance, (
                f"parent-bearing cell {cell_id} must declare required parent provenance"
            )

    def test_audit_cell_requires_injected_fresh_attested_factory(self) -> None:
        cells = _cells_module()
        plans = {plan.cell_id: plan for plan in cells.CELL_PLAN}
        assert cells.AUDIT_CELL_ID in plans
        audit = plans[cells.AUDIT_CELL_ID]
        assert audit.requires_injected_fresh_attested_factory is True
        assert audit.requires_reviews_before_live is True

    def test_required_cell_plan_descriptor_carries_composed_proof(self) -> None:
        """The required-cell descriptor pins the approved composed proof."""
        cells = _cells_module()
        plans = {plan.cell_id: plan for plan in cells.CELL_PLAN}
        required = plans[cells.TASK88_REQUIRED_CELL_ID]
        assert required.cell_name
        assert required.source_supported_facts, (
            "the composed-proof cell must carry non-empty concrete "
            "source-supported facts"
        )
        facts = " ".join(required.source_supported_facts)
        for fragment in (
            "rolled_back_failure",
            "audit",
            "observer",
            "_issue",
            "_upsert_evidence",
            "preflight",
            "inventory",
            "migration 019",
            "rollback-result-map",
        ):
            assert fragment in facts, f"composed-proof fact must mention {fragment!r}"
        assert required.required_parent_provenance == cells._PARENT_PROVENANCE_STATEMENT
        assert required.requires_injected_fresh_attested_factory is True
        assert required.requires_reviews_before_live is True

    def test_required_cell_plan_is_not_the_audit_cell(self) -> None:
        cells = _cells_module()
        assert cells.AUDIT_CELL_ID == "failure_audit_written"
        assert cells.AUDIT_CELL_ID != cells.TASK88_REQUIRED_CELL_ID

    def test_cell_plan_descriptors_are_frozen(self) -> None:
        cells = _cells_module()
        assert {field.name for field in dataclasses.fields(cells.CellPlan)} == {
            "cell_id",
            "cell_name",
            "source_supported_facts",
            "required_parent_provenance",
            "requires_injected_fresh_attested_factory",
            "requires_reviews_before_live",
        }
        with pytest.raises(FrozenInstanceError):
            cells.CELL_PLAN[0].cell_name = "changed"  # type: ignore[misc]

    def test_cell_plan_metadata_is_immutable(self) -> None:
        cells = _cells_module()
        assert isinstance(cells.CELL_PLAN, tuple)
        assert isinstance(cells.PARENT_BEARING_CELL_IDS, frozenset)
        assert isinstance(cells.LIVE_GATE_ORDER, tuple)
