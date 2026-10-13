# PLAN — data2html

Status: **Phases 0–6 and 8 complete (2026-10-12)**; Phase 7 partly done (7a; 7b–7f pending). Check `[x]` and add the date (YYYY-MM-DD) when closing each item.
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
- [x] Dashboard editor (react-grid-layout) that writes `report-spec`; the builder's «Add to report…» persists visuals (2026-10-12)
- [x] Publishing: versioned `content/reports/<id>.yaml`; saving = publishing, only after validation (ADR 0008, ADR 0009) (2026-10-12)
- [x] Viewer `/r/<id>`: renderer HTML + per-visual endpoint with the reader's identity (2026-10-12) — development identities until Phase 7
- [x] Typed report parameters and `access` groups in the contract (ADR 0009) (2026-10-12)
- [x] `config/theme.yaml` palette: the studio's validated palette (light and dark pass the dataviz validator; the light-mode contrast WARN is covered by the table view and tooltips) (2026-10-12)
- [x] Viewer chrome in English/Spanish following the reader's language (2026-10-12)
- [x] Cross-filtering; cache by hash (spec + model + identity + parameters + cross-filters) (2026-10-12)
- [x] Security test: two users, same report, different data — `backend/tests/security/` (2026-10-12)
- **Demo:** `D2H_DEV_IDENTITIES=1 uvicorn data2html.api.main:app`, open `http://localhost:8000/r/ventas_regionales`,
  sign in as `norte` (only Norte), sign out, sign in as `direccion` (all regions); click a bar to cross-filter.

## Phase 7 — Teradata, auth and deployment
- [ ] `TeradataSource` with `teradatasql`, trusted session + `PROXYUSER`
- [ ] Native execution in the source for large aggregations: Teradata and Postgres (`postgres_query()` postponed from Phases 1 and 5; see ADR 0008)
- [x] 7a. Auth: local (scrypt) and OIDC (Microsoft Entra ID, code + PKCE) providers behind `auth.current_identity`; server-side sessions with real sign-out; development identities kept for localhost only (ADR 0010) (2026-10-12)
- [x] 7a. Studio routes require the author role; CSRF origin check on every state-changing request (ADR 0010) (2026-10-12)
- [ ] 7a. Try the OIDC flow against the real Entra ID tenant (App Roles `data2html.author` + one per RLS group); today only against a mock provider
- [ ] Viewer cache: per-source TTL and a cache shared between processes (today in memory, global TTL)
- [ ] Connection pool and per-source concurrent query limit
- [ ] Explorer over large remote tables: estimated count and pagination without deep `OFFSET` (today DuckDB reads the whole table for `count(*)` and for sorting)
- [ ] Production Docker; decide hosting (see the network note in ARCHITECTURE.md)
- [ ] pbix importer: `pbix2html` → `report-spec` + seeding of the semantic model
- **Demo:** a report migrated from Power BI served live with RLS.

## Phase 8 — MySQL, DynamoDB and exports
- [x] `MySQLSource` via DuckDB's `mysql` extension (shared `AttachedSource` with Postgres); exact RLS on MySQL's case/accent-insensitive collation (ADR 0011) (2026-10-12)
- [x] DynamoDB: export-to-S3 pipeline → flattened Parquet, CLI for an external scheduler + "Export now" in the studio, never a live `Scan` (ADR 0012) (2026-10-12)
- [x] Export a visual to CSV (server: the reader's RLS rows, formula-injection guard, BOM) and PNG (client) in the viewer, the builder and the report editor (2026-10-12)
- [ ] Try a DynamoDB export against a real AWS account (only stubs so far), with confirmation before running it
- **Demo:** the example report on MySQL (`docker compose up -d mysql`), a reader downloads its CSV with only its rows; a DynamoDB table exported from the studio.

## Phase 9 — Optional AI
- [ ] Switches: global, per source (exposure level), per user — enforced in the backend
- [ ] `LLMProvider`: Claude API, Bedrock, OpenAI-compatible (Ollama/vLLM); models in `config/ai.yaml`
- [ ] Tools: `get_catalog`, `propose_visual`, `run_query`, `profile_column`
- [ ] Call auditing, token budget, cache

## Loose ends (outside a specific phase)
Noted when closing Phases 0–3 (2026-10-11); most closed on 2026-10-12. Move into a phase when tackled.

- [x] Review and accept ADRs 0007, 0008, 0009 and 0010 (2026-10-12)
- [ ] Review and accept ADRs 0011 (MySQL, exact RLS) and 0012 (DynamoDB import) — "proposed"
- [x] Commit Phases 0–5 on a branch (`feat/phases-3-5-i18n`) (2026-10-12)
- [x] English codebase and docs; English/Spanish studio and API messages, language selector that follows the browser and is remembered (2026-10-12)
- [x] Schema tab: show and edit descriptions of computed columns (2026-10-12)
- [x] Clean up abandoned CSV uploads (older than a day; at start-up and on every upload) (2026-10-12)
- [x] DuckDB/source error messages no longer leak server paths (`data2html/scrub.py`: `<data>/…`, `<path>`) (2026-10-12)
- [x] Postgres/MySQL: "refresh catalog" (↻ in the sidebar; reconnects so new tables appear) (2026-10-12)
- [ ] Move to React 19 when Glide Data Grid ships a stable 6.x that declares it (still 6.0.3 / React ≤ 18 on 2026-10-12; 6.0.4 is alpha)
- [x] Browser check with real clicks (headless Edge over CDP): CSV upload dialog, grid scroll/sort/filters over 50k rows, computed columns and their descriptions (2026-10-12)
- [ ] The profile's "sample" notice in a browser: needs a remote table above 100k rows (unit-tested only)
- [x] `StarletteDeprecationWarning`: tests use `httpx2` (2026-10-12)
- [x] Saving a model/report from the studio keeps hand-written comments (round-trip update with `ruamel.yaml`) (2026-10-12)
- [x] Dimensions over the explorer's computed columns (RLS stays on physical columns) (2026-10-12)
- [x] `format: currency` in the studio reads the currency from `config/theme.yaml` (`GET /api/theme`) (2026-10-12)
- [x] SQL editor: pages are deterministic with ties (`ORDER BY …, COLUMNS(*)`, or positions when grouped) (2026-10-12)
- [x] Configuration reference: `docs/CONFIGURATION.md` (every variable; secrets marked) (2026-10-12)
- [ ] Copy what you need from `docs/CONFIGURATION.md` into `.env.example` (the dev harness cannot read `.env*` files)
- [x] Login throttle shared by all workers (SQLite, keys hashed) (2026-10-12)
- [x] Report editor: renaming a parameter renames it in the visuals' filters (2026-10-12)
- [x] `mode: snapshot` reports: per-reader snapshots kept until republished or `refresh_hours` (contract field) (2026-10-12)
- [x] Viewer and studio: temporal axes labelled by `time_grain` ("ene 2025", "T1 2025") (2026-10-12)

## Open decisions log
| Topic | Status | Note |
|---|---|---|
| Hosting | Open | Needs a direct network path to Teradata for the live viewer |
| Final name | Open | `data2html` is provisional |
