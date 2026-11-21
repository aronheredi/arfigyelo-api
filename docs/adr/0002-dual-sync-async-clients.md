# 2. Dual sync/async clients from one implementation

Date: 2026-11-19

## Status

Accepted

## Context

The package is a library embedded by other Python programs whose concurrency
model we do not control. Some consumers are synchronous scripts; others run
event loops. Choosing one execution model excludes the other class of
consumers or forces them into executors.

## Decision

Build on `httpx`: one shared request/response implementation with all
validation, caching and parsing logic written once, exposed as
`ArfigyeloClient` (sync) and `AsyncArfigyeloClient` (async facades).

## Consequences

- Both consumer classes are first-class; method signatures mirror each other
  1:1.
- `httpx.MockTransport` provides deterministic network-free testing for both
  facades with no extra mock library.
- Cost: `httpx` is a heavier dependency than `requests` or `aiohttp`
  individually. Accepted.
- Hard to reverse: the client classes are the package's primary public surface.
