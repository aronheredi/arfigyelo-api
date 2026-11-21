# 3. Client-side pre-validation of server-500 inputs

Date: 2026-11-19

## Status

Accepted

## Context

The API answers several client mistakes with `500 INTERNAL_SERVER_ERROR`
instead of a 4xx: invalid `order` values, negative or non-numeric
`limit`/`offset`, and a missing search query (API.md "Errors", quirk #10).
A consumer debugging a `500` that is actually their own bad argument gets a
misleading signal.

Notably, `limit > 48` is *not* an error: the server silently clips. A single
shared `order` enum would also be wrong — `relevance` is valid on
`/api/search` but 500s on `/api/products-by-category` (quirk #8).

## Decision

The client validates, before sending: `order` against a per-endpoint enum,
`limit`/`offset` as non-negative integers, and search `q` as ≥ 3 characters
after trimming. Violations raise `ArfigyeloValidationError` (an
`ArfigyeloError` subclass) with a per-field message. `limit > 48` is passed
through untouched and documented as server-clipped.

## Consequences

- Server 500s become almost always genuinely server-side.
- The validation surface is frozen to the API's observed behavior; if the
  server later accepts new `order` values, the client rejects them until
  updated. Accepted: the surface is five parameters across two endpoints.
- All validation paths are unit-tested without network.
