"""Mention text normalization primitives (Phase 17 Wave 4a).

Deterministic, dependency-free normalization for mention/entity names.
Zero-width characters (the W2 follow-up) are removed here.

USCC helpers implement the GB 32100-2015 check-digit algorithm.  All
test vectors are constructed from the algorithm itself; no `official`
sample codes are claimed.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Final

__all__ = [
    "USCC_CHARSET",
    "extract_uscc",
    "normalize_mention_text",
    "normalize_uscc_code",
    "validate_uscc",
]

USCC_CHARSET: Final[str] = "0123456789ABCDEFGHJKLMNPQRTUWXY"

_ZERO_WIDTH_RE: Final[re.Pattern[str]] = re.compile("[\u200b\u200c\u200d\ufeff]")
_WHITESPACE_RE: Final[re.Pattern[str]] = re.compile(r"\s+")
_USCC_CANDIDATE_RE: Final[re.Pattern[str]] = re.compile("(?=([0-9A-HJ-NPQRTUWXY]{18}))")
_CHARSET_INDEX: Final[dict[str, int]] = {ch: idx for idx, ch in enumerate(USCC_CHARSET)}


def normalize_mention_text(raw: str) -> str:
    """Normalize a mention/entity name string.

    Pipeline: (1) Unicode NFKC; (2) remove zero-width chars U+200B,
    U+200C, U+200D, U+FEFF; (3) collapse every whitespace run (incl.
    U+3000) to one space; (4) strip ends and casefold.

    Idempotent: f(f(x)) == f(x).
    """
    if not isinstance(raw, str):
        raise ValueError(
            "normalize_mention_text expects str, got " + type(raw).__name__
        )
    nfkc = unicodedata.normalize("NFKC", raw)
    without_zero_width = _ZERO_WIDTH_RE.sub("", nfkc)
    collapsed = _WHITESPACE_RE.sub(" ", without_zero_width)
    return collapsed.strip().casefold()


def normalize_uscc_code(raw: str) -> str | None:
    """Return the normalized 18-char USCC, or None when malformed."""
    if not isinstance(raw, str):
        return None
    compact = raw.replace(" ", "").replace("-", "").upper()
    if len(compact) != 18:
        return None
    if any(ch not in _CHARSET_INDEX for ch in compact):
        return None
    return compact


def _uscc_check_value(first_17: str) -> int:
    total = 0
    for index in range(17):
        weight = pow(3, index, 31)
        total = (total + _CHARSET_INDEX[first_17[index]] * weight) % 31
    check = 31 - total
    if check == 31:
        check = 0
    return check


def validate_uscc(code: str) -> bool:
    """Validate an 18-char USCC check digit (GB 32100-2015)."""
    normalized = normalize_uscc_code(code)
    if normalized is None:
        return False
    expected = _uscc_check_value(normalized[:17])
    return _CHARSET_INDEX[normalized[17]] == expected


def extract_uscc(text: str) -> str | None:
    """Extract the first checksum-valid USCC embedded in `text`.

    Candidates are 18-char runs over the USCC alphabet (case-insensitive).
    Returns None when there is no candidate or none validates.
    """
    if not isinstance(text, str):
        raise ValueError("extract_uscc expects str, got " + type(text).__name__)
    for match in _USCC_CANDIDATE_RE.finditer(text.upper()):
        if validate_uscc(match.group(1)):
            return match.group(1)
    return None
