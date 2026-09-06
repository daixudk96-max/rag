"""Document the Phase 5 heading_path storage contract."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

OUTPUT_FILE = Path(__file__).parent / "heading_path_contract.json"


def build_heading_path_contract() -> dict[str, Any]:
    """Return the authoritative heading_path metric contract."""
    return {
        "authoritative_source": "canonical_spans.heading_path",
        "derived_sources": ["tree_nodes.heading_path", "vector_chunks.heading_path"],
        "metric_rule": "heading_path_rate = canonical_spans with non-null heading_path / canonical_spans for active_version_id",
        "minimum_threshold": 0.95,
    }


def main() -> int:
    contract = build_heading_path_contract()
    OUTPUT_FILE.write_text(json.dumps(contract, indent=2), encoding="utf-8")
    print(json.dumps(contract, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
