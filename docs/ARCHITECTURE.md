# Architecture

## Components

```
studio/ (React, author)           viewer /r/<id> (HTML, readers)
        │  REST + Arrow IPC              │  JSON per visual
        ▼                                ▼
backend/src/data2html/
  api/        FastAPI: studio and viewer routes, auth
  spec/       CONTRACT: Report, Visual, SemanticModel, compat, JSON Schema
  semantic/   loading and cross-validation of semantic models
  sqlgen/     Visual + SemanticModel → DuckDB SQL → SQLGlot(dialect)
  sources/    DataSource: csv, postgres, mysql, teradata, dynamodb_export
  profiling/  EDA (statistics, histograms, correlations, sampling)
  render/     Jinja2 + ECharts → report HTML (mark selector included)
  auth/       providers: local, oidc → Identity
  ai/         optional: LLMProvider, tools, exposure policies
  i18n.py, locales/  server messages in English / Spanish (per request)
  importers/pbix/    extractor inherited from pbix2html
```

## How a visual query flows

1. The viewer requests `GET /api/r/{report}/visuals/{visual}?params`.
2. `auth` resolves the reader's `Identity` (never from parameters).
3. The `Visual` is loaded from the `report-spec`, together with the `SemanticModel` it references.
4. `sqlgen` builds DuckDB-dialect SQL with parameters; SQLGlot transpiles it to the source's dialect.
5. The source runs it with the identity (Teradata: `PROXYUSER`; others: the model's RLS filter).
6. Result as Arrow → compact JSON (columns + rows) to the browser.
7. Cache by `hash(spec, identity, parameters)` with a per-source TTL.

## Execution modes

| Mode | Where the SQL runs | Sources |
|---|---|---|
| Import | Local DuckDB over Parquet | CSV, DynamoDB (export), optionally Postgres/MySQL |
| DirectQuery | In the source | Teradata, Postgres, MySQL |

Postgres/MySQL through DuckDB extensions: filters are pushed down, aggregations not always.
For large tables, `sqlgen` emits the whole query in the source's dialect
(`postgres_query`, `mysql_query` or a native connection) — planned for Phase 7 (ADR 0008).

## Identity and roles

- **Author:** a single user with access to the studio (`role=author`).
- **Reader:** any authenticated identity with access to the published report.
- `auth/` exposes `Identity(user_id, email, groups, provider)`. Providers: `local` (development and
  personal use) and `oidc` (corporate SSO). Both can be active at once.
- For Teradata, only `oidc` identities map to `PROXYUSER`; a local identity gets no Teradata data in
  the viewer unless the author configures an explicit mapping.

## Language

User-facing server messages are English msgids wrapped in `tr()`; the request language comes from
`Accept-Language` (the studio sends the user's choice) and `locales/es.py` holds the Spanish catalog.
The studio has its own typed dictionaries (`studio/src/i18n`). Data, model names and report content are
not translated.

## Network and hosting (open decision)

The live viewer queries Teradata on every interaction: it needs direct, low-latency connectivity. If
Teradata is on-prem, the viewer will probably live on the corporate network. Everything is packaged in
Docker and configured through environment variables so we are not tied to a provider.

## Why it is this way

See `docs/decisions/`.
