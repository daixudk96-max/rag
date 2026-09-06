"""Public rebuild API admission-boundary regression tests."""

from __future__ import annotations

import importlib.util
import inspect
from collections.abc import Callable, Mapping
from pathlib import Path
from types import ModuleType

import pytest

from llamaindex_runtime.okf.parser import (
    BundleResult,
    BundleStats,
    OKFDocument,
    OKFFrontmatter,
)
from llamaindex_runtime.okf.sidecar import SpanRecord

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "rebuild_from_okf.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("rebuild_public_api", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _document() -> OKFDocument:
    return OKFDocument(
        file_path=Path("raw/test.md"),
        frontmatter=OKFFrontmatter(
            type="raw",
            doc_id="00000000-0000-0000-0000-000000000001",
            version_id="00000000-0000-0000-0000-000000000002",
        ),
        body="Text",
        spans=(
            SpanRecord("00000000-0000-0000-0000-000000000003", None, (), 0, "Text"),
        ),
        canonical_hash="a" * 64,
    )


@pytest.mark.parametrize(
    "forged",
    [
        lambda module: module._AdmittedBundle(
            (module._freeze_raw_document(_document()),)
        ),
        lambda _: _document(),
    ],
    ids=("admitted-wrapper", "bare-document"),
)
def test_public_rebuild_rejects_non_path_input_before_connect(
    monkeypatch: pytest.MonkeyPatch,
    forged: Callable[[ModuleType], object],
) -> None:
    module = _load_module()
    connect_calls: list[tuple[object, ...]] = []

    def _forbid_connect(*args: object) -> None:
        connect_calls.append(args)
        pytest.fail("public API must reject non-path inputs before connect")

    monkeypatch.setattr(module.psycopg, "connect", _forbid_connect)

    with pytest.raises(TypeError, match="bundle path"):
        module.rebuild_bundle(forged(module))
    assert connect_calls == []


def test_public_rebuild_is_path_only_and_admits_once_before_private_writer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    document = _document()
    parser_calls = 0
    guard_calls: list[Mapping[str, str]] = []
    rebuilt: list[tuple[object, str, str]] = []
    environ = {
        "DATABASE_URL": "url",
        "OKF_REBUILD_EXPECTED_DATABASE": "db",
        "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE": "1",
    }

    class _Parser:
        def parse_bundle(self, _: Path) -> BundleResult:
            nonlocal parser_calls
            parser_calls += 1
            return BundleResult(
                [document], BundleStats(parsed=1, skipped=0, malformed=0)
            )

    signature = inspect.signature(module.rebuild_bundle)
    assert tuple(signature.parameters) == ("bundle_path", "environ")
    assert signature.parameters["environ"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["environ"].default is None

    def _guard(env: Mapping[str, str]) -> tuple[str, str]:
        guard_calls.append(env)
        return "url", "db"

    def _writer(admitted: object, url: str, database: str) -> int:
        rebuilt.append((admitted, url, database))
        return 1

    def _forbid_connect(*_: object) -> None:
        pytest.fail("public API must delegate database access to the private writer")

    monkeypatch.setattr(module, "OKFParser", _Parser)
    monkeypatch.setattr(module, "_require_disposable_database_url", _guard)
    monkeypatch.setattr(module, "_rebuild_admitted_bundle", _writer)
    monkeypatch.setattr(module.psycopg, "connect", _forbid_connect)

    assert module.rebuild_bundle(Path("bundle"), environ=environ) == 1
    assert parser_calls == 1
    assert guard_calls == [environ]
    assert rebuilt[0][1:] == ("url", "db")
