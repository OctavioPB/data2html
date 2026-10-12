# ADR 0001 — DuckDB as the embedded analytics engine

**Status:** accepted · 2026-10-11

## Context
The app combines an Excel-like explorer, EDA profiling and visuals over CSV and remote databases.
Aggregating in Pandas does not scale beyond a few hundred thousand rows.

## Decision
In-process DuckDB for CSV/Parquet and as a federation layer towards Postgres/MySQL
(`postgres`/`mysql` extensions, `READ_ONLY`).

## Consequences
- (+) Fast columnar SQL with no extra server; reads CSV/Parquet/Excel natively.
- (−) A single writer per file: one database per project and connections per request.
- (−) It does not always push aggregations down to Postgres/MySQL; see ADR 0003.
