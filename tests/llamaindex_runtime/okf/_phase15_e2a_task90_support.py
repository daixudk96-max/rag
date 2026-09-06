"""Process-local structural binding and controlled-producer surface for Task #90.

Non-collected (underscore prefix) support. This module owns the honest
process-local structural binding object and the single-use producer build
token. It is PURE: no environment variable access, no database access, no
Docker access, no test-framework machinery, and no import of the protected
historical verification runner.

Security contract:

- The binding can only be built with a single-use ``_BuildToken`` returned
  by ``acquire_build_token``; a plain dict, a serializer-only artifact, a
  hand-built exact-type result without a producer binding, or a fake/stub
  reconciler route is rejected at construction time.
- The binding holds the EXACT ``E2aReconciliationResult`` object identity
  (``is``) returned by the real reconciler, the invocation UUID, the
  canonical digest of the FULL result fields derived at runtime via
  ``dataclasses.fields(E2aReconciliationResult)``, and the independent
  fresh-observer full-collection scope snapshot plus its canonical digest.
- ``verify`` re-derives both digests from the held objects; ``verify_exact``
  re-checks object identity. A tampered serialized artifact is just a plain
  dict and cannot be rebuilt into a verifiable binding (no rebuild API).
- No credential, URI, target, or raw corpus text is ever stored or rendered;
  ``error_reason`` carries only a bounded ``code:ClassName`` diagnostic.
"""

from __future__ import annotations

from dataclasses import fields
from typing import Mapping
from uuid import uuid4

from llamaindex_runtime.okf.e2a_contracts import (
    E2aReconciliationResult,
    canonical_json,
    canonical_json_sha256,
)

from ._phase15_e2a_task90_types import (
    TASK90_CACHE_TABLES,
    TASK90_DENYLIST_TABLES,
    TASK90_PRIMARY_TABLES,
    TASK90_VALID_OUTCOMES,
    Task90ScopeSnapshot,
)

TASK90_BINDING_SCHEMA = "e2a-task90-binding-v1"
TASK90_ARTIFACT_SCHEMA = "e2a-task90-binding-artifact-v1"
# The only route the controlled producer may certify: the default
# ``E2aReconciler()`` (which defaults its repository to a real
# ``E2aMaterializationRepository()``) with NO injected fake/stub repository
# or builder. Any other route string is rejected by the binding factory.
TASK90_CANONICAL_ROUTE = "default-e2a-reconciler-default-e2a-materialization-repository"


def _result_fields_digest(result: E2aReconciliationResult) -> str:
    """Canonical SHA-256 of the FULL E2aReconciliationResult field surface.

    The field names are derived at runtime via
    ``dataclasses.fields(E2aReconciliationResult)``, so the digest
    automatically covers every field of the production contract and a
    removed, renamed, or invented field cannot silently slip out of the
    claimed surface. A separate ordered ``field_names`` tuple is included so
    a field reordering also changes the digest.
    """
    names = tuple(field.name for field in fields(E2aReconciliationResult))
    payload = {
        "schema": TASK90_BINDING_SCHEMA,
        "field_names": names,
        "values": {
            field.name: getattr(result, field.name)
            for field in fields(E2aReconciliationResult)
        },
    }
    return canonical_json_sha256(payload)


def _scope_snapshot_digest(snapshot: Task90ScopeSnapshot) -> str:
    """Canonical SHA-256 of the complete Task90ScopeSnapshot field surface.

    Covers the full 15-table primary counts, the per-table digests, the
    10-denylist existence-aware map, the 3 cache-invalidation counts, and
    the optional sync timestamp.
    """
    payload = {
        "schema": TASK90_BINDING_SCHEMA,
        "primary_counts": dict(snapshot.counts),
        "primary_digests": dict(snapshot.digests),
        "denylist": {
            key: (None if value is None else value)
            for key, value in snapshot.denylist.items()
        },
        "cache_invalidation": dict(snapshot.cache_invalidation),
        "sync_ts": snapshot.sync_ts,
    }
    return canonical_json_sha256(payload)


class _BuildToken:
    """Single-use capability for building exactly one Task90EvidenceBinding.

    Carries the invocation UUID and is consumed on the first successful
    binding build; a second build with the same token is a stale-invocation
    error. Only ``acquire_build_token`` can mint a token.
    """

    __slots__ = ("_invocation_id", "_consumed")

    def __init__(self) -> None:
        self._invocation_id = str(uuid4())
        self._consumed = False

    @property
    def invocation_id(self) -> str:
        return self._invocation_id

    @property
    def consumed(self) -> bool:
        return self._consumed


def acquire_build_token() -> _BuildToken:
    """Mint a fresh single-use producer build token for one invocation."""
    return _BuildToken()


class Task90EvidenceBinding:
    """Process-local structural evidence binding for the Task #90 live proof.

    The binding is deliberately NOT constructible from a dict, an artifact,
    or a hand-built result without a producer token. It holds:

    - ``result``: the EXACT ``E2aReconciliationResult`` instance returned by
      the real reconciler (identity-checked via ``verify_exact_result``),
    - ``invocation_id``: the UUID of the single producer invocation,
    - ``result_digest``: canonical SHA-256 of the full result field surface,
    - ``scope_snapshot``: the independent fresh-observer
      ``Task90ScopeSnapshot``,
    - ``scope_digest``: canonical SHA-256 of the snapshot surface.

    ``verify`` re-derives both digests from the held objects; any mismatch
    fails closed. ``verify_exact_result`` / ``verify_exact_scope`` require
    the exact object identity, so a value-equal forged copy is rejected.
    ``artifact_dict`` renders a redacted canonical artifact (no credentials,
    URIs, targets, error text, or raw corpus content).
    """

    __slots__ = (
        "_token",
        "_invocation_id",
        "_result",
        "_result_digest",
        "_scope_snapshot",
        "_scope_digest",
        "_outcome",
    )

    def __init__(
        self,
        *,
        token: _BuildToken,
        result: E2aReconciliationResult,
        scope_snapshot: Task90ScopeSnapshot,
        route: str,
    ) -> None:
        if type(token) is not _BuildToken:
            raise TypeError("task90_binding_token_required")
        if token.consumed:
            raise ValueError("task90_invocation_stale")
        if type(result) is not E2aReconciliationResult:
            raise TypeError("task90_binding_result_must_be_exact")
        if result.outcome not in TASK90_VALID_OUTCOMES:
            raise ValueError("task90_outcome_unsupported")
        if type(scope_snapshot) is not Task90ScopeSnapshot:
            raise TypeError("task90_binding_scope_must_be_exact")
        if route != TASK90_CANONICAL_ROUTE:
            raise ValueError("task90_route_not_controlled")
        object.__setattr__(token, "_consumed", True)
        self._token = token
        self._invocation_id = token.invocation_id
        self._result = result
        self._result_digest = _result_fields_digest(result)
        self._scope_snapshot = scope_snapshot
        self._scope_digest = _scope_snapshot_digest(scope_snapshot)
        self._outcome = result.outcome

    @property
    def invocation_id(self) -> str:
        return self._invocation_id

    @property
    def outcome(self) -> str:
        return self._outcome

    @property
    def result(self) -> E2aReconciliationResult:
        return self._result

    @property
    def result_digest(self) -> str:
        return self._result_digest

    @property
    def scope_snapshot(self) -> Task90ScopeSnapshot:
        return self._scope_snapshot

    @property
    def scope_digest(self) -> str:
        return self._scope_digest

    def verify(self) -> None:
        """Re-derive both digests from the held objects and fail closed.

        Recomputes the full-field result digest and the full-collection
        scope digest from the exact held objects and requires them to equal
        the stored digests; also re-pins the outcome allowlist and the full
        15/10/3 table coverage. Returns None on success.
        """
        if self._outcome not in TASK90_VALID_OUTCOMES:
            raise ValueError("task90_outcome_unsupported")
        if self._result_digest != _result_fields_digest(self._result):
            raise ValueError("task90_result_digest_mismatch")
        if self._scope_digest != _scope_snapshot_digest(self._scope_snapshot):
            raise ValueError("task90_scope_digest_mismatch")
        if set(self._scope_snapshot.counts) != TASK90_PRIMARY_TABLES:
            raise ValueError("task90_primary_tables_incomplete")
        if set(self._scope_snapshot.denylist) != TASK90_DENYLIST_TABLES:
            raise ValueError("task90_denylist_incomplete")
        if set(self._scope_snapshot.cache_invalidation) != TASK90_CACHE_TABLES:
            raise ValueError("task90_cache_tables_incomplete")

    def verify_exact_result(self, candidate: object) -> bool:
        """True only when the candidate IS the exact held result object."""
        return candidate is self._result

    def verify_exact_scope(self, candidate: object) -> bool:
        """True only when the candidate IS the exact held scope snapshot."""
        return candidate is self._scope_snapshot

    def artifact_dict(self) -> Mapping[str, object]:
        """Redacted canonical artifact dict for the controlled invocation.

        Contains only structural metadata: schema, invocation UUID, outcome,
        manifest SHA, the two digests, the full primary/denylist counts, and
        the rerun-no-op flag. It never contains credentials, URIs, targets,
        error text, or raw corpus content, and it is NOT re-constructible
        into a binding (no rebuild API exists).
        """
        return {
            "schema": TASK90_ARTIFACT_SCHEMA,
            "binding_schema": TASK90_BINDING_SCHEMA,
            "invocation_id": self._invocation_id,
            "outcome": self._outcome,
            "manifest_sha256": self._result.manifest_sha256,
            "result_digest": self._result_digest,
            "scope_digest": self._scope_digest,
            "primary_counts": dict(self._scope_snapshot.counts),
            "denylist_counts": {
                key: (None if value is None else value)
                for key, value in self._scope_snapshot.denylist.items()
            },
            "rerun_no_op": self._outcome == "no_op",
        }


def build_evidence_binding(
    token: _BuildToken,
    result: E2aReconciliationResult,
    scope_snapshot: Task90ScopeSnapshot,
    *,
    route: str = TASK90_CANONICAL_ROUTE,
) -> Task90EvidenceBinding:
    """Build a verifiable Task90EvidenceBinding for one controlled invocation.

    The token is single-use: building a binding consumes it, so a second
    build from the same invocation is a stale-invocation error. Any caller
    that is not the controlled producer lacks a minted token and cannot
    construct a binding.
    """
    return Task90EvidenceBinding(
        token=token,
        result=result,
        scope_snapshot=scope_snapshot,
        route=route,
    )


def _error_reason(code: str, failure: Exception) -> str:
    """Bounded class/type-only diagnostic; never echoes exception text.

    The only string that may leave the observation surface is a fixed
    ``code`` plus the exception's class name. No URL, credential, target,
    or raw corpus text is ever included.
    """
    return f"{code}:{type(failure).__name__}"


def _canonical_artifact_json(artifact: Mapping[str, object]) -> str:
    """Canonical JSON of a redacted artifact dict (for a stable artifact hash)."""
    return canonical_json(artifact)


def _artifact_digest(artifact: Mapping[str, object]) -> str:
    """SHA-256 of the canonical artifact JSON (structural, non-cryptographic claim)."""
    return canonical_json_sha256(artifact)


__all__ = [
    "TASK90_BINDING_SCHEMA",
    "TASK90_ARTIFACT_SCHEMA",
    "TASK90_CANONICAL_ROUTE",
    "Task90EvidenceBinding",
    "_BuildToken",
    "acquire_build_token",
    "build_evidence_binding",
    "_result_fields_digest",
    "_scope_snapshot_digest",
    "_error_reason",
    "_canonical_artifact_json",
    "_artifact_digest",
]
