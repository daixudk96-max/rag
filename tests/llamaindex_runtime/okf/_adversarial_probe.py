"""Adversarial security probes for run_e2a_verification.py.

NOT a test file - temporary verification script for security audit.
Tests edge cases NOT covered by the existing test suite.
All synthetic data - no real credentials.
"""
from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path
from typing import Any

# Load the module under test
_MODULE_NAME = "_adversarial_e2a_probe"
module_path = (
    Path(__file__).parent.parent.parent.parent
    / "verification"
    / "phase15-okf-ingestion-pipeline"
    / "run_e2a_verification.py"
)
spec = importlib.util.spec_from_file_location(_MODULE_NAME, module_path)
if spec is None or spec.loader is None:
    raise ImportError(f"Cannot load module from {module_path}")
mod = importlib.util.module_from_spec(spec)
sys.modules[_MODULE_NAME] = mod
spec.loader.exec_module(mod)

_redact_value = mod._redact_value
_admit_evidence = mod.admit_evidence_for_acceptance
_validate_authenticity = mod.validate_evidence_authenticity
_serialize = mod.serialize_evidence
_Phase15Blocked = mod.Phase15AcceptanceBlockedError
_is_denied = mod.is_historical_route_denied
_MAX_DEPTH = mod._MAX_REDACTION_DEPTH

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS: {name}")
    else:
        FAIL += 1
        print(f"  FAIL: {name} {detail}")


def section(title: str) -> None:
    print(f"\n=== {title} ===")


# ---------------------------------------------------------------------------
# 1. Bool/int equality quirk in collision check
# ---------------------------------------------------------------------------
section("Bool/int equality quirk")

# {True: "a", 1: "b"} collapses in Python dict construction
d = {True: "a", 1: "b"}
check("True/1 dict has 1 entry", len(d) == 1, f"got {len(d)}")

# But what about {0: "a", False: "b"}?
d = {0: "a", False: "b"}
check("0/False dict has 1 entry", len(d) == 1, f"got {len(d)}")

# Redaction should preserve whatever the dict has
r = _redact_value({True: "a", 2: "b", 3: "c"})
check("bool+int keys preserved", len(r) == 3, f"got {len(r)}")
check("bool key value preserved", r.get(True) == "a")
check("int key value preserved", r.get(2) == "b")

# None as key
r = _redact_value({None: "val", "safe": 2})
check("None key preserved", len(r) == 2, f"got {len(r)}")
check("None key value", r.get(None) == "val")

# Float as key
r = _redact_value({1.5: "a", 2.5: "b"})
check("float keys preserved", len(r) == 2, f"got {len(r)}")

# Mixed: int 1 and float 1.0 collapse (Python semantics)
d = {1: "a", 1.0: "b"}
check("int 1 / float 1.0 collapse", len(d) == 1)


# ---------------------------------------------------------------------------
# 2. Depth boundary: exactly at, just below, just above
# ---------------------------------------------------------------------------
section("Depth boundary precision")

def build_nested(depth: int) -> dict[str, Any]:
    root: dict[str, Any] = {}
    cur = root
    for _ in range(depth - 1):
        child: dict[str, Any] = {}
        cur["n"] = child
        cur = child
    cur["bottom"] = "safe"
    return root

# At depth _MAX_DEPTH - 1: should still process normally
r = _redact_value(build_nested(_MAX_DEPTH - 1))
check(f"depth={_MAX_DEPTH-1} no sentinel", "[REDACTED_DEPTH_BOUND]" not in str(r))

# At depth _MAX_DEPTH: sentinel should appear
r = _redact_value(build_nested(_MAX_DEPTH))
check(f"depth={_MAX_DEPTH} has sentinel", "[REDACTED_DEPTH_BOUND]" in str(r))

# At depth _MAX_DEPTH + 10: sentinel should appear
r = _redact_value(build_nested(_MAX_DEPTH + 10))
check(f"depth={_MAX_DEPTH+10} has sentinel", "[REDACTED_DEPTH_BOUND]" in str(r))

# Sensitive data below depth bound must not leak
sensitive = "postgres://audit_secret:audit_pw@audit_host:5432"
r = _redact_value(build_nested(_MAX_DEPTH + 5).copy())
# Replace bottom with sensitive
root = build_nested(_MAX_DEPTH + 5)
cur = root
for _ in range(_MAX_DEPTH + 4):
    cur = cur["n"]
cur["bottom"] = sensitive
r = _redact_value(root)
r_str = str(r)
check("sensitive below depth bound not leaked", "audit_secret" not in r_str)
check("sensitive below depth bound no pw", "audit_pw" not in r_str)
check("sentinel present for deep sensitive", "[REDACTED_DEPTH_BOUND]" in r_str)


# ---------------------------------------------------------------------------
# 3. Counter DoS: many literal placeholder-named keys
# ---------------------------------------------------------------------------
section("Counter DoS with placeholder-named keys")

# Create dict with many [REDACTED_KEY_N] literal keys plus one sensitive key
N = 5000
big_dict: dict[str, Any] = {}
for i in range(1, N + 1):
    big_dict[f"[REDACTED_KEY_{i}]"] = i
big_dict["postgres://secret@host"] = "sensitive_value"

start = time.perf_counter()
r = _redact_value(big_dict)
elapsed_ms = (time.perf_counter() - start) * 1000

check(f"counter DoS {N} keys completes", len(r) == N + 1, f"got {len(r)}")
check(f"counter DoS {N} keys < 5s", elapsed_ms < 5000, f"took {elapsed_ms:.0f}ms")
check("counter DoS no secret leak", "postgres://" not in str(r))
check("counter DoS no 'secret' leak", "secret@host" not in str(r))
# Check all values preserved
vals = list(r.values())
check("counter DoS all int values preserved", all(i in vals for i in range(1, N + 1)))
check("counter DoS sensitive value preserved", "sensitive_value" in vals)


# ---------------------------------------------------------------------------
# 4. Cycle cleanup under exception
# ---------------------------------------------------------------------------
section("Cycle cleanup under exception")

# Create a dict with a cycle and a key that will cause an issue
# We test that active_containers is properly cleaned up even when
# redaction raises (simulated via deep nesting hitting sentinel)
cyclic: dict[str, Any] = {"data": "postgres://secret@host"}
cyclic["self"] = cyclic
# This should not raise
r = _redact_value(cyclic)
check("cyclic dict terminates", isinstance(r, dict))
check("cyclic dict no secret", "postgres://" not in str(r))
check("cyclic dict has sentinel", "[REDACTED_CYCLE]" in str(r))

# After redacting cyclic, redact a shared acyclic dict (tests cleanup)
shared = {"safe": "value", "postgres://x@y": 1}
container = {"a": shared, "b": shared}
r = _redact_value(container)
check("post-cycle shared acyclic no false cycle", "[REDACTED_CYCLE]" not in str(r))
check("post-cycle shared acyclic 2 entries", len(r) == 2)


# ---------------------------------------------------------------------------
# 5. Sentinel strings as values/keys (not confused with real sentinels)
# ---------------------------------------------------------------------------
section("Sentinel string handling")

# Literal "[REDACTED_DEPTH_BOUND]" as a value should pass through
r = _redact_value({"key": "[REDACTED_DEPTH_BOUND]"})
check("sentinel string value preserved", r["key"] == "[REDACTED_DEPTH_BOUND]")

# Literal "[REDACTED_CYCLE]" as a value should pass through
r = _redact_value({"key": "[REDACTED_CYCLE]"})
check("cycle sentinel string value preserved", r["key"] == "[REDACTED_CYCLE]")

# Literal "[REDACTED_KEY_1]" as a non-sensitive key
r = _redact_value({"[REDACTED_KEY_1]": "val", "safe": 2})
check("literal placeholder key preserved", len(r) == 2)
check("literal placeholder key value", r.get("[REDACTED_KEY_1]") == "val" or "val" in r.values())


# ---------------------------------------------------------------------------
# 6. Wave 1 gate bypass attempts
# ---------------------------------------------------------------------------
section("Wave 1 gate bypass attempts")

# Non-dict input
try:
    _admit_evidence(None)  # type: ignore
    check("None evidence blocked", False, "no exception")
except _Phase15Blocked:
    check("None evidence blocked", True)
except Exception as e:
    check("None evidence blocked", False, f"wrong exception: {type(e).__name__}")

# List input
try:
    _admit_evidence([1, 2])  # type: ignore
    check("list evidence blocked", False, "no exception")
except _Phase15Blocked:
    check("list evidence blocked", True)
except Exception as e:
    check("list evidence blocked", False, f"wrong exception: {type(e).__name__}")

# Empty dict
try:
    _admit_evidence({})
    check("empty dict evidence blocked", False, "no exception")
except _Phase15Blocked:
    check("empty dict evidence blocked", True)

# Dict with fake typed_result=True
try:
    _admit_evidence({"typed_result": True, "outcome": "changed"})
    check("fake typed evidence blocked", False, "no exception")
except _Phase15Blocked:
    check("fake typed evidence blocked", True)

# Dict with hostile _source_route object (non-string)
try:
    _admit_evidence({"_source_route": {"malicious": True}})
    check("hostile route object blocked", False, "no exception")
except _Phase15Blocked:
    check("hostile route object blocked", True)
except Exception as e:
    check("hostile route object blocked", False, f"wrong exception: {type(e).__name__}")

# Dict with _source_route as a list (non-string, truthy)
try:
    _admit_evidence({"_source_route": ["verification/phase10-real-docx-retrieval-validation/run_validation.py"]})
    check("list route blocked", False, "no exception")
except _Phase15Blocked:
    check("list route blocked", True)
except Exception as e:
    check("list route blocked", False, f"wrong exception: {type(e).__name__}")

# Dict with _source_route as int
try:
    _admit_evidence({"_source_route": 42})
    check("int route blocked", False, "no exception")
except _Phase15Blocked:
    check("int route blocked", True)
except Exception as e:
    check("int route blocked", False, f"wrong exception: {type(e).__name__}")


# ---------------------------------------------------------------------------
# 7. validate_evidence_authenticity forgery attempts
# ---------------------------------------------------------------------------
section("validate_evidence_authenticity forgery attempts")

# typed_result=1 (truthy but not True)
try:
    _validate_authenticity({"typed_result": 1, "outcome": "changed"})
    check("typed_result=1 rejected", False, "accepted")
except ValueError:
    check("typed_result=1 rejected", True)
except Exception as e:
    check("typed_result=1 rejected", False, f"wrong exception: {type(e).__name__}")

# typed_result="yes" (truthy string)
try:
    _validate_authenticity({"typed_result": "yes", "outcome": "changed"})
    check("typed_result='yes' rejected", False, "accepted")
except ValueError:
    check("typed_result='yes' rejected", True)

# typed_result=[True] (truthy list)
try:
    _validate_authenticity({"typed_result": [True], "outcome": "changed"})
    check("typed_result=[True] rejected", False, "accepted")
except ValueError:
    check("typed_result=[True] rejected", True)

# outcome="pass" must be rejected with provenance message
try:
    _validate_authenticity({"typed_result": True, "outcome": "pass"})
    check("outcome=pass rejected", False, "accepted")
except ValueError as e:
    check("outcome=pass rejected", True)
    check("outcome=pass message mentions provenance", "provenance" in str(e).lower())

# outcome="Pass" (capital P)
try:
    _validate_authenticity({"typed_result": True, "outcome": "Pass"})
    check("outcome=Pass rejected", False, "accepted")
except ValueError:
    check("outcome=Pass rejected", True)

# outcome=123 (non-string)
try:
    _validate_authenticity({"typed_result": True, "outcome": 123})
    check("outcome=123 rejected", False, "accepted")
except ValueError:
    check("outcome=123 rejected", True)
except Exception as e:
    check("outcome=123 rejected", False, f"wrong exception: {type(e).__name__}")

# outcome=None
try:
    _validate_authenticity({"typed_result": True, "outcome": None})
    check("outcome=None rejected", False, "accepted")
except ValueError:
    check("outcome=None rejected", True)
except Exception as e:
    check("outcome=None rejected", False, f"wrong exception: {type(e).__name__}")

# outcome=list
try:
    _validate_authenticity({"typed_result": True, "outcome": ["changed"]})
    check("outcome=list rejected", False, "accepted")
except ValueError:
    check("outcome=list rejected", True)
except Exception as e:
    check("outcome=list rejected", False, f"wrong exception: {type(e).__name__}")

# Non-dict evidence
try:
    _validate_authenticity("not a dict")  # type: ignore
    check("non-dict authenticity rejected", False, "accepted")
except ValueError:
    check("non-dict authenticity rejected", True)
except Exception as e:
    check("non-dict authenticity rejected", False, f"wrong exception: {type(e).__name__}")


# ---------------------------------------------------------------------------
# 8. Static error messages (no attacker data interpolation)
# ---------------------------------------------------------------------------
section("Static error message verification")

# Verify that error messages don't contain attacker-controlled data
attacker_route = "verification/../../etc/passwd/SECRET_DATA/injected"
try:
    _admit_evidence({"_source_route": attacker_route})
except _Phase15Blocked as e:
    msg = str(e)
    check("denylist msg no attacker route", "etc/passwd" not in msg)
    check("denylist msg no SECRET_DATA", "SECRET_DATA" not in msg)
except Exception:
    check("denylist msg check", False, "unexpected exception type")

try:
    _admit_evidence({"_source_route": "safe_route"})
except _Phase15Blocked as e:
    msg = str(e)
    check("gate msg no route data", "safe_route" not in msg)

# validate_evidence_authenticity error messages
try:
    _validate_authenticity({"typed_result": True, "outcome": "INJECTED_BY_ATTACKER"})
except ValueError as e:
    msg = str(e)
    check("authenticity msg no outcome data", "INJECTED_BY_ATTACKER" not in msg)


# ---------------------------------------------------------------------------
# 9. Serializer never confers authenticity
# ---------------------------------------------------------------------------
section("Serializer authenticity")

# serialize_evidence sets typed_result=True unconditionally
# But admit_evidence_for_acceptance still blocks
from llamaindex_runtime.okf.e2a_contracts import E2aReconciliationResult

result = E2aReconciliationResult(
    outcome="changed",
    manifest_sha256="a" * 64,
    primary_dml_by_table={"table1": 5},
    denylist_dml_counts={},
    comparator_parity=None,
    stale_deletion_counts={},
    cache_invalidation_counts={},
    failure_audit_outcome=None,
    post_rollback_failure_audit_outcome=None,
    reconciliation_required=False,
)
evidence = _serialize(result)
check("serializer sets typed_result=True", evidence.get("typed_result") is True)

# Even with serialized evidence, acceptance is blocked
try:
    _admit_evidence(evidence)
    check("serialized evidence blocked", False, "not blocked")
except _Phase15Blocked:
    check("serialized evidence blocked", True)

# Format validation passes for serialized evidence
try:
    _validate_authenticity(evidence)
    check("serialized evidence format valid", True)
except ValueError as e:
    check("serialized evidence format valid", False, str(e))


# ---------------------------------------------------------------------------
# 10. Redaction leak via partial URI schemes
# ---------------------------------------------------------------------------
section("Redaction edge cases")

# Scheme only (no credentials) - should NOT be redacted by bare authority
r = _redact_value("postgres://")
check("scheme-only not bare-authority redacted", "postgres://" in str(r) or "[REDACTED]" in str(r))

# Bare authority with unusual characters
r = _redact_value("user:p@ss@host")
r_str = str(r)
check("bare auth with @ in password", "p@ss" not in r_str or "[REDACTED]" in r_str)

# Multiple @ signs (user@domain:pass@host - ambiguous)
r = _redact_value("user@domain:pass@host")
r_str = str(r)
# The bare authority scanner finds the first @, checks for : before it
# If : is found, redacts the whole token
check("multi-@ token handled", "[REDACTED]" in r_str or "pass" not in r_str)

# Empty string
r = _redact_value("")
check("empty string returns empty", r == "")

# String with only whitespace
r = _redact_value("   ")
check("whitespace-only preserved", r == "   ")

# String with only @
r = _redact_value("@")
check("lone @ not redacted", "@" in str(r))

# Credential with tab character (whitespace delimiter)
r = _redact_value("user:pass@host\tsafe_text")
r_str = str(r)
check("tab-delimited credential redacted", "pass" not in r_str)
check("tab-delimited safe text preserved", "safe_text" in r_str)


# ---------------------------------------------------------------------------
# 11. Path normalization edge cases
# ---------------------------------------------------------------------------
section("Path normalization edge cases")

# Trailing/leading whitespace
check("trailing space denied", _is_denied("verification/phase10-real-docx-retrieval-validation/run_validation.py "))
check("leading space denied", _is_denied(" verification/phase10-real-docx-retrieval-validation/run_validation.py"))
check("newline denied", _is_denied("verification/phase10-real-docx-retrieval-validation/run_validation.py\n"))

# Dot-dot escaping removes prefix (no match, but gate is fail-closed)
check("dotdot escape not denied", not _is_denied("verification/../phase10-real-docx-retrieval-validation/run_validation.py"))

# Absolute path (leading /)
check("absolute path not denied", not _is_denied("/verification/phase10-real-docx-retrieval-validation/run_validation.py"))

# Null byte injection
check("null byte not denied", not _is_denied("verification/phase10-real-docx-retrieval-validation/run_validation.py\x00"))

# Redundant dot segments
check("redundant dots denied", _is_denied("verification/./phase10-real-docx-retrieval-validation/./run_validation.py"))
check("double dotdot denied", _is_denied("verification/a/b/../../phase10-real-docx-retrieval-validation/run_validation.py"))


# ---------------------------------------------------------------------------
# 12. Empty containers
# ---------------------------------------------------------------------------
section("Empty containers")

r = _redact_value({})
check("empty dict -> empty dict", r == {})

r = _redact_value([])
check("empty list -> empty list", r == [])

r = _redact_value(())
check("empty tuple -> empty tuple", r == ())

r = _redact_value(set())
check("empty set -> empty set", r == set())

r = _redact_value(frozenset())
check("empty frozenset -> empty frozenset", r == frozenset())


# ---------------------------------------------------------------------------
# 13. run_verification never connects to DB
# ---------------------------------------------------------------------------
section("run_verification DB safety")

r1 = mod.run_verification(enable_disposable_db=False)
check("non-DB returns blocked", r1["disposable_db_status"] == "blocked_not_executed")
check("non-DB no connection", r1["outcome"] == "acceptance_blocked")

r2 = mod.run_verification(enable_disposable_db=True)
check("DB-requested returns blocked", r2["disposable_db_status"] == "blocked_not_executed")
check("DB-requested no connection", r2["outcome"] == "acceptance_blocked")


# ---------------------------------------------------------------------------
# 14. Input not mutated (including cyclic structures)
# ---------------------------------------------------------------------------
section("Input mutation - extended")

import copy

# Cyclic list
cyclic_list: list[Any] = ["postgres://secret@host"]
cyclic_list.append(cyclic_list)
snapshot = copy.deepcopy(cyclic_list)  # This will fail for cyclic...
# Use identity check instead
_redact_value(cyclic_list)
check("cyclic list still cyclic", cyclic_list[1] is cyclic_list)
check("cyclic list content intact", cyclic_list[0] == "postgres://secret@host")

# Shared acyclic reference
shared_dict = {"safe": "val", "postgres://x@y": 1}
container = {"a": shared_dict, "b": shared_dict}
_redact_value(container)
check("shared dict still shared", container["a"] is container["b"])
check("shared dict content intact", "postgres://x@y" in container["a"])

# Set values not mutated
s = {"postgres://secret@host", "safe"}
snapshot_s = copy.deepcopy(s)
_redact_value(s)
check("set not mutated", s == snapshot_s)


# ---------------------------------------------------------------------------
# 15. No sys.setrecursionlimit change
# ---------------------------------------------------------------------------
section("Recursion limit unchanged")

original = sys.getrecursionlimit()
# Deep nesting
_redact_value(build_nested(_MAX_DEPTH + 50))
# Cyclic
cyclic2: dict[str, Any] = {}
cyclic2["self"] = cyclic2
_redact_value(cyclic2)
check("recursion limit unchanged", sys.getrecursionlimit() == original)


# ---------------------------------------------------------------------------
# 16. Nested dict with sensitive keys at multiple levels
# ---------------------------------------------------------------------------
section("Multi-level sensitive key nesting")

deep = {
    "postgres://level1@host": {
        "mysql://level2@host": {
            "redis://level3@host": "deep_value"
        }
    }
}
r = _redact_value(deep)
r_str = str(r)
check("multi-level no postgres leak", "postgres://" not in r_str)
check("multi-level no mysql leak", "mysql://" not in r_str)
check("multi-level no redis leak", "redis://" not in r_str)
check("multi-level no level1 leak", "level1" not in r_str)
check("multi-level no level2 leak", "level2" not in r_str)
check("multi-level no level3 leak", "level3" not in r_str)
check("multi-level deep value preserved", "deep_value" in r_str)
# All 3 levels should have unique placeholders
placeholder_count = r_str.count("[REDACTED_KEY_")
check("multi-level 3 unique placeholders", placeholder_count >= 3, f"got {placeholder_count}")


# ---------------------------------------------------------------------------
# 17. Bare authority edge: password containing @
# ---------------------------------------------------------------------------
section("Bare authority with @ in password")

# The bare authority scanner finds the FIRST @ in the token.
# If password contains @, the scanner finds the first @ (end of username).
# The token still has : before @, so it's redacted.
cred = "user:p@ss@host:5432"
r = _redact_value(cred)
r_str = str(r)
check("@-in-password no raw leak", "p@ss" not in r_str or "[REDACTED]" in r_str)
check("@-in-password redacted", "[REDACTED]" in r_str)


# ---------------------------------------------------------------------------
# 18. Recursion limit: deeply nested mixed types
# ---------------------------------------------------------------------------
section("Deeply nested mixed types")

# Alternate dict/list nesting
root_mixed: Any = "safe_bottom"
for i in range(_MAX_DEPTH + 20):
    if i % 2 == 0:
        root_mixed = {"k": root_mixed}
    else:
        root_mixed = [root_mixed]

r = _redact_value(root_mixed)
check("mixed deep nesting terminates", "[REDACTED_DEPTH_BOUND]" in str(r))

# Verify no RecursionError
check("mixed deep nesting no exception", isinstance(r, (dict, list, str)))


# ---------------------------------------------------------------------------
# 19. Tuple key with sensitive frozenset element
# ---------------------------------------------------------------------------
section("Tuple/frozenset nested key redaction")

# Tuple containing frozenset containing sensitive string
nested_key = (frozenset({"postgres://deep@host"}), "safe_marker")
d = {nested_key: "value"}
r = _redact_value(d)
r_str = str(r)
check("nested tuple-frozenset key no leak", "postgres://" not in r_str)
check("nested tuple-frozenset key no deep", "deep@host" not in r_str)
check("nested tuple-frozenset cardinality", len(r) == 1)

# Two distinct sensitive nested tuple keys
k1 = (frozenset({"postgres://a@host"}),)
k2 = (frozenset({"mysql://b@host"}),)
d2 = {k1: 1, k2: 2}
r2 = _redact_value(d2)
check("two nested tuple-frozenset keys preserved", len(r2) == 2, f"got {len(r2)}")
check("two nested keys no postgres", "postgres://" not in str(r2))
check("two nested keys no mysql", "mysql://" not in str(r2))


# ---------------------------------------------------------------------------
# 20. Sensitive value inside set (not key)
# ---------------------------------------------------------------------------
section("Sensitive values inside sets")

s = {"postgres://secret@host", "safe_value", b"mysql://bytes@host"}
r = _redact_value(s)
r_str = str(r)
check("set value no postgres leak", "postgres://" not in r_str)
check("set value no mysql leak", "mysql://" not in r_str)
check("set value no secret", "secret@host" not in r_str)
check("set value safe preserved", "safe_value" in r_str)
check("set cardinality preserved", len(r) == 3)


print(f"\n{'='*60}")
print(f"ADVERSARIAL PROBE RESULTS: {PASS} passed, {FAIL} failed")
print(f"{'='*60}")
if FAIL > 0:
    sys.exit(1)
