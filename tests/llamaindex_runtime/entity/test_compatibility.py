"""Phase 16-13 tests: bounded STATIC unresolved runtime compatibility.

Pins the frozen contract of ``llamaindex_runtime.entity.compatibility`` in its
bounded STATIC scope: the module holds an immutable deferred state
(``blocked_not_executed`` / ``runtime_compatibility_id=None``) and exposes a pure
freeze boundary that derives a deterministic compatibility id only from complete
synthetic *measured* evidence. Nothing here fabricates live metrics or writes
evidence files.

Frozen facts pinned by this module:

* deferred state -- ``BLOCKED_STATUS`` is exactly ``blocked_not_executed``; the
  immutable ``BLOCKED`` state carries ``runtime_compatibility_id=None`` and is
  unmodifiable; the module-level current compatibility remains unresolved
  (``CURRENT_RUNTIME_COMPATIBILITY_ID is None``).
* deterministic id -- ``compute_compatibility_id`` is pure and stable for equal
  synthetic recorded evidence and changes for every material tuple component
  (extractor id/version, model id/revision, artifact digest, label map digest,
  schema/normalization/segmentation versions, and the measured resource
  envelope).
* freeze boundary -- ``freeze`` constructs a frozen state only from complete
  synthetic measured evidence and its id equals an independent recomputation
  (the canonical SHA-256 of the recorded-evidence mapping). It rejects
  non-mapping, missing, incomplete, wrong-typed, unmeasured (``None`` /
  non-finite) and explicitly blocked evidence and never fabricates an id.
* source surface -- the module imports only stdlib/pure contract helpers (never
  modelscope/torch/transformers/tokenizers/sentencepiece/jieba/network/DB) and
  is NOT exported from the ``llamaindex_runtime.entity`` facade.
* upstream contract -- ``MentionCandidate`` continues to accept
  ``runtime_compatibility_id=None``; this module pins rather than contradicts
  that frozen candidate contract.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from llamaindex_runtime.entity import compatibility
from llamaindex_runtime.entity.contracts import MentionCandidate, canonical_json_sha256

_HEAVY = (
    "modelscope",
    "torch",
    "sentencepiece",
    "transformers",
    "tokenizers",
    "jieba",
    "adaseq",
)

_TOP_LEVEL_COMPONENTS = (
    "extractor_id",
    "extractor_version",
    "model_id",
    "model_revision",
    "artifact_digest",
    "label_map_digest",
    "schema_version",
    "normalization_version",
    "segmentation_version",
    "resource_envelope",
)


def _synthetic_measured_evidence() -> dict[str, object]:
    """Complete SYNTHETIC recorded-measurement mapping (never a live run)."""
    return {
        "extractor_id": "raner",
        "extractor_version": "1.0.0",
        "model_id": "iic/nlp_raner_named-entity-recognition_chinese-large-generic",
        "model_revision": "4d15e5b1427685cfd2cfc416903890219dc0582c",
        "artifact_digest": "a" * 64,
        "label_map_digest": "b" * 64,
        "schema_version": "e2b-schema-1",
        "normalization_version": "norm-1",
        "segmentation_version": "seg-1",
        "resource_envelope": {
            "cold_start_ms": 123.0,
            "peak_memory_bytes": 4_500_000_000,
            "throughput_mentions_per_sec": 42.5,
            "p95_latency_ms": 88.0,
        },
    }


def _mutate_evidence(evidence: dict[str, object], key: str) -> dict[str, object]:
    """Return a modified copy changing exactly one material component."""
    changed = dict(evidence)
    if key == "resource_envelope":
        envelope = dict(changed["resource_envelope"])  # type: ignore[arg-type]
        envelope["p95_latency_ms"] = 99.0
        changed[key] = envelope
    elif key in ("artifact_digest", "label_map_digest"):
        changed[key] = "e" * 64
    else:
        changed[key] = f"{changed[key]}-changed"
    return changed


# --- 1. Deferred / unresolved state


def test_blocked_state_is_exact_and_immutable() -> None:
    assert compatibility.BLOCKED_STATUS == "blocked_not_executed"
    assert compatibility.BLOCKED.status == "blocked_not_executed"
    assert compatibility.BLOCKED.runtime_compatibility_id is None
    with pytest.raises(AttributeError):
        compatibility.BLOCKED.runtime_compatibility_id = "fabricated"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        compatibility.BLOCKED.status = "frozen"  # type: ignore[misc]


def test_module_current_compatibility_is_unresolved() -> None:
    assert compatibility.CURRENT_RUNTIME_COMPATIBILITY_ID is None
    assert compatibility.CURRENT_STATUS == "blocked_not_executed"


# --- 2. Deterministic id computation


def test_deterministic_id_stable_for_equal_synthetic_evidence() -> None:
    left = _synthetic_measured_evidence()
    right = dict(reversed(list(_synthetic_measured_evidence().items())))
    first = compatibility.compute_compatibility_id(left)
    second = compatibility.compute_compatibility_id(right)
    assert first == second
    assert isinstance(first, str) and first


@pytest.mark.parametrize("key", _TOP_LEVEL_COMPONENTS)
def test_deterministic_id_changes_for_each_material_component(key: str) -> None:
    base = _synthetic_measured_evidence()
    changed = _mutate_evidence(base, key)
    assert compatibility.compute_compatibility_id(changed) != (
        compatibility.compute_compatibility_id(base)
    )
    assert compatibility.freeze(changed).runtime_compatibility_id != (
        compatibility.freeze(base).runtime_compatibility_id
    )


# --- 3. Freeze / construct-from-evidence boundary


def test_freeze_succeeds_for_complete_measured_evidence() -> None:
    evidence = _synthetic_measured_evidence()
    frozen = compatibility.freeze(evidence)
    # Independent recomputation via the canonical contract helper.
    assert frozen.runtime_compatibility_id == canonical_json_sha256(evidence)
    assert frozen.runtime_compatibility_id == compatibility.compute_compatibility_id(
        evidence
    )
    assert frozen.runtime_compatibility_id is not None
    assert frozen.status != compatibility.BLOCKED_STATUS
    assert type(frozen) is type(compatibility.BLOCKED)


def test_freeze_returns_new_immutable_state_and_does_not_mutate_blocked() -> None:
    frozen = compatibility.freeze(_synthetic_measured_evidence())
    assert frozen is not compatibility.BLOCKED
    assert compatibility.BLOCKED.runtime_compatibility_id is None
    assert compatibility.BLOCKED.status == "blocked_not_executed"
    with pytest.raises(AttributeError):
        frozen.runtime_compatibility_id = "fabricated"  # type: ignore[misc]


@pytest.mark.parametrize(
    "bad",
    ["not-a-mapping", None, 123, [("extractor_id", "raner")]],
)
def test_freeze_rejects_non_mapping_evidence(bad: object) -> None:
    with pytest.raises(ValueError):
        compatibility.freeze(bad)  # type: ignore[arg-type]


def test_freeze_rejects_empty_evidence() -> None:
    with pytest.raises(ValueError):
        compatibility.freeze({})


@pytest.mark.parametrize("key", _TOP_LEVEL_COMPONENTS)
def test_freeze_rejects_incomplete_evidence(key: str) -> None:
    evidence = _synthetic_measured_evidence()
    del evidence[key]
    with pytest.raises(ValueError):
        compatibility.freeze(evidence)


def test_freeze_rejects_wrong_typed_values() -> None:
    base = _synthetic_measured_evidence()
    for bad_key, bad_value in (
        ("extractor_id", 123),
        ("artifact_digest", 0),
        ("schema_version", []),
        ("model_revision", b"rev"),
        ("resource_envelope", [123.0]),
    ):
        changed = dict(base)
        changed[bad_key] = bad_value
        with pytest.raises(ValueError):
            compatibility.freeze(changed)


def test_freeze_rejects_wrong_typed_measured_values() -> None:
    changed = dict(_synthetic_measured_evidence())
    envelope = dict(changed["resource_envelope"])  # type: ignore[arg-type]
    envelope["peak_memory_bytes"] = "big"
    changed["resource_envelope"] = envelope
    with pytest.raises(ValueError):
        compatibility.freeze(changed)


def test_freeze_rejects_unmeasured_resource_values() -> None:
    base = _synthetic_measured_evidence()
    envelope = dict(base["resource_envelope"])  # type: ignore[arg-type]
    for key in envelope:
        bad_envelope = dict(envelope)
        bad_envelope[key] = None
        changed = dict(base)
        changed["resource_envelope"] = bad_envelope
        with pytest.raises(ValueError):
            compatibility.freeze(changed)


def test_freeze_rejects_non_finite_measured_values() -> None:
    base = _synthetic_measured_evidence()
    envelope = dict(base["resource_envelope"])  # type: ignore[arg-type]
    for bad_value in (float("nan"), float("inf"), float("-inf")):
        bad_envelope = dict(envelope)
        bad_envelope["p95_latency_ms"] = bad_value
        changed = dict(base)
        changed["resource_envelope"] = bad_envelope
        with pytest.raises(ValueError):
            compatibility.freeze(changed)


def test_freeze_rejects_blocked_evidence_no_fabrication() -> None:
    evidence = _synthetic_measured_evidence()
    evidence["status"] = compatibility.BLOCKED_STATUS
    with pytest.raises(ValueError):
        compatibility.freeze(evidence)


# --- 4. Source surface and facade boundary


def test_compatibility_imports_no_heavy_dependencies() -> None:
    for name in _HEAVY:
        assert (
            name not in sys.modules
        ), f"llamaindex_runtime.entity.compatibility must not import {name}"


def test_compatibility_source_has_no_live_tooling_imports() -> None:
    source = Path(compatibility.__file__).read_text(encoding="utf-8")
    for line in source.splitlines():
        if line.startswith(("import ", "from ")):
            for forbidden in (
                "modelscope",
                "torch",
                "sentencepiece",
                "transformers",
                "tokenizers",
                "jieba",
                "adaseq",
                "subprocess",
                "psutil",
                "socket",
                "requests",
                "urllib",
                "http",
                "sqlalchemy",
                "psycopg",
                "load_model",
                "load_mirror",
            ):
                assert (
                    forbidden not in line
                ), f"forbidden import in compatibility: {line}"


def test_compatibility_not_exported_from_entity_facade() -> None:
    import llamaindex_runtime.entity as entity

    # ``__all__`` is the authoritative facade export surface: ``compatibility``
    # must not appear there.
    assert "compatibility" not in entity.__all__
    # Because ``from llamaindex_runtime.entity import compatibility`` at module
    # top-level attaches the loaded submodule as a package attribute, ``hasattr``
    # cannot express a no-facade-export contract. Check the source boundary
    # instead: the package __init__ must contain no explicit ``.compatibility``
    # import/export.
    assert entity.__file__ is not None
    init_source = Path(entity.__file__).read_text(encoding="utf-8")
    assert ".compatibility" not in init_source
    assert "import compatibility" not in init_source


# --- 5. Upstream contract pin: MentionCandidate still accepts None


def _mention(**overrides: object) -> MentionCandidate:
    base: dict[str, object] = {
        "input_id": "00000000-0000-0000-0000-000000000001",
        "input_kind": "corpus_span",
        "input_revision": "abc-v2",
        "normalized_text": "猫猫今天开会",
        "span_id": "00000000-0000-0000-0000-000000000001",
        "segment_id": "seg-1",
        "char_start": 0,
        "char_end": 2,
        "mention_text": "猫猫",
        "raw_label": "PER",
        "canonical_label": "Person",
        "entity_type": "Person",
        "confidence": None,
        "confidence_kind": "unavailable",
        "source": "model",
        "extractor_id": "raner",
        "extractor_version": "1.0.0",
        "model_id": "iic/nlp_raner_named-entity-recognition_chinese-large-generic",
        "model_revision": "4d15e5b1427685cfd2cfc416903890219dc0582c",
        "artifact_digest": "a" * 64,
        "schema_version": "e2b-schema-1",
        "normalization_version": "norm-1",
        "segmentation_version": "seg-1",
        "label_map_digest": "b" * 64,
        "runtime_compatibility_id": None,
        "document_id": "00000000-0000-0000-0000-000000000002",
        "version_id": "00000000-0000-0000-0000-000000000003",
        "document_revision": "abc-v2",
        "projection": {"document_char_start": 0, "document_char_end": 2},
    }
    base.update(overrides)
    return MentionCandidate(**base)  # type: ignore[arg-type]


def test_model_candidate_still_accepts_runtime_compatibility_id_none() -> None:
    candidate = _mention(runtime_compatibility_id=None)
    assert candidate.runtime_compatibility_id is None
    assert candidate.source == "model"
    assert candidate.model_id == (
        "iic/nlp_raner_named-entity-recognition_chinese-large-generic"
    )
    assert candidate.artifact_digest == "a" * 64
