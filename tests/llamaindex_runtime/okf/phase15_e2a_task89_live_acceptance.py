"""Task #89 authorized global live acceptance selector (durable integration).

This module is the honest live acceptance surface of the Task #89 slice.
It is NOT collected by default pytest runs (``phase15_`` filename prefix,
which matches neither ``test_*.py`` nor ``*_test.py``), and its selected
live test fails closed before any session creation unless separately
authorized:

    test_task89_authorized_live_acceptance()
      -> _require_authorization()                    # hard RuntimeError if not
                                                     # separately authorized
      -> one ExitStack/DisposableE2aSession          # safe container values
      -> _run_task89_durable_integration_impl(session)  # one direct positional call
      -> RuntimeError(observations.error_reason)     # on failure, redacted
      -> 25 success assertions on the observations

The selected live test executes the Task #89 durable-integration composed
proof's live component: one real ``IngestionPipeline.ingest`` over the
frozen sectioned-pdf source fixture through the real ``DoclingIngestor``,
the real OKF serializer/publisher/admission, a distinct fresh attested
connection factory (autocommit exactly False before reconcile, closed by
the reconciler), and an injected
``E2aReconciler(builder=E2aDesiredStateBuilder(embed_text=<deterministic
finite 16-float>))`` with NO repository argument. Instrumentation wrappers
always call the originals and are scoped-restored on every exit path.
Fail-fast traps guard the legacy/E2b persistence entry points enumerated in
``_LEGACY_PERSISTENCE_METHODS`` (legacy Docling ``.ingest`` plus every
``PostgresRegistryWriter`` ``write_*`` method that is never part of the E2a
route).
``PageIndexTreeAdapter.retrieve_tree_hits`` is consumed for real and its
exact node/chunk/span ids are compared against the independent
``query_tree_nodes_by_version`` / ``query_tree_node_spans_by_version`` /
``query_vector_chunk_spans_by_version`` results, while ``index_tree`` and
``_flatten_embedded_tree`` fail closed. It is an explicit authorized live
test, never an unconditionally passing test, never a ``pytest.skip``,
never an ``xfail``, and never a database command in itself (all database
work lives inside the helper cell).

All database work lives in the helper; this module never opens a
connection, never reads an environment variable, never creates a session
at module level, and never prints or logs a URI, credential, target, or
raw corpus text.
"""

from __future__ import annotations

import contextlib

from ._phase15_e2a_harness_lifecycle import DisposableE2aSession
from ._phase15_e2a_harness_types import (
    _require_authorization,
    _validate_container_name,
)
from ._phase15_e2a_task89_live_cells import (
    _generate_safe_container_name,
    _generate_test_password,
    _run_task89_durable_integration_impl,
    _select_ephemeral_port,
)
from ._phase15_e2a_task89_types import (
    REQUIRED_OBSERVATION_FIELDS,
    SMOKE_FAMILIES,
    SOURCE_PDF_RELATIVE,
    Task89Observations,
)


def test_task89_authorized_live_acceptance() -> None:
    """Task #89 global live acceptance (durable integration; auth-first).

    The authorization check is the FIRST statement and is never skipped;
    only after it may one ExitStack/DisposableE2aSession be opened
    (reusing the safe generated container name, ephemeral port, and
    generated password), exactly one direct positional
    ``_run_task89_durable_integration_impl(session)`` call run, and the
    25 observation fields asserted. On failure exactly one RuntimeError
    carries only ``observations.error_reason``.
    """
    _require_authorization()
    with contextlib.ExitStack() as stack:
        session = DisposableE2aSession(
            container_name=_validate_container_name(_generate_safe_container_name()),
            port=_select_ephemeral_port(),
            password=_generate_test_password(),
        )
        stack.enter_context(session)
        observations = _run_task89_durable_integration_impl(session)
    if not observations.success:
        raise RuntimeError(
            f"Task #89 global acceptance cell failed: {observations.error_reason}"
        )
    assert observations.ingest_calls_exact_one
    assert observations.convert_calls_exact_one
    assert observations.serialize_calls_exact_one
    assert observations.publish_raw_files_exact_three
    assert observations.admit_calls_exact_one
    assert observations.reconcile_calls_exact_one
    assert observations.wrappers_call_originals
    assert observations.admitted_is_reconcile_object
    assert observations.result_real_reconciliation_result
    assert observations.ingest_result_reconciliation_captured
    assert observations.factory_conn_distinct
    assert observations.factory_autocommit_false_pre_reconcile
    assert observations.factory_closed_after
    assert observations.registry_open_through_observer
    assert observations.writer_closed_by_helper
    assert observations.legacy_ingest_trap_active
    assert observations.write_spans_trap_active
    assert observations.write_tree_trap_active
    assert observations.legacy_persistence_traps_active
    assert observations.index_tree_fails_closed
    assert observations.flatten_embedded_tree_fails_closed
    assert observations.denylist_counts_exact_zero
    assert observations.observer_primary_durable
    assert observations.retrieve_hits_exact_ids
    assert observations.smoke_no_quality_claim


def test_task89_global_acceptance_metadata() -> None:
    """Non-live metadata companion: no authorization and no session.

    This test requires no authorization and no database; it pins the
    Task #89 observation surface (25 fields), the four reachability-only
    retrieval smoke families, and the frozen sectioned-pdf source fixture
    location.
    """
    assert len(REQUIRED_OBSERVATION_FIELDS) == 25
    assert REQUIRED_OBSERVATION_FIELDS == frozenset(Task89Observations._fields) - {
        "success",
        "error_reason",
    }
    assert SMOKE_FAMILIES == ("R1", "R2a", "R2b", "p6")
    assert SOURCE_PDF_RELATIVE == (
        "tests",
        "fixtures",
        "okf_roundtrip",
        "sectioned-pdf",
        "source.pdf",
    )
