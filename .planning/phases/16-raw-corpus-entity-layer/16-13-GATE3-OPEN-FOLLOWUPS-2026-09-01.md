# Gate 3 Open Follow-ups — recorded 2026-09-01 (user-directed)

## Purpose

User instruction (verbatim intent): '你先把剩下的问题先记录一下。然后你就去调用 sag 去跑一下，最后给你返回结果就行了。' — record the remaining unresolved problems BEFORE dispatching the multi-sentence diagnostic evaluation. This file is the durable record; the R2 root-cause doc §8 lists the same residuals.

## (a) modelscope preprocessor Chinese bug — load_model invocation-layer fix

- Symptom: official pipeline path returns empty output for unspaced Chinese; label_mask.sum==1 (expected 7) on the reference sentence 李雷在北京使用华为Mate60.
- Root cause: modelscope 1.39.1 get_label_mask_and_offset_mapping_XLMRobertaTokenizer (venv token_classification_preprocessor.py L438-462) assumes space-separated words; fast-tokenizer path has the same defect (HF word_ids treats the whole unspaced Chinese sentence as 1 word).
- Proven bypass (diagnostic probes): XLMRobertaTokenizerFast + add_special_tokens=True + char-level label_mask (mask <s>/</s> positions via offsets (0,0)) + model.head.decode(logits, label_mask) CRF Viterbi.
- Status: NOT authorized to implement; frozen files untouched. Any fix goes through owner+TDD+review chain.

## (b) _FIXTURE_SIGNATURES re-baseline needs explicit contract amendment

- run_raner_smoke_live.py (Task #218, frozen) hardcodes ("PER",0,2),("LOC",3,5),("CORP",7,9),("PROD",9,15) — authored without real-model validation (16-11: 'no real RaNER model wired').
- Real model on the reference sentence: 李雷 PER(0,2) matches; 北京 → O; 华为 → B-PROD; 华为Mate → PROD ending char 13, 60 → O. 3/4 fixture expectations disagree with the real model.
- Status: NOT authorized; fixture is frozen. Re-baselining = explicit contract amendment per the per-attempt authorization model.

## (c) test_worker_entry.py hermetic registry seams

- test_worker_entry.py:208/324 (pre-freeze 2026-08-12) assert 'not REGISTRY_PATH.exists()' — fails now because the append-only attempt registry is a legitimate phase deliverable (3 honest attempts). Non-hermetic test-vs-deliverable coupling, NOT a regression. Independent verifier C7 MEDIUM.
- Status: NOT authorized; exemption recorded in R2 doc §7. Fix = hermetic temp-registry injection via owner+TDD+review; never a test weakening.

## (d) Multi-sentence diagnostic evaluation — AUTHORIZED 2026-09-01

- Authorization: user verbatim intent (see Purpose). Scope: subagent (sag) runs the frozen local model on several different sentences and returns results; read-only toward all repo artifacts; scripts+outputs under .tmp only.
- This is DIAGNOSTIC measurement of model quality, NOT a formal Gate 3 attempt: no run_raner_smoke_launch.py, no registry writes, no output_root artifacts, no evidence records.
- Still forbidden: network/model downloads, pip installs, Docker, DB, RaNER production inference beyond these diagnostic sentences, C2, commit/push.

## Related records

- R1 completion: 16-13-GATE3-PREP-R1-COMPLETION-2026-08-29.md
- R2 root cause + verification + §8 user decision: 16-13-GATE3-LIVE-ATTEMPT-R2-ROOT-CAUSE-2026-09-01.md
- WSL measurement: 16-13-GATE3-WSL-GAP-DOWNSTREAM-2026-08-29.md (SKIPPED BY USER DECISION)

## (d) outcome — evaluation executed and verified (2026-09-01)

- Round 1 discarded: evaluator shift-by-one bug (CRF decode returns full-length path incl. specials; round-1 zipped 7 masked positions against 9 decoded entries). Preserved at .tmp/raner_eval_round1_bad.json (sha 25239fcb...86d4e).
- Fixed evaluator reproduces the independently-verified archived S1 9 token/label/offset pairs EXACTLY (coordinator re-checked S1_exact_match_vs_archived=True). New .tmp/raner_eval.json sha256 079e28c06e5a2dd3a3bc0dea6d190f6b3858608ee0df56cf42badb378a0a9f50.
- Corrected per-sentence entities: S1 [李雷 PER, 华为Mate PROD]; S2 [韩梅梅 PER, 上海 LOC]; S3 [腾讯 CORP]; S4 [华为 CORP]; S5 [] (orphan E-LOC anomaly — model tagged B-LOC on <s>); S6 [阿里巴巴 CORP]; S7 [小米 CORP, 王小明 PER]; S8 [比亚迪 CORP]. Load 16.9s, per-sentence 0.13-0.25s CPU.
- Informal quality read (8-sentence diagnostic sample, NOT a benchmark): CORP 5/5 strong; PER partial (3/6 occurrences); LOC weak (1/5); PROD boundaries blurred (华为Mate merged, 60 dropped; 华为 type flips CORP/PROD across sentences); S5 junk raw path. Multiple entities per sentence confirmed working (S1/S2/S7 give 2).
- Status: follow-up (d) CLOSED as diagnostic outcome recorded here. (a)/(b)/(c) remain NOT authorized.

## (e) PP-UIE deployment evaluation — AUTHORIZED 2026-09-01

- Authorization: user pasted the PP-UIE deployment doc and asked verbatim intent: '这个是部署教程，你这边能帮着部署吗？在这个百度UIE这个模型' (deploy Baidu/UIE).
- Scope: NEW separate venv at .cache/uie-venv (never global C:\Python311, never the frozen raner venv); weights under .cache/uie-models; scripts+outputs under .tmp/uie/; user chose PP-UIE-0.5B for CPU feasibility (float32; float16 requires CUDA>=7.0 GPU which this host lacks).
- Evaluation: same 8 diagnostic sentences used for RaNER (comparable entity schema ['人名','地名','公司名','产品名']) + 1 relation-extraction demo to verify entity+relation joint output.
- Boundaries: no changes to repo source/tests/planning beyond this record; no touching gate3/raner artifacts; network use = pip index + model weights download for THIS deployment only; user also indicated online APIs acceptable for relation extraction later (price-sensitive; not wired into the project).

### (e) outcome — PP-UIE-0.5B deployed and evaluated (2026-09-01, agent 196763de)

- Deployment: independent venv .cache/uie2-venv (paddlepaddle 3.0.0 + paddlenlp 3.0.0b4 + aistudio-sdk pinned 0.2.6 - the 3.0.0b4 import crashes against aistudio-sdk >= 0.3.9: 'cannot import name download from aistudio_sdk.hub'). Weights from the user-provided git source git.aistudio.baidu.com/PaddleNLP/PP-UIE-0.5B.git (safetensors 942 MB, real weights not lfs pointers).
- Load path: Taskflow local-dir is NOT supported (AssertionError: model name not in task) -> used the documented AutoModelForCausalLM(local, float32) + LLM_IE_PROMPT template path, CPU. lm_head tied-weights warning non-fatal (tie_word_embeddings=true).
- Entity eval (same 8 sentences): S1 [李雷,北京,华为,Mate60]; S2 [韩梅梅,上海]; S3 [张三,腾讯公司] (深圳 missing in entity schema, recovered in relation demo); S4 [华为,手机]; S5 [中国,北京]; S6 [阿里巴巴,杭州]; S7 [李雷,小米,王小明]; S8 [王小明,比亚迪]. Score vs coordinator expectation sheet: 18/19 (~95%) vs RaNER 9/19 (~47%).
- Relation extraction: WORKS (RaNER has none): S3 张三->所属公司[腾讯公司];张三->所在地[深圳]; S7 李雷->所属公司[小米]. Some subject noise (company as subject) - acceptable.
- Speed: CPU 6.9 s/sentence (RaNER 0.13-0.25 s) - 40x slower on CPU; RTX 4090 fp16 re-run is the obvious next step if needed, NOT executed (user wanted CPU-only quick test first).
- Artifacts: .tmp/uie2/{uie_eval.json sha 02090D11..., uie_relation.json sha CE291E07..., eval8.py, relation_demo.py, versions.py, smoke_taskflow.py}; weights .cache/uie2-models/aistudio/PP-UIE-0.5B (942MB safetensors). Repo untouched.
- Follow-up (f) implicitly opened, NOT authorized: switch the project model from RaNER to PP-UIE (Phase 17+ scope; requires contract amendment, new mirror, wheelhouse, fixture rewrite) and/or GPU re-eval incl. 1.5B/7B.

## (g) UIE -> coref rules wiring diagnostic — AUTHORIZED 2026-09-01

- User authorization (verbatim intent): '现在已经有数据了，那你让subagent给他接线试一下呗' — wire PP-UIE-0.5B extraction output into the existing 16-16 coref rules engine (llamaindex_runtime/entity/coref_rules.py) and run a diagnostic.
- Read-only toward repo: NO source/test/planning writes; scripts+outputs under .tmp/wire/ only; reuse existing UIE venv (.cache/uie2-venv) and model (.cache/uie2-models/aistudio/PP-UIE-0.5B) read-only; pure-function coref call only, NO PostgreSQL, NO live gate.
- Success criterion: demonstrate whether same-name mentions across different sentences (e.g., 华为 in S1/S3, 李雷 in S1/S4) merge into one coref cluster via the existing engine, and honestly report the engine's actual grouping semantics.
- Outcome (2026-09-01, subagent 2ab93586 + coordinator hash re-verification): WIRED SUCCESSFULLY. UIE (15 entities / 6 sentences, text-only) -> resolve_candidates (D1 attach 15/15) -> build_coref_clusters resolver_mode=rules -> 3 cross-sentence clusters: 华为@T1+T3+T6, 李雷@T1+T4, 王小明@T4+T5. Negative controls (per-sentence docs / empty authority / wrong mode) all 0 clusters. Key findings: (1) engine groups by (document_id, version_id, mention_text, entity_type) at coref_rules.py:19-20,176-179 - cross-DOCUMENT merging out of scope by design (Phase 17/18 alias-layer gap, now empirically confirmed); (2) UIE LLM path emits text only, no offsets/types - production needs a real UIE->mention adapter; (3) input_id/span_id must be per-mention UUIDs (input_id==span_id for corpus_span), per-sentence sharing raises ValueError coref_rules.py:171-174. Artifacts+sha256 (uie_mentions 1cb3ebec..., coref_clusters 6defbee5...) in .tmp/wire/; repo untouched (coref_rules.py mtime 2026-08-31 unchanged). No further action authorized.

## (h) User architectural direction (2026-09-01) - UIE wiring + normalization = ONE program

- User decision (verbatim intent): '接线和归一应该是一个项目，不应该分成两块…应该是灌库的时候就有归一程序' - the UIE wiring and the normalization layer (incl. cross-document alias resolution) must be ONE authorized program with ONE acceptance criterion, NOT two sequential efforts; normalization must be part of the ingestion pipeline at population time (no populate-first-normalize-later).
- Coordinator assessment: direction is architecturally correct - resolution (D1 authority) and materialization are already the same pipeline (Phase 16); populating production before alias normalization would create fragmented identities requiring costly retro-merges.
- Consequence for planning: when Phase 17 planning starts, scope the adapter (UIE->MentionCandidate), the alias-normalization layer attached to resolution, and end-to-end sample-corpus acceptance as ONE integrated package; extractor swap (raner->uie) contract decision (ROADMAP L672 RAG_ENTITY_EXTRACTOR) to be settled in that planning; production population itself remains Phase 18 (human-review) scope. NOT started - requires explicit user go.
- Deep research report 1 (entity normalization) received from user 2026-09-01 and archived: `.planning/RESEARCH-ENTITY-NORMALIZATION-DEEP-2026-09-01.md`. Core: three-outcome open-world resolver (AUTO/REVIEW/NEW), precision-first with type-specific hard vetoes, provenance-carrying alias table, immutable IDs + event-sourced logical merges, affected-set-only backfill, LLM as gray-zone judge/teacher only, BGE candidates + Splink-style calibrated scorer, PG-only stack. Report 2 (SQL multi-hop projects, prompt `.tmp/deep_research_prompt_sql_multihop_projects.md`) received 2026-09-01 and archived: `.planning/RESEARCH-SQL-GRAPH-MULTIHOP-DEEP-2026-09-01.md`. Core: PG-only graph VALIDATED (LightRAG PGTableGraphStorage 39ms p50 vs AGE 1099ms at 8k/40k; OpenFGA 12M-tuple index fix 65s->0.2s); recommended ONLINE main path = batched frontier BFS (one SQL per hop, NOT recursive CTE as default - refines 17-BOUNDARY L33 which allowed either and defaulted to RCTE; Phase 17 PLAN should adopt batched app-layer for the fixed 2-hop, keep RCTE as experimental path); five independent budgets (depth/fanout/nodes/edges/timeout, init: seeds<=5, hop1=24, hop2=12, nodes=1000, edges<=2000, timeout 180ms); directed edges (do NOT copy LightRAG undirected canonicalization); always $1::bigint[] casts; statement_timeout as DB fuse; evidence lands on provenance chunks; NO closure table for general KG (ltree/traversal_ids only for true hierarchies); do NOT add Apache AGE. Both research reports now complete - integrated program planning can be drafted on user go.

---

## Update 2026-09-01: FORMAL DECISION - LightRAG backend adopted (supersedes part of (h))
User decision: fully adopt LightRAG as RAG backend; graph+vector merged into ONE channel (LightRAG), our BM25+rerank channel retained and fused; normalization/alias layer stays ours (Phase 16 deterministic pipeline feeds LightRAG). Formal record: .planning/phases/17-graph-recall-multiroute-fusion/17-DECISION-LIGHTRAG-BACKEND-2026-09-01.md . Key open item: feeding mode (custom pre-built KG vs LightRAG LLM extraction) + query-time LLM vs zero-generative-LLM contract -> deep research v3 prompt issued (.tmp/deep_research_prompt_lightrag_integration_v3.md). Phase 17 planning will consume this decision.

- [2026-09-01] (h) 架构定稿并落盘主规划: .planning/phases/17-graph-recall-multiroute-fusion/17-PLAN-MASTER-2026-09-01.md (试抽分流制: 相似批 LLM定单→UIE / 大杂烩纯LLM; 单子生命周期; 篮子核对制; Wave W0-W7; 开放决策=生产 LLM 引擎 R3)。
