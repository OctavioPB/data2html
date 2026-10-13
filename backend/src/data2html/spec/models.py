"""The report-spec contract: semantic model and report.

This module is the boundary between producers (studio, pbix importer, AI) and the engine.
Any change here requires updating examples/, the exported JSON Schema and the tests.
"""

from __future__ import annotations

import datetime as dt
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from data2html.i18n import tr
from data2html.spec.expr import ExpressionError, parse_expression

Ident = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,62}$")]
Scalar = str | int | float | bool


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ---------------------------------------------------------------- semantic model


class FieldType(StrEnum):
    nominal = "nominal"
    ordinal = "ordinal"
    temporal = "temporal"
    quantitative = "quantitative"


class Dimension(Strict):
    column: str
    type: FieldType
    description: str = ""


class MeasureFormat(StrEnum):
    number = "number"
    currency = "currency"
    percent = "percent"


class Measure(Strict):
    sql: str = Field(
        description="One aggregate expression in DuckDB dialect over columns of the model's table, "
        "e.g. SUM(gross_amount - discount). No subqueries, windows or unknown functions; "
        "every column inside an aggregate."
    )
    format: MeasureFormat = MeasureFormat.number
    owner: str = Field(description="Who is accountable for the definition")
    description: str

    @model_validator(mode="after")
    def _aggregate_expression(self) -> Measure:
        try:
            parse_expression(self.sql, aggregate=True)
        except ExpressionError as e:
            raise ValueError(tr("invalid measure: {error}", error=e)) from e
        return self


class RlsRule(Strict):
    """Row filter for sources without native RLS: column = value of the reader's claim."""

    column: str
    claim: str = Field(description="Identity attribute, e.g. 'groups' or 'email'")


class SemanticModel(Strict):
    name: Ident
    source: Ident = Field(description="Id of a registered connection (never credentials)")
    table: str
    dimensions: dict[Ident, Dimension]
    measures: dict[Ident, Measure]
    rls: RlsRule | None = None

    @model_validator(mode="after")
    def _no_name_clash(self) -> SemanticModel:
        clash = set(self.dimensions) & set(self.measures)
        if clash:
            raise ValueError(tr("names used as both dimension and measure: {names}", names=sorted(clash)))
        return self


# ---------------------------------------------------------------- report


class Mark(StrEnum):
    table = "table"
    kpi = "kpi"
    bar = "bar"
    line = "line"
    pie = "pie"


class Layout(Strict):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(ge=1, le=12)
    h: int = Field(ge=1)


class FilterOp(StrEnum):
    eq = "eq"
    neq = "neq"
    in_ = "in"
    gte = "gte"
    lte = "lte"
    between = "between"


class Filter(Strict):
    """Filter on a dimension. The value comes from a report parameter (`param`) or is fixed
    (`value`); exactly one of the two."""

    dimension: Ident
    op: FilterOp
    param: Ident | None = Field(default=None, description="Report parameter that provides the value")
    value: Scalar | tuple[Scalar, ...] | None = Field(
        default=None, description="Fixed value; a list for 'in' and [from, to] for 'between'"
    )

    @model_validator(mode="after")
    def _one_source(self) -> Filter:
        if (self.param is None) == (self.value is None):
            raise ValueError(tr("a filter takes 'param' or 'value', exactly one"))
        if self.value is not None:
            is_list = isinstance(self.value, tuple)
            if self.op is FilterOp.between and not (is_list and len(self.value) == 2):  # type: ignore[arg-type]
                raise ValueError(tr("'between' expects value: [from, to]"))
            if self.op is FilterOp.in_ and not (is_list and self.value):
                raise ValueError(tr("'in' expects a non-empty list"))
            if self.op not in (FilterOp.between, FilterOp.in_) and is_list:
                raise ValueError(tr("'{op}' expects a single value", op=self.op.value))
        return self


class TimeGrain(StrEnum):
    day = "day"
    week = "week"
    month = "month"
    quarter = "quarter"
    year = "year"


class Visual(Strict):
    id: Ident
    title: str
    mark: Mark
    measure: Ident
    dimension: Ident | None = None
    time_grain: TimeGrain | None = Field(
        default=None, description="Groups a temporal dimension by period (date_trunc)"
    )
    color: Ident | None = None
    filters: tuple[Filter, ...] = ()
    layout: Layout


class Mode(StrEnum):
    live = "live"
    snapshot = "snapshot"


class ParamType(StrEnum):
    int = "int"
    float = "float"
    str = "str"
    date = "date"
    bool = "bool"


class ParamValueError(ValueError):
    pass


def coerce_param(type_: ParamType, raw: object) -> Scalar:
    """A parameter value (from YAML or a query string) → the declared type. Dates stay ISO text
    (`YYYY-MM-DD`): the generated SQL casts the placeholder to the column's type."""
    text = str(raw).strip()
    try:
        if type_ is ParamType.int:
            if isinstance(raw, bool):
                raise ValueError
            return int(text)
        if type_ is ParamType.float:
            if isinstance(raw, bool):
                raise ValueError
            return float(text)
        if type_ is ParamType.date:
            return dt.date.fromisoformat(text).isoformat()
        if type_ is ParamType.bool:
            if isinstance(raw, bool):
                return raw
            low = text.lower()
            if low not in ("true", "false", "1", "0"):
                raise ValueError
            return low in ("true", "1")
        return str(raw)
    except ValueError:
        msg = tr("'{value}' is not a valid {type}", value=text[:40], type=type_.value)
        raise ParamValueError(msg) from None


class Param(Strict):
    type: ParamType
    default: Scalar | None = Field(default=None, description="Initial value in the viewer")
    label: str = Field(default="", description="Text for the viewer's control; the name if empty")

    @model_validator(mode="after")
    def _default_matches_type(self) -> Param:
        if self.default is not None:
            try:
                coerce_param(self.type, self.default)
            except ParamValueError as e:
                raise ValueError(tr("invalid default: {error}", error=e)) from e
        return self


class Report(Strict):
    id: Ident
    title: str
    semantic_model: Ident
    mode: Mode = Field(
        default=Mode.live,
        description="live: every view queries the source. snapshot: each reader's data (with their RLS) is "
        "computed once and kept until the report is republished or `refresh_hours` pass",
    )
    refresh_hours: int | None = Field(
        default=None, ge=1, le=24 * 90,
        description="snapshot only: hours after which a reader's snapshot is recomputed; "
        "empty = until the report is republished",
    )
    params: dict[Ident, ParamType | Param] = Field(
        default_factory=dict, description="parameter → type, or {type, default, label}"
    )
    access: tuple[str, ...] = Field(
        default=(), description="Groups allowed to open the report; empty = any authenticated reader"
    )
    visuals: tuple[Visual, ...]

    @model_validator(mode="after")
    def _unique_ids(self) -> Report:
        ids = [v.id for v in self.visuals]
        dup = {i for i in ids if ids.count(i) > 1}
        if dup:
            raise ValueError(tr("duplicate visual ids: {ids}", ids=sorted(dup)))
        if self.refresh_hours is not None and self.mode is not Mode.snapshot:
            raise ValueError(tr("refresh_hours only applies to mode: snapshot"))
        return self

    def param(self, name: str) -> Param:
        """Declared parameter, with the `name: type` shorthand expanded."""
        p = self.params[name]
        return p if isinstance(p, Param) else Param(type=p)


# ---------------------------------------------------------------- cross validation

def validate_report(report: Report, model: SemanticModel) -> list[str]:
    """Errors of a report against its model, one per problem. Empty list = valid."""
    from data2html.spec.compat import allowed_marks

    errors: list[str] = []
    if report.semantic_model != model.name:
        errors.append(tr("the report uses '{used}', it was validated against '{model}'",
                         used=report.semantic_model, model=model.name))
    for v in report.visuals:
        where = v.id
        if v.measure not in model.measures:
            errors.append(tr("visual {id}: unknown measure '{name}'", id=where, name=v.measure))
        if v.dimension is not None and v.dimension not in model.dimensions:
            errors.append(tr("visual {id}: unknown dimension '{name}'", id=where, name=v.dimension))
        if v.color is not None and v.color not in model.dimensions:
            errors.append(tr("visual {id}: unknown color dimension '{name}'", id=where, name=v.color))
        for f in v.filters:
            if f.dimension not in model.dimensions:
                errors.append(tr("visual {id}: filter on unknown dimension '{name}'",
                                 id=where, name=f.dimension))
            if f.param is not None and f.param not in report.params:
                errors.append(tr("visual {id}: undeclared parameter '{name}'", id=where, name=f.param))
            elif f.param is not None and f.dimension in model.dimensions:
                ptype = report.param(f.param).type
                ftype = model.dimensions[f.dimension].type
                ok = {FieldType.temporal: {ParamType.date},
                      FieldType.quantitative: {ParamType.int, ParamType.float}}.get(ftype, set(ParamType))
                if ptype not in ok:
                    errors.append(tr("visual {id}: parameter '{name}' ({ptype}) cannot filter "
                                     "'{dimension}' ({ftype})", id=where, name=f.param, ptype=ptype.value,
                                     dimension=f.dimension, ftype=ftype.value))
        dim = model.dimensions.get(v.dimension) if v.dimension else None
        if v.time_grain is not None and (dim is None or dim.type is not FieldType.temporal):
            errors.append(tr("visual {id}: time_grain only applies to a temporal dimension", id=where))
        if v.dimension is None or dim is not None:
            allowed = allowed_marks(dim.type if dim else None, has_color=v.color is not None)
            if v.mark not in allowed:
                names = [m.value for m in allowed]
                errors.append(tr("visual {id}: mark '{mark}' is not compatible; allowed {allowed}",
                                 id=where, mark=v.mark.value, allowed=names))
    return errors
