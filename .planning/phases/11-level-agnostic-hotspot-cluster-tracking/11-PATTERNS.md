# Phase 11: Level-Agnostic Hotspot Cluster Tracking - Pattern Map

**Mapped:** 2026-06-17
**Files analyzed:** 8
**Analogs found:** 7 / 8

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `llamaindex_runtime/tree/semantic_distribution.py` (新增 dataclasses) | model | CRUD | `llamaindex_runtime/tree/semantic_distribution.py` (现有 `QueryHit`, `SubtreeHotspot`) | exact |
| `llamaindex_runtime/tree/semantic_distribution.py` (新增 `ClusterHotspotSelector`) | service | CRUD | `llamaindex_runtime/tree/semantic_distribution.py::SubtreeHotspotSelector` | exact |
| `llamaindex_runtime/tree/runtime.py` (修改 selector switch) | controller | request-response | `llamaindex_runtime/tree/runtime.py::_retrieve_tree_hits_from_backend` | exact |
| `tests/llamaindex_runtime/test_tree_semantic_hotspot.py` (新增测试) | test | validation | `tests/llamaindex_runtime/test_tree_semantic_hotspot.py::TestSubtreeHotspotSelector` | exact |
| `verification/phase11-level-agnostic-hotspot-cluster-tracking/validation_runner.py` | utility | batch | `verification/phase10-real-docx-retrieval-validation/run_validation.py` | exact |
| `verification/phase11-level-agnostic-hotspot-cluster-tracking/validation_corpus.md` | config | batch | `verification/p6_validation/p6_final_sample_structured.md` | role-match |
| `.env.example` (添加 `RAG_TREE_HOTSPOT_SELECTOR`) | config | batch | `.env.example` (现有环境变量) | exact |

## Pattern Assignments

### `llamaindex_runtime/tree/semantic_distribution.py` (新增 dataclasses)

**Analog:** `llamaindex_runtime/tree/semantic_distribution.py::QueryHit` (lines 458-476)

**Imports pattern** (lines 1-7):
```python
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Protocol, Sequence, runtime_checkable
from uuid import UUID
```

**Dataclass provenance pattern** (lines 458-476):
```python
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
```

**应用目标:** 新增 `NodeSemanticHit` 和 `ClusterCandidate` dataclasses 应遵循相同模式：
- 使用 `@dataclass(frozen=True)` 保持不可变性
- UUID 字段用于节点标识
- 使用类型注解 (`float`, `UUID`, `tuple[UUID, ...]`)
- 添加 docstring 说明数据语义

---

### `llamaindex_runtime/tree/semantic_distribution.py` (新增 `ClusterHotspotSelector`)

**Analog:** `llamaindex_runtime/tree/semantic_distribution.py::SubtreeHotspotSelector` (lines 490-571)

**Imports pattern** (继承现有 imports):
```python
# 无需新增 imports，继承现有模块 imports
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Sequence
from uuid import UUID
```

**Selector class pattern** (lines 490-571):
```python
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

        # 1. 计算所有节点的相似度 (不应用 route bonus)
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
            # ... scoring logic

        # 2. 排序并选择
        scored_hotspots.sort(key=lambda item: item[0].score, reverse=True)
        # ... overlap filtering
        return [hotspot for hotspot, _ in selected]
```

**Cosine similarity helper pattern** (lines 898-914):
```python
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
```

**Ancestor walking with cycle guard pattern** (lines 266-304):
```python
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
```

**应用目标:**
- `ClusterHotspotSelector` 应遵循相同接口签名 (`select_hotspots` 方法)
- 验证 query embedding dimension (继承现有 dimension check)
- 使用 `_cosine_similarity` 计算节点相似度 (不应用 route-node bonus)
- 使用 ancestor walking pattern 构建 cluster aggregation
- 遵循 `_MAX_TRAVERSAL_DEPTH` 循环防护

**关键差异 (CRITICAL):**
- **禁止应用 `route_bonus`, `depth_bonus`, `root_penalty`, `support_bonus`** (lines 534-543)
- Cluster scoring 公式必须独立实现:
  ```python
  cluster_score = (
      max_score * 0.40
      + avg_score * 0.30
      + normalized_support_count * 0.20
      + density * 0.10
  )
  ```
- 必须添加 root penalty 或 exclusion logic 以避免 root-bias

---

### `llamaindex_runtime/tree/runtime.py` (修改 selector switch)

**Analog:** `llamaindex_runtime/tree/runtime.py::_retrieve_tree_hits_from_backend` (lines 32-99)

**Imports pattern** (lines 1-26):
```python
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Sequence
from uuid import UUID

from llama_index.core import StorageContext
from llama_index.core.base.embeddings.base import BaseEmbedding

from llamaindex_runtime.ingestion.bundle import build_docling_bundle
from llamaindex_runtime.tree.scoring import TreeScoring
from llamaindex_runtime.vector import create_vector_index

from .backend_adapter import BackendHit
from .evidence_content_resolver import EvidenceContentResolver
from .factory import build_tree_nodes, create_auto_merging_retriever
from .hiro_decision_policy import HIROEnhancedTreeBranchDecisionPolicy
from .reasoning_backend import ReasoningTreeBackend
from .semantic_distribution import (
    BaselineTreeBranchDecisionPolicy,
    PersistedTreeSemanticDistributionAdapter,
    QueryHit,
    RecursiveTreeTraversalRunner,
    SubtreeHotspotSelector,
)
```

**Backend retrieval with selector integration pattern** (lines 32-99):
```python
def _retrieve_tree_hits_from_backend(
    query_text: str,
    *,
    version_id: Any,
    registry: Any,
    limit: int,
    embed_model: BaseEmbedding | None = None,
    decision_policy: str = "baseline",
    backend_type: str = "reasoning",
) -> list[dict[str, Any]]:
    nodes = registry.query_tree_nodes_by_version(version_id)
    if not nodes:
        return []

    resolved_backend_type = backend_type.lower()
    if resolved_backend_type == "reasoning":
        reasoning_backend = ReasoningTreeBackend()
        reasoning_hits = reasoning_backend.retrieve_tree_hits(
            query_text=query_text,
            version_id=version_id,
            registry=registry,
            limit=limit,
        )
        return [_backend_hit_to_dict(hit) for hit in reasoning_hits]

    # ... embedding/semantic backend path

    query_embedding = embed_model.get_query_embedding(query_text)
    adapter = PersistedTreeSemanticDistributionAdapter()
    distribution_report = adapter.analyze_tree_semantic_distribution(
        version_id=version_id,
        registry=registry,
    )
    # ... policy selection

    runner = RecursiveTreeTraversalRunner()
    hotspots = SubtreeHotspotSelector().select_hotspots(
        query_embedding=query_embedding,
        node_stats=distribution_report["node_stats"],
        tree_signals=distribution_report["tree_signals"],
        limit=max(limit, 1),
    )

    query_hits: list[QueryHit] = []
    # ... traversal logic
```

**Environment variable switch pattern** (lines 175-176):
```python
if backend_type is None:
    backend_type = os.environ.get("RAG_TREE_BACKEND_TYPE", "reasoning")
```

**应用目标:**
- 添加新环境变量: `RAG_TREE_HOTSPOT_SELECTOR` (默认值 `route_subtree`)
- Import `ClusterHotspotSelector` (新增 import)
- 修改 selector instantiation 逻辑:
  ```python
  hotspot_selector_type = os.environ.get("RAG_TREE_HOTSPOT_SELECTOR", "route_subtree")
  if hotspot_selector_type == "cluster":
      selector = ClusterHotspotSelector()
  else:
      selector = SubtreeHotspotSelector()
  hotspots = selector.select_hotspots(...)
  ```
- 保持 `_retrieve_tree_hits_from_backend` 其他逻辑不变
- 保持 `_map_query_hits_to_backend_hits` 不变 (CRITICAL path 已支持 hotspot metadata)

---

### `tests/llamaindex_runtime/test_tree_semantic_hotspot.py` (新增测试)

**Analog:** `tests/llamaindex_runtime/test_tree_semantic_hotspot.py::TestSubtreeHotspotSelector` (lines 28-96)

**Imports pattern** (lines 11-25):
```python
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from llamaindex_runtime.tree.runtime import _map_query_hits_to_backend_hits
from llamaindex_runtime.tree.semantic_distribution import (
    BaselineTreeBranchDecisionPolicy,
    PersistedTreeSemanticDistributionAdapter,
    QueryHit,
    RecursiveTreeTraversalRunner,
    SubtreeHotspotSelector,
)
```

**Test class structure pattern** (lines 28-96):
```python
class TestSubtreeHotspotSelector:
    """Hotspot selector chooses nearest parent route when descendant has evidence."""

    def test_selector_returns_nearest_parent_when_descendant_has_evidence(self) -> None:
        """When evidence is in descendant, hotspot should be the nearest route parent.

        This avoids root-bias while still treating parent nodes as route-only
        hotspot heads instead of final content hits.
        """
        version_id = uuid.uuid4()
        parent_node_id = uuid.uuid4()
        child_node_id = uuid.uuid4()
        grandchild_node_id = uuid.uuid4()
        span_id = uuid.uuid4()
        chunk_id = uuid.uuid4()

        # Mock registry with tree hierarchy
        registry = MagicMock()
        registry.query_tree_nodes_by_version.return_value = [
            {
                "node_id": parent_node_id,
                "heading_path": "Chapter 1",
                "level_no": 0,
                "parent_node_id": None,
            },
            {
                "node_id": child_node_id,
                "heading_path": "Chapter 1 > Section 1.1",
                "level_no": 1,
                "parent_node_id": parent_node_id,
            },
            {
                "node_id": grandchild_node_id,
                "heading_path": "Chapter 1 > Section 1.1 > Detail",
                "level_no": 2,
                "parent_node_id": child_node_id,
            },
        ]
        # ... mock setup

        report = PersistedTreeSemanticDistributionAdapter().analyze_tree_semantic_distribution(
            version_id=version_id,
            registry=registry,
        )
        hotspots = SubtreeHotspotSelector().select_hotspots(
            query_embedding=[1.0, 2.0],
            node_stats=report["node_stats"],
            tree_signals=report["tree_signals"],
            limit=1,
        )

        assert hotspots
        assert hotspots[0].node_id == child_node_id
```

**应用目标:**
- 新增 `TestClusterHotspotSelector` 类
- 测试方法遵循命名约定:
  - `test_cluster_hotspot_selector_scores_all_nodes_without_route_bonus`
  - `test_cluster_hotspot_selector_selects_densest_shared_ancestor`
  - `test_cluster_hotspot_selector_avoids_root_when_local_cluster_exists`
  - `test_short_exact_heading_node_survives_long_related_text`
  - `test_p6_ai_product_manager_core_dna_routes_to_product_characteristics`
- 使用相同的 mock registry pattern
- Import `ClusterHotspotSelector` (新增 import)

---

### `verification/phase11-level-agnostic-hotspot-cluster-tracking/validation_runner.py`

**Analog:** `verification/phase10-real-docx-retrieval-validation/run_validation.py` (lines 0-150)

**Imports pattern** (lines 0-45):
```python
from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import subprocess
import sys
import uuid
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).resolve().parent
DEFAULT_TOP_K = 5
QUERY_SET = [
    {"query_id": "Q01", "query_text": "AI产品经理的核心DNA是什么？"},
    # ... more queries
]

sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402
import psycopg  # noqa: E402

from llamaindex_runtime.ingestion.pipeline import IngestionPipeline  # noqa: E402
from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter  # noqa: E402
from llamaindex_runtime.registry.tree_generator import TreeGenerator  # noqa: E402
from llamaindex_runtime.tree.runtime import retrieve_tree_hits_from_pdf  # noqa: E402
from llamaindex_runtime.embeddings import SentenceTransformersEmbedding  # noqa: E402
from llamaindex_runtime.vector.loader import VectorLoader  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(message)s")
LOGGER = logging.getLogger(__name__)
```

**Embedding adapter pattern** (lines 50-67):
```python
class RealEmbedder:
    """Adapter to make SentenceTransformersEmbedding compatible with VectorLoader."""
    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._st_embedder = SentenceTransformersEmbedding(model_name=model_name)

    def embed_text(self, text: str) -> list[float]:
        """Adapter method for VectorLoader compatibility."""
        return self._st_embedder._get_text_embedding(text)


class RealEmbedding:
    """Adapter for query embedding."""
    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._embedder = SentenceTransformersEmbedding(model_name=model_name)

    def get_query_embedding(self, query: str) -> list[float]:
        return self._embedder._get_query_embedding(query)
```

**JSON serialization helper pattern** (lines 69-90):
```python
def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def json_default(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def write_json(name: str, payload: dict[str, Any]) -> None:
    (OUT_DIR / name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=json_default) + "\n",
        encoding="utf-8",
    )
```

**应用目标:**
- 复制 Phase 10 validation runner 结构
- 修改 `QUERY_SET` 为 p6 validation corpus (包含 DNA query)
- 添加环境变量设置: `os.environ["RAG_TREE_HOTSPOT_SELECTOR"] = "cluster"`
- 生成 `validation_status.json` 和 `evidence_chain_report.json`
- 验证 metadata rate ≥ 0.90

---

### `verification/phase11-level-agnostic-hotspot-cluster-tracking/validation_corpus.md`

**Analog:** `verification/p6_validation/p6_final_sample_structured.md`

**应用目标:**
- 提供 p6 validation corpus 文本内容
- 包含 "AI产品经理核心DNA" 相关证据链
- 作为 validation_runner.py 的输入参考

---

### `.env.example` (添加 `RAG_TREE_HOTSPOT_SELECTOR`)

**Analog:** `.env.example` (现有配置)

**Environment variable pattern** (lines 15-23):
```text
# ===== Existing runtime settings =====
# Example format: postgresql://username:password@localhost:5432/database_name
DATABASE_URL=__FILL_LOCAL_DATABASE_URL__
VECTOR_BACKEND=pgvector
TREE_STRATEGY=auto_merging
EMBEDDING_PROVIDER=mock
EMBEDDING_MODEL_NAME=all-MiniLM-L6-v2
QDRANT_URL=http://localhost:6333
MILVUS_URL=http://localhost:19530
```

**应用目标:**
- 在 "Existing runtime settings" section 后添加:
  ```text
  # ===== Phase 11 hotspot selector configuration =====
  RAG_TREE_HOTSPOT_SELECTOR=cluster
  ```
- 注释说明可选值: `route_subtree` (default), `cluster` (Phase 11)

---

## Shared Patterns

### Immutable Dataclass with UUID Provenance
**Source:** `llamaindex_runtime/tree/semantic_distribution.py::QueryHit` (lines 458-476)
**Apply to:** All new dataclasses (`NodeSemanticHit`, `ClusterCandidate`)
```python
@dataclass(frozen=True)
class QueryHit:
    """Provenance-anchored hit from tree traversal."""
    doc_id: UUID
    version_id: UUID
    span_id: UUID
    chunk_id: UUID
    node_id: UUID
    similarity_score: float
    hotspot_node_id: UUID | None = None
    navigation_node_ids: tuple[UUID, ...] = ()
    drill_depth: int = 0
```

### Cosine Similarity Computation
**Source:** `llamaindex_runtime/tree/semantic_distribution.py::_cosine_similarity` (lines 898-914)
**Apply to:** Cluster selector similarity scoring
```python
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
```

### Tree Traversal with Depth/Cycle Guards
**Source:** `llamaindex_runtime/tree/semantic_distribution.py::_collect_subtree_values` (lines 266-304)
**Apply to:** Ancestor walking for cluster aggregation
```python
_MAX_TRAVERSAL_DEPTH = 256

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
    if node_id in active_path:
        raise ValueError(f"tree cycle detected at node_id={node_id}")
    # ... traversal logic
```

### Mock Registry Fixture Pattern
**Source:** `tests/llamaindex_runtime/test_tree_semantic_hotspot.py::TestSubtreeHotspotSelector` (lines 28-96)
**Apply to:** All cluster selector tests
```python
registry = MagicMock()
registry.query_tree_nodes_by_version.return_value = [
    {
        "node_id": parent_node_id,
        "heading_path": "Chapter 1",
        "level_no": 0,
        "parent_node_id": None,
    },
    # ... more nodes
]
registry.query_tree_node_spans_by_version.return_value = [...]
registry.query_vector_chunks_by_version.return_value = [...]
registry.query_vector_chunk_spans_by_version.return_value = [...]
registry.query_doc_id_by_version.return_value = uuid.uuid4()

report = PersistedTreeSemanticDistributionAdapter().analyze_tree_semantic_distribution(
    version_id=version_id,
    registry=registry,
)
```

### Backend Hit Metadata Mapping
**Source:** `llamaindex_runtime/tree/runtime.py::_map_query_hits_to_backend_hits` (lines 253-308)
**Apply to:** Runtime backend mapping (preserve existing, no changes needed)
```python
hit_dict = {
    "node_id": hit.node_id,
    "chunk_id": hit.chunk_id,
    "chunk_id_missing": False,
    "score": hit.similarity_score,
    "text_preview": text_preview,
    "heading_path": node.get("heading_path"),
    "span_ids": list(span_ids),
    "hotspot_node_id": hit.hotspot_node_id,
    "navigation_node_ids": list(hit.navigation_node_ids),
    "navigation_path": navigation_path,
    "drill_depth": hit.drill_depth,
    "backend_source": "tree_semantic",
    "retrieval_path": (
        "subtree_hotspot_traversal"
        if hit.hotspot_node_id is not None
        else "semantic_traversal"
    ),
}
```

---

## No Analog Found

Files with no close match in the codebase (planner should use RESEARCH.md patterns instead):

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `verification/phase11-level-agnostic-hotspot-cluster-tracking/validation_corpus.md` | config | batch | p6 corpus 文件不存在于 Phase 10 validation，需从 `verification/p6_validation/` 目录查找 |

---

## Metadata

**Analog search scope:**
- `llamaindex_runtime/tree/semantic_distribution.py` (完整扫描)
- `llamaindex_runtime/tree/runtime.py` (完整扫描)
- `tests/llamaindex_runtime/test_tree_semantic_hotspot.py` (完整扫描)
- `tests/llamaindex_runtime/test_tree_runtime_traversal_integration.py` (完整扫描)
- `verification/phase10-real-docx-retrieval-validation/run_validation.py` (完整扫描)
- `.env.example` (完整扫描)

**Files scanned:** 6
**Pattern extraction date:** 2026-06-17

---

## Critical Pattern Differences

**Route-node bonus prohibition:**
- **禁止移植** `SubtreeHotspotSelector` 的 bonus scoring logic (lines 534-543):
  - `_ROUTE_NODE_BONUS = 0.08`
  - `_DEPTH_BONUS_PER_LEVEL = 0.03`
  - `_MAX_DEPTH_BONUS_LEVELS = 4`
  - `_ROOT_ROUTE_PENALTY = 0.06`
  - `_SUPPORT_BONUS_PER_CHUNK = 0.003`
- Cluster selector 必须使用独立评分公式 (来自 RESEARCH.md)

**Root-bias mitigation:**
- 必须添加 explicit root penalty 或 exclusion logic
- 参考 test `test_cluster_hotspot_selector_avoids_root_when_local_cluster_exists`

**Selector switch gating:**
- Runtime modification 必须使用 environment variable switch
- 保持 `route_subtree` fallback capability (不删除旧 selector)

---

## TDD Test Requirements

**Required test names** (来自 CONTEXT.md lines 99-104):
1. `test_cluster_hotspot_selector_scores_all_nodes_without_route_bonus`
2. `test_cluster_hotspot_selector_selects_densest_shared_ancestor`
3. `test_cluster_hotspot_selector_avoids_root_when_local_cluster_exists`
4. `test_short_exact_heading_node_survives_long_related_text`
5. `test_p6_ai_product_manager_core_dna_routes_to_product_characteristics`

**Validation requirement** (来自 CONTEXT.md line 47-48):
- p6 DNA query 必须返回包含 `数据驱动`, `非确定性`, `持续性` 的证据
- hotspot_node_id 必须为 `00:31 - 产品特性对比` 或 `AI产品经理核心DNA` 本身

---

**Pattern mapping complete. Planner can now reference analog patterns in PLAN.md files.**