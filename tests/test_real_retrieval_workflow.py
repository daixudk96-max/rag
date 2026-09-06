from __future__ import annotations

import subprocess
from types import SimpleNamespace

import psycopg
import pytest

import scripts.run_pageindex_real_retrieval_workflow as workflow
from scripts.run_pageindex_real_retrieval_workflow import (
    MIGRATION_FILES,
    database_is_reachable,
    ensure_local_pgvector_container,
    main,
    parse_postgres_database_url,
    _validate_local_database_target,
    _wrap_command,
)


class _FakeCursor:
    def __init__(self, fail_on_call: int | None = None) -> None:
        self.executed_sql: list[str] = []
        self._fail_on_call = fail_on_call

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def execute(self, sql: str) -> None:
        self.executed_sql.append(sql)
        if (
            self._fail_on_call is not None
            and len(self.executed_sql) == self._fail_on_call
        ):
            raise RuntimeError("boom")


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor

    def __enter__(self) -> _FakeConnection:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return self._cursor


def test_real_retrieval_workflow_has_exact_migration_order() -> None:
    assert MIGRATION_FILES == (
        "001_initial.sql",
        "002_version_lifecycle.sql",
        "003_tree_persistence.sql",
        "004_vector_extension.sql",
        "007_processing_status.sql",
    )
    assert "005_kg_extension.sql" not in MIGRATION_FILES
    assert not any(
        migration.startswith(("015_", "016_", "017_", "018_"))
        for migration in MIGRATION_FILES
    )


def test_parse_postgres_database_url_extracts_expected_fields() -> None:
    parsed = parse_postgres_database_url(
        "postgresql://postgres:postgres@localhost:5432/rag"
    )

    assert parsed["scheme"] == "postgresql"
    assert parsed["host"] == "127.0.0.1"
    assert parsed["port"] == 5432
    assert parsed["database"] == "rag"
    assert parsed["user"] == "postgres"
    assert parsed["password"] == "postgres"


def test_database_is_reachable_returns_false_on_connection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_error(*args, **kwargs):
        raise psycopg.OperationalError("connect failed")

    monkeypatch.setattr(
        "scripts.run_pageindex_real_retrieval_workflow.psycopg.connect",
        _raise_error,
    )

    assert (
        database_is_reachable("postgresql://postgres:postgres@localhost:5432/rag")
        is False
    )


def test_ensure_local_pgvector_container_raises_when_docker_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scripts.run_pageindex_real_retrieval_workflow.shutil.which",
        lambda _name: "docker",
    )

    def _raise_called_process_error(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "docker")

    monkeypatch.setattr(
        "scripts.run_pageindex_real_retrieval_workflow._run_command",
        _raise_called_process_error,
    )

    with pytest.raises(
        workflow._WorkflowError, match="Docker stage failed: daemon is not reachable"
    ):
        ensure_local_pgvector_container(
            "postgresql://postgres:postgres@localhost:5432/rag"
        )


@pytest.mark.parametrize(
    ("database_url", "expected_host"),
    [
        ("postgresql://postgres:postgres@localhost:5432/rag", "127.0.0.1"),
        ("postgresql://postgres:postgres@127.0.0.1:5432/rag", "127.0.0.1"),
    ],
)
def test_validate_local_database_target_accepts_normalized_loopback_hosts(
    database_url: str, expected_host: str
) -> None:
    assert _validate_local_database_target(database_url) == expected_host


def test_main_rejects_remote_database_before_any_side_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = "postgresql://postgres:never-log-me@db.example.com:5432/rag"
    calls: list[str] = []

    monkeypatch.setattr(
        "scripts.run_pageindex_real_retrieval_workflow.RuntimeSettings.from_env",
        lambda: SimpleNamespace(database_url=database_url),
    )

    def _unexpected_call(*args, **kwargs) -> None:
        calls.append("side effect")
        raise AssertionError("remote database URL must be rejected before side effects")

    monkeypatch.setattr(
        "scripts.run_pageindex_real_retrieval_workflow.database_is_reachable",
        _unexpected_call,
    )
    monkeypatch.setattr(
        "scripts.run_pageindex_real_retrieval_workflow.ensure_local_pgvector_container",
        _unexpected_call,
    )
    monkeypatch.setattr(
        "scripts.run_pageindex_real_retrieval_workflow.apply_migrations",
        _unexpected_call,
    )
    monkeypatch.setattr(
        "scripts.run_pageindex_real_retrieval_workflow._run_python_script",
        _unexpected_call,
    )

    with pytest.raises(SystemExit, match="local loopback") as exc_info:
        main()

    assert calls == []
    assert "never-log-me" not in str(exc_info.value)
    assert "db.example.com" not in str(exc_info.value)


def test_wrap_command_proxies_docker_but_preserves_other_commands() -> None:
    assert _wrap_command(("docker", "ps")) == ["rtk", "proxy", "docker", "ps"]
    assert _wrap_command(("python", "script.py")) == ["python", "script.py"]


@pytest.mark.parametrize(
    ("database_url", "expected_host"),
    [
        ("postgresql://postgres:password@localhost:5432/rag", "127.0.0.1"),
        ("postgres://postgres:password@127.0.0.1/rag", "127.0.0.1"),
        ("postgresql://postgres:password@[::1]:5432/rag", "::1"),
    ],
)
def test_validate_local_database_target_accepts_only_canonical_loopback_urls(
    database_url: str, expected_host: str
) -> None:
    assert _validate_local_database_target(database_url) == expected_host


def test_run_command_delegates_to_subprocess_with_supplied_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def _run(*args, **kwargs) -> subprocess.CompletedProcess[str]:
        calls.append(kwargs)
        return subprocess.CompletedProcess(args[0], 0, stdout="", stderr="")

    monkeypatch.setattr(workflow.subprocess, "run", _run)

    result = workflow._run_command(("docker", "ps"), env={"SAFE": "value"})

    assert result.returncode == 0
    assert calls == [
        {
            "cwd": workflow.REPO_ROOT,
            "check": True,
            "text": True,
            "capture_output": True,
            "timeout": 600,
            "env": {"SAFE": "value"},
        }
    ]


def test_print_completed_output_prints_nonempty_streams(
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow._print_completed_output(
        subprocess.CompletedProcess(
            ["command"], 0, stdout=" standard ", stderr=" error "
        )
    )

    assert capsys.readouterr().out.splitlines() == ["standard", "error"]


def test_database_is_reachable_returns_true_for_a_valid_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        workflow.psycopg,
        "connect",
        lambda **_kwargs: _FakeConnection(_FakeCursor()),
    )

    assert database_is_reachable("postgresql://postgres:password@localhost/rag")


def test_ensure_local_pgvector_container_requires_docker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(workflow.shutil, "which", lambda _name: None)

    with pytest.raises(
        workflow._WorkflowError, match="Docker stage failed: docker is required"
    ):
        ensure_local_pgvector_container("postgresql://postgres:password@localhost/rag")


def test_existing_stopped_container_is_started(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    commands: list[list[str]] = []

    def _run_command(*args, **kwargs) -> subprocess.CompletedProcess[str]:
        command = list(args[0])
        commands.append(command)
        if command[:2] == ["docker", "ps"]:
            return subprocess.CompletedProcess(command, 0, "rag-pg|Exited", "")
        return subprocess.CompletedProcess(command, 0, "started", "")

    monkeypatch.setattr(workflow, "_run_command", _run_command)

    workflow._find_start_or_create_pgvector_container(
        container_name="rag-pg",
        image="ignored",
        target=workflow._local_database_target(
            "postgresql://postgres:password@localhost:5432/rag"
        ),
    )

    assert commands[-1] == ["docker", "start", "rag-pg"]
    assert capsys.readouterr().out.strip() == "started"


def test_validate_local_database_target_rejects_non_string_and_missing_fields() -> None:
    with pytest.raises(RuntimeError, match="valid local loopback"):
        _validate_local_database_target(None)  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="valid local loopback"):
        _validate_local_database_target("postgresql://:password@localhost/rag")


def test_run_python_script_validates_url_and_passes_it_only_in_child_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _run_command(args, *, cwd=workflow.REPO_ROOT, timeout=600, env=None):
        captured["args"] = list(args)
        captured["cwd"] = cwd
        captured["env"] = env
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(workflow, "_run_command", _run_command)

    workflow._run_python_script(
        "test_real_integration.py",
        database_url="postgresql://postgres:password@localhost/rag",
    )

    assert captured["args"] == [
        workflow.sys.executable,
        str(workflow.REPO_ROOT / "test_real_integration.py"),
    ]
    assert captured["cwd"] == workflow.REPO_ROOT
    assert isinstance(captured["env"], dict)
    assert (
        captured["env"]["DATABASE_URL"]
        == "postgresql://postgres:password@127.0.0.1:5432/rag"
    )


def test_ensure_local_pgvector_container_creates_then_waits_without_docker(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[list[str]] = []
    waited_for: list[dict[str, object]] = []

    monkeypatch.setattr(workflow.shutil, "which", lambda _name: "docker")

    def _run_command(args, *, cwd=workflow.REPO_ROOT, timeout=600, env=None):
        command = list(args)
        calls.append(command)
        if command[:2] == ["docker", "ps"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="created", stderr="")

    monkeypatch.setattr(workflow, "_run_command", _run_command)
    monkeypatch.setattr(
        workflow,
        "_wait_for_pgvector_container",
        lambda **kwargs: waited_for.append(kwargs),
    )

    ensure_local_pgvector_container("postgresql://postgres:password@localhost/rag")

    assert calls[-1][:2] == ["docker", "run"]
    assert waited_for == [
        {
            "container_name": workflow.CONTAINER_NAME,
            "target": workflow._local_database_target(
                "postgresql://postgres:password@localhost/rag"
            ),
        }
    ]
    assert capsys.readouterr().out.strip() == "created"


def test_wait_for_pgvector_container_returns_when_first_probe_is_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probes: list[list[str]] = []

    def _run(args, **kwargs) -> SimpleNamespace:
        probes.append(list(args))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(workflow.subprocess, "run", _run)

    workflow._wait_for_pgvector_container(
        container_name="rag-pg",
        target=workflow._local_database_target(
            "postgresql://postgres:password@localhost:5432/rag"
        ),
    )

    assert probes[0][:3] == ["rtk", "proxy", "docker"]
