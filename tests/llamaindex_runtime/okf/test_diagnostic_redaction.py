"""Canaries proving document-derived diagnostics never disclose source text."""

from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from llamaindex_runtime.okf.diagnostics import (
    diagnostic_safe_path,
    diagnostic_safe_text,
    diagnostic_safe_uuid,
)
from llamaindex_runtime.okf.parser import OKFParser, _parse_timestamp
from llamaindex_runtime.okf.serializer import serialize_document


def _clean_environment() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "DATABASE_URL",
            "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE",
            "OKF_REBUILD_EXPECTED_DATABASE",
        }
    }


def _summary(value: str) -> str:
    encoded = value.encode("utf-8", "surrogatepass")
    return f"len={len(encoded)} sha256={hashlib.sha256(encoded).hexdigest()}"


class _StringificationCanary:
    def __str__(self) -> str:
        raise AssertionError("diagnostics must not stringify arbitrary objects")

    def __repr__(self) -> str:
        raise AssertionError("diagnostics must not render arbitrary objects")


@pytest.mark.parametrize(
    "value",
    (
        "short-printable-secret",
        "control\x00span-id",
        "high-surrogate-\ud800",
        "low-surrogate-\udcff",
    ),
    ids=("printable", "control", "high-surrogate", "low-surrogate"),
)
def test_diagnostic_safe_uuid_summarizes_invalid_strings_with_surrogatepass(
    value: str,
) -> None:
    """Invalid UUID text is opaque and deterministic for all UTF-8 edge cases."""
    expected = _summary(value)

    assert diagnostic_safe_uuid(value) == expected
    assert diagnostic_safe_uuid(value) == expected
    assert value not in expected


def test_diagnostic_safe_uuid_normalizes_canonical_uuid_without_summary() -> None:
    """A valid UUID remains directly actionable in diagnostics."""
    assert diagnostic_safe_uuid("B2191A11-CD8B-4C6E-B34A-7B5552E3C03C") == (
        "b2191a11-cd8b-4c6e-b34a-7b5552e3c03c"
    )


@pytest.mark.parametrize("value", ({"span_id": "secret"}, _StringificationCanary()))
def test_diagnostic_safe_uuid_never_stringifies_non_string_values(
    value: object,
) -> None:
    """Arbitrary mappings and objects have one fixed non-string category."""
    assert diagnostic_safe_uuid(value) == "invalid-type=non-string"


@pytest.mark.parametrize(
    "value",
    (
        "short-printable-secret",
        "C:\\Users\\alice\\private\\source.md",
        "/srv/private/source.md",
        "title\x1b[31m-control",
        "OPENAI_API_KEY=sk-canary-secret",
    ),
)
def test_diagnostic_text_and_path_always_use_deterministic_summaries(
    value: str,
) -> None:
    assert diagnostic_safe_text(value) == _summary(value)
    assert diagnostic_safe_path(value) == _summary(value)
    assert value not in diagnostic_safe_text(value)
    for component in ("alice", "private", "source.md", "sk-canary-secret"):
        assert component not in diagnostic_safe_path(value)


@pytest.mark.parametrize(
    "value",
    ("high-surrogate-\ud800", "low-surrogate-\udcff"),
    ids=("high-surrogate", "low-surrogate"),
)
def test_diagnostic_text_and_path_hash_surrogates_with_surrogatepass(
    value: str,
) -> None:
    """Text and path summaries use stable bytes for lone surrogate code points."""
    expected = _summary(value)

    assert diagnostic_safe_text(value) == expected
    assert diagnostic_safe_path(value) == expected


def test_invalid_timestamp_warning_hashes_short_document_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    timestamp = "OPENAI_API_KEY=sk-timestamp-canary"

    with caplog.at_level(logging.WARNING):
        assert _parse_timestamp(timestamp) is None

    assert caplog.messages == [
        f"Invalid timestamp format: field=timestamp {_summary(timestamp)}"
    ]
    assert timestamp not in caplog.text


def test_serializer_logs_only_safe_identifiers_and_fixed_counts(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    title = "heading-secret\x1b[31m"
    path_component = "bundle-private"
    bundle_root = tmp_path / path_component
    bundle_root.mkdir()
    node = {"text": "body-secret", "metadata": {"headings": [title]}}

    with caplog.at_level(logging.INFO):
        result = serialize_document(
            [node],
            doc_id=str(uuid4()),
            version_id=str(uuid4()),
            source_checksum="a" * 64,
            docling_version="2.109.0",
            bundle_root=bundle_root,
            name="safe-slug",
        )

    assert result.span_count == 1
    assert len(caplog.messages) == 1
    message = caplog.messages[0]
    assert message.startswith(
        "OKF serialization complete: span_count=1 dropped_node_count=0"
    )
    for secret in (title, "body-secret", path_component, "safe-slug"):
        assert secret not in message


def test_serializer_validation_errors_are_fixed_and_do_not_reflect_inputs(
    tmp_path: Path,
) -> None:
    secret_uuid = "OPENAI_API_KEY=sk-uuid-canary"
    secret_slug = "../OPENAI_API_KEY=sk-slug-canary"

    with pytest.raises(ValueError, match="^doc_id must be a UUID$") as uuid_error:
        serialize_document(
            [{"text": "body"}],
            doc_id=secret_uuid,
            version_id=str(uuid4()),
            source_checksum="a" * 64,
            docling_version="2.109.0",
            bundle_root=tmp_path,
            name="safe-slug",
        )
    with pytest.raises(ValueError, match="^invalid slug$") as slug_error:
        serialize_document(
            [{"text": "body"}],
            doc_id=str(uuid4()),
            version_id=str(uuid4()),
            source_checksum="a" * 64,
            docling_version="2.109.0",
            bundle_root=tmp_path,
            name=secret_slug,
        )

    assert secret_uuid not in str(uuid_error.value)
    assert secret_slug not in str(slug_error.value)


def test_parser_cli_does_not_emit_title_alias_timestamp_or_caller_path(
    tmp_path: Path,
) -> None:
    title = "title-OPENAI_API_KEY=sk-title-canary"
    alias = "alias-秘密-��"
    timestamp = "2026-07-16T09:30:00Z"
    document = tmp_path / "caller-private" / "entity.md"
    document.parent.mkdir()
    document.write_text(
        "---\n"
        "type: entity\n"
        f"title: '{title}'\n"
        f"aliases: ['{alias}']\n"
        f"timestamp: '{timestamp}'\n"
        "canonical_entity_id: b2191a11-cd8b-4c6e-b34a-7b5552e3c03c\n"
        "entity_type: person\n"
        "---\n"
        "body-secret\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "-m", "llamaindex_runtime.okf.parser", str(tmp_path)],
        cwd=Path(__file__).resolve().parents[3],
        capture_output=True,
        check=False,
        text=True,
        env=_clean_environment(),
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == "Parsed 1 documents:\n  Type: document\n  Paragraphs: 1\n"
    for secret in (
        title,
        alias,
        timestamp,
        "caller-private",
        "entity.md",
        "body-secret",
    ):
        assert secret not in result.stdout + result.stderr


def test_public_parser_frontmatter_error_uses_fixed_vocabulary() -> None:
    secret = "OPENAI_API_KEY=sk-yaml-canary"

    with pytest.raises(ValueError, match="^frontmatter YAML is invalid$") as error:
        OKFParser().parse_frontmatter(f"---\ntitle: [{secret}\n---\n")

    assert secret not in str(error.value)
