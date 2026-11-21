# 1. Money as Decimal

Date: 2026-11-19

## Status

Accepted

## Context

The Árfigyelő API returns all prices (HUF) as JSON numbers with up to two
decimals (`886.67`, `unitAmount: 997.78`). The package exists to compare and
order prices, and JSON floats are binary approximations: `886.67` is not
exactly representable, so equality checks, min-finding and repeated arithmetic
on `float` values drift.

Pydantic v2 parses JSON numbers into `Decimal` directly from the lexical
representation — there is no float round-trip — so exactness is available at
zero runtime cost.

## Decision

All money fields (`amount`, `unitAmount`, `minUnitPrice`, `productMinAmount`,
`returnFee`) are `Decimal` in every Pydantic model. Non-money numerics stay
`int`/`float`.

## Consequences

- Ordering, equality and aggregation over prices are exact.
- Consumers see `Decimal` in the public API; it is a `numbers.Real` and
  compares/formats like a number, but those needing `float` must convert
  explicitly.
- Hard to reverse: the field types are the package's public schema; changing
  `Decimal` → `float` later would be a breaking release.
