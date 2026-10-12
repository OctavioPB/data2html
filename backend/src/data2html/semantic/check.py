"""Validación de un modelo semántico contra el catálogo REAL de su fuente.

El contrato (`spec`) ya garantiza la forma; aquí se comprueba que la tabla y las columnas existen y que
cada medida corre (con `WHERE false`: valida tipos sin leer datos).
"""

from __future__ import annotations

import duckdb
from sqlglot import exp

from data2html.sources.base import DataSource, TableInfo
from data2html.sources.errors import QueryInterrupted, SourceError, SourceUnavailable
from data2html.spec import SemanticModel
from data2html.spec.expr import parse_expression
from data2html.sqlgen.validate import UnsafeSQL
from data2html.sqlgen.visual import measure_expr, table_expr


def check_model(model: SemanticModel, src: DataSource, *, run_measures: bool = True,
                timeout_s: int = 30) -> list[str]:
    """Errores en español, uno por problema. Lista vacía = el modelo funciona contra la fuente."""
    try:
        info: TableInfo = src.table_info(model.table)
    except SourceError:
        return [f"la tabla '{model.table}' no existe en la fuente '{model.source}'"]
    except SourceUnavailable as e:
        return [f"no se pudo validar contra la fuente: {e}"]

    columns = {c.name for c in info.columns}
    errors: list[str] = []
    for name, dim in model.dimensions.items():
        if dim.column not in columns:
            errors.append(f"dimensión '{name}': la columna '{dim.column}' no existe en {model.table}")
    if model.rls is not None and model.rls.column not in columns:
        errors.append(f"rls: la columna '{model.rls.column}' no existe en {model.table}")
    runnable: list[str] = []
    for name, m in model.measures.items():
        _, used = parse_expression(m.sql, aggregate=True)
        missing = sorted(used - columns)
        if missing:
            errors.append(f"medida '{name}': columnas inexistentes {missing}")
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
                errors.append(f"medida '{name}': {str(e).splitlines()[0]}")
            except (SourceUnavailable, QueryInterrupted) as e:
                errors.append(f"medida '{name}': no se pudo probar ({e})")
    return errors
