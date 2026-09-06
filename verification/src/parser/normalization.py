from __future__ import annotations


def clean_text(raw: str) -> str:
    return " ".join(raw.split())


def normalize_heading(heading: str) -> str:
    return " ".join(heading.strip().split())
