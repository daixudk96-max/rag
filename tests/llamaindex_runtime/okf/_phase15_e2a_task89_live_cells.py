"""Live cells for the Phase 15 E2A Task #89 durable-integration slice.

Non-collected (underscore prefix) support for the selected live acceptance
selector ``phase15_e2a_task89_live_acceptance``; never collected by default
pytest discovery. The core live helper is split into named stage helpers
(<50 lines each) and every instrumentation swap is scoped-restored on ALL
exit paths via ``_AttributeSwap`` + ``contextlib.ExitStack``.

Security contract: no environment reads, no connection target or secret
named, no URI/credential/target/corpus text in any repr, no test-framework
machinery, no fake/replacement of any production symbol; instrumentation
wrappers ALWAYS call the original and restore identity-exactly on every
exit path.
"""

from __future__ import annotations

import contextlib
import hashlib
import shutil
import tempfile
from pathlib import Path
from typing import Any

from llamaindex_runtime.ingestion.docling_ingestor import (
    DoclingConversionResult,
    DoclingIngestor,
)
from llamaindex_runtime.ingestion.pipeline import IngestionPipeline
from llamaindex_runtime.okf import e2a_admission
from llamaindex_runtime.okf import serializer
from llamaindex_runtime.okf._e2a_materialization_input import (
    E2aDesiredStateBuilder,
    E2aMaterializationInput,
)
from llamaindex_runtime.okf.e2a_contracts import E2aReconciliationResult
from llamaindex_runtime.okf.e2a_reconciler import E2aReconciler
from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter
from llamaindex_runtime.tree.pageindex_adapter import PageIndexTreeAdapter

from ._phase15_e2a_task88_live_cells import (
    _generate_safe_container_name as _generate_safe_container_name,
    _generate_test_password as _generate_test_password,
    _select_ephemeral_port as _select_ephemeral_port,
)
from ._phase15_e2a_task89_types import (
    REQUIRED_OBSERVATION_FIELDS,
    SMOKE_FAMILIES,
    Task89Observations,
)

from ._phase15_e2a_task89_support import (
    _VERIFICATION_MODULE_NAME as _VERIFICATION_MODULE_NAME,
    _close_quietly,
    _error_reason,
    _load_verification_module,
    _new_ingestor,
    _resolve_source_pdf,
)

# The 15 canonical E2a primary tables and the 10 denylist tables (the
# exact key sets of the production E2aReconciliationResult count maps,
# verified against e2a_materialization_repository in the contract suite).
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
# Denylist split mirrors Task88: five catalog-present tables whose rows are
# counted directly, and five catalog-absent tables proven only through the
# information_schema catalog (no DDL, no triggers).
_DENYLIST_PRESENT_TABLES = (
    "chunk_entity_links",
    "node_entity_links",
    "entity_aliases",
    "entity_mentions",
    "entity_merge_log",
)
_DENYLIST_ABSENT_TABLES = (
    "ner_entities",
    "ner_relations",
    "fusion_state",
    "r3_state",
    "external_projection_status",
)
_DENYLIST_TABLE_NAMES = frozenset(_DENYLIST_PRESENT_TABLES + _DENYLIST_ABSENT_TABLES)

# Every real PostgresRegistryWriter ``write_*`` method that the E2a route
# never invokes (E2a materializes through E2aMaterializationRepository over
# the reconciler's own cursor; the writer has no self.write_* call in the
# E2a path). Fail-fast traps guard exactly this set, and the trap-active
# proof covers every member.
_LEGACY_PERSISTENCE_METHODS = frozenset(
    {
        "write_spans",
        "write_tree",
        "write_node_embeddings",
        "write_semantic_distribution",
        "write_vector_chunks",
        "write_entities",
        "write_relations",
        "write_evidence_links",
        "write_evidence",
        "write_chunk_entity_links",
        "write_node_entity_links",
        "write_entity_type_schema",
        "write_relation_type_schema",
        "write_summaries",
    }
)

# Fixed message the fail-fast traps raise. It never echoes a credential,
# URI, target, or corpus text.
_LEGACY_TRAP_ERROR = "legacy_e2b_persistence_forbidden"

# Stable retrieval probe for the real PageIndex consumer (non-sensitive).
_RETRIEVAL_PROBE = "Task89 retrieval probe"


class _AttributeSwap:
    """Scoped owner-attribute swap with descriptor-aware restore.

    Records whether the attribute lived directly in ``owner.__dict__``. If
    it did, ``restore()`` writes the exact original object back via
    ``setattr`` (identity-exact); if it did not (e.g. an instance method
    resolved from the class descriptor), ``restore()`` uses ``delattr`` so
    the class descriptor lookup resumes with no instance shadow left
    behind. ``restore()`` is idempotent and, as a context manager, never
    masks an in-flight body exception.
    """

    def __init__(self, owner: Any, name: str, replacement: Any) -> None:
        self._owner = owner
        self._name = name
        self._had_instance_attr = name in owner.__dict__
        self._original = owner.__dict__[name] if self._had_instance_attr else None
        self._restored = False
        setattr(owner, name, replacement)

    def restore(self) -> None:
        if self._restored:
            return
        if self._had_instance_attr:
            setattr(self._owner, self._name, self._original)
        else:
            try:
                delattr(self._owner, self._name)
            except AttributeError:
                pass
        self._restored = True

    def __enter__(self) -> "_AttributeSwap":
        return self

    def __exit__(self, *exc_info: Any) -> bool:
        self.restore()
        return False


def _deterministic_embedding(value: str) -> tuple[float, ...]:
    """Deterministic finite 16-dimensional embedding for E2aDesiredStateBuilder.

    Pure and reproducible: the same input text always maps to the same tuple
    of 16 finite floats in a bounded range, exactly the shape the builder's
    span-chunk derivation requires.
    """
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return tuple(float((int(digest[index]) / 255.0) - 0.5) for index in range(16))


def _make_counting_wrapper(original: Any) -> tuple[Any, dict[str, Any]]:
    """Return (wrapper, state) where wrapper calls original and records counts.

    The wrapper ALWAYS invokes the original and returns its exact result; it
    only records call counts and the last result/arguments for observation.
    """
    state: dict[str, Any] = {
        "calls": 0,
        "last_result": None,
        "last_args": (),
        "last_kwargs": {},
    }

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        state["calls"] += 1
        result = original(*args, **kwargs)
        state["last_result"] = result
        state["last_args"] = args
        state["last_kwargs"] = kwargs
        return result

    return wrapper, state


def _legacy_trap(*args: Any, **kwargs: Any) -> Any:
    """Fail-fast trap installed on legacy/E2b persistence entry points.

    Raises the fixed non-echoing error if any legacy or E2b persistence
    route is ever reached during the Task #89 live proof. The E2a route
    never calls these methods, so the trap is never legitimately triggered.
    """
    raise RuntimeError(_LEGACY_TRAP_ERROR)


def _trap_raises_fixed(target: Any) -> bool:
    """Confirm a fail-fast trap raises exactly the fixed legacy-trap error."""
    try:
        target()
    except RuntimeError as failure:
        return str(failure) == _LEGACY_TRAP_ERROR
    return False


def _publish_exact_three(raw_dir: Path, version_str: str) -> bool:
    """Confirm the raw pair directory holds exactly the three pair members."""
    if not raw_dir.is_dir():
        return False
    names = {entry.name for entry in raw_dir.iterdir() if entry.is_file()}
    expected = {
        f"{version_str}.md",
        f"{version_str}.spans.json",
        f"{version_str}.pair.json",
    }
    return names == expected


def _verify_observer_durable(cursor: Any, version_id: Any, ingest_result: Any) -> bool:
    """Verify exact primary durable state on a fresh observer connection.

    Version-scoped tables are compared against the real ingested span count.
    ``entities``/``relations``/``evidence_links``/``okf_manual_fact_ownership``
    are GLOBAL tables: their whole-table zero assertion is the deliberate
    pristine-disposable-DB isolation proof, not a version-filtered claim.
    """
    version_str = str(version_id)
    expected_spans = len(ingest_result.spans)
    checks: list[bool] = []

    cursor.execute(
        "SELECT COUNT(*) FROM canonical_spans WHERE version_id = %s",
        (version_str,),
    )
    row = cursor.fetchone()
    checks.append(row is not None and row[0] == expected_spans)

    cursor.execute(
        "SELECT COUNT(*) FROM vector_chunks WHERE version_id = %s",
        (version_str,),
    )
    row = cursor.fetchone()
    checks.append(row is not None and row[0] == expected_spans)

    # vector_chunk_spans carries only chunk_id/span_id/ordinal_no (no
    # version_id column), so its version-scoped count must join through
    # vector_chunks exactly like the production
    # query_vector_chunk_spans_by_version SQL.
    cursor.execute(
        "SELECT COUNT(*) FROM vector_chunk_spans vcs "
        "JOIN vector_chunks vc ON vcs.chunk_id = vc.chunk_id "
        "WHERE vc.version_id = %s",
        (version_str,),
    )
    row = cursor.fetchone()
    checks.append(row is not None and row[0] == expected_spans)

    cursor.execute(
        "SELECT COUNT(*) FROM tree_nodes WHERE version_id = %s",
        (version_str,),
    )
    row = cursor.fetchone()
    checks.append(row is not None and row[0] >= 1)

    cursor.execute(
        "SELECT COUNT(*) FROM tree_node_spans tns "
        "JOIN tree_nodes tn ON tns.node_id = tn.node_id "
        "WHERE tn.version_id = %s",
        (version_str,),
    )
    row = cursor.fetchone()
    checks.append(row is not None and row[0] == expected_spans)

    cursor.execute(
        "SELECT COUNT(*) FROM evidence WHERE version_id = %s",
        (version_str,),
    )
    row = cursor.fetchone()
    checks.append(row is not None and row[0] == 0)

    cursor.execute(
        "SELECT COUNT(*) FROM okf_manual_evidence_targets WHERE version_id = %s",
        (version_str,),
    )
    row = cursor.fetchone()
    checks.append(row is not None and row[0] == 0)

    # Global tables: pristine-DB whole-table isolation proof (see docstring).
    for table in (
        "entities",
        "relations",
        "evidence_links",
        "okf_manual_fact_ownership",
    ):
        cursor.execute("SELECT COUNT(*) FROM " + table)
        row = cursor.fetchone()
        checks.append(row is not None and row[0] == 0)

    cursor.execute(
        "SELECT materialization_owner FROM okf_sync_state WHERE version_id = %s",
        (version_str,),
    )
    row = cursor.fetchone()
    checks.append(row is not None and row[0] == "e2a")

    return all(checks)


def _verify_observer_denylist(cursor: Any) -> bool:
    """Fresh-observer durable proof of exact-zero denylist isolation."""
    for table in _DENYLIST_PRESENT_TABLES:
        cursor.execute("SELECT COUNT(*) FROM " + table)
        row = cursor.fetchone()
        if row is None or type(row[0]) is not int or row[0] != 0:
            return False
    for table in _DENYLIST_ABSENT_TABLES:
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = %s",
            (table,),
        )
        if cursor.fetchone() != (0,):
            return False
    return True


def _hits_match_independent_queries(
    hits: Any,
    node_rows: Any,
    node_span_rows: Any,
    chunk_span_rows: Any,
) -> bool:
    """Compare real PageIndex hits against independent registry query results."""
    if not hits:
        return False
    span_ids_by_node: dict[Any, list[Any]] = {}
    for row in node_span_rows:
        span_ids_by_node.setdefault(row["node_id"], []).append(row["span_id"])
    expected: set[tuple[Any, Any, frozenset[Any]]] = set()
    for node in node_rows:
        node_id = node["node_id"]
        node_span_ids = set(span_ids_by_node.get(node_id, []))
        chunk_to_spans: dict[Any, list[Any]] = {}
        for row in chunk_span_rows:
            if row["span_id"] in node_span_ids:
                chunk_to_spans.setdefault(row["chunk_id"], []).append(row["span_id"])
        for chunk_id, span_ids in chunk_to_spans.items():
            expected.add((node_id, chunk_id, frozenset(span_ids)))
    actual = {(hit.node_id, hit.chunk_id, frozenset(hit.span_ids)) for hit in hits}
    return len(actual) == len(hits) and actual == expected


def _new_factory_state() -> dict[str, Any]:
    """Return a fresh factory-connection state record."""
    return {"connection": None, "autocommit_false_at_call": False}


def _new_reconciler() -> E2aReconciler:
    """Inject the E2a reconciler with a deterministic finite embedder only."""
    return E2aReconciler(
        builder=E2aDesiredStateBuilder(embed_text=_deterministic_embedding)
    )


def _make_connection_factory(session: Any, factory_state: dict[str, Any]) -> Any:
    """Return a fresh-attested connection factory recording its connection."""

    def connection_factory() -> Any:
        connection = session.open_fresh_attested_connection()
        factory_state["connection"] = connection
        factory_state["autocommit_false_at_call"] = (
            type(connection.autocommit) is bool and connection.autocommit is False
        )
        return connection

    return connection_factory


def _build_pipeline(
    registry_writer: Any,
    ingestor: Any,
    bundle_root: Path,
    session: Any,
    factory_state: dict[str, Any],
    reconciler: Any,
) -> IngestionPipeline:
    """Build the real IngestionPipeline with the fresh-attested factory."""
    return IngestionPipeline(
        registry=registry_writer,
        ingestor=ingestor,
        bundle_root=bundle_root,
        connection_factory=_make_connection_factory(session, factory_state),
        reconciler=reconciler,
    )


def _install_task89_instrumentation(
    swap_stack: Any,
    ingestor: Any,
    registry_writer: Any,
    reconciler: Any,
) -> dict[str, dict[str, Any]]:
    """Install scoped fail-fast traps and counting wrappers (all restored)."""
    swap_stack.enter_context(_AttributeSwap(DoclingIngestor, "ingest", _legacy_trap))
    for method_name in _LEGACY_PERSISTENCE_METHODS:
        swap_stack.enter_context(
            _AttributeSwap(registry_writer, method_name, _legacy_trap)
        )
    convert_wrapper, convert_state = _make_counting_wrapper(ingestor.convert_for_okf)
    swap_stack.enter_context(
        _AttributeSwap(ingestor, "convert_for_okf", convert_wrapper)
    )
    serialize_wrapper, serialize_state = _make_counting_wrapper(
        serializer.serialize_document
    )
    swap_stack.enter_context(
        _AttributeSwap(serializer, "serialize_document", serialize_wrapper)
    )
    publish_wrapper, publish_state = _make_counting_wrapper(serializer.publish_raw_pair)
    swap_stack.enter_context(
        _AttributeSwap(serializer, "publish_raw_pair", publish_wrapper)
    )
    admit_wrapper, admit_state = _make_counting_wrapper(
        e2a_admission.admit_e2a_materialization_input
    )
    swap_stack.enter_context(
        _AttributeSwap(e2a_admission, "admit_e2a_materialization_input", admit_wrapper)
    )
    reconcile_wrapper, reconcile_state = _make_counting_wrapper(reconciler.reconcile)
    swap_stack.enter_context(_AttributeSwap(reconciler, "reconcile", reconcile_wrapper))
    return {
        "convert": convert_state,
        "serialize": serialize_state,
        "publish": publish_state,
        "admit": admit_state,
        "reconcile": reconcile_state,
    }


def _result_denylist_exact_zero(result: Any) -> bool:
    """Result-map denylist counts: exact 10-key set, every value int 0."""
    denylist_map = result.denylist_dml_counts
    return set(denylist_map) == _DENYLIST_TABLE_NAMES and all(
        type(value) is int and value == 0 for value in denylist_map.values()
    )


def _observe_observer_durable(
    session: Any, version_id: Any, ingest_result: Any
) -> tuple[Any, bool, bool]:
    """Open a fresh independently attested observer, verify, and close it."""
    observer_conn = session.open_fresh_attested_connection()
    observer_cursor = observer_conn.cursor()
    try:
        primary = _verify_observer_durable(observer_cursor, version_id, ingest_result)
        denylist = _verify_observer_denylist(observer_cursor)
    finally:
        _close_quietly(observer_cursor)
        _close_quietly(observer_conn)
    return observer_conn, primary, denylist


def _observe_pageindex_retrieval(registry_writer: Any, version_id: Any) -> bool:
    """Consume the real PageIndex retrieval and compare against registry queries."""
    adapter = PageIndexTreeAdapter()
    node_rows = registry_writer.query_tree_nodes_by_version(version_id)
    node_span_rows = registry_writer.query_tree_node_spans_by_version(version_id)
    chunk_span_rows = registry_writer.query_vector_chunk_spans_by_version(version_id)
    hits = adapter.retrieve_tree_hits(
        query_text=_RETRIEVAL_PROBE,
        version_id=version_id,
        registry=registry_writer,
    )
    return _hits_match_independent_queries(
        hits, node_rows, node_span_rows, chunk_span_rows
    )


def _observe_pageindex_authoring_fail_closed(
    registry_writer: Any, source_path: Path, version_id: Any
) -> tuple[bool, bool]:
    """Confirm index_tree / _flatten_embedded_tree fail closed (FORBIDDEN)."""
    adapter = PageIndexTreeAdapter()
    index_tree_fails_closed = False
    try:
        adapter.index_tree(
            source_path=str(source_path),
            version_id=version_id,
            registry=registry_writer,
        )
    except RuntimeError as failure:
        index_tree_fails_closed = "FORBIDDEN" in str(failure)
    flatten_embedded_tree_fails_closed = False
    try:
        adapter._flatten_embedded_tree([], version_id=version_id)
    except RuntimeError as failure:
        flatten_embedded_tree_fails_closed = "FORBIDDEN" in str(failure)
    return index_tree_fails_closed, flatten_embedded_tree_fails_closed


def _observe_traps_active(registry_writer: Any) -> tuple[bool, bool, bool, bool]:
    """Prove every fail-fast trap is active after the E2a run."""
    legacy_ingest_trap_active = _trap_raises_fixed(DoclingIngestor.ingest)
    write_spans_trap_active = _trap_raises_fixed(registry_writer.write_spans)
    write_tree_trap_active = _trap_raises_fixed(registry_writer.write_tree)
    legacy_persistence_traps_active = all(
        _trap_raises_fixed(getattr(registry_writer, name))
        for name in _LEGACY_PERSISTENCE_METHODS
    )
    return (
        legacy_ingest_trap_active,
        write_spans_trap_active,
        write_tree_trap_active,
        legacy_persistence_traps_active,
    )


def _observe_smoke_families() -> bool:
    """Smoke-only reachability: each family validates with no quality claim."""
    verify = _load_verification_module()
    for family in SMOKE_FAMILIES:
        record = {
            "record_type": "smoke",
            "no_quality_claim": True,
            "family": family,
        }
        try:
            verify.validate_quality_claim(record)
        except Exception:
            return False
    return True


def _compute_connection_observations(
    *,
    states: dict[str, dict[str, Any]],
    ingest_state: dict[str, Any],
    ingest_result: Any,
    factory_state: dict[str, Any],
    writer_conn: Any,
    observer_conn: Any,
) -> dict[str, bool]:
    """Compute wrapper-fidelity and connection-lifecycle observations."""
    factory_conn = factory_state["connection"]
    result = ingest_result.reconciliation_result
    registry_open_through_observer = getattr(writer_conn, "closed", True) is False
    _close_quietly(writer_conn)
    writer_closed_by_helper = getattr(writer_conn, "closed", False) is True
    factory_conn_distinct = (
        factory_conn is not None
        and factory_conn is not writer_conn
        and factory_conn is not observer_conn
    )
    return {
        "wrappers_call_originals": (
            type(states["convert"]["last_result"]) is DoclingConversionResult
            and type(states["serialize"]["last_result"]) is serializer.SerializedRawFile
            and type(states["publish"]["last_result"]) is tuple
            and len(states["publish"]["last_result"]) == 3
            and type(states["admit"]["last_result"]) is E2aMaterializationInput
            and type(states["reconcile"]["last_result"]) is E2aReconciliationResult
            and ingest_state["last_result"] is ingest_result
        ),
        "admitted_is_reconcile_object": (
            states["admit"]["last_result"] is states["reconcile"]["last_args"][1]
        ),
        "result_real_reconciliation_result": (
            type(states["reconcile"]["last_result"]) is E2aReconciliationResult
        ),
        "ingest_result_reconciliation_captured": (
            result is states["reconcile"]["last_result"]
        ),
        "factory_conn_distinct": factory_conn_distinct,
        "factory_autocommit_false_pre_reconcile": (
            factory_state["autocommit_false_at_call"]
        ),
        "factory_closed_after": (
            factory_conn is not None and getattr(factory_conn, "closed", False) is True
        ),
        "registry_open_through_observer": registry_open_through_observer,
        "writer_closed_by_helper": writer_closed_by_helper,
    }


def _assemble_task89_observations(
    *,
    session: Any,
    states: dict[str, dict[str, Any]],
    ingest_state: dict[str, Any],
    ingest_result: Any,
    registry_writer: Any,
    factory_state: dict[str, Any],
    writer_conn: Any,
    bundle_root: Path,
    source_path: Path,
) -> Task89Observations:
    """Gather every stage observation into the redacted Task89Observations."""
    result = ingest_result.reconciliation_result
    version_id = ingest_result.version_id
    version_str = str(version_id)
    result_map_exact_zero = _result_denylist_exact_zero(result)
    observer_conn, observer_primary, observer_denylist = _observe_observer_durable(
        session, version_id, ingest_result
    )
    retrieve_hits_exact_ids = _observe_pageindex_retrieval(registry_writer, version_id)
    index_tree_fc, flatten_tree_fc = _observe_pageindex_authoring_fail_closed(
        registry_writer, source_path, version_id
    )
    trap_flags = _observe_traps_active(registry_writer)
    conn_obs = _compute_connection_observations(
        states=states,
        ingest_state=ingest_state,
        ingest_result=ingest_result,
        factory_state=factory_state,
        writer_conn=writer_conn,
        observer_conn=observer_conn,
    )
    return Task89Observations(
        ingest_calls_exact_one=ingest_state["calls"] == 1,
        convert_calls_exact_one=states["convert"]["calls"] == 1,
        serialize_calls_exact_one=states["serialize"]["calls"] == 1,
        publish_raw_files_exact_three=(
            states["publish"]["calls"] == 1
            and _publish_exact_three(bundle_root / "raw", version_str)
        ),
        admit_calls_exact_one=states["admit"]["calls"] == 1,
        reconcile_calls_exact_one=states["reconcile"]["calls"] == 1,
        wrappers_call_originals=conn_obs["wrappers_call_originals"],
        admitted_is_reconcile_object=conn_obs["admitted_is_reconcile_object"],
        result_real_reconciliation_result=conn_obs["result_real_reconciliation_result"],
        ingest_result_reconciliation_captured=conn_obs[
            "ingest_result_reconciliation_captured"
        ],
        factory_conn_distinct=conn_obs["factory_conn_distinct"],
        factory_autocommit_false_pre_reconcile=conn_obs[
            "factory_autocommit_false_pre_reconcile"
        ],
        factory_closed_after=conn_obs["factory_closed_after"],
        registry_open_through_observer=conn_obs["registry_open_through_observer"],
        writer_closed_by_helper=conn_obs["writer_closed_by_helper"],
        legacy_ingest_trap_active=trap_flags[0],
        write_spans_trap_active=trap_flags[1],
        write_tree_trap_active=trap_flags[2],
        legacy_persistence_traps_active=trap_flags[3],
        index_tree_fails_closed=index_tree_fc,
        flatten_embedded_tree_fails_closed=flatten_tree_fc,
        denylist_counts_exact_zero=(result_map_exact_zero and observer_denylist),
        observer_primary_durable=observer_primary,
        retrieve_hits_exact_ids=retrieve_hits_exact_ids,
        smoke_no_quality_claim=_observe_smoke_families(),
    )


def _failure_observations(failure: Exception) -> Task89Observations:
    """Absorb a failure into a redacted all-false observation."""
    return Task89Observations(
        **{field: False for field in REQUIRED_OBSERVATION_FIELDS},
        success=False,
        error_reason=_error_reason("task89_cell_failed", failure),
    )


def _remove_bundle(bundle_root: Path | None) -> None:
    """Best-effort removal of the ephemeral bundle directory."""
    if bundle_root is not None:
        try:
            shutil.rmtree(bundle_root)
        except Exception:
            pass


def _run_task89_durable_integration_impl(session: Any) -> Task89Observations:
    """Run the Task #89 durable-integration composed proof live component.

    One real ``IngestionPipeline.ingest``; the ``finally`` idempotently
    closes the factory connection (covering a reconcile pre-stage leak).
    """
    writer_conn = registry_writer = bundle_root = None
    factory_state = _new_factory_state()
    try:
        source_path = _resolve_source_pdf()
        writer_conn = session.open_fresh_attested_connection()
        registry_writer = PostgresRegistryWriter(writer_conn)
        ingestor = _new_ingestor()
        reconciler = _new_reconciler()
        bundle_root = Path(tempfile.mkdtemp(prefix="okf_e2a_task89_"))
        pipeline = _build_pipeline(
            registry_writer,
            ingestor,
            bundle_root,
            session,
            factory_state,
            reconciler,
        )
        with contextlib.ExitStack() as swap_stack:
            states = _install_task89_instrumentation(
                swap_stack,
                ingestor,
                registry_writer,
                reconciler,
            )
            ingest_wrapper, ingest_state = _make_counting_wrapper(pipeline.ingest)
            swap_stack.enter_context(_AttributeSwap(pipeline, "ingest", ingest_wrapper))
            return _assemble_task89_observations(
                session=session,
                states=states,
                ingest_state=ingest_state,
                ingest_result=pipeline.ingest(source_path),
                registry_writer=registry_writer,
                factory_state=factory_state,
                writer_conn=writer_conn,
                bundle_root=bundle_root,
                source_path=source_path,
            )
    except Exception as failure:
        return _failure_observations(failure)
    finally:
        _close_quietly(writer_conn)
        _close_quietly(registry_writer)
        _close_quietly(factory_state.get("connection"))
        _remove_bundle(bundle_root)
