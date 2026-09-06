"""Live cells for the Phase 15 E2A Task #88 foundation tranche.

This helper module is never collected by default test name discovery (the
``_`` prefix keeps it out of normal test collection). It provides the shared
cells for the explicitly selected live foundation selector:

- C13 cell: real parent registration via PostgresRegistryWriter over a
  temporary source file, plus provenance observation on a separate fresh
  connection (registration only; no reconcile in this cell).
- C1 cell: full E2a reconcile of one registered parent through the default
  repository, with issued-statement primary counts, the ten-key zero denylist
  map, manifest hash match, and durable observer state.
- C11 cell: catalog-limited denylist boundary with count observations on the
  five catalog-present denylist tables before and after a foundation
  reconcile, and information_schema catalog queries for the five absent
  names; the observer transaction is reset between the before and after
  count reads so the post-reconcile observation is isolation-level
  independent.

Security contract:

- No environment variable access of any kind; no DATABASE_URL anywhere.
- No URI, credential, target, container token, or raw fixture content is
  ever printed, logged, returned, or included in observation reprs.
- All connections come from DisposableE2aSession.open_fresh_attested_connection.
- Every cursor and connection is closed in a finally block; the reconciler
  primary connection is closed there too, so a reconcile failure before the
  reconciler's own cleanup cannot leak it (the close is idempotent after a
  successful reconcile).
- Failures are absorbed into redacted observations that carry a bounded
  class/type-only diagnostic; exception messages, args, and reprs never
  leave the helper.
- No test framework machinery, no skip or xfail mechanics.
"""

from __future__ import annotations

import hashlib
import secrets
import socket
import tempfile
import uuid
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any, NamedTuple

_SOURCE_FIXTURE_TEXT = (
    "Live E2A foundation source fixture. "
    "This text is registered through the real registry writer."
)
_SOURCE_RELATIVE_PATH = "e2a-foundation/source.txt"
_SOURCE_URI = "https://okf.local/e2a-foundation/source.txt"
_FIXTURE_TITLE = "Live Foundation Source"

_C11_PRESENT_TABLES = (
    "chunk_entity_links",
    "node_entity_links",
    "entity_aliases",
    "entity_mentions",
    "entity_merge_log",
)
_C11_ABSENT_TABLES = (
    "ner_entities",
    "ner_relations",
    "fusion_state",
    "r3_state",
    "external_projection_status",
)

_DENYLIST_TABLE_NAMES = frozenset(_C11_PRESENT_TABLES + _C11_ABSENT_TABLES)
_PRIMARY_TABLE_NAMES = frozenset(
    {
        "canonical_spans",
        "vector_chunks",
        "vector_chunk_spans",
        "tree_nodes",
        "tree_node_spans",
        "entities",
        "relations",
        "evidence",
        "evidence_links",
        "okf_manual_fact_ownership",
        "okf_manual_evidence_targets",
        "okf_sync_state",
        "summaries",
        "node_embeddings",
        "semantic_distribution",
    }
)


class C13Observations(NamedTuple):
    """Redacted observations for the C13 registration cell."""

    registered: bool
    provenance_matches: bool
    version_singleton: bool
    success: bool = True
    error_reason: str = ""

    def __repr__(self) -> str:
        return (
            "C13Observations(registered="
            + repr(self.registered)
            + ", provenance_matches="
            + repr(self.provenance_matches)
            + ", version_singleton="
            + repr(self.version_singleton)
            + ", success="
            + repr(self.success)
            + ", details=<redacted>)"
        )


class C1Observations(NamedTuple):
    """Redacted observations for the C1 reconcile cell."""

    outcome: str
    manifest_sha256_match: bool
    primary_shape_valid: bool
    denylist_zeros_valid: bool
    observer_durable: bool
    primary_issued_counts: Mapping[str, int]
    success: bool = True
    error_reason: str = ""

    def __repr__(self) -> str:
        return (
            "C1Observations(outcome="
            + repr(self.outcome)
            + ", manifest_sha256_match="
            + repr(self.manifest_sha256_match)
            + ", primary_shape_valid="
            + repr(self.primary_shape_valid)
            + ", denylist_zeros_valid="
            + repr(self.denylist_zeros_valid)
            + ", observer_durable="
            + repr(self.observer_durable)
            + ", counts=<redacted>, success="
            + repr(self.success)
            + ")"
        )


class C11Observations(NamedTuple):
    """Redacted observations for the C11 catalog-limited cell."""

    present_before: Mapping[str, int]
    present_after: Mapping[str, int]
    absent_catalog_flags: Mapping[str, bool]
    ten_zero_map: Mapping[str, int]
    unchanged_valid: bool
    success: bool = True
    error_reason: str = ""

    def __repr__(self) -> str:
        return (
            "C11Observations(unchanged_valid="
            + repr(self.unchanged_valid)
            + ", counts=<redacted>, flags=<redacted>, success="
            + repr(self.success)
            + ")"
        )


def _close_quietly(value: Any) -> None:
    """Close a resource in a finally path without masking an in-flight error."""
    if value is None:
        return
    try:
        value.close()
    except Exception:
        pass


def _error_reason(prefix: str, failure: Exception) -> str:
    """Bounded class/type-only diagnostic; never message, args, or repr."""
    error_type = type(failure).__name__
    return f"{prefix}:{error_type[:64]}"


def _generate_safe_container_name() -> str:
    """Generate a unique safe container name for test isolation."""
    random_hex = secrets.token_hex(8)
    return f"e2a-foundation-{random_hex}"


def _generate_test_password() -> str:
    """Generate a random test-only password (hex alphabet, env-file safe)."""
    return secrets.token_hex(24)


def _select_ephemeral_port() -> str:
    """Bind 127.0.0.1:0, read the assigned port, close, and return it.

    No SO_REUSEADDR, no fixed host port, no retry; if the port is claimed
    afterwards the test must fail rather than mask it.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        return str(port)


def _create_source_fixture() -> Path:
    """Create a temporary source file for registration.

    The caller must unlink the returned path in a finally block. Raw fixture
    contents never leave this frame.
    """
    handle = tempfile.NamedTemporaryFile(
        prefix="okf_e2a_foundation_", suffix=".txt", delete=False
    )
    path = Path(handle.name)
    try:
        handle.write(_SOURCE_FIXTURE_TEXT.encode("utf-8"))
        handle.flush()
    finally:
        handle.close()
    return path


def _file_sha256(path: Path) -> str:
    """Compute the lowercase SHA-256 digest of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _open_writer_connection(session: Any) -> Any:
    """Open the registry-writer role; the writer forces autocommit=True."""
    return session.open_fresh_attested_connection()


def _open_reconciler_primary_connection(session: Any) -> Any:
    """Open the reconciler primary role; it stays autocommit False by contract."""
    return session.open_fresh_attested_connection()


def _open_observer_connection(session: Any) -> Any:
    """Open the observer role on a separate fresh connection."""
    return session.open_fresh_attested_connection()


def _build_foundation_desired_state(registration: Any, source_path: Path) -> Any:
    """Build the single-parent foundation desired state from a real registration.

    All downstream identifiers derive deterministically from the runtime
    registration ids; no document or version is ever manually seeded.
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

    document_id = str(registration.doc_id)
    version_id = str(registration.version_id)
    file_sha256 = _file_sha256(source_path)
    span_id = str(uuid.uuid4())
    node_id = str(uuid.uuid4())
    chunk_id = str(uuid.uuid4())
    span_text = _SOURCE_FIXTURE_TEXT

    natural_key = canonical_json({"entity_type": "concept", "title": "Live Foundation"})
    entity = E2aManualFact(
        deterministic_id("entity", natural_key),
        "entity",
        _SOURCE_RELATIVE_PATH,
        file_sha256,
        {},
        natural_key,
    )
    ownership = E2aOwnershipFact.create(
        relative_path=_SOURCE_RELATIVE_PATH,
        fact_kind="entity",
        fact_id=entity.fact_id,
        source_digest=file_sha256,
        document_id=document_id,
        version_id=version_id,
    )
    evidence = E2aEvidenceObject.create(
        version_id=version_id, entity_id=entity.fact_id, relation_id=None
    )

    parent = E2aParent(document_id, version_id, _SOURCE_RELATIVE_PATH, file_sha256)
    span = E2aSpan(document_id, version_id, span_id, 0, span_text)

    node = {
        "node_id": node_id,
        "version_id": version_id,
        "parent_node_id": None,
        "node_type": "section",
        "level_no": 1,
        "title": "Live Foundation Section",
        "heading_path": "/e2a-foundation",
        "page_start": 1,
        "page_end": 1,
        "summary_text": "Foundation tree node summary.",
    }
    node_link = {"node_id": node_id, "span_id": span_id, "ordinal_no": 0}

    chunk = {
        "chunk_id": chunk_id,
        "version_id": version_id,
        "chunk_type": "text",
        "chunk_order": 0,
        "token_count": len(span_text.split()),
        "text_preview": span_text,
        "page_no": 1,
        "heading_path": "/e2a-foundation",
        "node_id": node_id,
        "embedding": tuple(float(index) for index in range(16)),
    }
    chunk_link = {"chunk_id": chunk_id, "span_id": span_id, "ordinal_no": 0}

    sync_row = {
        "okf_file_path": _SOURCE_RELATIVE_PATH,
        "doc_id": document_id,
        "version_id": version_id,
        "source_checksum": file_sha256,
        "canonical_hash": file_sha256,
        "status": "materialized",
        "materialization_owner": "e2a",
    }

    manifest = {
        "artifacts": [
            {
                "kind": "raw_pair",
                "path": _SOURCE_RELATIVE_PATH,
                "identity": f"{document_id}:{version_id}",
                "canonical_hash": file_sha256,
            },
            {
                "kind": "entity",
                "path": _SOURCE_RELATIVE_PATH,
                "identity": entity.fact_id,
                "source_digest": file_sha256,
            },
        ]
    }

    evidence_link = E2aEvidenceReference(
        document_id,
        version_id,
        span_id,
        entity.fact_id,
        None,
        evidence.evidence_id,
        ownership.ownership_id,
        ownership.scope_version_id,
    )

    return E2aDesiredState(
        manifest,
        canonical_json_sha256(manifest),
        (parent,),
        (span,),
        (chunk,),
        (chunk_link,),
        (node,),
        (node_link,),
        (entity,),
        (),
        (evidence,),
        (evidence_link,),
        (ownership,),
        (sync_row,),
        MappingProxyType({}),
        MappingProxyType({"authority": "okf"}),
    )


def _validate_c1_result_shape(result: Any) -> bool:
    """Validate the result shape without asserting exact statement counts."""
    from llamaindex_runtime.okf.e2a_contracts import E2aReconciliationResult

    if type(result) is not E2aReconciliationResult:
        return False
    if result.outcome not in {"changed", "no_op"}:
        return False
    if result.reconciliation_required is not False:
        return False
    if result.failure_audit_outcome is not None:
        return False
    if result.post_rollback_failure_audit_outcome is not None:
        return False
    if (
        result.comparator_parity is not None
        and type(result.comparator_parity) is not bool
    ):
        return False
    if set(result.primary_dml_by_table) != _PRIMARY_TABLE_NAMES:
        return False
    if any(
        type(value) is not int or value < 0
        for value in result.primary_dml_by_table.values()
    ):
        return False
    if set(result.denylist_dml_counts) != _DENYLIST_TABLE_NAMES:
        return False
    if any(value != 0 for value in result.denylist_dml_counts.values()):
        return False
    return True


def _verify_durable_state(cursor: Any, registration: Any, desired: Any) -> bool:
    """Verify the materialized state on the observer connection."""
    version_id = str(registration.version_id)
    checks: list[bool] = []

    cursor.execute(
        "SELECT COUNT(*) FROM canonical_spans WHERE version_id = %s",
        (version_id,),
    )
    checks.append(cursor.fetchone() == (1,))

    cursor.execute(
        "SELECT COUNT(*) FROM vector_chunks WHERE version_id = %s",
        (version_id,),
    )
    checks.append(cursor.fetchone() == (1,))

    cursor.execute(
        "SELECT COUNT(*) FROM tree_nodes WHERE version_id = %s",
        (version_id,),
    )
    checks.append(cursor.fetchone() == (1,))

    entity = desired.manual_entities[0]
    cursor.execute(
        "SELECT COUNT(*) FROM entities WHERE entity_id = %s",
        (entity.fact_id,),
    )
    checks.append(cursor.fetchone() == (1,))

    evidence = desired.evidence_objects[0]
    cursor.execute(
        "SELECT COUNT(*) FROM evidence WHERE evidence_id = %s",
        (evidence.evidence_id,),
    )
    checks.append(cursor.fetchone() == (1,))

    link = desired.evidence_links[0]
    cursor.execute(
        "SELECT COUNT(*) FROM evidence_links WHERE evidence_link_id = %s",
        (link.evidence_link_id,),
    )
    checks.append(cursor.fetchone() == (1,))

    ownership = desired.ownership_facts[0]
    cursor.execute(
        "SELECT COUNT(*) FROM okf_manual_fact_ownership WHERE ownership_id = %s",
        (ownership.ownership_id,),
    )
    checks.append(cursor.fetchone() == (1,))

    cursor.execute(
        "SELECT COUNT(*) FROM okf_manual_evidence_targets WHERE version_id = %s",
        (version_id,),
    )
    checks.append(cursor.fetchone() == (1,))

    cursor.execute(
        "SELECT materialization_owner FROM okf_sync_state WHERE okf_file_path = %s",
        (_SOURCE_RELATIVE_PATH,),
    )
    owner_row = cursor.fetchone()
    checks.append(owner_row is not None and owner_row[0] == "e2a")

    return all(checks)


def _denylist_present_counts(cursor: Any) -> dict[str, int]:
    """Observe count rows on the five catalog-present tables."""
    counts: dict[str, int] = {}
    for table in _C11_PRESENT_TABLES:
        cursor.execute("SELECT COUNT(*) FROM " + table)
        row = cursor.fetchone()
        if row is None or type(row[0]) is not int:
            raise RuntimeError("denylist count observation failed")
        counts[table] = row[0]
    return counts


def _catalog_absent_flags(cursor: Any) -> dict[str, bool]:
    """Confirm the five absent names only through the information_schema catalog."""
    flags: dict[str, bool] = {}
    for table in _C11_ABSENT_TABLES:
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = %s",
            (table,),
        )
        flags[table] = cursor.fetchone() == (0,)
    return flags


def _run_c13_impl(session: Any) -> C13Observations:
    """Run the C13 registration and provenance cell (no reconcile).

    Absorbs all failures into a redacted observation; no URI, credentials,
    fixture contents, connections, or cursors escape this frame.
    """
    from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

    source_path: Path | None = None
    writer_conn: Any = None
    observer_conn: Any = None
    cursor: Any = None
    try:
        source_path = _create_source_fixture()
        writer_conn = _open_writer_connection(session)
        writer = PostgresRegistryWriter(writer_conn)
        registration = writer.register_document(
            source_path=source_path,
            source_uri=_SOURCE_URI,
            title=_FIXTURE_TITLE,
        )
        document_id = str(registration.doc_id)
        version_id = str(registration.version_id)
        expected_sha256 = _file_sha256(source_path)

        observer_conn = _open_observer_connection(session)
        cursor = observer_conn.cursor()
        cursor.execute(
            "SELECT doc_id, source_uri, title FROM documents WHERE doc_id = %s",
            (document_id,),
        )
        document_row = cursor.fetchone()
        document_ok = (
            document_row is not None
            and str(document_row[0]) == document_id
            and document_row[2] == _FIXTURE_TITLE
        )
        cursor.execute(
            "SELECT version_id, version_no, is_active, status, content_hash, "
            "processing_status FROM document_versions WHERE version_id = %s",
            (version_id,),
        )
        version_row = cursor.fetchone()
        version_ok = (
            version_row is not None
            and str(version_row[0]) == version_id
            and version_row[1] == 1
            and version_row[2] is True
            and version_row[3] == "active"
            and version_row[4] == expected_sha256
            and version_row[5] == "registered"
        )
        cursor.execute(
            "SELECT COUNT(*) FROM document_versions WHERE doc_id = %s",
            (document_id,),
        )
        singleton_ok = cursor.fetchone() == (1,)
        return C13Observations(
            registered=True,
            provenance_matches=document_ok and version_ok,
            version_singleton=singleton_ok,
            success=True,
        )
    except Exception as failure:
        return C13Observations(
            registered=False,
            provenance_matches=False,
            version_singleton=False,
            success=False,
            error_reason=_error_reason("c13_cell_failed", failure),
        )
    finally:
        _close_quietly(cursor)
        _close_quietly(observer_conn)
        _close_quietly(writer_conn)
        if source_path is not None:
            try:
                source_path.unlink()
            except Exception:
                pass


def _run_c1_reconcile_impl(session: Any) -> C1Observations:
    """Run the C1 full-reconcile cell for one registered parent.

    The reconciler closes its primary connection on success; this frame also
    closes it in a finally path so a failure before the reconciler's internal
    cleanup cannot leak it. Absorbs failures into a redacted observation.
    """
    from llamaindex_runtime.okf.e2a_reconciler import E2aReconciler
    from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

    source_path: Path | None = None
    writer_conn: Any = None
    observer_conn: Any = None
    observer_cursor: Any = None
    primary_conn: Any = None
    try:
        source_path = _create_source_fixture()
        writer_conn = _open_writer_connection(session)
        registration = PostgresRegistryWriter(writer_conn).register_document(
            source_path=source_path,
            source_uri=_SOURCE_URI,
            title=_FIXTURE_TITLE,
        )

        desired = _build_foundation_desired_state(registration, source_path)

        primary_conn = _open_reconciler_primary_connection(session)
        result = E2aReconciler().reconcile(primary_conn, desired)

        shape_valid = _validate_c1_result_shape(result)
        manifest_match = result.manifest_sha256 == desired.corpus_manifest_sha256
        denylist_zeros = all(
            value == 0 for value in result.denylist_dml_counts.values()
        )

        observer_conn = _open_observer_connection(session)
        observer_cursor = observer_conn.cursor()
        durable = _verify_durable_state(observer_cursor, registration, desired)

        return C1Observations(
            outcome=result.outcome,
            manifest_sha256_match=manifest_match,
            primary_shape_valid=shape_valid,
            denylist_zeros_valid=denylist_zeros,
            observer_durable=durable,
            primary_issued_counts=MappingProxyType(dict(result.primary_dml_by_table)),
            success=True,
        )
    except Exception as failure:
        return C1Observations(
            outcome="",
            manifest_sha256_match=False,
            primary_shape_valid=False,
            denylist_zeros_valid=False,
            observer_durable=False,
            primary_issued_counts=MappingProxyType({}),
            success=False,
            error_reason=_error_reason("c1_reconcile_failed", failure),
        )
    finally:
        _close_quietly(observer_cursor)
        _close_quietly(observer_conn)
        _close_quietly(writer_conn)
        _close_quietly(primary_conn)
        if source_path is not None:
            try:
                source_path.unlink()
            except Exception:
                pass


def _run_c11_impl(session: Any) -> C11Observations:
    """Run the C11 catalog-limited denylist boundary cell.

    The five absent names are never queried as tables; they are confirmed
    only through the information_schema catalog. The ten-key zero map is
    copied from the reconciler's actual ``denylist_dml_counts`` result.
    The observer transaction is reset (read-only rollback, no DML/DDL)
    between the before and after count reads, so the post-reconcile
    observation is isolation-level independent of the pre-reconcile
    snapshot.
    """
    from llamaindex_runtime.okf.e2a_reconciler import E2aReconciler
    from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

    source_path: Path | None = None
    writer_conn: Any = None
    observer_conn: Any = None
    cursor: Any = None
    primary_conn: Any = None
    try:
        source_path = _create_source_fixture()
        writer_conn = _open_writer_connection(session)
        registration = PostgresRegistryWriter(writer_conn).register_document(
            source_path=source_path,
            source_uri=_SOURCE_URI,
            title=_FIXTURE_TITLE,
        )

        observer_conn = _open_observer_connection(session)
        cursor = observer_conn.cursor()
        before = _denylist_present_counts(cursor)
        absent_flags = _catalog_absent_flags(cursor)
        # End the pre-reconcile observer transaction (read-only rollback,
        # no DML/DDL) so the post-reconcile count read below opens a fresh
        # snapshot and is isolation-level independent.
        observer_conn.rollback()

        desired = _build_foundation_desired_state(registration, source_path)
        primary_conn = _open_reconciler_primary_connection(session)
        result = E2aReconciler().reconcile(primary_conn, desired)

        after = _denylist_present_counts(cursor)
        unchanged_valid = (
            before == after
            and all(value == 0 for value in after.values())
            and all(absent_flags.values())
        )
        ten_zero_map = MappingProxyType(dict(result.denylist_dml_counts))
        return C11Observations(
            present_before=MappingProxyType(dict(before)),
            present_after=MappingProxyType(dict(after)),
            absent_catalog_flags=MappingProxyType(dict(absent_flags)),
            ten_zero_map=ten_zero_map,
            unchanged_valid=unchanged_valid,
            success=True,
        )
    except Exception as failure:
        return C11Observations(
            present_before=MappingProxyType({}),
            present_after=MappingProxyType({}),
            absent_catalog_flags=MappingProxyType({}),
            ten_zero_map=MappingProxyType({}),
            unchanged_valid=False,
            success=False,
            error_reason=_error_reason("c11_cell_failed", failure),
        )
    finally:
        _close_quietly(cursor)
        _close_quietly(observer_conn)
        _close_quietly(writer_conn)
        _close_quietly(primary_conn)
        if source_path is not None:
            try:
                source_path.unlink()
            except Exception:
                pass
