"""E2a caller switchover API contract tests (Phase 15 Task #69).

These tests verify the IngestionPipeline accepts E2a-related kwargs and exhibits
the expected behavioral contracts. They use fake testkit components to avoid
production dependencies. The tests pass whether the E2a route is active or the
legacy fallback is used, as long as the API contracts are honored.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Sequence
from dataclasses import fields
from pathlib import Path
from typing import Any, Callable
from uuid import UUID, uuid4

import pytest

from llamaindex_runtime.ingestion.docling_ingestor import DoclingIngestor
from llamaindex_runtime.ingestion.models import IngestResult
from llamaindex_runtime.ingestion.pipeline import IngestionPipeline
from llamaindex_runtime.interfaces.span import CanonicalSpan
from llamaindex_runtime.registry.contracts import RegisteredDocument, VersionInfo

from okf._e2a_caller_switchover_testkit import (
    _ConnectionFactorySentinel,
    _ConversionSentinel,
    _FakeConnection,
    _FakeNode,
    _FakeParser,
    _FakeReader,
    _FakeRegistry,
    _NestedReadSentinel,
    _PageIndexSentinel,
    _ReconcileSentinel,
    _VectorLoaderSentinel,
    _build_pipeline,
    _fake_ingestor,
)
from okf._e2a_pipeline_testkit import (
    _FakeReconciler,
    _make_reconciliation_result,
)


class TestFakeNodeMetadataIsolation:
    """Regression: each _FakeNode instance must own its own metadata dict.

    Previously ``metadata`` was a mutable class attribute shared across all
    instances, so mutating one instance's metadata leaked into every other
    instance. These tests pin per-instance isolation while preserving the
    ``text`` and ``get_content`` contracts.
    """

    def test_metadata_not_shared_between_instances(self) -> None:
        node_a = _FakeNode()
        node_b = _FakeNode()
        node_a.metadata["leaked"] = True
        assert (
            node_b.metadata == {}
        ), f"metadata leaked between instances: {node_b.metadata!r}"

    def test_metadata_starts_empty_per_instance(self) -> None:
        assert _FakeNode().metadata == {}

    def test_text_and_get_content_preserved(self) -> None:
        node = _FakeNode()
        assert node.text == "fake"
        assert node.get_content() == "fake"


class TestModelsAndConversionContract:
    def test_reconciliation_result_field_exists(self) -> None:
        assert "reconciliation_result" in {f.name for f in fields(IngestResult)}

    def test_direct_ingest_returns_none(self, tmp_path: Path) -> None:
        source = tmp_path / "test.pdf"
        source.write_bytes(b"test")
        result = _fake_ingestor().ingest(source, doc_id=uuid4(), version_id=uuid4())
        assert result.reconciliation_result is None

    def test_conversion_result_frozen_fields(self, tmp_path: Path) -> None:
        source = tmp_path / "test.pdf"
        content = b"test content"
        source.write_bytes(content)
        result = _fake_ingestor().convert_for_okf(source)
        assert {f.name for f in fields(type(result))} == {
            "source_uri",
            "source_sha256",
            "docling_version",
            "nodes",
        }
        with pytest.raises(AttributeError):
            result.source_uri = "other"
        assert result.source_uri == source.resolve().as_uri()
        assert result.source_sha256 == hashlib.sha256(content).hexdigest()
        assert isinstance(result.docling_version, str)
        assert type(result.nodes) is tuple
        for node in result.nodes:
            assert not isinstance(node, CanonicalSpan)

    def test_reader_parser_called_once_and_mutation(self, tmp_path: Path) -> None:
        _FakeReader.calls = 0
        _FakeParser.calls = 0
        source = tmp_path / "test.pdf"
        source.write_bytes(b"test")
        _fake_ingestor().convert_for_okf(source)
        assert _FakeReader.calls == 1
        assert _FakeParser.calls == 1

        class _MutatingReader:
            def load_data(self, *, file_path: str) -> list[_FakeNode]:
                Path(file_path).write_bytes(b"mutated")
                return [_FakeNode()]

        source2 = tmp_path / "test2.pdf"
        source2.write_bytes(b"original")
        with pytest.raises(ValueError):
            DoclingIngestor(
                reader=_MutatingReader(), node_parser=_FakeParser()
            ).convert_for_okf(source2)


class TestConstructorKwargAcceptance:
    def test_bundle_root_accepted(self, tmp_path: Path) -> None:
        pipeline = IngestionPipeline(
            registry=_FakeRegistry(), ingestor=_fake_ingestor(), bundle_root=tmp_path
        )
        assert pipeline is not None

    def test_connection_factory_accepted(self, tmp_path: Path) -> None:
        pipeline = IngestionPipeline(
            registry=_FakeRegistry(),
            ingestor=_fake_ingestor(),
            connection_factory=lambda: _FakeConnection(),
        )
        assert pipeline is not None

    def test_reconciler_accepted(self, tmp_path: Path) -> None:
        pipeline = IngestionPipeline(
            registry=_FakeRegistry(),
            ingestor=_fake_ingestor(),
            reconciler=_FakeReconciler(),
        )
        assert pipeline is not None


class TestSourceValidationBeforeDependencyValidation:
    def test_missing_file_before_missing_deps(self, tmp_path: Path) -> None:
        registry = _FakeRegistry()
        pipeline = _build_pipeline(registry, _fake_ingestor())
        with pytest.raises(FileNotFoundError):
            pipeline.ingest(tmp_path / "missing.pdf")
        assert len(registry.calls) == 0
        source = tmp_path / "test.pdf"
        source.write_bytes(b"test")
        with pytest.raises(ValueError) as exc:
            pipeline.ingest(source)
        assert "bundle_root" in str(exc.value)


class TestNoEnvVarReads:
    def test_pipeline_does_not_read_env_vars(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env_reads = {"count": 0}
        orig_getitem = os.environ.__getitem__
        orig_get = os.environ.get
        orig_getenv = os.getenv

        class _TrapEnviron(dict):
            def __getitem__(self, key: str) -> str:
                env_reads["count"] += 1
                return orig_getitem(key)

            def get(self, key: str, default: Any = None) -> Any:
                env_reads["count"] += 1
                return orig_get(key, default)

        def _trap_getenv(key: str, default: Any = None) -> Any:
            env_reads["count"] += 1
            return default

        monkeypatch.setattr(os, "environ", _TrapEnviron(os.environ))
        monkeypatch.setattr(os, "getenv", _trap_getenv)
        pipeline = _build_pipeline(
            _FakeRegistry(),
            _fake_ingestor(),
            bundle_root=tmp_path,
            connection_factory=lambda: _FakeConnection(),
            reconciler=_FakeReconciler(),
        )
        source = tmp_path / "test.pdf"
        source.write_bytes(b"test")
        result = pipeline.ingest(source)
        assert env_reads["count"] == 0
        assert result.reconciliation_result is not None
        monkeypatch.setattr(os, "environ", orig_getitem.__self__)
        monkeypatch.setattr(os, "getenv", orig_getenv)


class TestIntegratedRouteAndTwoPair:
    def test_complete_route_sequence_two_nested_reads(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from llamaindex_runtime.okf import (
            e2a_admission,
            serializer as serializer_module,
        )
        from llamaindex_runtime.okf.serializer import serialize_document

        bundle_root = tmp_path / "bundle"
        bundle_root.mkdir()
        (bundle_root / "raw").mkdir()
        serialize_document(
            [_FakeNode()],
            doc_id=str(uuid4()),
            version_id=str(uuid4()),
            source_checksum="a" * 64,
            docling_version="1.0.0",
            bundle_root=bundle_root,
            name=str(uuid4()),
        )
        call_sequence: list[str] = []

        def _track(key: str, orig: Callable) -> Callable:
            def wrapper(*a: Any, **kw: Any) -> Any:
                call_sequence.append(key)
                return orig(*a, **kw)

            return wrapper

        monkeypatch.setattr(
            serializer_module,
            "publish_raw_pair",
            _track("nested_publish", serializer_module.publish_raw_pair),
        )
        monkeypatch.setattr(
            e2a_admission,
            "read_raw_pair",
            _track("nested_read", e2a_admission.read_raw_pair),
        )
        monkeypatch.setattr(
            serializer_module,
            "serialize_document",
            _track("serialize", serializer_module.serialize_document),
        )
        monkeypatch.setattr(
            e2a_admission,
            "admit_e2a_materialization_input",
            _track("admit", e2a_admission.admit_e2a_materialization_input),
        )

        class _TrackedRegistry(_FakeRegistry):
            def register_document(
                self, *, source_path: Path, source_uri: str, title: str | None = None
            ) -> RegisteredDocument:
                call_sequence.append("register")
                return super().register_document(
                    source_path=source_path, source_uri=source_uri, title=title
                )

            def get_version(self, version_id: UUID) -> VersionInfo | None:
                call_sequence.append("get_version")
                return super().get_version(version_id)

        class _TrackedIngestor(DoclingIngestor):
            def convert_for_okf(self, source: Path) -> object:
                call_sequence.append("convert")
                return super().convert_for_okf(source)

        class _TrackedReconciler:
            def reconcile(self, connection: object, desired: object) -> object:
                call_sequence.append("reconcile")
                return _FakeReconciler().reconcile(connection, desired)

        def _factory() -> _FakeConnection:
            call_sequence.append("factory")
            return _FakeConnection()

        pipeline = _build_pipeline(
            _TrackedRegistry(),
            _TrackedIngestor(reader=_FakeReader(), node_parser=_FakeParser()),
            bundle_root=bundle_root,
            connection_factory=_factory,
            reconciler=_TrackedReconciler(),
        )
        source = tmp_path / "test.pdf"
        source.write_bytes(b"test")
        result = pipeline.ingest(source)
        assert call_sequence == [
            "register",
            "get_version",
            "convert",
            "serialize",
            "nested_publish",
            "admit",
            "nested_read",
            "nested_read",
            "factory",
            "reconcile",
        ]
        assert result.reconciliation_result is not None


class TestConnectionBoundary:
    def test_connection_identity_and_guarded(self, tmp_path: Path) -> None:
        conn = _FakeConnection()
        factory_calls = 0
        seen_connection = None

        def _factory() -> _FakeConnection:
            nonlocal factory_calls, seen_connection
            factory_calls += 1
            seen_connection = conn
            return conn

        class _IdentityReconciler:
            def reconcile(self, connection: object, desired: object) -> object:
                nonlocal seen_connection
                seen_connection = connection
                return _FakeReconciler().reconcile(connection, desired)

        pipeline = _build_pipeline(
            _FakeRegistry(),
            _fake_ingestor(),
            bundle_root=tmp_path,
            connection_factory=_factory,
            reconciler=_IdentityReconciler(),
        )
        source = tmp_path / "test.pdf"
        source.write_bytes(b"test")
        result = pipeline.ingest(source)
        assert factory_calls == 1
        assert seen_connection is conn
        assert conn.autocommit is False
        assert conn.commit_calls == 0
        assert conn.rollback_calls == 0
        assert conn.close_calls == 0
        assert result.reconciliation_result is not None

        class _GuardedConnection:
            _autocommit = False

            @property
            def autocommit(self) -> bool:
                return self._autocommit

            @autocommit.setter
            def autocommit(self, value: bool) -> None:
                raise _ConnectionFactorySentinel()

        pipeline2 = _build_pipeline(
            _FakeRegistry(),
            _fake_ingestor(),
            bundle_root=tmp_path,
            connection_factory=lambda: _GuardedConnection(),
            reconciler=_FakeReconciler(),
        )
        source2 = tmp_path / "test2.pdf"
        source2.write_bytes(b"test")
        result2 = pipeline2.ingest(source2)
        assert result2.reconciliation_result is not None


class TestForbiddenOperations:
    def test_e2a_route_no_legacy_methods(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        registry = _FakeRegistry()
        bundle_root = tmp_path / "bundle"
        bundle_root.mkdir()
        (bundle_root / "raw").mkdir()

        class _IngestorNoDirect(DoclingIngestor):
            def ingest(
                self,
                source: Path,
                *,
                doc_id: UUID | None = None,
                version_id: UUID | None = None,
            ) -> IngestResult:
                raise RuntimeError("FORBIDDEN_DIRECT_COMPARATOR")

        def _page_index_trap(*a: Any, **kw: Any) -> Any:
            raise _PageIndexSentinel()

        def _vector_loader_trap(*a: Any, **kw: Any) -> Any:
            raise _VectorLoaderSentinel()

        from llamaindex_runtime.tree.pageindex_adapter import PageIndexTreeAdapter
        from llamaindex_runtime.vector.loader import VectorLoader

        monkeypatch.setattr(PageIndexTreeAdapter, "index_tree", _page_index_trap)
        monkeypatch.setattr(VectorLoader, "load", _vector_loader_trap)

        pipeline = _build_pipeline(
            registry,
            _IngestorNoDirect(reader=_FakeReader(), node_parser=_FakeParser()),
            bundle_root=bundle_root,
            connection_factory=lambda: _FakeConnection(),
            reconciler=_FakeReconciler(),
        )
        source = tmp_path / "test.pdf"
        source.write_bytes(b"test")
        result = pipeline.ingest(source)
        assert result.reconciliation_result is not None
        assert not any("query_spans_by_version" in c for c in registry.calls)
        assert not any("write_spans" in c for c in registry.calls)
        assert not any("write_tree" in c for c in registry.calls)
        assert not any("write_vector_chunks" in c for c in registry.calls)


class TestExactSentinelPropagation:
    def test_conversion_sentinel_propagates(self, tmp_path: Path) -> None:
        class _SentinelIngestor(DoclingIngestor):
            def convert_for_okf(self, source: Path) -> object:
                raise _ConversionSentinel()

        _FakeReconciler.calls = 0
        pipeline = _build_pipeline(
            _FakeRegistry(),
            _SentinelIngestor(reader=_FakeReader(), node_parser=_FakeParser()),
            bundle_root=tmp_path,
            connection_factory=lambda: _FakeConnection(),
            reconciler=_FakeReconciler(),
        )
        source = tmp_path / "test.pdf"
        source.write_bytes(b"test")
        with pytest.raises(_ConversionSentinel):
            pipeline.ingest(source)
        assert _FakeReconciler.calls == 0

    @pytest.mark.parametrize(
        "module_path,func_name,sentinel_name",
        [
            (
                "llamaindex_runtime.okf.serializer",
                "serialize_document",
                "_SerializationSentinel",
            ),
            (
                "llamaindex_runtime.okf.serializer",
                "publish_raw_pair",
                "_NestedPublishSentinel",
            ),
            (
                "llamaindex_runtime.okf.e2a_admission",
                "admit_e2a_materialization_input",
                "_AdmissionSentinel",
            ),
        ],
    )
    def test_module_sentinel_propagates(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        module_path: str,
        func_name: str,
        sentinel_name: str,
    ) -> None:
        import importlib

        from okf._e2a_caller_switchover_testkit import (
            _AdmissionSentinel,
            _NestedPublishSentinel,
            _SerializationSentinel,
        )

        sentinel_map = {
            "_SerializationSentinel": _SerializationSentinel,
            "_NestedPublishSentinel": _NestedPublishSentinel,
            "_AdmissionSentinel": _AdmissionSentinel,
        }
        sentinel_cls = sentinel_map[sentinel_name]

        module = importlib.import_module(module_path)

        def _sentinel(*a: Any, **kw: Any) -> Any:
            raise sentinel_cls()

        _FakeReconciler.calls = 0
        monkeypatch.setattr(module, func_name, _sentinel)
        pipeline = _build_pipeline(
            _FakeRegistry(),
            _fake_ingestor(),
            bundle_root=tmp_path,
            connection_factory=lambda: _FakeConnection(),
            reconciler=_FakeReconciler(),
        )
        source = tmp_path / "test.pdf"
        source.write_bytes(b"test")
        with pytest.raises(sentinel_cls):
            pipeline.ingest(source)
        assert _FakeReconciler.calls == 0

    def test_nested_read_sentinel(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from llamaindex_runtime.okf import e2a_admission

        def _sentinel(*a: Any, **kw: Any) -> Any:
            raise _NestedReadSentinel()

        _FakeReconciler.calls = 0
        monkeypatch.setattr(e2a_admission, "read_raw_pair", _sentinel)
        pipeline = _build_pipeline(
            _FakeRegistry(),
            _fake_ingestor(),
            bundle_root=tmp_path,
            connection_factory=lambda: _FakeConnection(),
            reconciler=_FakeReconciler(),
        )
        source = tmp_path / "test.pdf"
        source.write_bytes(b"test")
        with pytest.raises(_NestedReadSentinel):
            pipeline.ingest(source)
        assert _FakeReconciler.calls == 0

    def test_factory_and_reconcile_sentinels(self, tmp_path: Path) -> None:
        def _sentinel_factory() -> Any:
            raise _ConnectionFactorySentinel()

        _FakeReconciler.calls = 0
        pipeline = _build_pipeline(
            _FakeRegistry(),
            _fake_ingestor(),
            bundle_root=tmp_path,
            connection_factory=_sentinel_factory,
            reconciler=_FakeReconciler(),
        )
        source = tmp_path / "test.pdf"
        source.write_bytes(b"test")
        with pytest.raises(_ConnectionFactorySentinel):
            pipeline.ingest(source)
        assert _FakeReconciler.calls == 0

        class _SentinelReconciler:
            def reconcile(self, connection: object, desired: object) -> object:
                raise _ReconcileSentinel()

        conn = _FakeConnection()
        pipeline2 = _build_pipeline(
            _FakeRegistry(),
            _fake_ingestor(),
            bundle_root=tmp_path,
            connection_factory=lambda: conn,
            reconciler=_SentinelReconciler(),
        )
        source2 = tmp_path / "test2.pdf"
        source2.write_bytes(b"test")
        with pytest.raises(_ReconcileSentinel):
            pipeline2.ingest(source2)
        assert conn.commit_calls == 0
        assert conn.rollback_calls == 0
        assert conn.close_calls == 0


class TestHashMismatchBlocksDownstream:
    def test_mismatch_blocks_serialize_publish_admit_factory_reconcile(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _MismatchedRegistry(_FakeRegistry):
            def get_version(self, version_id: UUID) -> VersionInfo | None:
                self.calls.append(f"get_version:{version_id}")
                return VersionInfo(
                    version_id=version_id,
                    doc_id=self.doc_id,
                    version_no=1,
                    content_hash="b" * 64,
                    is_active=True,
                    status="complete",
                )

        from llamaindex_runtime.okf import (
            e2a_admission,
            serializer as serializer_module,
        )

        counts = {
            "serialize": 0,
            "publish": 0,
            "admit": 0,
            "factory": 0,
            "reconcile": 0,
        }

        def _track(key: str, orig: Callable) -> Callable:
            def wrapper(*a: Any, **kw: Any) -> Any:
                counts[key] += 1
                return orig(*a, **kw)

            return wrapper

        monkeypatch.setattr(
            serializer_module,
            "serialize_document",
            _track("serialize", serializer_module.serialize_document),
        )
        monkeypatch.setattr(
            serializer_module,
            "publish_raw_pair",
            _track("publish", serializer_module.publish_raw_pair),
        )
        monkeypatch.setattr(
            e2a_admission,
            "admit_e2a_materialization_input",
            _track("admit", e2a_admission.admit_e2a_materialization_input),
        )

        def _factory() -> _FakeConnection:
            counts["factory"] += 1
            return _FakeConnection()

        class _CountingReconciler:
            def reconcile(self, connection: object, desired: object) -> object:
                counts["reconcile"] += 1
                return _make_reconciliation_result()

        pipeline = _build_pipeline(
            _MismatchedRegistry(),
            _fake_ingestor(),
            bundle_root=tmp_path,
            connection_factory=_factory,
            reconciler=_CountingReconciler(),
        )
        source = tmp_path / "test.pdf"
        source.write_bytes(b"test")
        with pytest.raises(ValueError):
            pipeline.ingest(source)
        assert counts["serialize"] == 0
        assert counts["publish"] == 0
        assert counts["admit"] == 0
        assert counts["factory"] == 0
        assert counts["reconcile"] == 0


class TestRealReconstructionAndSlug:
    def test_current_foreign_reconstruction_with_metadata(self, tmp_path: Path) -> None:
        from llamaindex_runtime.okf.serializer import serialize_document

        bundle_root = tmp_path / "bundle"
        bundle_root.mkdir()
        (bundle_root / "raw").mkdir()
        serialize_document(
            [_FakeNode()],
            doc_id=str(uuid4()),
            version_id=str(uuid4()),
            source_checksum="a" * 64,
            docling_version="1.0.0",
            bundle_root=bundle_root,
            name=str(uuid4()),
        )

        class _NodeWithMetadata:
            text = "  text with   whitespace  "
            metadata = {"page_no": 7, "heading_path": "Alpha > Beta", "offset": 13}

            def get_content(self) -> str:
                return self.text

        class _NodeRoot:
            text = "root text"
            metadata = {"page_no": 1, "heading_path": "", "offset": 0}

            def get_content(self) -> str:
                return self.text

        class _NodeEmpty:
            text = "   "
            metadata: dict[str, Any] = {}

            def get_content(self) -> str:
                return self.text

        class _RealReader:
            def load_data(self, *, file_path: str) -> list[Any]:
                return [_NodeWithMetadata(), _NodeRoot(), _NodeEmpty()]

        class _RealParser:
            def get_nodes_from_documents(self, docs: Sequence[object]) -> list[Any]:
                return [_NodeWithMetadata(), _NodeRoot(), _NodeEmpty()]

        expected_reconciliation = _make_reconciliation_result("changed")

        class _ExactReconciler:
            def reconcile(self, connection: object, desired: object) -> object:
                return expected_reconciliation

        registry = _FakeRegistry()
        pipeline = _build_pipeline(
            registry,
            DoclingIngestor(reader=_RealReader(), node_parser=_RealParser()),
            bundle_root=bundle_root,
            connection_factory=lambda: _FakeConnection(),
            reconciler=_ExactReconciler(),
        )
        source = tmp_path / "test.pdf"
        source.write_bytes(b"test")
        result = pipeline.ingest(source)
        assert len(result.spans) == 2
        span_nonroot = result.spans[0]
        span_root = result.spans[1]
        assert isinstance(span_nonroot.span_id, UUID)
        assert isinstance(span_root.span_id, UUID)
        assert span_nonroot.doc_id == registry.doc_id
        assert span_root.doc_id == registry.doc_id
        assert span_nonroot.version_id == registry.version_id
        assert span_root.version_id == registry.version_id
        assert span_nonroot.text == "text with whitespace"
        assert span_root.text == "root text"
        assert span_nonroot.offset == 13
        assert span_root.offset == 0
        assert span_nonroot.page_no == 7
        assert span_root.page_no == 1
        assert span_nonroot.headings == ("Alpha", "Beta")
        assert span_root.headings == ()
        assert result.dropped_nodes == 1
        assert result.source_uri == source.resolve().as_uri()
        assert result.reconciliation_result is expected_reconciliation

    def test_exact_slug_and_reconciler_identity(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from llamaindex_runtime.okf import serializer as serializer_module

        registry = _FakeRegistry()
        bundle_root = tmp_path / "bundle"
        bundle_root.mkdir()
        (bundle_root / "raw").mkdir()
        serialize_calls: list[dict[str, Any]] = []
        conversion_results: list[Any] = []
        orig_serialize = serializer_module.serialize_document

        def _tracked_serialize(*a: Any, **kw: Any) -> Any:
            serialize_calls.append(kw)
            return orig_serialize(*a, **kw)

        class _TrackedIngestor(DoclingIngestor):
            def convert_for_okf(self, source: Path) -> object:
                result = super().convert_for_okf(source)
                conversion_results.append(result)
                return result

        monkeypatch.setattr(serializer_module, "serialize_document", _tracked_serialize)
        expected = _make_reconciliation_result("changed")

        class _ExactReconciler:
            def reconcile(self, connection: object, desired: object) -> object:
                return expected

        pipeline = _build_pipeline(
            registry,
            _TrackedIngestor(reader=_FakeReader(), node_parser=_FakeParser()),
            bundle_root=bundle_root,
            connection_factory=lambda: _FakeConnection(),
            reconciler=_ExactReconciler(),
        )
        source = tmp_path / "test.pdf"
        source.write_bytes(b"test")
        result = pipeline.ingest(source)
        assert len(serialize_calls) == 1
        assert len(conversion_results) == 1
        assert serialize_calls[0]["name"] == str(registry.version_id)
        version_info = registry.get_version(registry.version_id)
        assert version_info is not None
        assert serialize_calls[0]["source_checksum"] == version_info.content_hash
        assert (
            serialize_calls[0]["source_checksum"] == conversion_results[0].source_sha256
        )
        assert result.reconciliation_result is expected
