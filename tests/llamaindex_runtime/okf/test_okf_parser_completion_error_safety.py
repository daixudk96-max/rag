"""Tests for OKF parser completion, split by cohesive parser behavior."""

from __future__ import annotations

import hashlib
import unicodedata
from pathlib import Path
from typing import Any

import pytest


def _run_hostile_frontmatter_cli(
    parser_module: Any,
    unsafe_character: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> tuple[str, str]:
    """Run the CLI against untrusted frontmatter and return its output streams."""
    import sys

    canary = f"canary-{unsafe_character}-value"
    document = parser_module.OKFDocument(
        file_path=Path("ignored.md"),
        frontmatter=parser_module.OKFFrontmatter(
            type=canary,
            title=canary,
            aliases=["中文 alias", canary],
            okf_file_path=f"raw/{canary}.md",
        ),
        body="",
    )

    class _Parser:
        def parse_bundle(self, _: Path) -> Any:
            return parser_module.BundleResult(
                [document], parser_module.BundleStats(parsed=1)
            )

    monkeypatch.setattr(parser_module, "OKFParser", _Parser)
    monkeypatch.setattr(sys, "argv", ["parser.py", "safe-bundle"])
    parser_module.main()
    captured = capsys.readouterr()
    return captured.out, captured.err


class TestParserTerminalAndErrorSafety:
    """Untrusted parser diagnostics remain terminal-safe and path-redacted."""

    @pytest.mark.parametrize(
        "unsafe_character",
        (
            "\x1b",
            "\t",
            "\x00",
            "\x7f",
            "\x85",
            "‮",
            "​",
            "\r\n",
            "\x1b]8;;canary.invalid\x1b\\",
        ),
        ids=(
            "escape",
            "tab",
            "nul",
            "delete",
            "c1",
            "bidi",
            "zero-width",
            "crlf",
            "osc",
        ),
    )
    def test_standalone_cli_hashes_hostile_frontmatter_output(
        self,
        unsafe_character: str,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """CLI output never reflects controls from metadata or a relative filename."""
        from llamaindex_runtime.okf import parser as parser_module

        canary = f"canary-{unsafe_character}-value"
        stdout, stderr = _run_hostile_frontmatter_cli(
            parser_module, unsafe_character, monkeypatch, capsys
        )
        assert stderr == ""
        assert canary not in stdout + stderr
        assert "canary.invalid" not in stdout + stderr
        assert "中文 alias" not in stdout + stderr
        assert "Type: document" in stdout
        assert "Title:" not in stdout
        assert "Aliases:" not in stdout
        assert "raw/" not in stdout
        assert all(
            not unicodedata.category(character).startswith("C")
            for character in (stdout + stderr).replace("\n", "")
        )

    def test_parse_bundle_hashes_unsafe_type_in_info_log(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """The parsed-document type sink logs an opaque value when it is hostile."""
        from llamaindex_runtime.okf import parser as parser_module

        unsafe_type = "unknown-\x1b]8;;canary.invalid\x1b\\\r\n‮"
        document = parser_module.OKFDocument(
            file_path=Path("safe.md"),
            frontmatter=parser_module.OKFFrontmatter(
                type=unsafe_type, okf_file_path="entities/safe.md"
            ),
            body="",
        )

        monkeypatch.setattr(
            parser_module.OKFParser,
            "_parse_authorized",
            lambda *_: document,
        )
        (tmp_path / "safe.md").write_text("unused", encoding="utf-8")

        with caplog.at_level("INFO"):
            result = parser_module.OKFParser().parse_bundle(tmp_path)

        messages = [record.getMessage() for record in caplog.records]
        assert result.stats == parser_module.BundleStats(parsed=1)
        assert any(
            "Parsed OKF document: type=document" == message for message in messages
        )
        assert all(unsafe_type not in message for message in messages)
        assert all(
            not any(
                unicodedata.category(character).startswith("C") for character in message
            )
            for message in messages
        )

    def test_invalid_timestamp_log_hashes_unsafe_value(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Invalid timestamp warnings do not reflect terminal control sequences."""
        from llamaindex_runtime.okf.parser import _parse_timestamp

        unsafe_value = "invalid-\x1b]8;;canary.invalid\x1b\\\r\n‮"
        with caplog.at_level("WARNING"):
            assert _parse_timestamp(unsafe_value) is None

        messages = [record.getMessage() for record in caplog.records]
        assert messages == [
            "Invalid timestamp format: field=timestamp "
            f"len={len(unsafe_value.encode('utf-8'))} "
            f"sha256={hashlib.sha256(unsafe_value.encode('utf-8')).hexdigest()}"
        ]
        assert all(unsafe_value not in message for message in messages)
        assert all(
            not any(
                unicodedata.category(character).startswith("C") for character in message
            )
            for message in messages
        )

    def test_parse_document_rejects_root_outside_path_without_context(
        self, tmp_path: Path
    ) -> None:
        """Public path-boundary errors disclose neither absolute path nor cause."""
        from llamaindex_runtime.okf.parser import OKFParser

        bundle_root = tmp_path / "bundle"
        bundle_root.mkdir()
        outside_path = tmp_path / "outside-canary-absolute.md"
        outside_path.write_text("---\ntype: legacy\n---\nbody", encoding="utf-8")

        with pytest.raises(ValueError) as exc_info:
            OKFParser().parse_document(outside_path, bundle_root)

        assert str(exc_info.value) == "document path must be contained in bundle root"
        assert exc_info.value.__cause__ is None
        assert str(outside_path) not in str(exc_info.value)

    def test_parse_document_redacts_read_oserror_without_context(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Read failures return one fixed public error without OS detail leakage."""
        from llamaindex_runtime.okf import parser as parser_module

        bundle_root = tmp_path / "bundle"
        bundle_root.mkdir()
        candidate = bundle_root / "canary.md"
        candidate.write_text("---\ntype: legacy\n---\nbody", encoding="utf-8")
        monkeypatch.setattr(
            parser_module.BundleAuthority,
            "read_document",
            lambda *_: (_ for _ in ()).throw(OSError("os-canary / absolute/path")),
        )

        with pytest.raises(ValueError) as exc_info:
            parser_module.OKFParser().parse_document(candidate, bundle_root)

        assert str(exc_info.value) == "document cannot be read"
        assert exc_info.value.__cause__ is None
        assert "os-canary" not in str(exc_info.value)


def test_bundle_order_uses_relative_posix_unicode_codepoints(tmp_path: Path) -> None:
    from llamaindex_runtime.okf.parser import OKFParser

    entities = tmp_path / "entities"
    entities.mkdir()
    for name in ("Ä.md", "a.md", "Z.md"):
        (entities / name).write_text(
            f"---\ntype: legacy_entity\ntitle: {name}\n---\nbody\n", encoding="utf-8"
        )

    result = OKFParser().parse_bundle(tmp_path)

    assert [document.frontmatter.okf_file_path for document in result] == [
        "entities/Z.md",
        "entities/a.md",
        "entities/Ä.md",
    ]
