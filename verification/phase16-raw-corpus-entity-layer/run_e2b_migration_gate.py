"""Phase 16-14 Task 1 E2b migration gate runner.

Authorization-first, disposable-only migration gate. Refuses all work unless the
exact three routing environment switches authorize it, and only ever accepts a
programmatic keyword-only target_uri. Evidence is deterministic, redacted, and
written last on complete success. No live database, connection, or model access
is performed here; production work is delegated to the shared disposable
connection helpers and the immutable migration catalog.
"""

import hashlib
import json
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import psycopg

from llamaindex_runtime.okf.e2a_disposable_execution import _apply_catalog
from llamaindex_runtime.registry.migration_catalog import FULL_MIGRATION_CATALOG
from scripts._rebuild_database_connection import (
    parse_disposable_postgresql_target,
    runtime_connection_factory,
)

VERIFICATION_DIR = Path(__file__).resolve().parent
EVIDENCE_NAME = "e2b_migration_gate_evidence.md"
EVIDENCE_PATH = VERIFICATION_DIR / EVIDENCE_NAME

AUTH_ENV = "OKF_E2B_MIGRATION_TEST_AUTHORIZED"
DISPOSABLE_ENV = "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE"
EXPECTED_DATABASE_ENV = "OKF_REBUILD_EXPECTED_DATABASE"
GATE_ROUTING_KEYS = frozenset((AUTH_ENV, DISPOSABLE_ENV, EXPECTED_DATABASE_ENV))

BLOCKED_STATUS = "blocked_not_executed"
EXECUTED_STATUS = "executed"
CLI_FAILURE_MESSAGE = "E2b migration gate refused; failure details are not disclosed"
CONNECT_FAILURE_MESSAGE = "Database connection failed; refusing migration gate"

# Migration 020 structural contract, pinned from 020_ner_entity_mentions.sql.
_PROVENANCE_COLUMNS = (
    "input_id",
    "input_kind",
    "input_revision",
    "extractor_id",
    "extractor_version",
    "model_id",
    "model_revision",
    "artifact_digest",
    "schema_version",
    "normalization_version",
    "segmentation_version",
    "label_map_digest",
    "runtime_compatibility_id",
    "document_char_start",
    "document_char_end",
    "segment_id",
    "raw_label",
    "entity_type",
    "confidence_kind",
    "e2b_owner_scope",
)
_E2B_CONSTRAINTS = (
    "chk_okf_e2b_mentions_input_kind",
    "chk_okf_e2b_mentions_confidence_kind",
    "chk_okf_e2b_mentions_artifact_digest",
    "chk_okf_e2b_mentions_label_map_digest",
    "chk_okf_e2b_mentions_document_coordinates",
    "chk_okf_e2b_mentions_owner_scope",
)
_E2B_INDEXES = (
    "idx_okf_e2b_failure_audit_occurred_at",
    "idx_okf_e2b_failure_audit_scope",
    "idx_okf_e2b_node_link_ownership_node",
    "idx_okf_e2b_node_link_ownership_version",
)
_E2B_FUNCTIONS = (
    "prevent_okf_e2b_failure_audit_mutation",
    "validate_okf_e2b_node_link_ownership_version",
)
_E2B_TRIGGERS = (
    "trg_okf_e2b_failure_audit_append_only",
    "trg_okf_e2b_failure_audit_no_truncate",
    "trg_okf_e2b_node_link_ownership_version",
)
_OWNERSHIP_UNIQUE = "uq_okf_e2b_node_link_ownership"
# The ordered UNIQUE key of uq_okf_e2b_node_link_ownership is
# (node_id, entity_id, version_id); the ledger also indexes node/entity and version.
_OWNERSHIP_UNIQUE_COLUMNS = ("node_id", "entity_id", "version_id")
_E2B_TABLES = ("okf_e2b_failure_audit", "okf_e2b_node_link_ownership")
_CATALOG_TAIL = ("021_ner_coref_clusters.sql", "022_keyword_fts_indexes.sql")

_INVENTORY_KEYS = frozenset(
    (
        "provenance_columns",
        "constraints",
        "indexes",
        "ownership_ledger_unique",
        "ownership_ledger_unique_columns",
        "tables",
    )
)
_PAYLOAD_KEYS = frozenset(
    (
        "schema_version",
        "status",
        "catalog_tail",
        "catalog_apply_count",
        "idempotence_reapply_count",
        "idempotence_ddl_count",
        "provenance_column_count",
        "constraint_inventory",
        "index_inventory",
        "ownership_ledger_unique",
        "ownership_ledger_unique_columns",
        "tables",
    )
)

_MIGRATIONS_ROOT = (
    Path(__file__).resolve().parents[2]
    / "llamaindex_runtime"
    / "registry"
    / "migrations"
)
_MIGRATION_020_PATH = _MIGRATIONS_ROOT / "020_ner_entity_mentions.sql"


@dataclass(frozen=True)
class GateOutcome:
    """Exact frozen seven-field outcome of one migration gate run."""

    status: str
    catalog_tail: tuple[str, ...]
    catalog_apply_count: int
    idempotence_reapply_count: int
    idempotence_ddl_count: int
    inventory: dict[str, object]
    evidence_sha256: str


def _blocked_outcome() -> GateOutcome:
    """Authorized-nowhere outcome: no touch, no evidence, no detail."""
    return GateOutcome(BLOCKED_STATUS, (), 0, 0, 0, {}, "")


def _require_gate_authorization(environ: Mapping[str, str]) -> None:
    """Read only the three routing keys and require their exact values."""
    disposable = environ.get(DISPOSABLE_ENV)
    authorized = environ.get(AUTH_ENV)
    expected_database = environ.get(EXPECTED_DATABASE_ENV)
    if disposable != "1":
        raise ValueError(f"{DISPOSABLE_ENV}=1")
    if authorized != "1":
        raise ValueError(f"{AUTH_ENV}=1")
    if not expected_database:
        raise ValueError(EXPECTED_DATABASE_ENV)


def _verify_catalog_tail(catalog: tuple[str, ...]) -> None:
    """Require the 001 head and 021 immediately before the single 022 tail."""
    if (
        catalog[0] != "001_initial.sql"
        or catalog[-2:] != _CATALOG_TAIL
        or catalog.count(_CATALOG_TAIL[1]) != 1
    ):
        raise ValueError("invalid migration catalog tail")


def _validate_020_inventory(inventory: dict[str, object]) -> None:
    """Reject any deviation from the exact migration-020 structural contract."""
    unknown = set(inventory) - _INVENTORY_KEYS
    if unknown:
        raise ValueError("unknown inventory field")
    if tuple(inventory.get("provenance_columns", ())) != _PROVENANCE_COLUMNS:
        raise ValueError("invalid 020 provenance columns")
    if tuple(inventory.get("constraints", ())) != _E2B_CONSTRAINTS:
        raise ValueError("invalid 020 constraints")
    if tuple(inventory.get("indexes", ())) != _E2B_INDEXES:
        raise ValueError("invalid 020 indexes")
    if inventory.get("ownership_ledger_unique") != _OWNERSHIP_UNIQUE:
        raise ValueError("invalid 020 ownership unique")
    if (
        tuple(inventory.get("ownership_ledger_unique_columns", ()))
        != _OWNERSHIP_UNIQUE_COLUMNS
    ):
        raise ValueError("invalid 020 ownership unique columns")
    if tuple(inventory.get("tables", ())) != _E2B_TABLES:
        raise ValueError("invalid 020 tables")


def _canonical_evidence_payload(status: str) -> dict[str, object]:
    """Deterministic redacted payload built only from immutable constants."""
    return {
        "schema_version": 1,
        "status": status,
        "catalog_tail": _CATALOG_TAIL,
        "catalog_apply_count": 1,
        "idempotence_reapply_count": 1,
        "idempotence_ddl_count": 0,
        "provenance_column_count": len(_PROVENANCE_COLUMNS),
        "constraint_inventory": _E2B_CONSTRAINTS,
        "index_inventory": _E2B_INDEXES,
        "ownership_ledger_unique": _OWNERSHIP_UNIQUE,
        "ownership_ledger_unique_columns": _OWNERSHIP_UNIQUE_COLUMNS,
        "tables": _E2B_TABLES,
    }


def _redact_evidence_payload(payload: dict[str, object]) -> dict[str, object]:
    """Refuse any unknown evidence field before anything is written."""
    unknown = set(payload) - _PAYLOAD_KEYS
    if unknown:
        raise ValueError("unknown evidence payload field")
    return dict(payload)


def _write_evidence(payload: dict[str, object], path: Path) -> str:
    """Write the canonical JSON payload and return its sha256 hexdigest."""
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _inventory_020(connection: object) -> dict[str, object]:
    """Read the exact migration-020 structural inventory from the live schema."""
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT attname
        FROM pg_attribute
        WHERE attrelid = 'entity_mentions'::regclass
          AND attnum > 0
          AND NOT attisdropped
          AND attname = ANY(%s)
        ORDER BY array_position(%s::name[], attname)
        """,
        (list(_PROVENANCE_COLUMNS), list(_PROVENANCE_COLUMNS)),
    )
    provenance_columns = tuple(row[0] for row in cursor.fetchall())
    cursor.execute(
        """
        SELECT conname
        FROM pg_constraint
        WHERE conrelid = 'entity_mentions'::regclass
          AND conname = ANY(%s)
        ORDER BY array_position(%s::name[], conname)
        """,
        (list(_E2B_CONSTRAINTS), list(_E2B_CONSTRAINTS)),
    )
    constraints = tuple(row[0] for row in cursor.fetchall())
    cursor.execute(
        """
        SELECT index_class.relname
        FROM pg_index AS index_row
        JOIN pg_class AS index_class ON index_class.oid = index_row.indexrelid
        WHERE index_row.indrelid IN (
            SELECT class_row.oid
            FROM pg_class AS class_row
            WHERE class_row.relnamespace = (
                SELECT namespace_row.oid
                FROM pg_namespace AS namespace_row
                WHERE namespace_row.nspname = current_schema()
            )
        )
          AND index_class.relname = ANY(%s)
        ORDER BY array_position(%s::name[], index_class.relname)
        """,
        (list(_E2B_INDEXES), list(_E2B_INDEXES)),
    )
    indexes = tuple(row[0] for row in cursor.fetchall())
    cursor.execute(
        """
        SELECT constraint_row.conname
        FROM pg_constraint AS constraint_row
        WHERE constraint_row.conname = %s
          AND constraint_row.contype = 'u'
          AND constraint_row.conrelid = 'okf_e2b_node_link_ownership'::regclass
          AND constraint_row.connamespace = (
              SELECT namespace_row.oid
              FROM pg_namespace AS namespace_row
              WHERE namespace_row.nspname = current_schema()
          )
        """,
        (_OWNERSHIP_UNIQUE,),
    )
    ownership_row = cursor.fetchone()
    ownership_ledger_unique = ownership_row[0] if ownership_row is not None else None
    cursor.execute(
        """
        SELECT attribute_row.attname
        FROM pg_attribute AS attribute_row
        JOIN (
            SELECT constraint_row.conrelid AS conrelid,
                   key_column.attnum AS attnum,
                   key_column.ordinality AS ordinality
            FROM pg_constraint AS constraint_row
            CROSS JOIN LATERAL UNNEST(constraint_row.conkey)
                WITH ORDINALITY AS key_column(attnum, ordinality)
            WHERE constraint_row.conname = %s
              AND constraint_row.contype = 'u'
              AND constraint_row.conrelid = 'okf_e2b_node_link_ownership'::regclass
              AND constraint_row.connamespace = (
                  SELECT namespace_row.oid
                  FROM pg_namespace AS namespace_row
                  WHERE namespace_row.nspname = current_schema()
              )
        ) AS key_columns
          ON key_columns.conrelid = attribute_row.attrelid
         AND key_columns.attnum = attribute_row.attnum
        WHERE attribute_row.attnum > 0
          AND NOT attribute_row.attisdropped
        ORDER BY key_columns.ordinality
        """,
        (_OWNERSHIP_UNIQUE,),
    )
    ownership_ledger_unique_columns = tuple(row[0] for row in cursor.fetchall())
    cursor.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = current_schema()
          AND table_name = ANY(%s)
        ORDER BY array_position(%s::name[], table_name)
        """,
        (list(_E2B_TABLES), list(_E2B_TABLES)),
    )
    tables = tuple(row[0] for row in cursor.fetchall())
    return {
        "provenance_columns": provenance_columns,
        "constraints": constraints,
        "indexes": indexes,
        "ownership_ledger_unique": ownership_ledger_unique,
        "ownership_ledger_unique_columns": ownership_ledger_unique_columns,
        "tables": tables,
    }


def _snapshot_020(connection: object) -> dict[str, object]:
    """Canonical deterministic structural snapshot of migration-020 objects.

    Covers the migration-020 relevant columns, constraints, indexes, tables,
    functions, and triggers with explicit stable ordering, so equal snapshots
    prove effective structural idempotence of a migration-020 reapply.
    """
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT md5(string_agg(entry, E'\\n' ORDER BY entry))
        FROM (
            SELECT 'column|' || table_row.relname || '.' || attribute_row.attname
                   || '|' || pg_catalog.format_type(
                       attribute_row.atttypid, attribute_row.atttypmod
                   ) AS entry
            FROM pg_attribute AS attribute_row
            JOIN pg_class AS table_row ON table_row.oid = attribute_row.attrelid
            WHERE table_row.relnamespace = (
                    SELECT namespace_row.oid
                    FROM pg_namespace AS namespace_row
                    WHERE namespace_row.nspname = current_schema()
                )
              AND (
                    (table_row.relname = 'entity_mentions'
                     AND attribute_row.attname = ANY(%s))
                    OR table_row.relname = ANY(%s)
                  )
              AND attribute_row.attnum > 0
              AND NOT attribute_row.attisdropped
            UNION ALL
            SELECT 'constraint|' || constraint_row.conname || '|'
                   || pg_catalog.pg_get_constraintdef(constraint_row.oid) AS entry
            FROM pg_constraint AS constraint_row
            WHERE constraint_row.conrelid IN (
                    SELECT class_row.oid
                    FROM pg_class AS class_row
                    WHERE class_row.relnamespace = (
                            SELECT namespace_row.oid
                            FROM pg_namespace AS namespace_row
                            WHERE namespace_row.nspname = current_schema()
                        )
                      AND class_row.relname = ANY(%s)
                )
               OR (
                    constraint_row.conrelid = 'entity_mentions'::regclass
                    AND constraint_row.conname = ANY(%s)
                  )
            UNION ALL
            SELECT 'index|' || index_class.relname || '|'
                   || pg_catalog.pg_get_indexdef(index_row.indexrelid) AS entry
            FROM pg_index AS index_row
            JOIN pg_class AS index_class ON index_class.oid = index_row.indexrelid
            WHERE index_row.indrelid IN (
                    SELECT class_row.oid
                    FROM pg_class AS class_row
                    WHERE class_row.relnamespace = (
                            SELECT namespace_row.oid
                            FROM pg_namespace AS namespace_row
                            WHERE namespace_row.nspname = current_schema()
                        )
                )
              AND index_class.relname = ANY(%s)
            UNION ALL
            SELECT 'table|' || class_row.relname AS entry
            FROM pg_class AS class_row
            WHERE class_row.relnamespace = (
                    SELECT namespace_row.oid
                    FROM pg_namespace AS namespace_row
                    WHERE namespace_row.nspname = current_schema()
                )
              AND class_row.relkind = 'r'
              AND class_row.relname = ANY(%s)
            UNION ALL
            SELECT 'function|' || procedure_row.proname || '|'
                   || pg_catalog.pg_get_functiondef(procedure_row.oid) AS entry
            FROM pg_proc AS procedure_row
            WHERE procedure_row.pronamespace = (
                    SELECT namespace_row.oid
                    FROM pg_namespace AS namespace_row
                    WHERE namespace_row.nspname = current_schema()
                )
              AND procedure_row.proname = ANY(%s)
            UNION ALL
            SELECT 'trigger|' || trigger_row.tgname || '|'
                   || pg_catalog.pg_get_triggerdef(trigger_row.oid) AS entry
            FROM pg_trigger AS trigger_row
            WHERE trigger_row.tgrelid IN (
                    SELECT class_row.oid
                    FROM pg_class AS class_row
                    WHERE class_row.relnamespace = (
                            SELECT namespace_row.oid
                            FROM pg_namespace AS namespace_row
                            WHERE namespace_row.nspname = current_schema()
                        )
                )
              AND trigger_row.tgname = ANY(%s)
              AND NOT trigger_row.tgisinternal
        ) AS snapshot_rows
        """,
        (
            list(_PROVENANCE_COLUMNS),
            list(_E2B_TABLES),
            list(_E2B_TABLES),
            list(_E2B_CONSTRAINTS),
            list(_E2B_INDEXES),
            list(_E2B_TABLES),
            list(_E2B_FUNCTIONS),
            list(_E2B_TRIGGERS),
        ),
    )
    row = cursor.fetchone()
    fingerprint = row[0] if row is not None else None
    return {"objects": (fingerprint,)}


def _reapply_020(connection: object) -> None:
    """Re-execute migration 020; additive and idempotent by contract."""
    cursor = connection.cursor()
    cursor.execute(_MIGRATION_020_PATH.read_text(encoding="utf-8"))
    connection.commit()


def run_migration_gate(
    environ: Mapping[str, str],
    *,
    target_uri=None,
    target_parser=parse_disposable_postgresql_target,
    connection_factory=runtime_connection_factory,
    catalog=FULL_MIGRATION_CATALOG,
    apply_catalog=_apply_catalog,
    inventory_schema=_inventory_020,
    snapshot_schema=_snapshot_020,
    reapply_020=_reapply_020,
    evidence_writer=_write_evidence,
    evidence_path=EVIDENCE_PATH,
) -> GateOutcome:
    """Run the gate: authorize, verify catalog, apply, verify idempotence, evidence."""
    try:
        _require_gate_authorization(environ)
    except ValueError:
        return _blocked_outcome()
    if target_uri is None:
        raise ValueError("programmatic target_uri is required")
    _verify_catalog_tail(catalog)
    expected_database = environ.get(EXPECTED_DATABASE_ENV)
    target = target_parser(target_uri, expected_database)
    apply_catalog(target, connection_factory, catalog)
    connection = connection_factory(target)
    try:
        inventory = inventory_schema(connection)
        _validate_020_inventory(inventory)
        before = snapshot_schema(connection)
        reapply_020(connection)
        after = snapshot_schema(connection)
        if before != after:
            raise ValueError("idempotence snapshot mismatch after 020 reapply")
    finally:
        if not connection.closed:
            connection.close()
    payload = _canonical_evidence_payload(EXECUTED_STATUS)
    redacted = _redact_evidence_payload(payload)
    evidence_sha256 = evidence_writer(redacted, evidence_path)
    return GateOutcome(
        EXECUTED_STATUS,
        _CATALOG_TAIL,
        1,
        1,
        0,
        inventory,
        evidence_sha256,
    )


def main(argv: list[str] | None = None, *, target_uri: object = None) -> int:
    """Authorization-first entry point; the target_uri is keyword-only."""
    environ = os.environ
    try:
        _require_gate_authorization(environ)
    except ValueError:
        print(BLOCKED_STATUS)
        return 1
    if argv:
        raise ValueError("argv credential route is forbidden")
    if target_uri is None:
        raise ValueError("programmatic target_uri is required")
    outcome = run_migration_gate(environ, target_uri=target_uri)
    print(outcome.status)
    return 0


def _run_redacted_cli(argv: list[str] | None = None) -> int:
    """CLI wrapper with fixed redacted failure messages and blocked status."""
    if argv is None:
        argv = sys.argv[1:]
    try:
        code = main(argv)
    except ValueError:
        print(CLI_FAILURE_MESSAGE, file=sys.stderr)
        return 2
    except psycopg.Error:
        print(CONNECT_FAILURE_MESSAGE, file=sys.stderr)
        return 2
    return code


if __name__ == "__main__":
    raise SystemExit(_run_redacted_cli())
