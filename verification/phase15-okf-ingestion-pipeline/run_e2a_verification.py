"""E2A verification result consumer and evidence serializer.

Phase 15-04: Typed result consumer, NOT a second reconciler, NOT an evidence fabricator.

This module consumes measured E2aReconciliationResult values and emits redacted evidence.
It does NOT fabricate evidence, does NOT inspect/print environment values, and does NOT
open external services. Database acceptance requires separate authorization.

HARD CONSTRAINT: Default selector is non-DB. Without separate disposable authorization,
emit ONLY `blocked_not_executed` with NO connection attempt.

Wave 1 Acceptance Gate:
    The admit_evidence_for_acceptance() function FAILS CLOSED for ALL inputs.
    It produces NO acceptance artifacts in Wave 1.
    Future Wave 2 will implement actual E2aReconciler.reconcile() + disposable target attestation.
"""

from __future__ import annotations

import posixpath
import re
from typing import Any, Final

from llamaindex_runtime.okf.e2a_contracts import E2aReconciliationResult


class Phase15AcceptanceBlockedError(Exception):
    """Exception raised when Phase 15 acceptance is blocked.

    Wave 1: Always raised, regardless of input.
    Wave 2: Will be raised only when actual provenance/disposable validation fails.

    This exception does NOT echo or log sensitive evidence field values.
    """

    def __init__(
        self, message: str = "Phase 15 acceptance blocked: Wave 1 gate is fail-closed"
    ) -> None:
        super().__init__(message)


# Historical script denylist (exactly 9 routes)
# These routes are rejected by the Phase 15 acceptance boundary
# All paths use forward slashes for consistency; normalization handles backslashes
HISTORICAL_DENYLIST: Final[tuple[str, ...]] = (
    "verification/phase10-real-docx-retrieval-validation/run_validation.py",
    "verification/phase10-real-docx-retrieval-validation/reconstruct_transcript.py",
    "verification/phase11-level-agnostic-hotspot-cluster-tracking/run_validation.py",
    "verification/phase13-real-validation-2026-06-26/run_validation.py",
    "verification/phase13-real-validation-2026-06-26/diagnose_q18_live_path.py",
    "verification/phase14-new-doc-validation/run_validation.py",
    "verification/phase14-new-doc-validation/full_flow_diagnosis.py",
    "verification/phase14-new-doc-validation/verify_autocommit_fix.py",
    "verification/real-document-validation-2026-06-23/run_validation.py",
)


def _normalize_path_for_denylist(path: str) -> str:
    """Normalize path for denylist comparison (cross-platform, case-insensitive).

    Converts backslashes to forward slashes, strips leading/trailing whitespace,
    collapses doubled separators, and resolves dot segments (``.`` and ``..``)
    lexically, then lowercases for case-insensitive matching.

    This is a PURELY LEXICAL normalization (uses ``posixpath.normpath``). It
    performs NO filesystem access, no symlink resolution, and no absolute-path
    canonicalization. Lexical dot-segment resolution prevents denylist bypass
    via ``./`` or ``../`` path manipulation.

    HOSTILE-SUBCLASS SAFETY: Uses explicit base-class ``str`` method dispatch
    (``str.replace``, ``str.strip``, ``str.lower``) to bypass any str subclass
    overrides that could raise attacker-controlled exceptions or leak data.
    """
    # Use base-class str methods to bypass hostile subclass overrides.
    # str.replace(s, old, new) calls the C-level implementation directly,
    # never dispatching to a subclass override.
    normalized = str.replace(path, "\\", "/")
    normalized = str.strip(normalized)
    # Lexically collapse doubled separators and resolve dot segments (no FS access)
    normalized = posixpath.normpath(normalized)
    normalized = str.lower(normalized)
    return normalized


def is_historical_route_denied(route: str) -> bool:
    """Check if a route is in the historical script denylist.

    Args:
        route: Repo-relative path to check (forward or backslash format).

    Returns:
        True if route is in denylist, False otherwise.

    HOSTILE-SUBCLASS SAFETY: Normalization uses base-class ``str`` methods.
    Membership check compares against a plain ``frozenset`` of normalized
    denylist routes, avoiding hostile ``__eq__``/``__hash__`` dispatch on
    the input route by relying on the plain-str normalization output.
    """
    normalized = _normalize_path_for_denylist(route)
    # Normalize all denylist paths too (for consistency). Build a plain
    # frozenset of plain strings for O(1) membership testing that never
    # dispatches to attacker-controlled __eq__/__hash__ on the input.
    normalized_denylist = frozenset(
        _normalize_path_for_denylist(r) for r in HISTORICAL_DENYLIST
    )
    # `normalized` is already a plain str from _normalize_path_for_denylist,
    # so frozenset.__contains__ uses plain str hash/eq. No hostile dispatch.
    return normalized in normalized_denylist


def admit_evidence_for_acceptance(evidence: dict[str, Any]) -> None:
    """Admit evidence for Phase 15 acceptance artifact emission.

    WAVE 1: FAILS CLOSED - Always raises Phase15AcceptanceBlockedError.
    Produces NO acceptance artifacts.

    This function does NOT read, echo, or log sensitive evidence field values.
    Acceptance requires actual E2aReconciler provenance plus disposable target authorization.

    Args:
        evidence: Evidence dict (ignored in Wave 1, always blocked).

    Raises:
        Phase15AcceptanceBlockedError: Always in Wave 1.

    HOSTILE-SUBCLASS SAFETY: Uses ``dict.get(evidence, key)`` (base-class
    dispatch) instead of ``evidence.get(key)`` to prevent dict subclasses
    that override ``get`` from raising attacker-controlled exceptions or
    leaking data before the fail-closed block.
    """
    # Guard against non-dict input: must still fail closed with static error,
    # never AttributeError from calling .get on non-dict types.
    if not isinstance(evidence, dict):
        raise Phase15AcceptanceBlockedError(
            "Phase 15 acceptance blocked: Wave 1 gate is fail-closed"
        )

    # Check for historical script source route indicator.
    # Only string routes are matched against the denylist. Arbitrary non-string
    # (and potentially hostile) _source_route values are NEVER converted via
    # bool()/str() - those attacker-controlled conversions could raise and
    # escape as a non-Phase15AcceptanceBlockedError. Non-string routes simply
    # fall through to the unconditional fail-closed block below.
    #
    # HOSTILE-SUBCLASS SAFETY: Use dict.get(evidence, key) (base-class dispatch)
    # instead of evidence.get(key) to bypass any dict subclass override of
    # get() that could raise attacker-controlled exceptions.
    source_route = dict.get(evidence, "_source_route")
    if isinstance(source_route, str) and is_historical_route_denied(source_route):
        raise Phase15AcceptanceBlockedError(
            "Historical script evidence is denied by acceptance boundary"
        )

    # Wave 1: Fail-closed gate
    # Wave 2 will implement actual E2aReconciler.reconcile(connection, desired)
    # and disposable target attestation admission
    raise Phase15AcceptanceBlockedError(
        "Phase 15 acceptance blocked: Wave 1 gate is fail-closed"
    )


# Whitelist of allowed evidence fields (from E2aReconciliationResult shape)
_EVIDENCE_WHITELIST = frozenset(
    {
        "outcome",
        "manifest_sha256",
        "primary_dml_by_table",
        "denylist_dml_counts",
        "comparator_parity",
        "stale_deletion_counts",
        "cache_invalidation_counts",
        "failure_audit_outcome",
        "post_rollback_failure_audit_outcome",
        "reconciliation_required",
        "quality_level",  # Only for smoke/comparator records
        "disposable_db_status",
        "typed_result",  # Format metadata (NOT provenance)
    }
)

# Patterns that MUST be redacted from evidence
# NOTE: Specific scheme patterns are O(n) with well-defined bounds.
# The credential URI pattern uses a bounded scanner, not regex.
_REDACTION_PATTERNS = [
    # PostgreSQL connection strings
    re.compile(r"postgres(?:ql)?://[^\s]+", re.IGNORECASE),
    # MySQL/MariaDB connection strings
    re.compile(r"mysql(?:s)?://[^\s]+", re.IGNORECASE),
    # Redis connection strings
    re.compile(r"redis(?:s)?://[^\s]+", re.IGNORECASE),
    # AMQP/RabbitMQ connection strings
    re.compile(r"amqp(?:s)?://[^\s]+", re.IGNORECASE),
    # MongoDB connection strings
    re.compile(r"mongodb(?:\+srv)?://[^\s]+", re.IGNORECASE),
    # Generic localhost references with ports (catches many DB patterns)
    re.compile(r"@localhost:\d+", re.IGNORECASE),
    # Environment variable names and values
    re.compile(
        r"(?:DATABASE_URL|OPENAI_API_KEY|ANTHROPIC_API_KEY|SECRET|PASSWORD)[^\s]*",
        re.IGNORECASE,
    ),
    # Invented authorization receipts
    re.compile(r"authorization_receipt|authorized_by", re.IGNORECASE),
]


def _redact_credential_uris_bounded(value: str) -> str:
    """Redact URIs containing credentials with bounded O(n) complexity.

    Uses a simple linear scanner instead of backtracking regex to avoid
    catastrophic O(n^2) behavior on long URI-like strings.

    Looks for scheme://user:pass@host patterns and replaces the entire URI.
    This is O(n) where n is the length of the input string.

    Args:
        value: String that may contain credential URIs.

    Returns:
        String with credential URIs replaced by [REDACTED].
    """
    result: list[str] = []
    i = 0
    n = len(value)

    while i < n:
        # Look for ://
        j = value.find("://", i)
        if j == -1:
            # No more :// found, append remaining string
            result.append(value[i:])
            break

        # Found :// at position j
        # Look backwards from j to find scheme start
        scheme_start = j
        while scheme_start > 0 and (
            value[scheme_start - 1].isalnum() or value[scheme_start - 1] in "+.-"
        ):
            scheme_start -= 1

        # Look forward to find URI end (whitespace or end of string)
        uri_end = j + 3
        while uri_end < n and not value[uri_end].isspace():
            uri_end += 1

        # Extract the authority portion (after ://)
        authority = value[j + 3 : uri_end]

        # Check if this URI contains credentials (@ before any path)
        # A credential URI has: scheme://user:pass@host
        # We look for @ in the authority portion
        has_credentials = "@" in authority

        if has_credentials:
            # Redact the entire URI from scheme_start to uri_end
            result.append(value[i:scheme_start])
            result.append("[REDACTED]")
            i = uri_end
        else:
            # No credentials - keep the URI as-is
            result.append(value[i:uri_end])
            i = uri_end

    return "".join(result)


def _redact_bare_authority_credentials(value: str) -> str:
    """Redact bare ``user:pass@host`` credentials (no scheme) with bounded O(n) scan.

    Detects whitespace-delimited tokens containing a colon before an ``@``
    (the ``user:password@host`` authority form) and replaces the whole token
    with ``[REDACTED]``. This catches bare credentials that lack a
    ``scheme://`` qualifier, which the scheme-qualified scanner does not see.

    The scan is purely linear: each character is visited a constant number of
    times. No regex backtracking. Benign email addresses (``user@host`` with
    no colon before ``@``) are preserved.

    Args:
        value: String that may contain bare authority credentials.

    Returns:
        String with bare credential tokens replaced by ``[REDACTED]``.
    """
    result: list[str] = []
    i = 0
    n = len(value)

    while i < n:
        at = value.find("@", i)
        if at == -1:
            result.append(value[i:])
            break

        # Find the start of the whitespace-delimited token containing '@'.
        tok_start = at
        while tok_start > i and not value[tok_start - 1].isspace():
            tok_start -= 1

        # Find the end of the token (first whitespace at/after '@').
        tok_end = at + 1
        while tok_end < n and not value[tok_end].isspace():
            tok_end += 1

        # A bare authority credential has a ':' between the token start and '@'
        # (the user:password separator). If present, redact the whole token.
        if value.find(":", tok_start, at) != -1:
            result.append(value[i:tok_start])
            result.append("[REDACTED]")
        else:
            result.append(value[i:tok_end])

        i = tok_end

    return "".join(result)


def _redact_sensitive(value: str) -> str:
    """Redact sensitive patterns from string values.

    Uses a bounded-linear bare-authority scanner first (for ``user:pass@host``
    without a scheme), then regex patterns for specific schemes, then a
    bounded-linear scanner for generic ``scheme://user:pass@host`` URIs. All
    steps are O(n); none use unbounded regex backtracking.
    """
    # Bare authority credentials first (user:pass@host without scheme). Running
    # this before the @localhost:\d+ regex prevents partial leaks where only
    # the @host:port fragment would be redacted, leaving user:pass exposed.
    redacted = _redact_bare_authority_credentials(value)
    # Apply regex patterns for specific schemes
    for pattern in _REDACTION_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    # Apply bounded credential URI scanner for generic scheme://user:pass@host
    redacted = _redact_credential_uris_bounded(redacted)
    return redacted


# Maximum recursion depth for redaction traversal. Bounds stack usage to
# _MAX_REDACTION_DEPTH * ~3 frames per level, well within Python's default
# recursion limit (1000). Does NOT call sys.setrecursionlimit().
_MAX_REDACTION_DEPTH: Final[int] = 64

# Static, non-sensitive sentinel returned when the depth bound is reached.
# Clearly named to indicate a depth-bound boundary, not a cycle or redaction.
# Contains no raw data, no object identity, and is JSON-safe.
_DEPTH_BOUND_SENTINEL: Final[str] = "[REDACTED_DEPTH_BOUND]"

# Static, non-sensitive sentinel returned for unsupported/hostile object
# types that cannot be safely redacted. Prevents raw/repr/string conversion
# leaks from arbitrary objects whose __repr__/__str__ could raise or leak.
# Contains no raw data, no object identity, and is JSON-safe.
_UNSUPPORTED_TYPE_SENTINEL: Final[str] = "[REDACTED_UNSUPPORTED_TYPE]"


def _to_plain_str(s: str) -> str:
    """Convert a str subclass instance to a plain ``str``.

    Uses ``"".join([s])`` which accesses the internal unicode data of ``s``
    directly via the C-level ``str.join`` implementation. This bypasses any
    hostile subclass overrides of ``__str__``, ``__hash__``, ``__eq__``,
    ``replace``, ``strip``, ``lower``, ``find``, etc.

    For plain ``str`` inputs, returns the same object unchanged (no copy).

    Args:
        s: A str instance (possibly a hostile subclass).

    Returns:
        A plain ``str`` with the same character content, guaranteed to have
        ``type(result) is str``.
    """
    if type(s) is str:
        return s
    # "".join([s]) iterates over the plain list [s] (safe __iter__) and
    # accesses s's internal unicode data directly (no subclass method calls).
    # The result is always a plain str.
    return "".join([s])


def _allocate_unique_placeholder(counter: list[int], result: dict[Any, Any]) -> str:
    """Allocate a unique placeholder key not already present in result.

    Increments the shared counter until an unused placeholder name is found.
    The returned placeholder is a JSON-safe string, guaranteeing hashability
    and serializability for any transformed key.
    """
    while True:
        counter[0] += 1
        unique_k = f"[REDACTED_KEY_{counter[0]}]"
        if unique_k not in result:
            return unique_k


def _redact_dict_keys_and_values(
    d: dict[Any, Any],
    counter: list[int],
    active_containers: set[int],
    depth: int,
) -> dict[Any, Any]:
    """Redact dict with collision-safe unique placeholders for ALL transformed keys.

    Every key that is transformed by redaction -- including non-string
    bytes/bytearray/tuple/frozenset keys whose type or content changes --
    goes through deterministic unique collision allocation. This prevents
    silent cardinality collapse when:

    1. A string ``"key"`` and a bytes key ``b"key"`` both resolve to the
       same string after transformation.
    2. A literal/already-redacted tuple key and a sensitive tuple key
       both redact to the same tuple.
    3. A literal/already-redacted frozenset key and a sensitive frozenset
       key both redact to the same frozenset.
    4. A literal key collides with a previously assigned placeholder.

    Both insertion orders preserve mapping cardinality: no entry is
    overwritten or discarded. Key allocation remains hashable and
    JSON-safe/serializable (string placeholders).

    HOSTILE-SUBCLASS SAFETY: Uses ``dict.items(d)`` (base-class dispatch)
    instead of ``d.items()`` to bypass any dict subclass override of
    ``items`` that could raise attacker-controlled exceptions or return
    hostile iterators. Str subclass keys are converted to plain ``str``
    via ``_to_plain_str`` to bypass hostile ``__hash__``/``__eq__``/
    method overrides before use in the result dict.

    Args:
        d: Dict to redact.
        counter: Mutable counter for unique placeholder generation.
        active_containers: Set of container IDs currently being redacted
            (cycle detection).
        depth: Current recursion depth (for bounded traversal).

    Returns:
        Dict with sensitive keys replaced by unique placeholders.
    """
    result: dict[Any, Any] = {}

    # HOSTILE-SUBCLASS SAFETY: dict.items(d) calls the base-class items()
    # method directly, bypassing any dict subclass override that could
    # raise attacker-controlled exceptions or return hostile iterators.
    for k, v in dict.items(d):
        redacted_k: Any
        was_transformed: bool

        if isinstance(k, str):
            # Convert str subclass to plain str to bypass hostile
            # __hash__/__eq__/replace/strip/lower overrides before any
            # processing or dict key use.
            k = _to_plain_str(k)
            sensitive_k = _redact_sensitive(k)
            if sensitive_k != k:
                # Sensitive string key: will get a unique placeholder.
                was_transformed = True
                redacted_k = sensitive_k
            else:
                was_transformed = False
                redacted_k = k
        elif isinstance(k, (bytes, bytearray)):
            # Bytes/bytearray keys: ALWAYS transform to a string placeholder.
            # The bytes content is decoded as latin-1 and redacted. The result
            # is a string, which is never equal to the original bytes.
            # HOSTILE-SUBCLASS SAFETY: Do NOT compare redacted_k to k using
            # != or ==, as that would dispatch to hostile __ne__/__eq__.
            # Instead, unconditionally mark as transformed since bytes keys
            # are always converted to string placeholders.
            redacted_k = _redact_value(bytes(k), counter, active_containers, depth + 1)
            was_transformed = True  # Always transform bytes/bytearray keys
        elif isinstance(k, (tuple, frozenset)):
            # Tuple/frozenset keys: ALWAYS transform to a string placeholder.
            # These types are not valid JSON object keys and must be
            # replaced for JSON-safety. Recurse to handle sensitive
            # elements within the container, but always use placeholder.
            redacted_k = _redact_value(k, counter, active_containers, depth + 1)
            was_transformed = True  # Always transform for JSON-safety
        else:
            # int, float, bool, None, and other non-string keys:
            # ALWAYS transform to a string placeholder for JSON-safety.
            # Non-string keys are not valid JSON object keys and can cause
            # serialization collisions (e.g., int 1 and string "1" both
            # serialize to "1" in JSON, collapsing cardinality). The
            # placeholder is collision-safe (unique per allocation) and
            # does not leak the original key content.
            was_transformed = True
            redacted_k = k  # will be replaced by placeholder below

        # Collision-safe allocation: every transformed key gets a unique
        # placeholder. Literal keys that collide with an existing entry
        # (including previously assigned placeholders) also get a unique
        # placeholder. This preserves all entries without overwriting.
        if was_transformed:
            redacted_k = _allocate_unique_placeholder(counter, result)
        elif redacted_k in result:
            redacted_k = _allocate_unique_placeholder(counter, result)

        result[redacted_k] = _redact_value(v, counter, active_containers, depth + 1)

    return result


def _redact_value(
    value: Any,
    counter: list[int] | None = None,
    active_containers: set[int] | None = None,
    depth: int = 0,
) -> Any:
    """Redact sensitive values from any type.

    Recursively redacts both dict KEYS and VALUES to prevent sensitive
    connection strings from surviving in count-table keys (e.g.,
    primary_dml_by_table, denylist_dml_counts).

    Uses deterministic unique placeholders for ALL transformed keys
    (including non-string bytes/bytearray/tuple/frozenset) to prevent
    collision while not leaking sensitive key content.

    CYCLE DETECTION: Uses recursion-path identity tracking to detect cycles.
    When a cycle is detected, returns a static JSON-safe sentinel
    [REDACTED_CYCLE] without exposing raw data or object identity via repr().
    Shared but acyclic values are independently redacted (no false positives).

    DEPTH BOUND: Uses a bounded-depth safeguard to terminate deterministically
    on deeply nested acyclic structures (~500+ levels) without raising
    RecursionError. When depth exceeds _MAX_REDACTION_DEPTH, returns a static
    JSON-safe sentinel [REDACTED_DEPTH_BOUND]. Does NOT call
    sys.setrecursionlimit(). Does not silently drop data: the sentinel is a
    clearly named static string that replaces the deep subtree.

    HOSTILE-SUBCLASS SAFETY: str subclass values are converted to plain ``str``
    via ``_to_plain_str`` before redaction to bypass hostile method overrides
    (replace/strip/lower/find/etc.). Container subclasses (list/tuple/set/
    frozenset) are iterated via base-class ``__iter__`` dispatch
    (``list.__iter__(value)``, etc.) to bypass hostile ``__iter__`` overrides.
    Unknown object types are replaced with a static ``[REDACTED_UNSUPPORTED_TYPE]``
    sentinel to prevent raw/repr/string conversion leaks from arbitrary objects
    whose ``__repr__``/``__str__`` could raise or leak sensitive data.

    Args:
        value: Value to redact.
        counter: Mutable counter for unique placeholder generation.
            None creates a new counter for top-level calls.
        active_containers: Set of container IDs currently being redacted
            (cycle detection). None creates a new set for top-level calls.
        depth: Current recursion depth (internal use for bounded traversal).

    Returns:
        Redacted value with sensitive content replaced.
    """
    if counter is None:
        counter = [0]
    if active_containers is None:
        active_containers = set()

    # Depth-bounded safeguard: return static sentinel for deeply nested
    # structures. This prevents RecursionError on ~500+ level acyclic
    # nesting without calling sys.setrecursionlimit(). The sentinel is
    # a clearly named, non-sensitive, JSON-safe static string.
    if depth >= _MAX_REDACTION_DEPTH:
        return _DEPTH_BOUND_SENTINEL

    if isinstance(value, str):
        # Convert str subclass to plain str to bypass hostile method
        # overrides (replace/strip/lower/find/isalnum/isspace/etc.)
        # before any redaction processing.
        value = _to_plain_str(value)
        return _redact_sensitive(value)
    elif isinstance(value, (bytes, bytearray)):
        # Bytes-like values may carry secret-like data. Decode as latin-1 (a
        # lossless 1:1 mapping) and run the string redactor over it. The
        # resulting redacted string is then returned instead of the raw
        # bytes so secret-like bytes content does not survive serialization.
        return _redact_sensitive(bytes(value).decode("latin-1"))
    elif isinstance(value, dict):
        # CYCLE DETECTION: Check if this dict is already being redacted
        container_id = id(value)
        if container_id in active_containers:
            # Cycle detected - return static sentinel (no repr, no raw data)
            return "[REDACTED_CYCLE]"
        # Add to active path for cycle detection
        active_containers.add(container_id)
        try:
            return _redact_dict_keys_and_values(
                value, counter, active_containers, depth
            )
        finally:
            # Remove from active path when done (allows shared acyclic values)
            active_containers.discard(container_id)
    elif isinstance(value, list):
        # CYCLE DETECTION: Check if this list is already being redacted
        container_id = id(value)
        if container_id in active_containers:
            # Cycle detected - return static sentinel
            return "[REDACTED_CYCLE]"
        # Add to active path
        active_containers.add(container_id)
        try:
            # HOSTILE-SUBCLASS SAFETY: Use list.__iter__(value) (base-class
            # dispatch) instead of iter(value) to bypass any list subclass
            # override of __iter__ that could raise attacker-controlled
            # exceptions or return hostile iterators.
            return list(
                _redact_value(item, counter, active_containers, depth + 1)
                for item in list.__iter__(value)
            )
        finally:
            # Remove from active path when done
            active_containers.discard(container_id)
    elif isinstance(value, tuple):
        # CYCLE DETECTION: Check if this tuple is already being redacted
        container_id = id(value)
        if container_id in active_containers:
            # Cycle detected - return static sentinel
            return "[REDACTED_CYCLE]"
        # Add to active path
        active_containers.add(container_id)
        try:
            # Use plain tuple() instead of type(value)() to avoid
            # namedtuple constructor corruption: type(value)(generator)
            # passes the generator as a single positional argument,
            # silently corrupting 1-field namedtuples (generator becomes
            # the field value) and crashing 2+ field namedtuples
            # (TypeError: missing positional arguments). Plain
            # tuple(generator) safely unpacks into positional elements,
            # producing a JSON-safe plain tuple that preserves cardinality
            # without leaking namedtuple field names or raw data.
            #
            # HOSTILE-SUBCLASS SAFETY: Use tuple.__iter__(value) (base-class
            # dispatch) instead of iter(value) to bypass any tuple subclass
            # override of __iter__ that could raise attacker-controlled
            # exceptions or return hostile iterators.
            return tuple(
                _redact_value(item, counter, active_containers, depth + 1)
                for item in tuple.__iter__(value)
            )
        finally:
            # Remove from active path when done
            active_containers.discard(container_id)
    elif isinstance(value, (set, frozenset)):
        # CYCLE DETECTION: Check if this set/frozenset is already being redacted
        container_id = id(value)
        if container_id in active_containers:
            # Cycle detected - return static sentinel
            return "[REDACTED_CYCLE]"
        # Add to active path
        active_containers.add(container_id)
        try:
            # Use list() instead of type(value)() for two reasons:
            # 1. JSON-safety: sets/frozensets are not JSON-serializable,
            #    but lists are.
            # 2. Cardinality preservation: distinct sensitive members that
            #    all redact to "[REDACTED]" would collapse to a single
            #    member in a set due to deduplication. A list preserves
            #    all members, maintaining container cardinality.
            #
            # HOSTILE-SUBCLASS SAFETY: Use the base-class __iter__ dispatch
            # (set.__iter__ or frozenset.__iter__) instead of iter(value)
            # to bypass any subclass override of __iter__ that could raise
            # attacker-controlled exceptions or return hostile iterators.
            base_iter = set.__iter__ if isinstance(value, set) else frozenset.__iter__
            return list(
                _redact_value(item, counter, active_containers, depth + 1)
                for item in base_iter(value)
            )
        finally:
            # Remove from active path when done
            active_containers.discard(container_id)
    elif isinstance(value, (int, bool, float, type(None))):
        # HOSTILE-SUBCLASS SAFETY: Check for exact builtin types.
        # Subclasses could have hostile overrides of __repr__, __str__,
        # __eq__, __hash__, __int__, __float__, etc.
        if type(value) is bool or type(value) is type(None):
            # bool and None cannot have meaningful subclasses in Python
            return value
        if isinstance(value, int) and type(value) is not int:
            # Int subclass - return sentinel (fail closed)
            return _UNSUPPORTED_TYPE_SENTINEL
        if isinstance(value, float) and type(value) is not float:
            # Float subclass - return sentinel (fail closed)
            return _UNSUPPORTED_TYPE_SENTINEL
        # Safe primitives: plain int, float, bool, or None
        return value
    else:
        # Unknown type - return a static sentinel to prevent raw/repr/string
        # conversion leaks from arbitrary objects whose __repr__/__str__ could
        # raise or leak sensitive data. The sentinel is a clearly named,
        # non-sensitive, JSON-safe static string. This prevents hostile
        # unknown objects from causing arbitrary code dispatch, leaking raw
        # data, or escaping redaction via __repr__/__str__ overrides.
        return _UNSUPPORTED_TYPE_SENTINEL


def _redact_dict(d: dict[str, Any]) -> dict[str, Any]:
    """Whitelist top-level fields and redact sensitive values.

    Uses a shared counter across all top-level fields so that
    placeholder labels (e.g., [REDACTED_KEY_1], [REDACTED_KEY_2])
    are unique across the entire serialized evidence, not just
    within a single field. This prevents ambiguity when multiple
    fields contain sensitive dict keys.

    HOSTILE-SUBCLASS SAFETY: Uses ``dict.items(d)`` (base-class dispatch)
    instead of ``d.items()`` to bypass any dict subclass override of
    ``items`` that could raise attacker-controlled exceptions.
    """
    result: dict[str, Any] = {}
    # Single shared counter across all top-level fields for
    # globally unique placeholder labels.
    counter: list[int] = [0]
    # HOSTILE-SUBCLASS SAFETY: dict.items(d) calls the base-class items()
    # method directly, bypassing any dict subclass override.
    for key, value in dict.items(d):
        # HOSTILE-SUBCLASS SAFETY: Normalize str subclass keys to plain str
        # before whitelist membership check. This bypasses hostile __eq__/
        # __hash__ overrides that could raise during `key not in _EVIDENCE_WHITELIST`.
        # Non-string keys are skipped (not in whitelist).
        if isinstance(key, str):
            key = _to_plain_str(key)
        else:
            # Non-string keys are never in the whitelist
            continue
        # Whitelist only applies to top-level keys
        if key not in _EVIDENCE_WHITELIST:
            continue
        result[key] = _redact_value(value, counter)
    return result


def serialize_evidence(result: E2aReconciliationResult) -> dict[str, Any]:
    """Serialize E2aReconciliationResult to redacted evidence dict.

    Evidence emission accepts a typed E2aReconciliationResult and SERIALIZES it canonically.
    Serialized output EXCLUDES connection strings, environment values, raw corpus text,
    and invented authorization receipt metadata.

    This is a DIAGNOSTIC REDACTOR/FORMAT SERIALIZER, NOT an acceptance provenance mechanism.
    typed_result=True indicates format metadata, NOT producer authenticity.

    Args:
        result: Typed reconciliation result from E2a measurement.

    Returns:
        Redacted evidence dict with only whitelisted fields.
    """
    # Build evidence dict from typed result fields
    evidence: dict[str, Any] = {
        "outcome": result.outcome,
        "manifest_sha256": result.manifest_sha256,
        "primary_dml_by_table": dict(result.primary_dml_by_table),
        "denylist_dml_counts": dict(result.denylist_dml_counts),
        "comparator_parity": result.comparator_parity,
        "stale_deletion_counts": dict(result.stale_deletion_counts),
        "cache_invalidation_counts": dict(result.cache_invalidation_counts),
        "failure_audit_outcome": result.failure_audit_outcome,
        "post_rollback_failure_audit_outcome": result.post_rollback_failure_audit_outcome,
        "reconciliation_required": result.reconciliation_required,
        # Format metadata: indicates evidence derives from typed result shape
        # NOT producer authenticity or acceptance provenance
        "typed_result": True,
    }

    # Smoke/comparator records carry explicit no-quality/no-Level label
    # Per D-15-04/D-15-05/D-15-10: distinguishing smoke from quality claims
    if result.comparator_parity is not None:
        # This is a comparator/smoke test, NOT a quality measurement
        evidence["quality_level"] = "not_measured"

    # Apply redaction and whitelist filtering
    redacted = _redact_dict(evidence)

    return redacted


def run_verification(enable_disposable_db: bool = False) -> dict[str, Any]:
    """Run verification with optional disposable DB acceptance.

    Default selector is non-DB. Without separate disposable DB authorization,
    emits ONLY `blocked_not_executed` with NO connection attempt.

    CRITICAL: This function MUST NOT attempt a DB connection when
    enable_disposable_db=False. The blocked_not_executed status is honest
    evidence that no destructive activity occurred.

    Wave 1: Both paths return blocked_not_executed / acceptance_blocked.
    Wave 2 will implement actual E2aReconciler.reconcile() + disposable target
    attestation admission when enable_disposable_db=True.

    Args:
        enable_disposable_db: Whether disposable DB acceptance is authorized.
            Default False (non-DB only).

    Returns:
        Verification result dict with disposable_db_status field.
    """
    if not enable_disposable_db:
        # BLOCKED: No disposable DB authorization
        # CRITICAL: Do NOT attempt any DB connection here
        return {
            "disposable_db_status": "blocked_not_executed",
            "outcome": "acceptance_blocked",
            "typed_result": True,
        }

    # Wave 1: Even with disposable authorization requested, gate remains fail-closed.
    # Wave 2 will implement actual E2aReconciler.reconcile(connection, desired)
    # and disposable target attestation admission.
    # For now, also blocked to enforce the Wave 1 fail-closed gate.
    return {
        "disposable_db_status": "blocked_not_executed",
        "outcome": "acceptance_blocked",
        "typed_result": True,
    }


def validate_quality_claim(record: dict[str, Any]) -> None:
    """Validate quality claim on a smoke/comparator record.

    Per D-15-04/D-15-05/D-15-10: Smoke/comparator records MUST NOT claim
    quality or Level without actual quality measurement.

    Args:
        record: Record dict with quality claim.

    Raises:
        ValueError: If input is not a dict, or if smoke record claims a
            Level/quality.

    HOSTILE-SUBCLASS SAFETY: Uses ``dict.get(record, key, default)``
    (base-class dispatch) instead of ``record.get(key, default)`` to
    prevent dict subclasses that override ``get`` from raising
    attacker-controlled exceptions.
    """
    if not isinstance(record, dict):
        raise ValueError(
            "validate_quality_claim requires a dict record. "
            "Non-dict input is not a valid quality claim record."
        )

    record_type = dict.get(record, "record_type", "")

    # HOSTILE-SUBCLASS SAFETY: Convert str subclass record_type to plain
    # str before comparison to bypass hostile __eq__ overrides that could
    # raise attacker-controlled exceptions during `record_type == "smoke"`.
    if isinstance(record_type, str):
        record_type = _to_plain_str(record_type)

    # Smoke records cannot claim quality/Level
    if record_type == "smoke":
        claimed_level = dict.get(record, "claimed_level")
        if claimed_level is not None:
            raise ValueError(
                "Smoke record cannot claim quality Level. "
                "Smoke tests do not measure quality. Use typed quality results instead."
            )


def validate_evidence_authenticity(evidence: dict[str, Any]) -> None:
    """Validate that evidence has valid E2aReconciliationResult format.

    This function validates FORMAT ONLY - it checks that the evidence dict
    has the correct structure (typed_result=True, valid outcome field).
    It does NOT validate acceptance authorization or source provenance.

    CRITICAL: typed_result=True is format metadata, NOT source provenance.
    Passing this validation does NOT prove the evidence came from actual
    E2aReconciler. Acceptance requires separate provenance validation via
    admit_evidence_for_acceptance().

    Per D-15-04/D-15-05/D-15-10: Evidence must have valid format, but
    format validation alone cannot grant PASS acceptance.

    Args:
        evidence: Evidence dict to validate.

    Raises:
        ValueError: If evidence lacks valid format metadata or has invalid outcome.
    """
    # Fail-closed guard: non-dict inputs raise the documented ValueError,
    # NOT AttributeError/TypeError from incidental .get calls.
    if not isinstance(evidence, dict):
        raise ValueError(
            "Evidence must be a dict for format validation. "
            "Non-dict inputs are rejected."
        )

    # typed_result is format metadata, not provenance
    # Having typed_result=True does NOT prove authenticity
    #
    # HOSTILE-SUBCLASS SAFETY: Use dict.get(evidence, key) (base-class
    # dispatch) instead of evidence.get(key) to bypass any dict subclass
    # override of get() that could raise attacker-controlled exceptions.
    typed_result = dict.get(evidence, "typed_result")
    # STRICT IDENTITY CHECK: typed_result must be the boolean True,
    # not merely truthy (1, "yes", [True], etc.). This prevents forgery
    # via truthy non-boolean values.
    if typed_result is not True:
        raise ValueError(
            "Evidence lacks typed_result format metadata. "
            "Evidence must have typed_result=True for format validation."
        )

    # Must have outcome field from typed result
    outcome = dict.get(evidence, "outcome")

    # Robustly reject non-string outcomes with safe generic wording.
    # Non-string outcomes (int, list, dict, etc.) must raise ValueError,
    # NOT TypeError from unhashable types in the set membership check below.
    # The outcome value is NEVER echoed into the error message.
    if not isinstance(outcome, str):
        raise ValueError(
            "Evidence has invalid outcome. "
            "Valid outcomes: changed, no_op, rolled_back_failure, "
            "acceptance_blocked, outcome_unknown."
        )

    # HOSTILE-SUBCLASS SAFETY: Convert str subclass outcome to plain str
    # before ANY comparison or membership check. This bypasses hostile
    # __eq__/__hash__ overrides that could raise attacker-controlled
    # exceptions during comparison with 'pass' or membership checks.
    outcome = _to_plain_str(outcome)

    # CRITICAL: typed_result=True is NOT acceptance provenance.
    # Reject evidence claiming PASS outcome BEFORE generic allowed-outcome
    # validation so that 'pass' produces the dedicated provenance-requirement
    # message, not the generic invalid-outcome message. This dedicated check
    # must be reachable.
    # PASS acceptance requires actual E2aReconciler provenance plus disposable authorization.
    if outcome == "pass":
        raise ValueError(
            "Evidence claims invalid outcome 'pass'. "
            "E2aReconciliationResult outcomes are: changed, no_op, rolled_back_failure, "
            "acceptance_blocked, outcome_unknown. "
            "PASS acceptance requires actual E2aReconciler provenance plus disposable authorization."
        )

    # Generic allowed-outcome validation with STATIC error message.
    # No evidence-value interpolation: the outcome value is never echoed.
    if outcome not in {
        "changed",
        "no_op",
        "rolled_back_failure",
        "acceptance_blocked",
        "outcome_unknown",
    }:
        raise ValueError(
            "Evidence has invalid outcome. "
            "Valid outcomes: changed, no_op, rolled_back_failure, "
            "acceptance_blocked, outcome_unknown."
        )

    # Note: This validates FORMAT only.
    # Acceptance provenance is validated separately by admit_evidence_for_acceptance().


__all__ = [
    "serialize_evidence",
    "run_verification",
    "validate_quality_claim",
    "validate_evidence_authenticity",
    "Phase15AcceptanceBlockedError",
    "HISTORICAL_DENYLIST",
    "is_historical_route_denied",
    "admit_evidence_for_acceptance",
]
