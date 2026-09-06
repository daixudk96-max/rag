"""Phase 16-06 contract tests for the frozen versioned RaNER label map.

Pins ``llamaindex_runtime/entity/label_map.py``:
- ``RAINER_LABEL_MAP_VERSION`` (a non-empty, stable version string),
- ``RAINER_RAW_TO_CANONICAL`` (an immutable mapping with exactly the six
  frozen raw labels PER/LOC/CORP/GRP/CW/PROD),
- ``LabelMapError`` (a ``ValueError`` subclass) carrying the label-map version
  on unknown labels,
- ``resolve_label(raw_label) -> str`` mapping each raw label to its canonical
  type, where CORP/GRP both normalize to Organization while remaining distinct
  raw labels, and any unknown/invalid input raises a versioned
  ``LabelMapError``,
- the zero heavy-import boundary (no modelscope/torch/transformers/tokenizers/
  sentencepiece/jieba) and no substring coordinate recovery.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path

import pytest

from llamaindex_runtime.entity.label_map import (
    RAINER_LABEL_MAP_VERSION,
    RAINER_RAW_TO_CANONICAL,
    LabelMapError,
    resolve_label,
)
import llamaindex_runtime.entity.label_map as label_map_module


def test_label_map_version_is_non_empty_string() -> None:
    assert isinstance(RAINER_LABEL_MAP_VERSION, str)
    assert RAINER_LABEL_MAP_VERSION


def test_raw_to_canonical_has_exactly_six_frozen_entries() -> None:
    assert set(RAINER_RAW_TO_CANONICAL) == {"PER", "LOC", "CORP", "GRP", "CW", "PROD"}


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("PER", "Person"),
        ("LOC", "Location"),
        ("CORP", "Organization"),
        ("GRP", "Organization"),
        ("CW", "CreativeWork"),
        ("PROD", "Product"),
    ],
)
def test_resolve_label_maps_each_raw_label(raw: str, canonical: str) -> None:
    assert RAINER_RAW_TO_CANONICAL[raw] == canonical
    assert resolve_label(raw) == canonical


def test_corp_and_grp_normalize_but_remain_distinct_raw_labels() -> None:
    # Both fine-grained labels share the canonical Organization, but the raw
    # labels stay distinct keys so CORP vs GRP provenance is never collapsed.
    assert RAINER_RAW_TO_CANONICAL["CORP"] == "Organization"
    assert RAINER_RAW_TO_CANONICAL["GRP"] == "Organization"
    assert "CORP" in RAINER_RAW_TO_CANONICAL
    assert "GRP" in RAINER_RAW_TO_CANONICAL
    assert resolve_label("CORP") == resolve_label("GRP") == "Organization"


def test_mapping_is_immutable() -> None:
    assert isinstance(RAINER_RAW_TO_CANONICAL, Mapping)
    with pytest.raises(TypeError):
        RAINER_RAW_TO_CANONICAL["PER"] = "Other"  # type: ignore[index]
    with pytest.raises(TypeError):
        del RAINER_RAW_TO_CANONICAL["PER"]  # type: ignore[misc]


@pytest.mark.parametrize(
    "raw",
    [
        "ORG",
        "UNKNOWN",
        "person",  # case-sensitive
        "PER ",  # whitespace is not normalized
        "",
        None,
        3,
    ],
)
def test_unknown_or_invalid_raw_label_raises_versioned_error(raw: object) -> None:
    with pytest.raises(LabelMapError) as exc:
        resolve_label(raw)  # type: ignore[arg-type]
    assert RAINER_LABEL_MAP_VERSION in str(exc.value)


def test_label_map_error_is_a_value_error_subclass() -> None:
    assert issubclass(LabelMapError, ValueError)
    error = LabelMapError(f"unknown raw label FOO; label map {RAINER_LABEL_MAP_VERSION}")
    assert isinstance(error, ValueError)
    assert RAINER_LABEL_MAP_VERSION in str(error)


def test_label_map_source_imports_no_heavy_dependencies() -> None:
    source = Path(label_map_module.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "import modelscope",
        "from modelscope",
        "import torch",
        "from torch",
        "import transformers",
        "from transformers",
        "import tokenizers",
        "from tokenizers",
        "import sentencepiece",
        "from sentencepiece",
        "import jieba",
        "from jieba",
    ):
        assert forbidden not in source, f"forbidden import: {forbidden}"


def test_label_map_source_never_uses_substring_coordinate_recovery() -> None:
    source = Path(label_map_module.__file__).read_text(encoding="utf-8")
    for forbidden in ("str.find", ".find(", "str.index", ".index("):
        assert forbidden not in source, f"forbidden substring: {forbidden}"


def test_importing_label_map_imports_no_heavy_dependencies() -> None:
    import llamaindex_runtime.entity.label_map  # noqa: F401

    for name in ("modelscope", "torch", "jieba", "sentencepiece"):
        assert name not in sys.modules, (
            f"llamaindex_runtime.entity.label_map must not import {name}"
        )
