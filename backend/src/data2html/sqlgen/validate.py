"""Free-form SQL validation: only a single SELECT ever runs (CLAUDE.md, hard rules).

DuckDB's sandbox is not enough: with the configuration locked, functions such as
`postgres_scan('host=…')` or `postgres_execute` remain available. So functions that read files, open
connections or expose configuration are rejected too, as is any table function outside a short list.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from data2html.i18n import tr

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
        raise UnsafeSQL(tr("invalid SQL: {error}", error=e)) from e
    if len(statements) != 1:
        raise UnsafeSQL(tr("exactly one statement is expected"))
    stmt = statements[0]
    if not isinstance(stmt, exp.Query):
        raise UnsafeSQL(tr("only SELECT is allowed, not {kind}", kind=stmt.key.upper()))

    for node in stmt.walk():
        if isinstance(node, exp.Table) and isinstance(node.this, exp.Func):
            name = _func_name(node.this)
            if name not in _TABLE_FUNCS_OK:
                raise UnsafeSQL(tr("table function not allowed: {name}", name=name))
        if isinstance(node, exp.Func):
            name = _func_name(node)
            if name in _DENIED or name.startswith(_DENIED_PREFIXES):
                raise UnsafeSQL(tr("function not allowed: {name}", name=name))
    return stmt
