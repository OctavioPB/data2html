---
name: sqlgen-dialects
description: Usar al escribir o depurar la generación de SQL (backend/src/data2html/sqlgen/), al traducir entre DuckDB, Postgres, MySQL y Teradata con SQLGlot, o al validar SQL libre del editor.
---

# Generación de SQL

## Pipeline
`Visual + SemanticModel + params + Identity` → AST SQLGlot en dialecto `duckdb` →
`.sql(dialect=source.dialect)` → `DataSource.execute(sql, params, identity=...)`.

## Reglas
- Construye con el AST de SQLGlot (`exp.select(...)`), no con f-strings. Los valores de
  usuario y de parámetros van como placeholders, nunca interpolados.
- Columnas e identificadores salen del modelo semántico, que ya está validado; aun así,
  cítalos con `exp.to_identifier(..., quoted=True)`.
- `GROUP BY` por la dimensión (y color); `ORDER BY` por la dimensión si es temporal/ordinal,
  si no por la medida descendente. `LIMIT` por defecto 1000 filas para visuales.
- RLS: si el modelo tiene `rls` y la fuente no es Teradata, agrega `WHERE <col> IN (:claims)`
  desde `identity`. En Teradata el RLS lo aplica la sesión con `PROXYUSER`.

## Validación de SQL libre
```python
stmts = sqlglot.parse(sql, read=dialect)
if len(stmts) != 1 or not isinstance(stmts[0], exp.Select | exp.Union): rechazar
if any(stmts[0].find_all(exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Command)): rechazar
```

## Diferencias de dialecto a vigilar (con test snapshot cada una)
| DuckDB | Teradata | Nota |
|---|---|---|
| `LIMIT n` | `TOP n` / `SAMPLE n` | `SAMPLE` es aleatorio: no lo uses para paginar |
| `DATE_TRUNC('month', d)` | `TRUNC(d, 'MM')` | verifica el SQL que emite SQLGlot |
| `ILIKE` | `LIKE` con `UPPER()` | Teradata no tiene ILIKE |
| `OFFSET` | `QUALIFY ROW_NUMBER()` | paginación en Teradata |

Si SQLGlot traduce mal un caso, no lo parches con `replace` de strings: agrega una
transformación del AST en `sqlgen/dialect_fixes.py` con su test.
