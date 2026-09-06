from __future__ import annotations

import sys
import types

from llamaindex_runtime.integration import (
    load_docling_node_parser_class,
    load_docling_reader_class,
)
from llamaindex_runtime.tree import build_tree_nodes, create_auto_merging_retriever
from llamaindex_runtime.vector import create_vector_index


def _install_module(
    monkeypatch, module_name: str, **attrs: object
) -> types.ModuleType:  # noqa: ANN001
    module = types.ModuleType(module_name)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, module_name, module)
    return module


def test_docling_loaders_use_expected_import_paths(monkeypatch) -> None:  # noqa: ANN001
    class FakeReader:
        pass

    class FakeNodeParser:
        pass

    _install_module(monkeypatch, "llama_index", __path__=[])
    _install_module(monkeypatch, "llama_index.readers", __path__=[])
    _install_module(monkeypatch, "llama_index.node_parser", __path__=[])
    _install_module(
        monkeypatch, "llama_index.readers.docling", DoclingReader=FakeReader
    )
    _install_module(
        monkeypatch, "llama_index.node_parser.docling", DoclingNodeParser=FakeNodeParser
    )

    assert load_docling_reader_class() is FakeReader
    assert load_docling_node_parser_class() is FakeNodeParser


def test_vector_factory_uses_vector_store_index(monkeypatch) -> None:  # noqa: ANN001
    class FakeVectorStoreIndex:
        def __init__(self, nodes, **kwargs):  # noqa: ANN001
            self.nodes = nodes
            self.kwargs = kwargs

    _install_module(monkeypatch, "llama_index", __path__=[])
    _install_module(
        monkeypatch, "llama_index.core", VectorStoreIndex=FakeVectorStoreIndex
    )

    index = create_vector_index(["node-1", "node-2"], embed_model="demo")

    assert index.nodes == ["node-1", "node-2"]
    assert index.kwargs == {"embed_model": "demo"}


def test_tree_factories_use_hierarchical_parser_and_auto_merging_retriever(
    monkeypatch,
) -> None:  # noqa: ANN001
    class FakeHierarchicalNodeParser:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        @classmethod
        def from_defaults(cls, **kwargs):
            return cls(**kwargs)

        def get_nodes_from_documents(self, documents):  # noqa: ANN001
            return [f"tree:{document}" for document in documents]

    class FakeAutoMergingRetriever:
        def __init__(self, base_retriever, storage_context, **kwargs):  # noqa: ANN001
            self.base_retriever = base_retriever
            self.storage_context = storage_context
            self.kwargs = kwargs

    _install_module(monkeypatch, "llama_index", __path__=[])
    _install_module(monkeypatch, "llama_index.core", __path__=[])
    _install_module(
        monkeypatch,
        "llama_index.core.node_parser",
        HierarchicalNodeParser=FakeHierarchicalNodeParser,
    )
    _install_module(
        monkeypatch,
        "llama_index.core.retrievers",
        AutoMergingRetriever=FakeAutoMergingRetriever,
    )

    nodes = build_tree_nodes(["doc-a"], chunk_sizes=[512, 128])
    retriever = create_auto_merging_retriever("base", "storage", verbose=True)

    assert nodes == ["tree:doc-a"]
    assert retriever.base_retriever == "base"
    assert retriever.storage_context == "storage"
    assert retriever.kwargs == {"verbose": True}
