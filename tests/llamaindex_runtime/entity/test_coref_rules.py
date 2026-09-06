"""TDD-graph canonical tests for Phase 16-16 local conservative coref rules.

RED contract for llamaindex_runtime/entity/coref_rules.py (module does not exist
yet, so collection fails with ImportError until the GREEN task creates it).
Pinned contract:
- build_coref_clusters(resolved: ResolutionResult, *, coref_rules_version: str,
  resolver_mode: str | None = None) -> CorefClusterSet
- default off: only resolver_mode == "rules" clusters; anything else returns an
  empty cluster set (no exception)
- conservative lexical/structural grouping: identical mention_text AND identical
  entity_type within one (document_id, version_id); groups of size 1 never
  cluster; duplicate span_id members inside one scope raise ValueError; nothing
  ever clusters across documents or versions
- deterministic E2b identity: cluster_id = deterministic_id("coref_cluster",
  canonical_json({"coref_rules_version": version, "member_mention_ids": sorted
  member ids, "version_id": version_id}))
- frozen CorefCluster(cluster_id, version_id, member_mention_ids, tombstoned,
  provenance); provenance carries only coref_rules_version and strategy
  ("local_lexical_structural") - never model or confidence data
- frozen CorefClusterSet with .tombstone(cluster_id) returning a NEW set
  (originals untouched, membership rows retained); unknown id raises KeyError
Pure unit tests: no model, DB, network, or persistence access.
"""

from __future__ import annotations

import ast
import inspect
import random
from dataclasses import FrozenInstanceError, fields
from uuid import UUID

import pytest

from llamaindex_runtime.entity.contracts import (
    MentionCandidate,
    canonical_json,
    deterministic_id,
)
from llamaindex_runtime.entity.resolution import (
    ResolutionDecision,
    ResolutionResult,
)
import llamaindex_runtime.entity.coref_rules as coref_rules_module
from llamaindex_runtime.entity.coref_rules import (
    CorefCluster,
    build_coref_clusters,
)

_DOCUMENT_ID = str(UUID(int=1))
_DOCUMENT_ID_B = str(UUID(int=8))
_VERSION_ID = str(UUID(int=2))
_VERSION_ID_B = str(UUID(int=9))
_M1 = str(UUID(int=101))
_M2 = str(UUID(int=102))
_M3 = str(UUID(int=103))
_M4 = str(UUID(int=104))
_MX = str(UUID(int=201))
_COREF_VERSION = "coref-rules-1"
_RULE_KIND = "coref_cluster"
_STRATEGY = "local_lexical_structural"
_NORMALIZED = "猫猫今天华为发布猫猫手机"

_BANNED_IMPORT_ROOTS = frozenset(
    {
        "modelscope",
        "torch",
        "jieba",
        "psycopg",
        "sqlite",
        "sqlite3",
        "requests",
        "urllib",
        "socket",
        "http",
        "openai",
        "anthropic",
    }
)


def _mention(**overrides: object) -> MentionCandidate:
    base: dict[str, object] = {
        "input_id": _M1,
        "input_kind": "corpus_span",
        "input_revision": "doc-v1",
        "normalized_text": _NORMALIZED,
        "span_id": _M1,
        "segment_id": "seg-1",
        "char_start": 0,
        "char_end": 2,
        "mention_text": "猫猫",
        "raw_label": "PER",
        "canonical_label": "Person",
        "entity_type": "Person",
        "confidence": 1.0,
        "confidence_kind": "dictionary_exact",
        "source": "dictionary",
        "extractor_id": "supplementary",
        "extractor_version": "1.0.0",
        "model_id": None,
        "model_revision": None,
        "artifact_digest": None,
        "runtime_compatibility_id": None,
        "schema_version": "e2b-dict-schema-1",
        "normalization_version": "norm-1",
        "segmentation_version": "seg-1",
        "label_map_digest": "b" * 64,
        "document_id": _DOCUMENT_ID,
        "version_id": _VERSION_ID,
        "document_revision": "doc-v1",
        "projection": {"document_char_start": 0, "document_char_end": 2},
    }
    base.update(overrides)
    return MentionCandidate(**base)  # type: ignore[arg-type]


def _result(mentions) -> ResolutionResult:
    return ResolutionResult(
        priority_version="priority-v1",
        resolved=tuple(
            ResolutionDecision(candidate=m, entity_id=None) for m in mentions
        ),
        pending=(),
        chosen_priority={},
    )


def _pair():
    return _result(
        [
            _mention(span_id=_M1, input_id=_M1, char_start=0, char_end=2),
            _mention(
                span_id=_M2,
                input_id=_M2,
                char_start=8,
                char_end=10,
                segment_id="seg-2",
                projection={"document_char_start": 8, "document_char_end": 10},
            ),
        ]
    )


def _org_pair():
    return _result(
        [
            _mention(
                span_id=_M3,
                input_id=_M3,
                mention_text="华为",
                char_start=4,
                char_end=6,
                entity_type="Organization",
                canonical_label="Organization",
                raw_label="ORG",
            ),
            _mention(
                span_id=_M4,
                input_id=_M4,
                mention_text="华为",
                char_start=4,
                char_end=6,
                segment_id="seg-3",
                entity_type="Organization",
                projection={"document_char_start": 4, "document_char_end": 6},
            ),
        ]
    )


def _expected_cluster_id(version_id: str, member_ids, rules_version: str) -> str:
    return deterministic_id(
        _RULE_KIND,
        canonical_json(
            {
                "coref_rules_version": rules_version,
                "member_mention_ids": sorted(member_ids),
                "version_id": version_id,
            }
        ),
    )


def _clusters_payload(cluster_set) -> str:
    return canonical_json(
        {
            "clusters": [
                {
                    "cluster_id": c.cluster_id,
                    "version_id": c.version_id,
                    "member_mention_ids": list(c.member_mention_ids),
                    "tombstoned": c.tombstoned,
                    "provenance": {k: c.provenance[k] for k in sorted(c.provenance)},
                }
                for c in cluster_set.clusters
            ]
        }
    )


def test_pair_clusters_deterministically():
    original = build_coref_clusters(
        _pair(), coref_rules_version=_COREF_VERSION, resolver_mode="rules"
    )
    rebuilt = build_coref_clusters(
        _pair(), coref_rules_version=_COREF_VERSION, resolver_mode="rules"
    )
    assert len(original.clusters) == 1
    cluster = original.clusters[0]
    assert cluster.version_id == _VERSION_ID
    assert cluster.member_mention_ids == tuple(sorted([_M1, _M2]))
    assert cluster.tombstoned is False
    assert cluster.provenance["coref_rules_version"] == _COREF_VERSION
    assert cluster.provenance["strategy"] == _STRATEGY
    assert set(cluster.provenance) == {"coref_rules_version", "strategy"}
    assert cluster.cluster_id == _expected_cluster_id(
        _VERSION_ID, [_M1, _M2], _COREF_VERSION
    )
    assert _clusters_payload(original) == _clusters_payload(rebuilt)


def test_multiple_clusters_and_sorted_membership():
    base = list(_pair().resolved) + list(_org_pair().resolved)
    result = build_coref_clusters(
        _result([d.candidate for d in base]),
        coref_rules_version=_COREF_VERSION,
        resolver_mode="rules",
    )
    assert len(result.clusters) == 2
    ids = [c.cluster_id for c in result.clusters]
    assert ids == sorted(ids)
    for cluster in result.clusters:
        assert list(cluster.member_mention_ids) == sorted(cluster.member_mention_ids)


def test_determinism_under_shuffled_input():
    base = list(_pair().resolved) + list(_org_pair().resolved)
    baseline = build_coref_clusters(
        _result([d.candidate for d in base]),
        coref_rules_version=_COREF_VERSION,
        resolver_mode="rules",
    )
    baseline_payload = _clusters_payload(baseline)
    assert len(baseline.clusters) == 2
    for seed in range(5):
        order = [d.candidate for d in base]
        random.Random(seed).shuffle(order)
        variant = build_coref_clusters(
            _result(order), coref_rules_version=_COREF_VERSION, resolver_mode="rules"
        )
        assert _clusters_payload(variant) == baseline_payload


def test_different_text_never_clusters():
    resolved = _result(
        [
            _mention(),
            _mention(
                span_id=_M2,
                input_id=_M2,
                mention_text="今天",
                char_start=2,
                char_end=4,
                projection={"document_char_start": 2, "document_char_end": 4},
            ),
        ]
    )
    result = build_coref_clusters(
        resolved, coref_rules_version=_COREF_VERSION, resolver_mode="rules"
    )
    assert result.clusters == ()


def test_different_type_never_clusters():
    other_type = _mention(
        span_id=_M2,
        input_id=_M2,
        char_start=8,
        char_end=10,
        segment_id="seg-2",
        entity_type="Animal",
        canonical_label="Animal",
        raw_label="ANIMAL",
        projection={"document_char_start": 8, "document_char_end": 10},
    )
    result = build_coref_clusters(
        _result([_mention(), other_type]),
        coref_rules_version=_COREF_VERSION,
        resolver_mode="rules",
    )
    assert result.clusters == ()


def test_cross_version_never_clusters():
    cross = _mention(
        span_id=_MX,
        input_id=_MX,
        version_id=_VERSION_ID_B,
        document_id=_DOCUMENT_ID_B,
    )
    result = build_coref_clusters(
        _result([d.candidate for d in _pair().resolved] + [cross]),
        coref_rules_version=_COREF_VERSION,
        resolver_mode="rules",
    )
    assert len(result.clusters) == 1
    assert _MX not in result.clusters[0].member_mention_ids


def test_cross_document_never_clusters():
    cross_doc = _mention(
        span_id=_MX,
        input_id=_MX,
        char_start=0,
        char_end=2,
        document_id=_DOCUMENT_ID_B,
    )
    result = build_coref_clusters(
        _result([_pair().resolved[0].candidate, cross_doc]),
        coref_rules_version=_COREF_VERSION,
        resolver_mode="rules",
    )
    assert result.clusters == ()


def test_empty_and_single_mention_produce_no_clusters():
    empty = build_coref_clusters(
        _result([]), coref_rules_version=_COREF_VERSION, resolver_mode="rules"
    )
    assert empty.clusters == ()
    single = _result([_mention()])
    result = build_coref_clusters(
        single, coref_rules_version=_COREF_VERSION, resolver_mode="rules"
    )
    assert result.clusters == ()


@pytest.mark.parametrize("mode", [None, "", "dictionary", "model", "RULES", "rules "])
def test_default_off_requires_exact_rules_gate(mode):
    result = build_coref_clusters(
        _pair(), coref_rules_version=_COREF_VERSION, resolver_mode=mode
    )
    assert result.clusters == ()


def test_rules_gate_enables_clustering():
    result = build_coref_clusters(
        _pair(), coref_rules_version=_COREF_VERSION, resolver_mode="rules"
    )
    assert len(result.clusters) == 1


def test_duplicate_member_identity_fails_closed():
    with pytest.raises(ValueError):
        build_coref_clusters(
            _result(
                [
                    _mention(),
                    _mention(
                        span_id=_M1,
                        input_id=_M1,
                        mention_text="今天",
                        char_start=2,
                        char_end=4,
                        segment_id="seg-2",
                        projection={"document_char_start": 2, "document_char_end": 4},
                    ),
                ]
            ),
            coref_rules_version=_COREF_VERSION,
            resolver_mode="rules",
        )


def test_tombstone_returns_new_set_and_retains_members():
    original = build_coref_clusters(
        _pair(), coref_rules_version=_COREF_VERSION, resolver_mode="rules"
    )
    cluster = original.clusters[0]
    tombstoned = original.tombstone(cluster.cluster_id)
    assert tombstoned is not original
    new_cluster = [
        c for c in tombstoned.clusters if c.cluster_id == cluster.cluster_id
    ][0]
    assert new_cluster is not cluster
    assert new_cluster.tombstoned is True
    assert new_cluster.member_mention_ids == cluster.member_mention_ids
    assert cluster.tombstoned is False
    assert _clusters_payload(tombstoned) != _clusters_payload(original)


def test_tombstone_unknown_cluster_fails_closed():
    original = build_coref_clusters(
        _pair(), coref_rules_version=_COREF_VERSION, resolver_mode="rules"
    )
    with pytest.raises(KeyError):
        original.tombstone("00000000" + "-0000" * 4)


def test_cluster_and_set_are_frozen():
    original = build_coref_clusters(
        _pair(), coref_rules_version=_COREF_VERSION, resolver_mode="rules"
    )
    cluster = original.clusters[0]
    with pytest.raises(FrozenInstanceError):
        cluster.tombstoned = True
    with pytest.raises(FrozenInstanceError):
        original.clusters = ()


def test_coref_cluster_dto_shape():
    assert {f.name for f in fields(CorefCluster)} == {
        "cluster_id",
        "version_id",
        "member_mention_ids",
        "tombstoned",
        "provenance",
    }


def test_provenance_never_carries_model_or_confidence_data():
    original = build_coref_clusters(
        _pair(), coref_rules_version=_COREF_VERSION, resolver_mode="rules"
    )
    for cluster in original.clusters:
        for key, value in cluster.provenance.items():
            assert key in {"coref_rules_version", "strategy"}
            assert not isinstance(value, float)


def test_module_ast_import_purity():
    tree = ast.parse(inspect.getsource(coref_rules_module))
    banned = {
        "modelscope",
        "torch",
        "jieba",
        "psycopg",
        "sqlite",
        "sqlite3",
        "requests",
        "urllib",
        "socket",
        "http",
        "openai",
        "anthropic",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in banned
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert module.split(".")[0] not in banned
            assert module != "llamaindex_runtime.entity.merger"
            assert "offline_mirror" not in module
            assert "raner_adapter" not in module
        if isinstance(node, ast.Name):
            assert node.id != "relation_mentions"
        if isinstance(node, ast.Attribute):
            assert node.attr != "relation_mentions"


def test_package_exports_coref_api():
    import llamaindex_runtime.entity as entity_pkg

    assert hasattr(entity_pkg, "build_coref_clusters")
    assert hasattr(entity_pkg, "CorefCluster")
    assert hasattr(entity_pkg, "CorefClusterSet")
