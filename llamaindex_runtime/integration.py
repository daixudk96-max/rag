from __future__ import annotations

from importlib import import_module
from typing import Any


def _load_attr(module_path: str, attr_name: str) -> Any:
    module = import_module(module_path)
    return getattr(module, attr_name)


def load_vector_store_index_class() -> Any:
    return _load_attr("llama_index.core", "VectorStoreIndex")


def load_hierarchical_node_parser_class() -> Any:
    return _load_attr("llama_index.core.node_parser", "HierarchicalNodeParser")


def load_auto_merging_retriever_class() -> Any:
    return _load_attr("llama_index.core.retrievers", "AutoMergingRetriever")


def load_docling_reader_class() -> Any:
    try:
        return _load_attr("llama_index.readers.docling", "DoclingReader")
    except (AttributeError, ModuleNotFoundError):
        try:
            return _load_attr("llama_index.readers.file", "DoclingReader")
        except (AttributeError, ModuleNotFoundError) as fallback_error:
            raise ModuleNotFoundError(
                "DoclingReader is unavailable. Install llama-index-readers-docling and docling."
            ) from fallback_error


def load_docling_node_parser_class() -> Any:
    try:
        return _load_attr("llama_index.node_parser.docling", "DoclingNodeParser")
    except (AttributeError, ModuleNotFoundError) as exc:
        raise ModuleNotFoundError(
            "DoclingNodeParser is unavailable. Install llama-index-node-parser-docling and docling."
        ) from exc


