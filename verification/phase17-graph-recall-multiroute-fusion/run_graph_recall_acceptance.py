# ruff: noqa: E402
"""Phase 17 graph-recall acceptance gate runner (Wave 1).

Deterministic gate over the graph-recall multiroute-fusion proof chain.
The pipeline drives exactly the frozen components pinned by the W7 wave-1
contract: UIE mention/triple mapping, exact-name identity resolution,
review-basket construction, evidence-keyword relation review, custom-KG
payload assembly, and fused graph recall.  Live mode spawns the UIE
extraction worker as a UTF-8 subprocess (env-configured venv python +
worker script) and builds a PG-backed LightRAG through the
_pg_lightrag_factory seam; the only other I/O is the single-line
redacted evidence file written next to this module.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import types
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
from live_bridge import (  # type: ignore[import-not-found]
    _AqueryDataAdapter,
    _as_embedding_array,  # noqa: F401  (re-exported for the acceptance tests)
    _LoopBoundRag,
    _normalize_chunk_source_ids,  # noqa: F401
    _pg_lightrag_factory,
    _start_rag_loop,
    _SyncIngestAdapter,
)

from llamaindex_runtime.analysis.graph_channel import GraphHit, ranked_fusion
from llamaindex_runtime.entity import uie_adapter
from llamaindex_runtime.entity.identity import resolve_identities
from llamaindex_runtime.entity.relation_review import (
    EvidenceRef,
    RelationClaim,
    review_relation_claims,
)
from llamaindex_runtime.entity.review_basket import build_review_basket
from llamaindex_runtime.extraction import trial
from llamaindex_runtime.graph.lightrag_backend import (
    CustomKgChunk,
    CustomKgEntity,
    CustomKgPayload,
    CustomKgRelation,
)

# The approval-test harness loads this module with
# importlib.util.spec_from_file_location + module_from_spec and then
# exec_module, WITHOUT inserting it into sys.modules.  With the
# ``from __future__ import annotations`` future import above, every
# annotation is a string, and dataclasses._is_type() resolves those
# strings through sys.modules[cls.__module__].__dict__ (dataclasses.py
# line 712).  A module not registered there crashes with
# AttributeError: NoneType object has no attribute __dict__ at the
# first @dataclass definition.  Register a placeholder module that
# shares this module globals so frozen DTO classes can be defined
# under that loader.
if sys.modules.get(__name__) is None:
    _run_graph_recall_acceptance_module: types.ModuleType = types.ModuleType(__name__)
    _run_graph_recall_acceptance_module.__dict__.update(globals())
    sys.modules[__name__] = _run_graph_recall_acceptance_module

SKIPPED_STATUS: str = "skipped_not_entered"
FAILED_STATUS: str = "executed_failed"
OK_STATUS: str = "executed"
SKIP_EXIT: int = 1
FAIL_EXIT: int = 3
OK_EXIT: int = 0
AUTH_ENV: str = "OKF_GRAPH_RECALL_ACCEPTANCE_AUTHORIZED"
DISPOSABLE_ENV: str = "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE"
EXPECTED_DATABASE_ENV: str = "OKF_REBUILD_EXPECTED_DATABASE"
EVIDENCE_NAME: str = "graph_recall_acceptance_evidence.md"
GATE_BATCH_ID: str = "gate-batch"
VERSION_ID: str = str(uuid.uuid5(uuid.NAMESPACE_URL, "phase17-gate-version-v1"))
RECALL_QUERY: str = "华为的总部在哪里"
RECALL_HL_KEYWORDS: tuple[str, ...] = ("总部",)
RECALL_LL_KEYWORDS: tuple[str, ...] = ("华为",)
SAMPLE_TEXTS: tuple[str, ...] = (
    "李雷在北京使用华为Mate60",
    "韩梅梅明天去上海出差",
    "华为发布了新款手机",
)
VERIFICATION_DIR: Path = Path(__file__).resolve().parent


@dataclass(frozen=True)
class ExtractionEntity:
    text: str
    label: str
    char_start: int
    char_end: int
    confidence: float | None = 0.9


@dataclass(frozen=True)
class ExtractionRelation:
    subject_text: str
    subject_type: str
    relation: str
    object_text: str
    object_type: str
    source_text: str


@dataclass(frozen=True)
class DocumentExtraction:
    document_id: str
    source_text: str
    normalized_text: str
    entities: tuple[ExtractionEntity, ...]
    relations: tuple[ExtractionRelation, ...]


@dataclass(frozen=True)
class ExtractionBundle:
    documents: tuple[DocumentExtraction, ...]


@dataclass(frozen=True)
class AcceptanceDeps:
    trial_engine: object
    extractor: object
    reviewer: object
    ingestor: object
    recall: object
    bm25_titles: object


def build_gate_bundle() -> ExtractionBundle:
    """Canonical gate fixture pinned by the W7 wave-1 contract."""
    return ExtractionBundle(
        documents=(
            DocumentExtraction(
                document_id=str(uuid.uuid5(uuid.NAMESPACE_URL, "phase17-gate-doc-1")),
                source_text="李雷在北京使用华为Mate60",
                normalized_text="李雷在北京使用华为Mate60",
                entities=(
                    ExtractionEntity("李雷", "人名", 0, 2, 0.9),
                    ExtractionEntity("北京", "地名", 3, 5, 0.9),
                    ExtractionEntity("华为Mate60", "产品名", 7, 15, 0.9),
                ),
                relations=(
                    ExtractionRelation(
                        "李雷",
                        "人名",
                        "使用",
                        "华为Mate60",
                        "产品名",
                        "李雷在北京使用华为Mate60",
                    ),
                ),
            ),
            DocumentExtraction(
                document_id=str(uuid.uuid5(uuid.NAMESPACE_URL, "phase17-gate-doc-2")),
                source_text="韩梅梅明天去上海出差",
                normalized_text="韩梅梅明天去上海出差",
                entities=(
                    ExtractionEntity("韩梅梅", "人名", 0, 3, 0.9),
                    ExtractionEntity("上海", "地名", 6, 8, 0.9),
                ),
                relations=(),
            ),
            DocumentExtraction(
                document_id=str(uuid.uuid5(uuid.NAMESPACE_URL, "phase17-gate-doc-3")),
                source_text="华为发布了新款手机",
                normalized_text="华为发布了新款手机",
                entities=(
                    ExtractionEntity("华为", "公司名", 0, 2, 0.9),
                    ExtractionEntity("手机", "产品名", 7, 9, 0.9),
                ),
                relations=(
                    ExtractionRelation(
                        "华为",
                        "公司名",
                        "发布",
                        "手机",
                        "产品名",
                        "华为发布了新款手机",
                    ),
                ),
            ),
        )
    )


def _first_span_id(candidates: Sequence[object], mention_text: str) -> str | None:
    """First candidate span id whose mention_text equals the target exactly."""
    for candidate in candidates:
        if getattr(candidate, "mention_text", None) == mention_text:
            return getattr(candidate, "span_id", None)
    return None


def run_pipeline(
    bundle: ExtractionBundle,
    *,
    batch_id: str,
    route: str,
    coverage_ratio: float,
    reviewer: object,
    ingestor: object,
    recall: object,
    bm25_titles: object,
) -> dict[str, object]:
    """Run the frozen pipeline; return a redacted evidence dict.

    Values are numbers plus the route enum name only -- no corpus text, no
    entity names, no quotes ever reach the returned dict.
    """
    # 1. Entity mentions, per document, via the frozen UIE adapter.
    all_mentions: list[object] = []
    rejected_mentions_count: int = 0
    candidates_by_document: dict[str, tuple[object, ...]] = {}
    for doc in bundle.documents:
        rows: list[dict[str, object]] = []
        for entity in doc.entities:
            row: dict[str, object] = {
                "text": entity.text,
                "label": entity.label,
                "char_start": entity.char_start,
                "char_end": entity.char_end,
            }
            if entity.confidence is not None:
                row["confidence"] = entity.confidence
            rows.append(row)
        mapped = uie_adapter.map_entity_mentions(
            rows,
            document_id=doc.document_id,
            version_id=VERSION_ID,
            normalized_text=doc.normalized_text,
        )
        all_mentions.extend(mapped.candidates)
        candidates_by_document[doc.document_id] = mapped.candidates
        rejected_mentions_count += len(mapped.rejected)
    mentions_count: int = len(all_mentions)

    # 2. Exact-name identity resolution (frozen).
    identities = resolve_identities(all_mentions)
    identities_count: int = len(identities)

    # 3. Review basket over mentions x identities (frozen).
    basket = build_review_basket(all_mentions, identities)
    basket_items: int = len(basket.items)
    basket_pending: int = basket.pending_count

    # 4. span_id -> normalized identity name.
    span_to_name: dict[str, str] = {}
    for identity in identities:
        for span_id in identity.member_span_ids:
            span_to_name[span_id] = identity.normalized_name

    # 5-6. Relation triples + span linking -> claims.
    claims: list[RelationClaim] = []
    relations_total: int = 0
    relations_unlinked: int = 0
    for doc in bundle.documents:
        if not doc.relations:
            continue
        relation_rows = [
            {
                "subject_text": item.subject_text,
                "subject_type": item.subject_type,
                "relation": item.relation,
                "object_text": item.object_text,
                "object_type": item.object_type,
                "source_text": item.source_text,
            }
            for item in doc.relations
        ]
        doc_candidates = candidates_by_document[doc.document_id]
        relation_mapped = uie_adapter.map_relation_triples(
            relation_rows,
            uie_adapter.DEFAULT_RELATION_SCHEMA,
            document_id=doc.document_id,
            version_id=VERSION_ID,
            normalized_text=doc.normalized_text,
            candidates=doc_candidates,
        )
        for triple in relation_mapped.triples:
            relations_total += 1
            subject_span_id = _first_span_id(doc_candidates, triple.subject_text)
            object_span_id = _first_span_id(doc_candidates, triple.object_text)
            if (
                subject_span_id is None
                or object_span_id is None
                or subject_span_id == object_span_id
            ):
                relations_unlinked += 1
                continue
            claims.append(
                RelationClaim(
                    subject=triple.subject_text,
                    predicate=triple.relation,
                    object=triple.object_text,
                    subject_span_id=subject_span_id,
                    object_span_id=object_span_id,
                    evidence=(
                        EvidenceRef(source=doc.document_id, quote=triple.source_text),
                    ),
                )
            )

    # 7. Evidence review (frozen).
    outcome = review_relation_claims(claims, reviewer)
    relations_supported: int = len(outcome.supported)
    relations_pending: int = len(outcome.basket.items)

    # 8. Custom-KG payload.
    payload = CustomKgPayload(
        entities=tuple(
            CustomKgEntity(entity_name=identity.normalized_name)
            for identity in identities
        ),
        relations=tuple(
            CustomKgRelation(
                src_id=src,
                tgt_id=tgt,
                description=f"{src} {item.claim.predicate} {tgt}",
                keywords=item.claim.predicate,
            )
            for item in outcome.supported
            for src in (span_to_name.get(item.claim.subject_span_id),)
            for tgt in (span_to_name.get(item.claim.object_span_id),)
            if src is not None and tgt is not None
        ),
        chunks=tuple(
            CustomKgChunk(
                content=doc.source_text,
                source_id=doc.document_id,
                file_path=None,
            )
            for doc in bundle.documents
        ),
    )

    # 9. Ingestion receipt.
    # F1 spec amendment (final review M1): a fresh disposable workspace has
    # no pre-existing entities, so nothing is known and every payload entity
    # is inserted; a real pre-existing registry set belongs to the
    # materialization wave.
    receipt = cast(Any, ingestor).ingest(payload, known_entity_names=frozenset())
    ingest_entities: int = len(receipt.inserted_entities)
    ingest_relations: int = len(receipt.inserted_relations)
    ingest_chunks: int = len(receipt.inserted_chunks)

    # 10. Fused graph recall.
    hits = cast(Any, recall)(
        RECALL_QUERY,
        hl_keywords=RECALL_HL_KEYWORDS,
        ll_keywords=RECALL_LL_KEYWORDS,
        top_k=10,
    )
    fused = ranked_fusion(hits, cast(Any, bm25_titles)())
    fusion_max_score: float = max((hit.score for hit in fused), default=0.0)
    recall_hit_count: int = len(hits)

    return {
        "batch_id": batch_id,
        "route": route,
        "coverage_ratio": coverage_ratio,
        "mentions_count": mentions_count,
        "rejected_mentions_count": rejected_mentions_count,
        "identities_count": identities_count,
        "basket_items": basket_items,
        "basket_pending": basket_pending,
        "relations_total": relations_total,
        "relations_supported": relations_supported,
        "relations_pending": relations_pending,
        "relations_unlinked": relations_unlinked,
        "ingest_entities": ingest_entities,
        "ingest_relations": ingest_relations,
        "ingest_chunks": ingest_chunks,
        "recall_hit_count": recall_hit_count,
        "fusion_max_score": fusion_max_score,
    }


def _run_proof_steps(deps: AcceptanceDeps) -> dict[str, object]:
    trial_engine = cast(Any, deps.trial_engine)
    extractor = cast(Any, deps.extractor)
    report = trial_engine.run_trial(GATE_BATCH_ID, SAMPLE_TEXTS)
    decision = trial.decide_route(report)
    bundle = extractor.extract(SAMPLE_TEXTS)
    return run_pipeline(
        bundle,
        batch_id=GATE_BATCH_ID,
        route=decision.route.name,
        coverage_ratio=decision.coverage_ratio,
        reviewer=deps.reviewer,
        ingestor=deps.ingestor,
        recall=cast(Any, deps.recall),
        bm25_titles=cast(Any, deps.bm25_titles),
    )


def _write_evidence(payload: Mapping[str, object]) -> Path:
    path = VERIFICATION_DIR / EVIDENCE_NAME
    body = json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    path.write_text(body + "\n", encoding="utf-8")
    return path


class _EnvUieExtractor:
    """Live extractor: shells out to the UIE venv worker subprocess.

    Mirrors uie_batch.SubprocessUieBatchExtractor (W7 review Security-1:
    provider key prefixes are stripped from the inherited environment)
    but reuses THIS module's frozen extraction DTOs directly.  The venv
    python and worker script paths come from the environment so the
    gate never hardcodes machine layout.
    """

    def __init__(self, *, timeout_s: float = 600.0) -> None:
        raw_python = os.environ.get("PHASE17_UIE_PYTHON")
        if not raw_python:
            raise ValueError(
                "PHASE17_UIE_PYTHON must be set to the UIE venv python path"
            )
        raw_worker = os.environ.get("PHASE17_UIE_WORKER")
        if not raw_worker:
            raise ValueError(
                "PHASE17_UIE_WORKER must be set to the UIE worker script path"
            )
        for label, raw in (
            ("PHASE17_UIE_PYTHON", raw_python),
            ("PHASE17_UIE_WORKER", raw_worker),
        ):
            resolved = Path(raw)
            if not resolved.is_absolute():
                raise ValueError(f"{label} must be an absolute path: {raw!r}")
            if not resolved.is_file():
                raise ValueError(f"{label} does not exist: {raw!r}")
        self.venv_python = raw_python
        self.worker_script = raw_worker
        self.timeout_s = timeout_s

    def extract(self, texts: Sequence[str]) -> object:
        argv = [self.venv_python, self.worker_script]
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("OPENAI_", "DASHSCOPE_"))
        }
        env["PYTHONUTF8"] = "1"
        proc = subprocess.run(
            argv,
            input=json.dumps({"texts": [str(t) for t in texts]}).encode("utf-8"),
            capture_output=True,
            check=False,
            timeout=self.timeout_s,
            env=env,
        )
        if proc.returncode != 0:
            raw_stderr = proc.stderr or b""
            stderr_tail = raw_stderr.decode("utf-8", errors="replace").strip()[-500:]
            raise RuntimeError(
                f"uie extraction worker failed (rc={proc.returncode}): {stderr_tail}"
            )
        body = json.loads(proc.stdout.decode("utf-8"))
        documents: list[DocumentExtraction] = []
        for entry in body["documents"]:
            documents.append(
                DocumentExtraction(
                    document_id=str(entry["document_id"]),
                    source_text=str(entry["source_text"]),
                    normalized_text=str(entry["normalized_text"]),
                    entities=tuple(
                        ExtractionEntity(
                            text=str(e["text"]),
                            label=str(e["label"]),
                            char_start=int(e["char_start"]),
                            char_end=int(e["char_end"]),
                            confidence=e.get("confidence"),
                        )
                        for e in entry["entities"]
                    ),
                    relations=tuple(
                        ExtractionRelation(
                            subject_text=str(r["subject_text"]),
                            subject_type=str(r["subject_type"]),
                            relation=str(r["relation"]),
                            object_text=str(r["object_text"]),
                            object_type=str(r["object_type"]),
                            source_text=str(r["source_text"]),
                        )
                        for r in entry["relations"]
                    ),
                )
            )
        return ExtractionBundle(documents=tuple(documents))


def build_deps(target_uri: str) -> AcceptanceDeps:
    """Live dependency assembly (lazy imports only).

    Tests exercise it with faked seams; live deps are wired lazily here.
    Credentials and endpoints come from the environment.  A missing
    "lightrag" package surfaces as RuntimeError from the PG factory.
    Rag coroutines all run on one persistent daemon event loop (asyncpg
    pool loop affinity).
    """
    from llamaindex_runtime import llm_openai
    from llamaindex_runtime.analysis import graph_channel
    from llamaindex_runtime.graph import lightrag_backend

    relation_types = frozenset(
        ("所在地", "所属公司", "任职于", "发布", "总部位于", "使用", "通话", "前往")
    )
    client = llm_openai.client.OpenAICompatClient(
        model=os.environ.get("LLM_MODEL", "gpt-5.4-mini"),
        base_url=os.environ.get("OPENAI_BASE_URL", "http://127.0.0.1:8317/v1"),
        api_key=os.environ.get("OPENAI_API_KEY", ""),
    )
    trial_engine = llm_openai.trial_engine.LlmTrialEngine(
        client, relation_types=relation_types
    )
    reviewer = llm_openai.relation_reviewer.LlmRelationReviewer(client)
    config = lightrag_backend.LightragRuntimeConfig(
        workspace="phase17-gate",
        embedding_base_url=os.environ.get(
            "DASHSCOPE_EMBEDDING_BASE_URL", "http://127.0.0.1:8888/v1"
        ),
        embedding_model=os.environ.get(
            "DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v4"
        ),
        embedding_dimensions=int(
            os.environ.get("DASHSCOPE_EMBEDDING_DIMENSIONS", "1024")
        ),
    )
    embedding = lightrag_backend.DashScopeEmbedding(
        model=config.embedding_model,
        base_url=config.embedding_base_url,
        api_key=os.environ.get("DASHSCOPE_API_KEY", ""),
        dimensions=config.embedding_dimensions,
    )
    ingestor = lightrag_backend.LightragKgIngestor(
        config=config,
        embedding=embedding,
        lightrag_factory=_pg_lightrag_factory,
    )
    # W7 review (General-4): locked coupling to the frozen private
    # _ensure_rag; a public accessor should replace this in a later wave.
    _, loop = _start_rag_loop()
    rag = ingestor._ensure_rag()
    # LightRAG requires async initialize_storages; PG storages create
    # their namespace locks there.
    asyncio.run_coroutine_threadsafe(rag.initialize_storages(), loop).result(
        timeout=600.0
    )
    channel = graph_channel.LightragGraphChannel(
        _AqueryDataAdapter(_LoopBoundRag(rag, loop), rag, loop)
    )

    def _gate_recall(
        query: str,
        *,
        hl_keywords: Sequence[str],
        ll_keywords: Sequence[str],
        top_k: int = 10,
    ) -> tuple[GraphHit, ...]:
        return channel.fetch(
            query,
            hl_keywords=hl_keywords,
            ll_keywords=ll_keywords,
            top_k=top_k,
        )

    def _empty_bm25_titles() -> tuple[str, ...]:
        return ()

    extractor: object = _EnvUieExtractor()
    return AcceptanceDeps(
        trial_engine=trial_engine,
        extractor=extractor,
        reviewer=reviewer,
        ingestor=_SyncIngestAdapter(ingestor, loop),
        recall=_gate_recall,
        bm25_titles=_empty_bm25_titles,
    )


def main(
    argv: Sequence[str],
    *,
    target_uri: str,
    deps_factory: Callable[[str], AcceptanceDeps] | None = None,
) -> int:
    if argv:
        raise ValueError(
            "acceptance runner takes no command line arguments; "
            "target_uri is programmatic only"
        )
    if (
        os.environ.get(AUTH_ENV) != "1"
        or os.environ.get(DISPOSABLE_ENV) != "1"
        or os.environ.get(EXPECTED_DATABASE_ENV) != target_uri
    ):
        _write_evidence(
            {
                "status": SKIPPED_STATUS,
                "reason": "authorization gate not satisfied (redacted)",
                "exit_code": SKIP_EXIT,
            }
        )
        return SKIP_EXIT
    try:
        deps = (deps_factory if deps_factory is not None else build_deps)(target_uri)
        steps = _run_proof_steps(deps)
    except Exception as exc:
        _write_evidence(
            {
                "status": FAILED_STATUS,
                "error_type": type(exc).__name__,
                "exit_code": FAIL_EXIT,
            }
        )
        return FAIL_EXIT
    evidence = dict(steps)
    evidence.update({"status": OK_STATUS, "exit_code": OK_EXIT})
    evidence["invariants"] = {
        "recall_ge_1": int(cast(int, steps.get("recall_hit_count", 0))) >= 1
    }
    _write_evidence(evidence)
    return OK_EXIT
