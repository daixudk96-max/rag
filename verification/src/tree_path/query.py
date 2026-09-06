from __future__ import annotations

import uuid
from typing import Any

from psycopg.rows import dict_row


def rollup_to_parent(conn, node_id: uuid.UUID) -> dict[str, Any] | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT parent_node_id FROM tree_nodes WHERE node_id = %s", (str(node_id),))
        row = cur.fetchone()
        if row is None:
            raise ValueError("node not found")
        parent_node_id = row["parent_node_id"]
        if parent_node_id is None:
            return None
        cur.execute("SELECT * FROM tree_nodes WHERE node_id = %s", (str(parent_node_id),))
        parent = cur.fetchone()
    if parent is None:
        return None
    parent["node_id"] = uuid.UUID(str(parent["node_id"]))
    if parent.get("parent_node_id"):
        parent["parent_node_id"] = uuid.UUID(str(parent["parent_node_id"]))
    parent["version_id"] = uuid.UUID(str(parent["version_id"]))
    return parent
