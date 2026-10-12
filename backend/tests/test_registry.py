import pytest
from pydantic import ValidationError

from data2html.settings import Settings
from data2html.sources.base import DataSource
from data2html.sources.catalog_meta import CatalogMeta
from data2html.sources.errors import NotFound, SourceUnavailable
from data2html.sources.postgres import PostgresSource
from data2html.sources.registry import PostgresConfig, SourceRegistry, load_sources_file

PG = {"type": "postgres", "host": "localhost", "database": "d2h", "user": "d2h_reader",
      "password_env": "PG_TEST_PASSWORD"}


def write(tmp_path, text: str):
    p = tmp_path / "sources.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_missing_file_means_only_csv(tmp_path):
    s = Settings(data_dir=tmp_path, sources_file=tmp_path / "no-existe.yaml")
    reg = SourceRegistry.load(s, CatalogMeta(s.catalog_meta_path))
    assert [src.id for src in reg.all()] == ["csv"]
    with pytest.raises(NotFound):
        reg.get("pg")


def test_loads_postgres(tmp_path):
    f = write(tmp_path, "sources:\n  pg_dev:\n    type: postgres\n    host: localhost\n    database: d2h\n"
                        "    user: d2h_reader\n    password_env: PG_DEV_PASSWORD\n")
    s = Settings(data_dir=tmp_path, sources_file=f)
    reg = SourceRegistry.load(s, CatalogMeta(s.catalog_meta_path))
    pg = reg.get("pg_dev")
    assert isinstance(pg, DataSource) and pg.kind == "postgres"


@pytest.mark.parametrize("bad", [
    {"password": "d2h"},                      # a secret in the YAML: forbidden
    {"password_env": "pg password"},           # not a variable name
    {"host": "localhost' OR '1"},
    {"host": "h dbname=otra"},                 # injection into the connection string
    {"port": 0},
    {"schemas": []},
    {"type": "teradata"},                      # not supported yet
])
def test_rejects_bad_config(bad):
    with pytest.raises(ValidationError):
        PostgresConfig.model_validate(PG | bad)


def test_csv_id_is_reserved(tmp_path):
    f = write(tmp_path, "sources:\n  csv:\n    type: postgres\n    host: h\n    database: d\n"
                        "    user: u\n    password_env: X\n")
    with pytest.raises(ValueError, match="reserved"):
        load_sources_file(f)


def test_missing_password_env_is_unavailable_not_crash(tmp_path, monkeypatch):
    monkeypatch.delenv("PG_TEST_PASSWORD", raising=False)
    s = Settings(data_dir=tmp_path)
    src = PostgresSource("pg", PostgresConfig.model_validate(PG), s, CatalogMeta(s.catalog_meta_path))
    with pytest.raises(SourceUnavailable, match="PG_TEST_PASSWORD"):
        src.catalog()


def test_unreachable_server_hides_connection_details(tmp_path, monkeypatch):
    monkeypatch.setenv("PG_TEST_PASSWORD", "s3cr3t-no-debe-salir")
    s = Settings(data_dir=tmp_path)
    cfg = PostgresConfig.model_validate(PG | {"host": "127.0.0.1", "port": 1, "connect_timeout_s": 1})
    src = PostgresSource("pg", cfg, s, CatalogMeta(s.catalog_meta_path))
    with pytest.raises(SourceUnavailable) as err:
        src.catalog()
    msg = str(err.value)
    assert "s3cr3t" not in msg and "127.0.0.1" not in msg and "d2h_reader" not in msg
    assert "s3cr3t" not in repr(src)
    # does not retry on every request: fails fast during the retry window
    with pytest.raises(SourceUnavailable):
        src.catalog()


def test_example_config_is_valid():
    from pathlib import Path

    example = Path(__file__).resolve().parents[2] / "config/sources.example.yaml"
    assert "postgres_dev" in load_sources_file(example).sources
