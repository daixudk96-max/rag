from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw
from llama_index.core.embeddings import MockEmbedding
from qdrant_client import QdrantClient

from llamaindex_runtime.vector import retrieve_vector_hits_from_pdf
from llamaindex_runtime.vector.backend import VectorPoint
from llamaindex_runtime.vector.embedder import DeterministicEmbedder
from llamaindex_runtime.vector.qdrant_backend import QdrantVectorBackend


def _build_rich_pdf(pdf_path: Path) -> None:
    image = Image.new("RGB", (1200, 1600), "white")
    draw = ImageDraw.Draw(image)
    draw.text((80, 80), "Formal Runtime Heading", fill="black")
    draw.text((80, 180), "This is the first body paragraph for the formal runtime live vector test.", fill="black")
    draw.text((80, 260), "This is the second body paragraph and it should become a persisted span.", fill="black")
    image.save(pdf_path, "PDF")


def test_live_vector_index_retrieves_real_docling_nodes(tmp_path: Path) -> None:
    sample_pdf = tmp_path / "formal-runtime-vector.pdf"
    _build_rich_pdf(sample_pdf)

    hits = retrieve_vector_hits_from_pdf(
        sample_pdf,
        query="persisted span",
        embed_model=MockEmbedding(embed_dim=32),
        similarity_top_k=3,
    )

    assert hits
    assert any("persisted" in hit.text.lower() for hit in hits)


def test_qdrant_backend_in_memory_upsert_and_search() -> None:
    """Qdrant backend with in-memory client must upsert and search vectors."""
    import uuid

    client = QdrantClient(":memory:")
    backend = QdrantVectorBackend(client=client, embed_dim=8)
    embedder = DeterministicEmbedder(dim=8)

    # Upsert some vectors
    chunk_id_1 = uuid.uuid4()
    chunk_id_2 = uuid.uuid4()
    points = [
        VectorPoint(
            id=chunk_id_1,
            vector=embedder.embed_text("hello world"),
            payload={"text_preview": "hello world", "page_no": 1},
        ),
        VectorPoint(
            id=chunk_id_2,
            vector=embedder.embed_text("foo bar baz"),
            payload={"text_preview": "foo bar baz", "page_no": 2},
        ),
    ]
    backend.upsert_vectors("test_version", points)

    # Search for vectors
    query_vector = embedder.embed_text("hello")
    hits = backend.search("test_version", query_vector, limit=5)

    assert len(hits) == 2
    # The "hello world" vector should be more similar to "hello" than "foo bar baz"
    # (since embeddings are deterministic and text-based)
    assert hits[0].id in (chunk_id_1, chunk_id_2)
    assert hits[0].payload.get("text_preview") in ("hello world", "foo bar baz")


def test_qdrant_backend_delete_collection() -> None:
    """Qdrant backend must delete collections."""
    import uuid

    client = QdrantClient(":memory:")
    backend = QdrantVectorBackend(client=client, embed_dim=4)

    points = [
        VectorPoint(id=uuid.uuid4(), vector=[1.0, 0.0, 0.0, 0.0]),
    ]
    backend.upsert_vectors("temp_collection", points)

    # Verify collection exists
    collections = client.get_collections().collections
    assert any(c.name == "temp_collection" for c in collections)

    # Delete collection
    backend.delete_collection("temp_collection")

    # Verify collection is gone
    collections = client.get_collections().collections
    assert not any(c.name == "temp_collection" for c in collections)
