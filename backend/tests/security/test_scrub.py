"""Server paths never reach the browser (DuckDB errors quote the files they could not read)."""

from pathlib import Path

from data2html.scrub import register, scrub


def test_scrub_markers_and_generic_paths():
    register(Path("C:/srv/d2h/data"), "<data>")
    message = 'No files match "C:\\srv\\d2h\\data\\csv\\x.parquet"'
    assert scrub(message) == 'No files match "<data>/csv/x.parquet"'
    assert scrub("cannot open /var/lib/d2h/secret/file.parquet") == "cannot open <path>"
    assert scrub("drive D:\\backups\\db.sqlite") == "drive <path>"
    # not paths: dates, URL paths, plain messages
    for keep in ["fecha 13/04/2026 inválida", "abre /r/regional", 'Referenced column "monto" not found']:
        assert scrub(keep) == keep


def test_duckdb_error_with_a_file_path_is_scrubbed(viewer_app, viewer_settings):
    parquet = viewer_settings.csv_dir / "ventas.parquet"
    parquet.write_bytes(b"not a parquet file")  # DuckDB's error names the file it was reading
    r = viewer_app.post("/api/explore/csv/ventas", json={})
    assert r.status_code >= 400
    detail = r.json()["detail"]
    assert "<data>/csv/ventas.parquet" in detail, detail  # the path was there, now as a marker
    data_dir = viewer_settings.data_dir
    assert str(data_dir) not in detail and str(data_dir.resolve()) not in detail
    assert "\\" not in detail and ":/" not in detail.replace("http://", "")
