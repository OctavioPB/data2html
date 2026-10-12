# data2html

EDA, consulta SQL y visualización con reportes HTML servidos en vivo y seguridad por fila.
Sucesor de `pbix2html`: de los datos al HTML sin pasar por Power BI.

Pensado para desarrollarse con Claude Code: empieza por `CLAUDE.md` y `PLAN.md`, y usa `/fase`.

```bash
cp .env.example .env
docker compose up -d postgres            # datos de ejemplo (50k ventas)
cd backend && pip install -e ".[dev]"
pytest -q                                # contrato + compatibilidad + API
uvicorn data2html.api.main:app --reload  # http://localhost:8000/docs
```

## Estructura
```
CLAUDE.md, PLAN.md         gobierno del proyecto
.claude/skills/            report-spec, sqlgen-dialects, data-sources, security-rls,
                           eda-profiling, html-renderer
.claude/commands/          /fase, /nueva-fuente, /nuevo-visual, /revisar-seguridad
docs/ARCHITECTURE.md       componentes, flujo de una consulta, identidad
docs/decisions/            ADRs 0001–0006
backend/src/data2html/     spec (contrato) · sources · sqlgen · semantic · profiling ·
                           render · auth · api · ai · importers/pbix
examples/                  modelo semántico y reporte de referencia
config/                    fuentes, IA y tema (ejemplos, sin secretos)
studio/                    frontend React (Fase 0)
```
