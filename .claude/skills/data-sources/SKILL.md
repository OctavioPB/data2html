---
name: data-sources
description: Use when implementing, configuring or debugging a data source (CSV, Postgres, MySQL, Teradata, DynamoDB) in backend/src/data2html/sources/, or when registering connections and credentials.
---

# Data sources

Interface: `sources/base.py::DataSource` (`id`, `dialect`, `catalog()`, `execute()`, `cancel()`).
All of them return `pyarrow.Table`.

| Source | Implementation | Mode | Notes |
|---|---|---|---|
| CSV | DuckDB `read_csv` → Parquet | Import | the user reviews the types before confirming |
| Postgres | `ATTACH ... (TYPE postgres, READ_ONLY)` | DirectQuery/Import | large aggregations: `postgres_query()` |
| MySQL | `ATTACH ... (TYPE mysql, READ_ONLY)` | DirectQuery/Import | same with `mysql_query()` |
| Teradata | `teradatasql` | DirectQuery | `PROXYUSER` via query band; see the security-rls skill |
| DynamoDB | native export to S3 → `httpfs` → flattened Parquet | Scheduled import | **never** a live `Scan` or keyless PartiQL |

## CSV: inference traps
Ambiguous dates (`03/04/2026`), decimal comma, codes with leading zeros turned into integers,
repeated headers. Show the inferred types and let the user correct them; store the decision next
to the Parquet (`<table>.schema.json`).

## Connections
- Registered in `config/sources.yaml`: id, type, host, database and the **name** of the environment
  variable holding the secret. Never the secret itself.
- Database user with `SELECT`-only permissions.
- A pool per source with a maximum size and a semaphore for concurrent queries.
- Profiling remote sources: always on a sample (`TABLESAMPLE`, `SAMPLE`), and say so.

## New source (checklist)
- [ ] Class satisfying `DataSource` (`isinstance(x, DataSource)` in a test).
- [ ] Catalog and `execute` tests against a container or a fake.
- [ ] Dialect added to the `sqlgen` snapshots.
- [ ] Review with `/review-security`.
