from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.filterwarnings("ignore::DeprecationWarning"),
    pytest.mark.filterwarnings("ignore::FutureWarning"),
]

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "verification"
    / "phase10-real-docx-retrieval-validation"
    / "reconstruct_transcript.py"
)

spec = importlib.util.spec_from_file_location("phase10_reconstruct_transcript", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_metadata_lines_are_removed_without_dropping_content() -> None:
    rows = [
        {"raw_text": "[20]--【进阶版RAG】混合检索+结构化数据检索.MP_原文"},
        {"raw_text": "2026年03月09日 17:40"},
        {"raw_text": "发言人 00:00"},
        {"raw_text": "你有query了，你知道去什么数据源检索了。"},
        {"raw_text": "发言人 01:11"},
        {"raw_text": "关键词检索和向量检索为什么同时会做？"},
    ]

    cleaned = module.clean_transcript_rows(rows)

    assert [item["raw_text"] for item in cleaned] == [
        "你有query了，你知道去什么数据源检索了。",
        "关键词检索和向量检索为什么同时会做？",
    ]


def test_topic_classifier_prefers_hybrid_retrieval_terms() -> None:
    topic = module.classify_topic(
        "混合检索不是第三种独有的检索方式，它是关键词也做检索，语义向量也做检索，然后检索回来再重排。"
    )

    assert topic == "混合检索"


def test_topic_classifier_detects_structured_data_retrieval() -> None:
    topic = module.classify_topic(
        "如果用户问题涉及表格、数据库字段或者 SQL 查询，就应该走结构化数据检索。"
    )

    assert topic == "结构化数据检索"


def test_heading_path_has_three_levels_for_tree_traversal() -> None:
    heading_path = module.build_heading_path(
        text="关键词检索和向量检索一起召回，再对检索结果进行融合排序。",
        ordinal=7,
        previous_topic=None,
    )

    assert heading_path.startswith("进阶版 RAG > 混合检索 > ")
    assert heading_path.count(" > ") == 2


def test_reconstructed_span_rows_have_non_empty_heading_paths() -> None:
    rows = [
        {"span_id": "source-1", "raw_text": "发言人 00:00", "page_no": None},
        {"span_id": "source-2", "raw_text": "混合检索就是关键词检索和语义向量检索同时做。", "page_no": None},
        {"span_id": "source-3", "raw_text": "结构化数据检索适合表格、数据库字段和 SQL 查询。", "page_no": None},
    ]

    reconstructed = module.build_reconstructed_span_rows(rows)

    assert len(reconstructed) == 2
    assert all(item["heading_path"] for item in reconstructed)
    assert reconstructed[0]["heading_path"].startswith("进阶版 RAG > 混合检索 > ")
    assert reconstructed[1]["heading_path"].startswith("进阶版 RAG > 结构化数据检索 > ")
