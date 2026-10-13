"""API response models (the source of the studio's TS types through OpenAPI)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from data2html.sources.base import TableInfo
from data2html.sources.catalog_meta import TableMeta
from data2html.spec import Mark
from data2html.sqlgen.explore import NAME_PATTERN, ComputedColumn


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Health(_Out):
    status: str
    version: str


class ColumnOut(_Out):
    name: str
    type: str
    description: str


class ComputedOut(ComputedColumn):
    description: str = ""  # editable in the Schema tab, like a physical column's


class TableOut(_Out):
    name: str
    description: str
    row_count: int | None
    columns: list[ColumnOut]
    computed: list[ComputedOut]

    @classmethod
    def of(cls, t: TableInfo, meta: TableMeta) -> TableOut:
        return cls(
            name=t.name, description=t.description, row_count=t.row_count,
            columns=[ColumnOut(name=c.name, type=c.type, description=c.description) for c in t.columns],
            computed=[ComputedOut(**c.model_dump(), description=meta.columns.get(c.name, ""))
                      for c in meta.computed],
        )


class CatalogSource(_Out):
    id: str
    kind: str
    status: Literal["ok", "error"]
    error: str | None = None
    tables: list[TableOut]


class Catalog(_Out):
    sources: list[CatalogSource]


class Compat(_Out):
    marks: list[Mark]


class DescriptionsPatch(_Out):
    description: str | None = Field(default=None, max_length=2000)
    columns: dict[str, Annotated[str, Field(max_length=2000)]] | None = None


class ComputedIn(_Out):
    name: Annotated[str, Field(pattern=NAME_PATTERN)]
    expr: Annotated[str, Field(min_length=1, max_length=2000)]


Cell = str | int | float | bool | None


class ExploreColumn(_Out):
    name: str
    type: str
    computed: bool


class ExplorePage(_Out):
    columns: list[ExploreColumn]
    rows: list[list[Cell]]
    offset: int
    total: int | None
