"""Private shared helpers for disposable OKF rebuild integration coverage."""

import json
import os
import shutil
import socket
import subprocess
import sys
from collections import namedtuple
from collections.abc import Iterator, Sequence
from pathlib import Path
from time import sleep
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest

from llamaindex_runtime.okf.parser import OKFDocument, OKFParser
from llamaindex_runtime.okf.roundtrip import recompute_span_dicts
from llamaindex_runtime.okf.serializer import serialize_document

from ._rebuild_cli_testkit import _DATABASE_ENVIRONMENT_KEYS, _disposable_connection

# fmt: off
REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "rebuild_from_okf.py"
FIXTURE_ROOT = Path(__file__).parents[2] / "fixtures" / "okf_roundtrip"
MIGRATIONS = REPO_ROOT / "llamaindex_runtime" / "registry" / "migrations"
MIGRATION_NAMES = ("001_initial.sql", "002_version_lifecycle.sql", "003_tree_persistence.sql", "005_kg_extension.sql", "007_processing_status.sql", "008_evidence_object.sql", "011_evidence_dedup_key.sql", "015_okf_sync_state.sql", "016_entity_mentions.sql", "017_relation_qualifiers.sql", "018_okf_rebuild_failure_audit.sql")
_ReconciliationScenario = namedtuple("_ReconciliationScenario", "bundle target_version_id unrelated_version_id expected")
_ReconciliationSeed = namedtuple("_ReconciliationSeed", "retained_id corrupt_id removed_id unrelated_span retained_parents corrupt_parents removed_parents unrelated_parents unrelated_snapshot")
_CollisionScenario = namedtuple("_CollisionScenario", "bundle earlier_document_id earlier_version_id colliding_document_id colliding_version_id owner_document_id owner_version_id colliding_span_id")
_CollisionSnapshots = namedtuple("_CollisionSnapshots", "earlier colliding owner")
_MissingScopeScenario = namedtuple("_MissingScopeScenario", "bundle registered_document_id registered_version_id expected")
_MissingScopeSeed = namedtuple("_MissingScopeSeed", "retained_id corrupt_id removed_id retained_parents corrupt_parents removed_parents canonical_before bridge_before parent_before")
# fmt: on


class _RedactedDatabaseUrl(str):
    """Prevent accidental display of the disposable database credentials."""

    def __repr__(self) -> str:
        return "'<redacted disposable PostgreSQL URL>'"


def _sanitized_environment() -> dict[str, str]:
    """Build a child environment without inherited database routing."""
    return {
        key: value
        for key, value in os.environ.items()
        if key not in _DATABASE_ENVIRONMENT_KEYS
    }


def _free_localhost_port() -> int:
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            port = int(probe.getsockname()[1])
        if port != 5432:
            return port


def _run_docker(
    command: Sequence[str], environment: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *command],
        capture_output=True,
        check=False,
        text=True,
        env=environment,
    )


def _start_disposable_container(container_name: str, port: int, password: str) -> None:
    run_result = _run_docker(
        [
            "run",
            "--detach",
            "--name",
            container_name,
            "--label",
            "okf.task=34",
            "--publish",
            f"127.0.0.1:{port}:5432",
            "--env",
            "POSTGRES_DB=okf_task34",
            "--env",
            "POSTGRES_USER=okf",
            "--env",
            "POSTGRES_PASSWORD",
            "pgvector/pgvector:pg16",
        ],
        _sanitized_environment() | {"POSTGRES_PASSWORD": password},
    )
    if run_result.returncode != 0:
        pytest.fail("Unable to start the disposable PostgreSQL container")


def _wait_for_disposable_database(database_url: _RedactedDatabaseUrl) -> None:
    for _ in range(30):
        try:
            with _disposable_connection(database_url, connect_timeout=1):
                return
        except psycopg.OperationalError:
            sleep(1)
    pytest.fail("Disposable PostgreSQL container did not become ready")


def _remove_labeled_disposable_container(container_name: str) -> None:
    inspect_result = _run_docker(
        [
            "inspect",
            "--format",
            '{{ index .Config.Labels "okf.task" }}',
            container_name,
        ],
        _sanitized_environment(),
    )
    if inspect_result.returncode != 0 or inspect_result.stdout.strip() != "34":
        pytest.fail("Refusing to remove a container without the expected task label")
    remove_result = _run_docker(
        ["rm", "--force", container_name], _sanitized_environment()
    )
    if remove_result.returncode != 0:
        pytest.fail("Unable to remove the disposable PostgreSQL container")


def _apply_schema(database_url: str) -> None:
    with _disposable_connection(database_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute("DROP SCHEMA public CASCADE")
            cursor.execute("CREATE SCHEMA public")
            for name in MIGRATION_NAMES:
                cursor.execute((MIGRATIONS / name).read_text(encoding="utf-8"))


def _fixture_nodes() -> list[dict[str, Any]]:
    return json.loads(
        (FIXTURE_ROOT / "sectioned-pdf" / "docling_output.json").read_text(
            encoding="utf-8"
        )
    )


def _provision_bundle_root(bundle_root: Path) -> None:
    bundle_root.mkdir(parents=True, exist_ok=False)


def _write_raw_document(
    bundle_root: Path,
    *,
    name: str,
    doc_id: str,
    version_id: str,
    changed: bool,
) -> None:
    nodes = _fixture_nodes()
    if changed:
        nodes[0]["text"] = f"{nodes[0]['text']} Rebuilt."
    serialize_document(
        nodes,
        doc_id=doc_id,
        version_id=version_id,
        source_checksum="0" * 64,
        docling_version="2.109.0",
        bundle_root=bundle_root,
        name=name,
    )


def _expected_rows(document: OKFDocument) -> list[tuple[object, ...]]:
    doc_id = document.frontmatter.doc_id or ""
    version_id = document.frontmatter.version_id or ""
    recomputed = recompute_span_dicts(
        document.spans, doc_id=doc_id, version_id=version_id
    )
    return sorted(
        [
            (
                span["span_id"],
                span["offset"],
                span["offset"] + len(span["text"]),
                span["page_no"],
                " > ".join(span["heading_path"]) if span["heading_path"] else None,
                span["text"],
            )
            for span in recomputed
        ],
        key=lambda row: (row[1], row[0]),
    )


def _canonical_rows(
    connection: psycopg.Connection[Any], version_id: UUID
) -> list[tuple[object, ...]]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT span_id::text, start_offset, end_offset, page_no, heading_path, raw_text "
            "FROM canonical_spans WHERE version_id = %s ORDER BY start_offset, span_id",
            (version_id,),
        )
        return [tuple(row) for row in cursor.fetchall()]


def _run_cli(
    bundle: Path, database_url: _RedactedDatabaseUrl
) -> subprocess.CompletedProcess[str]:
    environment = _sanitized_environment() | {
        "DATABASE_URL": str(database_url),
        "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE": "1",
        "OKF_REBUILD_EXPECTED_DATABASE": "okf_task34",
        "PYTHONWARNINGS": "ignore",
    }
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--bundle", str(bundle), "--rebuild"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
        text=True,
        env=environment,
    )


def _insert_document_version(
    cursor: psycopg.Cursor[Any], doc_id: UUID, version_id: UUID
) -> None:
    cursor.execute("INSERT INTO documents (doc_id) VALUES (%s)", (doc_id,))
    cursor.execute(
        "INSERT INTO document_versions (version_id, doc_id, content_hash, version_no) "
        "VALUES (%s, %s, %s, 1)",
        (version_id, doc_id, str(uuid4())),
    )


def _insert_stale_span(
    cursor: psycopg.Cursor[Any], version_id: UUID, text: str
) -> UUID:
    span_id = uuid4()
    cursor.execute(
        "INSERT INTO canonical_spans "
        "(span_id, version_id, span_kind, start_offset, end_offset, raw_text) "
        "VALUES (%s, %s, 'paragraph', 0, 1, %s)",
        (span_id, version_id, text),
    )
    return span_id


def _insert_canonical_row(
    cursor: psycopg.Cursor[Any], version_id: UUID, row: Sequence[object]
) -> UUID:
    span_id, start, end, page_no, heading_path, raw_text = row
    cursor.execute(
        "INSERT INTO canonical_spans "
        "(span_id, version_id, span_kind, start_offset, end_offset, page_no, heading_path, raw_text) "
        "VALUES (%s, %s, 'paragraph', %s, %s, %s, %s, %s)",
        (UUID(str(span_id)), version_id, start, end, page_no, heading_path, raw_text),
    )
    return UUID(str(span_id))


def _seed_dependent_rows(
    cursor: psycopg.Cursor[Any], version_id: UUID, span_id: UUID, suffix: str
) -> tuple[UUID, UUID, UUID, UUID]:
    chunk_id, tree_node_id, entity_id, evidence_id = uuid4(), uuid4(), uuid4(), uuid4()
    cursor.execute(
        "INSERT INTO vector_chunks (chunk_id, version_id, chunk_type) "
        "VALUES (%s, %s, 'test')",
        (chunk_id, version_id),
    )
    cursor.execute(
        "INSERT INTO vector_chunk_spans (chunk_id, span_id) VALUES (%s, %s)",
        (chunk_id, span_id),
    )
    cursor.execute(
        "INSERT INTO tree_nodes (node_id, version_id, node_type, level_no) "
        "VALUES (%s, %s, 'test', 0)",
        (tree_node_id, version_id),
    )
    cursor.execute(
        "INSERT INTO tree_node_spans (node_id, span_id) VALUES (%s, %s)",
        (tree_node_id, span_id),
    )
    cursor.execute(
        "INSERT INTO entities (entity_id, entity_key) VALUES (%s, %s)",
        (entity_id, f"entity-{suffix}"),
    )
    cursor.execute(
        "INSERT INTO evidence (evidence_id, version_id) VALUES (%s, %s)",
        (evidence_id, version_id),
    )
    cursor.execute(
        "INSERT INTO evidence_links "
        "(evidence_link_id, version_id, entity_id, span_id, source_kind, evidence_id) "
        "VALUES (%s, %s, %s, %s, 'test', %s)",
        (uuid4(), version_id, entity_id, span_id, evidence_id),
    )
    cursor.execute(
        "INSERT INTO entity_mentions "
        "(mention_id, entity_id, span_id, char_start, char_end, mention_text, source) "
        "VALUES (%s, %s, %s, 0, 1, 'x', 'test')",
        (uuid4(), entity_id, span_id),
    )
    return chunk_id, tree_node_id, evidence_id, entity_id


def _dependent_counts(
    connection: psycopg.Connection[Any], span_id: UUID
) -> tuple[int, int, int, int]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT "
            "(SELECT count(*) FROM vector_chunk_spans WHERE span_id = %s), "
            "(SELECT count(*) FROM tree_node_spans WHERE span_id = %s), "
            "(SELECT count(*) FROM evidence_links WHERE span_id = %s), "
            "(SELECT count(*) FROM entity_mentions WHERE span_id = %s)",
            (span_id, span_id, span_id, span_id),
        )
        result = cursor.fetchone()
        assert result is not None, "Dependent-count query must return one aggregate row"
        return tuple(result)


def _parent_count(
    connection: psycopg.Connection[Any], parent_ids: Sequence[UUID]
) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM vector_chunks WHERE chunk_id = %s "
            "UNION ALL SELECT count(*) FROM tree_nodes WHERE node_id = %s "
            "UNION ALL SELECT count(*) FROM evidence WHERE evidence_id = %s "
            "UNION ALL SELECT count(*) FROM entities WHERE entity_id = %s",
            tuple(parent_ids),
        )
        return sum(row[0] for row in cursor.fetchall())


def _install_dml_audit(connection: psycopg.Connection[Any]) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "CREATE TABLE canonical_span_dml_audit "
            "(sequence_id BIGSERIAL PRIMARY KEY, operation TEXT NOT NULL, span_id UUID NOT NULL)"
        )
        cursor.execute(
            "CREATE FUNCTION audit_canonical_span_dml() RETURNS trigger LANGUAGE plpgsql "
            "AS $$ BEGIN INSERT INTO canonical_span_dml_audit (operation, span_id) "
            "VALUES (TG_OP, CASE WHEN TG_OP = 'DELETE' THEN OLD.span_id ELSE NEW.span_id END); "
            "RETURN NULL; END; $$"
        )
        cursor.execute(
            "CREATE TRIGGER canonical_span_dml_audit AFTER INSERT OR UPDATE OR DELETE "
            "ON canonical_spans FOR EACH ROW EXECUTE FUNCTION audit_canonical_span_dml()"
        )
    connection.commit()


def _completed_logs(connection: psycopg.Connection[Any]) -> list[tuple[object, ...]]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT status, span_count, mismatch_detail FROM okf_rebuild_log "
            "ORDER BY started_at, rebuild_id"
        )
        return [tuple(row) for row in cursor.fetchall()]


def _failure_rows(connection: psycopg.Connection[Any]) -> list[tuple[object, ...]]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT failure_category, failure_code, failure_phase, rollback_confirmed, "
            "scope_count FROM okf_rebuild_failure_audit ORDER BY occurred_at, audit_id"
        )
        return [tuple(row) for row in cursor.fetchall()]


def _build_reconciliation_scenario(tmp_path: Path) -> _ReconciliationScenario:
    bundle = tmp_path / "source"
    _provision_bundle_root(bundle)
    _write_raw_document(
        bundle,
        name="01-target",
        doc_id=str(uuid4()),
        version_id=str(uuid4()),
        changed=True,
    )
    target = OKFParser().parse_bundle(bundle)[0]
    expected = _expected_rows(target)
    assert len(expected) >= 3
    return _ReconciliationScenario(
        bundle=bundle,
        target_version_id=UUID(target.frontmatter.version_id or ""),
        unrelated_version_id=uuid4(),
        expected=expected,
    )


def _seed_reconciliation_spans(
    cursor: psycopg.Cursor[Any],
    scenario: _ReconciliationScenario,
    retained: tuple[object, ...],
    corrupt: tuple[object, ...],
) -> tuple[
    UUID,
    UUID,
    UUID,
    UUID,
    tuple[UUID, UUID, UUID, UUID],
    tuple[UUID, UUID, UUID, UUID],
    tuple[UUID, UUID, UUID, UUID],
    tuple[UUID, UUID, UUID, UUID],
]:
    retained_id = _insert_canonical_row(cursor, scenario.target_version_id, retained)
    corrupt_id = _insert_canonical_row(cursor, scenario.target_version_id, corrupt)
    cursor.execute(
        "UPDATE canonical_spans SET span_kind = 'corrupt', raw_text = 'corrupt' WHERE span_id = %s",
        (corrupt_id,),
    )
    removed_id = _insert_stale_span(cursor, scenario.target_version_id, "removed")
    retained_parents = _seed_dependent_rows(
        cursor, scenario.target_version_id, retained_id, "retained"
    )
    corrupt_parents = _seed_dependent_rows(
        cursor, scenario.target_version_id, corrupt_id, "corrupt"
    )
    removed_parents = _seed_dependent_rows(
        cursor, scenario.target_version_id, removed_id, "removed"
    )
    unrelated_span = _insert_stale_span(cursor, scenario.unrelated_version_id, "keep")
    unrelated_parents = _seed_dependent_rows(
        cursor, scenario.unrelated_version_id, unrelated_span, "unrelated"
    )
    return (
        retained_id,
        corrupt_id,
        removed_id,
        unrelated_span,
        retained_parents,
        corrupt_parents,
        removed_parents,
        unrelated_parents,
    )


def _seed_reconciliation_scenario(
    database_url: _RedactedDatabaseUrl, scenario: _ReconciliationScenario
) -> _ReconciliationSeed:
    retained, corrupt, *_ = scenario.expected
    unrelated_doc_id = uuid4()
    with _disposable_connection(database_url) as connection:
        with connection.cursor() as cursor:
            _insert_document_version(
                cursor,
                UUID(
                    OKFParser().parse_bundle(scenario.bundle)[0].frontmatter.doc_id
                    or ""
                ),
                scenario.target_version_id,
            )
            _insert_document_version(
                cursor, unrelated_doc_id, scenario.unrelated_version_id
            )
            seeded_spans = _seed_reconciliation_spans(
                cursor, scenario, retained, corrupt
            )
            (
                retained_id,
                corrupt_id,
                removed_id,
                unrelated_span,
                retained_parents,
                corrupt_parents,
                removed_parents,
                unrelated_parents,
            ) = seeded_spans
        connection.commit()
        unrelated_snapshot = _canonical_rows(connection, scenario.unrelated_version_id)
        assert _dependent_counts(connection, retained_id) == (1, 1, 1, 1)
        assert _dependent_counts(connection, corrupt_id) == (1, 1, 1, 1)
        assert _dependent_counts(connection, removed_id) == (1, 1, 1, 1)
        _install_dml_audit(connection)
    return _ReconciliationSeed(
        retained_id,
        corrupt_id,
        removed_id,
        unrelated_span,
        retained_parents,
        corrupt_parents,
        removed_parents,
        unrelated_parents,
        unrelated_snapshot,
    )


def _assert_reconciliation_after_first_run(
    database_url: _RedactedDatabaseUrl,
    scenario: _ReconciliationScenario,
    seed: _ReconciliationSeed,
) -> list[tuple[object, ...]]:
    with _disposable_connection(database_url) as connection:
        target_snapshot = _canonical_rows(connection, scenario.target_version_id)
        assert target_snapshot == scenario.expected
        assert (
            _canonical_rows(connection, scenario.unrelated_version_id)
            == seed.unrelated_snapshot
        )
        assert _dependent_counts(connection, seed.retained_id) == (1, 1, 1, 1)
        assert _dependent_counts(connection, seed.corrupt_id) == (1, 1, 1, 1)
        assert _dependent_counts(connection, seed.removed_id) == (0, 0, 0, 0)
        assert _dependent_counts(connection, seed.unrelated_span) == (1, 1, 1, 1)
        assert _parent_count(connection, seed.retained_parents) == 4
        assert _parent_count(connection, seed.corrupt_parents) == 4
        assert _parent_count(connection, seed.removed_parents) == 4
        assert _parent_count(connection, seed.unrelated_parents) == 4
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT sequence_id, operation, span_id FROM canonical_span_dml_audit ORDER BY sequence_id"
            )
            audit_rows = cursor.fetchall()
            assert {(operation, span_id) for _, operation, span_id in audit_rows} == {
                ("UPDATE", seed.corrupt_id),
                *[("INSERT", UUID(str(row[0]))) for row in scenario.expected[2:]],
                ("DELETE", seed.removed_id),
            }
            delete_sequence = next(
                sequence_id
                for sequence_id, operation, _ in audit_rows
                if operation == "DELETE"
            )
            assert all(
                sequence_id < delete_sequence
                for sequence_id, operation, _ in audit_rows
                if operation in {"UPDATE", "INSERT"}
            )
            cursor.execute("DELETE FROM canonical_span_dml_audit")
        connection.commit()
        assert _completed_logs(connection) == [
            ("completed", len(scenario.expected), None)
        ]
    return target_snapshot


def _assert_reconciliation_after_second_run(
    database_url: _RedactedDatabaseUrl,
    scenario: _ReconciliationScenario,
    target_snapshot: list[tuple[object, ...]],
) -> None:
    with _disposable_connection(database_url) as connection:
        assert (
            _canonical_rows(connection, scenario.target_version_id) == target_snapshot
        )
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM canonical_span_dml_audit")
            assert cursor.fetchone() == (0,)
        assert _completed_logs(connection) == [
            ("completed", len(scenario.expected), None),
            ("completed", len(scenario.expected), None),
        ]


def _build_collision_scenario(tmp_path: Path) -> _CollisionScenario:
    earlier_document_id = UUID("00000000-0000-0000-0000-000000000010")
    earlier_version_id = UUID("00000000-0000-0000-0000-000000000010")
    colliding_document_id = UUID("00000000-0000-0000-0000-000000000020")
    colliding_version_id = UUID("00000000-0000-0000-0000-000000000020")
    owner_document_id = UUID("00000000-0000-0000-0000-000000000030")
    owner_version_id = UUID("00000000-0000-0000-0000-000000000030")
    bundle = tmp_path / "collision"
    _provision_bundle_root(bundle)
    _write_raw_document(
        bundle,
        name="01-earlier",
        doc_id=str(earlier_document_id),
        version_id=str(earlier_version_id),
        changed=True,
    )
    _write_raw_document(
        bundle,
        name="02-colliding",
        doc_id=str(colliding_document_id),
        version_id=str(colliding_version_id),
        changed=False,
    )
    colliding_document = OKFParser().parse_bundle(bundle)[1]
    return _CollisionScenario(
        bundle,
        earlier_document_id,
        earlier_version_id,
        colliding_document_id,
        colliding_version_id,
        owner_document_id,
        owner_version_id,
        UUID(str(_expected_rows(colliding_document)[0][0])),
    )


def _seed_collision_scenario(
    database_url: _RedactedDatabaseUrl, scenario: _CollisionScenario
) -> _CollisionSnapshots:
    with _disposable_connection(database_url) as connection:
        with connection.cursor() as cursor:
            _insert_document_version(
                cursor, scenario.earlier_document_id, scenario.earlier_version_id
            )
            _insert_document_version(
                cursor, scenario.colliding_document_id, scenario.colliding_version_id
            )
            _insert_document_version(
                cursor, scenario.owner_document_id, scenario.owner_version_id
            )
            _insert_stale_span(cursor, scenario.earlier_version_id, "earlier-old")
            _insert_stale_span(cursor, scenario.colliding_version_id, "colliding-old")
            cursor.execute(
                "INSERT INTO canonical_spans "
                "(span_id, version_id, span_kind, start_offset, end_offset, raw_text) "
                "VALUES (%s, %s, 'paragraph', 0, 1, 'owner')",
                (scenario.colliding_span_id, scenario.owner_version_id),
            )
        connection.commit()
        snapshots = _CollisionSnapshots(
            _canonical_rows(connection, scenario.earlier_version_id),
            _canonical_rows(connection, scenario.colliding_version_id),
            _canonical_rows(connection, scenario.owner_version_id),
        )
        _install_dml_audit(connection)
    return snapshots


def _assert_collision_rollback(
    database_url: _RedactedDatabaseUrl,
    scenario: _CollisionScenario,
    snapshots: _CollisionSnapshots,
) -> None:
    with _disposable_connection(database_url) as connection:
        assert (
            _canonical_rows(connection, scenario.earlier_version_id)
            == snapshots.earlier
        )
        assert (
            _canonical_rows(connection, scenario.colliding_version_id)
            == snapshots.colliding
        )
        assert _canonical_rows(connection, scenario.owner_version_id) == snapshots.owner
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM canonical_span_dml_audit")
            assert cursor.fetchone() == (0,)
            cursor.execute("SELECT count(*) FROM okf_rebuild_log")
            assert cursor.fetchone() == (0,)


def _build_missing_scope_scenario(tmp_path: Path) -> _MissingScopeScenario:
    registered_document_id = UUID("00000000-0000-0000-0000-000000000010")
    registered_version_id = UUID("00000000-0000-0000-0000-000000000010")
    bundle = tmp_path / "rollback"
    _provision_bundle_root(bundle)
    _write_raw_document(
        bundle,
        name="01-registered",
        doc_id=str(registered_document_id),
        version_id=str(registered_version_id),
        changed=True,
    )
    document = OKFParser().parse_bundle(bundle)[0]
    _write_raw_document(
        bundle,
        name="02-unregistered",
        doc_id="00000000-0000-0000-0000-000000000020",
        version_id="00000000-0000-0000-0000-000000000020",
        changed=False,
    )
    return _MissingScopeScenario(
        bundle, registered_document_id, registered_version_id, _expected_rows(document)
    )


def _seed_missing_scope_spans(
    cursor: psycopg.Cursor[Any],
    scenario: _MissingScopeScenario,
    retained: tuple[object, ...],
    corrupt: tuple[object, ...],
) -> tuple[
    tuple[UUID, UUID, UUID],
    tuple[
        tuple[UUID, UUID, UUID, UUID],
        tuple[UUID, UUID, UUID, UUID],
        tuple[UUID, UUID, UUID, UUID],
    ],
]:
    retained_id = _insert_canonical_row(
        cursor, scenario.registered_version_id, retained
    )
    corrupt_id = _insert_canonical_row(cursor, scenario.registered_version_id, corrupt)
    cursor.execute(
        "UPDATE canonical_spans SET span_kind = 'corrupt', raw_text = 'corrupt' WHERE span_id = %s",
        (corrupt_id,),
    )
    removed_id = _insert_stale_span(cursor, scenario.registered_version_id, "removed")
    retained_parents = _seed_dependent_rows(
        cursor, scenario.registered_version_id, retained_id, "rollback-retained"
    )
    corrupt_parents = _seed_dependent_rows(
        cursor, scenario.registered_version_id, corrupt_id, "rollback-corrupt"
    )
    removed_parents = _seed_dependent_rows(
        cursor, scenario.registered_version_id, removed_id, "rollback-removed"
    )
    return (retained_id, corrupt_id, removed_id), (
        retained_parents,
        corrupt_parents,
        removed_parents,
    )


def _seed_missing_scope_scenario(
    database_url: _RedactedDatabaseUrl, scenario: _MissingScopeScenario
) -> _MissingScopeSeed:
    retained, corrupt, *_ = scenario.expected
    with _disposable_connection(database_url) as connection:
        with connection.cursor() as cursor:
            _insert_document_version(
                cursor, scenario.registered_document_id, scenario.registered_version_id
            )
            span_ids, parent_ids = _seed_missing_scope_spans(
                cursor, scenario, retained, corrupt
            )
            retained_id, corrupt_id, removed_id = span_ids
            retained_parents, corrupt_parents, removed_parents = parent_ids
        connection.commit()
        canonical_before = _canonical_rows(connection, scenario.registered_version_id)
        bridge_before = {
            span_id: _dependent_counts(connection, span_id)
            for span_id in (retained_id, corrupt_id, removed_id)
        }
        parent_before = {
            parent_ids: _parent_count(connection, parent_ids)
            for parent_ids in (retained_parents, corrupt_parents, removed_parents)
        }
        _install_dml_audit(connection)
    return _MissingScopeSeed(
        retained_id,
        corrupt_id,
        removed_id,
        retained_parents,
        corrupt_parents,
        removed_parents,
        canonical_before,
        bridge_before,
        parent_before,
    )


def _assert_missing_scope_rollback(
    database_url: _RedactedDatabaseUrl,
    scenario: _MissingScopeScenario,
    seed: _MissingScopeSeed,
) -> None:
    with _disposable_connection(database_url) as connection:
        assert (
            _canonical_rows(connection, scenario.registered_version_id)
            == seed.canonical_before
        )
        assert {
            span_id: _dependent_counts(connection, span_id)
            for span_id in (seed.retained_id, seed.corrupt_id, seed.removed_id)
        } == seed.bridge_before
        assert {
            parent_ids: _parent_count(connection, parent_ids)
            for parent_ids in (
                seed.retained_parents,
                seed.corrupt_parents,
                seed.removed_parents,
            )
        } == seed.parent_before
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM canonical_span_dml_audit")
            assert cursor.fetchone() == (0,)
            cursor.execute("SELECT count(*) FROM okf_rebuild_log")
            assert cursor.fetchone() == (0,)


def _disposable_postgres_impl() -> Iterator[_RedactedDatabaseUrl]:
    if os.environ.get("OKF_REBUILD_DOCKER_ACCEPTANCE") != "1":
        pytest.skip("set OKF_REBUILD_DOCKER_ACCEPTANCE=1 for disposable Docker tests")
    if shutil.which("docker") is None:
        pytest.skip("Docker executable is unavailable for OKF integration coverage")
    if _run_docker(["info"], _sanitized_environment()).returncode != 0:
        pytest.skip("Docker daemon is unavailable for OKF integration coverage")
    container_name, port, password = (
        f"okf-task34-{uuid4().hex}",
        _free_localhost_port(),
        uuid4().hex,
    )
    _start_disposable_container(container_name, port, password)
    database_url = _RedactedDatabaseUrl(
        f"postgresql://okf:{password}@127.0.0.1:{port}/okf_task34"
    )
    try:
        _wait_for_disposable_database(database_url)
        yield database_url
    finally:
        _remove_labeled_disposable_container(container_name)
