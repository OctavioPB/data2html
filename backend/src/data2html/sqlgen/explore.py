"""Excel-like explorer: sort, filters, search and computed columns → one paginated SELECT.

Everything is built with SQLGlot expressions; user values travel as parameters (`$p0`…) and column
names are checked against the catalog. Computed columns are scalar expressions reviewed by
`parse_computed` (no subqueries, aggregates, windows or unknown functions).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlglot import exp

from data2html.i18n import tr
from data2html.spec.expr import ExpressionError, parse_expression

MAX_LIMIT = 1000
NAME_PATTERN = r"^[a-z_][a-z0-9_]{0,62}$"

Scalar = str | int | float | bool


class InvalidExplore(ValueError):
    pass


# ------------------------------------------------------------------ request


class ExploreOp(StrEnum):
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


_NO_VALUE = {ExploreOp.is_null, ExploreOp.not_null}
_TEXT_OPS = {ExploreOp.contains, ExploreOp.starts_with}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SortKey(_Strict):
    column: str
    desc: bool = False


class ColumnFilter(_Strict):
    column: str
    op: ExploreOp
    value: Scalar | Annotated[list[Scalar], Field(max_length=500)] | None = None

    @model_validator(mode="after")
    def _value_matches_op(self) -> Self:
        v = self.value
        if self.op in _NO_VALUE:
            if v is not None:
                raise ValueError(tr("{op} takes no value", op=self.op.value))
        elif self.op is ExploreOp.between:
            if not (isinstance(v, list) and len(v) == 2):
                raise ValueError(tr("between expects [from, to]"))
        elif self.op is ExploreOp.in_:
            if not (isinstance(v, list) and v):
                raise ValueError(tr("in expects a non-empty list"))
        elif v is None or isinstance(v, list):
            raise ValueError(tr("'{op}' expects a single value", op=self.op.value))
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
    type: str = ""  # DuckDB type resolved when saved; empty while it is being validated


# ------------------------------------------------------------------ computed columns

def parse_computed(expr: str, columns: set[str]) -> exp.Expr:
    """Scalar (per-row) expression over existing columns, or `InvalidExplore` with the reason."""
    try:
        tree, used = parse_expression(expr, aggregate=False)
    except ExpressionError as e:
        raise InvalidExplore(str(e)) from e
    unknown = sorted(used - columns)
    if unknown:
        raise InvalidExplore(tr("unknown column: {name}", name=unknown[0]))
    return tree


# ------------------------------------------------------------------ SQL


@dataclass(frozen=True)
class ExploreSQL:
    page: str
    count: str | None
    params: dict[str, object]


def _col(name: str) -> exp.Column:
    return exp.column(exp.to_identifier(name, quoted=True))


def _table(relation: tuple[str, ...]) -> exp.Table:
    if not 1 <= len(relation) <= 3:
        raise InvalidExplore(tr("invalid relation: {relation}", relation=repr(relation)))
    *qual, name = (exp.to_identifier(p, quoted=True) for p in relation)
    catalog, db = ([None, None] + qual)[-2:]
    return exp.Table(this=name, db=db, catalog=catalog)


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
    # The parameter arrives as JSON text/number: cast it to the column's (server-side) type.
    return exp.cast(param, exp.DataType.build(type_, dialect="duckdb")) if type_ else param


def _ilike(target: exp.Expr, pattern: exp.Expr) -> exp.Expr:
    text = exp.cast(target, exp.DataType.build("VARCHAR"))
    return exp.Escape(this=exp.ILike(this=text, expression=pattern), expression=exp.Literal.string("\\"))


def _filter(f: ColumnFilter, type_: str, p: _Params) -> exp.Expr:
    c = _col(f.column)
    if f.op is ExploreOp.is_null:
        return exp.Is(this=c, expression=exp.Null())
    if f.op is ExploreOp.not_null:
        return exp.Not(this=exp.Is(this=c, expression=exp.Null()))
    if f.op in _TEXT_OPS:
        v = _escape_like(str(f.value))
        return _ilike(c, p.add(f"%{v}%" if f.op is ExploreOp.contains else f"{v}%"))
    if f.op is ExploreOp.between:
        assert isinstance(f.value, list)
        lo, hi = (_typed(p.add(v), type_) for v in f.value)
        return exp.Between(this=c, low=lo, high=hi)
    if f.op is ExploreOp.in_:
        assert isinstance(f.value, list)
        return exp.In(this=c, expressions=[_typed(p.add(v), type_) for v in f.value])
    cmp: dict[ExploreOp, type[exp.Binary]] = {
        ExploreOp.eq: exp.EQ, ExploreOp.ne: exp.NEQ, ExploreOp.lt: exp.LT,
        ExploreOp.le: exp.LTE, ExploreOp.gt: exp.GT, ExploreOp.ge: exp.GTE,
    }
    return cmp[f.op](this=c, expression=_typed(p.add(f.value), type_))


def base_select(
    relation: tuple[str, ...], columns: dict[str, str], computed: list[ComputedColumn]
) -> tuple[exp.Select, dict[str, str]]:
    """`SELECT *, <computed> FROM relation` and the types of all its columns."""
    types = dict(columns)
    projections: list[exp.Expr] = [exp.Star()]
    for cc in computed:
        if cc.name in types:
            raise InvalidExplore(tr("computed column {name} clashes with an existing one",
                                    name=repr(cc.name)))
        projections.append(exp.alias_(parse_computed(cc.expr, set(columns)), cc.name, quoted=True))
        types[cc.name] = cc.type
    return exp.select(*projections).from_(_table(relation)), types


def build_explore(
    relation: tuple[str, ...],
    columns: dict[str, str],
    computed: list[ComputedColumn],
    req: ExploreRequest,
) -> ExploreSQL:
    """`relation`: the table's qualified name (`DataSource.relation`); `columns`: name → DuckDB type
    (from the catalog). Returns parameterized DuckDB SQL."""
    base, types = base_select(relation, columns, computed)

    def known(name: str) -> str:
        if name not in types:
            raise InvalidExplore(tr("unknown column: {name}", name=repr(name)))
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

    filtered = exp.select("*").from_("_t").with_("_t", as_=base)
    if conds:
        filtered = filtered.where(exp.and_(*conds))

    page = filtered.copy()
    for s in req.sort:
        known(s.column)
    if req.sort:
        # DuckDB's sort is not stable: without a tiebreak, pages would repeat or skip rows.
        # Without `sort`, preserve_insertion_order (the default) keeps the file order.
        keys = [exp.Ordered(this=_col(s.column), desc=s.desc) for s in req.sort]
        sorted_cols = {s.column for s in req.sort}
        keys += [exp.Ordered(this=_col(n)) for n in columns if n not in sorted_cols]
        page = page.order_by(*keys)
    page = page.limit(req.limit).offset(req.offset)

    count = None
    if req.with_total:
        count = exp.select(exp.Count(this=exp.Star()).as_("n")).from_(filtered.subquery("_f")).sql("duckdb")
    return ExploreSQL(page=page.sql("duckdb"), count=count, params=p.values)
