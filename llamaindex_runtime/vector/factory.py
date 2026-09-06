from __future__ import annotations

from typing import Any, Sequence

from llamaindex_runtime.integration import load_vector_store_index_class


def create_vector_index(nodes: Sequence[object], **kwargs: Any) -> Any:
    vector_store_index_class = load_vector_store_index_class()
    return vector_store_index_class(list(nodes), **kwargs)
