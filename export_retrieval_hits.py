"""Export retrieval hits to JSON and generate visualization."""
import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock

from llamaindex_runtime.tree.pageindex_adapter import PageIndexTreeAdapter

# Load real nodes
nodes_json = Path("verification/real_validation_nodes.json")
nodes_data = json.loads(nodes_json.read_text())

# Convert UUID strings to UUID objects
nodes = []
for node_dict in nodes_data:
    node = node_dict.copy()
    node["node_id"] = uuid.UUID(node["node_id"])
    node["version_id"] = uuid.UUID(node["version_id"])
    if node["parent_node_id"]:
        node["parent_node_id"] = uuid.UUID(node["parent_node_id"])
    nodes.append(node)

version_id = nodes[0]["version_id"]

# Create shared span_ids
span_ids = [uuid.uuid4() for _ in nodes]
chunk_ids = [uuid.uuid4() for _ in nodes]

# Mock registry with matching spans
registry = MagicMock()
registry.query_tree_nodes_by_version = lambda vid: nodes
registry.query_tree_node_spans_by_version = lambda vid: [
    {"node_id": node["node_id"], "span_id": span_ids[i], "ordinal_no": 0}
    for i, node in enumerate(nodes)
]
registry.query_vector_chunk_spans_by_version = lambda vid: [
    {"chunk_id": chunk_ids[i], "span_id": span_ids[i]}
    for i in range(len(nodes))
]

# Execute retrieval
adapter = PageIndexTreeAdapter()
hits = adapter.retrieve_tree_hits(
    query_text="爱复盘竞品分析",
    version_id=version_id,
    registry=registry,
    limit=14,  # All hits
)

print(f"[OK] Retrieved {len(hits)} hits")

# Export hits to JSON
hits_export = []
for hit in hits:
    hit_dict = {
        "heading_path": hit.heading_path,
        "node_id": str(hit.node_id),
        "page_no": hit.page_no,
        "text_preview": hit.text_preview,
        "span_ids": [str(s) for s in hit.span_ids],
        "chunk_id": str(hit.chunk_id),
    }
    hits_export.append(hit_dict)

hits_json_path = Path("verification/retrieval_hits.json")
hits_json_path.write_text(json.dumps(hits_export, indent=2, ensure_ascii=False))
print(f"[OK] Exported hits: {hits_json_path}")

# Generate HTML visualization
html_content = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Tree Retrieval Hits</title>
  <style>
    :root {
      --bg: #0b1020;
      --panel: #121935;
      --text: #edf2ff;
      --muted: #a9b5d6;
      --line: #30406f;
      --accent: #79c0ff;
      --accent-2: #7ee787;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", "PingFang SC", sans-serif;
      background: linear-gradient(180deg, var(--bg), #0a0f1a 60%);
      color: var(--text);
      padding: 32px 24px;
    }
    h1 { font-size: 28px; margin-bottom: 24px; }
    .hit-card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 20px;
      margin: 16px 0;
    }
    .hit-header {
      font-size: 18px;
      color: var(--accent);
      font-weight: 600;
      margin-bottom: 12px;
    }
    .hit-fields {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
      gap: 10px;
    }
    .field {
      background: rgba(0,0,0,0.2);
      padding: 8px 12px;
      border-radius: 6px;
    }
    .field-label {
      color: var(--muted);
      font-size: 12px;
    }
    .field-value {
      color: var(--text);
      font-size: 13px;
      word-break: break-all;
    }
  </style>
</head>
<body>
  <h1>Tree Retrieval Hits (14 results)</h1>
"""

for i, hit in enumerate(hits_export, 1):
    html_content += f"""
  <div class="hit-card">
    <div class="hit-header">Hit #{i}: {hit['heading_path']}</div>
    <div class="hit-fields">
      <div class="field">
        <div class="field-label">node_id</div>
        <div class="field-value">{hit['node_id']}</div>
      </div>
      <div class="field">
        <div class="field-label">page_no</div>
        <div class="field-value">{hit['page_no']}</div>
      </div>
      <div class="field">
        <div class="field-label">text_preview</div>
        <div class="field-value">{hit['text_preview']}</div>
      </div>
      <div class="field">
        <div class="field-label">span_ids</div>
        <div class="field-value">{hit['span_ids'][0]} (1 span)</div>
      </div>
      <div class="field">
        <div class="field-label">chunk_id</div>
        <div class="field-value">{hit['chunk_id']}</div>
      </div>
    </div>
  </div>
"""

html_content += """
  <div style="color: var(--muted); margin-top: 24px; font-size: 14px;">
    Total hits: 14 | Query: "爱复盘竞品分析" | Model: gpt-5.4-mini
  </div>
</body>
</html>
"""

html_path = Path("verification/retrieval_hits_visual.html")
html_path.write_text(html_content)
print(f"[OK] Generated HTML: {html_path}")