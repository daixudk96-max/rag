from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Protocol, Sequence, runtime_checkable
from uuid import UUID


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
    return {
        "node_stats": list(node_stats),
        "tree_signals": {
            "node_count": len(tree_nodes),
            "analyzed_node_count": len(node_stats),
            "skipped_chunk_count": skipped_chunk_count,
            "embedding_dimension": embedding_dimension,
        },
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
            (cluster, _score_cluster(cluster, candidate_top_n))
            for cluster in cluster_candidates
        ]
        scored_clusters.sort(key=lambda pair: pair[1], reverse=True)

        # D-04: Exclude or penalize root when local clusters exist
        root_node_ids = [
            node_id
            for node_id, stats in node_by_id.items()
            if stats.get("parent_node_id") is None
        ]

        # Filter out root unless it's the only option
        non_root_clusters = [
            (cluster, score)
            for cluster, score in scored_clusters
            if cluster.ancestor_node_id not in root_node_ids
        ]

        # If non-root clusters exist, prefer them over root
        if non_root_clusters:
            selected_cluster = non_root_clusters[0][0]
        elif scored_clusters:
            # Fallback to root if no other option
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
            # Cycle detected, stop traversal
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

        density = support_count / subtree_candidate_count if subtree_candidate_count > 0 else 0.0

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


def _score_cluster(
    cluster: ClusterCandidate,
    candidate_top_n: int,
) -> float:
    """D-02: Score cluster by max, avg, support, and density.

    Formula:
      cluster_score = max_score * 0.40
                     + avg_score * 0.30
                     + normalized_support_count * 0.20
                     + density * 0.10
    """
    normalized_support = min(cluster.support_count / candidate_top_n, 1.0)
    return (
        cluster.max_score * 0.40
        + cluster.avg_score * 0.30
        + normalized_support * 0.20
        + cluster.density * 0.10
    )


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


def _cosine_similarity(vector_a: Sequence[float], vector_b: Sequence[float]) -> float:
    """Compute cosine similarity between same-dimensional vectors."""
    if not vector_a or not vector_b:
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


def get_hotspot_selector(strategy: str):
    """Factory function for hotspot selector instantiation.

    Phase 11: Config-driven selector switch for rollback safety.

    Args:
        strategy: "route_subtree" (Phase 10 route-node bonus) or "cluster" (Phase 11 level-agnostic)

    Returns:
        SubtreeHotspotSelector or ClusterHotspotSelector instance

    Raises:
        ValueError: if strategy is not recognized
    """
    if strategy == "route_subtree":
        return SubtreeHotspotSelector()
    elif strategy == "cluster":
        return ClusterHotspotSelector()
    else:
        raise ValueError(f"Unknown hotspot selector strategy: {strategy}")
