from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

os.environ["RAG_TREE_HOTSPOT_SELECTOR"] = "hybrid_cluster"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=False)

MODULE_PATH = Path(__file__).resolve().parent / "run_validation.py"
spec = importlib.util.spec_from_file_location("phase13_run_validation", str(MODULE_PATH))
run_validation = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(run_validation)

from llamaindex_runtime.ingestion.pipeline import IngestionPipeline  # noqa: E402
from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter  # noqa: E402
from llamaindex_runtime.registry.tree_generator import TreeGenerator  # noqa: E402
from llamaindex_runtime.tree.runtime import (  # noqa: E402
    MISSING_CHUNK_ID,
    _build_path_to_root_from_stats,
    _cosine_similarity,
    _extract_keywords_from_query,
    _map_query_hits_to_backend_hits,
    retrieve_tree_hits_from_pdf,
)
from llamaindex_runtime.tree.semantic_distribution import (  # noqa: E402
    BaselineTreeBranchDecisionPolicy,
    HotspotSelectionContext,
    KeywordSpanHit,
    NodeSemanticHit,
    PersistedTreeSemanticDistributionAdapter,
    RecursiveTreeTraversalRunner,
    get_hotspot_selector,
)
from llamaindex_runtime.vector.loader import VectorLoader  # noqa: E402


def main() -> None:
    queries = run_validation.load_business_queries()
    q18 = next(q for q in queries if q.query_id == "Q18")
    print("Q18:", q18.query_text)

    db_url = os.environ["DATABASE_URL"]
    if not run_validation.database_is_reachable(db_url):
        run_validation.ensure_local_pgvector_container(db_url)
    run_validation.apply_migrations(
        database_url=db_url,
        migrations_dir=PROJECT_ROOT / "llamaindex_runtime/registry/migrations",
        migration_files=run_validation.FULL_MIGRATIONS,
    )

    conn = psycopg.connect(db_url)
    registry = PostgresRegistryWriter(conn)

    print("[INGEST]")
    ingest_result = IngestionPipeline(registry=registry).ingest(
        run_validation.CORPUS_PATH,
        title="[phase13-debug] PageIndex完整功能分析与集成方案",
    )
    version_id = ingest_result.version_id
    print("version_id", version_id)
    spans = registry.query_spans_by_version(version_id)
    print("spans", len(spans))

    print("[TREE]")
    generated = TreeGenerator().generate_tree(spans, version_id=version_id)
    registry.write_tree(
        version_id=version_id,
        nodes=generated["nodes"],
        node_spans=generated["node_spans"],
    )
    print(
        "tree_nodes",
        len(registry.query_tree_nodes_by_version(version_id)),
        "node_spans",
        len(registry.query_tree_node_spans_by_version(version_id)),
    )

    print("[VECTOR]")
    loader_result = VectorLoader(
        embed_dim=run_validation.EMBED_DIM,
        embedder=run_validation.RealEmbedder(),
    ).load(conn, version_id)
    print("vector_loader_result", loader_result.get("count"))
    print(
        "chunks",
        len(registry.query_vector_chunks_by_version(version_id)),
        "chunk_spans",
        len(registry.query_vector_chunk_spans_by_version(version_id)),
    )

    embed_model = run_validation.RealEmbedding()
    query_embedding = embed_model.get_query_embedding(q18.query_text)
    adapter = PersistedTreeSemanticDistributionAdapter()
    distribution_report = adapter.analyze_tree_semantic_distribution(
        version_id=version_id,
        registry=registry,
    )
    node_stats = distribution_report["node_stats"]
    print("node_stats", len(node_stats), "tree_signals", distribution_report.get("tree_signals"))
    if node_stats:
        print("first stats keys", sorted(node_stats[0].keys()))
        print(
            "route_nodes",
            sum(1 for stats in node_stats if stats.get("is_route_node")),
            "direct_chunk_stats",
            sum(1 for stats in node_stats if stats.get("chunk_ids")),
        )

    span_rows = registry.query_tree_node_spans_by_version(version_id)
    span_ids_by_node = {}
    for row in span_rows:
        span_ids_by_node.setdefault(row["node_id"], []).append(row["span_id"])

    node_by_id_lookup = {stats["node_id"]: stats for stats in node_stats}
    vector_candidates = []
    for stats in node_stats:
        node_id = stats.get("node_id")
        prototype = stats.get("prototype_embedding") or stats.get("centroid")
        if node_id is None or not prototype:
            continue
        similarity = _cosine_similarity(query_embedding, prototype)
        if similarity <= 0.0:
            continue
        parent_node_id = stats.get("parent_node_id")
        vector_candidates.append(
            NodeSemanticHit(
                node_id=node_id,
                similarity=similarity,
                heading_path=stats.get("heading_path"),
                parent_node_id=parent_node_id,
                path_to_root=_build_path_to_root_from_stats(
                    node_id=node_id,
                    parent_node_id=parent_node_id,
                    node_by_id=node_by_id_lookup,
                ),
            )
        )

    query_keywords = _extract_keywords_from_query(q18.query_text)
    keyword_hits = []
    for stats in node_stats:
        node_id = stats.get("node_id")
        heading_path = stats.get("heading_path", "")
        if node_id is None or not heading_path:
            continue
        matched_keywords = tuple(
            keyword for keyword in query_keywords if keyword.lower() in heading_path.lower()
        )
        if matched_keywords:
            span_ids = span_ids_by_node.get(node_id, [])
            if span_ids:
                keyword_hits.append(
                    KeywordSpanHit(
                        span_id=span_ids[0],
                        node_id=node_id,
                        score=0.6,
                        matched_terms=matched_keywords,
                        source="heading_keyword_match",
                    )
                )

    context = HotspotSelectionContext(
        query_text=q18.query_text,
        query_embedding=query_embedding,
        node_stats=node_by_id_lookup,
        tree_signals=distribution_report["tree_signals"],
        vector_candidates=vector_candidates,
        keyword_hits=keyword_hits,
        rerank_scores=None,
        parent_to_children=distribution_report.get("parent_to_children", {}),
    )
    hotspots = get_hotspot_selector("hybrid_cluster").select_hotspots(
        context=context,
        limit=5,
    )
    print(
        "keywords",
        query_keywords,
        "vector_candidates",
        len(vector_candidates),
        "keyword_hits",
        len(keyword_hits),
        "hotspots",
        len(hotspots),
    )
    for index, hotspot in enumerate(hotspots, start=1):
        stats = node_by_id_lookup.get(hotspot.node_id, {})
        print(
            f"HS{index} node={hotspot.node_id} reason={hotspot.reason} "
            f"score={hotspot.score:.4f} chunks={len(stats.get('chunk_ids', []))} "
            f"subtree={len(stats.get('subtree_chunk_ids', []))} "
            f"parent={stats.get('parent_node_id')} heading={stats.get('heading_path')}"
        )

    runner = RecursiveTreeTraversalRunner()
    policy = BaselineTreeBranchDecisionPolicy(
        dispersion_threshold=1.0,
        entropy_threshold=0.5,
    )
    all_query_hits = []
    for index, hotspot in enumerate(hotspots, start=1):
        query_hits = runner.traverse_tree_for_query(
            version_id=version_id,
            query_embedding=query_embedding,
            registry=registry,
            policy=policy,
            adapter=adapter,
            start_node_id=hotspot.node_id,
            hotspot_node_id=hotspot.node_id,
        )
        print(f"  traverse HS{index}: {len(query_hits)} query hits")
        for hit in query_hits[:10]:
            print(
                f"    qhit node={hit.node_id} chunk={hit.chunk_id} "
                f"missing={hit.chunk_id == MISSING_CHUNK_ID} "
                f"depth={hit.drill_depth} score={hit.similarity_score:.4f}"
            )
        all_query_hits.extend(query_hits)
        if len(all_query_hits) >= 5:
            break

    nodes = registry.query_tree_nodes_by_version(version_id)
    node_by_id = {node["node_id"]: node for node in nodes}
    backend_hits = _map_query_hits_to_backend_hits(
        query_hits=all_query_hits,
        node_by_id=node_by_id,
        span_ids_by_node=span_ids_by_node,
        registry=registry,
        version_id=version_id,
    )
    print("mapped backend_hits", len(backend_hits))
    for hit in backend_hits[:10]:
        print(
            f"  bhit node={hit['node_id']} chunk={hit['chunk_id']} "
            f"depth={hit['drill_depth']} source={hit['backend_source']} "
            f"preview={hit['text_preview'][:60]}"
        )

    public_hits = retrieve_tree_hits_from_pdf(
        run_validation.CORPUS_PATH,
        query=q18.query_text,
        embed_model=embed_model,
        similarity_top_k=5,
        registry=registry,
        version_id=version_id,
        backend_type="embedding",
    )
    print("public_hits", len(public_hits))
    for hit in public_hits:
        print(
            f"  public node={hit.get('node_id')} chunk={hit.get('chunk_id')} "
            f"source={hit.get('backend_source')} missing={hit.get('chunk_id') == MISSING_CHUNK_ID} "
            f"preview={str(hit.get('text_preview'))[:60]}"
        )

    conn.rollback()
    conn.close()


if __name__ == "__main__":
    main()
