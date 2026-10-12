# data2html

EDA, SQL querying and visualization, with live-served HTML reports and row-level security.
Successor of `pbix2html`: from data to HTML without going through Power BI.

The studio and the server messages are available in English and Spanish (ES/EN selector in the top bar).

Designed to be developed with Claude Code: start with `CLAUDE.md` and `PLAN.md`, and use `/phase`.

```bash
cp .env.example .env
docker compose up -d postgres            # sample data (50k sales)
cd backend && pip install -e ".[dev]"
pytest -q                                # contract + compatibility + API
uvicorn data2html.api.main:app --reload  # http://localhost:8000/docs
cd studio && npm install && npm run dev  # http://localhost:5173
```

## Layout
```
CLAUDE.md, PLAN.md         project governance
.claude/skills/            report-spec, sqlgen-dialects, data-sources, security-rls,
                           eda-profiling, html-renderer
.claude/commands/          /phase, /new-source, /new-visual, /review-security
docs/ARCHITECTURE.md       components, how a query flows, identity
docs/decisions/            ADRs 0001–0008
backend/src/data2html/     spec (contract) · sources · sqlgen · semantic · profiling ·
                           render · auth · api · ai · importers/pbix · i18n + locales
examples/                  reference semantic model and report
content/                   versioned semantic models (and, from Phase 6, reports)
config/                    sources, AI and theme (examples, no secrets)
studio/                    React frontend
```
