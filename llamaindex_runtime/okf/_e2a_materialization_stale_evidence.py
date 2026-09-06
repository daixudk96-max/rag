"""Private stale E2a evidence cleanup for reconciliation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from ._e2a_materialization_inventory import Cursor, Scope, stale_ids, string
from .e2a_contracts import DmlRecorder, E2aDesiredState
from .e2a_materialization_dml import DmlTemplate, execute_template


def delete_stale_evidence(
    cursor: Cursor,
    desired: E2aDesiredState,
    existing: Scope,
    recorder: DmlRecorder,
    stale_counts: dict[str, int],
) -> None:
    """Delete stale E2a evidence without relying on cascading foreign keys."""
    stale_links = stale_ids(
        existing["evidence_links"], desired.evidence_links, "evidence_link_id"
    )
    stale_evidence = stale_ids(
        existing["evidence"], desired.evidence_objects, "evidence_id"
    )
    _delete_stale_links_for_desired_evidence(
        cursor,
        existing["evidence_links"],
        stale_links,
        stale_evidence,
        recorder,
    )
    if stale_evidence:
        _delete_links_for_stale_evidence(cursor, stale_evidence, recorder)
    if stale_links:
        stale_counts["evidence_links"] = len(stale_links)
    if not stale_evidence:
        return
    _delete_evidence_targets(cursor, stale_evidence, recorder)
    execute_template(
        cursor,
        DmlTemplate.DELETE_EVIDENCE_BY_IDS,
        (stale_evidence,),
        recorder,
    )
    stale_counts["evidence"] = len(stale_evidence)


def _delete_stale_links_for_desired_evidence(
    cursor: Cursor,
    existing: Sequence[Mapping[str, object]],
    stale_links: Sequence[str],
    stale_evidence: Sequence[str],
    recorder: DmlRecorder,
) -> None:
    stale_evidence_ids = frozenset(stale_evidence)
    stale_link_ids = frozenset(stale_links)
    link_ids = [
        link_id
        for row in existing
        if (link_id := string(row.get("evidence_link_id"))) in stale_link_ids
        and string(row.get("evidence_id")) not in stale_evidence_ids
    ]
    if link_ids:
        _delete_links_by_id(cursor, link_ids, recorder)


def _delete_links_by_id(
    cursor: Cursor, evidence_link_ids: Sequence[str], recorder: DmlRecorder
) -> None:
    execute_template(
        cursor,
        DmlTemplate.DELETE_EVIDENCE_LINKS_BY_IDS,
        (list(evidence_link_ids), "manual_okf"),
        recorder,
    )


def _delete_links_for_stale_evidence(
    cursor: Cursor, evidence_ids: Sequence[str], recorder: DmlRecorder
) -> None:
    execute_template(
        cursor,
        DmlTemplate.DELETE_EVIDENCE_LINKS_BY_EVIDENCE_IDS,
        (list(evidence_ids), "manual_okf"),
        recorder,
    )


def _delete_evidence_targets(
    cursor: Cursor, evidence_ids: Sequence[str], recorder: DmlRecorder
) -> None:
    execute_template(
        cursor,
        DmlTemplate.DELETE_EVIDENCE_TARGETS_BY_EVIDENCE_IDS,
        (list(evidence_ids),),
        recorder,
    )
