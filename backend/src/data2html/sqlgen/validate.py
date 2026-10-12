"""Validación de SQL libre: solo se ejecuta un único SELECT (CLAUDE.md, reglas duras)."""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError


class UnsafeSQL(ValueError):
    pass


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
    return stmt
