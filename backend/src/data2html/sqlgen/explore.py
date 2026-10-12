"""Explorador tipo Excel: orden, filtros, búsqueda y columnas calculadas → un SELECT paginado.

Todo se arma con expresiones SQLGlot; los valores del usuario viajan como parámetros (`$p0`…) y los
nombres de columna se validan contra el catálogo. Las columnas calculadas son expresiones escalares
revisadas por `parse_computed` (sin subconsultas, agregados, ventanas ni funciones desconocidas).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Self

import sqlglot
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlglot import exp
from sqlglot.errors import ParseError

MAX_LIMIT = 1000
NAME_PATTERN = r"^[a-z_][a-z0-9_]{0,62}$"

Scalar = str | int | float | bool


class InvalidExplore(ValueError):
    pass


# ------------------------------------------------------------------ petición


class FilterOp(StrEnum):
    eq = "="
    ne = "!="
    lt = "<"
    le = "<="
    gt = ">"
    ge = ">="
    contains = "contains"
    starts_with = "starts_with"
    between = "between"
    in_ = "in"
    is_null = "is_null"
    not_null = "not_null"


_NO_VALUE = {FilterOp.is_null, FilterOp.not_null}
_TEXT_OPS = {FilterOp.contains, FilterOp.starts_with}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SortKey(_Strict):
    column: str
    desc: bool = False


class ColumnFilter(_Strict):
    column: str
    op: FilterOp
    value: Scalar | Annotated[list[Scalar], Field(max_length=500)] | None = None

    @model_validator(mode="after")
    def _value_matches_op(self) -> Self:
        v = self.value
        if self.op in _NO_VALUE:
            if v is not None:
                raise ValueError(f"{self.op.value} no lleva valor")
        elif self.op is FilterOp.between:
            if not (isinstance(v, list) and len(v) == 2):
                raise ValueError("between espera [desde, hasta]")
        elif self.op is FilterOp.in_:
            if not (isinstance(v, list) and v):
                raise ValueError("in espera una lista no vacía")
        elif v is None or isinstance(v, list):
            raise ValueError(f"{self.op.value} espera un solo valor")
        return self


class ExploreRequest(_Strict):
    sort: Annotated[list[SortKey], Field(max_length=5)] = []
    filters: Annotated[list[ColumnFilter], Field(max_length=20)] = []
    search: Annotated[str, Field(max_length=200)] = ""
    offset: Annotated[int, Field(ge=0)] = 0
    limit: Annotated[int, Field(ge=1, le=MAX_LIMIT)] = 200
    with_total: bool = True


class ComputedColumn(_Strict):
    name: Annotated[str, Field(pattern=NAME_PATTERN)]
    expr: Annotated[str, Field(min_length=1, max_length=2000)]
    type: str = ""  # tipo DuckDB resuelto al guardarla; vacío mientras se valida


# ------------------------------------------------------------------ columnas calculadas

_FORBIDDEN: tuple[type[exp.Expr], ...] = (
    exp.Query, exp.Subquery, exp.AggFunc, exp.Window, exp.Table, exp.Star,
    exp.Placeholder, exp.Parameter, exp.Anonymous,
)


def parse_computed(expr: str, columns: set[str]) -> exp.Expr:
    """Expresión escalar sobre columnas existentes, o `InvalidExplore` con el motivo."""
    try:
        tree = sqlglot.parse_one(expr, read="duckdb")
    except ParseError as e:
        raise InvalidExplore(f"expresión inválida: {e.errors[0]['description'] if e.errors else e}") from e
    for node in tree.walk():
        if isinstance(node, exp.Anonymous):
            raise InvalidExplore(f"función no permitida: {node.name}")
        if isinstance(node, _FORBIDDEN):
            raise InvalidExplore(f"no se permite {node.key.upper()} en una columna calculada")
        if isinstance(node, exp.Column):
            if node.table:
                raise InvalidExplore(f"usa el nombre de columna sin prefijo: {node.sql('duckdb')}")
            if node.name not in columns:
                raise InvalidExplore(f"columna desconocida: {node.name}")
    return tree


# ------------------------------------------------------------------ SQL


@dataclass(frozen=True)
class ExploreSQL:
    page: str
    count: str | None
    params: dict[str, object]


def _col(name: str) -> exp.Column:
    return exp.column(exp.to_identifier(name, quoted=True))


def _escape_like(v: str) -> str:
    return v.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class _Params:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    def add(self, value: object) -> exp.Placeholder:
        name = f"p{len(self.values)}"
        self.values[name] = value
        return exp.Placeholder(this=name)


def _typed(param: exp.Expr, type_: str) -> exp.Expr:
    # El parámetro llega como texto/número JSON: se castea al tipo de la columna (tipo del servidor).
    return exp.cast(param, exp.DataType.build(type_, dialect="duckdb")) if type_ else param


def _ilike(target: exp.Expr, pattern: exp.Expr) -> exp.Expr:
    text = exp.cast(target, exp.DataType.build("VARCHAR"))
    return exp.Escape(this=exp.ILike(this=text, expression=pattern), expression=exp.Literal.string("\\"))


def _filter(f: ColumnFilter, type_: str, p: _Params) -> exp.Expr:
    c = _col(f.column)
    if f.op is FilterOp.is_null:
        return exp.Is(this=c, expression=exp.Null())
    if f.op is FilterOp.not_null:
        return exp.Not(this=exp.Is(this=c, expression=exp.Null()))
    if f.op in _TEXT_OPS:
        v = _escape_like(str(f.value))
        return _ilike(c, p.add(f"%{v}%" if f.op is FilterOp.contains else f"{v}%"))
    if f.op is FilterOp.between:
        assert isinstance(f.value, list)
        lo, hi = (_typed(p.add(v), type_) for v in f.value)
        return exp.Between(this=c, low=lo, high=hi)
    if f.op is FilterOp.in_:
        assert isinstance(f.value, list)
        return exp.In(this=c, expressions=[_typed(p.add(v), type_) for v in f.value])
    cmp: dict[FilterOp, type[exp.Binary]] = {
        FilterOp.eq: exp.EQ, FilterOp.ne: exp.NEQ, FilterOp.lt: exp.LT,
        FilterOp.le: exp.LTE, FilterOp.gt: exp.GT, FilterOp.ge: exp.GTE,
    }
    return cmp[f.op](this=c, expression=_typed(p.add(f.value), type_))


def build_explore(
    table: str,
    columns: dict[str, str],
    computed: list[ComputedColumn],
    req: ExploreRequest,
) -> ExploreSQL:
    """`columns`: nombre → tipo DuckDB de la tabla (del catálogo). Devuelve SQL DuckDB parametrizado."""
    types = dict(columns)
    projections: list[exp.Expr] = [exp.Star()]
    for cc in computed:
        if cc.name in types:
            raise InvalidExplore(f"la columna calculada {cc.name!r} choca con una existente")
        projections.append(exp.alias_(parse_computed(cc.expr, set(columns)), cc.name, quoted=True))
        types[cc.name] = cc.type

    def known(name: str) -> str:
        if name not in types:
            raise InvalidExplore(f"columna desconocida: {name!r}")
        return types[name]

    p = _Params()
    conds = [_filter(f, known(f.column), p) for f in req.filters]
    if req.search:
        text_cols = [n for n, t in types.items() if t.upper().startswith("VARCHAR")]
        if text_cols:
            pattern = p.add(f"%{_escape_like(req.search)}%")
            conds.append(exp.or_(*(_ilike(_col(n), pattern) for n in text_cols)))
        else:
            conds.append(exp.false())

    base = exp.select(*projections).from_(exp.Table(this=exp.to_identifier(table, quoted=True)))
    filtered = exp.select("*").from_("_t").with_("_t", as_=base)
    if conds:
        filtered = filtered.where(exp.and_(*conds))

    page = filtered.copy()
    for s in req.sort:
        known(s.column)
    if req.sort:
        # El sort de DuckDB no es estable: sin desempate, las páginas repetirían u omitirían filas.
        # Sin `sort`, preserve_insertion_order (default) mantiene el orden del archivo.
        keys = [exp.Ordered(this=_col(s.column), desc=s.desc) for s in req.sort]
        sorted_cols = {s.column for s in req.sort}
        keys += [exp.Ordered(this=_col(n)) for n in columns if n not in sorted_cols]
        page = page.order_by(*keys)
    page = page.limit(req.limit).offset(req.offset)

    count = None
    if req.with_total:
        count = exp.select(exp.Count(this=exp.Star()).as_("n")).from_(filtered.subquery("_f")).sql("duckdb")
    return ExploreSQL(page=page.sql("duckdb"), count=count, params=p.values)
