# ADR 0012 — DynamoDB as an Import source: native S3 export → Parquet, never a live Scan

**Status:** proposed · 2026-10-12

## Context
DynamoDB has no SQL engine for analytics; a live `Scan` (or keyless PartiQL) on every report interaction
would be slow, expensive and would compete with the production workload.

## Decision
1. **Import mode.** `python -m data2html.ingest dynamodb <source> [--table t]`, run from an external
   scheduler (cron, Task Scheduler, Kubernetes CronJob); the web server schedules nothing. The studio's
   author can also start one export per table ("Export now"); a lock file keeps it single-flight across
   processes.
2. **Pipeline.** `ExportTableToPointInTime` (PITR required; DYNAMODB_JSON; full export) → wait → manifests
   → boto3 downloads only keys under the export's own prefix → Python extracts the **declared** columns
   (`path: a.b` follows nested maps; lists/sets/maps → JSON text) into JSON lines → a sandboxed DuckDB (no
   network, only the staging and output directories, no UDFs) applies `TRY_CAST`s, counts values that did
   not convert, and atomically replaces `data/dynamodb/<source>/<table>.parquet` (+ `.export.json`).
3. **Queries** read those Parquet files like CSV uploads (`ParquetSource`): RLS from the semantic model
   applies as usual. Epoch timestamps convert with `make_timestamp(µs)` (UTC, independent of the server's
   time zone).
4. **Credentials** come from boto3's standard chain (role, environment, profile), never from YAML. boto3 is
   an optional dependency (`pip install -e ".[dynamodb]"`; Apache-2.0).

## Consequences
- DuckDB keeps `enable_external_access=false` everywhere: the network is boto3's, the flattening is local.
- Data is as fresh as the last export; the studio shows its time, row count and conversion warnings.
- Exports cost per GB and take minutes; incremental exports are a later improvement.
- Tested only against stubs (botocore Stubber + generated export files); no real AWS account was used.
