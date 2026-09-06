"""Types and validation for Phase 15 E2A harness (Task #132).

This module provides authorization gate, environment sanitization,
input validation, and immutable result types.

Contract: Never import from e2a_disposable_execution or e2a_disposable_acceptance.
"""

from __future__ import annotations

import logging
import os
import platform
import re
import secrets
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable, Literal

logger = logging.getLogger(__name__)

AUTHORIZATION_FLAG = "OKF_E2A_DISPOSABLE_TEST_AUTHORIZED"
_AUTHORIZATION_VALUE = "separately-authorized"

# KEEP for backward compatibility with other modules, but DO NOT USE for env construction
SENSITIVE_ENV_VARS = frozenset(
    {
        "DATABASE_URL",
        "FORMAL_RUNTIME_DATABASE_URL",
        "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE",
        "OKF_REBUILD_EXPECTED_DATABASE",
        "OKF_FAILURE_AUDIT_ACCEPTANCE",
        "OKF_REBUILD_DOCKER_ACCEPTANCE",
        "OKF_E2A_DISPOSABLE_TEST_AUTHORIZED",
    }
)

# Platform-aware minimal allowlist for Docker CLI execution
# Windows requires SystemRoot for DLL resolution, optionally PATHEXT
# POSIX requires only PATH
_DOCKER_ENV_ALLOWLIST_POSIX: tuple[str, ...] = ("PATH",)
_DOCKER_ENV_ALLOWLIST_WINDOWS: tuple[str, ...] = ("PATH", "SystemRoot", "PATHEXT")

# Single definition using conditional expression
_DOCKER_ENV_ALLOWLIST: tuple[str, ...] = (
    _DOCKER_ENV_ALLOWLIST_WINDOWS
    if platform.system() == "Windows"
    else _DOCKER_ENV_ALLOWLIST_POSIX
)


class SafeDockerEnv(Mapping[str, str]):
    """Environment mapping for Docker subprocess with redacted repr.

    Key security properties:
    - items()/values() yield REAL strings for subprocess via iteration
    - repr()/str() show REDACTED (no values visible in traceback)
    - Never exposes environment via __dict__
    - TUPLE-backed only, NO dict anywhere in storage
    - Linear lookup via tuple iteration (no dict)
    - Only contains allowlisted keys (validated at construction)
    - Cannot be mutated after construction

    Contract:
    - Standard set algebra works: `frozenset & env.keys()`
    - View repr contains no actual path/env values
    - No type suppression needed for Mapping protocol

    This ensures:
    1. Subprocess receives real values via iteration
    2. pytest traceback locals show redacted text
    3. Only minimal keys (PATH, SystemRoot on Windows) are included
    """

    __slots__ = ("_pairs",)
    _pairs: tuple[tuple[str, str], ...]

    def __init__(self, pairs: tuple[tuple[str, str], ...]) -> None:
        """Initialize with immutable tuple of (key, value) pairs.

        Args:
            pairs: Tuple of (key, value) tuples - caller must not retain mutable reference

        Raises:
            ValueError: If any key is not in the platform allowlist.
        """
        # Validate all keys are in allowlist
        for key, _ in pairs:
            if key not in _DOCKER_ENV_ALLOWLIST:
                raise ValueError(f"Key '{key}' not in Docker environment allowlist")
        # Check for duplicates
        seen_keys: set[str] = set()
        for key, _ in pairs:
            if key in seen_keys:
                raise ValueError(f"Duplicate key '{key}' in environment")
            seen_keys.add(key)

        object.__setattr__(self, "_pairs", pairs)

    def __getitem__(self, key: str) -> str:
        # Linear lookup - no dict
        for k, v in self._pairs:
            if k == key:
                return v
        raise KeyError(key)

    def __contains__(self, key: object) -> bool:
        # Linear lookup - no dict
        for k, _ in self._pairs:
            if k == key:
                return True
        return False

    def __iter__(self) -> Iterator[str]:
        for k, _ in self._pairs:
            yield k

    def __len__(self) -> int:
        return len(self._pairs)

    def __repr__(self) -> str:
        return "<SafeDockerEnv (redacted)>"

    def __str__(self) -> str:
        return "<SafeDockerEnv>"


def _make_docker_env(
    getter: Callable[[str], str | None] | None = None,
) -> SafeDockerEnv:
    """Create safe Docker environment using direct one-key reads.

    Args:
        getter: Optional key -> value function for unit test injection.
                Production path uses os.environ.get directly.

    Returns:
        SafeDockerEnv with only allowlisted keys.

    Security:
        - NEVER receives os.environ as local
        - NEVER iterates/enumerates environment
        - NEVER accesses non-allowlisted keys
        - Production: direct os.environ.get(key) per allowlisted key only
        - TUPLE-backed: no normal dict anywhere in storage
    """
    if getter is None:
        # Production path: direct one-key reads, no enumeration
        def _prod_getter(key: str) -> str | None:
            return os.environ.get(key)  # Single-key access only

        active_getter: Callable[[str], str | None] = _prod_getter
    else:
        active_getter = getter

    # Build TUPLE of (key, value) pairs with only allowlisted keys
    pairs_list: list[tuple[str, str]] = []
    for key in _DOCKER_ENV_ALLOWLIST:
        value = active_getter(key)
        if value is not None:
            pairs_list.append((key, value))

    # Convert to immutable tuple - no dict ever created
    pairs = tuple(pairs_list)

    return SafeDockerEnv(pairs)


_PORT_PARSE_ERROR = "invalid port"
_ATTESTATION_ERROR = "Database attestation failed"
_CLEANUP_ERROR = "Cleanup failed"

# Safe Docker container name regex: lowercase, digits, dash (no dots - regex metacharacter)
_SAFE_CONTAINER_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9\-]{0,62}$")

# Exact 64 lowercase hex token pattern (no whitespace/newlines, must match full string)
_HEX64_PATTERN = re.compile(r"\A[a-f0-9]{64}\Z", re.ASCII)


def _is_separately_authorized() -> bool:
    """Check if authorization flag is set to exact required value."""
    return os.environ.get(AUTHORIZATION_FLAG) == _AUTHORIZATION_VALUE


def _require_authorization() -> None:
    """Require authorization or raise RuntimeError.

    Raises:
        RuntimeError: If not separately authorized

    Contract:
        - Fails closed before any Docker/connection operations
        - Never uses pytest.skip or similar
    """
    if not _is_separately_authorized():
        raise RuntimeError("E2A disposable test requires separate authorization")


def _sanitized_env_copy() -> SafeDockerEnv:
    """Create redacted environment for Docker subprocess.

    Security:
        - Uses _make_docker_env which never enumerates os.environ
        - Only reads specific allowlisted keys via os.environ.get(key)
        - Returns SafeDockerEnv with redacted repr

    Note: Legacy SENSITIVE_ENV_VARS kept for compatibility, not used here.
    """
    return _make_docker_env()  # Uses production getter


def _parse_host_port(host_port: str) -> tuple[str, int]:
    """Parse host:port string with strict validation.

    Args:
        host_port: Host:port string (e.g., "localhost:5432")

    Returns:
        Tuple of (host, port)

    Raises:
        ValueError: If input is invalid (all failures use same redacted message)

    Contract:
        - Input must be exact built-in str type (reject subclasses)
        - Port must be ASCII digits only, 1-65535
        - Port "007" is valid (parses to 7)
        - All failures use fixed redacted message
    """
    if type(host_port) is not str:
        raise ValueError(_PORT_PARSE_ERROR)

    if ":" not in host_port:
        raise ValueError(_PORT_PARSE_ERROR)

    host, port_str = host_port.rsplit(":", 1)

    if not port_str:
        raise ValueError(_PORT_PARSE_ERROR)

    if not re.fullmatch(r"[0-9]+", port_str):
        raise ValueError(_PORT_PARSE_ERROR)

    try:
        port = int(port_str, 10)
    except ValueError:
        raise ValueError(_PORT_PARSE_ERROR) from None

    if not 1 <= port <= 65535:
        raise ValueError(_PORT_PARSE_ERROR)

    return host, port


def _validate_container_name(name: str) -> str:
    """Validate Docker container name for safety.

    Args:
        name: Container name to validate

    Returns:
        Validated name (same as input)

    Raises:
        ValueError: If name is invalid (fixed redacted message)

    Contract:
        - Must be exact built-in str
        - Must match safe Docker name pattern (no dots - regex metacharacter)
        - Reject whitespace/control chars, separators, option-like names
        - Reject subclasses with fixed redacted error
    """
    if type(name) is not str:
        raise ValueError("Invalid container name")

    if not name:
        raise ValueError("Invalid container name")

    if len(name) > 63:
        raise ValueError("Invalid container name")

    if not _SAFE_CONTAINER_NAME_PATTERN.match(name):
        raise ValueError("Invalid container name")

    if name.startswith("-"):
        raise ValueError("Invalid container name")

    return name


def _validate_host_port_str(port_str: str) -> str:
    """Validate host port string (ASCII digits, 1-65535).

    Args:
        port_str: Port as string

    Returns:
        Validated port string

    Raises:
        ValueError: If invalid (fixed redacted message)
    """
    if type(port_str) is not str:
        raise ValueError("Invalid port")

    if not re.fullmatch(r"[0-9]+", port_str):
        raise ValueError("Invalid port")

    try:
        port = int(port_str, 10)
        if not 1 <= port <= 65535:
            raise ValueError("Invalid port")
    except ValueError:
        raise ValueError("Invalid port") from None

    return port_str


def _validate_returncode(rc: object) -> int:
    """Validate that return code is exact built-in int.

    Args:
        rc: Object to validate

    Returns:
        int if valid

    Raises:
        ValueError: If rc is not exact built-in int (reject bool/subclasses)

    Contract:
        - Accept only exact built-in int type
        - Reject bool (bool is subclass of int)
        - Reject int subclasses
    """
    if type(rc) is not int:
        raise ValueError("Return code must be exact built-in int")
    return rc


def _generate_ownership_token() -> str:
    """Generate process-local ownership token.

    Returns:
        64-character lowercase hex string

    Contract:
        - Uses secrets.token_hex(32) for cryptographically secure token
        - Exact 64 lowercase hex characters
        - Must never appear in repr, error messages, logging, or test output
    """
    return secrets.token_hex(32)


def _validate_ownership_token(token: str) -> str:
    """Validate ownership token format.

    Args:
        token: Token to validate

    Returns:
        Validated token

    Raises:
        ValueError: If token format is invalid
    """
    if type(token) is not str:
        raise ValueError("Invalid ownership token")

    if not _HEX64_PATTERN.match(token):
        raise ValueError("Invalid ownership token")

    return token


def _validate_container_id(container_id: str) -> str:
    """Validate Docker container ID format.

    Args:
        container_id: Container ID to validate

    Returns:
        Validated ID

    Raises:
        ValueError: If ID format is invalid
    """
    if type(container_id) is not str:
        raise ValueError("Invalid container ID")

    if not _HEX64_PATTERN.match(container_id):
        raise ValueError("Invalid container ID")

    return container_id


def _normalize_docker_run_id(raw: str) -> str:
    """Normalize and validate container ID from docker run stdout.

    Accepts ONLY:
        - 64 hex chars (raw)
        - 64 hex + single \\n
        - 64 hex + single \\r\\n

    Rejects:
        - Any other trailing characters
        - Multiple line endings
        - Empty output
        - Whitespace before/after
        - Uppercase hex

    Args:
        raw: Raw output from docker run

    Returns:
        64-hex container ID string

    Raises:
        RuntimeError: If output is malformed (message contains no raw value)
    """
    if not raw:
        raise RuntimeError("Empty container ID from docker run")

    # Check for exact acceptable patterns
    if raw.endswith("\r\n"):
        candidate = raw[:-2]
    elif raw.endswith("\n"):
        candidate = raw[:-1]
    else:
        candidate = raw

    # Verify candidate is exactly 64 lowercase hex chars
    if len(candidate) != 64:
        raise RuntimeError("Invalid container ID length")

    if not _HEX64_PATTERN.match(candidate):
        raise RuntimeError("Invalid container ID format")

    # Verify no extra content (candidate should equal raw stripped of exactly one line ending)
    # Reject if there's any other trailing content
    if raw.endswith("\r\n"):
        if raw[:-2] != candidate:
            raise RuntimeError("Extra content after container ID")
    elif raw.endswith("\n"):
        if raw[:-1] != candidate:
            raise RuntimeError("Extra content after container ID")
    else:
        # No line ending - raw should be exactly candidate
        if raw != candidate:
            raise RuntimeError("Extra content after container ID")

    return candidate


def _validate_env_value(value: str, field_name: str) -> str:
    """Validate environment variable value for injection safety.

    Args:
        value: Value to validate
        field_name: Name of the field for error messages

    Returns:
        Validated value

    Raises:
        ValueError: If value contains forbidden characters

    Contract:
        - Must be exact built-in str
        - Must not contain newline (\n)
        - Must not contain carriage return (\r)
        - Must not contain NUL (\0)
        - Used for database, user, password in env-file
    """
    if type(value) is not str:
        raise ValueError(f"{field_name} must be exact built-in str")

    if "\n" in value:
        raise ValueError(f"{field_name} contains newline - injection not allowed")

    if "\r" in value:
        raise ValueError(
            f"{field_name} contains carriage return - injection not allowed"
        )

    if "\0" in value:
        raise ValueError(f"{field_name} contains NUL - injection not allowed")

    return value


# Trusted disposable image: upstream pgvector image for PostgreSQL 15 major.
# Stock postgres:15 cannot supply the vector extension required by the root
# migration catalog; the exact mutable upstream tag is the deterministic fix.
TRUSTED_DISPOSABLE_IMAGE = "pgvector/pgvector:pg15"

# Immutable declared capability registry for the trusted disposable image.
# Capabilities are DECLARED statically (never inferred from the image name and
# never inspected from image internals at runtime). The root migration catalog
# requires exactly these extensions.
TRUSTED_IMAGE_CAPABILITIES: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        TRUSTED_DISPOSABLE_IMAGE: frozenset({"vector", "pg_trgm"}),
    }
)


def _validate_disposable_image(image: str) -> str:
    """Validate that image is the trusted disposable image.

    Args:
        image: Image to validate

    Returns:
        Validated image

    Raises:
        ValueError: If image is not the trusted disposable image

    Contract:
        - Must be exact "pgvector/pgvector:pg15"
        - No arbitrary registry/image allowed
        - Error text is a fixed non-interpolated string - never echoes the
          attempted image
    """
    if type(image) is not str:
        raise ValueError("Image must be exact built-in str")

    if image != TRUSTED_DISPOSABLE_IMAGE:
        raise ValueError("Untrusted image - only pgvector/pgvector:pg15 allowed")

    return image


ContainerPresenceStatus = Literal[
    "confirmed_absent",
    "present",
    "unowned_label",
    "inspection_failure",
    "ambiguous_output",
]


@dataclass(frozen=True)
class ContainerPresenceResult:
    """Immutable result of container presence check.

    Attributes:
        status: One of the closed set of presence statuses
        rc: Return code from Docker CLI (if applicable)
        container_id: Container ID if present
        error_message: Fixed redacted error if inspection_failure

    Contract:
        - Frozen/immutable
        - status must be from closed set
        - For rc=0, only exact empty stdout is confirmed_absent
        - For rc=0, exactly one exact expected name is present
        - All other stdout is ambiguous
        - rc!=0 is inspection_failure

    Security: All Docker-derived values (container_id, error_message) are
    redacted in repr/str to prevent disclosure in logs/tracebacks.
    """

    status: ContainerPresenceStatus
    rc: int | None = None
    container_id: str | None = None
    error_message: str | None = None

    def __repr__(self) -> str:
        """Redacted repr - does not disclose container_id or error details."""
        return f"ContainerPresenceResult(status={self.status!r}, rc={self.rc}, container_id=<redacted>, error_message=<redacted>)"

    def __str__(self) -> str:
        """Redacted str - does not disclose sensitive values."""
        return f"ContainerPresenceResult(status={self.status})"

    def __post_init__(self) -> None:
        """Enforce closed contract with coherent field combinations."""
        valid_statuses = {
            "confirmed_absent",
            "present",
            "unowned_label",
            "inspection_failure",
            "ambiguous_output",
        }
        if self.status not in valid_statuses:
            raise ValueError(f"Unknown presence status: {self.status}")

        # rc validation
        if self.rc is not None:
            if type(self.rc) is not int:
                raise ValueError("rc must be exact built-in int")

        # Field coherence validation based on status
        if self.status == "confirmed_absent":
            if self.rc != 0:
                raise ValueError("rc must be 0 for confirmed_absent")
            if self.container_id is not None:
                raise ValueError("container_id must be None for confirmed_absent")
            if self.error_message is not None:
                raise ValueError("error_message must be None for confirmed_absent")

        elif self.status == "present":
            if self.rc is not None and self.rc != 0:
                raise ValueError("rc must be 0 for present")
            if self.container_id is None:
                raise ValueError("container_id required for present")
            if type(self.container_id) is not str:
                raise ValueError("container_id must be exact built-in str")
            if not _HEX64_PATTERN.match(self.container_id):
                raise ValueError("invalid container_id for present")
            if self.error_message is not None:
                raise ValueError("error_message must be None for present")

        elif self.status == "unowned_label":
            if self.container_id is None:
                raise ValueError("container_id required for unowned_label")
            if type(self.container_id) is not str:
                raise ValueError("container_id must be exact built-in str")
            if not _HEX64_PATTERN.match(self.container_id):
                raise ValueError("invalid container_id for unowned_label")

        elif self.status == "inspection_failure":
            if self.error_message is None:
                raise ValueError("error_message required for inspection_failure")
            if type(self.error_message) is not str:
                raise ValueError("error_message must be exact built-in str")
            if self.container_id is not None:
                raise ValueError("container_id must be None for inspection_failure")

        elif self.status == "ambiguous_output":
            if self.error_message is None:
                raise ValueError("error_message required for ambiguous_output")
            if type(self.error_message) is not str:
                raise ValueError("error_message must be exact built-in str")


ContainerCleanupOutcome = Literal[
    "confirmed_removed",
    "confirmed_absent",
    "unowned_label",
    "inspection_failure",
    "removal_failure",
    "post_removal_confirmation_failure",
]

_Stage = Literal["inspect", "remove", "confirm"]

_STAGE_OUTCOMES: dict[str, frozenset[str]] = {
    "inspect": frozenset({"confirmed_absent", "unowned_label", "inspection_failure"}),
    "remove": frozenset({"removal_failure"}),
    "confirm": frozenset({"confirmed_removed", "post_removal_confirmation_failure"}),
}


@dataclass(frozen=True)
class ContainerCleanupResult:
    """Immutable result of container cleanup attempt.

    Attributes:
        outcome: One of the closed set of cleanup outcomes
        stage: The stage that produced this result
        confirmed: Whether cleanup was confirmed successful
        inspect_rc: Return code from inspect phase (if applicable)
        remove_rc: Return code from remove phase (if applicable)

    Contract:
        - Frozen/immutable
        - outcome must be from closed set
        - stage must be from closed set
        - confirmed must be exact bool
        - Return codes must be exact int (reject bool)
        - outcome must be valid for stage

    Security: repr/str do not expose return codes to avoid
    encoding Docker-derived values in logs/tracebacks.
    """

    outcome: ContainerCleanupOutcome
    stage: _Stage
    confirmed: bool
    inspect_rc: int | None = None
    remove_rc: int | None = None

    def __repr__(self) -> str:
        """Redacted repr - does not disclose return codes."""
        return f"ContainerCleanupResult(outcome={self.outcome!r}, stage={self.stage!r}, confirmed={self.confirmed})"

    def __str__(self) -> str:
        """Redacted str - does not disclose return codes."""
        return f"ContainerCleanupResult(outcome={self.outcome})"

    def __post_init__(self) -> None:
        """Enforce closed contract with outcome-to-confirmed coherence."""
        if type(self.confirmed) is not bool:
            raise ValueError("confirmed must be exact built-in bool")

        valid_outcomes = {
            "confirmed_removed",
            "confirmed_absent",
            "unowned_label",
            "inspection_failure",
            "removal_failure",
            "post_removal_confirmation_failure",
        }
        if self.outcome not in valid_outcomes:
            raise ValueError(f"unknown outcome: {self.outcome}")

        valid_stages = {"inspect", "remove", "confirm"}
        if self.stage not in valid_stages:
            raise ValueError(f"unknown stage: {self.stage}")

        if self.outcome not in _STAGE_OUTCOMES.get(self.stage, frozenset()):
            raise ValueError(f"outcome {self.outcome} not valid for stage {self.stage}")

        if self.inspect_rc is not None:
            if type(self.inspect_rc) is not int:
                raise ValueError("inspect_rc must be exact built-in int")
        if self.remove_rc is not None:
            if type(self.remove_rc) is not int:
                raise ValueError("remove_rc must be exact built-in int")

        # outcome-to-confirmed coherence
        if self.outcome == "confirmed_removed" and not self.confirmed:
            raise ValueError("confirmed must be True for confirmed_removed")
        if self.outcome == "confirmed_absent" and not self.confirmed:
            raise ValueError("confirmed must be True for confirmed_absent")
        if self.outcome == "removal_failure" and self.confirmed:
            raise ValueError("confirmed must be False for removal_failure")
        if self.outcome == "inspection_failure" and self.confirmed:
            raise ValueError("confirmed must be False for inspection_failure")
        if self.outcome == "unowned_label" and self.confirmed:
            raise ValueError("confirmed must be False for unowned_label")
        if self.outcome == "post_removal_confirmation_failure" and self.confirmed:
            raise ValueError(
                "confirmed must be False for post_removal_confirmation_failure"
            )

        # outcome-specific field requirements
        if self.outcome == "removal_failure" and self.remove_rc is None:
            raise ValueError("remove_rc required for removal_failure")
        if self.remove_rc is not None and type(self.remove_rc) is not int:
            raise ValueError("remove_rc must be exact built-in int")


__all__ = [
    "AUTHORIZATION_FLAG",
    "SENSITIVE_ENV_VARS",
    "_is_separately_authorized",
    "_require_authorization",
    "_sanitized_env_copy",
    "_make_docker_env",
    "SafeDockerEnv",
    "_parse_host_port",
    "_validate_container_name",
    "_validate_host_port_str",
    "_validate_returncode",
    "_generate_ownership_token",
    "_validate_ownership_token",
    "_validate_container_id",
    "_normalize_docker_run_id",
    "_validate_env_value",
    "_validate_disposable_image",
    "TRUSTED_DISPOSABLE_IMAGE",
    "TRUSTED_IMAGE_CAPABILITIES",
    "ContainerPresenceResult",
    "ContainerCleanupResult",
    "ContainerCleanupOutcome",
    "ContainerPresenceStatus",
]
