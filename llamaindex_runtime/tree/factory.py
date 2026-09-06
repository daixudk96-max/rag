from __future__ import annotations

from typing import Any, Sequence

from llamaindex_runtime.integration import load_auto_merging_retriever_class, load_hierarchical_node_parser_class


def build_tree_nodes(documents: Sequence[object], **kwargs: Any) -> list[object]:
    parser_class = load_hierarchical_node_parser_class()
    parser = parser_class.from_defaults(**kwargs) if hasattr(parser_class, "from_defaults") else parser_class(**kwargs)
    return list(parser.get_nodes_from_documents(list(documents)))


def create_auto_merging_retriever(base_retriever: object, storage_context: object, **kwargs: Any) -> Any:
    retriever_class = load_auto_merging_retriever_class()
    return retriever_class(base_retriever, storage_context, **kwargs)
