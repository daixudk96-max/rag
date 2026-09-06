"""OKF (Open Knowledge Format) Parser Module.

This module parses OKF bundles and extracts structured data for ingestion
into the rag retrieval system.

References:
    - OKF v0.1 Spec: https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md
    - LLM Wiki: https://github.com/mchu1966/okf-wiki

Phase 14-03 additions:
    - Sidecar reading for raw files (span identity from sidecar, not body)
    - Raw frontmatter fail-fast validation via RawFrontmatterContract
    - Sync decision DTO/function for incremental sync
    - Delete detection via path comparison

Phase 18 addition: bundle-relative paths containing a '.staging' component are excluded from ingestion.
"""

from __future__ import annotations

import hashlib
import logging
import os
import stat
from collections.abc import Mapping, Set as AbstractSet
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from ._frontmatter import build_frontmatter_values
from . import _limits
from ._raw_pair_admission import thaw_frontmatter
from .contracts import (
    extract_bounded_frontmatter,
    load_bounded_safe_yaml,
    validate_known_frontmatter,
)
from .diagnostics import diagnostic_safe_path, diagnostic_safe_text
from .sidecar import SpanRecord
from .rooted_open import BundleAuthority, bundle_relative_components
from .raw_pair import RawPairSnapshot, read_raw_pair

logger = logging.getLogger(__name__)

# Untrusted document and frontmatter budgets. The document byte budget is shared
# with rooted reader and publisher paths; frontmatter bounds live in contracts.py.
MAX_YAML_DEPTH = 64
MAX_YAML_NODES = 10_000
MAX_YAML_ALIASES = 32


def _is_reparse_point(file_stat: os.stat_result) -> bool:
    """Return whether a Windows reparse point is present without platform assumptions."""
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(getattr(file_stat, "st_file_attributes", 0) & reparse_flag)


def _is_regular_file(file_stat: os.stat_result) -> bool:
    """Return whether a stat result describes a regular file."""
    return stat.S_ISREG(file_stat.st_mode) and not _is_reparse_point(file_stat)


def _read_document_bytes_bounded(file_path: Path) -> bytes:
    """Read a stable regular file from one descriptor without following links."""
    descriptor: int | None = None
    try:
        path_stat = os.lstat(file_path)
        if not _is_regular_file(path_stat):
            raise ValueError("document cannot be read")
        flags = os.O_RDONLY
        for flag_name in ("O_BINARY", "O_NONBLOCK", "O_NOFOLLOW"):
            flags |= getattr(os, flag_name, 0)
        descriptor = os.open(file_path, flags)
        descriptor_stat = os.fstat(descriptor)
        if not _is_regular_file(descriptor_stat) or not os.path.samestat(
            path_stat, descriptor_stat
        ):
            raise ValueError("document cannot be read")
        maximum = _limits.MAX_DOCUMENT_BYTES
        if descriptor_stat.st_size > maximum:
            raise ValueError("document exceeds maximum size")
        chunks: list[bytes] = []
        total = 0
        while total <= maximum:
            chunk = os.read(descriptor, min(64 * 1024, maximum + 1 - total))
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum:
                raise ValueError("document exceeds maximum size")
    except ValueError:
        raise
    except OSError:
        raise ValueError("document cannot be read") from None
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
    raise ValueError("document cannot be read")


def _decode_document(content_bytes: bytes) -> str:
    """Decode trusted bounded bytes without exposing codec context to callers."""
    try:
        return content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("document must be valid UTF-8") from None


# ==============================================================================
# Sync Decision Types (P14-07)
# ==============================================================================


@dataclass(frozen=True)
class SyncDecision:
    """Immutable DTO for incremental sync decisions.

    Status values:
        - "synced": New file, no previous state
        - "skipped": Unchanged canonical hash
        - "resynced": Changed canonical hash
        - "deleted": File removed from bundle (computed separately)
    """

    doc_id: str
    status: str  # "synced" | "skipped" | "resynced"
    canonical_hash: str
    okf_file_path: str


@dataclass(frozen=True)
class BundleStats:
    """Immutable stats for bundle parsing results."""

    parsed: int = 0
    skipped: int = 0
    malformed: int = 0


def compute_sync_decision(
    *,
    doc_id: str,
    okf_file_path: str,
    current_canonical_hash: str,
    previous_state: Mapping[str, Any] | None,
) -> SyncDecision:
    """Return a sync decision preserving the supplied current identity."""
    if previous_state is None:
        # New file - needs sync; current identity is preserved (not empty)
        return SyncDecision(
            doc_id=doc_id,
            status="synced",
            canonical_hash=current_canonical_hash,
            okf_file_path=okf_file_path,
        )

    previous_hash = previous_state.get("canonical_hash", "")

    if current_canonical_hash == previous_hash:
        # Unchanged - skip; current identity preserved
        return SyncDecision(
            doc_id=doc_id,
            status="skipped",
            canonical_hash=current_canonical_hash,
            okf_file_path=okf_file_path,
        )
    else:
        # Changed - needs resync; current identity preserved
        return SyncDecision(
            doc_id=doc_id,
            status="resynced",
            canonical_hash=current_canonical_hash,
            okf_file_path=okf_file_path,
        )


def compute_deleted_paths(
    previous_paths: AbstractSet[str],
    current_paths: AbstractSet[str],
) -> frozenset[str]:
    """Compute deleted paths by comparing previous and current path sets.

    Args:
        previous_paths: Set of previously-known OKF file paths (any AbstractSet).
        current_paths: Set of currently-discovered OKF file paths (any AbstractSet).

    Returns:
        Frozenset of paths that were in previous but not in current (deleted)
    """
    return frozenset(previous_paths - current_paths)


def _parse_timestamp(value: Any) -> datetime | None:
    """Coerce a frontmatter timestamp value into a datetime, or None.

    Robust across YAML-produced types:
    - ``datetime`` returned as-is.
    - ``date`` converted to a midnight ``datetime`` (same calendar day).
    - ``str`` parsed via ``datetime.fromisoformat`` after normalizing a
      trailing ``Z`` (UTC) suffix; invalid strings log a warning and return None.
    - Any other type (int, float, None, etc.) logs a warning and returns None
      instead of raising ``AttributeError``.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            logger.warning(
                "Invalid timestamp format: field=timestamp %s",
                diagnostic_safe_text(value),
            )
            return None
    logger.warning(
        f"Timestamp must be a datetime, date, or string; got {type(value).__name__}"
    )
    return None


@dataclass
class OKFFrontmatter:
    """OKF YAML frontmatter fields.

    Standard OKF v0.1 fields plus extensions for entity/relation layer.
    """

    # OKF v0.1 required fields
    type: str

    # OKF v0.1 recommended fields
    title: str | None = None
    description: str | None = None
    resource: str | None = None
    tags: list[str] = field(default_factory=list)
    timestamp: datetime | str | None = None

    # OKF extensions (producer-defined keys)
    aliases: list[str] = field(default_factory=list)
    canonical_entity_id: str | None = None
    entity_type: str | None = None
    relations: list[dict[str, Any]] = field(default_factory=list)
    mentions: list[dict[str, Any]] = field(default_factory=list)
    subject_entity_id: str | None = None
    predicate: str | None = None
    object_entity_id: str | None = None
    negation: bool | None = None
    condition: str | None = None
    direction: str | None = None
    confidence: float | int | None = None
    qualifiers: dict[str, Any] = field(default_factory=dict)

    # Additional metadata
    source: str | None = None  # For source-summary type
    okf_file_path: str | None = None
    okf_version_hash: str | None = None

    # Phase 14-03: Typed raw provenance fields (populated for raw files; None
    # otherwise). These mirror RawFrontmatterContract fields so callers can read
    # document-level provenance directly off OKFFrontmatter without re-parsing.
    doc_id: str | None = None
    version_id: str | None = None
    source_checksum: str | None = None
    docling_version: str | None = None
    generated_by: str | None = None

    # Phase 14-03: Additive spillover for unknown top-level frontmatter fields.
    extra_fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class OKFParagraph:
    """A paragraph in OKF body."""

    id: str  # Paragraph identifier (e.g., P1, P2)
    content: str
    heading: str | None = None  # Section heading if applicable
    okf_file_path: str | None = None


@dataclass
class OKFDocument:
    """A complete OKF document (markdown file)."""

    file_path: Path
    frontmatter: OKFFrontmatter
    body: str
    paragraphs: list[OKFParagraph] = field(default_factory=list)
    version_hash: str | None = None
    # Phase 14-03: Spans from sidecar (raw files only).
    # Uses the sidecar's frozen SpanRecord directly — no duplicate DTO.
    spans: tuple[SpanRecord, ...] = ()
    # Phase 14-03: Canonical structural hash for sync decisions.
    # Excludes Markdown body so reflow does not change identity.
    canonical_hash: str | None = None


class BundleDocuments(list[OKFDocument]):
    """List-compatible result from parse_bundle with mandatory .stats attribute.

    FROZEN CONTRACT: This class is a ``list[OKFDocument]`` subclass that exposes
    an immutable ``BundleStats`` object via the ``.stats`` property. The stats
    are mandatory, not optional - code must access ``result.stats`` directly
    without ``hasattr`` guards.

    Defined after ``OKFDocument`` so the ``list[OKFDocument]`` base has no
    runtime forward-reference problems.
    """

    __slots__ = ("_stats",)
    _stats: BundleStats

    def __init__(self, docs: list[OKFDocument], stats: BundleStats) -> None:
        """Initialize with documents list and immutable stats."""
        super().__init__(docs)
        object.__setattr__(self, "_stats", stats)

    @property
    def stats(self) -> BundleStats:
        """Return immutable BundleStats for this parse operation."""
        return self._stats

    @property
    def documents(self) -> "BundleDocuments":
        """Return the parsed documents (list-compatible view of this result)."""
        return self


# Backward-compatibility alias. BundleDocuments is the canonical name; new code
# should use BundleDocuments directly.
BundleResult = BundleDocuments


class OKFParser:
    """Parser for OKF bundles and documents.

    Usage:
        parser = OKFParser()
        bundle_docs = parser.parse_bundle(Path("okf_bundle"))
        document_count = len(bundle_docs)
        parsed_count = bundle_docs.stats.parsed
    """

    def __init__(self) -> None:
        # Phase 14-03: Additive stats API for the most recent parse_bundle call.
        # parse_bundle still returns list[OKFDocument] by default; stats are
        # exposed here to preserve backward compatibility.
        self.last_bundle_stats: BundleStats | None = None

    def parse_bundle(self, bundle_path: Path) -> BundleResult:
        """Parse candidates under one held root authority."""
        documents: list[OKFDocument]
        try:
            if hasattr(bundle_path, "exists") and not bundle_path.exists():
                logger.error(
                    "Bundle path does not exist: %s", diagnostic_safe_path(bundle_path)
                )
                documents, stats = [], BundleStats()
            else:
                root = Path(bundle_path)
                with BundleAuthority(root) as authority:
                    candidates = sorted(
                        root.rglob("*.md"),
                        key=lambda path: bundle_relative_components(path, root),
                    )
                    documents, stats = self._parse_candidates(
                        candidates, root, authority
                    )
        except (TypeError, ValueError, OSError, AttributeError):
            logger.error(
                "Bundle path is inaccessible: %s", diagnostic_safe_path(bundle_path)
            )
            documents, stats = [], BundleStats()
        self.last_bundle_stats = stats
        return BundleResult(documents, stats)

    def _parse_candidates(
        self, candidates: list[Path], root: Path, authority: BundleAuthority
    ) -> tuple[list[OKFDocument], BundleStats]:
        documents: list[OKFDocument] = []
        parsed = skipped = malformed = 0
        for candidate in candidates:
            try:
                parts = bundle_relative_components(candidate, root)
            except ValueError:
                malformed += 1
                skipped += 1
                logger.error(
                    "Failed to parse OKF document: path=%s category=invalid_document",
                    diagnostic_safe_path(candidate),
                )
                continue
            if (
                candidate.name in {"index.md", "log.md"}
                or ".obsidian" in parts
                or ".staging" in parts
            ):
                skipped += 1
                continue
            try:
                document = self._parse_authorized(candidate, parts, authority)
                documents.append(document)
                logger.info("Parsed OKF document: type=document")
                parsed += 1
            except ValueError:
                malformed += 1
                skipped += 1
                logger.error(
                    "Failed to parse OKF document: path=%s category=invalid_document",
                    diagnostic_safe_path("/".join(parts)),
                )
        return documents, BundleStats(
            parsed=parsed, skipped=skipped, malformed=malformed
        )

    def parse_document(
        self, file_path: Path, bundle_root: Path | None = None
    ) -> OKFDocument:
        """Parse one document through a held bundle authority when rooted."""
        if bundle_root is None:
            content_bytes = _read_document_bytes_bounded(file_path)
            return self._parse_content(file_path, None, content_bytes)
        parts = bundle_relative_components(file_path, bundle_root)
        with BundleAuthority(bundle_root) as authority:
            return self._parse_authorized(file_path, parts, authority)

    def _parse_authorized(
        self, file_path: Path, parts: tuple[str, ...], authority: BundleAuthority
    ) -> OKFDocument:
        if len(parts) >= 2 and parts[0] == "raw":
            return self._parse_admitted_raw(
                file_path, "/".join(parts), read_raw_pair(authority, parts)
            )
        try:
            content_bytes = authority.read_document(parts)
        except OSError:
            raise ValueError("document cannot be read") from None
        return self._parse_content(file_path, "/".join(parts), content_bytes)

    def _parse_admitted_raw(
        self, file_path: Path, okf_file_path: str, snapshot: RawPairSnapshot
    ) -> OKFDocument:
        """Build a raw document solely from the reader's admitted snapshot."""
        return self._build_document(
            file_path,
            thaw_frontmatter(snapshot.frontmatter),
            snapshot.body,
            okf_file_path,
            hashlib.sha256(snapshot.markdown_bytes).hexdigest(),
            True,
            snapshot.sidecar.spans,
            snapshot.manifest.canonical_hash,
        )

    def _parse_content(
        self, file_path: Path, okf_file_path: str | None, content_bytes: bytes
    ) -> OKFDocument:
        content = _decode_document(content_bytes)
        extracted = extract_bounded_frontmatter(content)
        frontmatter_dict = self._parse_extracted_frontmatter(extracted)
        body = extracted[1] if extracted is not None else content
        parts = tuple(okf_file_path.split("/")) if okf_file_path else ()
        is_raw_file = self._validate_location_parts(parts, frontmatter_dict)
        return self._build_document(
            file_path,
            frontmatter_dict,
            body.replace("\r\n", "\n"),
            okf_file_path,
            hashlib.sha256(content_bytes).hexdigest(),
            is_raw_file,
            (),
            None,
        )

    @staticmethod
    def _validate_location_parts(
        parts: tuple[str, ...], frontmatter: dict[str, Any]
    ) -> bool:
        raw_directory = len(parts) >= 2 and parts[0] == "raw"
        if raw_directory and frontmatter.get("type") != "raw":
            raise ValueError("raw directory document must declare type 'raw'")
        is_raw = frontmatter.get("type") == "raw"
        if is_raw:
            raise ValueError("raw document must reside under bundle root raw directory")
        validate_known_frontmatter(frontmatter)
        return False

    def _build_document(
        self,
        file_path: Path,
        frontmatter_dict: dict[str, Any],
        content: str,
        okf_file_path: str | None,
        version_hash: str,
        is_raw_file: bool,
        spans: tuple[SpanRecord, ...],
        canonical_hash: str | None,
    ) -> OKFDocument:
        frontmatter = self.build_frontmatter(
            frontmatter_dict, okf_file_path, version_hash
        )
        body = content.replace("\r\n", "\n")
        paragraphs = [] if is_raw_file else self.parse_paragraphs(body, okf_file_path)
        return OKFDocument(
            file_path=file_path,
            frontmatter=frontmatter,
            body=body,
            paragraphs=paragraphs,
            version_hash=version_hash,
            spans=spans,
            canonical_hash=canonical_hash,
        )

    def parse_frontmatter(self, content: str) -> dict[str, Any]:
        """Extract and parse YAML frontmatter.

        Fail-fast: malformed YAML raises ValueError instead of silently returning
        a type=unknown dict. A file with no frontmatter block at all retains the
        legacy ``{"type": "unknown"}`` fallback for backward compatibility.

        Args:
            content: Full markdown file content

        Returns:
            Dictionary of frontmatter fields

        Raises:
            ValueError: If the frontmatter block exists but contains malformed YAML,
                or if the parsed YAML is not a dict.
        """
        return self._parse_extracted_frontmatter(extract_bounded_frontmatter(content))

    @staticmethod
    def _parse_extracted_frontmatter(
        extracted: tuple[str, str] | None,
    ) -> dict[str, Any]:
        """Parse one already-extracted frontmatter block without rescanning body."""
        if extracted is None:
            logger.warning("No frontmatter found in content")
            return {"type": "unknown"}
        yaml_content, _ = extracted
        try:
            frontmatter_dict = load_bounded_safe_yaml(
                yaml_content,
                max_depth=MAX_YAML_DEPTH,
                max_nodes=MAX_YAML_NODES,
                max_aliases=MAX_YAML_ALIASES,
            )
        except ValueError as exc:
            raise ValueError(str(exc)) from None
        if not isinstance(frontmatter_dict, dict):
            raise ValueError("frontmatter must be a YAML mapping")
        return frontmatter_dict

    def build_frontmatter(
        self,
        frontmatter_dict: dict[str, Any],
        okf_file_path: str | None,
        version_hash: str,
    ) -> OKFFrontmatter:
        """Build a public frontmatter DTO from validated parsed YAML."""
        values = build_frontmatter_values(frontmatter_dict, _parse_timestamp)
        return OKFFrontmatter(
            **values,
            okf_file_path=okf_file_path,
            okf_version_hash=version_hash,
        )

    def extract_body(self, content: str) -> str:
        """Extract body content (after frontmatter).

        Args:
            content: Full markdown file content

        Returns:
            Body string (everything after --- closing delimiter)
        """
        extracted = extract_bounded_frontmatter(content)
        return extracted[1] if extracted is not None else content

    def parse_paragraphs(
        self, body: str, okf_file_path: str | None
    ) -> list[OKFParagraph]:
        """Parse body into paragraphs.

        Args:
            body: Body content (markdown)
            okf_file_path: Bundle-relative path for溯源

        Returns:
            List of OKFParagraph objects
        """
        paragraphs = []

        # Split by double newlines (paragraph boundaries)
        para_texts = [p.strip() for p in body.split("\n\n") if p.strip()]

        for i, para_text in enumerate(para_texts, start=1):
            # Check if paragraph starts with heading
            heading = None
            if para_text.startswith("#"):
                lines = para_text.split("\n")
                heading_line = lines[0]
                heading = heading_line.lstrip("# ").strip()

            paragraph_id = f"P{i}"
            paragraphs.append(
                OKFParagraph(
                    id=paragraph_id,
                    content=para_text,
                    heading=heading,
                    okf_file_path=okf_file_path,
                )
            )

        return paragraphs

    def compute_hash(self, file_path: Path) -> str:
        """Compute SHA256 hash of file for version tracking.

        Args:
            file_path: Path to file

        Returns:
            SHA256 hash string (hex)
        """
        content = _read_document_bytes_bounded(file_path)
        return hashlib.sha256(content).hexdigest()


def main() -> None:
    """CLI entry point for testing OKF parser."""
    import argparse

    parser = argparse.ArgumentParser(description="Parse OKF bundle")
    parser.add_argument("bundle_path", type=Path, help="Path to OKF bundle")
    args = parser.parse_args()

    okf_parser = OKFParser()
    docs = okf_parser.parse_bundle(args.bundle_path)

    print(f"Parsed {len(docs)} documents:")
    for doc in docs:
        print("  Type: document")
        print(f"  Paragraphs: {len(doc.paragraphs)}")


if __name__ == "__main__":
    main()
