# PLAN — data2html

Status: **Phases 0–5 complete (2026-10-11)**; next: Phase 6. Check `[x]` and add the date (YYYY-MM-DD) when closing each item.
Phase exit criteria: green tests, manual demo described in the phase, `PLAN.md` updated.

## Phase 0 — Skeleton and contract
- [x] `report-spec` contract and semantic model in Pydantic (`backend/src/data2html/spec/`)
- [x] Chart-type compatibility rules (`spec/compat.py`) + tests
- [x] Export JSON Schema to `studio/src/generated/spec.schema.json` (`python -m data2html.spec.export`) (2026-10-11)
- [x] Minimal FastAPI: `/health`, empty `/api/catalog`; OpenAPI → TS types (`npm run gen:api`) (2026-10-11)
- [x] Studio with Vite + React + TS + TanStack Query + Zustand, base layout (sources sidebar) (2026-10-11)
- [x] CI: ruff, mypy, pytest, `npm run build` (2026-10-11)
- **Demo:** `pytest` green; the studio shows "API OK".

## Phase 1 — Sources: CSV and Postgres
- [x] `DataSource` interface (catalog, execute → Arrow, cancel, dialect) (2026-10-11)
- [x] CSV: upload, type inference reviewed by the user, conversion to Parquet (2026-10-11)
- [x] Postgres via DuckDB `ATTACH ... (TYPE postgres, READ_ONLY)` (2026-10-11); `postgres_query()` moves to Phase 5
- [x] Catalog with editable table and column descriptions (2026-10-11)
- [x] Connection registry; credentials only from env (2026-10-11)
- **Demo:** upload a CSV and see its catalog next to Postgres's.

## Phase 2 — Excel-like explorer
- [x] Virtualized grid (Glide Data Grid) with server-side pagination (2026-10-11)
- [x] Sort/filter/search → SQL (`ORDER BY`, `WHERE`, `LIMIT/OFFSET`) (2026-10-11)
- [x] Computed columns as SQL expressions (not cell formulas) (2026-10-11)
- **Demo:** explore 5M rows without the browser freezing.

## Phase 3 — EDA profiling
- [x] Per-column profile (`SUMMARIZE` + histogram/top-N) on a sample for remote sources (2026-10-11)
- [x] Correlations between numeric columns, IQR outliers, warnings (high cardinality, possible ID, % nulls) (2026-10-11)
- [x] The UI shows when the profile comes from a sample (2026-10-11)
- **Demo:** full profile of a CSV and of a Postgres table.

## Phase 4 — SQL editor
- [x] CodeMirror 6 with autocompletion from the catalog (2026-10-11)
- [x] SQLGlot validation: a single `SELECT`; timeout and cancellation (2026-10-11)
- [x] History and saved queries; result → "Create visual" (2026-10-11) — unsaved quick view; publishing is Phase 5
- [x] Cancel EDA profiling from the studio too (2026-10-11)
- **Demo:** query → chart in two clicks.

## Phase 5 — Semantic model and visual builder
- [x] Semantic model editor (dimensions, measures with owner and description) (2026-10-11)
- [x] `sqlgen`: visual + model → DuckDB SQL → SQLGlot to the source's dialect (2026-10-11)
- [x] "Create visual" from the SQL editor → publishable visual: extract the measure into the semantic model (2026-10-11) — «Publish as measure…»
- [x] Drag-and-drop builder: dimension / measure / color / filter shelves (2026-10-11)
- [x] Chart-type selector limited by `compat.allowed_marks` (2026-10-11)
- [x] ECharts rendering (table included as a `mark`) (2026-10-11)
- **Demo:** "net sales by region" as bars → switch to table → to pie.

## Phase 6 — Reports and live viewer
- [ ] Dashboard editor (react-grid-layout) that writes `report-spec` (visuals from the Phase 5 builder are not persisted yet: only "Copy YAML")
- [ ] Publishing: versioned `content/reports/<id>.yaml` (ADR 0008)
- [ ] Viewer `/r/<id>`: renderer HTML + per-visual endpoint with the reader's identity
- [ ] `config/theme.yaml` palette: the dataviz skill validator gives a colorblindness WARN (orange↔green, ΔE 6.2); adjust it or require direct labels. The studio uses the validated reference palette
- [ ] Viewer chrome in English/Spanish following the reader's language (same mechanism as the studio)
- [ ] Cross-filtering; cache by hash (spec + identity + parameters)
- [ ] Security test: two users, same report, different data
- **Demo:** a published report seen by two different identities.

## Phase 7 — Teradata, auth and deployment
- [ ] `TeradataSource` with `teradatasql`, trusted session + `PROXYUSER`
- [ ] Native execution in the source for large aggregations: Teradata and Postgres (`postgres_query()` postponed from Phases 1 and 5; see ADR 0008)
- [ ] Auth: interface with a local provider (dev) and OIDC (corporate SSO)
- [ ] Connection pool and per-source concurrent query limit
- [ ] Explorer over large remote tables: estimated count and pagination without deep `OFFSET` (today DuckDB reads the whole table for `count(*)` and for sorting)
- [ ] Production Docker; decide hosting (see the network note in ARCHITECTURE.md)
- [ ] pbix importer: `pbix2html` → `report-spec` + seeding of the semantic model
- **Demo:** a report migrated from Power BI served live with RLS.

## Phase 8 — MySQL, DynamoDB and exports
- [ ] `MySQLSource` via DuckDB's `mysql` extension
- [ ] DynamoDB: export-to-S3 pipeline → flattened Parquet (scheduled, never a live `Scan`)
- [ ] Export a visual to CSV/PNG

## Phase 9 — Optional AI
- [ ] Switches: global, per source (exposure level), per user — enforced in the backend
- [ ] `LLMProvider`: Claude API, Bedrock, OpenAI-compatible (Ollama/vLLM); models in `config/ai.yaml`
- [ ] Tools: `get_catalog`, `propose_visual`, `run_query`, `profile_column`
- [ ] Call auditing, token budget, cache

## Loose ends (outside a specific phase)
Noted when closing Phases 0–3 (2026-10-11). Move into a phase when tackled.

- [ ] Review and accept (or adjust) ADR 0007 — currently "proposed"
- [x] Commit Phases 0–5 on a branch (`feat/phases-3-5-i18n`) (2026-10-12)
- [x] English codebase and docs; English/Spanish studio and API messages, language selector that follows the browser and is remembered (2026-10-12)
- [ ] Schema tab: show and edit descriptions of computed columns (they are saved, not shown)
- [ ] Clean up abandoned CSV uploads in `data/uploads/` (those neither confirmed nor cancelled)
- [ ] DuckDB error messages can include local server paths: sanitize them before Phase 7
- [ ] Postgres: "refresh catalog" button (DuckDB caches the attached schema; new tables do not show up)
- [ ] Move to React 19 when Glide Data Grid ships a stable 6.x that declares it (pinned to 18.3 today)
- [ ] Manual browser check: grid scroll/sort/filters, CSV upload dialog, computed columns, the profile's
      "sample" notice (only headless screenshots and tests). The SQL editor, "Create visual", cancellations
      and the language switch were tested with real clicks (headless Edge over CDP)
- [ ] `StarletteDeprecationWarning` from `httpx` in tests: migrate when FastAPI resolves it
- [ ] Review and accept ADR 0008 (versioned content in `content/`, RLS in the author's preview) — "proposed"
- [ ] Saving a model from the studio rewrites the YAML and loses hand-written comments (ADR 0008)
- [ ] Dimensions over the explorer's computed columns: today a model only uses physical columns
- [ ] `format: currency` currency fixed to MXN in the studio: read it from `config/theme.yaml`
- [ ] SQL editor: the user's query `ORDER BY` has no tie-breaker; with ties, paginating by
      re-running can repeat/skip rows between pages (the explorer does break ties)
- [ ] Translate `.env.example` comments (the dev harness blocks reading `.env*` files)

## Open decisions log
| Topic | Status | Note |
|---|---|---|
| Hosting | Open | Needs a direct network path to Teradata for the live viewer |
| Final name | Open | `data2html` is provisional |
