"""Local conservative coreference rule engine (Phase 16-16).

Pure, stdlib-only grouping of already-resolved corpus mentions into
conservative coreference clusters. A cluster exists only when, inside one
``(document_id, version_id)`` scope, at least two corpus mentions share the
exact same ``(mention_text, entity_type)``. Nothing is ever persisted, no
canonical entity is ever created or merged, no model confidence is ever
assigned, and this module performs no I/O.

Frozen rules
------------
- Gate: ``build_coref_clusters`` clusters only when ``resolver_mode`` is
  exactly ``"rules"``; every other value (including ``None``) returns an
  empty ``CorefClusterSet`` and never raises.
- Member identity: the ``span_id`` of each corpus mention candidate. A
  duplicated member identity inside one scope fails closed with
  ``ValueError``. Query-scoped mentions (no document/version projection)
  never carry a cluster-eligible identity and are skipped entirely.
- Grouping: ``(document_id, version_id, mention_text, entity_type)``; a group
  never spans documents or versions and needs at least 2 members to cluster.
- Identity: ``cluster_id = deterministic_id("coref_cluster",
  canonical_json({"coref_rules_version": ..., "member_mention_ids":
  sorted(members), "version_id": ...}))`` reusing the frozen E2b helpers from
  ``llamaindex_runtime.entity.contracts``.
- Provenance: carries only ``coref_rules_version`` and the frozen strategy
  tag ``"local_lexical_structural"`` - never model or confidence data.
- Determinism: clusters are sorted by ``cluster_id`` and members ascending,
  so identical input yields byte-identical output under any input order.

The output is a frozen ``CorefClusterSet``; ``CorefClusterSet.tombstone``
returns a NEW frozen set with the matching cluster replaced by a copy whose
``tombstoned`` flag is ``True`` and whose membership rows are retained.
Unknown cluster ids fail closed with ``KeyError``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Final

from .contracts import MentionCandidate, canonical_json, deterministic_id
from .resolution import ResolutionResult

__all__ = ["CorefCluster", "CorefClusterSet", "build_coref_clusters"]


RULES_RESOLVER_MODE: Final[str] = "rules"
COREF_CLUSTER_ID_KIND: Final[str] = "coref_cluster"
COREF_STRATEGY: Final[str] = "local_lexical_structural"
_MIN_CLUSTER_MEMBERS: Final[int] = 2

# (document_id, version_id) resolution scope identity.
_ResolutionScope = tuple[str, str]
# Grouping key: (document_id, version_id, mention_text, entity_type).
_GroupKey = tuple[str, str, str, str]


@dataclass(frozen=True)
class CorefCluster:
    """Immutable conservative coreference cluster over corpus mentions."""

    cluster_id: str
    version_id: str
    member_mention_ids: tuple[str, ...]
    tombstoned: bool
    provenance: Mapping[str, str]


@dataclass(frozen=True)
class CorefClusterSet:
    """Immutable set of clusters; tombstoning always returns a new set."""

    clusters: tuple[CorefCluster, ...]

    def tombstone(self, cluster_id: str) -> CorefClusterSet:
        """Return a NEW frozen set with one cluster tombstoned.

        The matching cluster is replaced by a copy whose ``tombstoned`` flag
        is ``True`` while its membership rows are retained unchanged; every
        other cluster and the original set are left untouched. Unknown ids
        fail closed with ``KeyError``.
        """
        positions = {
            cluster.cluster_id: position
            for position, cluster in enumerate(self.clusters)
        }
        try:
            position = positions[cluster_id]
        except KeyError:
            raise KeyError(cluster_id) from None
        tombstoned_cluster = replace(self.clusters[position], tombstoned=True)
        return CorefClusterSet(
            clusters=(
                *self.clusters[:position],
                tombstoned_cluster,
                *self.clusters[position + 1 :],
            )
        )


def _corpus_identity(candidate: MentionCandidate) -> tuple[str, str, str] | None:
    """(document_id, version_id, span_id), or None for query mentions."""
    document_id = candidate.document_id
    version_id = candidate.version_id
    span_id = candidate.span_id
    if document_id is None or version_id is None or span_id is None:
        return None
    return document_id, version_id, span_id


def _frozen_provenance(*, coref_rules_version: str) -> Mapping[str, str]:
    """Immutable provenance restricted to the two frozen keys."""
    return MappingProxyType(
        {
            "coref_rules_version": coref_rules_version,
            "strategy": COREF_STRATEGY,
        }
    )


def _build_cluster(
    group_key: _GroupKey,
    member_ids: list[str],
    *,
    coref_rules_version: str,
) -> CorefCluster:
    """Deterministically build one cluster from one qualifying group."""
    _document_id, version_id, _mention_text, _entity_type = group_key
    member_mention_ids = tuple(sorted(member_ids))
    return CorefCluster(
        cluster_id=deterministic_id(
            COREF_CLUSTER_ID_KIND,
            canonical_json(
                {
                    "coref_rules_version": coref_rules_version,
                    "member_mention_ids": list(member_mention_ids),
                    "version_id": version_id,
                },
            ),
        ),
        version_id=version_id,
        member_mention_ids=member_mention_ids,
        tombstoned=False,
        provenance=_frozen_provenance(coref_rules_version=coref_rules_version),
    )


def _collect_member_groups(
    resolved: ResolutionResult,
) -> dict[_GroupKey, list[str]]:
    """Register member identities; group qualifying corpus mentions.

    Fails closed with ``ValueError`` on a duplicated span_id inside one
    ``(document_id, version_id)`` scope.
    """
    groups: dict[_GroupKey, list[str]] = {}
    seen_member_ids: dict[_ResolutionScope, set[str]] = {}
    for decision in resolved.resolved:
        candidate = decision.candidate
        identity = _corpus_identity(candidate)
        if identity is None:
            continue
        document_id, version_id, member_id = identity
        scope = (document_id, version_id)
        scope_member_ids = seen_member_ids.get(scope)
        if scope_member_ids is None:
            scope_member_ids = set()
            seen_member_ids[scope] = scope_member_ids
        if member_id in scope_member_ids:
            raise ValueError(
                "duplicate span_id within one (document_id, version_id) scope",
            )
        scope_member_ids.add(member_id)
        groups.setdefault(
            (document_id, version_id, candidate.mention_text, candidate.entity_type),
            [],
        ).append(member_id)
    return groups


def _clusters_from_groups(
    groups: dict[_GroupKey, list[str]],
    *,
    coref_rules_version: str,
) -> tuple[CorefCluster, ...]:
    """Materialize sorted clusters from groups with enough members."""
    clusters = tuple(
        _build_cluster(group_key, member_ids, coref_rules_version=coref_rules_version)
        for group_key, member_ids in groups.items()
        if len(member_ids) >= _MIN_CLUSTER_MEMBERS
    )
    return tuple(sorted(clusters, key=lambda cluster: cluster.cluster_id))


def build_coref_clusters(
    resolved: ResolutionResult,
    *,
    coref_rules_version: str,
    resolver_mode: str | None = None,
) -> CorefClusterSet:
    """Cluster resolved corpus mentions with local conservative rules.

    Contract (frozen by the canonical Phase 16-16 tests):

    1. Only ``resolver_mode == "rules"`` clusters; any other value returns an
       empty ``CorefClusterSet`` without raising.
    2. Member identity is ``candidate.span_id``; a duplicated span_id inside
       one ``(document_id, version_id)`` scope raises ``ValueError``.
    3. The grouping key is ``(document_id, version_id, mention_text,
       entity_type)`` and only groups of at least two members cluster.
    4. ``cluster_id`` is the deterministic E2b id over the rules version, the
       sorted member ids, and the version id, via
       ``contracts.deterministic_id`` + ``contracts.canonical_json``.
    5. ``provenance`` is an immutable mapping carrying only the rules version
       and the frozen strategy tag - never model or confidence values.
    6. Clusters are sorted by ``cluster_id`` and member ids ascending, so
       identical input yields byte-identical output under any input order.
    7. Pure: no canonical entity is created or merged, no relation mention is
       written, no model confidence is assigned, and no I/O happens.
    """
    if resolver_mode != RULES_RESOLVER_MODE:
        return CorefClusterSet(clusters=())
    return CorefClusterSet(
        clusters=_clusters_from_groups(
            _collect_member_groups(resolved),
            coref_rules_version=coref_rules_version,
        )
    )
