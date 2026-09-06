"""Private testkit helpers for E2a caller switchover tests (Phase 15 Track A).

This module contains test-only fakes used by the caller switchover test modules.
These are NOT acceptance evidence, only test support utilities.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence
from uuid import UUID, uuid4

from llamaindex_runtime.ingestion.docling_ingestor import DoclingIngestor
from llamaindex_runtime.ingestion.pipeline import IngestionPipeline
from llamaindex_runtime.registry.contracts import RegisteredDocument, VersionInfo


class _FakeNode:
    text = "fake"

    def __init__(self) -> None:
        self.metadata: dict[str, Any] = {}

    def get_content(self) -> str:
        return "fake"


class _FakeReader:
    calls = 0

    def load_data(self, *, file_path: str) -> list[_FakeNode]:
        _FakeReader.calls += 1
        return [_FakeNode()]


class _FakeParser:
    calls = 0

    def get_nodes_from_documents(self, docs: Sequence[object]) -> list[_FakeNode]:
        _FakeParser.calls += 1
        return [_FakeNode()]


class _FakeRegistry:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.doc_id = uuid4()
        self.version_id = uuid4()

    def register_document(
        self, *, source_path: Path, source_uri: str, title: str | None = None
    ) -> RegisteredDocument:
        self.calls.append(f"register:{source_uri}")
        return RegisteredDocument(self.doc_id, self.version_id, source_uri)

    def get_version(self, version_id: UUID) -> VersionInfo | None:
        self.calls.append(f"get_version:{version_id}")
        return VersionInfo(
            version_id=version_id,
            doc_id=self.doc_id,
            version_no=1,
            content_hash=hashlib.sha256(b"test").hexdigest(),
            is_active=True,
            status="complete",
        )

    def query_spans_by_version(self, version_id: UUID) -> list:
        self.calls.append(f"query_spans_by_version:{version_id}")
        return []

    def write_spans(self, *, version_id: UUID, **kw: Any) -> None:
        self.calls.append(f"write_spans:{version_id}")

    def write_tree(self, *, version_id: UUID, **kw: Any) -> None:
        self.calls.append(f"write_tree:{version_id}")

    def write_vector_chunks(self, *, version_id: UUID, **kw: Any) -> None:
        self.calls.append(f"write_vector_chunks:{version_id}")


@dataclass(frozen=True)
class _FakeConnection:
    autocommit: bool = False
    commit_calls: int = 0
    rollback_calls: int = 0
    close_calls: int = 0

    def commit(self) -> None:
        object.__setattr__(self, "commit_calls", self.commit_calls + 1)

    def rollback(self) -> None:
        object.__setattr__(self, "rollback_calls", self.rollback_calls + 1)

    def close(self) -> None:
        object.__setattr__(self, "close_calls", self.close_calls + 1)


def _fake_ingestor() -> DoclingIngestor:
    return DoclingIngestor(reader=_FakeReader(), node_parser=_FakeParser())


def _build_pipeline(
    registry: _FakeRegistry,
    ingestor: DoclingIngestor,
    *,
    bundle_root: Path | None = None,
    connection_factory: Callable[[], Any] | None = None,
    reconciler: Any = None,
) -> IngestionPipeline:
    """Try E2a constructor; fall back to legacy on TypeError for new kwargs."""
    kwargs: dict[str, Any] = {}
    if bundle_root is not None:
        kwargs["bundle_root"] = bundle_root
    if connection_factory is not None:
        kwargs["connection_factory"] = connection_factory
    if reconciler is not None:
        kwargs["reconciler"] = reconciler
    try:
        return IngestionPipeline(registry=registry, ingestor=ingestor, **kwargs)
    except TypeError as e:
        msg = str(e)
        for key in kwargs:
            if f"'{key}'" in msg or f" {key} " in msg:
                return IngestionPipeline(registry=registry, ingestor=ingestor)
        raise


class _ConversionSentinel(Exception):
    pass


class _SerializationSentinel(Exception):
    pass


class _NestedPublishSentinel(Exception):
    pass


class _NestedReadSentinel(Exception):
    pass


class _AdmissionSentinel(Exception):
    pass


class _ConnectionFactorySentinel(Exception):
    pass


class _ReconcileSentinel(Exception):
    pass


class _PageIndexSentinel(Exception):
    pass


class _VectorLoaderSentinel(Exception):
    pass
