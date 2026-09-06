"""Rebuild refuses path-security malformed bundles before database connection."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from uuid import uuid4

import pytest

from llamaindex_runtime.okf.roundtrip import recompute_span_id
from llamaindex_runtime.okf.sidecar import SpanRecord, SpanSidecar

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "rebuild_from_okf.py"


def _load_rebuild() -> ModuleType:
    spec = importlib.util.spec_from_file_location("path_security_rebuild", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_raw(root: Path, relative: str) -> None:
    doc_id, version_id = str(uuid4()), str(uuid4())
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\ntype: raw\n"
        f"doc_id: {doc_id}\nversion_id: {version_id}\n"
        "source_checksum: " + "a" * 64 + "\n"
        "docling_version: test\ngenerated_by: test\n---\nbody\n",
        encoding="utf-8",
    )
    provisional = SpanRecord("00000000-0000-0000-0000-000000000000", 1, (), 0, "body")
    SpanSidecar(
        schema_version=1,
        doc_id=doc_id,
        version_id=version_id,
        spans=(
            SpanRecord(
                recompute_span_id(provisional, doc_id=doc_id, version_id=version_id),
                1,
                (),
                0,
                "body",
            ),
        ),
    ).dump(path.with_suffix(".spans.json"))


def test_rebuild_refuses_misplaced_raw_before_connecting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_raw(tmp_path, "entities/misplaced.md")
    module = _load_rebuild()
    monkeypatch.setattr(
        module.psycopg, "connect", lambda *_: pytest.fail("database connection")
    )

    with pytest.raises(
        ValueError, match="^malformed OKF documents found in bundle; refusing rebuild$"
    ):
        module._rebuild_admitted_bundle(
            module._admit_bundle(tmp_path), "unused", "unused"
        )
