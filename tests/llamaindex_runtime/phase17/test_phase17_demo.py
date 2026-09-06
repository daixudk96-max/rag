"""Canonical tests for the Phase 17 dual-route demo pipeline.

Covers run_phase17_demo.py (orchestrator) and uie_batch.py (subprocess
extractor).  All engines are fakes; the real pipeline pieces come from
the wave-1 acceptance runner module.  Zero sockets, zero docker, zero LLM.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import inspect
import json
import sys
import threading
import types
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from llamaindex_runtime import llm_openai
from llamaindex_runtime.analysis.graph_channel import GraphHit
from llamaindex_runtime.entity.relation_review import KeywordEvidenceReviewer
from llamaindex_runtime.extraction import trial
from llamaindex_runtime.graph.lightrag_backend import IngestReceipt

REPO_ROOT = Path(__file__).resolve().parents[3]
VERIFICATION_DIR = REPO_ROOT / "verification" / "phase17-graph-recall-multiroute-fusion"
RUNNER_PATH = VERIFICATION_DIR / "run_graph_recall_acceptance.py"
DEMO_PATH = VERIFICATION_DIR / "run_phase17_demo.py"
UIE_BATCH_PATH = VERIFICATION_DIR / "uie_batch.py"
AUTH_ENV = "OKF_PHASE17_DEMO_AUTHORIZED"
DISPOSABLE_ENV = "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE"
EXPECTED_DATABASE_ENV = "OKF_REBUILD_EXPECTED_DATABASE"


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = _load("run_graph_recall_acceptance", RUNNER_PATH)
DEMO = _load("run_phase17_demo", DEMO_PATH)
UIE_BATCH = _load("uie_batch", UIE_BATCH_PATH)


@pytest.fixture(autouse=True)
def _isolate_demo_artifacts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(DEMO, "VERIFICATION_DIR", tmp_path)


class FakeTrialEngine:
    def __init__(self, plans: dict[str, tuple[float, object]] | None = None) -> None:
        self._plans = plans or {}
        self.calls: list[str] = []

    def run_trial(self, batch_id: str, sample_texts: Any) -> trial.TrialReport:
        self.calls.append(batch_id)
        coverage, homogeneity = self._plans.get(
            batch_id, (1.0, trial.BatchHomogeneity.SIMILAR)
        )
        return trial.TrialReport(
            batch_id=batch_id,
            sample_texts=tuple(sample_texts),
            coverage_ratio=coverage,
            uncovered_items=(),
            new_type_proposals=(),
            homogeneity=homogeneity,
            engine_id="fake-trial",
            notes="",
        )


class FakeUieExtractor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def extract(self, texts: Any) -> Any:
        self.calls.append(tuple(texts))
        return RUNNER.build_gate_bundle()


class FakeLlmExtractor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, texts: Any) -> Any:
        self.calls.append(tuple(texts))
        return RUNNER.build_gate_bundle(), 0


class TupleLlmExtractor:
    """LLM-route fake honoring the (bundle, skipped) tuple contract."""

    def __init__(self, skipped: int = 0) -> None:
        self.skipped = skipped
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, texts: Any) -> Any:
        self.calls.append(tuple(texts))
        return RUNNER.build_gate_bundle(), self.skipped


class FakeIngestor:
    def __init__(self) -> None:
        self.count = 0

    def ingest(
        self, payload: Any, *, known_entity_names: frozenset[str] = frozenset()
    ) -> Any:
        self.count += 1
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


def _recall(query: str, *, hl_keywords: Any, ll_keywords: Any, top_k: int = 10) -> Any:
    return (GraphHit(title="hit-1", summary="s", keywords=("k",), source_ids=("s1",)),)


def _bm25_titles() -> tuple[str, ...]:
    return ("bm25-a",)


def _deps(
    plans: dict[str, tuple[float, object]] | None = None,
    *,
    uie: Any = None,
    llm: Any = None,
) -> Any:
    return DEMO.DemoDeps(
        trial_engine=FakeTrialEngine(plans),
        uie_extractor=uie or FakeUieExtractor(),
        llm_extractor=llm or FakeLlmExtractor(),
        reviewer=KeywordEvidenceReviewer(),
        ingestor=FakeIngestor(),
        recall=_recall,
        bm25_titles=_bm25_titles,
    )


def _authorize(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(AUTH_ENV, "1")
    monkeypatch.setenv(DISPOSABLE_ENV, "1")
    monkeypatch.setenv(EXPECTED_DATABASE_ENV, "postgresql://fixture/okf")


def _deauthorize(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(AUTH_ENV, raising=False)


def _report_path() -> Path:
    return DEMO.VERIFICATION_DIR / DEMO.REPORT_NAME


def test_demo_requires_authorization(monkeypatch: pytest.MonkeyPatch) -> None:
    _deauthorize(monkeypatch)
    uie = FakeUieExtractor()
    llm = FakeLlmExtractor()
    deps = _deps(uie=uie, llm=llm)
    code = DEMO.main(
        [], target_uri="postgresql://fixture/okf", deps_factory=lambda uri: deps
    )
    assert code == 1
    assert uie.calls == []
    assert llm.calls == []
    report = _report_path().read_text(encoding="utf-8")
    assert "skipped_not_entered" in report
    assert "authorization gate not satisfied (redacted)" in report


def test_missing_disposable_env_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(AUTH_ENV, "1")
    monkeypatch.delenv(DISPOSABLE_ENV, raising=False)
    monkeypatch.setenv(EXPECTED_DATABASE_ENV, "postgresql://fixture/okf")
    uie = FakeUieExtractor()
    llm = FakeLlmExtractor()
    deps = _deps(uie=uie, llm=llm)
    code = DEMO.main(
        [], target_uri="postgresql://fixture/okf", deps_factory=lambda uri: deps
    )
    assert code == 1
    assert uie.calls == []
    assert llm.calls == []
    report = _report_path().read_text(encoding="utf-8")
    assert "skipped_not_entered" in report
    assert "authorization gate not satisfied (redacted)" in report
    assert "postgresql://fixture/okf" not in report


def test_expected_database_mismatch_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(AUTH_ENV, "1")
    monkeypatch.setenv(DISPOSABLE_ENV, "1")
    monkeypatch.setenv(EXPECTED_DATABASE_ENV, "postgresql://elsewhere/okf")
    uie = FakeUieExtractor()
    llm = FakeLlmExtractor()
    deps = _deps(uie=uie, llm=llm)
    code = DEMO.main(
        [], target_uri="postgresql://fixture/okf", deps_factory=lambda uri: deps
    )
    assert code == 1
    assert uie.calls == []
    assert llm.calls == []
    report = _report_path().read_text(encoding="utf-8")
    assert "skipped_not_entered" in report
    assert "authorization gate not satisfied (redacted)" in report
    assert "postgresql://fixture/okf" not in report


def test_similar_batch_routes_to_uie_only(monkeypatch: pytest.MonkeyPatch) -> None:
    _authorize(monkeypatch)
    uie = FakeUieExtractor()
    llm = FakeLlmExtractor()
    deps = _deps(uie=uie, llm=llm)
    code = DEMO.main(
        [], target_uri="postgresql://fixture/okf", deps_factory=lambda uri: deps
    )
    assert code == 0
    assert llm.calls == []
    assert uie.calls[0] == tuple(DEMO.DEMO_BATCHES[0].texts)
    assert len(uie.calls) == 2


def test_mixed_batch_routes_to_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    _authorize(monkeypatch)
    plans = {
        "mixed": (0.4, trial.BatchHomogeneity.HETEROGENEOUS),
    }
    uie = FakeUieExtractor()
    llm = FakeLlmExtractor()
    deps = _deps(plans, uie=uie, llm=llm)
    code = DEMO.main(
        [], target_uri="postgresql://fixture/okf", deps_factory=lambda uri: deps
    )
    assert code == 0
    assert llm.calls == [tuple(DEMO.DEMO_BATCHES[1].texts)]
    assert len(uie.calls) == 1


def test_report_sections_in_demo_order(monkeypatch: pytest.MonkeyPatch) -> None:
    _authorize(monkeypatch)
    deps = _deps()
    assert (
        DEMO.main(
            [], target_uri="postgresql://fixture/okf", deps_factory=lambda uri: deps
        )
        == 0
    )
    report = _report_path().read_text(encoding="utf-8")
    assert report.index("## batch: similar") < report.index("## batch: mixed")


def test_report_counts_match_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    _authorize(monkeypatch)
    deps = _deps()
    assert (
        DEMO.main(
            [], target_uri="postgresql://fixture/okf", deps_factory=lambda uri: deps
        )
        == 0
    )
    report = _report_path().read_text(encoding="utf-8")
    assert "route: PURE_UIE" in report
    assert "mentions_count: 7" in report
    assert "relations_supported: 2" in report


def test_extractor_failure_marks_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    _authorize(monkeypatch)

    class Broken:
        def extract(self, texts: Any) -> Any:
            raise RuntimeError("boom")

    deps = _deps(uie=Broken())
    code = DEMO.main(
        [], target_uri="postgresql://fixture/okf", deps_factory=lambda uri: deps
    )
    assert code == 1
    report = _report_path().read_text(encoding="utf-8")
    assert "status: failed" in report
    assert "RuntimeError" in report


def test_real_pipeline_counts_via_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    _authorize(monkeypatch)
    deps = _deps()
    outcomes = DEMO.run_demo(deps)
    assert [o.status for o in outcomes] == ["executed", "executed"]
    assert outcomes[0].mentions_count == 7
    assert outcomes[0].relations_supported == 2
    assert outcomes[1].identities_count == 7


def test_run_demo_records_skipped_entities_count() -> None:
    plans = {"mixed": (0.4, trial.BatchHomogeneity.HETEROGENEOUS)}
    llm = TupleLlmExtractor(skipped=2)
    outcomes = DEMO.run_demo(_deps(plans, llm=llm))
    by_batch = {outcome.batch_id: outcome for outcome in outcomes}
    assert llm.calls == [tuple(DEMO.DEMO_BATCHES[1].texts)]
    assert by_batch["mixed"].skipped_entities == 2
    assert by_batch["similar"].skipped_entities == 0
    assert [outcome.status for outcome in outcomes] == ["executed", "executed"]


def test_report_contains_skipped_entities_line() -> None:
    plans = {"mixed": (0.4, trial.BatchHomogeneity.HETEROGENEOUS)}
    outcomes = DEMO.run_demo(_deps(plans, llm=TupleLlmExtractor(skipped=2)))
    report = DEMO.build_demo_report(outcomes)
    assert "- skipped_entities: 2" in report


def test_report_written_to_default_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _authorize(monkeypatch)
    deps = _deps()
    assert (
        DEMO.main(
            [], target_uri="postgresql://fixture/okf", deps_factory=lambda uri: deps
        )
        == 0
    )
    report = _report_path().read_text(encoding="utf-8")
    assert report.startswith("# Phase 17 dual-route demo report")


def test_subprocess_extractor_builds_expected_argv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    document = {
        "document_id": "d1",
        "source_text": "李雷在北京使用华为Mate60",
        "normalized_text": "李雷在北京使用华为Mate60",
        "entities": [
            {
                "text": "李雷",
                "label": "人名",
                "char_start": 0,
                "char_end": 2,
                "confidence": 0.9,
            }
        ],
        "relations": [],
    }
    payload = json.dumps({"documents": [document]}).encode("utf-8")
    captured: dict[str, Any] = {}

    def fake_run(
        argv: Any,
        input: Any = None,
        capture_output: bool = False,
        check: bool = False,
        timeout: Any = None,
        env: Any = None,
    ) -> Any:
        captured["argv"] = list(argv)
        captured["input"] = input
        return SimpleNamespace(returncode=0, stdout=payload, stderr=b"")

    monkeypatch.setattr(UIE_BATCH.subprocess, "run", fake_run)
    venv_python = tmp_path / "python.exe"
    worker = tmp_path / "uie_worker.py"
    venv_python.write_text("", encoding="utf-8")
    worker.write_text("", encoding="utf-8")
    extractor = UIE_BATCH.SubprocessUieBatchExtractor(str(venv_python), str(worker))
    bundle = extractor.extract(("李雷在北京使用华为Mate60",))
    assert captured["argv"] == [str(venv_python), str(worker)]
    sent = json.loads(captured["input"].decode("utf-8"))
    assert sent == {"texts": ["李雷在北京使用华为Mate60"]}
    assert bundle.documents[0].entities[0].text == "李雷"


def test_subprocess_extractor_fails_closed_on_nonzero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_run(
        argv: Any,
        input: Any = None,
        capture_output: bool = False,
        check: bool = False,
        timeout: Any = None,
        env: Any = None,
    ) -> Any:
        return SimpleNamespace(returncode=3, stdout=b"", stderr=b"boom")

    monkeypatch.setattr(UIE_BATCH.subprocess, "run", fake_run)
    venv_python = tmp_path / "python.exe"
    worker = tmp_path / "uie_worker.py"
    venv_python.write_text("", encoding="utf-8")
    worker.write_text("", encoding="utf-8")
    extractor = UIE_BATCH.SubprocessUieBatchExtractor(str(venv_python), str(worker))
    with pytest.raises(RuntimeError):
        extractor.extract(("text",))


def test_demo_argv_is_rejected() -> None:
    with pytest.raises(ValueError):
        DEMO.main(["--flag"], target_uri="postgresql://fixture/okf")


def test_subprocess_env_strips_provider_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    venv_python = tmp_path / "python.exe"
    worker = tmp_path / "uie_worker.py"
    venv_python.write_text("", encoding="utf-8")
    worker.write_text("", encoding="utf-8")
    captured: dict[str, Any] = {}

    def fake_run(
        argv: Any,
        input: Any = None,
        capture_output: bool = False,
        check: bool = False,
        timeout: Any = None,
        env: Any = None,
    ) -> Any:
        captured["env"] = env
        return SimpleNamespace(returncode=1, stdout=b"", stderr=b"")

    monkeypatch.setenv("OPENAI_API_KEY", "secret-a")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "secret-b")
    monkeypatch.setenv("SystemRoot", "C:\\Windows")
    monkeypatch.setattr(UIE_BATCH.subprocess, "run", fake_run)
    extractor = UIE_BATCH.SubprocessUieBatchExtractor(str(venv_python), str(worker))
    with pytest.raises(RuntimeError):
        extractor.extract(("text",))
    assert "OPENAI_API_KEY" not in captured["env"]
    assert "DASHSCOPE_API_KEY" not in captured["env"]
    system_root = next(
        v for k, v in captured["env"].items() if k.upper() == "SYSTEMROOT"
    )
    assert system_root == "C:\\Windows"


def test_subprocess_extractor_rejects_non_absolute_paths() -> None:
    with pytest.raises(ValueError):
        UIE_BATCH.SubprocessUieBatchExtractor("python.exe", "uie_worker.py")


def test_subprocess_extractor_rejects_missing_paths(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        UIE_BATCH.SubprocessUieBatchExtractor(
            str(tmp_path / "missing-python.exe"),
            str(tmp_path / "missing-worker.py"),
        )


def test_falsy_deps_factory_is_still_used(monkeypatch: pytest.MonkeyPatch) -> None:
    _authorize(monkeypatch)
    used: list[str] = []

    class FalsyFactory:
        def __bool__(self) -> bool:
            return False

        def __call__(self, target_uri: str) -> Any:
            used.append(target_uri)
            return _deps()

    code = DEMO.main(
        [], target_uri="postgresql://fixture/okf", deps_factory=FalsyFactory()
    )
    assert used == ["postgresql://fixture/okf"]
    assert code == 0


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


def test_build_deps_wires_pg_lightrag_factory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    light_kwargs, embed_kwargs, light_instances = _fake_lightrag_modules(monkeypatch)
    # The autouse fixture repoints DEMO.VERIFICATION_DIR at tmp_path and
    # build_deps loads uie_batch from there; provide a minimal stub so
    # the extractor seam constructs and the factory wiring is what the
    # test actually observes.
    (tmp_path / "uie_batch.py").write_text(
        "class SubprocessUieBatchExtractor:\n"
        "    def __init__(self, venv_python, worker_script, *, timeout_s=600.0):\n"
        "        self.venv_python = venv_python\n"
        "        self.worker_script = worker_script\n",
        encoding="utf-8",
    )
    venv_python = tmp_path / "python.exe"
    worker = tmp_path / "uie_worker.py"
    venv_python.write_text("", encoding="utf-8")
    worker.write_text("", encoding="utf-8")
    monkeypatch.setenv("PHASE17_UIE_PYTHON", str(venv_python))
    monkeypatch.setenv("PHASE17_UIE_WORKER", str(worker))
    monkeypatch.delenv("PHASE17_LIGHTRAG_WORKDIR", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-ds-key")
    monkeypatch.delenv("DASHSCOPE_EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("DASHSCOPE_EMBEDDING_DIMENSIONS", raising=False)
    deps = DEMO.build_deps("postgresql://fixture/okf")
    assert type(deps.ingestor).__name__ == "_SyncIngestAdapter"
    assert len(light_kwargs) == 1
    kwargs = light_kwargs[0]
    assert kwargs["workspace"] == "phase17-demo"
    assert kwargs["kv_storage"] == "PGKVStorage"
    assert kwargs["vector_storage"] == "PGVectorStorage"
    assert kwargs["graph_storage"] == "PGTableGraphStorage"
    assert kwargs["doc_status_storage"] == "PGDocStatusStorage"
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
    assert kwargs["working_dir"].endswith("phase17-lightrag-wd-phase17-demo")
    assert light_instances[0].initialize_calls == [True]
    assert len(embed_kwargs) == 1
    embed_call = embed_kwargs[0]
    assert embed_call["embedding_dim"] == 1024
    assert embed_call["model_name"] == "text-embedding-v4"
    assert callable(embed_call["func"])
    assert inspect.iscoroutinefunction(embed_call["func"])


def _write_demo_build_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "uie_batch.py").write_text(
        "class SubprocessUieBatchExtractor:\n"
        "    def __init__(self, venv_python, worker_script, *, timeout_s=600.0):\n"
        "        self.venv_python = venv_python\n"
        "        self.worker_script = worker_script\n",
        encoding="utf-8",
    )
    venv_python = tmp_path / "python.exe"
    worker = tmp_path / "uie_worker.py"
    venv_python.write_text("", encoding="utf-8")
    worker.write_text("", encoding="utf-8")
    monkeypatch.setenv("PHASE17_UIE_PYTHON", str(venv_python))
    monkeypatch.setenv("PHASE17_UIE_WORKER", str(worker))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-ds-key")
    monkeypatch.delenv("DASHSCOPE_EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("DASHSCOPE_EMBEDDING_DIMENSIONS", raising=False)
    monkeypatch.delenv("PHASE17_LIGHTRAG_WORKDIR", raising=False)


def test_demo_uie_env_missing_python_value_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fake_lightrag_modules(monkeypatch)
    _write_demo_build_env(monkeypatch, tmp_path)
    monkeypatch.delenv("PHASE17_UIE_PYTHON", raising=False)
    with pytest.raises(
        ValueError,
        match="PHASE17_UIE_PYTHON must be set to the UIE venv python path",
    ):
        DEMO.build_deps("postgresql://fixture/okf")


def test_demo_uie_env_missing_worker_value_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fake_lightrag_modules(monkeypatch)
    _write_demo_build_env(monkeypatch, tmp_path)
    monkeypatch.delenv("PHASE17_UIE_WORKER", raising=False)
    with pytest.raises(
        ValueError,
        match="PHASE17_UIE_WORKER must be set to the UIE worker script path",
    ):
        DEMO.build_deps("postgresql://fixture/okf")


def test_llm_extractor_document_ids_are_canonical_uuid5(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fake_lightrag_modules(monkeypatch)
    _write_demo_build_env(monkeypatch, tmp_path)

    class FakeClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def complete(self, prompt: str) -> Any:
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "entities": [
                            {
                                "text": "李雷",
                                "label": "人名",
                                "char_start": 0,
                                "char_end": 2,
                            }
                        ],
                        "relations": [],
                    }
                )
            )

    class FakeEngine:
        def __init__(self, client: Any, *, relation_types: Any) -> None:
            self.client = client

    class FakeReviewer:
        def __init__(self, client: Any) -> None:
            self.client = client

    fake_module = types.ModuleType("llamaindex_runtime.llm_openai.trial_engine")
    setattr(fake_module, "LlmTrialEngine", FakeEngine)
    monkeypatch.setattr(llm_openai, "trial_engine", fake_module)
    fake_reviewer_module = types.ModuleType(
        "llamaindex_runtime.llm_openai.relation_reviewer"
    )
    setattr(fake_reviewer_module, "LlmRelationReviewer", FakeReviewer)
    monkeypatch.setattr(llm_openai, "relation_reviewer", fake_reviewer_module)
    monkeypatch.setattr(llm_openai.client, "OpenAICompatClient", FakeClient)
    deps = DEMO.build_deps("postgresql://fixture/okf")
    bundle, skipped = deps.llm_extractor(["李雷在北京"])
    assert skipped == 0
    digest = hashlib.sha256("李雷在北京".encode("utf-8")).hexdigest()[:16]
    assert bundle.documents[0].document_id == str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"phase17-demo-doc-{digest}-1")
    )
    assert uuid.UUID(bundle.documents[0].document_id).version == 5


def test_llm_extractor_document_ids_scope_to_text_content(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fake_lightrag_modules(monkeypatch)
    _write_demo_build_env(monkeypatch, tmp_path)

    class FakeClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def complete(self, prompt: str) -> Any:
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "entities": [
                            {
                                "text": "李雷",
                                "label": "人名",
                                "char_start": 0,
                                "char_end": 2,
                            }
                        ],
                        "relations": [],
                    }
                )
            )

    class FakeEngine:
        def __init__(self, client: Any, *, relation_types: Any) -> None:
            self.client = client

    class FakeReviewer:
        def __init__(self, client: Any) -> None:
            self.client = client

    fake_module = types.ModuleType("llamaindex_runtime.llm_openai.trial_engine")
    setattr(fake_module, "LlmTrialEngine", FakeEngine)
    monkeypatch.setattr(llm_openai, "trial_engine", fake_module)
    fake_reviewer_module = types.ModuleType(
        "llamaindex_runtime.llm_openai.relation_reviewer"
    )
    setattr(fake_reviewer_module, "LlmRelationReviewer", FakeReviewer)
    monkeypatch.setattr(llm_openai, "relation_reviewer", fake_reviewer_module)
    monkeypatch.setattr(llm_openai.client, "OpenAICompatClient", FakeClient)
    deps = DEMO.build_deps("postgresql://fixture/okf")
    bundle_a, skipped_a = deps.llm_extractor(["李雷在甲地"])
    bundle_b, skipped_b = deps.llm_extractor(["李雷在乙地"])
    assert skipped_a == 0 and skipped_b == 0
    assert bundle_a.documents[0].document_id != bundle_b.documents[0].document_id
    bundle_a2, _ = deps.llm_extractor(["李雷在甲地"])
    assert bundle_a2.documents[0].document_id == bundle_a.documents[0].document_id


def test_llm_ie_example_is_valid_json() -> None:
    example = json.loads(DEMO._LLM_IE_EXAMPLE)
    assert "entities" in example
    assert "relations" in example


def test_llm_extractor_skips_non_verbatim_entities(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fake_lightrag_modules(monkeypatch)
    _write_demo_build_env(monkeypatch, tmp_path)

    class FakeClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def complete(self, prompt: str) -> Any:
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "entities": [
                            {
                                "text": "不存在的实体",
                                "label": "人名",
                                "char_start": 0,
                                "char_end": 5,
                            },
                            {
                                "text": "李雷",
                                "label": "人名",
                                "char_start": 0,
                                "char_end": 2,
                            },
                        ],
                        "relations": [],
                    }
                )
            )

    class FakeEngine:
        def __init__(self, client: Any, *, relation_types: Any) -> None:
            self.client = client

    class FakeReviewer:
        def __init__(self, client: Any) -> None:
            self.client = client

    fake_module = types.ModuleType("llamaindex_runtime.llm_openai.trial_engine")
    setattr(fake_module, "LlmTrialEngine", FakeEngine)
    monkeypatch.setattr(llm_openai, "trial_engine", fake_module)
    fake_reviewer_module = types.ModuleType(
        "llamaindex_runtime.llm_openai.relation_reviewer"
    )
    setattr(fake_reviewer_module, "LlmRelationReviewer", FakeReviewer)
    monkeypatch.setattr(llm_openai, "relation_reviewer", fake_reviewer_module)
    monkeypatch.setattr(llm_openai.client, "OpenAICompatClient", FakeClient)
    deps = DEMO.build_deps("postgresql://fixture/okf")
    bundle, skipped = deps.llm_extractor(["李雷在北京"])
    assert skipped == 1
    entities = bundle.documents[0].entities
    assert [e.text for e in entities] == ["李雷"]


def _stop_rag_loop(thread: threading.Thread, loop: asyncio.AbstractEventLoop) -> None:
    """Shut down a persistent rag loop started by _start_rag_loop."""
    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=5.0)
    assert not thread.is_alive()
    loop.close()


def test_start_rag_loop_returns_running_daemon_loop() -> None:
    thread, loop = DEMO._start_rag_loop()
    try:
        assert isinstance(thread, threading.Thread)
        assert thread.daemon is True
        assert thread.is_alive()
        assert loop.is_running()
    finally:
        _stop_rag_loop(thread, loop)


def test_loop_bound_rag_bridges_coroutines_to_persistent_loop() -> None:
    thread, persistent_loop = DEMO._start_rag_loop()

    class FakeRag:
        def __init__(self) -> None:
            self.workspace = "phase17-gate"
            self.calls: list[Any] = []

        async def aquery_data(self, param: Any) -> str:
            self.calls.append(param)
            assert asyncio.get_running_loop() is persistent_loop
            return "query-marker"

    fake = FakeRag()
    proxy = DEMO._LoopBoundRag(fake, persistent_loop)
    try:
        assert inspect.iscoroutinefunction(proxy.aquery_data)
        assert proxy.workspace == "phase17-gate"
        assert asyncio.run(proxy.aquery_data({"param": 1})) == "query-marker"
        assert fake.calls == [{"param": 1}]
    finally:
        _stop_rag_loop(thread, persistent_loop)


def test_sync_ingest_adapter_blocks_on_persistent_loop() -> None:
    thread, persistent_loop = DEMO._start_rag_loop()

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
    adapter = DEMO._SyncIngestAdapter(inner, persistent_loop)
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
            return SimpleNamespace(vectors=[[0.5, 1.5], [2.5, 3.5]])

    config = types.SimpleNamespace(
        embedding_dimensions=2,
        embedding_model="text-embedding-v4",
        workspace="phase17-demo",
    )
    DEMO._pg_lightrag_factory(config, FakeEmbedding())
    ef = light_kwargs[0]["embedding_func"]
    result = asyncio.run(ef(["a", "b"]))
    assert isinstance(result, np.ndarray)
    assert result.shape == (2, 2)
    assert result.dtype == np.float32
    assert result.tolist() == [[0.5, 1.5], [2.5, 3.5]]


def test_as_embedding_array_converts_rows_to_float32_ndarray() -> None:
    result = DEMO._as_embedding_array([[0.5, 1.5], [2.5, 3.5]])
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
    thread, loop = DEMO._start_rag_loop()
    try:
        loop_rag = DEMO._LoopBoundRag(fake_rag, loop)
        adapter = DEMO._AqueryDataAdapter(loop_rag, fake_rag, loop)
        param_ns = SimpleNamespace(
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
    adapter = DEMO._AqueryDataAdapter(
        DEMO._LoopBoundRag(fake_rag, None), fake_rag, None
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
    thread, loop = DEMO._start_rag_loop()
    try:
        loop_rag = DEMO._LoopBoundRag(fake_rag, loop)
        adapter = DEMO._AqueryDataAdapter(loop_rag, fake_rag, loop)
        param_ns = SimpleNamespace(
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
    result = DEMO._normalize_chunk_source_ids(response)
    chunks = result["data"]["chunks"]
    assert chunks[0]["source_id"] == "fp"
    assert chunks[1]["source_id"] == "ref9"
    assert chunks[2] == {"content": "c"}
    assert "source_id" not in chunks[2]


def test_normalize_passthrough_non_mapping_and_missing_keys() -> None:
    assert DEMO._normalize_chunk_source_ids("nope") == "nope"
    assert DEMO._normalize_chunk_source_ids({"status": "success"}) == {
        "status": "success"
    }
    assert DEMO._normalize_chunk_source_ids({"data": "str"}) == {"data": "str"}
    assert DEMO._normalize_chunk_source_ids({"data": {"chunks": "nope"}}) == {
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
    assert DEMO._normalize_chunk_source_ids(response) is response


def test_deps_factory_failure_writes_report_and_returns_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authorize(monkeypatch)

    def _raiser(target_uri: str) -> Any:
        raise RuntimeError("boom")

    code = DEMO.main([], target_uri="postgresql://fixture/okf", deps_factory=_raiser)
    assert code == 1
    report = _report_path().read_text(encoding="utf-8")
    assert "status: failed" in report
    assert "RuntimeError" in report
    assert "boom" not in report
