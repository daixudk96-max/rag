# Entity Canonicalization Minimum (v1)

## v1 decision

Entity resolution is deferred, but the architecture must preserve the separation between:

- mention text in a document span
- future stable entity identity

## Minimum rules

1. Do not derive future entity identity from `chunk_id`.
2. Mentions and entities are distinct conceptual layers.
3. Future graph extraction must attach evidence to `span_id`, not directly to vector chunks.
4. v1 may postpone alias resolution, but must not block later mention -> entity mapping.
