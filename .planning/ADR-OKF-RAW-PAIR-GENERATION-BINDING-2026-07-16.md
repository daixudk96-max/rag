# ADR: Bind Generated Raw Markdown and Pair Sidecars

- **Status:** Accepted
- **Date:** 2026-07-16
- **Decision scope:** OKF raw-pair generation and production parsing only
- **Owners:** OKF maintainers

## Context

OKF generated raw Markdown and its sidecar must be consumed as one explicitly bound
artifact pair. A parser that merely finds a nearby sidecar can ingest Markdown from
one generation with metadata from another after a partial replacement, accidental
copy, or hostile concurrent write. The binding must be deterministic, auditable, and
strict enough for production use without introducing an unsupported transactional
filesystem claim.

The repository currently has no committed `raw/<slug>.pair.json` artifacts. Tests,
fixtures, and callers that construct raw-pair inputs therefore migrate to this contract
rather than preserving a legacy production fallback.

## Decision

### 1. Required adjacent pair manifest

Every generated raw pair SHALL include an adjacent manifest. The filesystem authority
root is the configured **bundle root**; the logical raw root is
`<bundle-root>/raw/`. A legal pair location is:

```text
<bundle-root>/raw/[<safe-relative-directory>/]<slug>.{md,spans.json,pair.json}
```

For example, the current serializer emits the zero-depth form:

```text
<bundle-root>/raw/<slug>.md
<bundle-root>/raw/<slug>.spans.json
<bundle-root>/raw/<slug>.pair.json
```

The production reader also accepts a safely nested form:

```text
<bundle-root>/raw/reports/2026/<slug>.md
<bundle-root>/raw/reports/2026/<slug>.spans.json
<bundle-root>/raw/reports/2026/<slug>.pair.json
```

`<safe-relative-directory>` is optional and consists of zero or more safe path
components. It MUST NOT be absolute and MUST NOT contain empty, `.` or `..`
components, path traversal, or separators embedded in a component. `<slug>` is the
shared basename of all three members. The Markdown, sidecar, and manifest MUST be in
the same directory (adjacent) and have the same slug. Nested locations are supported
production locations, not a legacy fallback; zero-depth output remains the current
serializer layout.

The manifest is the authoritative binding record and contains exactly these required
logical fields:

| Field | Meaning |
| --- | --- |
| `schema_version` | Pair-manifest schema version. Initial value is `1`. |
| `markdown_file` | Filename, relative to the manifest directory, of the Markdown member. |
| `markdown_sha256` | SHA-256 of the exact Markdown file bytes. |
| `sidecar_file` | Filename, relative to the manifest directory, of the sidecar member. |
| `sidecar_sha256` | SHA-256 of the exact sidecar file bytes. |
| `canonical_hash` | The frozen v1 canonical hash for the validated logical pair. |

The file references MUST be exact plain filenames, not absolute paths or paths
containing path separators, `.` or `..` traversal components. Both members MUST
resolve to the manifest's own directory, which MUST be at or safely beneath the raw
root, and MUST match the manifest's `<slug>` naming convention. A manifest therefore
cannot bind members in another directory, including another safe descendant.

### 2. Deterministic generation and fixed JSON

Generation SHALL use no random value, timestamp, nonce, process identifier, host
identifier, or non-deterministic ordering. Given identical Markdown bytes, sidecar
bytes, and v1 canonical inputs, it SHALL produce byte-identical manifest content.

The manifest SHALL be serialized as fixed JSON: UTF-8, `ensure_ascii` behavior fixed
by the implementation, lexicographically sorted keys, compact fixed separators, and
a single terminal LF. Hash strings SHALL be lowercase 64-character hexadecimal
SHA-256 digests. No optional generated-at, producer, or diagnostic fields are
permitted in v1.

The writer SHALL create and validate the Markdown and sidecar first, calculate their
byte hashes and `canonical_hash`, serialize the manifest, and publish the manifest
last. Publishing the manifest last is a visibility protocol only; it does **not**
claim multi-file atomicity.

### 3. Freeze v1 sidecar and canonical-hash semantics

Sidecar schema v1 and the definition of `canonical_hash` are frozen for this binding
contract. The pair manifest does not reinterpret, normalize, or repair either
artifact. A change to v1 sidecar semantics or canonical-hash inputs/serialization
requires a new explicitly versioned schema and a coordinated migration; it MUST NOT
silently change the meaning of `schema_version: 1` manifests.

`canonical_hash` is verified in addition to byte hashes. It supplies logical-pair
identity under the frozen v1 definition; `markdown_sha256` and `sidecar_sha256`
supply exact-byte binding.

### 4. Strict production parser

Production parsing SHALL require a valid adjacent pair manifest. It SHALL have no
legacy fallback for a missing manifest, an older sidecar-only convention, inferred
filenames, partially valid fields, or an unrecognized schema version. Any contract
failure fails closed before the pair is accepted for downstream processing.

The parser SHALL reject at minimum:

- missing, unreadable, malformed, duplicate-key, or non-object JSON;
- unknown or unsupported `schema_version` values;
- absent, extra, wrongly typed, or non-canonical manifest fields;
- unsafe paths, missing members, or filenames that violate the pair convention;
- digest format violations or mismatches;
- invalid sidecar v1 data; and
- a recomputed v1 `canonical_hash` that differs from the manifest.

Test suites and fixtures SHALL migrate to create valid manifests. Because there are
no committed raw pairs, no compatibility corpus is retained as a reason for a
production legacy parser path.

### 5. Rooted, bounded, stable M-D-S-M read protocol

The production reader SHALL execute the following rooted, bounded M-D-S-M protocol,
with at most **three attempts** total:

1. **M — Manifest:** Use the authority/capability opened on the configured
   bundle root to read and strictly validate the adjacent manifest. This read is
   constrained to the logical `<bundle-root>/raw/` subtree.
2. **D — Markdown:** Resolve and read only the manifest-bound Markdown member;
   compute its SHA-256 and require equality with `markdown_sha256`.
3. **S — Sidecar:** Resolve and read only the manifest-bound sidecar member;
   compute its SHA-256, strictly validate sidecar v1, and require equality with
   `sidecar_sha256`.
4. **M — Manifest again:** Re-read the manifest and require byte identity with the
   first manifest read before accepting the recomputed `canonical_hash`.

Each attempt starts over from the first M on any read, parse, validation, byte-hash,
canonical-hash, path-containment, or stability failure. The reader SHALL accept only
an attempt in which all checks pass. After the third unsuccessful attempt it SHALL
fail closed; it SHALL not return a partially validated document, retry indefinitely,
or fall back to another format.

All resolution uses the authority/capability opened on the configured bundle root
and is constrained to the logical `<bundle-root>/raw/` subtree. Implementations
SHALL apply containment checks to resolved paths and avoid accepting redirects
outside that subtree.

### 6. Error redaction

Externally surfaced errors SHALL be stable, classified, and redacted. They MAY identify
the contract stage (for example, `pair_manifest_invalid`, `pair_hash_mismatch`, or
`pair_unstable`) and a safe relative artifact identity when operationally needed.
They SHALL NOT expose raw document contents, sidecar contents, absolute host paths,
internal exception traces, environment values, credentials, or complete untrusted
input payloads. Detailed diagnostics, where needed, belong only in protected internal
logs and must follow the same secret-redaction policy.

## Residual risks explicitly accepted

This decision reduces accidental and ordinary concurrent-write inconsistency, but it
does not make a filesystem transaction or a hostile filesystem safe.

- **Hardlinks:** A valid pathname may be hardlinked to content whose mutation affects
  another location. The protocol verifies observed bytes, not ownership or inode
  provenance.
- **In-place mutation:** A writer that modifies a member or manifest in place can race
  any reader. M-D-S-M detects many unstable observations but cannot prove a global
  snapshot across files.
- **Hostile simultaneous writer:** An adversary capable of changing files between or
  during reads can potentially cause retries, denial of service, or present a
  carefully timed stable-looking set. Three attempts bound resource use; fail-closed
  prevents acceptance when instability is observed, but does not establish hostile
  writer exclusion.
- **TOCTOU and platform semantics:** Symlink, reparse-point, handle, cache, and rename
  behavior varies by platform. Root containment and repeated validation are mandatory
  mitigations, not a security boundary against a privileged host actor.

Deployments requiring writer exclusion, ownership proof, or true multi-file atomicity
need a stronger storage boundary or coordination mechanism outside this ADR.

## Consequences

### Positive

- Raw Markdown and sidecar provenance is explicit, exact-byte verifiable, and
  reproducible.
- Deterministic manifests make fixture generation and review stable.
- Strict parsing avoids silently mixing generations or accepting obsolete formats.
- Bounded retries and redacted errors provide predictable operational behavior.

### Costs

- All raw-pair producers and test fixtures must generate an additional manifest.
- A transient write can cause up to three reads and then a fail-closed error.
- Existing raw inputs without manifests are intentionally invalid in production.
- Filesystem-level residual races remain and must not be described as solved.

## Non-goals and scope boundaries

This ADR does **not** expand into:

- Phase 18 controlled writeback;
- Phase 15 caller switch;
- a cross-file transaction, locking protocol, or atomic-publish guarantee;
- a compatibility parser for legacy raw artifacts; or
- changes to sidecar v1 or canonical-hash v1 semantics.

## GitNexus impact record

GitNexus analysis is **UNKNOWN/UNAVAILABLE** for this documentation-only ADR: the
required GitNexus MCP tools were not available in this execution environment. No code
symbol was edited and no automated graph result is asserted.

The textual blast radius is **HIGH**: future implementation touches raw-pair
producers, the production parser, canonical-hash/sidecar validation, raw-artifact
test fixtures, ingestion error handling, and all downstream consumers that assume a
validated raw document. Before implementation, maintainers MUST run GitNexus upstream
impact analysis for each target symbol, warn on any HIGH or CRITICAL result, and use
change detection before a commit.

## Implementation acceptance criteria

1. Repeated generation from identical inputs produces byte-identical
   `raw/<slug>.pair.json` output at the current zero-depth serializer location.
2. Parser tests cover each M-D-S-M failure point, one stable success, and exhaustion
   after exactly three attempts.
3. Tests prove rejection of missing manifests, unsafe paths, malformed JSON, unknown
   schema versions, incorrect byte hashes, invalid sidecar v1, and incorrect
   canonical hashes.
4. Tests prove zero-depth and safe nested pair locations are accepted only when all
   three same-slug members are adjacent; manifest `markdown_file` and `sidecar_file`
   remain plain filenames and cannot reference another directory.
5. Tests prove errors are redacted and do not include document contents, absolute
   paths, environment values, or credentials.
6. Tests cover observable replacement/in-place mutation behavior without asserting
   impossible multi-file atomicity.
7. No production legacy fallback is introduced; migrated fixtures use valid pair
   manifests.
