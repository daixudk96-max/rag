"""Phase-15 Wave-1 eighth-remediation application regression coverage."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from llamaindex_runtime.okf import e2a_admission
from llamaindex_runtime.okf.rooted_open import BundleAuthority


def _write_relation(
    path: Path,
    *,
    subject_entity_id: str,
    object_entity_id: str,
    qualifiers: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        "type: relation\n"
        f"subject_entity_id: {subject_entity_id}\n"
        "predicate: protects\n"
        f"object_entity_id: {object_entity_id}\n"
        "timestamp: '2026-07-19T00:00:00Z'\n"
        f"{qualifiers}"
        "---\n"
        "relation body\n",
        encoding="utf-8",
    )


def _admit_duplicate_relations(tmp_path: Path, *, first: str, second: str) -> object:
    subject_entity_id, object_entity_id = str(uuid4()), str(uuid4())
    _write_relation(
        tmp_path / "relations" / "first.md",
        subject_entity_id=subject_entity_id,
        object_entity_id=object_entity_id,
        qualifiers=first,
    )
    _write_relation(
        tmp_path / "relations" / "second.md",
        subject_entity_id=subject_entity_id,
        object_entity_id=object_entity_id,
        qualifiers=second,
    )
    with BundleAuthority(tmp_path) as authority:
        return e2a_admission.admit_e2a_corpus(authority)


def _assert_one_fact_with_two_sources(state: object) -> None:
    assert len(state.manual_relations) == 1  # type: ignore[union-attr]
    assert {owner.relative_path for owner in state.ownership_facts} == {  # type: ignore[union-attr]
        "relations/first.md",
        "relations/second.md",
    }
    assert {
        str(artifact["path"])
        for artifact in state.corpus_manifest["artifacts"]  # type: ignore[union-attr,index]
        if artifact["kind"] == "relation"  # type: ignore[index]
    } == {"relations/first.md", "relations/second.md"}


def test_admission_coalesces_nested_numeric_jsonb_qualifiers(tmp_path: Path) -> None:
    state = _admit_duplicate_relations(
        tmp_path,
        first=("qualifiers:\n  nested:\n    quantity: 1\n    offset: -0.0\n"),
        second=("qualifiers:\n  nested:\n    quantity: 1.0\n    offset: 0.0\n"),
    )

    _assert_one_fact_with_two_sources(state)


def test_admission_coalesces_order_independent_jsonb_mappings(tmp_path: Path) -> None:
    state = _admit_duplicate_relations(
        tmp_path,
        first=(
            "qualifiers:\n"
            "  timeline:\n"
            "    start: today\n"
            "    end: tomorrow\n"
            "  reviewed: true\n"
        ),
        second=(
            "qualifiers:\n"
            "  reviewed: true\n"
            "  timeline:\n"
            "    end: tomorrow\n"
            "    start: today\n"
        ),
    )

    _assert_one_fact_with_two_sources(state)


@pytest.mark.parametrize(
    ("first_value", "second_value"),
    (("true", "1"), ("false", "0")),
    ids=("true_vs_one", "false_vs_zero"),
)
def test_admission_rejects_boolean_numeric_jsonb_qualifier_collisions(
    tmp_path: Path, first_value: str, second_value: str
) -> None:
    with pytest.raises(ValueError, match="^e2a_admission_natural_key_collision$"):
        _admit_duplicate_relations(
            tmp_path,
            first=f"qualifiers:\n  nested:\n    value: {first_value}\n",
            second=f"qualifiers:\n  nested:\n    value: {second_value}\n",
        )


def test_admission_rejects_order_distinct_jsonb_arrays(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="^e2a_admission_natural_key_collision$"):
        _admit_duplicate_relations(
            tmp_path,
            first="qualifiers:\n  members:\n    - cat\n    - dog\n",
            second="qualifiers:\n  members:\n    - dog\n    - cat\n",
        )


@pytest.mark.parametrize(
    ("left", "right"),
    (
        ({"value": float("nan")}, {"value": float("nan")}),
        ({"value": float("inf")}, {"value": float("inf")}),
        ({"value": object()}, {"value": object()}),
    ),
    ids=("nan", "infinity", "unexpected_object"),
)
def test_relation_jsonb_qualifier_comparator_fails_closed_for_invalid_values(
    left: dict[str, object], right: dict[str, object]
) -> None:
    assert not e2a_admission._jsonb_qualifiers_equal(left, right)
