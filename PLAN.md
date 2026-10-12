# PLAN — data2html

Estado: **Fases 0–5 completas (2026-10-11)**; siguiente: Fase 6. Marca `[x]` y agrega la fecha (AAAA-MM-DD) al cerrar cada punto.
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
- [x] Perfil por columna (`SUMMARIZE` + histograma/top-N) sobre muestra para fuentes remotas (2026-10-11)
- [x] Correlaciones entre numéricas, outliers por IQR, avisos (alta cardinalidad, posible ID, % nulos) (2026-10-11)
- [x] La UI indica cuándo el perfil viene de una muestra (2026-10-11)
- **Demo:** perfil completo de un CSV y de una tabla de Postgres.

## Fase 4 — Editor SQL
- [x] CodeMirror 6 con autocompletado desde el catálogo (2026-10-11)
- [x] Validación SQLGlot: un solo `SELECT`; timeout y cancelación (2026-10-11)
- [x] Historial y consultas guardadas; resultado → "Crear visual" (2026-10-11) — vista rápida sin guardar; publicar es Fase 5
- [x] Cancelar también el perfilado EDA desde el studio (2026-10-11)
- **Demo:** consulta → gráfico en dos clics.

## Fase 5 — Modelo semántico y constructor visual
- [x] Editor del modelo semántico (dimensiones, medidas con dueño y descripción) (2026-10-11)
- [x] `sqlgen`: visual + modelo → SQL DuckDB → SQLGlot al dialecto de la fuente (2026-10-11)
- [x] "Crear visual" desde el editor SQL → visual publicable: extraer la medida al modelo semántico (2026-10-11) — «Publicar como medida…»
- [x] Constructor drag-and-drop: repisas dimensión / medida / color / filtros (2026-10-11)
- [x] Selector de tipo de gráfico limitado por `compat.allowed_marks` (2026-10-11)
- [x] Render con ECharts (tabla incluida como `mark`) (2026-10-11)
- **Demo:** "venta neta por región" en barras → cambiar a tabla → a pastel.

## Fase 6 — Reportes y visor en vivo
- [ ] Editor de dashboards (react-grid-layout) que escribe `report-spec` (los visuales del constructor de la Fase 5 aún no se persisten: solo "Copiar YAML")
- [ ] Publicación: `content/reports/<id>.yaml` versionado (ADR 0008)
- [ ] Visor `/r/<id>`: HTML del renderer + endpoint por visual con identidad del lector
- [ ] Paleta de `config/theme.yaml`: el validador de la skill dataviz da WARN de daltonismo (naranja↔verde, ΔE 6.2); ajustarla o exigir etiquetas directas. El studio usa la paleta de referencia validada
- [ ] Cross-filtering; caché por hash (spec + identidad + parámetros)
- [ ] Prueba de seguridad: dos usuarios, mismo reporte, datos distintos
- **Demo:** un reporte publicado visto por dos identidades distintas.

## Fase 7 — Teradata, auth y despliegue
- [ ] `TeradataSource` con `teradatasql`, sesión de confianza + `PROXYUSER`
- [ ] Ejecución nativa en la fuente para agregaciones grandes: Teradata y Postgres (`postgres_query()` pospuesto de las Fases 1 y 5; ver ADR 0008)
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

## Pendientes sueltos (fuera de una fase concreta)
Anotados al cerrar las Fases 0–3 (2026-10-11). Mover a una fase cuando se aborden.

- [ ] Revisar y aceptar (o ajustar) el ADR 0007 — hoy en estado "propuesta"
- [ ] Commit de las Fases 0–5 en una rama (todo el trabajo sigue sin commit)
- [ ] Pestaña Esquema: mostrar y editar descripciones de columnas calculadas (se guardan, no se muestran)
- [ ] Limpiar subidas de CSV abandonadas en `data/uploads/` (las que no se confirmaron ni cancelaron)
- [ ] Mensajes de error de DuckDB pueden incluir rutas locales del servidor: limpiarlos antes de la Fase 7
- [ ] Postgres: botón "refrescar catálogo" (DuckDB cachea el esquema adjunto; tablas nuevas no aparecen)
- [ ] Subir a React 19 cuando Glide Data Grid publique una 6.x estable que lo declare (hoy fijo en 18.3)
- [ ] Verificación manual en navegador: scroll/orden/filtros del grid, diálogo de subida CSV, columnas
      calculadas, aviso de "muestra" del perfil (solo capturas headless y tests). El editor SQL, "Crear
      visual" y las cancelaciones sí se probaron con clics reales (Edge headless por CDP)
- [ ] Aviso `StarletteDeprecationWarning` de `httpx` en los tests: migrar cuando FastAPI lo resuelva
- [ ] Revisar y aceptar el ADR 0008 (contenido versionado en `content/`, RLS en vista previa del autor) — "propuesta"
- [ ] Guardar un modelo desde el studio reescribe el YAML y pierde comentarios hechos a mano (ADR 0008)
- [ ] Dimensiones sobre columnas calculadas del explorador: hoy un modelo solo usa columnas físicas
- [ ] Moneda de `format: currency` fija en MXN en el studio: leerla de `config/theme.yaml`
- [ ] Editor SQL: el `ORDER BY` de la consulta del usuario no tiene desempate; si hay empates, paginar
      re-ejecutando puede repetir/omitir filas entre páginas (el explorador sí desempata)

## Bitácora de decisiones abiertas
| Tema | Estado | Nota |
|---|---|---|
| Hosting | Abierto | Debe tener red directa a Teradata para el visor en vivo |
| Nombre definitivo | Abierto | `data2html` es provisional |
