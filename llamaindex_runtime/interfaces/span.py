from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class CanonicalSpan:
    doc_id: UUID
    version_id: UUID
    span_id: UUID
    text: str
    page_no: int | None = None
    headings: tuple[str, ...] = ()
    offset: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.doc_id, UUID):
            raise ValueError("doc_id must be a UUID")
        if not isinstance(self.version_id, UUID):
            raise ValueError("version_id must be a UUID")
        if not isinstance(self.span_id, UUID):
            raise ValueError("span_id must be a UUID")
        if not isinstance(self.text, str):
            raise ValueError("text must be a string")
        if not self.text.strip():
            raise ValueError("text must not be empty")
        if any(not isinstance(part, str) for part in self.headings):
            raise ValueError("headings must contain only strings")
        if self.page_no is not None and self.page_no < 0:
            raise ValueError("page_no must be non-negative")
        if self.offset < 0:
            raise ValueError("offset must be non-negative")

    @property
    def coordinate(self) -> tuple[UUID, UUID, UUID]:
        return (self.doc_id, self.version_id, self.span_id)

    @property
    def heading_path(self) -> str:
        return " > ".join(self.headings) if self.headings else "(root)"
