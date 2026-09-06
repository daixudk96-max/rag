from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any


class TreeGenerator:
    def generate_tree(self, spans: list[dict[str, Any]], *, version_id: uuid.UUID) -> dict[str, list[dict[str, Any]]]:
        nodes: list[dict[str, Any]] = []
        node_spans: list[dict[str, Any]] = []
        key_to_id: dict[tuple[str, int], uuid.UUID] = {}
        paths = defaultdict(list)

        for span in spans:
            heading_path = span.get("heading_path") or "(root)"
            parts = [p.strip() for p in heading_path.split(" > ") if p.strip()]
            if not parts:
                parts = ["(root)"]
            paths[tuple(parts)].append(span)

        for parts, grouped_spans in sorted(paths.items()):
            parent_id: uuid.UUID | None = None
            for idx, part in enumerate(parts):
                key = (" > ".join(parts[: idx + 1]), idx)
                if key not in key_to_id:
                    node_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{version_id}:{key[0]}:{idx}")
                    key_to_id[key] = node_id
                    page_numbers = [s.get("page_no") for s in grouped_spans if s.get("page_no") is not None]
                    nodes.append(
                        {
                            "node_id": node_id,
                            "version_id": version_id,
                            "parent_node_id": parent_id,
                            "node_type": "chapter" if idx == 0 else "section",
                            "level_no": idx,
                            "title": part,
                            "heading_path": key[0],
                            "page_start": min(page_numbers) if page_numbers else None,
                            "page_end": max(page_numbers) if page_numbers else None,
                            "summary_text": None,
                        }
                    )
                parent_id = key_to_id[key]

            leaf_id = parent_id
            for ordinal, span in enumerate(grouped_spans):
                node_spans.append(
                    {
                        "node_id": leaf_id,
                        "span_id": span["span_id"],
                        "ordinal_no": ordinal,
                    }
                )

        return {"nodes": nodes, "node_spans": node_spans}
