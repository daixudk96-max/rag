"""Tests for llamaindex_runtime.entity.normalization (Wave 4a)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from llamaindex_runtime.entity.normalization import (
    USCC_CHARSET,
    extract_uscc,
    normalize_mention_text,
    validate_uscc,
)

_SOURCE = (
    Path(__file__).resolve().parents[3]
    / "llamaindex_runtime"
    / "entity"
    / "normalization.py"
)
_BASE17 = "91350100M000100YX"


def _construct(base17: str) -> str:
    charset = USCC_CHARSET
    total = 0
    for index in range(17):
        total = (total + charset.index(base17[index]) * pow(3, index, 31)) % 31
    check = 31 - total
    if check == 31:
        check = 0
    return base17 + charset[check]


class TestNormalizeMentionText:
    def test_fullwidth_to_ascii(self):
        assert normalize_mention_text("ＡＢＣ") == "abc"

    def test_fullwidth_punct_normalized(self):
        assert normalize_mention_text("（华为）") == "(华为)"

    def test_each_zero_width_char_removed(self):
        for ch in ("\u200b", "\u200c", "\u200d", "\ufeff"):
            assert normalize_mention_text("华" + ch + "为") == "华为"

    def test_ideographic_space_collapsed(self):
        assert normalize_mention_text("华为\u3000\u3000技术") == "华为 技术"

    def test_whitespace_runs_collapsed_and_stripped(self):
        assert normalize_mention_text("  华为   技术  ") == "华为 技术"

    def test_casefold(self):
        assert normalize_mention_text("Huawei") == "huawei"

    def test_chinese_unchanged(self):
        assert normalize_mention_text("华为") == "华为"

    def test_idempotent(self):
        once = normalize_mention_text(" Ｈｕａ\u200bｗｅｉ 技术 ")
        assert normalize_mention_text(once) == once

    def test_non_string_rejected(self):
        for bad in (123, None, b"huawei", ["华为"]):
            with pytest.raises(ValueError):
                normalize_mention_text(bad)  # type: ignore[arg-type]

    def test_empty_string_ok(self):
        assert normalize_mention_text("") == ""

    def test_deterministic(self):
        sample = "Ｈｕａ\u200bｗｅｉ"
        assert normalize_mention_text(sample) == normalize_mention_text(sample)


class TestValidateUscc:
    def test_constructed_positive(self):
        assert validate_uscc(_construct(_BASE17)) is True

    def test_tampered_positions_rejected(self):
        code = _construct(_BASE17)
        for pos in (0, 8, 16):
            chars = list(code)
            chars[pos] = USCC_CHARSET[(USCC_CHARSET.index(chars[pos]) + 1) % 31]
            assert validate_uscc("".join(chars)) is False

    def test_wrong_length_rejected(self):
        code = _construct(_BASE17)
        assert validate_uscc(code[:-1]) is False
        assert validate_uscc(code + "0") is False

    def test_illegal_alphabet_chars_rejected(self):
        assert validate_uscc(_BASE17 + "I") is False
        assert validate_uscc(_BASE17 + "O") is False
        assert validate_uscc(_BASE17 + "Z") is False

    def test_lowercase_and_separators_accepted(self):
        code = _construct(_BASE17)
        variant = code[:4] + " " + code[4:8] + "-" + code[8:].lower()
        assert validate_uscc(variant) is True

    def test_non_string_rejected_without_raise(self):
        for bad in (None, 123, True, ["x"]):
            assert validate_uscc(bad) is False  # type: ignore[arg-type]


class TestExtractUscc:
    def test_extracts_from_chinese_text(self):
        code = _construct(_BASE17)
        assert extract_uscc("统一社会信用代码 " + code + " 已核验") == code

    def test_no_candidate_returns_none(self):
        assert extract_uscc("没有代码的文本") is None

    def test_invalid_candidate_returns_none(self):
        broken = _construct(_BASE17)[:-1] + (
            "0" if _construct(_BASE17)[-1] != "0" else "1"
        )
        assert extract_uscc("代码 " + broken + " 结束") is None

    def test_first_valid_candidate_wins(self):
        good1 = _construct(_BASE17)
        good2 = _construct("92450100M000100AB")
        assert extract_uscc("A" + good1 + "B" + good2 + "C") == good1

    def test_non_string_rejected(self):
        with pytest.raises(ValueError):
            extract_uscc(None)  # type: ignore[arg-type]


class TestModulePurity:
    def test_imports_are_stdlib_whitelist(self):
        tree = ast.parse(_SOURCE.read_text(encoding="utf-8"))
        roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    roots.add(node.module.split(".")[0])
        assert roots == {"__future__", "re", "unicodedata", "typing"}

    def test_no_heavy_framework_substrings(self):
        text = _SOURCE.read_text(encoding="utf-8")
        for banned in ("datetime", "paddle", "torch", "transformers", "requests"):
            assert banned not in text
