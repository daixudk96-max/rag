#!/usr/bin/env python3
"""
Debug keyword matching logic with detailed logging
"""

import os
import sys
from pathlib import Path
import json

os.environ['RAG_TREE_HOTSPOT_SELECTOR'] = 'hybrid_cluster'

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / '.env', override=False)

import psycopg
from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter
from llamaindex_runtime.tree.semantic_distribution import analyze_semantic_distribution
from llamaindex_runtime.tree.runtime import _extract_keywords_from_query
from llamaindex_runtime.embeddings import SentenceTransformersEmbedding
from llama_index.core.embeddings import BaseEmbedding

# Get version_id from ingestion status
OUTPUT_DIR = Path(__file__).parent
status_path = OUTPUT_DIR / '02_document_ingestion_status.json'
with open(status_path, 'r', encoding='utf-8') as f:
    status = json.load(f)
    VERSION_ID = status['version_id']

CORPUS_PATH = PROJECT_ROOT / "docs/research/deep-research-report (1).md"
DEMO_QUERY = "KAG 和 NexusRAG 在知识图谱能力上有什么区别？"

class RealEmbedding(BaseEmbedding):
    def __init__(self, model_name='all-MiniLM-L6-v2'):
        super().__init__()
        self._embedder = SentenceTransformersEmbedding(model_name=model_name)

    def _get_query_embedding(self, query: str) -> list[float]:
        return self._embedder._get_query_embedding(query)

    def _get_text_embedding(self, text: str) -> list[float]:
        return self._embedder._get_text_embedding(text)

    def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        return [self._get_text_embedding(t) for t in texts]

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return self._get_query_embedding(query)

    async def _aget_text_embedding(self, text: str) -> list[float]:
        return self._get_text_embedding(text)

    async def _aget_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        return self._get_text_embeddings(texts)

# Setup
db_url = os.environ['DATABASE_URL']
conn = psycopg.connect(db_url, autocommit=True)
registry = PostgresRegistryWriter(conn)

# Get tree nodes
tree_nodes = registry.query_tree_nodes_by_version(VERSION_ID)
print(f"\nTotal tree nodes: {len(tree_nodes)}")

# Get node embeddings
node_embeddings = registry.query_node_embeddings_by_version(VERSION_ID)
print(f"Total node embeddings: {len(node_embeddings)}")

# Create embedder
embed_model = RealEmbedding()
query_embedding = embed_model._get_query_embedding(DEMO_QUERY)
print(f"Query embedding dimension: {len(query_embedding)}")

# Extract keywords
query_keywords = _extract_keywords_from_query(DEMO_QUERY)
print(f"\nExtracted keywords: {query_keywords}")

# Analyze semantic distribution
distribution_report = analyze_semantic_distribution(
    tree_nodes=tree_nodes,
    node_embeddings=node_embeddings,
    query_embedding=query_embedding,
    registry=registry,
    version_id=VERSION_ID,
)

print(f"\nNode stats count: {len(distribution_report['node_stats'])}")

# Check what fields are in node_stats
print("\nChecking node_stats fields:")
for i, stats in enumerate(distribution_report['node_stats'][:3]):
    print(f"\n  Node {i+1}:")
    print(f"    node_id: {stats.get('node_id')}")
    print(f"    heading_path: '{stats.get('heading_path', '')[:50]}'")
    print(f"    title: '{stats.get('title', '')[:50]}'")
    print(f"    summary_text: '{str(stats.get('summary_text', ''))[:50]}'")

    # Check keyword matches
    heading_path = stats.get("heading_path", "") or ""
    title = stats.get("title", "") or ""
    summary_text = stats.get("summary_text", "") or ""

    searchable_text = f"{heading_path} {title} {summary_text}".strip()

    if searchable_text:
        matched_keywords = tuple(
            kw for kw in query_keywords if kw.lower() in searchable_text.lower()
        )
        print(f"    searchable_text preview: '{searchable_text[:100]}'")
        print(f"    matched_keywords: {matched_keywords}")

conn.close()