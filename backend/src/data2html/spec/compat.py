"""Qué tipos de gráfico admite un visual según su encoding.

Fuente única de verdad: la usan el studio (vía API), el renderer (selector del HTML) y la IA.
"""

from __future__ import annotations

from data2html.spec.models import FieldType, Mark

_SEQUENTIAL = {FieldType.temporal, FieldType.ordinal}


def allowed_marks(dimension: FieldType | None, *, has_color: bool = False) -> list[Mark]:
    """Marks válidos para una medida agrupada (o no) por una dimensión del tipo dado."""
    if dimension is None:
        return [Mark.kpi, Mark.table]
    if dimension is FieldType.quantitative:
        # agrupar por una cantidad continua no tiene sentido sin binning (pendiente)
        return [Mark.table]
    marks = [Mark.table, Mark.bar]
    if dimension in _SEQUENTIAL:
        marks.append(Mark.line)
    if dimension is FieldType.nominal and not has_color:
        # pastel: partes de un todo sin orden; con color sería un pastel anidado ilegible
        marks.append(Mark.pie)
    return marks
