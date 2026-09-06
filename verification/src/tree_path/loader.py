from __future__ import annotations

from typing import Any


class TreeLoader:
    def load(self, conn, generated: dict[str, list[dict[str, Any]]], *, attach_leaf_node_ids: bool = False) -> dict[str, int]:
        nodes = generated.get("nodes", [])
        node_spans = generated.get("node_spans", [])
        with conn.transaction(), conn.cursor() as cur:
            for node in nodes:
                cur.execute(
                    "INSERT INTO tree_nodes (node_id, version_id, parent_node_id, node_type, level_no, title, heading_path, page_start, page_end, summary_text) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        str(node["node_id"]),
                        str(node["version_id"]),
                        str(node["parent_node_id"]) if node["parent_node_id"] else None,
                        node["node_type"],
                        node["level_no"],
                        node["title"],
                        node["heading_path"],
                        node["page_start"],
                        node["page_end"],
                        node["summary_text"],
                    ),
                )
            for mapping in node_spans:
                cur.execute(
                    "INSERT INTO tree_node_spans (node_id, span_id, ordinal_no) VALUES (%s, %s, %s)",
                    (str(mapping["node_id"]), str(mapping["span_id"]), mapping["ordinal_no"]),
                )
            if attach_leaf_node_ids:
                for mapping in node_spans:
                    cur.execute(
                        """
                        UPDATE vector_chunks vc
                        SET node_id = %s
                        WHERE vc.version_id IN (
                            SELECT cs.version_id FROM canonical_spans cs WHERE cs.span_id = %s
                        )
                        AND EXISTS (
                            SELECT 1 FROM vector_chunk_spans vcs
                            WHERE vcs.chunk_id = vc.chunk_id AND vcs.span_id = %s
                        )
                        """,
                        (str(mapping["node_id"]), str(mapping["span_id"]), str(mapping["span_id"])),
                    )
        return {"node_count": len(nodes), "node_span_count": len(node_spans)}
