# data2html

EDA, SQL querying and visualization, with live-served HTML reports and row-level security.
Successor of `pbix2html`: from data to HTML without going through Power BI.

The studio and the server messages are available in English and Spanish (ES/EN selector in the top bar).

Designed to be developed with Claude Code: start with `CLAUDE.md` and `PLAN.md`, and use `/phase`.

```bash
cp .env.example .env
docker compose up -d postgres mysql      # sample data (50k sales in each)
cd backend && pip install -e ".[dev]"
pytest -q                                # contract + compatibility + API + security
D2H_DEV_IDENTITIES=1 uvicorn data2html.api.main:app --reload  # http://localhost:8000/docs
cd studio && npm install && npm run dev  # http://localhost:5173 → sign in as "autor"
```

The studio requires an author session (ADR 0010). In development, `D2H_DEV_IDENTITIES=1` offers fake
identities at `/login` (localhost only). For real users: `python -m data2html.auth add-user …` (local
passwords) and/or Microsoft Entra ID in `config/auth.yaml` (see `config/auth.example.yaml`).

## Live viewer (Phase 6)

Reports are built in the studio (*Reports*, or «Add to report…» in the visual builder); saving publishes
them to `content/reports/`. Readers open `/r/<id>` and each one only sees their own rows (RLS).
Try it with development identities (or any local/Entra ID user):

```bash
D2H_DEV_IDENTITIES=1 uvicorn data2html.api.main:app --reload
# http://localhost:8000/r/ventas_regionales → sign in as "norte", then as "direccion"
```

## Layout
```
CLAUDE.md, PLAN.md         project governance
.claude/skills/            report-spec, sqlgen-dialects, data-sources, security-rls,
                           eda-profiling, html-renderer
.claude/commands/          /phase, /new-source, /new-visual, /review-security
docs/ARCHITECTURE.md       components, how a query flows, identity
docs/decisions/            ADRs 0001–0012
backend/src/data2html/     spec (contract) · sources · ingest · sqlgen · semantic · profiling ·
                           reports · render · auth · api · ai · importers/pbix · i18n + locales
examples/                  reference semantic model and report
content/                   versioned semantic models and published reports
config/                    sources, AI and theme (examples, no secrets)
studio/                    React frontend
```
