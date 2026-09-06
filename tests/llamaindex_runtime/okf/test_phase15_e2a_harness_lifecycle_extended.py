"""Extended tests for Phase 15 E2A harness lifecycle (Task #132).

Covers edge cases, error paths, and security requirements.
Uses parametrization to reduce redundancy while maintaining coverage.
"""

from __future__ import annotations

from typing import Any, Sequence, cast
from unittest.mock import MagicMock

import pytest

import psycopg

from ._phase15_e2a_harness_lifecycle import (
    DisposableE2aSession,
    _apply_migrations,
    _apply_migrations_with_connection,
    _attest_target,
    _compose_failures,
    _observe_container_presence,
    _remove_container_by_id,
)
from ._phase15_e2a_harness_types import AUTHORIZATION_FLAG

# Constants for minimal pipe-format inspect mock
CONTAINER_ID_64 = "a" * 64
TOKEN_64 = "b" * 64


def _minimal_inspect_output(container_id: str, name: str, token: str, port: int) -> str:
    """Return minimal pipe-format inspect output."""
    return f"{container_id}|/{name}|{token}|127.0.0.1:{port}"


def _mock_conn_factory_success() -> Any:
    """Return mock connection factory with successful lifecycle."""
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.side_effect = [
        ("test_db",),  # current_database()
        ("public",),  # current_schema()
        ("test_user",),  # current_user()
        ("test_user",),  # session_user()
        (1,),  # SELECT 1 readiness
    ]
    conn.cursor.return_value = cursor
    return conn


class TestFailureComposition:
    """Tests for failure composition."""

    def test_no_failures_raises(self) -> None:
        """No failures raises RuntimeError."""
        with pytest.raises(RuntimeError, match="no exceptions"):
            _compose_failures(None, None)

    def test_sanitized_message_constant(self) -> None:
        """Sanitized message is constant, not derived from input."""
        cleanup1 = RuntimeError("secret token abc123")
        cleanup2 = RuntimeError("different secret xyz789")
        result1 = _compose_failures(None, cleanup1)
        result2 = _compose_failures(None, cleanup2)
        assert str(result1) == str(result2)
        assert "abc123" not in str(result1)
        assert "xyz789" not in str(result2)


class TestTargetAttestation:
    """Tests for target attestation."""

    @pytest.mark.parametrize(
        "fetchone_results,error_match",
        [
            # Wrong schema
            ([("test_db",), ("wrong_schema",)], "attestation"),
            # Wrong user
            ([("test_db",), ("public",), ("wrong_user",)], "attestation"),
            # Wrong session_user
            (
                [("test_db",), ("public",), ("test_user",), ("wrong_session",)],
                "attestation",
            ),
        ],
    )
    def test_attestation_wrong_value_redacted(
        self, fetchone_results: list[tuple[str]], error_match: str
    ) -> None:
        """Wrong attestation values raise fixed redacted error."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = fetchone_results
        with pytest.raises(ValueError, match=error_match):
            _attest_target(
                mock_cursor,
                expected_database="test_db",
                expected_schema="public",
                expected_user="test_user",
            )

    def test_attestation_empty_row(self) -> None:
        """Empty row raises fixed redacted error."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        with pytest.raises(ValueError):
            _attest_target(
                mock_cursor,
                expected_database="test_db",
                expected_schema="public",
                expected_user="test_user",
            )

    def test_attestation_cursor_exception(self) -> None:
        """Cursor exception raises fixed redacted error."""
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = RuntimeError("DB error")
        with pytest.raises(ValueError, match="attestation"):
            _attest_target(
                mock_cursor,
                expected_database="test_db",
                expected_schema="public",
                expected_user="test_user",
            )


class TestMigrationExecution:
    """Tests for migration execution."""

    @pytest.mark.parametrize("filename", ["", "file.txt", "nonexistent.sql"])
    def test_invalid_migration_filename_rejected(self, filename: str) -> None:
        """Invalid migration filenames are rejected."""
        mock_cursor = MagicMock()
        with pytest.raises(ValueError, match="subset|catalog|bypass"):
            _apply_migrations(mock_cursor, migration_filenames=[filename])

    def test_rollback_failure_preserves_primary(self) -> None:
        """Rollback failure preserves primary exception."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = ValueError("migration error")
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.rollback.side_effect = RuntimeError("rollback failed")
        with pytest.raises(ValueError, match="migration error"):
            _apply_migrations_with_connection(mock_conn)


class TestDisposableE2aSessionStartup:
    """Tests for DisposableE2aSession startup failures."""

    def test_container_start_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Container start failure raises RuntimeError."""
        monkeypatch.setenv(AUTHORIZATION_FLAG, "separately-authorized")

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 1 if "run" in args else 0
            result.stdout = ""
            return result

        with pytest.raises(RuntimeError, match="Failed to start container"):
            with DisposableE2aSession(
                container_name="test-container",
                password="test-password",
                runner=mock_run,
                token_factory=lambda: TOKEN_64,
            ):
                pass

    def test_invalid_container_id_from_run(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Invalid container ID from docker run raises RuntimeError."""
        monkeypatch.setenv(AUTHORIZATION_FLAG, "separately-authorized")

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            if "run" in args:
                result.stdout = "invalid-id"
            elif "inspect" in args:
                result.stdout = ""
            else:
                result.stdout = ""
            return result

        with pytest.raises(RuntimeError, match="Invalid container ID"):
            with DisposableE2aSession(
                container_name="test-container",
                password="test-password",
                runner=mock_run,
                token_factory=lambda: TOKEN_64,
            ):
                pass

    def test_runner_exception_during_start(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Runner exception during start raises RuntimeError."""
        monkeypatch.setenv(AUTHORIZATION_FLAG, "separately-authorized")

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            if "run" in args:
                raise RuntimeError("Docker failed")
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            return result

        with pytest.raises(RuntimeError, match="Failed to start container"):
            with DisposableE2aSession(
                container_name="test-container",
                password="test-password",
                runner=mock_run,
                token_factory=lambda: TOKEN_64,
            ):
                pass


class TestDisposableE2aSessionSecurity:
    """Tests for DisposableE2aSession security requirements."""

    def test_port_must_be_str_not_int(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Port must be exact built-in str, not int."""
        from typing import cast

        monkeypatch.setenv(AUTHORIZATION_FLAG, "separately-authorized")
        with pytest.raises(ValueError, match="Port must be exact built-in str"):
            DisposableE2aSession(
                container_name="test-container",
                password="test-password",
                port=cast(Any, 5432),  # Deliberate invalid port type for runtime test
            )

    def test_image_constrained_to_trusted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Image must be constrained to trusted disposable image."""
        monkeypatch.setenv(AUTHORIZATION_FLAG, "separately-authorized")
        with pytest.raises(ValueError, match="untrusted|image"):
            DisposableE2aSession(
                container_name="test-container",
                password="test-password",
                image="malicious/postgres:latest",
            )

    def test_token_factory_output_validated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Token factory output must be validated as 64-hex."""
        monkeypatch.setenv(AUTHORIZATION_FLAG, "separately-authorized")
        with pytest.raises(ValueError, match="Invalid.*token"):
            with DisposableE2aSession(
                container_name="test-container",
                password="test-password",
                token_factory=lambda: "not-valid-token",
            ):
                pass

    @pytest.mark.parametrize(
        "field,value,error_match",
        [
            ("password", "pass\nword", "newline|injection"),
            ("password", "pass\x00word", "NUL|injection"),
            ("password", "pass\rword", "carriage|injection"),
            ("database", "test\ndb", "newline|injection"),
            ("user", "test\nuser", "newline|injection"),
        ],
    )
    def test_injection_rejected(
        self,
        monkeypatch: pytest.MonkeyPatch,
        field: str,
        value: str,
        error_match: str,
    ) -> None:
        """Injection attempts in parameters are rejected."""
        monkeypatch.setenv(AUTHORIZATION_FLAG, "separately-authorized")
        kwargs: dict[str, Any] = {
            "container_name": "test-container",
            "password": "test-password",
        }
        kwargs[field] = value
        with pytest.raises(ValueError, match=error_match):
            DisposableE2aSession(**kwargs)

    def test_authorization_rechecked_at_enter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Authorization must be rechecked at __enter__ time."""
        monkeypatch.setenv(AUTHORIZATION_FLAG, "separately-authorized")
        session = DisposableE2aSession(
            container_name="test-container",
            password="test-password",
            token_factory=lambda: TOKEN_64,
        )
        monkeypatch.delenv(AUTHORIZATION_FLAG)
        with pytest.raises(RuntimeError, match="authorization"):
            with session:
                pass


class TestInjectedConnectionLifecycle:
    """Tests for injected connection factory running full lifecycle."""

    def test_injected_factory_runs_readiness(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Injected connection factory must run readiness probe."""
        monkeypatch.setenv(AUTHORIZATION_FLAG, "separately-authorized")

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            if "ps" in args:
                result.stdout = ""
            elif "run" in args:
                result.stdout = CONTAINER_ID_64
            elif "inspect" in args:
                result.stdout = _minimal_inspect_output(
                    CONTAINER_ID_64, "test-container", TOKEN_64, 5432
                )
            else:
                result.stdout = ""
            return result

        def mock_conn_factory(
            host: str,
            port: int,
            database: str,
            user: str,
            password: str | None = None,
            **kwargs: Any,
        ) -> psycopg.Connection[tuple[Any, ...]]:
            conn = MagicMock()
            cursor = MagicMock()
            cursor.fetchone.side_effect = [
                ("test_db",),
                ("public",),
                ("test_user",),
                ("test_user",),
                (1,),  # SELECT 1 readiness
            ]
            conn.cursor.return_value = cursor
            return cast(psycopg.Connection[tuple[Any, ...]], conn)

        with DisposableE2aSession(
            container_name="test-container",
            password="test-password",
            runner=mock_run,
            conn_factory=mock_conn_factory,
            token_factory=lambda: TOKEN_64,
        ):
            pass

    def test_injected_factory_runs_attestation_and_migrations(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Injected connection factory must run attestation and migrations."""
        monkeypatch.setenv(AUTHORIZATION_FLAG, "separately-authorized")

        execute_calls: list[str] = []
        call_count = [0]

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            if "ps" in args:
                result.stdout = ""
            elif "run" in args:
                result.stdout = CONTAINER_ID_64
            elif "inspect" in args:
                result.stdout = _minimal_inspect_output(
                    CONTAINER_ID_64, "test-container", TOKEN_64, 5432
                )
            else:
                result.stdout = ""
            return result

        def mock_conn_factory(
            host: str,
            port: int,
            database: str,
            user: str,
            password: str | None = None,
            **kwargs: Any,
        ) -> psycopg.Connection[tuple[Any, ...]]:
            conn = MagicMock()
            cursor = MagicMock()
            call_count[0] += 1

            # Track execute calls for attestation/migrations (second call)
            if call_count[0] == 2:

                def track_execute(sql: str) -> None:
                    execute_calls.append(sql.strip()[:50])

                cursor.execute.side_effect = track_execute
                cursor.fetchone.side_effect = [
                    ("test_db",),
                    ("public",),
                    ("test_user",),
                    ("test_user",),
                ]
            else:
                # First call: readiness check
                cursor.fetchone.return_value = (1,)
            conn.cursor.return_value = cursor
            return cast(psycopg.Connection[tuple[Any, ...]], conn)

        with DisposableE2aSession(
            container_name="test-container",
            password="test-password",
            runner=mock_run,
            conn_factory=mock_conn_factory,
            token_factory=lambda: TOKEN_64,
        ):
            pass

        # Verify attestation and migration queries were executed
        assert len(execute_calls) >= 4  # At least attestation queries


class TestEnvFileSecurity:
    """Tests for env-file security requirements."""

    def test_no_password_in_docker_args(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Password must never appear in Docker args."""
        monkeypatch.setenv(AUTHORIZATION_FLAG, "separately-authorized")
        password = "super-secret-password"

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            for arg in args:
                assert password not in str(arg)
            result = MagicMock()
            result.returncode = 0
            if "ps" in args:
                result.stdout = ""
            elif "run" in args:
                result.stdout = CONTAINER_ID_64
                assert "--env-file" in args
            elif "inspect" in args:
                result.stdout = _minimal_inspect_output(
                    CONTAINER_ID_64, "test-container", TOKEN_64, 5432
                )
            else:
                result.stdout = ""
            return result

        def mock_conn_factory(
            host: str,
            port: int,
            database: str,
            user: str,
            password: str | None = None,
            **kwargs: Any,
        ) -> psycopg.Connection[tuple[Any, ...]]:
            conn = MagicMock()
            cursor = MagicMock()
            cursor.fetchone.side_effect = [
                ("test_db",),
                ("public",),
                ("test_user",),
                ("test_user",),
                (1,),
            ]
            conn.cursor.return_value = cursor
            return cast(psycopg.Connection[tuple[Any, ...]], conn)

        with DisposableE2aSession(
            container_name="test-container",
            password=password,
            runner=mock_run,
            conn_factory=mock_conn_factory,
            token_factory=lambda: TOKEN_64,
        ):
            pass

    def test_env_file_deleted_after_normal_exit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Env file must be deleted after normal exit, after container removal."""
        from pathlib import Path

        monkeypatch.setenv(AUTHORIZATION_FLAG, "separately-authorized")
        # Use mutable container for captured path (closures can't rebind scalars)
        captured: list[Path | None] = [None]
        # Event log to prove ordering: rm must precede env-file unlink
        events: list[str] = []

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            if "ps" in args:
                result.stdout = ""
            elif "run" in args:
                # Capture the --env-file path from args
                for i, arg in enumerate(args):
                    if arg == "--env-file" and i + 1 < len(args):
                        env_path = Path(args[i + 1])
                        captured[0] = env_path
                        # Create a real temp file at that path
                        env_path.parent.mkdir(parents=True, exist_ok=True)
                        env_path.write_text("PASSWORD=test-password\n")
                        break
                result.stdout = CONTAINER_ID_64
            elif "inspect" in args:
                result.stdout = _minimal_inspect_output(
                    CONTAINER_ID_64, "test-container", TOKEN_64, 5432
                )
            elif "rm" in args:
                # Record container removal event
                events.append("rm")
                result.stdout = ""
            else:
                result.stdout = ""
            return result

        def mock_conn_factory(
            host: str,
            port: int,
            database: str,
            user: str,
            password: str | None = None,
            **kwargs: Any,
        ) -> psycopg.Connection[tuple[Any, ...]]:
            conn = MagicMock()
            cursor = MagicMock()
            cursor.fetchone.side_effect = [
                ("test_db",),
                ("public",),
                ("test_user",),
                ("test_user",),
                (1,),
            ]
            conn.cursor.return_value = cursor
            return cast(psycopg.Connection[tuple[Any, ...]], conn)

        # Track unlink calls to verify deletion and ordering
        original_unlink = Path.unlink

        def tracked_unlink(self_path: Path, *args: Any, **kwargs: Any) -> None:
            if captured[0] is not None and self_path == captured[0]:
                events.append("env_file_unlink")
            return original_unlink(self_path, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", tracked_unlink)

        session_instance = None
        with DisposableE2aSession(
            container_name="test-container",
            password="test-password",
            runner=mock_run,
            conn_factory=mock_conn_factory,
            token_factory=lambda: TOKEN_64,
        ) as session:
            session_instance = session
            # Verify session has started
            assert session_instance._started
            assert session_instance._container_id == CONTAINER_ID_64
            assert session_instance._token == TOKEN_64
            assert session_instance._env_file_path is not None

        # After exit:
        # 1. Env file must be deleted
        if captured[0] is not None:
            assert not captured[0].exists()
        # 2. Deletion must have been recorded
        assert "env_file_unlink" in events
        # 3. Container rm must precede env-file unlink
        rm_idx = events.index("rm") if "rm" in events else -1
        unlink_idx = events.index("env_file_unlink")
        assert rm_idx >= 0, "Container rm event not recorded"
        assert rm_idx < unlink_idx, f"rm must precede env_file_unlink: events={events}"
        # 4. Session state must be cleared
        assert session_instance is not None
        assert not session_instance._started
        assert session_instance._container_id is None
        assert session_instance._token is None
        assert session_instance._env_file_path is None

    def test_env_file_unlink_failure_raises_cleanup_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Env file unlink failure must raise fixed cleanup RuntimeError."""
        import traceback
        from pathlib import Path

        monkeypatch.setenv(AUTHORIZATION_FLAG, "separately-authorized")
        # Use mutable container for captured path
        captured: list[Path | None] = [None]
        events: list[str] = []

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            if "ps" in args:
                result.stdout = ""
            elif "run" in args:
                # Capture the --env-file path from args
                for i, arg in enumerate(args):
                    if arg == "--env-file" and i + 1 < len(args):
                        env_path = Path(args[i + 1])
                        captured[0] = env_path
                        # Create a real temp file at that path
                        env_path.parent.mkdir(parents=True, exist_ok=True)
                        env_path.write_text("PASSWORD=test-password\n")
                        break
                result.stdout = CONTAINER_ID_64
            elif "inspect" in args:
                result.stdout = _minimal_inspect_output(
                    CONTAINER_ID_64, "test-container", TOKEN_64, 5432
                )
            elif "rm" in args:
                events.append("rm")
                result.stdout = ""
            else:
                result.stdout = ""
            return result

        def mock_conn_factory(
            host: str,
            port: int,
            database: str,
            user: str,
            password: str | None = None,
            **kwargs: Any,
        ) -> psycopg.Connection[tuple[Any, ...]]:
            conn = MagicMock()
            cursor = MagicMock()
            cursor.fetchone.side_effect = [
                ("test_db",),
                ("public",),
                ("test_user",),
                ("test_user",),
                (1,),
            ]
            conn.cursor.return_value = cursor
            return cast(psycopg.Connection[tuple[Any, ...]], conn)

        # Make unlink fail for the captured env file
        original_unlink = Path.unlink
        password_canary = "unlink_canary_PASS999"

        def failing_unlink(self_path: Path, *args: Any, **kwargs: Any) -> None:
            if captured[0] is not None and self_path == captured[0]:
                events.append("env_file_unlink_failed")
                raise PermissionError("Mock unlink failure")
            return original_unlink(self_path, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", failing_unlink)

        session_instance = None
        exc_caught: RuntimeError | None = None

        try:
            with DisposableE2aSession(
                container_name="test-container",
                password=password_canary,
                runner=mock_run,
                conn_factory=mock_conn_factory,
                token_factory=lambda: TOKEN_64,
            ) as session:
                session_instance = session
                pass
        except RuntimeError as exc:
            exc_caught = exc

        # Must raise RuntimeError with fixed message
        assert exc_caught is not None
        assert str(exc_caught) == "Cleanup failed"
        # Password canary must NOT appear in error message
        assert password_canary not in str(exc_caught)

        # State must be cleared despite failure
        assert session_instance is not None
        assert not session_instance._started
        assert session_instance._container_id is None
        assert session_instance._token is None
        assert session_instance._env_file_path is None

        # Container rm must precede env-file unlink attempt
        assert "rm" in events
        assert "env_file_unlink_failed" in events
        rm_idx = events.index("rm")
        unlink_idx = events.index("env_file_unlink_failed")
        assert rm_idx < unlink_idx, f"rm must precede env_file_unlink: events={events}"

        # Verify no secrets in traceback
        if exc_caught:
            te = traceback.TracebackException.from_exception(
                exc_caught, capture_locals=True
            )
            for frame in te.stack:
                if frame.filename.endswith("_phase15_e2a_harness_lifecycle.py"):
                    if frame.locals:
                        locals_str = str(frame.locals)
                        assert password_canary not in locals_str
                        assert "PASS999" not in locals_str

    def test_cleanup_attestation_failure_deletes_env_file(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Cleanup attestation failure must still delete the env file.

        When cleanup ownership verification fails (refused removal),
        the worker must still attempt env-file deletion so credentials
        do not remain on disk. The env file must be absent after __exit__.
        """
        import traceback
        from pathlib import Path

        monkeypatch.setenv(AUTHORIZATION_FLAG, "separately-authorized")
        captured: list[Path | None] = [None]
        events: list[str] = []
        # Phase flag: startup inspect succeeds, cleanup inspect fails
        inspect_for_startup = [True]

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            if "ps" in args:
                result.stdout = ""
            elif "run" in args:
                for i, arg in enumerate(args):
                    if arg == "--env-file" and i + 1 < len(args):
                        env_path = Path(args[i + 1])
                        captured[0] = env_path
                        env_path.parent.mkdir(parents=True, exist_ok=True)
                        env_path.write_text("PASSWORD=test-password\n")
                        break
                result.stdout = CONTAINER_ID_64
            elif "inspect" in args:
                if inspect_for_startup[0]:
                    result.stdout = _minimal_inspect_output(
                        CONTAINER_ID_64, "test-container", TOKEN_64, 5432
                    )
                else:
                    # Cleanup attestation fails (ownership verification fails)
                    result.returncode = 1
                    result.stdout = ""
            elif "rm" in args:
                events.append("rm_attempted")
                result.stdout = ""
            else:
                result.stdout = ""
            return result

        def mock_conn_factory(
            host: str,
            port: int,
            database: str,
            user: str,
            password: str | None = None,
            **kwargs: Any,
        ) -> psycopg.Connection[tuple[Any, ...]]:
            conn = MagicMock()
            cursor = MagicMock()
            cursor.fetchone.side_effect = [
                ("test_db",),
                ("public",),
                ("test_user",),
                ("test_user",),
                (1,),
            ]
            conn.cursor.return_value = cursor
            return cast(psycopg.Connection[tuple[Any, ...]], conn)

        original_unlink = Path.unlink

        def tracked_unlink(self_path: Path, *args: Any, **kwargs: Any) -> None:
            if captured[0] is not None and self_path == captured[0]:
                events.append("env_file_unlink")
            return original_unlink(self_path, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", tracked_unlink)

        password_canary = "attest_fail_canary_DEF777"
        session_instance = None
        exc_caught: RuntimeError | None = None

        try:
            with DisposableE2aSession(
                container_name="test-container",
                password=password_canary,
                runner=mock_run,
                conn_factory=mock_conn_factory,
                token_factory=lambda: TOKEN_64,
            ) as session:
                session_instance = session
                # After successful startup, make cleanup attestation fail
                inspect_for_startup[0] = False
        except RuntimeError as exc:
            exc_caught = exc

        # Must raise RuntimeError (cleanup failed)
        assert exc_caught is not None
        assert str(exc_caught) == "Cleanup failed"

        # Env file must be absent despite attestation failure
        if captured[0] is not None:
            assert not captured[
                0
            ].exists(), "Env file must be deleted after cleanup attestation failure"

        # Env-file unlink must have occurred
        assert (
            "env_file_unlink" in events
        ), f"Env file unlink event missing: events={events}"

        # Container rm should NOT have been attempted (attestation refused)
        assert (
            "rm_attempted" not in events
        ), f"rm must not run when attestation fails: events={events}"

        # State must be cleared
        assert session_instance is not None
        assert not session_instance._started
        assert session_instance._container_id is None
        assert session_instance._token is None
        assert session_instance._env_file_path is None

        # Verify no secrets in traceback
        if exc_caught:
            te = traceback.TracebackException.from_exception(
                exc_caught, capture_locals=True
            )
            for frame in te.stack:
                if frame.filename.endswith("_phase15_e2a_harness_lifecycle.py"):
                    if frame.locals:
                        locals_str = str(frame.locals)
                        assert password_canary not in locals_str
                        assert "DEF777" not in locals_str


class TestCleanupSemantics:
    """Tests for exactly-once cleanup semantics."""

    def test_pre_attestation_before_removal(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Cleanup must pre-attest ownership before removal."""
        monkeypatch.setenv(AUTHORIZATION_FLAG, "separately-authorized")
        call_order: list[str] = []

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            if "ps" in args:
                call_order.append("ps")
                result.stdout = ""
            elif "run" in args:
                call_order.append("run")
                result.stdout = CONTAINER_ID_64
            elif "inspect" in args:
                call_order.append("inspect")
                result.stdout = _minimal_inspect_output(
                    CONTAINER_ID_64, "test-container", TOKEN_64, 5432
                )
            elif "rm" in args:
                call_order.append("rm")
                result.stdout = ""
            else:
                result.stdout = ""
            return result

        def mock_conn_factory(
            host: str,
            port: int,
            database: str,
            user: str,
            password: str | None = None,
            **kwargs: Any,
        ) -> psycopg.Connection[tuple[Any, ...]]:
            conn = MagicMock()
            cursor = MagicMock()
            cursor.fetchone.side_effect = [
                ("test_db",),
                ("public",),
                ("test_user",),
                ("test_user",),
                (1,),
            ]
            conn.cursor.return_value = cursor
            return cast(psycopg.Connection[tuple[Any, ...]], conn)

        with DisposableE2aSession(
            container_name="test-container",
            password="test-password",
            runner=mock_run,
            conn_factory=mock_conn_factory,
            token_factory=lambda: TOKEN_64,
        ):
            pass

        if "rm" in call_order:
            rm_idx = call_order.index("rm")
            inspect_indices = [i for i, c in enumerate(call_order) if c == "inspect"]
            assert inspect_indices and max(inspect_indices) < rm_idx

    def test_post_removal_confirmed_absence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Cleanup must confirm absence after removal."""
        monkeypatch.setenv(AUTHORIZATION_FLAG, "separately-authorized")
        call_order: list[str] = []

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            if "ps" in args:
                call_order.append("ps")
                result.stdout = ""
            elif "run" in args:
                call_order.append("run")
                result.stdout = CONTAINER_ID_64
            elif "inspect" in args:
                call_order.append("inspect")
                result.stdout = _minimal_inspect_output(
                    CONTAINER_ID_64, "test-container", TOKEN_64, 5432
                )
            elif "rm" in args:
                call_order.append("rm")
                result.stdout = ""
            else:
                result.stdout = ""
            return result

        def mock_conn_factory(
            host: str,
            port: int,
            database: str,
            user: str,
            password: str | None = None,
            **kwargs: Any,
        ) -> psycopg.Connection[tuple[Any, ...]]:
            conn = MagicMock()
            cursor = MagicMock()
            cursor.fetchone.side_effect = [
                ("test_db",),
                ("public",),
                ("test_user",),
                ("test_user",),
                (1,),
            ]
            conn.cursor.return_value = cursor
            return cast(psycopg.Connection[tuple[Any, ...]], conn)

        with DisposableE2aSession(
            container_name="test-container",
            password="test-password",
            runner=mock_run,
            conn_factory=mock_conn_factory,
            token_factory=lambda: TOKEN_64,
        ):
            pass

        ps_count = call_order.count("ps")
        assert ps_count >= 2

    def test_no_removal_on_unowned_state(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cleanup must not remove container with mismatched ownership."""
        monkeypatch.setenv(AUTHORIZATION_FLAG, "separately-authorized")
        rm_called = [False]
        wrong_token = "wrong" + "c" * 58

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            if "ps" in args:
                result.stdout = ""
            elif "run" in args:
                result.stdout = CONTAINER_ID_64
            elif "inspect" in args:
                result.stdout = _minimal_inspect_output(
                    CONTAINER_ID_64, "test-container", wrong_token, 5432
                )
            elif "rm" in args:
                rm_called[0] = True
                result.stdout = ""
            else:
                result.stdout = ""
            return result

        with pytest.raises(RuntimeError):
            with DisposableE2aSession(
                container_name="test-container",
                password="test-password",
                runner=mock_run,
                token_factory=lambda: TOKEN_64,
            ):
                pass

        assert not rm_called[0]

    def test_removes_by_exact_full_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Must remove by exact full 64-char ID, not short form."""
        monkeypatch.setenv(AUTHORIZATION_FLAG, "separately-authorized")
        rm_args: list[str] = []

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            if "ps" in args:
                result.stdout = ""
            elif "run" in args:
                result.stdout = CONTAINER_ID_64
            elif "inspect" in args:
                result.stdout = _minimal_inspect_output(
                    CONTAINER_ID_64, "test-container", TOKEN_64, 5432
                )
            elif "rm" in args:
                rm_args.extend(args)
                result.stdout = ""
            else:
                result.stdout = ""
            return result

        def mock_conn_factory(
            host: str,
            port: int,
            database: str,
            user: str,
            password: str | None = None,
            **kwargs: Any,
        ) -> psycopg.Connection[tuple[Any, ...]]:
            conn = MagicMock()
            cursor = MagicMock()
            cursor.fetchone.side_effect = [
                ("test_db",),
                ("public",),
                ("test_user",),
                ("test_user",),
                (1,),
            ]
            conn.cursor.return_value = cursor
            return cast(psycopg.Connection[tuple[Any, ...]], conn)

        with DisposableE2aSession(
            container_name="test-container",
            password="test-password",
            runner=mock_run,
            conn_factory=mock_conn_factory,
            token_factory=lambda: TOKEN_64,
        ):
            pass

        assert CONTAINER_ID_64 in rm_args


class TestObserveContainerPresence:
    """Tests for container presence observation."""

    def test_container_id_without_newline(self) -> None:
        """Container ID without newline must be handled."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = f"test-container\t{CONTAINER_ID_64}"

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            return mock_result

        result = _observe_container_presence(
            "test-container", config_dir="/tmp/test-config", run=mock_run
        )
        assert result.status == "present"
        assert result.container_id == CONTAINER_ID_64

    def test_malformed_output_ambiguous(self) -> None:
        """Malformed Docker output must be ambiguous."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "not-valid-format"

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            return mock_result

        result = _observe_container_presence(
            "test-container", config_dir="/tmp/test-config", run=mock_run
        )
        assert result.status == "ambiguous_output"

    def test_name_mismatch_not_present(self) -> None:
        """Container with different name must not be present."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = f"other-container\t{CONTAINER_ID_64}\n"

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            return mock_result

        result = _observe_container_presence(
            "test-container", config_dir="/tmp/test-config", run=mock_run
        )
        assert result.status != "present"


class TestRemoveContainer:
    """Tests for container removal."""

    def test_runner_exception_returns_false(self) -> None:
        """Runner exception during removal returns False."""

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            raise RuntimeError("Docker failed")

        result = _remove_container_by_id(
            CONTAINER_ID_64, config_dir="/tmp/test-config", run=mock_run
        )
        assert result is False

    def test_non_int_returncode_returns_false(self) -> None:
        """Non-int return code returns False."""
        mock_result = MagicMock()
        mock_result.returncode = True

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            return mock_result

        result = _remove_container_by_id(
            CONTAINER_ID_64, config_dir="/tmp/test-config", run=mock_run
        )
        assert result is False


class TestStartupFailureRemovalSemantics:
    """Tests for startup failure removal with fresh attestation.

    Security: Startup failure paths must re-attest ownership before removal.
    Never remove a container we don't own.
    """

    def test_database_setup_failure_removes_after_fresh_attestation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Database setup failure must fresh-attest before removal.

        Proves that when database setup fails:
        1. Fresh attestation is performed before removal
        2. Container is only removed if attestation succeeds
        3. Env file is always deleted
        4. Fixed redacted error is raised
        """
        import os
        from pathlib import Path
        from unittest.mock import patch

        monkeypatch.setenv(AUTHORIZATION_FLAG, "separately-authorized")
        events: list[str] = []
        captured: list[Path | None] = [None]

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            if "ps" in args:
                result.stdout = ""
            elif "run" in args:
                for i, arg in enumerate(args):
                    if arg == "--env-file" and i + 1 < len(args):
                        env_path = Path(args[i + 1])
                        captured[0] = env_path
                        env_path.parent.mkdir(parents=True, exist_ok=True)
                        env_path.write_text("PASSWORD=test-password\n")
                        break
                result.stdout = CONTAINER_ID_64
            elif "inspect" in args:
                events.append("inspect")
                result.stdout = _minimal_inspect_output(
                    CONTAINER_ID_64, "test-container", TOKEN_64, 5432
                )
            elif "rm" in args:
                events.append("rm")
                result.stdout = ""
            else:
                result.stdout = ""
            return result

        def mock_conn_factory(
            host: str,
            port: int,
            database: str,
            user: str,
            password: str | None = None,
            **kwargs: Any,
        ) -> psycopg.Connection[tuple[Any, ...]]:
            conn = MagicMock()
            cursor = MagicMock()
            cursor.fetchone.return_value = ("test_db",)
            conn.cursor.return_value = cursor
            return cast(psycopg.Connection[tuple[Any, ...]], conn)

        # Patch _setup_database_impl to return a failed result
        failed_db_result = type("Result", (), {"success": False})()

        def patched_setup_db_fail(
            port: str,
            database: str,
            user: str,
            password: str,
            conn_factory_input: Any,
            sleep_fn: Any,
        ) -> Any:
            return failed_db_result

        original_unlink = os.unlink

        def tracked_unlink(path: str | Path, *args: Any, **kwargs: Any) -> None:
            if captured[0] is not None and Path(path) == captured[0]:
                events.append("env_file_unlink")
            return original_unlink(path, *args, **kwargs)

        monkeypatch.setattr(os, "unlink", tracked_unlink)

        from . import _phase15_e2a_harness_lifecycle as lifecycle_mod

        exc_caught: RuntimeError | None = None
        with patch.object(
            lifecycle_mod,
            "_setup_database_impl",
            side_effect=patched_setup_db_fail,
        ):
            try:
                with DisposableE2aSession(
                    container_name="test-container",
                    password="db-fail-canary-XYZ",
                    runner=mock_run,
                    conn_factory=mock_conn_factory,
                    token_factory=lambda: TOKEN_64,
                ):
                    pass
            except RuntimeError as exc:
                exc_caught = exc

        # Must raise RuntimeError
        assert exc_caught is not None
        # Env file must be deleted
        assert (
            "env_file_unlink" in events
        ), f"Env file unlink event missing: events={events}"
        if captured[0] is not None:
            assert not captured[0].exists()
        # Must have fresh attestation (inspect) before rm
        assert "inspect" in events
        assert "rm" in events, f"rm event missing: events={events}"
        # Inspect must precede rm
        inspect_idx = events.index("inspect")
        rm_idx = events.index("rm")
        assert inspect_idx >= 0
        assert rm_idx > inspect_idx, f"rm must follow inspect: events={events}"

    def test_database_setup_failure_no_remove_after_failed_attestation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Database setup failure must NOT remove if fresh attestation fails.

        Proves that when fresh attestation fails during startup failure cleanup:
        1. Container rm is NOT attempted
        2. Env file is still deleted
        3. Fixed redacted error is raised
        4. No unowned container is removed
        """
        import os
        from pathlib import Path
        from unittest.mock import patch

        monkeypatch.setenv(AUTHORIZATION_FLAG, "separately-authorized")
        events: list[str] = []
        captured: list[Path | None] = [None]
        # Control when attestation should fail
        inspect_should_fail = [False]

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            if "ps" in args:
                result.stdout = ""
            elif "run" in args:
                for i, arg in enumerate(args):
                    if arg == "--env-file" and i + 1 < len(args):
                        env_path = Path(args[i + 1])
                        captured[0] = env_path
                        env_path.parent.mkdir(parents=True, exist_ok=True)
                        env_path.write_text("PASSWORD=test-password\n")
                        break
                result.stdout = CONTAINER_ID_64
            elif "inspect" in args:
                events.append("inspect")
                if inspect_should_fail[0]:
                    # Fresh attestation for removal fails
                    result.returncode = 1
                    result.stdout = ""
                else:
                    result.stdout = _minimal_inspect_output(
                        CONTAINER_ID_64, "test-container", TOKEN_64, 5432
                    )
            elif "rm" in args:
                events.append("rm_attempted")
                result.stdout = ""
            else:
                result.stdout = ""
            return result

        def mock_conn_factory(
            host: str,
            port: int,
            database: str,
            user: str,
            password: str | None = None,
            **kwargs: Any,
        ) -> psycopg.Connection[tuple[Any, ...]]:
            call_count = [0]

            def fetchone_side_effect() -> Any:
                call_count[0] += 1
                if call_count[0] <= 5:
                    # First 5 calls succeed
                    return ("test_db",) if call_count[0] <= 4 else (1,)
                else:
                    # Database setup fails
                    raise Exception("Database operation failed")

            conn = MagicMock()
            cursor = MagicMock()
            cursor.fetchone.side_effect = fetchone_side_effect
            conn.cursor.return_value = cursor
            return cast(psycopg.Connection[tuple[Any, ...]], conn)

        # Patch _setup_database_impl to make it fail AND set attestation to fail
        failed_db_result = type("Result", (), {"success": False})()

        def patched_setup_db_fail_then_attest_fail(
            port: str,
            database: str,
            user: str,
            password: str,
            conn_factory_input: Any,
            sleep_fn: Any,
        ) -> Any:
            # Set attestation to fail before returning
            inspect_should_fail[0] = True
            return failed_db_result

        original_unlink = os.unlink

        def tracked_unlink(path: str | Path, *args: Any, **kwargs: Any) -> None:
            if captured[0] is not None and Path(path) == captured[0]:
                events.append("env_file_unlink")
            return original_unlink(path, *args, **kwargs)

        monkeypatch.setattr(os, "unlink", tracked_unlink)

        from . import _phase15_e2a_harness_lifecycle as lifecycle_mod

        exc_caught: RuntimeError | None = None
        with patch.object(
            lifecycle_mod,
            "_setup_database_impl",
            side_effect=patched_setup_db_fail_then_attest_fail,
        ):
            try:
                with DisposableE2aSession(
                    container_name="test-container",
                    password="attest-fail-canary-ABC",
                    runner=mock_run,
                    conn_factory=mock_conn_factory,
                    token_factory=lambda: TOKEN_64,
                ):
                    pass
            except RuntimeError as exc:
                exc_caught = exc

        # Must raise RuntimeError
        assert exc_caught is not None
        # Env file must be deleted
        assert (
            "env_file_unlink" in events
        ), f"Env file unlink event missing: events={events}"
        # rm must NOT be attempted (attestation failed)
        assert (
            "rm_attempted" not in events
        ), f"rm must not run when removal attestation fails: events={events}"
        # At least one inspect should have occurred (startup)
        assert "inspect" in events
        if captured[0] is not None:
            assert not captured[0].exists()


class TestRealFilesystemFailureScenarios:
    """Tests for real-filesystem failure scenarios with env-file and removal failures."""

    def test_removal_failure_combined_with_env_unlink_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Removal failure combined with env-file unlink failure.

        Proves:
        1. Env-file deletion was attempted
        2. Public cleanup failure is raised
        3. All lifecycle state cleared (_started, _container_id, _token, _env_file_path)
        4. No unproven removal occurred
        5. Cleanup error message is redacted (no raw password in lifecycle frames)
        """
        import os
        from pathlib import Path
        from traceback import TracebackException

        monkeypatch.setenv(AUTHORIZATION_FLAG, "separately-authorized")
        password_canary = "rm-fail-env-unlink-fail-CANARY-XYZ"
        events: list[str] = []
        captured: list[Path | None] = [None]

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            if "ps" in args:
                result.stdout = ""
            elif "run" in args:
                for i, arg in enumerate(args):
                    if arg == "--env-file" and i + 1 < len(args):
                        env_path = Path(args[i + 1])
                        captured[0] = env_path
                        env_path.parent.mkdir(parents=True, exist_ok=True)
                        env_path.write_text(f"PASSWORD={password_canary}\n")
                        break
                result.stdout = CONTAINER_ID_64
            elif "inspect" in args:
                events.append("inspect")
                result.stdout = _minimal_inspect_output(
                    CONTAINER_ID_64, "test-container", TOKEN_64, 5432
                )
            elif "rm" in args:
                events.append("rm_attempted")
                # Simulate removal failure
                result.returncode = 1
                result.stdout = ""
            else:
                result.stdout = ""
            return result

        def mock_conn_factory(
            host: str,
            port: int,
            database: str,
            user: str,
            password: str | None = None,
            **kwargs: Any,
        ) -> psycopg.Connection[tuple[Any, ...]]:
            conn = MagicMock()
            cursor = MagicMock()
            cursor.fetchone.side_effect = [
                ("test_db",),
                ("public",),
                ("test_user",),
                ("test_user",),
                (1,),
            ]
            conn.cursor.return_value = cursor
            return cast(psycopg.Connection[tuple[Any, ...]], conn)

        original_unlink = os.unlink

        def tracked_unlink_with_failure(
            path: str | Path, *args: Any, **kwargs: Any
        ) -> None:
            path_obj = Path(path)
            if captured[0] is not None and path_obj == captured[0]:
                events.append("env_file_unlink_attempted")
                # Simulate env-file unlink failure
                raise PermissionError("Simulated unlink failure")
            return original_unlink(path, *args, **kwargs)

        monkeypatch.setattr(os, "unlink", tracked_unlink_with_failure)

        session_instance = None
        exc_caught: Exception | None = None
        try:
            with DisposableE2aSession(
                container_name="test-container",
                password=password_canary,
                runner=mock_run,
                conn_factory=mock_conn_factory,
                token_factory=lambda: TOKEN_64,
            ) as session:
                session_instance = session
        except Exception as exc:
            exc_caught = exc

        # Must raise an exception (cleanup failure)
        assert exc_caught is not None

        # Env-file unlink was attempted
        assert (
            "env_file_unlink_attempted" in events
        ), f"Env file unlink attempt not recorded: events={events}"

        # rm was attempted (with attestation)
        assert "rm_attempted" in events, f"rm attempt not recorded: events={events}"

        # Inspect was called (attestation before rm)
        assert "inspect" in events

        # All lifecycle state must be cleared
        assert session_instance is not None
        assert not session_instance._started
        assert session_instance._container_id is None
        assert session_instance._token is None
        assert session_instance._env_file_path is None

        # Cleanup error message should be redacted
        exc_message = str(exc_caught)
        assert (
            password_canary not in exc_message
        ), f"Password canary in exception message: {exc_message}"

        # Password canary absent from lifecycle frames in traceback
        tb = TracebackException.from_exception(exc_caught, capture_locals=True)
        for frame in tb.stack:
            # Only check lifecycle implementation frames, not test frames
            if "_phase15_e2a_harness_lifecycle.py" in frame.filename:
                if frame.locals:
                    locals_str = str(frame.locals)
                    assert (
                        password_canary not in locals_str
                    ), f"Password canary in lifecycle locals: {frame.name}"

        # No temp file should remain (test hygiene)
        if captured[0] is not None and captured[0].exists():
            original_unlink(captured[0])

    def test_post_removal_absence_verification_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Post-removal absence verification failure.

        Proves:
        1. Container was removed (rm called)
        2. Post-removal ps check returns non-absence (verification failure)
        3. Fixed redacted cleanup failure is raised
        4. Env file is deleted
        5. All lifecycle state cleared
        6. Password canary absent from lifecycle frames in traceback
        """
        import os
        from pathlib import Path
        from traceback import TracebackException

        monkeypatch.setenv(AUTHORIZATION_FLAG, "separately-authorized")
        password_canary = "post-rm-verify-fail-CANARY-ABC"
        events: list[str] = []
        captured: list[Path | None] = [None]
        ps_count = [0]

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            if "ps" in args:
                ps_count[0] += 1
                events.append(f"ps_{ps_count[0]}")
                if ps_count[0] == 1:
                    # First ps: container absent (startup check)
                    result.stdout = ""
                elif ps_count[0] == 2:
                    # Second ps: post-removal verification - return present (failure)
                    events.append("post_rm_verification_failure")
                    # Return container still present (verification failure)
                    result.stdout = f"{CONTAINER_ID_64}\ttest-container"
                else:
                    result.stdout = ""
            elif "run" in args:
                for i, arg in enumerate(args):
                    if arg == "--env-file" and i + 1 < len(args):
                        env_path = Path(args[i + 1])
                        captured[0] = env_path
                        env_path.parent.mkdir(parents=True, exist_ok=True)
                        env_path.write_text(f"PASSWORD={password_canary}\n")
                        break
                result.stdout = CONTAINER_ID_64
            elif "inspect" in args:
                events.append("inspect")
                result.stdout = _minimal_inspect_output(
                    CONTAINER_ID_64, "test-container", TOKEN_64, 5432
                )
            elif "rm" in args:
                events.append("rm")
                result.stdout = ""
            else:
                result.stdout = ""
            return result

        def mock_conn_factory(
            host: str,
            port: int,
            database: str,
            user: str,
            password: str | None = None,
            **kwargs: Any,
        ) -> psycopg.Connection[tuple[Any, ...]]:
            conn = MagicMock()
            cursor = MagicMock()
            cursor.fetchone.side_effect = [
                ("test_db",),
                ("public",),
                ("test_user",),
                ("test_user",),
                (1,),
            ]
            conn.cursor.return_value = cursor
            return cast(psycopg.Connection[tuple[Any, ...]], conn)

        original_unlink = os.unlink

        def tracked_unlink(path: str | Path, *args: Any, **kwargs: Any) -> None:
            if captured[0] is not None and Path(path) == captured[0]:
                events.append("env_file_unlink")
            return original_unlink(path, *args, **kwargs)

        monkeypatch.setattr(os, "unlink", tracked_unlink)

        session_instance = None
        exc_caught: Exception | None = None
        try:
            with DisposableE2aSession(
                container_name="test-container",
                password=password_canary,
                runner=mock_run,
                conn_factory=mock_conn_factory,
                token_factory=lambda: TOKEN_64,
            ) as session:
                session_instance = session
        except Exception as exc:
            exc_caught = exc

        # Must raise cleanup failure (post-removal verification failed)
        assert (
            exc_caught is not None
        ), "Expected cleanup failure for post-removal verification"

        # rm was called
        assert "rm" in events, f"rm not called: events={events}"

        # Post-removal verification failure occurred (ps returned non-absence)
        assert (
            "post_rm_verification_failure" in events
        ), f"Post-rm verification failure not recorded: events={events}"

        # Env file was deleted
        assert "env_file_unlink" in events, f"Env file not deleted: events={events}"

        # All lifecycle state must be cleared
        assert session_instance is not None
        assert not session_instance._started
        assert session_instance._container_id is None
        assert session_instance._token is None
        assert session_instance._env_file_path is None

        # Actual temp file is gone
        if captured[0] is not None:
            assert not captured[0].exists()

        # Password canary absent from lifecycle frames in traceback
        tb = TracebackException.from_exception(exc_caught, capture_locals=True)
        for frame in tb.stack:
            # Only check lifecycle implementation frames, not test frames
            if "_phase15_e2a_harness_lifecycle.py" in frame.filename:
                if frame.locals:
                    locals_str = str(frame.locals)
                    assert (
                        password_canary not in locals_str
                    ), f"Password canary in lifecycle locals: {frame.name}"

    def test_catch_all_cleanup_exception_with_env_unlink_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Catch-all cleanup exception combined with env-file unlink failure.

        Proves:
        1. Env-file deletion was attempted
        2. Public cleanup failure is raised
        3. All lifecycle state cleared
        4. No unproven removal
        5. Exception message is redacted (no raw password in lifecycle frames)
        """
        import os
        from pathlib import Path
        from traceback import TracebackException
        from unittest.mock import patch

        monkeypatch.setenv(AUTHORIZATION_FLAG, "separately-authorized")
        password_canary = "catch-all-env-unlink-fail-CANARY-QWE"
        events: list[str] = []
        captured: list[Path | None] = [None]
        sanitized_env_call_count = [0]

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            if "ps" in args:
                result.stdout = ""
            elif "run" in args:
                for i, arg in enumerate(args):
                    if arg == "--env-file" and i + 1 < len(args):
                        env_path = Path(args[i + 1])
                        captured[0] = env_path
                        env_path.parent.mkdir(parents=True, exist_ok=True)
                        env_path.write_text(f"PASSWORD={password_canary}\n")
                        break
                result.stdout = CONTAINER_ID_64
            elif "inspect" in args:
                events.append("inspect")
                result.stdout = _minimal_inspect_output(
                    CONTAINER_ID_64, "test-container", TOKEN_64, 5432
                )
            elif "rm" in args:
                events.append("rm")
                result.stdout = ""
            else:
                result.stdout = ""
            return result

        def mock_conn_factory(
            host: str,
            port: int,
            database: str,
            user: str,
            password: str | None = None,
            **kwargs: Any,
        ) -> psycopg.Connection[tuple[Any, ...]]:
            conn = MagicMock()
            cursor = MagicMock()
            cursor.fetchone.side_effect = [
                ("test_db",),
                ("public",),
                ("test_user",),
                ("test_user",),
                (1,),
            ]
            conn.cursor.return_value = cursor
            return cast(psycopg.Connection[tuple[Any, ...]], conn)

        original_unlink = os.unlink

        def tracked_unlink_with_failure(
            path: str | Path, *args: Any, **kwargs: Any
        ) -> None:
            path_obj = Path(path)
            if captured[0] is not None and path_obj == captured[0]:
                events.append("env_file_unlink_attempted")
                # Simulate env-file unlink failure
                raise PermissionError("Simulated unlink failure in cleanup")
            return original_unlink(path, *args, **kwargs)

        monkeypatch.setattr(os, "unlink", tracked_unlink_with_failure)

        from . import _phase15_e2a_harness_lifecycle as lifecycle_mod
        from ._phase15_e2a_harness_types import SafeDockerEnv

        # Patch _sanitized_env_copy to succeed on first two calls (startup) and fail on third (cleanup)
        original_sanitized_env_copy = lifecycle_mod._sanitized_env_copy

        def patched_sanitized_env_copy() -> SafeDockerEnv:
            sanitized_env_call_count[0] += 1
            if sanitized_env_call_count[0] <= 2:
                # First two calls during startup - succeed
                return original_sanitized_env_copy()
            else:
                # Third call during cleanup - trigger exception in catch-all
                raise RuntimeError("Simulated exception in cleanup")

        session_instance = None
        exc_caught: Exception | None = None
        with patch.object(
            lifecycle_mod,
            "_sanitized_env_copy",
            side_effect=patched_sanitized_env_copy,
        ):
            try:
                with DisposableE2aSession(
                    container_name="test-container",
                    password=password_canary,
                    runner=mock_run,
                    conn_factory=mock_conn_factory,
                    token_factory=lambda: TOKEN_64,
                ) as session:
                    session_instance = session
            except Exception as exc:
                exc_caught = exc

        # Must raise RuntimeError (cleanup failure)
        assert exc_caught is not None

        # Env-file unlink was attempted (in catch-all handler)
        assert (
            "env_file_unlink_attempted" in events
        ), f"Env file unlink attempt not recorded: events={events}"

        # Inspect was called (attestation before any rm)
        assert "inspect" in events

        # rm may or may not be called depending on when exception occurs
        # But if called, it was after attestation

        # All lifecycle state must be cleared
        assert session_instance is not None
        assert not session_instance._started
        assert session_instance._container_id is None
        assert session_instance._token is None
        assert session_instance._env_file_path is None

        # Exception message should not contain password canary
        exc_message = str(exc_caught)
        assert (
            password_canary not in exc_message
        ), f"Password canary in exception message: {exc_message}"

        # Password canary absent from lifecycle frames in traceback
        tb = TracebackException.from_exception(exc_caught, capture_locals=True)
        for frame in tb.stack:
            # Only check lifecycle implementation frames, not test frames
            if "_phase15_e2a_harness_lifecycle.py" in frame.filename:
                if frame.locals:
                    locals_str = str(frame.locals)
                    assert (
                        password_canary not in locals_str
                    ), f"Password canary in lifecycle locals: {frame.name}"

        # Clean up leftover test file through original unlink
        if captured[0] is not None and captured[0].exists():
            original_unlink(captured[0])
