from __future__ import annotations

from dataclasses import FrozenInstanceError
from uuid import uuid4

import pytest

from llamaindex_runtime.interfaces import CanonicalSpan


def test_canonical_span_preserves_pre_normalized_text_and_headings() -> None:
    span = CanonicalSpan(
        doc_id=uuid4(),
        version_id=uuid4(),
        span_id=uuid4(),
        text="  hello   world  ",
        page_no=3,
        headings=(" Intro ", " ", "Details  "),
        offset=12,
    )

    assert span.text == "  hello   world  "
    assert span.headings == (" Intro ", " ", "Details  ")
    assert span.heading_path == " Intro  >   > Details  "


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("doc_id", None),
        ("version_id", None),
        ("span_id", None),
        ("doc_id", "not-a-uuid"),
        ("version_id", "not-a-uuid"),
        ("span_id", "not-a-uuid"),
    ],
)
def test_canonical_span_rejects_invalid_coordinates(field_name: str, field_value: object) -> None:
    kwargs = {
        "doc_id": uuid4(),
        "version_id": uuid4(),
        "span_id": uuid4(),
        "text": "span",
    }
    kwargs[field_name] = field_value

    with pytest.raises(ValueError):
        CanonicalSpan(**kwargs)  # type: ignore[arg-type]


def test_canonical_span_is_immutable() -> None:
    span = CanonicalSpan(
        doc_id=uuid4(),
        version_id=uuid4(),
        span_id=uuid4(),
        text="span",
    )

    with pytest.raises((AttributeError, FrozenInstanceError)):
        span.text = "mutated"  # type: ignore[misc]


def test_canonical_span_rejects_negative_page_number() -> None:
    with pytest.raises(ValueError):
        CanonicalSpan(
            doc_id=uuid4(),
            version_id=uuid4(),
            span_id=uuid4(),
            text="span",
            page_no=-1,
        )


def test_coordinate_is_exposed_without_overriding_full_value_equality() -> None:
    doc_id = uuid4()
    version_id = uuid4()
    span_id = uuid4()

    first = CanonicalSpan(
        doc_id=doc_id,
        version_id=version_id,
        span_id=span_id,
        text="first",
        page_no=1,
        headings=("A",),
        offset=1,
    )
    second = CanonicalSpan(
        doc_id=doc_id,
        version_id=version_id,
        span_id=span_id,
        text="second",
        page_no=2,
        headings=("B",),
        offset=9,
    )

    assert first.coordinate == second.coordinate
    assert first != second
    assert hash(first) != hash(second)
