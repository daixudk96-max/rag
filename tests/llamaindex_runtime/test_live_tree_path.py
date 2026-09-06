from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw
from llama_index.core.embeddings import MockEmbedding

from llamaindex_runtime.tree import retrieve_tree_hits_from_pdf


def _normalize_text(text: str) -> str:
    return "".join(character for character in text.lower() if character.isalnum())


def _build_rich_pdf(pdf_path: Path) -> None:
    image = Image.new("RGB", (1200, 1600), "white")
    draw = ImageDraw.Draw(image)
    draw.text((80, 80), "Formal Runtime Heading", fill="black")
    draw.text((80, 180), "This is the first body paragraph for the formal runtime tree test.", fill="black")
    draw.text((80, 260), "This is the second body paragraph and it should become merged context.", fill="black")
    image.save(pdf_path, "PDF")


def test_live_tree_path_merges_parent_context(tmp_path: Path) -> None:
    sample_pdf = tmp_path / "formal-runtime-tree.pdf"
    _build_rich_pdf(sample_pdf)

    hits = retrieve_tree_hits_from_pdf(
        sample_pdf,
        query="merged context",
        embed_model=MockEmbedding(embed_dim=32),
        similarity_top_k=4,
        chunk_sizes=[256, 96],
    )

    assert hits

    normalized_hit_text = _normalize_text(hits[0].text)
    assert "firstbodyparagraph" in normalized_hit_text
    assert "secondbodyparagraph" in normalized_hit_text
    assert "mergedcontext" in normalized_hit_text
