"""Canonical tests for the W7-LIVE UIE worker (uie_worker.py).

The worker lives at verification/phase17-graph-recall-multiroute-fusion/
uie_worker.py and is loaded via importlib by absolute path, registered
in sys.modules like the runner tests do.  Paddle is imported ONLY inside
main(), so the host interpreter imports this module cleanly and every
helper is exercised through faked 'infer' seams -- zero model loads,
zero network.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKER_PATH = (
    REPO_ROOT
    / "verification"
    / "phase17-graph-recall-multiroute-fusion"
    / "uie_worker.py"
)


def _load_worker() -> Any:
    spec = importlib.util.spec_from_file_location("phase17_uie_worker", WORKER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


WORKER = _load_worker()

TEXT_1 = "李雷在北京使用华为Mate60"


class FakeInfer:
    """Canned UIE responses keyed by (text, prompt); logs every call."""

    def __init__(self, mapping: dict[tuple[str, str], str] | None = None) -> None:
        self._mapping = mapping or {}
        self.calls: list[tuple[str, str]] = []

    def __call__(self, text: str, prompt: str) -> str:
        self.calls.append((text, prompt))
        return self._mapping.get((text, prompt), "无相应实体")


def test_split_items_empty_blank_and_marker_inputs() -> None:
    assert WORKER.split_items("") == []
    assert WORKER.split_items("   ") == []
    assert WORKER.split_items("无相应实体") == []
    assert WORKER.split_items("无") == []


def test_split_items_all_separators() -> None:
    raw = "李雷，韩梅梅、王小明;小米/华为|比亚迪"
    assert WORKER.split_items(raw) == [
        "李雷",
        "韩梅梅",
        "王小明",
        "小米",
        "华为",
        "比亚迪",
    ]


def test_split_items_strips_parts_and_drops_embedded_marker() -> None:
    assert WORKER.split_items(" 无相应实体 ， 李雷 ， ") == ["李雷"]
    assert WORKER.split_items("  李雷 ， 韩梅梅  ") == ["李雷", "韩梅梅"]


def test_map_to_entity_exact_match_first() -> None:
    assert WORKER.map_to_entity("华为", ("华为", "手机")) == "华为"


def test_map_to_entity_prefers_longest_contained() -> None:
    assert (
        WORKER.map_to_entity("新款华为Mate60手机", ("华为", "华为Mate60"))
        == "华为Mate60"
    )


def test_map_to_entity_value_contained_in_candidate() -> None:
    assert WORKER.map_to_entity("雷", ("李雷",)) == "李雷"


def test_map_to_entity_unmapped_or_empty_candidates_return_none() -> None:
    assert WORKER.map_to_entity("苹果", ("李雷",)) is None
    assert WORKER.map_to_entity("李雷", ()) is None


def test_relation_gate_known_types() -> None:
    assert WORKER._relation_gate("人名") == (
        "所在地",
        "所属公司",
        "任职于",
        "使用",
        "通话",
        "前往",
    )
    assert WORKER._relation_gate("公司名") == ("发布", "总部位于")
    assert WORKER._relation_gate("产品名") == ("所属公司",)


def test_relation_gate_empty_for_place_other_and_unknown() -> None:
    assert WORKER._relation_gate("地名") == ()
    assert WORKER._relation_gate("其他") == ()
    assert WORKER._relation_gate("地点") == ()


def test_module_constants_and_prompt_are_locked() -> None:
    assert WORKER.SCHEMA_FLAT == (
        "所在地",
        "所属公司",
        "任职于",
        "发布",
        "总部位于",
        "使用",
        "通话",
        "前往",
    )
    assert WORKER.SCHEMA_GATE == {
        "人名": ("所在地", "所属公司", "任职于", "使用", "通话", "前往"),
        "公司名": ("发布", "总部位于"),
        "产品名": ("所属公司",),
        "地名": (),
        "其他": (),
    }
    assert WORKER.ENTITY_TYPES == ("人名", "地名", "公司名", "产品名")
    assert (
        WORKER.DEFAULT_MODEL_DIR
        == r"E:\github\rag\.cache\uie2-models\aistudio\PP-UIE-0.5B"
    )
    assert "{sentence}" in WORKER.LLM_IE_PROMPT
    assert "{prompt}" in WORKER.LLM_IE_PROMPT


def test_prompt_template_has_question_and_answer_markers() -> None:
    formatted = WORKER.LLM_IE_PROMPT.format(sentence="S", prompt="P")
    assert "**句子开始**" in formatted
    assert "**句子结束**" in formatted
    assert "**问题开始**" in formatted
    assert "**问题结束**" in formatted
    assert "**回答开始**" in formatted


def test_worker_module_holds_no_paddle_at_top() -> None:
    # main() must be the only place paddle is imported; the module-level
    # import of this file under the host interpreter already proves the
    # top-level import surface is stdlib-only.
    assert "paddle" not in sys.modules
    assert callable(WORKER.main)
    assert callable(WORKER.build_documents)


def test_build_documents_entities_offsets_order_confidence() -> None:
    infer = FakeInfer(
        {
            (TEXT_1, "人名"): "李雷",
            (TEXT_1, "地名"): "北京",
            (TEXT_1, "公司名"): "无相应实体",
            (TEXT_1, "产品名"): "华为Mate60",
        }
    )
    result = WORKER.build_documents([TEXT_1], infer=infer)
    doc = result["documents"][0]
    digest = hashlib.sha256(TEXT_1.encode("utf-8")).hexdigest()[:16]
    assert doc["document_id"] == str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"phase17-uie-doc-{digest}-1")
    )
    assert doc["source_text"] == TEXT_1
    assert doc["normalized_text"] == TEXT_1
    assert doc["entities"] == [
        {
            "text": "李雷",
            "label": "人名",
            "char_start": 0,
            "char_end": 2,
            "confidence": None,
        },
        {
            "text": "北京",
            "label": "地名",
            "char_start": 3,
            "char_end": 5,
            "confidence": None,
        },
        {
            "text": "华为Mate60",
            "label": "产品名",
            "char_start": 7,
            "char_end": 15,
            "confidence": None,
        },
    ]
    assert doc["relations"] == []


def test_build_documents_skips_non_verbatim_items() -> None:
    infer = FakeInfer({(TEXT_1, "人名"): "王小明"})
    doc = WORKER.build_documents([TEXT_1], infer=infer)["documents"][0]
    assert doc["entities"] == []


def test_build_documents_dedups_by_text_and_type_first_wins() -> None:
    infer = FakeInfer({(TEXT_1, "人名"): "李雷，李雷"})
    doc = WORKER.build_documents([TEXT_1], infer=infer)["documents"][0]
    assert doc["entities"] == [
        {
            "text": "李雷",
            "label": "人名",
            "char_start": 0,
            "char_end": 2,
            "confidence": None,
        }
    ]


def test_build_documents_keeps_same_text_under_two_labels() -> None:
    text = "华为发布了手机"
    infer = FakeInfer({(text, "人名"): "华为", (text, "公司名"): "华为"})
    doc = WORKER.build_documents([text], infer=infer)["documents"][0]
    assert [(e["text"], e["label"]) for e in doc["entities"]] == [
        ("华为", "人名"),
        ("华为", "公司名"),
    ]


def test_build_documents_relation_prompts_follow_gate_and_format() -> None:
    infer = FakeInfer(
        {
            (TEXT_1, "人名"): "李雷",
            (TEXT_1, "产品名"): "华为Mate60",
            (TEXT_1, "李雷的使用"): "华为Mate60",
        }
    )
    WORKER.build_documents([TEXT_1], infer=infer)
    prompts = [prompt for _, prompt in infer.calls]
    assert [p for p in prompts if "的" not in p] == [
        "人名",
        "地名",
        "公司名",
        "产品名",
    ]
    assert [p for p in prompts if p.startswith("李雷的")] == [
        "李雷的所在地",
        "李雷的所属公司",
        "李雷的任职于",
        "李雷的使用",
        "李雷的通话",
        "李雷的前往",
    ]
    assert [p for p in prompts if p.startswith("华为Mate60的")] == [
        "华为Mate60的所属公司"
    ]


def test_build_documents_relation_exact_object_fields() -> None:
    infer = FakeInfer(
        {
            (TEXT_1, "人名"): "李雷",
            (TEXT_1, "产品名"): "华为Mate60",
            (TEXT_1, "李雷的使用"): "华为Mate60",
        }
    )
    doc = WORKER.build_documents([TEXT_1], infer=infer)["documents"][0]
    assert doc["relations"] == [
        {
            "subject_text": "李雷",
            "subject_type": "人名",
            "relation": "使用",
            "object_text": "华为Mate60",
            "object_type": "产品名",
            "source_text": TEXT_1,
        }
    ]


def test_build_documents_relation_maps_contained_object() -> None:
    infer = FakeInfer(
        {
            (TEXT_1, "人名"): "李雷",
            (TEXT_1, "产品名"): "华为Mate60",
            (TEXT_1, "李雷的使用"): "新款华为Mate60手机",
        }
    )
    doc = WORKER.build_documents([TEXT_1], infer=infer)["documents"][0]
    assert doc["relations"][0]["object_text"] == "华为Mate60"
    assert doc["relations"][0]["object_type"] == "产品名"


def test_build_documents_skips_unmapped_relation_object() -> None:
    infer = FakeInfer(
        {
            (TEXT_1, "人名"): "李雷",
            (TEXT_1, "产品名"): "华为Mate60",
            (TEXT_1, "李雷的使用"): "苹果",
        }
    )
    doc = WORKER.build_documents([TEXT_1], infer=infer)["documents"][0]
    assert doc["relations"] == []


def test_build_documents_skips_self_loop_relation() -> None:
    infer = FakeInfer(
        {
            (TEXT_1, "人名"): "李雷",
            (TEXT_1, "李雷的所在地"): "李雷",
        }
    )
    doc = WORKER.build_documents([TEXT_1], infer=infer)["documents"][0]
    assert doc["relations"] == []


def test_build_documents_dedups_relation_triples_first_wins() -> None:
    infer = FakeInfer(
        {
            (TEXT_1, "人名"): "李雷",
            (TEXT_1, "产品名"): "华为Mate60",
            (TEXT_1, "李雷的使用"): "华为Mate60，华为Mate60",
        }
    )
    doc = WORKER.build_documents([TEXT_1], infer=infer)["documents"][0]
    assert len(doc["relations"]) == 1


def test_build_documents_company_place_product_gating() -> None:
    text = "华为在深圳发布了手机"
    infer = FakeInfer(
        {
            (text, "公司名"): "华为",
            (text, "地名"): "深圳",
            (text, "产品名"): "手机",
            (text, "华为的发布"): "手机",
            (text, "手机的所属公司"): "华为",
        }
    )
    doc = WORKER.build_documents([text], infer=infer)["documents"][0]
    prompts = [prompt for _, prompt in infer.calls]
    assert [p for p in prompts if p.startswith("华为的")] == [
        "华为的发布",
        "华为的总部位于",
    ]
    assert [p for p in prompts if p.startswith("深圳的")] == []
    assert [p for p in prompts if p.startswith("手机的")] == ["手机的所属公司"]
    assert len(doc["relations"]) == 2


def test_build_documents_object_type_resolved_both_ways() -> None:
    text = "华为发布了手机"
    infer = FakeInfer(
        {
            (text, "公司名"): "华为",
            (text, "产品名"): "手机",
            (text, "华为的发布"): "手机",
            (text, "手机的所属公司"): "华为",
        }
    )
    doc = WORKER.build_documents([text], infer=infer)["documents"][0]
    triples = {
        (r["subject_text"], r["relation"], r["object_text"], r["object_type"])
        for r in doc["relations"]
    }
    assert triples == {
        ("华为", "发布", "手机", "产品名"),
        ("手机", "所属公司", "华为", "公司名"),
    }


def test_document_ids_sequence_and_contract_keys() -> None:
    infer = FakeInfer()
    result = WORKER.build_documents(["甲", "乙"], infer=infer)
    docs = result["documents"]
    digest = hashlib.sha256("甲\n乙".encode("utf-8")).hexdigest()[:16]
    assert [d["document_id"] for d in docs] == [
        str(uuid.uuid5(uuid.NAMESPACE_URL, f"phase17-uie-doc-{digest}-1")),
        str(uuid.uuid5(uuid.NAMESPACE_URL, f"phase17-uie-doc-{digest}-2")),
    ]
    assert uuid.UUID(docs[0]["document_id"]).version == 5
    assert set(result) == {"documents"}
    for doc in docs:
        assert set(doc) == {
            "document_id",
            "source_text",
            "normalized_text",
            "entities",
            "relations",
        }
        for entry in doc["entities"]:
            assert set(entry) == {
                "text",
                "label",
                "char_start",
                "char_end",
                "confidence",
            }
            assert entry["confidence"] is None
        for triple in doc["relations"]:
            assert set(triple) == {
                "subject_text",
                "subject_type",
                "relation",
                "object_text",
                "object_type",
                "source_text",
            }


def test_build_documents_empty_texts_no_infer_calls() -> None:
    infer = FakeInfer()
    assert WORKER.build_documents([], infer=infer) == {"documents": []}
    assert infer.calls == []


def test_gate_route_document_ids_are_canonical_uuid5() -> None:
    result = WORKER.build_documents(["甲", "乙"], infer=FakeInfer())
    digest = hashlib.sha256("甲\n乙".encode("utf-8")).hexdigest()[:16]
    for index, doc in enumerate(result["documents"], start=1):
        assert uuid.UUID(doc["document_id"]) == uuid.uuid5(
            uuid.NAMESPACE_URL, f"phase17-uie-doc-{digest}-{index}"
        )


def test_force_utf8_stdio_reconfigures_stdio_to_utf8(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_out = io.TextIOWrapper(io.BytesIO(), encoding="gbk", line_buffering=True)
    fake_in = io.TextIOWrapper(io.BytesIO(), encoding="gbk")
    monkeypatch.setattr(sys, "stdout", fake_out)
    monkeypatch.setattr(sys, "stdin", fake_in)
    WORKER._force_utf8_stdio()
    assert sys.stdout.encoding == "utf-8"
    assert sys.stdin.encoding == "utf-8"


def test_type_of_scope_is_per_document() -> None:
    doc1_text = "华为发布了畅享70"
    doc2_text = "张三使用了华为"
    infer = FakeInfer(
        {
            (doc1_text, "公司名"): "华为",
            (doc1_text, "产品名"): "畅享70",
            (doc1_text, "华为的发布"): "畅享70",
            (doc2_text, "人名"): "张三",
            (doc2_text, "产品名"): "华为",
            (doc2_text, "张三的使用"): "华为",
        }
    )
    result = WORKER.build_documents([doc1_text, doc2_text], infer=infer)
    doc1, doc2 = result["documents"]
    assert [(e["text"], e["label"]) for e in doc1["entities"]] == [
        ("华为", "公司名"),
        ("畅享70", "产品名"),
    ]
    assert [(e["text"], e["label"]) for e in doc2["entities"]] == [
        ("张三", "人名"),
        ("华为", "产品名"),
    ]
    # doc1 is unaffected by doc2 and keeps its own product typing.
    assert doc1["relations"][0]["object_type"] == "产品名"
    # Regression: type_of previously leaked 华为=公司名 from doc1 into doc2.
    assert doc2["relations"][0]["object_type"] == "产品名"
    assert doc2["relations"][0]["object_text"] == "华为"


def test_resolve_model_dir_env_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    monkeypatch.setenv("PHASE17_UIE_MODEL_DIR", str(model_dir))
    assert WORKER._resolve_model_dir() == str(model_dir)


def test_resolve_model_dir_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PHASE17_UIE_MODEL_DIR", raising=False)
    assert WORKER._resolve_model_dir() == WORKER.DEFAULT_MODEL_DIR


def test_resolve_model_dir_rejects_relative_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PHASE17_UIE_MODEL_DIR", "relative/model")
    with pytest.raises(ValueError, match="must be an absolute path"):
        WORKER._resolve_model_dir()


def test_resolve_model_dir_rejects_nonexistent_absolute_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PHASE17_UIE_MODEL_DIR", str(tmp_path / "missing"))
    with pytest.raises(ValueError, match="does not exist"):
        WORKER._resolve_model_dir()


def test_resolve_model_dir_rejects_drive_relative_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # regression guard: 3.11 ntpath.isabs already rejects drive-relative
    # (no-root) paths; the pathlib guard keeps this true across Python versions.
    monkeypatch.setenv("PHASE17_UIE_MODEL_DIR", "C:models-x")
    with pytest.raises(ValueError, match="must be an absolute path"):
        WORKER._resolve_model_dir()


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="root-relative drive anchoring is Windows-specific",
)
def test_resolve_model_dir_rejects_root_relative_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PHASE17_UIE_MODEL_DIR", "/models-x")
    with pytest.raises(ValueError, match="must be an absolute path"):
        WORKER._resolve_model_dir()


def test_build_documents_ids_scope_to_text_content() -> None:
    infer = FakeInfer(
        {
            ("内容甲", "人名"): "李雷",
            ("内容乙", "人名"): "王芳",
        }
    )
    result_a1 = WORKER.build_documents(["内容甲"], infer=infer)
    result_a2 = WORKER.build_documents(["内容甲"], infer=infer)
    result_b = WORKER.build_documents(["内容乙"], infer=infer)
    id_a = result_a1["documents"][0]["document_id"]
    assert id_a == result_a2["documents"][0]["document_id"]
    assert id_a != result_b["documents"][0]["document_id"]
    assert uuid.UUID(id_a).version == 5
