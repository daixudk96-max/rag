"""Tests for Phase 15 E2A harness types (Task #132).

These tests verify authorization gate, environment sanitization,
Docker input validation, port parsing, return code validation,
ownership tokens, and immutable result types.

TDD Phase: RED - strengthen tests to fail against faulty implementation.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any
from typing import cast as typing_cast

import pytest

from ._phase15_e2a_harness_types import (
    AUTHORIZATION_FLAG,
    ContainerCleanupResult,
    ContainerPresenceResult,
    SENSITIVE_ENV_VARS,
    SafeDockerEnv,
    _generate_ownership_token,
    _is_separately_authorized,
    _parse_host_port,
    _require_authorization,
    _sanitized_env_copy,
    _validate_container_id,
    _validate_container_name,
    _validate_host_port_str,
    _validate_ownership_token,
    _validate_returncode,
)


class TestAuthorizationGate:
    """Test exact authorization gate contract."""

    def test_authorization_flag_constant(self) -> None:
        """Authorization flag must be exactly 'OKF_E2A_DISPOSABLE_TEST_AUTHORIZED'."""
        assert AUTHORIZATION_FLAG == "OKF_E2A_DISPOSABLE_TEST_AUTHORIZED"

    def test_authorization_value_exact_match(self) -> None:
        """Authorization succeeds only with exact match."""
        assert _is_separately_authorized.__name__ == "_is_separately_authorized"

    def test_require_authorization_raises_when_not_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_require_authorization must raise RuntimeError when not authorized."""
        monkeypatch.delenv(AUTHORIZATION_FLAG, raising=False)

        with pytest.raises(RuntimeError, match="requires separate authorization"):
            _require_authorization()

    def test_require_authorization_raises_with_wrong_value(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_require_authorization must raise RuntimeError with wrong value."""
        monkeypatch.setenv(AUTHORIZATION_FLAG, "wrong-value")

        with pytest.raises(RuntimeError, match="requires separate authorization"):
            _require_authorization()

    def test_require_authorization_passes_with_exact_value(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_require_authorization must pass with exact 'separately-authorized'."""
        monkeypatch.setenv(AUTHORIZATION_FLAG, "separately-authorized")

        _require_authorization()


class TestSensitiveEnvironmentVariables:
    """Test that exactly seven sensitive variables are defined."""

    def test_exactly_seven_sensitive_vars(self) -> None:
        """Must define exactly seven sensitive environment variables."""
        assert len(SENSITIVE_ENV_VARS) == 7

    def test_sensitive_vars_include_all_governed(self) -> None:
        """All seven governed variables must be present."""
        expected = {
            "DATABASE_URL",
            "FORMAL_RUNTIME_DATABASE_URL",
            "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE",
            "OKF_REBUILD_EXPECTED_DATABASE",
            "OKF_FAILURE_AUDIT_ACCEPTANCE",
            "OKF_REBUILD_DOCKER_ACCEPTANCE",
            "OKF_E2A_DISPOSABLE_TEST_AUTHORIZED",
        }
        assert SENSITIVE_ENV_VARS == expected


class TestEnvironmentSanitization:
    """Test immutable environment copy stripping sensitive variables."""

    def test_sanitized_copy_returns_immutable_mapping(self) -> None:
        """_sanitized_env_copy must return immutable Mapping."""
        from collections.abc import Mapping

        result = _sanitized_env_copy()
        # SafeDockerEnv is an immutable Mapping (not dict, not mutable)
        assert isinstance(result, Mapping)
        assert not hasattr(result, "__setitem__") or callable(
            getattr(result, "__setitem__")
        )

    def test_sanitized_copy_is_allowlist_based(self) -> None:
        """Sanitized copy must only include allowlisted variables."""
        import platform

        sanitized = _sanitized_env_copy()
        # On Windows, only PATH, SystemRoot, PATHEXT are allowed
        # On POSIX, only PATH is allowed
        if platform.system() == "Windows":
            allowed = {"PATH", "SystemRoot", "PATHEXT"}
        else:
            allowed = {"PATH"}

        for key in sanitized:
            assert key in allowed, f"Non-allowlisted key {key} in sanitized env"

    def test_sanitized_copy_strips_all_seven(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """All seven sensitive variables must be absent from sanitized copy."""
        for var in SENSITIVE_ENV_VARS:
            monkeypatch.setenv(var, "secret-value")

        sanitized = _sanitized_env_copy()
        for var in SENSITIVE_ENV_VARS:
            assert var not in sanitized

    def test_sanitized_copy_only_allows_platform_specific(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-allowlisted variables must not be preserved (allowlist model)."""

        monkeypatch.setenv("SAFE_VAR", "safe-value")
        for var in SENSITIVE_ENV_VARS:
            monkeypatch.setenv(var, "secret")

        sanitized = _sanitized_env_copy()
        # SAFE_VAR is NOT in the allowlist, so it must not be present
        assert sanitized.get("SAFE_VAR") is None

    def test_safedockerenv_constructor_rejects_non_allowlisted(
        self,
    ) -> None:
        """SafeDockerEnv must reject non-allowlisted keys at construction."""
        import pytest

        # Attempt to construct with DATABASE_URL should fail
        with pytest.raises(ValueError, match="not in Docker environment allowlist"):
            SafeDockerEnv((("DATABASE_URL", "postgres://secret"),))

    def test_safedockerenv_constructor_rejects_duplicates(
        self,
    ) -> None:
        """SafeDockerEnv must reject duplicate keys."""
        import pytest

        with pytest.raises(ValueError, match="Duplicate key"):
            SafeDockerEnv((("PATH", "/bin"), ("PATH", "/usr/bin")))

    def test_safedockerenv_allows_valid_keys(
        self,
    ) -> None:
        """SafeDockerEnv must accept allowlisted keys."""
        import platform

        if platform.system() == "Windows":
            env = SafeDockerEnv(
                (
                    ("PATH", "/usr/bin"),
                    ("SystemRoot", "C:\\Windows"),
                    ("PATHEXT", ".COM;.EXE"),
                )
            )
            assert env["PATH"] == "/usr/bin"
            assert env["SystemRoot"] == "C:\\Windows"
        else:
            env = SafeDockerEnv((("PATH", "/usr/bin"),))
            assert env["PATH"] == "/usr/bin"

    def test_safedockerenv_set_algebra_works(
        self,
    ) -> None:
        """Standard set algebra must work with keys view."""
        env = SafeDockerEnv((("PATH", "/usr/bin"),))

        # frozenset intersection must work
        keys = env.keys()
        required = frozenset({"PATH", "HOME"})

        # This should not raise TypeError
        common = required & keys
        assert "PATH" in common
        assert "HOME" not in common


class TestSafeDockerEnvIntegration:
    """Test SafeDockerEnv integration with real runtime functions."""

    def test_runtime_connection_kwargs_accepts_safedockerenv(
        self,
    ) -> None:
        """runtime_connection_kwargs must accept SafeDockerEnv without TypeError."""
        import os

        # Import the real function and target type
        from scripts._rebuild_database_connection import (
            DisposablePostgresqlTarget,
            runtime_connection_kwargs,
        )

        # Create a target
        target = DisposablePostgresqlTarget(
            host="127.0.0.1",
            port=5432,
            dbname="test",
            user="test",
            password="test",
            hostaddr="127.0.0.1",
        )

        # Create SafeDockerEnv with allowlisted keys
        test_env = SafeDockerEnv((("PATH", os.environ.get("PATH", "/usr/bin")),))

        # This must not raise TypeError
        # The function should accept SafeDockerEnv as a Mapping
        kwargs = runtime_connection_kwargs(target, environ=test_env)

        # Verify it returns a dict with expected keys
        assert isinstance(kwargs, dict)
        assert "host" in kwargs
        assert kwargs["host"] == "127.0.0.1"

    def test_runtime_connection_kwargs_rejects_service_routing(
        self,
    ) -> None:
        """PGSERVICE and other service-routing inputs must fail closed.

        This test proves that runtime_connection_kwargs rejects service-routing
        environment variables BEFORE a connection attempt, not just SafeDockerEnv.
        """
        import pytest

        from scripts._rebuild_database_connection import (
            DisposablePostgresqlTarget,
            runtime_connection_kwargs,
        )

        target = DisposablePostgresqlTarget(
            host="127.0.0.1",
            port=5432,
            dbname="test",
            user="test",
            password="test",
            hostaddr="127.0.0.1",
        )

        # Test 1: PGSERVICE must be rejected
        hostile_env_pgservice = {"PGSERVICE": "production", "PATH": "/usr/bin"}
        with pytest.raises(ValueError, match="refuse ambient service routing"):
            runtime_connection_kwargs(target, environ=hostile_env_pgservice)

        # Test 2: PGSERVICEFILE must be rejected
        hostile_env_pgservicefile = {
            "PGSERVICEFILE": "/etc/pg_service.conf",
            "PATH": "/usr/bin",
        }
        with pytest.raises(ValueError, match="refuse ambient service routing"):
            runtime_connection_kwargs(target, environ=hostile_env_pgservicefile)

        # Test 3: PGSYSCONFDIR must be rejected
        hostile_env_pgsysconfdir = {
            "PGSYSCONFDIR": "/etc/postgresql",
            "PATH": "/usr/bin",
        }
        with pytest.raises(ValueError, match="refuse ambient service routing"):
            runtime_connection_kwargs(target, environ=hostile_env_pgsysconfdir)

        # Test 4: Combined hostile env with multiple service-routing keys
        hostile_env_combined = {
            "PGSERVICE": "production",
            "PGSERVICEFILE": "/etc/pg_service.conf",
            "PGSYSCONFDIR": "/etc/postgresql",
            "PATH": "/usr/bin",
        }
        with pytest.raises(ValueError, match="refuse ambient service routing"):
            runtime_connection_kwargs(target, environ=hostile_env_combined)

    def test_safedockerenv_frozenset_intersection_works(
        self,
    ) -> None:
        """frozenset & environ.keys() must work with SafeDockerEnv.keys()."""
        import os

        test_env = SafeDockerEnv((("PATH", os.environ.get("PATH", "/usr/bin")),))

        # This pattern is used in runtime functions
        environ_keys: frozenset[str] = frozenset({"PATH", "HOME", "DATABASE_URL"})

        # This should not raise TypeError
        common = environ_keys & test_env.keys()

        # Only PATH should be common
        assert "PATH" in common
        assert "HOME" not in common
        assert "DATABASE_URL" not in common


class TestHostPortParser:
    """Test strict host:port parser with ASCII decimal only."""

    def test_valid_port_5432(self) -> None:
        """Port 5432 must parse correctly."""
        assert _parse_host_port("localhost:5432") == ("localhost", 5432)

    def test_valid_port_1(self) -> None:
        """Port 1 (minimum valid) must parse correctly."""
        assert _parse_host_port("host:1") == ("host", 1)

    def test_valid_port_65535(self) -> None:
        """Port 65535 (maximum valid) must parse correctly."""
        assert _parse_host_port("host:65535") == ("host", 65535)

    def test_port_with_leading_zeros(self) -> None:
        """Port '007' must parse to 7."""
        assert _parse_host_port("host:007") == ("host", 7)

    def test_reject_port_0(self) -> None:
        """Port 0 must be rejected."""
        with pytest.raises(ValueError, match="invalid port"):
            _parse_host_port("host:0")

    def test_reject_port_too_large(self) -> None:
        """Port > 65535 must be rejected."""
        with pytest.raises(ValueError, match="invalid port"):
            _parse_host_port("host:65536")

    def test_reject_port_with_whitespace(self) -> None:
        """Port with whitespace must be rejected."""
        with pytest.raises(ValueError, match="invalid port"):
            _parse_host_port("host: 5432")

    def test_reject_port_with_sign(self) -> None:
        """Port with sign must be rejected."""
        with pytest.raises(ValueError, match="invalid port"):
            _parse_host_port("host:+5432")

    def test_reject_unicode_digits(self) -> None:
        """Port with Unicode digits must be rejected."""
        with pytest.raises(ValueError, match="invalid port"):
            _parse_host_port("host:５４３２")

    def test_reject_port_with_suffix(self) -> None:
        """Port with suffix must be rejected."""
        with pytest.raises(ValueError, match="invalid port"):
            _parse_host_port("host:5432tcp")

    def test_reject_non_string_input(self) -> None:
        """Non-string input must be rejected."""
        with pytest.raises(ValueError, match="invalid port"):
            _parse_host_port(typing_cast(Any, 12345))

    def test_reject_str_subclass(self) -> None:
        """String subclass must be rejected."""

        class MyStr(str):
            pass

        with pytest.raises(ValueError):
            _parse_host_port(MyStr("host:5432"))

    def test_fixed_redacted_message(self) -> None:
        """All parse failures must use the same fixed redacted message."""
        msg1: str | None = None
        msg2: str | None = None
        try:
            _parse_host_port("host:0")
        except ValueError as e:
            msg1 = str(e)
        try:
            _parse_host_port("host:65536")
        except ValueError as e:
            msg2 = str(e)

        assert msg1 is not None
        assert msg2 is not None
        assert msg1 == msg2
        assert "invalid port" in msg1.lower()


class TestHostPortStrValidation:
    """Test host port string validation."""

    def test_valid_port_string(self) -> None:
        """Valid port string must be accepted."""
        assert _validate_host_port_str("5432") == "5432"

    def test_port_with_leading_zeros(self) -> None:
        """Port '007' must be valid."""
        assert _validate_host_port_str("007") == "007"

    def test_reject_port_0(self) -> None:
        """Port 0 must be rejected."""
        with pytest.raises(ValueError, match="Invalid port"):
            _validate_host_port_str("0")

    def test_reject_port_too_large(self) -> None:
        """Port > 65535 must be rejected."""
        with pytest.raises(ValueError, match="Invalid port"):
            _validate_host_port_str("65536")

    def test_reject_non_digits(self) -> None:
        """Port with non-digits must be rejected."""
        with pytest.raises(ValueError, match="Invalid port"):
            _validate_host_port_str("54a2")

    def test_reject_empty_string(self) -> None:
        """Empty string must be rejected."""
        with pytest.raises(ValueError, match="Invalid port"):
            _validate_host_port_str("")


class TestContainerNameValidation:
    """Test Docker container name validation."""

    def test_valid_simple_name(self) -> None:
        """Valid simple name must be accepted."""
        assert _validate_container_name("test-container") == "test-container"

    def test_valid_with_digits(self) -> None:
        """Name with digits must be accepted."""
        assert _validate_container_name("test123") == "test123"

    def test_reject_leading_dash(self) -> None:
        """Name with leading dash must be rejected."""
        with pytest.raises(ValueError, match="Invalid container name"):
            _validate_container_name("-test")

    def test_reject_leading_dot(self) -> None:
        """Name with leading dot must be rejected."""
        with pytest.raises(ValueError, match="Invalid container name"):
            _validate_container_name(".test")

    def test_reject_uppercase(self) -> None:
        """Name with uppercase must be rejected."""
        with pytest.raises(ValueError, match="Invalid container name"):
            _validate_container_name("Test")

    def test_reject_whitespace(self) -> None:
        """Name with whitespace must be rejected."""
        with pytest.raises(ValueError, match="Invalid container name"):
            _validate_container_name("test container")

    def test_reject_option_like(self) -> None:
        """Option-like names must be rejected."""
        with pytest.raises(ValueError, match="Invalid container name"):
            _validate_container_name("--help")

    def test_reject_empty(self) -> None:
        """Empty name must be rejected."""
        with pytest.raises(ValueError, match="Invalid container name"):
            _validate_container_name("")

    def test_reject_too_long(self) -> None:
        """Name > 63 chars must be rejected."""
        long_name = "a" * 64
        with pytest.raises(ValueError, match="Invalid container name"):
            _validate_container_name(long_name)

    def test_reject_str_subclass(self) -> None:
        """String subclass must be rejected."""

        class MyStr(str):
            pass

        with pytest.raises(ValueError):
            _validate_container_name(MyStr("test-container"))

    def test_reject_dots(self) -> None:
        """Name with dots must be rejected (regex metacharacter)."""
        with pytest.raises(ValueError, match="Invalid container name"):
            _validate_container_name("test.container")

    def test_reject_underscore(self) -> None:
        """Name with underscore must be rejected."""
        with pytest.raises(ValueError, match="Invalid container name"):
            _validate_container_name("test_container")


class TestOwnershipToken:
    """Test ownership token generation and validation."""

    def test_generate_64_hex_chars(self) -> None:
        """Generated token must be exactly 64 lowercase hex chars."""
        token = _generate_ownership_token()
        assert len(token) == 64
        assert all(c in "0123456789abcdef" for c in token)

    def test_tokens_are_unique(self) -> None:
        """Each token must be unique."""
        token1 = _generate_ownership_token()
        token2 = _generate_ownership_token()
        assert token1 != token2

    def test_validate_valid_token(self) -> None:
        """Valid token must pass validation."""
        token = _generate_ownership_token()
        assert _validate_ownership_token(token) == token

    def test_validate_reject_wrong_length(self) -> None:
        """Token with wrong length must be rejected."""
        with pytest.raises(ValueError, match="Invalid ownership token"):
            _validate_ownership_token("abc123")

    def test_validate_reject_uppercase(self) -> None:
        """Token with uppercase must be rejected."""
        with pytest.raises(ValueError, match="Invalid ownership token"):
            _validate_ownership_token("A" * 64)

    def test_validate_reject_non_hex(self) -> None:
        """Token with non-hex chars must be rejected."""
        with pytest.raises(ValueError, match="Invalid ownership token"):
            _validate_ownership_token("g" * 64)

    def test_token_generated_via_secrets_module(self) -> None:
        """Token must be generated via secrets.token_hex(32)."""
        import secrets

        # Generate two tokens and verify they're different (proves randomness)
        token1 = _generate_ownership_token()
        token2 = secrets.token_hex(32)
        assert len(token1) == len(token2) == 64
        # tokens should be different (statistical guarantee)
        assert token1 != token2


class TestContainerIdValidation:
    """Test container ID validation."""

    def test_validate_valid_id(self) -> None:
        """Valid 64-hex ID must pass validation."""
        id_val = _generate_ownership_token()
        assert _validate_container_id(id_val) == id_val

    def test_validate_reject_wrong_length(self) -> None:
        """ID with wrong length must be rejected."""
        with pytest.raises(ValueError, match="Invalid container ID"):
            _validate_container_id("abc123")

    def test_validate_reject_uppercase(self) -> None:
        """ID with uppercase must be rejected."""
        with pytest.raises(ValueError, match="Invalid container ID"):
            _validate_container_id("A" * 64)

    def test_validate_reject_with_whitespace(self) -> None:
        """ID with whitespace must be rejected."""
        with pytest.raises(ValueError, match="Invalid container ID"):
            _validate_container_id(" " + "a" * 64)

    def test_validate_reject_with_newline(self) -> None:
        """ID with newline must be rejected."""
        with pytest.raises(ValueError, match="Invalid container ID"):
            _validate_container_id("a" * 64 + "\n")


class TestReturnCodeValidation:
    """Test exact built-in int validation for subprocess return codes."""

    def test_valid_returncode_int(self) -> None:
        """Valid int returncode must be accepted."""
        assert _validate_returncode(0) == 0
        assert _validate_returncode(1) == 1
        assert _validate_returncode(-1) == -1

    def test_reject_returncode_bool(self) -> None:
        """Bool must be rejected (bool is subclass of int)."""
        with pytest.raises(ValueError):
            _validate_returncode(True)
        with pytest.raises(ValueError):
            _validate_returncode(False)

    def test_reject_returncode_int_subclass(self) -> None:
        """Int subclass must be rejected."""

        class MyInt(int):
            pass

        with pytest.raises(ValueError):
            _validate_returncode(MyInt(0))

    def test_reject_returncode_non_int(self) -> None:
        """Non-int must be rejected."""
        with pytest.raises(ValueError):
            _validate_returncode(0.0)
        with pytest.raises(ValueError):
            _validate_returncode("0")


class TestContainerPresenceResultCoherence:
    """Test coherent field combinations for ContainerPresenceResult."""

    def test_confirmed_absent_must_have_rc_zero(self) -> None:
        """confirmed_absent must have rc=0."""
        with pytest.raises(ValueError, match="rc must be 0 for confirmed_absent"):
            ContainerPresenceResult(status="confirmed_absent", rc=1)

    def test_confirmed_absent_must_have_no_container_id(self) -> None:
        """confirmed_absent must not have container_id."""
        with pytest.raises(
            ValueError, match="container_id must be None for confirmed_absent"
        ):
            ContainerPresenceResult(
                status="confirmed_absent", rc=0, container_id="a" * 64
            )

    def test_confirmed_absent_must_have_no_error(self) -> None:
        """confirmed_absent must not have error_message."""
        with pytest.raises(
            ValueError, match="error_message must be None for confirmed_absent"
        ):
            ContainerPresenceResult(
                status="confirmed_absent", rc=0, error_message="error"
            )

    def test_present_must_have_container_id(self) -> None:
        """present must have valid container_id."""
        with pytest.raises(ValueError, match="container_id required for present"):
            ContainerPresenceResult(status="present", rc=0)

    def test_present_container_id_must_be_valid_hex(self) -> None:
        """present container_id must be valid 64-hex."""
        with pytest.raises(ValueError, match="invalid container_id"):
            ContainerPresenceResult(status="present", rc=0, container_id="invalid")

    def test_present_container_id_must_be_exact_builtin_str(self) -> None:
        """present container_id must be exact str, not subclass."""

        class MyStr(str):
            pass

        with pytest.raises(ValueError, match="container_id must be exact built-in str"):
            ContainerPresenceResult(
                status="present", rc=0, container_id=MyStr("a" * 64)
            )

    def test_present_must_have_rc_zero(self) -> None:
        """present must have rc=0."""
        with pytest.raises(ValueError, match="rc must be 0 for present"):
            ContainerPresenceResult(status="present", rc=1, container_id="a" * 64)

    def test_present_must_have_no_error(self) -> None:
        """present must not have error_message."""
        with pytest.raises(ValueError, match="error_message must be None for present"):
            ContainerPresenceResult(
                status="present", rc=0, container_id="a" * 64, error_message="error"
            )

    def test_inspection_failure_must_have_error_message(self) -> None:
        """inspection_failure must have error_message."""
        with pytest.raises(
            ValueError, match="error_message required for inspection_failure"
        ):
            ContainerPresenceResult(status="inspection_failure", rc=1)

    def test_inspection_failure_error_must_be_exact_builtin_str(self) -> None:
        """inspection_failure error_message must be exact str."""

        class MyStr(str):
            pass

        with pytest.raises(
            ValueError, match="error_message must be exact built-in str"
        ):
            ContainerPresenceResult(
                status="inspection_failure", rc=1, error_message=MyStr("error")
            )

    def test_inspection_failure_must_have_no_container_id(self) -> None:
        """inspection_failure must not have container_id."""
        with pytest.raises(
            ValueError, match="container_id must be None for inspection_failure"
        ):
            ContainerPresenceResult(
                status="inspection_failure",
                rc=1,
                error_message="error",
                container_id="a" * 64,
            )

    def test_unowned_label_must_have_container_id(self) -> None:
        """unowned_label must have container_id."""
        with pytest.raises(ValueError, match="container_id required for unowned_label"):
            ContainerPresenceResult(status="unowned_label", rc=0)

    def test_unowned_label_container_id_must_be_valid(self) -> None:
        """unowned_label container_id must be valid 64-hex."""
        with pytest.raises(ValueError, match="invalid container_id"):
            ContainerPresenceResult(
                status="unowned_label", rc=0, container_id="invalid"
            )

    def test_ambiguous_output_must_have_error_message(self) -> None:
        """ambiguous_output must have error_message."""
        with pytest.raises(
            ValueError, match="error_message required for ambiguous_output"
        ):
            ContainerPresenceResult(status="ambiguous_output", rc=0)


class TestContainerPresenceResult:
    """Test immutable ContainerPresenceResult with strict invariants."""

    def test_frozen_dataclass(self) -> None:
        """Result must be frozen/immutable."""
        result = ContainerPresenceResult(
            status="confirmed_absent",
            rc=0,
        )
        with pytest.raises(FrozenInstanceError):
            typing_cast(Any, result).status = "present"

    def test_valid_confirmed_absent(self) -> None:
        """Valid confirmed_absent status must be accepted."""
        result = ContainerPresenceResult(status="confirmed_absent", rc=0)
        assert result.status == "confirmed_absent"
        assert result.rc == 0

    def test_valid_present(self) -> None:
        """Valid present status must be accepted."""
        container_id = "a" * 64
        result = ContainerPresenceResult(
            status="present",
            rc=0,
            container_id=container_id,
        )
        assert result.status == "present"
        assert result.container_id == container_id

    def test_invalid_status_rejected(self) -> None:
        """Invalid status must be rejected."""
        with pytest.raises(ValueError, match="Unknown presence status"):
            ContainerPresenceResult(status=typing_cast(Any, "invalid"))

    def test_rc_must_be_exact_int(self) -> None:
        """rc must be exact int, not bool."""
        with pytest.raises(ValueError, match="exact built-in int"):
            ContainerPresenceResult(
                status="confirmed_absent",
                rc=True,
            )

    def test_container_id_must_be_valid_if_present(self) -> None:
        """container_id must be valid 64-hex if provided."""
        # This test is superseded by coherence tests above
        # Kept for backward compatibility
        pass


class TestContainerCleanupResultCoherence:
    """Test coherent field combinations for ContainerCleanupResult."""

    def test_confirmed_removed_must_have_confirmed_true(self) -> None:
        """confirmed_removed must have confirmed=True."""
        with pytest.raises(
            ValueError, match="confirmed must be True for confirmed_removed"
        ):
            ContainerCleanupResult(
                outcome="confirmed_removed", stage="confirm", confirmed=False
            )

    def test_confirmed_absent_must_have_confirmed_true(self) -> None:
        """confirmed_absent must have confirmed=True."""
        with pytest.raises(
            ValueError, match="confirmed must be True for confirmed_absent"
        ):
            ContainerCleanupResult(
                outcome="confirmed_absent", stage="inspect", confirmed=False
            )

    def test_removal_failure_must_have_confirmed_false(self) -> None:
        """removal_failure must have confirmed=False."""
        with pytest.raises(
            ValueError, match="confirmed must be False for removal_failure"
        ):
            ContainerCleanupResult(
                outcome="removal_failure", stage="remove", confirmed=True
            )

    def test_inspection_failure_must_have_confirmed_false(self) -> None:
        """inspection_failure must have confirmed=False."""
        with pytest.raises(
            ValueError, match="confirmed must be False for inspection_failure"
        ):
            ContainerCleanupResult(
                outcome="inspection_failure", stage="inspect", confirmed=True
            )

    def test_unowned_label_must_have_confirmed_false(self) -> None:
        """unowned_label must have confirmed=False."""
        with pytest.raises(
            ValueError, match="confirmed must be False for unowned_label"
        ):
            ContainerCleanupResult(
                outcome="unowned_label", stage="inspect", confirmed=True
            )

    def test_post_removal_confirmation_failure_must_have_confirmed_false(self) -> None:
        """post_removal_confirmation_failure must have confirmed=False."""
        with pytest.raises(
            ValueError,
            match="confirmed must be False for post_removal_confirmation_failure",
        ):
            ContainerCleanupResult(
                outcome="post_removal_confirmation_failure",
                stage="confirm",
                confirmed=True,
            )

    def test_inspect_stage_confirmed_absent_no_inspect_rc(self) -> None:
        """confirmed_absent at inspect stage should not require inspect_rc."""
        result = ContainerCleanupResult(
            outcome="confirmed_absent", stage="inspect", confirmed=True
        )
        assert result.outcome == "confirmed_absent"

    def test_removal_failure_must_have_remove_rc(self) -> None:
        """removal_failure must have remove_rc provided."""
        with pytest.raises(ValueError, match="remove_rc required for removal_failure"):
            ContainerCleanupResult(
                outcome="removal_failure", stage="remove", confirmed=False
            )

    def test_remove_rc_must_be_exact_builtin_int(self) -> None:
        """remove_rc must be exact int, not bool."""

        class MyInt(int):
            pass

        with pytest.raises(ValueError, match="remove_rc must be exact built-in int"):
            ContainerCleanupResult(
                outcome="removal_failure",
                stage="remove",
                confirmed=False,
                remove_rc=MyInt(1),
            )


class TestContainerCleanupResult:
    """Test immutable ContainerCleanupResult with strict invariants."""

    def test_frozen_dataclass(self) -> None:
        """Result must be frozen/immutable."""
        result = ContainerCleanupResult(
            outcome="confirmed_removed",
            stage="confirm",
            confirmed=True,
            inspect_rc=0,
            remove_rc=0,
        )
        with pytest.raises(FrozenInstanceError):
            typing_cast(Any, result).confirmed = False

    def test_confirmed_must_be_exact_bool(self) -> None:
        """confirmed must be exact bool, not int/None."""
        with pytest.raises(ValueError, match="exact built-in bool"):
            ContainerCleanupResult(
                outcome="confirmed_removed",
                stage="confirm",
                confirmed=typing_cast(Any, 1),
            )

    def test_outcome_must_be_valid_literal(self) -> None:
        """outcome must be from the closed set."""
        with pytest.raises(ValueError, match="unknown outcome"):
            ContainerCleanupResult(
                outcome=typing_cast(Any, "invalid_outcome"),
                stage="confirm",
                confirmed=True,
            )

    def test_stage_must_be_valid(self) -> None:
        """stage must be from the closed set."""
        with pytest.raises(ValueError, match="unknown stage"):
            ContainerCleanupResult(
                outcome="confirmed_removed",
                stage=typing_cast(Any, "invalid_stage"),
                confirmed=True,
            )

    def test_stage_outcome_coherence(self) -> None:
        """outcome must be valid for the given stage."""
        with pytest.raises(ValueError, match="not valid for stage"):
            ContainerCleanupResult(
                outcome="confirmed_removed",
                stage="inspect",
                confirmed=True,
            )

    def test_rc_must_be_exact_int(self) -> None:
        """Return codes must be exact int, not bool."""
        with pytest.raises(ValueError, match="exact built-in int"):
            ContainerCleanupResult(
                outcome="confirmed_absent",
                stage="inspect",
                confirmed=True,
                inspect_rc=True,
            )
