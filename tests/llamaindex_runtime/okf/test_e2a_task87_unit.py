"""Unit tests for Phase 15 Task #87: fresh-connection bridge and zero-capability post-lock seam.

TDD Phase: Parts 1-3 are RED-stage tests for the Task #87 implementation.
Parts 4-5 are characterization/security contracts over already-correct source
behavior: they were immediately GREEN when written, and no RED stage is
fabricated by mutating source (see the Part 4 and Part 5 section docstrings).

This module covers:
1. runtime_connection_factory autocommit/environ forwarding (testing FACTORY, not kwargs)
2. DisposableE2aSession.open_fresh_attested_connection bridge success/failure paths
3. E2aReconciler post_lock_sync_hook placement and error handling
4. _setup_database_impl default-path characterization/security contracts
5. _setup_database_impl cold-boot readiness budget contract (30 attempts @ 1.0s)
"""

from __future__ import annotations

import inspect
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import UUID

import psycopg
import pytest

from llamaindex_runtime.okf.e2a_contracts import (
    E2aDesiredState,
    E2aParent,
    E2aReconciliationResult,
)
from llamaindex_runtime.okf.e2a_reconciler import E2aReconciler


# =============================================================================
# Part 1: runtime_connection_factory autocommit/environ forwarding tests
# =============================================================================


class TestRuntimeConnectionFactoryForwarding:
    """Test runtime_connection_factory itself forwards autocommit and environ."""

    def test_factory_calls_psycopg_connect_with_kwargs_dict(self) -> None:
        """Factory must call psycopg.connect with the dict returned by runtime_connection_kwargs."""
        from scripts._rebuild_database_connection import (
            DisposablePostgresqlTarget,
            runtime_connection_factory,
        )

        target = DisposablePostgresqlTarget(
            host="127.0.0.1",
            hostaddr="127.0.0.1",
            port=5432,
            dbname="test_db",
            user="test_user",
            password="test_password",
        )

        mock_connection = MagicMock()
        kwargs_dict = {
            "host": "127.0.0.1",
            "port": 5432,
            "dbname": "test_db",
            "user": "test_user",
            "autocommit": False,
        }

        with patch(
            "scripts._rebuild_database_connection.psycopg.connect",
            return_value=mock_connection,
        ) as mock_connect:
            with patch(
                "scripts._rebuild_database_connection.runtime_connection_kwargs",
                return_value=kwargs_dict,
            ):
                result = runtime_connection_factory(target)

                # Assert psycopg.connect was called with the exact dict from kwargs
                mock_connect.assert_called_once_with(**kwargs_dict)
                assert result is mock_connection

    def test_factory_forwards_autocommit_true_to_kwargs(self) -> None:
        """Factory must forward autocommit=True to kwargs."""
        from scripts._rebuild_database_connection import (
            DisposablePostgresqlTarget,
            runtime_connection_factory,
        )

        target = DisposablePostgresqlTarget(
            host="127.0.0.1",
            hostaddr="127.0.0.1",
            port=5432,
            dbname="test_db",
            user="test_user",
            password="test_password",
        )

        mock_connection = MagicMock()
        kwargs_dict = {
            "host": "127.0.0.1",
            "port": 5432,
            "dbname": "test_db",
            "user": "test_user",
            "autocommit": True,
        }

        with patch(
            "scripts._rebuild_database_connection.psycopg.connect",
            return_value=mock_connection,
        ) as mock_connect:
            with patch(
                "scripts._rebuild_database_connection.runtime_connection_kwargs",
                return_value=kwargs_dict,
            ) as mock_kwargs:
                result = runtime_connection_factory(target, autocommit=True)

                # Assert kwargs was called with autocommit=True
                mock_kwargs.assert_called_once()
                call_kwargs = mock_kwargs.call_args
                assert call_kwargs[1].get("autocommit") is True
                # Assert psycopg.connect was called with the dict
                mock_connect.assert_called_once_with(**kwargs_dict)
                assert result is mock_connection

    def test_factory_forwards_environ_to_kwargs(self) -> None:
        """Factory must forward environ to kwargs."""
        from scripts._rebuild_database_connection import (
            DisposablePostgresqlTarget,
            runtime_connection_factory,
        )

        target = DisposablePostgresqlTarget(
            host="127.0.0.1",
            hostaddr="127.0.0.1",
            port=5432,
            dbname="test_db",
            user="test_user",
            password="test_password",
        )

        sanitized_env = {"PATH": "/usr/bin", "HOME": "/home/test"}
        mock_connection = MagicMock()
        kwargs_dict = {
            "host": "127.0.0.1",
            "port": 5432,
            "dbname": "test_db",
            "user": "test_user",
        }

        with patch(
            "scripts._rebuild_database_connection.psycopg.connect",
            return_value=mock_connection,
        ):
            with patch(
                "scripts._rebuild_database_connection.runtime_connection_kwargs",
                return_value=kwargs_dict,
            ) as mock_kwargs:
                result = runtime_connection_factory(target, environ=sanitized_env)

                # Assert kwargs was called with environ
                mock_kwargs.assert_called_once()
                call_kwargs = mock_kwargs.call_args
                assert call_kwargs[1].get("environ") is sanitized_env
                assert result is mock_connection

    def test_factory_forwards_both_autocommit_and_environ(self) -> None:
        """Factory must forward both autocommit and environ together."""
        from scripts._rebuild_database_connection import (
            DisposablePostgresqlTarget,
            runtime_connection_factory,
        )

        target = DisposablePostgresqlTarget(
            host="127.0.0.1",
            hostaddr="127.0.0.1",
            port=5432,
            dbname="test_db",
            user="test_user",
            password="test_password",
        )

        sanitized_env = {"PATH": "/usr/bin"}
        mock_connection = MagicMock()
        kwargs_dict = {
            "host": "127.0.0.1",
            "port": 5432,
            "dbname": "test_db",
            "user": "test_user",
            "autocommit": True,
        }

        with patch(
            "scripts._rebuild_database_connection.psycopg.connect",
            return_value=mock_connection,
        ):
            with patch(
                "scripts._rebuild_database_connection.runtime_connection_kwargs",
                return_value=kwargs_dict,
            ) as mock_kwargs:
                result = runtime_connection_factory(
                    target, autocommit=True, environ=sanitized_env
                )

                # Assert both were forwarded
                mock_kwargs.assert_called_once()
                call_kwargs = mock_kwargs.call_args
                assert call_kwargs[1].get("autocommit") is True
                assert call_kwargs[1].get("environ") is sanitized_env
                assert result is mock_connection

    def test_factory_signature_has_keyword_only_params(self) -> None:
        """Factory autocommit and environ must be keyword-only parameters - directly index both params."""
        from scripts._rebuild_database_connection import runtime_connection_factory

        sig = inspect.signature(runtime_connection_factory)

        # Directly index both params - must exist and be keyword-only
        autocommit_param = sig.parameters["autocommit"]
        environ_param = sig.parameters["environ"]

        assert (
            autocommit_param.kind == inspect.Parameter.KEYWORD_ONLY
        ), f"autocommit must be keyword-only, got {autocommit_param.kind}"
        assert (
            environ_param.kind == inspect.Parameter.KEYWORD_ONLY
        ), f"environ must be keyword-only, got {environ_param.kind}"


# =============================================================================
# Part 2: DisposableE2aSession.open_fresh_attested_connection bridge tests
# =============================================================================


def _make_mock_connection() -> MagicMock:
    """Create a mock connection with cursor/rollback/close."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.close = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_conn.rollback = MagicMock()
    mock_conn.close = MagicMock()
    return mock_conn


class TestBridgePreConditions:
    """Test bridge pre-conditions: authorization, entered session, no injected factory."""

    def test_bridge_requires_authorization_at_construction(self) -> None:
        """Session construction must fail without authorization."""
        from ._phase15_e2a_harness_lifecycle import DisposableE2aSession

        with patch.dict(
            "os.environ",
            {"OKF_E2A_DISPOSABLE_TEST_AUTHORIZED": "not-the-right-value"},
            clear=False,
        ):
            with pytest.raises(RuntimeError, match="authorization"):
                DisposableE2aSession(
                    container_name="test-container",
                    port="5432",
                    database="test_db",
                    user="test_user",
                    password="test_password",
                )

    def test_bridge_requires_entered_session_state(self) -> None:
        """Bridge must reject pre-enter state (no container ID/token) - verify neither reattest nor factory runs."""
        from . import _phase15_e2a_harness_lifecycle as lifecycle_module
        from ._phase15_e2a_harness_lifecycle import DisposableE2aSession

        with patch.dict(
            "os.environ",
            {"OKF_E2A_DISPOSABLE_TEST_AUTHORIZED": "separately-authorized"},
            clear=False,
        ):
            session = DisposableE2aSession(
                container_name="test-container",
                port="5432",
                database="test_db",
                user="test_user",
                password="test_password",
            )

            # Patch reattest and factory to ensure they are NOT called
            with patch.object(
                lifecycle_module, "_full_container_inspect"
            ) as mock_inspect:
                with patch(
                    "scripts._rebuild_database_connection.runtime_connection_factory"
                ) as mock_factory:
                    # Session not entered - should raise fixed error
                    with pytest.raises(RuntimeError, match="active|enter|session"):
                        session.open_fresh_attested_connection()

                    # Assert neither reattest nor factory was called
                    mock_inspect.assert_not_called()
                    mock_factory.assert_not_called()

    def test_bridge_rejects_injected_conn_factory_sessions(self) -> None:
        """Bridge must reject sessions with injected conn_factory - verify neither reattest nor factory runs."""
        from . import _phase15_e2a_harness_lifecycle as lifecycle_module
        from ._phase15_e2a_harness_lifecycle import DisposableE2aSession

        mock_conn_factory = MagicMock()

        with patch.dict(
            "os.environ",
            {"OKF_E2A_DISPOSABLE_TEST_AUTHORIZED": "separately-authorized"},
            clear=False,
        ):
            session = DisposableE2aSession(
                container_name="test-container",
                port="5432",
                database="test_db",
                user="test_user",
                password="test_password",
                conn_factory=mock_conn_factory,
            )

            # Simulate entered state
            import tempfile

            mock_config_dir = tempfile.TemporaryDirectory(prefix="test-config-")
            session._started = True
            session._container_id = "a" * 64
            session._token = "b" * 64
            session._docker_config_dir = mock_config_dir

            # Patch reattest and factory to ensure they are NOT called
            with patch.object(
                lifecycle_module, "_full_container_inspect"
            ) as mock_inspect:
                with patch(
                    "scripts._rebuild_database_connection.runtime_connection_factory"
                ) as mock_factory:
                    # Should reject injected factory mode with fixed error
                    with pytest.raises(RuntimeError, match="injected|factory"):
                        session.open_fresh_attested_connection()

                    # Assert neither reattest nor strict factory was called
                    mock_inspect.assert_not_called()
                    mock_factory.assert_not_called()

    def test_bridge_per_call_authorization_recheck(self) -> None:
        """Bridge must recheck authorization PER-CALL - fail before inspect/factory if auth revoked."""
        from . import _phase15_e2a_harness_lifecycle as lifecycle_module
        from ._phase15_e2a_harness_lifecycle import DisposableE2aSession

        # Construct under authorized env
        with patch.dict(
            "os.environ",
            {"OKF_E2A_DISPOSABLE_TEST_AUTHORIZED": "separately-authorized"},
            clear=False,
        ):
            session = DisposableE2aSession(
                container_name="test-container",
                port="5432",
                database="test_db",
                user="test_user",
                password="test_password",
            )

            # Establish controlled entered state
            session._started = True
            session._container_id = "a" * 64
            session._token = "b" * 64

            # Revoke/change auth after construction
            with patch.dict(
                "os.environ",
                {"OKF_E2A_DISPOSABLE_TEST_AUTHORIZED": "different-authorized-value"},
                clear=False,
            ):
                # Patch reattest and factory to ensure they are NOT called
                with patch.object(
                    lifecycle_module, "_full_container_inspect"
                ) as mock_inspect:
                    with patch(
                        "scripts._rebuild_database_connection.runtime_connection_factory"
                    ) as mock_factory:
                        # Should fail BEFORE _full_container_inspect or factory
                        with pytest.raises(
                            RuntimeError, match="authorization|authorized"
                        ):
                            session.open_fresh_attested_connection()

                        # Assert neither inspect nor factory was called
                        mock_inspect.assert_not_called()
                        mock_factory.assert_not_called()


class TestBridgeSuccessPath:
    """Test bridge success path with full mocked lifecycle."""

    def test_bridge_success_full_mocked_path(self) -> None:
        """Bridge must perform full re-attestation, attestation, rollback, return connection."""
        from . import _phase15_e2a_harness_lifecycle as lifecycle_module
        from ._phase15_e2a_harness_lifecycle import (
            DisposableE2aSession,
            FullInspectResult,
        )

        with patch.dict(
            "os.environ",
            {"OKF_E2A_DISPOSABLE_TEST_AUTHORIZED": "separately-authorized"},
            clear=False,
        ):
            session = DisposableE2aSession(
                container_name="test-container",
                port="5432",
                database="test_db",
                user="test_user",
                password="test_password",
            )

            # Simulate entered state
            import tempfile

            mock_config_dir = tempfile.TemporaryDirectory(prefix="test-config-")
            session._started = True
            session._container_id = "a" * 64
            session._token = "b" * 64
            session._docker_config_dir = mock_config_dir

            # Track calls
            inspect_calls: list[tuple[str, str, str, int]] = []
            parser_calls: list[dict[str, Any]] = []
            factory_calls: list[dict[str, Any]] = []
            attest_calls: list[tuple[Any, str, str, str]] = []

            def mock_full_inspect(
                container_id: str,
                name: str,
                token: str,
                port: int,
                **kwargs: Any,
            ) -> FullInspectResult:
                inspect_calls.append((container_id, name, token, port))
                return FullInspectResult(
                    container_id=container_id,
                    name=name,
                    owner=token,
                    host_ip="127.0.0.1",
                    host_port=port,
                    valid=True,
                )

            mock_conn = _make_mock_connection()
            mock_target = MagicMock()
            sanitized_env = {"PATH": "/usr/bin", "HOME": "/home/test"}

            def mock_parser(uri: str, database: str) -> MagicMock:
                parser_calls.append({"uri": uri, "database": database})
                return mock_target

            def mock_factory(target: Any, **kwargs: Any) -> MagicMock:
                factory_calls.append({"target": target, "kwargs": kwargs})
                return mock_conn

            def mock_attest(cursor: Any, db: str, schema: str, user: str) -> None:
                attest_calls.append((cursor, db, schema, user))

            with patch.object(
                lifecycle_module, "_full_container_inspect", mock_full_inspect
            ):
                with patch.object(
                    lifecycle_module, "_sanitized_env_copy", return_value=sanitized_env
                ):
                    with patch(
                        "scripts._rebuild_database_connection.parse_disposable_postgresql_target",
                        mock_parser,
                    ):
                        with patch(
                            "scripts._rebuild_database_connection.runtime_connection_factory",
                            mock_factory,
                        ):
                            with patch.object(
                                lifecycle_module, "_attest_target", mock_attest
                            ):
                                result = session.open_fresh_attested_connection()

            # Verify full inspect was called with exact container attestation args
            assert len(inspect_calls) == 1
            assert inspect_calls[0] == ("a" * 64, "test-container", "b" * 64, 5432)

            # Verify parser was called through the strict route with expected DB
            assert len(parser_calls) == 1
            parser_arg = parser_calls[0]
            assert parser_arg.get("database") == "test_db"
            assert "postgresql://" in parser_arg.get("uri", "")
            assert "127.0.0.1:5432" in parser_arg.get("uri", "")

            # Verify factory received its parsed target, autocommit=False, and the sanitized env
            assert len(factory_calls) == 1
            assert factory_calls[0]["target"] is mock_target
            assert factory_calls[0]["kwargs"].get("autocommit") is False
            assert factory_calls[0]["kwargs"].get("environ") == sanitized_env

            # Verify attestation was called
            assert len(attest_calls) == 1
            assert attest_calls[0][1:] == ("test_db", "public", "test_user")

            # Verify cursor was closed
            mock_conn.cursor.return_value.close.assert_called_once()

            # Verify rollback was called before return
            mock_conn.rollback.assert_called_once()

            # Verify returned connection is the mock
            assert result is mock_conn

    def test_bridge_returns_distinct_connections_per_invocation(self) -> None:
        """Each call must return a distinct fresh connection."""
        from . import _phase15_e2a_harness_lifecycle as lifecycle_module
        from ._phase15_e2a_harness_lifecycle import (
            DisposableE2aSession,
            FullInspectResult,
        )

        with patch.dict(
            "os.environ",
            {"OKF_E2A_DISPOSABLE_TEST_AUTHORIZED": "separately-authorized"},
            clear=False,
        ):
            session = DisposableE2aSession(
                container_name="test-container",
                port="5432",
                database="test_db",
                user="test_user",
                password="test_password",
            )

            import tempfile

            mock_config_dir = tempfile.TemporaryDirectory(prefix="test-config-")
            session._started = True
            session._container_id = "a" * 64
            session._token = "b" * 64
            session._docker_config_dir = mock_config_dir

            conn_counter = [0]
            connections: list[MagicMock] = []

            def mock_factory(target: Any, **kwargs: Any) -> MagicMock:
                conn_counter[0] += 1
                mock_conn = _make_mock_connection()
                mock_conn._id = conn_counter[0]
                connections.append(mock_conn)
                return mock_conn

            valid_result = FullInspectResult(
                container_id="a" * 64,
                name="test-container",
                owner="b" * 64,
                host_ip="127.0.0.1",
                host_port=5432,
                valid=True,
            )

            mock_target = MagicMock()

            with patch.object(
                lifecycle_module, "_full_container_inspect", return_value=valid_result
            ):
                with patch.object(
                    lifecycle_module, "_sanitized_env_copy", return_value={}
                ):
                    with patch(
                        "scripts._rebuild_database_connection.parse_disposable_postgresql_target",
                        return_value=mock_target,
                    ):
                        with patch(
                            "scripts._rebuild_database_connection.runtime_connection_factory",
                            mock_factory,
                        ):
                            with patch.object(lifecycle_module, "_attest_target"):
                                conn1 = session.open_fresh_attested_connection()
                                conn2 = session.open_fresh_attested_connection()

            # Must return distinct connections
            assert conn1 is not conn2
            assert len(connections) == 2


class TestBridgeFailurePath:
    """Test bridge failure paths: connection close, redacted error."""

    def test_bridge_closes_connection_on_attestation_failure(self) -> None:
        """On attestation failure, newly opened connection must be closed with cursor cleanup."""
        from . import _phase15_e2a_harness_lifecycle as lifecycle_module
        from ._phase15_e2a_harness_lifecycle import (
            DisposableE2aSession,
            FullInspectResult,
        )

        with patch.dict(
            "os.environ",
            {"OKF_E2A_DISPOSABLE_TEST_AUTHORIZED": "separately-authorized"},
            clear=False,
        ):
            session = DisposableE2aSession(
                container_name="test-container",
                port="5432",
                database="test_db",
                user="test_user",
                password="test_password",
            )

            import tempfile

            mock_config_dir = tempfile.TemporaryDirectory(prefix="test-config-")
            session._started = True
            session._container_id = "a" * 64
            session._token = "b" * 64
            session._docker_config_dir = mock_config_dir

            mock_conn = _make_mock_connection()
            mock_cursor = mock_conn.cursor.return_value

            valid_result = FullInspectResult(
                container_id="a" * 64,
                name="test-container",
                owner="b" * 64,
                host_ip="127.0.0.1",
                host_port=5432,
                valid=True,
            )

            def fail_attest(cursor: Any, db: str, schema: str, user: str) -> None:
                raise ValueError("sensitive attestation error with password123")

            mock_target = MagicMock()

            with patch.object(
                lifecycle_module, "_full_container_inspect", return_value=valid_result
            ):
                with patch.object(
                    lifecycle_module, "_sanitized_env_copy", return_value={}
                ):
                    with patch(
                        "scripts._rebuild_database_connection.parse_disposable_postgresql_target",
                        return_value=mock_target,
                    ):
                        with patch(
                            "scripts._rebuild_database_connection.runtime_connection_factory",
                            return_value=mock_conn,
                        ):
                            with patch.object(
                                lifecycle_module, "_attest_target", fail_attest
                            ):
                                with pytest.raises(
                                    RuntimeError,
                                    match="Fresh attested connection bridge failed",
                                ) as exc_info:
                                    session.open_fresh_attested_connection()

            # Connection must be closed on failure
            mock_conn.close.assert_called_once()

            # Cursor must be closed on failure
            mock_cursor.close.assert_called_once()

            # Error must be exactly the fixed redacted text
            assert str(exc_info.value) == "Fresh attested connection bridge failed"

            # Context must be suppressed
            assert exc_info.value.__suppress_context__ is True

            # Error must not contain sensitive values
            error_msg = str(exc_info.value)
            assert "password" not in error_msg.lower()
            assert "token" not in error_msg.lower()

    def test_bridge_error_is_redacted_no_sensitive_values(self) -> None:
        """Bridge failure error must be fixed redacted message with suppressed context."""
        from . import _phase15_e2a_harness_lifecycle as lifecycle_module
        from ._phase15_e2a_harness_lifecycle import (
            DisposableE2aSession,
            FullInspectResult,
        )

        with patch.dict(
            "os.environ",
            {"OKF_E2A_DISPOSABLE_TEST_AUTHORIZED": "separately-authorized"},
            clear=False,
        ):
            session = DisposableE2aSession(
                container_name="test-container",
                port="5432",
                database="test_db",
                user="test_user",
                password="secret_password_12345",
            )

            import tempfile

            mock_config_dir = tempfile.TemporaryDirectory(prefix="test-config-")
            session._started = True
            session._container_id = "a" * 64
            session._token = "b" * 64
            session._docker_config_dir = mock_config_dir

            valid_result = FullInspectResult(
                container_id="a" * 64,
                name="test-container",
                owner="b" * 64,
                host_ip="127.0.0.1",
                host_port=5432,
                valid=True,
            )

            def fail_factory(target: Any, **kwargs: Any) -> MagicMock:
                raise ValueError("connection failed with password123 and token xyz")

            mock_target = MagicMock()

            with patch.object(
                lifecycle_module, "_full_container_inspect", return_value=valid_result
            ):
                with patch.object(
                    lifecycle_module, "_sanitized_env_copy", return_value={}
                ):
                    with patch(
                        "scripts._rebuild_database_connection.parse_disposable_postgresql_target",
                        return_value=mock_target,
                    ):
                        with patch(
                            "scripts._rebuild_database_connection.runtime_connection_factory",
                            fail_factory,
                        ):
                            with pytest.raises(
                                RuntimeError,
                                match="Fresh attested connection bridge failed",
                            ) as exc_info:
                                session.open_fresh_attested_connection()

            # Error message must be exactly the fixed redacted text
            assert str(exc_info.value) == "Fresh attested connection bridge failed"

            # Context must be suppressed
            assert exc_info.value.__suppress_context__ is True

            # Error message must not contain sensitive values
            error_msg = str(exc_info.value)
            assert "password" not in error_msg.lower()
            assert "token" not in error_msg.lower()
            assert "xyz" not in error_msg


# =============================================================================
# Part 3: E2aReconciler post_lock_sync_hook tests
# =============================================================================


def _uuid(number: int) -> str:
    return str(UUID(int=number))


def _digest() -> str:
    return "a" * 64


def _desired(*, parent_count: int = 1) -> E2aDesiredState:
    parents = tuple(
        E2aParent(_uuid(index), _uuid(index + 100), f"raw/{index}.pair.json", _digest())
        for index in range(1, parent_count + 1)
    )
    from types import MappingProxyType

    from llamaindex_runtime.okf.e2a_contracts import canonical_json_sha256

    manifest = {
        "schema": "e2a-corpus-v1",
        "artifacts": [
            {
                "kind": "raw_pair",
                "path": parent.relative_path,
                "identity": f"{parent.document_id}:{parent.version_id}",
                "canonical_hash": parent.canonical_hash,
            }
            for parent in parents
        ],
    }
    return E2aDesiredState(
        corpus_manifest=manifest,
        corpus_manifest_sha256=canonical_json_sha256(manifest),
        parents=parents,
        canonical_spans=(),
        vector_chunks=(),
        vector_chunk_span_links=(),
        tree_nodes=(),
        tree_node_span_links=(),
        manual_entities=(),
        manual_relations=(),
        manual_concepts=(),
        evidence_objects=(),
        evidence_links=(),
        ownership_facts=(),
        sync_state_rows=(),
        validation_metadata=MappingProxyType({}),
        provenance_metadata=MappingProxyType({"authority": "okf"}),
    )


class _MockCursor:
    """Mock cursor for reconciler tests."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, object | None]] = []
        self._last_statement = ""
        self.closed = 0
        self.adapters = _MockAdapterRegistry()
        self.connection = object()

    def execute(self, statement: str, parameters: object | None = None) -> None:
        self._last_statement = statement
        self.calls.append((statement, parameters))

    def fetchall(self) -> list[dict[str, object]]:
        parameters = self.calls[-1][1] if self.calls else None
        is_parent_lock = "document_versions" in self._last_statement.lower()
        if is_parent_lock and isinstance(parameters, tuple) and len(parameters) == 2:
            return [{"doc_id": parameters[0], "version_id": parameters[1]}]
        return []

    def fetchone(self) -> dict[str, object] | None:
        return None

    def close(self) -> None:
        self.closed += 1


class _MockAdapterRegistry:
    def register_loader(self, _: str, __: object) -> None:
        return None


class _MockConnection:
    """Mock connection for reconciler tests."""

    def __init__(self, cursor: _MockCursor) -> None:
        self._cursor = cursor
        self.autocommit: bool = False
        self.commits: int = 0
        self.rollbacks: int = 0
        self.closed: int = 0

    def cursor(self, *, row_factory: object = None) -> _MockCursor:
        return self._cursor

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed += 1


class TestReconcilerPostLockSyncHook:
    """Test post_lock_sync_hook parameter and behavior."""

    def test_hook_default_none_no_change(self) -> None:
        """None hook must leave current behavior unchanged."""
        cursor = _MockCursor()
        connection = _MockConnection(cursor)

        class NoOpRepository:
            def reconcile(
                self, _: object, desired: E2aDesiredState, *, recorder: object
            ) -> E2aReconciliationResult:
                return E2aReconciliationResult(
                    outcome="no_op",
                    manifest_sha256=desired.corpus_manifest_sha256,
                    primary_dml_by_table={},
                    denylist_dml_counts={},
                    comparator_parity=True,
                    stale_deletion_counts={},
                    cache_invalidation_counts={},
                    failure_audit_outcome=None,
                    post_rollback_failure_audit_outcome=None,
                )

        reconciler = E2aReconciler(repository=NoOpRepository())
        result = reconciler.reconcile(connection, _desired())

        assert result.outcome == "no_op"

    def test_hook_rejects_non_callable_with_value_error(self) -> None:
        """Non-None non-callable must raise ValueError mentioning post_lock_sync_hook."""
        from typing import cast

        with pytest.raises(ValueError, match="post_lock_sync_hook|callable"):
            E2aReconciler(post_lock_sync_hook=cast(Any, "not_callable"))

    def test_hook_accepts_callable_zero_args(self) -> None:
        """Callable hook must be accepted and stored."""

        def my_hook() -> None:
            pass

        reconciler = E2aReconciler(post_lock_sync_hook=my_hook)
        assert reconciler._post_lock_sync_hook is my_hook

    def test_hook_exact_placement_after_locks_before_preflights(self) -> None:
        """Hook must be called exactly after locks, before global_preflight, before manual_preflight."""
        cursor = _MockCursor()
        connection = _MockConnection(cursor)

        # Track exact event sequence
        events: list[str] = []

        # Save original methods
        original_acquire = E2aReconciler._acquire_scope_locks

        def tracked_acquire(
            self: E2aReconciler, cur: _MockCursor, desired: E2aDesiredState
        ) -> None:
            events.append("locks")
            # Call original to populate cursor.calls
            original_acquire(self, cur, desired)

        def tracked_hook() -> None:
            events.append("hook")

        def tracked_global_preflight(
            cur: _MockCursor, desired: E2aDesiredState
        ) -> None:
            events.append("global_preflight")
            # Return without raising (no-op)

        # Track manual preflight
        def tracked_manual_preflight(
            cur: _MockCursor, desired: E2aDesiredState
        ) -> None:
            events.append("manual_preflight")

        class TrackingRepository:
            def reconcile(
                self, _: object, desired: E2aDesiredState, *, recorder: object
            ) -> E2aReconciliationResult:
                events.append("repository")
                return E2aReconciliationResult(
                    outcome="no_op",
                    manifest_sha256=desired.corpus_manifest_sha256,
                    primary_dml_by_table={},
                    denylist_dml_counts={},
                    comparator_parity=True,
                    stale_deletion_counts={},
                    cache_invalidation_counts={},
                    failure_audit_outcome=None,
                    post_rollback_failure_audit_outcome=None,
                )

        reconciler = E2aReconciler(
            repository=TrackingRepository(),
            post_lock_sync_hook=tracked_hook,
        )

        with patch.object(E2aReconciler, "_acquire_scope_locks", tracked_acquire):
            with patch(
                "llamaindex_runtime.okf.e2a_reconciler._preflight_global_primary_keys",
                tracked_global_preflight,
            ):
                with patch(
                    "llamaindex_runtime.okf.e2a_reconciler.preflight_manual_fact_collisions",
                    tracked_manual_preflight,
                ):
                    result = reconciler.reconcile(connection, _desired())

        assert result.outcome == "no_op"

        # Verify exact event sequence: locks -> hook -> global_preflight -> manual_preflight -> repository
        assert events == [
            "locks",
            "hook",
            "global_preflight",
            "manual_preflight",
            "repository",
        ], f"Expected exact sequence, got: {events}"

    def test_hook_receives_zero_arguments_strict(self) -> None:
        """Hook must receive exactly zero arguments - no cursor/connection/state."""
        cursor = _MockCursor()
        connection = _MockConnection(cursor)

        call_args: list[tuple[object, ...]] = []
        call_kwargs: list[dict[str, object]] = []

        def strict_hook(*args: object, **kwargs: object) -> None:
            call_args.append(args)
            call_kwargs.append(kwargs)

        class NoOpRepository:
            def reconcile(
                self, _: object, desired: E2aDesiredState, *, recorder: object
            ) -> E2aReconciliationResult:
                return E2aReconciliationResult(
                    outcome="no_op",
                    manifest_sha256=desired.corpus_manifest_sha256,
                    primary_dml_by_table={},
                    denylist_dml_counts={},
                    comparator_parity=True,
                    stale_deletion_counts={},
                    cache_invalidation_counts={},
                    failure_audit_outcome=None,
                    post_rollback_failure_audit_outcome=None,
                )

        reconciler = E2aReconciler(
            repository=NoOpRepository(),
            post_lock_sync_hook=strict_hook,
        )
        reconciler.reconcile(connection, _desired())

        # Must receive exactly zero args and zero kwargs
        assert call_args == [()], f"Hook received unexpected args: {call_args}"
        assert call_kwargs == [{}], f"Hook received unexpected kwargs: {call_kwargs}"

    def test_hook_exception_triggers_rollback_close_failure_audit(self) -> None:
        """Hook exception must flow through rollback/close and trigger failure audit."""
        cursor = _MockCursor()
        connection = _MockConnection(cursor)

        class HookError(Exception):
            pass

        def failing_hook() -> None:
            raise HookError("hook failure")

        class NoOpRepository:
            def reconcile(
                self, _: object, desired: E2aDesiredState, *, recorder: object
            ) -> E2aReconciliationResult:
                # Should not be called
                return E2aReconciliationResult(
                    outcome="no_op",
                    manifest_sha256=desired.corpus_manifest_sha256,
                    primary_dml_by_table={},
                    denylist_dml_counts={},
                    comparator_parity=True,
                    stale_deletion_counts={},
                    cache_invalidation_counts={},
                    failure_audit_outcome=None,
                    post_rollback_failure_audit_outcome=None,
                )

        # Without failure_audit_connection_factory, exception must propagate
        reconciler = E2aReconciler(
            repository=NoOpRepository(),
            post_lock_sync_hook=failing_hook,
        )

        with pytest.raises(HookError):
            reconciler.reconcile(connection, _desired())

        # Connection must be rolled back
        assert connection.rollbacks >= 1, "Primary connection must be rolled back"

        # Connection must be closed
        assert connection.closed >= 1, "Primary connection must be closed"

    def test_hook_exception_with_failure_audit_returns_result(self) -> None:
        """With failure_audit_connection_factory, hook exception returns rolled_back_failure result with audit."""
        cursor = _MockCursor()
        connection = _MockConnection(cursor)

        audit_factory_calls: list[int] = []
        audit_write_calls: list[dict[str, Any]] = []

        class HookError(Exception):
            pass

        def failing_hook() -> None:
            raise HookError("hook failure")

        class NoOpRepository:
            def reconcile(
                self, _: object, desired: E2aDesiredState, *, recorder: object
            ) -> E2aReconciliationResult:
                return E2aReconciliationResult(
                    outcome="no_op",
                    manifest_sha256=desired.corpus_manifest_sha256,
                    primary_dml_by_table={},
                    denylist_dml_counts={},
                    comparator_parity=True,
                    stale_deletion_counts={},
                    cache_invalidation_counts={},
                    failure_audit_outcome=None,
                    post_rollback_failure_audit_outcome=None,
                )

        def audit_factory() -> _MockConnection:
            audit_factory_calls.append(1)
            audit_cursor = _MockCursor()
            audit_conn = _MockConnection(audit_cursor)
            return audit_conn

        def mock_write_failure_audit(
            self,
            desired: Any,
            failure: Exception,
            *,
            rollback_confirmed: bool,
        ):
            audit_write_calls.append(
                {
                    "desired": desired,
                    "exc": failure,
                    "rollback_confirmed": rollback_confirmed,
                }
            )
            # Return object with outcome attribute
            return type(
                "_AuditWriteResult",
                (),
                {"outcome": "hook_exception_audit", "cleanup": None},
            )()

        reconciler = E2aReconciler(
            repository=NoOpRepository(),
            post_lock_sync_hook=failing_hook,
            failure_audit_connection_factory=audit_factory,
        )

        with patch.object(
            E2aReconciler, "_write_failure_audit", mock_write_failure_audit
        ):
            result = reconciler.reconcile(connection, _desired())

        # Must return rolled_back_failure result, not raise
        assert result.outcome == "rolled_back_failure"

        # Connection must be rolled back
        assert connection.rollbacks >= 1, "Primary connection must be rolled back"

        # Connection must be closed
        assert connection.closed >= 1, "Primary connection must be closed"

        # Failure audit write must be called with hook exception
        assert len(audit_write_calls) >= 1, "Failure audit write must be invoked"
        assert isinstance(
            audit_write_calls[0]["exc"], HookError
        ), "Audit must receive hook exception"
        assert (
            audit_write_calls[0]["rollback_confirmed"] is True
        ), "Rollback must be confirmed"

        # Result must have post_rollback_failure_audit_outcome from mocked audit
        assert result.post_rollback_failure_audit_outcome == "hook_exception_audit"


class TestBlockedImportProof:
    """Test that blocked modules are not imported."""

    def test_importing_lifecycle_does_not_import_blocked_modules(self) -> None:
        """Importing lifecycle helper must not import any of the 8 blocked modules."""
        import sys
        import subprocess
        from pathlib import Path

        project_root = Path(__file__).parent.parent.parent.parent

        script = f"""
import sys
import importlib.util
from types import ModuleType
from pathlib import Path

project_root = Path("{project_root.as_posix()}")
sys.path.insert(0, str(project_root))

# Create package chain
tests_pkg = ModuleType("tests")
tests_pkg.__path__ = [str(project_root / "tests")]
tests_pkg.__package__ = "tests"
sys.modules["tests"] = tests_pkg

tests_llamaindex_pkg = ModuleType("tests.llamaindex_runtime")
tests_llamaindex_pkg.__path__ = [str(project_root / "tests" / "llamaindex_runtime")]
tests_llamaindex_pkg.__package__ = "tests.llamaindex_runtime"
sys.modules["tests.llamaindex_runtime"] = tests_llamaindex_pkg

tests_okf_pkg = ModuleType("tests.llamaindex_runtime.okf")
tests_okf_pkg.__path__ = [str(project_root / "tests" / "llamaindex_runtime" / "okf")]
tests_okf_pkg.__package__ = "tests.llamaindex_runtime.okf"
sys.modules["tests.llamaindex_runtime.okf"] = tests_okf_pkg

# Import types
spec_types = importlib.util.spec_from_file_location(
    "tests.llamaindex_runtime.okf._phase15_e2a_harness_types",
    project_root / "tests" / "llamaindex_runtime" / "okf" / "_phase15_e2a_harness_types.py",
    submodule_search_locations=[],
)
types_mod = importlib.util.module_from_spec(spec_types)
types_mod.__package__ = "tests.llamaindex_runtime.okf"
sys.modules["tests.llamaindex_runtime.okf._phase15_e2a_harness_types"] = types_mod
spec_types.loader.exec_module(types_mod)

# Import lifecycle
spec_lifecycle = importlib.util.spec_from_file_location(
    "tests.llamaindex_runtime.okf._phase15_e2a_harness_lifecycle",
    project_root / "tests" / "llamaindex_runtime" / "okf" / "_phase15_e2a_harness_lifecycle.py",
    submodule_search_locations=[],
)
lifecycle_mod = importlib.util.module_from_spec(spec_lifecycle)
lifecycle_mod.__package__ = "tests.llamaindex_runtime.okf"
sys.modules["tests.llamaindex_runtime.okf._phase15_e2a_harness_lifecycle"] = lifecycle_mod
spec_lifecycle.loader.exec_module(lifecycle_mod)

# Check blocked modules
blocked = [
    "tests.llamaindex_runtime.okf.test_real_e2a_reconciler_harness_unit",
    "tests.llamaindex_runtime.okf.test_real_e2a_reconciler_lifecycle_unit",
    "tests.llamaindex_runtime.okf.test_real_e2a_reconciler_acceptance",
    "tests.llamaindex_runtime.okf._real_e2a_reconciler_container_cleanup",
    "tests.llamaindex_runtime.okf._real_e2a_reconciler_lifecycle",
    "tests.llamaindex_runtime.okf._real_e2a_reconciler_types",
    "llamaindex_runtime.okf.e2a_disposable_execution",
    "verification.phase15-okf-ingestion-pipeline.run_e2a_verification",
]

imported_blocked = [m for m in blocked if m in sys.modules]
if imported_blocked:
    sys.exit(1)
sys.exit(0)
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            cwd=str(project_root),
        )

        assert result.returncode == 0, f"Blocked modules were imported: {result.stderr}"


# =============================================================================
# Part 4: _setup_database_impl default (non-injected) path contracts
# =============================================================================


class TestSetupDatabaseDefaultPath:
    """Characterization/security contracts for the default (non-injected) _setup_database_impl path.

    TDD note: the source behavior already exists, so these are characterization
    and security contracts, not new-feature tests; no RED stage is manufactured
    by mutating source. The gate failure (77.11% < 80%) is the red signal this
    increment addresses. All external effects are module-level patches/fakes:
    no Docker, no PostgreSQL, no network, no filesystem credential persistence,
    no real database connection.
    """

    def test_default_path_success_orchestration(self) -> None:
        """Default path must percent-encode every URI-reserved character in the user and
        password, then forward sanitized env, attest, and migrate."""
        from . import _phase15_e2a_harness_lifecycle as lifecycle_module

        mock_conn = _make_mock_connection()
        mock_target = MagicMock()
        sanitized_env = {"PATH": "/usr/bin"}

        parser_calls: list[tuple[str, str]] = []
        factory_calls: list[tuple[Any, dict[str, Any]]] = []
        wait_calls: list[tuple[Any, dict[str, Any]]] = []
        attest_calls: list[tuple[Any, str, str, str]] = []
        migrate_calls: list[Any] = []

        def mock_parser(uri: str, database: str) -> MagicMock:
            parser_calls.append((uri, database))
            return mock_target

        def mock_factory(target: Any, **kwargs: Any) -> MagicMock:
            factory_calls.append((target, kwargs))
            return mock_conn

        def mock_wait(conn_factory: Any, **kwargs: Any) -> None:
            wait_calls.append((conn_factory, kwargs))
            # Exercise the real default-path closure: it must forward the
            # parsed target and the sanitized env to runtime_connection_factory.
            conn_factory()

        def mock_attest(cursor: Any, db: str, schema: str, user: str) -> None:
            attest_calls.append((cursor, db, schema, user))

        def mock_migrate(conn: Any, migration_filenames: Any = None) -> None:
            migrate_calls.append(conn)

        with patch.object(
            lifecycle_module, "_sanitized_env_copy", return_value=sanitized_env
        ):
            with patch(
                "scripts._rebuild_database_connection.parse_disposable_postgresql_target",
                mock_parser,
            ):
                with patch(
                    "scripts._rebuild_database_connection.runtime_connection_factory",
                    mock_factory,
                ):
                    with patch.object(lifecycle_module, "_wait_for_ready", mock_wait):
                        with patch.object(
                            lifecycle_module, "_attest_target", mock_attest
                        ):
                            with patch.object(
                                lifecycle_module,
                                "_apply_migrations_with_connection",
                                mock_migrate,
                            ):
                                # Hostile-but-fake inline test literals (never
                                # environment-derived): every URI-reserved character in
                                # the user/password must be percent-encoded before the
                                # parser is called.
                                result = lifecycle_module._setup_database_impl(
                                    "5432",
                                    "test_db",
                                    "test:user@example/%",
                                    "p@ss/word?with#hash%",
                                    None,
                                    sleep_fn=lambda seconds: None,
                                )

        # Success result with redacted string forms (no credentials)
        assert result.success is True
        assert str(result) == "_DatabaseSetupResult(success=True)"
        assert "p@ss/word?with#hash%" not in str(result)
        assert "p@ss/word?with#hash%" not in repr(result)

        # Default path must build target from percent-encoded URI with exact database.
        # Expected value is hard-coded (never recomputed with the encoder): raw
        # interpolation of the fake user/password would leave literal reserved
        # characters in the userinfo and fail this exact-equality contract.
        assert len(parser_calls) == 1
        uri, database_arg = parser_calls[0]
        assert database_arg == "test_db"
        assert uri == (
            "postgresql://test%3Auser%40example%2F%25:"
            "p%40ss%2Fword%3Fwith%23hash%25@127.0.0.1:5432/test_db"
        )

        # Factory must receive the parsed target and the sanitized Docker env
        # for BOTH the readiness probe and the attestation connection
        assert len(factory_calls) == 2
        assert factory_calls[0][0] is mock_target
        assert factory_calls[0][1].get("environ") == sanitized_env
        assert factory_calls[1][0] is mock_target
        assert factory_calls[1][1].get("environ") == sanitized_env

        # Readiness wait must receive the closure and the injected sleep
        assert len(wait_calls) == 1
        assert wait_calls[0][1].get("sleep") is not None

        # Attestation must run with the exact target contract, using the UNENCODED
        # logical database and user (not the percent-encoded URI forms)
        assert len(attest_calls) == 1
        assert attest_calls[0][1:] == ("test_db", "public", "test:user@example/%")

        # Migrations must run on the opened connection
        assert len(migrate_calls) == 1
        assert migrate_calls[0] is mock_conn

        # Connection cursor was acquired through the opened connection
        mock_conn.cursor.assert_called()

    def test_default_path_failure_closes_cursor_and_conn_fail_closed(self) -> None:
        """Default path failure must absorb, close cursor+conn (even if close raises), return safe False."""
        from . import _phase15_e2a_harness_lifecycle as lifecycle_module

        mock_conn = _make_mock_connection()
        mock_cursor = mock_conn.cursor.return_value
        mock_target = MagicMock()
        sanitized_env = {"PATH": "/usr/bin"}

        # Close failures must not mask or escape the absorbed setup failure
        mock_cursor.close.side_effect = RuntimeError("cursor close failed")
        mock_conn.close.side_effect = RuntimeError("conn close failed")

        def mock_factory(target: Any, **kwargs: Any) -> MagicMock:
            return mock_conn

        def mock_migrate_fail(conn: Any, migration_filenames: Any = None) -> None:
            raise RuntimeError("migration failed with secret_password inside")

        with patch.object(
            lifecycle_module, "_sanitized_env_copy", return_value=sanitized_env
        ):
            with patch(
                "scripts._rebuild_database_connection.parse_disposable_postgresql_target",
                return_value=mock_target,
            ):
                with patch(
                    "scripts._rebuild_database_connection.runtime_connection_factory",
                    mock_factory,
                ):
                    with patch.object(lifecycle_module, "_wait_for_ready"):
                        with patch.object(lifecycle_module, "_attest_target"):
                            with patch.object(
                                lifecycle_module,
                                "_apply_migrations_with_connection",
                                mock_migrate_fail,
                            ):
                                result = lifecycle_module._setup_database_impl(
                                    "5432",
                                    "test_db",
                                    "test_user",
                                    "test_password",
                                    None,
                                    sleep_fn=lambda seconds: None,
                                )

        # Failure must be absorbed into a safe False result - no exception escapes
        assert result.success is False
        assert str(result) == "_DatabaseSetupResult(success=False)"
        assert "test_password" not in str(result)
        assert "test_password" not in repr(result)

        # Both cursor and connection close were attempted despite close failures
        mock_cursor.close.assert_called_once()
        mock_conn.close.assert_called_once()


# =============================================================================
# Part 5: _setup_database_impl cold-boot readiness budget (Task #87 fix)
# =============================================================================


class TestSetupDatabaseColdBootReadinessBudget:
    """Task #87 readiness-policy fix: _setup_database_impl must run the REAL
    _wait_for_ready under a bounded production budget that tolerates a cold
    disposable PostgreSQL first boot lasting longer than the legacy 3-attempt
    probe.

    The source already implements the exact agreed policy (30 attempts spaced
    1.0s apart), so every assertion in this section is IMMEDIATELY GREEN - it
    pins the contract, it does not claim a fresh RED stage. Expected values
    are hard-coded literals (30 and 1.0), never derived from the module
    constants, so a regression such as 30 -> 5 attempts or 1.0 -> 0.5s fails
    these tests even if the constants and defaults were changed in lockstep.

    Deterministic and non-live: the controlled connection factory raises
    psycopg.OperationalError for a fixed number of attempts then succeeds;
    the injected no-op sleep guarantees zero wall-clock delay; only downstream
    attestation/migration are mocked. No Docker, no PostgreSQL, no network.
    """

    def test_readiness_policy_constants_pin_exact_contract(self) -> None:
        """The readiness budget is a hard-coded policy contract: exactly 30
        attempts spaced exactly 1.0s apart.

        Asserted against BOTH the module constants and the _wait_for_ready
        default parameter values (which _setup_database_impl relies on
        implicitly): each must be exactly 30 and exactly 1.0. A regression in
        either the constant or the signature default (e.g. 30 -> 5,
        1.0 -> 0.5) fails here, and the behavior tests below independently
        fail if the effective budget drifts.
        """
        from . import _phase15_e2a_harness_lifecycle as lifecycle_module
        from ._phase15_e2a_harness_lifecycle import _wait_for_ready

        # Hard-coded contract - independent of the values it verifies.
        assert lifecycle_module._READY_MAX_ATTEMPTS == 30
        assert lifecycle_module._READY_RETRY_DELAY_SECONDS == 1.0

        # _setup_database_impl calls _wait_for_ready without an explicit
        # budget, so the signature defaults ARE the effective policy.
        sig_params = inspect.signature(_wait_for_ready).parameters
        assert sig_params["max_retries"].default == 30
        assert sig_params["delay"].default == 1.0

    def test_cold_boot_longer_than_legacy_three_attempts_succeeds(self) -> None:
        """A legitimate cold first boot that outlives the legacy 3-attempt probe
        must still yield a successful setup result under the bounded budget."""
        from . import _phase15_e2a_harness_lifecycle as lifecycle_module

        # More consecutive failures than the legacy production default of 3
        # startup attempts: a cold pgvector/pgvector:pg15 first boot may still
        # be initializing past the old probe window.
        fail_attempts = 4
        call_count = [0]
        sleep_calls: list[float] = []

        def controlled_conn_factory(
            host: str,
            port: int,
            database: str,
            user: str,
            password: str | None = None,
            **kwargs: Any,
        ) -> Any:
            call_count[0] += 1
            if call_count[0] <= fail_attempts:
                raise psycopg.OperationalError("cold boot still initializing")
            return _make_mock_connection()

        def noop_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        with patch.object(lifecycle_module, "_attest_target"):
            with patch.object(lifecycle_module, "_apply_migrations_with_connection"):
                result = lifecycle_module._setup_database_impl(
                    "5432",
                    "test_db",
                    "test_user",
                    "test_password",
                    controlled_conn_factory,
                    sleep_fn=noop_sleep,
                )

        assert result.success is True
        # Exactly 4 failed probes + 1 successful probe + 1 attestation
        # connection = 6 connection-factory calls (exact expected value).
        assert call_count[0] == 6
        # The cold boot must fit inside the pinned 30-attempt budget.
        assert call_count[0] <= 30
        # Every failed attempt waited exactly the hard-coded 1.0s delay
        # (literal contract value - never derived from the module constant).
        assert sleep_calls == [1.0] * fail_attempts

    def test_never_ready_still_fails_closed_within_bounded_budget(self) -> None:
        """The readiness policy must stay BOUNDED: a database that never
        becomes ready still fails closed after EXACTLY the pinned contract
        budget - 30 attempts, 29 inter-attempt sleeps of exactly 1.0s - never
        an unbounded retry loop and never a regression down toward the legacy
        3-attempt probe."""
        from . import _phase15_e2a_harness_lifecycle as lifecycle_module

        call_count = [0]
        sleep_calls: list[float] = []

        def never_ready_factory(
            host: str,
            port: int,
            database: str,
            user: str,
            password: str | None = None,
            **kwargs: Any,
        ) -> Any:
            call_count[0] += 1
            raise psycopg.OperationalError("cold boot never completes")

        def noop_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        with patch.object(lifecycle_module, "_attest_target"):
            with patch.object(lifecycle_module, "_apply_migrations_with_connection"):
                result = lifecycle_module._setup_database_impl(
                    "5432",
                    "test_db",
                    "test_user",
                    "test_password",
                    never_ready_factory,
                    sleep_fn=noop_sleep,
                )

        assert result.success is False
        # Exact hard-coded contract: the never-ready database exhausts the
        # budget at exactly 30 attempts with 29 sleeps of exactly 1.0s each.
        assert call_count[0] == 30
        assert sleep_calls == [1.0] * 29
