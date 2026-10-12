"""Server-side DuckDB connections, always sandboxed (see the security rules in CLAUDE.md)."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

import duckdb


def sql_literal(value: str) -> str:
    """SQL string literal. Only for server-generated values (our own paths, formats from a closed
    list) in statements that do not accept parameters. Never for user input."""
    return "'" + value.replace("'", "''") + "'"


def sql_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def ensure_extension(name: str) -> None:
    """Install a DuckDB extension (one-time download). Server connections only LOAD."""
    with duckdb.connect(":memory:") as conn:
        conn.execute(f"INSTALL {sql_ident(name)}")


def new_duckdb(
    *,
    allowed_dirs: Iterable[Path],
    memory_limit: str,
    threads: int,
    setup: Callable[[duckdb.DuckDBPyConnection], None] | None = None,
) -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB that can only touch `allowed_dirs`, with no new extensions and no network.

    `setup` runs before the lock (extension LOADs, secrets, ATTACH). Afterwards the configuration is
    locked: a query can neither re-enable external access nor attach another database.
    """
    conn = duckdb.connect(":memory:", config={"memory_limit": memory_limit, "threads": threads})
    if setup is not None:
        try:
            setup(conn)
        except BaseException:
            conn.close()
            raise
    dirs = ", ".join(sql_literal(str(Path(d).resolve())) for d in allowed_dirs)
    conn.execute(f"SET allowed_directories = [{dirs}]")
    conn.execute("SET enable_external_access = false")
    conn.execute("SET autoinstall_known_extensions = false")
    conn.execute("SET autoload_known_extensions = false")
    conn.execute("SET lock_configuration = true")
    return conn
