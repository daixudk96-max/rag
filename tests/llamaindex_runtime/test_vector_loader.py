from __future__ import annotations

import uuid
from typing import Any

from llamaindex_runtime.vector.loader import VectorLoader


class _FakeConnection:
    pass


def test_load_returns_zero_when_no_spans(monkeypatch) -> None:  # noqa: ANN001
    version_id = uuid.uuid4()
    loader = VectorLoader()
    monkeypatch.setattr(loader, "_read_spans", lambda _conn, _version_id: [])

    assert loader.load(_FakeConnection(), version_id) == {"chunk_ids": [], "count": 0}


def test_load_repairs_existing_chunks_missing_embeddings_and_node_ids(monkeypatch) -> None:  # noqa: ANN001
    version_id = uuid.uuid4()
    span_id = uuid.uuid4()
    chunk_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{version_id}:{span_id}")
    loader = VectorLoader()
    calls: dict[str, int] = {
        "update_embeddings": 0,
        "repair_tree_nodes": 0,
        "project_to_backend": 0,
    }

    monkeypatch.setattr(
        loader,
        "_read_spans",
        lambda _conn, _version_id: [
            {
                "span_id": span_id,
                "version_id": version_id,
                "raw_text": "span body",
                "heading_path": "canonical_spans.heading_path",
            }
        ],
    )
    monkeypatch.setattr(loader, "_count_existing_chunks", lambda _conn, _version_id: 1)
    monkeypatch.setattr(loader, "_read_chunk_ids", lambda _conn, _version_id: [chunk_id])
    monkeypatch.setattr(loader, "_count_chunks_missing_embedding", lambda _conn, _version_id: 1)

    def _update_embeddings(_conn: Any, _chunks: list[dict[str, Any]]) -> None:
        calls["update_embeddings"] += 1

    def _repair_tree_nodes(
        _conn: Any,
        _version_id: uuid.UUID,
        _spans: list[dict[str, Any]],
    ) -> None:
        calls["repair_tree_nodes"] += 1

    def _project_to_backend(
        _version_id: uuid.UUID,
        _chunks: list[dict[str, Any]],
    ) -> None:
        calls["project_to_backend"] += 1

    monkeypatch.setattr(loader, "_update_embeddings", _update_embeddings)
    monkeypatch.setattr(loader, "_repair_tree_nodes", _repair_tree_nodes)
    monkeypatch.setattr(loader, "_project_to_backend", _project_to_backend)

    assert loader.load(_FakeConnection(), version_id) == {"chunk_ids": [chunk_id], "count": 1}
    assert calls == {
        "update_embeddings": 1,
        "repair_tree_nodes": 1,
        "project_to_backend": 1,
    }


def test_load_creates_chunks_and_mappings_when_missing(monkeypatch) -> None:  # noqa: ANN001
    version_id = uuid.uuid4()
    span_id = uuid.uuid4()
    loader = VectorLoader()
    calls: dict[str, int] = {
        "write_chunks": 0,
        "write_chunk_span_mappings": 0,
        "update_embeddings": 0,
        "link_tree_nodes": 0,
    }

    monkeypatch.setattr(
        loader,
        "_read_spans",
        lambda _conn, _version_id: [
            {
                "span_id": span_id,
                "version_id": version_id,
                "raw_text": "span body",
                "heading_path": "canonical_spans.heading_path",
            }
        ],
    )
    monkeypatch.setattr(loader, "_count_existing_chunks", lambda _conn, _version_id: 0)

    def _write_chunks(
        _conn: Any,
        _version_id: uuid.UUID,
        chunks: list[dict[str, Any]],
    ) -> None:
        assert len(chunks) == 1
        calls["write_chunks"] += 1

    def _write_chunk_span_mappings(
        _conn: Any,
        mappings: list[tuple[uuid.UUID, uuid.UUID, int]],
    ) -> None:
        assert mappings == [(uuid.uuid5(uuid.NAMESPACE_URL, f"{version_id}:{span_id}"), span_id, 0)]
        calls["write_chunk_span_mappings"] += 1

    def _update_embeddings(_conn: Any, chunks: list[dict[str, Any]]) -> None:
        assert len(chunks) == 1
        calls["update_embeddings"] += 1

    def _link_tree_nodes(
        _conn: Any,
        _version_id: uuid.UUID,
        chunks: list[dict[str, Any]],
    ) -> None:
        assert len(chunks) == 1
        calls["link_tree_nodes"] += 1

    monkeypatch.setattr(loader, "_write_chunks", _write_chunks)
    monkeypatch.setattr(loader, "_write_chunk_span_mappings", _write_chunk_span_mappings)
    monkeypatch.setattr(loader, "_update_embeddings", _update_embeddings)
    monkeypatch.setattr(loader, "_link_tree_nodes", _link_tree_nodes)
    monkeypatch.setattr(loader, "_project_to_backend", lambda _version_id, _chunks: None)

    result = loader.load(_FakeConnection(), version_id)

    assert result["count"] == 1
    assert result["chunk_ids"] == [uuid.uuid5(uuid.NAMESPACE_URL, f"{version_id}:{span_id}")]
    assert calls == {
        "write_chunks": 1,
        "write_chunk_span_mappings": 1,
        "update_embeddings": 1,
        "link_tree_nodes": 1,
    }
