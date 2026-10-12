"""Validation of a semantic model against the REAL catalog of its source.

The contract (`spec`) already guarantees the shape; this checks that the table and columns exist and
that every measure runs (with `WHERE false`: types are validated without reading data).
"""

from __future__ import annotations

import duckdb
from sqlglot import exp

from data2html.i18n import tr
from data2html.sources.base import DataSource, TableInfo
from data2html.sources.errors import QueryInterrupted, SourceError, SourceUnavailable
from data2html.spec import SemanticModel
from data2html.spec.expr import parse_expression
from data2html.sqlgen.validate import UnsafeSQL
from data2html.sqlgen.visual import measure_expr, table_expr


def check_model(model: SemanticModel, src: DataSource, *, run_measures: bool = True,
                timeout_s: int = 30) -> list[str]:
    """Errors, one per problem. Empty list = the model works against the source."""
    try:
        info: TableInfo = src.table_info(model.table)
    except SourceError:
        return [tr("table '{table}' does not exist in source '{source}'",
                   table=model.table, source=model.source)]
    except SourceUnavailable as e:
        return [tr("could not validate against the source: {error}", error=e)]

    columns = {c.name for c in info.columns}
    errors: list[str] = []
    for name, dim in model.dimensions.items():
        if dim.column not in columns:
            errors.append(tr("dimension '{name}': column '{column}' does not exist in {table}",
                             name=name, column=dim.column, table=model.table))
    if model.rls is not None and model.rls.column not in columns:
        errors.append(tr("rls: column '{column}' does not exist in {table}",
                         column=model.rls.column, table=model.table))
    runnable: list[str] = []
    for name, m in model.measures.items():
        _, used = parse_expression(m.sql, aggregate=True)
        missing = sorted(used - columns)
        if missing:
            errors.append(tr("measure '{name}': missing columns {columns}", name=name, columns=missing))
        else:
            runnable.append(name)

    if run_measures:
        relation = src.relation(model.table)
        for name in runnable:
            q = (exp.select(exp.alias_(measure_expr(model.measures[name].sql), "v", quoted=True))
                 .from_(table_expr(relation)).where(exp.false()))
            try:
                src.execute(q.sql("duckdb"), {}, identity=None, timeout_s=timeout_s)
            except (duckdb.Error, UnsafeSQL) as e:
                errors.append(tr("measure '{name}': {error}", name=name, error=str(e).splitlines()[0]))
            except (SourceUnavailable, QueryInterrupted) as e:
                errors.append(tr("measure '{name}': could not be tested ({error})", name=name, error=e))
    return errors
