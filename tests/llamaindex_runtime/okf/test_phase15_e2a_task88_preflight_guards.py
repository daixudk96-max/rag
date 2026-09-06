"""Task #88 preflight and DmlRecorder guard pins (non-live).

This module is one of three focused Task #88 unit modules split from the
original oversized single-file RED surface. It pins, entirely WITHOUT a
database and using narrow recording doubles from
``_phase15_e2a_task88_testkit``:

- exact ``DmlRecorder`` denylist errors and accumulation,
- global primary-key preflight rejection messages (cross-scope takeover
  and non-manual evidence-link source kinds) with all five preflight
  queries issued and no DML before rejection,
- sync ownership conflict messages,
- manual-fact collision preflight exact messages.

No database, no Docker, and no live selector is exercised here.
"""

from __future__ import annotations

import re

import pytest

from llamaindex_runtime.okf._e2a_manual_fact_collision_preflight import (
    preflight_manual_fact_collisions,
)
from llamaindex_runtime.okf._e2a_sync_state_operations import (
    ensure_sync_path_ownership,
    upsert_sync_state,
)
from llamaindex_runtime.okf.e2a_contracts import (
    DmlRecorder,
    E2aDesiredState,
    E2aManualFact,
)
from llamaindex_runtime.okf.e2a_reconciler import E2aReconciler

from ._phase15_e2a_task88_testkit import (
    _GLOBAL_ROWS,
    _OTHER_ENTITY_ID,
    _OTHER_VERSION_ID,
    _VERSION_ID,
    _Connection,
    _Cursor,
    _desired_full,
    _entity_row,
    _identifier_for,
    _is_dml,
    _matching_parent_rows,
    _normalized,
    _ownership_row,
    _references_exact_table,
    _Repository,
    _sync_row,
    _SyncDesired,
)


class TestDmlRecorderDenylistErrors:
    """Exact DmlRecorder denylist error messages and counts."""

    @pytest.mark.parametrize(
        "table",
        (
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
        ),
    )
    def test_record_issued_denylist_exact_error_and_count(self, table: str) -> None:
        recorder = DmlRecorder()
        with pytest.raises(
            ValueError, match=re.escape(f"forbidden DML table: {table}")
        ):
            recorder.record_issued(table=table, operation="INSERT")
        assert recorder.denylist_dml_counts[table] == 1
        assert table not in recorder.primary_dml_by_table

    def test_record_measured_effect_denylist_exact_error(self) -> None:
        recorder = DmlRecorder()
        with pytest.raises(
            ValueError, match=re.escape("forbidden cascade table: chunk_entity_links")
        ):
            recorder.record_measured_effect(
                table="chunk_entity_links", count=1, origin="cascade"
            )
        assert recorder.denylist_dml_counts["chunk_entity_links"] == 1

    def test_record_outside_allowlist_exact_error(self) -> None:
        recorder = DmlRecorder()
        with pytest.raises(
            ValueError,
            match=re.escape("DML table is outside the E2a allowlist: random_table"),
        ):
            recorder.record_issued(table="random_table", operation="UPDATE")

    def test_record_unsupported_operation_exact_error(self) -> None:
        recorder = DmlRecorder()
        with pytest.raises(ValueError, match="DML operation is unsupported"):
            recorder.record_issued(table="canonical_spans", operation="TRUNCATE")

    def test_record_cache_effect_unsupported_table_exact_error(self) -> None:
        recorder = DmlRecorder()
        with pytest.raises(ValueError, match="cache effect table is unsupported"):
            recorder.record_cache_effect(table="entity_mentions", count=1)

    def test_record_invalid_count_exact_error(self) -> None:
        recorder = DmlRecorder()
        with pytest.raises(ValueError, match="DML record is invalid"):
            recorder.record_measured_effect(
                table="canonical_spans", count=-1, origin="cascade"
            )

    def test_record_issued_allowlist_table_accumulates(self) -> None:
        recorder = DmlRecorder()
        recorder.record_issued(table="canonical_spans", operation="INSERT")
        recorder.record_issued(table="canonical_spans", operation="UPDATE")
        assert recorder.primary_dml_by_table["canonical_spans"] == 2
        assert recorder.denylist_dml_counts == {}


class TestGlobalPrimaryKeyPreflight:
    """Global PK preflight errors via narrow recording cursor."""

    @pytest.mark.parametrize("table", tuple(row[0] for row in _GLOBAL_ROWS))
    def test_global_preflight_rejects_cross_scope_takeover_exact_message(
        self, table: str
    ) -> None:
        desired = _desired_full()
        identifier = _identifier_for(desired, table)
        cursor = _Cursor(
            parent_rows=_matching_parent_rows(desired),
            collision_table=table,
            collision_identifier=identifier,
        )
        connection = _Connection(cursor)
        repository = _Repository()

        expected = (
            f"global {table} {_GLOBAL_ROWS[tuple(row[0] for row in _GLOBAL_ROWS).index(table)][1]}"
            f"={identifier} is owned by incompatible scope version {_OTHER_VERSION_ID}"
        )
        with pytest.raises(ValueError, match=re.escape(expected)):
            E2aReconciler(repository=repository).reconcile(connection, desired)

        self._assert_all_five_preflight_queries(cursor)
        assert repository.calls == []
        assert not any(_is_dml(statement) for statement, _ in cursor.calls)
        assert connection.commits == 0
        assert connection.rollbacks == connection.closed == 1

    def test_evidence_links_preflight_rejects_non_manual_source_kind(self) -> None:
        desired = _desired_full()
        link_id = desired.evidence_links[0].evidence_link_id
        cursor = _Cursor(
            parent_rows=_matching_parent_rows(desired),
            collision_table="evidence_links",
            collision_identifier=link_id,
            collision_version_id=_VERSION_ID,
            collision_source_kind="legacy",
        )
        connection = _Connection(cursor)
        repository = _Repository()

        with pytest.raises(
            ValueError,
            match=re.escape(
                f"global evidence_links evidence_link_id={link_id} has "
                "source_kind=legacy, expected manual_okf"
            ),
        ):
            E2aReconciler(repository=repository).reconcile(connection, desired)

        self._assert_all_five_preflight_queries(cursor)
        assert repository.calls == []
        assert connection.commits == 0
        assert connection.rollbacks == connection.closed == 1

    def test_same_scope_global_rows_commit_no_op(self) -> None:
        desired = _desired_full()
        cursor = _Cursor(
            parent_rows=_matching_parent_rows(desired),
            compatible_identifiers={
                table: _identifier_for(desired, table) for table, _ in _GLOBAL_ROWS
            },
        )
        connection = _Connection(cursor)
        repository = _Repository()

        result = E2aReconciler(repository=repository).reconcile(connection, desired)

        self._assert_all_five_preflight_queries(cursor)
        assert result.outcome == "no_op"
        assert len(repository.calls) == 1
        assert connection.commits == connection.closed == 1
        assert connection.rollbacks == 0

    @staticmethod
    def _assert_all_five_preflight_queries(cursor: _Cursor) -> None:
        for table, _ in _GLOBAL_ROWS:
            matches = [
                statement
                for statement, _ in cursor.calls
                if _references_exact_table(statement, keyword="from", table=table)
                and "= any(%s)" in _normalized(statement)
            ]
            assert (
                len(matches) == 1
            ), f"expected exactly one preflight query for {table}"


class TestSyncConflictExactMessages:
    """Sync ownership conflict messages via direct module calls."""

    def test_ensure_sync_path_ownership_rejects_legacy_owner(self) -> None:
        row = _sync_row()
        desired = _SyncDesired((row,))
        cursor = _Cursor(
            sync_owner_rows=[
                {
                    "okf_file_path": row["okf_file_path"],
                    "materialization_owner": "legacy",
                }
            ]
        )

        with pytest.raises(
            ValueError, match="sync ownership collision with a non-E2a row"
        ):
            ensure_sync_path_ownership(cursor, desired)

    def test_ensure_sync_path_ownership_rejects_invalid_result_set(self) -> None:
        desired = _SyncDesired((_sync_row(),))
        cursor = _Cursor(sync_owner_rows="not a sequence")

        with pytest.raises(
            ValueError, match="sync ownership query returned an invalid result set"
        ):
            ensure_sync_path_ownership(cursor, desired)

    def test_ensure_sync_path_ownership_rejects_malformed_row(self) -> None:
        desired = _SyncDesired((_sync_row(),))
        cursor = _Cursor(
            sync_owner_rows=[
                {"okf_file_path": desired.sync_state_rows[0]["okf_file_path"]}
            ]
        )

        with pytest.raises(
            ValueError, match="sync ownership query returned a malformed row"
        ):
            ensure_sync_path_ownership(cursor, desired)

    def test_upsert_sync_state_conflict_exact_message(self) -> None:
        desired_row = _sync_row()
        stale_row = {**desired_row, "status": "stale"}
        cursor = _Cursor(fetchone_none=True)
        recorder = DmlRecorder()

        with pytest.raises(
            ValueError, match="sync ownership conflict prevented materialization"
        ):
            upsert_sync_state(
                cursor,
                _SyncDesired((desired_row,)),
                {"okf_sync_state": (stale_row,)},
                recorder,
            )

        assert cursor.calls, "the upsert statement must be issued"

    def test_upsert_sync_state_success_records_primary_dml(self) -> None:
        desired_row = _sync_row()
        stale_row = {**desired_row, "status": "stale"}
        cursor = _Cursor()
        recorder = DmlRecorder()

        upsert_sync_state(
            cursor,
            _SyncDesired((desired_row,)),
            {"okf_sync_state": (stale_row,)},
            recorder,
        )

        assert recorder.primary_dml_by_table["okf_sync_state"] == 1
        assert cursor.calls, "the upsert statement must be issued"


class TestManualFactPreflightExactMessages:
    """Manual fact preflight messages via direct calls with narrow cursors."""

    def _desired_and_fact(self) -> tuple[E2aDesiredState, E2aManualFact]:
        desired = _desired_full()
        return desired, desired.manual_entities[0]

    def test_manual_fact_natural_key_collision_exact_message(self) -> None:
        desired, fact = self._desired_and_fact()
        row = dict(_entity_row(fact))
        row["entity_id"] = _OTHER_ENTITY_ID
        cursor = _Cursor(entity_rows=[row], ownership_rows=[])

        with pytest.raises(
            ValueError, match="manual fact natural key collides with another identifier"
        ):
            preflight_manual_fact_collisions(cursor, desired)

    def test_manual_fact_incompatible_material_exact_message(self) -> None:
        desired, fact = self._desired_and_fact()
        row = dict(_entity_row(fact))
        row["entity_key"] = "different-key"
        cursor = _Cursor(entity_rows=[row], ownership_rows=[])

        with pytest.raises(
            ValueError, match="manual fact base row has incompatible material"
        ):
            preflight_manual_fact_collisions(cursor, desired)

    def test_manual_fact_unmanaged_enrichment_exact_message(self) -> None:
        desired, fact = self._desired_and_fact()
        row = dict(_entity_row(fact))
        row["description"] = "polluted"
        cursor = _Cursor(entity_rows=[row], ownership_rows=[])

        with pytest.raises(
            ValueError, match="manual fact base row has unmanaged enrichment"
        ):
            preflight_manual_fact_collisions(cursor, desired)

    def test_manual_fact_ownership_without_base_row_exact_message(self) -> None:
        desired, _ = self._desired_and_fact()
        owner = desired.ownership_facts[0]
        cursor = _Cursor(entity_rows=[], ownership_rows=[_ownership_row(owner)])

        with pytest.raises(
            ValueError, match="manual fact ownership exists without its base row"
        ):
            preflight_manual_fact_collisions(cursor, desired)

    def test_manual_fact_lacks_e2a_ownership_exact_message(self) -> None:
        desired, fact = self._desired_and_fact()
        cursor = _Cursor(entity_rows=[_entity_row(fact)], ownership_rows=[])

        with pytest.raises(
            ValueError, match="manual fact base row lacks compatible E2a ownership"
        ):
            preflight_manual_fact_collisions(cursor, desired)

    def test_manual_fact_compatible_rows_pass_preflight(self) -> None:
        desired, fact = self._desired_and_fact()
        owner = desired.ownership_facts[0]
        cursor = _Cursor(
            entity_rows=[_entity_row(fact)],
            ownership_rows=[_ownership_row(owner)],
        )

        preflight_manual_fact_collisions(cursor, desired)
