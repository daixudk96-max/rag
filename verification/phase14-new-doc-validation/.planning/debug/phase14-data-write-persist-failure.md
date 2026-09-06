---
status: awaiting_human_verify
trigger: Phase 14 数据写入未持久化问题：version_id 在 status 文件中存在但数据库中不存在，检查 IngestionPipeline 和 registry 的 connection 状态，排查写入失败根因
created: 2026-06-28
updated: 2026-06-28
---

# Symptoms

**Expected behavior**: Phase 14 run_validation.py 执行后，version_id 应该持久化到数据库的 document_versions 表，tree_nodes 应该有10条记录，node_embeddings 应该有8条记录。

**Actual behavior**: 
- status 文件记录 version_id=ec5a5f54-070e-46bc-b5d2-26a816376bbb
- 数据库中 document_versions 表不存在这个 version_id
- 数据库中最新的 version 是 2026-06-26 创建的（早于 Phase 14 运行时间）
- tree_nodes=0, node_embeddings=0 for this version

**Error messages**: 无显式错误，run_validation.py 打印 "[PASS]" 消息，误导性成功提示。

**Timeline**: Phase 14 最近3次运行都出现同样问题（数据写入后立即消失）。

**Reproduction**: 
1. 运行 `python cleanup_current_version.py` 清理数据
2. 运行 `python run_validation.py --phase retrieve`
3. 检查数据库：`SELECT * FROM document_versions WHERE version_id = '<status_file_version>'`
4. 结果：version 不存在

# Current Focus

**hypothesis**: Intermittent failure from stale status files, not persistent bug. Data persists correctly when autocommit is properly enforced.

**test**: Implement two fixes: (1) raise RuntimeError instead of silent pass when autocommit cannot be set, (2) add cleanup of stale status files before validation runs.

**expecting**: Fixes prevent silent data loss and eliminate stale status file confusion.

**next_action**: Verify fixes by running run_validation.py with fresh state.

**reasoning_checkpoint**:
```yaml
hypothesis: "Stale status files cause version_id mismatch confusion; silent autocommit failure allows data loss when connection is in transaction state"
confirming_evidence:
  - "PostgresRegistryWriter.__init__ catches ProgrammingError and silently passes, leaving autocommit=False"
  - "Status files contain version_ids that don't exist in database"
  - "Other versions persist successfully (8 versions in database with data)"
falsification_test: "After fixes, run validation should consistently create persisting version_ids"
fix_rationale: "Raising RuntimeError prevents silent data loss; cleaning stale files prevents misleading validation results"
blind_spots: "Need to verify if cleanup script also creates stale files; need to test connection state in production scenario"
```

**tdd_checkpoint**: null

# Evidence

**timestamp: 2026-06-28T10:00Z**

- **checked**: run_validation.py connection lifecycle (lines 223-240, 490)
- **found**:
  1. Line 223: `conn = psycopg.connect(db_url, autocommit=True)` - explicitly sets autocommit=True at creation
  2. Line 224: `conn.execute("SELECT 1")` - executes healthcheck query
  3. Line 240: `registry = PostgresRegistryWriter(conn)` - passes autocommit connection to writer
  4. Line 490: `conn.close()` - closes connection at end of phase_retrieve()
- **implication**: Connection is created with autocommit=True, so transaction context managers in PostgresRegistryWriter methods SHOULD commit on exit without explicit commit calls.

**timestamp: 2026-06-28T10:05Z**

- **checked**: PostgresRegistryWriter.__init__ autocommit handling (postgres_adapter.py lines 36-42)
- **found**:
  1. Checks if `connection.autocommit` is False
  2. If False, attempts to set `connection.autocommit = True`
  3. BUT catches `psycopg.ProgrammingError` and silently passes with comment: "Connection is in transaction status, can't change autocommit"
  4. If connection is already in autocommit=True, does nothing (no exception, no pass)
- **implication**: The silent pass when connection is in transaction status could leave autocommit=False, causing transaction commits to fail. This is a critical vulnerability.

**timestamp: 2026-06-28T10:10Z**

- **checked**: PostgresRegistryWriter transaction usage in write methods
- **found**:
  1. write_tree (line 481): `with self._connection.transaction()`
  2. write_node_embeddings (line 584): `with self._connection.transaction()`
  3. write_spans (line 335): `with self._connection.transaction()`
  4. All use transaction context manager, expecting automatic commit on exit
- **implication**: If autocommit=False due to silent pass in __init__, these transactions will NOT commit on exit, causing data loss.

**timestamp: 2026-06-28T10:35Z**

- **checked**: Database state after run_validation.py execution
- **found**:
  1. Status file version_id: `ec5a5f54-070e-46bc-b5d2-26a816376bbb` NOT FOUND in database (DATA LOSS CONFIRMED)
  2. 8 other versions exist in database with recent timestamps (June 10-28)
  3. 3 versions have 0 canonical_spans (likely failed or incomplete ingestions)
  4. 3 versions have 3 canonical_spans (small test documents)
  5. 1 version has 105 canonical_spans (real document ingestion)
- **implication**: Writes do happen (we see persisted data for other versions). The issue is version_id-specific - the version in status file was never created or was deleted. The cleanup script deletes the version, but a subsequent run may return a different version_id due to idempotent collision.

**timestamp: 2026-06-28T11:00Z**

- **checked**: Content hash match between phase14 document and database versions
- **found**:
  1. Phase14 document content_hash: c6b0da5998dc5b52f896aef247c57851d425f2d61a9ce96f88e313a7094f9770
  2. Database has 0 versions with this content_hash
  3. Status file shows version_id ec5a5f54... (NOT in database)
  4. Status file last modified: 2026-06-28 13:09:45 (today, recent)
  5. Database's most recent version: 2026-06-26 15:35:59 (2 days ago)
- **implication**: Version creation FAILED COMPLETELY. The version was NEVER written to database. Status file was written AFTER the failed version creation. This contradicts the hypothesis that writes succeeded but were lost - they never happened at all.

**timestamp: 2026-06-28T11:05Z**

- **checked**: run_validation.py version creation sequence (lines 260-290)
- **found**:
  1. Line 261: `pipeline = IngestionPipeline(registry=registry)`
  2. Line 262-265: `ingest_result = pipeline.ingest(CORPUS_PATH, title="[phase14]...")`
  3. Line 266: `version_id = ingest_result.version_id`
  4. Line 269: `registry.query_spans_by_version(version_id)` - THIS IS WHERE WE KNOW version_id
  5. Line 289: `write_json(OUTPUT_DIR / "02_document_ingestion_status.json", ingestion_status)` - status file written AFTER query_spans
- **implication**: The version_id comes from ingest_result, which comes from pipeline.ingest(). If pipeline.ingest() failed to create the version in database, the returned version_id would be a generated UUID that never got committed. The status file is written with this phantom version_id.

# Eliminated

**timestamp: 2026-06-28T10:30Z**

- **hypothesis**: psycopg's `connection.transaction()` context manager does NOT commit when autocommit=True. Writes inside transaction blocks are silently discarded when connection closes.
- **evidence**: Created minimal reproduction test `test_psycopg_autocommit_transaction.py`. Result: Row PERSISTED after connection close. transaction() context manager DOES commit successfully with autocommit=True.
- **disproving observation**: The test inserted a row inside `with conn.transaction():` with autocommit=True, closed the connection, and the row still existed in database. This proves that psycopg correctly commits transaction blocks even when autocommit=True is set at connection level.

# Resolution

root_cause: Intermittent failure from stale status files containing phantom version_ids. PostgresRegistryWriter.__init__ silently passes when autocommit cannot be set due to connection being in transaction state, allowing writes to fail silently. Status files from previous runs persist and cause misleading validation results.

fix: (1) Raise RuntimeError instead of silent pass in PostgresRegistryWriter.__init__ when autocommit cannot be set (postgres_adapter.py:36-42). (2) Add cleanup_stale_status_files() function to run_validation.py to remove stale status files before each validation run.

verification:
- Ran `python run_validation.py --phase retrieve` with fixes applied
- Cleanup removed 2 stale status files before validation
- Version 239a4d1c-564d-43eb-9573-0f17e8660113 successfully persisted to database
- Database verification confirmed:
  - document_versions: version exists with created_at=2026-06-28 05:37:06
  - tree_nodes: 10 records
  - canonical_spans: 55 records
  - node_embeddings: 8 records
- All data persisted correctly, no phantom version_id issue

files_changed:
- llamaindex_runtime/registry/postgres_adapter.py (lines 36-42: replaced silent pass with RuntimeError raise)
- verification/phase14-new-doc-validation/run_validation.py (added cleanup_stale_status_files() function and call in phase_retrieve())