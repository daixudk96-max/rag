"""Phase 15 Caller Inventory Enforcement Test."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

import pytest


@dataclass(frozen=True)
class InventoryRow:
    """Parsed inventory row from Markdown table."""

    uid: str
    path_symbol: str
    entry_condition: str
    owner: str
    disposition: str
    direct_callers: str
    processes: str
    risk: str
    enforcement_test_surface: str


# Canonical UIDs required in inventory (verified from GitNexus)
CANONICAL_UIDS: frozenset[str] = frozenset(
    {
        "Method:llamaindex_runtime/ingestion/pipeline.py:IngestionPipeline.ingest#2",
        "Method:llamaindex_runtime/registry/postgres_adapter.py:PostgresRegistryWriter.write_spans#2",
        "Method:llamaindex_runtime/registry/postgres_adapter.py:PostgresRegistryWriter.write_tree#3",
        "Method:llamaindex_runtime/registry/postgres_adapter.py:PostgresRegistryWriter.write_vector_chunks#2",
        "Method:llamaindex_runtime/registry/tree_generator.py:TreeGenerator.generate_tree#2",
        "Method:llamaindex_runtime/tree/pageindex_adapter.py:PageIndexTreeAdapter.index_tree#3",
        "Method:llamaindex_runtime/tree/pageindex_adapter.py:PageIndexTreeAdapter._flatten_embedded_tree#4",
        "Method:llamaindex_runtime/client/pageindex_client.py:EnhancedPageIndexClient.index#4",
        "Function:llamaindex_runtime/cli/run_pageindex.py:main",
        "Method:llamaindex_runtime/okf/e2a_reconciler.py:E2aReconciler.reconcile#2",
        "Function:llamaindex_runtime/processing/callbacks.py:build_tree_entity_extraction_callback",
        "Method:llamaindex_runtime/registry/postgres_adapter.py:PostgresRegistryWriter.write_chunk_entity_links#2",
        "Method:llamaindex_runtime/registry/postgres_adapter.py:PostgresRegistryWriter.write_node_entity_links#2",
        "Method:llamaindex_runtime/vector/loader.py:VectorLoader.load#2",
        "Method:llamaindex_runtime/registry/postgres_adapter.py:PostgresRegistryWriter.write_entities#1",
        "Method:llamaindex_runtime/registry/postgres_adapter.py:PostgresRegistryWriter.write_evidence_links#2",
    }
)

CRITICAL_UIDS: frozenset[str] = frozenset(
    {
        "Method:llamaindex_runtime/ingestion/pipeline.py:IngestionPipeline.ingest#2",
        "Method:llamaindex_runtime/registry/postgres_adapter.py:PostgresRegistryWriter.write_tree#3",
        "Method:llamaindex_runtime/tree/pageindex_adapter.py:PageIndexTreeAdapter._flatten_embedded_tree#4",
    }
)

HIGH_UIDS: frozenset[str] = frozenset(
    {
        "Method:llamaindex_runtime/registry/postgres_adapter.py:PostgresRegistryWriter.write_spans#2",
        "Method:llamaindex_runtime/tree/pageindex_adapter.py:PageIndexTreeAdapter.index_tree#3",
        "Method:llamaindex_runtime/client/pageindex_client.py:EnhancedPageIndexClient.index#4",
    }
)

VALID_RISKS: frozenset[str] = frozenset(
    {"CRITICAL", "HIGH", "MEDIUM", "LOW", "UNRESOLVED"}
)
VALID_OWNERS: frozenset[str] = frozenset(
    {"E2a", "E2b", "legacy", "cache/legacy", "split E2a/E2b", "legacy/cache"}
)

VECTORLOADER_UID = "Method:llamaindex_runtime/vector/loader.py:VectorLoader.load#2"

# Compact canonical expectations: UID -> (path_symbol, owner, direct_callers, processes, risk)
CANONICAL_EXPECTATIONS: dict[str, tuple[str, str, str, str, str]] = {
    "Method:llamaindex_runtime/ingestion/pipeline.py:IngestionPipeline.ingest#2": (
        "IngestionPipeline.ingest",
        "E2a",
        "103 direct",
        "2 processes",
        "CRITICAL",
    ),
    "Method:llamaindex_runtime/registry/postgres_adapter.py:PostgresRegistryWriter.write_spans#2": (
        "PostgresRegistryWriter.write_spans",
        "legacy",
        "6 direct",
        "4 processes",
        "HIGH",
    ),
    "Method:llamaindex_runtime/registry/postgres_adapter.py:PostgresRegistryWriter.write_tree#3": (
        "PostgresRegistryWriter.write_tree",
        "legacy",
        "54 direct",
        "6 processes",
        "CRITICAL",
    ),
    "Method:llamaindex_runtime/registry/postgres_adapter.py:PostgresRegistryWriter.write_vector_chunks#2": (
        "PostgresRegistryWriter.write_vector_chunks",
        "legacy",
        "14 direct",
        "0 processes",
        "MEDIUM",
    ),
    "Method:llamaindex_runtime/registry/tree_generator.py:TreeGenerator.generate_tree#2": (
        "TreeGenerator.generate_tree",
        "E2a",
        "6 direct",
        "0 processes",
        "MEDIUM",
    ),
    "Method:llamaindex_runtime/tree/pageindex_adapter.py:PageIndexTreeAdapter.index_tree#3": (
        "PageIndexTreeAdapter.index_tree",
        "cache/legacy",
        "15 direct",
        "4 processes",
        "HIGH",
    ),
    "Method:llamaindex_runtime/tree/pageindex_adapter.py:PageIndexTreeAdapter._flatten_embedded_tree#4": (
        "PageIndexTreeAdapter._flatten_embedded_tree",
        "cache/legacy",
        "13 direct",
        "5 processes",
        "CRITICAL",
    ),
    "Method:llamaindex_runtime/client/pageindex_client.py:EnhancedPageIndexClient.index#4": (
        "EnhancedPageIndexClient.index",
        "cache/legacy",
        "9 direct",
        "3 processes",
        "HIGH",
    ),
    "Function:llamaindex_runtime/cli/run_pageindex.py:main": (
        "CLI main",
        "E2a",
        "1 direct",
        "0 processes",
        "LOW",
    ),
    "Method:llamaindex_runtime/okf/e2a_reconciler.py:E2aReconciler.reconcile#2": (
        "E2aReconciler.reconcile",
        "E2a",
        "3 direct",
        "0 processes",
        "LOW",
    ),
    "Function:llamaindex_runtime/processing/callbacks.py:build_tree_entity_extraction_callback": (
        "build_tree_entity_extraction_callback",
        "E2b",
        "4 direct",
        "0 processes",
        "LOW",
    ),
    "Method:llamaindex_runtime/registry/postgres_adapter.py:PostgresRegistryWriter.write_chunk_entity_links#2": (
        "write_chunk_entity_links",
        "E2b",
        "0 direct",
        "0 processes",
        "LOW",
    ),
    "Method:llamaindex_runtime/registry/postgres_adapter.py:PostgresRegistryWriter.write_node_entity_links#2": (
        "write_node_entity_links",
        "E2b",
        "0 direct",
        "0 processes",
        "LOW",
    ),
    "Method:llamaindex_runtime/vector/loader.py:VectorLoader.load#2": (
        "VectorLoader.load",
        "legacy/cache",
        "UNRESOLVED (partial:true from tool error)",
        "0 processes (from context, not impact)",
        "UNRESOLVED",
    ),
    "Method:llamaindex_runtime/registry/postgres_adapter.py:PostgresRegistryWriter.write_entities#1": (
        "PostgresRegistryWriter.write_entities",
        "split E2a/E2b",
        "0 direct",
        "0 processes",
        "LOW",
    ),
    "Method:llamaindex_runtime/registry/postgres_adapter.py:PostgresRegistryWriter.write_evidence_links#2": (
        "PostgresRegistryWriter.write_evidence_links",
        "split E2a/E2b",
        "0 direct",
        "0 processes",
        "LOW",
    ),
}


class InventoryParser:
    """Parse Phase 15 Caller Inventory Markdown table.

    Robustly parses the execution inventory table directly following the
    nine-column header. Raises ValueError on any malformed row.
    """

    HEADER_PATTERN: ClassVar[re.Pattern] = re.compile(
        r"^\|\s*UID\s*\|.*?\|\s*Enforcement Test Surface\s*\|$", re.MULTILINE
    )
    # Matches a table row: UID and Path/Symbol are backtick-protected;
    # remaining seven cells are not required to be backtick-protected.
    ROW_PATTERN: ClassVar[re.Pattern] = re.compile(
        r"^\|\s*`([^`]+)`\s*\|"
        r"\s*`([^`]+)`\s*\|"
        r"\s*([^|]+?)\s*\|"
        r"\s*([^|]+?)\s*\|"
        r"\s*([^|]+?)\s*\|"
        r"\s*([^|]+?)\s*\|"
        r"\s*([^|]+?)\s*\|"
        r"\s*([^|]+?)\s*\|"
        r"\s*([^|]+?)\s*\|$",
        re.MULTILINE,
    )
    # Separator row pattern
    SEPARATOR_PATTERN: ClassVar[re.Pattern] = re.compile(r"^\|[-|]+\|$", re.MULTILINE)

    def __init__(self, inventory_path: Path) -> None:
        self.inventory_path = inventory_path

    def _extract_table_section(self, content: str) -> str:
        """Extract content from header to next section boundary.

        Returns only the table section (header + separator + data rows)
        immediately following the nine-column header.
        """
        header_match = self.HEADER_PATTERN.search(content)
        if not header_match:
            raise ValueError(
                f"Inventory table header not found in {self.inventory_path}"
            )

        # Find the start of the header
        start = header_match.start()
        # Find the next section boundary (--- or ##) after the header
        boundary_match = re.search(r"\n---|\n##", content[start:])
        if boundary_match:
            return content[start : start + boundary_match.start()]
        return content[start:]

    def _parse_row(self, line: str, line_num: int) -> InventoryRow:
        """Parse a single table row with validation.

        Raises ValueError if the row is malformed.
        """
        match = self.ROW_PATTERN.match(line)
        if not match:
            # Check if it's a separator row (skip silently)
            if self.SEPARATOR_PATTERN.match(line):
                raise ValueError("Separator row should not be parsed as data")
            # Check cell count
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) != 9:
                raise ValueError(
                    f"Row {line_num}: Expected 9 cells, got {len(cells)}: {line!r}"
                )
            # Check backtick protection for UID and Path/Symbol
            if not (cells[0].startswith("`") and cells[0].endswith("`")):
                raise ValueError(
                    f"Row {line_num}: UID must be backtick-protected, got: {cells[0]!r}"
                )
            if not (cells[1].startswith("`") and cells[1].endswith("`")):
                raise ValueError(
                    f"Row {line_num}: Path/Symbol must be backtick-protected, got: {cells[1]!r}"
                )
            # Generic malformed row error
            raise ValueError(f"Row {line_num}: Malformed inventory row: {line!r}")

        return InventoryRow(
            uid=match.group(1).strip(),
            path_symbol=match.group(2).strip(),
            entry_condition=match.group(3).strip(),
            owner=match.group(4).strip(),
            disposition=match.group(5).strip(),
            direct_callers=match.group(6).strip(),
            processes=match.group(7).strip(),
            risk=match.group(8).strip(),
            enforcement_test_surface=match.group(9).strip(),
        )

    def parse(self) -> list[InventoryRow]:
        """Parse Markdown table rows into structured inventory.

        Raises ValueError if any non-separator row in the table is malformed.
        """
        content = self.inventory_path.read_text(encoding="utf-8")
        table_section = self._extract_table_section(content)

        lines = table_section.split("\n")
        rows: list[InventoryRow] = []

        for i, line in enumerate(lines, start=1):
            line = line.strip()
            if not line or not line.startswith("|"):
                continue
            # Skip header row
            if self.HEADER_PATTERN.match(line):
                continue
            # Skip separator row
            if self.SEPARATOR_PATTERN.match(line):
                continue
            # Parse data row
            try:
                row = self._parse_row(line, i)
                rows.append(row)
            except ValueError as e:
                if "Separator row" in str(e):
                    continue
                raise

        if not rows:
            raise ValueError(f"No inventory rows found in {self.inventory_path}")

        return rows


def find_inventory_path() -> Path:
    """Locate inventory document by walking ancestors for canonical path."""
    test_file = Path(__file__).resolve()
    inventory_rel = (
        Path(".planning")
        / "phases"
        / "15-okf-ingestion-pipeline"
        / "15-CALLER-INVENTORY.md"
    )

    for parent in test_file.parents:
        candidate = parent / inventory_rel
        if candidate.is_file():
            return candidate

    raise FileNotFoundError(f"Could not find inventory document at {inventory_rel}")


def get_inventory_rows() -> list[InventoryRow]:
    """Load and parse inventory from Markdown source of truth."""
    inventory_path = find_inventory_path()
    parser = InventoryParser(inventory_path)
    return parser.parse()


class TestPhase15CallerInventoryEnforcement:
    """Enforcement test for Phase 15 Caller Inventory completeness."""

    def test_inventory_has_exact_canonical_uids(self) -> None:
        """Verify inventory contains exactly the canonical UIDs, no more."""
        rows = get_inventory_rows()
        actual_uids = {row.uid for row in rows}

        missing = CANONICAL_UIDS - actual_uids
        assert not missing, f"Missing canonical UIDs: {missing}"

        extra = actual_uids - CANONICAL_UIDS
        assert not extra, f"Unexpected UIDs not in canonical set: {extra}"

    def test_inventory_uids_unique(self) -> None:
        """Verify all UIDs are unique."""
        rows = get_inventory_rows()
        uids = [row.uid for row in rows]
        assert len(uids) == len(set(uids)), "Duplicate UIDs found in inventory"

    def test_inventory_has_nonempty_remaining_fields(self) -> None:
        """Verify entry_condition, disposition, enforcement_test_surface are non-empty."""
        rows = get_inventory_rows()
        remaining_fields = [
            "entry_condition",
            "disposition",
            "enforcement_test_surface",
        ]

        for row in rows:
            for field in remaining_fields:
                value = getattr(row, field)
                assert value, f"Row {row.uid} has empty field: {field}"

    def test_canonical_expectations_match(self) -> None:
        """Verify each UID has exact expected path_symbol, owner, callers, processes, risk."""
        rows = get_inventory_rows()
        row_map = {row.uid: row for row in rows}

        for uid, expected in CANONICAL_EXPECTATIONS.items():
            exp_path, exp_owner, exp_callers, exp_processes, exp_risk = expected
            row = row_map.get(uid)

            assert row is not None, f"UID {uid} not found in inventory"
            assert (
                row.path_symbol == exp_path
            ), f"UID {uid}: expected path_symbol {exp_path!r}, got {row.path_symbol!r}"
            assert (
                row.owner == exp_owner
            ), f"UID {uid}: expected owner {exp_owner!r}, got {row.owner!r}"
            assert (
                row.direct_callers == exp_callers
            ), f"UID {uid}: expected direct_callers {exp_callers!r}, got {row.direct_callers!r}"
            assert (
                row.processes == exp_processes
            ), f"UID {uid}: expected processes {exp_processes!r}, got {row.processes!r}"
            assert (
                row.risk == exp_risk
            ), f"UID {uid}: expected risk {exp_risk!r}, got {row.risk!r}"

    def test_critical_symbols_present(self) -> None:
        """Verify CRITICAL risk symbols are present."""
        rows = get_inventory_rows()
        actual_critical = {row.uid for row in rows if row.risk == "CRITICAL"}

        missing = CRITICAL_UIDS - actual_critical
        assert not missing, f"Missing CRITICAL symbols: {missing}"

    def test_high_symbols_present(self) -> None:
        """Verify HIGH risk symbols are present."""
        rows = get_inventory_rows()
        actual_high = {row.uid for row in rows if row.risk == "HIGH"}

        missing = HIGH_UIDS - actual_high
        assert not missing, f"Missing HIGH symbols: {missing}"

    def test_vectorloader_has_unresolved_caveat(self) -> None:
        """Verify VectorLoader.load has required unresolved partial caveats."""
        rows = get_inventory_rows()
        vl_rows = [row for row in rows if row.uid == VECTORLOADER_UID]

        assert len(vl_rows) == 1, "VectorLoader.load must appear exactly once"

        vl = vl_rows[0]
        assert (
            vl.risk == "UNRESOLVED"
        ), f"VectorLoader risk must be UNRESOLVED, got: {vl.risk}"

        # Disposition has markdown bold formatting
        assert (
            "UNRESOLVED/PARTIAL" in vl.disposition
        ), "VectorLoader disposition must contain UNRESOLVED/PARTIAL"
        assert (
            "partial:true" in vl.disposition
        ), "VectorLoader disposition must reference partial:true"
        assert (
            "NOT a verified zero-impact assertion" in vl.disposition
        ), "VectorLoader disposition must state NOT a verified zero-impact assertion"
        assert (
            "Fresh impact analysis mandatory before edit" in vl.disposition
        ), "VectorLoader disposition must mandate fresh impact analysis"

    def test_risk_classifications_valid(self) -> None:
        """Verify all risk classifications are from valid set."""
        rows = get_inventory_rows()

        for row in rows:
            assert (
                row.risk in VALID_RISKS
            ), f"Row {row.uid} has invalid risk: {row.risk}"

    def test_owner_classifications_valid(self) -> None:
        """Verify all owner classifications are from valid set."""
        rows = get_inventory_rows()

        for row in rows:
            assert (
                row.owner in VALID_OWNERS
            ), f"Row {row.uid} has invalid owner: {row.owner}"

    def test_only_vectorloader_unresolved(self) -> None:
        """Verify only VectorLoader has UNRESOLVED risk."""
        rows = get_inventory_rows()
        unresolved = [
            row.uid
            for row in rows
            if row.risk == "UNRESOLVED" and row.uid != VECTORLOADER_UID
        ]

        assert not unresolved, f"Unexpected UNRESOLVED symbols: {unresolved}"

    def test_malformed_row_raises_value_error(self, tmp_path: Path) -> None:
        """Verify malformed rows raise descriptive ValueError."""
        # Test: wrong cell count
        bad_content = """## Execution Inventory

| UID | Path/Symbol | Entry Condition | Owner | Disposition | Direct Callers | Processes | Risk | Enforcement Test Surface |
|-----|-------------|-----------------|-------|-------------|----------------|-----------|------|--------------------------|
| `Method:foo.py:bar#1` | `bar` | cond | owner | disp | callers | proc | risk |
"""
        bad_file = tmp_path / "bad_inventory.md"
        bad_file.write_text(bad_content, encoding="utf-8")

        parser = InventoryParser(bad_file)
        with pytest.raises(ValueError, match="Expected 9 cells"):
            parser.parse()

    def test_missing_backtick_protection_raises_value_error(
        self, tmp_path: Path
    ) -> None:
        """Verify missing backtick protection raises ValueError."""
        # Test: UID missing backticks
        bad_content = """## Execution Inventory

| UID | Path/Symbol | Entry Condition | Owner | Disposition | Direct Callers | Processes | Risk | Enforcement Test Surface |
|-----|-------------|-----------------|-------|-------------|----------------|-----------|------|--------------------------|
| Method:foo.py:bar#1 | `bar` | cond | owner | disp | callers | proc | risk | surface |
"""
        bad_file = tmp_path / "bad_inventory_no_backticks.md"
        bad_file.write_text(bad_content, encoding="utf-8")

        parser = InventoryParser(bad_file)
        with pytest.raises(ValueError, match="UID must be backtick-protected"):
            parser.parse()

    def test_path_symbol_missing_backtick_protection_raises_value_error(
        self, tmp_path: Path
    ) -> None:
        """Verify Path/Symbol missing backtick protection raises ValueError."""
        # Test: UID has backticks but Path/Symbol does not
        bad_content = """## Execution Inventory

| UID | Path/Symbol | Entry Condition | Owner | Disposition | Direct Callers | Processes | Risk | Enforcement Test Surface |
|-----|-------------|-----------------|-------|-------------|----------------|-----------|------|--------------------------|
| `Method:foo.py:bar#1` | bar | cond | owner | disp | callers | proc | risk | surface |
"""
        bad_file = tmp_path / "bad_inventory_path_no_backticks.md"
        bad_file.write_text(bad_content, encoding="utf-8")

        parser = InventoryParser(bad_file)
        with pytest.raises(ValueError, match="Path/Symbol must be backtick-protected"):
            parser.parse()
