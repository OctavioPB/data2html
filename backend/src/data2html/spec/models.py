"""Contrato report-spec: modelo semántico y reporte.

Este módulo es la frontera entre productores (studio, importador pbix, IA) y el engine.
Cualquier cambio aquí exige actualizar examples/, el JSON Schema exportado y los tests.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

Ident = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,62}$")]


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
    sql: str = Field(description="Expresión agregada en dialecto DuckDB, p. ej. SUM(MONTO)")
    format: MeasureFormat = MeasureFormat.number
    owner: str = Field(description="Responsable de la definición")
    description: str

    @model_validator(mode="after")
    def _single_expression(self) -> Measure:
        if ";" in self.sql:
            raise ValueError("una medida es una sola expresión, sin ';'")
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
    in_ = "in"
    gte = "gte"
    lte = "lte"


class Filter(Strict):
    dimension: Ident
    op: FilterOp
    param: Ident = Field(description="Nombre del parámetro del reporte que aporta el valor")


class Visual(Strict):
    id: Ident
    title: str
    mark: Mark
    measure: Ident
    dimension: Ident | None = None
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
            if f.param not in report.params:
                errors.append(f"{where}: parámetro no declarado '{f.param}'")
        dim = model.dimensions.get(v.dimension) if v.dimension else None
        if v.dimension is None or dim is not None:
            allowed = allowed_marks(dim.type if dim else None, has_color=v.color is not None)
            if v.mark not in allowed:
                names = [m.value for m in allowed]
                errors.append(f"{where}: mark '{v.mark}' no compatible; permitidos {names}")
    return errors
