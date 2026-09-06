"""Debug script to investigate vector retrieval behavior."""
from pathlib import Path
from llama_index.core.embeddings import MockEmbedding
from llamaindex_runtime.vector.runtime import retrieve_vector_hits_from_pdf
from llamaindex_runtime.ingestion.bundle import build_docling_bundle
from llamaindex_runtime.integration import load_docling_node_parser_class

SAMPLE_PDF = Path("verification/tests/fixtures/sample_minimal.pdf")

# Step 1: Check bundle creation
print("Step 1: Creating bundle...")
bundle = build_docling_bundle(SAMPLE_PDF)
print(f"JSON docs: {len(bundle.json_documents)}")
print(f"Markdown docs: {len(bundle.markdown_documents)}")
print(f"JSON doc text length: {len(bundle.json_documents[0].text)}")

# Step 2: Check node parsing
print("\nStep 2: Parsing nodes...")
parser = load_docling_node_parser_class()()
nodes = parser.get_nodes_from_documents(bundle.json_documents)
print(f"Nodes created: {len(nodes)}")
if nodes:
    print(f"First node text preview: {nodes[0].text[:100] if len(nodes[0].text) > 100 else nodes[0].text}")

# Step 3: Check retrieval
print("\nStep 3: Retrieving hits...")
embed_model = MockEmbedding(embed_dim=32)
hits = retrieve_vector_hits_from_pdf(
    SAMPLE_PDF,
    query="test",
    embed_model=embed_model,
    similarity_top_k=3
)
print(f"Hits retrieved: {len(hits)}")
if hits:
    print(f"First hit node text: {hits[0].node.text[:100]}")
    print(f"First hit score: {hits[0].score}")