"""Check what text is in the sample_minimal.pdf."""
from pathlib import Path
from llama_index.core.embeddings import MockEmbedding
from llamaindex_runtime.tree.runtime import retrieve_tree_hits_from_pdf
from llamaindex_runtime.ingestion.bundle import build_docling_bundle

SAMPLE_PDF = Path("verification/tests/fixtures/sample_minimal.pdf")

# Check bundle
print("Step 1: Creating bundle...")
bundle = build_docling_bundle(SAMPLE_PDF)
print(f"Markdown text:\n{bundle.markdown_documents[0].text[:500]}")

# Check tree retrieval
print("\nStep 2: Retrieving tree hits...")
embed_model = MockEmbedding(embed_dim=32)
hits = retrieve_tree_hits_from_pdf(
    SAMPLE_PDF,
    query="test",
    embed_model=embed_model,
    similarity_top_k=5
)
print(f"Tree hits: {len(hits)}")
if hits:
    for i, hit in enumerate(hits[:3]):
        print(f"\nHit {i+1}:")
        print(f"  Score: {hit.score}")
        print(f"  Text preview: {hit.node.text[:200]}")