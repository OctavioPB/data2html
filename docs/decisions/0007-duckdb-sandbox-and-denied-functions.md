# ADR 0007 — DuckDB sandbox + denied-function list; one connection per remote source

**Status:** proposed · 2026-10-11

## Context
Every query runs in a DuckDB with `allowed_directories`, `enable_external_access=false` and
`lock_configuration=true`. While integrating Postgres we confirmed (DuckDB 1.5.6) that this is **not
enough**: with the configuration locked, `postgres_scan('host=…')`, `postgres_query` and
`postgres_execute` are still available, and `COPY … TO` writes inside an allowed directory. Also,
`ATTACH` is blocked after locking, so a remote source has to be attached beforehand.

## Decision
1. **Two layers for SQL.** `sqlgen/validate.ensure_single_select` runs inside each source's `execute()`:
   a single `SELECT`, no table functions except `range`/`generate_series`/`unnest`, and none of the
   `postgres_*`, `mysql_*`, `sqlite_*`, `read_*`, `parquet_*`, `duckdb_*`, `pragma_*`, `glob`, `query`,
   `query_table`, `getenv`, `current_setting`, `which_secret`, `load_extension` functions. The DuckDB
   sandbox stays as a second layer, not the only one.
2. **One long-lived DuckDB connection per remote source**: `LOAD` → temporary secret with the password
   from the environment → `ATTACH … READ_ONLY` → sandbox lock. Each query uses its own `cursor()`.
3. Sources that do not respond do not bring the app down: the catalog marks them with `status="error"`,
   the API answers 503 with a generic message, and it retries after 30 s.

## Consequences
- A new DuckDB function that reads files or opens connections requires reviewing the list (test in
  `tests/test_sqlgen_validate.py`). Phase 4 (SQL editor) inherits this validation as is.
- The Postgres catalog stays in DuckDB's cache; schema changes will need an explicit "refresh"
  (pending).
- The connection pool and per-source concurrency limits remain in Phase 7.
