"""Independently authored migration-019 catalog expectations."""

from __future__ import annotations

from dataclasses import dataclass

from llamaindex_runtime.okf.e2a_disposable_sql_lexer import (
    _check,
    _definition,
    _fk,
    _unique,
)


@dataclass(frozen=True)
class _ConstraintExpectation:
    table: str
    name: str
    contype: str
    definition: str
    columns: str = ""
    reference_table: str | None = None
    reference_columns: str = ""


@dataclass(frozen=True)
class _IndexExpectation:
    table: str
    name: str
    keys: str
    unique: bool = False
    predicate: str = ""
    definition: str = ""
    primary: bool = False
    options: str = ""


@dataclass(frozen=True)
class _TriggerExpectation:
    table: str
    name: str
    function: str
    trigger_type: int


@dataclass(frozen=True)
class _FunctionExpectation:
    name: str
    prokind: str
    pronargs: int
    proargtypes: str
    provariadic: int
    prorettype: str
    proretset: bool
    language: str
    source: str


# These contracts are authored independently of the SQL reader.  Names select a
# required artifact; OIDs and ordered key arrays establish its actual identity.
_EXPECTED_019_CONSTRAINT_ROWS = (
    _ConstraintExpectation(
        "document_versions",
        "uq_document_versions_doc_version",
        "u",
        _unique("doc_id, version_id"),
        "doc_id,version_id",
    ),
    _ConstraintExpectation(
        "canonical_spans",
        "uq_canonical_spans_version_span",
        "u",
        _unique("version_id, span_id"),
        "version_id,span_id",
    ),
    _ConstraintExpectation(
        "evidence",
        "uq_evidence_version_evidence",
        "u",
        _unique("version_id, evidence_id"),
        "version_id,evidence_id",
    ),
    _ConstraintExpectation(
        "okf_manual_fact_ownership",
        "pk_okf_manual_fact_ownership",
        "p",
        _definition("PRIMARY KEY (ownership_id)"),
        "ownership_id",
    ),
    _ConstraintExpectation(
        "okf_manual_fact_ownership",
        "chk_okf_manual_fact_ownership_path",
        "c",
        _check(
            "okf_relative_path <> ''::text AND okf_relative_path !~ '^(?:/|\\\\)'::text AND okf_relative_path !~ '/$'::text AND okf_relative_path !~ '//'::text AND okf_relative_path !~ '(^|/)(\\.|\\.\\.)(/|$)'::text AND okf_relative_path !~ '[\\\\:]'::text AND okf_relative_path !~ '(^|/)[^/]*[. ](/|$)'::text AND okf_relative_path !~* '(^|/)(con|prn|aux|nul|com[1-9]|lpt[1-9])(\\.[^/]*)?(/|$)'::text"
        ),
    ),
    _ConstraintExpectation(
        "okf_manual_fact_ownership",
        "chk_okf_manual_fact_ownership_kind",
        "c",
        _check("fact_kind = ANY (ARRAY['entity'::text, 'relation'::text])"),
    ),
    _ConstraintExpectation(
        "okf_manual_fact_ownership",
        "chk_okf_manual_fact_ownership_digest",
        "c",
        _check("source_digest ~ '^[0-9a-f]{64}$'::text"),
    ),
    _ConstraintExpectation(
        "okf_manual_fact_ownership",
        "chk_okf_manual_fact_ownership_target",
        "c",
        _check(
            "((fact_kind = 'entity'::text) AND (entity_id IS NOT NULL) AND (entity_id = fact_id) AND (relation_id IS NULL)) OR ((fact_kind = 'relation'::text) AND (relation_id IS NOT NULL) AND (relation_id = fact_id) AND (entity_id IS NULL))"
        ),
    ),
    _ConstraintExpectation(
        "okf_manual_fact_ownership",
        "chk_okf_manual_fact_ownership_scope",
        "c",
        _check(
            "((scope_version_id = '00000000-0000-0000-0000-000000000000'::uuid) AND (document_id IS NULL) AND (version_id IS NULL)) OR ((scope_version_id = version_id) AND (document_id IS NOT NULL) AND (version_id IS NOT NULL))"
        ),
    ),
    _ConstraintExpectation(
        "okf_manual_fact_ownership",
        "fk_okf_manual_fact_ownership_entity",
        "f",
        _fk("entity_id", "entities", "entity_id"),
        "entity_id",
        "entities",
        "entity_id",
    ),
    _ConstraintExpectation(
        "okf_manual_fact_ownership",
        "fk_okf_manual_fact_ownership_relation",
        "f",
        _fk("relation_id", "relations", "relation_id"),
        "relation_id",
        "relations",
        "relation_id",
    ),
    _ConstraintExpectation(
        "okf_manual_fact_ownership",
        "fk_okf_manual_fact_ownership_document_version",
        "f",
        _fk("document_id, version_id", "document_versions", "doc_id, version_id"),
        "document_id,version_id",
        "document_versions",
        "doc_id,version_id",
    ),
    _ConstraintExpectation(
        "okf_manual_fact_ownership",
        "uq_okf_manual_fact_ownership_path_fact",
        "u",
        _unique("okf_relative_path, fact_kind, fact_id"),
        "okf_relative_path,fact_kind,fact_id",
    ),
    _ConstraintExpectation(
        "okf_manual_fact_ownership",
        "uq_okf_manual_fact_ownership_entity_target",
        "u",
        _unique("ownership_id, entity_id"),
        "ownership_id,entity_id",
    ),
    _ConstraintExpectation(
        "okf_manual_fact_ownership",
        "uq_okf_manual_fact_ownership_relation_target",
        "u",
        _unique("ownership_id, relation_id"),
        "ownership_id,relation_id",
    ),
    _ConstraintExpectation(
        "okf_manual_fact_ownership",
        "uq_okf_manual_fact_ownership_scope",
        "u",
        _unique("ownership_id, scope_version_id"),
        "ownership_id,scope_version_id",
    ),
    _ConstraintExpectation(
        "okf_manual_evidence_targets",
        "pk_okf_manual_evidence_targets",
        "p",
        _definition("PRIMARY KEY (version_id, evidence_id)"),
        "version_id,evidence_id",
    ),
    _ConstraintExpectation(
        "okf_manual_evidence_targets",
        "uq_okf_manual_evidence_targets_entity",
        "u",
        _unique("version_id, evidence_id, entity_id"),
        "version_id,evidence_id,entity_id",
    ),
    _ConstraintExpectation(
        "okf_manual_evidence_targets",
        "uq_okf_manual_evidence_targets_relation",
        "u",
        _unique("version_id, evidence_id, relation_id"),
        "version_id,evidence_id,relation_id",
    ),
    _ConstraintExpectation(
        "okf_manual_evidence_targets",
        "chk_okf_manual_evidence_targets_exactly_one_target",
        "c",
        _check("num_nonnulls(entity_id, relation_id) = 1"),
    ),
    _ConstraintExpectation(
        "okf_manual_evidence_targets",
        "fk_okf_manual_evidence_targets_version_evidence",
        "f",
        _fk("version_id, evidence_id", "evidence", "version_id, evidence_id"),
        "version_id,evidence_id",
        "evidence",
        "version_id,evidence_id",
    ),
    _ConstraintExpectation(
        "okf_manual_evidence_targets",
        "fk_okf_manual_evidence_targets_entity",
        "f",
        _fk("entity_id", "entities", "entity_id"),
        "entity_id",
        "entities",
        "entity_id",
    ),
    _ConstraintExpectation(
        "okf_manual_evidence_targets",
        "fk_okf_manual_evidence_targets_relation",
        "f",
        _fk("relation_id", "relations", "relation_id"),
        "relation_id",
        "relations",
        "relation_id",
    ),
    _ConstraintExpectation(
        "evidence_links",
        "fk_evidence_links_version",
        "f",
        _fk("version_id", "document_versions", "version_id"),
        "version_id",
        "document_versions",
        "version_id",
    ),
    _ConstraintExpectation(
        "evidence_links",
        "fk_evidence_links_entity",
        "f",
        _fk("entity_id", "entities", "entity_id"),
        "entity_id",
        "entities",
        "entity_id",
    ),
    _ConstraintExpectation(
        "evidence_links",
        "fk_evidence_links_relation",
        "f",
        _fk("relation_id", "relations", "relation_id"),
        "relation_id",
        "relations",
        "relation_id",
    ),
    _ConstraintExpectation(
        "evidence_links",
        "fk_evidence_links_version_span",
        "f",
        _fk("version_id, span_id", "canonical_spans", "version_id, span_id"),
        "version_id,span_id",
        "canonical_spans",
        "version_id,span_id",
    ),
    _ConstraintExpectation(
        "evidence_links",
        "fk_evidence_links_version_evidence",
        "f",
        _fk("version_id, evidence_id", "evidence", "version_id, evidence_id"),
        "version_id,evidence_id",
        "evidence",
        "version_id,evidence_id",
    ),
    _ConstraintExpectation(
        "evidence_links",
        "fk_evidence_links_ownership",
        "f",
        _fk("ownership_id", "okf_manual_fact_ownership", "ownership_id"),
        "ownership_id",
        "okf_manual_fact_ownership",
        "ownership_id",
    ),
    _ConstraintExpectation(
        "evidence_links",
        "fk_evidence_links_ownership_scope",
        "f",
        _fk(
            "ownership_id, ownership_scope_version_id",
            "okf_manual_fact_ownership",
            "ownership_id, scope_version_id",
        ),
        "ownership_id,ownership_scope_version_id",
        "okf_manual_fact_ownership",
        "ownership_id,scope_version_id",
    ),
    _ConstraintExpectation(
        "evidence_links",
        "fk_evidence_links_manual_entity_owner",
        "f",
        _fk(
            "ownership_id, manual_entity_id",
            "okf_manual_fact_ownership",
            "ownership_id, entity_id",
        ),
        "ownership_id,manual_entity_id",
        "okf_manual_fact_ownership",
        "ownership_id,entity_id",
    ),
    _ConstraintExpectation(
        "evidence_links",
        "fk_evidence_links_manual_relation_owner",
        "f",
        _fk(
            "ownership_id, manual_relation_id",
            "okf_manual_fact_ownership",
            "ownership_id, relation_id",
        ),
        "ownership_id,manual_relation_id",
        "okf_manual_fact_ownership",
        "ownership_id,relation_id",
    ),
    _ConstraintExpectation(
        "evidence_links",
        "fk_evidence_links_manual_entity_target",
        "f",
        _fk(
            "version_id, evidence_id, manual_entity_id",
            "okf_manual_evidence_targets",
            "version_id, evidence_id, entity_id",
        ),
        "version_id,evidence_id,manual_entity_id",
        "okf_manual_evidence_targets",
        "version_id,evidence_id,entity_id",
    ),
    _ConstraintExpectation(
        "evidence_links",
        "fk_evidence_links_manual_relation_target",
        "f",
        _fk(
            "version_id, evidence_id, manual_relation_id",
            "okf_manual_evidence_targets",
            "version_id, evidence_id, relation_id",
        ),
        "version_id,evidence_id,manual_relation_id",
        "okf_manual_evidence_targets",
        "version_id,evidence_id,relation_id",
    ),
    _ConstraintExpectation(
        "evidence_links",
        "chk_evidence_links_exactly_one_target",
        "c",
        _check("num_nonnulls(entity_id, relation_id) = 1"),
    ),
    _ConstraintExpectation(
        "evidence_links",
        "chk_evidence_links_manual_projection",
        "c",
        _check(
            "(source_kind <> 'manual_okf'::text AND ownership_id IS NULL AND ownership_scope_version_id IS NULL AND manual_entity_id IS NULL AND manual_relation_id IS NULL) OR (source_kind = 'manual_okf'::text AND evidence_id IS NOT NULL AND ownership_id IS NOT NULL AND ownership_scope_version_id IS NOT NULL AND num_nonnulls(manual_entity_id, manual_relation_id) = 1 AND (((manual_entity_id IS NOT NULL) AND (entity_id IS NOT NULL) AND (manual_entity_id = entity_id) AND (manual_relation_id IS NULL)) OR ((manual_relation_id IS NOT NULL) AND (relation_id IS NOT NULL) AND (manual_relation_id = relation_id) AND (manual_entity_id IS NULL))))"
        ),
    ),
    _ConstraintExpectation(
        "evidence_links",
        "chk_evidence_links_manual_scope",
        "c",
        _check(
            "((source_kind = 'manual_okf'::text) AND (ownership_scope_version_id IS NOT NULL) AND ((ownership_scope_version_id = version_id) OR (ownership_scope_version_id = '00000000-0000-0000-0000-000000000000'::uuid))) OR ((source_kind <> 'manual_okf'::text) AND (ownership_scope_version_id IS NULL))"
        ),
    ),
    _ConstraintExpectation(
        "okf_rebuild_failure_audit",
        "chk_okf_rebuild_failure_audit_phase",
        "c",
        _check(
            "failure_phase = ANY (ARRAY['target_validation'::text, 'scope_lock'::text, 'parent_reconciliation'::text, 'span_reconciliation'::text, 'tree_reconciliation'::text, 'chunk_reconciliation'::text, 'manual_fact_reconciliation'::text, 'evidence_reconciliation'::text, 'transaction_commit'::text, 'success_log_write'::text])"
        ),
    ),
)
_EXPECTED_019_CONSTRAINTS = tuple(
    sorted((item.table, item.name) for item in _EXPECTED_019_CONSTRAINT_ROWS)
)
_EXPECTED_019_CONSTRAINT_DEFINITIONS = {
    (item.table, item.name): item.definition for item in _EXPECTED_019_CONSTRAINT_ROWS
}
_EXPECTED_019_FK_KEYS = {
    (item.table, item.name): (item.columns, item.reference_columns)
    for item in _EXPECTED_019_CONSTRAINT_ROWS
    if item.contype == "f"
}

_EXPECTED_019_INDEX_ROWS = (
    _IndexExpectation(
        "evidence_links",
        "idx_evidence_links_e2a_entity_dedup",
        "version_id,span_id,manual_entity_id,evidence_id,ownership_id",
        True,
        "(source_kind = 'manual_okf'::text) AND (manual_entity_id IS NOT NULL)",
    ),
    _IndexExpectation(
        "evidence_links",
        "idx_evidence_links_e2a_relation_dedup",
        "version_id,span_id,manual_relation_id,evidence_id,ownership_id",
        True,
        "(source_kind = 'manual_okf'::text) AND (manual_relation_id IS NOT NULL)",
    ),
    _IndexExpectation("evidence_links", "idx_evidence_links_version", "version_id"),
    _IndexExpectation("evidence_links", "idx_evidence_links_entity", "entity_id"),
    _IndexExpectation("evidence_links", "idx_evidence_links_relation", "relation_id"),
    _IndexExpectation("evidence_links", "idx_evidence_links_span", "span_id"),
    _IndexExpectation(
        "evidence_links",
        "idx_evidence_links_evidence",
        "evidence_id",
        predicate="evidence_id IS NOT NULL",
    ),
    _IndexExpectation(
        "evidence_links", "idx_evidence_links_version_span", "version_id,span_id"
    ),
    _IndexExpectation(
        "evidence_links",
        "idx_evidence_links_version_evidence",
        "version_id,evidence_id",
    ),
    _IndexExpectation(
        "evidence_links", "idx_evidence_links_ownership_id", "ownership_id"
    ),
    _IndexExpectation(
        "evidence_links",
        "idx_evidence_links_ownership_scope",
        "ownership_id,ownership_scope_version_id",
    ),
    _IndexExpectation(
        "evidence_links",
        "idx_evidence_links_manual_entity_owner",
        "ownership_id,manual_entity_id",
    ),
    _IndexExpectation(
        "evidence_links",
        "idx_evidence_links_manual_relation_owner",
        "ownership_id,manual_relation_id",
    ),
    _IndexExpectation(
        "evidence_links",
        "idx_evidence_links_version_evidence_manual_entity",
        "version_id,evidence_id,manual_entity_id",
    ),
    _IndexExpectation(
        "evidence_links",
        "idx_evidence_links_version_evidence_manual_relation",
        "version_id,evidence_id,manual_relation_id",
    ),
    _IndexExpectation(
        "okf_manual_fact_ownership",
        "idx_okf_manual_fact_ownership_document_version",
        "document_id,version_id",
    ),
    _IndexExpectation(
        "okf_manual_fact_ownership",
        "idx_okf_manual_fact_ownership_scope_version",
        "scope_version_id,ownership_id",
    ),
    _IndexExpectation(
        "okf_manual_fact_ownership", "idx_okf_manual_fact_ownership_entity", "entity_id"
    ),
    _IndexExpectation(
        "okf_manual_fact_ownership",
        "idx_okf_manual_fact_ownership_relation",
        "relation_id",
    ),
    _IndexExpectation(
        "okf_manual_evidence_targets",
        "idx_okf_manual_evidence_targets_version_evidence",
        "version_id,evidence_id",
    ),
    _IndexExpectation(
        "okf_manual_evidence_targets",
        "idx_okf_manual_evidence_targets_entity",
        "entity_id",
    ),
    _IndexExpectation(
        "okf_manual_evidence_targets",
        "idx_okf_manual_evidence_targets_relation",
        "relation_id",
    ),
    _IndexExpectation(
        "okf_rebuild_failure_audit",
        "idx_okf_rebuild_failure_audit_occurred_at",
        "occurred_at",
        options="3",
    ),
    _IndexExpectation(
        "okf_rebuild_failure_audit",
        "idx_okf_rebuild_failure_audit_scope",
        "failing_doc_id,failing_version_id",
        predicate="failing_doc_id IS NOT NULL",
    ),
)
_EXPECTED_019_INDEXES = tuple(
    sorted((item.table, item.name) for item in _EXPECTED_019_INDEX_ROWS)
)
_EXPECTED_018_APPEND_ONLY_FUNCTION = _FunctionExpectation(
    name="prevent_okf_rebuild_failure_audit_mutation",
    prokind="f",
    pronargs=0,
    proargtypes="",
    provariadic=0,
    prorettype="trigger",
    proretset=False,
    language="plpgsql",
    source="""BEGIN
    RAISE EXCEPTION 'okf_rebuild_failure_audit is append-only';
END;""",
)
_EXPECTED_018_TRIGGER_ROWS = (
    _TriggerExpectation(
        "okf_rebuild_failure_audit",
        "trg_okf_rebuild_failure_audit_append_only",
        "prevent_okf_rebuild_failure_audit_mutation",
        27,
    ),
    _TriggerExpectation(
        "okf_rebuild_failure_audit",
        "trg_okf_rebuild_failure_audit_no_truncate",
        "prevent_okf_rebuild_failure_audit_mutation",
        34,
    ),
)
_EXPECTED_019_INDEX_DEFINITIONS = {
    (item.table, item.name): _definition(
        f"CREATE {'UNIQUE ' if item.unique else ''}INDEX {item.name} ON {item.table} USING btree ({item.keys.replace(',', ', ')})"
        + (f" WHERE {item.predicate}" if item.predicate else "")
    )
    for item in _EXPECTED_019_INDEX_ROWS
}
_EXPECTED_019_COLUMNS = (
    ("evidence_links", "manual_entity_id", "uuid", "YES", None),
    ("evidence_links", "manual_relation_id", "uuid", "YES", None),
    ("evidence_links", "ownership_id", "uuid", "YES", None),
    ("evidence_links", "ownership_scope_version_id", "uuid", "YES", None),
    ("okf_manual_evidence_targets", "entity_id", "uuid", "YES", None),
    ("okf_manual_evidence_targets", "evidence_id", "uuid", "NO", None),
    ("okf_manual_evidence_targets", "relation_id", "uuid", "YES", None),
    ("okf_manual_evidence_targets", "version_id", "uuid", "NO", None),
    (
        "okf_manual_fact_ownership",
        "scope_version_id",
        "uuid",
        "NO",
        "'00000000-0000-0000-0000-000000000000'::uuid",
    ),
)
