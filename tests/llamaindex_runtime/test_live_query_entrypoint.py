from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw
from llama_index.core.embeddings import MockEmbedding

from llamaindex_runtime.entrypoints import QueryHit, QueryResult, query


def _normalize_text(text: str) -> str:
    return "".join(character for character in text.lower() if character.isalnum())


def _build_rich_pdf(pdf_path: Path) -> None:
    image = Image.new("RGB", (1200, 1600), "white")
    draw = ImageDraw.Draw(image)
    draw.text((80, 80), "Formal Runtime Heading", fill="black")
    draw.text((80, 180), "This is the first body paragraph for the unified live query test.", fill="black")
    draw.text((80, 260), "This is the second body paragraph and it should become persisted merged context.", fill="black")
    image.save(pdf_path, "PDF")


def test_live_query_vector_mode_returns_structured_hits(tmp_path: Path) -> None:
    sample_pdf = tmp_path / "formal-runtime-query-vector.pdf"
    _build_rich_pdf(sample_pdf)

    result = query(
        source_path=sample_pdf,
        query_text="persisted merged context",
        embed_model=MockEmbedding(embed_dim=32),
        mode="vector",
        similarity_top_k=3,
    )

    assert isinstance(result, QueryResult)
    assert result.mode == "vector"
    assert result.source_path == str(sample_pdf)
    assert result.query == "persisted merged context"
    assert result.hits
    assert isinstance(result.hits, tuple)
    assert all(isinstance(hit, QueryHit) for hit in result.hits)
    assert any("persisted" in hit.text.lower() for hit in result.hits)


def test_live_query_tree_mode_returns_structured_hits(tmp_path: Path) -> None:
    sample_pdf = tmp_path / "formal-runtime-query-tree.pdf"
    _build_rich_pdf(sample_pdf)

    result = query(
        source_path=sample_pdf,
        query_text="merged context",
        embed_model=MockEmbedding(embed_dim=32),
        mode="tree",
        similarity_top_k=4,
    )

    assert isinstance(result, QueryResult)
    assert result.mode == "tree"
    assert result.source_path == str(sample_pdf)
    assert result.query == "merged context"
    assert result.hits
    assert isinstance(result.hits, tuple)
    assert all(isinstance(hit, QueryHit) for hit in result.hits)

    normalized_hit_text = _normalize_text(result.hits[0].text)
    assert "firstbodyparagraph" in normalized_hit_text
    assert "secondbodyparagraph" in normalized_hit_text
    assert "mergedcontext" in normalized_hit_text
