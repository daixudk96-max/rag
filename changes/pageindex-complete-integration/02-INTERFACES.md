# PageIndex Complete Integration — INTERFACES

## Immutable Contracts (Frozen)

### Registry Seam (MUST PRESERVE)

**Contract**: `RegistryWriter` protocol (llamaindex_runtime/registry/contracts.py)

```python
class RegistryWriter(Protocol):
    def write_tree(self, version_id: UUID, nodes: list[TreeNode], node_spans: list[TreeNodeSpan]) -> None: ...
    def query_tree_nodes_by_version(self, version_id: UUID) -> list[dict]: ...
    def query_tree_node_spans_by_version(self, version_id: UUID) -> list[dict]: ...
    def write_node_embeddings(self, node_embeddings: Sequence[dict]) -> None: ...  # Phase 2 added
    def write_semantic_distribution(self, semantic_distribution: Sequence[dict]) -> None: ...  # Phase 4 added
```

**Frozen Rule**: reasoning_backend MUST use this seam. No direct database writes.

---

### BackendHit Protocol (MUST PRESERVE)

**Contract**: `BackendHit` dataclass (llamaindex_runtime/tree/backend_adapter.py)

```python
@dataclass
class BackendHit:
    score: float | None
    text_preview: str
    heading_path: str | None
    page_no: int | None
    span_ids: Sequence[UUID]
    node_id: UUID
    chunk_id: UUID | None
    # Frozen fields (immutable)
    
    backend_source: str | None = None  # Phase 2 extension
    retrieval_path: str | None = None  # Phase 2 extension
    # Extension fields (provenance metadata)
```

**Frozen Rule**: reasoning_backend MUST return BackendHit format (frozen fields + provenance).

---

### RuntimeSettings Unified Seam (MUST PRESERVE)

**Contract**: `RuntimeSettings.from_env_llm_only()` (llamaindex_runtime/config.py)

```python
@classmethod
def from_env_llm_only(cls) -> dict[str, str | float]:
    """Load only LLM config from .env without DATABASE_URL requirement."""
    return {
        "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
        "llm_model": os.getenv("LLM_MODEL", "gpt-4o-mini"),
        "llm_temperature": float(os.getenv("LLM_TEMPERATURE", "0.0")),
        "openai_base_url": os.getenv("OPENAI_BASE_URL", ""),
    }
```

**Frozen Rule**: reasoning_backend LLM calls MUST route through this seam.

---

## Adapter Seams (Integration Points)

### reasoning_backend → Registry Seam

**Seam**: `ReasoningTreeBackend.retrieve_tree_hits()` → Registry query

```python
# llamaindex_runtime/tree/reasoning_backend.py (TODO resolution required)
def retrieve_tree_hits(self, query_text: str, version_id: UUID, registry: RegistryWriter):
    # 1. Load tree structure from Registry
    nodes = registry.query_tree_nodes_by_version(version_id)
    
    # 2. LLM reasoning to judge relevant nodes (TODO: line 114)
    relevant_nodes = self._llm_reasoning(query_text, nodes)
    
    # 3. Extract provenance (TODO: line 134-137)
    hits = [
        BackendHit(
            heading_path=node.get("heading_path"),
            node_id=uuid.UUID(node.get("node_id")),
            span_ids=[],  # TODO: Map from Registry
            backend_source="reasoning",
            retrieval_path="llm_navigation",
        )
        for node in relevant_nodes
    ]
    
    return hits
```

---

### reasoning_backend → Unified LLM Seam

**Seam**: `_llm_reasoning()` → RuntimeSettings.from_env_llm_only()

```python
def _llm_reasoning(self, query_text: str, tree_nodes: list[dict]) -> list[dict]:
    # Use unified LLM seam (not PageIndex config.yaml)
    llm_config = RuntimeSettings.from_env_llm_only()
    
    # Call LLM to judge relevance (implementation required)
    # ...
```

---

## Preserved Logic (DO NOT REPLACE)

**Existing tree logic MUST be preserved**:

- `llamaindex_runtime/tree/runtime.py`: retrieve_tree_hits_from_backend() (core retrieval)
- `llamaindex_runtime/tree/semantic_distribution.py`: BaselineTreeBranchDecisionPolicy (decision)
- `llamaindex_runtime/tree/hiro_decision_policy.py`: HIROEnhancedTreeBranchDecisionPolicy (HIRO)
- `llamaindex_runtime/tree/scoring.py`: TreeScoring (Jaccard scoring)
- `llamaindex_runtime/analysis/analyzer.py`: HitDistributionAnalyzer (CV + Entropy)

**Integration rule**: reasoning_backend ADDS functionality, does NOT replace existing logic.

---

## Frozen Contract Violations → STOP

Executor MUST stop and report if:
- PageIndex donor modified (frozen contract breach)
- RegistryWriter protocol changed (seam violation)
- BackendHit format altered (output contract breach)
- RuntimeSettings.from_env_llm_only() bypassed (unified seam violation)
- Existing tree logic replaced (preservation violation)

---

**STOP CONDITION**: Immutable contract violation → STOP, report to user immediately.