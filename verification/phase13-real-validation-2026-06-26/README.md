# Phase 13 Real Validation — Hotspot Traverse Fix

Purpose: rerun the real-document validation with the Phase 13 hotspot traversal redesign.

Fresh outputs are intentionally written here instead of overwriting `verification/real-document-validation-2026-06-23/`, which is the pre-fix baseline used during Q18 root-cause analysis.

Primary checks:
- Q18 should no longer produce only null/zero chunk evidence.
- Hotspot traversal should emit a waypoint plus one-level child evidence chunks when children exist.
- Evidence-chain zero/placeholder chunk counts should improve versus the 2026-06-23 baseline.
