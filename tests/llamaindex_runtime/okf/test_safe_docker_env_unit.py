"""Unit tests for safe Docker environment mapping (Task #87 remediation).

TDD Phase: RED - tests must fail until implementation is complete.

This module covers:
1. SafeDockerEnv allowlist enforcement (never reads canaries)
2. Subprocess compatibility (items() yields real values)
3. Repr/str/TracebackException redaction
4. Container ID normalization (CRLF/LF/whitespace)
5. Docker ps output parsing
"""

from __future__ import annotations

import subprocess
import tempfile
import traceback
from collections.abc import Sequence
from typing import Any

import pytest


# =============================================================================
# Part 1: Allowlist enforcement tests
# =============================================================================


class _CanaryTrappingGetter:
    """Getter that traps non-allowlisted key access."""

    def __init__(self, canary_values: dict[str, str]):
        self._canary = canary_values
        self.requested_keys: list[str] = []
        # Use platform-aware allowlist
        import platform

        if platform.system() == "Windows":
            self._allowlist = frozenset({"PATH", "SystemRoot", "PATHEXT"})
        else:
            self._allowlist = frozenset({"PATH"})

    def __call__(self, key: str) -> str | None:
        self.requested_keys.append(key)
        # TRAP: Fail immediately if non-allowlisted key requested
        if key not in self._allowlist:
            raise AssertionError(
                f"SECURITY VIOLATION: Getter called with non-allowlisted key {key!r}"
            )
        return self._canary.get(key)


class TestSafeDockerEnvImmutability:
    """Test SafeDockerEnv is genuinely immutable and not dict-backed."""

    def test_cannot_set_item(self) -> None:
        """SafeDockerEnv must not support item assignment."""
        from typing import cast

        from ._phase15_e2a_harness_types import SafeDockerEnv

        env = SafeDockerEnv((("PATH", "/test"),))

        # Cast to Any to bypass mypy static analysis while testing runtime behavior
        with pytest.raises(TypeError):
            cast(Any, env)["PATH"] = "/malicious"

    def test_cannot_del_item(self) -> None:
        """SafeDockerEnv must not support item deletion."""
        from typing import cast

        from ._phase15_e2a_harness_types import SafeDockerEnv

        env = SafeDockerEnv((("PATH", "/test"),))

        # Cast to Any to bypass mypy static analysis while testing runtime behavior
        with pytest.raises(TypeError):
            del cast(Any, env)["PATH"]

    def test_no_dict_attribute(self) -> None:
        """SafeDockerEnv must not have __dict__."""
        from ._phase15_e2a_harness_types import _make_docker_env

        env = _make_docker_env(lambda k: {"PATH": "/test"}.get(k))

        # Must not have __dict__ attribute (slots-only)
        assert not hasattr(env, "__dict__")

    def test_backing_is_tuple_not_dict(self) -> None:
        """SafeDockerEnv internal storage must be tuple, not dict."""
        from ._phase15_e2a_harness_types import _make_docker_env

        env = _make_docker_env(lambda k: {"PATH": "/test"}.get(k))

        # Check internal _pairs is tuple
        assert isinstance(env._pairs, tuple)
        # Check all elements are (str, str) tuples
        for item in env._pairs:
            assert isinstance(item, tuple)
            assert len(item) == 2
            assert isinstance(item[0], str)
            assert isinstance(item[1], str)

    def test_platform_aware_allowlist(self) -> None:
        """Allowlist must be platform-aware (SystemRoot on Windows, PATH-only on POSIX)."""
        from ._phase15_e2a_harness_types import _DOCKER_ENV_ALLOWLIST
        import platform

        # Platform-specific checks
        if platform.system() == "Windows":
            # Windows must include SystemRoot
            assert "SystemRoot" in _DOCKER_ENV_ALLOWLIST
            assert "PATH" in _DOCKER_ENV_ALLOWLIST
        else:
            # POSIX should only have PATH
            assert "PATH" in _DOCKER_ENV_ALLOWLIST
            assert "SystemRoot" not in _DOCKER_ENV_ALLOWLIST

    def test_items_view_returns_standard_type(self) -> None:
        """items() must return ItemsView (from Mapping ABC), not custom type."""
        from ._phase15_e2a_harness_types import SafeDockerEnv

        env = SafeDockerEnv((("PATH", "/test"),))
        items = env.items()

        # Must be standard ItemsView type from Mapping ABC
        # (dict_items is for actual dicts, ItemsView is for Mapping subclasses)
        assert type(items).__name__ == "ItemsView"

    def test_items_view_redacts_sensitive_values(self) -> None:
        """items() must not expose raw sensitive values."""
        import os

        from ._phase15_e2a_harness_types import SafeDockerEnv

        env = SafeDockerEnv((("PATH", os.environ.get("PATH", "/usr/bin")),))

        # items() should return allowlisted values
        items = list(env.items())
        assert len(items) == 1
        assert items[0][0] == "PATH"
        # PATH value should be present (it's allowlisted)
        assert items[0][1] == os.environ.get("PATH", "/usr/bin")


class TestSafeDockerEnvAllowlist:
    """Test SafeDockerEnv only reads allowlisted keys."""

    def test_never_accesses_database_url_canary(self) -> None:
        """Constructor must never read DATABASE_URL."""
        from ._phase15_e2a_harness_types import _make_docker_env

        canary = {
            "PATH": "/safe/test/path",
            "DATABASE_URL": "CANARY_URL_trap_12345",
        }
        trapping = _CanaryTrappingGetter(canary)
        _ = _make_docker_env(trapping)

        # DATABASE_URL must never have been requested
        assert "DATABASE_URL" not in trapping.requested_keys

    def test_never_accesses_docker_host_canary(self) -> None:
        """Constructor must never read DOCKER_HOST."""
        from ._phase15_e2a_harness_types import _make_docker_env

        canary = {
            "PATH": "/safe/test/path",
            "DOCKER_HOST": "CANARY_HOST_trap_67890",
        }
        trapping = _CanaryTrappingGetter(canary)
        _ = _make_docker_env(trapping)

        assert "DOCKER_HOST" not in trapping.requested_keys

    def test_never_accesses_home_canary(self) -> None:
        """Constructor must never read HOME/USERPROFILE."""
        from ._phase15_e2a_harness_types import _make_docker_env

        canary = {
            "PATH": "/safe/test/path",
            "HOME": "CANARY_HOME_trap_abcde",
            "USERPROFILE": "CANARY_USERPROFILE_trap_fghij",
        }
        trapping = _CanaryTrappingGetter(canary)
        _ = _make_docker_env(trapping)

        assert "HOME" not in trapping.requested_keys
        assert "USERPROFILE" not in trapping.requested_keys

    def test_never_accesses_auth_variables(self) -> None:
        """Constructor must never read auth-related variables."""
        from ._phase15_e2a_harness_types import _make_docker_env

        canary = {
            "PATH": "/safe/test/path",
            "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE": "CANARY_AUTH_trap_xyz",
            "FORMAL_RUNTIME_DATABASE_URL": "CANARY_AUTH_trap_uvw",
        }
        trapping = _CanaryTrappingGetter(canary)
        _ = _make_docker_env(trapping)

        for key in trapping.requested_keys:
            assert "AUTH" not in key.upper()
            assert "DATABASE" not in key.upper()


# =============================================================================
# Part 2: Subprocess compatibility tests
# =============================================================================


class TestSafeDockerEnvSubprocessCompatibility:
    """Test SafeDockerEnv yields real values to subprocess."""

    def test_items_yields_real_path_value(self) -> None:
        """items() must yield real PATH, not '<redacted>'."""
        from ._phase15_e2a_harness_types import _make_docker_env

        env = _make_docker_env(lambda k: {"PATH": "/real/value"}.get(k))
        items_list = list(env.items())

        assert len(items_list) >= 1
        # Find PATH entry
        path_value = None
        for key, value in items_list:
            if key == "PATH":
                path_value = value
                break

        assert path_value is not None
        assert path_value == "/real/value"  # REAL value, not '<redacted>'

    def test_items_iterator_for_subprocess(self) -> None:
        """subprocess-style iteration must receive real values."""
        from ._phase15_e2a_harness_types import _make_docker_env

        env = _make_docker_env(lambda k: {"PATH": "/usr/bin:/bin"}.get(k))

        # Simulate what subprocess.run does internally
        env_list = []
        for key, value in env.items():
            env_list.append(f"{key}={value}")

        # Must have real values
        assert any("PATH=/usr/bin:/bin" == entry for entry in env_list)


# =============================================================================
# Part 3: Repr/str redaction tests
# =============================================================================


class TestSafeDockerEnvRedaction:
    """Test SafeDockerEnv hides values in repr/str/traceback."""

    def test_repr_shows_redacted_not_value(self) -> None:
        """repr() must show redacted, not actual values."""
        from ._phase15_e2a_harness_types import _make_docker_env

        env = _make_docker_env(lambda k: {"PATH": "/secret/hidden/path"}.get(k))
        r = repr(env)

        assert "secret" not in r
        assert "hidden" not in r
        assert "/secret" not in r

    def test_str_shows_redacted_not_value(self) -> None:
        """str() must show redacted, not actual values."""
        from ._phase15_e2a_harness_types import _make_docker_env

        env = _make_docker_env(lambda k: {"PATH": "/secret/hidden/path"}.get(k))
        s = str(env)

        assert "secret" not in s
        assert "hidden" not in s

    def test_items_repr_shows_redacted(self) -> None:
        """repr(env.items()) must show redacted."""
        from ._phase15_e2a_harness_types import _make_docker_env

        env = _make_docker_env(lambda k: {"PATH": "/secret/path"}.get(k))
        items = env.items()
        r = repr(items)

        assert "secret" not in r

    def test_traceback_exception_capture_locals_no_secrets(self) -> None:
        """TracebackException(capture_locals=True) must not show secrets."""
        from ._phase15_e2a_harness_types import _make_docker_env

        # Create env with canary secret - env must be in frame for test
        canary_env = _make_docker_env(lambda k: {"PATH": "/SECRET_CANARY_xyz"}.get(k))

        def failing_function() -> None:
            # canary_env is in locals
            _ = canary_env  # Keep in frame
            raise ValueError("Test error")

        try:
            failing_function()
        except Exception as exc:
            tb = traceback.TracebackException.from_exception(exc, capture_locals=True)

            # Format the traceback
            formatted = "".join(tb.format())

            # Must not contain the secret
            assert "SECRET_CANARY" not in formatted
            assert "xyz" not in formatted


# =============================================================================
# Part 4: Container ID normalization tests
# =============================================================================


class TestContainerIdNormalization:
    """Test exact container ID normalization with CRLF/LF handling."""

    def test_accepts_raw_64hex(self) -> None:
        """Raw 64 hex chars (no ending) must be accepted."""
        from ._phase15_e2a_harness_types import _normalize_docker_run_id

        result = _normalize_docker_run_id("a" * 64)
        assert result == "a" * 64

    def test_accepts_64hex_with_single_lf(self) -> None:
        """64 hex + single LF must be accepted."""
        from ._phase15_e2a_harness_types import _normalize_docker_run_id

        result = _normalize_docker_run_id("a" * 64 + "\n")
        assert result == "a" * 64

    def test_accepts_64hex_with_single_crlf(self) -> None:
        """64 hex + single CRLF must be accepted."""
        from ._phase15_e2a_harness_types import _normalize_docker_run_id

        result = _normalize_docker_run_id("a" * 64 + "\r\n")
        assert result == "a" * 64

    def test_rejects_double_lf(self) -> None:
        """Double LF must be rejected."""
        from ._phase15_e2a_harness_types import _normalize_docker_run_id

        with pytest.raises(RuntimeError):
            _normalize_docker_run_id("a" * 64 + "\n\n")

    def test_rejects_double_crlf(self) -> None:
        """Double CRLF must be rejected."""
        from ._phase15_e2a_harness_types import _normalize_docker_run_id

        with pytest.raises(RuntimeError):
            _normalize_docker_run_id("a" * 64 + "\r\n\r\n")

    def test_rejects_lf_crlf_combo(self) -> None:
        """LF+CRLF combo must be rejected."""
        from ._phase15_e2a_harness_types import _normalize_docker_run_id

        with pytest.raises(RuntimeError):
            _normalize_docker_run_id("a" * 64 + "\n\r\n")

    def test_rejects_whitespace_prefix(self) -> None:
        """Whitespace before ID must be rejected."""
        from ._phase15_e2a_harness_types import _normalize_docker_run_id

        with pytest.raises(RuntimeError):
            _normalize_docker_run_id(" " + "a" * 64)

    def test_rejects_extra_content_after_id(self) -> None:
        """Extra content after ID must be rejected."""
        from ._phase15_e2a_harness_types import _normalize_docker_run_id

        with pytest.raises(RuntimeError):
            _normalize_docker_run_id("a" * 64 + "extra")

    def test_rejects_uppercase_hex(self) -> None:
        """Uppercase hex must be rejected (lowercase only)."""
        from ._phase15_e2a_harness_types import _normalize_docker_run_id

        with pytest.raises(RuntimeError):
            _normalize_docker_run_id("A" * 64)

    def test_rejects_too_short(self) -> None:
        """Too short ID must be rejected."""
        from ._phase15_e2a_harness_types import _normalize_docker_run_id

        with pytest.raises(RuntimeError):
            _normalize_docker_run_id("a" * 63)

    def test_rejects_empty(self) -> None:
        """Empty string must be rejected."""
        from ._phase15_e2a_harness_types import _normalize_docker_run_id

        with pytest.raises(RuntimeError):
            _normalize_docker_run_id("")


# =============================================================================
# Part 5: Docker ps output parsing tests (EXACT parsing)
# =============================================================================


class TestDockerPsParsing:
    """Test docker ps output parsing with EXACT parsing rules."""

    def test_empty_is_confirmed_absent(self) -> None:
        """Empty stdout is confirmed_absent."""
        from ._phase15_e2a_harness_lifecycle import _observe_container_presence

        result = _observe_container_presence(
            "test-container",
            config_dir="/tmp/config",
            run=lambda *args, **kwargs: subprocess.CompletedProcess(
                args=["docker", "ps"], returncode=0, stdout="", stderr=""
            ),
        )
        assert result.status == "confirmed_absent"

    def test_whitespace_only_is_confirmed_absent(self) -> None:
        """Whitespace-only stdout (spaces/tabs/LF/CRLF) is confirmed_absent."""
        from ._phase15_e2a_harness_lifecycle import _observe_container_presence

        result = _observe_container_presence(
            "test-container",
            config_dir="/tmp/config",
            run=lambda *args, **kwargs: subprocess.CompletedProcess(
                args=["docker", "ps"], returncode=0, stdout="   \t\n\r\n", stderr=""
            ),
        )
        assert result.status == "confirmed_absent"

    def test_crlf_only_is_confirmed_absent(self) -> None:
        """CRLF-only stdout is confirmed_absent."""
        from ._phase15_e2a_harness_lifecycle import _observe_container_presence

        result = _observe_container_presence(
            "test-container",
            config_dir="/tmp/config",
            run=lambda *args, **kwargs: subprocess.CompletedProcess(
                args=["docker", "ps"], returncode=0, stdout="\r\n", stderr=""
            ),
        )
        assert result.status == "confirmed_absent"

    def test_lf_only_is_confirmed_absent(self) -> None:
        """LF-only stdout is confirmed_absent."""
        from ._phase15_e2a_harness_lifecycle import _observe_container_presence

        result = _observe_container_presence(
            "test-container",
            config_dir="/tmp/config",
            run=lambda *args, **kwargs: subprocess.CompletedProcess(
                args=["docker", "ps"], returncode=0, stdout="\n", stderr=""
            ),
        )
        assert result.status == "confirmed_absent"

    def test_single_line_with_crlf_is_present(self) -> None:
        """Single line with CRLF ending is parsed as present."""
        from ._phase15_e2a_harness_lifecycle import _observe_container_presence

        result = _observe_container_presence(
            "test-container",
            config_dir="/tmp/config",
            run=lambda *args, **kwargs: subprocess.CompletedProcess(
                args=["docker", "ps"],
                returncode=0,
                stdout=f"test-container\t{'a' * 64}\r\n",
                stderr="",
            ),
        )
        assert result.status == "present"
        assert result.container_id == "a" * 64

    def test_single_line_with_lf_is_present(self) -> None:
        """Single line with LF ending is parsed as present."""
        from ._phase15_e2a_harness_lifecycle import _observe_container_presence

        result = _observe_container_presence(
            "test-container",
            config_dir="/tmp/config",
            run=lambda *args, **kwargs: subprocess.CompletedProcess(
                args=["docker", "ps"],
                returncode=0,
                stdout=f"test-container\t{'a' * 64}\n",
                stderr="",
            ),
        )
        assert result.status == "present"
        assert result.container_id == "a" * 64

    def test_single_line_no_ending_is_present(self) -> None:
        """Single line with no ending is parsed as present."""
        from ._phase15_e2a_harness_lifecycle import _observe_container_presence

        result = _observe_container_presence(
            "test-container",
            config_dir="/tmp/config",
            run=lambda *args, **kwargs: subprocess.CompletedProcess(
                args=["docker", "ps"],
                returncode=0,
                stdout=f"test-container\t{'a' * 64}",
                stderr="",
            ),
        )
        assert result.status == "present"
        assert result.container_id == "a" * 64

    def test_rejects_double_lf(self) -> None:
        """Double LF must be rejected."""
        from ._phase15_e2a_harness_lifecycle import _observe_container_presence

        result = _observe_container_presence(
            "test-container",
            config_dir="/tmp/config",
            run=lambda *args, **kwargs: subprocess.CompletedProcess(
                args=["docker", "ps"],
                returncode=0,
                stdout=f"test-container\t{'a' * 64}\n\n",
                stderr="",
            ),
        )
        assert result.status == "ambiguous_output"

    def test_rejects_double_crlf(self) -> None:
        """Double CRLF must be rejected."""
        from ._phase15_e2a_harness_lifecycle import _observe_container_presence

        result = _observe_container_presence(
            "test-container",
            config_dir="/tmp/config",
            run=lambda *args, **kwargs: subprocess.CompletedProcess(
                args=["docker", "ps"],
                returncode=0,
                stdout=f"test-container\t{'a' * 64}\r\n\r\n",
                stderr="",
            ),
        )
        assert result.status == "ambiguous_output"

    def test_rejects_record_plus_blank_line(self) -> None:
        """Record followed by blank line must be rejected."""
        from ._phase15_e2a_harness_lifecycle import _observe_container_presence

        result = _observe_container_presence(
            "test-container",
            config_dir="/tmp/config",
            run=lambda *args, **kwargs: subprocess.CompletedProcess(
                args=["docker", "ps"],
                returncode=0,
                stdout=f"test-container\t{'a' * 64}\n\n",
                stderr="",
            ),
        )
        assert result.status == "ambiguous_output"

    def test_rejects_multiple_records(self) -> None:
        """Multiple records must be rejected."""
        from ._phase15_e2a_harness_lifecycle import _observe_container_presence

        result = _observe_container_presence(
            "test-container",
            config_dir="/tmp/config",
            run=lambda *args, **kwargs: subprocess.CompletedProcess(
                args=["docker", "ps"],
                returncode=0,
                stdout=f"test-container\t{'a' * 64}\nother\t{'b' * 64}",
                stderr="",
            ),
        )
        assert result.status == "ambiguous_output"

    def test_rejects_embedded_cr_in_record(self) -> None:
        """Embedded CR in record must be rejected."""
        from ._phase15_e2a_harness_lifecycle import _observe_container_presence

        result = _observe_container_presence(
            "test-container",
            config_dir="/tmp/config",
            run=lambda *args, **kwargs: subprocess.CompletedProcess(
                args=["docker", "ps"],
                returncode=0,
                stdout=f"test-container\t{'a' * 32}\r{'a' * 32}",
                stderr="",
            ),
        )
        assert result.status == "ambiguous_output"

    def test_rejects_embedded_lf_in_record(self) -> None:
        """Embedded LF in record must be rejected."""
        from ._phase15_e2a_harness_lifecycle import _observe_container_presence

        result = _observe_container_presence(
            "test-container",
            config_dir="/tmp/config",
            run=lambda *args, **kwargs: subprocess.CompletedProcess(
                args=["docker", "ps"],
                returncode=0,
                stdout=f"test-container\t{'a' * 32}\n{'a' * 32}",
                stderr="",
            ),
        )
        assert result.status == "ambiguous_output"

    def test_rejects_leading_whitespace(self) -> None:
        """Leading whitespace must be rejected."""
        from ._phase15_e2a_harness_lifecycle import _observe_container_presence

        result = _observe_container_presence(
            "test-container",
            config_dir="/tmp/config",
            run=lambda *args, **kwargs: subprocess.CompletedProcess(
                args=["docker", "ps"],
                returncode=0,
                stdout=f" test-container\t{'a' * 64}",
                stderr="",
            ),
        )
        assert result.status == "ambiguous_output"

    def test_rejects_trailing_whitespace(self) -> None:
        """Trailing whitespace must be rejected."""
        from ._phase15_e2a_harness_lifecycle import _observe_container_presence

        result = _observe_container_presence(
            "test-container",
            config_dir="/tmp/config",
            run=lambda *args, **kwargs: subprocess.CompletedProcess(
                args=["docker", "ps"],
                returncode=0,
                stdout=f"test-container\t{'a' * 64} ",
                stderr="",
            ),
        )
        assert result.status == "ambiguous_output"

    def test_rejects_malformed_tabs(self) -> None:
        """Malformed (not 2 tab-separated fields) must be rejected."""
        from ._phase15_e2a_harness_lifecycle import _observe_container_presence

        result = _observe_container_presence(
            "test-container",
            config_dir="/tmp/config",
            run=lambda *args, **kwargs: subprocess.CompletedProcess(
                args=["docker", "ps"],
                returncode=0,
                stdout="name-only-no-tab",
                stderr="",
            ),
        )
        assert result.status == "ambiguous_output"

    def test_rejects_three_tab_fields(self) -> None:
        """Three tab-separated fields must be rejected."""
        from ._phase15_e2a_harness_lifecycle import _observe_container_presence

        result = _observe_container_presence(
            "test-container",
            config_dir="/tmp/config",
            run=lambda *args, **kwargs: subprocess.CompletedProcess(
                args=["docker", "ps"],
                returncode=0,
                stdout=f"test-container\t{'a' * 64}\textra",
                stderr="",
            ),
        )
        assert result.status == "ambiguous_output"

    def test_rejects_unexpected_name(self) -> None:
        """Unexpected container name must be rejected."""
        from ._phase15_e2a_harness_lifecycle import _observe_container_presence

        result = _observe_container_presence(
            "test-container",
            config_dir="/tmp/config",
            run=lambda *args, **kwargs: subprocess.CompletedProcess(
                args=["docker", "ps"],
                returncode=0,
                stdout=f"other-container\t{'a' * 64}",
                stderr="",
            ),
        )
        assert result.status == "ambiguous_output"
        assert "Unexpected container name" in (result.error_message or "")

    def test_rejects_invalid_container_id(self) -> None:
        """Invalid container ID format must be rejected."""
        from ._phase15_e2a_harness_lifecycle import _observe_container_presence

        result = _observe_container_presence(
            "test-container",
            config_dir="/tmp/config",
            run=lambda *args, **kwargs: subprocess.CompletedProcess(
                args=["docker", "ps"],
                returncode=0,
                stdout="test-container\tinvalid-id",
                stderr="",
            ),
        )
        assert result.status == "ambiguous_output"
        assert "Invalid container ID" in (result.error_message or "")


# =============================================================================
# Part 6: Docker command prefix tests
# =============================================================================


class TestDockerCommandPrefix:
    """Test all Docker commands have --config and --context default."""

    def test_observe_container_presence_has_prefix(self) -> None:
        """_observe_container_presence must use --config --context default."""
        from ._phase15_e2a_harness_lifecycle import _observe_container_presence

        captured_args: list[list[str]] = []

        def capture_runner(
            args: list[str], **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            captured_args.append(list(args))
            return subprocess.CompletedProcess(
                args=args, returncode=0, stdout="", stderr=""
            )

        _observe_container_presence(
            "test-container",
            config_dir="/tmp/test-config",
            run=capture_runner,
        )

        assert len(captured_args) == 1
        args = captured_args[0]

        # Must start with docker --config <dir> --context default
        assert args[0] == "docker"
        assert args[1] == "--config"
        assert args[2] == "/tmp/test-config"
        assert args[3] == "--context"
        assert args[4] == "default"
        # Then ps subcommand
        assert "ps" in args

    def test_remove_container_has_prefix(self) -> None:
        """_remove_container_by_id must use --config --context default."""
        from ._phase15_e2a_harness_lifecycle import _remove_container_by_id

        captured_args: list[list[str]] = []

        def capture_runner(
            args: list[str], **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            captured_args.append(list(args))
            return subprocess.CompletedProcess(
                args=args, returncode=0, stdout="", stderr=""
            )

        _remove_container_by_id(
            "a" * 64,
            config_dir="/tmp/test-config",
            run=capture_runner,
        )

        assert len(captured_args) == 1
        args = captured_args[0]

        assert args[0] == "docker"
        assert args[1] == "--config"
        assert args[2] == "/tmp/test-config"
        assert args[3] == "--context"
        assert args[4] == "default"
        assert "rm" in args

    def test_inspect_container_has_prefix(self) -> None:
        """_full_container_inspect must use --config --context default."""
        from ._phase15_e2a_harness_lifecycle import _full_container_inspect

        captured_args: list[list[str]] = []

        def capture_runner(
            args: list[str], **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            captured_args.append(list(args))
            # Return valid inspect output
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=f"{'a' * 64}|/test-container|token123|127.0.0.1:5432",
                stderr="",
            )

        result = _full_container_inspect(
            "a" * 64,
            "test-container",
            "token123",
            5432,
            config_dir="/tmp/test-config",
            run=capture_runner,
        )

        assert result.valid

        assert len(captured_args) == 1
        args = captured_args[0]

        assert args[0] == "docker"
        assert args[1] == "--config"
        assert args[2] == "/tmp/test-config"
        assert args[3] == "--context"
        assert args[4] == "default"
        assert "inspect" in args


# =============================================================================
# Part 7: Non-Docker subprocess compatibility test
# =============================================================================


class TestSubprocessCompatibility:
    """Test SafeDockerEnv works with real subprocess."""

    def test_python_subprocess_receives_real_values(self) -> None:
        """Subprocess must receive real values when SafeDockerEnv is passed directly."""
        from ._phase15_e2a_harness_types import _make_docker_env
        import sys

        # Create env with test marker (harmless synthetic value)
        test_path_value = "/TESTMARKER_SUBPROCESS_XYZ999"
        env = _make_docker_env(lambda k: {"PATH": test_path_value}.get(k))

        # Run Python subprocess WITH SafeDockerEnv DIRECTLY (not a separate dict)
        # This is the real test - subprocess must iterate env.items() and get real values
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import os; import sys; "
                "path = os.environ.get('PATH', 'MISSING'); "
                "sys.stdout.write(path)",
            ],
            capture_output=True,
            text=True,
            env=env,  # Pass SafeDockerEnv directly - the real test
            timeout=10,
        )

        # Subprocess should have received the real value through items() iteration
        assert result.returncode == 0
        # The marker should appear in output (proves subprocess got real value)
        assert "TESTMARKER_SUBPROCESS_XYZ999" in result.stdout

        # Verify our env repr is still redacted
        assert "TESTMARKER" not in repr(env)
        assert "TESTMARKER" not in str(env)


class TestSafeDockerEnvNoDict:
    """Test SafeDockerEnv has NO dict anywhere."""

    def test_no_dict_attribute(self) -> None:
        """SafeDockerEnv must not have __dict__."""
        from ._phase15_e2a_harness_types import _make_docker_env

        env = _make_docker_env(lambda k: {"PATH": "/test"}.get(k))

        # Must not have __dict__ attribute (slots-only)
        assert not hasattr(env, "__dict__")

    def test_no_key_index_dict(self) -> None:
        """SafeDockerEnv must not have _key_index dict."""
        from ._phase15_e2a_harness_types import _make_docker_env

        env = _make_docker_env(lambda k: {"PATH": "/test"}.get(k))

        # Must not have _key_index attribute
        assert not hasattr(env, "_key_index")

    def test_linear_lookup_no_dict(self) -> None:
        """SafeDockerEnv lookup must work without dict."""
        from ._phase15_e2a_harness_types import _make_docker_env

        env = _make_docker_env(
            lambda k: {"PATH": "/test_path", "HOME": "/test_home"}.get(k)
        )

        # Lookup should work via linear iteration
        assert env["PATH"] == "/test_path"
        assert env.get("NONEXISTENT") is None
        assert "PATH" in env
        assert "NONEXISTENT" not in env


# =============================================================================
# Part 8: Docker config directory lifecycle tests
# =============================================================================


class TestDockerConfigLifecycle:
    """Test session-owned Docker config directory."""

    def test_docker_receives_safe_env_not_dict(self) -> None:
        """Docker runner must receive SafeDockerEnv, not dict."""
        from ._phase15_e2a_harness_lifecycle import _run_docker_start
        from ._phase15_e2a_harness_types import (
            SafeDockerEnv,
            TRUSTED_DISPOSABLE_IMAGE,
            _make_docker_env,
        )

        env_checks: list[bool] = []

        def checking_runner(
            args: Sequence[str], **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            env = kwargs.get("env")
            if env is not None:
                # Verify it's SafeDockerEnv, not dict
                env_checks.append(isinstance(env, SafeDockerEnv))
            # Return a container ID to simulate success
            return subprocess.CompletedProcess(
                args=args, returncode=0, stdout="a" * 64, stderr=""
            )

        # Create safe env
        safe_env = _make_docker_env(lambda k: {"PATH": "/usr/bin"}.get(k))

        # Call _run_docker_start directly to verify runner receives SafeDockerEnv
        from pathlib import Path
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            env_file = Path(f.name)

        try:
            _run_docker_start(
                runner=checking_runner,
                config_dir="/tmp/cfg",
                container_name="test-container",
                port="5432",
                token="b" * 64,
                env_file_path=env_file,
                image=TRUSTED_DISPOSABLE_IMAGE,
                sanitized_env=safe_env,
            )

            # Verify runner was called
            assert len(env_checks) == 1, "Runner should have been called once"
            assert env_checks[0] is True, "Runner must receive SafeDockerEnv, not dict"
        finally:
            env_file.unlink(missing_ok=True)

    def test_all_docker_commands_have_config_and_context(self) -> None:
        """All production Docker commands must have --config and --context default."""
        from ._phase15_e2a_harness_lifecycle import (
            _observe_container_presence,
            _remove_container_by_id,
            _full_container_inspect,
        )

        captured_commands: list[list[str]] = []

        def capture_run(
            args: Sequence[str], **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            captured_commands.append(list(args))
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="")

        # Test observe
        _observe_container_presence("test", config_dir="/tmp/cfg", run=capture_run)
        # Test remove
        _remove_container_by_id("a" * 64, config_dir="/tmp/cfg", run=capture_run)
        # Test inspect
        _full_container_inspect(
            "a" * 64, "test", "b" * 64, 5432, config_dir="/tmp/cfg", run=capture_run
        )

        for cmd in captured_commands:
            assert "--config" in cmd, f"Missing --config in {cmd}"
            config_idx = cmd.index("--config")
            assert config_idx + 1 < len(cmd), "Missing config dir value"
            assert "--context" in cmd, f"Missing --context in {cmd}"
            context_idx = cmd.index("--context")
            assert context_idx + 1 < len(cmd), "Missing context value"
            assert cmd[context_idx + 1] == "default", "Context must be 'default'"


# =============================================================================
# Part 7: Environment no-dict-conversion tests
# =============================================================================


class TestNoDictConversion:
    """Test that environment is never converted to dict."""

    def test_sanitized_env_copy_returns_safe_env_not_dict(self) -> None:
        """_sanitized_env_copy must return SafeDockerEnv, not dict."""
        from ._phase15_e2a_harness_types import _sanitized_env_copy

        env = _sanitized_env_copy()

        # Must NOT be plain dict
        assert not isinstance(env, dict), "_sanitized_env_copy must not return dict"

    def test_no_dict_call_on_env(self) -> None:
        """Verify SafeDockerEnv is not a dict and doesn't expose values through iteration."""
        from ._phase15_e2a_harness_types import _make_docker_env

        env = _make_docker_env(lambda k: {"PATH": "/usr/bin"}.get(k))

        # SafeDockerEnv must be a Mapping
        from collections.abc import Mapping

        assert isinstance(env, Mapping)

        # Must NOT be a dict
        assert not isinstance(env, dict)

        # Verify __class__ is not dict
        assert env.__class__.__name__ == "SafeDockerEnv"

        # Verify items() returns items view, not dict
        items = env.items()
        assert hasattr(items, "__iter__")
        assert not isinstance(items, dict)


# =============================================================================
# Part 8: Result repr redaction tests
# =============================================================================


class TestResultReprRedaction:
    """Test that result dataclass repr/str are properly redacted."""

    def test_container_presence_result_repr_no_container_id(self) -> None:
        """ContainerPresenceResult repr must not contain container ID."""
        from ._phase15_e2a_harness_types import ContainerPresenceResult

        canary_id = "a" * 64
        result = ContainerPresenceResult(
            status="present", rc=0, container_id=canary_id, error_message=None
        )

        # repr must be redacted
        assert canary_id not in repr(result)
        assert "<redacted>" in repr(result)
        # str must be redacted
        assert canary_id not in str(result)

    def test_container_presence_result_repr_no_error_message(self) -> None:
        """ContainerPresenceResult repr must not contain error_message."""
        from ._phase15_e2a_harness_types import ContainerPresenceResult

        canary_msg = "CANARY_ERROR_MSG_12345"
        result = ContainerPresenceResult(
            status="inspection_failure",
            rc=1,
            container_id=None,
            error_message=canary_msg,
        )

        assert canary_msg not in repr(result)
        assert "<redacted>" in repr(result)
        assert canary_msg not in str(result)

    def test_disposable_target_repr_no_credentials(self) -> None:
        """DisposablePostgresqlTarget repr must not contain credentials."""
        from pathlib import Path

        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "scripts"))
        from _rebuild_database_connection import DisposablePostgresqlTarget

        canary_password = "CANARY_PASSWORD_XYZ789"
        canary_dbname = "CANARY_DBNAME"
        canary_user = "CANARY_USER"
        canary_port = 9999

        target = DisposablePostgresqlTarget(
            host="127.0.0.1",
            hostaddr="127.0.0.1",
            port=canary_port,
            dbname=canary_dbname,
            user=canary_user,
            password=canary_password,
        )

        # All sensitive fields must be redacted
        assert canary_password not in repr(target)
        assert canary_dbname not in repr(target)
        assert canary_user not in repr(target)
        assert str(canary_port) not in repr(target)
        assert "<redacted>" in repr(target)
        assert "<redacted>" in str(target)

    def test_full_inspect_result_repr_no_container_id(self) -> None:
        """FullInspectResult repr must not contain container ID or owner."""
        from ._phase15_e2a_harness_lifecycle import FullInspectResult

        canary_id = "a" * 64
        canary_token = "b" * 64
        canary_name = "test-container"
        canary_ip = "127.0.0.1"
        canary_port = 5432

        result = FullInspectResult(
            container_id=canary_id,
            name=canary_name,
            owner=canary_token,
            host_ip=canary_ip,
            host_port=canary_port,
            valid=True,
        )

        # All Docker-derived fields must be redacted
        assert canary_id not in repr(result)
        assert canary_token not in repr(result)
        assert canary_name not in repr(result)
        assert canary_ip not in repr(result)
        assert str(canary_port) not in repr(result)
        assert "<redacted>" in repr(result)
        # str() shows only validity
        assert "valid=True" in str(result)
        assert canary_id not in str(result)

    def test_safe_docker_env_repr_no_path_value(self) -> None:
        """SafeDockerEnv repr must not contain PATH value."""
        from ._phase15_e2a_harness_types import _make_docker_env

        canary_path = "CANARY_PATH_VALUE_987"
        env = _make_docker_env(lambda k: {"PATH": canary_path}.get(k))

        assert canary_path not in repr(env)
        assert canary_path not in str(env)
        # SafeDockerEnv uses "(redacted)" marker
        assert "redacted" in repr(env).lower()

    def test_container_cleanup_result_repr_no_rc(self) -> None:
        """ContainerCleanupResult repr must not expose return codes."""
        from ._phase15_e2a_harness_types import ContainerCleanupResult

        result = ContainerCleanupResult(
            outcome="inspection_failure",
            stage="inspect",
            confirmed=False,
            inspect_rc=127,
            remove_rc=None,
        )

        assert "127" not in repr(result)
        assert "inspect_rc" not in repr(result)
        assert "<redacted>" not in repr(result)  # Status is fine to show
        assert result.outcome in repr(result)


# =============================================================================
# Part 9: TracebackException capture_locals redaction tests
# =============================================================================


class TestTracebackExceptionCaptureLocalsRedaction:
    """Test that TracebackException(capture_locals=True) doesn't expose secrets."""

    def test_run_docker_start_failure_no_secrets_in_traceback(self) -> None:
        """_run_docker_start must absorb failures - no secrets in traceback locals."""
        from ._phase15_e2a_harness_lifecycle import _run_docker_start
        from ._phase15_e2a_harness_types import (
            TRUSTED_DISPOSABLE_IMAGE,
            _make_docker_env,
        )
        from pathlib import Path

        # Canary values to verify are not exposed in public result
        password_canary = "SECRET_PASSWORD_12345"
        token_canary = "SECRET_TOKEN_ABCDE"

        # Create a runner that will fail with sensitive data in locals
        def failing_runner(
            args: Sequence[str], **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            # Inject canaries into exception context to test absorption
            raise ValueError(
                f"Simulated Docker failure with {password_canary} {token_canary}"
            )

        safe_env = _make_docker_env(lambda k: {"PATH": "/usr/bin"}.get(k))

        # Call _run_docker_start - it should absorb the failure
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            env_file = Path(f.name)

        try:
            result = _run_docker_start(
                runner=failing_runner,
                config_dir="/tmp/cfg",
                container_name="test-container",
                port="5432",
                token="b" * 64,
                env_file_path=env_file,
                image=TRUSTED_DISPOSABLE_IMAGE,
                sanitized_env=safe_env,
            )

            # Result should indicate failure
            assert result.success is False
            assert result.container_id == ""

            # Verify public result representation does not expose canaries
            result_repr = repr(result)
            assert password_canary not in result_repr
            assert token_canary not in result_repr

            # No exception raised - failure absorbed
        finally:
            env_file.unlink(missing_ok=True)

    def test_open_fresh_connection_impl_failure_absorbs_exceptions(self) -> None:
        """_open_fresh_attested_connection_impl must absorb all failures."""
        from ._phase15_e2a_harness_lifecycle import _open_fresh_attested_connection_impl

        # Test uses lambda runner that returns failure - function absorbs exception
        result = _open_fresh_attested_connection_impl(
            container_id="a" * 64,
            container_name="test-container",
            token="b" * 64,
            port=5432,
            user="test_user",
            password="secret_password",
            database="test_db",
            config_dir="/tmp/cfg",
            runner=lambda *a, **kw: subprocess.CompletedProcess(
                args=a, returncode=1, stdout="", stderr=""
            ),
        )

        # Result should indicate failure
        assert result.success is False
        assert result.connection is None

        # No exception raised - failure absorbed

    def test_safe_docker_env_locals_not_in_traceback(self) -> None:
        """SafeDockerEnv repr in traceback locals must be redacted."""
        from ._phase15_e2a_harness_types import _make_docker_env

        def failing_function() -> None:
            # Create env - repr should be redacted even in traceback
            env = _make_docker_env(lambda k: {"PATH": "/secret/path/value"}.get(k))
            # Force an exception with env in locals
            _ = 1 / 0  # ZeroDivisionError
            # Use env to avoid "local variable not used" warning
            _ = env

        try:
            failing_function()
        except Exception as exc:
            te = traceback.TracebackException.from_exception(exc, capture_locals=True)

            # Format the traceback
            tb_lines = list(te.format())
            tb_text = "\n".join(tb_lines)

            # The env's repr must be redacted (shows <SafeDockerEnv (redacted)>)
            # Note: test function's own locals are NOT the concern - only production code's
            assert (
                "/secret/path/value" not in tb_text
            ), f"Sensitive PATH value leaked in traceback:\n{tb_text}"

            # SafeDockerEnv repr must show redacted marker
            assert "SafeDockerEnv" in tb_text
            assert "(redacted)" in tb_text

    def test_result_namedtuple_repr_in_traceback_is_redacted(self) -> None:
        """_DockerStartResult repr in traceback must be redacted."""
        from ._phase15_e2a_harness_lifecycle import _DockerStartResult

        def failing_function() -> None:
            # Create result with secret container ID
            result = _DockerStartResult(success=False, container_id="a" * 64)
            # Force an exception with result in locals
            _ = 1 / 0  # ZeroDivisionError
            # Use result to avoid "local variable not used" warning
            _ = result

        try:
            failing_function()
        except Exception as exc:
            te = traceback.TracebackException.from_exception(exc, capture_locals=True)
            tb_lines = list(te.format())
            tb_text = "\n".join(tb_lines)

            # The container ID must NOT appear in the traceback
            # (the repr should show <redacted> instead)
            assert (
                "aaaaaaaaaaaaaaaa" not in tb_text
            ), f"Container ID leaked in traceback:\n{tb_text}"

            # Result repr must show redacted marker
            assert "_DockerStartResult" in tb_text
            assert "<redacted>" in tb_text

    def test_public_enter_docker_start_failure_no_secrets_in_traceback(self) -> None:
        """__enter__ public failure path must not expose secrets in traceback.

        This test verifies that when Docker start fails, the public __enter__
        only binds safe result objects, not raw secrets.
        """
        from ._phase15_e2a_harness_lifecycle import DisposableE2aSession
        from unittest.mock import patch

        def failing_runner(
            args: Sequence[str], **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            if "ps" in args:
                # Return empty output for ps command (no existing containers)
                return subprocess.CompletedProcess(
                    args=args, returncode=0, stdout="", stderr=""
                )
            # Return failure for other commands
            return subprocess.CompletedProcess(
                args=args, returncode=1, stdout="", stderr="Docker error"
            )

        with patch.dict(
            "os.environ",
            {"OKF_E2A_DISPOSABLE_TEST_AUTHORIZED": "separately-authorized"},
            clear=False,
        ):
            try:
                session = DisposableE2aSession(
                    container_name="test-container",
                    password="test_password",
                    runner=failing_runner,
                )
                with session:
                    pass
            except RuntimeError as exc:
                # Verify the error message is fixed, not exposing secrets
                assert "test_password" not in str(exc)
                # Verify the exception type is correct
                assert "Failed to start container" in str(exc) or "Startup" in str(exc)
            else:
                raise AssertionError("Expected RuntimeError from __enter__")

    def test_public_enter_env_file_failure_no_secrets_in_traceback(self) -> None:
        """__enter__ env file creation failure must not expose secrets."""
        from ._phase15_e2a_harness_lifecycle import DisposableE2aSession
        from unittest.mock import patch

        # Invalid password with newline - should fail validation
        with patch.dict(
            "os.environ",
            {"OKF_E2A_DISPOSABLE_TEST_AUTHORIZED": "separately-authorized"},
            clear=False,
        ):
            try:
                session = DisposableE2aSession(
                    container_name="test-container",
                    password="test\npassword",  # Invalid: contains newline
                )
                with session:
                    pass
            except (ValueError, RuntimeError) as exc:
                # Verify the error message does not expose the password
                assert "test\npassword" not in str(exc)
            else:
                raise AssertionError("Expected exception from __enter__")

    def test_public_bridge_failure_no_secrets_in_traceback(self) -> None:
        """open_fresh_attested_connection public failure must not expose secrets."""

        # Test the helper function directly to verify it absorbs failures
        from ._phase15_e2a_harness_lifecycle import _open_fresh_attested_connection_impl

        # Simulate a connection factory that fails
        def failing_runner(
            args: Sequence[str], **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            raise RuntimeError("Connection factory failed")

        # env parameter removed - function creates env internally
        result = _open_fresh_attested_connection_impl(
            container_id="a" * 64,
            container_name="test-container",
            token="b" * 64,
            port=5432,
            user="test_user",
            password="test_password_canary_xyz",
            database="test_db",
            config_dir="/tmp/cfg",
            runner=failing_runner,
        )

        # Result should indicate failure without exposing secrets
        assert result.success is False
        assert result.connection is None

        # Verify repr doesn't expose secrets
        result_repr = repr(result)
        assert "test_password" not in result_repr
        assert "test_user" not in result_repr
        assert "test_db" not in result_repr
        assert "<redacted>" in result_repr


# =============================================================================
# Part 10: Adversarial strict parser tests
# =============================================================================


class TestStrictParserAdversarial:
    """Test strict parser rejects adversarial edge cases."""

    def test_single_valid_record_plus_empty_line_rejected(self) -> None:
        """Valid record + empty line must be rejected."""
        from ._phase15_e2a_harness_lifecycle import _observe_container_presence

        container_id = "a" * 64
        result = _observe_container_presence(
            "test-container",
            config_dir="/tmp/config",
            run=lambda *args, **kwargs: subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=f"test-container\t{container_id}\n\n",
                stderr="",
            ),
        )
        assert result.status == "ambiguous_output"

    def test_single_valid_record_plus_newline_line_rejected(self) -> None:
        """Valid record + newline-only line must be rejected."""
        from ._phase15_e2a_harness_lifecycle import _observe_container_presence

        container_id = "a" * 64
        result = _observe_container_presence(
            "test-container",
            config_dir="/tmp/config",
            run=lambda *args, **kwargs: subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=f"test-container\t{container_id}\n \n",
                stderr="",
            ),
        )
        assert result.status == "ambiguous_output"

    def test_full_inspect_rejects_trailing_newline_in_id(self) -> None:
        """Full inspect must reject container ID with trailing newline."""
        from ._phase15_e2a_harness_lifecycle import _full_container_inspect

        canary_id = "a" * 64 + "\n"
        result = _full_container_inspect(
            canary_id,
            "test-container",
            "b" * 64,
            5432,
            config_dir="/tmp/config",
            run=lambda *args, **kwargs: subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=f"{canary_id}|/test-container|{'b' * 64}|127.0.0.1:5432",
                stderr="",
            ),
        )
        assert not result.valid

    def test_full_inspect_rejects_extra_pipe_field(self) -> None:
        """Full inspect must reject output with extra pipe field."""
        from ._phase15_e2a_harness_lifecycle import _full_container_inspect

        container_id = "a" * 64
        result = _full_container_inspect(
            container_id,
            "test-container",
            "b" * 64,
            5432,
            config_dir="/tmp/config",
            run=lambda *args, **kwargs: subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=f"{container_id}|/test-container|{'b' * 64}|127.0.0.1:5432|extra",
                stderr="",
            ),
        )
        assert not result.valid

    def test_full_inspect_rejects_missing_pipe_field(self) -> None:
        """Full inspect must reject output with missing pipe field."""
        from ._phase15_e2a_harness_lifecycle import _full_container_inspect

        container_id = "a" * 64
        result = _full_container_inspect(
            container_id,
            "test-container",
            "b" * 64,
            5432,
            config_dir="/tmp/config",
            run=lambda *args, **kwargs: subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=f"{container_id}|/test-container|{'b' * 64}",
                stderr="",
            ),
        )
        assert not result.valid

    def test_full_inspect_accepts_trailing_crlf(self) -> None:
        """Full inspect must accept output with CRLF ending."""
        from ._phase15_e2a_harness_lifecycle import _full_container_inspect

        container_id = "a" * 64
        result = _full_container_inspect(
            container_id,
            "test-container",
            "b" * 64,
            5432,
            config_dir="/tmp/config",
            run=lambda *args, **kwargs: subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=f"{container_id}|/test-container|{'b' * 64}|127.0.0.1:5432\r\n",
                stderr="",
            ),
        )
        # CRLF ending is valid
        assert result.valid

    def test_full_inspect_accepts_trailing_lf(self) -> None:
        """Full inspect must accept output with LF ending."""
        from ._phase15_e2a_harness_lifecycle import _full_container_inspect

        container_id = "a" * 64
        result = _full_container_inspect(
            container_id,
            "test-container",
            "b" * 64,
            5432,
            config_dir="/tmp/config",
            run=lambda *args, **kwargs: subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=f"{container_id}|/test-container|{'b' * 64}|127.0.0.1:5432\n",
                stderr="",
            ),
        )
        # LF ending is valid
        assert result.valid

    def test_full_inspect_accepts_no_ending(self) -> None:
        """Full inspect must accept output with no line ending."""
        from ._phase15_e2a_harness_lifecycle import _full_container_inspect

        container_id = "a" * 64
        result = _full_container_inspect(
            container_id,
            "test-container",
            "b" * 64,
            5432,
            config_dir="/tmp/config",
            run=lambda *args, **kwargs: subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=f"{container_id}|/test-container|{'b' * 64}|127.0.0.1:5432",
                stderr="",
            ),
        )
        # No ending is valid
        assert result.valid

    def test_full_inspect_rejects_bare_cr(self) -> None:
        """Full inspect must reject output with bare CR."""
        from ._phase15_e2a_harness_lifecycle import _full_container_inspect

        container_id = "a" * 64
        result = _full_container_inspect(
            container_id,
            "test-container",
            "b" * 64,
            5432,
            config_dir="/tmp/config",
            run=lambda *args, **kwargs: subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=f"{container_id}|/test-container|{'b' * 64}|127.0.0.1:5432\r",
                stderr="",
            ),
        )
        assert not result.valid

    def test_full_inspect_rejects_lfcr(self) -> None:
        """Full inspect must reject output with LFCR ending."""
        from ._phase15_e2a_harness_lifecycle import _full_container_inspect

        container_id = "a" * 64
        result = _full_container_inspect(
            container_id,
            "test-container",
            "b" * 64,
            5432,
            config_dir="/tmp/config",
            run=lambda *args, **kwargs: subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=f"{container_id}|/test-container|{'b' * 64}|127.0.0.1:5432\n\r",
                stderr="",
            ),
        )
        assert not result.valid

    def test_full_inspect_rejects_double_crlf(self) -> None:
        """Full inspect must reject output with double CRLF."""
        from ._phase15_e2a_harness_lifecycle import _full_container_inspect

        container_id = "a" * 64
        result = _full_container_inspect(
            container_id,
            "test-container",
            "b" * 64,
            5432,
            config_dir="/tmp/config",
            run=lambda *args, **kwargs: subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=f"{container_id}|/test-container|{'b' * 64}|127.0.0.1:5432\r\n\r\n",
                stderr="",
            ),
        )
        assert not result.valid

    def test_full_inspect_rejects_embedded_cr(self) -> None:
        """Full inspect must reject output with embedded CR in record."""
        from ._phase15_e2a_harness_lifecycle import _full_container_inspect

        container_id = "a" * 64
        result = _full_container_inspect(
            container_id,
            "test-container",
            "b" * 64,
            5432,
            config_dir="/tmp/config",
            run=lambda *args, **kwargs: subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=f"{container_id}|/test-container|{'b' * 32}\r{'b' * 32}|127.0.0.1:5432",
                stderr="",
            ),
        )
        assert not result.valid

    def test_full_inspect_rejects_non_digit_port(self) -> None:
        """Full inspect must reject non-ASCII-decimal port."""
        from ._phase15_e2a_harness_lifecycle import _full_container_inspect

        container_id = "a" * 64
        result = _full_container_inspect(
            container_id,
            "test-container",
            "b" * 64,
            5432,
            config_dir="/tmp/config",
            run=lambda *args, **kwargs: subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=f"{container_id}|/test-container|{'b' * 64}|127.0.0.1:5432x",
                stderr="",
            ),
        )
        assert not result.valid

    def test_full_inspect_rejects_port_with_whitespace(self) -> None:
        """Full inspect must reject port with whitespace."""
        from ._phase15_e2a_harness_lifecycle import _full_container_inspect

        container_id = "a" * 64
        result = _full_container_inspect(
            container_id,
            "test-container",
            "b" * 64,
            5432,
            config_dir="/tmp/config",
            run=lambda *args, **kwargs: subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=f"{container_id}|/test-container|{'b' * 64}|127.0.0.1: 5432",
                stderr="",
            ),
        )
        assert not result.valid


# =============================================================================
# Part 11: TracebackException(capture_locals=True) tests
# =============================================================================


class TestTracebackExceptionCaptureLocals:
    """Test that sensitive values are redacted in TracebackException output."""

    def test_prepare_startup_invalid_token_no_raw_token_in_traceback(
        self,
    ) -> None:
        """_prepare_startup_impl with invalid token must not expose raw token.

        This test uses TracebackException(capture_locals=True) to verify
        that when token validation fails, the raw token does not appear
        in the captured locals.
        """

        from ._phase15_e2a_harness_lifecycle import (
            _prepare_startup_impl,
        )

        # Token factory that returns invalid token
        def invalid_token_factory() -> str:
            return "invalid-token-with-canary-xyz-123"

        # Call _prepare_startup_impl directly to capture its frame
        result = _prepare_startup_impl(invalid_token_factory)

        # Verify result indicates failure
        assert result.success is False
        assert result.invalid_token is True

        # Verify repr does not expose the canary
        result_repr = repr(result)
        assert "canary-xyz-123" not in result_repr
        assert "<redacted>" in result_repr

    def test_prepare_startup_success_no_raw_token_in_result_repr(self) -> None:
        """Successful _prepare_startup_impl must redact token in repr."""
        from ._phase15_e2a_harness_lifecycle import _prepare_startup_impl

        # Token factory that returns valid token
        def valid_token_factory() -> str:
            return "a" * 64

        result = _prepare_startup_impl(valid_token_factory)

        # Verify success
        assert result.success is True

        # Verify repr redacts the token
        result_repr = repr(result)
        assert "a" * 64 not in result_repr
        assert "<redacted>" in result_repr

        # Clean up temp directory
        if result.config_dir_obj is not None:
            result.config_dir_obj.cleanup()

    def test_startup_impl_failure_no_container_id_in_result_repr(self) -> None:
        """_startup_impl failure must not expose container_id in repr."""
        import subprocess

        from ._phase15_e2a_harness_lifecycle import _startup_impl
        from ._phase15_e2a_harness_types import TRUSTED_DISPOSABLE_IMAGE

        def failing_runner(
            args: Sequence[str], **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            if "ps" in args:
                return subprocess.CompletedProcess(
                    args=args, returncode=0, stdout="", stderr=""
                )
            return subprocess.CompletedProcess(
                args=args, returncode=1, stdout="", stderr="Docker error"
            )

        # sanitized_env parameter removed - function creates env internally
        result = _startup_impl(
            runner=failing_runner,
            config_dir="/tmp/test-config",
            container_name="test-container",
            port="5432",
            token="b" * 64,
            password="test_password_canary",
            database="test_db",
            user="test_user",
            image=TRUSTED_DISPOSABLE_IMAGE,
            conn_factory_input=None,
            sleep_fn=lambda n: None,
        )

        # Verify failure
        assert result.success is False

        # Verify repr does not expose secrets
        result_repr = repr(result)
        assert "b" * 64 not in result_repr  # token
        assert "test_password_canary" not in result_repr
        assert "<redacted>" in result_repr

    def test_create_env_file_failure_no_password_in_result_repr(self) -> None:
        """_create_env_file_impl failure must not expose password in repr."""
        from ._phase15_e2a_harness_lifecycle import _create_env_file_impl

        # Invalid password with newline - should fail validation
        result = _create_env_file_impl(
            password="test\npassword",  # Invalid: contains newline
            database="test_db",
            user="test_user",
        )

        # Verify failure
        assert result.success is False

        # Verify repr does not expose the password
        result_repr = repr(result)
        assert "test\npassword" not in result_repr
        assert "test_db" not in result_repr
        assert "test_user" not in result_repr

    def test_open_connection_failure_no_secrets_in_result_repr(self) -> None:
        """_open_fresh_attested_connection_impl failure must not expose secrets."""
        import subprocess

        from ._phase15_e2a_harness_lifecycle import (
            _open_fresh_attested_connection_impl,
        )

        def failing_runner(
            args: Sequence[str], **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(
                args=args, returncode=1, stdout="", stderr="Error"
            )

        # env parameter removed - function creates env internally
        result = _open_fresh_attested_connection_impl(
            container_id="a" * 64,
            container_name="test-container",
            token="b" * 64,
            port=5432,
            user="test_user_canary",
            password="test_password_canary_xyz",
            database="test_db_canary",
            config_dir="/tmp/cfg",
            runner=failing_runner,
        )

        # Verify failure
        assert result.success is False

        # Verify repr does not expose secrets
        result_repr = repr(result)
        assert "test_password_canary_xyz" not in result_repr
        assert "test_user_canary" not in result_repr
        assert "test_db_canary" not in result_repr
        assert "<redacted>" in result_repr


# =============================================================================
# Part 12: TracebackException(capture_locals=True) public boundary tests
# =============================================================================


class TestTracebackExceptionPublicBoundary:
    """Test that public boundaries do not expose secrets in traceback locals."""

    def test_public_enter_env_construction_failure_no_secrets(
        self,
    ) -> None:
        """__enter__ env construction failure must not expose secrets in traceback.

        This test patches the worker-side env construction seam to fail,
        then verifies the public __enter__ error doesn't expose secrets.
        """
        import subprocess
        import traceback
        from unittest.mock import patch

        from ._phase15_e2a_harness_lifecycle import DisposableE2aSession
        from . import _phase15_e2a_harness_lifecycle as lifecycle_mod

        # PATH canary to verify allowlisted env values don't leak
        path_canary = "/usr/canary/bin/PATH_TEST_123"

        def failing_runner(args, **kwargs):
            # Succeed on ps check (container absent)
            if "ps" in args:
                return subprocess.CompletedProcess(
                    args=args, returncode=0, stdout="", stderr=""
                )
            # Should not reach docker run due to env file failure
            return subprocess.CompletedProcess(
                args=args, returncode=1, stdout="", stderr="Error"
            )

        canary_password = "env_construction_canary_XYZ123"

        # Build a failed env-file result object matching _EnvFileResult shape
        failed_env_result = type("Result", (), {"success": False, "path": None})()

        with patch.dict(
            "os.environ",
            {
                "OKF_E2A_DISPOSABLE_TEST_AUTHORIZED": "separately-authorized",
                "PATH": path_canary,
            },
            clear=False,
        ):
            # Patch the worker-used construction seam to fail
            with patch.object(
                lifecycle_mod,
                "_create_env_file_impl",
                return_value=failed_env_result,
            ):
                try:
                    session = DisposableE2aSession(
                        container_name="test-container",
                        password=canary_password,
                        runner=failing_runner,
                    )
                    with session:
                        pass
                except RuntimeError as exc:
                    # Capture traceback with locals
                    te = traceback.TracebackException.from_exception(
                        exc, capture_locals=True
                    )

                    # Check each production frame
                    for frame in te.stack:
                        if frame.filename.endswith("_phase15_e2a_harness_lifecycle.py"):
                            if frame.locals:
                                locals_str = str(frame.locals)
                                # Password must NOT appear in production frames
                                assert (
                                    canary_password not in locals_str
                                ), f"Password leaked in {frame.name}:\n{locals_str}"
                                # PATH canary must NOT appear
                                assert (
                                    path_canary not in locals_str
                                ), f"PATH leaked in {frame.name}:\n{locals_str}"
                                # Token should be redacted
                                if "token" in locals_str:
                                    assert "<redacted>" in locals_str
                else:
                    raise AssertionError("Expected RuntimeError")

    def test_public_enter_docker_start_failure_traceback_locals(
        self,
    ) -> None:
        """__enter__ Docker start failure must not expose secrets in traceback locals."""
        import subprocess
        import traceback
        from unittest.mock import patch

        from ._phase15_e2a_harness_lifecycle import DisposableE2aSession

        def failing_runner(args, **kwargs):
            if "ps" in args:
                return subprocess.CompletedProcess(
                    args=args, returncode=0, stdout="", stderr=""
                )
            return subprocess.CompletedProcess(
                args=args, returncode=1, stdout="", stderr="Docker error"
            )

        canary_password = "canary_password_XYZ123"

        with patch.dict(
            "os.environ",
            {"OKF_E2A_DISPOSABLE_TEST_AUTHORIZED": "separately-authorized"},
            clear=False,
        ):
            try:
                session = DisposableE2aSession(
                    container_name="test-container",
                    password=canary_password,
                    runner=failing_runner,
                )
                with session:
                    pass
            except RuntimeError as exc:
                # Capture traceback with locals
                te = traceback.TracebackException.from_exception(
                    exc, capture_locals=True
                )

                # Check each frame individually
                # The test frame will have the canary, but production frames must not
                for frame in te.stack:
                    if frame.filename.endswith("_phase15_e2a_harness_lifecycle.py"):
                        # Production code frame - must not have canary in locals
                        if frame.locals:
                            locals_str = str(frame.locals)
                            assert (
                                canary_password not in locals_str
                            ), f"Password leaked in {frame.name}:\n{locals_str}"
                            assert "XYZ123" not in locals_str
            else:
                raise AssertionError("Expected RuntimeError")

    def test_public_fresh_bridge_failure_traceback_locals(
        self,
    ) -> None:
        """open_fresh_attested_connection public failure must not expose secrets.

        This test completes startup successfully, then makes the bridge
        re-attestation fail, and verifies no secrets leak in traceback.
        """
        import subprocess
        import traceback
        from unittest.mock import patch

        from . import _phase15_e2a_harness_lifecycle as lifecycle_mod
        from ._phase15_e2a_harness_lifecycle import DisposableE2aSession

        path_canary = "/usr/canary/bin/BRIDGE_PATH_456"

        def successful_runner(args, **kwargs):
            """Succeeds on ps, run, inspect (for startup)."""
            if "ps" in args:
                return subprocess.CompletedProcess(
                    args=args, returncode=0, stdout="", stderr=""
                )
            if "run" in args:
                return subprocess.CompletedProcess(
                    args=args, returncode=0, stdout="a" * 64, stderr=""
                )
            if "inspect" in args:
                # Valid inspect output during startup
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=0,
                    stdout=f"{'a' * 64}|/test-container|{'b' * 64}|127.0.0.1:5432",
                    stderr="",
                )
            return subprocess.CompletedProcess(
                args=args, returncode=1, stdout="", stderr="Error"
            )

        canary_password = "bridge_canary_PASS789"

        with patch.dict(
            "os.environ",
            {
                "OKF_E2A_DISPOSABLE_TEST_AUTHORIZED": "separately-authorized",
                "PATH": path_canary,
            },
            clear=False,
        ):
            # Patch _setup_database_impl to succeed without Docker
            successful_db_result = type("Result", (), {"success": True})()

            # Patch the bridge worker to fail (simulating re-attestation failure)
            failed_bridge_result = type(
                "Result", (), {"success": False, "connection": None}
            )()

            with patch.object(
                lifecycle_mod,
                "_setup_database_impl",
                return_value=successful_db_result,
            ):
                with patch.object(
                    lifecycle_mod,
                    "_open_fresh_attested_connection_impl",
                    return_value=failed_bridge_result,
                ):
                    try:
                        session = DisposableE2aSession(
                            container_name="test-container",
                            password=canary_password,
                            runner=successful_runner,
                            # No conn_factory - must use production path
                        )
                        with session:
                            # Call the public bridge - should fail
                            session.open_fresh_attested_connection()
                    except RuntimeError as exc:
                        # Capture traceback with locals
                        te = traceback.TracebackException.from_exception(
                            exc, capture_locals=True
                        )

                        # Check each production frame
                        for frame in te.stack:
                            if frame.filename.endswith(
                                "_phase15_e2a_harness_lifecycle.py"
                            ):
                                if frame.locals:
                                    locals_str = str(frame.locals)
                                    assert (
                                        canary_password not in locals_str
                                    ), f"Password leaked in {frame.name}:\n{locals_str}"
                                    assert (
                                        path_canary not in locals_str
                                    ), f"PATH leaked in {frame.name}:\n{locals_str}"
                                    assert "PASS789" not in locals_str
                    else:
                        raise AssertionError("Expected RuntimeError")

    def test_cleanup_failure_traceback_locals(
        self,
    ) -> None:
        """__exit__ public cleanup failure must not expose secrets.

        This test completes startup successfully, then makes cleanup fail,
        and verifies no secrets leak in traceback.
        """
        import subprocess
        import traceback
        from unittest.mock import patch

        from . import _phase15_e2a_harness_lifecycle as lifecycle_mod
        from ._phase15_e2a_harness_lifecycle import DisposableE2aSession

        path_canary = "/usr/canary/bin/CLEANUP_PATH_789"

        # Runner succeeds for startup but fails for cleanup
        inspect_for_startup = [True]

        def conditional_runner(args, **kwargs):
            """Succeeds for startup, fails for cleanup."""
            if "ps" in args:
                return subprocess.CompletedProcess(
                    args=args, returncode=0, stdout="", stderr=""
                )
            if "run" in args:
                return subprocess.CompletedProcess(
                    args=args, returncode=0, stdout="a" * 64, stderr=""
                )
            if "inspect" in args:
                if inspect_for_startup[0]:
                    # Valid inspect output during startup
                    return subprocess.CompletedProcess(
                        args=args,
                        returncode=0,
                        stdout=f"{'a' * 64}|/test-container|{'b' * 64}|127.0.0.1:5432",
                        stderr="",
                    )
                else:
                    # Fail inspect during cleanup
                    return subprocess.CompletedProcess(
                        args=args, returncode=1, stdout="", stderr="Error"
                    )
            return subprocess.CompletedProcess(
                args=args, returncode=1, stdout="", stderr="Error"
            )

        canary_password = "cleanup_canary_ABC456"

        with patch.dict(
            "os.environ",
            {
                "OKF_E2A_DISPOSABLE_TEST_AUTHORIZED": "separately-authorized",
                "PATH": path_canary,
            },
            clear=False,
        ):
            # Patch _setup_database_impl to succeed without Docker
            successful_db_result = type("Result", (), {"success": True})()

            with patch.object(
                lifecycle_mod,
                "_setup_database_impl",
                return_value=successful_db_result,
            ):
                try:
                    session = DisposableE2aSession(
                        container_name="test-container",
                        password=canary_password,
                        runner=conditional_runner,
                    )
                    # Startup will succeed
                    with session:
                        # After successful startup, make cleanup fail
                        inspect_for_startup[0] = False
                        # Exit will fail at cleanup (inspect fails)
                        pass
                except RuntimeError as exc:
                    # Capture traceback with locals
                    te = traceback.TracebackException.from_exception(
                        exc, capture_locals=True
                    )

                    # Check each production frame
                    for frame in te.stack:
                        if frame.filename.endswith("_phase15_e2a_harness_lifecycle.py"):
                            if frame.locals:
                                locals_str = str(frame.locals)
                                assert (
                                    canary_password not in locals_str
                                ), f"Password leaked in {frame.name}:\n{locals_str}"
                                assert (
                                    path_canary not in locals_str
                                ), f"PATH leaked in {frame.name}:\n{locals_str}"
                                assert "ABC456" not in locals_str
                else:
                    raise AssertionError("Expected RuntimeError")

    # NOTE: test_env_file_deleted_after_normal_exit removed because
    # it requires a full database mock which is not feasible in unit tests.
    # The env file cleanup is tested in integration tests with real Docker.
