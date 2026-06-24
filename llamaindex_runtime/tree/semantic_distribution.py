from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence, runtime_checkable
from uuid import UUID


logger = logging.getLogger(__name__)


@runtime_checkable
class SemanticDistributionRegistry(Protocol):
    """Registry methods required by the tree semantic distribution baseline."""

    def query_tree_nodes_by_version(self, version_id: UUID) -> list[dict[str, Any]]: ...

    def query_tree_node_spans_by_version(
        self, version_id: UUID
    ) -> list[dict[str, Any]]: ...

    def query_vector_chunks_by_version(
        self, version_id: UUID
    ) -> list[dict[str, Any]]: ...

    def query_vector_chunk_spans_by_version(
        self, version_id: UUID
    ) -> list[dict[str, Any]]: ...

    def query_doc_id_by_version(self, version_id: UUID) -> UUID: ...


@runtime_checkable
class TreeSemanticDistributionAdapter(Protocol):
    """Protocol for tree-internal semantic distribution analysis."""

    def analyze_tree_semantic_distribution(
        self,
        *,
        version_id: UUID,
        registry: SemanticDistributionRegistry,
        limit: int | None = None,
    ) -> dict[str, Any]: ...


@runtime_checkable
class TreeBranchDecisionPolicy(Protocol):
    """Protocol for branch decisions based on semantic-distribution outputs."""

    def decide_branch_action(
        self,
        *,
        node_stats: dict[str, Any],
        tree_signals: dict[str, Any],
    ) -> str: ...


_MAX_TRAVERSAL_DEPTH = 256
_ROUTE_NODE_BONUS = 0.08
_DEPTH_BONUS_PER_LEVEL = 0.03
_MAX_DEPTH_BONUS_LEVELS = 4
_ROOT_ROUTE_PENALTY = 0.06
_SUPPORT_BONUS_PER_CHUNK = 0.003
_MAX_SUPPORT_BONUS_CHUNKS = 10
_MISSING_CHUNK_ID = UUID(int=0)  # mirrors runtime.MISSING_CHUNK_ID (runtime.py:86); defined locally to avoid circular import


@dataclass(frozen=True)
class BaselineTreeBranchDecisionPolicy:
    """Distribution-based decision policy using dispersion and entropy thresholds.

    This is a baseline implementation that does NOT transplant HIRO's distance-based
    threshold logic. Instead, it uses semantic distribution statistics directly.
    """

    dispersion_threshold: float
    entropy_threshold: float
    min_support_threshold: int = 1

    def decide_branch_action(
        self,
        *,
        node_stats: dict[str, Any],
        tree_signals: dict[str, Any],
    ) -> str:
        support_count = node_stats.get("support_count", 0)
        if support_count < self.min_support_threshold:
            return "prune"

        if node_stats.get("is_route_node"):
            return "drill_down"

        dispersion = node_stats.get("dispersion", 0.0)
        entropy = node_stats.get("entropy", 0.0)

        high_dispersion = dispersion > self.dispersion_threshold
        high_entropy = entropy > self.entropy_threshold

        if high_dispersion and high_entropy:
            return "drill_down"

        if not high_dispersion and not high_entropy:
            return "keep_parent"

        return "prune"

    def evaluate_children(
        self,
        *,
        child_stats: list[dict[str, Any]],
        tree_signals: dict[str, Any],
    ) -> dict[str, Any]:
        """Aggregate a child-level baseline decision (HIRO-parity interface).

        Baseline strategy: choose the best-similarity child (lowest query_distance)
        and apply decide_branch_action to that single child. Does NOT implement
        HIRO's distance+delta logic — this is the simple parity baseline.
        """
        if not child_stats:
            return {
                "decision": "prune",
                "selected_child_id": None,
                "child_decisions": {},
            }

        best_child = min(child_stats, key=lambda c: c.get("query_distance", 1.0))
        best_child_id = best_child.get("node_id")
        best_decision = self.decide_branch_action(
            node_stats=best_child,
            tree_signals=tree_signals,
        )

        if best_decision == "drill_down":
            return {
                "decision": "drill_down",
                "selected_child_id": best_child_id,
                "child_decisions": {best_child_id: "drill_down"},
            }

        if best_decision == "keep_parent":
            return {
                "decision": "keep_parent",
                "selected_child_id": None,
                "child_decisions": {best_child_id: "keep_parent"},
            }

        return {
            "decision": "prune",
            "selected_child_id": None,
            "child_decisions": {best_child_id: "prune"},
        }


@dataclass(frozen=True)
class _RegistrySnapshot:
    tree_nodes: list[dict[str, Any]]
    node_to_span_ids: dict[UUID, list[UUID]]
    span_to_node_id: dict[UUID, UUID]
    chunk_to_span_ids: dict[UUID, list[UUID]]
    vector_chunks: list[dict[str, Any]]


class PersistedTreeSemanticDistributionAdapter:
    """Compute per-node semantic distribution stats from persisted tree/vector tables."""

    def analyze_tree_semantic_distribution(
        self,
        *,
        version_id: UUID,
        registry: SemanticDistributionRegistry,
        limit: int | None = None,
    ) -> dict[str, Any]:
        snapshot = _load_registry_snapshot(
            version_id=version_id,
            registry=registry,
            limit=limit,
        )
        node_to_vectors, node_to_chunk_ids, skipped_chunk_count = (
            _collect_chunk_assignments(
                snapshot=snapshot,
            )
        )
        node_stats = _build_node_stats(
            tree_nodes=snapshot.tree_nodes,
            node_to_span_ids=snapshot.node_to_span_ids,
            node_to_vectors=node_to_vectors,
            node_to_chunk_ids=node_to_chunk_ids,
        )
        return _build_report(
            tree_nodes=snapshot.tree_nodes,
            node_stats=node_stats,
            skipped_chunk_count=skipped_chunk_count,
        )


def _load_registry_snapshot(
    *,
    version_id: UUID,
    registry: SemanticDistributionRegistry,
    limit: int | None,
) -> _RegistrySnapshot:
    tree_nodes = registry.query_tree_nodes_by_version(version_id)
    if limit is not None:
        tree_nodes = tree_nodes[:limit]

    tree_node_spans = registry.query_tree_node_spans_by_version(version_id)
    return _RegistrySnapshot(
        tree_nodes=tree_nodes,
        node_to_span_ids=_build_ordered_map(
            rows=tree_node_spans,
            key_name="node_id",
            value_name="span_id",
        ),
        span_to_node_id={
            _required_value(row, "span_id"): _required_value(row, "node_id")
            for row in tree_node_spans
        },
        chunk_to_span_ids=_build_ordered_map(
            rows=registry.query_vector_chunk_spans_by_version(version_id),
            key_name="chunk_id",
            value_name="span_id",
        ),
        vector_chunks=registry.query_vector_chunks_by_version(version_id),
    )


def _collect_chunk_assignments(
    *,
    snapshot: _RegistrySnapshot,
) -> tuple[dict[UUID, list[list[float]]], dict[UUID, list[UUID]], int]:
    allowed_node_ids = {
        _required_value(node, "node_id") for node in snapshot.tree_nodes
    }
    node_to_vectors: dict[UUID, list[list[float]]] = defaultdict(list)
    node_to_chunk_ids: dict[UUID, list[UUID]] = defaultdict(list)
    skipped_chunk_count = 0

    for chunk in snapshot.vector_chunks:
        embedding = _coerce_embedding(chunk.get("embedding"))
        if embedding is None:
            skipped_chunk_count += 1
            continue

        node_id = _resolve_node_id(
            chunk=chunk,
            chunk_to_span_ids=snapshot.chunk_to_span_ids,
            span_to_node_id=snapshot.span_to_node_id,
        )
        if node_id is None or node_id not in allowed_node_ids:
            skipped_chunk_count += 1
            continue

        node_to_vectors[node_id].append(embedding)
        node_to_chunk_ids[node_id].append(_required_value(chunk, "chunk_id"))

    return dict(node_to_vectors), dict(node_to_chunk_ids), skipped_chunk_count


def _build_node_stats(
    *,
    tree_nodes: Sequence[dict[str, Any]],
    node_to_span_ids: dict[UUID, list[UUID]],
    node_to_vectors: dict[UUID, list[list[float]]],
    node_to_chunk_ids: dict[UUID, list[UUID]],
) -> list[dict[str, Any]]:
    """Build stats for direct evidence nodes and route-only subtree parents.

    Parent nodes remain route/navigation nodes: their ``chunk_ids`` stay limited
    to direct evidence only.  Their centroid/support fields are computed from
    descendant vectors so they can act as semantic hotspots and waypoint nodes
    without pretending to own descendant text.
    """
    subtree_vectors_by_node = _collect_subtree_values(
        tree_nodes=tree_nodes,
        direct_values=node_to_vectors,
    )
    subtree_chunk_ids_by_node = _collect_subtree_values(
        tree_nodes=tree_nodes,
        direct_values=node_to_chunk_ids,
    )

    node_stats: list[dict[str, Any]] = []
    for node in tree_nodes:
        node_id = _required_value(node, "node_id")
        direct_vectors = node_to_vectors.get(node_id, [])
        subtree_vectors = subtree_vectors_by_node.get(node_id, [])
        vectors = direct_vectors or subtree_vectors
        if not vectors:
            continue

        direct_chunk_ids = node_to_chunk_ids.get(node_id, [])
        subtree_chunk_ids = subtree_chunk_ids_by_node.get(node_id, [])
        centroid = _compute_centroid(vectors)
        prototype_embedding = _compute_prototype_embedding(vectors)
        distances = [_euclidean_distance(vector, centroid) for vector in vectors]
        node_stats.append(
            {
                "node_id": node_id,
                "heading_path": node.get("heading_path"),
                "parent_node_id": node.get("parent_node_id"),
                "level_no": node.get("level_no"),
                "span_ids": node_to_span_ids.get(node_id, []),
                "chunk_ids": direct_chunk_ids,
                "subtree_chunk_ids": subtree_chunk_ids,
                "centroid": centroid,
                "prototype_embedding": prototype_embedding,
                "dispersion": _mean(distances),
                "entropy": _compute_entropy(distances),
                "support_count": len(vectors),
                "direct_support_count": len(node_to_vectors.get(node_id, [])),
                "is_route_node": not direct_chunk_ids and bool(subtree_chunk_ids),
            }
        )
    return node_stats


def _collect_subtree_values(
    *,
    tree_nodes: Sequence[dict[str, Any]],
    direct_values: dict[UUID, list[Any]],
) -> dict[UUID, list[Any]]:
    parent_to_children = _build_parent_to_children(tree_nodes)
    cached_values: dict[UUID, list[Any]] = {}

    def collect(
        node_id: UUID,
        *,
        active_path: frozenset[UUID] = frozenset(),
        depth: int = 0,
    ) -> list[Any]:
        if depth > _MAX_TRAVERSAL_DEPTH:
            raise ValueError(
                f"tree traversal depth exceeded {_MAX_TRAVERSAL_DEPTH} at node_id={node_id}"
            )
        if node_id in cached_values:
            return cached_values[node_id]
        if node_id in active_path:
            raise ValueError(f"tree cycle detected at node_id={node_id}")

        values = list(direct_values.get(node_id, []))
        next_path = active_path | frozenset((node_id,))
        for child in parent_to_children.get(node_id, []):
            values.extend(
                collect(
                    _required_value(child, "node_id"),
                    active_path=next_path,
                    depth=depth + 1,
                )
            )
        cached_values[node_id] = values
        return values

    for node in tree_nodes:
        collect(_required_value(node, "node_id"))
    return cached_values


def _build_parent_to_children(
    tree_nodes: Sequence[dict[str, Any]],
) -> dict[UUID | None, list[dict[str, Any]]]:
    parent_to_children: dict[UUID | None, list[dict[str, Any]]] = defaultdict(list)
    for node in tree_nodes:
        parent_to_children[node.get("parent_node_id")].append(node)
    return dict(parent_to_children)


def _build_report(
    *,
    tree_nodes: Sequence[dict[str, Any]],
    node_stats: Sequence[dict[str, Any]],
    skipped_chunk_count: int,
) -> dict[str, Any]:
    embedding_dimension = len(node_stats[0]["centroid"]) if node_stats else 0

    # Phase 12 D-07: Build parent_to_children from COMPLETE tree_nodes (E2 gap closure)
    # Reuse existing _build_parent_to_children which returns dict[UUID|None, list[node_dict]]
    _p2c_raw = _build_parent_to_children(tree_nodes)
    # Reduce to tuple of node_ids for the denominator (provenance: real node_ids only)
    parent_to_children = {
        parent_id: tuple(_required_value(node, "node_id") for node in children)
        for parent_id, children in _p2c_raw.items()
    }

    return {
        "node_stats": list(node_stats),
        "tree_signals": {
            "node_count": len(tree_nodes),
            "analyzed_node_count": len(node_stats),
            "skipped_chunk_count": skipped_chunk_count,
            "embedding_dimension": embedding_dimension,
        },
        "parent_to_children": parent_to_children,
    }


def _build_ordered_map(
    *,
    rows: Sequence[dict[str, Any]],
    key_name: str,
    value_name: str,
) -> dict[UUID, list[UUID]]:
    grouped: dict[UUID, list[UUID]] = defaultdict(list)
    seen: dict[UUID, set[UUID]] = defaultdict(set)
    for row in rows:
        key = _required_value(row, key_name)
        value = _required_value(row, value_name)
        if value in seen[key]:
            continue
        seen[key].add(value)
        grouped[key].append(value)
    return dict(grouped)


def _resolve_node_id(
    *,
    chunk: dict[str, Any],
    chunk_to_span_ids: dict[UUID, list[UUID]],
    span_to_node_id: dict[UUID, UUID],
) -> UUID | None:
    node_id = chunk.get("node_id")
    if node_id is not None:
        return node_id

    chunk_id = _required_value(chunk, "chunk_id")
    for span_id in chunk_to_span_ids.get(chunk_id, []):
        resolved = span_to_node_id.get(span_id)
        if resolved is not None:
            return resolved
    return None


def _required_value(row: dict[str, Any], key: str) -> Any:
    if key not in row:
        raise ValueError(f"row missing required column: {key}")
    return row[key]


def _coerce_embedding(value: Any) -> list[float] | None:
    if value is None:
        return None
    if isinstance(value, memoryview):
        value = value.tobytes().decode("utf-8")
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        if stripped.startswith("[") and stripped.endswith("]"):
            stripped = stripped[1:-1].strip()
        if not stripped:
            return None
        return [float(part.strip()) for part in stripped.split(",")]
    if isinstance(value, Sequence):
        vector = [float(part) for part in value]
        return vector or None
    return None


def _compute_centroid(vectors: Sequence[Sequence[float]]) -> list[float]:
    if not vectors:
        raise ValueError("vectors cannot be empty")

    dimensions = {len(vector) for vector in vectors}
    if 0 in dimensions:
        raise ValueError("embeddings must not be empty")
    if len(dimensions) != 1:
        raise ValueError(
            f"all embeddings must share the same dimension; got {sorted(dimensions)}"
        )

    dimension = next(iter(dimensions))
    return [
        sum(vector[index] for vector in vectors) / len(vectors)
        for index in range(dimension)
    ]


def _compute_prototype_embedding(vectors: Sequence[Sequence[float]]) -> list[float]:
    """Psi-RAG-style prototype embedding transplant.

    Donor mapping:
    - Psi-RAG `prototype_embeddings(..., method='average')`
    - local adaptation preserves the same average prototype behavior
    """
    return _compute_centroid(vectors)


def _euclidean_distance(vector: Sequence[float], centroid: Sequence[float]) -> float:
    return math.sqrt(
        sum(
            (value - center) ** 2
            for value, center in zip(vector, centroid, strict=True)
        )
    )


def _mean(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _compute_entropy(values: Sequence[float]) -> float:
    positive_values = [value for value in values if value > 0]
    total = sum(positive_values)
    if total <= 0:
        return 0.0

    entropy = 0.0
    for value in positive_values:
        probability = value / total
        entropy -= probability * math.log2(probability)
    return entropy


# -- Phase 2: Psi-RAG traversal skeleton transplant --


@dataclass(frozen=True)
class QueryHit:
    """Provenance-anchored hit from tree traversal.

    This preserves all immutable provenance contracts from Phase 1.  Hotspot
    fields describe navigation provenance only; final hits still come from
    evidence-bearing chunk/span nodes.
    """

    doc_id: UUID
    version_id: UUID
    span_id: UUID
    chunk_id: UUID
    node_id: UUID
    similarity_score: float
    hotspot_node_id: UUID | None = None
    navigation_node_ids: tuple[UUID, ...] = ()
    drill_depth: int = 0


@dataclass(frozen=True)
class SubtreeHotspot:
    """Semantic hotspot subtree head selected before local traversal."""

    node_id: UUID
    score: float
    reason: str
    support_count: int
    dispersion: float
    entropy: float


@dataclass(frozen=True)
class KeywordSpanHit:
    """Keyword/BM25 span hit with node mapping.

    Phase 11 11-07: Generic keyword hit for hybrid fusion scoring.
    Captures BM25 or other keyword retrieval results with span-to-node mapping.
    """

    span_id: UUID
    node_id: UUID
    score: float
    matched_terms: tuple[str, ...]
    source: str  # "bm25", "exact_match", etc.


@dataclass(frozen=True)
class HotspotSelectionContext:
    """V2 selection context for hybrid hotspot selector.

    Phase 11 11-07: Unified context for vector + keyword + optional rerank fusion.
    Enables generic cross-domain selector without hardcoded domain-specific terms.

    Phase 12 12-01 D-07: Extended with parent_to_children for complete direct-child denominator.
    E2 gap closure: denominator includes no-vector children absent from node_stats.
    """

    query_text: str
    query_embedding: list[float]
    node_stats: dict[UUID, dict[str, Any]]
    tree_signals: dict[str, Any]
    vector_candidates: list[NodeSemanticHit]
    keyword_hits: list[KeywordSpanHit]
    rerank_scores: dict[UUID, float] | None = None
    parent_to_children: dict[UUID | None, tuple[UUID, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class NodeSemanticHit:
    """Level-agnostic semantic candidate node before cluster inference.

    Phase 11 D-01: All eligible nodes compete equally by cosine similarity.
    This record preserves the raw similarity score before any route-node bonus,
    depth bonus, or parent preference is applied.

    The path_to_root enables ancestor aggregation for cluster scoring.
    """

    node_id: UUID
    similarity: float
    heading_path: str | None
    parent_node_id: UUID | None
    path_to_root: tuple[UUID, ...]


@dataclass(frozen=True)
class ClusterCandidate:
    """Ancestor/local subtree region with aggregated semantic hits.

    Phase 11 D-02: Hotspot is inferred post-hoc from densest shared region,
    not predeclared as route/hotspot node.

    Scoring formula (D-02, D-04):
      cluster_score = max_score * 0.40
                     + avg_score * 0.30
                     + normalized_support_count * 0.20
                     + density * 0.10
    """

    ancestor_node_id: UUID
    member_node_ids: tuple[UUID, ...]
    member_scores: tuple[float, ...]
    max_score: float
    avg_score: float
    support_count: int
    subtree_candidate_count: int
    density: float


class SubtreeHotspotSelector:
    """Select route nodes whose subtrees are semantically close to a query.

    The selector scores subtree statistics, not node-owned text.  A selected
    parent is a traversal starting point (hotspot head), never a final content
    hit unless it also has direct evidence chunks.
    """

    def select_hotspots(
        self,
        *,
        query_embedding: list[float],
        node_stats: Sequence[dict[str, Any]],
        tree_signals: dict[str, Any],
        limit: int = 3,
    ) -> list[SubtreeHotspot]:
        if limit <= 0:
            return []
        expected_dimension = tree_signals.get("embedding_dimension")
        if (
            isinstance(expected_dimension, int)
            and expected_dimension > 0
            and len(query_embedding) != expected_dimension
        ):
            raise ValueError(
                "query embedding dimension "
                f"{len(query_embedding)} does not match tree embedding dimension "
                f"{expected_dimension}"
            )

        scored_hotspots: list[tuple[SubtreeHotspot, tuple[str, ...]]] = []
        for stats in node_stats:
            node_id = stats.get("node_id")
            if node_id is None:
                continue
            prototype = stats.get("prototype_embedding") or stats.get("centroid")
            if not prototype:
                continue
            similarity = _cosine_similarity(query_embedding, prototype)
            if similarity <= 0.0:
                continue
            path_parts = _heading_path_parts(stats.get("heading_path"))
            depth = max(len(path_parts) - 1, 0)
            is_route_node = bool(stats.get("is_route_node"))
            route_bonus = _ROUTE_NODE_BONUS if is_route_node else 0.0
            depth_bonus = min(depth, _MAX_DEPTH_BONUS_LEVELS) * _DEPTH_BONUS_PER_LEVEL
            root_penalty = _ROOT_ROUTE_PENALTY if is_route_node and depth == 0 else 0.0
            support_count = int(stats.get("support_count", 0))
            support_bonus = (
                min(support_count, _MAX_SUPPORT_BONUS_CHUNKS) * _SUPPORT_BONUS_PER_CHUNK
            )
            score = (
                similarity + route_bonus + depth_bonus + support_bonus - root_penalty
            )
            scored_hotspots.append(
                (
                    SubtreeHotspot(
                        node_id=node_id,
                        score=score,
                        reason=(
                            "subtree_similarity" if is_route_node else "node_similarity"
                        ),
                        support_count=support_count,
                        dispersion=float(stats.get("dispersion", 0.0)),
                        entropy=float(stats.get("entropy", 0.0)),
                    ),
                    path_parts,
                )
            )

        scored_hotspots.sort(key=lambda item: item[0].score, reverse=True)
        selected: list[tuple[SubtreeHotspot, tuple[str, ...]]] = []
        for hotspot, path_parts in scored_hotspots:
            if any(
                _paths_overlap(path_parts, selected_path)
                for _, selected_path in selected
            ):
                continue
            selected.append((hotspot, path_parts))
            if len(selected) >= limit:
                break
        return [hotspot for hotspot, _ in selected]


class ClusterHotspotSelector:
    """Level-agnostic cluster-based hotspot selector.

    Phase 11 D-01: All eligible nodes compete equally by cosine similarity.
    Phase 11 D-02: Hotspot is inferred post-hoc from densest shared region.
    Phase 11 D-03: Candidate breadth uses candidate_top_n = max(limit * 4, 20).
    Phase 11 D-04: Root is excluded or penalized unless no local region exists.

    This selector does NOT apply route-node bonus, depth bonus, or support bonus
    in the first pass. It scores all nodes equally, then infers the hotspot from
    where semantic hits cluster structurally.
    """

    def select_hotspots(
        self,
        *,
        query_embedding: list[float],
        node_stats: Sequence[dict[str, Any]],
        tree_signals: dict[str, Any],
        limit: int = 3,
    ) -> list[SubtreeHotspot]:
        """Select hotspots by cluster inference, not route-node preselection.

        Returns list[SubtreeHotspot] so runtime can switch selectors without
        downstream type churn.
        """
        if limit <= 0:
            return []

        # D-01: Validate embedding dimension (identical to SubtreeHotspotSelector)
        expected_dimension = tree_signals.get("embedding_dimension")
        if (
            isinstance(expected_dimension, int)
            and expected_dimension > 0
            and len(query_embedding) != expected_dimension
        ):
            raise ValueError(
                "query embedding dimension "
                f"{len(query_embedding)} does not match tree embedding dimension "
                f"{expected_dimension}"
            )

        # Build node lookup for ancestor walking
        node_by_id: dict[UUID, dict[str, Any]] = {}
        for stats in node_stats:
            node_id = stats.get("node_id")
            if node_id is not None:
                node_by_id[node_id] = stats

        # D-01: Compute similarity for all eligible nodes (no route bonus)
        semantic_hits: list[NodeSemanticHit] = []
        for stats in node_stats:
            node_id = stats.get("node_id")
            if node_id is None:
                continue
            prototype = stats.get("prototype_embedding") or stats.get("centroid")
            if not prototype:
                continue

            # D-01: Similarity-only scoring (no bonuses)
            similarity = _cosine_similarity(query_embedding, prototype)
            if similarity <= 0.0:
                continue

            # Build path_to_root by walking parent_node_id
            parent_node_id = stats.get("parent_node_id")
            path_to_root = _build_path_to_root(
                node_id=node_id,
                parent_node_id=parent_node_id,
                node_by_id=node_by_id,
            )

            semantic_hits.append(
                NodeSemanticHit(
                    node_id=node_id,
                    similarity=similarity,
                    heading_path=stats.get("heading_path"),
                    parent_node_id=parent_node_id,
                    path_to_root=path_to_root,
                )
            )

        # D-03: Select broader candidate set
        candidate_top_n = max(limit * 4, 20)
        semantic_hits.sort(key=lambda hit: hit.similarity, reverse=True)
        candidates = semantic_hits[:candidate_top_n]

        if not candidates:
            return []

        # D-02: Build ancestor clusters
        cluster_candidates = _build_ancestor_clusters(
            candidates=candidates,
            node_by_id=node_by_id,
        )

        # D-04: Score clusters and select best
        scored_clusters = [
            (cluster, _score_cluster(cluster, candidate_top_n, node_by_id))
            for cluster in cluster_candidates
        ]
        scored_clusters.sort(key=lambda pair: pair[1], reverse=True)

        # D-04: Exclude or penalize root when local clusters exist
        root_node_ids = [
            node_id
            for node_id, stats in node_by_id.items()
            if stats.get("parent_node_id") is None
        ]

        # D-04: Root penalty - prefer local clusters, but allow root when it's the only option
        # Check if we have non-root alternatives before filtering
        has_non_root_alternatives = len(scored_clusters) > 1 and any(
            c.ancestor_node_id not in root_node_ids for c, _ in scored_clusters
        )

        if has_non_root_alternatives:
            # Prefer non-root when alternatives exist
            non_root_clusters = [
                (cluster, score)
                for cluster, score in scored_clusters
                if cluster.ancestor_node_id not in root_node_ids
            ]
            selected_cluster = non_root_clusters[0][0]
        elif scored_clusters:
            # Fallback to root OR single local cluster
            selected_cluster = scored_clusters[0][0]
        else:
            return []

        # Return SubtreeHotspot objects (same shape as old selector)
        hotspots: list[SubtreeHotspot] = []
        ancestor_stats = node_by_id.get(selected_cluster.ancestor_node_id)
        if ancestor_stats is None:
            # Fallback: return strongest member nodes
            for member_id in selected_cluster.member_node_ids[:limit]:
                member_stats = node_by_id.get(member_id)
                if member_stats:
                    hotspots.append(
                        SubtreeHotspot(
                            node_id=member_id,
                            score=selected_cluster.max_score,
                            reason="cluster_member",
                            support_count=selected_cluster.support_count,
                            dispersion=float(member_stats.get("dispersion", 0.0)),
                            entropy=float(member_stats.get("entropy", 0.0)),
                        )
                    )
        else:
            # Return inferred ancestor as hotspot
            hotspots.append(
                SubtreeHotspot(
                    node_id=selected_cluster.ancestor_node_id,
                    score=selected_cluster.max_score,
                    reason="cluster_hotspot",
                    support_count=selected_cluster.support_count,
                    dispersion=float(ancestor_stats.get("dispersion", 0.0)),
                    entropy=float(ancestor_stats.get("entropy", 0.0)),
                )
            )

            # Add top member nodes as additional hits if space remains
            remaining_limit = limit - len(hotspots)
            if remaining_limit > 0:
                for member_id in selected_cluster.member_node_ids[:remaining_limit]:
                    member_stats = node_by_id.get(member_id)
                    if member_stats and member_id != selected_cluster.ancestor_node_id:
                        hotspots.append(
                            SubtreeHotspot(
                                node_id=member_id,
                                score=selected_cluster.max_score,
                                reason="cluster_member",
                                support_count=selected_cluster.support_count,
                                dispersion=float(member_stats.get("dispersion", 0.0)),
                                entropy=float(member_stats.get("entropy", 0.0)),
                            )
                        )

        return hotspots


class HybridClusterHotspotSelector:
    """Hybrid hotspot selector using vector + keyword + optional rerank fusion.

    Phase 11 11-07: Generic cross-domain selector without hardcoded domain-specific terms.
    Phase 12 12-03: Cluster-hot coverage selection with dual-hot gate.

    Fusion weights (documented, not magic):
      _VECTOR_WEIGHT = 0.40: Primary semantic similarity
      _KEYWORD_WEIGHT = 0.30: BM25/exact match evidence
      _EXACT_KEYWORD_WEIGHT = 2.00: Full heading term coverage promotion tuned to beat broad single-term vector hits
      _RERANK_WEIGHT = 0.20: Optional reranker scores (default-off when None)
      _DISTRIBUTION_WEIGHT = 0.10: Child-node distribution bonus (preserved for helper tests)

    Cluster-hot coverage weights (Phase 12, separate from fusion):
      _COVERAGE_THETA = 0.5: Coverage ratio threshold (configurable)
      _MIN_SUPPORT = 2: Minimum dual-hot children for cluster hotspot
      _VECTOR_HOT_THRESHOLD = 0.5: Normalized vector score threshold for child hotness
      _KEYWORD_HOT_MIN_TERMS = 1: Minimum matched query terms for child hotness
      _ROOT_CHILD_BREADTH_CAP = 8: Maximum direct children for root-avoidance
      _COVERAGE_WEIGHT = 0.50: Coverage ratio weight in parent scoring
      _COVERAGE_VECTOR_WEIGHT = 0.30: Average child vector weight in parent scoring
      _COVERAGE_SUPPORT_WEIGHT = 0.20: Support count weight in parent scoring

    Coverage definition (Phase 12 D-01):
      Parent is hotspot iff coverage(P) >= theta AND dual_hot_child_count >= min_support,
      where child_hot(c) = vector_hot(c) AND keyword_hot(c).

    Leaf fallback (Phase 12 D-06):
      When no parent meets coverage, return strongest dual-hot leaf nodes.
      Root is never promoted by coverage alone.
    """

    # Documented weight constants (not magic numbers)
    # Fusion weights (Phase 11 - preserved for helper tests)
    _VECTOR_WEIGHT: float = 0.40
    _KEYWORD_WEIGHT: float = 0.30
    _EXACT_KEYWORD_WEIGHT: float = 2.00
    _RERANK_WEIGHT: float = 0.20
    _DISTRIBUTION_WEIGHT: float = 0.10

    # Cluster-hot coverage weights (Phase 12 - separate from fusion)
    _COVERAGE_THETA: float = 0.5
    _MIN_SUPPORT: int = 2
    _VECTOR_HOT_THRESHOLD: float = 0.5
    _KEYWORD_HOT_MIN_TERMS: int = 1
    _ROOT_CHILD_BREADTH_CAP: int = 8
    _COVERAGE_WEIGHT: float = 0.50
    _COVERAGE_VECTOR_WEIGHT: float = 0.30
    _COVERAGE_SUPPORT_WEIGHT: float = 0.20

    def __init__(
        self,
        *,
        coverage_theta: float = _COVERAGE_THETA,
        min_support: int = _MIN_SUPPORT,
        theta: float | None = None,  # Alias for coverage_theta (backward compat for tests)
    ) -> None:
        """Initialize cluster-hot selector with configurable thresholds.

        Args:
            coverage_theta: Coverage ratio threshold for parent hotspots (default 0.5)
            min_support: Minimum dual-hot children for cluster hotspot (default 2)
            theta: Alias for coverage_theta (backward compatibility)
        """
        # Support theta alias for backward compatibility
        if theta is not None:
            coverage_theta = theta
        self._coverage_theta = coverage_theta
        self._min_support = min_support

    def select_hotspots(
        self,
        *,
        context: HotspotSelectionContext,
        limit: int = 3,
    ) -> list[SubtreeHotspot]:
        """Select hotspots by hybrid fusion scoring.

        Args:
            context: V2 selection context with vector_candidates, keyword_hits, optional rerank_scores
            limit: Maximum hotspots to return

        Returns:
            List of SubtreeHotspot objects (same shape as other selectors)
        """
        if limit <= 0:
            return []

        # Validate embedding dimension
        expected_dimension = context.tree_signals.get("embedding_dimension")
        if (
            isinstance(expected_dimension, int)
            and expected_dimension > 0
            and len(context.query_embedding) != expected_dimension
        ):
            raise ValueError(
                f"query embedding dimension {len(context.query_embedding)} "
                f"does not match tree embedding dimension {expected_dimension}"
            )

        if not context.node_stats:
            return []

        # Build node lookup
        node_by_id = context.node_stats

        # Collect vector candidates (already computed similarity)
        vector_candidates = context.vector_candidates or []

        # Build keyword hit map by node
        keyword_hits_by_node: dict[UUID, list[KeywordSpanHit]] = defaultdict(list)
        for hit in context.keyword_hits or []:
            keyword_hits_by_node[hit.node_id].append(hit)

        # Normalize vector scores
        vector_scores_raw = [c.similarity for c in vector_candidates]
        vector_scores_normalized = _normalize_scores(vector_scores_raw)
        vector_by_node = {
            c.node_id: s for c, s in zip(vector_candidates, vector_scores_normalized)
        }

        # Normalize keyword scores. Heading matches also carry matched_terms,
        # so use term coverage to distinguish a broad one-term hit from a
        # full heading match when raw scores are identical.
        keyword_scores_raw = [h.score for h in context.keyword_hits or []]
        keyword_scores_normalized = _normalize_scores(keyword_scores_raw)
        all_matched_terms = {
            term
            for hit in context.keyword_hits or []
            for term in hit.matched_terms
            if term
        }
        terms_by_node: dict[UUID, set[str]] = defaultdict(set)
        keyword_by_node: dict[UUID, float] = {}
        for hit, norm_score in zip(
            context.keyword_hits or [], keyword_scores_normalized
        ):
            terms_by_node[hit.node_id].update(
                term for term in hit.matched_terms if term
            )
            term_coverage = (
                len(terms_by_node[hit.node_id]) / len(all_matched_terms)
                if all_matched_terms
                else 0.0
            )
            # Take max keyword signal per node: lexical score OR query-term coverage.
            existing = keyword_by_node.get(hit.node_id, 0.0)
            keyword_by_node[hit.node_id] = max(existing, norm_score, term_coverage)
        exact_keyword_nodes = {
            node_id
            for node_id, matched_terms in terms_by_node.items()
            if len(all_matched_terms) > 1 and all_matched_terms.issubset(matched_terms)
        }

        # Normalize rerank scores if present
        rerank_by_node: dict[UUID, float] | None = None
        if context.rerank_scores:
            rerank_scores_raw = list(context.rerank_scores.values())
            rerank_scores_normalized = _normalize_scores(rerank_scores_raw)
            rerank_by_node = {
                node_id: norm_score
                for node_id, norm_score in zip(
                    context.rerank_scores.keys(), rerank_scores_normalized
                )
            }

        # Phase 12: Cluster-hot coverage selection
        # Step 2: Compute hotness sets (dual-hot intersection gate)
        vector_hot = {
            nid for nid, s in vector_by_node.items()
            if s >= self._VECTOR_HOT_THRESHOLD
        }
        keyword_hot = {
            nid for nid, terms in terms_by_node.items()
            if len(terms) >= self._KEYWORD_HOT_MIN_TERMS
        }
        dual_hot = vector_hot & keyword_hot  # INTERSECTION (D-02)

        # Step 3: Build candidate PARENTS from dual_hot children (D-01)
        # Direct parent lookup via node_stats - no fallback scan (B5)
        candidate_parents = set()
        for child_id in dual_hot:
            child_stats = node_by_id.get(child_id)
            if child_stats:
                parent_id = child_stats.get("parent_node_id")
                if parent_id is not None:
                    candidate_parents.add(parent_id)

        # Step 4: Select parents passing coverage + support + root-avoidance
        parent_scores: list[tuple[UUID, float, float, int]] = []
        for parent_id in candidate_parents:
            coverage_ratio, hot_count = _compute_child_coverage_score(
                parent_id=parent_id,
                parent_to_children=context.parent_to_children,
                dual_hot=dual_hot,
            )

            # Coverage gate (D-01, D-05)
            if coverage_ratio < self._coverage_theta:
                continue
            if hot_count < self._min_support:
                continue

            # Root avoidance (D-06)
            parent_stats = node_by_id.get(parent_id)
            if parent_stats:
                children_count = len(context.parent_to_children.get(parent_id, ()))
                if _apply_root_avoidance(
                    parent_id=parent_id,
                    parent_stats=parent_stats,
                    children_count=children_count,
                    breadth_cap=self._ROOT_CHILD_BREADTH_CAP,
                ):
                    continue  # Skip root/very-broad nodes

            # Step 5: Score parent using coverage weights (separate from fusion)
            # Parent score = coverage_ratio * 0.50 + avg_child_vector * 0.30 + support_bonus * 0.20
            avg_child_vector = 0.0
            dual_hot_children = [
                c for c in context.parent_to_children.get(parent_id, ())
                if c in dual_hot
            ]
            if dual_hot_children:
                avg_child_vector = sum(
                    vector_by_node.get(c, 0.0) for c in dual_hot_children
                ) / len(dual_hot_children)

            support_bonus = min(hot_count / 5.0, 1.0)  # Cap at 5 children
            parent_score = (
                coverage_ratio * self._COVERAGE_WEIGHT
                + avg_child_vector * self._COVERAGE_VECTOR_WEIGHT
                + support_bonus * self._COVERAGE_SUPPORT_WEIGHT
            )
            parent_scores.append((parent_id, parent_score, coverage_ratio, hot_count))

        # Sort parents by score
        parent_scores.sort(key=lambda p: p[1], reverse=True)
        selected_parents = parent_scores[:limit]

        # Step 6: Build SubtreeHotspot objects for selected parents
        hotspots: list[SubtreeHotspot] = []
        for parent_id, score, coverage_ratio, hot_count in selected_parents:
            stats = node_by_id.get(parent_id)
            if stats:
                hotspots.append(
                    SubtreeHotspot(
                        node_id=parent_id,
                        score=score,
                        reason="cluster_coverage",
                        support_count=stats.get("support_count", 0),
                        dispersion=float(stats.get("dispersion", 0.0)),
                        entropy=float(stats.get("entropy", 0.0)),
                    )
                )

        # Step 7: Leaf fallback (D-06)
        # If NO parent qualifies, return strongest dual-hot leaf nodes
        if not hotspots:
            leaf_candidates = _apply_leaf_fallback(
                dual_hot=dual_hot,
                exact_keyword_nodes=exact_keyword_nodes,
                vector_by_node=vector_by_node,
                keyword_by_node=keyword_by_node,
                node_by_id=node_by_id,
                parent_to_children=context.parent_to_children,
                limit=limit,
            )

            for nid, score in leaf_candidates:
                stats = node_by_id.get(nid)
                if stats:
                    hotspots.append(
                        SubtreeHotspot(
                            node_id=nid,
                            score=score,
                            reason="leaf_fallback",
                            support_count=stats.get("support_count", 0),
                            dispersion=float(stats.get("dispersion", 0.0)),
                            entropy=float(stats.get("entropy", 0.0)),
                        )
                    )

        return hotspots


def _compute_child_coverage_score(
    *,
    parent_id: UUID,
    parent_to_children: dict[UUID | None, tuple[UUID, ...]],
    dual_hot: set[UUID],
) -> tuple[float, int]:
    """Compute coverage ratio and dual-hot child count for a parent.

    Phase 12 D-01: Coverage(P) = dual_hot_children / direct_children(P).
    Denominator is complete direct-child set from parent_to_children (D-07).

    Args:
        parent_id: Parent node UUID
        parent_to_children: Complete parent→children mapping from tree structure
        dual_hot: Set of child node IDs that are both vector_hot AND keyword_hot

    Returns:
        Tuple of (coverage_ratio, dual_hot_child_count)
    """
    children = parent_to_children.get(parent_id, ())
    denom = len(children)
    hot = sum(1 for c in children if c in dual_hot)
    ratio = hot / denom if denom > 0 else 0.0
    return (ratio, hot)


def _is_child_dual_hot(
    *,
    child_id: UUID,
    vector_hot: set[UUID],
    keyword_hot: set[UUID],
) -> bool:
    """Check if a child node is dual-hot (vector_hot AND keyword_hot).

    Phase 12 D-02: Intersection gate - child must be hot in BOTH dimensions.

    Args:
        child_id: Child node UUID
        vector_hot: Set of child IDs with normalized vector >= threshold
        keyword_hot: Set of child IDs with matched query terms >= threshold

    Returns:
        True if child is in BOTH vector_hot AND keyword_hot sets
    """
    return child_id in vector_hot and child_id in keyword_hot


def _apply_leaf_fallback(
    *,
    dual_hot: set[UUID],
    exact_keyword_nodes: set[UUID],
    vector_by_node: dict[UUID, float],
    keyword_by_node: dict[UUID, float],
    node_by_id: dict[UUID, dict[str, Any]],
    parent_to_children: dict[UUID | None, tuple[UUID, ...]],
    limit: int,
) -> list[tuple[UUID, float]]:
    """Apply leaf fallback when no parent meets coverage threshold.

    Phase 12 D-06: Return strongest dual-hot leaf nodes when parent coverage fails.
    Root avoidance applies only when parent hierarchy exists (parent_to_children non-empty).
    In flat fixtures (no parents), all nodes compete equally in leaf fallback.

    Args:
        dual_hot: Set of dual-hot child node IDs
        exact_keyword_nodes: Set of nodes with full query term coverage
        vector_by_node: Normalized vector scores per node
        keyword_by_node: Normalized keyword scores per node
        node_by_id: Node stats lookup
        parent_to_children: Parent-to-children mapping (determines hierarchy presence)
        limit: Maximum fallback candidates to return

    Returns:
        List of (node_id, combined_score) tuples for leaf fallback
    """
    leaf_candidates: list[tuple[UUID, float]] = []

    # Determine if parent hierarchy exists
    # Empty parent_to_children or only None as parent means flat fixture (no hierarchy)
    has_parent_hierarchy = bool(
        parent_to_children and any(pid is not None for pid in parent_to_children.keys())
    )

    # Priority 1: Exact keyword nodes (full query term coverage)
    # These outrank all other candidates even with lower vector scores
    # Phase 12 D-06: Exact-heading match should beat broad single-term hits
    for nid in exact_keyword_nodes:
        if has_parent_hierarchy:
            stats = node_by_id.get(nid)
            if stats and stats.get("parent_node_id") is None:
                continue  # Skip root only when hierarchy exists

        vector_score = vector_by_node.get(nid, 0.0)
        keyword_score = keyword_by_node.get(nid, 0.0)

        # Exact keyword nodes get heavily boosted keyword weight (0.85)
        # This ensures full coverage beats broad high-vector hits
        combined_score = vector_score * 0.15 + keyword_score * 0.85
        leaf_candidates.append((nid, combined_score))

    # Priority 2: Dual-hot nodes (both vector_hot AND keyword_hot)
    # These have passed the intersection gate but may not have full coverage
    for nid in dual_hot:
        # Skip if already added via exact_keyword tier (avoid duplicates)
        if any(c[0] == nid for c in leaf_candidates):
            continue

        if has_parent_hierarchy:
            stats = node_by_id.get(nid)
            if stats and stats.get("parent_node_id") is None:
                continue

        # Standard dual-hot scoring: vector + keyword equal weight
        vector_score = vector_by_node.get(nid, 0.0)
        keyword_score = keyword_by_node.get(nid, 0.0)
        combined_score = vector_score * 0.5 + keyword_score * 0.5
        leaf_candidates.append((nid, combined_score))

    # Priority 3: Pure vector fallback (if no exact/dual candidates)
    if not leaf_candidates and vector_by_node:
            top_vector_node = max(vector_by_node.items(), key=lambda p: p[1])
            nid, vector_score = top_vector_node
            leaf_candidates.append((nid, vector_score))

    # Sort and take top limit
    leaf_candidates.sort(key=lambda p: p[1], reverse=True)
    return leaf_candidates[:limit]


def _apply_root_avoidance(
    *,
    parent_id: UUID,
    parent_stats: dict[str, Any],
    children_count: int,
    breadth_cap: int,
) -> bool:
    """Check if a parent should be avoided as a hotspot (root or very-broad node).

    Phase 12 D-06: Root is never promoted by coverage alone.
    Very-broad nodes exceed child breadth cap.

    Args:
        parent_id: Parent node UUID
        parent_stats: Parent node stats
        children_count: Number of direct children
        breadth_cap: Maximum allowed children for hotspot eligibility

    Returns:
        True if parent should be AVOIDED (filtered out), False if eligible
    """
    # Root is node with parent_node_id=None
    if parent_stats.get("parent_node_id") is None:
        return True  # Avoid root

    # Very-broad nodes exceed child breadth cap
    if children_count > breadth_cap:
        return True  # Avoid very-broad nodes

    return False  # Eligible


def _build_path_to_root(
    *,
    node_id: UUID,
    parent_node_id: UUID | None,
    node_by_id: dict[UUID, dict[str, Any]],
) -> tuple[UUID, ...]:
    """Walk parent chain to build path_to_root with cycle/depth guards."""
    if parent_node_id is None:
        return (node_id,)

    path: list[UUID] = [node_id]
    current_id = parent_node_id
    visited: set[UUID] = {node_id}
    depth = 0
    max_depth = 256  # Match _MAX_TRAVERSAL_DEPTH

    while current_id is not None and depth < max_depth:
        if current_id in visited:
            # Cycle detected - log warning and return partial path
            logger.warning(
                "ancestor path cycle detected: node_id=%s, cycle_at=%s, path_so_far=%s",
                node_id,
                current_id,
                path,
            )
            break
        visited.add(current_id)
        path.append(current_id)

        parent_stats = node_by_id.get(current_id)
        if parent_stats is None:
            break
        current_id = parent_stats.get("parent_node_id")
        depth += 1

    return tuple(path)


def _build_ancestor_clusters(
    *,
    candidates: list[NodeSemanticHit],
    node_by_id: dict[UUID, dict[str, Any]],
) -> list[ClusterCandidate]:
    """Group candidate hits by ancestors for cluster scoring."""
    ancestor_to_members: dict[UUID, list[NodeSemanticHit]] = defaultdict(list)

    # Each candidate contributes to all its ancestors
    for candidate in candidates:
        for ancestor_id in candidate.path_to_root:
            ancestor_to_members[ancestor_id].append(candidate)

    # Build cluster records
    clusters: list[ClusterCandidate] = []
    for ancestor_id, members in ancestor_to_members.items():
        member_ids = tuple(m.node_id for m in members)
        member_scores = tuple(m.similarity for m in members)
        max_score = max(member_scores)
        avg_score = sum(member_scores) / len(member_scores)
        support_count = len(members)

        # Count total candidates under this ancestor's subtree
        subtree_candidate_count = _count_subtree_candidates(
            ancestor_id=ancestor_id,
            candidates=candidates,
            node_by_id=node_by_id,
        )

        # WR-03: Skip clusters with invalid subtree scope (zero density denominator)
        if subtree_candidate_count == 0:
            logger.warning(
                "cluster ancestor %s has subtree_candidate_count=0 with support_count=%d, skipping",
                ancestor_id,
                support_count,
            )
            continue

        density = support_count / subtree_candidate_count

        clusters.append(
            ClusterCandidate(
                ancestor_node_id=ancestor_id,
                member_node_ids=member_ids,
                member_scores=member_scores,
                max_score=max_score,
                avg_score=avg_score,
                support_count=support_count,
                subtree_candidate_count=subtree_candidate_count,
                density=density,
            )
        )

    return clusters


def _count_subtree_candidates(
    *,
    ancestor_id: UUID,
    candidates: list[NodeSemanticHit],
    node_by_id: dict[UUID, dict[str, Any]],
) -> int:
    """Count how many candidates are in the subtree under ancestor_id."""
    # Build parent-to-children map for subtree traversal
    parent_to_children: dict[UUID, list[UUID]] = defaultdict(list)
    for node_id, stats in node_by_id.items():
        parent_id = stats.get("parent_node_id")
        if parent_id is not None:
            parent_to_children[parent_id].append(node_id)

    # Collect all nodes in subtree under ancestor_id
    subtree_nodes: set[UUID] = set()
    stack = [ancestor_id]
    visited: set[UUID] = set()
    while stack:
        current_id = stack.pop()
        if current_id in visited:
            continue
        visited.add(current_id)
        subtree_nodes.add(current_id)
        stack.extend(parent_to_children.get(current_id, []))

    # Count candidates in this subtree
    candidate_node_ids = {c.node_id for c in candidates}
    return len(candidate_node_ids & subtree_nodes)


def _normalize_scores(scores: list[float]) -> list[float]:
    """Normalize scores to [0.0, 1.0] range preserving ranking.

    Phase 11 11-07: Generic normalization for hybrid fusion scoring.
    Handles vector scores [0-1], BM25 scores [0-20+], rerank scores [0-100].
    """
    if not scores:
        return []

    min_score = min(scores)
    max_score = max(scores)

    # All same value: return midpoint
    if max_score == min_score:
        return [0.5 for _ in scores]

    # Min-max normalization
    return [(s - min_score) / (max_score - min_score) for s in scores]


def _compute_child_distribution_score(
    *,
    target_node_id: UUID,
    hits: list[dict[str, Any]],
    node_stats: dict[UUID, dict[str, Any]],
) -> float:
    """Compute child distribution score for multi-child evidence bonus.

    Phase 11 11-07: Reward nodes with distributed child hits over isolated high-score nodes.
    Uses parent_node_id from hit dicts or node_stats to compute distribution breadth.

    Parent nodes WITHOUT direct hits can still score high when they have descendant evidence.
    This enables cluster-style scoring where parent aggregation beats isolated leaf hits.
    """
    # Count direct hits on target
    direct_hits = [h for h in hits if h.get("node_id") == target_node_id]

    # Get target's parent from node_stats or hit dict
    target_stats = node_stats.get(target_node_id, {})
    target_parent_id = target_stats.get("parent_node_id")
    if target_parent_id is None and direct_hits:
        # Try to get from first direct hit
        target_parent_id = direct_hits[0].get("parent_node_id")

    # Count sibling hits (same parent as target)
    sibling_hits = []
    for h in hits:
        h_parent_id = h.get("parent_node_id") or node_stats.get(
            h.get("node_id"), {}
        ).get("parent_node_id")
        if h_parent_id == target_parent_id and h.get("node_id") != target_node_id:
            sibling_hits.append(h)

    # Count child hits (target is parent of hit)
    child_hits = []
    for h in hits:
        h_parent_id = h.get("parent_node_id") or node_stats.get(
            h.get("node_id"), {}
        ).get("parent_node_id")
        if h_parent_id == target_node_id:
            child_hits.append(h)

    # If no direct hits but has child hits: score based on child aggregation
    if not direct_hits:
        if child_hits:
            # Parent with child evidence: use average child score + breadth bonus
            avg_child_score = sum(h.get("score", 0.0) for h in child_hits) / len(
                child_hits
            )
            # Breadth bonus: more children = higher score
            breadth_bonus = min(len(child_hits) / 5.0, 1.0)  # Cap at 5 children
            return avg_child_score * 0.80 + breadth_bonus * 0.20
        # No direct hits and no child hits: zero score
        return 0.0

    # Direct hit exists: compute full distribution score
    # Direct hit contributes base score
    direct_score = sum(h.get("score", 0.0) for h in direct_hits) / len(direct_hits)

    # Sibling breadth bonus: reward distributed evidence across siblings
    sibling_breadth = len(sibling_hits) / max(len(sibling_hits) + 1, 1)

    # Child depth bonus: reward nodes with descendant evidence
    child_depth = len(child_hits) / max(len(child_hits) + 1, 1)

    return direct_score * 0.60 + sibling_breadth * 0.25 + child_depth * 0.15


def _compute_fusion_score(
    *,
    vector_score: float,
    keyword_score: float,
    rerank_score: float | None = None,
    distribution_score: float = 0.0,
    vector_weight: float = 0.40,
    keyword_weight: float = 0.30,
    rerank_weight: float = 0.20,
    distribution_weight: float = 0.10,
) -> float:
    """Compute weighted fusion score for hybrid hotspot selection.

    Phase 11 11-07: Weighted sum of normalized scores.
    Rerank score is optional (default-off seam).
    """
    # Normalize weights if rerank is None
    if rerank_score is None:
        # Distribute rerank weight to other components
        total_weight = vector_weight + keyword_weight + distribution_weight
        vector_weight = vector_weight / total_weight
        keyword_weight = keyword_weight / total_weight
        distribution_weight = distribution_weight / total_weight
        rerank_contribution = 0.0
    else:
        rerank_contribution = rerank_weight * rerank_score

    return (
        vector_weight * vector_score
        + keyword_weight * keyword_score
        + distribution_weight * distribution_score
        + rerank_contribution
    )


def _score_cluster_base(
    cluster: ClusterCandidate,
    candidate_top_n: int,
) -> float:
    """D-02: Base cluster scoring without semantic awareness.

    Formula weights adjusted for Phase 11 gap closure:
      max_score * 0.20: Reduced to prevent single-node dominance
      avg_score * 0.35: Increased to prioritize cluster consistency
      normalized_support_count * 0.30: Increased to reward cluster breadth
      density * 0.15: Increased to reward tight clustering

    See Phase 11 debug report for empirical validation rationale.
    """
    normalized_support = min(cluster.support_count / candidate_top_n, 1.0)
    return (
        cluster.max_score * 0.20
        + cluster.avg_score * 0.35
        + normalized_support * 0.30
        + cluster.density * 0.15
    )


def _score_cluster(
    cluster: ClusterCandidate,
    candidate_top_n: int,
    node_by_id: dict[UUID, dict[str, Any]],  # noqa: ARG001 - kept for API compatibility
) -> float:
    """D-02: Score cluster by distribution statistics.

    Phase 11 11-07: Removed hardcoded expected_keywords/forbidden_keywords.
    Selector is now generic across domains - no project-specific keyword constants.
    Heading semantic relevance is handled by fusion scoring, not hardcoded bonuses.
    """
    # Pure distribution-based scoring (no domain-specific keyword bonuses)
    return _score_cluster_base(cluster, candidate_top_n)


def _heading_path_parts(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    text = str(value).strip()
    if not text:
        return ()
    separator = " > " if " > " in text else "/"
    return tuple(part.strip() for part in text.split(separator) if part.strip())


def _paths_overlap(first: tuple[str, ...], second: tuple[str, ...]) -> bool:
    if not first or not second:
        return False
    shared_depth = min(len(first), len(second))
    return first[:shared_depth] == second[:shared_depth]


@runtime_checkable
class TreeSemanticTraversalRunner(Protocol):
    """Protocol for tree traversal with semantic distribution guidance.

    This is the Psi-RAG traversal skeleton transplanted into local seams.
    """

    def traverse_tree_for_query(
        self,
        *,
        version_id: UUID,
        query_embedding: list[float],
        registry: SemanticDistributionRegistry,
        policy: TreeBranchDecisionPolicy,
        adapter: TreeSemanticDistributionAdapter,
        max_depth: int | None = None,
        start_node_id: UUID | None = None,
        hotspot_node_id: UUID | None = None,
    ) -> list[QueryHit]: ...


class RecursiveTreeTraversalRunner:
    """Psi-RAG traversal skeleton: recursive descent with policy-guided decisions.

    This implements the traversal loop missing from Phase 1 baseline.
    Uses Phase 1 adapter to compute node stats, and Phase 1 policy to guide descent.
    """

    def traverse_tree_for_query(
        self,
        *,
        version_id: UUID,
        query_embedding: list[float],
        registry: SemanticDistributionRegistry,
        policy: TreeBranchDecisionPolicy,
        adapter: TreeSemanticDistributionAdapter,
        max_depth: int | None = None,
        start_node_id: UUID | None = None,
        hotspot_node_id: UUID | None = None,
    ) -> list[QueryHit]:
        # 1. Get node stats from Phase 1 adapter
        distribution_report = adapter.analyze_tree_semantic_distribution(
            version_id=version_id,
            registry=registry,
        )

        node_stats_list = distribution_report["node_stats"]
        tree_signals = distribution_report["tree_signals"]

        # 2. Build node lookup for parent-child relationships
        nodes = registry.query_tree_nodes_by_version(version_id)
        node_by_id = {node["node_id"]: node for node in nodes}
        doc_id = registry.query_doc_id_by_version(version_id)
        chunk_to_span_ids = _build_ordered_map(
            rows=registry.query_vector_chunk_spans_by_version(version_id),
            key_name="chunk_id",
            value_name="span_id",
        )

        # 3. Resolve traversal starting points.  A hotspot head narrows the
        # search scope; without one, traversal preserves the historical root
        # behavior.
        if start_node_id is not None:
            start_node = node_by_id.get(start_node_id)
            start_nodes = [start_node] if start_node is not None else []
        else:
            start_nodes = [node for node in nodes if node.get("parent_node_id") is None]

        # Hotspot traversal: short-circuit to a dedicated handler that enforces the
        # "waypoint + one-level child chunks" contract. The drill-down decision is
        # deferred to the children level (not made on the hotspot parent), which is
        # what prevents a route-like parent from returning [] and triggering the
        # chunk_id-less fallback (Q18 root cause).
        is_hotspot_traversal = (
            hotspot_node_id is not None
            and start_node_id is not None
            and hotspot_node_id == start_node_id
        )
        if is_hotspot_traversal and start_nodes:
            return self._traverse_hotspot_with_children(
                hotspot_node=start_nodes[0],
                version_id=version_id,
                query_embedding=query_embedding,
                node_stats_list=node_stats_list,
                node_by_id=node_by_id,
                tree_signals=tree_signals,
                policy=policy,
                registry=registry,
                doc_id=doc_id,
                chunk_to_span_ids=chunk_to_span_ids,
                max_depth=max_depth,
            )

        # 4. Traverse from selected starts
        hits: list[QueryHit] = []
        for start_node in start_nodes:
            hits.extend(
                self._traverse_from_node(
                    node=start_node,
                    version_id=version_id,
                    query_embedding=query_embedding,
                    node_stats_list=node_stats_list,
                    node_by_id=node_by_id,
                    tree_signals=tree_signals,
                    policy=policy,
                    registry=registry,
                    doc_id=doc_id,
                    chunk_to_span_ids=chunk_to_span_ids,
                    parent_query_distance=None,
                    navigation_node_ids=(start_node["node_id"],),
                    hotspot_node_id=hotspot_node_id or start_node_id,
                    current_depth=0,
                    max_depth=max_depth,
                )
            )

        return hits

    def _traverse_from_node(
        self,
        *,
        node: dict[str, Any],
        version_id: UUID,
        query_embedding: list[float],
        node_stats_list: list[dict[str, Any]],
        node_by_id: dict[UUID, dict[str, Any]],
        tree_signals: dict[str, Any],
        policy: TreeBranchDecisionPolicy,
        registry: SemanticDistributionRegistry,
        doc_id: UUID,
        chunk_to_span_ids: dict[UUID, list[UUID]],
        parent_query_distance: float | None,
        navigation_node_ids: tuple[UUID, ...],
        hotspot_node_id: UUID | None,
        current_depth: int,
        max_depth: int | None,
    ) -> list[QueryHit]:
        node_id = node["node_id"]
        if current_depth > _MAX_TRAVERSAL_DEPTH:
            return []

        # 1. Find stats for this node
        node_stats = next(
            (stats for stats in node_stats_list if stats["node_id"] == node_id),
            None,
        )
        if node_stats is None:
            return []

        # 2. Compute similarity to query using transplanted Psi-RAG prototype embedding
        prototype_embedding = node_stats.get("prototype_embedding") or node_stats.get(
            "centroid", []
        )
        similarity = _cosine_similarity(query_embedding, prototype_embedding)
        query_distance = 1.0 - similarity
        effective_parent_query_distance = (
            parent_query_distance
            if parent_query_distance is not None
            else query_distance
        )
        enriched_node_stats = {
            **node_stats,
            "query_distance": query_distance,
            "parent_query_distance": effective_parent_query_distance,
        }

        # 3. Policy decides action
        decision = policy.decide_branch_action(
            node_stats=enriched_node_stats,
            tree_signals=tree_signals,
        )

        # 4. Execute decision
        hits: list[QueryHit] = []

        if decision == "keep_parent":
            # Collect evidence from this node
            hits.extend(
                _build_hits_from_node(
                    node_stats=enriched_node_stats,
                    version_id=version_id,
                    doc_id=doc_id,
                    similarity=similarity,
                    chunk_to_span_ids=chunk_to_span_ids,
                    hotspot_node_id=hotspot_node_id,
                    navigation_node_ids=navigation_node_ids,
                    drill_depth=current_depth,
                )
            )

        elif decision == "drill_down":
            # Check depth limit
            if max_depth is not None and current_depth >= max_depth:
                return []

            child_nodes = [
                node_by_id[child_id]
                for child_id in node_by_id
                if node_by_id[child_id].get("parent_node_id") == node_id
            ]
            if not child_nodes:
                return []

            child_stats_by_id = {
                stats["node_id"]: stats
                for stats in node_stats_list
                if stats["node_id"]
                in {child_node["node_id"] for child_node in child_nodes}
            }

            if hasattr(policy, "evaluate_children"):
                child_stats = []
                for child_node in child_nodes:
                    child_node_stats = child_stats_by_id.get(child_node["node_id"])
                    if child_node_stats is None:
                        continue
                    child_prototype = child_node_stats.get(
                        "prototype_embedding"
                    ) or child_node_stats.get("centroid", [])
                    child_similarity = _cosine_similarity(
                        query_embedding, child_prototype
                    )
                    child_query_distance = 1.0 - child_similarity
                    child_stats.append(
                        {
                            **child_node_stats,
                            "query_distance": child_query_distance,
                            "parent_query_distance": query_distance,
                        }
                    )

                child_result = policy.evaluate_children(
                    child_stats=child_stats,
                    tree_signals=tree_signals,
                )
                aggregate_decision = child_result.get("decision")
                selected_child_id = child_result.get("selected_child_id")

                if aggregate_decision == "keep_parent":
                    hits.extend(
                        _build_hits_from_node(
                            node_stats=enriched_node_stats,
                            version_id=version_id,
                            doc_id=doc_id,
                            similarity=similarity,
                            chunk_to_span_ids=chunk_to_span_ids,
                            hotspot_node_id=hotspot_node_id,
                            navigation_node_ids=navigation_node_ids,
                            drill_depth=current_depth,
                        )
                    )
                    return hits

                if (
                    aggregate_decision == "drill_down"
                    and selected_child_id in node_by_id
                ):
                    hits.extend(
                        self._traverse_from_node(
                            node=node_by_id[selected_child_id],
                            version_id=version_id,
                            query_embedding=query_embedding,
                            node_stats_list=node_stats_list,
                            node_by_id=node_by_id,
                            tree_signals=tree_signals,
                            policy=policy,
                            registry=registry,
                            doc_id=doc_id,
                            chunk_to_span_ids=chunk_to_span_ids,
                            parent_query_distance=query_distance,
                            navigation_node_ids=(
                                *navigation_node_ids,
                                selected_child_id,
                            ),
                            hotspot_node_id=hotspot_node_id,
                            current_depth=current_depth + 1,
                            max_depth=max_depth,
                        )
                    )
                    return hits

                return []

            # Fallback: recursively visit children prioritized by similarity
            child_nodes_with_similarity = [
                (
                    child_node,
                    _cosine_similarity(
                        query_embedding,
                        next(
                            (
                                stats.get("prototype_embedding") or stats["centroid"]
                                for stats in node_stats_list
                                if stats["node_id"] == child_node["node_id"]
                            ),
                            [],
                        ),
                    ),
                )
                for child_node in child_nodes
            ]
            child_nodes_with_similarity.sort(key=lambda pair: pair[1], reverse=True)

            for child_node, _ in child_nodes_with_similarity:
                hits.extend(
                    self._traverse_from_node(
                        node=child_node,
                        version_id=version_id,
                        query_embedding=query_embedding,
                        node_stats_list=node_stats_list,
                        node_by_id=node_by_id,
                        tree_signals=tree_signals,
                        policy=policy,
                        registry=registry,
                        doc_id=doc_id,
                        chunk_to_span_ids=chunk_to_span_ids,
                        parent_query_distance=query_distance,
                        navigation_node_ids=(
                            *navigation_node_ids,
                            child_node["node_id"],
                        ),
                        hotspot_node_id=hotspot_node_id,
                        current_depth=current_depth + 1,
                        max_depth=max_depth,
                    )
                )

        # "prune" decision: no hits collected

        return hits

    def _traverse_hotspot_with_children(
        self,
        *,
        hotspot_node: dict[str, Any] | None,
        version_id: UUID,
        query_embedding: list[float],
        node_stats_list: list[dict[str, Any]],
        node_by_id: dict[UUID, dict[str, Any]],
        tree_signals: dict[str, Any],
        policy: TreeBranchDecisionPolicy,
        registry: SemanticDistributionRegistry,
        doc_id: UUID,
        chunk_to_span_ids: dict[UUID, list[UUID]],
        max_depth: int | None,
    ) -> list[QueryHit]:
        """Hotspot traversal: return hotspot waypoint + one-level child chunks.

        Design principle: "热点总结节点本身一定是小节点，需要下钻，默认热点返回逻辑就是要带小节点的"

        Workflow:
        1. Build waypoint hit from hotspot node (navigation marker, chunk_id=MISSING_CHUNK_ID)
        2. Collect one-level children (direct children, NOT descendants)
        3. Enrich child stats with similarity
        4. Build evidence hits from children with real chunk_ids
        5. Apply policy.evaluate_children on children (if available) to decide further drilling
        """
        if hotspot_node is None:
            return []

        hotspot_node_id = hotspot_node["node_id"]

        # Step 1: Build waypoint FIRST so it is always present
        waypoint_hits = _build_waypoint_hit(
            node=hotspot_node,
            version_id=version_id,
            doc_id=doc_id,
            chunk_to_span_ids=chunk_to_span_ids,
            hotspot_node_id=hotspot_node_id,
            navigation_node_ids=(hotspot_node_id,),
        )

        # Step 2: Collect ONE level of direct children
        child_nodes = [
            node_by_id[child_id]
            for child_id in node_by_id
            if node_by_id[child_id].get("parent_node_id") == hotspot_node_id
        ]

        if not child_nodes:
            # Edge case: hotspot has no children - return waypoint only (P13-05)
            return waypoint_hits

        # Step 3: Build stats lookup and enrich child stats with similarity
        stats_by_id = {s["node_id"]: s for s in node_stats_list}
        child_stats_with_similarity: list[dict[str, Any]] = []

        for child_node in child_nodes:
            cstats = stats_by_id.get(child_node["node_id"])
            if cstats is None:
                continue
            prototype = cstats.get("prototype_embedding") or cstats.get("centroid", [])
            if not prototype:
                # Pitfall 5 — do not let empty prototype yield silent 0.0
                continue
            similarity = _cosine_similarity(query_embedding, prototype)
            child_stats_with_similarity.append({
                **cstats,
                "query_distance": 1.0 - similarity,
                "similarity": similarity,
                "parent_query_distance": None,
            })

        # Step 4: Build evidence hits from children that carry direct chunk_ids
        # Route-only children (no chunk_ids) yield none — P13-06
        evidence_hits: list[QueryHit] = []
        for cstats in child_stats_with_similarity:
            if cstats.get("chunk_ids"):
                evidence_hits.extend(
                    _build_hits_from_node(
                        node_stats=cstats,
                        version_id=version_id,
                        doc_id=doc_id,
                        similarity=cstats["similarity"],
                        chunk_to_span_ids=chunk_to_span_ids,
                        hotspot_node_id=hotspot_node_id,
                        navigation_node_ids=(hotspot_node_id, cstats["node_id"]),
                        drill_depth=1,
                    )
                )

        # Step 5: Child-level decision (optional further drill)
        # Anti-Pattern 4 guard — only call with non-empty stats
        if hasattr(policy, "evaluate_children") and child_stats_with_similarity:
            child_result = policy.evaluate_children(
                child_stats=child_stats_with_similarity,
                tree_signals=tree_signals,
            )

            if (
                child_result.get("decision") == "drill_down"
                and child_result.get("selected_child_id") in node_by_id
            ):
                selected_child_id = child_result["selected_child_id"]
                # Pitfall 3 — re-enter standard traversal at current_depth=2
                # If selected child is route node without stats, it returns [],
                # which only affects optional drill, not one-level evidence already collected
                evidence_hits.extend(
                    self._traverse_from_node(
                        node=node_by_id[selected_child_id],
                        version_id=version_id,
                        query_embedding=query_embedding,
                        node_stats_list=node_stats_list,
                        node_by_id=node_by_id,
                        tree_signals=tree_signals,
                        policy=policy,
                        registry=registry,
                        doc_id=doc_id,
                        chunk_to_span_ids=chunk_to_span_ids,
                        parent_query_distance=None,
                        navigation_node_ids=(hotspot_node_id, selected_child_id),
                        hotspot_node_id=hotspot_node_id,
                        current_depth=2,
                        max_depth=max_depth,
                    )
                )

        # Return waypoint + evidence hits
        return waypoint_hits + evidence_hits


def _cosine_similarity(vector_a: Sequence[float], vector_b: Sequence[float]) -> float:
    """Compute cosine similarity between same-dimensional vectors."""
    if not vector_a or not vector_b:
        logger.warning(
            "cosine_similarity received empty vector: len(a)=%d, len(b)=%d",
            len(vector_a),
            len(vector_b),
        )
        return 0.0
    if len(vector_a) != len(vector_b):
        raise ValueError(
            f"vectors must share the same dimension; got {len(vector_a)} and {len(vector_b)}"
        )

    dot_product = sum(a * b for a, b in zip(vector_a, vector_b, strict=True))
    norm_a = math.sqrt(sum(a * a for a in vector_a))
    norm_b = math.sqrt(sum(b * b for b in vector_b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)


def _build_hits_from_node(
    *,
    node_stats: dict[str, Any],
    version_id: UUID,
    doc_id: UUID,
    similarity: float,
    chunk_to_span_ids: dict[UUID, list[UUID]],
    hotspot_node_id: UUID | None,
    navigation_node_ids: tuple[UUID, ...],
    drill_depth: int,
) -> list[QueryHit]:
    """Build final evidence-bearing QueryHits from direct node chunks only.

    Route nodes can aggregate descendant semantics for hotspot selection, but
    their ``chunk_ids`` remain limited to direct evidence. This function never
    transplants descendant chunks onto a parent waypoint, so a route-only parent
    produces no final hits and remains navigation metadata only.
    """
    node_id = node_stats["node_id"]
    chunk_ids = node_stats.get("chunk_ids", [])

    hits: list[QueryHit] = []
    for chunk_id in chunk_ids:
        span_ids = chunk_to_span_ids.get(chunk_id, [])
        if not span_ids:
            continue
        for span_id in span_ids:
            hits.append(
                QueryHit(
                    doc_id=doc_id,
                    version_id=version_id,
                    span_id=span_id,
                    chunk_id=chunk_id,
                    node_id=node_id,
                    similarity_score=similarity,
                    hotspot_node_id=hotspot_node_id,
                    navigation_node_ids=navigation_node_ids,
                    drill_depth=drill_depth,
                )
            )

    return hits


def _build_waypoint_hit(
    *,
    node: dict[str, Any],
    version_id: UUID,
    doc_id: UUID,
    chunk_to_span_ids: dict[UUID, list[UUID]],
    hotspot_node_id: UUID | None,
    navigation_node_ids: tuple[UUID, ...],
) -> list[QueryHit]:
    """Build a waypoint hit (navigation marker) from a hotspot node.

    A waypoint marks the hotspot in the traversal path; it is NOT real evidence
    content. chunk_id is the MISSING sentinel so _map_query_hits_to_backend_hits
    (runtime.py:512) skips it from backend output while it still prevents an empty
    traversal result for hotspot-with-children traversal.
    """
    node_id = node["node_id"]
    span_id_placeholder = UUID(int=node_id.int & (2**63 - 1))
    return [
        QueryHit(
            doc_id=doc_id,
            version_id=version_id,
            span_id=span_id_placeholder,
            chunk_id=_MISSING_CHUNK_ID,
            node_id=node_id,
            similarity_score=0.0,
            hotspot_node_id=hotspot_node_id,
            navigation_node_ids=navigation_node_ids,
            drill_depth=0,
        )
    ]


def get_hotspot_selector(strategy: str):
    """Factory function for hotspot selector instantiation.

    Phase 11: Config-driven selector switch for rollback safety.

    Args:
        strategy: "route_subtree" (Phase 10), "cluster" (Phase 11), or "hybrid_cluster" (Phase 11 11-07)

    Returns:
        SubtreeHotspotSelector, ClusterHotspotSelector, or HybridClusterHotspotSelector instance

    Raises:
        ValueError: if strategy is not recognized
    """
    if strategy == "route_subtree":
        return SubtreeHotspotSelector()
    elif strategy == "cluster":
        return ClusterHotspotSelector()
    elif strategy == "hybrid_cluster":
        return HybridClusterHotspotSelector()
    else:
        raise ValueError(f"Unknown hotspot selector strategy: {strategy}")
