"""Contrato report-spec: modelo semántico y reporte.

Este módulo es la frontera entre productores (studio, importador pbix, IA) y el engine.
Cualquier cambio aquí exige actualizar examples/, el JSON Schema exportado y los tests.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from data2html.spec.expr import ExpressionError, parse_expression

Ident = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,62}$")]
Scalar = str | int | float | bool


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ---------------------------------------------------------------- modelo semántico


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
        description="Una expresión agregada en dialecto DuckDB sobre columnas de la tabla del modelo, "
        "p. ej. SUM(monto_bruto - descuento). Sin subconsultas, ventanas ni funciones desconocidas; "
        "toda columna dentro de un agregado."
    )
    format: MeasureFormat = MeasureFormat.number
    owner: str = Field(description="Responsable de la definición")
    description: str

    @model_validator(mode="after")
    def _aggregate_expression(self) -> Measure:
        try:
            parse_expression(self.sql, aggregate=True)
        except ExpressionError as e:
            raise ValueError(f"medida inválida: {e}") from e
        return self


class RlsRule(Strict):
    """Filtro por fila para fuentes sin RLS nativo: column = valor del claim del lector."""

    column: str
    claim: str = Field(description="Atributo de Identity, p. ej. 'groups' o 'email'")


class SemanticModel(Strict):
    name: Ident
    source: Ident = Field(description="Id de conexión registrada (nunca credenciales)")
    table: str
    dimensions: dict[Ident, Dimension]
    measures: dict[Ident, Measure]
    rls: RlsRule | None = None

    @model_validator(mode="after")
    def _no_name_clash(self) -> SemanticModel:
        clash = set(self.dimensions) & set(self.measures)
        if clash:
            raise ValueError(f"nombres usados como dimensión y medida a la vez: {sorted(clash)}")
        return self


# ---------------------------------------------------------------- reporte


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
    """Filtro sobre una dimensión. El valor viene de un parámetro del reporte (`param`) o es fijo
    (`value`); exactamente uno de los dos."""

    dimension: Ident
    op: FilterOp
    param: Ident | None = Field(default=None, description="Parámetro del reporte que aporta el valor")
    value: Scalar | tuple[Scalar, ...] | None = Field(
        default=None, description="Valor fijo; lista para 'in' y [desde, hasta] para 'between'"
    )

    @model_validator(mode="after")
    def _one_source(self) -> Filter:
        if (self.param is None) == (self.value is None):
            raise ValueError("un filtro lleva 'param' o 'value', exactamente uno")
        if self.value is not None:
            is_list = isinstance(self.value, tuple)
            if self.op is FilterOp.between and not (is_list and len(self.value) == 2):  # type: ignore[arg-type]
                raise ValueError("'between' espera value: [desde, hasta]")
            if self.op is FilterOp.in_ and not (is_list and self.value):
                raise ValueError("'in' espera una lista no vacía")
            if self.op not in (FilterOp.between, FilterOp.in_) and is_list:
                raise ValueError(f"'{self.op.value}' espera un solo valor")
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
        default=None, description="Agrupa una dimensión temporal por periodo (date_trunc)"
    )
    color: Ident | None = None
    filters: tuple[Filter, ...] = ()
    layout: Layout


class Mode(StrEnum):
    live = "live"
    snapshot = "snapshot"


class Report(Strict):
    id: Ident
    title: str
    semantic_model: Ident
    mode: Mode = Mode.live
    params: dict[Ident, str] = Field(default_factory=dict, description="parámetro → tipo")
    visuals: tuple[Visual, ...]

    @model_validator(mode="after")
    def _unique_ids(self) -> Report:
        ids = [v.id for v in self.visuals]
        dup = {i for i in ids if ids.count(i) > 1}
        if dup:
            raise ValueError(f"ids de visual duplicados: {sorted(dup)}")
        return self


# ---------------------------------------------------------------- validación cruzada

def validate_report(report: Report, model: SemanticModel) -> list[str]:
    """Errores de un reporte contra su modelo. Lista vacía = válido."""
    from data2html.spec.compat import allowed_marks

    errors: list[str] = []
    if report.semantic_model != model.name:
        errors.append(f"el reporte usa '{report.semantic_model}', se validó contra '{model.name}'")
    for v in report.visuals:
        where = f"visual {v.id}"
        if v.measure not in model.measures:
            errors.append(f"{where}: medida desconocida '{v.measure}'")
        for name, label in ((v.dimension, "dimensión"), (v.color, "color")):
            if name is not None and name not in model.dimensions:
                errors.append(f"{where}: {label} desconocida '{name}'")
        for f in v.filters:
            if f.dimension not in model.dimensions:
                errors.append(f"{where}: filtro sobre dimensión desconocida '{f.dimension}'")
            if f.param is not None and f.param not in report.params:
                errors.append(f"{where}: parámetro no declarado '{f.param}'")
        dim = model.dimensions.get(v.dimension) if v.dimension else None
        if v.time_grain is not None and (dim is None or dim.type is not FieldType.temporal):
            errors.append(f"{where}: time_grain solo aplica a una dimensión temporal")
        if v.dimension is None or dim is not None:
            allowed = allowed_marks(dim.type if dim else None, has_color=v.color is not None)
            if v.mark not in allowed:
                names = [m.value for m in allowed]
                errors.append(f"{where}: mark '{v.mark}' no compatible; permitidos {names}")
    return errors
