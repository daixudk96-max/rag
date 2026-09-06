# ADR — Phase 15 Migration 019 Atomic File-Size Exception

**Date:** 2026-07-19  
**Status:** Accepted for Phase 15 planning; execution remains unstarted

## Decision

The universal guideline that source files remain under 800 physical lines continues to apply. The only exception is `llamaindex_runtime/registry/migrations/019_e2a_materialization_contract.sql`, which exceeds 800 physical lines.

Migration 019 must remain one atomic, fail-closed dynamic `DO` state machine. It has one root migration-catalog entry, applied exactly once in the established catalog order. The migration runner executes the file with one `cursor.execute` and performs one post-file commit.

## Rationale

The state machine classifies the schema as fresh, final, or partial before it can issue DDL. Splitting its catalog migration would permit a committed partial schema between fragments and would violate that fresh/final/partial classifier. Runtime fragment composition and helper database objects are not authorized alternatives.

## Compensating controls

- One dynamic `DO` block owns the entire migration state machine.
- No DDL may run before classification.
- The root catalog preserves exact order and includes 019 once only.
- Fresh, final, and rerun classifier checks remain required.
- A future live disposable proof must validate the catalog/runner behavior, but requires separate current authorization.

## Control-plane trust boundary

An append-only function attestation validates the observed catalog state during the migration transaction, with no `pg_proc` exclusion. An authorized function owner or superuser can replace an attested function or trigger concurrently with that transaction or after commit. Accordingly, the attestation makes no hostile-superuser, tamper-evidence, or postcommit guarantee.

A final in-transaction re-attestation is detection only: it neither locks the control plane nor prevents a race. Production ownership, least privilege, a cooperative migration lease, controlled DDL, and postdeployment attestation are separately authorized operational work.

## Scope and future change

This exception is narrow: it does not relax the universal file-size guideline for other files or migrations. It does not authorize live database activity, production activity, D4, Phase 16, or Phase 15 execution completion.

Any future split requires superseding architecture and explicit user authority; it may not be introduced through runtime composition or helper database objects.
