"""End-to-end retrieval + rerank smoke on a short generated article.

Flow: short PDF (2 topics) -> disposable pgvector container -> registry spans
-> hybrid query (keyword+vector+tree, real local MiniLM embeddings)
-> fuse_candidates (RRF) -> rerank_pipeline -> sanity assertions.

Run: python verification/smoke_retrieval_rerank_2026-09-05.py
Authorization: 16-15 disposable-DB pattern (one-shot container, tmpfs, --rm,
random credentials, programmatic DSN only, stop+cleanup at exit).
"""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PORT = 15443
DB = "rag_registry"
USER = "smoke"
PASSWORD = secrets.token_hex(12)
DSN = f"postgresql://{USER}:{PASSWORD}@127.0.0.1:{PORT}/{DB}"
CONTAINER = "rag_smoke_pg"


TOPIC_A = [
    "Urban Air Quality Management: city monitoring stations measure PM2.5, NO2 and ozone around the clock.",
    "The Air Quality Index (AQI) converts pollutant concentrations into a single public health score.",
    "Emission standards for vehicles and factories are the main policy lever for reducing smog episodes.",
]
TOPIC_B = [
    "A community composting program turns household food waste into nutrient rich compost.",
    "Compost improves soil health by adding organic matter and feeding soil microbes.",
    "Weekly compost bin collection reduces landfill volume and cuts methane emissions.",
]


def build_pdf(path: Path) -> None:
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path))
    y = 780
    c.setFont("Helvetica", 13)
    c.drawString(72, y, "Smoke Article: Two Community Topics")
    y -= 24
    for title, paras in (
        ("Part A - Urban Air Quality", TOPIC_A),
        ("Part B - Community Composting", TOPIC_B),
    ):
        c.setFont("Helvetica-Bold", 11)
        c.drawString(72, y, title)
        y -= 16
        c.setFont("Helvetica", 9)
        for p in paras:
            for line in _wrap(p, 95):
                c.drawString(72, y, line)
                y -= 11
            y -= 6
    c.save()


def _wrap(text: str, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return lines


def wait_docker(timeout_s: int = 180) -> None:
    print("[1] waiting for docker daemon ...", flush=True)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        r = subprocess.run(
            ["docker", "info", "--format", "ok"], capture_output=True, text=True
        )
        if r.returncode == 0 and "ok" in r.stdout:
            print("    docker ready", flush=True)
            return
        time.sleep(5)
    raise RuntimeError("docker daemon not reachable in time")


def start_pg() -> None:
    print("[2] starting disposable pgvector container ...", flush=True)
    subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)
    r = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--rm",
            "--name",
            CONTAINER,
            "-e",
            f"POSTGRES_USER={USER}",
            "-e",
            f"POSTGRES_PASSWORD={PASSWORD}",
            "-e",
            f"POSTGRES_DB={DB}",
            "-p",
            f"127.0.0.1:{PORT}:5432",
            "pgvector/pgvector:pg16",
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        raise RuntimeError("docker run failed: " + r.stderr.strip()[:300])
    deadline = time.time() + 90
    while time.time() < deadline:
        chk = subprocess.run(
            ["docker", "exec", CONTAINER, "pg_isready", "-U", USER, "-d", DB],
            capture_output=True,
            text=True,
        )
        if chk.returncode == 0:
            print("    postgres ready on 127.0.0.1:%d" % PORT, flush=True)
            return
        time.sleep(3)
    raise RuntimeError("postgres not ready in time")


def stop_pg() -> None:
    subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)
    print("[cleanup] container removed, credentials discarded", flush=True)


def apply_migrations(conn) -> int:
    mig = ROOT / "llamaindex_runtime" / "registry" / "migrations"
    files = sorted(mig.glob("*.sql"))
    with conn.cursor() as cur:
        for f in files:
            cur.execute(f.read_text(encoding="utf-8"))
    return len(files)


def main() -> int:
    from llamaindex_runtime.analysis.fusion import fuse_candidates, rerank_pipeline
    from llamaindex_runtime.entrypoints import query
    from llamaindex_runtime.entrypoints._query import (
        _map_backend_dict_to_hit,
        _map_node_to_hit,
    )
    from llamaindex_runtime.interfaces import CanonicalSpan
    from llamaindex_runtime.keyword import retrieve_keyword_hits
    from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter
    from llamaindex_runtime.tree import retrieve_tree_hits_from_pdf
    from llamaindex_runtime.vector import retrieve_vector_hits_from_pdf
    import psycopg

    work = ROOT / ".tmp" / "retrieval_smoke"
    work.mkdir(parents=True, exist_ok=True)
    pdf = work / "smoke_article.pdf"
    build_pdf(pdf)
    print("[0] article PDF built:", pdf, flush=True)

    wait_docker()
    start_pg()
    try:
        conn = psycopg.connect(DSN, autocommit=True)
        n = apply_migrations(conn)
        print(f"[3] {n} migrations applied", flush=True)
        registry = PostgresRegistryWriter(conn)
        reg = registry.register_document(
            source_path=pdf,
            source_uri="smoke://short-article-2026-09-05",
            title="Smoke Short Article",
        )
        version_id = reg.version_id
        print(
            f"[4] document registered: doc_id={reg.doc_id} version_id={version_id}",
            flush=True,
        )

        spans = []
        offset = 0
        for para in TOPIC_A + TOPIC_B:
            spans.append(
                CanonicalSpan(
                    doc_id=reg.doc_id,
                    version_id=version_id,
                    span_id=uuid.uuid5(uuid.NAMESPACE_URL, para),
                    text=para,
                    offset=offset,
                    page_no=1,
                )
            )
            offset += len(para) + 1
        registry.write_spans(version_id=version_id, spans=spans)
        print(f"[5] {len(spans)} canonical spans written to ledger", flush=True)

        from llamaindex_runtime.embeddings import SentenceTransformersEmbedding

        embed = SentenceTransformersEmbedding("all-MiniLM-L6-v2")
        print("[6] local MiniLM embedder ready", flush=True)

        failures = []
        cases = [
            (
                "How is urban air quality monitored and the AQI computed?",
                TOPIC_A,
                "air",
            ),
            ("How does composting food waste improve soil health?", TOPIC_B, "compost"),
        ]
        for qi, (qtext, topic_paras, topic_key) in enumerate(cases, 1):
            print(flush=True)
            print(f"=== QUERY {qi}: {qtext}", flush=True)
            result = query(
                source_path=pdf,
                query_text=qtext,
                mode="hybrid",
                embed_model=embed,
                registry=registry,
                version_id=version_id,
                limit=8,
            )
            assert result.mode == "hybrid", "mode must be hybrid"
            hits = list(result.hits)
            assert hits, "hybrid must return hits"
            scores = [h.score for h in hits]
            assert all(
                s is not None for s in scores
            ), "fused scores must be real numbers"
            assert all(
                scores[i] >= scores[i + 1] for i in range(len(scores) - 1)
            ), "fused hits must be score-descending"
            top_texts = [h.text for h in hits[:3]]
            on_topic = sum(1 for t in top_texts if topic_key in t.lower())
            print(
                f"  fused hits={len(hits)} scores[0..2]={[round(s, 4) for s in scores[:3]]} top3_on_topic={on_topic}/3",
                flush=True,
            )
            for h in hits[:3]:
                md = dict(h.metadata)
                prov = {
                    k: (str(v)[:36])
                    for k, v in md.items()
                    if k
                    in (
                        "span_id",
                        "version_id",
                        "source_paths",
                        "page_no",
                        "heading_path",
                        "backend_source",
                    )
                }
                print(
                    "    -", round(h.score, 4), "|", h.text[:80], "|", prov, flush=True
                )
            if on_topic < 2:
                failures.append(f"query{qi}: top3 on-topic {on_topic}/3")

            kw = list(
                retrieve_keyword_hits(registry, qtext, version_id=version_id, limit=50)
            )
            vec_raw = retrieve_vector_hits_from_pdf(
                pdf, query=qtext, embed_model=embed, similarity_top_k=3
            )
            vec = (
                [_map_backend_dict_to_hit(h) for h in vec_raw]
                if (vec_raw and isinstance(vec_raw[0], dict))
                else [_map_node_to_hit(h) for h in vec_raw]
            )
            tree_raw = retrieve_tree_hits_from_pdf(
                pdf, query=qtext, embed_model=embed, similarity_top_k=4
            )
            tree = (
                [_map_node_to_hit(h) for h in tree_raw]
                if not (tree_raw and isinstance(tree_raw[0], dict))
                else [_map_backend_dict_to_hit(h) for h in tree_raw]
            )
            fused = fuse_candidates({"keyword": kw, "vector": vec, "tree": tree})
            reranked = rerank_pipeline(fused)
            print(
                f"  per-path: keyword={len(kw)} vector={len(vec)} tree={len(tree)} -> fused={len(fused)} -> reranked={len(reranked)}",
                flush=True,
            )
            for rh in reranked[:3]:
                print(
                    "    *",
                    round(rh.rerank_score, 4),
                    sorted(rh.source_paths),
                    "|",
                    rh.text[:70],
                    flush=True,
                )
            assert reranked, "rerank pipeline must return hits"
            r_scores = [rh.rerank_score for rh in reranked]
            assert all(
                r_scores[i] >= r_scores[i + 1] for i in range(len(r_scores) - 1)
            ), "reranked must be score-descending"

        stop_pg()
        print(flush=True)
        if failures:
            print("SMOKE RESULT: FAIL ->", failures, flush=True)
            return 1
        print(
            "SMOKE RESULT: PASS - retrieval+fusion+rerank behaves sanely on the short article",
            flush=True,
        )
        return 0
    except Exception:
        stop_pg()
        raise


if __name__ == "__main__":
    sys.exit(main())
