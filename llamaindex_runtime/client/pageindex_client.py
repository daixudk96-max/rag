"""PageIndex client integration with Registry seam.

移植PageIndex完整功能 + 扩展Registry写入。
保留PageIndex所有核心功能：workspace管理、lazy-load、工具函数。
扩展：写入Registry（tree_nodes, node_spans）以支持hybrid检索。
"""

import os
import uuid
import json
import asyncio
import concurrent.futures
from pathlib import Path
from typing import Dict, Any, Optional, List

from ..tree.pageindex_adapter import PageIndexTreeAdapter
from ..registry import RegistryWriter, PostgresRegistryWriter
from ..config import RuntimeSettings
from .retrieve import get_document, get_document_structure, get_page_content

META_INDEX = "_meta.json"


def _normalize_retrieve_model(model: str) -> str:
    """Preserve supported Agents SDK prefixes and route other provider paths via LiteLLM."""
    passthrough_prefixes = ("litellm/", "openai/")
    if not model or "/" not in model:
        return model
    if model.startswith(passthrough_prefixes):
        return model
    return f"litellm/{model}"


class EnhancedPageIndexClient:
    """
    PageIndex client integrated with Registry seam.

    保留PageIndex完整功能：
    - Workspace管理（持久化）
    - Lazy-load优化（只加载元数据，按需加载完整树）
    - 工具函数（get_document, get_document_structure, get_page_content）

    扩展Registry集成：
    - index()后写入Registry（tree_nodes, node_spans）
    - 支持hybrid检索（tree + graph + vector）
    """

    def __init__(
        self,
        registry: Optional[RegistryWriter] = None,
        settings: Optional[RuntimeSettings] = None,
        workspace: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        retrieve_model: Optional[str] = None,
    ):
        self.registry = registry
        self.settings = settings or RuntimeSettings.from_env()

        # 配置统一到RuntimeSettings
        if api_key:
            os.environ["OPENAI_API_KEY"] = api_key
        elif not os.getenv("OPENAI_API_KEY") and os.getenv("CHATGPT_API_KEY"):
            os.environ["OPENAI_API_KEY"] = os.getenv("CHATGPT_API_KEY")

        # Workspace路径（优先参数，其次RuntimeSettings）
        self.workspace = Path(workspace or self.settings.pageindex_workspace).expanduser()
        if self.workspace:
            self.workspace.mkdir(parents=True, exist_ok=True)

        # 模型配置（优先参数，其次RuntimeSettings）
        self.model = model or self.settings.llm_model
        self.retrieve_model = _normalize_retrieve_model(retrieve_model or self.model)

        self.documents: Dict[str, Any] = {}
        if self.workspace:
            self._load_workspace()

        # PageIndexTreeAdapter（已有移植）
        self.adapter = PageIndexTreeAdapter()

    def index(
        self,
        file_path: str,
        mode: str = "auto",
        version_id: Optional[str] = None,
        write_to_registry: bool = True,
    ) -> str:
        """
        Index a document and optionally write to Registry.

        Args:
            file_path: 文档路径（PDF或Markdown）
            mode: 索引模式（auto/pdf/md）
            version_id: Registry版本ID（可选，自动生成）
            write_to_registry: 是否写入Registry（默认True）

        Returns:
            doc_id: PageIndex文档ID

        保留PageIndex完整功能：
        - PDF索引（page_index）
        - Markdown索引（md_to_tree）
        - Workspace持久化
        - Lazy-load优化

        扩展Registry集成：
        - 写入tree_nodes
        - 写入node_spans
        - 支持hybrid检索
        """
        file_path = os.path.abspath(os.path.expanduser(file_path))
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        doc_id = str(uuid.uuid4())
        ext = os.path.splitext(file_path)[1].lower()

        is_pdf = ext == '.pdf'
        is_md = ext in ['.md', '.markdown']

        # PageIndex索引（生成树结构）
        if mode == "pdf" or (mode == "auto" and is_pdf):
            print(f"PageIndex indexing PDF: {file_path}")

            # 调用PageIndex donor的page_index（移植版本）
            try:
                from pageindex.page_index import page_index
                import PyPDF2

                result = page_index(
                    doc=file_path,
                    model=self.model,
                    if_add_node_summary='yes',
                    if_add_node_text='yes',
                    if_add_node_id='yes',
                    if_add_doc_description='yes'
                )

                # 提取PDF页面文本（PageIndex原版逻辑）
                pages = []
                with open(file_path, 'rb') as f:
                    pdf_reader = PyPDF2.PdfReader(f)
                    for i, page in enumerate(pdf_reader.pages, 1):
                        pages.append({'page': i, 'content': page.extract_text() or ''})

                tree_structure = result.get('structure', [])

                # 写入Registry（如果启用）
                if write_to_registry and self.registry:
                    # 使用PageIndexTreeAdapter写入Registry
                    self.adapter.index_tree(
                        source_path=file_path,
                        version_id=version_id or doc_id,
                        registry=self.registry,
                    )

                self.documents[doc_id] = {
                    'id': doc_id,
                    'type': 'pdf',
                    'path': file_path,
                    'doc_name': result.get('doc_name', ''),
                    'doc_description': result.get('doc_description', ''),
                    'page_count': len(pages),
                    'structure': tree_structure,
                    'pages': pages,
                    'version_id': version_id or doc_id,
                }

            except ImportError:
                # PageIndex donor未安装，fallback到PageIndexTreeAdapter
                self.adapter.index_tree(
                    source_path=file_path,
                    version_id=version_id or doc_id,
                    registry=self.registry if write_to_registry else None,
                )

                # 从Registry读取树结构（fallback）
                if write_to_registry and self.registry:
                    nodes = self.registry.query_tree_nodes_by_version(version_id or doc_id)
                    tree_structure = self._nodes_to_tree(nodes)
                else:
                    tree_structure = []

                self.documents[doc_id] = {
                    'id': doc_id,
                    'type': 'pdf',
                    'path': file_path,
                    'doc_name': '',
                    'doc_description': '',
                    'page_count': 0,
                    'structure': tree_structure,
                    'pages': [],
                    'version_id': version_id or doc_id,
                }

        elif mode == "md" or (mode == "auto" and is_md):
            print(f"PageIndex indexing Markdown: {file_path}")

            # 调用PageIndex donor的md_to_tree（移植版本）
            try:
                import asyncio
                from pageindex.page_index_md import md_to_tree

                coro = md_to_tree(
                    md_path=file_path,
                    if_thinning=False,
                    if_add_node_summary='yes',
                    summary_token_threshold=200,
                    model=self.model,
                    if_add_doc_description='yes',
                    if_add_node_text='yes',
                    if_add_node_id='yes'
                )

                try:
                    asyncio.get_running_loop()
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        result = pool.submit(asyncio.run, coro).result()
                except RuntimeError:
                    result = asyncio.run(coro)

                tree_structure = result.get('structure', [])

                # 写入Registry（如果启用）
                if write_to_registry and self.registry:
                    # Register document and version in Registry FIRST (FK constraint)
                    registered_doc = self.registry.register_document(
                        source_path=Path(file_path),
                        source_uri=f"file://{file_path}",
                        title=result.get('doc_name', Path(file_path).stem),
                    )
                    # Use version_id from registered document
                    registry_version_id = registered_doc.version_id

                    # Use first tree_structure directly (no second md_to_tree call)
                    flat_nodes = self.adapter._flatten_embedded_tree(
                        tree_structure,
                        version_id=registry_version_id
                    )
                    self.registry.write_tree(
                        version_id=registry_version_id,
                        nodes=flat_nodes,
                        node_spans=[],
                    )
                    # Update version_id to actual Registry version_id
                    version_id = str(registry_version_id)

                self.documents[doc_id] = {
                    'id': doc_id,
                    'type': 'md',
                    'path': file_path,
                    'doc_name': result.get('doc_name', ''),
                    'doc_description': result.get('doc_description', ''),
                    'line_count': result.get('line_count', 0),
                    'structure': tree_structure,
                    'version_id': version_id or doc_id,
                }

            except ImportError:
                # PageIndex donor未安装，fallback到PageIndexTreeAdapter
                self.adapter.index_tree(
                    source_path=file_path,
                    version_id=version_id or doc_id,
                    registry=self.registry if write_to_registry else None,
                )

                # 从Registry读取树结构（fallback）
                if write_to_registry and self.registry:
                    nodes = self.registry.query_tree_nodes_by_version(version_id or doc_id)
                    tree_structure = self._nodes_to_tree(nodes)
                else:
                    tree_structure = []

                self.documents[doc_id] = {
                    'id': doc_id,
                    'type': 'md',
                    'path': file_path,
                    'doc_name': '',
                    'doc_description': '',
                    'line_count': 0,
                    'structure': tree_structure,
                    'version_id': version_id or doc_id,
                }
        else:
            raise ValueError(f"Unsupported file format for: {file_path}")

        print(f"PageIndex indexing complete. Document ID: {doc_id}")

        # Workspace持久化（PageIndex原版逻辑）
        if self.workspace:
            self._save_doc(doc_id)

        # Return version_id (for Registry) instead of doc_id (internal)
        return version_id if write_to_registry and self.registry else doc_id

    @staticmethod
    def _make_meta_entry(doc: dict) -> dict:
        """Build a lightweight meta entry from a document dict."""
        entry = {
            'type': doc.get('type', ''),
            'doc_name': doc.get('doc_name', ''),
            'doc_description': doc.get('doc_description', ''),
            'path': doc.get('path', ''),
            'version_id': doc.get('version_id', ''),
        }
        if doc.get('type') == 'pdf':
            entry['page_count'] = doc.get('page_count')
        elif doc.get('type') == 'md':
            entry['line_count'] = doc.get('line_count')
        return entry

    @staticmethod
    def _read_json(path) -> Optional[dict]:
        """Read a JSON file, returning None on any error."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: corrupt {Path(path).name}: {e}")
            return None

    def _save_doc(self, doc_id: str):
        """Save document to workspace with lazy-load optimization."""
        doc = self.documents[doc_id].copy()

        # Strip text from structure nodes — redundant with pages (PDF only)
        if doc.get('structure') and doc.get('type') == 'pdf':
            from .utils import remove_fields
            doc['structure'] = remove_fields(doc['structure'], fields=['text'])

        path = self.workspace / f"{doc_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)

        self._save_meta(doc_id, self._make_meta_entry(doc))

        # Drop heavy fields; will lazy-load on demand
        self.documents[doc_id].pop('structure', None)
        self.documents[doc_id].pop('pages', None)

    def _rebuild_meta(self) -> dict:
        """Scan individual doc JSON files and return a meta dict."""
        meta = {}
        for path in self.workspace.glob("*.json"):
            if path.name == META_INDEX:
                continue
            doc = self._read_json(path)
            if doc and isinstance(doc, dict):
                meta[path.stem] = self._make_meta_entry(doc)
        return meta

    def _read_meta(self) -> Optional[dict]:
        """Read and validate _meta.json, returning None on any corruption."""
        meta = self._read_json(self.workspace / META_INDEX)
        if meta is not None and not isinstance(meta, dict):
            print(f"Warning: {META_INDEX} is not a JSON object, ignoring")
            return None
        return meta

    def _save_meta(self, doc_id: str, entry: dict):
        """Save meta index."""
        meta = self._read_meta() or self._rebuild_meta()
        meta[doc_id] = entry
        meta_path = self.workspace / META_INDEX
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    def _load_workspace(self):
        """Load workspace meta index."""
        meta = self._read_meta()
        if meta is None:
            meta = self._rebuild_meta()
            if meta:
                print(f"Loaded {len(meta)} document(s) from workspace (legacy mode).")

        for doc_id, entry in meta.items():
            doc = dict(entry, id=doc_id)
            if doc.get('path') and not os.path.isabs(doc['path']):
                doc['path'] = str((self.workspace / doc['path']).resolve())
            self.documents[doc_id] = doc

    def _ensure_doc_loaded(self, doc_id: str):
        """Load full document JSON on demand (structure, pages, etc.)."""
        doc = self.documents.get(doc_id)
        if not doc or doc.get('structure') is not None:
            return
        full = self._read_json(self.workspace / f"{doc_id}.json")
        if not full:
            return
        doc['structure'] = full.get('structure', [])
        if full.get('pages'):
            doc['pages'] = full['pages']

    # 工具函数（PageIndex原版）
    def get_document(self, doc_id: str) -> str:
        """Return document metadata JSON."""
        return get_document(self.documents, doc_id)

    def get_document_structure(self, doc_id: str) -> str:
        """Return document tree structure JSON (without text fields)."""
        if self.workspace:
            self._ensure_doc_loaded(doc_id)
        return get_document_structure(self.documents, doc_id)

    def get_page_content(self, doc_id: str, pages: str) -> str:
        """Return page content for the given pages string (e.g. '5-7', '3,8', '12')."""
        if self.workspace:
            self._ensure_doc_loaded(doc_id)
        return get_page_content(self.documents, doc_id, pages)

    def _nodes_to_tree(self, nodes: List[Any]) -> List[Dict[str, Any]]:
        """
        Convert flat Registry nodes to nested tree structure.

        Helper for fallback scenario when PageIndex donor not installed.
        """
        # Simple implementation: flat list without nesting
        # (Registry nodes are already flat with heading_path)
        return [
            {
                'title': node.get('heading_path', '').split('/')[-1],
                'heading_path': node.get('heading_path', ''),
                'node_id': str(node.get('node_id', '')),
                'level_no': node.get('level_no', 0),
                'nodes': [],  # No nesting in fallback
            }
            for node in nodes
        ]