"""Visual + modelo semántico → SQL DuckDB parametrizado (skill sqlgen-dialects).

- La medida sale del modelo (ADR 0004); el visual solo la nombra.
- `GROUP BY` dimensión (+ color), con `date_trunc` si hay `time_grain`. `ORDER BY` la dimensión si es
  temporal/ordinal; si no, la medida descendente. `LIMIT` 1000 por defecto.
- Valores de filtros y de RLS van como parámetros (`$p0`…), nunca en el texto del SQL.
- RLS: si el modelo declara `rls`, hace falta la identidad del lector. Sin identidad solo se genera con
  `author_preview=True` explícito (studio monousuario); nunca por omisión.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlglot import exp

from data2html.sources.base import Identity
from data2html.spec.expr import parse_expression
from data2html.spec.models import FieldType, Filter, FilterOp, SemanticModel, Visual

DEFAULT_LIMIT = 1000
_RLS_CLAIMS = {"groups", "email", "user_id"}


class VisualQueryError(ValueError):
    pass


@dataclass(frozen=True)
class VisualQuery:
    sql: str
    params: dict[str, object]
    dimension: str | None  # nombres de las columnas del resultado
    color: str | None
    measure: str


def _ident(name: str) -> exp.Identifier:
    return exp.to_identifier(name, quoted=True)


def _col(name: str) -> exp.Column:
    return exp.column(_ident(name))


def table_expr(relation: tuple[str, ...]) -> exp.Table:
    if not 1 <= len(relation) <= 3:
        raise VisualQueryError(f"relación inválida: {relation!r}")
    *qual, name = (_ident(p) for p in relation)
    catalog, db = ([None, None] + qual)[-2:]
    return exp.Table(this=name, db=db, catalog=catalog)


class _Params:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    def add(self, value: object, cast_to: str | None) -> exp.Expr:
        name = f"p{len(self.values)}"
        self.values[name] = value
        ph = exp.Placeholder(this=name)
        return exp.cast(ph, exp.DataType.build(cast_to, dialect="duckdb")) if cast_to else ph


def measure_expr(sql: str) -> exp.Expr:
    tree, _ = parse_expression(sql, aggregate=True)
    for c in tree.find_all(exp.Column):  # citar: el modelo ya validó los nombres, igual se citan
        c.set("this", _ident(c.name))
    return tree


def _filter(
    f: Filter, column: str, cast_to: str | None, report_params: dict[str, object], p: _Params
) -> exp.Expr:
    if f.param is not None:
        if f.param not in report_params:
            raise VisualQueryError(f"falta el valor del parámetro '{f.param}'")
        raw = report_params[f.param]
    else:
        raw = f.value
    values = list(raw) if isinstance(raw, list | tuple) else [raw]
    c = _col(column)
    if f.op is FilterOp.in_:
        return exp.In(this=c, expressions=[p.add(v, cast_to) for v in values])
    if f.op is FilterOp.between:
        if len(values) != 2:
            raise VisualQueryError("'between' espera [desde, hasta]")
        return exp.Between(this=c, low=p.add(values[0], cast_to), high=p.add(values[1], cast_to))
    if len(values) != 1:
        raise VisualQueryError(f"'{f.op.value}' espera un solo valor")
    cmp: dict[FilterOp, type[exp.Binary]] = {
        FilterOp.eq: exp.EQ, FilterOp.neq: exp.NEQ, FilterOp.gte: exp.GTE, FilterOp.lte: exp.LTE,
    }
    return cmp[f.op](this=c, expression=p.add(values[0], cast_to))


def _rls(
    model: SemanticModel, identity: Identity | None, author_preview: bool, p: _Params
) -> exp.Expr | None:
    if model.rls is None:
        return None
    if identity is None:
        if author_preview:
            return None
        raise VisualQueryError("el modelo tiene RLS: se necesita la identidad del lector")
    claim = model.rls.claim
    if claim not in _RLS_CLAIMS:
        raise VisualQueryError(f"claim de RLS desconocido: {claim!r}")
    raw = getattr(identity, claim)
    values = list(raw) if isinstance(raw, tuple | list) else [raw]
    if not values:
        return exp.false()  # sin claims, sin filas
    return exp.In(this=_col(model.rls.column), expressions=[p.add(str(v), None) for v in values])


def build_visual_query(
    visual: Visual,
    model: SemanticModel,
    relation: tuple[str, ...],
    *,
    column_types: dict[str, str],
    report_params: dict[str, object] | None = None,
    identity: Identity | None,
    author_preview: bool = False,
    limit: int = DEFAULT_LIMIT,
) -> VisualQuery:
    """`column_types`: columna física → tipo DuckDB (del catálogo), para tipar los parámetros."""
    if visual.measure not in model.measures:
        raise VisualQueryError(f"medida desconocida: {visual.measure!r}")
    p = _Params()
    select: list[exp.Expr] = []
    group: list[exp.Expr] = []
    order: list[exp.Ordered] = []

    dim_name = visual.dimension
    if dim_name is not None:
        dim = model.dimensions.get(dim_name)
        if dim is None:
            raise VisualQueryError(f"dimensión desconocida: {dim_name!r}")
        key: exp.Expr = _col(dim.column)
        if visual.time_grain is not None:
            if dim.type is not FieldType.temporal:
                raise VisualQueryError("time_grain solo aplica a una dimensión temporal")
            trunc = exp.func("date_trunc", exp.Literal.string(visual.time_grain.value), _col(dim.column))
            key = exp.cast(trunc, exp.DataType.build("DATE"))
        select.append(exp.alias_(key, dim_name, quoted=True))
        group.append(key.copy())
        if dim.type in (FieldType.temporal, FieldType.ordinal):
            order.append(exp.Ordered(this=_col(dim_name)))

    color_name = visual.color
    if color_name is not None:
        color = model.dimensions.get(color_name)
        if color is None:
            raise VisualQueryError(f"dimensión de color desconocida: {color_name!r}")
        select.append(exp.alias_(_col(color.column), color_name, quoted=True))
        group.append(_col(color.column))

    measure = model.measures[visual.measure]
    select.append(exp.alias_(measure_expr(measure.sql), visual.measure, quoted=True))
    if not order and dim_name is not None:
        order.append(exp.Ordered(this=_col(visual.measure), desc=True))
    if color_name is not None:
        order.append(exp.Ordered(this=_col(color_name)))

    q = exp.select(*select).from_(table_expr(relation))
    conds: list[exp.Expr] = []
    for f in visual.filters:
        dim = model.dimensions.get(f.dimension)
        if dim is None:
            raise VisualQueryError(f"filtro sobre dimensión desconocida: {f.dimension!r}")
        conds.append(_filter(f, dim.column, column_types.get(dim.column), report_params or {}, p))
    rls = _rls(model, identity, author_preview, p)
    if rls is not None:
        conds.append(rls)
    if conds:
        q = q.where(exp.and_(*conds))
    if group:
        q = q.group_by(*group)
    if order:
        q = q.order_by(*order)
    q = q.limit(limit)
    return VisualQuery(sql=q.sql("duckdb"), params=p.values, dimension=dim_name, color=color_name,
                       measure=visual.measure)
