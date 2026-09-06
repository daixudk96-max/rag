"""Phase 16-14 relation-scope regression for _inventory_020 ownership UNIQUE.

PostgreSQL constraint names are not schema-wide unique: a same-named UNIQUE
constraint on an unrelated (imposter) relation can satisfy the ownership
inventory unless both pg_constraint probes pin the exact target relation. This
narrow static regression pins the target-relation conrelid predicate exactly
twice -- once for the existence probe and once for the ordered-column lookup --
and requires both to remain constrained to contype = 'u' with the live
UNNEST/ORDINALITY ordering. No database, Docker, network, or credentials are
touched.
"""

from __future__ import annotations

import importlib.util
import inspect
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
VERIFICATION_DIR = REPO_ROOT / "verification" / "phase16-raw-corpus-entity-layer"
RUNNER_PATH = VERIFICATION_DIR / "run_e2b_migration_gate.py"

TARGET_RELATION = "okf_e2b_node_link_ownership"
RELATION_PREDICATE = f"AND constraint_row.conrelid = '{TARGET_RELATION}'::regclass"
PROBE_SITES = 2  # existence probe + ordered-column probe


def _runner() -> types.ModuleType:
    """Lazily load the runner; fail cleanly when the runner file is absent."""
    if not RUNNER_PATH.is_file():
        pytest.fail(f"RED: runner module absent: {RUNNER_PATH}")
    spec = importlib.util.spec_from_file_location(
        "run_e2b_migration_gate", str(RUNNER_PATH)
    )
    if spec is None or spec.loader is None:
        pytest.fail(f"RED: runner module unloadable: {RUNNER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _inventory_020_source() -> str:
    return inspect.getsource(_runner()._inventory_020)


def _ownership_probe_blocks() -> list[str]:
    source = _inventory_020_source()
    return [
        block
        for block in source.split("cursor.execute(")
        if RELATION_PREDICATE in block
    ]


def test_inventory_020_pins_target_relation_in_both_ownership_probes() -> None:
    source = _inventory_020_source()
    assert source.count(RELATION_PREDICATE) == PROBE_SITES
    blocks = _ownership_probe_blocks()
    assert len(blocks) == PROBE_SITES
    # Exactly one probe is the existence probe; the other is the ordered-column
    # lookup.
    ordered = [block for block in blocks if "UNNEST(constraint_row.conkey)" in block]
    existence = [
        block for block in blocks if "UNNEST(constraint_row.conkey)" not in block
    ]
    assert len(ordered) == 1
    assert len(existence) == 1
    assert "SELECT constraint_row.conname" in existence[0]
    assert "SELECT attribute_row.attname" in ordered[0]


def test_inventory_020_ownership_probes_remain_uniqueness_scoped() -> None:
    blocks = _ownership_probe_blocks()
    assert len(blocks) == PROBE_SITES
    for block in blocks:
        assert "constraint_row.conname = %s" in block
        assert "contype = 'u'" in block
        assert "constraint_row.connamespace = (" in block
    source = _inventory_020_source()
    assert source.count("contype = 'u'") == PROBE_SITES
    assert source.count("UNNEST(constraint_row.conkey)") == 1
    assert source.count("WITH ORDINALITY") == 1
    assert "ORDER BY key_columns.ordinality" in source
