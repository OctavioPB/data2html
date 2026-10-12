# data2html — From data to HTML reports, without Power BI

A home-grown web app for **EDA, SQL querying and visualization** (Excel + Power BI + SQL in a single
tool) that publishes **live-served HTML reports** with row-level security.

- **Backend:** FastAPI on Uvicorn, Python 3.12, DuckDB, SQLGlot, Pydantic v2.
- **Frontend (studio):** React + Vite + TypeScript.
- **Sources:** CSV (upload), Postgres, MySQL, Teradata, DynamoDB (via export to S3).
- **Origin:** succeeds `pbix2html`. Its engine (query/render/serve) is brought over here in phases
  (see `backend/src/data2html/importers/pbix/README.md`); its extractor stays as an importer.
  pbix2html keeps running until the cutover: do not modify it from this repo.

Read `PLAN.md` to know which phase we are in. Read `docs/ARCHITECTURE.md` before touching more
than one module. Closed decisions live in `docs/decisions/` — do not reopen them without a new ADR.

## Mental model (do not break it)

```
Studio (single author) ──► report-spec (validated YAML/JSON) ──► engine ──► live HTML (readers)
pbix importer ─────────┘         ▲
                         semantic model (measures defined ONCE)
```

1. **The `report-spec` is the contract.** The studio, the pbix importer and (later) the AI produce it.
   The engine consumes it. It lives in `backend/src/data2html/spec/`. If you change the contract, also
   change the exported JSON Schema, the examples in `examples/` and the tests.
2. **Measures are defined in the semantic model, never in the visual.** A visual references
   `measure: venta_neta` by name. Measure SQL embedded in a visual is forbidden.
3. **The browser never receives raw data.** Only aggregated results or pages (`LIMIT`).
4. **SQL is generated in the DuckDB dialect and transpiled with SQLGlot** to the source's dialect.
   Never concatenate SQL strings with user values: use parameters.
5. **One author, many readers.** The studio is single-user. The viewer (`/r/...`) is multi-user with RLS.

## Hard rules (security)

- **Never** an HTML with data from more than one role/user. Every viewer response is computed with
  the reader's identity.
- Teradata RLS: trusted session with `PROXYUSER` via `SET QUERY_BAND`. The identity comes from the
  auth provider (OIDC or local login), **never** from a request parameter.
- Source connections: database users with `SELECT` only. Also, all free SQL is parsed with SQLGlot
  and rejected unless it is a single `SELECT`.
- Credentials: only in environment variables / vault. Never in repo YAML, logs or responses.
- Server DuckDB: `enable_external_access=false` except during ingestion, memory and thread limits,
  per-query timeout.
- Data in HTML: escape `<`, `>`, `&` in embedded JSON; cells with `textContent`.
- If the AI is enabled, its tools run with the identity and RLS of the user asking.

## Conventions

- Python: `ruff` + `mypy --strict` in `spec/`, `semantic/`, `sqlgen/`. Tests with `pytest`.
- Pydantic models with `extra="forbid"`: an unknown field is an error, not ignored.
- Every source implements `DataSource` (`backend/src/data2html/sources/base.py`) and returns Arrow.
- Frontend: types generated from OpenAPI (`npm run gen:api`); do not hand-write API types.
- Licenses: permissive only (MIT/Apache/BSD). GPL or commercial ones are forbidden without an ADR.
- AI model names and credentials: always in configuration, never in code.
- Language: code, comments and docs in English. User-facing text is translated:
  - Backend: English msgid in `tr("...", **params)` (`data2html/i18n.py`) plus its entry in
    `locales/es.py`; `tests/test_i18n.py` fails if one is missing or unused.
  - Studio: key in `studio/src/i18n/en.ts` and `es.ts`, used through `useT()` / `t()`.
  - Data, model/measure names and report content are never translated.

## Working with me

- One phase at a time; check boxes in `PLAN.md` when done and add the date.
- Before implementing anything that touches the contract, security or a new source, show me
  the design (files to touch + interface) and wait for my approval.
- Before running anything against real Teradata, ask me for confirmation.
- Use the skills in `.claude/skills/` for their domain. Commands: `/phase`, `/new-source`,
  `/new-visual`, `/review-security`.

## Commands

```bash
docker compose up -d postgres          # development source
cd backend && pip install -e ".[dev]" && pytest -q
uvicorn data2html.api.main:app --reload
cd studio && npm install && npm run dev
```
