"""Pure container-cleanup and failure-composition helpers for Task #87.

Extracted from ``_real_e2a_reconciler_lifecycle`` to keep that module
under the 800-line limit.  These functions are mechanically tested by
``test_real_e2a_reconciler_lifecycle_unit``.
"""

from __future__ import annotations

import builtins
import subprocess
from collections.abc import Callable

from ._real_e2a_reconciler_types import ContainerCleanupResult

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CLEANUP_FAILURE_MESSAGE = "connection cleanup failed"
_LIFECYCLE_CLEANUP_MESSAGE = "label-gated cleanup failed"

# Docker / container constants (shared with lifecycle module).
_CONTAINER_LABEL_KEY = "okf.task"
_CONTAINER_LABEL_VALUE = "87.real.e2a.acceptance"

# Type alias: any object with .run(command, ...) and the same signature.
RunDocker = Callable[..., subprocess.CompletedProcess[str]]


# ---------------------------------------------------------------------------
# Failure composition
# ---------------------------------------------------------------------------


def _compose_failures(
    primary: BaseException | None,
    cleanup_msg: str,
) -> BaseException | None:
    """Compose a failure group from primary and cleanup exceptions.

    Rules:
    - If primary is None: return RuntimeError(cleanup_msg) for cleanup-only failure
    - If primary is not None: return ExceptionGroup or BaseExceptionGroup
    - Group contains [exact original primary, RuntimeError(cleanup_msg)]
    - All Exception members -> ExceptionGroup
    - Any non-Exception BaseException member -> BaseExceptionGroup
    - Never exposes raw cleanup exception/message

    This helper is the single source of truth for failure composition.
    """
    cleanup_exc = RuntimeError(cleanup_msg)

    if primary is None:
        # Cleanup-only failure
        return cleanup_exc

    # Both primary and cleanup failed
    # Choose group type based on member types
    members: list[BaseException] = [primary, cleanup_exc]

    # Check if all members are Exception (not just BaseException)
    if all(isinstance(m, Exception) for m in members):
        # Type narrow: we know all are Exception
        # Create a new list with proper type for ExceptionGroup
        exc_members: list[Exception] = []
        for m in members:
            assert isinstance(m, Exception)
            exc_members.append(m)
        return builtins.ExceptionGroup("failure group", exc_members)
    else:
        return builtins.BaseExceptionGroup("failure group", members)


# ---------------------------------------------------------------------------
# Returncode validation
# ---------------------------------------------------------------------------


def _validate_exact_returncode(rc: object) -> int:
    """Validate returncode is exact built-in int (reject bool/subclass).

    Returns the validated int, or -1 for invalid values.
    """
    if type(rc) is int:
        return rc
    # Invalid: return sentinel value
    return -1


# ---------------------------------------------------------------------------
# Exact-name container listing
# ---------------------------------------------------------------------------


def _exact_name_list_container(
    container_name: str,
    *,
    run: RunDocker,
) -> tuple[int, bool]:
    """Exact-name container listing using ``docker container ls``.

    Returns (returncode, exists) where:
    - returncode is validated exact int (or -1 for invalid)
    - exists is True only if exact-name match found

    Uses ``docker container ls --filter name=^container_name$`` for exact matching.
    """
    try:
        result = run(
            [
                "container",
                "ls",
                "--all",
                "--filter",
                f"name=^{container_name}$",
                "--format",
                "{{.Names}}",
            ]
        )
    except Exception:
        # Runner exception - cannot confirm
        return (-1, False)

    # Validate returncode is exact int
    rc = _validate_exact_returncode(result.returncode)

    if rc != 0:
        # Docker daemon failure
        return (rc, False)

    # Check for exact-name match
    lines = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
    # Exact match: single line that exactly equals container_name
    exists = len(lines) == 1 and lines[0] == container_name
    return (rc, exists)


# ---------------------------------------------------------------------------
# Container removal
# ---------------------------------------------------------------------------


def _check_container_ownership(
    container_name: str,
    *,
    run: RunDocker,
) -> tuple[int, bool]:
    """Check if container exists and has our ownership label.

    Returns (returncode, is_owned) where:
    - returncode is 0 on success, or error code
    - is_owned is True only if container exists with our label
    """
    # First check if container exists
    list_rc, exists = _exact_name_list_container(container_name, run=run)
    if list_rc != 0:
        return (list_rc, False)
    if not exists:
        return (0, False)  # Container absent

    # Check ownership label
    try:
        inspect = run(
            [
                "inspect",
                "--format",
                f'{{{{ index .Config.Labels "{_CONTAINER_LABEL_KEY}" }}}}',
                container_name,
            ]
        )
    except Exception:
        return (-1, False)

    inspect_rc = _validate_exact_returncode(inspect.returncode)
    if inspect_rc != 0:
        return (inspect_rc, False)

    # Check label value
    if inspect.stdout.strip() != _CONTAINER_LABEL_VALUE:
        return (0, False)  # Exists but not owned

    return (0, True)  # Owned


def _attempt_removal_and_verify(
    container_name: str,
    *,
    run: RunDocker,
) -> tuple[int, bool]:
    """Attempt container removal and verify absence.

    Returns (remove_rc, confirmed) where:
    - remove_rc is 0 on success, or error code
    - confirmed is True only if absence is verified
    """
    try:
        remove = run(["rm", "--force", container_name])
    except Exception:
        return (-1, False)

    remove_rc = _validate_exact_returncode(remove.returncode)
    if remove_rc != 0:
        return (remove_rc, False)

    # Verify absence
    confirm_rc, still_exists = _exact_name_list_container(container_name, run=run)
    if confirm_rc != 0:
        return (0, False)

    return (0, not still_exists)


def _build_inspection_failure_result(own_rc: int) -> ContainerCleanupResult:
    """Build result for inspection failure."""
    return ContainerCleanupResult(
        outcome="inspection_failure",
        stage="inspect",
        confirmed=False,
        inspect_rc=own_rc,
    )


def _build_confirmed_absent_result() -> ContainerCleanupResult:
    """Build result for confirmed absent container."""
    return ContainerCleanupResult(
        outcome="confirmed_absent",
        stage="inspect",
        confirmed=True,
        inspect_rc=0,
    )


def _build_unowned_label_result() -> ContainerCleanupResult:
    """Build result for unowned container."""
    return ContainerCleanupResult(
        outcome="unowned_label",
        stage="inspect",
        confirmed=False,
        inspect_rc=0,
    )


def _build_removal_failure_result(remove_rc: int) -> ContainerCleanupResult:
    """Build result for removal failure."""
    return ContainerCleanupResult(
        outcome="removal_failure",
        stage="remove",
        confirmed=False,
        inspect_rc=0,
        remove_rc=remove_rc,
    )


def _build_confirmation_failure_result() -> ContainerCleanupResult:
    """Build result for post-removal confirmation failure."""
    return ContainerCleanupResult(
        outcome="post_removal_confirmation_failure",
        stage="confirm",
        confirmed=False,
        inspect_rc=0,
        remove_rc=0,
    )


def _build_confirmed_removed_result() -> ContainerCleanupResult:
    """Build result for confirmed removed container."""
    return ContainerCleanupResult(
        outcome="confirmed_removed",
        stage="confirm",
        confirmed=True,
        inspect_rc=0,
        remove_rc=0,
    )


def _remove_owned_container(
    container_name: str,
    *,
    run: RunDocker,
) -> ContainerCleanupResult:
    """Attempt removal of an owned container; return typed result.

    Uses MECHANICAL EXACT-NAME PROOF:
    - ``docker container ls --filter name=^container_name$`` for exact matching
    - Empty result = confirmed absent (not substring matching)
    - Label must match exactly before removal

    Outcomes:
    - confirmed_removed: Container existed, was removed, absence verified.
    - confirmed_absent: Container never existed (exact-name listing empty).
    - unowned_label: Container exists but lacks our ownership label.
    - inspection_failure: Docker daemon error during initial listing.
    - removal_failure: Removal command failed.
    - post_removal_confirmation_failure: Removal succeeded but still exists.

    Never deletes an unowned container.
    All return codes are exact built-in int (bool rejected).
    """
    own_rc, is_owned = _check_container_ownership(container_name, run=run)

    if own_rc != 0:
        return _build_inspection_failure_result(own_rc)

    if not is_owned:
        list_rc, exists = _exact_name_list_container(container_name, run=run)
        if list_rc != 0:
            return _build_inspection_failure_result(list_rc)
        if not exists:
            return _build_confirmed_absent_result()
        return _build_unowned_label_result()

    remove_rc, confirmed = _attempt_removal_and_verify(container_name, run=run)

    if remove_rc != 0:
        return _build_removal_failure_result(remove_rc)

    if not confirmed:
        return _build_confirmation_failure_result()

    return _build_confirmed_removed_result()


__all__ = [
    "_CLEANUP_FAILURE_MESSAGE",
    "_LIFECYCLE_CLEANUP_MESSAGE",
    "_CONTAINER_LABEL_KEY",
    "_CONTAINER_LABEL_VALUE",
    "RunDocker",
    "_compose_failures",
    "_validate_exact_returncode",
    "_exact_name_list_container",
    "_remove_owned_container",
]
