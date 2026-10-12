"""Validación de SQL libre: solo se ejecuta un único SELECT (CLAUDE.md, reglas duras).

El sandbox de DuckDB no basta: con la configuración cerrada, funciones como `postgres_scan('host=…')`
o `postgres_execute` siguen disponibles. Por eso además se rechazan funciones que leen archivos,
abren conexiones o exponen la configuración, y cualquier función de tabla fuera de una lista corta.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

_DENIED_PREFIXES = (
    "postgres_", "mysql_", "sqlite_", "read_", "parquet_", "iceberg_", "delta_", "duckdb_", "pragma_",
)
_DENIED = {"glob", "query", "query_table", "getenv", "current_setting", "which_secret", "load_extension"}
_TABLE_FUNCS_OK = {"range", "generate_series", "unnest"}


class UnsafeSQL(ValueError):
    pass


def _func_name(node: exp.Func) -> str:
    return (node.name if isinstance(node, exp.Anonymous) else node.sql_name()).lower()


def ensure_single_select(sql: str, dialect: str = "duckdb") -> exp.Query:
    try:
        statements = [s for s in sqlglot.parse(sql, read=dialect) if s is not None]
    except ParseError as e:
        raise UnsafeSQL(f"SQL inválido: {e}") from e
    if len(statements) != 1:
        raise UnsafeSQL("se espera exactamente una sentencia")
    stmt = statements[0]
    if not isinstance(stmt, exp.Query):
        raise UnsafeSQL(f"solo se permite SELECT, no {stmt.key.upper()}")

    for node in stmt.walk():
        if isinstance(node, exp.Table) and isinstance(node.this, exp.Func):
            name = _func_name(node.this)
            if name not in _TABLE_FUNCS_OK:
                raise UnsafeSQL(f"función de tabla no permitida: {name}")
        if isinstance(node, exp.Func):
            name = _func_name(node)
            if name in _DENIED or name.startswith(_DENIED_PREFIXES):
                raise UnsafeSQL(f"función no permitida: {name}")
    return stmt
