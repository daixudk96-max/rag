"""Shared strict names for adjacent OKF raw-pair members."""

from __future__ import annotations

import re

_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def is_okf_slug(value: str) -> bool:
    """Return whether value is a legal lowercase kebab-case OKF member slug."""
    return (
        type(value) is str
        and 1 <= str.__len__(value) <= 100
        and bool(_SLUG_PATTERN.fullmatch(value))
    )
