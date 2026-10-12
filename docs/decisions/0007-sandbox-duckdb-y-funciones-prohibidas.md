# ADR 0007 — Sandbox de DuckDB + lista de funciones prohibidas; una conexión por fuente remota

**Estado:** propuesta · 2026-10-11

## Contexto
Toda consulta corre en un DuckDB con `allowed_directories`, `enable_external_access=false` y
`lock_configuration=true`. Al integrar Postgres se comprobó (DuckDB 1.5.6) que eso **no basta**:
con la configuración cerrada, `postgres_scan('host=…')`, `postgres_query` y `postgres_execute` siguen
disponibles, y `COPY … TO` escribe dentro de un directorio permitido. Además, `ATTACH` queda bloqueado
tras el cierre, así que una fuente remota tiene que adjuntarse antes.

## Decisión
1. **Dos capas para SQL.** `sqlgen/validate.ensure_single_select` corre dentro de `execute()` de cada
   fuente: un único `SELECT`, sin funciones de tabla salvo `range`/`generate_series`/`unnest`, y sin
   funciones `postgres_*`, `mysql_*`, `sqlite_*`, `read_*`, `parquet_*`, `duckdb_*`, `pragma_*`, `glob`,
   `query`, `query_table`, `getenv`, `current_setting`, `which_secret`, `load_extension`. El sandbox de
   DuckDB queda como segunda capa, no como la única.
2. **Una conexión DuckDB de larga vida por fuente remota**: `LOAD` → secreto temporal con la
   contraseña del entorno → `ATTACH … READ_ONLY` → cierre del sandbox. Cada consulta usa su `cursor()`.
3. Las fuentes que no responden no tumban la app: el catálogo las marca con `status="error"`, la API
   responde 503 con un mensaje genérico y se reintenta tras 30 s.

## Consecuencias
- Una función nueva de DuckDB que lea archivos o abra conexiones exige revisar la lista (test en
  `tests/test_sqlgen_validate.py`). La Fase 4 (editor SQL) hereda esta validación tal cual.
- El catálogo de Postgres queda en la caché de DuckDB; los cambios de esquema necesitarán un
  "refrescar" explícito (pendiente).
- El pool de conexiones y los límites de concurrencia por fuente siguen en la Fase 7.
