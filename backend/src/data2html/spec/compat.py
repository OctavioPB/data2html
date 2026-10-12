"""Which chart types a visual supports given its encoding.

Single source of truth: used by the studio (through the API), the renderer (the HTML selector) and the AI.
"""

from __future__ import annotations

from data2html.spec.models import FieldType, Mark

_SEQUENTIAL = {FieldType.temporal, FieldType.ordinal}


def allowed_marks(dimension: FieldType | None, *, has_color: bool = False) -> list[Mark]:
    """Valid marks for a measure grouped (or not) by a dimension of the given type."""
    if dimension is None:
        return [Mark.kpi, Mark.table]
    if dimension is FieldType.quantitative:
        # grouping by a continuous quantity makes no sense without binning (pending)
        return [Mark.table]
    marks = [Mark.table, Mark.bar]
    if dimension in _SEQUENTIAL:
        marks.append(Mark.line)
    if dimension is FieldType.nominal and not has_color:
        # pie: unordered parts of a whole; with color it would be an unreadable nested pie
        marks.append(Mark.pie)
    return marks
