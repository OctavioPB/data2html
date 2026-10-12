"""Conexiones DuckDB del servidor, siempre encapsuladas (ver reglas de seguridad en CLAUDE.md)."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import duckdb


def sql_literal(value: str) -> str:
    """Literal de cadena SQL. Solo para valores que genera el servidor (rutas propias, formatos de
    una lista cerrada) en sentencias que no aceptan parámetros. Nunca para entrada del usuario."""
    return "'" + value.replace("'", "''") + "'"


def sql_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def new_duckdb(*, allowed_dirs: Iterable[Path], memory_limit: str, threads: int) -> duckdb.DuckDBPyConnection:
    """DuckDB en memoria que solo puede tocar `allowed_dirs`, sin extensiones nuevas ni red.

    La configuración queda bloqueada: una consulta no puede volver a abrir el acceso externo.
    """
    conn = duckdb.connect(":memory:", config={"memory_limit": memory_limit, "threads": threads})
    dirs = ", ".join(sql_literal(str(Path(d).resolve())) for d in allowed_dirs)
    conn.execute(f"SET allowed_directories = [{dirs}]")
    conn.execute("SET enable_external_access = false")
    conn.execute("SET autoinstall_known_extensions = false")
    conn.execute("SET autoload_known_extensions = false")
    conn.execute("SET lock_configuration = true")
    return conn
