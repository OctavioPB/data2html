import io
import math

import pytest
from fastapi.testclient import TestClient

from data2html.api.main import app, get_settings
from data2html.api.profile import cache
from data2html.profiling.models import ColumnKind, ProfileOptions, WarningCode
from data2html.profiling.profiler import classify, hist_bins, profile_table
from data2html.settings import Settings
from data2html.sources.catalog_meta import CatalogMeta
from data2html.sources.csv_source import ConfirmRequest, CsvSource
from data2html.sqlgen.explore import ComputedColumn

N = 40


def _csv(rows: int = N) -> bytes:
    lines = ["id,cat,x,y,z,fecha,cp,num_txt,fijo,casi_vacia"]
    for i in range(1, rows + 1):
        cat = "" if i % 4 == 0 else ["a", "b", "b"][i % 3]          # 25% nulos
        x = 1000 if i == rows else i                                  # un outlier alto
        fecha = f"2026-0{[1, 4, 7][i % 3]}-{1 + i % 28:02d}"
        casi = "v" if i == 1 else ""
        lines.append(f"{i},{cat},{x},{2 * x},{x ** 3},{fecha},{i:05d},{i * 1.5},k,{casi}")
    return ("\n".join(lines) + "\n").encode()


def _load(src: CsvSource, table: str, body: bytes) -> None:
    p = src.preview(src.stage(io.BytesIO(body), f"{table}.csv"))
    cols = [c.model_dump(exclude={"warnings"}) for c in p.columns]
    for c in cols:  # 'num_txt' como texto a propósito, para el aviso
        if c["name"] == "num_txt":
            c.update(type="VARCHAR", decimal_comma=False)
    src.confirm(ConfirmRequest(upload_id=p.upload_id, table=table, columns=cols))


@pytest.fixture
def env(tmp_path):
    s = Settings(data_dir=tmp_path, duckdb_memory_limit="256MB", duckdb_threads=1)
    meta = CatalogMeta(s.catalog_meta_path)
    src = CsvSource(s, meta)
    _load(src, "t", _csv())
    return s, meta, src


def by_name(profile):
    return {c.name: c for c in profile.columns}


@pytest.mark.parametrize(("t", "kind"), [
    ("BIGINT", ColumnKind.numeric), ("DECIMAL(18,2)", ColumnKind.numeric), ("DOUBLE", ColumnKind.numeric),
    ("DATE", ColumnKind.temporal), ("TIMESTAMP WITH TIME ZONE", ColumnKind.temporal),
    ("VARCHAR", ColumnKind.text), ("BOOLEAN", ColumnKind.boolean), ("INTEGER[]", ColumnKind.other),
])
def test_classify(t, kind):
    assert classify(t) is kind


def test_hist_bins():
    assert hist_bins(5, 5, 5, 5, 10, 1, False, 50).bins == 1                 # constante
    h = hist_bins(1, 20, 5, 15, 1000, 20, True, 50)                         # enteros de rango corto
    assert (h.start, h.width, h.bins) == (1, 1.0, 20)
    assert hist_bins(0, 1, 0.25, 0.75, 10**6, 10**6, False, 50).bins == 50  # tope max_bins
    assert hist_bins(0, 0.3, 0.1, 0.2, 10**6, 31, False, 50).bins == 31     # no más bins que distintos


def test_profile_csv(env):
    s, meta, src = env
    p = profile_table(src, meta, "t", s)
    assert (p.rows, p.sampled, p.sample_size) == (N, False, None)
    c = by_name(p)

    codes = {name: {w.code for w in col.warnings} for name, col in c.items()}
    assert WarningCode.possible_id in codes["id"]
    assert WarningCode.nulls in codes["cat"] and c["cat"].null_ratio == pytest.approx(0.25)
    assert WarningCode.constant in codes["fijo"]
    assert WarningCode.numeric_as_text in codes["num_txt"]
    assert WarningCode.numeric_as_text not in codes["cp"]           # '00001' es un código, no un número
    assert WarningCode.possible_id in codes["cp"]
    assert WarningCode.nulls in codes["casi_vacia"]

    x = c["x"]
    assert x.kind is ColumnKind.numeric and x.min == 1 and x.max == 1000
    assert sum(b.count for b in x.histogram) == x.non_null == N
    assert x.outliers.above == 1 and x.outliers.below == 0

    cat = c["cat"]
    assert [(v.value, v.count) for v in cat.top] == [("b", 20), ("a", 10)]
    assert cat.other_count == 0

    f = c["fecha"]
    assert f.kind is ColumnKind.temporal and f.period_unit == "month"
    assert sum(pc.count for pc in f.periods) == N
    assert [pc.period for pc in f.periods] == ["2026-01-01", "2026-04-01", "2026-07-01"]


def test_correlations(env):
    s, meta, src = env
    corr = profile_table(src, meta, "t", s).correlations
    assert corr is not None and corr.n == N
    ix = {name: i for i, name in enumerate(corr.columns)}
    assert corr.pearson[ix["x"]][ix["y"]] == pytest.approx(1.0)          # lineal
    assert corr.spearman[ix["x"]][ix["z"]] == pytest.approx(1.0)         # monótona
    assert corr.pearson[ix["x"]][ix["z"]] < 0.999                        # pero no lineal
    assert all(corr.pearson[i][i] == 1.0 for i in range(len(corr.columns)))
    assert "fijo" not in ix                                              # constante: sin correlación


def test_computed_columns_are_profiled(env):
    s, meta, src = env
    meta.put_computed("csv", "t", ComputedColumn(name="doble", expr="x * 2", type="BIGINT"))
    d = by_name(profile_table(src, meta, "t", s))["doble"]
    assert d.computed and d.max == 2000


class _Remote:
    """Envuelve la fuente CSV pero se declara remota: fuerza el camino con muestra."""

    kind = "postgres"
    dialect = "duckdb"

    def __init__(self, inner: CsvSource) -> None:
        self._inner = inner
        self.id = inner.id

    def __getattr__(self, name):
        return getattr(self._inner, name)


def test_remote_sources_are_sampled(tmp_path):
    s = Settings(data_dir=tmp_path, duckdb_memory_limit="256MB", duckdb_threads=1)
    meta = CatalogMeta(s.catalog_meta_path)
    src = CsvSource(s, meta)
    _load(src, "grande", _csv(3000))
    p = profile_table(_Remote(src), meta, "grande", s, ProfileOptions(sample_rows=1000))
    assert (p.sampled, p.sample_size, p.rows) == (True, 1000, 1000)
    assert p.correlations is not None and p.correlations.n == 1000

    small = profile_table(_Remote(src), meta, "grande", s, ProfileOptions(sample_rows=5000))
    assert (small.sampled, small.rows) == (False, 3000)  # cupo completa en la muestra


@pytest.fixture
def client(tmp_path):
    cache.clear()
    s = Settings(data_dir=tmp_path)
    app.dependency_overrides[get_settings] = lambda: s
    _load(CsvSource(s, CatalogMeta(s.catalog_meta_path)), "t", _csv())
    yield TestClient(app)
    app.dependency_overrides.clear()
    cache.clear()


def test_api_profile_is_cached(client):
    r = client.get("/api/profile/csv/t")
    assert r.status_code == 200
    first = r.json()
    assert first["rows"] == N and not first["sampled"]
    assert client.get("/api/profile/csv/t").json()["profiled_at"] == first["profiled_at"]

    # una columna calculada nueva invalida la caché
    client.put("/api/catalog/csv/t/computed", json={"name": "doble", "expr": "x * 2"})
    names = [c["name"] for c in client.get("/api/profile/csv/t").json()["columns"]]
    assert names[-1] == "doble"


def test_api_profile_errors(client):
    assert client.get("/api/profile/csv/no_existe").status_code == 404
    assert client.get("/api/profile/pg/t").status_code == 404


def test_profile_json_has_no_nan(client):
    body = client.get("/api/profile/csv/t").text
    assert "NaN" not in body and "Infinity" not in body
    assert not any(isinstance(v, float) and math.isnan(v)
                   for c in client.get("/api/profile/csv/t").json()["columns"] for v in c.values())
