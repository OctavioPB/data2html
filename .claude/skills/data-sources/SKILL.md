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
| Postgres | `AttachedSource`: `ATTACH ... (TYPE postgres, READ_ONLY)` | DirectQuery | native execution pending (7b) |
| MySQL | `AttachedSource`: `ATTACH ... (TYPE mysql, READ_ONLY)` | DirectQuery | `loose_collation`: RLS re-checked exactly (ADR 0011) |
| Teradata | `teradatasql` | DirectQuery | `PROXYUSER` via query band; see the security-rls skill |
| DynamoDB | `ParquetSource` over `ingest/dynamodb.py` output: native S3 export → boto3 → declared columns → Parquet | Scheduled import | **never** a live `Scan` or keyless PartiQL (ADR 0012) |

## CSV: inference traps
Ambiguous dates (`03/04/2026`), decimal comma, codes with leading zeros turned into integers,
repeated headers. Show the inferred types and let the user correct them; store the decision next
to the Parquet (`<table>.schema.json`).

## Collation and pushdown
Check how the source compares text: if it ignores case/accents and DuckDB pushes filters down to it,
set `loose_collation = True` so RLS stays exact. Seed dev data with an explicit UTF-8 client charset.

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
