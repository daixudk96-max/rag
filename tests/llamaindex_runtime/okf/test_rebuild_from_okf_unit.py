"""Unit coverage for deterministic Task 34 verifier and CLI guard branches."""

from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import json
import sys
from dataclasses import is_dataclass
from importlib.abc import Loader
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from llamaindex_runtime.okf.diagnostics import (
    diagnostic_safe_path,
    diagnostic_safe_text,
)
from llamaindex_runtime.okf.roundtrip import (
    first_roundtrip_mismatch,
    persisted_span_id_mismatch,
    recompute_span_dicts,
    roundtrip_mismatch,
)
from llamaindex_runtime.okf.sidecar import SpanRecord

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "rebuild_from_okf.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("task34_rebuild_unit", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _span(span_id: str = "00000000-0000-0000-0000-000000000010") -> SpanRecord:
    return SpanRecord(
        span_id=span_id,
        page_no=None,
        heading_path=("Heading",),
        offset=0,
        text="Text",
    )


def test_isolated_script_import_replaces_matching_path_poisoned_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper_path = REPO_ROOT / "scripts" / "_rebuild_database_connection.py"
    poison = ModuleType("_okf_rebuild_database_connection")
    poison.__file__ = str(helper_path)
    calls: list[str] = []

    def poisoned(*_: object, **__: object) -> object:
        calls.append("called")
        return object()

    helper_exports = (
        "DisposablePostgresqlTarget",
        "normalize_libpq_metadata",
        "parse_disposable_postgresql_target",
        "reject_ambient_service_routing",
        "runtime_connection_kwargs",
        "runtime_connection_factory",
        "pq",
    )
    bound_exports = (
        "_DisposablePostgresqlTarget",
        "_normalize_libpq_metadata",
        "_parse_disposable_postgresql_target",
        "_reject_ambient_service_routing",
        "_runtime_connection_kwargs",
        "_runtime_connection_factory",
        "pq",
    )
    for name in helper_exports:
        setattr(poison, name, poisoned)
    monkeypatch.setitem(sys.modules, poison.__name__, poison)

    module = _load_module()

    assert module._connection_support is not poison
    assert Path(module._connection_support.__file__).resolve() == helper_path.resolve()
    assert all(getattr(module, name) is not poisoned for name in bound_exports)
    target = module._parse_disposable_postgresql_target(
        "postgresql://okf:secret@127.0.0.1:5432/okf_task34", "okf_task34"
    )
    assert target.password == "secret"
    assert "secret" not in repr(target)
    assert calls == []


@pytest.mark.parametrize(
    ("prior", "is_absent"),
    ((None, True), (None, False), (object(), False)),
)
def test_connection_support_loader_restores_exact_prior_slot_after_success(
    monkeypatch: pytest.MonkeyPatch, prior: object | None, is_absent: bool
) -> None:
    module = _load_module()
    module_name = module._CONNECTION_HELPER_MODULE_NAME
    if is_absent:
        monkeypatch.delitem(sys.modules, module_name, raising=False)
    else:
        monkeypatch.setitem(sys.modules, module_name, prior)

    support = module._load_connection_support()

    if is_absent:
        assert module_name not in sys.modules
    else:
        assert sys.modules[module_name] is prior
    assert is_dataclass(support.DisposablePostgresqlTarget)
    target = support.parse_disposable_postgresql_target(
        "postgresql://user:secret@127.0.0.1:5432/db", "db"
    )
    assert type(target) is support.DisposablePostgresqlTarget
    assert "secret" not in repr(target)


def test_connection_support_loader_restores_slot_and_preserves_hijack_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class OriginalBaseException(BaseException):
        pass

    module = _load_module()
    module_name = module._CONNECTION_HELPER_MODULE_NAME
    for error in (Exception("ordinary execution error"), OriginalBaseException()):
        prior = object()
        attacker = ModuleType("attacker_connection_support")
        monkeypatch.setitem(sys.modules, module_name, prior)

        class HijackingLoader(Loader):
            def create_module(
                self, _: importlib.machinery.ModuleSpec
            ) -> ModuleType | None:
                return None

            def exec_module(self, _: ModuleType) -> None:
                sys.modules[module_name] = attacker
                raise error

        spec = importlib.machinery.ModuleSpec(module_name, HijackingLoader())
        monkeypatch.setattr(module, "spec_from_file_location", lambda *_: spec)

        with pytest.raises(type(error)) as captured:
            module._load_connection_support()

        assert captured.value is error
        assert sys.modules[module_name] is prior


def test_roundtrip_text_mismatch_redacts_content_deterministically() -> None:
    direct_text = "secret-direct-中文"
    okf_text = "secret-okf-🔒"
    direct: list[dict[str, Any]] = [
        {
            "span_id": "direct-id",
            "page_no": None,
            "heading_path": [],
            "offset": 0,
            "text": direct_text,
        }
    ]
    okf: list[dict[str, Any]] = [
        {
            "span_id": "okf-id",
            "page_no": None,
            "heading_path": [],
            "offset": 0,
            "text": okf_text,
        }
    ]

    mismatch = first_roundtrip_mismatch(
        direct, okf, doc_id="doc", file_path="raw/test.md"
    )

    assert mismatch == (
        "ROUNDTRIP MISMATCH at span[0]: field=text "
        f"direct={diagnostic_safe_text(direct_text)} "
        f"okf={diagnostic_safe_text(okf_text)} "
        f"(doc={diagnostic_safe_text('doc')} "
        f"file={diagnostic_safe_path('raw/test.md')})"
    )
    assert direct_text not in mismatch
    assert okf_text not in mismatch


def test_roundtrip_helpers_report_count_and_persisted_identity_failures() -> None:
    span = _span()
    recomputed = recompute_span_dicts(
        (span,),
        doc_id="00000000-0000-0000-0000-000000000001",
        version_id="00000000-0000-0000-0000-000000000002",
    )

    assert persisted_span_id_mismatch((span,), recomputed) is not None
    assert persisted_span_id_mismatch((), recomputed) == (
        "SIDECAR SPAN ID MISMATCH: persisted_count=0 recomputed_count=1"
    )
    assert first_roundtrip_mismatch(
        [], recomputed, doc_id="doc", file_path="raw/test.md"
    ) == (
        "ROUNDTRIP MISMATCH at span[0]: field=span_count direct=0 okf=1 "
        f"(doc={diagnostic_safe_text('doc')} "
        f"file={diagnostic_safe_path('raw/test.md')})"
    )


def test_roundtrip_prefers_direct_coordinate_mismatch_before_sidecar_id() -> None:
    span = _span()
    direct = [
        {
            "span_id": "00000000-0000-0000-0000-000000000011",
            "page_no": 1,
            "heading_path": ["Heading"],
            "offset": 0,
            "text": "Text",
        }
    ]

    assert roundtrip_mismatch(
        direct=direct,
        spans=(span,),
        doc_id="doc",
        version_id="version",
        file_path="raw/test.md",
    ) == (
        "ROUNDTRIP MISMATCH at span[0]: field=page_no direct=1 okf=None "
        f"(doc={diagnostic_safe_text('doc')} "
        f"file={diagnostic_safe_path('raw/test.md')})"
    )


def test_cli_argument_and_environment_guards_fail_closed() -> None:
    module = _load_module()

    with pytest.raises(SystemExit):
        module.parse_arguments(["--bundle", "bundle"])
    with pytest.raises(SystemExit):
        module.parse_arguments(["--bundle", "bundle", "--fixture", "docx", "--rebuild"])
    with pytest.raises(ValueError, match="DATABASE_URL"):
        module._require_disposable_database_url({})
    with pytest.raises(ValueError, match="OKF_MIGRATION_TEST_DATABASE_DISPOSABLE"):
        module._require_disposable_database_url({"DATABASE_URL": "isolated"})
    with pytest.raises(ValueError, match="OKF_REBUILD_EXPECTED_DATABASE"):
        module._require_disposable_database_url(
            {
                "DATABASE_URL": "isolated",
                "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE": "1",
            }
        )
    with pytest.raises(ValueError, match="OKF_REBUILD_EXPECTED_DATABASE"):
        module._require_disposable_database_url(
            {
                "DATABASE_URL": "isolated",
                "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE": "1",
                "OKF_REBUILD_EXPECTED_DATABASE": " \t\n ",
            }
        )
    with pytest.raises(ValueError, match="DATABASE_URL is required"):
        module._require_disposable_database_url(
            {
                "DATABASE_URL": " \t\n ",
                "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE": "1",
                "OKF_REBUILD_EXPECTED_DATABASE": "expected",
            }
        )
    assert module._require_disposable_database_url(
        {
            "DATABASE_URL": "  postgresql://okf:secret@127.0.0.1:5432/expected  ",
            "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE": "1",
            "OKF_REBUILD_EXPECTED_DATABASE": " expected \t",
        }
    ) == ("postgresql://okf:secret@127.0.0.1:5432/expected", "expected")


def test_verify_roundtrip_reports_missing_matching_fixture_document(
    tmp_path: Path,
) -> None:
    module = _load_module()
    fixture = module.FIXTURE_ROOT / "docx" / "expected_span_ids.json"
    expected = json.loads(fixture.read_text(encoding="utf-8"))

    fixture_path = "raw/docx.md"
    assert module.verify_roundtrip(module._AdmittedBundle(()), "docx") == (
        "ROUNDTRIP MISMATCH at span[0]: field=document_count direct_count=1 okf_count=0 "
        f"(doc={expected['doc_id']} file=len={len(fixture_path.encode('utf-8'))} "
        f"sha256={hashlib.sha256(fixture_path.encode('utf-8')).hexdigest()})"
    )


def test_rebuild_rejects_empty_raw_bundle_without_database_access(
    tmp_path: Path,
) -> None:
    module = _load_module()

    with pytest.raises(ValueError, match="No raw OKF documents"):
        module._rebuild_admitted_bundle(
            module._admit_bundle(tmp_path), "not-used", "expected"
        )


def test_fixture_loader_rejects_missing_and_malformed_expectations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_module()
    monkeypatch.setattr(module, "FIXTURE_ROOT", tmp_path)
    unsafe_fixture = "missing-canary-秘密"
    fixture_summary = (
        f"len={len(unsafe_fixture.encode('utf-8'))} "
        f"sha256={hashlib.sha256(unsafe_fixture.encode('utf-8')).hexdigest()}"
    )

    with pytest.raises(
        ValueError,
        match=f"^Fixture expectations unavailable: fixture={fixture_summary}$",
    ) as missing:
        module._load_expected_spans(unsafe_fixture)
    assert unsafe_fixture not in str(missing.value)

    unsafe_malformed_fixture = "fixture-canary-秘密"
    malformed = tmp_path / unsafe_malformed_fixture
    malformed.mkdir()
    (malformed / "expected_span_ids.json").write_text("[]", encoding="utf-8")
    with pytest.raises(
        ValueError, match="^Fixture expectations are malformed: fixture=len="
    ) as invalid:
        module._load_expected_spans(unsafe_malformed_fixture)
    assert unsafe_malformed_fixture not in str(invalid.value)


def test_missing_document_validates_fixture_scope_before_diagnostic() -> None:
    module = _load_module()
    unsafe_fixture = "fixture-canary-秘密"
    expected = {
        "doc_id": "not-a-canonical-uuid",
        "version_id": "00000000-0000-0000-0000-000000000002",
        "spans": [],
    }

    with pytest.raises(
        ValueError, match="^Fixture expectations are malformed: fixture=len="
    ) as captured:
        module._verify_fixture(module._AdmittedBundle(()), expected, unsafe_fixture)

    assert unsafe_fixture not in str(captured.value)


def test_main_returns_contract_statuses_without_database_access(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load_module()
    matching_args = module.argparse.Namespace(
        bundle=Path("bundle"), verify_roundtrip=True, fixture="docx", rebuild=False
    )
    monkeypatch.setattr(module, "parse_arguments", lambda _: matching_args)
    monkeypatch.setattr(module, "_admit_bundle", lambda _: module._AdmittedBundle(()))
    monkeypatch.setattr(module, "_verify_fixture", lambda *_: None)
    assert module.main([]) == 0

    monkeypatch.setattr(module, "_verify_fixture", lambda *_: "mismatch")
    assert module.main([]) == 1
    assert capsys.readouterr().err == "mismatch\n"

    missing_fixture_args = module.argparse.Namespace(
        bundle=Path("bundle"), verify_roundtrip=True, fixture=None, rebuild=False
    )
    monkeypatch.setattr(module, "parse_arguments", lambda _: missing_fixture_args)
    with pytest.raises(ValueError, match="--fixture is required"):
        module.main([])


def test_main_rebuild_passes_only_guarded_environment_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    args = module.argparse.Namespace(
        bundle=Path("bundle"), verify_roundtrip=False, fixture=None, rebuild=True
    )
    calls: list[object] = []
    monkeypatch.setattr(module, "parse_arguments", lambda _: args)
    monkeypatch.setattr(
        module,
        "_require_disposable_database_url",
        lambda env: ("guarded", "expected"),
    )
    admitted = module._AdmittedBundle(())

    def _writer(snapshot: object, database_url: str, expected_database: str) -> int:
        calls.append((snapshot, database_url, expected_database))
        return 1

    monkeypatch.setattr(module, "_admit_bundle", lambda _: admitted)
    monkeypatch.setattr(module, "_rebuild_admitted_bundle", _writer)

    assert module.main([]) == 0
    assert calls == [(admitted, "guarded", "expected")]
