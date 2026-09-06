#!/usr/bin/env python3
"""Verify and rebuild canonical span rows from an OKF bundle alone."""


import argparse
import hashlib
import json
import logging
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Any, TypeAlias
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from llamaindex_runtime.okf.diagnostics import diagnostic_safe_path  # noqa: E402
from llamaindex_runtime.okf.parser import OKFDocument, OKFParser  # noqa: E402
from llamaindex_runtime.okf.sidecar import SpanRecord  # noqa: E402
from llamaindex_runtime.okf.roundtrip import (  # noqa: E402
    recompute_span_dicts,
    roundtrip_mismatch,
)

LOGGER = logging.getLogger(__name__)
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "okf_roundtrip"
SpanValues: TypeAlias = tuple[str, int, int, int | None, str | None, str]
CanonicalRow: TypeAlias = tuple[str, str, int, int, int | None, str | None, str]
ConnectionFactory: TypeAlias = Callable[[str], psycopg.Connection[Any]]
_CONNECTION_HELPER_MODULE_NAME = "_okf_rebuild_database_connection"


def _load_connection_support() -> ModuleType:
    """Load a fresh sibling helper module without trusting ``sys.modules``."""
    module_cache = sys.modules
    _MISSING = object()
    prior = module_cache.get(_CONNECTION_HELPER_MODULE_NAME, _MISSING)
    helper_path = Path(__file__).with_name("_rebuild_database_connection.py")
    spec = spec_from_file_location(_CONNECTION_HELPER_MODULE_NAME, helper_path)
    if spec is None or spec.loader is None:
        raise ImportError("Unable to load rebuild database connection support")
    support = module_from_spec(spec)
    module_cache[_CONNECTION_HELPER_MODULE_NAME] = support
    try:
        spec.loader.exec_module(support)
        return support
    finally:
        if prior is _MISSING:
            module_cache.pop(_CONNECTION_HELPER_MODULE_NAME, None)
        else:
            module_cache[_CONNECTION_HELPER_MODULE_NAME] = prior  # type: ignore[assignment]


_connection_support = _load_connection_support()
_DisposablePostgresqlTarget = _connection_support.DisposablePostgresqlTarget
_normalize_libpq_metadata = _connection_support.normalize_libpq_metadata
_parse_disposable_postgresql_target = (
    _connection_support.parse_disposable_postgresql_target
)
_reject_ambient_service_routing = _connection_support.reject_ambient_service_routing
_runtime_connection_kwargs = _connection_support.runtime_connection_kwargs
_runtime_connection_factory = _connection_support.runtime_connection_factory
pq = _connection_support.pq


class _RebuildFailure(ValueError):

    def __init__(
        self,
        failure_category: str,
        failure_code: str,
        failure_phase: str,
        doc_id: UUID | None,
        version_id: UUID | None,
    ) -> None:
        safe_messages = {
            "unregistered_document_version": "OKF document version is not registered for its doc_id",
            "span_id_owned_by_other_version": "Canonical span ID belongs to a different document version",
        }
        super().__init__(safe_messages.get(failure_code, "Rebuild failed"))
        self.failure_category = failure_category
        self.failure_code = failure_code
        self.failure_phase = failure_phase
        self.doc_id = doc_id
        self.version_id = version_id


class _PrimaryExitFailure(ValueError):

    def __init__(self) -> None:
        super().__init__("Primary connection close failed after committed rebuild")


@dataclass(frozen=True)
class _AdmittedSpan:

    span_id: str
    page_no: int | None
    heading_path: tuple[str, ...]
    offset: int
    text: str


@dataclass(frozen=True)
class _AdmittedRawDocument:

    doc_id: str
    version_id: str
    canonical_hash: str
    spans: tuple[_AdmittedSpan, ...]
    verification_path: str


@dataclass(frozen=True)
class _AdmittedBundle:

    documents: tuple[_AdmittedRawDocument, ...]
    malformed: int = 0


def _freeze_raw_document(document: OKFDocument) -> _AdmittedRawDocument:
    if not document.canonical_hash:
        raise ValueError("raw OKF document lacks an admitted raw pair")
    doc_id = str(UUID(document.frontmatter.doc_id or ""))
    version_id = str(UUID(document.frontmatter.version_id or ""))
    spans = tuple(
        _AdmittedSpan(
            str(span.span_id),
            span.page_no,
            tuple(span.heading_path),
            span.offset,
            span.text,
        )
        for span in document.spans
    )
    path = document.frontmatter.okf_file_path or document.file_path.as_posix()
    return _AdmittedRawDocument(
        doc_id, version_id, str(document.canonical_hash), spans, str(path)
    )


def _admitted_span_records(
    document: _AdmittedRawDocument,
) -> tuple[SpanRecord, ...]:
    return tuple(
        SpanRecord(
            span.span_id, span.page_no, span.heading_path, span.offset, span.text
        )
        for span in document.spans
    )


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--verify-roundtrip", action="store_true")
    parser.add_argument(
        "--fixture", choices=("sectioned-pdf", "complex-layout-pdf", "docx")
    )
    parser.add_argument("--rebuild", action="store_true")
    parsed = parser.parse_args(arguments)
    if parsed.fixture and not parsed.verify_roundtrip:
        parser.error("--fixture requires --verify-roundtrip")
    if not parsed.verify_roundtrip and not parsed.rebuild:
        parser.error("one of --verify-roundtrip or --rebuild is required")
    return parsed


def _fixture_failure(fixture: object, *, unavailable: bool = False) -> ValueError:
    status = "unavailable" if unavailable else "are malformed"
    return ValueError(
        f"Fixture expectations {status}: fixture={diagnostic_safe_path(fixture)}"
    )


def _validate_expected_spans(loaded: object, fixture: object) -> dict[str, Any]:
    if not isinstance(loaded, dict) or not isinstance(loaded.get("spans"), list):
        raise _fixture_failure(fixture)
    for scope_field in ("doc_id", "version_id"):
        value = loaded.get(scope_field)
        try:
            canonical = str(UUID(value)) if isinstance(value, str) else None
        except ValueError:
            canonical = None
        if canonical != value:
            raise _fixture_failure(fixture)
    return loaded


def _load_expected_spans(fixture: str) -> dict[str, Any]:
    if not isinstance(fixture, str):
        raise _fixture_failure(fixture)
    fixture_path = FIXTURE_ROOT / fixture / "expected_span_ids.json"
    try:
        loaded = json.loads(fixture_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise _fixture_failure(fixture, unavailable=True) from None
    return _validate_expected_spans(loaded, fixture)


def _admit_bundle(bundle: Path) -> _AdmittedBundle:
    parsed = OKFParser().parse_bundle(bundle)
    raw_documents = tuple(
        document for document in parsed if document.frontmatter.type == "raw"
    )
    _ensure_unique_raw_document_versions(raw_documents)
    frozen = tuple(_freeze_raw_document(document) for document in raw_documents)
    return _AdmittedBundle(
        tuple(sorted(frozen, key=lambda item: (item.doc_id, item.version_id))),
        parsed.stats.malformed,
    )


def _validate_rebuild_admission(admitted: _AdmittedBundle) -> None:
    if admitted.malformed:
        raise ValueError("malformed OKF documents found in bundle; refusing rebuild")
    if not admitted.documents:
        raise ValueError("No raw OKF documents were found in the bundle")


def _scope_manifest(admitted: _AdmittedBundle) -> tuple[dict[str, Any], str]:
    scopes = sorted(
        (
            {
                "doc_id": item.doc_id,
                "version_id": item.version_id,
                "canonical_hash": item.canonical_hash,
                "span_count": len(item.spans),
            }
            for item in admitted.documents
        ),
        key=lambda scope: (str(scope["doc_id"]), str(scope["version_id"])),
    )
    manifest: dict[str, Any] = {"schema_version": 1, "scopes": scopes}
    encoded = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return manifest, hashlib.sha256(encoded).hexdigest()


def _verify_fixture(
    admitted: _AdmittedBundle, expected: dict[str, Any], fixture: str
) -> str | None:
    validated = _validate_expected_spans(expected, fixture)
    matching = [
        item
        for item in admitted.documents
        if item.doc_id == validated["doc_id"]
        and item.version_id == validated["version_id"]
    ]
    if len(matching) != 1:
        return (
            "ROUNDTRIP MISMATCH at span[0]: field=document_count "
            f"direct_count=1 okf_count={len(matching)} "
            f"(doc={validated['doc_id']} "
            f"file={diagnostic_safe_path(f'raw/{fixture}.md')})"
        )
    document = matching[0]
    return roundtrip_mismatch(
        direct=validated["spans"],
        spans=_admitted_span_records(document),
        doc_id=document.doc_id,
        version_id=document.version_id,
        file_path=document.verification_path,
    )


def verify_roundtrip(admitted: _AdmittedBundle, fixture: str) -> str | None:
    return _verify_fixture(admitted, _load_expected_spans(fixture), fixture)


def _require_fixture_scope_matches_bundle(
    admitted: _AdmittedBundle, expected: dict[str, Any]
) -> None:
    fixture_scope = (expected.get("doc_id"), expected.get("version_id"))
    admitted_scopes = {(item.doc_id, item.version_id) for item in admitted.documents}
    if admitted_scopes != {fixture_scope}:
        raise ValueError(
            "fixture scope does not cover admitted bundle; refusing rebuild"
        )


def _require_disposable_rebuild_parameters(
    database_url: str, expected_database: str, environ: Mapping[str, str]
) -> tuple[str, str]:
    if not isinstance(database_url, str):
        raise TypeError("database URL must be a string")
    if not isinstance(expected_database, str):
        raise TypeError("expected database must be a string")
    normalized_url = database_url.strip()
    if not normalized_url:
        raise ValueError(
            "DATABASE_URL is required for --rebuild; refusing database access"
        )
    if environ.get("OKF_MIGRATION_TEST_DATABASE_DISPOSABLE") != "1":
        raise ValueError(
            "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE=1 is required for --rebuild"
        )
    normalized_database = expected_database.strip()
    if not normalized_database:
        raise ValueError(
            "OKF_REBUILD_EXPECTED_DATABASE is required for --rebuild; refusing database access"
        )
    _reject_ambient_service_routing(environ)
    _parse_disposable_postgresql_target(normalized_url, normalized_database)
    return normalized_url, normalized_database


def _require_disposable_database_url(environ: Mapping[str, str]) -> tuple[str, str]:
    return _require_disposable_rebuild_parameters(
        environ.get("DATABASE_URL", ""),
        environ.get("OKF_REBUILD_EXPECTED_DATABASE", ""),
        environ,
    )


def _canonical_rows(document: _AdmittedRawDocument) -> list[CanonicalRow]:
    recomputed = recompute_span_dicts(
        _admitted_span_records(document),
        doc_id=document.doc_id,
        version_id=document.version_id,
    )
    return sorted(
        [
            (
                span["span_id"],
                "paragraph",
                span["offset"],
                span["offset"] + len(span["text"]),
                span["page_no"],
                " > ".join(span["heading_path"]) if span["heading_path"] else None,
                span["text"],
            )
            for span in recomputed
        ],
        key=lambda row: row[0],
    )


def _ensure_unique_span_ids(rows: Sequence[CanonicalRow]) -> None:
    span_ids = [row[0] for row in rows]
    if len(span_ids) != len(set(span_ids)):
        raise ValueError("Duplicate canonical span ID in OKF document")


def _prepare_rebuild(
    document: _AdmittedRawDocument,
) -> tuple[UUID, UUID, list[CanonicalRow]]:
    doc_id = UUID(document.doc_id)
    version_id = UUID(document.version_id)
    rows = _canonical_rows(document)
    _ensure_unique_span_ids(rows)
    return doc_id, version_id, rows


def _lock_registered_version(
    cursor: psycopg.Cursor[Any], doc_id: UUID, version_id: UUID
) -> None:
    cursor.execute(
        "SELECT 1 FROM document_versions WHERE doc_id = %s AND version_id = %s FOR UPDATE",
        (doc_id, version_id),
    )
    if cursor.fetchone() != (1,):
        raise _RebuildFailure(
            "scope_validation",
            "unregistered_document_version",
            "scope_lock",
            doc_id,
            version_id,
        )


def _validate_span_collisions(
    cursor: psycopg.Cursor[Any],
    desired_by_id: dict[UUID, SpanValues],
    doc_id: UUID,
    version_id: UUID,
) -> None:
    cursor.execute(
        "SELECT span_id, version_id FROM canonical_spans "
        "WHERE span_id = ANY(%s) ORDER BY span_id FOR KEY SHARE",
        (list(desired_by_id),),
    )
    for existing_span_id, existing_version_id in cursor.fetchall():
        if existing_version_id != version_id:
            raise _RebuildFailure(
                "identity_conflict",
                "span_id_owned_by_other_version",
                "span_reconciliation",
                doc_id,
                version_id,
            )


def _load_current_spans(
    cursor: psycopg.Cursor[Any], version_id: UUID
) -> dict[UUID, SpanValues]:
    cursor.execute(
        "SELECT span_id, span_kind, start_offset, end_offset, page_no, heading_path, raw_text "
        "FROM canonical_spans WHERE version_id = %s ORDER BY span_id FOR UPDATE",
        (version_id,),
    )
    return {row[0]: tuple(row[1:]) for row in cursor.fetchall()}


def _reconcile_spans(
    cursor: psycopg.Cursor[Any],
    desired_by_id: dict[UUID, SpanValues],
    current_by_id: dict[UUID, SpanValues],
    version_id: UUID,
) -> int:
    changed = 0
    for span_id in sorted(desired_by_id):
        desired = desired_by_id[span_id]
        current = current_by_id.pop(span_id, None)
        if current is None:
            _insert_span(cursor, span_id, version_id, desired)
            changed += 1
        elif current != desired:
            _update_span(cursor, span_id, version_id, desired)
            changed += 1
    for span_id in sorted(current_by_id):
        cursor.execute(
            "DELETE FROM canonical_spans WHERE version_id = %s AND span_id = %s",
            (version_id, span_id),
        )
        changed += 1
    return changed


def _insert_span(
    cursor: psycopg.Cursor[Any], span_id: UUID, version_id: UUID, desired: SpanValues
) -> None:
    cursor.execute(
        "INSERT INTO canonical_spans "
        "(span_id, version_id, span_kind, start_offset, end_offset, page_no, heading_path, raw_text) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (span_id, version_id, *desired),
    )


def _update_span(
    cursor: psycopg.Cursor[Any], span_id: UUID, version_id: UUID, desired: SpanValues
) -> None:
    cursor.execute(
        "UPDATE canonical_spans SET span_kind = %s, start_offset = %s, "
        "end_offset = %s, page_no = %s, heading_path = %s, raw_text = %s "
        "WHERE version_id = %s AND span_id = %s",
        (*desired, version_id, span_id),
    )


def _log_completed_rebuild(
    cursor: psycopg.Cursor[Any], rebuild_id: UUID, span_count: int
) -> None:
    cursor.execute(
        "INSERT INTO okf_rebuild_log "
        "(rebuild_id, started_at, finished_at, status, span_count, mismatch_detail) "
        "VALUES (%s, now(), now(), 'completed', %s, NULL)",
        (rebuild_id, span_count),
    )


def _database_failure(
    error: psycopg.Error, phase: str, doc_id: UUID, version_id: UUID
) -> _RebuildFailure:
    category, code = (
        ("integrity", "integrity_error")
        if isinstance(error, psycopg.IntegrityError)
        else ("database", "database_error")
    )
    return _RebuildFailure(category, code, phase, doc_id, version_id)


def _rebuild_admitted_document(
    connection: psycopg.Connection[Any], admitted: _AdmittedRawDocument
) -> int:
    if not isinstance(admitted, _AdmittedRawDocument):
        raise TypeError("canonical writer requires an admitted raw document")
    doc_id, version_id, rows = _prepare_rebuild(admitted)
    desired_by_id = {UUID(row[0]): row[1:] for row in rows}
    with connection.cursor() as cursor:
        try:
            _lock_registered_version(cursor, doc_id, version_id)
        except psycopg.Error as error:
            raise _database_failure(error, "scope_lock", doc_id, version_id) from None
        try:
            _validate_span_collisions(cursor, desired_by_id, doc_id, version_id)
            changed = _reconcile_spans(
                cursor,
                desired_by_id,
                _load_current_spans(cursor, version_id),
                version_id,
            )
        except psycopg.Error as error:
            raise _database_failure(
                error, "span_reconciliation", doc_id, version_id
            ) from None
        try:
            _log_completed_rebuild(cursor, uuid4(), len(rows))
        except psycopg.Error as error:
            raise _database_failure(
                error, "success_log_write", doc_id, version_id
            ) from None
    return int(bool(changed))


def _ensure_unique_raw_document_versions(documents: Sequence[OKFDocument]) -> None:
    scopes = [
        (document.frontmatter.doc_id, document.frontmatter.version_id)
        for document in documents
    ]
    if len(scopes) != len(set(scopes)):
        raise ValueError("Duplicate raw OKF document version in bundle")


def _safe_failure_details(
    error: Exception, phase: str
) -> tuple[str, str, str, UUID | None, UUID | None]:
    if isinstance(error, _RebuildFailure):
        return (
            error.failure_category,
            error.failure_code,
            error.failure_phase,
            error.doc_id,
            error.version_id,
        )
    if isinstance(error, psycopg.IntegrityError):
        return "integrity", "integrity_error", phase, None, None
    if isinstance(error, psycopg.Error):
        return "database", "database_error", phase, None, None
    return "internal", "internal_failure", phase, None, None


def _discard_audit_connection(connection: psycopg.Connection[Any]) -> None:
    try:
        connection.rollback()
    except Exception:
        pass
    try:
        connection.close()
    except Exception:
        pass


def _insert_failure_audit(
    cursor: psycopg.Cursor[Any],
    rebuild_run_id: UUID,
    manifest: dict[str, Any],
    manifest_sha256: str,
    failure: tuple[str, str, str, UUID | None, UUID | None],
) -> None:
    category, code, phase, doc_id, version_id = failure
    cursor.execute(
        "INSERT INTO okf_rebuild_failure_audit "
        "(audit_id, rebuild_run_id, failure_category, failure_code, "
        "failure_phase, rollback_confirmed, scope_count, scope_manifest, "
        "scope_manifest_sha256, failing_doc_id, failing_version_id, diagnostic) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (rebuild_run_id) DO NOTHING",
        (
            uuid4(),
            rebuild_run_id,
            category,
            code,
            phase,
            True,
            len(manifest["scopes"]),
            Jsonb(manifest),
            manifest_sha256,
            doc_id,
            version_id,
            Jsonb({"schema_version": 1}),
        ),
    )


def _is_expected_audit_database(result: object, expected_database: str) -> bool:
    return (
        isinstance(result, tuple)
        and len(result) == 1
        and type(result[0]) is str
        and result[0] == expected_database
    )


def _write_failure_audit(
    connection_factory: ConnectionFactory,
    database_url: str,
    expected_database: str,
    rebuild_run_id: UUID,
    manifest: dict[str, Any],
    manifest_sha256: str,
    failure: tuple[str, str, str, UUID | None, UUID | None],
) -> None:
    connection = connection_factory(database_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            current_database = cursor.fetchone()
    except Exception:
        _discard_audit_connection(connection)
        return
    if not _is_expected_audit_database(current_database, expected_database):
        _discard_audit_connection(connection)
        return
    try:
        connection.rollback()
    except Exception:
        _discard_audit_connection(connection)
        return
    try:
        with connection.transaction():
            with connection.cursor() as cursor:
                _insert_failure_audit(
                    cursor, rebuild_run_id, manifest, manifest_sha256, failure
                )
    finally:
        connection.close()


def _confirm_explicit_rollback(connection: psycopg.Connection[Any]) -> bool:
    try:
        connection.rollback()
    except Exception:
        LOGGER.warning("event=okf_rebuild_rollback_confirmation_failed")
        return False
    return True


def _run_primary_transaction(
    connection: psycopg.Connection[Any],
    admitted: _AdmittedBundle,
    expected_database: str,
) -> tuple[int | None, Exception | None, bool, bool, str]:
    phase = "target_validation"
    target_verified = False
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            current_database = cursor.fetchone()
        if not _is_expected_audit_database(current_database, expected_database):
            raise ValueError(
                "Connected database identity does not match rebuild target"
            )
        target_verified = True
        phase = "scope_lock"
        rebuilt = sum(
            (
                _rebuild_admitted_document(connection, item)
                for item in admitted.documents
            ),
            start=0,
        )
        phase = "transaction_commit"
        connection.commit()
    except Exception as error:
        return (
            None,
            error,
            _confirm_explicit_rollback(connection),
            target_verified,
            phase,
        )
    return rebuilt, None, False, target_verified, phase


def _run_primary_rebuild(
    admitted: _AdmittedBundle,
    database_url: str,
    expected_database: str,
    factory: ConnectionFactory,
) -> tuple[int | None, Exception | None, bool, bool, str]:
    try:
        connection = factory(database_url)
    except Exception as error:
        return None, error, False, False, "target_validation"
    rebuilt, failure, rollback_confirmed, target_verified, phase = (
        _run_primary_transaction(connection, admitted, expected_database)
    )
    try:
        connection.close()
    except Exception:
        if failure is None:
            failure = _PrimaryExitFailure()
        rollback_confirmed = False
    return rebuilt, failure, rollback_confirmed, target_verified, phase


def _default_connection_factory(
    database_url: str, expected_database: str
) -> ConnectionFactory:
    target = _parse_disposable_postgresql_target(database_url, expected_database)
    return lambda _: _runtime_connection_factory(target)


def _rebuild_admitted_bundle(
    admitted: _AdmittedBundle,
    database_url: str,
    expected_database: str,
    *,
    connection_factory: ConnectionFactory | None = None,
) -> int:
    _validate_rebuild_admission(admitted)
    manifest, manifest_sha256 = _scope_manifest(admitted)
    rebuild_run_id = uuid4()
    factory = (
        _default_connection_factory(database_url, expected_database)
        if connection_factory is None
        else connection_factory
    )
    rebuilt, error, rollback_confirmed, target_verified, phase = _run_primary_rebuild(
        admitted, database_url, expected_database, factory
    )
    if error is None:
        return rebuilt or 0
    if target_verified and rollback_confirmed:
        failure = _safe_failure_details(error, phase)
        try:
            _write_failure_audit(
                factory,
                database_url,
                expected_database,
                rebuild_run_id,
                manifest,
                manifest_sha256,
                failure,
            )
        except Exception:
            LOGGER.warning("event=okf_rebuild_failure_audit_write_failed")
    raise error


def rebuild_bundle(
    bundle_path: Path, *, environ: Mapping[str, str] | None = None
) -> int:
    if not isinstance(bundle_path, Path):
        raise TypeError("rebuild requires a bundle path")
    guarded_url, guarded_database = _require_disposable_database_url(
        os.environ if environ is None else environ
    )
    admitted = _admit_bundle(bundle_path)
    return _rebuild_admitted_bundle(admitted, guarded_url, guarded_database)


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_arguments(arguments)
    admitted = _admit_bundle(args.bundle)
    expected: dict[str, Any] | None = None
    if args.verify_roundtrip:
        if args.fixture is None:
            raise ValueError("--fixture is required for --verify-roundtrip")
        expected = _load_expected_spans(args.fixture)
        mismatch = _verify_fixture(admitted, expected, args.fixture)
        if mismatch is not None:
            print(mismatch, file=sys.stderr)
            return 1
    if args.rebuild:
        if expected is not None:
            _require_fixture_scope_matches_bundle(admitted, expected)
        database_url, expected_database = _require_disposable_database_url(
            dict(os.environ)
        )
        rebuilt = _rebuild_admitted_bundle(admitted, database_url, expected_database)
        LOGGER.info("Rebuilt %s raw OKF document(s)", rebuilt)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from None
    except psycopg.Error:
        print("Database connection failed; refusing rebuild", file=sys.stderr)
        raise SystemExit(2) from None
