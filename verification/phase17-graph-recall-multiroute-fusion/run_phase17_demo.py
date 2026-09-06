# ruff: noqa: E402
"""Phase 17 dual-route demo pipeline (Wave 2).

Routes demo batches through trial-based routing and reuses the wave-1
acceptance runner module (loaded via importlib, same pattern as the
canonical tests) for routing, pipeline execution and the real DTOs.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import os
import sys
import types
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
from live_bridge import (  # type: ignore[import-not-found]
    _AqueryDataAdapter,
    _as_embedding_array,  # noqa: F401  (re-exported for the demo tests)
    _LoopBoundRag,
    _normalize_chunk_source_ids,  # noqa: F401
    _pg_lightrag_factory,
    _start_rag_loop,
    _SyncIngestAdapter,
)

from llamaindex_runtime.extraction import trial

# The approval-test harness loads this module with
# importlib.util.spec_from_file_location + module_from_spec and then
# exec_module, WITHOUT inserting it into sys.modules.  With the
# future-annotations import above, every annotation is a string, and
# dataclasses._is_type() resolves those strings through
# sys.modules[cls.__module__].__dict__ (dataclasses.py line 712).  A
# module not registered there crashes with AttributeError: NoneType
# object has no attribute __dict__ at the first dataclass definition.
# Register a placeholder module that shares this module globals so
# frozen DTO classes can be defined under that loader.
if sys.modules.get(__name__) is None:
    _run_phase17_demo_module: types.ModuleType = types.ModuleType(__name__)
    _run_phase17_demo_module.__dict__.update(globals())
    sys.modules[__name__] = _run_phase17_demo_module

VERIFICATION_DIR: Path = Path(__file__).resolve().parent
AUTH_ENV: str = "OKF_PHASE17_DEMO_AUTHORIZED"
DISPOSABLE_ENV: str = "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE"
EXPECTED_DATABASE_ENV: str = "OKF_REBUILD_EXPECTED_DATABASE"
REPORT_NAME: str = "phase17_demo_report.md"
SKIPPED_REPORT_BODY: str = (
    "# Phase 17 dual-route demo report\n"
    "\n"
    "status: skipped_not_entered\n"
    "reason: authorization gate not satisfied (redacted)\n"
)
_LLM_IE_EXAMPLE: str = (
    '{"entities": [{"text": "<实体>", "label": "<类型>", "char_start": 0, '
    '"char_end": 1}], "relations": [{"subject_text": "<主语>", '
    '"subject_type": "<类型>", "relation": "<关系>", "object_text": "<宾语>", '
    '"object_type": "<类型>", "source_text": "<原句>"}]}'
)


def _load_runner() -> Any:
    """Load the wave-1 acceptance runner module via importlib by path."""
    spec = importlib.util.spec_from_file_location(
        "run_graph_recall_acceptance",
        VERIFICATION_DIR / "run_graph_recall_acceptance.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load run_graph_recall_acceptance module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_uie_batch() -> Any:
    """Load the wave-2 uie_batch helper module via importlib by path."""
    spec = importlib.util.spec_from_file_location(
        "uie_batch", VERIFICATION_DIR / "uie_batch.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load uie_batch module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = _load_runner()


@dataclass(frozen=True)
class DemoBatch:
    """One demo batch: a stable id plus the texts to route."""

    batch_id: str
    texts: tuple[str, ...]


DEMO_BATCHES: tuple[DemoBatch, ...] = (
    DemoBatch("similar", RUNNER.SAMPLE_TEXTS),
    DemoBatch(
        "mixed",
        (
            "李雷昨天去了上海",
            "医院的张医生给了诊断",
            "昨天的球赛很精彩",
            "股票市场今天上涨",
        ),
    ),
)


@dataclass(frozen=True)
class DemoDeps:
    """Injected engines for the demo pipeline."""

    trial_engine: object
    uie_extractor: object
    llm_extractor: object
    reviewer: object
    ingestor: object
    recall: object
    bm25_titles: object


@dataclass(frozen=True)
class BatchOutcome:
    """Redacted per-batch outcome (counts and enum names only)."""

    batch_id: str
    route: str
    status: str
    mentions_count: int
    identities_count: int
    basket_pending: int
    relations_total: int
    relations_supported: int
    relations_rejected: int
    ingest_entities: int
    recall_hit_count: int
    fusion_max_score: float
    skipped_entities: int = 0
    error_type: str | None = None


def run_demo(deps: DemoDeps) -> tuple[BatchOutcome, ...]:
    """Route and run every demo batch in order, never raising."""
    outcomes: list[BatchOutcome] = []
    trial_engine = cast(Any, deps.trial_engine)
    uie_extractor = cast(Any, deps.uie_extractor)
    llm_extractor = cast(Any, deps.llm_extractor)
    for batch in DEMO_BATCHES:
        route = "UNKNOWN"
        try:
            report = trial_engine.run_trial(batch.batch_id, batch.texts)
            decision = trial.decide_route(report)
            route = decision.route.name
            if decision.route is trial.ExtractionRoute.PURE_UIE:
                bundle = uie_extractor.extract(batch.texts)
                skipped = 0
            else:
                bundle, skipped = llm_extractor(batch.texts)
            steps = RUNNER.run_pipeline(
                bundle,
                batch_id=batch.batch_id,
                route=route,
                coverage_ratio=decision.coverage_ratio,
                reviewer=deps.reviewer,
                ingestor=deps.ingestor,
                recall=deps.recall,
                bm25_titles=deps.bm25_titles,
            )
            outcomes.append(
                BatchOutcome(
                    batch_id=batch.batch_id,
                    route=route,
                    status="executed",
                    mentions_count=int(steps["mentions_count"]),
                    identities_count=int(steps["identities_count"]),
                    basket_pending=int(steps["basket_pending"]),
                    relations_total=int(steps["relations_total"]),
                    relations_supported=int(steps["relations_supported"]),
                    # Spec-pinned report name (W7 review General-3): this
                    # reflects the pending review-basket count; a true
                    # rejected count is not tracked yet.
                    relations_rejected=int(steps["relations_pending"]),
                    ingest_entities=int(steps["ingest_entities"]),
                    recall_hit_count=int(steps["recall_hit_count"]),
                    fusion_max_score=float(steps["fusion_max_score"]),
                    skipped_entities=skipped,
                )
            )
        except Exception as exc:
            outcomes.append(
                BatchOutcome(
                    batch_id=batch.batch_id,
                    route=route,
                    status="failed",
                    mentions_count=0,
                    identities_count=0,
                    basket_pending=0,
                    relations_total=0,
                    relations_supported=0,
                    relations_rejected=0,
                    ingest_entities=0,
                    recall_hit_count=0,
                    fusion_max_score=0.0,
                    error_type=type(exc).__name__,
                )
            )
    return tuple(outcomes)


def build_demo_report(outcomes: Sequence[BatchOutcome]) -> str:
    """Render the deterministic markdown demo report."""
    lines = ["# Phase 17 dual-route demo report", ""]
    for outcome in outcomes:
        lines += [
            "## batch: " + outcome.batch_id,
            "- route: " + outcome.route,
            "- status: " + outcome.status,
            "- skipped_entities: " + str(outcome.skipped_entities),
            "- mentions_count: " + str(outcome.mentions_count),
            "- identities_count: " + str(outcome.identities_count),
            "- relations_supported: " + str(outcome.relations_supported),
            "- relations_rejected: " + str(outcome.relations_rejected),
            "- relations_total: " + str(outcome.relations_total),
            "- ingest_entities: " + str(outcome.ingest_entities),
            "- recall_hit_count: " + str(outcome.recall_hit_count),
            "- fusion_max_score: " + format(outcome.fusion_max_score, ".6f"),
        ]
        if outcome.error_type is not None:
            lines.append("- error_type: " + outcome.error_type)
        lines.append("")
    return "\n".join(lines)


def build_deps(target_uri: str) -> DemoDeps:
    """Live dependency assembly (lazy imports only).

    Tests exercise it with faked seams; live deps are wired lazily here.
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

    def _llm_extractor(texts: Sequence[str]) -> Any:
        digest = hashlib.sha256("\n".join(texts).encode("utf-8")).hexdigest()[:16]
        prompt = "请从文本中抽取实体与关系，仅输出 JSON 对象：" + _LLM_IE_EXAMPLE
        documents: list[Any] = []
        skipped = 0
        for index, text in enumerate(texts):
            response = client.complete(prompt + "\n文本：" + text)
            body = json.loads(response.content)
            entities = []
            for e in body.get("entities", ()):
                entity_text = str(e["text"])
                if entity_text not in text:
                    skipped += 1
                    continue
                char_start = text.index(entity_text)
                entities.append(
                    RUNNER.ExtractionEntity(
                        text=entity_text,
                        label=str(e["label"]),
                        char_start=char_start,
                        char_end=char_start + len(entity_text),
                        confidence=None,
                    )
                )
            relations = tuple(
                RUNNER.ExtractionRelation(
                    subject_text=str(r["subject_text"]),
                    subject_type=str(r["subject_type"]),
                    relation=str(r["relation"]),
                    object_text=str(r["object_text"]),
                    object_type=str(r["object_type"]),
                    source_text=str(r["source_text"]),
                )
                for r in body.get("relations", ())
            )
            documents.append(
                RUNNER.DocumentExtraction(
                    document_id=str(
                        uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"phase17-demo-doc-{digest}-{index + 1}",
                        )
                    ),
                    source_text=text,
                    normalized_text=text,
                    entities=tuple(entities),
                    relations=relations,
                )
            )
        return (RUNNER.ExtractionBundle(documents=tuple(documents)), skipped)

    uie_batch_module = _load_uie_batch()
    uie_python = os.environ.get("PHASE17_UIE_PYTHON")
    if not uie_python:
        raise ValueError("PHASE17_UIE_PYTHON must be set to the UIE venv python path")
    uie_worker = os.environ.get("PHASE17_UIE_WORKER")
    if not uie_worker:
        raise ValueError("PHASE17_UIE_WORKER must be set to the UIE worker script path")
    uie_extractor: object = uie_batch_module.SubprocessUieBatchExtractor(
        uie_python,
        uie_worker,
    )
    config = lightrag_backend.LightragRuntimeConfig(
        workspace="phase17-demo",
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
    loop_thread, loop = _start_rag_loop()
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
    ) -> tuple[Any, ...]:
        return channel.fetch(
            query,
            hl_keywords=hl_keywords,
            ll_keywords=ll_keywords,
            top_k=top_k,
        )

    def _empty_bm25_titles() -> tuple[str, ...]:
        return ()

    return DemoDeps(
        trial_engine=trial_engine,
        uie_extractor=uie_extractor,
        llm_extractor=_llm_extractor,
        reviewer=reviewer,
        ingestor=_SyncIngestAdapter(ingestor, loop),
        recall=_gate_recall,
        bm25_titles=_empty_bm25_titles,
    )


def main(
    argv: Sequence[str],
    *,
    target_uri: str,
    deps_factory: Callable[[str], DemoDeps] | None = None,
) -> int:
    """Programmatic entry point; authorization is env-gated."""
    if argv:
        raise ValueError(
            "demo runner takes no command line arguments; "
            "target_uri is programmatic only"
        )
    if (
        os.environ.get(AUTH_ENV) != "1"
        or os.environ.get(DISPOSABLE_ENV) != "1"
        or os.environ.get(EXPECTED_DATABASE_ENV) != target_uri
    ):
        (VERIFICATION_DIR / REPORT_NAME).write_text(
            SKIPPED_REPORT_BODY, encoding="utf-8"
        )
        return 1
    try:
        deps = cast(Any, deps_factory if deps_factory is not None else build_deps)(
            target_uri
        )
        outcomes = run_demo(deps)
    except Exception as exc:
        outcomes = tuple(
            BatchOutcome(
                batch_id=batch.batch_id,
                route="UNKNOWN",
                status="failed",
                mentions_count=0,
                identities_count=0,
                basket_pending=0,
                relations_total=0,
                relations_supported=0,
                relations_rejected=0,
                ingest_entities=0,
                recall_hit_count=0,
                fusion_max_score=0.0,
                error_type=type(exc).__name__,
            )
            for batch in DEMO_BATCHES
        )
    report = build_demo_report(outcomes)
    (VERIFICATION_DIR / REPORT_NAME).write_text(report, encoding="utf-8")
    print(report)
    return 0 if all(o.status == "executed" for o in outcomes) else 1
