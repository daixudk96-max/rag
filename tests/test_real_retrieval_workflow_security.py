from __future__ import annotations

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

import pytest

import scripts.run_pageindex_real_retrieval_workflow as workflow
from scripts.run_pageindex_real_retrieval_workflow import (
    ensure_local_pgvector_container,
    main,
)
import psycopg


class _HostileError(Exception):
    def __str__(self) -> str:
        raise AssertionError("exception __str__ must not be called")

    def __repr__(self) -> str:
        raise AssertionError("exception __repr__ must not be called")


def _installed_libpq_envvars() -> set[str]:
    envvars: set[str] = set()
    for option in psycopg.pq.Conninfo.get_defaults():
        metadata_value: object = option.envvar
        envvar = workflow._normalize_libpq_metadata_value(metadata_value)
        if envvar is not None:
            envvars.add(envvar)
    return envvars


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql://postgres:canary@localhost/rag?host=evil.example",
        "postgresql://postgres:canary@localhost/rag?hostaddr=198.51.100.1",
        "postgresql://postgres:canary@localhost/rag?host=localhost,evil.example",
        "postgresql:///rag?host=/var/run/postgresql",
        "postgresql://postgres:canary@localhost/rag?service=outside",
        "postgresql://postgres:canary@localhost,evil.example/rag",
        "postgresql://postgres:canary@localhost:not-a-port/rag",
        "postgresql://postgres:canary@/rag",
        "mysql://postgres:canary@localhost/rag",
        "postgresql://postgres:canary@localhost/rag?sslmode=require",
    ],
)
def test_main_rejects_unsafe_database_urls_before_any_side_effect(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        "scripts.run_pageindex_real_retrieval_workflow.RuntimeSettings.from_env",
        lambda: SimpleNamespace(database_url=database_url),
    )

    def _unexpected_call(*args, **kwargs) -> None:
        calls.append("side effect")
        raise AssertionError("unsafe URLs must be rejected before side effects")

    for name in (
        "database_is_reachable",
        "ensure_local_pgvector_container",
        "apply_migrations",
        "_run_python_script",
    ):
        monkeypatch.setattr(workflow, name, _unexpected_call)
    monkeypatch.setattr(workflow.shutil, "which", _unexpected_call)
    monkeypatch.setattr(workflow.subprocess, "run", _unexpected_call)
    monkeypatch.setattr(workflow, "_run_command", _unexpected_call)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert calls == []
    assert "canary" not in str(exc_info.value)
    assert "evil.example" not in str(exc_info.value)


def test_docker_run_failure_redacts_database_password_and_keeps_it_out_of_args(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    database_url = "postgresql://postgres:docker-password-canary@localhost:5432/rag"
    calls: list[tuple[list[str], dict[str, str] | None]] = []
    original_environment = os.environ.copy()

    monkeypatch.setattr(workflow.shutil, "which", lambda _name: "docker")

    def _run_command(
        args, *, cwd=workflow.REPO_ROOT, timeout=600, env=None
    ) -> subprocess.CompletedProcess[str]:
        copied_args = list(args)
        calls.append((copied_args, env))
        if copied_args[:2] == ["docker", "ps"]:
            return subprocess.CompletedProcess(copied_args, 0, stdout="", stderr="")
        raise subprocess.CalledProcessError(1, copied_args, output=database_url)

    monkeypatch.setattr(workflow, "_run_command", _run_command)

    with pytest.raises(RuntimeError) as exc_info:
        ensure_local_pgvector_container(database_url)

    captured = capsys.readouterr()
    diagnostic_text = " ".join(
        [
            str(exc_info.value),
            captured.out,
            captured.err,
            *[" ".join(args) for args, _env in calls],
        ]
    )
    assert "docker-password-canary" not in diagnostic_text
    assert database_url not in diagnostic_text
    assert os.environ == original_environment
    run_args, run_env = calls[-1]
    assert run_args[:2] == ["docker", "run"]
    assert "POSTGRES_PASSWORD=docker-password-canary" not in run_args
    assert run_args[run_args.index("-e") + 1] == "POSTGRES_USER=postgres"
    assert run_env is not None
    assert run_env["POSTGRES_PASSWORD"] == "docker-password-canary"


def test_child_environment_removes_libpq_routing_and_uses_normalized_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canaries = {
        "PGHOST": "remote-host-canary",
        "PGHOSTADDR": "remote-hostaddr-canary",
        "PGSERVICE": "remote-service-canary",
        "PGSERVICEFILE": "remote-service-file-canary",
        "PGPORT": "6543",
        "PGDATABASE": "remote-database-canary",
        "PGUSER": "remote-user-canary",
        "PGPASSWORD": "remote-password-canary",
        "PGPASSFILE": "remote-passfile-canary",
        "PGTARGETSESSIONATTRS": "read-write",
    }
    for key, value in canaries.items():
        monkeypatch.setenv(key, value)
    original_environment = os.environ.copy()
    captured: dict[str, object] = {}

    def _run_command(args, *, cwd=workflow.REPO_ROOT, timeout=600, env=None):
        captured["env"] = env
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(workflow, "_run_command", _run_command)
    workflow._run_python_script(
        "test_real_integration.py",
        database_url="postgresql://local-user:pass%20word@localhost:5432/local-db",
    )

    child_env = captured["env"]
    assert isinstance(child_env, dict)
    assert child_env["DATABASE_URL"] == (
        "postgresql://local-user:pass%20word@127.0.0.1:5432/local-db"
    )
    assert not set(canaries).intersection(child_env)
    assert os.environ == original_environment


def test_child_output_and_failures_redact_all_known_database_secrets(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    original_url = "postgresql://local-user:raw%2Fpassword@localhost:5432/local-db"
    normalized_url = "postgresql://local-user:raw%2Fpassword@127.0.0.1:5432/local-db"
    secrets = (
        original_url,
        normalized_url,
        "raw/password",
        quote("raw/password", safe=""),
    )
    output = "diagnostic retained: child started; " + " | ".join(secrets)

    monkeypatch.setattr(
        workflow,
        "_run_command",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, stdout=output, stderr=output
        ),
    )
    workflow._run_python_script("test_real_integration.py", database_url=original_url)
    success_output = capsys.readouterr()
    assert "diagnostic retained: child started" in success_output.out
    assert "[REDACTED]" in success_output.out
    assert not any(
        secret in success_output.out + success_output.err for secret in secrets
    )

    def _raise_child_failure(*args, **kwargs) -> None:
        raise subprocess.CalledProcessError(1, args[0], output=output, stderr=output)

    monkeypatch.setattr(workflow, "_run_command", _raise_child_failure)
    with pytest.raises(RuntimeError) as exc_info:
        workflow._run_python_script(
            "test_real_integration.py", database_url=original_url
        )
    failure_output = capsys.readouterr()
    diagnostic_text = str(exc_info.value) + failure_output.out + failure_output.err
    assert "Child script stage failed: test_real_integration.py" in diagnostic_text
    assert not any(secret in diagnostic_text for secret in secrets)


def test_main_does_not_expose_secret_bearing_child_exception(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    original_url = "postgresql://local-user:raw%2Fpassword@localhost:5432/local-db"
    normalized_url = "postgresql://local-user:raw%2Fpassword@127.0.0.1:5432/local-db"
    secrets = (
        original_url,
        normalized_url,
        "raw/password",
        quote("raw/password", safe=""),
    )
    monkeypatch.setattr(
        workflow.RuntimeSettings,
        "from_env",
        lambda: SimpleNamespace(database_url=original_url),
    )
    monkeypatch.setattr(workflow, "database_is_reachable", lambda _url: True)
    monkeypatch.setattr(workflow, "apply_migrations", lambda **kwargs: [])
    monkeypatch.setattr(
        workflow,
        "_run_python_script",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError(" | ".join(secrets))
        ),
    )

    with pytest.raises(SystemExit) as exc_info:
        workflow.main()

    diagnostic_text = str(exc_info.value) + capsys.readouterr().out
    assert "Workflow failed" in diagnostic_text
    assert not any(secret in diagnostic_text for secret in secrets)


def test_redaction_structurally_removes_lowercase_encoded_child_uri_credentials(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    original_url = "postgresql://local-user:raw%2fpassword@localhost:5432/local-db"
    child_url = "postgresql://local-user:raw%2fpassword@127.0.0.1:5432/local-db"
    output = f"child diagnostic retained; {child_url}"

    monkeypatch.setattr(
        workflow,
        "_run_command",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, stdout=output, stderr=""
        ),
    )

    workflow._run_python_script("test_real_integration.py", database_url=original_url)

    captured = capsys.readouterr().out
    assert "child diagnostic retained" in captured
    assert "[REDACTED]@127.0.0.1:5432/local-db" in captured
    assert "raw%2fpassword" not in captured
    assert "raw%2Fpassword" not in captured
    assert "raw/password" not in captured
    assert original_url not in captured
    assert child_url not in captured


def test_main_uses_fixed_final_message_without_rendering_hostile_exception(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        workflow.RuntimeSettings,
        "from_env",
        lambda: SimpleNamespace(
            database_url="postgresql://postgres:password@localhost/rag"
        ),
    )
    monkeypatch.setattr(workflow, "database_is_reachable", lambda _url: True)
    monkeypatch.setattr(
        workflow,
        "apply_migrations",
        lambda **_kwargs: (_ for _ in ()).throw(_HostileError()),
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert str(exc_info.value) == "Workflow failed; see preceding safe diagnostics"
    assert "exception __str__ must not be called" not in capsys.readouterr().out


def test_main_uses_fixed_final_message_for_hostile_runtime_settings_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        workflow.RuntimeSettings,
        "from_env",
        lambda: (_ for _ in ()).throw(_HostileError()),
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert str(exc_info.value) == "Workflow failed; see preceding safe diagnostics"


@pytest.mark.parametrize("encoded_password", ["raw%2fpassword", "RAW%2FPASSWORD"])
def test_child_output_redacts_standalone_percent_encoded_password_variants(
    encoded_password: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database_url = "postgresql://local-user:raw%2Fpassword@localhost:5432/local-db"
    output = f"child diagnostic retained; password={encoded_password}; continuing"
    monkeypatch.setattr(
        workflow,
        "_run_command",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, stdout=output, stderr=""
        ),
    )

    workflow._run_python_script("test_real_integration.py", database_url=database_url)

    captured = capsys.readouterr().out
    assert "child diagnostic retained" in captured
    assert encoded_password not in captured
    assert "[REDACTED]" in captured


def test_workflow_error_rejects_untrusted_constructor_data() -> None:
    with pytest.raises(TypeError):
        workflow._WorkflowError(  # type: ignore[call-arg]
            stage="arbitrary", message="untrusted"
        )
    with pytest.raises(ValueError):
        workflow._WorkflowError("migration_failed", "../../untrusted.sql")

    error = workflow._WorkflowError("migration_failed", "003_tree_persistence.sql")

    assert error.stage == "migration"
    assert str(error) == "Migration stage failed: 003_tree_persistence.sql"


def test_missing_allowlisted_child_script_diagnostic_is_safe_and_useful() -> None:
    script_name = "test_retrieve_real.py"
    script_path = workflow.REPO_ROOT / script_name
    original_exists = Path.exists

    def _missing_requested_script(path: Path) -> bool:
        return False if path == script_path else original_exists(path)

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(Path, "exists", _missing_requested_script)
        with pytest.raises(workflow._WorkflowError) as exc_info:
            workflow._run_python_script(
                script_name,
                database_url="postgresql://postgres:password@localhost/rag",
            )

    assert exc_info.value.stage == "child"
    assert str(exc_info.value) == f"Child script stage failed: {script_name}"


@pytest.mark.parametrize(
    "failure",
    [
        subprocess.TimeoutExpired(["docker", "ps"], timeout=1),
        OSError("docker-hostile-canary"),
        subprocess.CalledProcessError(
            1, ["docker", "ps"], output="docker-hostile-canary"
        ),
    ],
)
def test_docker_status_uses_fixed_safe_diagnostic_for_hostile_failures(
    failure: BaseException, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise_failure(*_args: object, **_kwargs: object) -> None:
        raise failure

    monkeypatch.setattr(workflow, "_run_command", _raise_failure)

    with pytest.raises(workflow._WorkflowError) as exc_info:
        workflow._docker_container_status("rag-pg")

    assert exc_info.value.code == "docker_unreachable"
    assert str(exc_info.value) == "Docker stage failed: daemon is not reachable"
    assert "docker-hostile-canary" not in str(exc_info.value)


def test_docker_run_explicitly_binds_validated_ipv4_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def _run_command(args, **_kwargs) -> subprocess.CompletedProcess[str]:
        commands.append(list(args))
        return subprocess.CompletedProcess(args, 0, stdout="created", stderr="")

    monkeypatch.setattr(workflow, "_run_command", _run_command)
    workflow._create_pgvector_container(
        container_name="rag-pg",
        image="pgvector/pgvector:pg15",
        target=workflow._local_database_target(
            "postgresql://postgres:password@127.0.0.1:55432/rag"
        ),
        sensitive_values=(),
    )

    command = commands[0]
    assert command[command.index("-p") + 1] == "127.0.0.1:55432:5432"


def test_docker_run_brackets_ipv6_loopback_when_url_is_supported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def _run_command(args, **_kwargs) -> subprocess.CompletedProcess[str]:
        commands.append(list(args))
        return subprocess.CompletedProcess(args, 0, stdout="created", stderr="")

    monkeypatch.setattr(workflow, "_run_command", _run_command)
    workflow._create_pgvector_container(
        container_name="rag-pg",
        image="pgvector/pgvector:pg15",
        target=workflow._local_database_target(
            "postgresql://postgres:password@[::1]:55433/rag"
        ),
        sensitive_values=(),
    )

    command = commands[0]
    assert command[command.index("-p") + 1] == "[::1]:55433:5432"


def test_child_environment_removes_every_installed_libpq_envvar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installed_envvars = _installed_libpq_envvars()
    assert installed_envvars
    for envvar in installed_envvars:
        monkeypatch.setenv(envvar, f"canary-{envvar}")

    child_env = workflow._child_environment(
        workflow._local_database_target("postgresql://user:password@localhost/rag")
    )

    assert not installed_envvars.intersection(child_env)
    assert child_env["DATABASE_URL"] == "postgresql://user:password@127.0.0.1:5432/rag"


def test_installed_metadata_envvars_are_normalized_and_legacy_extras_retained(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata = (
        SimpleNamespace(envvar=b"PGFUTURE"),
        SimpleNamespace(envvar="PGSTRING"),
        SimpleNamespace(envvar=None),
    )
    monkeypatch.setattr(workflow.psycopg.pq.Conninfo, "get_defaults", lambda: metadata)

    envvars = workflow._libpq_connection_envvars()

    assert {"PGFUTURE", "PGSTRING"}.issubset(envvars)
    assert {"PGSERVICE", "PGSERVICEFILE", "PGREQUIRESSL"}.issubset(envvars)
