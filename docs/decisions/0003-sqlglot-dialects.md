# ADR 0003 — Canonical SQL in DuckDB, transpiled with SQLGlot

**Status:** accepted · 2026-10-11

## Decision
`sqlgen` emits DuckDB-dialect SQL; SQLGlot translates it to `teradata`, `postgres` or `mysql`.
Aggregations of DirectQuery models run entirely in the source.

## Consequences
- A single generator implementation; each source only declares its dialect.
- Every new translation needs a test with the expected SQL per dialect (snapshot).
- SQLGlot also validates the editor's free SQL: a single `SELECT`.
