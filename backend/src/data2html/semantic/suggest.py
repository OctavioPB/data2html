"""Promote a SQL editor query to a measure (+ dimension) of the semantic model.

Only queries shaped like `SELECT [dim,] AGG(...) [AS name] FROM table [WHERE …] GROUP BY dim`:
one catalog table, no joins or CTEs, at most one dimension and a single aggregate. Anything else is
rejected with the reason; the WHERE is not carried over (a warning says it belongs in a visual filter).
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict
from sqlglot import exp

from data2html.i18n import tr
from data2html.spec import FieldType, SemanticModel
from data2html.spec.expr import ExpressionError, parse_expression
from data2html.sqlgen.validate import UnsafeSQL, ensure_single_select


class NotPromotable(ValueError):
    pass


class SuggestedDimension(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    column: str
    type: FieldType
    exists: bool  # already in the model


class Suggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str
    table: str
    model: str | None  # existing model for that source + table
    dimension: SuggestedDimension | None
    measure_name: str
    measure_sql: str
    measure_exists: bool
    warnings: list[str]


def _slug(text: str, fallback: str) -> str:
    s = re.sub(r"[^a-z0-9_]+", "_", text.lower()).strip("_")
    if not s or not s[0].isalpha():
        s = f"{fallback}_{s}".strip("_")
    return s[:63]


def _tree(sql: str) -> exp.Expr:
    """A measure's tree: two measures with the same tree are the same, whatever their formatting."""
    return parse_expression(sql, aggregate=True)[0]


def _field_type(db_type: str) -> FieldType:
    t = db_type.upper()
    if t.startswith(("DATE", "TIMESTAMP")):
        return FieldType.temporal
    return FieldType.nominal


def suggest_from_sql(
    sql: str,
    *,
    source: str,
    tables: dict[str, dict[str, str]],
    models: list[SemanticModel],
) -> Suggestion:
    """`tables`: catalog table → {column: DuckDB type}."""
    try:
        q = ensure_single_select(sql)
    except UnsafeSQL as e:
        raise NotPromotable(str(e)) from e
    if not isinstance(q, exp.Select):
        raise NotPromotable(tr("only a simple SELECT (no UNION) can be promoted"))
    if q.find(exp.CTE) is not None or q.args.get("joins"):
        raise NotPromotable(tr("not with CTEs or joins: the measure must come from a single table"))
    from_ = q.args.get("from") or q.args.get("from_")
    table_node = from_.this if from_ is not None else None
    if not isinstance(table_node, exp.Table) or not isinstance(table_node.this, exp.Identifier):
        raise NotPromotable(tr("the FROM must be a catalog table"))
    key = ".".join(p for p in (table_node.db, table_node.name) if p).lower()
    table = next((t for t in tables if t.lower() == key), None)
    if table is None:
        raise NotPromotable(tr("table '{table}' is not in the catalog of '{source}'",
                               table=key, source=source))
    columns = tables[table]

    dims = [e for e in q.expressions if isinstance(e.unalias(), exp.Column)]
    aggs = [e for e in q.expressions if e.find(exp.AggFunc) is not None]
    others = [e for e in q.expressions if e not in dims and e not in aggs]
    if others:
        raise NotPromotable(tr("column that is neither a dimension nor an aggregate: {expr}",
                               expr=others[0].sql("duckdb")))
    if len(aggs) != 1:
        raise NotPromotable(tr("there must be exactly one aggregate (the measure)"))
    if len(dims) > 1:
        raise NotPromotable(tr("at most one dimension (group by a single column)"))

    agg = aggs[0]
    measure_sql = agg.unalias().sql("duckdb")
    try:
        _, used = parse_expression(measure_sql, aggregate=True)
    except ExpressionError as e:
        raise NotPromotable(tr("the measure is not valid: {error}", error=e)) from e
    missing = sorted(used - set(columns))
    if missing:
        raise NotPromotable(tr("missing columns in {table}: {columns}", table=table, columns=missing))

    model = next((m for m in models if m.source == source and m.table == table), None)
    measure_name = _slug(agg.alias, "measure") if agg.alias else "measure"
    measure_exists = False
    if model is not None:
        target = _tree(measure_sql)
        same = next((n for n, m in model.measures.items() if _tree(m.sql) == target), None)
        if same is not None:
            measure_name, measure_exists = same, True

    dimension = None
    if dims:
        col = dims[0].unalias()
        assert isinstance(col, exp.Column)
        if col.name not in columns:
            raise NotPromotable(tr("column '{column}' is not in {table}", column=col.name, table=table))
        dims_of_model = model.dimensions.items() if model else []
        existing = next((n for n, d in dims_of_model if d.column == col.name), None)
        dimension = SuggestedDimension(
            name=existing or _slug(dims[0].alias or col.name, "dim"),
            column=col.name,
            type=model.dimensions[existing].type if model and existing else _field_type(columns[col.name]),
            exists=existing is not None,
        )

    warnings = []
    if q.args.get("where") is not None:
        warnings.append(tr("the WHERE is not carried into the measure: add it as a filter in the builder"))
    if q.args.get("having") is not None:
        warnings.append(tr("the HAVING is not carried over"))
    return Suggestion(source=source, table=table, model=model.name if model else None, dimension=dimension,
                      measure_name=measure_name, measure_sql=measure_sql, measure_exists=measure_exists,
                      warnings=warnings)
