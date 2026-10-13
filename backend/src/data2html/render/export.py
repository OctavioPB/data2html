"""Visual → CSV download (viewer and studio). Only the visual's aggregated rows, never raw data.

- UTF-8 with BOM, so Excel opens accents correctly.
- Formula injection: a text cell starting with `=`, `+`, `-`, `@`, TAB or CR would run as a formula in a
  spreadsheet; it is prefixed with `'` (numbers are written as numbers and need no guard).
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence

from fastapi.responses import Response

_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
BOM = chr(0xFEFF)  # Excel needs it to read UTF-8


def safe_cell(value: object) -> object:
    if isinstance(value, str) and value.startswith(_FORMULA_START):
        return "'" + value
    if isinstance(value, float) and value.is_integer():
        return int(value)  # 33333, not 33333.0
    return "" if value is None else value


def to_csv(columns: Sequence[str], rows: Sequence[Sequence[object]]) -> bytes:
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow([safe_cell(c) for c in columns])
    for r in rows:
        w.writerow([safe_cell(v) for v in r])
    return (BOM + buf.getvalue()).encode("utf-8")


def csv_response(filename: str, columns: Sequence[str], rows: Sequence[Sequence[object]]) -> Response:
    """`filename` is built from identifiers (`^[a-z][a-z0-9_]*$`), safe in the header."""
    return Response(
        to_csv(columns, rows),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
