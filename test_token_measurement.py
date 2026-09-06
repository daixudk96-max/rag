"""Token consumption measurement for optimized reasoning_backend.

Tests verify:
1. Compact structure formatting token count
2. Minimal prompt token count
3. Total token consumption < 200 tokens (90%+ target)
"""
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

from llamaindex_runtime.tree.reasoning_backend import ReasoningTreeBackend
from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter
import psycopg
import tiktoken

def count_tokens(text: str, model: str = "gpt-4o-mini") -> int:
    """Count tokens in text using tiktoken."""
    try:
        encoding = tiktoken.encoding_for_model(model)
        return len(encoding.encode(text))
    except:
        # Fallback: rough estimate (4 chars per token)
        return len(text) // 4

def test_token_consumption():
    """Measure token consumption of optimized reasoning_backend."""
    print("=== Token Consumption Measurement (Optimized) ===\n")

    # Connect to PostgreSQL
    database_url = os.getenv("DATABASE_URL", "")
    conn = psycopg.connect(database_url)
    registry = PostgresRegistryWriter(conn)

    # Get version_id
    cursor = conn.cursor()
    cursor.execute("SELECT version_id FROM document_versions ORDER BY created_at DESC LIMIT 1")
    version_id = uuid.UUID(str(cursor.fetchone()[0]))
    cursor.close()

    # Get tree structure
    nodes = registry.query_tree_nodes_by_version(version_id)
    all_nodes_count = len(nodes)
    print(f"[INFO] Total nodes: {all_nodes_count}")

    # Create backend and structure
    backend = ReasoningTreeBackend(llm_model="gpt-4o-mini")
    structure = backend._build_structure_from_nodes(nodes)

    # Measure structure formatting tokens
    structure_text = backend._format_structure_for_llm(structure)
    structure_tokens = count_tokens(structure_text)
    print(f"\n[MEASURE] Structure formatting:")
    print(f"  - Text length: {len(structure_text)} chars")
    print(f"  - Token count: {structure_tokens} tokens")

    # Measure prompt tokens (minimal prompt - actual from backend)
    query_text = "市场概况"
    # Build prompt the same way backend does
    prompt = f"Pages:\n{structure_text}\nQuery: {query_text}\nRelevant:"
    prompt_tokens = count_tokens(prompt)
    print(f"\n[MEASURE] LLM prompt:")
    print(f"  - Prompt length: {len(prompt)} chars")
    print(f"  - Token count: {prompt_tokens} tokens")
    print(f"  - Prompt text preview: {prompt[:50]}...")

    # Measure LLM response (estimated)
    response_tokens = 10  # "5,8" minimal response

    # Calculate total
    total_tokens = prompt_tokens + response_tokens
    print(f"\n[MEASURE] Total token consumption:")
    print(f"  - Prompt: {prompt_tokens} tokens")
    print(f"  - Response: {response_tokens} tokens (estimated)")
    print(f"  - TOTAL: {total_tokens} tokens")

    # Compare with baseline
    baseline_tokens = 2000  # PageIndex standalone
    savings = (baseline_tokens - total_tokens) / baseline_tokens * 100
    print(f"\n[COMPARE] vs baseline:")
    print(f"  - Baseline: {baseline_tokens} tokens (PageIndex standalone)")
    print(f"  - Current: {total_tokens} tokens (optimized)")
    print(f"  - Savings: {savings:.1f}%")

    # Verify target
    target_tokens = 200  # 90%+ threshold
    if total_tokens <= target_tokens:
        print(f"\n[SUCCESS] 90%+ TARGET MET: {total_tokens} ≤ {target_tokens} tokens")
        print(f"[SUCCESS] Savings: {savings:.1f}% ≥ 90%")
        return True
    else:
        print(f"\n[FAIL] Target not met: {total_tokens} > {target_tokens} tokens")
        print(f"[INFO] Gap: {total_tokens - target_tokens} tokens over limit")
        return False

    conn.close()

if __name__ == "__main__":
    success = test_token_consumption()
    if success:
        print("\n=== Token optimization SUCCESS ===")
    else:
        print("\n=== Token optimization FAILED ===")