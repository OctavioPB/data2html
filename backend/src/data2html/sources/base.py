"""Interface every data source implements. The rest of the app never knows the concrete source."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import pyarrow as pa


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    type: str
    description: str = ""


@dataclass(frozen=True)
class TableInfo:
    name: str
    columns: tuple[ColumnInfo, ...]
    row_count: int | None = None  # None when counting is expensive (remote sources)
    description: str = ""


@dataclass(frozen=True)
class Identity:
    """Authenticated reader. Always comes from auth/, never from request parameters."""

    user_id: str
    email: str
    provider: str  # "local" | "oidc"
    groups: tuple[str, ...] = field(default_factory=tuple)


@runtime_checkable
class DataSource(Protocol):
    id: str
    kind: str  # csv, postgres, mysql, teradata…
    dialect: str  # SQLGlot dialect accepted by execute(): duckdb, postgres, mysql, teradata

    def catalog(self) -> list[TableInfo]: ...

    def table_info(self, name: str) -> TableInfo:
        """One catalog table; `errors.NotFound` if it does not exist."""
        ...

    def relation(self, name: str) -> tuple[str, ...]:
        """Parts of the qualified name for the FROM clause (e.g. ("pg_dev", "public", "sales"))."""
        ...

    def execute(
        self,
        sql: str,
        params: dict[str, object],
        *,
        identity: Identity | None,
        timeout_s: int,
        query_id: str | None = None,
    ) -> pa.Table:
        """Run a single, already validated and transpiled SELECT. Applies RLS with `identity`.

        `query_id` lets another thread cancel it with `cancel(query_id)`.
        """
        ...

    def cancel(self, query_id: str) -> None: ...
