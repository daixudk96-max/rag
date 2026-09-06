"""Canonical tests for the Phase 17 graph-recall acceptance gate runner.

The runner lives at verification/phase17-graph-recall-multiroute-fusion/
run_graph_recall_acceptance.py and is loaded via importlib (16-17
convention).  Every heavy dependency is injected through AcceptanceDeps;
these tests use fakes only - zero sockets, zero docker, zero LLM calls.
"""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import json
import sys
import threading
import types
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from llamaindex_runtime import llm_openai
from llamaindex_runtime.analysis.graph_channel import GraphHit, ranked_fusion
from llamaindex_runtime.entity.relation_review import KeywordEvidenceReviewer
from llamaindex_runtime.extraction import trial
from llamaindex_runtime.graph import lightrag_backend
from llamaindex_runtime.graph.lightrag_backend import IngestReceipt

REPO_ROOT = Path(__file__).resolve().parents[3]
VERIFICATION_DIR = REPO_ROOT / "verification" / "phase17-graph-recall-multiroute-fusion"
RUNNER_PATH = VERIFICATION_DIR / "run_graph_recall_acceptance.py"


def _load_runner() -> Any:
    spec = importlib.util.spec_from_file_location(
        "run_graph_recall_acceptance", RUNNER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = _load_runner()
AUTH_ENV = "OKF_GRAPH_RECALL_ACCEPTANCE_AUTHORIZED"
DISPOSABLE_ENV = "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE"
EXPECTED_DATABASE_ENV = "OKF_REBUILD_EXPECTED_DATABASE"


@pytest.fixture(autouse=True)
def _isolate_runner_artifacts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(RUNNER, "VERIFICATION_DIR", tmp_path)


def _authorize(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(AUTH_ENV, "1")
    monkeypatch.setenv(DISPOSABLE_ENV, "1")
    monkeypatch.setenv(EXPECTED_DATABASE_ENV, "postgresql://fixture/okf")


def _deauthorize(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (AUTH_ENV, DISPOSABLE_ENV, EXPECTED_DATABASE_ENV):
        monkeypatch.delenv(name, raising=False)


class FakeTrialEngine:
    def __init__(
        self, coverage: float = 1.0, homogeneity: object | None = None
    ) -> None:
        self._coverage = coverage
        self._homogeneity = homogeneity or trial.BatchHomogeneity.SIMILAR
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def run_trial(self, batch_id: str, sample_texts: Any) -> trial.TrialReport:
        self.calls.append((batch_id, tuple(sample_texts)))
        return trial.TrialReport(
            batch_id=batch_id,
            sample_texts=tuple(sample_texts),
            coverage_ratio=self._coverage,
            uncovered_items=(),
            new_type_proposals=(),
            homogeneity=self._homogeneity,
            engine_id="fake-trial",
            notes="",
        )


class FakeExtractor:
    def __init__(self, runner: Any, *, fail: bool = False) -> None:
        self._runner = runner
        self._fail = fail
        self.calls: list[tuple[str, ...]] = []

    def extract(self, texts: Any) -> Any:
        self.calls.append(tuple(texts))
        if self._fail:
            raise RuntimeError("boom")
        return self._runner.build_gate_bundle()


class FakeIngestor:
    def __init__(self) -> None:
        self.payloads: list[Any] = []
        self.known: list[frozenset[str]] = []

    def ingest(
        self, payload: Any, *, known_entity_names: frozenset[str] = frozenset()
    ) -> Any:
        self.payloads.append(payload)
        self.known.append(known_entity_names)
        return IngestReceipt(
            inserted_entities=tuple(
                e.entity_name
                for e in payload.entities
                if e.entity_name not in known_entity_names
            ),
            skipped_entities=(),
            inserted_relations=tuple(payload.relations),
            skipped_relations=(),
            inserted_chunks=tuple(payload.chunks),
        )


class FakeRecall:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self, query: str, *, hl_keywords: Any, ll_keywords: Any, top_k: int = 10
    ) -> Any:
        self.calls.append(
            {
                "query": query,
                "hl": tuple(hl_keywords),
                "ll": tuple(ll_keywords),
                "top_k": top_k,
            }
        )
        return (
            GraphHit(
                title="doc-1",
                summary="s",
                keywords=("use",),
                source_ids=("gate-doc-1",),
            ),
            GraphHit(
                title="doc-3",
                summary="s",
                keywords=("publish",),
                source_ids=("gate-doc-3",),
            ),
        )


def _bm25_titles() -> tuple[str, ...]:
    return ("bm25-alpha", "bm25-beta")


def _read_evidence() -> tuple[str, dict[str, Any]]:
    path = RUNNER.VERIFICATION_DIR / RUNNER.EVIDENCE_NAME
    content = path.read_text(encoding="utf-8")
    return content, json.loads(content)


def test_missing_authorization_skips_without_building_deps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _deauthorize(monkeypatch)
    recorder: dict[str, Any] = {}
    factory = _deps_factory_that_must_not_run(recorder)
    code = RUNNER.main([], target_uri="postgresql://fixture/okf", deps_factory=factory)
    assert code == 1
    assert recorder.get("built", 0) == 0
    content, data = _read_evidence()
    assert data["status"] == RUNNER.SKIPPED_STATUS
    assert data["reason"] == "authorization gate not satisfied (redacted)"
    assert "\n" not in content.strip()


def _deps_factory_that_must_not_run(recorder: dict[str, Any]) -> Any:
    def _factory(target_uri: str) -> Any:
        recorder["built"] = recorder.get("built", 0) + 1
        raise AssertionError("deps must not be built when the gate is closed")

    return _factory


def test_missing_expected_database_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(AUTH_ENV, "1")
    monkeypatch.setenv(DISPOSABLE_ENV, "1")
    monkeypatch.delenv(EXPECTED_DATABASE_ENV, raising=False)
    recorder: dict[str, Any] = {}
    factory = _deps_factory_that_must_not_run(recorder)
    assert (
        RUNNER.main([], target_uri="postgresql://fixture/okf", deps_factory=factory)
        == 1
    )
    assert recorder.get("built", 0) == 0


def test_missing_disposable_flag_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(AUTH_ENV, "1")
    monkeypatch.delenv(DISPOSABLE_ENV, raising=False)
    monkeypatch.setenv(EXPECTED_DATABASE_ENV, "postgresql://fixture/okf")
    recorder: dict[str, Any] = {}
    factory = _deps_factory_that_must_not_run(recorder)
    assert (
        RUNNER.main([], target_uri="postgresql://fixture/okf", deps_factory=factory)
        == 1
    )
    assert recorder.get("built", 0) == 0


def test_expected_database_mismatch_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(AUTH_ENV, "1")
    monkeypatch.setenv(DISPOSABLE_ENV, "1")
    monkeypatch.setenv(EXPECTED_DATABASE_ENV, "postgresql://elsewhere/okf")
    recorder: dict[str, Any] = {}
    factory = _deps_factory_that_must_not_run(recorder)
    code = RUNNER.main([], target_uri="postgresql://fixture/okf", deps_factory=factory)
    assert code == 1
    assert recorder.get("built", 0) == 0
    content, data = _read_evidence()
    assert data["status"] == RUNNER.SKIPPED_STATUS
    assert data["reason"] == "authorization gate not satisfied (redacted)"
    assert "postgresql://fixture/okf" not in content
    assert "\n" not in content.strip()


def test_authorized_happy_path_executes(monkeypatch: pytest.MonkeyPatch) -> None:
    _authorize(monkeypatch)
    recorder: dict[str, Any] = {}
    factory = _full_deps_factory(recorder)
    code = RUNNER.main([], target_uri="postgresql://fixture/okf", deps_factory=factory)
    assert code == 0
    content, data = _read_evidence()
    assert data["status"] == RUNNER.OK_STATUS
    assert data["route"] == "PURE_UIE"
    assert data["batch_id"] == RUNNER.GATE_BATCH_ID
    assert data["mentions_count"] == 7
    assert data["identities_count"] == 7
    assert data["ingest_entities"] == data["identities_count"]
    assert data["ingest_entities"] > 0
    assert data["relations_supported"] == 2
    assert data["recall_hit_count"] == 2
    assert data["fusion_max_score"] > 0.0
    assert "\n" not in content.strip()


def test_evidence_invariants_recall_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    _authorize(monkeypatch)
    recorder: dict[str, Any] = {}
    factory = _full_deps_factory(recorder)
    assert (
        RUNNER.main([], target_uri="postgresql://fixture/okf", deps_factory=factory)
        == 0
    )
    content, data = _read_evidence()
    assert data["invariants"] == {"recall_ge_1": True}


def test_evidence_invariants_recall_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    _authorize(monkeypatch)

    class ZeroRecall:
        def __call__(
            self, query: str, *, hl_keywords: Any, ll_keywords: Any, top_k: int = 10
        ) -> Any:
            return ()

    def _factory(target_uri: str) -> Any:
        return RUNNER.AcceptanceDeps(
            trial_engine=FakeTrialEngine(),
            extractor=FakeExtractor(RUNNER),
            reviewer=KeywordEvidenceReviewer(),
            ingestor=FakeIngestor(),
            recall=ZeroRecall(),
            bm25_titles=_bm25_titles,
        )

    assert (
        RUNNER.main([], target_uri="postgresql://fixture/okf", deps_factory=_factory)
        == 0
    )
    content, data = _read_evidence()
    assert data["recall_hit_count"] == 0
    assert data["invariants"] == {"recall_ge_1": False}


def _full_deps_factory(recorder: dict[str, Any]) -> Any:
    ingestor = FakeIngestor()
    recorder["ingestor"] = ingestor

    def _factory(target_uri: str) -> Any:
        recorder["target_uri"] = target_uri
        recorder["built"] = recorder.get("built", 0) + 1
        return RUNNER.AcceptanceDeps(
            trial_engine=FakeTrialEngine(),
            extractor=FakeExtractor(RUNNER),
            reviewer=KeywordEvidenceReviewer(),
            ingestor=ingestor,
            recall=FakeRecall(),
            bm25_titles=_bm25_titles,
        )

    return _factory


def test_happy_path_uses_real_ranked_fusion(monkeypatch: pytest.MonkeyPatch) -> None:
    _authorize(monkeypatch)
    hits = (
        GraphHit(title="a", summary="s", keywords=("k",), source_ids=("d1",)),
        GraphHit(title="b", summary="s", keywords=("k",), source_ids=("d2",)),
    )
    fused = ranked_fusion(hits, ("c",))
    assert fused[0].title == "a"
    assert fused[0].score > 0.0
    assert [hit.title for hit in fused] == ["a", "c", "b"]


def test_ingest_receives_entities_relations_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authorize(monkeypatch)
    recorder: dict[str, Any] = {}
    factory = _full_deps_factory(recorder)
    assert (
        RUNNER.main([], target_uri="postgresql://fixture/okf", deps_factory=factory)
        == 0
    )
    ingestor = recorder["ingestor"]
    assert len(ingestor.payloads) == 1
    payload = ingestor.payloads[0]
    assert len(payload.entities) == 7
    assert len(payload.chunks) == 3
    pairs = sorted((rel.src_id, rel.tgt_id) for rel in payload.relations)
    assert pairs == [("华为", "手机"), ("李雷", "华为mate60")]
    assert ingestor.known[0] == frozenset()


def test_evidence_is_redacted(monkeypatch: pytest.MonkeyPatch) -> None:
    _authorize(monkeypatch)
    recorder: dict[str, Any] = {}
    assert (
        RUNNER.main(
            [],
            target_uri="postgresql://fixture/okf",
            deps_factory=_full_deps_factory(recorder),
        )
        == 0
    )
    content, _ = _read_evidence()
    assert "李雷" not in content
    assert "华为" not in content
    assert "韩梅梅" not in content


def test_proof_failure_writes_failed_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    _authorize(monkeypatch)

    class BrokenExtractor:
        def extract(self, texts: Any) -> Any:
            raise RuntimeError("boom")

    def _factory(target_uri: str) -> Any:
        return RUNNER.AcceptanceDeps(
            trial_engine=FakeTrialEngine(),
            extractor=BrokenExtractor(),
            reviewer=KeywordEvidenceReviewer(),
            ingestor=FakeIngestor(),
            recall=FakeRecall(),
            bm25_titles=_bm25_titles,
        )

    code = RUNNER.main([], target_uri="postgresql://fixture/okf", deps_factory=_factory)
    assert code == RUNNER.FAIL_EXIT
    content, data = _read_evidence()
    assert data["status"] == RUNNER.FAILED_STATUS
    assert data["error_type"] == "RuntimeError"
    assert "boom" not in content


def test_argv_is_rejected() -> None:
    with pytest.raises(ValueError):
        RUNNER.main(["--flag"], target_uri="postgresql://fixture/okf")


def test_trial_engine_receives_gate_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    _authorize(monkeypatch)
    trial_engine = FakeTrialEngine()

    def _factory(target_uri: str) -> Any:
        return RUNNER.AcceptanceDeps(
            trial_engine=trial_engine,
            extractor=FakeExtractor(RUNNER),
            reviewer=KeywordEvidenceReviewer(),
            ingestor=FakeIngestor(),
            recall=FakeRecall(),
            bm25_titles=_bm25_titles,
        )

    assert (
        RUNNER.main([], target_uri="postgresql://fixture/okf", deps_factory=_factory)
        == 0
    )
    assert trial_engine.calls[0][0] == RUNNER.GATE_BATCH_ID
    assert trial_engine.calls[0][1] == RUNNER.SAMPLE_TEXTS


def test_deterministic_evidence_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    _authorize(monkeypatch)
    recorder: dict[str, Any] = {}
    assert (
        RUNNER.main(
            [],
            target_uri="postgresql://fixture/okf",
            deps_factory=_full_deps_factory(recorder),
        )
        == 0
    )
    first = (RUNNER.VERIFICATION_DIR / RUNNER.EVIDENCE_NAME).read_bytes()
    assert (
        RUNNER.main(
            [],
            target_uri="postgresql://fixture/okf",
            deps_factory=_full_deps_factory(recorder),
        )
        == 0
    )
    second = (RUNNER.VERIFICATION_DIR / RUNNER.EVIDENCE_NAME).read_bytes()
    assert first == second


def test_heterogeneous_trial_routes_to_llm_primary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authorize(monkeypatch)
    engine = FakeTrialEngine(
        coverage=0.4, homogeneity=trial.BatchHomogeneity.HETEROGENEOUS
    )

    def _factory(target_uri: str) -> Any:
        return RUNNER.AcceptanceDeps(
            trial_engine=engine,
            extractor=FakeExtractor(RUNNER),
            reviewer=KeywordEvidenceReviewer(),
            ingestor=FakeIngestor(),
            recall=FakeRecall(),
            bm25_titles=_bm25_titles,
        )

    assert (
        RUNNER.main([], target_uri="postgresql://fixture/okf", deps_factory=_factory)
        == 0
    )
    content, data = _read_evidence()
    assert data["route"] == "LLM_PRIMARY_UIE_ASSIST"
    assert "LLM_PRIMARY_UIE_ASSIST" == trial.ExtractionRoute.LLM_PRIMARY_UIE_ASSIST.name


def test_build_deps_binds_relation_types_as_keyword(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, Any] = {}

    class FakeEngine:
        def __init__(self, client: Any, *, relation_types: Any) -> None:
            captured["relation_types"] = relation_types

    fake_module = types.ModuleType("llamaindex_runtime.llm_openai.trial_engine")
    setattr(fake_module, "LlmTrialEngine", FakeEngine)
    monkeypatch.setattr(llm_openai, "trial_engine", fake_module)

    class FakeRag:
        async def initialize_storages(self) -> None:
            pass

    monkeypatch.setattr(
        lightrag_backend.LightragKgIngestor,
        "_ensure_rag",
        lambda self: FakeRag(),
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-ds-key")
    _write_uie_env_fixtures(monkeypatch, tmp_path)
    deps = RUNNER.build_deps("postgresql://fixture/okf")
    assert captured["relation_types"] == frozenset(
        ("所在地", "所属公司", "任职于", "发布", "总部位于", "使用", "通话", "前往")
    )
    assert deps.trial_engine is not None


def _fake_lightrag_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[Any]]:
    light_kwargs: list[dict[str, Any]] = []
    embed_kwargs: list[dict[str, Any]] = []
    light_instances: list[Any] = []

    class FakeLightRAG:
        def __init__(self, **kwargs: Any) -> None:
            light_kwargs.append(dict(kwargs))
            light_instances.append(self)
            self.initialize_calls: list[bool] = []

        async def initialize_storages(self) -> None:
            self.initialize_calls.append(True)

    class FakeEmbeddingFunc:
        def __init__(self, **kwargs: Any) -> None:
            embed_kwargs.append(dict(kwargs))
            self.func = kwargs.get("func")

        async def __call__(self, *args: Any, **kwargs: Any) -> Any:
            # Mirrors the real EmbeddingFunc.__call__ contract
            # (lightrag/utils.py:653-656): the wrapped function must
            # return an object exposing .size (np.ndarray).
            result = await self.func(*args, **kwargs)
            if not hasattr(result, "size"):
                raise AttributeError(
                    "'%s' object has no attribute 'size'" % type(result).__name__
                )
            return result

    fake_lightrag = types.ModuleType("lightrag")
    setattr(fake_lightrag, "LightRAG", FakeLightRAG)
    fake_utils = types.ModuleType("lightrag.utils")
    setattr(fake_utils, "EmbeddingFunc", FakeEmbeddingFunc)
    setattr(fake_lightrag, "utils", fake_utils)
    monkeypatch.setitem(sys.modules, "lightrag", fake_lightrag)
    monkeypatch.setitem(sys.modules, "lightrag.utils", fake_utils)
    return light_kwargs, embed_kwargs, light_instances


def _write_uie_env_fixtures(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    venv_python = tmp_path / "python.exe"
    worker = tmp_path / "uie_worker.py"
    venv_python.write_text("", encoding="utf-8")
    worker.write_text("", encoding="utf-8")
    monkeypatch.setenv("PHASE17_UIE_PYTHON", str(venv_python))
    monkeypatch.setenv("PHASE17_UIE_WORKER", str(worker))


def test_env_uie_extractor_requires_python_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PHASE17_UIE_PYTHON", raising=False)
    with pytest.raises(ValueError, match="PHASE17_UIE_PYTHON must be set"):
        RUNNER._EnvUieExtractor()


def test_env_uie_extractor_requires_worker_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    venv_python = tmp_path / "python.exe"
    venv_python.write_text("", encoding="utf-8")
    monkeypatch.setenv("PHASE17_UIE_PYTHON", str(venv_python))
    monkeypatch.delenv("PHASE17_UIE_WORKER", raising=False)
    with pytest.raises(ValueError, match="PHASE17_UIE_WORKER must be set"):
        RUNNER._EnvUieExtractor()


def test_env_uie_extractor_rejects_relative_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PHASE17_UIE_PYTHON", "relative/python.exe")
    monkeypatch.setenv("PHASE17_UIE_WORKER", "relative/worker.py")
    with pytest.raises(ValueError, match="must be an absolute path"):
        RUNNER._EnvUieExtractor()


def test_env_uie_extractor_rejects_missing_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    missing = tmp_path / "nope.exe"
    monkeypatch.setenv("PHASE17_UIE_PYTHON", str(missing))
    worker = tmp_path / "worker.py"
    worker.write_text("", encoding="utf-8")
    monkeypatch.setenv("PHASE17_UIE_WORKER", str(worker))
    with pytest.raises(ValueError, match="does not exist"):
        RUNNER._EnvUieExtractor()


def test_env_uie_extractor_extract_happy_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worker_script = tmp_path / "worker.py"
    worker_script.write_text(
        "import json\n"
        "import sys\n"
        "sys.stdin.read()\n"
        "document = {\n"
        "    'document_id': 'doc-1',\n"
        "    'source_text': '李雷在北京使用华为Mate60',\n"
        "    'normalized_text': '李雷在北京使用华为Mate60',\n"
        "    'entities': [\n"
        "        {'text': '李雷', 'label': '人名', 'char_start': 0,\n"
        "         'char_end': 2, 'confidence': 0.9}\n"
        "    ],\n"
        "    'relations': [\n"
        "        {'subject_text': '李雷', 'subject_type': '人名',\n"
        "         'relation': '使用', 'object_text': '华为Mate60',\n"
        "         'object_type': '产品名',\n"
        "         'source_text': '李雷在北京使用华为Mate60'}\n"
        "    ],\n"
        "}\n"
        "sys.stdout.write(json.dumps({'documents': [document]}))\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PHASE17_UIE_PYTHON", sys.executable)
    monkeypatch.setenv("PHASE17_UIE_WORKER", str(worker_script))
    extractor = RUNNER._EnvUieExtractor()
    bundle = extractor.extract(["李雷在北京使用华为Mate60"])
    assert isinstance(bundle, RUNNER.ExtractionBundle)
    assert len(bundle.documents) == 1
    doc = bundle.documents[0]
    assert doc.document_id == "doc-1"
    assert doc.source_text == "李雷在北京使用华为Mate60"
    assert doc.normalized_text == "李雷在北京使用华为Mate60"
    assert len(doc.entities) == 1
    entity = doc.entities[0]
    assert entity.text == "李雷"
    assert entity.label == "人名"
    assert entity.char_start == 0
    assert entity.char_end == 2
    assert entity.confidence == 0.9
    assert len(doc.relations) == 1
    relation = doc.relations[0]
    assert relation.subject_text == "李雷"
    assert relation.subject_type == "人名"
    assert relation.relation == "使用"
    assert relation.object_text == "华为Mate60"
    assert relation.object_type == "产品名"
    assert relation.source_text == "李雷在北京使用华为Mate60"


def test_env_uie_extractor_nonzero_exit_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worker_script = tmp_path / "worker.py"
    worker_script.write_text(
        "import sys\n"
        "sys.stdin.read()\n"
        "sys.stderr.write('UIE_WORKER_OOM_MARKER\\n')\n"
        "sys.exit(2)\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PHASE17_UIE_PYTHON", sys.executable)
    monkeypatch.setenv("PHASE17_UIE_WORKER", str(worker_script))
    extractor = RUNNER._EnvUieExtractor()
    with pytest.raises(
        RuntimeError,
        match=r"uie extraction worker failed \(rc=2\).*UIE_WORKER_OOM_MARKER",
    ):
        extractor.extract(["文本"])


def test_env_uie_extractor_strips_provider_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dump_path = tmp_path / "env_dump.json"
    worker_script = tmp_path / "worker.py"
    worker_script.write_text(
        "import json\n"
        "import os\n"
        "import sys\n"
        "with open(os.environ['PHASE17_UIE_ENV_DUMP'], 'w', encoding='utf-8') as f:\n"
        "    json.dump(dict(os.environ), f)\n"
        "sys.stdin.read()\n"
        "sys.stdout.write(json.dumps({'documents': []}))\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PHASE17_UIE_PYTHON", sys.executable)
    monkeypatch.setenv("PHASE17_UIE_WORKER", str(worker_script))
    monkeypatch.setenv("PHASE17_UIE_ENV_DUMP", str(dump_path))
    monkeypatch.setenv("OPENAI_API_KEY", "secret-key")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "secret-ds")
    extractor = RUNNER._EnvUieExtractor()
    bundle = extractor.extract(["文本"])
    assert bundle.documents == ()
    keys = json.loads(dump_path.read_text(encoding="utf-8"))
    assert keys
    assert "OPENAI_API_KEY" not in keys
    assert "DASHSCOPE_API_KEY" not in keys
    assert all(not key.upper().startswith(("OPENAI_", "DASHSCOPE_")) for key in keys)
    assert keys["PYTHONUTF8"] == "1"
    assert "PHASE17_UIE_ENV_DUMP" in keys


def test_build_deps_wires_pg_lightrag_factory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    light_kwargs, embed_kwargs, light_instances = _fake_lightrag_modules(monkeypatch)

    class FakeEngine:
        def __init__(self, client: Any, *, relation_types: Any) -> None:
            self.client = client

    fake_module = types.ModuleType("llamaindex_runtime.llm_openai.trial_engine")
    setattr(fake_module, "LlmTrialEngine", FakeEngine)
    monkeypatch.setattr(llm_openai, "trial_engine", fake_module)
    _write_uie_env_fixtures(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-ds-key")
    monkeypatch.delenv("DASHSCOPE_EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("DASHSCOPE_EMBEDDING_DIMENSIONS", raising=False)
    workdir = tmp_path / "lightrag-wd"
    monkeypatch.setenv("PHASE17_LIGHTRAG_WORKDIR", str(workdir))
    deps = RUNNER.build_deps("postgresql://fixture/okf")
    assert isinstance(deps.extractor, RUNNER._EnvUieExtractor)
    assert type(deps.ingestor).__name__ == "_SyncIngestAdapter"
    assert len(light_kwargs) == 1
    kwargs = light_kwargs[0]
    assert kwargs["kv_storage"] == "PGKVStorage"
    assert kwargs["vector_storage"] == "PGVectorStorage"
    assert kwargs["graph_storage"] == "PGTableGraphStorage"
    assert kwargs["doc_status_storage"] == "PGDocStatusStorage"
    assert kwargs["workspace"] == "phase17-gate"
    assert callable(kwargs["llm_model_func"])
    with pytest.raises(
        RuntimeError,
        match="llm_model_func is a deliberate stub; "
        "LightRAG keyword short-circuit must prevent LLM calls",
    ):
        kwargs["llm_model_func"]()
    assert kwargs["llm_model_name"] == "stub-fail-closed-no-llm"
    assert kwargs["vector_db_storage_cls_kwargs"] == {
        "cosine_better_than_threshold": 0.2
    }
    assert kwargs["working_dir"] == str(workdir)
    assert light_instances[0].initialize_calls == [True]
    assert len(embed_kwargs) == 1
    ekwargs = embed_kwargs[0]
    assert ekwargs["embedding_dim"] == 1024
    assert ekwargs["model_name"] == "text-embedding-v4"
    assert callable(ekwargs["func"])
    assert inspect.iscoroutinefunction(ekwargs["func"])


def test_env_uie_extractor_decodes_utf8_child_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worker_script = tmp_path / "worker.py"
    worker_script.write_text(
        "import json\n"
        "import sys\n"
        "sys.stdin.read()\n"
        "sys.stdout.reconfigure(encoding='utf-8')\n"
        "sys.stdout.write(json.dumps(\n"
        "    {'documents': [{'document_id': '文档甲',\n"
        "                    'source_text': '李雷',\n"
        "                    'normalized_text': '李雷',\n"
        "                    'entities': [], 'relations': []}]},\n"
        "    ensure_ascii=False))\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PHASE17_UIE_PYTHON", sys.executable)
    monkeypatch.setenv("PHASE17_UIE_WORKER", str(worker_script))
    extractor = RUNNER._EnvUieExtractor()
    bundle = extractor.extract(["李雷"])
    assert bundle.documents[0].document_id == "文档甲"


def test_pg_lightrag_factory_falls_back_to_workspace_workdir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    light_kwargs, embed_kwargs, _ = _fake_lightrag_modules(monkeypatch)

    class FakeEngine:
        def __init__(self, client: Any, *, relation_types: Any) -> None:
            self.client = client

    fake_module = types.ModuleType("llamaindex_runtime.llm_openai.trial_engine")
    setattr(fake_module, "LlmTrialEngine", FakeEngine)
    monkeypatch.setattr(llm_openai, "trial_engine", fake_module)
    _write_uie_env_fixtures(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-ds-key")
    monkeypatch.delenv("DASHSCOPE_EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("DASHSCOPE_EMBEDDING_DIMENSIONS", raising=False)
    monkeypatch.delenv("PHASE17_LIGHTRAG_WORKDIR", raising=False)
    RUNNER.build_deps("postgresql://fixture/okf")
    assert len(light_kwargs) == 1
    assert light_kwargs[0]["working_dir"].endswith("phase17-lightrag-wd-phase17-gate")
    assert len(embed_kwargs) == 1


def _stop_rag_loop(thread: threading.Thread, loop: asyncio.AbstractEventLoop) -> None:
    """Shut down a persistent rag loop started by _start_rag_loop."""
    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=5.0)
    assert not thread.is_alive()
    loop.close()


def test_start_rag_loop_returns_running_daemon_loop() -> None:
    thread, loop = RUNNER._start_rag_loop()
    try:
        assert isinstance(thread, threading.Thread)
        assert thread.daemon is True
        assert thread.is_alive()
        assert loop.is_running()
    finally:
        _stop_rag_loop(thread, loop)


def test_loop_bound_rag_bridges_coroutines_to_persistent_loop() -> None:
    thread, persistent_loop = RUNNER._start_rag_loop()

    class FakeRag:
        def __init__(self) -> None:
            self.workspace = "phase17-gate"
            self.calls: list[Any] = []

        async def aquery_data(self, param: Any) -> str:
            self.calls.append(param)
            assert asyncio.get_running_loop() is persistent_loop
            return "query-marker"

    fake = FakeRag()
    proxy = RUNNER._LoopBoundRag(fake, persistent_loop)
    try:
        assert inspect.iscoroutinefunction(proxy.aquery_data)
        assert proxy.workspace == "phase17-gate"
        assert asyncio.run(proxy.aquery_data({"param": 1})) == "query-marker"
        assert fake.calls == [{"param": 1}]
    finally:
        _stop_rag_loop(thread, persistent_loop)


def test_sync_ingest_adapter_blocks_on_persistent_loop() -> None:
    thread, persistent_loop = RUNNER._start_rag_loop()

    class FakeAsyncIngestor:
        def __init__(self) -> None:
            self.seen: list[tuple[Any, frozenset[str]]] = []

        async def ingest(
            self,
            payload: Any,
            *,
            known_entity_names: frozenset[str] = frozenset(),
        ) -> str:
            self.seen.append((payload, frozenset(known_entity_names)))
            assert asyncio.get_running_loop() is persistent_loop
            return "receipt-marker"

    inner = FakeAsyncIngestor()
    adapter = RUNNER._SyncIngestAdapter(inner, persistent_loop)
    try:
        result = adapter.ingest({"payload": 1}, known_entity_names=frozenset({"李雷"}))
        assert result == "receipt-marker"
        assert not asyncio.iscoroutine(result)
        assert inner.seen == [({"payload": 1}, frozenset({"李雷"}))]
        assert adapter.ingest({"payload": 2}) == "receipt-marker"
        assert inner.seen[-1] == ({"payload": 2}, frozenset())
    finally:
        _stop_rag_loop(thread, persistent_loop)


def test_pg_lightrag_factory_embedding_func_returns_numpy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    light_kwargs, _embed_kwargs, _instances = _fake_lightrag_modules(monkeypatch)
    monkeypatch.setenv("PHASE17_LIGHTRAG_WORKDIR", str(tmp_path / "wd"))

    class FakeEmbedding:
        def embed(self, texts: Any) -> Any:
            return types.SimpleNamespace(vectors=[[0.5, 1.5], [2.5, 3.5]])

    config = types.SimpleNamespace(
        embedding_dimensions=2,
        embedding_model="text-embedding-v4",
        workspace="phase17-gate",
    )
    RUNNER._pg_lightrag_factory(config, FakeEmbedding())
    ef = light_kwargs[0]["embedding_func"]
    result = asyncio.run(ef(["a", "b"]))
    assert isinstance(result, np.ndarray)
    assert result.shape == (2, 2)
    assert result.dtype == np.float32
    assert result.tolist() == [[0.5, 1.5], [2.5, 3.5]]


def test_pg_lightrag_factory_rejects_relative_workdir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_lightrag_modules(monkeypatch)
    monkeypatch.setenv("PHASE17_LIGHTRAG_WORKDIR", "relative/wd")

    class FakeEmbedding:
        def embed(self, texts: Any) -> Any:
            return types.SimpleNamespace(vectors=[[0.5, 1.5], [2.5, 3.5]])

    config = types.SimpleNamespace(
        embedding_dimensions=2,
        embedding_model="text-embedding-v4",
        workspace="phase17-gate",
    )
    with pytest.raises(ValueError, match="must be an absolute path"):
        RUNNER._pg_lightrag_factory(config, FakeEmbedding())
    # regression guard: 3.11 ntpath.isabs already rejects drive-relative
    # (no-root) paths; the pathlib guard keeps this true across Python versions.
    monkeypatch.setenv("PHASE17_LIGHTRAG_WORKDIR", "C:phase17-wd")
    with pytest.raises(ValueError, match="must be an absolute path"):
        RUNNER._pg_lightrag_factory(config, FakeEmbedding())


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="root-relative drive anchoring is Windows-specific",
)
def test_pg_lightrag_factory_rejects_root_relative_workdir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_lightrag_modules(monkeypatch)
    monkeypatch.setenv("PHASE17_LIGHTRAG_WORKDIR", "/phase17-wd")

    class FakeEmbedding:
        def embed(self, texts: Any) -> Any:
            return types.SimpleNamespace(vectors=[[0.5, 1.5], [2.5, 3.5]])

    config = types.SimpleNamespace(
        embedding_dimensions=2,
        embedding_model="text-embedding-v4",
        workspace="phase17-gate",
    )
    with pytest.raises(ValueError, match="must be an absolute path"):
        RUNNER._pg_lightrag_factory(config, FakeEmbedding())


def test_as_embedding_array_converts_rows_to_float32_ndarray() -> None:
    result = RUNNER._as_embedding_array([[0.5, 1.5], [2.5, 3.5]])
    assert isinstance(result, np.ndarray)
    assert result.shape == (2, 2)
    assert result.dtype == np.float32
    assert result.tolist() == [[0.5, 1.5], [2.5, 3.5]]


def test_aquery_data_adapter_translates_namespace_to_query_param(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_lightrag = types.ModuleType("lightrag")
    fake_base = types.ModuleType("lightrag.base")

    class QueryParam:
        def __init__(self, **kwargs: Any) -> None:
            self.mode = kwargs.get("mode", "hybrid")
            self.only_need_context = kwargs.get("only_need_context", False)
            self.top_k = kwargs.get("top_k", 10)
            self.chunk_top_k = kwargs.get("chunk_top_k", 20)
            self.hl_keywords = kwargs.get("hl_keywords", [])
            self.ll_keywords = kwargs.get("ll_keywords", [])

    fake_base.QueryParam = QueryParam
    fake_lightrag.base = fake_base
    monkeypatch.setitem(sys.modules, "lightrag", fake_lightrag)
    monkeypatch.setitem(sys.modules, "lightrag.base", fake_base)

    seen: list[tuple[str, Any]] = []

    class FakeRag:
        async def aquery_data(self, query: str, param: Any) -> Any:
            seen.append((query, param))
            return {
                "status": "success",
                "data": {"entities": [], "relationships": [], "chunks": []},
            }

    fake_rag = FakeRag()
    thread, loop = RUNNER._start_rag_loop()
    try:
        loop_rag = RUNNER._LoopBoundRag(fake_rag, loop)
        adapter = RUNNER._AqueryDataAdapter(loop_rag, fake_rag, loop)
        param_ns = types.SimpleNamespace(
            query="华为的总部在哪里",
            mode="naive",
            only_need_context=True,
            top_k=10,
            chunk_top_k=10,
            hl_keywords=("总部",),
            ll_keywords=("华为",),
        )
        result = asyncio.run(adapter.aquery_data(param_ns))
    finally:
        _stop_rag_loop(thread, loop)

    assert result["status"] == "success"
    assert len(seen) == 1
    recorded_query, recorded_param = seen[0]
    assert recorded_query == "华为的总部在哪里"
    assert isinstance(recorded_param, QueryParam)
    assert recorded_param.mode == "naive"
    assert recorded_param.only_need_context is True
    assert recorded_param.top_k == 10
    assert recorded_param.chunk_top_k == 10
    assert recorded_param.hl_keywords == ["总部"]
    assert recorded_param.ll_keywords == ["华为"]


def test_aquery_data_adapter_passes_other_attrs_through() -> None:
    class FakeRag:
        pass

    fake_rag = FakeRag()
    fake_rag.some_attr = "passthrough-ok"
    adapter = RUNNER._AqueryDataAdapter(
        RUNNER._LoopBoundRag(fake_rag, None), fake_rag, None
    )
    assert adapter.some_attr == "passthrough-ok"


def test_adapter_normalizes_naive_chunk_source_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_lightrag = types.ModuleType("lightrag")
    fake_base = types.ModuleType("lightrag.base")

    class QueryParam:
        def __init__(self, **kwargs: Any) -> None:
            self.mode = kwargs.get("mode", "hybrid")
            self.only_need_context = kwargs.get("only_need_context", False)
            self.top_k = kwargs.get("top_k", 10)
            self.chunk_top_k = kwargs.get("chunk_top_k", 20)
            self.hl_keywords = kwargs.get("hl_keywords", [])
            self.ll_keywords = kwargs.get("ll_keywords", [])

    fake_base.QueryParam = QueryParam
    fake_lightrag.base = fake_base
    monkeypatch.setitem(sys.modules, "lightrag", fake_lightrag)
    monkeypatch.setitem(sys.modules, "lightrag.base", fake_base)

    class FakeRag:
        async def aquery_data(self, query: str, param: Any) -> Any:
            return {
                "status": "success",
                "data": {
                    "entities": [],
                    "relationships": [],
                    "chunks": [
                        {
                            "reference_id": "1",
                            "content": "华为的总部在杭州",
                            "file_path": "custom_kg",
                            "chunk_id": "abc123",
                        },
                        {"content": "x", "source_id": "kept"},
                    ],
                },
            }

    fake_rag = FakeRag()
    thread, loop = RUNNER._start_rag_loop()
    try:
        loop_rag = RUNNER._LoopBoundRag(fake_rag, loop)
        adapter = RUNNER._AqueryDataAdapter(loop_rag, fake_rag, loop)
        param_ns = types.SimpleNamespace(
            query="华为的总部在哪里",
            mode="naive",
            only_need_context=True,
            top_k=10,
            chunk_top_k=10,
            hl_keywords=("总部",),
            ll_keywords=("华为",),
        )
        result = asyncio.run(adapter.aquery_data(param_ns))
    finally:
        _stop_rag_loop(thread, loop)

    chunks = result["data"]["chunks"]
    assert chunks[0]["source_id"] == "abc123"
    assert chunks[1]["source_id"] == "kept"


def test_normalize_helper_fallback_chain() -> None:
    response = {
        "status": "success",
        "data": {
            "entities": [],
            "relationships": [],
            "chunks": [
                {"content": "a", "file_path": "fp"},
                {
                    "content": "b",
                    "chunk_id": "",
                    "file_path": "",
                    "reference_id": "ref9",
                },
                {"content": "c"},
            ],
        },
    }
    result = RUNNER._normalize_chunk_source_ids(response)
    chunks = result["data"]["chunks"]
    assert chunks[0]["source_id"] == "fp"
    assert chunks[1]["source_id"] == "ref9"
    assert chunks[2] == {"content": "c"}
    assert "source_id" not in chunks[2]


def test_normalize_passthrough_non_mapping_and_missing_keys() -> None:
    assert RUNNER._normalize_chunk_source_ids("nope") == "nope"
    assert RUNNER._normalize_chunk_source_ids({"status": "success"}) == {
        "status": "success"
    }
    assert RUNNER._normalize_chunk_source_ids({"data": "str"}) == {"data": "str"}
    assert RUNNER._normalize_chunk_source_ids({"data": {"chunks": "nope"}}) == {
        "data": {"chunks": "nope"}
    }


def test_normalize_returns_same_object_when_nothing_changed() -> None:
    response = {
        "status": "success",
        "data": {
            "entities": [],
            "relationships": [],
            "chunks": [{"content": "x", "source_id": "kept"}],
        },
    }
    assert RUNNER._normalize_chunk_source_ids(response) is response


def test_deps_factory_failure_writes_failed_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authorize(monkeypatch)
    monkeypatch.setenv(EXPECTED_DATABASE_ENV, "x")

    def _raiser(target_uri: str) -> Any:
        raise RuntimeError("boom")

    code = RUNNER.main([], target_uri="x", deps_factory=_raiser)
    assert code == RUNNER.FAIL_EXIT
    content, data = _read_evidence()
    assert data["status"] == RUNNER.FAILED_STATUS
    assert data["error_type"] == "RuntimeError"
    assert "boom" not in content
