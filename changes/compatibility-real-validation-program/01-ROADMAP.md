# Compatibility Real-Validation Program — Roadmap Snapshot

## Mainline Route

### Line A — Credential gate and input freeze
- confirm whether `OPENAI_API_KEY` is present in the current session without printing it
- fix one real validation document path and one real query

### Line B — Real donor execution
- run the donor-integrated path on the chosen real document
- confirm whether the execution is truly credentialed and not stub/fallback

### Line C — Artifact capture and classification
- capture a fresh validation artifact
- classify the outcome clearly instead of hand-waving around failure causes

### Line D — Independent review
- after the first real run, ask for an independent second-person review before changing any strategic conclusion

## Phase Sequence

### Phase 1 — Validation input freeze
- lock the credential-status check
- lock the document path, query text, and output artifact path

### Phase 2 — Credentialed donor execution
- run the real donor validation pass
- distinguish credential block from runtime/parsing/provider failure

### Phase 3 — Minimal bug-fix loop if needed
- only if validation reveals a real code defect
- use GitNexus + TDD for the smallest repair and then rerun the same validation

### Phase 4 — Review and recommendation
- summarize whether the parent package should keep `DEFER`
- require an independent second-person review before claiming promotion readiness

## Current Program Sequence

1. inherit frozen constraints from the parent package
2. freeze the real validation inputs before running
3. prefer evidence capture over interpretation
4. treat this package as validation-first, not feature-development-first
