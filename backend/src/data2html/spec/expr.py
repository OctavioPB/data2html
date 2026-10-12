"""SQL expressions inside the contract: semantic-model measures and computed columns.

A single DuckDB-dialect expression with no subqueries, windows, tables, parameters or functions that
SQLGlot does not recognize (the ones that read files or open connections land there; see ADR 0007).
Measures must also aggregate, and every column must sit inside an aggregate.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from data2html.i18n import tr

_FORBIDDEN: tuple[type[exp.Expr], ...] = (
    exp.Query, exp.Subquery, exp.Window, exp.Table, exp.Placeholder, exp.Parameter,
)


class ExpressionError(ValueError):
    pass


def _inside_aggregate(node: exp.Expr) -> bool:
    parent = node.parent
    while parent is not None:
        if isinstance(parent, exp.AggFunc | exp.Filter):  # FILTER (WHERE …) is part of the aggregate
            return True
        parent = parent.parent
    return False


def parse_expression(sql: str, *, aggregate: bool) -> tuple[exp.Expr, set[str]]:
    """Validate the expression and return (tree, referenced columns). `ExpressionError` if invalid."""
    if ";" in sql:
        raise ExpressionError(tr("a single expression, without ';'"))
    try:
        tree = sqlglot.parse_one(sql, read="duckdb")
    except ParseError as e:
        detail = e.errors[0]["description"] if e.errors else e
        raise ExpressionError(tr("invalid expression: {detail}", detail=detail)) from e
    if tree is None:
        raise ExpressionError(tr("empty expression"))

    if aggregate and not any(isinstance(n, exp.AggFunc) for n in tree.walk()):
        raise ExpressionError(tr("a measure must aggregate (SUM, COUNT, AVG, MIN, MAX…)"))

    columns: set[str] = set()
    for node in tree.walk():
        if isinstance(node, exp.Anonymous):
            raise ExpressionError(tr("function not allowed: {name}", name=node.name))
        if isinstance(node, _FORBIDDEN):
            raise ExpressionError(tr("{kind} is not allowed in an expression", kind=node.key.upper()))
        if isinstance(node, exp.AggFunc) and not aggregate:
            raise ExpressionError(tr("{kind} is not allowed: a computed column is per row",
                                     kind=node.key.upper()))
        if isinstance(node, exp.Star) and not (aggregate and isinstance(node.parent, exp.Count)):
            raise ExpressionError(tr("'*' is only allowed in COUNT(*)"))
        if isinstance(node, exp.Column):
            if node.table:
                raise ExpressionError(tr("use the column name without a prefix: {column}",
                                         column=node.sql("duckdb")))
            if aggregate and not _inside_aggregate(node):
                raise ExpressionError(tr("column '{name}' is outside an aggregate", name=node.name))
            columns.add(node.name)
    return tree, columns
