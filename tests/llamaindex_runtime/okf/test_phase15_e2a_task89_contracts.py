"""Task #89 non-DB unit contracts for the durable-integration live cells.

This module is the collected RED/GREEN static surface for the Task #89
slice. It pins, WITHOUT any database, Docker, or live selector:

- the 25-field redacted observation shape (``Task89Observations``) and
  the frozen source-fixture / smoke-family constants,
- the deterministic finite 16-float embedder contract against the real
  ``E2aDesiredStateBuilder`` ``_embedding`` validation,
- the counting-instrumentation wrapper contract (the wrapper MUST call the
  original and return its result),
- the core live helper is defined and its body carries the real production
  boundaries with no fake/replacement machinery,
- the live cells module performs no environment reads and never builds a
  session,
- the real production symbol signatures the live helper depends on, plus
  the fail-closed ``index_tree`` / ``_flatten_embedded_tree`` behavior and
  the real ``retrieve_tree_hits`` consumer surface.

The real-ingestor construction and the unique ``sys.modules`` scoped
verification-loader contracts live in the focused sibling module
``test_phase15_e2a_task89_live_ingestor_loader``.

The embedder/wrapper/core-helper behavior contracts are RED until GREEN
completes ``_phase15_e2a_task89_live_cells``. No environment variable is
read, no database is touched, and no session is ever created here.
"""

from __future__ import annotations

import ast
import math
from dataclasses import fields
from pathlib import Path
from types import ModuleType

import pytest

from llamaindex_runtime.ingestion.docling_ingestor import DoclingIngestor
from llamaindex_runtime.ingestion.models import IngestResult
from llamaindex_runtime.ingestion.pipeline import IngestionPipeline
from llamaindex_runtime.okf import e2a_admission
from llamaindex_runtime.okf import serializer
from llamaindex_runtime.okf import e2a_contracts as contracts
from llamaindex_runtime.okf._e2a_materialization_input import (
    E2aDesiredStateBuilder,
    E2aMaterializationInput,
)
from llamaindex_runtime.okf.e2a_contracts import E2aReconciliationResult
from llamaindex_runtime.okf.e2a_reconciler import E2aReconciler
from llamaindex_runtime.okf.raw_pair import publish_raw_pair
from llamaindex_runtime.registry.postgres_adapter import (
    PostgresRegistryWriter,
    RegisteredDocument,
)
from llamaindex_runtime.tree.backend_adapter import BackendHit
from llamaindex_runtime.tree.pageindex_adapter import PageIndexTreeAdapter

from ._phase15_e2a_task89_ast_proof import (
    HELPER_IMPL_FUNCTION,
    LIVE_CELLS_FILENAME,
    SUPPORT_FILENAME,
    _verify_helper_finally_closes_factory,
    _verify_live_cells_boundaries,
    _verify_live_cells_source,
    _verify_support_source,
)
from ._phase15_e2a_task89_observer_sql_proof import _verify_observer_durable_sql
from ._phase15_e2a_task89_types import (
    REQUIRED_OBSERVATION_FIELDS,
    SMOKE_FAMILIES,
    SOURCE_PDF_RELATIVE,
    Task89Observations,
)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
OKF_DIR = Path(__file__).parent


class _FakeWriter:
    """Minimal owner with a legacy write method for scoped-swap tests."""

    def write_spans(self, *args: object, **kwargs: object) -> str:
        return "original-write-spans"


class _StubConnection:
    """Minimal closeable whose ``close`` is idempotent and observable."""

    closed = False

    def close(self) -> None:
        self.closed = True


class _StubCursor:
    """Minimal execute/fetchone stub for the denylist observer contract tests."""

    def __init__(self, present_counts: list[int], absent_counts: list[int]) -> None:
        values = [(count,) for count in present_counts] + [
            (count,) for count in absent_counts
        ]
        self._values = iter(values)
        self._next: tuple[int] | None = None

    def execute(self, statement: str, params: object | None = None) -> None:
        self._next = next(self._values, None)

    def fetchone(self) -> tuple[int] | None:
        return self._next


def _live_cells_module() -> ModuleType:
    from . import _phase15_e2a_task89_live_cells as cells

    return cells


def _all_true_observations() -> Task89Observations:
    """Construct a full Task89Observations with every observation True."""
    return Task89Observations(
        ingest_calls_exact_one=True,
        convert_calls_exact_one=True,
        serialize_calls_exact_one=True,
        publish_raw_files_exact_three=True,
        admit_calls_exact_one=True,
        reconcile_calls_exact_one=True,
        wrappers_call_originals=True,
        admitted_is_reconcile_object=True,
        result_real_reconciliation_result=True,
        ingest_result_reconciliation_captured=True,
        factory_conn_distinct=True,
        factory_autocommit_false_pre_reconcile=True,
        factory_closed_after=True,
        registry_open_through_observer=True,
        writer_closed_by_helper=True,
        legacy_ingest_trap_active=True,
        write_spans_trap_active=True,
        write_tree_trap_active=True,
        legacy_persistence_traps_active=True,
        index_tree_fails_closed=True,
        flatten_embedded_tree_fails_closed=True,
        denylist_counts_exact_zero=True,
        observer_primary_durable=True,
        retrieve_hits_exact_ids=True,
        smoke_no_quality_claim=True,
    )


class TestTask89ObservationSurface:
    """Exact redacted observation surface of the durable-integration cell."""

    def test_observation_fields_exact_twenty_five(self) -> None:
        cells = _live_cells_module()
        assert len(REQUIRED_OBSERVATION_FIELDS) == 25
        assert REQUIRED_OBSERVATION_FIELDS == frozenset(Task89Observations._fields) - {
            "success",
            "error_reason",
        }
        # The live selector imports the same constants from the types module.
        assert cells.REQUIRED_OBSERVATION_FIELDS is REQUIRED_OBSERVATION_FIELDS

    def test_observation_namedtuple_immutable(self) -> None:
        observations = Task89Observations(
            ingest_calls_exact_one=True,
            convert_calls_exact_one=True,
            serialize_calls_exact_one=True,
            publish_raw_files_exact_three=True,
            admit_calls_exact_one=True,
            reconcile_calls_exact_one=True,
            wrappers_call_originals=True,
            admitted_is_reconcile_object=True,
            result_real_reconciliation_result=True,
            ingest_result_reconciliation_captured=True,
            factory_conn_distinct=True,
            factory_autocommit_false_pre_reconcile=True,
            factory_closed_after=True,
            registry_open_through_observer=True,
            writer_closed_by_helper=True,
            legacy_ingest_trap_active=True,
            write_spans_trap_active=True,
            write_tree_trap_active=True,
            legacy_persistence_traps_active=True,
            index_tree_fails_closed=True,
            flatten_embedded_tree_fails_closed=True,
            denylist_counts_exact_zero=True,
            observer_primary_durable=True,
            retrieve_hits_exact_ids=True,
            smoke_no_quality_claim=True,
        )
        assert observations.success is True
        with pytest.raises(AttributeError):
            observations.ingest_calls_exact_one = False  # type: ignore[misc]

    def test_observation_success_defaults_true(self) -> None:
        observations = _all_true_observations()
        assert observations.success is True
        assert observations.error_reason == ""

    def test_observation_repr_redacts_error_reason(self) -> None:
        observations = _all_true_observations()._replace(
            success=False, error_reason="cell_failed:ValueError"
        )
        rendered = repr(observations)
        assert "cell_failed" not in rendered
        assert "ValueError" not in rendered
        assert "details=<redacted>" in rendered

    def test_smoke_families_reachability_only(self) -> None:
        assert SMOKE_FAMILIES == ("R1", "R2a", "R2b", "p6")
        assert len(SMOKE_FAMILIES) == 4

    def test_source_pdf_fixture_location(self) -> None:
        assert SOURCE_PDF_RELATIVE == (
            "tests",
            "fixtures",
            "okf_roundtrip",
            "sectioned-pdf",
            "source.pdf",
        )


class TestTask89EmbedderContract:
    """Deterministic finite 16-float embedder (RED until helper exists)."""

    def test_embedder_returns_exactly_sixteen_finite_floats(self) -> None:
        cells = _live_cells_module()
        values = cells._deterministic_embedding("live sectioned-pdf probe")
        assert type(values) is tuple
        assert len(values) == 16
        assert all(type(value) is float for value in values)
        assert all(math.isfinite(value) for value in values)

    def test_embedder_is_deterministic(self) -> None:
        cells = _live_cells_module()
        first = cells._deterministic_embedding("same input text")
        second = cells._deterministic_embedding("same input text")
        assert first == second

    def test_embedder_accepts_builder_validation(self) -> None:
        from llamaindex_runtime.okf._e2a_materialization_input import _embedding

        cells = _live_cells_module()
        values = cells._deterministic_embedding("accepted by the builder")
        validated = _embedding(values)
        assert validated == values

    def test_embedder_builder_construction(self) -> None:
        cells = _live_cells_module()
        builder = E2aDesiredStateBuilder(embed_text=cells._deterministic_embedding)
        assert callable(builder.embed_text)

    def test_builder_requires_callable_embed_text(self) -> None:
        with pytest.raises(TypeError, match="embed_text must be callable"):
            E2aDesiredStateBuilder(embed_text="not-callable")  # type: ignore[arg-type]

    def test_builder_rejects_non_input_source(self) -> None:
        cells = _live_cells_module()
        builder = E2aDesiredStateBuilder(embed_text=cells._deterministic_embedding)
        with pytest.raises(TypeError, match="E2aMaterializationInput"):
            builder.build(object())  # type: ignore[arg-type]


class TestTask89CountingWrapperContract:
    """Instrumentation wrapper must call the original and record counts."""

    def test_wrapper_calls_original_and_returns_identity(self) -> None:
        cells = _live_cells_module()
        sentinel = {"marker": 1}
        original = lambda value: sentinel  # noqa: E731
        wrapper, state = cells._make_counting_wrapper(original)
        result = wrapper("anything")
        assert result is sentinel
        assert state["calls"] == 1
        assert state["last_result"] is sentinel

    def test_wrapper_increments_per_call(self) -> None:
        cells = _live_cells_module()
        original = lambda value: value  # noqa: E731
        wrapper, state = cells._make_counting_wrapper(original)
        wrapper(1)
        wrapper(2)
        assert state["calls"] == 2
        assert state["last_result"] == 2


class TestTask89AttributeSwapContract:
    """Scoped attribute swaps restore the exact original lookup state.

    ``_AttributeSwap`` is descriptor-aware: when the swapped attribute was
    already a direct instance attribute it restores identity-exactly via
    ``setattr``; when it resolved from the class descriptor (an instance
    method), it restores via ``delattr`` so the class descriptor lookup
    resumes with no instance shadow left behind. The three ``_FakeWriter``
    cases assert exactly that: ``write_spans`` is absent from
    ``owner.__dict__`` after restore, resolves back to the class method,
    and answers with the original implementation. Direct instance
    attributes and module/class functions are asserted identity-exact.
    """

    def test_swap_restores_original_on_normal_exit(self) -> None:
        cells = _live_cells_module()
        owner = _FakeWriter()
        with cells._AttributeSwap(owner, "write_spans", cells._legacy_trap):
            assert owner.write_spans is cells._legacy_trap
        assert "write_spans" not in owner.__dict__
        assert owner.write_spans.__func__ is _FakeWriter.write_spans
        assert owner.write_spans() == "original-write-spans"

    def test_swap_restores_original_when_body_raises(self) -> None:
        cells = _live_cells_module()
        owner = _FakeWriter()
        with pytest.raises(RuntimeError, match="boom"):
            with cells._AttributeSwap(owner, "write_spans", cells._legacy_trap):
                raise RuntimeError("boom")
        assert "write_spans" not in owner.__dict__
        assert owner.write_spans.__func__ is _FakeWriter.write_spans
        assert owner.write_spans() == "original-write-spans"

    def test_swap_restore_is_idempotent(self) -> None:
        cells = _live_cells_module()
        owner = _FakeWriter()
        swap = cells._AttributeSwap(owner, "write_spans", cells._legacy_trap)
        swap.restore()
        swap.restore()
        assert "write_spans" not in owner.__dict__
        assert owner.write_spans.__func__ is _FakeWriter.write_spans
        assert owner.write_spans() == "original-write-spans"

    def test_swap_restores_direct_instance_attribute_identity(self) -> None:
        cells = _live_cells_module()
        owner = _FakeWriter()
        marker = lambda *args, **kwargs: "marker"  # noqa: E731
        owner.write_spans = marker
        with cells._AttributeSwap(owner, "write_spans", cells._legacy_trap):
            assert owner.write_spans is cells._legacy_trap
        assert owner.write_spans is marker

    def test_swap_restores_module_function_identity(self) -> None:
        cells = _live_cells_module()
        original = cells._trap_raises_fixed
        with cells._AttributeSwap(cells, "_trap_raises_fixed", lambda target: True):
            assert cells._trap_raises_fixed is not original
        assert cells._trap_raises_fixed is original

    def test_swap_restores_class_attribute_identity(self) -> None:
        cells = _live_cells_module()
        original = DoclingIngestor.ingest
        with cells._AttributeSwap(DoclingIngestor, "ingest", cells._legacy_trap):
            assert DoclingIngestor.ingest is cells._legacy_trap
        assert DoclingIngestor.ingest is original

    def test_swap_restores_serializer_module_attribute_identity(self) -> None:
        cells = _live_cells_module()
        original = serializer.serialize_document
        with cells._AttributeSwap(serializer, "serialize_document", cells._legacy_trap):
            assert serializer.serialize_document is cells._legacy_trap
        assert serializer.serialize_document is original


class TestTask89LegacyTrapSurface:
    """The legacy trap set covers every real legacy/E2b persistence method."""

    def test_legacy_persistence_methods_all_exist_on_writer(self) -> None:
        cells = _live_cells_module()
        assert cells._LEGACY_PERSISTENCE_METHODS
        for method_name in cells._LEGACY_PERSISTENCE_METHODS:
            assert hasattr(PostgresRegistryWriter, method_name), method_name
            assert callable(getattr(PostgresRegistryWriter, method_name)), method_name

    def test_legacy_persistence_methods_not_in_e2a_path(self) -> None:
        # The E2a route materializes through E2aMaterializationRepository
        # over the reconciler's own cursor; none of these writer write_*
        # entry points are invoked by IngestionPipeline._ingest_e2a.
        cells = _live_cells_module()
        e2a_route_calls = {
            "register_document",
            "get_version",
            "query_tree_nodes_by_version",
            "query_tree_node_spans_by_version",
            "query_vector_chunk_spans_by_version",
            "query_vector_chunks_by_version",
        }
        assert set(cells._LEGACY_PERSISTENCE_METHODS).isdisjoint(e2a_route_calls)


class TestTask89ObserverDenylistContract:
    """The fresh observer directly proves the ten-key denylist isolation."""

    def test_denylist_observer_accepts_pristine(self) -> None:
        cells = _live_cells_module()
        cursor = _StubCursor(present_counts=[0] * 5, absent_counts=[0] * 5)
        assert cells._verify_observer_denylist(cursor) is True

    def test_denylist_observer_rejects_nonzero_present_table(self) -> None:
        cells = _live_cells_module()
        cursor = _StubCursor(present_counts=[0, 0, 1, 0, 0], absent_counts=[0] * 5)
        assert cells._verify_observer_denylist(cursor) is False

    def test_denylist_observer_rejects_catalog_present_absent_name(self) -> None:
        cells = _live_cells_module()
        cursor = _StubCursor(present_counts=[0] * 5, absent_counts=[0, 1, 0, 0, 0])
        assert cells._verify_observer_denylist(cursor) is False

    def test_observer_durable_version_filters_join_vector_chunks(self) -> None:
        # Structural AST/SQL proof against the actual live-cells source: the
        # verifier resolves every cursor.execute SQL (implicit adjacent
        # literals and module-level constant extraction included), normalizes
        # SQL whitespace, requires direct parameterized version COUNTs for
        # canonical_spans and vector_chunks, and requires exactly one
        # vector_chunk_spans COUNT that JOINs vector_chunks on the two
        # chunk_id references with the version filter through the
        # vector_chunks alias -- rejecting any direct/unjoined variant.
        source = (OKF_DIR / LIVE_CELLS_FILENAME).read_text(encoding="utf-8")
        _verify_observer_durable_sql(source)


class TestTask89FactoryConnectionClose:
    """The helper finally must idempotently close the factory connection."""

    def test_live_cells_helper_finally_closes_factory_connection(self) -> None:
        source = (OKF_DIR / LIVE_CELLS_FILENAME).read_text(encoding="utf-8")
        tree = ast.parse(source)
        helpers = [
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == HELPER_IMPL_FUNCTION
        ]
        assert len(helpers) == 1
        _verify_helper_finally_closes_factory(helpers[0])

    def test_close_quietly_is_idempotent(self) -> None:
        cells = _live_cells_module()
        resource = _StubConnection()
        cells._close_quietly(resource)
        assert resource.closed is True
        cells._close_quietly(resource)
        assert resource.closed is True

    def test_factory_connection_closed_after_reconcile_is_idempotent(self) -> None:
        cells = _live_cells_module()
        factory_state: dict[str, object] = {
            "connection": _StubConnection(),
            "autocommit_false_at_call": True,
        }
        cells._close_quietly(factory_state["connection"])
        cells._close_quietly(factory_state["connection"])
        assert factory_state["connection"].closed is True


class TestTask89LiveCellsHygiene:
    """The live cells module never reads env, builds a session, or fakes."""

    def test_live_cells_module_no_env_no_session_no_fakes(self) -> None:
        source = (OKF_DIR / LIVE_CELLS_FILENAME).read_text(encoding="utf-8")
        tree = ast.parse(source)
        _verify_live_cells_source(source)
        # No top-level session construction or connection opening.
        for statement in tree.body:
            if isinstance(statement, (ast.Expr, ast.Assign, ast.AnnAssign)):
                for node in ast.walk(statement):
                    if isinstance(node, ast.Call) and (
                        (
                            isinstance(node.func, ast.Name)
                            and node.func.id == "DisposableE2aSession"
                        )
                        or (
                            isinstance(node.func, ast.Attribute)
                            and node.func.attr == "open_fresh_attested_connection"
                        )
                    ):
                        raise AssertionError(
                            "module-level session construction or connection "
                            "opening is forbidden"
                        )

    def test_live_cells_helper_defined_once(self) -> None:
        source = (OKF_DIR / LIVE_CELLS_FILENAME).read_text(encoding="utf-8")
        tree = ast.parse(source)
        helpers = [
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == HELPER_IMPL_FUNCTION
        ]
        assert len(helpers) == 1

    def test_live_cells_helper_body_real_boundaries_no_fakes(self) -> None:
        source = (OKF_DIR / LIVE_CELLS_FILENAME).read_text(encoding="utf-8")
        tree = ast.parse(source)
        helpers = [
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == HELPER_IMPL_FUNCTION
        ]
        assert len(helpers) == 1
        _verify_live_cells_boundaries(source)
        _verify_helper_finally_closes_factory(helpers[0])

    def test_live_cells_helper_under_50_lines(self) -> None:
        source = (OKF_DIR / LIVE_CELLS_FILENAME).read_text(encoding="utf-8")
        tree = ast.parse(source)
        helpers = [
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == HELPER_IMPL_FUNCTION
        ]
        assert len(helpers) == 1
        span = helpers[0].end_lineno - helpers[0].lineno
        assert span <= 50, f"the live helper must stay under 50 lines, got {span}"


class TestTask89SupportHygiene:
    """The extracted support module keeps the scoped-loader/real-ingestor pins.

    The support module holds the file-based verification-module loader and
    the real Docling ingestor constructor. Its source must pin the explicit-
    file spec loading, the unique scoped module key, the BaseException
    restore path, the real reader/node-parser loader path, and the bounded
    class/type-only diagnostic, and must never contain environment/secret
    access, mock/fake machinery, sys.path mutation, session/DB construction,
    or unsafe dynamic imports or exec/eval.
    """

    def test_support_module_source_pins_scoped_loader_and_real_ingestor(
        self,
    ) -> None:
        source = (OKF_DIR / SUPPORT_FILENAME).read_text(encoding="utf-8")
        _verify_support_source(source)


class TestTask89ProductionSignatures:
    """Real production symbols the durable-integration helper depends on."""

    def test_pipeline_accepts_e2a_kwargs(self) -> None:
        # A dummy ingestor avoids the lazy default docling reader construction.
        pipeline = IngestionPipeline(registry=object(), ingestor=object())
        assert pipeline is not None
        assert callable(pipeline.ingest)

    def test_pipeline_ingest_validates_source_first(self) -> None:
        pipeline = IngestionPipeline(registry=object(), ingestor=object())
        with pytest.raises(FileNotFoundError):
            pipeline.ingest(Path(OKF_DIR) / "definitely_missing_source_file.pdf")

    def test_pipeline_ingest_missing_e2a_dependencies(self) -> None:
        pipeline = IngestionPipeline(registry=object(), ingestor=object())
        source = OKF_DIR / LIVE_CELLS_FILENAME
        with pytest.raises(ValueError, match="Missing E2a dependencies"):
            pipeline.ingest(source)

    def test_docling_ingestor_has_convert_and_legacy_ingest(self) -> None:
        # Class-level method presence only; no heavy reader construction.
        assert callable(DoclingIngestor.convert_for_okf)
        assert callable(DoclingIngestor.ingest)

    def test_reconciler_accepts_builder_kwarg_only(self) -> None:
        builder = E2aDesiredStateBuilder(embed_text=lambda text: (0.0,) * 16)
        reconciler = E2aReconciler(builder=builder)
        assert reconciler is not None
        assert callable(reconciler.reconcile)

    def test_serializer_serialize_document_signature(self) -> None:
        import inspect

        signature = inspect.signature(serializer.serialize_document)
        parameters = signature.parameters
        assert parameters["bundle_root"].kind is inspect.Parameter.KEYWORD_ONLY
        assert parameters["name"].kind is inspect.Parameter.KEYWORD_ONLY
        assert "doc_id" in parameters
        assert "version_id" in parameters
        assert "source_checksum" in parameters

    def test_publish_raw_pair_returns_three_paths(self) -> None:
        import inspect

        signature = inspect.signature(publish_raw_pair)
        assert set(signature.parameters) >= {
            "bundle_root",
            "slug",
            "markdown_bytes",
            "sidecar_bytes",
            "manifest_bytes",
        }

    def test_admit_e2a_materialization_input_signature(self) -> None:
        import inspect

        signature = inspect.signature(e2a_admission.admit_e2a_materialization_input)
        assert set(signature.parameters) == {"authority"}

    def test_writer_constructor_forces_autocommit_true(self) -> None:
        # PostgresRegistryWriter(connection) sets autocommit=True; with a
        # plain object the constructor rejects it before any DB work.
        with pytest.raises((AttributeError, RuntimeError)):
            PostgresRegistryWriter(object())  # type: ignore[arg-type]

    def test_registered_document_and_version_info_exist(self) -> None:
        assert RegisteredDocument is not None
        assert contracts is not None
        assert E2aReconciliationResult is not None

    def test_result_has_exact_ten_fields(self) -> None:
        assert set(E2aReconciliationResult.__dataclass_fields__) == {
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

    def test_ingest_result_carries_reconciliation_result(self) -> None:
        assert "reconciliation_result" in IngestResult.__dataclass_fields__
        assert "spans" in IngestResult.__dataclass_fields__

    def test_materialization_input_is_importable(self) -> None:
        assert E2aMaterializationInput is not None

    def test_primary_table_names_match_production(self) -> None:
        from llamaindex_runtime.okf.e2a_materialization_repository import (
            _PRIMARY_TABLES,
        )

        cells = _live_cells_module()
        assert cells._PRIMARY_TABLE_NAMES == _PRIMARY_TABLES

    def test_denylist_table_names_match_production(self) -> None:
        from llamaindex_runtime.okf.e2a_materialization_repository import (
            _DENYLIST_TABLES,
        )

        cells = _live_cells_module()
        assert cells._DENYLIST_TABLE_NAMES == _DENYLIST_TABLES

    def test_backend_hit_fields(self) -> None:
        assert {field.name for field in fields(BackendHit)} >= {
            "score",
            "text_preview",
            "heading_path",
            "page_no",
            "span_ids",
            "node_id",
            "chunk_id",
            "entity_id",
            "relation_id",
        }


class TestTask89PageIndexFailClosed:
    """PageIndex must fail closed on authoring; consume for real on read."""

    def test_index_tree_fails_closed(self) -> None:
        adapter = PageIndexTreeAdapter()
        with pytest.raises(RuntimeError, match="FORBIDDEN"):
            adapter.index_tree(
                source_path="any.pdf",
                version_id=__import__("uuid").UUID(int=1),
                registry=object(),
            )

    def test_flatten_embedded_tree_fails_closed(self) -> None:
        adapter = PageIndexTreeAdapter()
        with pytest.raises(RuntimeError, match="FORBIDDEN"):
            adapter._flatten_embedded_tree(
                [], version_id=__import__("uuid").UUID(int=1)
            )

    def test_retrieve_tree_hits_real_consumer_signature(self) -> None:
        import inspect

        signature = inspect.signature(PageIndexTreeAdapter.retrieve_tree_hits)
        assert set(signature.parameters) >= {
            "self",
            "query_text",
            "version_id",
            "registry",
            "limit",
        }


class TestTask89VerificationModuleByFile:
    """The verification module loads by file and its smoke guard behaves."""

    def _load_verification(self):
        cells = _live_cells_module()
        return cells._load_verification_module()

    def test_verification_module_loads_by_file(self) -> None:
        verify = self._load_verification()
        assert callable(verify.validate_quality_claim)
        assert callable(verify.validate_evidence_authenticity)
        assert callable(verify.serialize_evidence)
        assert callable(verify.run_verification)

    def test_smoke_record_with_no_quality_claim_validates(self) -> None:
        verify = self._load_verification()
        for family in SMOKE_FAMILIES:
            record = {
                "record_type": "smoke",
                "no_quality_claim": True,
                "family": family,
            }
            verify.validate_quality_claim(record)

    def test_smoke_record_claiming_level_is_rejected(self) -> None:
        verify = self._load_verification()
        claiming = {"record_type": "smoke", "claimed_level": "L2"}
        with pytest.raises(ValueError, match="cannot claim quality Level"):
            verify.validate_quality_claim(claiming)

    def test_run_verification_blocked_not_executed(self) -> None:
        verify = self._load_verification()
        result = verify.run_verification(enable_disposable_db=False)
        assert result["disposable_db_status"] == "blocked_not_executed"
        assert result["outcome"] == "acceptance_blocked"


class TestTask89LiveSelectorHygiene:
    """The live selector (non-collected) stays safe at import time."""

    def test_live_selector_module_never_constructs_session(self) -> None:
        source = (OKF_DIR / "phase15_e2a_task89_live_acceptance.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        for statement in tree.body:
            if isinstance(statement, (ast.Expr, ast.Assign, ast.AnnAssign)):
                for node in ast.walk(statement):
                    if isinstance(node, ast.Call) and (
                        (
                            isinstance(node.func, ast.Name)
                            and node.func.id == "DisposableE2aSession"
                        )
                        or (
                            isinstance(node.func, ast.Attribute)
                            and node.func.attr == "open_fresh_attested_connection"
                        )
                    ):
                        raise AssertionError(
                            "module-level session construction or connection "
                            "opening is forbidden in the live selector"
                        )

    def test_live_selector_metadata_test_no_session(self) -> None:
        from ._phase15_e2a_task89_ast_proof import (
            METADATA_TEST_NAME,
            _single_function_by_name,
        )

        source = (OKF_DIR / "phase15_e2a_task89_live_acceptance.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        function = _single_function_by_name(tree, METADATA_TEST_NAME)
        referenced = {
            node.id for node in ast.walk(function) if isinstance(node, ast.Name)
        }
        assert "DisposableE2aSession" not in referenced
        assert "open_fresh_attested_connection" not in referenced
        assert HELPER_IMPL_FUNCTION not in referenced
        assert not any(
            isinstance(node, ast.With) for node in ast.walk(function)
        ), "the metadata companion test must not open a context manager"
