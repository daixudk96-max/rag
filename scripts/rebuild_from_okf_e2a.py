"""E2a route variant for OKF canonical span rebuild (scripts/rebuild_from_okf.py E1 sibling).

This script is the E2a CLI counterpart to ``scripts/rebuild_from_okf.py``:

* E1 (scripts/rebuild_from_okf.py) is the sole supported E1 CLI per STATE.md
  Section 10 active predicates. It uses the legacy psycopg direct path that
  manipulates ``canonical_spans`` rows one document at a time.

* E2a (this script) routes through the E2a materialization/reconciliation
  sequence, delegating to ``llamaindex_runtime.okf.e2a_admission`` and
  ``llamaindex_runtime.okf.e2a_reconciler.E2aReconciler``. The E2a flow
  matches steps 6 through 8 of
  ``llamaindex_runtime.ingestion.pipeline.IngestionPipeline._ingest_e2a``:

      1. ``BundleAuthority(bundle_root)``
      2. ``e2a_admission.admit_e2a_materialization_input(authority)``
      3. ``connection_factory()`` returning a psycopg connection with
         ``autocommit=False``
      4. ``E2aReconciler().reconcile(connection, materialization_input)``

The CLI surface (``--bundle``, ``--verify-roundtrip``, ``--fixture``,
``--rebuild``) is preserved for parity with the E1 CLI. The
``--verify-roundtrip`` path uses the same ``OKFParser`` admission as E1 and is
intentionally a no-DB code path. The ``--rebuild`` path is the E2a route and
requires disposable PostgreSQL authorization.

The E2a variant does NOT replace the E1 CLI; both are first-class entry points
with non-overlapping routes. Bundles produced by the E2a route are byte-stable
with the E1 route because the desired-state is derived from the same raw pairs
the E1 path consumes.

Security constraints (inherited from E1):

* Never read, log, or print ``DATABASE_URL`` or other credentials. The script
  accepts the URL only as an opaque disposable target.
* ``--rebuild`` requires ``OKF_MIGRATION_TEST_DATABASE_DISPOSABLE=1`` and
  ``OKF_REBUILD_EXPECTED_DATABASE`` (mirroring the E1 CLI gates) and
  additionally requires ``OKF_E2A_DISPOSABLE_TEST_AUTHORIZED=1`` because the
  E2a reconciler issues whole-corpus DML that exceeds the E1 per-document
  scope.
* ``bundle_root`` defaults to the value of the ``OKF_BUNDLE_ROOT`` environment
  variable, falling back to ``"okf_bundle"`` (the STATE.md Section 10
  ratified default). The ``--bundle`` CLI argument, when supplied, takes
  precedence over the env var.
"""

from __future__ import annotations

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
from uuid import UUID

import psycopg

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from llamaindex_runtime.okf import e2a_admission  # noqa: E402
from llamaindex_runtime.okf.diagnostics import diagnostic_safe_path  # noqa: E402
from llamaindex_runtime.okf.e2a_reconciler import E2aReconciler  # noqa: E402
from llamaindex_runtime.okf.parser import OKFDocument, OKFParser  # noqa: E402
from llamaindex_runtime.okf.rooted_open import BundleAuthority  # noqa: E402
from llamaindex_runtime.okf.roundtrip import (  # noqa: E402
    recompute_span_dicts,
    roundtrip_mismatch,
)
from llamaindex_runtime.okf.sidecar import SpanRecord  # noqa: E402

LOGGER = logging.getLogger(__name__)
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "okf_roundtrip"
DEFAULT_BUNDLE_ROOT = "okf_bundle"
SpanValues: TypeAlias = tuple[str, int, int, int | None, str | None, str]
CanonicalRow: TypeAlias = tuple[str, str, int, int, int | None, str | None, str]
ConnectionFactory: TypeAlias = Callable[[], psycopg.Connection[Any]]
ReconcilerFactory: TypeAlias = Callable[[], E2aReconciler]
_CONNECTION_HELPER_MODULE_NAME = "_okf_rebuild_database_connection"
_E2A_BUNDLE_ENV_VAR = "OKF_BUNDLE_ROOT"


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


@dataclass(frozen=True)
class _E2aRebuildOutcome:
    """Redacted, typed summary of an E2a reconciliation outcome."""

    outcome: str
    manifest_sha256: str
    primary_dml_by_table: Mapping[str, int]
    failure_audit_outcome: str | None
    post_rollback_failure_audit_outcome: str | None
    reconciliation_required: bool


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
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=(
            "This is the E2a route variant. It uses E2aReconciler and "
            "admit_e2a_materialization_input. The E1 CLI is "
            "scripts/rebuild_from_okf.py."
        ),
    )
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


def _ensure_unique_raw_document_versions(documents: Sequence[OKFDocument]) -> None:
    scopes = [
        (document.frontmatter.doc_id, document.frontmatter.version_id)
        for document in documents
    ]
    if len(scopes) != len(set(scopes)):
        raise ValueError("Duplicate raw OKF document version in bundle")


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


def _require_fixture_scope_matches_bundle(
    admitted: _AdmittedBundle, expected: dict[str, Any]
) -> None:
    fixture_scope = (expected.get("doc_id"), expected.get("version_id"))
    admitted_scopes = {(item.doc_id, item.version_id) for item in admitted.documents}
    if admitted_scopes != {fixture_scope}:
        raise ValueError(
            "fixture scope does not cover admitted bundle; refusing rebuild"
        )


def _resolve_bundle_root(cli_bundle: Path, environ: Mapping[str, str]) -> Path:
    """Resolve the E2a ``bundle_root`` from CLI/env precedence rules.

    The CLI ``--bundle`` argument always wins. When the CLI argument is
    supplied, it is the bundle root for E2a reconciliation. When it is
    omitted, the value of ``OKF_BUNDLE_ROOT`` is consulted; if that is also
    missing, the STATE.md Section 10 ratified default ``okf_bundle`` is used.
    This function only resolves; it does not validate that the path exists or
    is readable (that is the E2a reconciler's responsibility).
    """
    if cli_bundle is not None and str(cli_bundle) != "":
        return Path(cli_bundle)
    env_value = environ.get(_E2A_BUNDLE_ENV_VAR, "").strip()
    if env_value:
        return Path(env_value)
    return Path(DEFAULT_BUNDLE_ROOT)


def _require_disposable_rebuild_parameters(
    database_url: str,
    expected_database: str,
    environ: Mapping[str, str],
) -> tuple[str, str]:
    """Enforce the standard E1 disposable-DB guards plus the E2a gate.

    E2a rebuilds issue whole-corpus DML via ``E2aReconciler``, which is a
    strictly stronger scope than the E1 per-document path. Therefore the E2a
    CLI additionally requires ``OKF_E2A_DISPOSABLE_TEST_AUTHORIZED=1`` to
    be set. The other guards (``DATABASE_URL``,
    ``OKF_MIGRATION_TEST_DATABASE_DISPOSABLE=1``,
    ``OKF_REBUILD_EXPECTED_DATABASE``) are inherited verbatim from E1.
    """
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
    if environ.get("OKF_E2A_DISPOSABLE_TEST_AUTHORIZED") != "1":
        raise ValueError(
            "OKF_E2A_DISPOSABLE_TEST_AUTHORIZED=1 is required for the E2a route"
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


def _build_e2a_connection_factory(
    database_url: str, expected_database: str
) -> ConnectionFactory:
    """Construct a zero-arg ``connection_factory`` for the E2a reconciler.

    The returned callable ignores its arguments and always opens a fresh
    psycopg connection from the validated disposable target. The
    ``E2aReconciler`` expects ``autocommit=False`` (the E2a protocol
    requires a single explicit ``commit()`` or ``rollback()``), and
    ``_runtime_connection_factory`` already enforces that contract.
    """
    target = _parse_disposable_postgresql_target(database_url, expected_database)

    def _factory() -> psycopg.Connection[Any]:
        return _runtime_connection_factory(target)

    return _factory


def _build_e2a_reconciler_factory() -> ReconcilerFactory:
    """Construct a zero-arg ``reconciler`` factory returning a real E2aReconciler.

    A factory (rather than a single instance) is used so that every E2a
    rebuild CLI invocation gets a fresh reconciler. This matches the
    E2aReconciler contract: the reconciler owns one primary transaction per
    ``reconcile`` call, and re-using a reconciler across transactions would
    couple unrelated runs.
    """

    def _factory() -> E2aReconciler:
        return E2aReconciler()

    return _factory


def _redact_reconciliation_outcome(
    raw: object,
) -> _E2aRebuildOutcome:
    """Map a raw ``E2aReconciliationResult`` (or coerced equivalent) to a typed summary.

    The redaction intentionally does not include any DSN-like value, the
    corpus manifest body, span texts, or per-table DML keys beyond the
    primary DML table name list. Only counters and the outcome are surfaced.
    """
    if not isinstance(raw, object) or raw is None:
        raise ValueError("E2a reconciliation returned an invalid result")
    outcome = getattr(raw, "outcome", None)
    if not isinstance(outcome, str):
        raise ValueError("E2a reconciliation outcome is invalid")
    manifest_sha256 = getattr(raw, "manifest_sha256", None)
    if not isinstance(manifest_sha256, str) or not manifest_sha256:
        raise ValueError("E2a reconciliation manifest_sha256 is invalid")
    primary = getattr(raw, "primary_dml_by_table", {})
    if not isinstance(primary, Mapping):
        raise ValueError("E2a reconciliation primary_dml_by_table is invalid")
    failure_audit = getattr(raw, "failure_audit_outcome", None)
    post_rollback = getattr(raw, "post_rollback_failure_audit_outcome", None)
    reconciliation_required = getattr(raw, "reconciliation_required", False)
    if not isinstance(reconciliation_required, bool):
        raise ValueError("E2a reconciliation reconciliation_required is invalid")
    return _E2aRebuildOutcome(
        outcome=outcome,
        manifest_sha256=manifest_sha256,
        primary_dml_by_table={str(key): int(value) for key, value in primary.items()},
        failure_audit_outcome=(
            str(failure_audit) if isinstance(failure_audit, str) else None
        ),
        post_rollback_failure_audit_outcome=(
            str(post_rollback) if isinstance(post_rollback, str) else None
        ),
        reconciliation_required=reconciliation_required,
    )


def _e2a_rebuild_bundle(
    bundle_root: Path,
    admitted: _AdmittedBundle,
    *,
    connection_factory: ConnectionFactory,
    reconciler_factory: ReconcilerFactory,
) -> _E2aRebuildOutcome:
    """Execute the E2a materialization/reconciliation sequence.

    Sequence (matches steps 6-8 of
    ``IngestionPipeline._ingest_e2a``):

      1. Open ``BundleAuthority(bundle_root)`` and admit materialization
         input (which calls ``read_raw_pair`` per pair internally).
      2. Open a primary connection via the supplied ``connection_factory``.
      3. Build a fresh ``E2aReconciler`` via ``reconciler_factory()`` and call
         ``reconcile(connection, materialization_input)``.
      4. Return a redacted, typed summary of the outcome.
    """
    _validate_rebuild_admission(admitted)
    bundle_root_path = Path(bundle_root)
    if not bundle_root_path.exists():
        raise ValueError("E2a bundle_root does not exist")
    if not bundle_root_path.is_dir():
        raise ValueError("E2a bundle_root is not a directory")
    with BundleAuthority(bundle_root_path) as authority:
        materialization_input = e2a_admission.admit_e2a_materialization_input(authority)
    connection = connection_factory()
    try:
        reconciler = reconciler_factory()
        result = reconciler.reconcile(connection, materialization_input)
    finally:
        try:
            connection.close()
        except Exception:
            LOGGER.warning("event=okf_e2a_rebuild_connection_close_failed")
    return _redact_reconciliation_outcome(result)


def rebuild_bundle(
    bundle_path: Path,
    *,
    bundle_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> _E2aRebuildOutcome:
    """Public entry point: rebuild a bundle via the E2a route.

    ``bundle_path`` is the OKF bundle directory supplied by the caller. When
    ``bundle_root`` is provided, it overrides the env-var resolution. When it
    is ``None``, the E2a ``bundle_root`` is resolved from
    ``OKF_BUNDLE_ROOT`` (falling back to the State-ratified default
    ``okf_bundle``). The CLI surface always passes both arguments through,
    with the CLI ``--bundle`` winning the precedence race.
    """
    if not isinstance(bundle_path, Path):
        raise TypeError("rebuild requires a bundle path")
    env = os.environ if environ is None else environ
    guarded_url, guarded_database = _require_disposable_database_url(env)
    admitted = _admit_bundle(bundle_path)
    resolved_root = (
        Path(bundle_root)
        if bundle_root is not None
        else _resolve_bundle_root(bundle_path, env)
    )
    connection_factory = _build_e2a_connection_factory(guarded_url, guarded_database)
    reconciler_factory = _build_e2a_reconciler_factory()
    return _e2a_rebuild_bundle(
        resolved_root,
        admitted,
        connection_factory=connection_factory,
        reconciler_factory=reconciler_factory,
    )


def _format_outcome(outcome: _E2aRebuildOutcome) -> str:
    """Format a redacted single-line summary of the E2a outcome.

    Never includes the manifest body, any DSN, or any per-row payload. The
    summary is safe to print on stdout and to log via the ``logging`` module.
    """
    primary = (
        ", ".join(
            f"{table}={count}"
            for table, count in sorted(outcome.primary_dml_by_table.items())
        )
        or "none"
    )
    return (
        f"E2a rebuild outcome={outcome.outcome} "
        f"manifest_sha256={outcome.manifest_sha256} "
        f"primary_dml={primary} "
        f"failure_audit={outcome.failure_audit_outcome} "
        f"post_rollback_audit={outcome.post_rollback_failure_audit_outcome} "
        f"reconciliation_required={outcome.reconciliation_required}"
    )


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
        bundle_root = _resolve_bundle_root(args.bundle, os.environ)
        outcome = rebuild_bundle(
            args.bundle,
            bundle_root=bundle_root,
            environ={
                "DATABASE_URL": database_url,
                "OKF_REBUILD_EXPECTED_DATABASE": expected_database,
            },
        )
        LOGGER.info(_format_outcome(outcome))
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
