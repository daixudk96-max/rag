-- E2a manual evidence materialization contract.
-- preexisting manual_okf ownership is rejected during a fresh preflight.
-- The one-block state machine deliberately rejects drift before it can issue DDL.
DO $e2a019$
DECLARE
    schema_name pg_catalog.name := pg_catalog.current_schema();
    schema_oid pg_catalog.oid := (
        SELECT pg_catalog.pg_namespace.oid
        FROM pg_catalog.pg_namespace
        WHERE pg_catalog.pg_namespace.nspname = pg_catalog.current_schema()
    );
    final_schema_oid pg_catalog.oid;
    document_versions_oid pg_catalog.oid;
    canonical_spans_oid pg_catalog.oid;
    evidence_oid pg_catalog.oid;
    entities_oid pg_catalog.oid;
    relations_oid pg_catalog.oid;
    evidence_links_oid pg_catalog.oid;
    audit_oid pg_catalog.oid;
    sync_state_oid pg_catalog.oid;
    ownership_oid pg_catalog.oid;
    targets_oid pg_catalog.oid;
    locked_document_versions_oid pg_catalog.oid;
    locked_canonical_spans_oid pg_catalog.oid;
    locked_evidence_oid pg_catalog.oid;
    locked_entities_oid pg_catalog.oid;
    locked_relations_oid pg_catalog.oid;
    locked_evidence_links_oid pg_catalog.oid;
    locked_audit_oid pg_catalog.oid;
    locked_sync_state_oid pg_catalog.oid;
    locked_ownership_oid pg_catalog.oid;
    locked_targets_oid pg_catalog.oid;
    lock_relation_name pg_catalog.name;
    legacy_cascade_oid pg_catalog.oid;
    append_only_function_oid pg_catalog.oid;
    append_only_function_source pg_catalog.text;
    append_only_function_source_actual pg_catalog.text;
    append_only_function_source_expected pg_catalog.text;
    append_only_function_final_oid pg_catalog.oid;
    append_only_function_final_source pg_catalog.text;
    append_only_function_final_shape boolean := false;
    append_only_function_final_source_matches boolean := false;
    append_only_function_final_trigger_shape boolean := false;
    final_row_drift boolean := false;
    fresh_target_drift boolean := false;
    fresh_span_drift boolean := false;
    fresh_evidence_drift boolean := false;
    old_audit_check_body pg_catalog.text;
    final_check_body pg_catalog.text;
    expected_check_body pg_catalog.text;
    e2a_normalize_expression_actual pg_catalog.text;
    e2a_normalize_expression_expected pg_catalog.text;
    e2a_normalize_expression_predicate_actual pg_catalog.text;
    e2a_normalize_expression_predicate_expected pg_catalog.text;
    e2a_normalize_expression_input pg_catalog.text;
    e2a_normalize_expression_output pg_catalog.text;
    e2a_normalize_expression_index integer;
    e2a_normalize_expression_depth integer;
    e2a_normalize_expression_comment_depth integer;
    e2a_normalize_expression_quote pg_catalog.text;
    e2a_normalize_expression_character pg_catalog.text;
    e2a_normalize_expression_next integer;
    e2a_normalize_expression_pending_space boolean;
    e2a_normalize_expression_escape boolean;
    e2a_normalize_expression_tag pg_catalog.text;
    e2a_normalize_expression_side integer;
    e2a_normalize_expression_outer boolean;
    final_check_name pg_catalog.text;
    final_check_table_oid pg_catalog.oid;
    final_check_position integer;
    document_versions_ref pg_catalog.text;
    canonical_spans_ref pg_catalog.text;
    evidence_ref pg_catalog.text;
    entities_ref pg_catalog.text;
    relations_ref pg_catalog.text;
    evidence_links_ref pg_catalog.text;
    audit_ref pg_catalog.text;
    sync_state_ref pg_catalog.text;
    ownership_ref pg_catalog.text;
    targets_ref pg_catalog.text;
    fresh_signature boolean := false;
    final_signature boolean := false;
    base_links_shape boolean := false;
    sync_state_fresh_shape boolean := false;
    legacy_fk_shape boolean := false;
    baseline_indexes_match boolean := false;
    fresh_trigger_shape boolean := false;
    append_only_function_shape boolean := false;
    append_only_function_source_matches boolean := false;
    old_audit_check_matches boolean := false;
    final_inventory_matches boolean := false;
    has_manual_okf boolean := false;
    cstr_record pg_catalog.record;
BEGIN
    schema_name := pg_catalog.current_schema();
    fresh_signature := false;
    final_signature := false;
    IF schema_oid IS NULL THEN
        RAISE EXCEPTION 'e2a_preflight_missing_current_schema';
    END IF;

    SELECT class_row.oid INTO document_versions_oid
    FROM pg_catalog.pg_class AS class_row
    WHERE class_row.relnamespace = schema_oid
      AND class_row.relname = 'document_versions'
      AND class_row.relkind IN ('r', 'p');
    SELECT class_row.oid INTO canonical_spans_oid
    FROM pg_catalog.pg_class AS class_row
    WHERE class_row.relnamespace = schema_oid
      AND class_row.relname = 'canonical_spans'
      AND class_row.relkind IN ('r', 'p');
    SELECT class_row.oid INTO evidence_oid
    FROM pg_catalog.pg_class AS class_row
    WHERE class_row.relnamespace = schema_oid
      AND class_row.relname = 'evidence'
      AND class_row.relkind IN ('r', 'p');
    SELECT class_row.oid INTO entities_oid
    FROM pg_catalog.pg_class AS class_row
    WHERE class_row.relnamespace = schema_oid
      AND class_row.relname = 'entities'
      AND class_row.relkind IN ('r', 'p');
    SELECT class_row.oid INTO relations_oid
    FROM pg_catalog.pg_class AS class_row
    WHERE class_row.relnamespace = schema_oid
      AND class_row.relname = 'relations'
      AND class_row.relkind IN ('r', 'p');
    SELECT class_row.oid INTO evidence_links_oid
    FROM pg_catalog.pg_class AS class_row
    WHERE class_row.relnamespace = schema_oid
      AND class_row.relname = 'evidence_links'
      AND class_row.relkind IN ('r', 'p');
    SELECT class_row.oid INTO audit_oid
    FROM pg_catalog.pg_class AS class_row
    WHERE class_row.relnamespace = schema_oid
      AND class_row.relname = 'okf_rebuild_failure_audit'
      AND class_row.relkind IN ('r', 'p');
    SELECT class_row.oid INTO sync_state_oid
    FROM pg_catalog.pg_class AS class_row
    WHERE class_row.relnamespace = schema_oid
      AND class_row.relname = 'okf_sync_state'
      AND class_row.relkind IN ('r', 'p');
    SELECT class_row.oid INTO ownership_oid
    FROM pg_catalog.pg_class AS class_row
    WHERE class_row.relnamespace = schema_oid
      AND class_row.relname = 'okf_manual_fact_ownership'
      AND class_row.relkind IN ('r', 'p');
    SELECT class_row.oid INTO targets_oid
    FROM pg_catalog.pg_class AS class_row
    WHERE class_row.relnamespace = schema_oid
      AND class_row.relname = 'okf_manual_evidence_targets'
      AND class_row.relkind IN ('r', 'p');

    IF document_versions_oid IS NULL OR canonical_spans_oid IS NULL
       OR evidence_oid IS NULL OR entities_oid IS NULL OR relations_oid IS NULL
       OR evidence_links_oid IS NULL OR audit_oid IS NULL OR sync_state_oid IS NULL THEN
        RAISE EXCEPTION 'e2a_preflight_missing_required_table';
    END IF;

    -- Lock every affected relation that exists, in catalog-name order, before
    -- shape or data classification.  The post-lock OID pass closes DDL races.
    FOR lock_relation_name IN
        SELECT class_row.relname
        FROM pg_catalog.pg_class AS class_row
        WHERE class_row.relnamespace = schema_oid
          AND class_row.relkind IN ('r', 'p')
          AND class_row.relname = ANY (ARRAY[
              'canonical_spans', 'document_versions', 'entities', 'evidence',
              'evidence_links', 'okf_manual_evidence_targets',
              'okf_manual_fact_ownership', 'okf_rebuild_failure_audit', 'okf_sync_state',
              'relations'
          ])
        ORDER BY class_row.relname
    LOOP
        EXECUTE pg_catalog.format(
            'LOCK TABLE %I.%I IN ACCESS EXCLUSIVE MODE', schema_name, lock_relation_name
        );
    END LOOP;

    locked_document_versions_oid := document_versions_oid;
    locked_canonical_spans_oid := canonical_spans_oid;
    locked_evidence_oid := evidence_oid;
    locked_entities_oid := entities_oid;
    locked_relations_oid := relations_oid;
    locked_evidence_links_oid := evidence_links_oid;
    locked_audit_oid := audit_oid;
    locked_sync_state_oid := sync_state_oid;
    locked_ownership_oid := ownership_oid;
    locked_targets_oid := targets_oid;
    SELECT namespace_row.oid INTO final_schema_oid
    FROM pg_catalog.pg_namespace AS namespace_row
    WHERE namespace_row.nspname = pg_catalog.current_schema();
    IF final_schema_oid IS DISTINCT FROM schema_oid THEN
        RAISE EXCEPTION 'e2a_preflight_relation_changed';
    END IF;
    schema_oid := final_schema_oid;
    SELECT class_row.oid INTO document_versions_oid FROM pg_catalog.pg_class AS class_row WHERE class_row.relnamespace = schema_oid AND class_row.relname = 'document_versions' AND class_row.relkind IN ('r', 'p');
    SELECT class_row.oid INTO canonical_spans_oid FROM pg_catalog.pg_class AS class_row WHERE class_row.relnamespace = schema_oid AND class_row.relname = 'canonical_spans' AND class_row.relkind IN ('r', 'p');
    SELECT class_row.oid INTO evidence_oid FROM pg_catalog.pg_class AS class_row WHERE class_row.relnamespace = schema_oid AND class_row.relname = 'evidence' AND class_row.relkind IN ('r', 'p');
    SELECT class_row.oid INTO entities_oid FROM pg_catalog.pg_class AS class_row WHERE class_row.relnamespace = schema_oid AND class_row.relname = 'entities' AND class_row.relkind IN ('r', 'p');
    SELECT class_row.oid INTO relations_oid FROM pg_catalog.pg_class AS class_row WHERE class_row.relnamespace = schema_oid AND class_row.relname = 'relations' AND class_row.relkind IN ('r', 'p');
    SELECT class_row.oid INTO evidence_links_oid FROM pg_catalog.pg_class AS class_row WHERE class_row.relnamespace = schema_oid AND class_row.relname = 'evidence_links' AND class_row.relkind IN ('r', 'p');
    SELECT class_row.oid INTO audit_oid FROM pg_catalog.pg_class AS class_row WHERE class_row.relnamespace = schema_oid AND class_row.relname = 'okf_rebuild_failure_audit' AND class_row.relkind IN ('r', 'p');
    SELECT class_row.oid INTO sync_state_oid FROM pg_catalog.pg_class AS class_row WHERE class_row.relnamespace = schema_oid AND class_row.relname = 'okf_sync_state' AND class_row.relkind IN ('r', 'p');
    SELECT class_row.oid INTO ownership_oid FROM pg_catalog.pg_class AS class_row WHERE class_row.relnamespace = schema_oid AND class_row.relname = 'okf_manual_fact_ownership' AND class_row.relkind IN ('r', 'p');
    SELECT class_row.oid INTO targets_oid FROM pg_catalog.pg_class AS class_row WHERE class_row.relnamespace = schema_oid AND class_row.relname = 'okf_manual_evidence_targets' AND class_row.relkind IN ('r', 'p');
    IF document_versions_oid IS DISTINCT FROM locked_document_versions_oid
       OR canonical_spans_oid IS DISTINCT FROM locked_canonical_spans_oid
       OR evidence_oid IS DISTINCT FROM locked_evidence_oid
       OR entities_oid IS DISTINCT FROM locked_entities_oid
       OR relations_oid IS DISTINCT FROM locked_relations_oid
       OR evidence_links_oid IS DISTINCT FROM locked_evidence_links_oid
       OR audit_oid IS DISTINCT FROM locked_audit_oid
       OR sync_state_oid IS DISTINCT FROM locked_sync_state_oid
       OR ownership_oid IS DISTINCT FROM locked_ownership_oid
       OR targets_oid IS DISTINCT FROM locked_targets_oid THEN
        RAISE EXCEPTION 'e2a_preflight_relation_changed';
    END IF;

    document_versions_ref := pg_catalog.format('%I.%I', schema_name, 'document_versions');
    canonical_spans_ref := pg_catalog.format('%I.%I', schema_name, 'canonical_spans');
    evidence_ref := pg_catalog.format('%I.%I', schema_name, 'evidence');
    entities_ref := pg_catalog.format('%I.%I', schema_name, 'entities');
    relations_ref := pg_catalog.format('%I.%I', schema_name, 'relations');
    evidence_links_ref := pg_catalog.format('%I.%I', schema_name, 'evidence_links');
    audit_ref := pg_catalog.format('%I.%I', schema_name, 'okf_rebuild_failure_audit');
    sync_state_ref := pg_catalog.format('%I.%I', schema_name, 'okf_sync_state');
    ownership_ref := pg_catalog.format('%I.%I', schema_name, 'okf_manual_fact_ownership');
    targets_ref := pg_catalog.format('%I.%I', schema_name, 'okf_manual_evidence_targets');

    -- Read-only base-table shape classification.  The source_kind default is
    -- intentionally absent in the 001--018 fresh signature.
    SELECT NOT EXISTS (
        WITH expected(column_name, type_name, required_not_null, default_expression) AS (
            VALUES
                ('evidence_link_id', 'uuid', true, NULL::text),
                ('version_id', 'uuid', true, NULL::text),
                ('entity_id', 'uuid', false, NULL::text),
                ('relation_id', 'uuid', false, NULL::text),
                ('span_id', 'uuid', true, NULL::text),
                ('source_kind', 'text', true, NULL::text),
                ('confidence_score', 'double precision', false, NULL::text),
                ('created_at', 'timestamp with time zone', true, 'now()'),
                ('evidence_id', 'uuid', false, NULL::text)
        ), actual AS (
            SELECT attribute_row.attname,
                   pg_catalog.format_type(attribute_row.atttypid, attribute_row.atttypmod),
                   attribute_row.attnotnull,
                   COALESCE(
                       pg_catalog.regexp_replace(
                           pg_catalog.pg_get_expr(default_row.adbin, default_row.adrelid),
                           '^pg_catalog\.?now\(\)$', 'now()'
                       ),
                       pg_catalog.pg_get_expr(default_row.adbin, default_row.adrelid)
                   ) AS pg_get_expr
            FROM pg_catalog.pg_attribute AS attribute_row
            LEFT JOIN pg_catalog.pg_attrdef AS default_row
              ON default_row.adrelid = attribute_row.attrelid
             AND default_row.adnum = attribute_row.attnum
            WHERE attribute_row.attrelid = evidence_links_oid
              AND attribute_row.attnum > 0 AND NOT attribute_row.attisdropped
        )
        SELECT 1
        FROM expected
        FULL JOIN actual ON actual.attname = expected.column_name
        WHERE actual.attname IS NULL OR expected.column_name IS NULL
           OR actual.format_type IS DISTINCT FROM expected.type_name
           OR actual.attnotnull IS DISTINCT FROM expected.required_not_null
           OR actual.pg_get_expr IS DISTINCT FROM expected.default_expression
    ) INTO base_links_shape;

    -- Fresh 001--018 schemas must retain 015's exact sync-state inventory
    -- and its path-only primary-key shape.  This excludes altered inherited
    -- schemas from the fresh DDL branch before any materialization DDL runs.
    SELECT NOT EXISTS (
        WITH expected(column_name, type_name, required_not_null, default_expression) AS (
            VALUES
                ('okf_file_path', 'text', true, NULL::text),
                ('doc_id', 'uuid', false, NULL::text),
                ('version_id', 'uuid', false, NULL::text),
                ('source_checksum', 'text', true, NULL::text),
                ('canonical_hash', 'text', true, NULL::text),
                ('status', 'text', true, NULL::text),
                ('last_synced_at', 'timestamp with time zone', true, 'now()')
        ), actual AS (
            SELECT attribute_row.attname,
                   pg_catalog.format_type(attribute_row.atttypid, attribute_row.atttypmod),
                   attribute_row.attnotnull,
                   COALESCE(
                       pg_catalog.regexp_replace(
                           pg_catalog.pg_get_expr(default_row.adbin, default_row.adrelid),
                           '^pg_catalog\.?now\(\)$', 'now()'
                       ),
                       pg_catalog.pg_get_expr(default_row.adbin, default_row.adrelid)
                   ) AS pg_get_expr
            FROM pg_catalog.pg_attribute AS attribute_row
            LEFT JOIN pg_catalog.pg_attrdef AS default_row
              ON default_row.adrelid = attribute_row.attrelid
             AND default_row.adnum = attribute_row.attnum
            WHERE attribute_row.attrelid = sync_state_oid
              AND attribute_row.attnum > 0 AND NOT attribute_row.attisdropped
        )
        SELECT 1
        FROM expected
        FULL JOIN actual ON actual.attname = expected.column_name
        WHERE actual.attname IS NULL OR expected.column_name IS NULL
           OR actual.format_type IS DISTINCT FROM expected.type_name
           OR actual.attnotnull IS DISTINCT FROM expected.required_not_null
           OR actual.pg_get_expr IS DISTINCT FROM expected.default_expression
    )
    AND (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_constraint AS constraint_row
         WHERE constraint_row.conrelid = sync_state_oid
           AND constraint_row.contype = 'p') = 1
    AND EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint AS constraint_row
        WHERE constraint_row.conrelid = sync_state_oid
          AND constraint_row.contype = 'p'
          AND constraint_row.conkey IS NOT DISTINCT FROM ARRAY[
              (SELECT attribute_row.attnum
               FROM pg_catalog.pg_attribute AS attribute_row
               WHERE attribute_row.attrelid = sync_state_oid
                 AND attribute_row.attname = 'okf_file_path'
                 AND attribute_row.attnum > 0 AND NOT attribute_row.attisdropped)
          ]
    ) INTO sync_state_fresh_shape;

    SELECT class_row.oid INTO ownership_oid
    FROM pg_catalog.pg_class AS class_row
    WHERE class_row.relnamespace = schema_oid
      AND class_row.relname = 'okf_manual_fact_ownership'
      AND class_row.relkind IN ('r', 'p');
    SELECT class_row.oid INTO targets_oid
    FROM pg_catalog.pg_class AS class_row
    WHERE class_row.relnamespace = schema_oid
      AND class_row.relname = 'okf_manual_evidence_targets'
      AND class_row.relkind IN ('r', 'p');

    -- 005's three ordinary btree indexes are part of the fresh contract and
    -- must be reused, never rebuilt under migration 019.
    SELECT NOT EXISTS (
        WITH expected(index_name, table_oid, columns, required_unique, predicate, options) AS (
            VALUES
                ('idx_evidence_links_version', evidence_links_oid, ARRAY['version_id'], false, NULL::text, ARRAY[0]::smallint[]),
                ('idx_evidence_links_entity', evidence_links_oid, ARRAY['entity_id'], false, NULL::text, ARRAY[0]::smallint[]),
                ('idx_evidence_links_relation', evidence_links_oid, ARRAY['relation_id'], false, NULL::text, ARRAY[0]::smallint[]),
                ('idx_evidence_links_span', evidence_links_oid, ARRAY['span_id'], false, NULL::text, ARRAY[0]::smallint[]),
                ('idx_evidence_links_evidence', evidence_links_oid, ARRAY['evidence_id'], false, '(evidence_id IS NOT NULL)', ARRAY[0]::smallint[]),
                ('idx_okf_rebuild_failure_audit_occurred_at', audit_oid, ARRAY['occurred_at'], false, NULL::text, ARRAY[3]::smallint[]),
                ('idx_okf_rebuild_failure_audit_scope', audit_oid, ARRAY['failing_doc_id', 'failing_version_id'], false, '(failing_doc_id IS NOT NULL)', ARRAY[0, 0]::smallint[])
        )
        SELECT 1
        FROM expected
        LEFT JOIN pg_catalog.pg_class AS index_class
          ON index_class.relnamespace = schema_oid
         AND index_class.relname = expected.index_name
        LEFT JOIN pg_catalog.pg_index AS index_row
          ON index_row.indexrelid = index_class.oid
        LEFT JOIN pg_catalog.pg_am AS index_method
          ON index_method.oid = index_class.relam
        WHERE index_row.indexrelid IS NULL
           OR index_row.indrelid <> expected.table_oid
           OR index_row.indisunique IS DISTINCT FROM expected.required_unique
           OR NOT index_row.indisvalid OR NOT index_row.indisready OR NOT index_row.indislive
           OR index_row.indisexclusion
           OR index_method.amname IS DISTINCT FROM 'btree'
           OR index_row.indnkeyatts <> pg_catalog.cardinality(expected.columns)
           OR index_row.indnatts <> pg_catalog.cardinality(expected.columns)
           OR index_row.indexprs IS NOT NULL
           OR EXISTS (
                SELECT 1
                FROM pg_catalog.unnest(expected.columns) WITH ORDINALITY
                    AS column_row(column_name, ordinality)
                JOIN pg_catalog.pg_attribute AS attribute_row
                  ON attribute_row.attrelid = expected.table_oid
                 AND attribute_row.attname = column_row.column_name
                WHERE index_row.indkey[column_row.ordinality - 1]
                    IS DISTINCT FROM attribute_row.attnum
                   OR index_row.indoption[column_row.ordinality - 1]
                    IS DISTINCT FROM expected.options[column_row.ordinality]
           )
           OR EXISTS (
                SELECT 1
                FROM pg_catalog.unnest(expected.columns) WITH ORDINALITY
                    AS column_row(column_name, ordinality)
                JOIN pg_catalog.pg_attribute AS attribute_row
                  ON attribute_row.attrelid = expected.table_oid
                 AND attribute_row.attname = column_row.column_name
                JOIN pg_catalog.pg_opclass AS opclass_row
                  ON opclass_row.oid = index_row.indclass[column_row.ordinality - 1]
                WHERE index_row.indcollation[column_row.ordinality - 1]
                          IS DISTINCT FROM attribute_row.attcollation
                   OR NOT opclass_row.opcdefault
           )
           OR (expected.predicate IS NULL AND index_row.indpred IS NOT NULL)
           OR (expected.predicate IS NOT NULL AND pg_catalog.pg_get_expr(index_row.indpred, index_row.indrelid, false) IS DISTINCT FROM expected.predicate)
    ) INTO baseline_indexes_match;

    -- Exactly the five inherited evidence_links foreign-key identities are
    -- permitted during a fresh transition.  Either CASCADE or NO ACTION is
    -- accepted at preflight; only the approved CASCADE instances are dropped.
    SELECT NOT EXISTS (
        WITH expected(source_oid, target_oid, source_columns, target_columns) AS (
            VALUES
                (evidence_links_oid, document_versions_oid, ARRAY['version_id'], ARRAY['version_id']),
                (evidence_links_oid, canonical_spans_oid, ARRAY['span_id'], ARRAY['span_id']),
                (evidence_links_oid, evidence_oid, ARRAY['evidence_id'], ARRAY['evidence_id']),
                (evidence_links_oid, entities_oid, ARRAY['entity_id'], ARRAY['entity_id']),
                (evidence_links_oid, relations_oid, ARRAY['relation_id'], ARRAY['relation_id'])
        )
        SELECT 1
        FROM expected
        WHERE (SELECT pg_catalog.count(*)
               FROM pg_catalog.pg_constraint AS constraint_row
               WHERE constraint_row.conrelid = expected.source_oid
                 AND constraint_row.confrelid = expected.target_oid
                 AND constraint_row.contype = 'f'
                 AND constraint_row.conkey = ARRAY(
                     SELECT attribute_row.attnum
                     FROM pg_catalog.unnest(expected.source_columns) WITH ORDINALITY
                         AS column_row(column_name, ordinality)
                     JOIN pg_catalog.pg_attribute AS attribute_row
                       ON attribute_row.attrelid = expected.source_oid
                      AND attribute_row.attname = column_row.column_name
                     ORDER BY column_row.ordinality
                 )
                 AND constraint_row.confkey = ARRAY(
                     SELECT attribute_row.attnum
                     FROM pg_catalog.unnest(expected.target_columns) WITH ORDINALITY
                         AS column_row(column_name, ordinality)
                     JOIN pg_catalog.pg_attribute AS attribute_row
                       ON attribute_row.attrelid = expected.target_oid
                      AND attribute_row.attname = column_row.column_name
                     ORDER BY column_row.ordinality
                 )
              ) <> 1
           OR EXISTS (
               SELECT 1
               FROM pg_catalog.pg_constraint AS constraint_row
               WHERE constraint_row.conrelid = expected.source_oid
                 AND constraint_row.confrelid = expected.target_oid
                 AND constraint_row.contype = 'f'
                 AND constraint_row.conkey = ARRAY(
                     SELECT attribute_row.attnum FROM pg_catalog.unnest(expected.source_columns) WITH ORDINALITY AS column_row(column_name, ordinality)
                     JOIN pg_catalog.pg_attribute AS attribute_row ON attribute_row.attrelid = expected.source_oid AND attribute_row.attname = column_row.column_name ORDER BY column_row.ordinality
                 )
                 AND constraint_row.confkey = ARRAY(
                     SELECT attribute_row.attnum FROM pg_catalog.unnest(expected.target_columns) WITH ORDINALITY AS column_row(column_name, ordinality)
                     JOIN pg_catalog.pg_attribute AS attribute_row ON attribute_row.attrelid = expected.target_oid AND attribute_row.attname = column_row.column_name ORDER BY column_row.ordinality
                 )
                 AND (NOT constraint_row.convalidated
                      OR constraint_row.confmatchtype <> 's'
                      OR constraint_row.confupdtype <> 'a'
                      OR constraint_row.condeferrable
                      OR constraint_row.condeferred
                      OR NOT (constraint_row.confdeltype IN ('c', 'a')))
           )
    ) INTO legacy_fk_shape;

    -- The append-only trigger function is a separately attested predecessor
    -- artifact.  Its source is normalized by the fail-closed lexer below.
    SELECT pg_catalog.count(*) = 1
       AND NOT EXISTS (
           SELECT 1
           FROM pg_catalog.pg_proc AS procedure_row
           JOIN pg_catalog.pg_namespace AS procedure_schema
             ON procedure_schema.oid = procedure_row.pronamespace
           JOIN pg_catalog.pg_language AS language_row
             ON language_row.oid = procedure_row.prolang
           WHERE procedure_schema.nspname = schema_name
             AND procedure_row.proname = 'prevent_okf_rebuild_failure_audit_mutation'
             AND (procedure_row.prokind IS DISTINCT FROM 'f'
                  OR procedure_row.pronargs IS DISTINCT FROM 0
                  OR procedure_row.proargtypes IS DISTINCT FROM ''::pg_catalog.oidvector
                  OR procedure_row.provariadic IS DISTINCT FROM 0::pg_catalog.oid
                  OR procedure_row.prorettype IS DISTINCT FROM 'trigger'::pg_catalog.regtype
                  OR procedure_row.proretset
                  OR language_row.lanname IS DISTINCT FROM 'plpgsql')
       ) INTO append_only_function_shape
    FROM pg_catalog.pg_proc AS procedure_row
    JOIN pg_catalog.pg_namespace AS procedure_schema
      ON procedure_schema.oid = procedure_row.pronamespace
    WHERE procedure_schema.nspname = schema_name
      AND procedure_row.proname = 'prevent_okf_rebuild_failure_audit_mutation';
    SELECT procedure_row.oid, procedure_row.prosrc
      INTO append_only_function_oid, append_only_function_source
    FROM pg_catalog.pg_proc AS procedure_row
    JOIN pg_catalog.pg_namespace AS procedure_schema
      ON procedure_schema.oid = procedure_row.pronamespace
    WHERE procedure_schema.nspname = schema_name
      AND procedure_row.proname = 'prevent_okf_rebuild_failure_audit_mutation'
    ORDER BY procedure_row.oid
    LIMIT 1;

    -- Retained 018 append-only triggers are part of the exact fresh signature.
    SELECT NOT EXISTS (
        WITH expected(trigger_name, expected_type) AS (
            VALUES
                ('trg_okf_rebuild_failure_audit_append_only', 27::smallint),
                ('trg_okf_rebuild_failure_audit_no_truncate', 34::smallint)
        )
        SELECT 1
        FROM expected
        LEFT JOIN pg_catalog.pg_trigger AS trigger_row
          ON trigger_row.tgrelid = audit_oid
         AND trigger_row.tgname = expected.trigger_name
        LEFT JOIN pg_catalog.pg_proc AS procedure_row
          ON procedure_row.oid = trigger_row.tgfoid
        LEFT JOIN pg_catalog.pg_namespace AS procedure_schema
          ON procedure_schema.oid = procedure_row.pronamespace
        WHERE trigger_row.oid IS NULL
           OR procedure_schema.nspname IS DISTINCT FROM schema_name
           OR procedure_row.proname IS DISTINCT FROM 'prevent_okf_rebuild_failure_audit_mutation'
           OR trigger_row.tgfoid IS DISTINCT FROM append_only_function_oid
           OR trigger_row.tgtype IS DISTINCT FROM expected.expected_type
           OR trigger_row.tgenabled IS DISTINCT FROM 'O'
           OR trigger_row.tgisinternal
           OR trigger_row.tgargs IS DISTINCT FROM ''::bytea
           OR trigger_row.tgqual IS NOT NULL
           OR trigger_row.tgattr IS DISTINCT FROM ''::int2vector
           OR trigger_row.tgconstraint <> 0
           OR (
               SELECT pg_catalog.count(*)
               FROM pg_catalog.pg_trigger AS observed_trigger
               WHERE observed_trigger.tgrelid = audit_oid
           ) <> (
               SELECT pg_catalog.count(*)
               FROM expected
           )
    ) INTO fresh_trigger_shape;

    -- Compare 018's deparsed five-phase CHECK with the same fail-closed lexer
    -- used by the final branch; pg_get_expr may add redundant outer wrappers.
    SELECT pg_catalog.pg_get_expr(
        constraint_row.conbin, constraint_row.conrelid, false
    ) INTO old_audit_check_body
    FROM pg_catalog.pg_constraint AS constraint_row
    WHERE constraint_row.conrelid = audit_oid
      AND constraint_row.conname = 'chk_okf_rebuild_failure_audit_phase'
      AND constraint_row.contype = 'c'
      AND constraint_row.convalidated;
    old_audit_check_matches := false;
    append_only_function_source_matches := false;
    IF old_audit_check_body IS NOT NULL AND append_only_function_source IS NOT NULL THEN
        FOR e2a_normalize_expression_side IN 1..4 LOOP
            e2a_normalize_expression_input := CASE e2a_normalize_expression_side
                WHEN 1 THEN append_only_function_source
                WHEN 2 THEN $e2a_018_append_only$BEGIN RAISE EXCEPTION 'okf_rebuild_failure_audit is append-only'; END;$e2a_018_append_only$
                WHEN 3 THEN old_audit_check_body
                ELSE $e2a_018_phase$failure_phase = ANY (ARRAY['target_validation'::text, 'scope_lock'::text, 'span_reconciliation'::text, 'success_log_write'::text, 'transaction_commit'::text])$e2a_018_phase$
            END;
            e2a_normalize_expression_output := '';
            e2a_normalize_expression_index := 1;
            e2a_normalize_expression_depth := 0;
            e2a_normalize_expression_pending_space := false;
            WHILE e2a_normalize_expression_index <= pg_catalog.length(e2a_normalize_expression_input) LOOP
                e2a_normalize_expression_character := pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index, 1);
                IF e2a_normalize_expression_character IN (' ', E'\t', E'\n', E'\r', E'\f') THEN
                    e2a_normalize_expression_pending_space := e2a_normalize_expression_output <> '';
                    e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                ELSIF pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index, 2) = '--' THEN
                    e2a_normalize_expression_index := e2a_normalize_expression_index + 2;
                    WHILE e2a_normalize_expression_index <= pg_catalog.length(e2a_normalize_expression_input)
                          AND pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index, 1) NOT IN (E'\n', E'\r') LOOP
                        e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                    END LOOP;
                    e2a_normalize_expression_pending_space := e2a_normalize_expression_output <> '';
                ELSIF pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index, 2) = '/*' THEN
                    e2a_normalize_expression_comment_depth := 1;
                    e2a_normalize_expression_index := e2a_normalize_expression_index + 2;
                    WHILE e2a_normalize_expression_index <= pg_catalog.length(e2a_normalize_expression_input)
                          AND e2a_normalize_expression_comment_depth > 0 LOOP
                        IF pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index, 2) = '/*' THEN
                            e2a_normalize_expression_comment_depth := e2a_normalize_expression_comment_depth + 1;
                            e2a_normalize_expression_index := e2a_normalize_expression_index + 2;
                        ELSIF pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index, 2) = '*/' THEN
                            e2a_normalize_expression_comment_depth := e2a_normalize_expression_comment_depth - 1;
                            e2a_normalize_expression_index := e2a_normalize_expression_index + 2;
                        ELSE
                            e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                        END IF;
                    END LOOP;
                    IF e2a_normalize_expression_comment_depth <> 0 THEN
                        RAISE EXCEPTION 'e2a_preflight_audit_check_drift';
                    END IF;
                    e2a_normalize_expression_pending_space := e2a_normalize_expression_output <> '';
                ELSIF pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index, 2) = '*/' THEN
                    RAISE EXCEPTION 'e2a_preflight_audit_check_drift';
                ELSIF e2a_normalize_expression_character = '$'
                        AND (e2a_normalize_expression_index = 1
                            OR pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index - 1, 1) ~ '^[[:ascii:]]$'
                            AND pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index - 1, 1) !~ '^[A-Za-z0-9_$]$') THEN
                    e2a_normalize_expression_tag := substring(
                        pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index)
                        FROM '^\$(?:[A-Za-z_][A-Za-z_0-9]*)?\$'
                    );
                    IF e2a_normalize_expression_tag IS NULL THEN
                        IF substring(
                            pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index)
                            FROM '^\$[0-9][A-Za-z_0-9]*\$'
                        ) IS NOT NULL
                        OR substring(
                            pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index)
                            FROM '^\$[A-Za-z_0-9]'
                        ) IS NOT NULL
                        OR substring(
                            pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index)
                            FROM '^\$[^[:ascii:]]'
                        ) IS NOT NULL
                        OR substring(
                            pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index)
                            FROM '^\$[A-Za-z_][A-Za-z_0-9]*[^[:ascii:]]'
                        ) IS NOT NULL THEN
                            RAISE EXCEPTION 'e2a_preflight_audit_check_drift';
                        END IF;
                        e2a_normalize_expression_output := e2a_normalize_expression_output || '$';
                        e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                    ELSE
                        e2a_normalize_expression_next := position(
                            e2a_normalize_expression_tag IN pg_catalog.substr(
                                e2a_normalize_expression_input,
                                e2a_normalize_expression_index + pg_catalog.length(e2a_normalize_expression_tag)
                            )
                        );
                        IF e2a_normalize_expression_next = 0 THEN
                            RAISE EXCEPTION 'e2a_preflight_audit_check_drift';
                        END IF;
                        e2a_normalize_expression_output := e2a_normalize_expression_output
                            || pg_catalog.substr(
                                e2a_normalize_expression_input,
                                e2a_normalize_expression_index,
                                (2 * pg_catalog.length(e2a_normalize_expression_tag))
                                + e2a_normalize_expression_next - 1
                            );
                        e2a_normalize_expression_index := e2a_normalize_expression_index
                            + (2 * pg_catalog.length(e2a_normalize_expression_tag))
                            + e2a_normalize_expression_next - 1;
                    END IF;
                ELSIF e2a_normalize_expression_character IN ('''', '"') THEN
                    e2a_normalize_expression_quote := e2a_normalize_expression_character;
                    e2a_normalize_expression_escape := e2a_normalize_expression_quote = ''''
                        AND e2a_normalize_expression_index > 1
                        AND pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index - 1, 1) IN ('E', 'e')
                        AND (e2a_normalize_expression_index = 2
                            OR pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index - 2, 1) ~ '^[[:ascii:]]$'
                            AND pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index - 2, 1) !~ '^[A-Za-z0-9_$]$');
                    e2a_normalize_expression_output := e2a_normalize_expression_output || e2a_normalize_expression_character;
                    e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                    LOOP
                        IF e2a_normalize_expression_index > pg_catalog.length(e2a_normalize_expression_input) THEN
                            RAISE EXCEPTION 'e2a_preflight_audit_check_drift';
                        END IF;
                        e2a_normalize_expression_character := pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index, 1);
                        e2a_normalize_expression_output := e2a_normalize_expression_output || e2a_normalize_expression_character;
                        IF e2a_normalize_expression_escape AND e2a_normalize_expression_character = E'\\' THEN
                            IF e2a_normalize_expression_index = pg_catalog.length(e2a_normalize_expression_input) THEN
                                RAISE EXCEPTION 'e2a_preflight_audit_check_drift';
                            END IF;
                            e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                            e2a_normalize_expression_output := e2a_normalize_expression_output || pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index, 1);
                        ELSIF e2a_normalize_expression_character = e2a_normalize_expression_quote THEN
                            IF pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index + 1, 1) = e2a_normalize_expression_quote THEN
                                e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                                e2a_normalize_expression_output := e2a_normalize_expression_output || e2a_normalize_expression_quote;
                            ELSE
                                e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                                EXIT;
                            END IF;
                        END IF;
                        e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                    END LOOP;
                ELSE
                    IF e2a_normalize_expression_character = '(' THEN
                        e2a_normalize_expression_depth := e2a_normalize_expression_depth + 1;
                    ELSIF e2a_normalize_expression_character = ')' THEN
                        e2a_normalize_expression_depth := e2a_normalize_expression_depth - 1;
                        IF e2a_normalize_expression_depth < 0 THEN
                            RAISE EXCEPTION 'e2a_preflight_audit_check_drift';
                        END IF;
                    END IF;
                    IF e2a_normalize_expression_pending_space
                       AND (e2a_normalize_expression_output ~ '[A-Za-z0-9_$]$'
                            OR e2a_normalize_expression_output ~ '[^[:ascii:]]$')
                       AND (e2a_normalize_expression_character ~ '^[A-Za-z0-9_$]$'
                            OR e2a_normalize_expression_character ~ '^[^[:ascii:]]$') THEN
                        e2a_normalize_expression_output := e2a_normalize_expression_output || ' ';
                    END IF;
                    e2a_normalize_expression_pending_space := false;
                    e2a_normalize_expression_output := e2a_normalize_expression_output || e2a_normalize_expression_character;
                    e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                END IF;
            END LOOP;
            IF e2a_normalize_expression_depth <> 0 THEN
                RAISE EXCEPTION 'e2a_preflight_audit_check_drift';
            END IF;
            -- Re-lex the normalized bytes before each strip: literal, quoted,
            -- dollar, and comment parentheses cannot close an outer wrapper.
            WHILE pg_catalog.left(e2a_normalize_expression_output, 1) = '('
              AND pg_catalog.right(e2a_normalize_expression_output, 1) = ')'
              AND pg_catalog.length(e2a_normalize_expression_output) > 2 LOOP
                e2a_normalize_expression_outer := true;
                e2a_normalize_expression_depth := 0;
                e2a_normalize_expression_index := 1;
                WHILE e2a_normalize_expression_index
                      <= pg_catalog.length(e2a_normalize_expression_output) LOOP
                    e2a_normalize_expression_character := pg_catalog.substr(
                        e2a_normalize_expression_output,
                        e2a_normalize_expression_index,
                        1
                    );
                    IF pg_catalog.substr(
                        e2a_normalize_expression_output,
                        e2a_normalize_expression_index,
                        2
                    ) = '--' THEN
                        e2a_normalize_expression_index := e2a_normalize_expression_index + 2;
                        WHILE e2a_normalize_expression_index
                              <= pg_catalog.length(e2a_normalize_expression_output)
                          AND pg_catalog.substr(
                              e2a_normalize_expression_output,
                              e2a_normalize_expression_index,
                              1
                          ) NOT IN (E'\n', E'\r') LOOP
                            e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                        END LOOP;
                    ELSIF pg_catalog.substr(
                        e2a_normalize_expression_output,
                        e2a_normalize_expression_index,
                        2
                    ) = '/*' THEN
                        e2a_normalize_expression_comment_depth := 1;
                        e2a_normalize_expression_index := e2a_normalize_expression_index + 2;
                        WHILE e2a_normalize_expression_index
                              <= pg_catalog.length(e2a_normalize_expression_output)
                          AND e2a_normalize_expression_comment_depth > 0 LOOP
                            IF pg_catalog.substr(
                                e2a_normalize_expression_output,
                                e2a_normalize_expression_index,
                                2
                            ) = '/*' THEN
                                e2a_normalize_expression_comment_depth := e2a_normalize_expression_comment_depth + 1;
                                e2a_normalize_expression_index := e2a_normalize_expression_index + 2;
                            ELSIF pg_catalog.substr(
                                e2a_normalize_expression_output,
                                e2a_normalize_expression_index,
                                2
                            ) = '*/' THEN
                                e2a_normalize_expression_comment_depth := e2a_normalize_expression_comment_depth - 1;
                                e2a_normalize_expression_index := e2a_normalize_expression_index + 2;
                            ELSE
                                e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                            END IF;
                        END LOOP;
                        IF e2a_normalize_expression_comment_depth <> 0 THEN
                            RAISE EXCEPTION 'e2a_preflight_audit_check_drift';
                        END IF;
                    ELSIF pg_catalog.substr(
                        e2a_normalize_expression_output,
                        e2a_normalize_expression_index,
                        2
                    ) = '*/' THEN
                        RAISE EXCEPTION 'e2a_preflight_audit_check_drift';
                    ELSIF e2a_normalize_expression_character = '$'
                      AND (e2a_normalize_expression_index = 1
                        OR pg_catalog.substr(
                            e2a_normalize_expression_output,
                            e2a_normalize_expression_index - 1,
                            1
                        ) ~ '^[[:ascii:]]$'
                        AND pg_catalog.substr(
                            e2a_normalize_expression_output,
                            e2a_normalize_expression_index - 1,
                            1
                        ) !~ '^[A-Za-z0-9_$]$') THEN
                        e2a_normalize_expression_tag := substring(
                            pg_catalog.substr(
                                e2a_normalize_expression_output,
                                e2a_normalize_expression_index
                            ) FROM '^\$(?:[A-Za-z_][A-Za-z_0-9]*)?\$'
                        );
                        IF e2a_normalize_expression_tag IS NULL THEN
                            IF substring(
                                pg_catalog.substr(
                                    e2a_normalize_expression_output,
                                    e2a_normalize_expression_index
                                ) FROM '^\$[A-Za-z_0-9]'
                            ) IS NOT NULL
                            OR substring(
                                pg_catalog.substr(
                                    e2a_normalize_expression_output,
                                    e2a_normalize_expression_index
                                ) FROM '^\$[^[:ascii:]]'
                            ) IS NOT NULL
                            OR substring(
                                pg_catalog.substr(
                                    e2a_normalize_expression_output,
                                    e2a_normalize_expression_index
                                ) FROM '^\$[A-Za-z_][A-Za-z_0-9]*[^[:ascii:]]'
                            ) IS NOT NULL THEN
                                RAISE EXCEPTION 'e2a_preflight_audit_check_drift';
                            END IF;
                            e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                        ELSE
                            e2a_normalize_expression_next := position(
                                e2a_normalize_expression_tag IN pg_catalog.substr(
                                    e2a_normalize_expression_output,
                                    e2a_normalize_expression_index
                                    + pg_catalog.length(e2a_normalize_expression_tag)
                                )
                            );
                            IF e2a_normalize_expression_next = 0 THEN
                                RAISE EXCEPTION 'e2a_preflight_audit_check_drift';
                            END IF;
                            e2a_normalize_expression_index := e2a_normalize_expression_index
                                + (2 * pg_catalog.length(e2a_normalize_expression_tag))
                                + e2a_normalize_expression_next - 1;
                        END IF;
                    ELSIF e2a_normalize_expression_character IN ('''', '"') THEN
                        e2a_normalize_expression_quote := e2a_normalize_expression_character;
                        e2a_normalize_expression_escape := e2a_normalize_expression_quote = ''''
                            AND e2a_normalize_expression_index > 1
                            AND pg_catalog.substr(
                                e2a_normalize_expression_output,
                                e2a_normalize_expression_index - 1,
                                1
                            ) IN ('E', 'e')
                            AND (e2a_normalize_expression_index = 2
                                OR pg_catalog.substr(
                                    e2a_normalize_expression_output,
                                    e2a_normalize_expression_index - 2,
                                    1
                                ) ~ '^[[:ascii:]]$'
                                AND pg_catalog.substr(
                                    e2a_normalize_expression_output,
                                    e2a_normalize_expression_index - 2,
                                    1
                                ) !~ '^[A-Za-z0-9_$]$');
                        e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                        LOOP
                            IF e2a_normalize_expression_index
                               > pg_catalog.length(e2a_normalize_expression_output) THEN
                                RAISE EXCEPTION 'e2a_preflight_audit_check_drift';
                            END IF;
                            e2a_normalize_expression_character := pg_catalog.substr(
                                e2a_normalize_expression_output,
                                e2a_normalize_expression_index,
                                1
                            );
                            IF e2a_normalize_expression_escape
                               AND e2a_normalize_expression_character = E'\\' THEN
                                IF e2a_normalize_expression_index
                                   = pg_catalog.length(e2a_normalize_expression_output) THEN
                                    RAISE EXCEPTION 'e2a_preflight_audit_check_drift';
                                END IF;
                                e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                            ELSIF e2a_normalize_expression_character
                                  = e2a_normalize_expression_quote THEN
                                IF pg_catalog.substr(
                                    e2a_normalize_expression_output,
                                    e2a_normalize_expression_index + 1,
                                    1
                                ) = e2a_normalize_expression_quote THEN
                                    e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                                ELSE
                                    e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                                    EXIT;
                                END IF;
                            END IF;
                            e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                        END LOOP;
                    ELSE
                        IF e2a_normalize_expression_character = '(' THEN
                            e2a_normalize_expression_depth := e2a_normalize_expression_depth + 1;
                        ELSIF e2a_normalize_expression_character = ')' THEN
                            e2a_normalize_expression_depth := e2a_normalize_expression_depth - 1;
                            IF e2a_normalize_expression_depth < 0 THEN
                                RAISE EXCEPTION 'e2a_preflight_audit_check_drift';
                            ELSIF e2a_normalize_expression_depth = 0
                              AND e2a_normalize_expression_index
                                  < pg_catalog.length(e2a_normalize_expression_output) THEN
                                e2a_normalize_expression_outer := false;
                                EXIT;
                            END IF;
                        END IF;
                        e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                    END IF;
                END LOOP;
                IF e2a_normalize_expression_depth <> 0 THEN
                    RAISE EXCEPTION 'e2a_preflight_audit_check_drift';
                END IF;
                EXIT WHEN NOT e2a_normalize_expression_outer;
                e2a_normalize_expression_output := pg_catalog.substr(
                    e2a_normalize_expression_output,
                    2,
                    pg_catalog.length(e2a_normalize_expression_output) - 2
                );
            END LOOP;
            IF e2a_normalize_expression_side = 1 THEN
                append_only_function_source_actual := e2a_normalize_expression_output;
            ELSIF e2a_normalize_expression_side = 2 THEN
                append_only_function_source_expected := e2a_normalize_expression_output;
            ELSIF e2a_normalize_expression_side = 3 THEN
                e2a_normalize_expression_actual := e2a_normalize_expression_output;
            ELSE
                e2a_normalize_expression_expected := e2a_normalize_expression_output;
            END IF;
        END LOOP;
        append_only_function_source_matches := pg_catalog.regexp_replace(
            append_only_function_source_actual,
            '^pg_catalog\.?now\(\)$', 'now()'
        )
        IS NOT DISTINCT FROM pg_catalog.regexp_replace(
            append_only_function_source_expected,
            '^pg_catalog\.?now\(\)$', 'now()'
        );
        old_audit_check_matches := pg_catalog.regexp_replace(
            e2a_normalize_expression_actual,
            '^pg_catalog\.?now\(\)$', 'now()'
        )
        IS NOT DISTINCT FROM pg_catalog.regexp_replace(
            e2a_normalize_expression_expected,
            '^pg_catalog\.?now\(\)$', 'now()'
        );
    END IF;

    SELECT NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_attribute AS attribute_row
        WHERE attribute_row.attrelid = evidence_links_oid
          AND attribute_row.attnum > 0 AND NOT attribute_row.attisdropped
          AND attribute_row.attname = ANY (ARRAY[
              'ownership_id', 'ownership_scope_version_id',
              'manual_entity_id', 'manual_relation_id'
          ])
    )
    AND ownership_oid IS NULL
    AND NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_attribute AS attribute_row
        WHERE attribute_row.attrelid = sync_state_oid
          AND attribute_row.attnum > 0 AND NOT attribute_row.attisdropped
          AND attribute_row.attname = 'materialization_owner'
    )
    AND targets_oid IS NULL
    AND NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint AS constraint_row
        WHERE constraint_row.connamespace = schema_oid
          AND constraint_row.conname = ANY (ARRAY[
              'uq_document_versions_doc_version',
              'uq_canonical_spans_version_span',
              'uq_evidence_version_evidence',
              'pk_okf_manual_fact_ownership',
              'pk_okf_manual_evidence_targets',
              'chk_evidence_links_manual_projection',
              'chk_evidence_links_manual_scope'
          ])
    )
    AND NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class AS index_class
        WHERE index_class.relnamespace = schema_oid
          AND index_class.relkind = 'i'
          AND index_class.relname = ANY (ARRAY[
              'idx_evidence_links_e2a_entity_dedup',
              'idx_evidence_links_e2a_relation_dedup',
              'idx_evidence_links_version_span',
              'idx_evidence_links_version_evidence',
              'idx_evidence_links_ownership_id',
              'idx_evidence_links_ownership_scope',
              'idx_evidence_links_manual_entity_owner',
              'idx_evidence_links_manual_relation_owner',
              'idx_evidence_links_version_evidence_manual_entity',
              'idx_evidence_links_version_evidence_manual_relation',
              'idx_okf_manual_fact_ownership_document_version',
              'idx_okf_manual_fact_ownership_scope_version',
              'idx_okf_manual_fact_ownership_entity',
              'idx_okf_manual_fact_ownership_relation',
              'idx_okf_manual_evidence_targets_version_evidence',
              'idx_okf_manual_evidence_targets_entity',
              'idx_okf_manual_evidence_targets_relation'
          ])
    )
    AND base_links_shape
    AND sync_state_fresh_shape
    AND legacy_fk_shape
    AND baseline_indexes_match
    AND old_audit_check_matches
    AND append_only_function_shape
    AND append_only_function_source_matches
    AND fresh_trigger_shape INTO fresh_signature;

    -- Final signature first requires the complete 019 inventory.  Detailed
    -- shape, FK action, index, and data validation follows before the return.
    SELECT ownership_oid IS NOT NULL
       AND targets_oid IS NOT NULL
       AND sync_state_oid IS NOT NULL
       AND append_only_function_shape
       AND EXISTS (
           SELECT 1
           FROM pg_catalog.pg_attribute AS attribute_row
           JOIN pg_catalog.pg_attrdef AS default_row
             ON default_row.adrelid = attribute_row.attrelid
            AND default_row.adnum = attribute_row.attnum
           WHERE attribute_row.attrelid = sync_state_oid
             AND attribute_row.attname = 'materialization_owner'
             AND attribute_row.attnum > 0 AND NOT attribute_row.attisdropped
             AND pg_catalog.format_type(attribute_row.atttypid, attribute_row.atttypmod) = 'text'
             AND attribute_row.attnotnull
             AND pg_catalog.pg_get_expr(default_row.adbin, default_row.adrelid)
                 = '''legacy_pre_e2a''::text'
       )
       AND EXISTS (
           SELECT 1 FROM pg_catalog.pg_constraint AS constraint_row
           WHERE constraint_row.conrelid = sync_state_oid
             AND constraint_row.conname = 'chk_okf_sync_state_materialization_owner'
             AND constraint_row.contype = 'c' AND constraint_row.convalidated
       )
       AND NOT EXISTS (
           SELECT 1
           FROM (VALUES
               ('ownership_id', 'uuid', false, NULL::text),
               ('ownership_scope_version_id', 'uuid', false, NULL::text),
               ('manual_entity_id', 'uuid', false, NULL::text),
               ('manual_relation_id', 'uuid', false, NULL::text)
           ) AS expected(column_name, type_name, required_not_null, default_expression)
           LEFT JOIN pg_catalog.pg_attribute AS attribute_row
             ON attribute_row.attrelid = evidence_links_oid
            AND attribute_row.attname = expected.column_name
            AND attribute_row.attnum > 0 AND NOT attribute_row.attisdropped
           LEFT JOIN pg_catalog.pg_attrdef AS default_row
             ON default_row.adrelid = attribute_row.attrelid
            AND default_row.adnum = attribute_row.attnum
           WHERE attribute_row.attname IS NULL
              OR pg_catalog.format_type(attribute_row.atttypid, attribute_row.atttypmod)
                   IS DISTINCT FROM expected.type_name
              OR attribute_row.attnotnull IS DISTINCT FROM expected.required_not_null
              OR pg_catalog.pg_get_expr(default_row.adbin, default_row.adrelid)
                   IS DISTINCT FROM expected.default_expression
       )
       AND EXISTS (
           SELECT 1 FROM pg_catalog.pg_attrdef AS default_row
           JOIN pg_catalog.pg_attribute AS attribute_row
             ON attribute_row.attrelid = default_row.adrelid
            AND attribute_row.attnum = default_row.adnum
           WHERE default_row.adrelid = evidence_links_oid
             AND attribute_row.attname = 'source_kind'
             AND pg_catalog.pg_get_expr(default_row.adbin, default_row.adrelid)
                 = '''legacy''::text'
       )
       AND NOT EXISTS (
           SELECT 1
           FROM (VALUES
               ('uq_document_versions_doc_version'),
               ('uq_canonical_spans_version_span'),
               ('uq_evidence_version_evidence'),
               ('pk_okf_manual_fact_ownership'),
               ('chk_okf_manual_fact_ownership_path'),
               ('chk_okf_manual_fact_ownership_kind'),
               ('chk_okf_manual_fact_ownership_digest'),
               ('chk_okf_manual_fact_ownership_target'),
               ('chk_okf_manual_fact_ownership_scope'),
               ('fk_okf_manual_fact_ownership_entity'),
               ('fk_okf_manual_fact_ownership_relation'),
               ('fk_okf_manual_fact_ownership_document_version'),
               ('uq_okf_manual_fact_ownership_path_fact'),
               ('uq_okf_manual_fact_ownership_entity_target'),
               ('uq_okf_manual_fact_ownership_relation_target'),
               ('uq_okf_manual_fact_ownership_scope'),
               ('pk_okf_manual_evidence_targets'),
               ('uq_okf_manual_evidence_targets_entity'),
               ('uq_okf_manual_evidence_targets_relation'),
               ('chk_okf_manual_evidence_targets_exactly_one_target'),
               ('fk_okf_manual_evidence_targets_version_evidence'),
               ('fk_okf_manual_evidence_targets_entity'),
               ('fk_okf_manual_evidence_targets_relation'),
               ('fk_evidence_links_version'),
               ('fk_evidence_links_entity'),
               ('fk_evidence_links_relation'),
               ('fk_evidence_links_version_span'),
               ('fk_evidence_links_version_evidence'),
               ('fk_evidence_links_ownership'),
               ('fk_evidence_links_ownership_scope'),
               ('fk_evidence_links_manual_entity_owner'),
               ('fk_evidence_links_manual_relation_owner'),
               ('fk_evidence_links_manual_entity_target'),
               ('fk_evidence_links_manual_relation_target'),
               ('chk_evidence_links_exactly_one_target'),
               ('chk_evidence_links_manual_projection'),
               ('chk_evidence_links_manual_scope'),
               ('chk_okf_sync_state_materialization_owner'),
               ('chk_okf_rebuild_failure_audit_phase')
           ) AS expected(constraint_name)
           LEFT JOIN pg_catalog.pg_constraint AS constraint_row
             ON constraint_row.connamespace = schema_oid
            AND constraint_row.conname = expected.constraint_name
           WHERE constraint_row.oid IS NULL OR NOT constraint_row.convalidated
       )
       AND NOT EXISTS (
           SELECT 1
           FROM (VALUES
               ('idx_evidence_links_e2a_entity_dedup'),
               ('idx_evidence_links_e2a_relation_dedup'),
               ('idx_evidence_links_version'),
               ('idx_evidence_links_entity'),
               ('idx_evidence_links_relation'),
               ('idx_evidence_links_span'),
               ('idx_evidence_links_evidence'),
               ('idx_okf_rebuild_failure_audit_occurred_at'),
               ('idx_okf_rebuild_failure_audit_scope'),
               ('idx_evidence_links_version_span'),
               ('idx_evidence_links_version_evidence'),
               ('idx_evidence_links_ownership_id'),
               ('idx_evidence_links_ownership_scope'),
               ('idx_evidence_links_manual_entity_owner'),
               ('idx_evidence_links_manual_relation_owner'),
               ('idx_evidence_links_version_evidence_manual_entity'),
               ('idx_evidence_links_version_evidence_manual_relation'),
               ('idx_okf_manual_fact_ownership_document_version'),
               ('idx_okf_manual_fact_ownership_scope_version'),
               ('idx_okf_manual_fact_ownership_entity'),
               ('idx_okf_manual_fact_ownership_relation'),
               ('idx_okf_manual_evidence_targets_version_evidence'),
               ('idx_okf_manual_evidence_targets_entity'),
               ('idx_okf_manual_evidence_targets_relation')
           ) AS expected(index_name)
           LEFT JOIN pg_catalog.pg_class AS index_class
             ON index_class.relnamespace = schema_oid
            AND index_class.relkind = 'i'
            AND index_class.relname = expected.index_name
           LEFT JOIN pg_catalog.pg_index AS index_row
             ON index_row.indexrelid = index_class.oid
           WHERE index_row.indexrelid IS NULL OR NOT index_row.indisvalid
       )
    INTO final_signature;

    IF fresh_signature AND final_signature
       OR NOT fresh_signature AND NOT final_signature THEN
        RAISE EXCEPTION 'e2a_preflight_malformed_partial';
    END IF;

    IF fresh_signature THEN
        -- Every fresh-data probe is read-only and occurs before the first DDL.
        EXECUTE pg_catalog.format(
            'SELECT EXISTS (SELECT 1 FROM %s AS link '
            || 'WHERE num_nonnulls(link.entity_id, link.relation_id) <> 1)',
            evidence_links_ref
        ) INTO fresh_target_drift;
        IF fresh_target_drift THEN
            RAISE EXCEPTION 'e2a_preflight_exactly_one_target';
        END IF;
        EXECUTE pg_catalog.format(
            'SELECT EXISTS (SELECT 1 FROM %s AS link '
            || 'JOIN %s AS span ON span.span_id = link.span_id '
            || 'WHERE span.version_id IS DISTINCT FROM link.version_id)',
            evidence_links_ref, canonical_spans_ref
        ) INTO fresh_span_drift;
        IF fresh_span_drift THEN
            RAISE EXCEPTION 'e2a_preflight_cross_version_span';
        END IF;
        EXECUTE pg_catalog.format(
            'SELECT EXISTS (SELECT 1 FROM %s AS link '
            || 'JOIN %s AS evidence ON evidence.evidence_id = link.evidence_id '
            || 'WHERE link.evidence_id IS NOT NULL '
            || 'AND evidence.version_id IS DISTINCT FROM link.version_id)',
            evidence_links_ref, evidence_ref
        ) INTO fresh_evidence_drift;
        IF fresh_evidence_drift THEN
            RAISE EXCEPTION 'e2a_preflight_cross_version_evidence';
        END IF;
        EXECUTE pg_catalog.format(
            'SELECT EXISTS (SELECT 1 FROM %s AS link WHERE link.source_kind = $1)',
            evidence_links_ref
        ) INTO has_manual_okf USING 'manual_okf';
        IF has_manual_okf THEN
            RAISE EXCEPTION 'e2a_preflight_existing_manual_okf';
        END IF;
    END IF;

    IF final_signature THEN
        -- The final branch is validation-only and intentionally performs zero DDL.
        IF NOT append_only_function_source_matches THEN
            RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
        END IF;
        -- e2a_normalize_expression is an inline fail-closed PL/pgSQL lexer for
        -- pg_get_expr bodies. It retains ordinary/E/Unicode/dollar literals and
        -- quoted identifiers byte-for-byte, strips only comments/insignificant
        -- outside-token whitespace, and rejects malformed nesting or lexemes.
        FOR final_check_name, final_check_table_oid, expected_check_body, final_check_position IN
            SELECT check_name, table_oid, check_body, 0
            FROM (VALUES
                ('chk_okf_manual_fact_ownership_path', ownership_oid, $e2a_body$((okf_relative_path <> ''::text) AND (okf_relative_path !~ '^(?:/|\\)'::text) AND (okf_relative_path !~ '/$'::text) AND (okf_relative_path !~ '//'::text) AND (okf_relative_path !~ '(^|/)(\.|\.\.)(/|$)'::text) AND (okf_relative_path !~ '[\\:]'::text) AND (okf_relative_path !~ '(^|/)[^/]*[. ](/|$)'::text) AND (okf_relative_path !~* '(^|/)(con|prn|aux|nul|com[1-9]|lpt[1-9])(\.[^/]*)?(/|$)'::text))$e2a_body$),
                ('chk_okf_manual_fact_ownership_kind', ownership_oid, $e2a_body$fact_kind = ANY (ARRAY['entity'::text, 'relation'::text])$e2a_body$),
                ('chk_okf_manual_fact_ownership_digest', ownership_oid, $e2a_body$source_digest ~ '^[0-9a-f]{64}$'::text$e2a_body$),
                ('chk_okf_manual_fact_ownership_target', ownership_oid, $e2a_body$((fact_kind = 'entity'::text) AND (entity_id IS NOT NULL) AND (entity_id = fact_id) AND (relation_id IS NULL)) OR ((fact_kind = 'relation'::text) AND (relation_id IS NOT NULL) AND (relation_id = fact_id) AND (entity_id IS NULL))$e2a_body$),
                ('chk_okf_manual_fact_ownership_scope', ownership_oid, $e2a_body$((scope_version_id = '00000000-0000-0000-0000-000000000000'::uuid) AND (document_id IS NULL) AND (version_id IS NULL)) OR ((scope_version_id = version_id) AND (document_id IS NOT NULL) AND (version_id IS NOT NULL))$e2a_body$),
                ('chk_okf_manual_evidence_targets_exactly_one_target', targets_oid, $e2a_body$num_nonnulls(entity_id, relation_id) = 1$e2a_body$),
                ('chk_evidence_links_exactly_one_target', evidence_links_oid, $e2a_body$num_nonnulls(entity_id, relation_id) = 1$e2a_body$),
                ('chk_evidence_links_manual_projection', evidence_links_oid, $e2a_body$(((source_kind <> 'manual_okf'::text) AND (ownership_id IS NULL) AND (ownership_scope_version_id IS NULL) AND (manual_entity_id IS NULL) AND (manual_relation_id IS NULL)) OR ((source_kind = 'manual_okf'::text) AND (evidence_id IS NOT NULL) AND (ownership_id IS NOT NULL) AND (ownership_scope_version_id IS NOT NULL) AND (num_nonnulls(manual_entity_id, manual_relation_id) = 1) AND (((manual_entity_id IS NOT NULL) AND (entity_id IS NOT NULL) AND (manual_entity_id = entity_id) AND (manual_relation_id IS NULL)) OR ((manual_relation_id IS NOT NULL) AND (relation_id IS NOT NULL) AND (manual_relation_id = relation_id) AND (manual_entity_id IS NULL)))))$e2a_body$),
                ('chk_evidence_links_manual_scope', evidence_links_oid, $e2a_body$((source_kind = 'manual_okf'::text) AND (ownership_scope_version_id IS NOT NULL) AND ((ownership_scope_version_id = version_id) OR (ownership_scope_version_id = '00000000-0000-0000-0000-000000000000'::uuid))) OR ((source_kind <> 'manual_okf'::text) AND (ownership_scope_version_id IS NULL))$e2a_body$),
                ('chk_okf_sync_state_materialization_owner', sync_state_oid, $e2a_body$materialization_owner = ANY (ARRAY['legacy_pre_e2a'::text, 'e2a'::text])$e2a_body$),
                ('chk_okf_rebuild_failure_audit_phase', audit_oid, $e2a_body$failure_phase = ANY (ARRAY['target_validation'::text, 'scope_lock'::text, 'parent_reconciliation'::text, 'span_reconciliation'::text, 'tree_reconciliation'::text, 'chunk_reconciliation'::text, 'manual_fact_reconciliation'::text, 'evidence_reconciliation'::text, 'transaction_commit'::text, 'success_log_write'::text])$e2a_body$)
            ) AS expected_checks(check_name, table_oid, check_body)
            UNION ALL
            SELECT index_name, table_oid, predicate, 1
            FROM (VALUES
                ('idx_evidence_links_e2a_entity_dedup', evidence_links_oid, '(source_kind = ''manual_okf''::text) AND (manual_entity_id IS NOT NULL)'),
                ('idx_evidence_links_e2a_relation_dedup', evidence_links_oid, '(source_kind = ''manual_okf''::text) AND (manual_relation_id IS NOT NULL)'),
                ('idx_evidence_links_evidence', evidence_links_oid, '(evidence_id IS NOT NULL)'),
                ('idx_okf_rebuild_failure_audit_scope', audit_oid, '(failing_doc_id IS NOT NULL)')
            ) AS expected_predicates(index_name, table_oid, predicate)
        LOOP
            IF final_check_position = 0 THEN
                SELECT pg_catalog.pg_get_expr(
                    constraint_row.conbin, constraint_row.conrelid, false
                ) INTO final_check_body
                FROM pg_catalog.pg_constraint AS constraint_row
                WHERE constraint_row.connamespace = schema_oid
                  AND constraint_row.conname = final_check_name
                  AND constraint_row.conrelid = final_check_table_oid
                  AND constraint_row.contype = 'c'
                  AND constraint_row.convalidated;
            ELSE
                SELECT pg_catalog.pg_get_expr(
                    index_row.indpred, index_row.indrelid, false
                ) INTO final_check_body
                FROM pg_catalog.pg_class AS index_class
                JOIN pg_catalog.pg_index AS index_row
                  ON index_row.indexrelid = index_class.oid
                WHERE index_class.relnamespace = schema_oid
                  AND index_class.relname = final_check_name
                  AND index_row.indrelid = final_check_table_oid;
            END IF;
            IF final_check_body IS NULL THEN
                RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
            END IF;

            FOR e2a_normalize_expression_side IN 1..2 LOOP
                e2a_normalize_expression_input := CASE e2a_normalize_expression_side
                    WHEN 1 THEN final_check_body ELSE expected_check_body END;
                e2a_normalize_expression_output := '';
                e2a_normalize_expression_index := 1;
                e2a_normalize_expression_depth := 0;
                e2a_normalize_expression_pending_space := false;
                WHILE e2a_normalize_expression_index <= pg_catalog.length(e2a_normalize_expression_input) LOOP
                    e2a_normalize_expression_character := pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index, 1);
                    IF e2a_normalize_expression_character IN (' ', E'\t', E'\n', E'\r', E'\f') THEN
                        e2a_normalize_expression_pending_space := e2a_normalize_expression_output <> '';
                        e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                    ELSIF pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index, 2) = '--' THEN
                        e2a_normalize_expression_index := e2a_normalize_expression_index + 2;
                        WHILE e2a_normalize_expression_index <= pg_catalog.length(e2a_normalize_expression_input)
                              AND pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index, 1) NOT IN (E'\n', E'\r') LOOP
                            e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                        END LOOP;
                        e2a_normalize_expression_pending_space := e2a_normalize_expression_output <> '';
                    ELSIF pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index, 2) = '/*' THEN
                        e2a_normalize_expression_comment_depth := 1;
                        e2a_normalize_expression_index := e2a_normalize_expression_index + 2;
                        WHILE e2a_normalize_expression_index <= pg_catalog.length(e2a_normalize_expression_input)
                              AND e2a_normalize_expression_comment_depth > 0 LOOP
                            IF pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index, 2) = '/*' THEN
                                e2a_normalize_expression_comment_depth := e2a_normalize_expression_comment_depth + 1;
                                e2a_normalize_expression_index := e2a_normalize_expression_index + 2;
                            ELSIF pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index, 2) = '*/' THEN
                                e2a_normalize_expression_comment_depth := e2a_normalize_expression_comment_depth - 1;
                                e2a_normalize_expression_index := e2a_normalize_expression_index + 2;
                            ELSE
                                e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                            END IF;
                        END LOOP;
                        IF e2a_normalize_expression_comment_depth <> 0 THEN
                            RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
                        END IF;
                        e2a_normalize_expression_pending_space := e2a_normalize_expression_output <> '';
                    ELSIF pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index, 2) = '*/' THEN
                        RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
                    ELSIF e2a_normalize_expression_character = '$'
                        AND (e2a_normalize_expression_index = 1
                            OR pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index - 1, 1) ~ '^[[:ascii:]]$'
                            AND pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index - 1, 1) !~ '^[A-Za-z0-9_$]$') THEN
                        e2a_normalize_expression_tag := substring(
                            pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index)
                            FROM '^\$(?:[A-Za-z_][A-Za-z_0-9]*)?\$'
                        );
                        IF e2a_normalize_expression_tag IS NULL THEN
                            IF substring(
                                pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index)
                                FROM '^\$[0-9][A-Za-z_0-9]*\$'
                            ) IS NOT NULL
                            OR substring(
                                pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index)
                                FROM '^\$[A-Za-z_0-9]'
                            ) IS NOT NULL
                            OR substring(
                                pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index)
                                FROM '^\$[^[:ascii:]]'
                            ) IS NOT NULL
                            OR substring(
                                pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index)
                                FROM '^\$[A-Za-z_][A-Za-z_0-9]*[^[:ascii:]]'
                            ) IS NOT NULL THEN
                                RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
                            END IF;
                            e2a_normalize_expression_output := e2a_normalize_expression_output || '$';
                            e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                        ELSE
                            e2a_normalize_expression_next := position(
                                e2a_normalize_expression_tag IN pg_catalog.substr(
                                    e2a_normalize_expression_input,
                                    e2a_normalize_expression_index + pg_catalog.length(e2a_normalize_expression_tag)
                                )
                            );
                            IF e2a_normalize_expression_next = 0 THEN
                                RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
                            END IF;
                            e2a_normalize_expression_output := e2a_normalize_expression_output
                                || pg_catalog.substr(
                                    e2a_normalize_expression_input,
                                    e2a_normalize_expression_index,
                                    (2 * pg_catalog.length(e2a_normalize_expression_tag)
                                    + e2a_normalize_expression_next - 1)
                                );
                            e2a_normalize_expression_index := e2a_normalize_expression_index
                                + (2 * pg_catalog.length(e2a_normalize_expression_tag))
                                + e2a_normalize_expression_next - 1;
                        END IF;
                    ELSIF e2a_normalize_expression_character IN ('''', '"') THEN
                        e2a_normalize_expression_quote := e2a_normalize_expression_character;
                        e2a_normalize_expression_escape := e2a_normalize_expression_quote = ''''
                            AND e2a_normalize_expression_index > 1
                            AND pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index - 1, 1) IN ('E', 'e')
                            AND (e2a_normalize_expression_index = 2
                                OR pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index - 2, 1) ~ '^[[:ascii:]]$'
                                AND pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index - 2, 1) !~ '^[A-Za-z0-9_$]$');
                        e2a_normalize_expression_output := e2a_normalize_expression_output || e2a_normalize_expression_character;
                        e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                        LOOP
                            IF e2a_normalize_expression_index > pg_catalog.length(e2a_normalize_expression_input) THEN
                                RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
                            END IF;
                            e2a_normalize_expression_character := pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index, 1);
                            e2a_normalize_expression_output := e2a_normalize_expression_output || e2a_normalize_expression_character;
                            IF e2a_normalize_expression_escape AND e2a_normalize_expression_character = E'\\' THEN
                                IF e2a_normalize_expression_index = pg_catalog.length(e2a_normalize_expression_input) THEN
                                    RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
                                END IF;
                                e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                                e2a_normalize_expression_output := e2a_normalize_expression_output || pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index, 1);
                            ELSIF e2a_normalize_expression_character = e2a_normalize_expression_quote THEN
                                IF pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index + 1, 1) = e2a_normalize_expression_quote THEN
                                    e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                                    e2a_normalize_expression_output := e2a_normalize_expression_output || e2a_normalize_expression_quote;
                                ELSE
                                    e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                                    EXIT;
                                END IF;
                            END IF;
                            e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                        END LOOP;
                    ELSE
                        IF e2a_normalize_expression_character = '(' THEN
                            e2a_normalize_expression_depth := e2a_normalize_expression_depth + 1;
                        ELSIF e2a_normalize_expression_character = ')' THEN
                            e2a_normalize_expression_depth := e2a_normalize_expression_depth - 1;
                            IF e2a_normalize_expression_depth < 0 THEN
                                RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
                            END IF;
                        END IF;
                        IF e2a_normalize_expression_pending_space
                           AND (e2a_normalize_expression_output ~ '[A-Za-z0-9_$]$'
                                OR e2a_normalize_expression_output ~ '[^[:ascii:]]$')
                           AND (e2a_normalize_expression_character ~ '^[A-Za-z0-9_$]$'
                                OR e2a_normalize_expression_character ~ '^[^[:ascii:]]$') THEN
                            e2a_normalize_expression_output := e2a_normalize_expression_output || ' ';
                        END IF;
                        e2a_normalize_expression_pending_space := false;
                        e2a_normalize_expression_output := e2a_normalize_expression_output || e2a_normalize_expression_character;
                        e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                    END IF;
                END LOOP;
                IF e2a_normalize_expression_depth <> 0 THEN
                    RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
                END IF;
                -- Remove only complete redundant outer expression parentheses.
            -- Re-lex the normalized bytes before each strip: literal, quoted,
            -- dollar, and comment parentheses cannot close an outer wrapper.
            WHILE pg_catalog.left(e2a_normalize_expression_output, 1) = '('
              AND pg_catalog.right(e2a_normalize_expression_output, 1) = ')'
              AND pg_catalog.length(e2a_normalize_expression_output) > 2 LOOP
                e2a_normalize_expression_outer := true;
                e2a_normalize_expression_depth := 0;
                e2a_normalize_expression_index := 1;
                WHILE e2a_normalize_expression_index
                      <= pg_catalog.length(e2a_normalize_expression_output) LOOP
                    e2a_normalize_expression_character := pg_catalog.substr(
                        e2a_normalize_expression_output,
                        e2a_normalize_expression_index,
                        1
                    );
                    IF pg_catalog.substr(
                        e2a_normalize_expression_output,
                        e2a_normalize_expression_index,
                        2
                    ) = '--' THEN
                        e2a_normalize_expression_index := e2a_normalize_expression_index + 2;
                        WHILE e2a_normalize_expression_index
                              <= pg_catalog.length(e2a_normalize_expression_output)
                          AND pg_catalog.substr(
                              e2a_normalize_expression_output,
                              e2a_normalize_expression_index,
                              1
                          ) NOT IN (E'\n', E'\r') LOOP
                            e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                        END LOOP;
                    ELSIF pg_catalog.substr(
                        e2a_normalize_expression_output,
                        e2a_normalize_expression_index,
                        2
                    ) = '/*' THEN
                        e2a_normalize_expression_comment_depth := 1;
                        e2a_normalize_expression_index := e2a_normalize_expression_index + 2;
                        WHILE e2a_normalize_expression_index
                              <= pg_catalog.length(e2a_normalize_expression_output)
                          AND e2a_normalize_expression_comment_depth > 0 LOOP
                            IF pg_catalog.substr(
                                e2a_normalize_expression_output,
                                e2a_normalize_expression_index,
                                2
                            ) = '/*' THEN
                                e2a_normalize_expression_comment_depth := e2a_normalize_expression_comment_depth + 1;
                                e2a_normalize_expression_index := e2a_normalize_expression_index + 2;
                            ELSIF pg_catalog.substr(
                                e2a_normalize_expression_output,
                                e2a_normalize_expression_index,
                                2
                            ) = '*/' THEN
                                e2a_normalize_expression_comment_depth := e2a_normalize_expression_comment_depth - 1;
                                e2a_normalize_expression_index := e2a_normalize_expression_index + 2;
                            ELSE
                                e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                            END IF;
                        END LOOP;
                        IF e2a_normalize_expression_comment_depth <> 0 THEN
                            RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
                        END IF;
                    ELSIF pg_catalog.substr(
                        e2a_normalize_expression_output,
                        e2a_normalize_expression_index,
                        2
                    ) = '*/' THEN
                        RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
                    ELSIF e2a_normalize_expression_character = '$'
                      AND (e2a_normalize_expression_index = 1
                        OR pg_catalog.substr(
                            e2a_normalize_expression_output,
                            e2a_normalize_expression_index - 1,
                            1
                        ) ~ '^[[:ascii:]]$'
                        AND pg_catalog.substr(
                            e2a_normalize_expression_output,
                            e2a_normalize_expression_index - 1,
                            1
                        ) !~ '^[A-Za-z0-9_$]$') THEN
                        e2a_normalize_expression_tag := substring(
                            pg_catalog.substr(
                                e2a_normalize_expression_output,
                                e2a_normalize_expression_index
                            ) FROM '^\$(?:[A-Za-z_][A-Za-z_0-9]*)?\$'
                        );
                        IF e2a_normalize_expression_tag IS NULL THEN
                            IF substring(
                                pg_catalog.substr(
                                    e2a_normalize_expression_output,
                                    e2a_normalize_expression_index
                                ) FROM '^\$[A-Za-z_0-9]'
                            ) IS NOT NULL
                            OR substring(
                                pg_catalog.substr(
                                    e2a_normalize_expression_output,
                                    e2a_normalize_expression_index
                                ) FROM '^\$[^[:ascii:]]'
                            ) IS NOT NULL
                            OR substring(
                                pg_catalog.substr(
                                    e2a_normalize_expression_output,
                                    e2a_normalize_expression_index
                                ) FROM '^\$[A-Za-z_][A-Za-z_0-9]*[^[:ascii:]]'
                            ) IS NOT NULL THEN
                                RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
                            END IF;
                            e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                        ELSE
                            e2a_normalize_expression_next := position(
                                e2a_normalize_expression_tag IN pg_catalog.substr(
                                    e2a_normalize_expression_output,
                                    e2a_normalize_expression_index
                                    + pg_catalog.length(e2a_normalize_expression_tag)
                                )
                            );
                            IF e2a_normalize_expression_next = 0 THEN
                                RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
                            END IF;
                            e2a_normalize_expression_index := e2a_normalize_expression_index
                                + (2 * pg_catalog.length(e2a_normalize_expression_tag))
                                + e2a_normalize_expression_next - 1;
                        END IF;
                    ELSIF e2a_normalize_expression_character IN ('''', '"') THEN
                        e2a_normalize_expression_quote := e2a_normalize_expression_character;
                        e2a_normalize_expression_escape := e2a_normalize_expression_quote = ''''
                            AND e2a_normalize_expression_index > 1
                            AND pg_catalog.substr(
                                e2a_normalize_expression_output,
                                e2a_normalize_expression_index - 1,
                                1
                            ) IN ('E', 'e')
                            AND (e2a_normalize_expression_index = 2
                                OR pg_catalog.substr(
                                    e2a_normalize_expression_output,
                                    e2a_normalize_expression_index - 2,
                                    1
                                ) ~ '^[[:ascii:]]$'
                                AND pg_catalog.substr(
                                    e2a_normalize_expression_output,
                                    e2a_normalize_expression_index - 2,
                                    1
                                ) !~ '^[A-Za-z0-9_$]$');
                        e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                        LOOP
                            IF e2a_normalize_expression_index
                               > pg_catalog.length(e2a_normalize_expression_output) THEN
                                RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
                            END IF;
                            e2a_normalize_expression_character := pg_catalog.substr(
                                e2a_normalize_expression_output,
                                e2a_normalize_expression_index,
                                1
                            );
                            IF e2a_normalize_expression_escape
                               AND e2a_normalize_expression_character = E'\\' THEN
                                IF e2a_normalize_expression_index
                                   = pg_catalog.length(e2a_normalize_expression_output) THEN
                                    RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
                                END IF;
                                e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                            ELSIF e2a_normalize_expression_character
                                  = e2a_normalize_expression_quote THEN
                                IF pg_catalog.substr(
                                    e2a_normalize_expression_output,
                                    e2a_normalize_expression_index + 1,
                                    1
                                ) = e2a_normalize_expression_quote THEN
                                    e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                                ELSE
                                    e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                                    EXIT;
                                END IF;
                            END IF;
                            e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                        END LOOP;
                    ELSE
                        IF e2a_normalize_expression_character = '(' THEN
                            e2a_normalize_expression_depth := e2a_normalize_expression_depth + 1;
                        ELSIF e2a_normalize_expression_character = ')' THEN
                            e2a_normalize_expression_depth := e2a_normalize_expression_depth - 1;
                            IF e2a_normalize_expression_depth < 0 THEN
                                RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
                            ELSIF e2a_normalize_expression_depth = 0
                              AND e2a_normalize_expression_index
                                  < pg_catalog.length(e2a_normalize_expression_output) THEN
                                e2a_normalize_expression_outer := false;
                                EXIT;
                            END IF;
                        END IF;
                        e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                    END IF;
                END LOOP;
                IF e2a_normalize_expression_depth <> 0 THEN
                    RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
                END IF;
                EXIT WHEN NOT e2a_normalize_expression_outer;
                e2a_normalize_expression_output := pg_catalog.substr(
                    e2a_normalize_expression_output,
                    2,
                    pg_catalog.length(e2a_normalize_expression_output) - 2
                );
            END LOOP;
                IF e2a_normalize_expression_side = 1 THEN
                    e2a_normalize_expression_actual := e2a_normalize_expression_output;
                    IF final_check_position = 1 THEN
                        e2a_normalize_expression_predicate_actual := e2a_normalize_expression_output;
                    END IF;
                ELSE
                    e2a_normalize_expression_expected := e2a_normalize_expression_output;
                    IF final_check_position = 1 THEN
                        e2a_normalize_expression_predicate_expected := e2a_normalize_expression_output;
                    END IF;
                END IF;
            END LOOP;
            IF (final_check_position = 0
                AND e2a_normalize_expression_actual
                    IS DISTINCT FROM e2a_normalize_expression_expected)
               OR (final_check_position = 1
                AND e2a_normalize_expression_predicate_actual
                    IS DISTINCT FROM e2a_normalize_expression_predicate_expected) THEN
                RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
            END IF;
        END LOOP;

        -- The final branch is validation-only and intentionally performs zero DDL.
        SELECT NOT EXISTS (
            WITH expected_final_columns(table_oid, column_name, type_name, required_not_null, default_expression) AS (
                VALUES
                    (evidence_links_oid, 'evidence_link_id', 'uuid', true, NULL::text), (evidence_links_oid, 'version_id', 'uuid', true, NULL::text),
                    (evidence_links_oid, 'entity_id', 'uuid', false, NULL::text), (evidence_links_oid, 'relation_id', 'uuid', false, NULL::text),
                    (evidence_links_oid, 'span_id', 'uuid', true, NULL::text), (evidence_links_oid, 'source_kind', 'text', true, '''legacy''::text'),
                    (evidence_links_oid, 'confidence_score', 'double precision', false, NULL::text), (evidence_links_oid, 'created_at', 'timestamp with time zone', true, 'now()'),
                    (evidence_links_oid, 'evidence_id', 'uuid', false, NULL::text), (evidence_links_oid, 'ownership_id', 'uuid', false, NULL::text),
                    (evidence_links_oid, 'ownership_scope_version_id', 'uuid', false, NULL::text), (evidence_links_oid, 'manual_entity_id', 'uuid', false, NULL::text), (evidence_links_oid, 'manual_relation_id', 'uuid', false, NULL::text),
                    (ownership_oid, 'ownership_id', 'uuid', true, NULL::text), (ownership_oid, 'okf_relative_path', 'text', true, NULL::text),
                    (ownership_oid, 'fact_kind', 'text', true, NULL::text), (ownership_oid, 'fact_id', 'uuid', true, NULL::text), (ownership_oid, 'entity_id', 'uuid', false, NULL::text),
                    (ownership_oid, 'relation_id', 'uuid', false, NULL::text), (ownership_oid, 'source_digest', 'character(64)', true, NULL::text),
                    (ownership_oid, 'document_id', 'uuid', false, NULL::text), (ownership_oid, 'version_id', 'uuid', false, NULL::text), (ownership_oid, 'scope_version_id', 'uuid', true, '''00000000-0000-0000-0000-000000000000''::uuid'),
                    (ownership_oid, 'created_at', 'timestamp with time zone', true, 'now()'),
                    (targets_oid, 'version_id', 'uuid', true, NULL::text), (targets_oid, 'evidence_id', 'uuid', true, NULL::text),
                    (targets_oid, 'entity_id', 'uuid', false, NULL::text), (targets_oid, 'relation_id', 'uuid', false, NULL::text),
                    (sync_state_oid, 'okf_file_path', 'text', true, NULL::text), (sync_state_oid, 'doc_id', 'uuid', false, NULL::text),
                    (sync_state_oid, 'version_id', 'uuid', false, NULL::text), (sync_state_oid, 'source_checksum', 'text', true, NULL::text),
                    (sync_state_oid, 'canonical_hash', 'text', true, NULL::text), (sync_state_oid, 'status', 'text', true, NULL::text),
                    (sync_state_oid, 'last_synced_at', 'timestamp with time zone', true, 'now()'),
                    (sync_state_oid, 'materialization_owner', 'text', true, '''legacy_pre_e2a''::text')
            ), actual AS (
                SELECT attribute_row.attrelid, attribute_row.attname, pg_catalog.format_type(attribute_row.atttypid, attribute_row.atttypmod), attribute_row.attnotnull, pg_catalog.pg_get_expr(default_row.adbin, default_row.adrelid)
                FROM pg_catalog.pg_attribute AS attribute_row
                LEFT JOIN pg_catalog.pg_attrdef AS default_row ON default_row.adrelid = attribute_row.attrelid AND default_row.adnum = attribute_row.attnum
                WHERE attribute_row.attrelid = ANY (ARRAY[evidence_links_oid, ownership_oid, targets_oid, sync_state_oid]) AND attribute_row.attnum > 0 AND NOT attribute_row.attisdropped
            )
            SELECT 1 FROM expected_final_columns
            FULL JOIN actual ON actual.attrelid = expected_final_columns.table_oid AND actual.attname = expected_final_columns.column_name
            WHERE actual.attname IS NULL OR expected_final_columns.column_name IS NULL
               OR actual.format_type IS DISTINCT FROM expected_final_columns.type_name
               OR actual.attnotnull IS DISTINCT FROM expected_final_columns.required_not_null
               OR actual.pg_get_expr IS DISTINCT FROM expected_final_columns.default_expression
        ) INTO final_inventory_matches;
        IF NOT final_inventory_matches THEN
            RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
        END IF;

        SELECT NOT EXISTS (
            WITH expected_final_constraints(constraint_name, table_oid, constraint_type, columns) AS (
                VALUES
                    ('uq_document_versions_doc_version', document_versions_oid, 'u', ARRAY['doc_id', 'version_id']), ('uq_canonical_spans_version_span', canonical_spans_oid, 'u', ARRAY['version_id', 'span_id']), ('uq_evidence_version_evidence', evidence_oid, 'u', ARRAY['version_id', 'evidence_id']),
                    ('pk_okf_manual_fact_ownership', ownership_oid, 'p', ARRAY['ownership_id']), ('uq_okf_manual_fact_ownership_path_fact', ownership_oid, 'u', ARRAY['okf_relative_path', 'fact_kind', 'fact_id']), ('uq_okf_manual_fact_ownership_entity_target', ownership_oid, 'u', ARRAY['ownership_id', 'entity_id']), ('uq_okf_manual_fact_ownership_relation_target', ownership_oid, 'u', ARRAY['ownership_id', 'relation_id']), ('uq_okf_manual_fact_ownership_scope', ownership_oid, 'u', ARRAY['ownership_id', 'scope_version_id']),
                    ('pk_okf_manual_evidence_targets', targets_oid, 'p', ARRAY['version_id', 'evidence_id']), ('uq_okf_manual_evidence_targets_entity', targets_oid, 'u', ARRAY['version_id', 'evidence_id', 'entity_id']), ('uq_okf_manual_evidence_targets_relation', targets_oid, 'u', ARRAY['version_id', 'evidence_id', 'relation_id']),
                    ('okf_sync_state_pkey', sync_state_oid, 'p', ARRAY['okf_file_path']),
                    ('chk_okf_sync_state_materialization_owner', sync_state_oid, 'c', NULL::text[]),
                    ('chk_okf_manual_fact_ownership_path', ownership_oid, 'c', NULL::text[]), ('chk_okf_manual_fact_ownership_kind', ownership_oid, 'c', NULL::text[]), ('chk_okf_manual_fact_ownership_digest', ownership_oid, 'c', NULL::text[]), ('chk_okf_manual_fact_ownership_target', ownership_oid, 'c', NULL::text[]), ('chk_okf_manual_fact_ownership_scope', ownership_oid, 'c', NULL::text[]), ('chk_okf_manual_evidence_targets_exactly_one_target', targets_oid, 'c', NULL::text[]), ('chk_evidence_links_exactly_one_target', evidence_links_oid, 'c', NULL::text[]), ('chk_evidence_links_manual_projection', evidence_links_oid, 'c', NULL::text[]), ('chk_evidence_links_manual_scope', evidence_links_oid, 'c', NULL::text[]), ('chk_okf_rebuild_failure_audit_phase', audit_oid, 'c', NULL::text[])
            )
            SELECT 1 FROM expected_final_constraints
            LEFT JOIN pg_catalog.pg_constraint AS constraint_row ON constraint_row.connamespace = schema_oid AND constraint_row.conname = expected_final_constraints.constraint_name
            WHERE constraint_row.oid IS NULL OR constraint_row.conrelid <> expected_final_constraints.table_oid OR constraint_row.contype <> expected_final_constraints.constraint_type OR NOT constraint_row.convalidated
               OR (expected_final_constraints.columns IS NOT NULL AND constraint_row.conkey IS DISTINCT FROM ARRAY(SELECT attribute_row.attnum FROM pg_catalog.unnest(expected_final_constraints.columns) WITH ORDINALITY AS column_row(column_name, ordinality) JOIN pg_catalog.pg_attribute AS attribute_row ON attribute_row.attrelid = expected_final_constraints.table_oid AND attribute_row.attname = column_row.column_name ORDER BY column_row.ordinality))
               OR (expected_final_constraints.constraint_type = 'c' AND pg_catalog.pg_get_constraintdef(constraint_row.oid, true) IS NULL)
        ) INTO final_inventory_matches;
        IF NOT final_inventory_matches THEN
            RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
        END IF;

        SELECT NOT EXISTS (
            WITH expected_final_indexes(index_name, table_oid, columns, required_unique, predicate) AS (
                VALUES
                    ('idx_evidence_links_e2a_entity_dedup', evidence_links_oid, ARRAY['version_id', 'span_id', 'manual_entity_id', 'evidence_id', 'ownership_id'], true, '(source_kind = ''manual_okf''::text) AND (manual_entity_id IS NOT NULL)'), ('idx_evidence_links_e2a_relation_dedup', evidence_links_oid, ARRAY['version_id', 'span_id', 'manual_relation_id', 'evidence_id', 'ownership_id'], true, '(source_kind = ''manual_okf''::text) AND (manual_relation_id IS NOT NULL)'),
                    ('idx_evidence_links_version', evidence_links_oid, ARRAY['version_id'], false, NULL::text), ('idx_evidence_links_entity', evidence_links_oid, ARRAY['entity_id'], false, NULL::text), ('idx_evidence_links_relation', evidence_links_oid, ARRAY['relation_id'], false, NULL::text), ('idx_evidence_links_span', evidence_links_oid, ARRAY['span_id'], false, NULL::text), ('idx_evidence_links_evidence', evidence_links_oid, ARRAY['evidence_id'], false, '(evidence_id IS NOT NULL)'), ('idx_okf_rebuild_failure_audit_occurred_at', audit_oid, ARRAY['occurred_at'], false, NULL::text), ('idx_okf_rebuild_failure_audit_scope', audit_oid, ARRAY['failing_doc_id', 'failing_version_id'], false, '(failing_doc_id IS NOT NULL)'), ('idx_evidence_links_version_span', evidence_links_oid, ARRAY['version_id', 'span_id'], false, NULL::text), ('idx_evidence_links_version_evidence', evidence_links_oid, ARRAY['version_id', 'evidence_id'], false, NULL::text), ('idx_evidence_links_ownership_id', evidence_links_oid, ARRAY['ownership_id'], false, NULL::text), ('idx_evidence_links_ownership_scope', evidence_links_oid, ARRAY['ownership_id', 'ownership_scope_version_id'], false, NULL::text), ('idx_evidence_links_manual_entity_owner', evidence_links_oid, ARRAY['ownership_id', 'manual_entity_id'], false, NULL::text), ('idx_evidence_links_manual_relation_owner', evidence_links_oid, ARRAY['ownership_id', 'manual_relation_id'], false, NULL::text), ('idx_evidence_links_version_evidence_manual_entity', evidence_links_oid, ARRAY['version_id', 'evidence_id', 'manual_entity_id'], false, NULL::text), ('idx_evidence_links_version_evidence_manual_relation', evidence_links_oid, ARRAY['version_id', 'evidence_id', 'manual_relation_id'], false, NULL::text),
                    ('idx_okf_manual_fact_ownership_document_version', ownership_oid, ARRAY['document_id', 'version_id'], false, NULL::text), ('idx_okf_manual_fact_ownership_scope_version', ownership_oid, ARRAY['scope_version_id', 'ownership_id'], false, NULL::text), ('idx_okf_manual_fact_ownership_entity', ownership_oid, ARRAY['entity_id'], false, NULL::text), ('idx_okf_manual_fact_ownership_relation', ownership_oid, ARRAY['relation_id'], false, NULL::text), ('idx_okf_manual_evidence_targets_version_evidence', targets_oid, ARRAY['version_id', 'evidence_id'], false, NULL::text), ('idx_okf_manual_evidence_targets_entity', targets_oid, ARRAY['entity_id'], false, NULL::text), ('idx_okf_manual_evidence_targets_relation', targets_oid, ARRAY['relation_id'], false, NULL::text)
            )
            SELECT 1 FROM expected_final_indexes
            LEFT JOIN pg_catalog.pg_class AS index_class ON index_class.relnamespace = schema_oid AND index_class.relname = expected_final_indexes.index_name AND index_class.relkind = 'i'
            LEFT JOIN pg_catalog.pg_index AS index_row ON index_row.indexrelid = index_class.oid
            LEFT JOIN pg_catalog.pg_am AS index_method ON index_method.oid = index_class.relam
            WHERE index_row.indexrelid IS NULL OR index_row.indrelid <> expected_final_indexes.table_oid OR index_row.indisunique IS DISTINCT FROM expected_final_indexes.required_unique OR NOT index_row.indisvalid OR NOT index_row.indisready OR NOT index_row.indislive OR index_row.indisexclusion OR index_method.amname IS DISTINCT FROM 'btree' OR index_row.indexprs IS NOT NULL
               OR index_row.indnkeyatts <> pg_catalog.cardinality(expected_final_indexes.columns)
               OR index_row.indnatts <> pg_catalog.cardinality(expected_final_indexes.columns)
               OR EXISTS (
                   SELECT 1
                   FROM pg_catalog.unnest(expected_final_indexes.columns) WITH ORDINALITY
                        AS column_row(column_name, ordinality)
                   JOIN pg_catalog.pg_attribute AS attribute_row
                     ON attribute_row.attrelid = expected_final_indexes.table_oid
                    AND attribute_row.attname = column_row.column_name
                   JOIN pg_catalog.pg_opclass AS opclass_row
                     ON opclass_row.oid = index_row.indclass[column_row.ordinality - 1]
                   WHERE index_row.indkey[column_row.ordinality - 1]
                             IS DISTINCT FROM attribute_row.attnum
                      OR index_row.indcollation[column_row.ordinality - 1]
                             IS DISTINCT FROM attribute_row.attcollation
                      OR NOT opclass_row.opcdefault
                      OR index_row.indoption[column_row.ordinality - 1]
                             IS DISTINCT FROM CASE
                                 WHEN expected_final_indexes.index_name = 'idx_okf_rebuild_failure_audit_occurred_at'
                                     THEN 3::smallint
                                 ELSE 0::smallint
                             END
               )
               OR (expected_final_indexes.predicate IS NULL AND index_row.indpred IS NOT NULL)
               OR (expected_final_indexes.predicate IS NOT NULL AND index_row.indpred IS NULL)
        ) INTO final_inventory_matches;
        IF NOT final_inventory_matches THEN
            RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
        END IF;

        SELECT NOT EXISTS (
            WITH expected_final_foreign_keys(constraint_name, source_columns, target_columns) AS (
                VALUES
                    ('fk_okf_manual_fact_ownership_entity', ARRAY['entity_id'], ARRAY['entity_id']), ('fk_okf_manual_fact_ownership_relation', ARRAY['relation_id'], ARRAY['relation_id']), ('fk_okf_manual_fact_ownership_document_version', ARRAY['document_id', 'version_id'], ARRAY['doc_id', 'version_id']), ('fk_okf_manual_evidence_targets_version_evidence', ARRAY['version_id', 'evidence_id'], ARRAY['version_id', 'evidence_id']), ('fk_okf_manual_evidence_targets_entity', ARRAY['entity_id'], ARRAY['entity_id']), ('fk_okf_manual_evidence_targets_relation', ARRAY['relation_id'], ARRAY['relation_id']),
                    ('fk_evidence_links_version', ARRAY['version_id'], ARRAY['version_id']), ('fk_evidence_links_entity', ARRAY['entity_id'], ARRAY['entity_id']), ('fk_evidence_links_relation', ARRAY['relation_id'], ARRAY['relation_id']), ('fk_evidence_links_version_span', ARRAY['version_id', 'span_id'], ARRAY['version_id', 'span_id']), ('fk_evidence_links_version_evidence', ARRAY['version_id', 'evidence_id'], ARRAY['version_id', 'evidence_id']), ('fk_evidence_links_ownership', ARRAY['ownership_id'], ARRAY['ownership_id']), ('fk_evidence_links_ownership_scope', ARRAY['ownership_id', 'ownership_scope_version_id'], ARRAY['ownership_id', 'scope_version_id']), ('fk_evidence_links_manual_entity_owner', ARRAY['ownership_id', 'manual_entity_id'], ARRAY['ownership_id', 'entity_id']), ('fk_evidence_links_manual_relation_owner', ARRAY['ownership_id', 'manual_relation_id'], ARRAY['ownership_id', 'relation_id']), ('fk_evidence_links_manual_entity_target', ARRAY['version_id', 'evidence_id', 'manual_entity_id'], ARRAY['version_id', 'evidence_id', 'entity_id']), ('fk_evidence_links_manual_relation_target', ARRAY['version_id', 'evidence_id', 'manual_relation_id'], ARRAY['version_id', 'evidence_id', 'relation_id'])
            )
            SELECT 1 FROM expected_final_foreign_keys
            JOIN pg_catalog.pg_constraint AS constraint_row ON constraint_row.connamespace = schema_oid AND constraint_row.conname = expected_final_foreign_keys.constraint_name
            WHERE constraint_row.conkey IS DISTINCT FROM ARRAY(SELECT attribute_row.attnum FROM pg_catalog.unnest(expected_final_foreign_keys.source_columns) WITH ORDINALITY AS column_row(column_name, ordinality) JOIN pg_catalog.pg_attribute AS attribute_row ON attribute_row.attrelid = constraint_row.conrelid AND attribute_row.attname = column_row.column_name ORDER BY column_row.ordinality)
               OR constraint_row.confkey IS DISTINCT FROM ARRAY(SELECT attribute_row.attnum FROM pg_catalog.unnest(expected_final_foreign_keys.target_columns) WITH ORDINALITY AS column_row(column_name, ordinality) JOIN pg_catalog.pg_attribute AS attribute_row ON attribute_row.attrelid = constraint_row.confrelid AND attribute_row.attname = column_row.column_name ORDER BY column_row.ordinality)
        ) INTO final_inventory_matches;
        IF NOT final_inventory_matches THEN
            RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
        END IF;

        SELECT NOT EXISTS (
            WITH named_fk(constraint_name, source_oid, target_oid) AS (
                VALUES
                    ('fk_okf_manual_fact_ownership_entity', ownership_oid, entities_oid),
                    ('fk_okf_manual_fact_ownership_relation', ownership_oid, relations_oid),
                    ('fk_okf_manual_fact_ownership_document_version', ownership_oid, document_versions_oid),
                    ('fk_okf_manual_evidence_targets_version_evidence', targets_oid, evidence_oid),
                    ('fk_okf_manual_evidence_targets_entity', targets_oid, entities_oid),
                    ('fk_okf_manual_evidence_targets_relation', targets_oid, relations_oid),
                    ('fk_evidence_links_version', evidence_links_oid, document_versions_oid),
                    ('fk_evidence_links_entity', evidence_links_oid, entities_oid),
                    ('fk_evidence_links_relation', evidence_links_oid, relations_oid),
                    ('fk_evidence_links_version_span', evidence_links_oid, canonical_spans_oid),
                    ('fk_evidence_links_version_evidence', evidence_links_oid, evidence_oid),
                    ('fk_evidence_links_ownership', evidence_links_oid, ownership_oid),
                    ('fk_evidence_links_ownership_scope', evidence_links_oid, ownership_oid),
                    ('fk_evidence_links_manual_entity_owner', evidence_links_oid, ownership_oid),
                    ('fk_evidence_links_manual_relation_owner', evidence_links_oid, ownership_oid),
                    ('fk_evidence_links_manual_entity_target', evidence_links_oid, targets_oid),
                    ('fk_evidence_links_manual_relation_target', evidence_links_oid, targets_oid)
            )
            SELECT 1
            FROM named_fk
            LEFT JOIN pg_catalog.pg_constraint AS constraint_row
              ON constraint_row.connamespace = schema_oid
             AND constraint_row.conname = named_fk.constraint_name
            WHERE constraint_row.oid IS NULL
               OR constraint_row.contype <> 'f'
               OR constraint_row.conrelid <> named_fk.source_oid
               OR constraint_row.confrelid <> named_fk.target_oid
               OR NOT constraint_row.convalidated
               OR constraint_row.confdeltype <> 'r'
               OR constraint_row.confmatchtype <> 's'
               OR constraint_row.confupdtype <> 'a'
               OR constraint_row.condeferrable
               OR constraint_row.condeferred
        ) INTO final_inventory_matches;
        IF NOT final_inventory_matches THEN
            RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
        END IF;

        -- The five replaced identities may retain inherited NO ACTION FKs, but
        -- no CASCADE FK with any of those exact source/target key shapes remains.
        IF EXISTS (
            WITH replaceable(target_oid, source_columns, target_columns) AS (
                VALUES
                    (document_versions_oid, ARRAY['version_id'], ARRAY['version_id']),
                    (canonical_spans_oid, ARRAY['span_id'], ARRAY['span_id']),
                    (evidence_oid, ARRAY['evidence_id'], ARRAY['evidence_id']),
                    (entities_oid, ARRAY['entity_id'], ARRAY['entity_id']),
                    (relations_oid, ARRAY['relation_id'], ARRAY['relation_id'])
            )
            SELECT 1
            FROM pg_catalog.pg_constraint AS constraint_row
            JOIN replaceable ON replaceable.target_oid = constraint_row.confrelid
            WHERE constraint_row.conrelid = evidence_links_oid
              AND constraint_row.contype = 'f'
              AND constraint_row.confdeltype = 'c'
              AND constraint_row.conkey = ARRAY(
                  SELECT attribute_row.attnum
                  FROM pg_catalog.unnest(replaceable.source_columns)
                      WITH ORDINALITY AS column_row(column_name, ordinality)
                  JOIN pg_catalog.pg_attribute AS attribute_row
                    ON attribute_row.attrelid = evidence_links_oid
                   AND attribute_row.attname = column_row.column_name
                  ORDER BY column_row.ordinality
              )
              AND constraint_row.confkey = ARRAY(
                  SELECT attribute_row.attnum
                  FROM pg_catalog.unnest(replaceable.target_columns)
                      WITH ORDINALITY AS column_row(column_name, ordinality)
                  JOIN pg_catalog.pg_attribute AS attribute_row
                    ON attribute_row.attrelid = replaceable.target_oid
                   AND attribute_row.attname = column_row.column_name
                  ORDER BY column_row.ordinality
              )
        ) THEN
            RAISE EXCEPTION 'e2a_preflight_final_legacy_cascade';
        END IF;

        IF EXISTS (
            WITH expected(trigger_name, expected_type) AS (
                VALUES
                    ('trg_okf_rebuild_failure_audit_append_only', 27::smallint),
                    ('trg_okf_rebuild_failure_audit_no_truncate', 34::smallint)
            )
            SELECT 1
            FROM expected
            LEFT JOIN pg_catalog.pg_trigger AS trigger_row
              ON trigger_row.tgrelid = audit_oid
             AND trigger_row.tgname = expected.trigger_name
            LEFT JOIN pg_catalog.pg_proc AS procedure_row
              ON procedure_row.oid = trigger_row.tgfoid
            LEFT JOIN pg_catalog.pg_namespace AS procedure_schema
              ON procedure_schema.oid = procedure_row.pronamespace
            WHERE trigger_row.oid IS NULL
               OR procedure_schema.nspname IS DISTINCT FROM schema_name
               OR procedure_row.proname IS DISTINCT FROM 'prevent_okf_rebuild_failure_audit_mutation'
               OR trigger_row.tgfoid IS DISTINCT FROM append_only_function_oid
               OR trigger_row.tgtype IS DISTINCT FROM expected.expected_type
               OR trigger_row.tgenabled IS DISTINCT FROM 'O'
               OR trigger_row.tgisinternal
               OR trigger_row.tgargs IS DISTINCT FROM ''::bytea
               OR trigger_row.tgqual IS NOT NULL
               OR trigger_row.tgattr IS DISTINCT FROM ''::int2vector
               OR trigger_row.tgconstraint <> 0
               OR (
                   SELECT pg_catalog.count(*)
                   FROM pg_catalog.pg_trigger AS observed_trigger
                   WHERE observed_trigger.tgrelid = audit_oid
               ) <> (
                   SELECT pg_catalog.count(*)
                   FROM expected
               )
        ) THEN
            RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
        END IF;

        EXECUTE pg_catalog.format(
            'SELECT EXISTS (SELECT 1 FROM %s AS link '
            || 'LEFT JOIN %s AS owner ON owner.ownership_id = link.ownership_id '
            || 'LEFT JOIN %s AS target ON target.version_id = link.version_id '
            || 'AND target.evidence_id = link.evidence_id '
            || 'AND target.entity_id IS NOT DISTINCT FROM link.manual_entity_id '
            || 'AND target.relation_id IS NOT DISTINCT FROM link.manual_relation_id '
            || 'WHERE (link.source_kind <> ''manual_okf'' AND '
            || '(link.ownership_id IS NOT NULL OR link.ownership_scope_version_id IS NOT NULL '
            || 'OR link.manual_entity_id IS NOT NULL OR link.manual_relation_id IS NOT NULL)) '
            || 'OR (link.source_kind = ''manual_okf'' AND '
            || '(link.evidence_id IS NULL OR link.ownership_id IS NULL '
            || 'OR link.ownership_scope_version_id IS NULL '
            || 'OR num_nonnulls(link.manual_entity_id, link.manual_relation_id) <> 1 '
            || 'OR owner.ownership_id IS NULL OR target.evidence_id IS NULL)))',
            evidence_links_ref, ownership_ref, targets_ref
        ) INTO final_row_drift;
        IF final_row_drift THEN
            RAISE EXCEPTION 'e2a_preflight_final_row_drift';
        END IF;
        -- Detection-only final re-attestation.
        append_only_function_final_oid := NULL;
        append_only_function_final_source := NULL;
        append_only_function_final_shape := false;
        append_only_function_final_source_matches := false;
        append_only_function_final_trigger_shape := false;
        SELECT pg_catalog.count(*) = 1
           AND NOT EXISTS (
               SELECT 1
               FROM pg_catalog.pg_proc AS procedure_row
               JOIN pg_catalog.pg_namespace AS procedure_schema
                 ON procedure_schema.oid = procedure_row.pronamespace
               JOIN pg_catalog.pg_language AS language_row
                 ON language_row.oid = procedure_row.prolang
               WHERE procedure_schema.nspname = schema_name
                 AND procedure_row.proname = 'prevent_okf_rebuild_failure_audit_mutation'
                 AND (procedure_row.oid IS DISTINCT FROM append_only_function_oid
                      OR procedure_row.prokind IS DISTINCT FROM 'f'
                      OR procedure_row.pronargs IS DISTINCT FROM 0
                      OR procedure_row.proargtypes IS DISTINCT FROM ''::pg_catalog.oidvector
                      OR procedure_row.provariadic IS DISTINCT FROM 0::pg_catalog.oid
                      OR procedure_row.prorettype IS DISTINCT FROM 'trigger'::pg_catalog.regtype
                      OR procedure_row.proretset
                      OR language_row.lanname IS DISTINCT FROM 'plpgsql')
           ) INTO append_only_function_final_shape
        FROM pg_catalog.pg_proc AS procedure_row
        JOIN pg_catalog.pg_namespace AS procedure_schema
          ON procedure_schema.oid = procedure_row.pronamespace
        WHERE procedure_schema.nspname = schema_name
          AND procedure_row.proname = 'prevent_okf_rebuild_failure_audit_mutation';
        SELECT procedure_row.oid, procedure_row.prosrc
          INTO append_only_function_final_oid, append_only_function_final_source
        FROM pg_catalog.pg_proc AS procedure_row
        JOIN pg_catalog.pg_namespace AS procedure_schema
          ON procedure_schema.oid = procedure_row.pronamespace
        WHERE procedure_schema.nspname = schema_name
          AND procedure_row.proname = 'prevent_okf_rebuild_failure_audit_mutation'
        ORDER BY procedure_row.oid
        LIMIT 1;
        IF NOT append_only_function_final_shape
           OR append_only_function_final_oid IS DISTINCT FROM append_only_function_oid
           OR append_only_function_final_source IS NULL THEN
            RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
        END IF;
        e2a_normalize_expression_input := append_only_function_final_source;
            e2a_normalize_expression_output := '';
            e2a_normalize_expression_index := 1;
            e2a_normalize_expression_depth := 0;
            e2a_normalize_expression_pending_space := false;
            WHILE e2a_normalize_expression_index <= pg_catalog.length(e2a_normalize_expression_input) LOOP
                e2a_normalize_expression_character := pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index, 1);
                IF e2a_normalize_expression_character IN (' ', E'\t', E'\n', E'\r', E'\f') THEN
                    e2a_normalize_expression_pending_space := e2a_normalize_expression_output <> '';
                    e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                ELSIF pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index, 2) = '--' THEN
                    e2a_normalize_expression_index := e2a_normalize_expression_index + 2;
                    WHILE e2a_normalize_expression_index <= pg_catalog.length(e2a_normalize_expression_input)
                          AND pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index, 1) NOT IN (E'\n', E'\r') LOOP
                        e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                    END LOOP;
                    e2a_normalize_expression_pending_space := e2a_normalize_expression_output <> '';
                ELSIF pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index, 2) = '/*' THEN
                    e2a_normalize_expression_comment_depth := 1;
                    e2a_normalize_expression_index := e2a_normalize_expression_index + 2;
                    WHILE e2a_normalize_expression_index <= pg_catalog.length(e2a_normalize_expression_input)
                          AND e2a_normalize_expression_comment_depth > 0 LOOP
                        IF pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index, 2) = '/*' THEN
                            e2a_normalize_expression_comment_depth := e2a_normalize_expression_comment_depth + 1;
                            e2a_normalize_expression_index := e2a_normalize_expression_index + 2;
                        ELSIF pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index, 2) = '*/' THEN
                            e2a_normalize_expression_comment_depth := e2a_normalize_expression_comment_depth - 1;
                            e2a_normalize_expression_index := e2a_normalize_expression_index + 2;
                        ELSE
                            e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                        END IF;
                    END LOOP;
                    IF e2a_normalize_expression_comment_depth <> 0 THEN
                        RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
                    END IF;
                    e2a_normalize_expression_pending_space := e2a_normalize_expression_output <> '';
                ELSIF pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index, 2) = '*/' THEN
                    RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
                ELSIF e2a_normalize_expression_character = '$'
                        AND (e2a_normalize_expression_index = 1
                            OR pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index - 1, 1) ~ '^[[:ascii:]]$'
                            AND pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index - 1, 1) !~ '^[A-Za-z0-9_$]$') THEN
                    e2a_normalize_expression_tag := substring(
                        pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index)
                        FROM '^\$(?:[A-Za-z_][A-Za-z_0-9]*)?\$'
                    );
                    IF e2a_normalize_expression_tag IS NULL THEN
                        IF substring(
                            pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index)
                            FROM '^\$[0-9][A-Za-z_0-9]*\$'
                        ) IS NOT NULL
                        OR substring(
                            pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index)
                            FROM '^\$[A-Za-z_0-9]'
                        ) IS NOT NULL
                        OR substring(
                            pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index)
                            FROM '^\$[^[:ascii:]]'
                        ) IS NOT NULL
                        OR substring(
                            pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index)
                            FROM '^\$[A-Za-z_][A-Za-z_0-9]*[^[:ascii:]]'
                        ) IS NOT NULL THEN
                            RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
                        END IF;
                        e2a_normalize_expression_output := e2a_normalize_expression_output || '$';
                        e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                    ELSE
                        e2a_normalize_expression_next := position(
                            e2a_normalize_expression_tag IN pg_catalog.substr(
                                e2a_normalize_expression_input,
                                e2a_normalize_expression_index + pg_catalog.length(e2a_normalize_expression_tag)
                            )
                        );
                        IF e2a_normalize_expression_next = 0 THEN
                            RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
                        END IF;
                        e2a_normalize_expression_output := e2a_normalize_expression_output
                            || pg_catalog.substr(
                                e2a_normalize_expression_input,
                                e2a_normalize_expression_index,
                                (2 * pg_catalog.length(e2a_normalize_expression_tag))
                                + e2a_normalize_expression_next - 1
                            );
                        e2a_normalize_expression_index := e2a_normalize_expression_index
                            + (2 * pg_catalog.length(e2a_normalize_expression_tag))
                            + e2a_normalize_expression_next - 1;
                    END IF;
                ELSIF e2a_normalize_expression_character IN ('''', '"') THEN
                    e2a_normalize_expression_quote := e2a_normalize_expression_character;
                    e2a_normalize_expression_escape := e2a_normalize_expression_quote = ''''
                        AND e2a_normalize_expression_index > 1
                        AND pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index - 1, 1) IN ('E', 'e')
                        AND (e2a_normalize_expression_index = 2
                            OR pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index - 2, 1) ~ '^[[:ascii:]]$'
                            AND pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index - 2, 1) !~ '^[A-Za-z0-9_$]$');
                    e2a_normalize_expression_output := e2a_normalize_expression_output || e2a_normalize_expression_character;
                    e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                    LOOP
                        IF e2a_normalize_expression_index > pg_catalog.length(e2a_normalize_expression_input) THEN
                            RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
                        END IF;
                        e2a_normalize_expression_character := pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index, 1);
                        e2a_normalize_expression_output := e2a_normalize_expression_output || e2a_normalize_expression_character;
                        IF e2a_normalize_expression_escape AND e2a_normalize_expression_character = E'\\' THEN
                            IF e2a_normalize_expression_index = pg_catalog.length(e2a_normalize_expression_input) THEN
                                RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
                            END IF;
                            e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                            e2a_normalize_expression_output := e2a_normalize_expression_output || pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index, 1);
                        ELSIF e2a_normalize_expression_character = e2a_normalize_expression_quote THEN
                            IF pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index + 1, 1) = e2a_normalize_expression_quote THEN
                                e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                                e2a_normalize_expression_output := e2a_normalize_expression_output || e2a_normalize_expression_quote;
                            ELSE
                                e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                                EXIT;
                            END IF;
                        END IF;
                        e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                    END LOOP;
                ELSE
                    IF e2a_normalize_expression_character = '(' THEN
                        e2a_normalize_expression_depth := e2a_normalize_expression_depth + 1;
                    ELSIF e2a_normalize_expression_character = ')' THEN
                        e2a_normalize_expression_depth := e2a_normalize_expression_depth - 1;
                        IF e2a_normalize_expression_depth < 0 THEN
                            RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
                        END IF;
                    END IF;
                    IF e2a_normalize_expression_pending_space
                       AND (e2a_normalize_expression_output ~ '[A-Za-z0-9_$]$'
                            OR e2a_normalize_expression_output ~ '[^[:ascii:]]$')
                       AND (e2a_normalize_expression_character ~ '^[A-Za-z0-9_$]$'
                            OR e2a_normalize_expression_character ~ '^[^[:ascii:]]$') THEN
                        e2a_normalize_expression_output := e2a_normalize_expression_output || ' ';
                    END IF;
                    e2a_normalize_expression_pending_space := false;
                    e2a_normalize_expression_output := e2a_normalize_expression_output || e2a_normalize_expression_character;
                    e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                END IF;
            END LOOP;
            IF e2a_normalize_expression_depth <> 0 THEN
                RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
            END IF;
            -- Re-lex the normalized bytes before each strip: literal, quoted,
            -- dollar, and comment parentheses cannot close an outer wrapper.
            WHILE pg_catalog.left(e2a_normalize_expression_output, 1) = '('
              AND pg_catalog.right(e2a_normalize_expression_output, 1) = ')'
              AND pg_catalog.length(e2a_normalize_expression_output) > 2 LOOP
                e2a_normalize_expression_outer := true;
                e2a_normalize_expression_depth := 0;
                e2a_normalize_expression_index := 1;
                WHILE e2a_normalize_expression_index
                      <= pg_catalog.length(e2a_normalize_expression_output) LOOP
                    e2a_normalize_expression_character := pg_catalog.substr(
                        e2a_normalize_expression_output,
                        e2a_normalize_expression_index,
                        1
                    );
                    IF pg_catalog.substr(
                        e2a_normalize_expression_output,
                        e2a_normalize_expression_index,
                        2
                    ) = '--' THEN
                        e2a_normalize_expression_index := e2a_normalize_expression_index + 2;
                        WHILE e2a_normalize_expression_index
                              <= pg_catalog.length(e2a_normalize_expression_output)
                          AND pg_catalog.substr(
                              e2a_normalize_expression_output,
                              e2a_normalize_expression_index,
                              1
                          ) NOT IN (E'\n', E'\r') LOOP
                            e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                        END LOOP;
                    ELSIF pg_catalog.substr(
                        e2a_normalize_expression_output,
                        e2a_normalize_expression_index,
                        2
                    ) = '/*' THEN
                        e2a_normalize_expression_comment_depth := 1;
                        e2a_normalize_expression_index := e2a_normalize_expression_index + 2;
                        WHILE e2a_normalize_expression_index
                              <= pg_catalog.length(e2a_normalize_expression_output)
                          AND e2a_normalize_expression_comment_depth > 0 LOOP
                            IF pg_catalog.substr(
                                e2a_normalize_expression_output,
                                e2a_normalize_expression_index,
                                2
                            ) = '/*' THEN
                                e2a_normalize_expression_comment_depth := e2a_normalize_expression_comment_depth + 1;
                                e2a_normalize_expression_index := e2a_normalize_expression_index + 2;
                            ELSIF pg_catalog.substr(
                                e2a_normalize_expression_output,
                                e2a_normalize_expression_index,
                                2
                            ) = '*/' THEN
                                e2a_normalize_expression_comment_depth := e2a_normalize_expression_comment_depth - 1;
                                e2a_normalize_expression_index := e2a_normalize_expression_index + 2;
                            ELSE
                                e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                            END IF;
                        END LOOP;
                        IF e2a_normalize_expression_comment_depth <> 0 THEN
                            RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
                        END IF;
                    ELSIF pg_catalog.substr(
                        e2a_normalize_expression_output,
                        e2a_normalize_expression_index,
                        2
                    ) = '*/' THEN
                        RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
                    ELSIF e2a_normalize_expression_character = '$'
                      AND (e2a_normalize_expression_index = 1
                        OR pg_catalog.substr(
                            e2a_normalize_expression_output,
                            e2a_normalize_expression_index - 1,
                            1
                        ) ~ '^[[:ascii:]]$'
                        AND pg_catalog.substr(
                            e2a_normalize_expression_output,
                            e2a_normalize_expression_index - 1,
                            1
                        ) !~ '^[A-Za-z0-9_$]$') THEN
                        e2a_normalize_expression_tag := substring(
                            pg_catalog.substr(
                                e2a_normalize_expression_output,
                                e2a_normalize_expression_index
                            ) FROM '^\$(?:[A-Za-z_][A-Za-z_0-9]*)?\$'
                        );
                        IF e2a_normalize_expression_tag IS NULL THEN
                            IF substring(
                                pg_catalog.substr(
                                    e2a_normalize_expression_output,
                                    e2a_normalize_expression_index
                                ) FROM '^\$[A-Za-z_0-9]'
                            ) IS NOT NULL
                            OR substring(
                                pg_catalog.substr(
                                    e2a_normalize_expression_output,
                                    e2a_normalize_expression_index
                                ) FROM '^\$[^[:ascii:]]'
                            ) IS NOT NULL
                            OR substring(
                                pg_catalog.substr(
                                    e2a_normalize_expression_output,
                                    e2a_normalize_expression_index
                                ) FROM '^\$[A-Za-z_][A-Za-z_0-9]*[^[:ascii:]]'
                            ) IS NOT NULL THEN
                                RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
                            END IF;
                            e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                        ELSE
                            e2a_normalize_expression_next := position(
                                e2a_normalize_expression_tag IN pg_catalog.substr(
                                    e2a_normalize_expression_output,
                                    e2a_normalize_expression_index
                                    + pg_catalog.length(e2a_normalize_expression_tag)
                                )
                            );
                            IF e2a_normalize_expression_next = 0 THEN
                                RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
                            END IF;
                            e2a_normalize_expression_index := e2a_normalize_expression_index
                                + (2 * pg_catalog.length(e2a_normalize_expression_tag))
                                + e2a_normalize_expression_next - 1;
                        END IF;
                    ELSIF e2a_normalize_expression_character IN ('''', '"') THEN
                        e2a_normalize_expression_quote := e2a_normalize_expression_character;
                        e2a_normalize_expression_escape := e2a_normalize_expression_quote = ''''
                            AND e2a_normalize_expression_index > 1
                            AND pg_catalog.substr(
                                e2a_normalize_expression_output,
                                e2a_normalize_expression_index - 1,
                                1
                            ) IN ('E', 'e')
                            AND (e2a_normalize_expression_index = 2
                                OR pg_catalog.substr(
                                    e2a_normalize_expression_output,
                                    e2a_normalize_expression_index - 2,
                                    1
                                ) ~ '^[[:ascii:]]$'
                                AND pg_catalog.substr(
                                    e2a_normalize_expression_output,
                                    e2a_normalize_expression_index - 2,
                                    1
                                ) !~ '^[A-Za-z0-9_$]$');
                        e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                        LOOP
                            IF e2a_normalize_expression_index
                               > pg_catalog.length(e2a_normalize_expression_output) THEN
                                RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
                            END IF;
                            e2a_normalize_expression_character := pg_catalog.substr(
                                e2a_normalize_expression_output,
                                e2a_normalize_expression_index,
                                1
                            );
                            IF e2a_normalize_expression_escape
                               AND e2a_normalize_expression_character = E'\\' THEN
                                IF e2a_normalize_expression_index
                                   = pg_catalog.length(e2a_normalize_expression_output) THEN
                                    RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
                                END IF;
                                e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                            ELSIF e2a_normalize_expression_character
                                  = e2a_normalize_expression_quote THEN
                                IF pg_catalog.substr(
                                    e2a_normalize_expression_output,
                                    e2a_normalize_expression_index + 1,
                                    1
                                ) = e2a_normalize_expression_quote THEN
                                    e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                                ELSE
                                    e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                                    EXIT;
                                END IF;
                            END IF;
                            e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                        END LOOP;
                    ELSE
                        IF e2a_normalize_expression_character = '(' THEN
                            e2a_normalize_expression_depth := e2a_normalize_expression_depth + 1;
                        ELSIF e2a_normalize_expression_character = ')' THEN
                            e2a_normalize_expression_depth := e2a_normalize_expression_depth - 1;
                            IF e2a_normalize_expression_depth < 0 THEN
                                RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
                            ELSIF e2a_normalize_expression_depth = 0
                              AND e2a_normalize_expression_index
                                  < pg_catalog.length(e2a_normalize_expression_output) THEN
                                e2a_normalize_expression_outer := false;
                                EXIT;
                            END IF;
                        END IF;
                        e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                    END IF;
                END LOOP;
                IF e2a_normalize_expression_depth <> 0 THEN
                    RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
                END IF;
                EXIT WHEN NOT e2a_normalize_expression_outer;
                e2a_normalize_expression_output := pg_catalog.substr(
                    e2a_normalize_expression_output,
                    2,
                    pg_catalog.length(e2a_normalize_expression_output) - 2
                );
            END LOOP;
        append_only_function_final_source_matches :=
            e2a_normalize_expression_output
                IS NOT DISTINCT FROM append_only_function_source_expected;
        IF NOT append_only_function_final_source_matches THEN
            RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
        END IF;
        SELECT NOT EXISTS (
            WITH expected(trigger_name, expected_type) AS (
                VALUES
                    ('trg_okf_rebuild_failure_audit_append_only', 27::smallint),
                    ('trg_okf_rebuild_failure_audit_no_truncate', 34::smallint)
            )
            SELECT 1
            FROM expected
            LEFT JOIN pg_catalog.pg_trigger AS trigger_row
              ON trigger_row.tgrelid = audit_oid
             AND trigger_row.tgname = expected.trigger_name
            LEFT JOIN pg_catalog.pg_proc AS procedure_row
              ON procedure_row.oid = trigger_row.tgfoid
            LEFT JOIN pg_catalog.pg_namespace AS procedure_schema
              ON procedure_schema.oid = procedure_row.pronamespace
            WHERE trigger_row.oid IS NULL
               OR procedure_schema.nspname IS DISTINCT FROM schema_name
               OR procedure_row.proname IS DISTINCT FROM 'prevent_okf_rebuild_failure_audit_mutation'
               OR trigger_row.tgfoid IS DISTINCT FROM append_only_function_final_oid
               OR trigger_row.tgtype IS DISTINCT FROM expected.expected_type
               OR trigger_row.tgenabled IS DISTINCT FROM 'O'
               OR trigger_row.tgisinternal
               OR trigger_row.tgargs IS DISTINCT FROM ''::bytea
               OR trigger_row.tgqual IS NOT NULL
               OR trigger_row.tgattr IS DISTINCT FROM ''::int2vector
               OR trigger_row.tgconstraint <> 0
               OR (
                   SELECT pg_catalog.count(*)
                   FROM pg_catalog.pg_trigger AS observed_trigger
                   WHERE observed_trigger.tgrelid = audit_oid
               ) <> (
                   SELECT pg_catalog.count(*)
                   FROM expected
               )
        ) INTO append_only_function_final_trigger_shape;
        IF NOT append_only_function_final_trigger_shape THEN
            RAISE EXCEPTION 'e2a_preflight_final_catalog_drift';
        END IF;
        RETURN;
    END IF;

    -- Only the exact fresh signature reaches this DDL phase.
    EXECUTE pg_catalog.format(
        'ALTER TABLE %s ADD CONSTRAINT %I UNIQUE (doc_id, version_id)',
        document_versions_ref, 'uq_document_versions_doc_version'
    );
    EXECUTE pg_catalog.format(
        'ALTER TABLE %s ADD CONSTRAINT %I UNIQUE (version_id, span_id)',
        canonical_spans_ref, 'uq_canonical_spans_version_span'
    );
    EXECUTE pg_catalog.format(
        'ALTER TABLE %s ADD CONSTRAINT %I UNIQUE (version_id, evidence_id)',
        evidence_ref, 'uq_evidence_version_evidence'
    );

    -- Shape-drop only the preflight-approved CASCADE legacy identities.
    FOR cstr_record IN
        WITH expected(target_oid, source_columns, target_columns) AS (
            VALUES
                (document_versions_oid, ARRAY['version_id'], ARRAY['version_id']),
                (canonical_spans_oid, ARRAY['span_id'], ARRAY['span_id']),
                (evidence_oid, ARRAY['evidence_id'], ARRAY['evidence_id']),
                (entities_oid, ARRAY['entity_id'], ARRAY['entity_id']),
                (relations_oid, ARRAY['relation_id'], ARRAY['relation_id'])
        )
        SELECT constraint_row.oid, constraint_row.conname
        FROM pg_catalog.pg_constraint AS constraint_row
        JOIN expected ON expected.target_oid = constraint_row.confrelid
        WHERE constraint_row.conrelid = evidence_links_oid
          AND constraint_row.contype = 'f'
          AND constraint_row.confdeltype = 'c'
          AND constraint_row.conkey = ARRAY(
              SELECT attribute_row.attnum FROM pg_catalog.unnest(expected.source_columns) WITH ORDINALITY AS column_row(column_name, ordinality)
              JOIN pg_catalog.pg_attribute AS attribute_row ON attribute_row.attrelid = evidence_links_oid AND attribute_row.attname = column_row.column_name
              ORDER BY column_row.ordinality
          )
          AND constraint_row.confkey = ARRAY(
              SELECT attribute_row.attnum FROM pg_catalog.unnest(expected.target_columns) WITH ORDINALITY AS column_row(column_name, ordinality)
              JOIN pg_catalog.pg_attribute AS attribute_row ON attribute_row.attrelid = expected.target_oid AND attribute_row.attname = column_row.column_name
              ORDER BY column_row.ordinality
          )
    LOOP
        legacy_cascade_oid := cstr_record.oid;
        IF NOT EXISTS (
            SELECT 1 FROM pg_catalog.pg_constraint AS constraint_row
            WHERE constraint_row.oid = legacy_cascade_oid
              AND constraint_row.conrelid = evidence_links_oid
              AND constraint_row.contype = 'f'
              AND constraint_row.confdeltype = 'c'
              AND constraint_row.convalidated
              AND constraint_row.confmatchtype = 's'
              AND constraint_row.confupdtype = 'a'
              AND NOT constraint_row.condeferrable
              AND NOT constraint_row.condeferred
        ) THEN
            RAISE EXCEPTION 'e2a_preflight_legacy_fk_changed';
        END IF;
        EXECUTE pg_catalog.format(
            'ALTER TABLE %s DROP CONSTRAINT %I', evidence_links_ref, cstr_record.conname
        );
    END LOOP;

    EXECUTE pg_catalog.format($ddl$
        CREATE TABLE %s (
            ownership_id uuid NOT NULL,
            okf_relative_path text NOT NULL,
            fact_kind text NOT NULL,
            fact_id uuid NOT NULL,
            entity_id uuid,
            relation_id uuid,
            source_digest char(64) NOT NULL,
            document_id uuid,
            version_id uuid,
            scope_version_id uuid NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000'::uuid,
            created_at timestamp with time zone NOT NULL DEFAULT now(),
            CONSTRAINT pk_okf_manual_fact_ownership PRIMARY KEY (ownership_id),
            CONSTRAINT chk_okf_manual_fact_ownership_path CHECK (okf_relative_path <> ''::text AND okf_relative_path !~ '^(?:/|\\)'::text AND okf_relative_path !~ '/$'::text AND okf_relative_path !~ '//'::text AND okf_relative_path !~ '(^|/)(\.|\.\.)(/|$)'::text AND okf_relative_path !~ '[\\:]'::text AND okf_relative_path !~ '(^|/)[^/]*[. ](/|$)'::text AND okf_relative_path !~* '(^|/)(con|prn|aux|nul|com[1-9]|lpt[1-9])(\.[^/]*)?(/|$)'::text),
            CONSTRAINT chk_okf_manual_fact_ownership_kind CHECK (fact_kind = ANY (ARRAY['entity'::text, 'relation'::text])),
            CONSTRAINT chk_okf_manual_fact_ownership_digest CHECK (source_digest ~ '^[0-9a-f]{64}$'::text),
            CONSTRAINT chk_okf_manual_fact_ownership_target CHECK (((fact_kind = 'entity'::text) AND (entity_id IS NOT NULL) AND (entity_id = fact_id) AND (relation_id IS NULL)) OR ((fact_kind = 'relation'::text) AND (relation_id IS NOT NULL) AND (relation_id = fact_id) AND (entity_id IS NULL))),
            CONSTRAINT chk_okf_manual_fact_ownership_scope CHECK (((scope_version_id = '00000000-0000-0000-0000-000000000000'::uuid) AND (document_id IS NULL) AND (version_id IS NULL)) OR ((scope_version_id = version_id) AND (document_id IS NOT NULL) AND (version_id IS NOT NULL))),
            CONSTRAINT fk_okf_manual_fact_ownership_entity FOREIGN KEY (entity_id) REFERENCES %s(entity_id) ON DELETE RESTRICT,
            CONSTRAINT fk_okf_manual_fact_ownership_relation FOREIGN KEY (relation_id) REFERENCES %s(relation_id) ON DELETE RESTRICT,
            CONSTRAINT fk_okf_manual_fact_ownership_document_version FOREIGN KEY (document_id, version_id) REFERENCES %s(doc_id, version_id) ON DELETE RESTRICT,
            CONSTRAINT uq_okf_manual_fact_ownership_path_fact UNIQUE (okf_relative_path, fact_kind, fact_id),
            CONSTRAINT uq_okf_manual_fact_ownership_entity_target UNIQUE (ownership_id, entity_id),
            CONSTRAINT uq_okf_manual_fact_ownership_relation_target UNIQUE (ownership_id, relation_id),
            CONSTRAINT uq_okf_manual_fact_ownership_scope UNIQUE (ownership_id, scope_version_id)
        )
        $ddl$, ownership_ref, entities_ref, relations_ref, document_versions_ref
    );
    EXECUTE pg_catalog.format($ddl$
        CREATE TABLE %s (
            version_id uuid NOT NULL,
            evidence_id uuid NOT NULL,
            entity_id uuid,
            relation_id uuid,
            CONSTRAINT pk_okf_manual_evidence_targets PRIMARY KEY (version_id, evidence_id),
            CONSTRAINT uq_okf_manual_evidence_targets_entity UNIQUE (version_id, evidence_id, entity_id),
            CONSTRAINT uq_okf_manual_evidence_targets_relation UNIQUE (version_id, evidence_id, relation_id),
            CONSTRAINT chk_okf_manual_evidence_targets_exactly_one_target CHECK (num_nonnulls(entity_id, relation_id) = 1),
            CONSTRAINT fk_okf_manual_evidence_targets_version_evidence FOREIGN KEY (version_id, evidence_id) REFERENCES %s(version_id, evidence_id) ON DELETE RESTRICT,
            CONSTRAINT fk_okf_manual_evidence_targets_entity FOREIGN KEY (entity_id) REFERENCES %s(entity_id) ON DELETE RESTRICT,
            CONSTRAINT fk_okf_manual_evidence_targets_relation FOREIGN KEY (relation_id) REFERENCES %s(relation_id) ON DELETE RESTRICT
        )
        $ddl$, targets_ref, evidence_ref, entities_ref, relations_ref
    );
    EXECUTE pg_catalog.format(
        'ALTER TABLE %s ADD COLUMN ownership_id uuid, '
        || 'ADD COLUMN ownership_scope_version_id uuid, '
        || 'ADD COLUMN manual_entity_id UUID, '
        || 'ADD COLUMN manual_relation_id UUID, '
        || 'ALTER COLUMN source_kind SET DEFAULT ''legacy''::text',
        evidence_links_ref
    );
    EXECUTE pg_catalog.format($ddl$
        ALTER TABLE %s
            ADD CONSTRAINT fk_evidence_links_version FOREIGN KEY (version_id) REFERENCES %s(version_id) ON DELETE RESTRICT,
            ADD CONSTRAINT fk_evidence_links_entity FOREIGN KEY (entity_id) REFERENCES %s(entity_id) ON DELETE RESTRICT,
            ADD CONSTRAINT fk_evidence_links_relation FOREIGN KEY (relation_id) REFERENCES %s(relation_id) ON DELETE RESTRICT,
            ADD CONSTRAINT fk_evidence_links_version_span FOREIGN KEY (version_id, span_id) REFERENCES %s(version_id, span_id) ON DELETE RESTRICT,
            ADD CONSTRAINT fk_evidence_links_version_evidence FOREIGN KEY (version_id, evidence_id) REFERENCES %s(version_id, evidence_id) ON DELETE RESTRICT,
            ADD CONSTRAINT fk_evidence_links_ownership FOREIGN KEY (ownership_id) REFERENCES %s(ownership_id) ON DELETE RESTRICT,
            ADD CONSTRAINT fk_evidence_links_ownership_scope FOREIGN KEY (ownership_id, ownership_scope_version_id) REFERENCES %s(ownership_id, scope_version_id) ON DELETE RESTRICT,
            ADD CONSTRAINT fk_evidence_links_manual_entity_owner FOREIGN KEY (ownership_id, manual_entity_id) REFERENCES %s(ownership_id, entity_id) ON DELETE RESTRICT,
            ADD CONSTRAINT fk_evidence_links_manual_relation_owner FOREIGN KEY (ownership_id, manual_relation_id) REFERENCES %s(ownership_id, relation_id) ON DELETE RESTRICT,
            ADD CONSTRAINT fk_evidence_links_manual_entity_target FOREIGN KEY (version_id, evidence_id, manual_entity_id) REFERENCES %s(version_id, evidence_id, entity_id) ON DELETE RESTRICT,
            ADD CONSTRAINT fk_evidence_links_manual_relation_target FOREIGN KEY (version_id, evidence_id, manual_relation_id) REFERENCES %s(version_id, evidence_id, relation_id) ON DELETE RESTRICT,
            ADD CONSTRAINT chk_evidence_links_exactly_one_target CHECK (num_nonnulls(entity_id, relation_id) = 1),
            ADD CONSTRAINT chk_evidence_links_manual_projection CHECK ((source_kind <> 'manual_okf'::text AND ownership_id IS NULL AND ownership_scope_version_id IS NULL AND manual_entity_id IS NULL AND manual_relation_id IS NULL) OR (source_kind = 'manual_okf'::text AND evidence_id IS NOT NULL AND ownership_id IS NOT NULL AND ownership_scope_version_id IS NOT NULL AND num_nonnulls(manual_entity_id, manual_relation_id) = 1 AND (((manual_entity_id IS NOT NULL) AND (entity_id IS NOT NULL) AND (manual_entity_id = entity_id) AND (manual_relation_id IS NULL)) OR ((manual_relation_id IS NOT NULL) AND (relation_id IS NOT NULL) AND (manual_relation_id = relation_id) AND (manual_entity_id IS NULL))))),
            ADD CONSTRAINT chk_evidence_links_manual_scope CHECK (((source_kind = 'manual_okf'::text) AND (ownership_scope_version_id IS NOT NULL) AND ((ownership_scope_version_id = version_id) OR (ownership_scope_version_id = '00000000-0000-0000-0000-000000000000'::uuid))) OR ((source_kind <> 'manual_okf'::text) AND (ownership_scope_version_id IS NULL)))
        $ddl$, evidence_links_ref, document_versions_ref, entities_ref, relations_ref,
        canonical_spans_ref, evidence_ref, ownership_ref, ownership_ref, ownership_ref,
        ownership_ref, targets_ref, targets_ref
    );

    EXECUTE pg_catalog.format('CREATE UNIQUE INDEX %I ON %s (version_id, span_id, manual_entity_id, evidence_id, ownership_id) WHERE (source_kind = ''manual_okf''::text) AND (manual_entity_id IS NOT NULL)', 'idx_evidence_links_e2a_entity_dedup', evidence_links_ref);
    EXECUTE pg_catalog.format('CREATE UNIQUE INDEX %I ON %s (version_id, span_id, manual_relation_id, evidence_id, ownership_id) WHERE (source_kind = ''manual_okf''::text) AND (manual_relation_id IS NOT NULL)', 'idx_evidence_links_e2a_relation_dedup', evidence_links_ref);
    EXECUTE pg_catalog.format('CREATE INDEX %I ON %s (version_id, span_id)', 'idx_evidence_links_version_span', evidence_links_ref);
    EXECUTE pg_catalog.format('CREATE INDEX %I ON %s (version_id, evidence_id)', 'idx_evidence_links_version_evidence', evidence_links_ref);
    EXECUTE pg_catalog.format('CREATE INDEX %I ON %s (ownership_id)', 'idx_evidence_links_ownership_id', evidence_links_ref);
    EXECUTE pg_catalog.format('CREATE INDEX %I ON %s (ownership_id, ownership_scope_version_id)', 'idx_evidence_links_ownership_scope', evidence_links_ref);
    EXECUTE pg_catalog.format('CREATE INDEX %I ON %s (ownership_id, manual_entity_id)', 'idx_evidence_links_manual_entity_owner', evidence_links_ref);
    EXECUTE pg_catalog.format('CREATE INDEX %I ON %s (ownership_id, manual_relation_id)', 'idx_evidence_links_manual_relation_owner', evidence_links_ref);
    EXECUTE pg_catalog.format('CREATE INDEX %I ON %s (version_id, evidence_id, manual_entity_id)', 'idx_evidence_links_version_evidence_manual_entity', evidence_links_ref);
    EXECUTE pg_catalog.format('CREATE INDEX %I ON %s (version_id, evidence_id, manual_relation_id)', 'idx_evidence_links_version_evidence_manual_relation', evidence_links_ref);
    EXECUTE pg_catalog.format('CREATE INDEX %I ON %s (document_id, version_id)', 'idx_okf_manual_fact_ownership_document_version', ownership_ref);
    EXECUTE pg_catalog.format('CREATE INDEX %I ON %s (scope_version_id, ownership_id)', 'idx_okf_manual_fact_ownership_scope_version', ownership_ref);
    EXECUTE pg_catalog.format('CREATE INDEX %I ON %s (entity_id)', 'idx_okf_manual_fact_ownership_entity', ownership_ref);
    EXECUTE pg_catalog.format('CREATE INDEX %I ON %s (relation_id)', 'idx_okf_manual_fact_ownership_relation', ownership_ref);
    EXECUTE pg_catalog.format('CREATE INDEX %I ON %s (version_id, evidence_id)', 'idx_okf_manual_evidence_targets_version_evidence', targets_ref);
    EXECUTE pg_catalog.format('CREATE INDEX %I ON %s (entity_id)', 'idx_okf_manual_evidence_targets_entity', targets_ref);
    EXECUTE pg_catalog.format('CREATE INDEX %I ON %s (relation_id)', 'idx_okf_manual_evidence_targets_relation', targets_ref);
    -- Preexisting sync rows are deliberately classified only by the conservative
    -- default: materialization_owner TEXT NOT NULL DEFAULT 'legacy_pre_e2a'.
    -- Allowed values are materialization_owner IN ('legacy_pre_e2a', 'e2a').
    -- No status, path, hash, or timestamp can promote legacy ownership.
    EXECUTE pg_catalog.format(
        'ALTER TABLE %s ADD COLUMN materialization_owner TEXT NOT NULL DEFAULT ''legacy_pre_e2a'', '
        || 'ADD CONSTRAINT %I CHECK (materialization_owner IN (''legacy_pre_e2a'', ''e2a''))',
        sync_state_ref, 'chk_okf_sync_state_materialization_owner'
    );

    -- Verify the 018 predecessor exactly, then atomically widen and validate it.
    IF NOT old_audit_check_matches THEN
        RAISE EXCEPTION 'e2a_preflight_audit_check_drift';
    END IF;
    EXECUTE pg_catalog.format(
        'ALTER TABLE %s DROP CONSTRAINT %I',
        audit_ref, 'chk_okf_rebuild_failure_audit_phase'
    );
    EXECUTE pg_catalog.format(
        'ALTER TABLE %s ADD CONSTRAINT %I CHECK (failure_phase = ANY (ARRAY['
        || '''target_validation''::text, ''scope_lock''::text, '
        || '''parent_reconciliation''::text, ''span_reconciliation''::text, '
        || '''tree_reconciliation''::text, ''chunk_reconciliation''::text, '
        || '''manual_fact_reconciliation''::text, ''evidence_reconciliation''::text, '
        || '''transaction_commit''::text, ''success_log_write''::text])) NOT VALID',
        audit_ref, 'chk_okf_rebuild_failure_audit_phase'
    );
    EXECUTE pg_catalog.format(
        'ALTER TABLE %s VALIDATE CONSTRAINT %I',
        audit_ref, 'chk_okf_rebuild_failure_audit_phase'
    );
        -- Detection-only fresh re-attestation.
        append_only_function_final_oid := NULL;
        append_only_function_final_source := NULL;
        append_only_function_final_shape := false;
        append_only_function_final_source_matches := false;
        append_only_function_final_trigger_shape := false;
        SELECT pg_catalog.count(*) = 1
           AND NOT EXISTS (
               SELECT 1
               FROM pg_catalog.pg_proc AS procedure_row
               JOIN pg_catalog.pg_namespace AS procedure_schema
                 ON procedure_schema.oid = procedure_row.pronamespace
               JOIN pg_catalog.pg_language AS language_row
                 ON language_row.oid = procedure_row.prolang
               WHERE procedure_schema.nspname = schema_name
                 AND procedure_row.proname = 'prevent_okf_rebuild_failure_audit_mutation'
                 AND (procedure_row.oid IS DISTINCT FROM append_only_function_oid
                      OR procedure_row.prokind IS DISTINCT FROM 'f'
                      OR procedure_row.pronargs IS DISTINCT FROM 0
                      OR procedure_row.proargtypes IS DISTINCT FROM ''::pg_catalog.oidvector
                      OR procedure_row.provariadic IS DISTINCT FROM 0::pg_catalog.oid
                      OR procedure_row.prorettype IS DISTINCT FROM 'trigger'::pg_catalog.regtype
                      OR procedure_row.proretset
                      OR language_row.lanname IS DISTINCT FROM 'plpgsql')
           ) INTO append_only_function_final_shape
        FROM pg_catalog.pg_proc AS procedure_row
        JOIN pg_catalog.pg_namespace AS procedure_schema
          ON procedure_schema.oid = procedure_row.pronamespace
        WHERE procedure_schema.nspname = schema_name
          AND procedure_row.proname = 'prevent_okf_rebuild_failure_audit_mutation';
        SELECT procedure_row.oid, procedure_row.prosrc
          INTO append_only_function_final_oid, append_only_function_final_source
        FROM pg_catalog.pg_proc AS procedure_row
        JOIN pg_catalog.pg_namespace AS procedure_schema
          ON procedure_schema.oid = procedure_row.pronamespace
        WHERE procedure_schema.nspname = schema_name
          AND procedure_row.proname = 'prevent_okf_rebuild_failure_audit_mutation'
        ORDER BY procedure_row.oid
        LIMIT 1;
        IF NOT append_only_function_final_shape
           OR append_only_function_final_oid IS DISTINCT FROM append_only_function_oid
           OR append_only_function_final_source IS NULL THEN
            RAISE EXCEPTION 'e2a_preflight_audit_check_drift';
        END IF;
        e2a_normalize_expression_input := append_only_function_final_source;
            e2a_normalize_expression_output := '';
            e2a_normalize_expression_index := 1;
            e2a_normalize_expression_depth := 0;
            e2a_normalize_expression_pending_space := false;
            WHILE e2a_normalize_expression_index <= pg_catalog.length(e2a_normalize_expression_input) LOOP
                e2a_normalize_expression_character := pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index, 1);
                IF e2a_normalize_expression_character IN (' ', E'\t', E'\n', E'\r', E'\f') THEN
                    e2a_normalize_expression_pending_space := e2a_normalize_expression_output <> '';
                    e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                ELSIF pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index, 2) = '--' THEN
                    e2a_normalize_expression_index := e2a_normalize_expression_index + 2;
                    WHILE e2a_normalize_expression_index <= pg_catalog.length(e2a_normalize_expression_input)
                          AND pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index, 1) NOT IN (E'\n', E'\r') LOOP
                        e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                    END LOOP;
                    e2a_normalize_expression_pending_space := e2a_normalize_expression_output <> '';
                ELSIF pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index, 2) = '/*' THEN
                    e2a_normalize_expression_comment_depth := 1;
                    e2a_normalize_expression_index := e2a_normalize_expression_index + 2;
                    WHILE e2a_normalize_expression_index <= pg_catalog.length(e2a_normalize_expression_input)
                          AND e2a_normalize_expression_comment_depth > 0 LOOP
                        IF pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index, 2) = '/*' THEN
                            e2a_normalize_expression_comment_depth := e2a_normalize_expression_comment_depth + 1;
                            e2a_normalize_expression_index := e2a_normalize_expression_index + 2;
                        ELSIF pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index, 2) = '*/' THEN
                            e2a_normalize_expression_comment_depth := e2a_normalize_expression_comment_depth - 1;
                            e2a_normalize_expression_index := e2a_normalize_expression_index + 2;
                        ELSE
                            e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                        END IF;
                    END LOOP;
                    IF e2a_normalize_expression_comment_depth <> 0 THEN
                        RAISE EXCEPTION 'e2a_preflight_audit_check_drift';
                    END IF;
                    e2a_normalize_expression_pending_space := e2a_normalize_expression_output <> '';
                ELSIF pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index, 2) = '*/' THEN
                    RAISE EXCEPTION 'e2a_preflight_audit_check_drift';
                ELSIF e2a_normalize_expression_character = '$'
                        AND (e2a_normalize_expression_index = 1
                            OR pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index - 1, 1) ~ '^[[:ascii:]]$'
                            AND pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index - 1, 1) !~ '^[A-Za-z0-9_$]$') THEN
                    e2a_normalize_expression_tag := substring(
                        pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index)
                        FROM '^\$(?:[A-Za-z_][A-Za-z_0-9]*)?\$'
                    );
                    IF e2a_normalize_expression_tag IS NULL THEN
                        IF substring(
                            pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index)
                            FROM '^\$[0-9][A-Za-z_0-9]*\$'
                        ) IS NOT NULL
                        OR substring(
                            pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index)
                            FROM '^\$[A-Za-z_0-9]'
                        ) IS NOT NULL
                        OR substring(
                            pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index)
                            FROM '^\$[^[:ascii:]]'
                        ) IS NOT NULL
                        OR substring(
                            pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index)
                            FROM '^\$[A-Za-z_][A-Za-z_0-9]*[^[:ascii:]]'
                        ) IS NOT NULL THEN
                            RAISE EXCEPTION 'e2a_preflight_audit_check_drift';
                        END IF;
                        e2a_normalize_expression_output := e2a_normalize_expression_output || '$';
                        e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                    ELSE
                        e2a_normalize_expression_next := position(
                            e2a_normalize_expression_tag IN pg_catalog.substr(
                                e2a_normalize_expression_input,
                                e2a_normalize_expression_index + pg_catalog.length(e2a_normalize_expression_tag)
                            )
                        );
                        IF e2a_normalize_expression_next = 0 THEN
                            RAISE EXCEPTION 'e2a_preflight_audit_check_drift';
                        END IF;
                        e2a_normalize_expression_output := e2a_normalize_expression_output
                            || pg_catalog.substr(
                                e2a_normalize_expression_input,
                                e2a_normalize_expression_index,
                                (2 * pg_catalog.length(e2a_normalize_expression_tag))
                                + e2a_normalize_expression_next - 1
                            );
                        e2a_normalize_expression_index := e2a_normalize_expression_index
                            + (2 * pg_catalog.length(e2a_normalize_expression_tag))
                            + e2a_normalize_expression_next - 1;
                    END IF;
                ELSIF e2a_normalize_expression_character IN ('''', '"') THEN
                    e2a_normalize_expression_quote := e2a_normalize_expression_character;
                    e2a_normalize_expression_escape := e2a_normalize_expression_quote = ''''
                        AND e2a_normalize_expression_index > 1
                        AND pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index - 1, 1) IN ('E', 'e')
                        AND (e2a_normalize_expression_index = 2
                            OR pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index - 2, 1) ~ '^[[:ascii:]]$'
                            AND pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index - 2, 1) !~ '^[A-Za-z0-9_$]$');
                    e2a_normalize_expression_output := e2a_normalize_expression_output || e2a_normalize_expression_character;
                    e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                    LOOP
                        IF e2a_normalize_expression_index > pg_catalog.length(e2a_normalize_expression_input) THEN
                            RAISE EXCEPTION 'e2a_preflight_audit_check_drift';
                        END IF;
                        e2a_normalize_expression_character := pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index, 1);
                        e2a_normalize_expression_output := e2a_normalize_expression_output || e2a_normalize_expression_character;
                        IF e2a_normalize_expression_escape AND e2a_normalize_expression_character = E'\\' THEN
                            IF e2a_normalize_expression_index = pg_catalog.length(e2a_normalize_expression_input) THEN
                                RAISE EXCEPTION 'e2a_preflight_audit_check_drift';
                            END IF;
                            e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                            e2a_normalize_expression_output := e2a_normalize_expression_output || pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index, 1);
                        ELSIF e2a_normalize_expression_character = e2a_normalize_expression_quote THEN
                            IF pg_catalog.substr(e2a_normalize_expression_input, e2a_normalize_expression_index + 1, 1) = e2a_normalize_expression_quote THEN
                                e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                                e2a_normalize_expression_output := e2a_normalize_expression_output || e2a_normalize_expression_quote;
                            ELSE
                                e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                                EXIT;
                            END IF;
                        END IF;
                        e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                    END LOOP;
                ELSE
                    IF e2a_normalize_expression_character = '(' THEN
                        e2a_normalize_expression_depth := e2a_normalize_expression_depth + 1;
                    ELSIF e2a_normalize_expression_character = ')' THEN
                        e2a_normalize_expression_depth := e2a_normalize_expression_depth - 1;
                        IF e2a_normalize_expression_depth < 0 THEN
                            RAISE EXCEPTION 'e2a_preflight_audit_check_drift';
                        END IF;
                    END IF;
                    IF e2a_normalize_expression_pending_space
                       AND (e2a_normalize_expression_output ~ '[A-Za-z0-9_$]$'
                            OR e2a_normalize_expression_output ~ '[^[:ascii:]]$')
                       AND (e2a_normalize_expression_character ~ '^[A-Za-z0-9_$]$'
                            OR e2a_normalize_expression_character ~ '^[^[:ascii:]]$') THEN
                        e2a_normalize_expression_output := e2a_normalize_expression_output || ' ';
                    END IF;
                    e2a_normalize_expression_pending_space := false;
                    e2a_normalize_expression_output := e2a_normalize_expression_output || e2a_normalize_expression_character;
                    e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                END IF;
            END LOOP;
            IF e2a_normalize_expression_depth <> 0 THEN
                RAISE EXCEPTION 'e2a_preflight_audit_check_drift';
            END IF;
            -- Re-lex the normalized bytes before each strip: literal, quoted,
            -- dollar, and comment parentheses cannot close an outer wrapper.
            WHILE pg_catalog.left(e2a_normalize_expression_output, 1) = '('
              AND pg_catalog.right(e2a_normalize_expression_output, 1) = ')'
              AND pg_catalog.length(e2a_normalize_expression_output) > 2 LOOP
                e2a_normalize_expression_outer := true;
                e2a_normalize_expression_depth := 0;
                e2a_normalize_expression_index := 1;
                WHILE e2a_normalize_expression_index
                      <= pg_catalog.length(e2a_normalize_expression_output) LOOP
                    e2a_normalize_expression_character := pg_catalog.substr(
                        e2a_normalize_expression_output,
                        e2a_normalize_expression_index,
                        1
                    );
                    IF pg_catalog.substr(
                        e2a_normalize_expression_output,
                        e2a_normalize_expression_index,
                        2
                    ) = '--' THEN
                        e2a_normalize_expression_index := e2a_normalize_expression_index + 2;
                        WHILE e2a_normalize_expression_index
                              <= pg_catalog.length(e2a_normalize_expression_output)
                          AND pg_catalog.substr(
                              e2a_normalize_expression_output,
                              e2a_normalize_expression_index,
                              1
                          ) NOT IN (E'\n', E'\r') LOOP
                            e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                        END LOOP;
                    ELSIF pg_catalog.substr(
                        e2a_normalize_expression_output,
                        e2a_normalize_expression_index,
                        2
                    ) = '/*' THEN
                        e2a_normalize_expression_comment_depth := 1;
                        e2a_normalize_expression_index := e2a_normalize_expression_index + 2;
                        WHILE e2a_normalize_expression_index
                              <= pg_catalog.length(e2a_normalize_expression_output)
                          AND e2a_normalize_expression_comment_depth > 0 LOOP
                            IF pg_catalog.substr(
                                e2a_normalize_expression_output,
                                e2a_normalize_expression_index,
                                2
                            ) = '/*' THEN
                                e2a_normalize_expression_comment_depth := e2a_normalize_expression_comment_depth + 1;
                                e2a_normalize_expression_index := e2a_normalize_expression_index + 2;
                            ELSIF pg_catalog.substr(
                                e2a_normalize_expression_output,
                                e2a_normalize_expression_index,
                                2
                            ) = '*/' THEN
                                e2a_normalize_expression_comment_depth := e2a_normalize_expression_comment_depth - 1;
                                e2a_normalize_expression_index := e2a_normalize_expression_index + 2;
                            ELSE
                                e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                            END IF;
                        END LOOP;
                        IF e2a_normalize_expression_comment_depth <> 0 THEN
                            RAISE EXCEPTION 'e2a_preflight_audit_check_drift';
                        END IF;
                    ELSIF pg_catalog.substr(
                        e2a_normalize_expression_output,
                        e2a_normalize_expression_index,
                        2
                    ) = '*/' THEN
                        RAISE EXCEPTION 'e2a_preflight_audit_check_drift';
                    ELSIF e2a_normalize_expression_character = '$'
                      AND (e2a_normalize_expression_index = 1
                        OR pg_catalog.substr(
                            e2a_normalize_expression_output,
                            e2a_normalize_expression_index - 1,
                            1
                        ) ~ '^[[:ascii:]]$'
                        AND pg_catalog.substr(
                            e2a_normalize_expression_output,
                            e2a_normalize_expression_index - 1,
                            1
                        ) !~ '^[A-Za-z0-9_$]$') THEN
                        e2a_normalize_expression_tag := substring(
                            pg_catalog.substr(
                                e2a_normalize_expression_output,
                                e2a_normalize_expression_index
                            ) FROM '^\$(?:[A-Za-z_][A-Za-z_0-9]*)?\$'
                        );
                        IF e2a_normalize_expression_tag IS NULL THEN
                            IF substring(
                                pg_catalog.substr(
                                    e2a_normalize_expression_output,
                                    e2a_normalize_expression_index
                                ) FROM '^\$[A-Za-z_0-9]'
                            ) IS NOT NULL
                            OR substring(
                                pg_catalog.substr(
                                    e2a_normalize_expression_output,
                                    e2a_normalize_expression_index
                                ) FROM '^\$[^[:ascii:]]'
                            ) IS NOT NULL
                            OR substring(
                                pg_catalog.substr(
                                    e2a_normalize_expression_output,
                                    e2a_normalize_expression_index
                                ) FROM '^\$[A-Za-z_][A-Za-z_0-9]*[^[:ascii:]]'
                            ) IS NOT NULL THEN
                                RAISE EXCEPTION 'e2a_preflight_audit_check_drift';
                            END IF;
                            e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                        ELSE
                            e2a_normalize_expression_next := position(
                                e2a_normalize_expression_tag IN pg_catalog.substr(
                                    e2a_normalize_expression_output,
                                    e2a_normalize_expression_index
                                    + pg_catalog.length(e2a_normalize_expression_tag)
                                )
                            );
                            IF e2a_normalize_expression_next = 0 THEN
                                RAISE EXCEPTION 'e2a_preflight_audit_check_drift';
                            END IF;
                            e2a_normalize_expression_index := e2a_normalize_expression_index
                                + (2 * pg_catalog.length(e2a_normalize_expression_tag))
                                + e2a_normalize_expression_next - 1;
                        END IF;
                    ELSIF e2a_normalize_expression_character IN ('''', '"') THEN
                        e2a_normalize_expression_quote := e2a_normalize_expression_character;
                        e2a_normalize_expression_escape := e2a_normalize_expression_quote = ''''
                            AND e2a_normalize_expression_index > 1
                            AND pg_catalog.substr(
                                e2a_normalize_expression_output,
                                e2a_normalize_expression_index - 1,
                                1
                            ) IN ('E', 'e')
                            AND (e2a_normalize_expression_index = 2
                                OR pg_catalog.substr(
                                    e2a_normalize_expression_output,
                                    e2a_normalize_expression_index - 2,
                                    1
                                ) ~ '^[[:ascii:]]$'
                                AND pg_catalog.substr(
                                    e2a_normalize_expression_output,
                                    e2a_normalize_expression_index - 2,
                                    1
                                ) !~ '^[A-Za-z0-9_$]$');
                        e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                        LOOP
                            IF e2a_normalize_expression_index
                               > pg_catalog.length(e2a_normalize_expression_output) THEN
                                RAISE EXCEPTION 'e2a_preflight_audit_check_drift';
                            END IF;
                            e2a_normalize_expression_character := pg_catalog.substr(
                                e2a_normalize_expression_output,
                                e2a_normalize_expression_index,
                                1
                            );
                            IF e2a_normalize_expression_escape
                               AND e2a_normalize_expression_character = E'\\' THEN
                                IF e2a_normalize_expression_index
                                   = pg_catalog.length(e2a_normalize_expression_output) THEN
                                    RAISE EXCEPTION 'e2a_preflight_audit_check_drift';
                                END IF;
                                e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                            ELSIF e2a_normalize_expression_character
                                  = e2a_normalize_expression_quote THEN
                                IF pg_catalog.substr(
                                    e2a_normalize_expression_output,
                                    e2a_normalize_expression_index + 1,
                                    1
                                ) = e2a_normalize_expression_quote THEN
                                    e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                                ELSE
                                    e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                                    EXIT;
                                END IF;
                            END IF;
                            e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                        END LOOP;
                    ELSE
                        IF e2a_normalize_expression_character = '(' THEN
                            e2a_normalize_expression_depth := e2a_normalize_expression_depth + 1;
                        ELSIF e2a_normalize_expression_character = ')' THEN
                            e2a_normalize_expression_depth := e2a_normalize_expression_depth - 1;
                            IF e2a_normalize_expression_depth < 0 THEN
                                RAISE EXCEPTION 'e2a_preflight_audit_check_drift';
                            ELSIF e2a_normalize_expression_depth = 0
                              AND e2a_normalize_expression_index
                                  < pg_catalog.length(e2a_normalize_expression_output) THEN
                                e2a_normalize_expression_outer := false;
                                EXIT;
                            END IF;
                        END IF;
                        e2a_normalize_expression_index := e2a_normalize_expression_index + 1;
                    END IF;
                END LOOP;
                IF e2a_normalize_expression_depth <> 0 THEN
                    RAISE EXCEPTION 'e2a_preflight_audit_check_drift';
                END IF;
                EXIT WHEN NOT e2a_normalize_expression_outer;
                e2a_normalize_expression_output := pg_catalog.substr(
                    e2a_normalize_expression_output,
                    2,
                    pg_catalog.length(e2a_normalize_expression_output) - 2
                );
            END LOOP;
        append_only_function_final_source_matches :=
            e2a_normalize_expression_output
                IS NOT DISTINCT FROM append_only_function_source_expected;
        IF NOT append_only_function_final_source_matches THEN
            RAISE EXCEPTION 'e2a_preflight_audit_check_drift';
        END IF;
        SELECT NOT EXISTS (
            WITH expected(trigger_name, expected_type) AS (
                VALUES
                    ('trg_okf_rebuild_failure_audit_append_only', 27::smallint),
                    ('trg_okf_rebuild_failure_audit_no_truncate', 34::smallint)
            )
            SELECT 1
            FROM expected
            LEFT JOIN pg_catalog.pg_trigger AS trigger_row
              ON trigger_row.tgrelid = audit_oid
             AND trigger_row.tgname = expected.trigger_name
            LEFT JOIN pg_catalog.pg_proc AS procedure_row
              ON procedure_row.oid = trigger_row.tgfoid
            LEFT JOIN pg_catalog.pg_namespace AS procedure_schema
              ON procedure_schema.oid = procedure_row.pronamespace
            WHERE trigger_row.oid IS NULL
               OR procedure_schema.nspname IS DISTINCT FROM schema_name
               OR procedure_row.proname IS DISTINCT FROM 'prevent_okf_rebuild_failure_audit_mutation'
               OR trigger_row.tgfoid IS DISTINCT FROM append_only_function_final_oid
               OR trigger_row.tgtype IS DISTINCT FROM expected.expected_type
               OR trigger_row.tgenabled IS DISTINCT FROM 'O'
               OR trigger_row.tgisinternal
               OR trigger_row.tgargs IS DISTINCT FROM ''::bytea
               OR trigger_row.tgqual IS NOT NULL
               OR trigger_row.tgattr IS DISTINCT FROM ''::int2vector
               OR trigger_row.tgconstraint <> 0
               OR (
                   SELECT pg_catalog.count(*)
                   FROM pg_catalog.pg_trigger AS observed_trigger
                   WHERE observed_trigger.tgrelid = audit_oid
               ) <> (
                   SELECT pg_catalog.count(*)
                   FROM expected
               )
        ) INTO append_only_function_final_trigger_shape;
        IF NOT append_only_function_final_trigger_shape THEN
            RAISE EXCEPTION 'e2a_preflight_audit_check_drift';
        END IF;
END
$e2a019$;
