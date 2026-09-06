# PageIndex Migration Program — INTERFACES

## Immutable Contracts (Frozen)

### Registry Seam (MUST PRESERVE)

**Contract**: `RegistryWriter` protocol (llamaindex_runtime/registry/contracts.py)

```python
class RegistryWriter(Protocol):
    def write_tree(self, version_id: UUID, nodes: list[TreeNode], node_spans: list[TreeNodeSpan]) -> None: ...
    def query_tree_nodes_by_version(self, version_id: UUID) -> list[dict]: ...
    def query_tree_node_spans_by_version(self, version_id: UUID) -> list[dict]: ...
```

**Frozen Rule**: PageIndex migration MUST use this seam. No direct database writes.

### Tree Backend Protocol (MUST PRESERVE)

**Contract**: `TreeBackendAdapter` (llamaindex_runtime/tree/backend_adapter.py)

```python
class TreeBackendAdapter(Protocol):
    def index_tree(self, source_path: str, version_id: UUID, registry: RegistryWriter) -> None: ...
    def retrieve_tree_hits(self, query_text: str, version_id: UUID, registry: RegistryWriter) -> list[BackendHit]: ...
```

**Frozen Rule**: All tree backends (PageIndex, TreeGenerator, Hybrid) MUST implement this protocol.

### BackendHit Output Format (MUST PRESERVE)

**Contract**: `BackendHit` dataclass (llamaindex_runtime/tree/backend_adapter.py)

```python
@dataclass
class BackendHit:
    heading_path: str
    node_id: UUID
    page_no: int | None
    span_ids: list[UUID]
    chunk_id: UUID | None
    text_preview: str
```

**Frozen Rule**: PageIndex retrieve_tree_hits() MUST return BackendHit format.

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

**Frozen Rule**: PageIndex LLM calls MUST route through this seam. No PageIndex config.yaml.

## Adapter Seams (Integration Points)

### EnhancedPageIndexClient → Registry

**Seam**: `PageIndexClient.index()` → `registry.write_tree()`

```python
# llamaindex_runtime/client/pageindex_client.py
def index(self, file_path: str, write_to_registry: bool = True) -> str:
    # PageIndex tree extraction
    structure = md_to_tree(file_path, ...)

    # Registry seam integration
    if write_to_registry:
        self.adapter.index_tree(
            source_path=file_path,
            version_id=version_id,
            registry=self.registry,  # ← RegistryWriter seam
        )
```

### PageIndex LLM → RuntimeSettings

**Seam**: `md_to_tree()` → `RuntimeSettings.from_env_llm_only()`

```python
# llamaindex_runtime/tree/pageindex_adapter.py
def _call_pageindex_md_to_tree(self, source_path: str):
    llm_config = RuntimeSettings.from_env_llm_only()  # ← Unified seam

    result = asyncio.run(
        md_to_tree(
            md_path=source_path,
            model=llm_config["llm_model"],  # ← Unified config
            ...
        )
    )
```

### Retrieve Tools → BackendHit

**Seam**: `get_page_content()` → `BackendHit` format

```python
# llamaindex_runtime/client/retrieve.py
def get_page_content(documents: dict, doc_id: str, pages: str) -> str:
    # PageIndex tool function (preserved)
    content = _get_md_page_content(doc_info, page_nums)

    # BackendHit conversion (integration)
    return json.dumps([
        {'page': p['page'], 'content': p['content']}
        for p in content
    ])
```

## Preserved Logic (DO NOT REPLACE)

**Existing tree logic (Phase 6/8) MUST be preserved**:

- `llamaindex_runtime/tree/runtime.py`: retrieve_tree_hits_from_backend() (core retrieval)
- `llamaindex_runtime/tree/semantic_distribution.py`: BaselineTreeBranchDecisionPolicy (decision strategy)
- `llamaindex_runtime/tree/hiro_decision_policy.py`: HIROEnhancedTreeBranchDecisionPolicy (HIRO transplant)
- `llamaindex_runtime/tree/scoring.py`: TreeScoring (Jaccard scoring)
- `llamaindex_runtime/analysis/analyzer.py`: HitDistributionAnalyzer (CV + Entropy)

**Integration rule**: PageIndex migration ADDS functionality, does NOT replace existing logic.

## Frozen Contract Violations → STOP

Executor MUST stop and report if:
- PageIndex donor code modified (frozen contract breach)
- RegistryWriter protocol changed (seam violation)
- BackendHit format altered (output contract breach)
- RuntimeSettings.from_env_llm_only() bypassed (unified seam violation)

---

**STOP CONDITION**: Immutable contract violation → STOP, report to user immediately.