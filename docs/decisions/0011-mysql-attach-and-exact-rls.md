# ADR 0011 — MySQL through DuckDB's `mysql` extension; exact RLS on loose collations

**Status:** proposed · 2026-10-12

## Context
Phase 8 adds MySQL. Phase 7b (native execution with pg8000) is still pending, so MySQL follows the same
path Postgres uses today. Probing DuckDB 1.5.6 + MySQL 8.4 showed three things:
1. With the sandbox locked, `ATTACH` and writes are blocked, but `mysql_query(...)` and
   `CALL mysql_clear_cache()` still run (as ADR 0007 found for `postgres_query`).
2. The MySQL database appears as a schema (`d2h`), next to `information_schema`.
3. MySQL's default collation (`utf8mb4_0900_ai_ci`) ignores case and accents, and DuckDB pushes filters
   down to MySQL without re-checking them: `region_desc IN ('bajio')` returns the rows of `Bajío`.

## Decision
1. `MySQLSource` attaches READ_ONLY with a temporary secret (password from the environment, `ssl_mode`
   configurable), sharing `AttachedSource` with Postgres. Only the configured database is visible
   (`<database>.<table>`). `ensure_single_select` keeps rejecting `mysql_*` and non-SELECT statements.
2. Sources whose text comparison is loose declare `loose_collation = True`. For them `sqlgen` emits the RLS
   predicate twice: `col IN (…)` (pushed down, it narrows the rows in MySQL) **and**
   `(col || '') IN (…)`, which DuckDB cannot push down and evaluates exactly. A group "sur" never sees "Sur".
3. Development and CI run a `mysql:8.4` service with the same `fact_ventas` seed (`SET NAMES utf8mb4`:
   the init client is latin1 and otherwise stores `Bajío` double-encoded).

## Consequences
- Reader filters (parameters, cross-filters) keep MySQL's semantics (case/accent-insensitive); only RLS is
  forced to be exact. Author-side explorer filters behave like the source.
- When native execution (7b) arrives, MySQL moves with Postgres; the exact-RLS rule must then be expressed
  in the source's dialect (e.g. `COLLATE utf8mb4_bin` / `BINARY`).
