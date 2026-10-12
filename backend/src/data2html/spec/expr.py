"""Expresiones SQL dentro del contrato: medidas del modelo semántico y columnas calculadas.

Una sola expresión en dialecto DuckDB, sin subconsultas, ventanas, tablas, parámetros ni funciones que
SQLGlot no reconozca (las que leen archivos o abren conexiones caen ahí; ver ADR 0007). Las medidas
además deben agregar, y toda columna debe quedar dentro de un agregado.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

_FORBIDDEN: tuple[type[exp.Expr], ...] = (
    exp.Query, exp.Subquery, exp.Window, exp.Table, exp.Placeholder, exp.Parameter,
)


class ExpressionError(ValueError):
    pass


def _inside_aggregate(node: exp.Expr) -> bool:
    parent = node.parent
    while parent is not None:
        if isinstance(parent, exp.AggFunc | exp.Filter):  # FILTER (WHERE …) es parte del agregado
            return True
        parent = parent.parent
    return False


def parse_expression(sql: str, *, aggregate: bool) -> tuple[exp.Expr, set[str]]:
    """Valida la expresión y devuelve (árbol, columnas referenciadas). `ExpressionError` si no vale."""
    if ";" in sql:
        raise ExpressionError("una expresión, sin ';'")
    try:
        tree = sqlglot.parse_one(sql, read="duckdb")
    except ParseError as e:
        raise ExpressionError(f"expresión inválida: {e.errors[0]['description'] if e.errors else e}") from e
    if tree is None:
        raise ExpressionError("expresión vacía")

    if aggregate and not any(isinstance(n, exp.AggFunc) for n in tree.walk()):
        raise ExpressionError("una medida debe agregar (SUM, COUNT, AVG, MIN, MAX…)")

    columns: set[str] = set()
    for node in tree.walk():
        if isinstance(node, exp.Anonymous):
            raise ExpressionError(f"función no permitida: {node.name}")
        if isinstance(node, _FORBIDDEN):
            raise ExpressionError(f"no se permite {node.key.upper()} en una expresión")
        if isinstance(node, exp.AggFunc) and not aggregate:
            raise ExpressionError(f"no se permite {node.key.upper()}: la columna calculada es por fila")
        if isinstance(node, exp.Star) and not (aggregate and isinstance(node.parent, exp.Count)):
            raise ExpressionError("'*' solo se permite en COUNT(*)")
        if isinstance(node, exp.Column):
            if node.table:
                raise ExpressionError(f"usa el nombre de columna sin prefijo: {node.sql('duckdb')}")
            if aggregate and not _inside_aggregate(node):
                raise ExpressionError(f"la columna '{node.name}' está fuera de un agregado")
            columns.add(node.name)
    return tree, columns
