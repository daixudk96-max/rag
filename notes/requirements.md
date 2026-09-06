# Requirements - 16-16 local coref rules (single wave)

repoRoot: E:/github/rag
testsRoot: tests
wave id: coref-rules-16-16
test file (canonical, relative to testsRoot): llamaindex_runtime/entity/test_coref_rules.py

Interface contract (pinned from 16-16-PLAN Task 1/Task 2 + contracts.py):
- build_coref_clusters(resolved: ResolutionResult, *, coref_rules_version: str,
  resolver_mode: str | None = None) -> CorefClusterSet
  (spec decision: the plan Task-2 behavior "requires an explicit resolver mode
  'rules' (default off; otherwise empty set)" is realized as a keyword-only
  resolver_mode=None default; exact-match gate; anything != "rules" -> empty set)
- CorefCluster frozen fields exactly: cluster_id, version_id,
  member_mention_ids (tuple[str,...] sorted), tombstoned: bool, provenance (frozen mapping
  with coref_rules_version + strategy only, never model/confidence values)
- CorefClusterSet frozen; .tombstone(cluster_id) -> NEW set, memberships retained,
  unknown id raises KeyError
- cluster_id = deterministic_id("coref_cluster", canonical_json({"coref_rules_version": v,
  "member_mention_ids": sorted(ids), "version_id": version_id}))
- grouping rule (conservative, lexical/structural only): identical mention_text AND
  identical entity_type AND same (document_id, version_id); groups of size 1 -> no cluster;
  duplicate span_id within one scope -> ValueError; cross-scope never clusters
- purity: stdlib only; no DB/model/network/persistence imports; exported from
  llamaindex_runtime/entity/__init__.py without touching existing exports

Graph wiring: waves=[{id:"coref-rules-16-16", tests:{"<path>": <RED test content>}, spec}]
options: { repoRoot: E:/github/rag, testsRoot: tests, attemptBudget: 2, loopBudget: 2,
allowTestsUpdate: false, maxWaveFiles: 20 }

Handoff: run the compiled GraphDefinitionBody via tdd_graph action:"run" (waitMs 600000),
then resume per WAITING_SIGNAL guidance (mutation-equivalent verdicts only if honest).
