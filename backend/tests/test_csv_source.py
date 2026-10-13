import io
from datetime import date

import duckdb
import pytest

from data2html.settings import Settings
from data2html.sources.base import DataSource
from data2html.sources.catalog_meta import CatalogMeta
from data2html.sources.csv_source import ConfirmRequest, CsvSource, CsvType
from data2html.sources.engine import new_duckdb
from data2html.sources.errors import Conflict, NotFound, QueryInterrupted, SourceError, TooLarge
from data2html.sqlgen.validate import UnsafeSQL

# Typical Spanish-locale Excel export: ';', decimal comma, Latin-1, d/m/y dates
VENTAS = (
    "cp;región;monto;fecha;cp\n"
    "01234;Norte;1.234,50;13/04/2026;a\n"
    "05678;Sur;99,9;03/04/2026;b\n"
).encode("latin-1")


@pytest.fixture
def src(tmp_path) -> CsvSource:
    s = Settings(data_dir=tmp_path, max_upload_mb=1, duckdb_memory_limit="256MB", duckdb_threads=1)
    return CsvSource(s, CatalogMeta(s.catalog_meta_path))


def _load(src: CsvSource, table: str = "ventas") -> None:
    preview = src.preview(src.stage(io.BytesIO(VENTAS), "Ventas.csv"))
    src.confirm(ConfirmRequest(upload_id=preview.upload_id, table=table,
                               columns=[c.model_dump(exclude={"warnings"}) for c in preview.columns]))


def test_is_a_datasource(src):
    assert isinstance(src, DataSource)


def test_preview_detects_traps(src):
    p = src.preview(src.stage(io.BytesIO(VENTAS), "Ventas.csv"))
    assert (p.encoding, p.delimiter, p.suggested_table) == ("latin-1", ";", "ventas")
    assert [c.name for c in p.columns] == ["cp", "región", "monto", "fecha", "cp_1"]
    types = {c.name: c.type for c in p.columns}
    assert types == {"cp": CsvType.VARCHAR, "región": CsvType.VARCHAR, "monto": CsvType.DOUBLE,
                     "fecha": CsvType.DATE, "cp_1": CsvType.VARCHAR}
    assert any("Latin-1" in w for w in p.warnings)
    assert any("repeated" in w for w in p.warnings)
    assert p.rows[0][:2] == ["01234", "Norte"]


def test_confirm_writes_typed_parquet(src, tmp_path):
    _load(src)
    assert (tmp_path / "csv/ventas.parquet").exists()
    assert (tmp_path / "csv/ventas.schema.json").exists()
    assert not list((tmp_path / "uploads").iterdir())  # the upload is cleaned up

    t = src.execute("SELECT * FROM ventas ORDER BY cp", {}, identity=None, timeout_s=10)
    assert t.column("cp").to_pylist() == ["01234", "05678"]
    assert t.column("monto").to_pylist() == [1234.5, 99.9]
    assert t.column("fecha").to_pylist() == [date(2026, 4, 13), date(2026, 4, 3)]

    info = src.catalog()[0]
    assert (info.name, info.row_count) == ("ventas", 2)
    assert [c.type for c in info.columns][:3] == ["VARCHAR", "VARCHAR", "DOUBLE"]


def test_confirm_rejects_existing_table(src):
    _load(src)
    with pytest.raises(Conflict):
        _load(src)


def test_confirm_rejects_wrong_columns(src):
    up = src.stage(io.BytesIO(VENTAS), "v.csv")
    with pytest.raises(SourceError, match="do not match"):
        src.confirm(ConfirmRequest(upload_id=up, table="v", columns=[{"name": "cp", "type": "VARCHAR"}]))


def test_confirm_reports_bad_conversion(src):
    up = src.stage(io.BytesIO(VENTAS), "v.csv")
    cols = [c.model_dump(exclude={"warnings"}) for c in src.preview(up).columns]
    cols[1] = {"name": "región", "type": "BIGINT"}
    with pytest.raises(SourceError, match="could not convert"):
        src.confirm(ConfirmRequest(upload_id=up, table="v", columns=cols))


def test_upload_size_limit(src):
    with pytest.raises(TooLarge):
        src.stage(io.BytesIO(b"x" * (2 * 1024 * 1024)), "big.csv")


def test_empty_upload(src):
    with pytest.raises(SourceError, match="empty"):
        src.stage(io.BytesIO(b""), "vacio.csv")


def test_unknown_upload(src):
    with pytest.raises(NotFound):
        src.preview("../../etc/passwd")
    with pytest.raises(NotFound):
        src.preview("0" * 32)


def test_execute_with_params(src):
    _load(src)
    sql = "SELECT count(*) AS n FROM ventas WHERE monto > $m"
    t = src.execute(sql, {"m": 100}, identity=None, timeout_s=10)
    assert t.column("n").to_pylist() == [1]


@pytest.mark.parametrize("sql", [
    "DROP TABLE ventas",
    "SELECT 1; SELECT 2",
    "COPY ventas TO 'x.csv'",
    "INSTALL httpfs",
    "ATTACH 'x.db'",
])
def test_execute_rejects_non_select(src, sql):
    with pytest.raises(UnsafeSQL):
        src.execute(sql, {}, identity=None, timeout_s=10)


def test_execute_cannot_read_outside_data_dir(src, tmp_path):
    secret = tmp_path.parent / "secreto.csv"
    secret.write_text("a\n1\n")
    sql = f"SELECT * FROM read_csv('{secret.as_posix()}')"  # noqa: S608 (simulated attack)
    # layer 1: validation rejects the function
    with pytest.raises(UnsafeSQL, match="read_csv"):
        src.execute(sql, {}, identity=None, timeout_s=10)
    # layer 2: even if validation failed, DuckDB's sandbox does not read outside data/csv
    conn = new_duckdb(allowed_dirs=[tmp_path / "csv"], memory_limit="256MB", threads=1)
    with pytest.raises(duckdb.PermissionException):
        conn.execute(sql)


def test_execute_timeout(src):
    with pytest.raises(QueryInterrupted):
        src.execute("SELECT sum(i * i) FROM range(100000000000) t(i)", {}, identity=None, timeout_s=1)


def test_abandoned_uploads_are_cleaned(src):
    import os
    import time

    from data2html.sources.csv_source import UPLOAD_TTL_S

    old = src.stage(io.BytesIO(VENTAS), "viejo.csv")
    fresh = src.stage(io.BytesIO(VENTAS), "nuevo.csv")
    long_ago = time.time() - UPLOAD_TTL_S - 60
    for suffix in (".csv", ".json"):
        os.utime(src._s.uploads_dir / f"{old}{suffix}", (long_ago, long_ago))
    (src._s.uploads_dir / "notes.txt").write_text("not ours")
    assert src.clean_uploads() == 1
    names = {p.name for p in src._s.uploads_dir.iterdir()}
    assert f"{fresh}.csv" in names and f"{old}.csv" not in names and f"{old}.json" not in names
    assert "notes.txt" in names  # only our own files are touched
