"""E2b rebuild CLI orchestrator for the raw-corpus entity layer (Phase 16-11).

This script is the E2b counterpart to ``scripts/rebuild_from_okf_e2a.py``. It
routes one OKF bundle through the composed E2b pipeline (corpus inputs ->
extractor candidates -> desired state -> ``E2bMaterializationRepository``) and
prints a redacted typed outcome.

Design constraints
------------------
- ``--rebuild`` is off by default: it requires exactly ``RAG_ENTITY_EXTRACTOR=raner``
  and refuses to run before any connection is constructed otherwise. The switch is
  read directly from the process environment.
- The runner executes no SQL, commit, or rollback itself. Each document/version
  is reconciled by ``E2bMaterializationRepository.reconcile_document``, which
  acquires E2a's exact shared advisory key
  ``okf:e2a:parent:{document_id}:{version_id}`` (never ``okf:e2b:parent``), owns
  commit/rollback, and opens a fresh failure-audit connection only when the
  primary is already rolled back and closed.
- Connection support is freshly loaded from ``scripts/_rebuild_database_connection.py``
  without trusting ``sys.modules``; a raw URI is never passed positionally to
  ``psycopg.connect``.
- The runner prints only redacted typed outcomes; it never prints or logs a DSN,
  credential, disposable target, corpus body, span text, or bundle path.
- ``--verify-roundtrip`` is parser-only / no-DB / no-model and requires neither
  ``RAG_ENTITY_EXTRACTOR`` nor ``DATABASE_URL``.
- ``rebuild_bundle`` exposes keyword-only injectable pipeline factories
  (connection, repository, extractor, corpus-input, desired-state). Defaults are
  the fail-closed seam builders, so default execution stays model-lazy and
  refuses before any connection/model activity; a future authorized gate may
  inject pure fakes to drive deterministic orchestration.
- The CLI ``__main__``/``_run_redacted_cli`` never prints ``str(exc)``: it emits
  a fixed redacted message and a deterministic nonzero exit code.
"""

import argparse
import hashlib
import json
import logging
import os
import re
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

from llamaindex_runtime.entity.materialization_repository import (  # noqa: E402
    E2bDesiredState,
    E2bDmlRecorder,
    E2bDocumentScope,
    E2bMaterializationRepository,
    E2bReconciliationResult,
)
from llamaindex_runtime.okf.diagnostics import diagnostic_safe_path  # noqa: E402
from llamaindex_runtime.okf.parser import OKFDocument, OKFParser  # noqa: E402
from llamaindex_runtime.okf.roundtrip import roundtrip_mismatch  # noqa: E402
from llamaindex_runtime.okf.sidecar import SpanRecord  # noqa: E402

LOGGER = logging.getLogger(__name__)
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "okf_roundtrip"
_CONNECTION_HELPER_MODULE_NAME = "_okf_rebuild_database_connection"
ConnectionFactory: TypeAlias = Callable[[], psycopg.Connection[Any]]
_E2B_PRIMARY_TABLES = frozenset(
    {"entity_mentions", "okf_e2b_node_link_ownership", "node_entity_links"}
)
_E2B_AUDIT_STATUSES = frozenset(
    {"written", "failed", "outcome_unknown", "written_cleanup_unconfirmed"}
)
_E2B_OUTCOMES = frozenset(
    {"changed", "no_op", "rolled_back_failure", "outcome_unknown"}
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_E2B_CLI_FAILURE_MESSAGE = "E2b rebuild refused; failure details are not disclosed"
_OUTCOME_PRIORITY = {
    "no_op": 0,
    "changed": 1,
    "rolled_back_failure": 2,
    "outcome_unknown": 3,
}


def _load_connection_support() -> ModuleType:
    """Load a fresh sibling helper module without trusting ``sys.modules``."""
    module_cache = sys.modules
    missing = object()
    prior = module_cache.get(_CONNECTION_HELPER_MODULE_NAME, missing)
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
        if prior is missing:
            module_cache.pop(_CONNECTION_HELPER_MODULE_NAME, None)
        else:
            module_cache[_CONNECTION_HELPER_MODULE_NAME] = prior  # type: ignore[assignment]


_connection_support = _load_connection_support()
_DisposablePostgresqlTarget = _connection_support.DisposablePostgresqlTarget
_parse_disposable_postgresql_target = (
    _connection_support.parse_disposable_postgresql_target
)
_reject_ambient_service_routing = _connection_support.reject_ambient_service_routing
_runtime_connection_factory = _connection_support.runtime_connection_factory


@dataclass(frozen=True)
class _E2bAdmittedSpan:
    span_id: str
    page_no: int | None
    heading_path: tuple[str, ...]
    offset: int
    text: str


@dataclass(frozen=True)
class _E2bAdmittedRawDocument:
    doc_id: str
    version_id: str
    canonical_hash: str
    spans: tuple[_E2bAdmittedSpan, ...]
    verification_path: str


@dataclass(frozen=True)
class _E2bAdmittedBundle:
    documents: tuple[_E2bAdmittedRawDocument, ...]
    malformed: int = 0


@dataclass(frozen=True)
class _E2bRebuildOutcome:
    """Redacted, typed summary of an E2b reconciliation run."""

    outcome: str
    manifest_sha256: str
    primary_dml_by_table: Mapping[str, int]
    failure_audit_outcome: str | None
    post_rollback_failure_audit_outcome: str | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "primary_dml_by_table", dict(self.primary_dml_by_table)
        )


def _freeze_raw_document(document: OKFDocument) -> _E2bAdmittedRawDocument:
    if not document.canonical_hash:
        raise ValueError("raw OKF document lacks an admitted raw pair")
    doc_id = str(UUID(document.frontmatter.doc_id or ""))
    version_id = str(UUID(document.frontmatter.version_id or ""))
    spans = tuple(
        _E2bAdmittedSpan(
            str(span.span_id),
            span.page_no,
            tuple(span.heading_path),
            span.offset,
            span.text,
        )
        for span in document.spans
    )
    path = document.frontmatter.okf_file_path or document.file_path.as_posix()
    return _E2bAdmittedRawDocument(
        doc_id, version_id, str(document.canonical_hash), spans, str(path)
    )


def _admitted_span_records(
    document: _E2bAdmittedRawDocument,
) -> tuple[SpanRecord, ...]:
    return tuple(
        SpanRecord(
            span.span_id, span.page_no, span.heading_path, span.offset, span.text
        )
        for span in document.spans
    )


def _ensure_unique_raw_document_versions(
    documents: Sequence[OKFDocument],
) -> None:
    scopes = [
        (document.frontmatter.doc_id, document.frontmatter.version_id)
        for document in documents
    ]
    if len(scopes) != len(set(scopes)):
        raise ValueError("Duplicate raw OKF document version in bundle")


def _admit_bundle(bundle: Path) -> _E2bAdmittedBundle:
    parsed = OKFParser().parse_bundle(bundle)
    raw_documents = tuple(
        document for document in parsed if document.frontmatter.type == "raw"
    )
    _ensure_unique_raw_document_versions(raw_documents)
    frozen = tuple(_freeze_raw_document(document) for document in raw_documents)
    return _E2bAdmittedBundle(
        tuple(sorted(frozen, key=lambda item: (item.doc_id, item.version_id))),
        parsed.stats.malformed,
    )


def _validate_rebuild_admission(admitted: _E2bAdmittedBundle) -> None:
    if admitted.malformed:
        raise ValueError("malformed OKF documents found in bundle; refusing rebuild")
    if not admitted.documents:
        raise ValueError("No raw OKF documents were found in the bundle")


def _scope_manifest(admitted: _E2bAdmittedBundle) -> tuple[dict[str, Any], str]:
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


def _verify_fixture(
    admitted: _E2bAdmittedBundle,
    expected: dict[str, Any],
    fixture: str,
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


def _require_raner_extractor(environ: Mapping[str, str]) -> None:
    """Require the exact ``raner`` extractor switch before any connection."""
    switch = environ.get("RAG_ENTITY_EXTRACTOR", "off")
    if switch != "raner":
        raise ValueError(
            "RAG_ENTITY_EXTRACTOR must be exactly 'raner' to rebuild; refusing"
        )


def _build_e2b_connection_factory(environ: Mapping[str, str]) -> ConnectionFactory:
    """Build a zero-arg factory that opens fresh disposable connections."""
    database_url = environ.get("DATABASE_URL", "")
    expected_database = environ.get("OKF_REBUILD_EXPECTED_DATABASE", "")
    if environ.get("OKF_MIGRATION_TEST_DATABASE_DISPOSABLE") != "1":
        raise ValueError(
            "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE=1 is required for --rebuild"
        )
    if environ.get("OKF_E2B_DISPOSABLE_TEST_AUTHORIZED") != "1":
        raise ValueError(
            "OKF_E2B_DISPOSABLE_TEST_AUTHORIZED=1 is required for the E2b route"
        )
    if not expected_database:
        raise ValueError(
            "OKF_REBUILD_EXPECTED_DATABASE is required for --rebuild; refusing database access"
        )
    _reject_ambient_service_routing(environ)
    target = _parse_disposable_postgresql_target(database_url, expected_database)

    def _factory() -> psycopg.Connection[Any]:
        return _runtime_connection_factory(target)

    return _factory


def _build_e2b_repository_factory() -> (
    Callable[[ConnectionFactory], E2bMaterializationRepository]
):
    """Build a factory that creates a fresh repository per document."""

    def _factory(
        failure_audit_connection_factory: ConnectionFactory,
    ) -> E2bMaterializationRepository:
        return E2bMaterializationRepository(
            failure_audit_connection_factory=failure_audit_connection_factory
        )

    return _factory


def _build_e2b_extractor_factory() -> Callable[[], object]:
    """Return a zero-arg extractor factory.

    The real E2b extractor depends on the RaNER model path, which this runner
    never constructs (no model loading). The default fails closed; callers must
    inject a fake extractor through this seam.
    """

    def _unconfigured() -> object:
        raise ValueError("E2b extractor is not configured; no model path is permitted")

    return _unconfigured


def _build_e2b_corpus_input_factory() -> Callable[[object], list[object]]:
    """Return a per-document corpus-input mapping, fail-closed by default."""

    def _unconfigured(document: object) -> list[object]:
        raise ValueError("E2b corpus-input mapping is not configured; inject the seam")

    return _unconfigured


def _build_e2b_desired_state_factory() -> Callable[[object, object], E2bDesiredState]:
    """Return a per-document desired-state builder, fail-closed by default."""

    def _unconfigured(document: object, candidates: object) -> E2bDesiredState:
        raise ValueError("E2b desired-state mapping is not configured; inject the seam")

    return _unconfigured


def _redact_rebuild_outcome(raw: object, *, manifest_sha256: str) -> _E2bRebuildOutcome:
    """Map a raw reconciliation result to a typed, redacted summary."""
    if (
        type(manifest_sha256) is not str
        or _SHA256_RE.fullmatch(manifest_sha256) is None
    ):
        raise ValueError("E2b outcome manifest_sha256 must be a lowercase SHA-256")
    if raw is None:
        raise ValueError("E2b reconciliation returned an invalid result")
    outcome = getattr(raw, "outcome", None)
    if type(outcome) is not str or outcome not in _E2B_OUTCOMES:
        raise ValueError("E2b reconciliation outcome is invalid")
    primary = getattr(raw, "primary_dml_by_table", None)
    if not isinstance(primary, Mapping):
        raise ValueError("E2b reconciliation primary_dml_by_table is invalid")
    redacted_primary: dict[str, int] = {}
    for table, count in primary.items():
        if table not in _E2B_PRIMARY_TABLES:
            raise ValueError("E2b reconciliation table is not allowlisted")
        if type(count) is not int or count < 0:
            raise ValueError("E2b reconciliation count must be a nonnegative integer")
        redacted_primary[table] = count
    failure_audit = getattr(raw, "failure_audit_outcome", None)
    if failure_audit is not None and (
        type(failure_audit) is not str or failure_audit not in _E2B_AUDIT_STATUSES
    ):
        raise ValueError("E2b failure-audit status is not allowlisted")
    post_rollback = getattr(raw, "post_rollback_failure_audit_outcome", None)
    if post_rollback is not None:
        raise ValueError("E2b outcome must not carry a second audit channel")
    return _E2bRebuildOutcome(
        outcome=outcome,
        manifest_sha256=manifest_sha256,
        primary_dml_by_table=redacted_primary,
        failure_audit_outcome=failure_audit,
        post_rollback_failure_audit_outcome=None,
    )


def _merge_outcomes(
    outcomes: Sequence[_E2bRebuildOutcome], manifest_sha256: str
) -> _E2bRebuildOutcome:
    if not outcomes:
        raise ValueError("no E2b reconciliation outcomes to merge")
    aggregate_outcome = max(
        outcomes, key=lambda outcome: _OUTCOME_PRIORITY[outcome.outcome]
    ).outcome
    primary: dict[str, int] = {}
    failure_audit: str | None = None
    for outcome in outcomes:
        for table, count in outcome.primary_dml_by_table.items():
            primary[table] = primary.get(table, 0) + count
        if outcome.failure_audit_outcome is not None:
            failure_audit = outcome.failure_audit_outcome
    return _E2bRebuildOutcome(
        outcome=aggregate_outcome,
        manifest_sha256=manifest_sha256,
        primary_dml_by_table=primary,
        failure_audit_outcome=failure_audit,
        post_rollback_failure_audit_outcome=None,
    )


def _format_outcome(outcome: _E2bRebuildOutcome) -> str:
    """Format a redacted single-line summary of the E2b outcome."""
    primary = (
        ", ".join(
            f"{table}={count}"
            for table, count in sorted(outcome.primary_dml_by_table.items())
        )
        or "none"
    )
    return (
        f"E2b rebuild outcome={outcome.outcome} "
        f"manifest_sha256={outcome.manifest_sha256} "
        f"primary_dml={primary} "
        f"failure_audit={outcome.failure_audit_outcome} "
        f"post_rollback_audit={outcome.post_rollback_failure_audit_outcome}"
    )


def _rebuild_one(
    document: _E2bAdmittedRawDocument,
    *,
    connection_factory: ConnectionFactory,
    repository_factory: Callable[[ConnectionFactory], object],
    extractor_factory: Callable[[], object],
    corpus_input_factory: Callable[[_E2bAdmittedRawDocument], list[object]],
    desired_state_factory: Callable[[_E2bAdmittedRawDocument, object], E2bDesiredState],
) -> E2bReconciliationResult:
    inputs = corpus_input_factory(document)
    extractor = extractor_factory()
    candidates = extractor.extract(inputs)  # type: ignore[attr-defined]
    desired = desired_state_factory(document, candidates)
    connection = connection_factory()
    try:
        repository = repository_factory(connection_factory)
        scope = E2bDocumentScope(
            document_id=document.doc_id, version_id=document.version_id
        )
        recorder = E2bDmlRecorder()
        result = repository.reconcile_document(  # type: ignore[attr-defined]
            connection.cursor(), scope, desired=desired, recorder=recorder
        )
    finally:
        # The runner owns the primary connection and never calls commit() or
        # rollback(). Close it in a finally whenever it is not already closed --
        # including repository pre-transaction contract errors that propagate
        # before reconcile_document returns. The repository may already have
        # closed the connection on its failure paths, so never double-close.
        if not getattr(connection, "closed", False):
            connection.close()
    return result


def rebuild_bundle(
    bundle_path: Path,
    *,
    environ: Mapping[str, str] | None = None,
    connection_factory: ConnectionFactory | None = None,
    repository_factory: Callable[[ConnectionFactory], object] | None = None,
    extractor_factory: Callable[[], object] | None = None,
    corpus_input_factory: (
        Callable[[_E2bAdmittedRawDocument], list[object]] | None
    ) = None,
    desired_state_factory: (
        Callable[[_E2bAdmittedRawDocument, object], E2bDesiredState] | None
    ) = None,
) -> _E2bRebuildOutcome:
    """Rebuild one OKF bundle through the E2b pipeline and redact the outcome.

    All pipeline factories are keyword-only injectable parameters. When an
    argument is ``None`` the module-level fail-closed seam builders are used, so
    the default stays model-lazy and refuses before any connection/model
    activity. A future authorized gate may inject pure fakes (extractor,
    corpus-input, desired-state, repository, connection) to drive deterministic
    orchestration.
    """
    if not isinstance(bundle_path, Path):
        raise TypeError("rebuild requires a bundle path")
    env = os.environ if environ is None else environ
    _require_raner_extractor(env)
    admitted = _admit_bundle(bundle_path)
    _validate_rebuild_admission(admitted)
    manifest_sha256 = _scope_manifest(admitted)[1]
    if connection_factory is None:
        connection_factory = _build_e2b_connection_factory(env)
    if repository_factory is None:
        repository_factory = _build_e2b_repository_factory()
    if extractor_factory is None:
        extractor_factory = _build_e2b_extractor_factory()
    if corpus_input_factory is None:
        corpus_input_factory = _build_e2b_corpus_input_factory()
    if desired_state_factory is None:
        desired_state_factory = _build_e2b_desired_state_factory()
    outcomes = [
        _redact_rebuild_outcome(
            _rebuild_one(
                document,
                connection_factory=connection_factory,
                repository_factory=repository_factory,
                extractor_factory=extractor_factory,
                corpus_input_factory=corpus_input_factory,
                desired_state_factory=desired_state_factory,
            ),
            manifest_sha256=manifest_sha256,
        )
        for document in admitted.documents
    ]
    return _merge_outcomes(outcomes, manifest_sha256)


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


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_arguments(arguments)
    if args.verify_roundtrip:
        admitted = _admit_bundle(args.bundle)
        if args.fixture is None:
            raise ValueError("--fixture is required for --verify-roundtrip")
        expected = _load_expected_spans(args.fixture)
        mismatch = _verify_fixture(admitted, expected, args.fixture)
        if mismatch is not None:
            print(mismatch, file=sys.stderr)
            return 1
    if args.rebuild:
        _require_raner_extractor(os.environ)
        outcome = rebuild_bundle(args.bundle, environ=dict(os.environ))
        LOGGER.info(_format_outcome(outcome))
    return 0


def _run_redacted_cli(arguments: Sequence[str] | None = None) -> int:
    """Run the CLI, mapping user-facing failures to fixed redacted stderr.

    ``main`` keeps raising ``ValueError`` so programmatic callers can handle
    structured errors; this wrapper is the CLI-facing boundary that never
    prints ``str(exc)`` (which could leak a DSN, credential, path, corpus text,
    or node/entity data). The exit code stays deterministic (2).
    """
    try:
        return main(arguments)
    except ValueError:
        print(_E2B_CLI_FAILURE_MESSAGE, file=sys.stderr)
        return 2
    except psycopg.Error:
        print("Database connection failed; refusing rebuild", file=sys.stderr)
        return 2


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    raise SystemExit(_run_redacted_cli())
