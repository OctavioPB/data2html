---
name: data-sources
description: Usar al implementar, configurar o depurar una fuente de datos (CSV, Postgres, MySQL, Teradata, DynamoDB) en backend/src/data2html/sources/, o al registrar conexiones y credenciales.
---

# Fuentes de datos

Interfaz: `sources/base.py::DataSource` (`id`, `dialect`, `catalog()`, `execute()`, `cancel()`).
Todas devuelven `pyarrow.Table`.

| Fuente | Implementación | Modo | Notas |
|---|---|---|---|
| CSV | DuckDB `read_csv` → Parquet | Import | revisión de tipos por el usuario antes de confirmar |
| Postgres | `ATTACH ... (TYPE postgres, READ_ONLY)` | DirectQuery/Import | agregaciones grandes: `postgres_query()` |
| MySQL | `ATTACH ... (TYPE mysql, READ_ONLY)` | DirectQuery/Import | idem con `mysql_query()` |
| Teradata | `teradatasql` | DirectQuery | `PROXYUSER` por query band; ver skill security-rls |
| DynamoDB | export nativo a S3 → `httpfs` → Parquet aplanado | Import programado | **nunca** `Scan` ni PartiQL sin clave en vivo |

## CSV: trampas de inferencia
Fechas ambiguas (`03/04/2026`), coma decimal, códigos con ceros a la izquierda convertidos a
entero, encabezados repetidos. Muestra los tipos inferidos y deja corregirlos; guarda la
decisión junto al Parquet (`<tabla>.schema.json`).

## Conexiones
- Registro en `config/sources.yaml`: id, tipo, host, base y **nombre** de la variable de entorno
  con el secreto. Nunca el secreto.
- Usuario de base de datos con permisos de solo `SELECT`.
- Pool por fuente con tamaño máximo y semáforo de consultas concurrentes.
- Perfilado sobre fuentes remotas: siempre con muestra (`TABLESAMPLE`, `SAMPLE`) e indícalo.

## Nueva fuente (checklist)
- [ ] Clase que cumple `DataSource` (`isinstance(x, DataSource)` en test).
- [ ] Test de catálogo y de `execute` contra un contenedor o un fake.
- [ ] Dialecto agregado a los snapshots de `sqlgen`.
- [ ] Revisión con `/revisar-seguridad`.
