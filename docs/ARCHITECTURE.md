# Arquitectura

## Componentes

```
studio/ (React, autor)            visor /r/<id> (HTML, lectores)
        │  REST + Arrow IPC              │  JSON por visual
        ▼                                ▼
backend/src/data2html/
  api/        FastAPI: rutas del studio y del visor, auth
  spec/       CONTRATO: Report, Visual, SemanticModel, compat, JSON Schema
  semantic/   carga y validación cruzada de modelos semánticos
  sqlgen/     Visual + SemanticModel → SQL DuckDB → SQLGlot(dialecto)
  sources/    DataSource: csv, postgres, mysql, teradata, dynamodb_export
  profiling/  EDA (SUMMARIZE, histogramas, correlaciones, muestreo)
  render/     Jinja2 + ECharts → HTML del reporte (selector de mark incluido)
  auth/       proveedores: local, oidc → Identity
  ai/         opcional: LLMProvider, herramientas, políticas de exposición
  importers/pbix/  extractor heredado de pbix2html
```

## Flujo de una consulta de visual

1. El visor pide `GET /api/r/{report}/visuals/{visual}?params`.
2. `auth` resuelve la `Identity` del lector (nunca desde parámetros).
3. Se carga el `Visual` del `report-spec` y el `SemanticModel` que referencia.
4. `sqlgen` construye SQL en dialecto DuckDB con parámetros; SQLGlot lo transpila al de la fuente.
5. La fuente ejecuta con la identidad (Teradata: `PROXYUSER`; otras: filtro RLS del modelo).
6. Resultado como Arrow → JSON compacto (columnas + filas) al navegador.
7. Caché por `hash(spec, identidad, parámetros)` con TTL por fuente.

## Modos de ejecución

| Modo | Dónde corre el SQL | Fuentes |
|---|---|---|
| Import | DuckDB local sobre Parquet | CSV, DynamoDB (export), Postgres/MySQL opcional |
| DirectQuery | En la fuente | Teradata, Postgres, MySQL |

Postgres/MySQL vía extensiones de DuckDB: los filtros se empujan, las agregaciones no siempre.
Para tablas grandes, `sqlgen` emite la consulta completa en el dialecto de la fuente
(`postgres_query`, `mysql_query` o conexión nativa).

## Identidad y roles

- **Autor:** un único usuario con acceso al studio (`role=author`).
- **Lector:** cualquier identidad autenticada con acceso al reporte publicado.
- `auth/` expone `Identity(user_id, email, groups, provider)`. Proveedores: `local` (desarrollo y
  uso personal) y `oidc` (SSO corporativo). Ambos pueden estar activos a la vez.
- Para Teradata, solo identidades `oidc` mapean a `PROXYUSER`; una identidad local no obtiene
  datos de Teradata en el visor salvo mapeo explícito configurado por el autor.

## Red y hosting (decisión abierta)

El visor en vivo consulta Teradata en cada interacción: necesita conectividad directa y de baja
latencia. Si Teradata está on-prem, el visor probablemente viva en la red corporativa. Todo se
empaqueta en Docker y se configura por variables de entorno para no atarse a un proveedor.

## Por qué así

Ver `docs/decisions/`.
