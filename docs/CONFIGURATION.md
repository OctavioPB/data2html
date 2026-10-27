# Configuration

Everything is configured through environment variables and files in `config/`. Secrets live **only** in
the environment (or a vault that injects them); config files hold the *names* of the variables that
carry them. Copy what you need into your `.env` (see `.env.example`).

## Server

| Variable | Default | Purpose |
|---|---|---|
| `D2H_DATA_DIR` | `data/` | Parquet tables, uploads, catalog metadata, sessions (`sessions.sqlite`), per-reader snapshots (`snapshots.sqlite`). Not versioned; it holds data — protect it like the sources. |
| `D2H_CONTENT_DIR` | `content/` | Semantic models and published reports (versioned in git, ADR 0008). |
| `D2H_SOURCES_FILE` | `config/sources.yaml` | Connection registry (see `config/sources.example.yaml`). |
| `D2H_THEME_FILE` | `config/theme.yaml` | Palette, font and currency for the studio and the viewer. |
| `D2H_MAX_UPLOAD_MB` | `500` | Largest CSV upload. |
| `D2H_DUCKDB_MEMORY` | `2GB` | Memory limit of each server-side DuckDB. |
| `D2H_DUCKDB_THREADS` | `4` | Threads of each server-side DuckDB. |
| `D2H_QUERY_TIMEOUT_S` | `60` | Per-query timeout. |
| `D2H_VIEWER_CACHE_TTL_S` | `60` | Live viewer cache per (report, model, visual, identity, parameters, cross-filters). |
| `D2H_VIEWER_CACHE_MAX` | `1000` | Entries in that cache. |
| `D2H_ECHARTS_URL` | jsDelivr, ECharts 6.1.0 | Where the viewer loads ECharts from (SRI-checked; self-host the same file). |

## Sign-in (ADR 0010)

| Variable | Default | Purpose |
|---|---|---|
| `D2H_SESSION_SECRET` | random per process | **Secret.** Signs the session cookie; ≥ 32 characters. Required in production. |
| `D2H_AUTH_FILE` | `config/auth.yaml` | Providers (see `config/auth.example.yaml`). Absent = local users only. |
| `D2H_USERS_FILE` | `config/users.yaml` | Local users (scrypt hashes): `python -m data2html.auth add-user`. |
| `D2H_PUBLIC_URL` | — | Public origin behind a proxy, e.g. `https://bi.example.com` (OIDC redirect, CSRF check). |
| `D2H_OIDC_CLIENT_SECRET` | — | **Secret.** Entra ID client secret; the name is set by `client_secret_env` in `auth.yaml`. |
| `D2H_DEV_IDENTITIES` | — | `1` enables development identities at `/login` (localhost only). **Never in production.** |
| `D2H_DEV_IDENTITIES_FILE` | `config/dev_identities.yaml` | Those identities. |

## AI and the MCP server (ADR 0014)

| Variable | Default | Purpose |
|---|---|---|
| `D2H_AI_FILE` | `config/ai.yaml` | Exposure per source for the AI: `none`, `metadata` (default) or `results`, plus `max_rows`. See `config/ai.example.yaml`. Absent = `metadata` everywhere. |

The MCP process (`python -m data2html.mcp`, started by Claude Desktop) reads its own environment:

| Variable | Default | Purpose |
|---|---|---|
| `D2H_TOKEN` | — | **Secret.** Personal access token, created at `/tokens` (or `python -m data2html.auth token create <local user>`). Expires in ≤ 90 days; revocable. |
| `D2H_URL` | `http://127.0.0.1:8000` | The data2html backend the MCP server calls. |

## Sources

The variable names below are examples: each source names its own in `config/sources.yaml`.

| Variable | Used by | Purpose |
|---|---|---|
| `PG_DEV_PASSWORD` | `postgres_dev` (`password_env`) | **Secret.** Password of the SELECT-only Postgres user. |
| `MYSQL_DEV_PASSWORD` | `mysql_dev` (`password_env`) | **Secret.** Password of the SELECT-only MySQL user. |
| `AWS_*`, `AWS_PROFILE`, instance/task role | DynamoDB ingest | boto3's standard credential chain (ADR 0012). Never in YAML. |
| `TD_HOST`, `TD_USER`, `TD_PASSWORD` | Teradata (Phase 7) | Trusted-session service account. |
| `ANTHROPIC_API_KEY`, `AWS_REGION` | AI (Phase 9) | Named in `config/ai.yaml`. |

## Development only

| Variable | Default | Purpose |
|---|---|---|
| `MYSQL_DEV_ROOT_PASSWORD` | `d2h-root` | Root password of the docker-compose MySQL. |
| `D2H_TEST_PG_HOST` / `D2H_TEST_PG_PORT` | `localhost` / `5432` | Postgres for the integration tests. |
| `D2H_TEST_MYSQL_HOST` / `D2H_TEST_MYSQL_PORT` | `127.0.0.1` / `3306` | MySQL for the integration tests. |
