"""Interfaz que toda fuente de datos implementa. El resto de la app no conoce la fuente concreta."""

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
    row_count: int | None = None  # None si contarlo es caro (fuentes remotas)
    description: str = ""


@dataclass(frozen=True)
class Identity:
    """Lector autenticado. Siempre viene de auth/, nunca de parámetros de la petición."""

    user_id: str
    email: str
    provider: str  # "local" | "oidc"
    groups: tuple[str, ...] = field(default_factory=tuple)


@runtime_checkable
class DataSource(Protocol):
    id: str
    dialect: str  # nombre de dialecto SQLGlot: duckdb, postgres, mysql, teradata

    def catalog(self) -> list[TableInfo]: ...

    def execute(
        self,
        sql: str,
        params: dict[str, object],
        *,
        identity: Identity | None,
        timeout_s: int,
        query_id: str | None = None,
    ) -> pa.Table:
        """Ejecuta un único SELECT ya validado y transpilado. Aplica RLS con `identity`.

        `query_id` permite cancelarla desde otro hilo con `cancel(query_id)`.
        """
        ...

    def cancel(self, query_id: str) -> None: ...
