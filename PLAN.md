# PLAN — data2html

Estado: **Fases 0, 1 y 2 completas (2026-10-11)**; siguiente: Fase 3. Marca `[x]` y agrega la fecha (AAAA-MM-DD) al cerrar cada punto.
Criterio de cierre de fase: tests verdes, demo manual descrita en la fase, `PLAN.md` actualizado.

## Fase 0 — Esqueleto y contrato
- [x] Contrato `report-spec` y modelo semántico en Pydantic (`backend/src/data2html/spec/`)
- [x] Reglas de compatibilidad de tipos de gráfico (`spec/compat.py`) + tests
- [x] Exportar JSON Schema a `studio/src/generated/spec.schema.json` (`python -m data2html.spec.export`) (2026-10-11)
- [x] FastAPI mínimo: `/health`, `/api/catalog` vacío; OpenAPI → tipos TS (`npm run gen:api`) (2026-10-11)
- [x] Studio con Vite + React + TS + TanStack Query + Zustand, layout base (sidebar de fuentes) (2026-10-11)
- [x] CI: ruff, mypy, pytest, `npm run build` (2026-10-11)
- **Demo:** `pytest` verde; el studio muestra "API OK".

## Fase 1 — Fuentes: CSV y Postgres
- [x] Interfaz `DataSource` (catálogo, execute → Arrow, cancel, dialecto) (2026-10-11)
- [x] CSV: subida, inferencia de tipos con revisión del usuario, conversión a Parquet (2026-10-11)
- [x] Postgres vía `ATTACH ... (TYPE postgres, READ_ONLY)` de DuckDB (2026-10-11); `postgres_query()` pasa a la Fase 5
- [x] Catálogo con descripciones editables de tablas y columnas (2026-10-11)
- [x] Registro de conexiones; credenciales solo desde env (2026-10-11)
- **Demo:** subir un CSV y ver su catálogo junto al de Postgres.

## Fase 2 — Explorador tipo Excel
- [x] Grid virtualizado (Glide Data Grid) con paginación del lado del servidor (2026-10-11)
- [x] Sort/filtro/búsqueda → SQL (`ORDER BY`, `WHERE`, `LIMIT/OFFSET`) (2026-10-11)
- [x] Columnas calculadas como expresiones SQL (no fórmulas de celda) (2026-10-11)
- **Demo:** explorar 5M filas sin que el navegador se congele.

## Fase 3 — Perfilado EDA
- [ ] Perfil por columna (`SUMMARIZE` + histograma/top-N) sobre muestra para fuentes remotas
- [ ] Correlaciones entre numéricas, outliers por IQR, avisos (alta cardinalidad, posible ID, % nulos)
- [ ] La UI indica cuándo el perfil viene de una muestra
- **Demo:** perfil completo de un CSV y de una tabla de Postgres.

## Fase 4 — Editor SQL
- [ ] CodeMirror 6 con autocompletado desde el catálogo
- [ ] Validación SQLGlot: un solo `SELECT`; timeout y cancelación
- [ ] Historial y consultas guardadas; resultado → "Crear visual"
- **Demo:** consulta → gráfico en dos clics.

## Fase 5 — Modelo semántico y constructor visual
- [ ] Editor del modelo semántico (dimensiones, medidas con dueño y descripción)
- [ ] `sqlgen`: visual + modelo → SQL DuckDB → SQLGlot al dialecto de la fuente
- [ ] Agregaciones grandes en Postgres con `postgres_query()` (pospuesto de la Fase 1)
- [ ] Constructor drag-and-drop: repisas dimensión / medida / color / filtros
- [ ] Selector de tipo de gráfico limitado por `compat.allowed_marks`
- [ ] Render con ECharts (tabla incluida como `mark`)
- **Demo:** "venta neta por región" en barras → cambiar a tabla → a pastel.

## Fase 6 — Reportes y visor en vivo
- [ ] Editor de dashboards (react-grid-layout) que escribe `report-spec`
- [ ] Publicación: `reports/<id>.yaml` versionado
- [ ] Visor `/r/<id>`: HTML del renderer + endpoint por visual con identidad del lector
- [ ] Cross-filtering; caché por hash (spec + identidad + parámetros)
- [ ] Prueba de seguridad: dos usuarios, mismo reporte, datos distintos
- **Demo:** un reporte publicado visto por dos identidades distintas.

## Fase 7 — Teradata, auth y despliegue
- [ ] `TeradataSource` con `teradatasql`, sesión de confianza + `PROXYUSER`
- [ ] Auth: interfaz con proveedor local (dev) y OIDC (SSO corporativo)
- [ ] Pool de conexiones y límite de consultas concurrentes por fuente
- [ ] Explorador sobre tablas remotas grandes: conteo estimado y paginación sin `OFFSET` profundo (hoy DuckDB lee la tabla completa para `count(*)` y para ordenar)
- [ ] Docker de producción; decidir hosting (ver nota de red en ARCHITECTURE.md)
- [ ] Importador pbix: `pbix2html` → `report-spec` + siembra del modelo semántico
- **Demo:** un reporte migrado de Power BI servido en vivo con RLS.

## Fase 8 — MySQL, DynamoDB y exportaciones
- [ ] `MySQLSource` vía extensión `mysql` de DuckDB
- [ ] DynamoDB: pipeline export-a-S3 → Parquet aplanado (programado, nunca `Scan` en vivo)
- [ ] Exportar visual a CSV/PNG

## Fase 9 — IA opcional
- [ ] Interruptores: global, por fuente (nivel de exposición), por usuario — verificados en backend
- [ ] `LLMProvider`: Claude API, Bedrock, OpenAI-compatible (Ollama/vLLM); modelos en `config/ai.yaml`
- [ ] Herramientas: `get_catalog`, `propose_visual`, `run_query`, `profile_column`
- [ ] Auditoría de llamadas, presupuesto de tokens, caché

## Bitácora de decisiones abiertas
| Tema | Estado | Nota |
|---|---|---|
| Hosting | Abierto | Debe tener red directa a Teradata para el visor en vivo |
| Nombre definitivo | Abierto | `data2html` es provisional |
