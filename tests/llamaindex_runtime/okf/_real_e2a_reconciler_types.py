"""Typed structures for Task #87 E2a reconciler acceptance tests.

This module owns the frozen dataclasses and literal types used across
the lifecycle, testkit, and acceptance modules.

Important: This module defines ContainerCleanupOutcome for container lifecycle.
For reconciliation Outcome, import from llamaindex_runtime.okf.e2a_contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal


def _is_exact_int(value: object) -> bool:
    """Return True only for exact built-in int (reject bool/subclasses)."""
    return type(value) is int


# Exact outcome contract for container cleanup results (NOT reconciliation)
ContainerCleanupOutcome = Literal[
    "confirmed_removed",
    "confirmed_absent",
    "unowned_label",
    "inspection_failure",
    "removal_failure",
    "post_removal_confirmation_failure",
]

# Closed set of valid stages
_Stage = Literal["inspect", "remove", "confirm"]

# Valid outcomes for each stage (closed contract)
_STAGE_OUTCOMES: dict[str, frozenset[str]] = {
    "inspect": frozenset({"confirmed_absent", "unowned_label", "inspection_failure"}),
    "remove": frozenset({"removal_failure"}),
    "confirm": frozenset({"confirmed_removed", "post_removal_confirmation_failure"}),
}


@dataclass(frozen=True)
class ContainerCleanupResult:
    """Immutable result of attempting owned-container cleanup.

    confirmed=True only when removal succeeded or absence was mechanically proven.
    All diagnostics are fixed text; no raw values are exposed.

    Closed contract (enforced in __post_init__):
    - outcome must be a known ContainerCleanupOutcome literal
    - stage must be a valid _Stage for the outcome
    - confirmed must be exact built-in bool
    - inspect_rc/remove_rc must be exact built-in int (reject bool)
    - Each outcome has strict rc requirements; extra rc fields are rejected
    - Unknown outcome/stage values raise ValueError
    """

    outcome: ContainerCleanupOutcome
    stage: _Stage
    confirmed: bool
    inspect_rc: int | None = None
    remove_rc: int | None = None

    def __post_init__(self) -> None:
        """Enforce closed outcome-stage-confirmed-rc contract."""
        # Validate confirmed is exact bool
        if type(self.confirmed) is not bool:
            raise ValueError("confirmed must be exact built-in bool")

        # Validate outcome is known
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

        # Validate stage is known
        valid_stages = {"inspect", "remove", "confirm"}
        if self.stage not in valid_stages:
            raise ValueError(f"unknown stage: {self.stage}")

        # Validate stage-outcome coherence
        if self.outcome not in _STAGE_OUTCOMES.get(self.stage, frozenset()):
            raise ValueError(f"outcome {self.outcome} not valid for stage {self.stage}")

        # Validate exact built-in int for all rc values (reject bool/subclass)
        if self.inspect_rc is not None:
            if not _is_exact_int(self.inspect_rc):
                raise ValueError("inspect_rc must be exact built-in int")
        if self.remove_rc is not None:
            if not _is_exact_int(self.remove_rc):
                raise ValueError("remove_rc must be exact built-in int")

        # Outcome-specific invariants
        if self.outcome == "confirmed_removed":
            if not self.confirmed:
                raise ValueError("confirmed_removed requires confirmed=True")
            if self.inspect_rc != 0:
                raise ValueError("confirmed_removed requires inspect_rc=0")
            if self.remove_rc != 0:
                raise ValueError("confirmed_removed requires remove_rc=0")
            # Extra fields forbidden
            if self.inspect_rc is None or self.remove_rc is None:
                raise ValueError("confirmed_removed requires both rc fields")

        elif self.outcome == "confirmed_absent":
            if not self.confirmed:
                raise ValueError("confirmed_absent requires confirmed=True")
            # confirmed_absent: container does not exist (exact-name listing empty)
            # rc=0 means successful query with empty result
            if self.inspect_rc is None:
                raise ValueError("confirmed_absent requires inspect_rc")
            if not _is_exact_int(self.inspect_rc):
                raise ValueError("confirmed_absent requires exact int inspect_rc")
            if self.inspect_rc != 0:
                raise ValueError("confirmed_absent requires inspect_rc=0")
            if self.remove_rc is not None:
                raise ValueError("confirmed_absent must not have remove_rc")

        elif self.outcome == "unowned_label":
            if self.confirmed:
                raise ValueError("unowned_label requires confirmed=False")
            if self.inspect_rc is None or self.inspect_rc != 0:
                raise ValueError("unowned_label requires inspect_rc=0")
            if self.remove_rc is not None:
                raise ValueError("unowned_label must not have remove_rc")

        elif self.outcome == "inspection_failure":
            if self.confirmed:
                raise ValueError("inspection_failure requires confirmed=False")
            if self.inspect_rc is None:
                raise ValueError("inspection_failure requires inspect_rc")
            if not _is_exact_int(self.inspect_rc):
                raise ValueError("inspection_failure requires exact int inspect_rc")
            if self.remove_rc is not None:
                raise ValueError("inspection_failure must not have remove_rc")

        elif self.outcome == "removal_failure":
            if self.confirmed:
                raise ValueError("removal_failure requires confirmed=False")
            if self.inspect_rc is None or self.inspect_rc != 0:
                raise ValueError("removal_failure requires inspect_rc=0")
            if self.remove_rc is None:
                raise ValueError("removal_failure requires remove_rc")
            if not _is_exact_int(self.remove_rc):
                raise ValueError("removal_failure requires exact int remove_rc")

        elif self.outcome == "post_removal_confirmation_failure":
            if self.confirmed:
                raise ValueError(
                    "post_removal_confirmation_failure requires confirmed=False"
                )
            if self.inspect_rc is None or self.inspect_rc != 0:
                raise ValueError(
                    "post_removal_confirmation_failure requires inspect_rc=0"
                )
            if self.remove_rc is None or self.remove_rc != 0:
                raise ValueError(
                    "post_removal_confirmation_failure requires remove_rc=0"
                )


@dataclass(frozen=True)
class ScopeSnapshot:
    """Immutable observation of database state for a single version scope.

    Defensive copies are made at construction time; input mappings are frozen.
    Values are validated as exact built-in nonnegative int (bool rejected).
    digests are validated as non-empty str.
    denylist permits None for physically absent tables.

    Mutation of original input dicts after construction does NOT affect snapshot.
    This is achieved by unwrapping any MappingProxyType and creating fresh copies.
    """

    counts: MappingProxyType[str, int]
    digests: MappingProxyType[str, str]
    denylist: MappingProxyType[str, int | None]
    sync_ts: str | None

    def __post_init__(self) -> None:
        """Defensive-copy all input mappings and validate contents.

        IMPORTANT: This unwraps any MappingProxyType wrappers and creates
        fresh independent copies, ensuring the snapshot is immune to
        mutation of the original dicts.
        """
        # Defensive copy: unwrap any MappingProxyType and create fresh copy
        # This ensures mutation of original dict does NOT affect snapshot
        counts_copy = dict(self.counts)  # Creates independent copy
        digests_copy = dict(self.digests)
        denylist_copy = dict(self.denylist)

        # Use object.__setattr__ since dataclass is frozen
        object.__setattr__(self, "counts", MappingProxyType(counts_copy))
        object.__setattr__(self, "digests", MappingProxyType(digests_copy))
        object.__setattr__(self, "denylist", MappingProxyType(denylist_copy))

        # Validate counts: exact nonnegative int
        for key, value in self.counts.items():
            if not _is_exact_int(value):
                raise ValueError(f"counts[{key}] must be exact built-in int")
            if value < 0:
                raise ValueError(f"counts[{key}] must be nonnegative")

        # Validate digests: non-empty str
        for digest_key, digest_value in self.digests.items():
            if type(digest_value) is not str:
                raise ValueError(f"digests[{digest_key}] must be exact built-in str")
            if not digest_value:
                raise ValueError(f"digests[{digest_key}] must be non-empty")

        # Validate denylist: exact nonnegative int or None
        for denylist_key, denylist_value in self.denylist.items():
            if denylist_value is not None:
                if not _is_exact_int(denylist_value):
                    raise ValueError(
                        f"denylist[{denylist_key}] must be exact built-in int or None"
                    )
                if denylist_value < 0:
                    raise ValueError(f"denylist[{denylist_key}] must be nonnegative")

        # Validate sync_ts: str or None
        if self.sync_ts is not None:
            if type(self.sync_ts) is not str:
                raise ValueError("sync_ts must be exact built-in str or None")


def make_scope_snapshot(
    counts: dict[str, int],
    digests: dict[str, str],
    denylist: dict[str, int | None],
    sync_ts: str | None,
) -> ScopeSnapshot:
    """Construct a ScopeSnapshot with defensive copies of input mappings.

    This ensures mutation of original dicts does NOT affect the snapshot.
    The dataclass __post_init__ will create additional defensive copies,
    so this factory is the preferred entry point.
    """
    return ScopeSnapshot(
        counts=MappingProxyType(dict(counts)),
        digests=MappingProxyType(dict(digests)),
        denylist=MappingProxyType(dict(denylist)),
        sync_ts=sync_ts,
    )


__all__ = [
    "ContainerCleanupOutcome",
    "ContainerCleanupResult",
    "ScopeSnapshot",
    "make_scope_snapshot",
]
