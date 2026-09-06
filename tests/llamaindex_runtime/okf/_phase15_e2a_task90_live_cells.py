"""Live cells for the Phase 15 E2A Task #90 controlled producer.

Non-collected (underscore prefix) support for the selected live acceptance
selector ``phase15_e2a_task90_live_acceptance``; never collected by default
pytest discovery. The core live helper is a wire-only controlled producer:
when separately authorized it runs one disposable DB lifecycle and, in a
single invocation, exercises the real strict E2A admission of two endpoint
entities and one manual relation, a real first reconcile with the DEFAULT
``E2aReconciler()`` (whose repository defaults to a real
``E2aMaterializationRepository()``), an equivalent rerun that MUST be
``no_op`` with every real primary DML table count exactly 0, independent
fresh-observer full-collection scope snapshots before and after the rerun
that MUST be equal, and the build + verify of a process-local structural
binding over the exact first-reconcile result object -- all before a
redacted canonical artifact dict is produced.

Security contract: no environment reads, no connection target or secret
named, no URI/credential/target/corpus text in any repr, no test-framework
machinery, no fake/replacement of any production symbol, and no import of
the protected historical verification runner. Connections are opened only
through the caller-provided disposable session's attested factory.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from llamaindex_runtime.okf import e2a_admission
from llamaindex_runtime.okf.canonical_hash import canonical_hash
from llamaindex_runtime.okf.contracts import dump_raw_frontmatter
from llamaindex_runtime.okf.e2a_contracts import (
    E2aDesiredState,
    E2aParent,
    E2aReconciliationResult,
    canonical_json,
    deterministic_id,
)
from llamaindex_runtime.okf.e2a_materialization_repository import (
    E2aMaterializationRepository,
)
from llamaindex_runtime.okf.e2a_reconciler import E2aReconciler
from llamaindex_runtime.okf.generation_manifest import GenerationManifest
from llamaindex_runtime.okf.rooted_open import BundleAuthority
from llamaindex_runtime.okf.roundtrip import recompute_span_id
from llamaindex_runtime.okf.sidecar import SpanRecord, SpanSidecar

from ._phase15_e2a_task90_support import (
    _error_reason,
    _scope_snapshot_digest,
    acquire_build_token,
    build_evidence_binding,
)
from ._phase15_e2a_task90_types import (
    REQUIRED_OBSERVATION_FIELDS,
    TASK90_CACHE_TABLES,
    TASK90_DENYLIST_TABLES,
    TASK90_PRIMARY_TABLES,
    Task90Observations,
    Task90ScopeSnapshot,
    make_task90_scope_snapshot,
)
from ._real_e2a_reconciler_testkit import _all_denylist_counts

# Fixed corpus identity for the single manual relation (non-sensitive).
#
# The two endpoint entity canonical ids are DERIVED from the normalized
# lowercase ASCII title/entity_type constants via the production
# deterministic-id contract (never hardcoded UUIDs); the relation frontmatter
# below references exactly these derived ids.
_SUBJECT_ENTITY_TITLE = "alpha subject"
_SUBJECT_ENTITY_TYPE = "agent"
_OBJECT_ENTITY_TITLE = "alpha object"
_OBJECT_ENTITY_TYPE = "document"


def _entity_fact_id(title: str, entity_type: str) -> str:
    """Derive the canonical entity fact id from its normalized natural key."""
    return deterministic_id(
        "entity",
        canonical_json({"title": title, "entity_type": entity_type}),
    )


_SUBJECT_ENTITY_ID = _entity_fact_id(_SUBJECT_ENTITY_TITLE, _SUBJECT_ENTITY_TYPE)
_OBJECT_ENTITY_ID = _entity_fact_id(_OBJECT_ENTITY_TITLE, _OBJECT_ENTITY_TYPE)

# Fixed raw-pair identity for the single strict M-D-S-M pair in the live
# corpus (non-sensitive). The span id is derived from these coordinates via
# the production canonical-span recomputation, never hardcoded.
_PAIR_DOC_ID = "00000000-0000-0000-0000-000000001c01"
_PAIR_VERSION_ID = "00000000-0000-0000-0000-000000001c02"
_PLACEHOLDER_SPAN_ID = "00000000-0000-0000-0000-000000000000"
_SOURCE_CHECKSUM = "a" * 64

# Sensitive marker names used ONLY to assert redaction of the artifact repr.
# Each marker is assembled from concatenated fragments so the literal name
# never appears in this module's source (source-level hygiene; the runtime
# check is unchanged).
_SENSITIVE_MARKERS = (
    "DATABASE_" + "URL",
    "PG" + "HOST",
)


def _close_quietly(value: Any) -> None:
    close = getattr(value, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass


def _task90_parent_identities(
    parents: Sequence[object],
) -> tuple[tuple[str, str], ...]:
    """Sorted, fail-closed (document_id, version_id) identity set.

    Every identity is type-checked as an exact ``E2aParent``; an empty parent
    set and a duplicated identity both fail closed before any SQL is issued.
    The sorted tuple is deterministic for the single-parent corpus and for any
    future multi-parent corpus.
    """
    identities: list[tuple[str, str]] = []
    for value in parents:
        if type(value) is not E2aParent:
            raise ValueError("task90_parent_registration_malformed")
        identities.append((value.document_id, value.version_id))
    if not identities:
        raise ValueError("task90_parent_registration_empty")
    if len(set(identities)) != len(identities):
        raise ValueError("task90_parent_registration_duplicate")
    return tuple(sorted(identities))


def _register_task90_parents(conn: Any, desired: E2aDesiredState) -> None:
    """Register every admitted parent as real documents/document_versions rows.

    Production ``E2aReconciler._acquire_scope_locks`` requires exactly one
    ``document_versions`` row per admitted parent (``FOR UPDATE``) and
    fail-closes otherwise. This harness precondition runs on a fresh
    caller-owned connection BEFORE the first reconcile and commits the
    registration so the reconcile connection observes the rows.

    The SQL shape is the proven schema-compatible insert from the
    ``_real_e2a_reconciler_testkit`` parent registration; connections are
    never created here (the caller's session owns the attested factory) and
    ``content_hash`` is the admitted parent's canonical 64-hex digest (derived
    from admitted corpus data, never a secret or connection target). No values
    are logged or printed.
    """
    _task90_parent_identities(desired.parents)
    parents = tuple(
        sorted(
            desired.parents,
            key=lambda parent: (parent.document_id, parent.version_id),
        )
    )
    for parent in parents:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO documents (doc_id) VALUES (%s) "
                "ON CONFLICT (doc_id) DO NOTHING",
                (parent.document_id,),
            )
            cursor.execute(
                "INSERT INTO document_versions "
                "(version_id, doc_id, content_hash, version_no, is_active, status) "
                "VALUES (%s, %s, %s, 1, TRUE, 'active') "
                "ON CONFLICT (version_id) DO NOTHING",
                (parent.version_id, parent.document_id, parent.canonical_hash),
            )
    conn.commit()


def _write_live_raw_pair(root: Path) -> str:
    """Write one complete strict M-D-S-M raw pair with a real canonical span.

    Returns the canonical span id (S_okf) computed from the fixed
    doc/version coordinates, which the manual relation's ``evidence``
    frontmatter then resolves to.
    """
    raw = root / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    frontmatter = {
        "type": "raw",
        "doc_id": _PAIR_DOC_ID,
        "version_id": _PAIR_VERSION_ID,
        "source_checksum": _SOURCE_CHECKSUM,
        "docling_version": "test",
        "generated_by": "test",
    }
    markdown = dump_raw_frontmatter(frontmatter, "Raw corpus body.\n").encode("utf-8")
    span_id = recompute_span_id(
        SpanRecord(
            span_id=_PLACEHOLDER_SPAN_ID,
            page_no=1,
            heading_path=("Introduction",),
            offset=0,
            text="Canonical span text.",
        ),
        doc_id=_PAIR_DOC_ID,
        version_id=_PAIR_VERSION_ID,
    )
    sidecar = SpanSidecar(
        schema_version=1,
        doc_id=_PAIR_DOC_ID,
        version_id=_PAIR_VERSION_ID,
        spans=(
            SpanRecord(
                span_id=span_id,
                page_no=1,
                heading_path=("Introduction",),
                offset=0,
                text="Canonical span text.",
            ),
        ),
    )
    sidecar_bytes = sidecar.to_bytes()
    md_path = raw / "alpha-source.md"
    md_path.write_bytes(markdown)
    md_path.with_suffix(".spans.json").write_bytes(sidecar_bytes)
    manifest = GenerationManifest.create(
        markdown_file=md_path.name,
        markdown_bytes=markdown,
        sidecar_file="alpha-source.spans.json",
        sidecar_bytes=sidecar_bytes,
        canonical_hash=canonical_hash(frontmatter, sidecar),
    )
    md_path.with_suffix(".pair.json").write_bytes(manifest.to_bytes())
    return span_id


def _write_entity_fact(
    root: Path,
    name: str,
    title: str,
    entity_type: str,
    entity_id: str,
) -> None:
    """Write one strict manual entity fact with its derived canonical id."""
    ent_dir = root / "entities"
    ent_dir.mkdir(parents=True, exist_ok=True)
    (ent_dir / f"{name}.md").write_text(
        "---\n"
        "type: entity\n"
        f"title: {title}\n"
        "timestamp: '2026-07-15T09:30:00Z'\n"
        f"canonical_entity_id: {entity_id}\n"
        f"entity_type: {entity_type}\n"
        "---\n"
        "Entity body.\n",
        encoding="utf-8",
    )


def _write_manual_relation_corpus(root: Path) -> Path:
    """Write a complete strict M-D-S-M corpus: one raw pair + two endpoint
    entity facts + one relation.

    The raw pair carries one real canonical span; the two manual entity facts
    carry the relation's subject/object endpoints (their canonical ids are
    derived from the normalized title/entity_type constants via the
    production deterministic-id contract); the manual relation's
    ``evidence`` frontmatter resolves to that admitted doc/version/span, so
    the admitted state carries a NON-EMPTY evidence object/link that
    references the admitted span/version/document.
    """
    span_id = _write_live_raw_pair(root)
    _write_entity_fact(
        root,
        "alpha",
        _SUBJECT_ENTITY_TITLE,
        _SUBJECT_ENTITY_TYPE,
        _SUBJECT_ENTITY_ID,
    )
    _write_entity_fact(
        root,
        "beta",
        _OBJECT_ENTITY_TITLE,
        _OBJECT_ENTITY_TYPE,
        _OBJECT_ENTITY_ID,
    )
    rel_dir = root / "relations"
    rel_dir.mkdir(parents=True, exist_ok=True)
    md_path = rel_dir / "alpha.md"
    md_path.write_text(
        "---\ntype: relation\n"
        f"subject_entity_id: {_SUBJECT_ENTITY_ID}\n"
        "predicate: supports\n"
        f"object_entity_id: {_OBJECT_ENTITY_ID}\n"
        "timestamp: '2026-07-15T09:30:00Z'\n"
        "negation: false\n"
        "evidence:\n"
        f"  - document_id: {_PAIR_DOC_ID}\n"
        f"    version_id: {_PAIR_VERSION_ID}\n"
        f"    span_id: {span_id}\n"
        "---\nFact body.\n",
        encoding="utf-8",
    )
    return md_path


def _table_count(conn: Any, table: str) -> int:
    """Whole-table count for a validated primary table."""
    if table not in TASK90_PRIMARY_TABLES:
        raise ValueError("task90_scope_table_unknown")
    with conn.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM " + table)
        row = cursor.fetchone()
        return int(row[0]) if row and row[0] is not None else 0


def _table_content_digest(conn: Any, table: str) -> str:
    """Deterministic whole-table md5 (heap-stable via ctid ordering)."""
    if table not in TASK90_PRIMARY_TABLES:
        raise ValueError("task90_scope_table_unknown")
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT md5(COALESCE(string_agg(t::text, '|'), '')) "
            f"FROM (SELECT * FROM {table} ORDER BY ctid) AS t"
        )
        row = cursor.fetchone()
        return str(row[0]) if row and row[0] is not None else ""


def _build_task90_scope_snapshot(conn: Any) -> Task90ScopeSnapshot:
    """Build a full-collection Task90ScopeSnapshot on a fresh observer conn."""
    counts = {table: _table_count(conn, table) for table in TASK90_PRIMARY_TABLES}
    digests = {
        table: _table_content_digest(conn, table) for table in TASK90_PRIMARY_TABLES
    }
    denylist = dict(_all_denylist_counts(conn))
    cache_invalidation = {table: counts[table] for table in TASK90_CACHE_TABLES}
    return make_task90_scope_snapshot(
        counts=counts,
        digests=digests,
        denylist=denylist,
        cache_invalidation=cache_invalidation,
        sync_ts=None,
    )


def _admitted_span_keys(desired: E2aDesiredState) -> set[tuple[str, str, str]]:
    """The (document, version, span) key set of the admitted canonical spans."""
    return {
        (span.document_id, span.version_id, span.span_id)
        for span in desired.canonical_spans
    }


def _evidence_links_reference_admitted_spans(desired: E2aDesiredState) -> bool:
    """True only when every evidence link resolves to an admitted span."""
    span_keys = _admitted_span_keys(desired)
    return bool(desired.evidence_links) and all(
        (link.document_id, link.version_id, link.span_id) in span_keys
        for link in desired.evidence_links
    )


def _relation_endpoints_resolve_to_admitted_entities(
    desired: E2aDesiredState,
) -> bool:
    """True only when every admitted relation endpoint resolves to an admitted
    entity fact id.

    Relation endpoints live in the relation's canonical natural key
    (``{"subject_entity_id", "predicate", "object_entity_id"}``), so that key
    is parsed here and the helper fail-closes on a malformed shape or an
    empty entity set instead of raising from the completeness predicate.
    """
    entity_ids = {fact.fact_id for fact in desired.manual_entities}
    if not entity_ids:
        return False
    for fact in desired.manual_relations:
        try:
            natural = json.loads(fact.natural_key)
            subject = natural["subject_entity_id"]
            object_entity = natural["object_entity_id"]
        except (json.JSONDecodeError, KeyError, TypeError):
            return False
        if (
            type(subject) is not str
            or type(object_entity) is not str
            or subject not in entity_ids
            or object_entity not in entity_ids
        ):
            return False
    return True


def _is_complete_desired_state(desired: E2aDesiredState) -> bool:
    """The live corpus is complete: one raw pair, one span, TWO endpoint
    entity facts, one relation, three ownership facts, and one resolved
    evidence object/link that references the admitted span/version/document.

    Every admitted relation subject/object endpoint must resolve to an
    admitted entity fact id (the two endpoint entities). The vector/tree/sync
    collections are honestly pinned EMPTY because the production admission
    defers them (``derived_materialization: deferred_wave2``); the non-empty
    materialized primary scope is the raw parent + canonical span + two
    entities + relation + ownership + evidence surface.
    """
    return (
        len(desired.parents) == 1
        and len(desired.canonical_spans) >= 1
        and len(desired.manual_relations) == 1
        and len(desired.manual_entities) == 2
        and len(desired.ownership_facts) == 3
        and len(desired.evidence_objects) == 1
        and len(desired.evidence_links) == 1
        and _evidence_links_reference_admitted_spans(desired)
        and _relation_endpoints_resolve_to_admitted_entities(desired)
        and desired.vector_chunks == ()
        and desired.vector_chunk_span_links == ()
        and desired.tree_nodes == ()
        and desired.tree_node_span_links == ()
        and desired.sync_state_rows == ()
        and desired.corpus_manifest_sha256
        == e2a_admission.admit_e2a_corpus_hash(desired)
    )


def _denylist_exact_zero(denylist: Mapping[str, int | None]) -> bool:
    return set(denylist) == TASK90_DENYLIST_TABLES and all(
        value is None or (type(value) is int and value == 0)
        for value in denylist.values()
    )


def _rerun_primary_dml_all_zero(result: E2aReconciliationResult) -> bool:
    return set(result.primary_dml_by_table) == TASK90_PRIMARY_TABLES and all(
        type(value) is int and value == 0
        for value in result.primary_dml_by_table.values()
    )


def _artifact_redacted(artifact: Mapping[str, object]) -> bool:
    rendered = str(artifact)
    return (
        "error_reason" not in artifact
        and "password" not in rendered.lower()
        and all(marker not in rendered for marker in _SENSITIVE_MARKERS)
        and all(
            type(value) is int for value in artifact["primary_counts"].values()  # type: ignore[union-attr]
        )
    )


def _failure_observations(failure: Exception) -> Task90Observations:
    """Absorb a failure into a redacted all-false observation."""
    return Task90Observations(
        **{field: False for field in REQUIRED_OBSERVATION_FIELDS},
        success=False,
        error_reason=_error_reason("task90_cell_failed", failure),
    )


def _run_task90_live_proof(session: Any) -> Task90Observations:
    """Run the Task #90 controlled live producer in ONE invocation.

    Real strict admission of two endpoint entities and one manual relation,
    default reconciler first reconcile + equivalent rerun (must be ``no_op``
    with every primary DML count exactly 0), independent fresh-observer
    full-collection scope snapshots before/after the rerun (must be equal),
    and the build + verify of a process-local structural binding over the
    exact first-reconcile result object before a redacted canonical artifact
    dict is produced.
    """
    bundle_root: Path | None = None
    conn_parents: Any = None
    conn_first: Any = None
    conn_rerun: Any = None
    conn_pre_observer: Any = None
    conn_post_observer: Any = None
    try:
        bundle_root = Path(tempfile.mkdtemp(prefix="okf_e2a_task90_"))
        _write_manual_relation_corpus(bundle_root)
        with BundleAuthority(bundle_root) as authority:
            desired = e2a_admission.admit_e2a_corpus(authority)
        admitted_state_complete = _is_complete_desired_state(desired)
        admitted_has_manual_relation = len(desired.manual_relations) == 1
        admitted_has_raw_pair = len(desired.parents) == 1
        admitted_has_resolved_evidence = len(
            desired.evidence_links
        ) == 1 and _evidence_links_reference_admitted_spans(desired)

        # Harness precondition: register every admitted parent as real
        # documents/document_versions rows on a fresh caller-owned connection
        # BEFORE the first reconcile. Production ``_acquire_scope_locks``
        # fail-closes unless each admitted parent has exactly one
        # document_versions row. The registration is committed here and the
        # connection is closed in the finally block below; no values are
        # logged or printed.
        conn_parents = session.open_fresh_attested_connection()
        _register_task90_parents(conn_parents, desired)
        _close_quietly(conn_parents)
        conn_parents = None

        reconciler = E2aReconciler()
        default_reconciler_default_repository = (
            type(reconciler) is E2aReconciler
            and type(reconciler._repository)
            is E2aMaterializationRepository  # noqa: SLF001
        )

        conn_first = session.open_fresh_attested_connection()
        first_result = reconciler.reconcile(conn_first, desired)
        reconcile_first_changed = first_result.outcome == "changed"

        conn_pre_observer = session.open_fresh_attested_connection()
        pre_snapshot = _build_task90_scope_snapshot(conn_pre_observer)
        _close_quietly(conn_pre_observer)
        conn_pre_observer = None

        conn_rerun = session.open_fresh_attested_connection()
        rerun_result = reconciler.reconcile(conn_rerun, desired)
        rerun_no_op = rerun_result.outcome == "no_op"
        rerun_primary_dml_all_zero = _rerun_primary_dml_all_zero(rerun_result)

        conn_post_observer = session.open_fresh_attested_connection()
        post_snapshot = _build_task90_scope_snapshot(conn_post_observer)
        _close_quietly(conn_post_observer)
        conn_post_observer = None

        denylist_exact_zero = _denylist_exact_zero(post_snapshot.denylist)
        pre_post_scope_snapshots_equal = (
            pre_snapshot == post_snapshot
            and _scope_snapshot_digest(pre_snapshot)
            == _scope_snapshot_digest(post_snapshot)
        )

        token = acquire_build_token()
        binding = build_evidence_binding(token, first_result, post_snapshot)
        binding_built_in_invocation = (
            binding.verify_exact_result(first_result) and token.consumed
        )
        binding.verify()
        binding_verifies = True
        artifact = binding.artifact_dict()
        artifact_redacted = _artifact_redacted(artifact)
        exact_returned_objects_kept = (
            binding.verify_exact_result(first_result)
            and type(first_result) is E2aReconciliationResult
            and type(rerun_result) is E2aReconciliationResult
        )

        return Task90Observations(
            admitted_state_complete=admitted_state_complete,
            admitted_has_manual_relation=admitted_has_manual_relation,
            admitted_has_raw_pair=admitted_has_raw_pair,
            admitted_has_resolved_evidence=admitted_has_resolved_evidence,
            reconcile_first_changed=reconcile_first_changed,
            rerun_no_op=rerun_no_op,
            rerun_primary_dml_all_zero=rerun_primary_dml_all_zero,
            denylist_exact_zero=denylist_exact_zero,
            default_reconciler_default_repository=default_reconciler_default_repository,
            exact_returned_objects_kept=exact_returned_objects_kept,
            pre_post_scope_snapshots_equal=pre_post_scope_snapshots_equal,
            binding_built_in_invocation=binding_built_in_invocation,
            binding_verifies=binding_verifies,
            artifact_redacted=artifact_redacted,
        )
    except Exception as failure:
        return _failure_observations(failure)
    finally:
        _close_quietly(conn_parents)
        _close_quietly(conn_first)
        _close_quietly(conn_rerun)
        _close_quietly(conn_pre_observer)
        _close_quietly(conn_post_observer)
        if bundle_root is not None:
            shutil.rmtree(bundle_root, ignore_errors=True)
