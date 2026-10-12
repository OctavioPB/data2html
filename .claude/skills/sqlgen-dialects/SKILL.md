---
name: sqlgen-dialects
description: Use when writing or debugging SQL generation (backend/src/data2html/sqlgen/), when translating between DuckDB, Postgres, MySQL and Teradata with SQLGlot, or when validating the editor's free SQL.
---

# SQL generation

## Pipeline
`Visual + SemanticModel + params + Identity` → SQLGlot AST in the `duckdb` dialect →
`.sql(dialect=source.dialect)` → `DataSource.execute(sql, params, identity=...)`.

## Rules
- Build with the SQLGlot AST (`exp.select(...)`), not f-strings. User and parameter values go in
  as placeholders, never interpolated.
- Columns and identifiers come from the semantic model, which is already validated; even so,
  quote them with `exp.to_identifier(..., quoted=True)`.
- `GROUP BY` the dimension (and color); `ORDER BY` the dimension if temporal/ordinal, otherwise
  by the measure descending. Default `LIMIT` of 1000 rows for visuals.
- RLS: if the model has `rls` and the source is not Teradata, add `WHERE <col> IN (:claims)`
  from `identity`. In Teradata, RLS is applied by the session with `PROXYUSER`.

## Free SQL validation
```python
stmts = sqlglot.parse(sql, read=dialect)
if len(stmts) != 1 or not isinstance(stmts[0], exp.Select | exp.Union): reject
if any(stmts[0].find_all(exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Command)): reject
```

## Dialect differences to watch (each with a snapshot test)
| DuckDB | Teradata | Note |
|---|---|---|
| `LIMIT n` | `TOP n` / `SAMPLE n` | `SAMPLE` is random: do not use it to paginate |
| `DATE_TRUNC('month', d)` | `TRUNC(d, 'MM')` | check the SQL SQLGlot emits |
| `ILIKE` | `LIKE` with `UPPER()` | Teradata has no ILIKE |
| `OFFSET` | `QUALIFY ROW_NUMBER()` | pagination in Teradata |

If SQLGlot translates a case wrongly, do not patch it with string `replace`: add an AST
transformation in `sqlgen/dialect_fixes.py` with its test.
