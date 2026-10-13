# data2html

**From your data to live HTML reports — without Power BI.**

data2html is a self-hosted web app that puts the everyday analytics workflow in one place: explore a table
like a spreadsheet, profile it, query it with SQL, define your business metrics once, build charts, and
publish them as **live HTML reports** where every reader only sees the rows they are allowed to see.

- **Explore** any table with a fast, virtualized grid: sort, filter, search and add computed columns.
- **Profile** a table in one click: distributions, top values, outliers, correlations and data-quality
  warnings.
- **Query** with a SQL editor (autocomplete, cancel, history, saved queries). Only read-only `SELECT`
  statements are accepted.
- **Model:** define dimensions and **measures once** in a semantic model (e.g. `venta_neta =
  SUM(monto_bruto - descuento)`), so a number is the same in every report.
- **Build** charts by drag and drop (bars, lines, pie, KPI, table), arrange them into dashboards, and
  publish them.
- **Share** live reports at `/r/<id>`:
  - **row-level security (RLS)** per reader;
  - parameters and cross-filtering;
  - CSV/PNG downloads;
  - optional per-reader snapshots.
- **Connect** to CSV uploads, PostgreSQL, MySQL and DynamoDB (via S3 exports). Teradata is planned.
- **Bilingual:** the interface is in English and Spanish (ES/EN switch).

It succeeds `pbix2html`, and its reports follow an open, validated YAML contract (`report-spec`).

---

## Contents

1. [How it works](#how-it-works)
2. [Requirements](#requirements)
3. [Quick start](#quick-start)
4. [Using the app](#using-the-app)
5. [Configuration](#configuration)
6. [DynamoDB imports](#dynamodb-imports)
7. [Tests and checks](#tests-and-checks)
8. [Project layout](#project-layout)
9. [Status and roadmap](#status-and-roadmap)
10. [Further reading](#further-reading)

---

## How it works

```
                   ┌──────────── backend (FastAPI + DuckDB) ────────────┐
 Studio (author) ─►│  semantic model ─► SQL generator ─► data source    │◄─ Postgres / MySQL / CSV / DynamoDB
 React, :5173      │  report-spec (YAML, versioned in content/)         │
                   │  sign-in, sessions, RLS, cache                     │
 Readers ─────────►│  live viewer /r/<id>  (HTML + aggregated JSON)     │
                   └────────────────────────────────────────────────────┘
```

There are two roles:
- **Author:** one person, who works in the **studio** (the React app). They connect sources, define
  semantic models, build visuals and publish reports. Saving a report publishes it.
- **Readers:** many people, who open the **viewer** (`/r/<report>`). Every response is computed for the
  reader's identity, so each one gets only their rows.

The browser never receives raw tables, only aggregated results or paginated rows. SQL is generated as an
AST and transpiled with SQLGlot, and user values always travel as parameters.

---

## Requirements

| Tool | Version | Used for |
|---|---|---|
| [Python](https://www.python.org/) | 3.12+ | backend |
| [Node.js](https://nodejs.org/) | 22+ (with npm) | studio (frontend) |
| [Docker](https://docs.docker.com/get-docker/) with Compose | any recent | sample Postgres and MySQL databases |
| Git | any | cloning |

Everything below works on Windows, macOS and Linux. Where commands differ, both forms are shown.
Docker is optional: without it you can still upload CSV files.

---

## Quick start

About ten minutes from clone to your first report.

### 1. Clone

```bash
git clone https://github.com/OctavioPB/data2html.git
cd data2html
```

### 2. Start the sample databases (optional, recommended)

```bash
docker compose up -d postgres mysql
```

This starts PostgreSQL (port 5432) and MySQL (port 3306), each seeded with the same table `fact_ventas`:
50,000 sales across four regions (Norte, Centro, Sur, Bajío). The app connects with a read-only user.

### 3. Create your `.env`

Create a file named `.env` in the repository root. You can start from `.env.example`. It needs at least:

```dotenv
# Development sign-in: pick a fake identity at /login (localhost only — never in production)
D2H_DEV_IDENTITIES=1
# Passwords of the read-only users in the sample databases (see docker-compose.yml)
PG_DEV_PASSWORD=d2h
MYSQL_DEV_PASSWORD=d2h
```

Every available variable is listed in [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md).

### 4. Register the data sources

```bash
# macOS / Linux
cp config/sources.example.yaml config/sources.yaml
# Windows (PowerShell)
Copy-Item config/sources.example.yaml config/sources.yaml
```

`config/sources.yaml` is not committed. The example already points to the two sample databases. If you
skipped Docker, you can leave this file out, and you will still have CSV uploads.

### 5. Install and start the backend

```bash
cd backend
python -m venv .venv
```

Activate the environment:

```bash
# macOS / Linux
source .venv/bin/activate
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
```

Install and run:

```bash
pip install -e ".[dev]"
python -m data2html.devtools install-extensions   # one-time: DuckDB's postgres/mysql connectors
uvicorn data2html.api.main:app --reload --env-file ../.env
```

The API is now at http://localhost:8000, with interactive docs at http://localhost:8000/docs. Leave it
running.

### 6. Install and start the studio

In a second terminal, from the repository root:

```bash
cd studio
npm install
npm run dev
```

### 7. Sign in

Open **http://localhost:5173** and click **Sign in**. In development you can choose an identity without
a password:

| Identity | Can use the studio | Sees in reports (RLS) |
|---|---|---|
| `autor` | yes (author) | all regions |
| `norte` | no | only Norte |
| `sur` | no | only Sur |
| `direccion` | no | all regions |
| `sin_grupo` | no | nothing |

Pick **`autor`**. You will see the sources in the sidebar: `postgres_dev`, `mysql_dev` and `csv`. The
identities are defined in [`config/dev_identities.yaml`](config/dev_identities.yaml).

> The repository ships with a sample semantic model (`content/semantic/ventas.yaml`) and a sample report
> (`content/reports/ventas_regionales.yaml`), both over `postgres_dev`. Open
> http://localhost:5173/r/ventas_regionales to see a live report straight away.

---

## Using the app

A short tour, in the order you will usually work.

### Add data

- **Databases:** sources in `config/sources.yaml` appear in the sidebar automatically. If someone adds
  tables later, the **↻** button next to a Postgres/MySQL source re-reads its schema.
- **CSV:** click **+ CSV** and choose a file.
  - data2html detects the encoding, the delimiter and each column's type.
  - It warns about common traps: decimal commas, ambiguous dates, codes with leading zeros.
  - Review the types, name the table and click **Create table**. The data is stored as Parquet under
    `data/`.

### Explore a table (*Data* tab)

Click a table to open it. The grid loads pages from the server as you scroll, so tables with millions of
rows stay fast.
- Sort by clicking a column header.
- Add filters with **+ Filter**, or use the search box for text columns.
- Click **+ Computed column** to add a column defined by an SQL expression, for example
  `monto_bruto - descuento`. Computed columns can later be used as dimensions in a model.

### Profile it (*Profile* tab)

Shows per-column statistics, histograms, top values, outliers, correlations and warnings (possible IDs,
high null rates, numbers stored as text…). For remote tables the profile is computed on a sample, and the
page says so.

### Describe it (*Schema* tab)

Write descriptions for the table and its columns, including computed ones. They show up as hints
throughout the studio.

### Query it (*SQL editor*)

Write a `SELECT` against one source, using the table names from the sidebar.
- **Run** with **Ctrl+Enter**; **Stop** cancels a long query.
- Results are paginated. **History** and **Saved** queries sit next to the editor.
- Anything that is not a single read-only `SELECT` is rejected.
- **Chart** gives you a quick view of the result.
- **Publish as measure…** turns an aggregate in your query into a measure of a semantic model.

### Define a semantic model (*Models and visuals*)

A model belongs to one table and declares:
- **dimensions:** what you group and filter by (a region, a date, a channel);
- **measures:** what you aggregate, each with an owner and a description;
- optional **RLS:** which column is matched against each reader's groups.

Measures are defined **here, once**: visuals only reference them by name. Every save is validated
against the real source (each measure is actually executed), and the model is stored as YAML in
`content/semantic/`. Hand-written comments in that file are preserved.

### Build a visual (*Builder* tab)

1. Drag a dimension and a measure onto the shelves. Optionally add a color dimension and filters.
2. Choose a chart type. Only the types that fit the data are offered.
3. Download the result as **CSV** or **PNG**, or click **Add to report…**.

### Compose and publish a report (*Reports*)

The report editor arranges visuals on a 12-column grid: drag a visual by its handle (⠿) to move it, and
resize it from the corner. You can also set:
- **Parameters**, for example a start date with a default. Readers can change them.
- **Access:** the groups allowed to open the report. Empty means any signed-in reader.
- **Mode:**
  - **Live** queries the source on every view.
  - **Snapshot** keeps each reader's data until you republish, or for N hours.

**Save and publish** validates the report and writes it to `content/reports/<id>.yaml`. That makes it
live at `/r/<id>` straight away; **Open viewer** takes you there.

### Read a report (*viewer*, `/r/<id>`)

Readers sign in and see only the rows their groups allow. On a report they can:
- change parameters;
- switch a visual's chart type (it is redrawn with the same data);
- click a bar or a slice to cross-filter the other visuals;
- download each visual as CSV (only their data) or PNG.

To see RLS in action, open http://localhost:5173/r/ventas_regionales as `norte`, sign out, and open it
again as `direccion`. The numbers change because each reader gets different rows.

---

## Configuration

All configuration lives in `config/` and in environment variables. **Secrets are only ever environment
variables.** The config files hold variable *names*, never values. See
[`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) for the full reference.

| File | Purpose | Committed? |
|---|---|---|
| `config/sources.yaml` | Data sources (start from `sources.example.yaml`) | no |
| `config/auth.yaml` | Sign-in providers (start from `auth.example.yaml`) | no |
| `config/users.yaml` | Local users with hashed passwords (start from `users.example.yaml`) | no |
| `config/dev_identities.yaml` | Fake identities for development | yes |
| `config/theme.yaml` | Chart palette (light and dark), font and currency | yes |

### Data sources

Each entry in `config/sources.yaml` has an id, a `type` and connection details. Use a database user with
read-only (`SELECT`) permissions.

| Type | Mode | Notes |
|---|---|---|
| `postgres` | live (DirectQuery) | `password_env` names the variable that holds the password |
| `mysql` | live (DirectQuery) | same; RLS compares exactly even though MySQL ignores case and accents |
| `dynamodb_export` | import (Parquet) | refreshed by an export job, never by scanning the table live ([below](#dynamodb-imports)) |
| CSV | import (Parquet) | always available, through uploads in the studio |

### Users and sign-in

The studio requires an **author** session, and the viewer requires any signed-in identity. There are three
ways to sign in:

1. **Local users** (username and password):
   ```bash
   python -m data2html.auth add-user ana --email ana@example.com --groups Norte,Sur --author
   ```
   This prompts for the password and stores only a scrypt hash, in `config/users.yaml`. `--groups` feeds
   report access and RLS, and `--author` grants the studio.
2. **Microsoft Entra ID (OIDC):** copy `config/auth.example.yaml` to `config/auth.yaml` and fill in the
   `oidc` section. Register the redirect URI `<D2H_PUBLIC_URL>/auth/callback` and define App Roles: one
   per report group (e.g. `Norte`) and `data2html.author` for the studio. Put the client secret in the
   environment variable named by `client_secret_env`.
3. **Development identities:** `D2H_DEV_IDENTITIES=1`. They only work on localhost. **Never enable them
   in production.**

In production, also set `D2H_SESSION_SECRET` (at least 32 random characters) and `D2H_PUBLIC_URL`.

### Theme

`config/theme.yaml` sets the categorical palette (validated for color-blind safety, in light and dark
variants), the font, and the currency used by measures with `format: currency`.

---

## DynamoDB imports

DynamoDB tables are imported, never queried live:
1. A native **export to S3** (point-in-time recovery must be enabled on the table).
2. data2html downloads it and keeps **only the columns you declare**.
3. It writes them as Parquet, which reports then query like any other table.

```bash
pip install -e ".[dynamodb]"                         # adds boto3
python -m data2html.ingest dynamodb <source-id>      # all tables of that source; --table <name> for one
```

- **When it runs:** schedule the command with cron, Windows Task Scheduler or a Kubernetes CronJob. The
  author can also click **Export now** in the studio.
- **AWS credentials:** they come from the standard AWS chain (instance role, environment variables or
  profile), never from config files.
- **Configuring the export:** the source entry is in `config/sources.example.yaml`, and the full design in
  [ADR 0012](docs/decisions/0012-dynamodb-import-via-s3-export.md).

---

## Tests and checks

Backend (from `backend/`, with the virtual environment active):

```bash
pytest -q          # ~600 tests: contract, sources, SQL generation, API, security (RLS, sign-in, CSRF…)
ruff check .       # lint
mypy src           # types (strict in spec/, semantic/, sqlgen/)
```

The Postgres and MySQL integration tests run when the Docker databases are up, and are skipped
otherwise.

Studio (from `studio/`):

```bash
npm run lint
npm run build      # type-check + production bundle
```

When you change the API, regenerate the frontend types so the studio stays in sync:

```bash
cd backend && python -m data2html.api.openapi    # writes studio/src/generated/openapi.json
cd ../studio && npm run gen:api                  # writes studio/src/generated/api.ts
```

CI (`.github/workflows/ci.yml`) runs all of the above against Postgres and MySQL services.

Optional: `python -m data2html.devtools demo` creates a 5-million-row CSV table (`demo_ventas`), to see the
explorer handle large tables.

---

## Project layout

```
backend/src/data2html/
  spec/        the report-spec contract (Pydantic) + JSON Schema export
  sources/     data sources: CSV, Postgres, MySQL, DynamoDB (all return Arrow)
  ingest/      scheduled imports (DynamoDB S3 export → Parquet)
  sqlgen/      SQL generation and validation (SQLGlot)
  semantic/    semantic models: storage and validation against the source
  profiling/   EDA profiles
  reports/     published report storage
  render/      viewer HTML, viewer.js, theme, cache, snapshots, CSV export
  auth/        sign-in (local, OIDC, dev), sessions, CSRF
  api/         FastAPI routes (studio, sign-in, viewer)
  locales/     Spanish translations of server messages
studio/        React + Vite + TypeScript frontend (src/i18n: English/Spanish)
content/       versioned semantic models and published reports (YAML)
examples/      reference model and report used by the tests
config/        configuration (examples and non-secret defaults)
dev/           seed SQL for the sample databases
docs/          architecture, configuration, decisions (ADRs)
```

---

## Status and roadmap

**Version 0.1.0, under active development.** See [`PLAN.md`](PLAN.md) for the detailed plan.

| Area | Status |
|---|---|
| CSV, Postgres, MySQL, DynamoDB sources | ✅ |
| Explorer, profiling, SQL editor | ✅ |
| Semantic models, visual builder, reports, live viewer with RLS | ✅ |
| Local and Microsoft Entra ID sign-in, protected studio | ✅ (Entra ID only tested against a mock provider so far) |
| CSV/PNG exports, snapshot reports, English/Spanish | ✅ |
| Teradata source (trusted sessions with `PROXYUSER`) | planned |
| Production Docker image and deployment guide | planned |
| Power BI (`.pbix`) importer | planned |
| Optional AI assistant | planned |

Until the production image is ready, run data2html as described in [Quick start](#quick-start). Do not
expose a development setup (`D2H_DEV_IDENTITIES=1`) to a network.

---

## Further reading

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): components, how a query flows, identity and roles.
- [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md): every environment variable.
- [`docs/decisions/`](docs/decisions/): architecture decision records (ADRs 0001–0012).
- [`studio/README.md`](studio/README.md): frontend details (generated types, i18n, pinned versions).
- [`CLAUDE.md`](CLAUDE.md): working rules for contributors and for Claude Code (`/phase`, `/new-source`,
  `/new-visual`, `/review-security`).

There is no license file yet. Ask the maintainer before reusing the code.
