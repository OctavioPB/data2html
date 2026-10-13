"""Development tools. The app does not import them.

    python -m data2html.devtools demo [filas]        → data/csv/demo_ventas.parquet (default 5M rows)
    python -m data2html.devtools install-extensions  → downloads the DuckDB extensions once
                                                       (e.g. when building the image)
"""

from __future__ import annotations

import json
import sys
import time

import duckdb

from data2html.settings import Settings
from data2html.sources.engine import ensure_extension, sql_literal

EXTENSIONS = ("postgres", "mysql")


def demo(rows: int = 5_000_000) -> None:
    s = Settings.from_env()
    s.csv_dir.mkdir(parents=True, exist_ok=True)
    out = s.csv_dir / "demo_ventas.parquet"
    t0 = time.perf_counter()
    conn = duckdb.connect()
    conn.execute("SELECT setseed(0.42)")
    conn.execute(f"""
        COPY (
            SELECT
                i AS pedido_id,
                DATE '2024-01-01' + CAST(floor(random() * 900) AS INTEGER) AS fecha,
                ['Norte', 'Sur', 'Centro', 'Occidente', 'Sureste'][1 + CAST(floor(random() * 5) AS INTEGER)]
                    AS region,
                'Cliente ' || lpad(CAST(CAST(floor(random() * 50000) AS INTEGER) AS VARCHAR), 5, '0')
                    AS cliente,
                ['Abarrotes', 'Bebidas', 'Limpieza', 'Electrónica', 'Ropa', 'Farmacia']
                    [1 + CAST(floor(random() * 6) AS INTEGER)] AS categoria,
                CAST(1 + floor(random() * 20) AS INTEGER) AS unidades,
                round(10 + random() * 990, 2) AS precio,
                CASE WHEN random() < 0.03 THEN NULL ELSE round(random() * 0.3, 2) END AS descuento
            FROM range({int(rows)}) t(i)
        ) TO {sql_literal(str(out))} (FORMAT parquet, ROW_GROUP_SIZE 122880)
    """)  # noqa: S608 (rows is an int; our own path)
    conn.close()
    out.with_suffix(".schema.json").write_text(
        json.dumps({"table": "demo_ventas", "source_file": "(generado)", "rows": rows}, indent=2),
        encoding="utf-8",
    )
    print(f"{rows:,} rows -> {out} in {time.perf_counter() - t0:.1f}s")


def install_extensions() -> None:
    for name in EXTENSIONS:
        ensure_extension(name)
        print(f"extension {name}: installed")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "demo":
        demo(int(sys.argv[2]) if len(sys.argv) > 2 else 5_000_000)
    elif cmd == "install-extensions":
        install_extensions()
    else:
        sys.exit(__doc__)
