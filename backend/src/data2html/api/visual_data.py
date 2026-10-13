"""Run a visual: shared by the studio's preview (author) and the live viewer (reader identity)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from data2html.api.explore import to_cell
from data2html.api.schemas import Cell, ExploreColumn
from data2html.api.sql import duckdb_type
from data2html.sources.base import DataSource, Identity
from data2html.spec import Mark, SemanticModel, Visual, allowed_marks
from data2html.sqlgen.visual import build_visual_query


class VisualData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    columns: list[ExploreColumn]
    rows: list[list[Cell]]
    allowed_marks: list[Mark]
    as_of: str | None = None  # snapshot reports: when this reader's data was taken (ISO, UTC)


def run_visual(
    visual: Visual,
    model: SemanticModel,
    src: DataSource,
    *,
    params: dict[str, object],
    identity: Identity | None,
    author_preview: bool = False,
    timeout_s: int,
    computed: dict[str, str] | None = None,
) -> tuple[VisualData, str]:
    """Aggregated rows of the visual (never raw rows) and the generated DuckDB SQL.

    RLS: `build_visual_query` requires `identity` when the model declares `rls`, unless the caller
    is the studio's author preview (`author_preview=True`); the viewer never passes that flag.
    """
    info = src.table_info(model.table)
    q = build_visual_query(
        visual, model, src.relation(model.table),
        column_types={c.name: c.type for c in info.columns},
        report_params=params, identity=identity, author_preview=author_preview,
        rls_exact_recheck=getattr(src, "loose_collation", False), computed=computed,
    )
    table = src.execute(q.sql, q.params, identity=identity, timeout_s=timeout_s)
    data = [[to_cell(v) for v in table.column(i).to_pylist()] for i in range(table.num_columns)]
    dim = model.dimensions.get(visual.dimension) if visual.dimension else None
    out = VisualData(
        columns=[ExploreColumn(name=f.name, type=duckdb_type(f.type), computed=False) for f in table.schema],
        rows=[list(r) for r in zip(*data, strict=True)],
        allowed_marks=allowed_marks(dim.type if dim else None, has_color=visual.color is not None),
    )
    return out, q.sql
