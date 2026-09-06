"""Disposable connection execution helpers for migration acceptance."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path, PurePath
from typing import Any, Protocol

from llamaindex_runtime.registry.migration_catalog import FULL_MIGRATION_CATALOG
from scripts._rebuild_database_connection import DisposablePostgresqlTarget


class _Connection(Protocol):
    def cursor(self) -> Any: ...

    def commit(self) -> Any: ...

    def rollback(self) -> Any: ...

    def close(self) -> Any: ...


class _ApplyRollbackFailure(Exception):
    pass


class _ProbeRollbackFailure(Exception):
    pass


def _validate_catalog_filenames(filenames: Iterable[str]) -> tuple[str, ...]:
    """Materialize and validate the selected migration names before any I/O."""
    try:
        selected = filenames if type(filenames) is tuple else tuple(filenames)
    except Exception as error:
        raise ValueError("executed_failed") from error
    for filename in selected:
        if (
            type(filename) is not str
            or filename not in FULL_MIGRATION_CATALOG
            or "/" in filename
            or "\\" in filename
            or PurePath(filename).is_absolute()
        ):
            raise ValueError("executed_failed")
    return selected


def _attest_connection_target(cursor: Any, target: DisposablePostgresqlTarget) -> None:
    """Fail closed unless a newly opened connection is in the parsed public target."""
    try:
        cursor.execute("SELECT current_database(), current_schema()")
        identity = cursor.fetchone()
    except Exception as error:
        raise ValueError("executed_failed") from error
    if type(identity) is not tuple or identity != (target.dbname, "public"):
        raise ValueError("executed_failed")


def _apply_catalog(
    target: DisposablePostgresqlTarget,
    connection_factory: Callable[[DisposablePostgresqlTarget], _Connection],
    filenames: Iterable[str] = FULL_MIGRATION_CATALOG,
    *,
    attest_connection_target: (
        Callable[[Any, DisposablePostgresqlTarget], None] | None
    ) = None,
    close: Callable[[_Connection], None] | None = None,
) -> None:
    """Apply migrations, retaining optional seams for the legacy facade."""
    selected_filenames = _validate_catalog_filenames(filenames)
    connection: _Connection | None = None
    primary_failure: Exception | None = None
    attester = (
        _attest_connection_target
        if attest_connection_target is None
        else attest_connection_target
    )
    close_connection = _close if close is None else close
    try:
        connection = connection_factory(target)
        cursor = connection.cursor()
        attester(cursor, target)
        root = Path(__file__).resolve().parents[1] / "registry" / "migrations"
        for filename in selected_filenames:
            cursor.execute((root / filename).read_text(encoding="utf-8"))
            connection.commit()
    except Exception as error:
        primary_failure = error
        if connection is not None:
            try:
                connection.rollback()
            except Exception as rollback_error:
                primary_failure = _ApplyRollbackFailure()
                raise primary_failure from rollback_error
        raise
    finally:
        if connection is not None:
            try:
                close_connection(connection)
            except Exception:
                if primary_failure is None:
                    raise


def _close(connection: _Connection) -> None:
    try:
        connection.close()
    except Exception as error:
        raise ValueError("executed_failed") from error


def _run_rollback_only_probe(
    connection: _Connection,
    cursor: Any,
    *,
    semantic_probe: str | None = None,
) -> None:
    """Run the probe in its own transaction and roll it back exactly once."""
    probe = _SEMANTIC_PROBE if semantic_probe is None else semantic_probe
    failure: Exception | None = None
    try:
        cursor.execute("BEGIN")
        cursor.execute(probe)
    except Exception as error:
        failure = error
    try:
        connection.rollback()
    except Exception as error:
        raise _ProbeRollbackFailure from error
    if failure is not None:
        raise ValueError("executed_failed") from None


_SEMANTIC_PROBE = """
DO $$
BEGIN
    -- Rollback-only setup: versions, spans, generic evidence, manual target, owners.
    INSERT INTO documents (doc_id, source_uri, title, doc_type)
    VALUES ('00000000-0000-0000-0000-000000000101', 'acceptance', 'acceptance', 'test');
    INSERT INTO document_versions (version_id, doc_id, content_hash, version_no) VALUES
      ('00000000-0000-0000-0000-000000000102','00000000-0000-0000-0000-000000000101','one',1),
      ('00000000-0000-0000-0000-000000000103','00000000-0000-0000-0000-000000000101','two',2);
    INSERT INTO entities (entity_id, entity_key) VALUES
      ('00000000-0000-0000-0000-000000000104','one'),
      ('00000000-0000-0000-0000-000000000105','two');
    INSERT INTO relations (relation_id, relation_key, relation_type, source_entity_id, target_entity_id)
    VALUES ('00000000-0000-0000-0000-000000000106','one','test',
            '00000000-0000-0000-0000-000000000104','00000000-0000-0000-0000-000000000105');
    INSERT INTO canonical_spans (span_id, version_id, span_kind, start_offset, end_offset) VALUES
      ('00000000-0000-0000-0000-000000000107','00000000-0000-0000-0000-000000000102','test',0,1),
      ('00000000-0000-0000-0000-000000000108','00000000-0000-0000-0000-000000000103','test',0,1);
    INSERT INTO evidence (evidence_id, version_id) VALUES
      ('00000000-0000-0000-0000-000000000109','00000000-0000-0000-0000-000000000102'),
      ('00000000-0000-0000-0000-000000000110','00000000-0000-0000-0000-000000000103');

    -- Legal generic links: one evidence object may cover two different targets
    -- and needs no manual target mapping.
    INSERT INTO evidence_links (evidence_link_id, version_id, entity_id, span_id, source_kind, evidence_id) VALUES
      ('00000000-0000-0000-0000-000000000111','00000000-0000-0000-0000-000000000102','00000000-0000-0000-0000-000000000104','00000000-0000-0000-0000-000000000107','legacy','00000000-0000-0000-0000-000000000109'),
      ('00000000-0000-0000-0000-000000000112','00000000-0000-0000-0000-000000000102','00000000-0000-0000-0000-000000000105','00000000-0000-0000-0000-000000000107','another_generic','00000000-0000-0000-0000-000000000109');
    INSERT INTO okf_manual_evidence_targets (version_id, evidence_id, entity_id)
      VALUES ('00000000-0000-0000-0000-000000000102','00000000-0000-0000-0000-000000000109','00000000-0000-0000-0000-000000000104');
    INSERT INTO okf_manual_fact_ownership
      (ownership_id, okf_relative_path, fact_kind, fact_id, entity_id, source_digest)
      VALUES ('00000000-0000-0000-0000-000000000113','entities/one.md','entity',
              '00000000-0000-0000-0000-000000000104','00000000-0000-0000-0000-000000000104',repeat('a',64));
    INSERT INTO evidence_links
      (evidence_link_id, version_id, entity_id, manual_entity_id, span_id, source_kind,
       evidence_id, ownership_id, ownership_scope_version_id)
      VALUES ('00000000-0000-0000-0000-000000000114','00000000-0000-0000-0000-000000000102',
       '00000000-0000-0000-0000-000000000104','00000000-0000-0000-0000-000000000104',
       '00000000-0000-0000-0000-000000000107','manual_okf','00000000-0000-0000-0000-000000000109',
       '00000000-0000-0000-0000-000000000113','00000000-0000-0000-0000-000000000000');

    -- e2a_probe_legal_manual_relation: the relation branch has its own owner,
    -- version/evidence target, and canonical span-backed manual projection.
    INSERT INTO okf_manual_evidence_targets (version_id, evidence_id, relation_id)
      VALUES ('00000000-0000-0000-0000-000000000103','00000000-0000-0000-0000-000000000110',
              '00000000-0000-0000-0000-000000000106');
    INSERT INTO okf_manual_fact_ownership
      (ownership_id, okf_relative_path, fact_kind, fact_id, relation_id, source_digest)
      VALUES ('00000000-0000-0000-0000-000000000121','relations/one.md','relation',
              '00000000-0000-0000-0000-000000000106','00000000-0000-0000-0000-000000000106',repeat('b',64));
    INSERT INTO evidence_links
      (evidence_link_id, version_id, relation_id, manual_relation_id, span_id, source_kind,
       evidence_id, ownership_id, ownership_scope_version_id)
      VALUES ('00000000-0000-0000-0000-000000000122','00000000-0000-0000-0000-000000000103',
       '00000000-0000-0000-0000-000000000106','00000000-0000-0000-0000-000000000106',
       '00000000-0000-0000-0000-000000000108','manual_okf','00000000-0000-0000-0000-000000000110',
       '00000000-0000-0000-0000-000000000121','00000000-0000-0000-0000-000000000000');

    BEGIN -- e2a_probe_entity_owner_without_entity_target
      INSERT INTO okf_manual_fact_ownership
        (ownership_id, okf_relative_path, fact_kind, fact_id, source_digest)
      VALUES ('00000000-0000-0000-0000-000000000123','entities/missing-target.md','entity',
              '00000000-0000-0000-0000-000000000104',repeat('c',64));
      RAISE EXCEPTION 'e2a_probe_entity_owner_without_entity_target_not_rejected';
    EXCEPTION WHEN check_violation THEN NULL; END;
    BEGIN -- e2a_probe_relation_owner_without_relation_target
      INSERT INTO okf_manual_fact_ownership
        (ownership_id, okf_relative_path, fact_kind, fact_id, source_digest)
      VALUES ('00000000-0000-0000-0000-000000000124','relations/missing-target.md','relation',
              '00000000-0000-0000-0000-000000000106',repeat('d',64));
      RAISE EXCEPTION 'e2a_probe_relation_owner_without_relation_target_not_rejected';
    EXCEPTION WHEN check_violation THEN NULL; END;

    BEGIN -- e2a_probe_missing_manual_evidence_owner_scope
      INSERT INTO evidence_links (evidence_link_id,version_id,entity_id,manual_entity_id,span_id,source_kind)
      VALUES ('00000000-0000-0000-0000-000000000115','00000000-0000-0000-0000-000000000102','00000000-0000-0000-0000-000000000104','00000000-0000-0000-0000-000000000104','00000000-0000-0000-0000-000000000107','manual_okf');
      RAISE EXCEPTION 'e2a_probe_missing_manual_evidence_owner_scope_not_rejected';
    EXCEPTION WHEN check_violation THEN NULL; END;
    BEGIN -- e2a_probe_wrong_shadow_projection
      INSERT INTO evidence_links (evidence_link_id,version_id,entity_id,manual_entity_id,span_id,source_kind,evidence_id,ownership_id,ownership_scope_version_id)
      VALUES ('00000000-0000-0000-0000-000000000116','00000000-0000-0000-0000-000000000102','00000000-0000-0000-0000-000000000104','00000000-0000-0000-0000-000000000105','00000000-0000-0000-0000-000000000107','manual_okf','00000000-0000-0000-0000-000000000109','00000000-0000-0000-0000-000000000113','00000000-0000-0000-0000-000000000000');
      RAISE EXCEPTION 'e2a_probe_wrong_shadow_projection_not_rejected';
    EXCEPTION WHEN check_violation THEN NULL; END;
    BEGIN -- e2a_probe_wrong_owner_target
      INSERT INTO evidence_links (evidence_link_id,version_id,relation_id,manual_relation_id,span_id,source_kind,evidence_id,ownership_id,ownership_scope_version_id)
      VALUES ('00000000-0000-0000-0000-000000000117','00000000-0000-0000-0000-000000000102','00000000-0000-0000-0000-000000000106','00000000-0000-0000-0000-000000000106','00000000-0000-0000-0000-000000000107','manual_okf','00000000-0000-0000-0000-000000000109','00000000-0000-0000-0000-000000000113','00000000-0000-0000-0000-000000000000');
      RAISE EXCEPTION 'e2a_probe_wrong_owner_target_not_rejected';
    EXCEPTION WHEN foreign_key_violation THEN NULL; END;
    BEGIN -- e2a_probe_wrong_target_mapping
      INSERT INTO evidence_links (evidence_link_id,version_id,entity_id,manual_entity_id,span_id,source_kind,evidence_id,ownership_id,ownership_scope_version_id)
      VALUES ('00000000-0000-0000-0000-000000000118','00000000-0000-0000-0000-000000000102','00000000-0000-0000-0000-000000000105','00000000-0000-0000-0000-000000000105','00000000-0000-0000-0000-000000000107','manual_okf','00000000-0000-0000-0000-000000000109','00000000-0000-0000-0000-000000000113','00000000-0000-0000-0000-000000000000');
      RAISE EXCEPTION 'e2a_probe_wrong_target_mapping_not_rejected';
    EXCEPTION WHEN foreign_key_violation THEN NULL; END;
    BEGIN -- e2a_probe_cross_version_span_evidence
      INSERT INTO evidence_links (evidence_link_id,version_id,entity_id,span_id,source_kind,evidence_id)
      VALUES ('00000000-0000-0000-0000-000000000119','00000000-0000-0000-0000-000000000102','00000000-0000-0000-0000-000000000104','00000000-0000-0000-0000-000000000108','legacy','00000000-0000-0000-0000-000000000110');
      RAISE EXCEPTION 'e2a_probe_cross_version_span_evidence_not_rejected';
    EXCEPTION WHEN foreign_key_violation THEN NULL; END;
    BEGIN -- e2a_probe_invalid_global_scoped_scope
      INSERT INTO evidence_links (evidence_link_id,version_id,entity_id,manual_entity_id,span_id,source_kind,evidence_id,ownership_id,ownership_scope_version_id)
      VALUES ('00000000-0000-0000-0000-000000000120','00000000-0000-0000-0000-000000000102','00000000-0000-0000-0000-000000000104','00000000-0000-0000-0000-000000000104','00000000-0000-0000-0000-000000000107','manual_okf','00000000-0000-0000-0000-000000000109','00000000-0000-0000-0000-000000000113','00000000-0000-0000-0000-000000000102');
      RAISE EXCEPTION 'e2a_probe_invalid_global_scoped_scope_not_rejected';
    EXCEPTION WHEN foreign_key_violation THEN NULL; END;
    BEGIN -- e2a_probe_restrict_delete
      DELETE FROM entities WHERE entity_id = '00000000-0000-0000-0000-000000000104';
      RAISE EXCEPTION 'e2a_probe_restrict_delete_not_rejected';
    EXCEPTION WHEN foreign_key_violation THEN NULL; END;
END $$;
"""
