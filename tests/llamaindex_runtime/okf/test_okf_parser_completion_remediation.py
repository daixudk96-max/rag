"""Tests for OKF parser completion, split by cohesive parser behavior."""

from __future__ import annotations

import hashlib
import unicodedata
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from ._parser_completion_testkit import _make_raw_md_content, _make_sidecar
from .raw_pair_testkit import bind_raw_bytes, refresh_raw_manifest


class TestParserContractRemediation:
    """Resource budgets and copied frontmatter protect the untrusted boundary."""

    def test_build_frontmatter_snapshots_mutable_values(self) -> None:
        from llamaindex_runtime.okf.parser import OKFParser

        input_frontmatter: dict[str, Any] = {
            "type": "entity",
            "title": "Alice",
            "timestamp": "2026-07-15T09:30:00Z",
            "canonical_entity_id": str(uuid4()),
            "entity_type": "person",
            "tags": ["person"],
            "aliases": ["A."],
            "relations": [{"target": "Acme", "nested": {"source": "test"}}],
            "mentions": [{"span": "P1"}],
            "qualifiers": {"future": {"flag": True}},
            "future_top_level": {"values": ["original"]},
        }

        frontmatter = OKFParser().build_frontmatter(input_frontmatter, None, "a" * 64)
        input_frontmatter["tags"].append("mutated")
        input_frontmatter["aliases"].append("mutated")
        input_frontmatter["relations"][0]["nested"]["source"] = "mutated"
        input_frontmatter["mentions"][0]["span"] = "mutated"
        input_frontmatter["qualifiers"]["future"]["flag"] = False
        input_frontmatter["future_top_level"]["values"].append("mutated")

        assert frontmatter.tags == ["person"]
        assert frontmatter.aliases == ["A."]
        assert frontmatter.relations[0]["nested"] == {"source": "test"}
        assert frontmatter.mentions == [{"span": "P1"}]
        assert frontmatter.qualifiers == {"future": {"flag": True}}
        assert frontmatter.extra_fields == {
            "future_top_level": {"values": ["original"]}
        }

    def test_parse_document_rejects_oversized_file_before_reading(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from llamaindex_runtime.okf import parser as parser_module

        md_path = tmp_path / "canary-secret-document.md"
        md_path.write_text("---\ntype: legacy\n---\nbody", encoding="utf-8")
        monkeypatch.setattr(parser_module._limits, "MAX_DOCUMENT_BYTES", 1)

        with pytest.raises(ValueError) as exc_info:
            parser_module.OKFParser().parse_document(md_path, tmp_path)

        assert str(exc_info.value) == "document exceeds maximum size"
        assert "canary-secret-document" not in str(exc_info.value)

    def test_parse_document_hashes_already_read_bytes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from llamaindex_runtime.okf.parser import OKFParser

        md_path = tmp_path / "legacy.md"
        content = "---\ntype: legacy\n---\nbody"
        md_path.write_bytes(content.encode("utf-8"))
        parser = OKFParser()
        monkeypatch.setattr(
            parser, "compute_hash", lambda _: pytest.fail("second file read")
        )

        document = parser.parse_document(md_path, tmp_path)

        import hashlib

        assert (
            document.version_hash == hashlib.sha256(content.encode("utf-8")).hexdigest()
        )

    @pytest.mark.parametrize(
        "yaml_content, expected_message",
        [
            ("key: canary-yaml-secret", "frontmatter exceeds maximum size"),
            (
                "nested: " + "[" * 80 + "x" + "]" * 80,
                "frontmatter YAML exceeds maximum depth",
            ),
            (
                "\n".join(f"key{i}: value{i}" for i in range(20)),
                "frontmatter YAML exceeds maximum nodes",
            ),
            (
                "base: &item value\n"
                + "items: ["
                + ", ".join("*item" for _ in range(40))
                + "]",
                "frontmatter YAML exceeds maximum aliases",
            ),
        ],
    )
    def test_parse_frontmatter_enforces_budgets_without_echoing_input(
        self,
        yaml_content: str,
        expected_message: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from llamaindex_runtime.okf import contracts
        from llamaindex_runtime.okf import parser as parser_module

        monkeypatch.setattr(contracts, "MAX_FRONTMATTER_BYTES", 10)
        if expected_message != "frontmatter exceeds maximum size":
            monkeypatch.setattr(contracts, "MAX_FRONTMATTER_BYTES", 100_000)
        monkeypatch.setattr(parser_module, "MAX_YAML_DEPTH", 8)
        monkeypatch.setattr(parser_module, "MAX_YAML_NODES", 10)
        monkeypatch.setattr(parser_module, "MAX_YAML_ALIASES", 3)

        with pytest.raises(ValueError) as exc_info:
            parser_module.OKFParser().parse_frontmatter(
                f"---\n{yaml_content}\n---\nbody"
            )

        assert str(exc_info.value) == expected_message
        assert "canary-yaml-secret" not in str(exc_info.value)

    def test_parse_frontmatter_malformed_yaml_has_fixed_non_echoing_error(self) -> None:
        from llamaindex_runtime.okf.parser import OKFParser

        with pytest.raises(ValueError) as exc_info:
            OKFParser().parse_frontmatter("---\nbad: [canary-secret\n---\nbody")

        assert str(exc_info.value) == "frontmatter YAML is invalid"
        assert "canary-secret" not in str(exc_info.value)

    def test_parse_frontmatter_rejects_depth_1500_before_recursion_error(self) -> None:
        from llamaindex_runtime.okf.parser import OKFParser

        yaml_content = "nested: " + "[" * 1_500 + "canary" + "]" * 1_500

        with pytest.raises(ValueError) as exc_info:
            OKFParser().parse_frontmatter(f"---\n{yaml_content}\n---\nbody")

        assert str(exc_info.value) == "frontmatter YAML exceeds maximum depth"
        assert "canary" not in str(exc_info.value)


class TestParserBoundaryRemediation:
    """Descriptor-bounded reads and sanitized error reporting at the file boundary."""

    def test_bounded_read_limits_actual_descriptor_read_after_growth(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from llamaindex_runtime.okf import parser as parser_module

        path = tmp_path / "growing.md"
        path.write_bytes(b"xxxx")
        monkeypatch.setattr(parser_module._limits, "MAX_DOCUMENT_BYTES", 3)

        with pytest.raises(ValueError) as exc_info:
            parser_module._read_document_bytes_bounded(path)

        assert str(exc_info.value) == "document exceeds maximum size"

    def test_parse_document_rejects_invalid_utf8_with_fixed_non_echoing_error(
        self, tmp_path: Path
    ) -> None:
        from llamaindex_runtime.okf.parser import OKFParser

        md_path = tmp_path / "canary-path.md"
        md_path.write_bytes(b"---\ntype: legacy\n---\n\xffcanary-bytes")

        with pytest.raises(ValueError) as exc_info:
            OKFParser().parse_document(md_path, tmp_path)

        assert str(exc_info.value) == "document must be valid UTF-8"
        assert "canary-path" not in str(exc_info.value)
        assert "canary-bytes" not in str(exc_info.value)

    @pytest.mark.parametrize("mismatch_field", ("doc_id", "version_id"))
    def test_sidecar_identity_mismatch_does_not_echo_identifiers(
        self, tmp_path: Path, mismatch_field: str
    ) -> None:
        from llamaindex_runtime.okf.parser import OKFParser

        doc_id = str(uuid4())
        version_id = str(uuid4())
        frontmatter = {
            "type": "raw",
            "doc_id": doc_id,
            "version_id": version_id,
            "source_checksum": "a" * 64,
            "docling_version": "2.45.0",
            "generated_by": "test",
        }
        md_path = tmp_path / "raw" / "canary.md"
        md_path.parent.mkdir()
        md_path.write_text(_make_raw_md_content(frontmatter), encoding="utf-8")
        sidecar = _make_sidecar(
            doc_id=str(uuid4()) if mismatch_field == "doc_id" else doc_id,
            version_id=str(uuid4()) if mismatch_field == "version_id" else version_id,
        )
        sidecar.dump(md_path.with_suffix(".spans.json"))
        refresh_raw_manifest(md_path)

        with pytest.raises(ValueError) as exc_info:
            OKFParser().parse_document(md_path, tmp_path)

        assert (
            str(exc_info.value)
            == f"sidecar {mismatch_field} does not match frontmatter"
        )
        assert doc_id not in str(exc_info.value)
        assert version_id not in str(exc_info.value)
        assert str(md_path) not in str(exc_info.value)

    def test_missing_sidecar_error_does_not_echo_absolute_path(
        self, tmp_path: Path
    ) -> None:
        from llamaindex_runtime.okf.parser import OKFParser

        doc_id = str(uuid4())
        version_id = str(uuid4())
        md_path = tmp_path / "raw" / "canary.md"
        md_path.parent.mkdir()
        md_path.write_text(
            _make_raw_md_content(
                {
                    "type": "raw",
                    "doc_id": doc_id,
                    "version_id": version_id,
                    "source_checksum": "a" * 64,
                    "docling_version": "2.45.0",
                    "generated_by": "test",
                }
            ),
            encoding="utf-8",
        )
        bind_raw_bytes(md_path, b"placeholder", write_sidecar=False)

        with pytest.raises(ValueError) as exc_info:
            OKFParser().parse_document(md_path, tmp_path)

        assert str(exc_info.value) == "raw file requires adjacent sidecar"
        assert str(md_path) not in str(exc_info.value)

    def test_parse_bundle_log_summarizes_relative_path_without_raw_error(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        from llamaindex_runtime.okf.parser import OKFParser

        absolute_canary = tmp_path / "entities" / "canary.md"
        absolute_canary.parent.mkdir()
        absolute_canary.write_text("---\nbad: [raw-canary\n---\nbody", encoding="utf-8")

        with caplog.at_level("ERROR"):
            OKFParser().parse_bundle(tmp_path)

        messages = [record.getMessage() for record in caplog.records]
        relative_path = "entities/canary.md"
        assert any(
            f"path=len={len(relative_path.encode('utf-8'))} "
            f"sha256={hashlib.sha256(relative_path.encode('utf-8')).hexdigest()}"
            in message
            for message in messages
        )
        assert all(str(absolute_canary) not in message for message in messages)
        assert all("raw-canary" not in message for message in messages)

    def test_parse_bundle_hashes_control_bearing_missing_bundle_path(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Missing-bundle diagnostics are one safe log record for hostile input."""
        from llamaindex_runtime.okf.parser import BundleStats, OKFParser

        unsafe_path = "missing-\r\n\x00\x1b\t\x7f\x85‮​\x1b]8;;canary.invalid\x1b\\bundle"

        class _MissingBundle:
            def exists(self) -> bool:
                return False

            def __str__(self) -> str:
                return unsafe_path

        with caplog.at_level("ERROR"):
            result = OKFParser().parse_bundle(_MissingBundle())  # type: ignore[arg-type]

        messages = [record.getMessage() for record in caplog.records]
        assert result.stats == BundleStats()
        assert messages == ["Bundle path does not exist: invalid-type=non-string"]
        assert len(caplog.records) == 1
        assert all("canary.invalid" not in message for message in messages)
        assert all(
            not any(
                unicodedata.category(character).startswith("C") for character in message
            )
            for message in messages
        )

    def test_parse_bundle_hashes_unsafe_malformed_relative_path(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Malformed-file diagnostics never echo control-bearing relative paths."""
        from llamaindex_runtime.okf import parser as parser_module
        from llamaindex_runtime.okf.parser import BundleStats, OKFParser

        unsafe_path = "raw/\x1b\t\x7f\x85‮​\x1b]8;;canary.invalid\x1b\\canary.md"

        class _MalformedFile:
            def __str__(self) -> str:
                return unsafe_path

        candidate = _MalformedFile()
        calls = 0

        def malformed_after_sort(*_: object) -> tuple[str, ...]:
            nonlocal calls
            calls += 1
            if calls == 1:
                return ("safe",)
            raise ValueError("invalid")

        monkeypatch.setattr(Path, "rglob", lambda *_: [candidate])
        monkeypatch.setattr(
            parser_module, "bundle_relative_components", malformed_after_sort
        )

        with caplog.at_level("ERROR"):
            result = OKFParser().parse_bundle(tmp_path)

        messages = [record.getMessage() for record in caplog.records]
        assert result.stats == BundleStats(parsed=0, skipped=1, malformed=1)
        assert messages == [
            "Failed to parse OKF document: "
            "path=invalid-type=non-string category=invalid_document"
        ]
        assert all("canary.invalid" not in message for message in messages)
        assert all(
            not any(
                unicodedata.category(character).startswith("C") for character in message
            )
            for message in messages
        )
