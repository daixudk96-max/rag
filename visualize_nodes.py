"""Generate HTML visualization for real validation nodes."""
import json
from pathlib import Path

nodes_json = Path("verification/real_validation_nodes.json")
nodes = json.loads(nodes_json.read_text())

html_template = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Real Validation Tree Nodes</title>
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
      line-height: 1.45;
      padding: 32px 24px;
    }
    h1 { font-size: 28px; margin-bottom: 24px; }
    .node-card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 20px;
      margin: 16px 0;
    }
    .node-header {
      display: flex;
      align-items: baseline;
      gap: 12px;
      margin-bottom: 16px;
    }
    .node-title {
      font-size: 20px;
      color: var(--accent);
      font-weight: 600;
    }
    .node-type {
      background: var(--accent-2);
      color: var(--bg);
      padding: 2px 10px;
      border-radius: 4px;
      font-size: 13px;
    }
    .node-fields {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 12px;
    }
    .field {
      background: var(--panel-2);
      padding: 10px 14px;
      border-radius: 6px;
    }
    .field-label {
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 4px;
    }
    .field-value {
      color: var(--text);
      font-size: 14px;
      word-break: break-all;
    }
    .metadata {
      color: var(--muted);
      font-size: 14px;
      margin-top: 24px;
    }
  </style>
</head>
<body>
  <h1>Real Validation Tree Nodes</h1>
"""

for node in nodes:
    html_template += f"""
  <div class="node-card">
    <div class="node-header">
      <span class="node-title">{node['title']}</span>
      <span class="node-type">{node['node_type']}</span>
    </div>
    <div class="node-fields">
      <div class="field">
        <div class="field-label">node_id</div>
        <div class="field-value">{node['node_id']}</div>
      </div>
      <div class="field">
        <div class="field-label">version_id</div>
        <div class="field-value">{node['version_id']}</div>
      </div>
      <div class="field">
        <div class="field-label">parent_node_id</div>
        <div class="field-value">{node['parent_node_id'] or 'null (root)'}</div>
      </div>
      <div class="field">
        <div class="field-label">heading_path</div>
        <div class="field-value">{node['heading_path']}</div>
      </div>
      <div class="field">
        <div class="field-label">page_no</div>
        <div class="field-value">{node['page_no']}</div>
      </div>
      <div class="field">
        <div class="field-label">page_range</div>
        <div class="field-value">{node['page_start']} - {node['page_end']}</div>
      </div>
      <div class="field">
        <div class="field-label">level_no</div>
        <div class="field-value">{node['level_no'] or 'null'}</div>
      </div>
      <div class="field">
        <div class="field-label">summary_text</div>
        <div class="field-value">{node['summary_text']}</div>
      </div>
    </div>
  </div>
"""

html_template += f"""
  <div class="metadata">
    Total nodes: {len(nodes)} | Source: verification/real_validation_nodes.json | Model: gpt-5.4-mini
  </div>
</body>
</html>
"""

output_path = Path("verification/real_validation_tree_visual.html")
output_path.write_text(html_template)
print(f"[OK] Visualization HTML generated: {output_path}")
print(f"  Open in browser: {output_path.absolute()}")