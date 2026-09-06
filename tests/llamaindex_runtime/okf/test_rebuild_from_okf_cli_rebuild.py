"""Rebuild public API, database guards, and transaction fake behavior tests."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from psycopg import pq

from llamaindex_runtime.okf.parser import BundleResult, OKFDocument, OKFParser

from . import _rebuild_cli_testkit as cli_testkit
from . import _rebuild_integration_testkit as integration_testkit
from ._rebuild_cli_testkit import (
    Connection,
    Cursor,
    bundle_result,
    load_rebuild_module,
    make_bundle,
    run_cli,
)

_LIBPQ_ENVIRONMENT_KEYS = frozenset(
    default.envvar.decode("ascii")
    for default in pq.Conninfo.get_defaults()
    if default.envvar
)
_EXPLICIT_REMOVAL_EXTRAS = frozenset(
    {
        "PGREQUIRESSL",
        "PGSERVICEFILE",
        "PGSYSCONFDIR",
        "DATABASE_URL",
        "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE",
        "OKF_REBUILD_EXPECTED_DATABASE",
        "OKF_FAILURE_AUDIT_ACCEPTANCE",
        "OKF_REBUILD_DOCKER_ACCEPTANCE",
    }
)
_REQUIRED_PROCESS_ENVIRONMENT = {
    "PATH": "posix-path-canary",
    "HOME": "posix-home-canary",
    "SYSTEMROOT": r"C:\Windows",
    "COMSPEC": r"C:\Windows\System32\cmd.exe",
}
_EXPLICIT_REBUILD_ENVIRONMENT_KEYS = {
    "DATABASE_URL",
    "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE",
    "OKF_REBUILD_EXPECTED_DATABASE",
}


def test_rebuild_testkits_remove_all_libpq_canaries_without_parent_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    expected_removals = _LIBPQ_ENVIRONMENT_KEYS | _EXPLICIT_REMOVAL_EXTRAS
    assert cli_testkit._DATABASE_ENVIRONMENT_KEYS == expected_removals
    assert isinstance(cli_testkit._DATABASE_ENVIRONMENT_KEYS, frozenset)
    canaries = {key: f"canary-{key.lower()}" for key in expected_removals}
    for key, value in (canaries | _REQUIRED_PROCESS_ENVIRONMENT).items():
        monkeypatch.setenv(key, value)
    parent_before = dict(cli_testkit.os.environ)
    captured: list[dict[str, str]] = []

    def fake_run(_: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        captured.append(environment)
        return subprocess.CompletedProcess([], 0, "", "")

    monkeypatch.setattr(cli_testkit.subprocess, "run", fake_run)
    monkeypatch.setattr(integration_testkit.subprocess, "run", fake_run)
    database_url = integration_testkit._RedactedDatabaseUrl(
        "postgresql://okf:secret@127.0.0.1:5432/okf_task34"
    )
    cli_testkit.run_cli(
        "--help", database_url=database_url, expected_database="okf_task34"
    )
    integration_testkit._run_cli(tmp_path, database_url)

    assert dict(cli_testkit.os.environ) == parent_before
    assert len(captured) == 2
    for environment in captured:
        assert (
            not (canaries.keys() - _EXPLICIT_REBUILD_ENVIRONMENT_KEYS)
            & environment.keys()
        )
        assert {key: environment[key] for key in _REQUIRED_PROCESS_ENVIRONMENT} == (
            _REQUIRED_PROCESS_ENVIRONMENT
        )
        assert environment["DATABASE_URL"] == database_url
        assert environment["OKF_MIGRATION_TEST_DATABASE_DISPOSABLE"] == "1"
        assert environment["OKF_REBUILD_EXPECTED_DATABASE"] == "okf_task34"


def test_disposable_connection_factory_neutralizes_libpq_environment_canaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canaries = {
        key: f"ambient-{key.lower()}"
        for key in _LIBPQ_ENVIRONMENT_KEYS
        if key not in {"PGSERVICE", "PGSERVICEFILE", "PGSYSCONFDIR"}
    } | {
        "PGREQUIRESSL": "1",
    }
    for key, value in canaries.items():
        monkeypatch.setenv(key, value)
    parent_before = dict(integration_testkit.os.environ)
    captured: dict[str, object] = {}
    sentinel = object()

    def fake_connect(**kwargs: object) -> object:
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(cli_testkit.psycopg, "connect", fake_connect)
    result = integration_testkit._disposable_connection(
        integration_testkit._RedactedDatabaseUrl(
            "postgresql://okf:disposable-password@127.0.0.1:5432/okf_task34"
        ),
        autocommit=True,
        connect_timeout=1,
    )

    assert result is sentinel
    assert dict(integration_testkit.os.environ) == parent_before
    assert {
        default.keyword.decode("ascii")
        for default in pq.Conninfo.get_defaults()
        if default.envvar and default.keyword != b"service"
    } <= captured.keys()
    assert "service" not in captured
    assert not set(canaries.values()) & set(captured.values())
    assert captured["options"] == "-c search_path=public"
    assert captured["sslmode"] == "disable"
    assert captured["sslnegotiation"] == "postgres"
    assert captured["gssencmode"] == "disable"
    assert captured["require_auth"] == "scram-sha-256"
    assert captured["channel_binding"] == "disable"
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 5432
    assert captured["dbname"] == "okf_task34"
    assert captured["user"] == "okf"
    assert captured["autocommit"] is True
    assert captured["connect_timeout"] == 1


@pytest.mark.parametrize("service_key", ("PGSERVICE", "PGSERVICEFILE", "PGSYSCONFDIR"))
def test_disposable_connection_factory_refuses_ambient_service_routing(
    monkeypatch: pytest.MonkeyPatch, service_key: str
) -> None:
    monkeypatch.setenv(service_key, "ambient-service-routing-canary")
    calls: list[dict[str, object]] = []

    def fake_connect(**kwargs: object) -> object:
        calls.append(kwargs)
        return object()

    monkeypatch.setattr(cli_testkit.psycopg, "connect", fake_connect)

    with pytest.raises(ValueError, match="service routing"):
        integration_testkit._disposable_connection(
            integration_testkit._RedactedDatabaseUrl(
                "postgresql://okf:disposable-password@127.0.0.1:5432/okf_task34"
            )
        )

    assert calls == []


def test_rebuild_requires_disposable_database_guard_before_connecting(
    tmp_path: Path,
) -> None:
    bundle = make_bundle(tmp_path, "sectioned-pdf")

    result = run_cli("--bundle", str(bundle), "--rebuild")

    assert result.returncode == 2
    product_line = result.stderr.splitlines()[-1]
    assert (
        product_line
        == "DATABASE_URL is required for --rebuild; refusing database access"
    )
    assert not any(character.isprintable() is False for character in product_line)


def test_rebuild_rejects_whitespace_database_url_before_connecting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = make_bundle(tmp_path, "sectioned-pdf")
    module = load_rebuild_module()
    calls: list[object] = []
    monkeypatch.setattr(
        module,
        "parse_arguments",
        lambda _: argparse.Namespace(
            bundle=bundle, verify_roundtrip=False, fixture=None, rebuild=True
        ),
    )
    monkeypatch.setattr(
        module.os,
        "environ",
        {
            "DATABASE_URL": " \t\n ",
            "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE": "1",
            "OKF_REBUILD_EXPECTED_DATABASE": "expected",
        },
    )
    monkeypatch.setattr(module.psycopg, "connect", lambda _: calls.append("connect"))

    with pytest.raises(ValueError, match="DATABASE_URL is required"):
        module.main([])


def test_rebuild_redacts_database_driver_connection_errors(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path, "sectioned-pdf")
    canary_url = "not-a-valid-dsn-task46-canary-password"

    result = run_cli(
        "--bundle",
        str(bundle),
        "--rebuild",
        database_url=canary_url,
        expected_database="canary_expected_database",
    )

    assert result.returncode == 2
    assert result.stdout == ""
    product_line = result.stderr.splitlines()[-1]
    assert product_line == "Invalid disposable PostgreSQL target; refusing rebuild"
    assert not any(character.isprintable() is False for character in product_line)
    for stream in (result.stdout, result.stderr):
        assert canary_url not in stream
        assert "task46-canary-password" not in stream


def test_rebuild_requires_expected_database_before_connecting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = make_bundle(tmp_path, "sectioned-pdf")
    module = load_rebuild_module()
    calls: list[object] = []
    monkeypatch.setattr(
        module,
        "parse_arguments",
        lambda _: argparse.Namespace(
            bundle=bundle, verify_roundtrip=False, fixture=None, rebuild=True
        ),
    )
    monkeypatch.setattr(
        module.os,
        "environ",
        {
            "DATABASE_URL": "postgresql://redacted",
            "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE": "1",
        },
    )
    monkeypatch.setattr(module.psycopg, "connect", lambda _: calls.append("connect"))

    with pytest.raises(ValueError, match="OKF_REBUILD_EXPECTED_DATABASE"):
        module.main([])

    assert calls == []


def test_rebuild_rejects_duplicate_document_versions_before_connecting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = make_bundle(tmp_path, "sectioned-pdf")
    document = OKFParser().parse_bundle(bundle)[0]
    module = load_rebuild_module()

    class _DuplicateParser:
        def parse_bundle(self, _: Path) -> BundleResult:
            return bundle_result(document, document)

    def _fail_connect(_: str) -> None:
        pytest.fail("psycopg.connect must not be called for duplicate bundle documents")

    monkeypatch.setattr(module, "OKFParser", _DuplicateParser)
    monkeypatch.setattr(module.psycopg, "connect", _fail_connect)

    with pytest.raises(ValueError, match="Duplicate raw OKF document version"):
        module._rebuild_admitted_bundle(
            module._admit_bundle(bundle), "unused", "expected"
        )


def test_admitted_writer_rejects_duplicate_desired_span_ids_before_dml(
    tmp_path: Path,
) -> None:
    bundle = make_bundle(tmp_path, "sectioned-pdf")
    document = OKFParser().parse_bundle(bundle)[0]
    duplicate_document = replace(document, spans=(document.spans[0], document.spans[0]))
    module = load_rebuild_module()
    cursor = Cursor()

    with pytest.raises(ValueError, match="Duplicate canonical span ID"):
        module._rebuild_admitted_document(
            Connection(cursor), module._freeze_raw_document(duplicate_document)
        )

    assert cursor.executed == []


def test_rebuild_bundle_rebuilds_raw_documents_in_stable_scope_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = make_bundle(tmp_path, "sectioned-pdf")
    document = OKFParser().parse_bundle(bundle)[0]
    later_scope = _with_scope(document, "00000000-0000-0000-0000-000000000002")
    earlier_scope = _with_scope(document, "00000000-0000-0000-0000-000000000001")
    module = load_rebuild_module()
    connection = Connection(Cursor([[("expected",)]]))
    rebuilt_scopes: list[tuple[str, str]] = []

    class _ReverseScopeParser:
        def parse_bundle(self, _: Path) -> BundleResult:
            return bundle_result(later_scope, earlier_scope)

    def _record_rebuild(_: Any, admitted: Any) -> int:
        rebuilt_scopes.append((admitted.doc_id, admitted.version_id))
        return 1

    monkeypatch.setattr(module, "OKFParser", _ReverseScopeParser)
    monkeypatch.setattr(module.psycopg, "connect", lambda **_: connection)
    monkeypatch.setattr(module, "_rebuild_admitted_document", _record_rebuild)

    assert (
        module._rebuild_admitted_bundle(
            module._admit_bundle(bundle),
            "postgresql://okf:secret@127.0.0.1:5432/expected",
            "expected",
        )
        == 2
    )
    assert rebuilt_scopes == [
        (earlier_scope.frontmatter.doc_id, earlier_scope.frontmatter.version_id),
        (later_scope.frontmatter.doc_id, later_scope.frontmatter.version_id),
    ]


def _with_scope(document: OKFDocument, scope: str) -> OKFDocument:
    return replace(
        document,
        frontmatter=replace(document.frontmatter, doc_id=scope, version_id=scope),
    )


def test_rebuild_bundle_rejects_database_identity_before_version_lock_or_dml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = make_bundle(tmp_path, "sectioned-pdf")
    module = load_rebuild_module()
    cursor = Cursor([[("unexpected",)]])
    connection = Connection(cursor)

    monkeypatch.setattr(module.psycopg, "connect", lambda **_: connection)

    with pytest.raises(ValueError, match="database identity"):
        module._rebuild_admitted_bundle(
            module._admit_bundle(bundle),
            "postgresql://okf:secret@127.0.0.1:5432/expected",
            "expected",
        )

    assert cursor.executed == [("SELECT current_database()", None)]
    assert connection.transactions == 0
    assert connection.rolled_back is True


def test_rebuild_bundle_uses_one_transaction_and_reports_only_changed_documents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = make_bundle(tmp_path, "sectioned-pdf")
    document = OKFParser().parse_bundle(bundle)[0]
    module = load_rebuild_module()
    cursor = Cursor([[("expected",)], [(1,)], [], []])
    connection = Connection(cursor)

    class _Parser:
        def parse_bundle(self, _: Path) -> BundleResult:
            return bundle_result(document)

    monkeypatch.setattr(module, "OKFParser", _Parser)
    monkeypatch.setattr(module.psycopg, "connect", lambda **_: connection)

    assert (
        module._rebuild_admitted_bundle(
            module._admit_bundle(bundle),
            "postgresql://okf:secret@127.0.0.1:5432/expected",
            "expected",
        )
        == 1
    )
    assert connection.transactions == 0
    assert connection.committed is True
    assert cursor.executed[0] == ("SELECT current_database()", None)
    assert any(
        query.startswith("INSERT INTO canonical_spans") for query, _ in cursor.executed
    )
    assert not any(
        query == "DELETE FROM canonical_spans WHERE version_id = %s"
        for query, _ in cursor.executed
    )


def test_rebuild_bundle_rolls_back_earlier_documents_and_logs_on_later_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = make_bundle(tmp_path, "sectioned-pdf")
    document = OKFParser().parse_bundle(bundle)[0]
    failing_document = _with_scope(document, "00000000-0000-0000-0000-000000000002")
    module = load_rebuild_module()
    primary_connection = Connection(Cursor([[("expected",)]]))
    audit_connection = Connection(Cursor([[("expected",)]]))
    connections = [primary_connection, audit_connection]
    rebuilt_scopes: list[tuple[str, str]] = []

    class _Parser:
        def parse_bundle(self, _: Path) -> BundleResult:
            return bundle_result(document, failing_document)

    def _fail_after_first(_: Any, admitted: Any) -> int:
        rebuilt_scopes.append((admitted.doc_id, admitted.version_id))
        if admitted.doc_id == failing_document.frontmatter.doc_id:
            raise ValueError("not registered")
        return 1

    monkeypatch.setattr(module, "OKFParser", _Parser)
    monkeypatch.setattr(module, "_rebuild_admitted_document", _fail_after_first)

    with pytest.raises(ValueError, match="not registered"):
        module._rebuild_admitted_bundle(
            module._admit_bundle(bundle),
            "unused",
            "expected",
            connection_factory=lambda _: connections.pop(0),
        )

    assert rebuilt_scopes == [
        (document.frontmatter.doc_id, document.frontmatter.version_id),
        (failing_document.frontmatter.doc_id, failing_document.frontmatter.version_id),
    ]
    assert connections == []
    assert primary_connection.transactions == 0
    assert primary_connection.rolled_back is True
    assert audit_connection.transactions == 1


def test_argument_and_database_guards_reject_invalid_cli_surfaces(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = load_rebuild_module()

    with pytest.raises(SystemExit, match="2"):
        module.parse_arguments(["--bundle", "bundle"])
    assert (
        "one of --verify-roundtrip or --rebuild is required" in capsys.readouterr().err
    )

    with pytest.raises(SystemExit, match="2"):
        module.parse_arguments(["--bundle", "bundle", "--rebuild", "--fixture", "docx"])
    assert "--fixture requires --verify-roundtrip" in capsys.readouterr().err

    _assert_database_guard_rejections(module)
    assert module._require_disposable_database_url(
        {
            "DATABASE_URL": "  postgresql://okf:secret@127.0.0.1:5432/expected  ",
            "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE": "1",
            "OKF_REBUILD_EXPECTED_DATABASE": " expected \t",
        }
    ) == ("postgresql://okf:secret@127.0.0.1:5432/expected", "expected")


def _assert_database_guard_rejections(module: Any) -> None:
    with pytest.raises(ValueError, match="DATABASE_URL is required"):
        module._require_disposable_database_url({})
    with pytest.raises(ValueError, match="DISPOSABLE=1 is required"):
        module._require_disposable_database_url({"DATABASE_URL": "test-url"})
    with pytest.raises(ValueError, match="OKF_REBUILD_EXPECTED_DATABASE"):
        module._require_disposable_database_url(
            {"DATABASE_URL": "test-url", "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE": "1"}
        )
    with pytest.raises(ValueError, match="OKF_REBUILD_EXPECTED_DATABASE"):
        module._require_disposable_database_url(
            {
                "DATABASE_URL": "test-url",
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


def test_verify_roundtrip_handles_fixture_errors_and_document_count_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_rebuild_module()
    monkeypatch.setattr(module, "FIXTURE_ROOT", tmp_path)

    _assert_fixture_load_errors(module, tmp_path)
    fixture = tmp_path / "count"
    fixture.mkdir()
    (fixture / "expected_span_ids.json").write_text(
        json.dumps(
            {
                "doc_id": "00000000-0000-0000-0000-000000000001",
                "version_id": "00000000-0000-0000-0000-000000000002",
                "spans": [],
            }
        ),
        encoding="utf-8",
    )

    assert (
        module.verify_roundtrip(module._AdmittedBundle(()), "count")
        == _count_mismatch_line()
    )


def _assert_fixture_load_errors(module: Any, tmp_path: Path) -> None:
    absent_summary = (
        f"len={len('absent')} sha256={hashlib.sha256(b'absent').hexdigest()}"
    )
    with pytest.raises(
        ValueError,
        match=f"^Fixture expectations unavailable: fixture={absent_summary}$",
    ):
        module._load_expected_spans("absent")
    malformed = tmp_path / "malformed"
    malformed.mkdir()
    (malformed / "expected_span_ids.json").write_text("[]", encoding="utf-8")
    summary = (
        f"len={len('malformed')} sha256={hashlib.sha256(b'malformed').hexdigest()}"
    )
    with pytest.raises(
        ValueError, match=f"^Fixture expectations are malformed: fixture={summary}$"
    ):
        module._load_expected_spans("malformed")


def _count_mismatch_line() -> str:
    safe_file = "raw/count.md"
    return (
        "ROUNDTRIP MISMATCH at span[0]: field=document_count direct_count=1 okf_count=0 "
        "(doc=00000000-0000-0000-0000-000000000001 "
        f"file=len={len(safe_file.encode('utf-8'))} sha256={hashlib.sha256(safe_file.encode('utf-8')).hexdigest()})"
    )


def test_rebuild_bundle_rejects_malformed_bundle_before_connecting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = make_bundle(tmp_path, "sectioned-pdf")
    (bundle / "malformed.md").write_text("---\ninvalid: [\n---\n", encoding="utf-8")
    module = load_rebuild_module()

    monkeypatch.setattr(
        module.psycopg,
        "connect",
        lambda _: pytest.fail(
            "psycopg.connect must not be called for malformed bundles"
        ),
    )

    with pytest.raises(ValueError, match="malformed"):
        module._rebuild_admitted_bundle(
            module._admit_bundle(bundle), "unused", "expected"
        )


def test_rebuild_bundle_rejects_no_raw_documents_and_invalid_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_rebuild_module()
    document = OKFParser().parse_bundle(make_bundle(tmp_path, "sectioned-pdf"))[0]

    class _NonRawParser:
        def parse_bundle(self, _: Path) -> BundleResult:
            return bundle_result(
                OKFDocument(
                    frontmatter=replace(document.frontmatter, type="derived"),
                    spans=document.spans,
                    body=document.body,
                    file_path=document.file_path,
                    canonical_hash=document.canonical_hash,
                )
            )

    monkeypatch.setattr(module, "OKFParser", _NonRawParser)
    with pytest.raises(ValueError, match="No raw OKF documents"):
        module._rebuild_admitted_bundle(
            module._admit_bundle(tmp_path), "unused", "expected"
        )

    invalid = replace(
        document, frontmatter=replace(document.frontmatter, doc_id="not-a-uuid")
    )
    with pytest.raises(ValueError):
        module._rebuild_admitted_document(
            Connection(Cursor([])), module._freeze_raw_document(invalid)
        )


@pytest.mark.parametrize(
    "database_url",
    (
        "postgresql://okf:secret@localhost:5432/okf_task34",
        "postgresql://okf:secret@127.0.0.1/okf_task34",
        "postgresql://okf:secret@127.0.0.1:5432/other_database",
        "postgresql://okf:secret@127.0.0.1:5432/okf_task34?sslmode=require",
        "postgresql://okf:secret@127.0.0.1:5432/okf_task34?",
        "postgresql://okf:secret@127.0.0.1:5432/okf_task34#fragment",
        "postgresql://okf:secret@127.0.0.1:5432/okf_task34#",
        "postgresql://okf@127.0.0.1:5432/okf_task34",
        "postgresql://okf:secret@127.0.0.1,127.0.0.2:5432/okf_task34",
    ),
)
def test_runtime_target_parser_rejects_non_exact_postgresql_uris_before_connect(
    database_url: str,
) -> None:
    module = load_rebuild_module()

    with pytest.raises(ValueError, match="disposable PostgreSQL target"):
        module._parse_disposable_postgresql_target(database_url, "okf_task34")


def test_runtime_target_parser_returns_frozen_redacted_connection_target() -> None:
    module = load_rebuild_module()

    target = module._parse_disposable_postgresql_target(
        "postgresql://okf:secret@127.0.0.1:5432/okf_task34", "okf_task34"
    )

    assert target.host == target.hostaddr == "127.0.0.1"
    assert (target.port, target.dbname, target.user, target.password) == (
        5432,
        "okf_task34",
        "okf",
        "secret",
    )
    assert "secret" not in repr(target)


@pytest.mark.parametrize("value", (b"PGHOST", "PGHOST", None))
def test_libpq_metadata_normalization_accepts_exact_bytes_str_or_none(
    value: object,
) -> None:
    module = load_rebuild_module()

    assert module._normalize_libpq_metadata(value) == (
        value.decode("ascii") if isinstance(value, bytes) else value
    )


@pytest.mark.parametrize("value", (1, bytearray(b"PGHOST"), object()))
def test_libpq_metadata_normalization_rejects_unsupported_types(value: object) -> None:
    module = load_rebuild_module()

    with pytest.raises(TypeError, match="libpq metadata"):
        module._normalize_libpq_metadata(value)


def test_default_runtime_factory_uses_only_explicit_kwargs_for_primary_and_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_rebuild_module()
    calls: list[dict[str, object]] = []

    def fake_connect(*args: object, **kwargs: object) -> object:
        assert args == ()
        calls.append(kwargs)
        return Connection(Cursor([[("okf_task34",)]]))

    monkeypatch.setattr(module.psycopg, "connect", fake_connect)
    target = module._parse_disposable_postgresql_target(
        "postgresql://okf:secret@127.0.0.1:5432/okf_task34", "okf_task34"
    )

    assert module._runtime_connection_factory(target) is not None
    assert module._runtime_connection_factory(target) is not None
    assert len(calls) == 2
    for kwargs in calls:
        assert kwargs["host"] == kwargs["hostaddr"] == "127.0.0.1"
        assert kwargs["dbname"] == "okf_task34"
        assert kwargs["options"] == "-c search_path=public"
        assert kwargs["connect_timeout"] == 5
        assert "service" not in kwargs


def test_runtime_connection_kwargs_filter_controls_to_installed_capabilities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_rebuild_module()

    class _Metadata:
        def __init__(self, keyword: bytes, envvar: bytes | None) -> None:
            self.keyword = keyword
            self.envvar = envvar

    class _Conninfo:
        @staticmethod
        def get_defaults() -> tuple[_Metadata, ...]:
            return (
                _Metadata(b"service", b"PGSERVICE"),
                _Metadata(b"user", b"PGUSER"),
                _Metadata(b"password", b"PGPASSWORD"),
                _Metadata(b"dbname", b"PGDATABASE"),
                _Metadata(b"host", b"PGHOST"),
                _Metadata(b"hostaddr", b"PGHOSTADDR"),
                _Metadata(b"port", b"PGPORT"),
                _Metadata(b"client_encoding", b"PGCLIENTENCODING"),
            )

    monkeypatch.setattr(module.pq, "Conninfo", _Conninfo)
    target = module._parse_disposable_postgresql_target(
        "postgresql://okf:secret@127.0.0.1:5432/okf_task34", "okf_task34"
    )

    assert module._runtime_connection_kwargs(target) == {
        "user": "okf",
        "password": "secret",
        "dbname": "okf_task34",
        "host": "127.0.0.1",
        "hostaddr": "127.0.0.1",
        "port": 5432,
        "connect_timeout": 5,
        "client_encoding": "UTF8",
        "autocommit": False,
    }


@pytest.mark.parametrize("service_key", ("PGSERVICE", "PGSERVICEFILE", "PGSYSCONFDIR"))
def test_runtime_factory_refuses_ambient_service_routing_before_connect(
    monkeypatch: pytest.MonkeyPatch, service_key: str
) -> None:
    module = load_rebuild_module()
    monkeypatch.setenv(service_key, "ambient-service")
    monkeypatch.setattr(
        module.psycopg,
        "connect",
        lambda *_args, **_kwargs: pytest.fail("must reject before connecting"),
    )
    target = module._parse_disposable_postgresql_target(
        "postgresql://okf:secret@127.0.0.1:5432/okf_task34", "okf_task34"
    )

    with pytest.raises(ValueError, match="service routing"):
        module._runtime_connection_factory(target)
