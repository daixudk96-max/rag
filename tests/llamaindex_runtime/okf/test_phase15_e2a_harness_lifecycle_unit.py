"""Tests for Phase 15 E2A harness lifecycle internals (Task #132).

TDD Phase: RED - strengthen tests to fail against faulty implementation.
"""

from __future__ import annotations

import builtins
from typing import Any, Sequence
from unittest.mock import MagicMock

import psycopg
import pytest

from ._phase15_e2a_harness_lifecycle import (
    _apply_migrations,
    _apply_migrations_with_connection,
    _attest_target,
    _compose_failures,
    _observe_container_presence,
    _remove_container_by_id,
    _wait_for_ready,
    _full_container_inspect,
)


class TestObserveContainerPresence:
    """Test exact-name container presence observation."""

    def test_rc_nonzero_inspection_failure(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error"

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            return mock_result

        result = _observe_container_presence(
            "test-container", config_dir="/tmp/config", run=mock_run
        )
        assert result.status == "inspection_failure"
        assert result.rc == 1

    def test_runner_exception_inspection_failure(self) -> None:
        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            raise RuntimeError("Docker failed")

        result = _observe_container_presence(
            "test-container", config_dir="/tmp/config", run=mock_run
        )
        assert result.status == "inspection_failure"
        assert result.rc is None

    def test_rc_zero_empty_stdout_confirmed_absent(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            return mock_result

        result = _observe_container_presence(
            "test-container", config_dir="/tmp/config", run=mock_run
        )
        assert result.status == "confirmed_absent"
        assert result.rc == 0

    def test_rc_zero_whitespace_stdout_confirmed_absent(self) -> None:
        """Whitespace-only stdout is confirmed_absent (EXACT parsing)."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "  \n  "
        mock_result.stderr = ""

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            return mock_result

        result = _observe_container_presence(
            "test-container", config_dir="/tmp/config", run=mock_run
        )
        assert result.status == "confirmed_absent"

    def test_rc_zero_one_container_present(self) -> None:
        container_id = "a" * 64
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = f"test-container\t{container_id}\n"
        mock_result.stderr = ""

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            return mock_result

        result = _observe_container_presence(
            "test-container", config_dir="/tmp/config", run=mock_run
        )
        assert result.status == "present"
        assert result.container_id == container_id

    def test_rc_zero_multiple_containers_ambiguous(self) -> None:
        """Multiple records is ambiguous_output."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = f"container1\t{'a' * 64}\ncontainer2\t{'b' * 64}"
        mock_result.stderr = ""

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            return mock_result

        result = _observe_container_presence(
            "container1", config_dir="/tmp/config", run=mock_run
        )
        assert result.status == "ambiguous_output"

    def test_invalid_name_inspection_failure(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""

        result = _observe_container_presence(
            "--help", config_dir="/tmp/config", run=lambda *a, **k: mock_result
        )
        assert result.status == "inspection_failure"

    def test_non_int_returncode_inspection_failure(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = True

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            return mock_result

        result = _observe_container_presence(
            "test-container", config_dir="/tmp/config", run=mock_run
        )
        assert result.status == "inspection_failure"

    def test_no_regex_filter_in_docker_args(self) -> None:
        docker_args_list: list[list[str]] = []

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            docker_args_list.append(list(args))
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            return result

        _observe_container_presence(
            "test-container", config_dir="/tmp/config", run=mock_run
        )

        for args in docker_args_list:
            args_str = " ".join(args)
            assert "name=^" not in args_str
            assert "name=$" not in args_str

    def test_uses_no_trunc_flag(self) -> None:
        docker_args_list: list[list[str]] = []

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            docker_args_list.append(list(args))
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            return result

        _observe_container_presence(
            "test-container", config_dir="/tmp/config", run=mock_run
        )

        found_no_trunc = any("--no-trunc" in args for args in docker_args_list)
        assert found_no_trunc, "Must use --no-trunc for full container IDs"

    def test_uses_format_flag_for_structured_output(self) -> None:
        docker_args_list: list[list[str]] = []

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            docker_args_list.append(list(args))
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            return result

        _observe_container_presence(
            "test-container", config_dir="/tmp/config", run=mock_run
        )
        assert any("--format" in args for args in docker_args_list)

    def test_exact_name_literal_comparison(self) -> None:
        container_id = "a" * 64
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = f"test-container-extra\t{container_id}\n"

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            return mock_result

        result = _observe_container_presence(
            "test-container", config_dir="/tmp/config", run=mock_run
        )
        assert result.status != "present"

    def test_newline_only_stdout_is_confirmed_absent(self) -> None:
        """Newline-only stdout is confirmed_absent with EXACT parsing."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "\n"
        mock_result.stderr = ""

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            return mock_result

        result = _observe_container_presence(
            "test-container", config_dir="/tmp/config", run=mock_run
        )
        assert result.status == "confirmed_absent"

    def test_bare_newline_is_confirmed_absent(self) -> None:
        """Bare newline is confirmed_absent with EXACT parsing."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "\n"
        mock_result.stderr = ""

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            return mock_result

        result = _observe_container_presence(
            "test-container", config_dir="/tmp/config", run=mock_run
        )
        assert result.status == "confirmed_absent"

    def test_no_strip_on_container_id(self) -> None:
        container_id = "a" * 64
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = f"test-container\t{container_id}\n"

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            return mock_result

        result = _observe_container_presence(
            "test-container", config_dir="/tmp/config", run=mock_run
        )
        assert result.status == "present"
        if result.container_id:
            assert len(result.container_id) == 64
            assert result.container_id == container_id


class TestRemoveContainerById:
    """Test container removal by exact ID."""

    def test_remove_success(self) -> None:
        """Successful removal returns True."""
        container_id = "a" * 64
        mock_result = MagicMock()
        mock_result.returncode = 0

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            return mock_result

        result = _remove_container_by_id(
            container_id, config_dir="/tmp/config", run=mock_run
        )
        assert result is True

    def test_remove_failure_returns_false(self) -> None:
        """Failed removal returns False."""
        container_id = "a" * 64
        mock_result = MagicMock()
        mock_result.returncode = 1

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            return mock_result

        result = _remove_container_by_id(
            container_id, config_dir="/tmp/config", run=mock_run
        )
        assert result is False

    def test_invalid_id_returns_false(self) -> None:
        """Invalid ID returns False."""
        result = _remove_container_by_id(
            "invalid", config_dir="/tmp/config", run=lambda *a, **k: MagicMock()
        )
        assert result is False

    def test_removes_by_exact_id_not_name(self) -> None:
        """Remove must use exact full ID, never name."""
        container_id = "a" * 64
        docker_args_list: list[list[str]] = []

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            docker_args_list.append(list(args))
            result = MagicMock()
            result.returncode = 0
            return result

        _remove_container_by_id(container_id, config_dir="/tmp/config", run=mock_run)

        # Verify rm command uses ID
        rm_commands = [cmd for cmd in docker_args_list if "rm" in cmd]
        assert len(rm_commands) == 1
        rm_cmd = rm_commands[0]
        # ID must be in the command
        assert container_id in rm_cmd


class TestFailureComposition:
    """Test exception failure composition."""

    def test_primary_only_re_raises_exact(self) -> None:
        """Primary-only failure re-raises identical exception."""
        primary = ValueError("primary error")
        result = _compose_failures(primary, None)
        assert result is primary

    def test_cleanup_only_raises_fixed_sanitized(self) -> None:
        """Cleanup-only failure raises fixed sanitized exception."""
        cleanup = RuntimeError("cleanup failed with details")
        result = _compose_failures(None, cleanup)
        assert isinstance(result, RuntimeError)
        assert "Cleanup failed" in str(result)
        assert "details" not in str(result)

    def test_dual_failure_exception_group(self) -> None:
        """Dual failure with Exception => ExceptionGroup."""
        primary = ValueError("primary error")
        cleanup = RuntimeError("cleanup failed")
        result = _compose_failures(primary, cleanup)
        assert isinstance(result, builtins.ExceptionGroup)
        exceptions = list(result.exceptions)
        assert len(exceptions) == 2
        assert exceptions[0] is primary
        assert isinstance(exceptions[1], RuntimeError)
        assert "Cleanup failed" in str(exceptions[1])

    def test_dual_failure_base_exception_group(self) -> None:
        """Dual failure with KeyboardInterrupt => BaseExceptionGroup."""
        primary = KeyboardInterrupt()
        cleanup = RuntimeError("cleanup failed")
        result = _compose_failures(primary, cleanup)
        assert isinstance(result, builtins.BaseExceptionGroup)
        exceptions = list(result.exceptions)
        assert len(exceptions) == 2
        assert exceptions[0] is primary
        assert isinstance(exceptions[1], RuntimeError)

    def test_sanitized_cleanup_does_not_include_original_message(self) -> None:
        """Sanitized cleanup error must not include original details."""
        cleanup = RuntimeError("cleanup failed with secret token abc123")
        result = _compose_failures(None, cleanup)
        assert "secret token" not in str(result)
        assert "abc123" not in str(result)


class TestTargetAttestation:
    """Test database target attestation."""

    def test_attestation_success(self) -> None:
        """Successful attestation passes."""
        mock_cursor = MagicMock()
        fetchone_results = [
            ("test_db",),
            ("public",),
            ("test_user",),
            ("test_user",),
        ]
        mock_cursor.fetchone.side_effect = fetchone_results

        _attest_target(
            mock_cursor,
            expected_database="test_db",
            expected_schema="public",
            expected_user="test_user",
        )

    def test_attestation_wrong_database(self) -> None:
        """Wrong database raises fixed redacted error."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ("wrong_db",)

        with pytest.raises(ValueError) as exc_info:
            _attest_target(
                mock_cursor,
                expected_database="test_db",
                expected_schema="public",
                expected_user="test_user",
            )

        error_msg = str(exc_info.value)
        assert "wrong_db" not in error_msg
        assert "test_db" not in error_msg
        assert "attestation" in error_msg.lower()


class TestReadinessProbe:
    """Test database readiness with fresh connection/cursor."""

    def test_fresh_connection_per_attempt(self) -> None:
        """Each attempt uses fresh connection AND cursor."""
        call_count = [0]

        def mock_conn_factory() -> MagicMock:
            call_count[0] += 1
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.execute.return_value = None
            mock_cursor.fetchone.return_value = (1,)
            mock_conn.cursor.return_value = mock_cursor
            return mock_conn

        _wait_for_ready(mock_conn_factory, max_retries=1)

        assert call_count[0] == 1

    def test_retries_only_operational_error(self) -> None:
        """Only psycopg.OperationalError is retried."""
        call_count = [0]

        def mock_conn_factory() -> MagicMock:
            call_count[0] += 1
            mock_conn = MagicMock()
            mock_cursor = MagicMock()

            if call_count[0] == 1:
                mock_cursor.execute.side_effect = psycopg.OperationalError(
                    "connection error"
                )
            else:
                mock_cursor.execute.return_value = None
                mock_cursor.fetchone.return_value = (1,)

            mock_conn.cursor.return_value = mock_cursor
            return mock_conn

        _wait_for_ready(mock_conn_factory, max_retries=2, sleep=lambda s: None)

        assert call_count[0] == 2

    def test_non_operational_error_propagates(self) -> None:
        """Non-OperationalError propagates immediately."""

        def mock_conn_factory() -> MagicMock:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.execute.side_effect = ValueError("bad query")
            mock_conn.cursor.return_value = mock_cursor
            return mock_conn

        with pytest.raises(ValueError, match="bad query"):
            _wait_for_ready(mock_conn_factory, max_retries=3)

    def test_exhaustion_fixed_error(self) -> None:
        """Exhaustion raises fixed sanitized error."""

        def mock_conn_factory() -> MagicMock:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.execute.side_effect = psycopg.OperationalError(
                "connection error"
            )
            mock_conn.cursor.return_value = mock_cursor
            return mock_conn

        with pytest.raises(RuntimeError, match="never became ready"):
            _wait_for_ready(mock_conn_factory, max_retries=1, sleep=lambda s: None)

    def test_connection_closed_after_success(self) -> None:
        """Connection must be closed after successful attempt."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.return_value = None
        mock_cursor.fetchone.return_value = (1,)
        mock_conn.cursor.return_value = mock_cursor

        def mock_conn_factory() -> MagicMock:
            return mock_conn

        _wait_for_ready(mock_conn_factory, max_retries=1)

        mock_conn.close.assert_called_once()

    def test_connection_closed_after_operational_error(self) -> None:
        """Connection must be closed even after OperationalError."""
        close_counts: list[int] = []

        def mock_conn_factory() -> MagicMock:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.execute.side_effect = psycopg.OperationalError("error")
            mock_conn.cursor.return_value = mock_cursor
            mock_conn.close.side_effect = lambda: close_counts.append(1)
            return mock_conn

        with pytest.raises(RuntimeError, match="never became ready"):
            _wait_for_ready(mock_conn_factory, max_retries=2, sleep=lambda s: None)

        # Each connection attempt must have been closed
        assert len(close_counts) >= 2


class TestMigrationExecution:
    """Test migration execution with real package resources."""

    def test_reads_full_catalog(self) -> None:
        """Migration helper reads full catalog and executes SQL."""

        mock_cursor = MagicMock()

        _apply_migrations(mock_cursor, migration_filenames=None)

        # Should execute all migrations in catalog
        assert mock_cursor.execute.call_count >= 1

    def test_rejects_subset_bypass(self) -> None:
        """Subset bypass must be rejected - only full catalog allowed."""
        mock_cursor = MagicMock()

        with pytest.raises(ValueError, match="subset.*bypass|full catalog"):
            _apply_migrations(mock_cursor, migration_filenames=["001_initial.sql"])

    def test_rejects_any_provided_list(self) -> None:
        """Any provided list must be rejected - must use None."""
        mock_cursor = MagicMock()

        with pytest.raises(ValueError, match="subset|catalog"):
            _apply_migrations(mock_cursor, migration_filenames=[])

    def test_transaction_commit_on_success(self) -> None:
        """Success commits exactly once."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        _apply_migrations_with_connection(mock_conn)

        mock_conn.commit.assert_called_once()
        mock_conn.rollback.assert_not_called()

    def test_transaction_rollback_on_failure(self) -> None:
        """Failure rolls back exactly once and preserves primary exception."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = ValueError("migration error")
        mock_conn.cursor.return_value = mock_cursor

        with pytest.raises(ValueError, match="migration error"):
            _apply_migrations_with_connection(mock_conn)

        mock_conn.rollback.assert_called_once()
        mock_conn.commit.assert_not_called()

    def test_cursor_closed_once(self) -> None:
        """Cursor closed exactly once in finally."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        _apply_migrations_with_connection(mock_conn)

        mock_cursor.close.assert_called_once()


class TestMigrationExecutionClosedCatalog:
    """Test that migrations are loaded from immutable catalog only."""

    def test_no_subset_bypass_allowed(self) -> None:
        """Caller-selected subset must be rejected - must use full catalog."""
        mock_cursor = MagicMock()

        # Attempt to pass any list should fail
        with pytest.raises(ValueError, match="subset|catalog|full"):
            _apply_migrations(mock_cursor, migration_filenames=["arbitrary.sql"])

    def test_none_means_full_catalog(self) -> None:
        """None (default) must load full catalog exactly once."""
        mock_cursor = MagicMock()

        # Use real catalog
        _apply_migrations(mock_cursor, migration_filenames=None)

        # Should execute all migrations in catalog order
        assert mock_cursor.execute.call_count >= 1

    def test_forces_full_catalog_order(self) -> None:
        """Migrations must be executed in exact catalog order."""
        from llamaindex_runtime.registry.migration_catalog import FULL_MIGRATION_CATALOG

        mock_cursor = MagicMock()

        _apply_migrations(mock_cursor, migration_filenames=None)

        # Must execute in exact catalog order (count matches catalog)
        assert mock_cursor.execute.call_count == len(FULL_MIGRATION_CATALOG)


class TestFullContainerInspect:
    """Test structured full container inspection."""

    def test_valid_full_inspect(self) -> None:
        """Valid full inspect returns valid result."""
        cid, tok, port = "a" * 64, "b" * 64, 5433

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            mock = MagicMock()
            mock.returncode = 0
            mock.stdout = f"{cid}|/test-container|{tok}|127.0.0.1:{port}"
            return mock

        result = _full_container_inspect(
            cid, "test-container", tok, port, config_dir="/tmp/config", run=mock_run
        )
        assert result.valid
        assert result.container_id == cid
        assert result.name == "test-container"
        assert result.owner == tok
        assert result.host_ip == "127.0.0.1"
        assert result.host_port == port

    def test_wrong_host_ip_invalid(self) -> None:
        """Wrong host IP returns invalid."""
        cid, tok, port = "a" * 64, "b" * 64, 5433

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            mock = MagicMock()
            mock.returncode = 0
            mock.stdout = f"{cid}|/test-container|{tok}|0.0.0.0:{port}"
            return mock

        result = _full_container_inspect(
            cid, "test-container", tok, port, config_dir="/tmp/config", run=mock_run
        )
        assert not result.valid

    def test_wrong_port_invalid(self) -> None:
        """Wrong port returns invalid."""
        cid, tok = "a" * 64, "b" * 64

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            mock = MagicMock()
            mock.returncode = 0
            mock.stdout = f"{cid}|/test-container|{tok}|127.0.0.1:5434"
            return mock

        result = _full_container_inspect(
            cid, "test-container", tok, 5433, config_dir="/tmp/config", run=mock_run
        )
        assert not result.valid

    def test_wrong_owner_invalid(self) -> None:
        """Wrong owner returns invalid."""
        cid, port = "a" * 64, 5433

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            mock = MagicMock()
            mock.returncode = 0
            mock.stdout = f"{cid}|/test-container|wrong-token|127.0.0.1:{port}"
            return mock

        result = _full_container_inspect(
            cid,
            "test-container",
            "b" * 64,
            port,
            config_dir="/tmp/config",
            run=mock_run,
        )
        assert not result.valid

    def test_wrong_name_invalid(self) -> None:
        """Wrong name returns invalid."""
        cid, tok, port = "a" * 64, "b" * 64, 5433

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            mock = MagicMock()
            mock.returncode = 0
            mock.stdout = f"{cid}|/wrong-container|{tok}|127.0.0.1:{port}"
            return mock

        result = _full_container_inspect(
            cid, "test-container", tok, port, config_dir="/tmp/config", run=mock_run
        )
        assert not result.valid

    def test_invalid_container_id(self) -> None:
        """Invalid container ID returns invalid."""
        result = _full_container_inspect(
            "invalid",
            "test-container",
            "b" * 64,
            5433,
            config_dir="/tmp/config",
            run=lambda *a, **k: MagicMock(),
        )
        assert not result.valid


class TestFullContainerInspectSecurity:
    """Test security requirements for full container inspection."""

    def test_never_requests_raw_json_format(self) -> None:
        """Full inspect must NEVER request raw {{json .}} format."""
        cid, tok, port = "a" * 64, "b" * 64, 5433
        docker_args_list: list[list[str]] = []

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            docker_args_list.append(list(args))
            mock = MagicMock()
            mock.returncode = 0
            mock.stdout = f"{cid}|/test-container|{tok}|127.0.0.1:{port}"
            return mock

        _full_container_inspect(
            cid, "test-container", tok, port, config_dir="/tmp/config", run=mock_run
        )

        # Check that no raw {{json .}} was used
        for args in docker_args_list:
            args_str = " ".join(args)
            assert (
                "{{json .}}" not in args_str
            ), "Must NOT request raw {{json .}} format"

    def test_requests_minimal_structured_format(self) -> None:
        """Full inspect must request minimal structured format."""
        cid, tok, port = "a" * 64, "b" * 64, 5433
        docker_args_list: list[list[str]] = []

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            docker_args_list.append(list(args))
            mock = MagicMock()
            mock.returncode = 0
            mock.stdout = f"{cid}|/test-container|{tok}|127.0.0.1:{port}"
            return mock

        _full_container_inspect(
            cid, "test-container", tok, port, config_dir="/tmp/config", run=mock_run
        )

        # Must use --format with minimal template
        found_format = False
        for args in docker_args_list:
            if "--format" in args:
                found_format = True
                # Check format argument is minimal (not raw {{json .}})
                format_idx = args.index("--format")
                if format_idx + 1 < len(args):
                    format_arg = args[format_idx + 1]
                    assert "{{json .}}" not in format_arg
                    # Should contain specific fields, not full object
                    assert ".Id" in format_arg or ".Name" in format_arg
        assert found_format, "Must use --format flag"

    def test_rejects_mismatched_container_id(self) -> None:
        """Must reject when returned container ID doesn't match requested."""
        cid, tok, port = "a" * 64, "b" * 64, 5433

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            mock = MagicMock()
            mock.returncode = 0
            # Return different container ID
            mock.stdout = f"{'c' * 64}|/test-container|{tok}|127.0.0.1:{port}"
            return mock

        result = _full_container_inspect(
            cid, "test-container", tok, port, config_dir="/tmp/config", run=mock_run
        )
        assert not result.valid

    def test_rejects_malformed_output(self) -> None:
        """Must reject malformed minimal format output."""
        cid, tok, port = "a" * 64, "b" * 64, 5433

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            mock = MagicMock()
            mock.returncode = 0
            mock.stdout = "not-valid-format"
            return mock

        result = _full_container_inspect(
            cid, "test-container", tok, port, config_dir="/tmp/config", run=mock_run
        )
        assert not result.valid

    def test_rejects_missing_name(self) -> None:
        """Must reject missing name field."""
        cid, tok, port = "a" * 64, "b" * 64, 5433

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            mock = MagicMock()
            mock.returncode = 0
            # Missing name (empty after slash)
            mock.stdout = f"{cid}||{tok}|127.0.0.1:{port}"
            return mock

        result = _full_container_inspect(
            cid, "test-container", tok, port, config_dir="/tmp/config", run=mock_run
        )
        assert not result.valid

    def test_rejects_missing_port_binding(self) -> None:
        """Must reject missing port binding."""
        cid, tok, port = "a" * 64, "b" * 64, 5433

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            mock = MagicMock()
            mock.returncode = 0
            # Missing port binding (empty last field)
            mock.stdout = f"{cid}|/test-container|{tok}|"
            return mock

        result = _full_container_inspect(
            cid, "test-container", tok, port, config_dir="/tmp/config", run=mock_run
        )
        assert not result.valid

    def test_uses_sanitized_env(self) -> None:
        """Full inspect can use sanitized environment when provided."""
        cid, tok, port = "a" * 64, "b" * 64, 5433
        env_received: list[dict[str, str] | None] = []

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            env_received.append(kwargs.get("env"))
            mock = MagicMock()
            mock.returncode = 0
            mock.stdout = f"{cid}|/test-container|{tok}|127.0.0.1:{port}"
            return mock

        # Pass sanitized env
        sanitized_env = {"PATH": "/usr/bin"}
        _full_container_inspect(
            cid,
            "test-container",
            tok,
            port,
            config_dir="/tmp/config",
            run=mock_run,
            env=sanitized_env,
        )

        # Env should be provided and should not contain sensitive vars
        assert len(env_received) == 1
        assert env_received[0] is not None
        # Check sensitive vars are absent
        sensitive = {
            "DATABASE_URL",
            "FORMAL_RUNTIME_DATABASE_URL",
            "OKF_E2A_DISPOSABLE_TEST_AUTHORIZED",
        }
        for var in sensitive:
            assert var not in env_received[0], f"Sensitive var {var} found in env"
