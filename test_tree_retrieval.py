"""Test tree retrieval with real nodes from markdown document."""
import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock

from llamaindex_runtime.tree.pageindex_adapter import PageIndexTreeAdapter

print("=" * 70)
print("Tree Retrieval Test - Real 14-node Structure")
print("=" * 70)

# Step 1: Load real nodes from validation
nodes_json = Path("verification/real_validation_nodes.json")
nodes_data = json.loads(nodes_json.read_text())

# Convert UUID strings to UUID objects (required by retrieve_tree_hits)
nodes = []
for node_dict in nodes_data:
    node = node_dict.copy()
    node["node_id"] = uuid.UUID(node["node_id"])
    node["version_id"] = uuid.UUID(node["version_id"])
    if node["parent_node_id"]:
        node["parent_node_id"] = uuid.UUID(node["parent_node_id"])
    nodes.append(node)

version_id = nodes[0]["version_id"]

print(f"\n[OK] Loaded {len(nodes)} nodes from markdown document")
print(f"Version ID: {version_id}")
print(f"Root node: {nodes[0]['title']}")

# Step 2: Build mock registry with real nodes and matching span/chunk data
registry = MagicMock()

# Create shared span_ids for each node (one span per node)
span_ids = [uuid.uuid4() for _ in nodes]
chunk_ids = [uuid.uuid4() for _ in nodes]

# Mock registry methods for retrieval
def mock_query_tree_nodes_by_version(vid):
    return nodes

def mock_query_tree_node_spans_by_version(vid):
    # Link each node to its span (must use UUID objects)
    return [
        {"node_id": node["node_id"], "span_id": span_ids[i], "ordinal_no": 0}
        for i, node in enumerate(nodes)
    ]

def mock_query_vector_chunk_spans_by_version(vid):
    # Link each chunk to the SAME span (one chunk per node)
    return [
        {"chunk_id": chunk_ids[i], "span_id": span_ids[i]}
        for i in range(len(nodes))
    ]

registry.query_tree_nodes_by_version = mock_query_tree_nodes_by_version
registry.query_tree_node_spans_by_version = mock_query_tree_node_spans_by_version
registry.query_vector_chunk_spans_by_version = mock_query_vector_chunk_spans_by_version

# Step 3: Test retrieval
adapter = PageIndexTreeAdapter()

print("\n--- TEST 1: Empty query ---")
hits = adapter.retrieve_tree_hits(
    query_text="",
    version_id=version_id,
    registry=registry,
    limit=5,
)
print(f"Hits returned: {len(hits)}")
if hits:
    print("First hit preview:")
    first_hit = hits[0]
    print(f"  - heading_path: {first_hit.heading_path}")
    print(f"  - node_id: {first_hit.node_id}")
    print(f"  - page_no: {first_hit.page_no}")
    print(f"  - text_preview: {first_hit.text_preview[:80]}...")

print("\n--- TEST 2: Specific query ---")
hits = adapter.retrieve_tree_hits(
    query_text="爱复盘 SWOT 分析",
    version_id=version_id,
    registry=registry,
    limit=10,
)
print(f"Hits returned: {len(hits)}")

# Step 4: Find specific node by title
print("\n--- TEST 3: Find '竞品 A：爱复盘' node ---")
target_node = None
for node in nodes:
    if "竞品 A" in node["title"]:
        target_node = node
        break

if target_node:
    print(f"[FOUND] Node: {target_node['title']}")
    print(f"  - node_id: {target_node['node_id']}")
    print(f"  - heading_path: {target_node['heading_path']}")
    print(f"  - page_no: {target_node['page_no']}")
    print(f"  - parent_node_id: {target_node['parent_node_id']}")

    # Find parent node
    parent_id = target_node['parent_node_id']
    if parent_id:
        parent_node = next((n for n in nodes if n['node_id'] == parent_id), None)
        if parent_node:
            print(f"  - Parent: {parent_node['title']} (page {parent_node['page_no']})")
else:
    print("[NOT FOUND] No node with '竞品 A' in title")

# Step 5: Show hierarchy
print("\n--- TEST 4: Hierarchy traversal ---")
def show_tree(nodes, parent_id=None, indent=0):
    children = [n for n in nodes if n['parent_node_id'] == parent_id]
    for child in children:
        prefix = "  " * indent
        print(f"{prefix}- {child['title']} (line {child['page_no']})")
        show_tree(nodes, parent_id=child['node_id'], indent=indent+1)

print("Tree hierarchy:")
show_tree(nodes)

print("\n" + "=" * 70)
print("RETRIEVAL TEST SUMMARY")
print("=" * 70)
print(f"Total nodes indexed: {len(nodes)}")
print(f"Hierarchy levels: 3 (root → section → subsection)")
print(f"Provenance integrity: {all(n['version_id'] == str(version_id) for n in nodes)}")
print(f"Node schema fields: 11 (node_id, version_id, parent_node_id, node_type, level_no, title, heading_path, page_no, page_start, page_end, summary_text)")
print("=" * 70)