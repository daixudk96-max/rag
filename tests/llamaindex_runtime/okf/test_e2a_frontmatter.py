from __future__ import annotations

import pytest

from llamaindex_runtime.okf import e2a_frontmatter
from llamaindex_runtime.okf.e2a_frontmatter import load_strict_e2a_frontmatter


@pytest.mark.parametrize(
    "yaml_block",
    (
        "defaults: &safe\n  type: entity\nitem: *safe",
        "base: &safe\n  title: cat\nitem:\n  <<: *safe",
        "title: cat\ntitle: dog",
        "outer:\n  nested:\n    title: cat\n    title: dog",
    ),
)
def test_e2a_frontmatter_rejects_alias_merge_and_duplicate_keys_at_every_depth(
    yaml_block: str,
) -> None:
    with pytest.raises(ValueError, match="^e2a_frontmatter_invalid$"):
        load_strict_e2a_frontmatter(f"---\n{yaml_block}\n---\nbody")


def test_e2a_frontmatter_has_local_depth_and_node_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("llamaindex_runtime.okf.e2a_frontmatter.MAX_E2A_YAML_DEPTH", 2)
    monkeypatch.setattr("llamaindex_runtime.okf.e2a_frontmatter.MAX_E2A_YAML_NODES", 4)

    with pytest.raises(ValueError, match="^e2a_frontmatter_resource_limit$"):
        load_strict_e2a_frontmatter("---\na:\n  b:\n    c: value\n---\nbody")
    with pytest.raises(ValueError, match="^e2a_frontmatter_resource_limit$"):
        load_strict_e2a_frontmatter("---\na: one\nb: two\nc: three\n---\nbody")


def test_e2a_frontmatter_rejects_non_unicode_scalar_input_with_redacted_error() -> None:
    with pytest.raises(ValueError, match="^e2a_frontmatter_invalid$") as error:
        load_strict_e2a_frontmatter("---\ntitle: \ud800\n---\nbody")

    assert "title" not in str(error.value)


@pytest.mark.parametrize(
    "document",
    (
        b"--- \t\ntitle: cat\n---\t \nvalid body\xff",
        b"--- \t\r\ntitle: cat\r\n---\t \r\nvalid body\xff",
    ),
)
def test_byte_validator_accepts_lf_and_crlf_without_decoding_invalid_utf8_body(
    document: bytes,
) -> None:
    e2a_frontmatter.validate_strict_e2a_raw_frontmatter_bytes(document)


@pytest.mark.parametrize(
    "yaml_block",
    (
        b"title: cat\ntitle: dog",
        b"defaults: &safe\n  type: entity\nitem: *safe",
        b"base: &safe\n  title: cat\nitem:\n  <<: *safe",
        b"- cat",
        b'title: "\\uD800"',
    ),
)
def test_byte_validator_preserves_strict_yaml_rejections(yaml_block: bytes) -> None:
    with pytest.raises(ValueError, match="^e2a_frontmatter_invalid$"):
        e2a_frontmatter.validate_strict_e2a_raw_frontmatter_bytes(
            b"---\n" + yaml_block + b"\n---\nbody"
        )


@pytest.mark.parametrize(
    "document",
    (
        b"not-frontmatter\n---\ntitle: cat\n---\n",
        b"---\x0b\ntitle: cat\n---\n",
        b"---\ntitle: cat\nbody",
    ),
)
def test_byte_validator_rejects_nonzero_or_unclosed_delimiters(document: bytes) -> None:
    with pytest.raises(ValueError, match="^e2a_frontmatter_invalid$"):
        e2a_frontmatter.validate_strict_e2a_raw_frontmatter_bytes(document)


def test_byte_validator_rejects_frontmatter_over_its_bounded_byte_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(e2a_frontmatter, "MAX_E2A_FRONTMATTER_BYTES", 5)

    with pytest.raises(ValueError, match="^e2a_frontmatter_invalid$"):
        e2a_frontmatter.validate_strict_e2a_raw_frontmatter_bytes(
            b"---\ntitle: cat\n---\nbody"
        )


@pytest.mark.parametrize("line_ending", (b"\n", b"\r\n"), ids=("lf", "crlf"))
@pytest.mark.parametrize("whitespace", (b"", b" \t" * 32), ids=("none", "exactly_64"))
def test_byte_validator_accepts_exact_payload_cap_and_delimiter_hws(
    monkeypatch: pytest.MonkeyPatch, line_ending: bytes, whitespace: bytes
) -> None:
    monkeypatch.setattr(e2a_frontmatter, "MAX_E2A_FRONTMATTER_BYTES", 4)
    document = (
        b"---"
        + whitespace
        + line_ending
        + b"a: b"
        + line_ending
        + b"---"
        + whitespace
        + line_ending
        + b"invalid body \xff"
    )

    e2a_frontmatter.validate_strict_e2a_raw_frontmatter_bytes(document)


@pytest.mark.parametrize("line_ending", (b"\n", b"\r\n"), ids=("lf", "crlf"))
@pytest.mark.parametrize("at_opening", (True, False), ids=("opening", "closing"))
def test_byte_validator_rejects_delimiter_hws_above_local_cap(
    line_ending: bytes, at_opening: bool
) -> None:
    valid_delimiter = b"---" + line_ending
    oversized_delimiter = b"---" + (b" " * 65) + line_ending
    opening = oversized_delimiter if at_opening else valid_delimiter
    closing = valid_delimiter if at_opening else oversized_delimiter

    with pytest.raises(ValueError, match="^e2a_frontmatter_invalid$"):
        e2a_frontmatter.validate_strict_e2a_raw_frontmatter_bytes(
            opening + b"a: b" + line_ending + closing
        )


@pytest.mark.parametrize(
    "document",
    (
        b"---\rtitle: cat\n---\n",
        b"---\v\ntitle: cat\n---\n",
        b"---\f\ntitle: cat\n---\n",
        b"----\ntitle: cat\n---\n",
        b"--- text\ntitle: cat\n---\n",
        b"---\na: b\n---\rbody",
        b"---\na: b\n---\v\n",
        b"---\na: b\n----\n",
        b"---\na: b\n--- text\n",
    ),
    ids=(
        "opening_bare_cr",
        "opening_vertical_tab",
        "opening_form_feed",
        "opening_extra_hyphen",
        "opening_text",
        "closing_bare_cr",
        "closing_vertical_tab",
        "closing_extra_hyphen",
        "closing_text",
    ),
)
def test_byte_validator_rejects_non_grammar_delimiters(document: bytes) -> None:
    with pytest.raises(ValueError, match="^e2a_frontmatter_invalid$"):
        e2a_frontmatter.validate_strict_e2a_raw_frontmatter_bytes(document)
