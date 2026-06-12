"""White-box demo for subtree-hotspot semantic tree retrieval.

This script exercises the real persisted index/retrieval path:
1. register a real temporary markdown document in PostgreSQL
2. persist canonical_spans
3. build tree_nodes + tree_node_spans with TreeGenerator
4. materialize vector_chunks + embeddings with VectorLoader
5. run semantic tree retrieval via SubtreeHotspotSelector -> RecursiveTreeTraversalRunner
6. print evidence-bearing final hits and navigation metadata

No retrieval results are mocked.  The only controlled part is the tiny source
fixture, which makes the intended parent-route/child-evidence behavior visible.
"""

from __future__ import annotations

import io
import os
import sys
import uuid
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402
import psycopg  # noqa: E402

from llamaindex_runtime.interfaces import CanonicalSpan  # noqa: E402
from llamaindex_runtime.registry.postgres_adapter import (
    PostgresRegistryWriter,
)  # noqa: E402
from llamaindex_runtime.registry.tree_generator import TreeGenerator  # noqa: E402
from llamaindex_runtime.tree.runtime import retrieve_tree_hits_from_pdf  # noqa: E402
from llamaindex_runtime.tree.semantic_distribution import (  # noqa: E402
    PersistedTreeSemanticDistributionAdapter,
    SubtreeHotspotSelector,
)
from llamaindex_runtime.vector.embedder import DeterministicEmbedder  # noqa: E402
from llamaindex_runtime.vector.loader import VectorLoader  # noqa: E402


class DeterministicQueryEmbedding:
    """Tiny adapter exposing LlamaIndex-like get_query_embedding()."""

    def __init__(self, dim: int = 16) -> None:
        self._embedder = DeterministicEmbedder(dim=dim)

    def get_query_embedding(self, query: str) -> list[float]:
        return self._embedder.embed_text(query)


def _write_fixture() -> Path:
    fixture_dir = REPO_ROOT / "verification" / "hotspot-semantic-demo"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    source_path = fixture_dir / f"hotspot-source-{uuid.uuid4()}.md"
    source_path.write_text(
        "\n".join(
            [
                "# PageIndex 完整功能分析与集成方案",
                "",
                "## PageIndex vs 当前实现对比",
                "",
                "### 功能矩阵",
                "PageIndex 当前实现 功能矩阵 对比：PageIndex 支持目录树导航、页面级结构、LLM 选择节点；当前实现需要保留 provenance、tree_node_spans、vector_chunks 和 evidence chain。",
                "",
                "### Token 消耗对比",
                "PageIndex 当前实现 Token 消耗对比：热点子树先定位父节点，然后多跳下钻，只返回有 chunk evidence 的叶子内容，避免返回父节点全文。",
                "",
                "## 无关章节",
                "这部分讨论部署清单、环境变量和日志格式，和 PageIndex 功能矩阵对比无关。",
            ]
        ),
        encoding="utf-8",
    )
    return source_path


def _build_spans(*, doc_id: uuid.UUID, version_id: uuid.UUID) -> list[CanonicalSpan]:
    rows = [
        (
            "PageIndex 完整功能分析与集成方案 > PageIndex vs 当前实现对比 > 功能矩阵",
            "PageIndex 当前实现 功能矩阵 对比：PageIndex 支持目录树导航、页面级结构、LLM 选择节点；当前实现需要保留 provenance、tree_node_spans、vector_chunks 和 evidence chain。",
            100,
        ),
        (
            "PageIndex 完整功能分析与集成方案 > PageIndex vs 当前实现对比 > Token 消耗对比",
            "PageIndex 当前实现 Token 消耗对比：热点子树先定位父节点，然后多跳下钻，只返回有 chunk evidence 的叶子内容，避免返回父节点全文。",
            260,
        ),
        (
            "PageIndex 完整功能分析与集成方案 > 无关章节",
            "部署清单、环境变量、日志格式，与 PageIndex 功能矩阵差异问题无关。",
            420,
        ),
    ]
    spans: list[CanonicalSpan] = []
    for heading_path, text, offset in rows:
        headings = tuple(heading_path.split(" > "))
        span_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"{doc_id}:{version_id}:{heading_path}:{offset}:{text}",
        )
        spans.append(
            CanonicalSpan(
                doc_id=doc_id,
                version_id=version_id,
                span_id=span_id,
                text=text,
                page_no=1,
                headings=headings,
                offset=offset,
            )
        )
    return spans


def main() -> int:
    load_dotenv(REPO_ROOT / ".env")
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("[FAIL] DATABASE_URL is not configured")
        return 2

    source_path = _write_fixture()
    query = "PageIndex 当前实现 功能矩阵 Token 消耗 对比"
    embed_model = DeterministicQueryEmbedding(dim=16)

    print("=" * 88)
    print("Subtree hotspot semantic retrieval white-box demo")
    print("=" * 88)
    print(f"source_path: {source_path}")
    print(f"query: {query}")

    with psycopg.connect(db_url) as conn:
        registry = PostgresRegistryWriter(conn)
        registered = registry.register_document(
            source_path=source_path,
            source_uri=source_path.as_uri(),
            title="hotspot semantic demo",
        )
        version_id = registered.version_id
        doc_id = registered.doc_id
        print(f"\n[1] registered doc_id={doc_id} version_id={version_id}")

        spans = _build_spans(doc_id=doc_id, version_id=version_id)
        registry.write_spans(version_id=version_id, spans=spans)
        persisted_spans = registry.query_spans_by_version(version_id)
        print(f"[2] canonical_spans={len(persisted_spans)}")
        for span in persisted_spans:
            print(
                f"    span heading={span['heading_path']} text={span['raw_text'][:48]}..."
            )

        generated = TreeGenerator().generate_tree(
            persisted_spans, version_id=version_id
        )
        registry.write_tree(
            version_id=version_id,
            nodes=generated["nodes"],
            node_spans=generated["node_spans"],
        )
        nodes = registry.query_tree_nodes_by_version(version_id)
        node_spans = registry.query_tree_node_spans_by_version(version_id)
        print(f"[3] tree_nodes={len(nodes)} tree_node_spans={len(node_spans)}")
        for node in nodes:
            direct_span_count = sum(
                1 for row in node_spans if row["node_id"] == node["node_id"]
            )
            print(
                "    node level={level} spans={spans} id={id} path={path}".format(
                    level=node.get("level_no"),
                    spans=direct_span_count,
                    id=node["node_id"],
                    path=node.get("heading_path"),
                )
            )

        loader_result = VectorLoader(embed_dim=16).load(conn, version_id)
        chunks = registry.query_vector_chunks_by_version(version_id)
        print(f"[4] vector_loader={loader_result} vector_chunks={len(chunks)}")
        for chunk in chunks:
            print(
                "    chunk node_id={node_id} chunk_id={chunk_id} heading={heading}".format(
                    node_id=chunk.get("node_id"),
                    chunk_id=chunk["chunk_id"],
                    heading=chunk.get("heading_path"),
                )
            )

        report = PersistedTreeSemanticDistributionAdapter().analyze_tree_semantic_distribution(
            version_id=version_id,
            registry=registry,
        )
        query_embedding = embed_model.get_query_embedding(query)
        hotspots = SubtreeHotspotSelector().select_hotspots(
            query_embedding=query_embedding,
            node_stats=report["node_stats"],
            tree_signals=report["tree_signals"],
            limit=3,
        )
        print("[5] semantic stats:")
        for stats in report["node_stats"]:
            print(
                "    stats route={route} direct={direct} subtree={subtree} support={support} path={path}".format(
                    route=stats.get("is_route_node"),
                    direct=stats.get("direct_support_count"),
                    subtree=len(stats.get("subtree_chunk_ids", [])),
                    support=stats.get("support_count"),
                    path=stats.get("heading_path"),
                )
            )
        print("[6] selected hotspots:")
        for hotspot in hotspots:
            node = next(item for item in nodes if item["node_id"] == hotspot.node_id)
            print(
                "    score={score:.4f} reason={reason} support={support} path={path}".format(
                    score=hotspot.score,
                    reason=hotspot.reason,
                    support=hotspot.support_count,
                    path=node.get("heading_path"),
                )
            )

        hits = retrieve_tree_hits_from_pdf(
            source_path,
            query=query,
            embed_model=embed_model,  # type: ignore[arg-type]
            similarity_top_k=5,
            registry=registry,
            version_id=version_id,
            backend_type="embedding",
        )
        print("[7] final hits (evidence-bearing only):")
        for index, hit in enumerate(hits, start=1):
            print(f"\n    HIT #{index}")
            print(f"      heading_path={hit.get('heading_path')}")
            print(f"      chunk_id={hit.get('chunk_id')}")
            print(f"      chunk_id_missing={hit.get('chunk_id_missing')}")
            print(f"      hotspot_node_id={hit.get('hotspot_node_id')}")
            print(f"      navigation_path={hit.get('navigation_path')}")
            print(f"      retrieval_path={hit.get('retrieval_path')}")
            print(f"      text_preview={hit.get('text_preview')}")

        zero_chunks = [hit for hit in hits if hit.get("chunk_id_missing") is True]
        parent_only_hits = [hit for hit in hits if not hit.get("span_ids")]
        print("\n[8] assertions:")
        print(f"    zero_chunk_hits={len(zero_chunks)}")
        print(f"    parent_only_hits={len(parent_only_hits)}")
        print(f"    total_hits={len(hits)}")
        if not hits or zero_chunks or parent_only_hits:
            print("[FAIL] expected evidence-bearing hits with normal chunk IDs")
            return 1
        print(
            "[OK] parent hotspots were used as navigation; final hits are evidence-bearing chunks"
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
