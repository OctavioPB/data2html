# PLAN — data2html

Estado: **Fase 0 en curso**. Marca `[x]` y agrega la fecha (AAAA-MM-DD) al cerrar cada punto.
Criterio de cierre de fase: tests verdes, demo manual descrita en la fase, `PLAN.md` actualizado.

## Fase 0 — Esqueleto y contrato
- [x] Contrato `report-spec` y modelo semántico en Pydantic (`backend/src/data2html/spec/`)
- [x] Reglas de compatibilidad de tipos de gráfico (`spec/compat.py`) + tests
- [ ] Exportar JSON Schema a `studio/src/generated/spec.schema.json` (`python -m data2html.spec.export`)
- [ ] FastAPI mínimo: `/health`, `/api/catalog` vacío; OpenAPI → tipos TS (`npm run gen:api`)
- [ ] Studio con Vite + React + TS + TanStack Query + Zustand, layout base (sidebar de fuentes)
- [ ] CI: ruff, mypy, pytest, `npm run build`
- **Demo:** `pytest` verde; el studio muestra "API OK".

## Fase 1 — Fuentes: CSV y Postgres
- [ ] Interfaz `DataSource` (catálogo, execute → Arrow, cancel, dialecto)
- [ ] CSV: subida, inferencia de tipos con revisión del usuario, conversión a Parquet
- [ ] Postgres vía `ATTACH ... (TYPE postgres, READ_ONLY)` de DuckDB; `postgres_query()` para agregaciones grandes
- [ ] Catálogo con descripciones editables de tablas y columnas
- [ ] Registro de conexiones; credenciales solo desde env
- **Demo:** subir un CSV y ver su catálogo junto al de Postgres.

## Fase 2 — Explorador tipo Excel
- [ ] Grid virtualizado (Glide Data Grid) con paginación del lado del servidor
- [ ] Sort/filtro/búsqueda → SQL (`ORDER BY`, `WHERE`, `LIMIT/OFFSET`)
- [ ] Columnas calculadas como expresiones SQL (no fórmulas de celda)
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
