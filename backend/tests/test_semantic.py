import pytest
import yaml
from fastapi.testclient import TestClient

from data2html.api.main import app, get_settings
from data2html.semantic.check import check_model
from data2html.semantic.store import ModelNotFound, ModelStore
from data2html.semantic.suggest import NotPromotable, suggest_from_sql
from data2html.settings import Settings
from data2html.sources.catalog_meta import CatalogMeta
from data2html.sources.csv_source import CsvSource
from data2html.spec import SemanticModel

CSV = (
    b"region,canal,fecha,monto,descuento\n"
    b"Norte,Web,2026-01-05,100,10\n"
    b"Norte,Tienda,2026-01-20,50,0\n"
    b"Sur,Web,2026-02-10,300,20\n"
)

MODEL = {
    "name": "ventas",
    "source": "csv",
    "table": "ventas",
    "dimensions": {
        "region": {"column": "region", "type": "nominal"},
        "fecha": {"column": "fecha", "type": "temporal"},
    },
    "measures": {
        "venta_neta": {
            "sql": "SUM(monto - descuento)",
            "format": "currency",
            "owner": "finanzas",
            "description": "Venta neta",
        }
    },
}


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path, sources_file=None)


@pytest.fixture
def csv_src(settings):
    src = CsvSource(settings, CatalogMeta(settings.catalog_meta_path))
    import io

    p = src.preview(src.stage(io.BytesIO(CSV), "ventas.csv"))
    from data2html.sources.csv_source import ConfirmRequest

    src.confirm(
        ConfirmRequest(
            upload_id=p.upload_id,
            table="ventas",
            columns=[c.model_dump(exclude={"warnings"}) for c in p.columns],
        )
    )
    return src


# ------------------------------------------------------------------ store


def test_store_roundtrip(settings):
    store = ModelStore(settings.semantic_dir)
    m = SemanticModel.model_validate(MODEL)
    store.put(m)
    assert store.get("ventas") == m
    text = (settings.semantic_dir / "ventas.yaml").read_text(encoding="utf-8")
    assert text.startswith("# Semantic model") and "venta_neta" in text
    (settings.semantic_dir / "roto.yaml").write_text("name: Roto\n", encoding="utf-8")
    models, broken = store.list()
    assert [x.name for x in models] == ["ventas"] and "roto.yaml" in broken
    store.delete("ventas")
    with pytest.raises(ModelNotFound):
        store.get("ventas")


# ------------------------------------------------------------------ check against the catalog


def test_check_ok(csv_src):
    assert check_model(SemanticModel.model_validate(MODEL), csv_src) == []


def test_check_finds_problems(csv_src):
    bad = MODEL | {
        "dimensions": MODEL["dimensions"] | {"pais": {"column": "pais", "type": "nominal"}},
        "measures": MODEL["measures"]
        | {
            "fantasma": {"sql": "SUM(no_existe)", "owner": "x", "description": "x"},
            "texto": {"sql": "SUM(region)", "owner": "x", "description": "x"},  # types: fails when run
        },
    }
    errors = check_model(SemanticModel.model_validate(bad), csv_src)
    assert any("'pais'" in e for e in errors)
    assert any("fantasma" in e and "no_existe" in e for e in errors)
    assert any(e.startswith("measure 'texto'") for e in errors)


def test_check_unknown_table(csv_src):
    errors = check_model(SemanticModel.model_validate(MODEL | {"table": "otra"}), csv_src)
    assert errors == ["table 'otra' does not exist in source 'csv'"]


# ------------------------------------------------------------------ promote from the SQL editor

TABLES = {
    "ventas": {
        "region": "VARCHAR",
        "canal": "VARCHAR",
        "fecha": "DATE",
        "monto": "BIGINT",
        "descuento": "BIGINT",
    }
}


def test_suggest_new_model():
    s = suggest_from_sql(
        "SELECT region, SUM(monto - descuento) AS Venta_Neta FROM ventas GROUP BY region",
        source="csv",
        tables=TABLES,
        models=[],
    )
    assert (s.table, s.model, s.measure_name, s.measure_exists) == ("ventas", None, "venta_neta", False)
    assert s.measure_sql == "SUM(monto - descuento)"
    assert (s.dimension.name, s.dimension.column, s.dimension.type, s.dimension.exists) == (
        "region",
        "region",
        "nominal",
        False,
    )


def test_suggest_reuses_existing_model_names():
    model = SemanticModel.model_validate(MODEL)
    s = suggest_from_sql(
        "SELECT fecha AS dia, sum( monto-descuento ) FROM ventas WHERE canal = 'Web' GROUP BY 1",
        source="csv",
        tables=TABLES,
        models=[model],
    )
    assert s.model == "ventas"
    assert (s.measure_name, s.measure_exists) == ("venta_neta", True)  # same measure, other format
    assert (s.dimension.name, s.dimension.exists, s.dimension.type) == ("fecha", True, "temporal")
    assert any("WHERE" in w for w in s.warnings)


def test_suggest_kpi_without_dimension():
    s = suggest_from_sql("SELECT COUNT(*) AS pedidos FROM ventas", source="csv", tables=TABLES, models=[])
    assert s.dimension is None and s.measure_name == "pedidos"


@pytest.mark.parametrize(
    ("sql", "msg"),
    [
        ("SELECT region, SUM(monto) FROM ventas v JOIN otra o USING (region) GROUP BY 1", "joins"),
        ("WITH t AS (SELECT * FROM ventas) SELECT SUM(monto) FROM t", "CTE"),
        ("SELECT region, SUM(monto), COUNT(*) FROM ventas GROUP BY 1", "exactly one aggregate"),
        ("SELECT region, canal, SUM(monto) FROM ventas GROUP BY 1, 2", "at most one dimension"),
        ("SELECT region FROM ventas", "exactly one aggregate"),
        ("SELECT SUM(monto) FROM otra", "catalog"),
        ("SELECT SUM(monto) FROM ventas UNION ALL SELECT 1", "UNION"),
        ("SELECT upper(region), SUM(monto) FROM ventas GROUP BY 1", "neither a dimension nor an aggregate"),
        ("DELETE FROM ventas", "SELECT"),
    ],
)
def test_not_promotable(sql, msg):
    with pytest.raises(NotPromotable, match=msg):
        suggest_from_sql(sql, source="csv", tables=TABLES, models=[])


# ------------------------------------------------------------------ API


@pytest.fixture
def client(settings, csv_src):
    app.dependency_overrides[get_settings] = lambda: settings
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_api_model_lifecycle(client, settings):
    assert client.post("/api/semantic/check", json=MODEL).json() == []
    r = client.put("/api/semantic/ventas", json=MODEL)
    assert r.status_code == 200, r.text
    assert (
        yaml.safe_load((settings.semantic_dir / "ventas.yaml").read_text(encoding="utf-8"))["name"]
        == "ventas"
    )
    listing = client.get("/api/semantic").json()
    assert [e["model"]["name"] for e in listing["models"]] == ["ventas"] and listing["models"][0][
        "errors"
    ] == []
    assert client.put("/api/semantic/otro", json=MODEL).status_code == 422  # name does not match
    bad = MODEL | {"measures": {"m": {"sql": "SUM(no_existe)", "owner": "x", "description": "x"}}}
    r = client.put("/api/semantic/ventas", json=bad)
    assert r.status_code == 422 and "no_existe" in r.json()["detail"]
    bad_shape = MODEL | {"measures": {"m": {"sql": "monto", "owner": "x", "description": "x"}}}
    assert client.put("/api/semantic/ventas", json=bad_shape).status_code == 422  # the contract rejects it
    assert client.delete("/api/semantic/ventas").status_code == 204
    assert client.get("/api/semantic/ventas").status_code == 404


def test_api_visual_query(client):
    client.put("/api/semantic/ventas", json=MODEL)
    r = client.post(
        "/api/visual/query",
        json={"model": "ventas", "visual": {"mark": "bar", "measure": "venta_neta", "dimension": "region"}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rows"] == [["Sur", 280], ["Norte", 140]]
    assert body["allowed_marks"] == ["table", "bar", "pie"]
    assert "GROUP BY" in body["sql"]

    line = client.post(
        "/api/visual/query",
        json={
            "model": "ventas",
            "visual": {
                "mark": "line",
                "measure": "venta_neta",
                "dimension": "fecha",
                "time_grain": "month",
                "filters": [{"dimension": "region", "op": "eq", "value": "Norte"}],
            },
        },
    ).json()
    assert line["rows"] == [["2026-01-01", 140]]

    bad = client.post(
        "/api/visual/query",
        json={"model": "ventas", "visual": {"mark": "line", "measure": "venta_neta", "dimension": "region"}},
    )
    assert bad.status_code == 422 and "not compatible" in bad.json()["detail"]
    assert (
        client.post(
            "/api/visual/query", json={"model": "nope", "visual": {"mark": "kpi", "measure": "venta_neta"}}
        ).status_code
        == 404
    )


def test_api_suggest(client):
    r = client.post(
        "/api/semantic/suggest",
        json={"source": "csv", "sql": "SELECT region, SUM(monto) AS bruto FROM ventas GROUP BY region"},
    )
    assert r.status_code == 200 and r.json()["measure_name"] == "bruto"
    r = client.post("/api/semantic/suggest", json={"source": "csv", "sql": "SELECT * FROM ventas"})
    assert r.status_code == 422 and "cannot be promoted" in r.json()["detail"]


def test_saving_keeps_hand_written_comments(settings):
    """ADR 0008 follow-up: the studio updates the YAML in place instead of rewriting it."""
    from pathlib import Path

    example = Path(__file__).resolve().parents[2] / "examples/semantic/ventas.yaml"
    store = ModelStore(settings.semantic_dir)
    settings.semantic_dir.mkdir(parents=True)
    target = settings.semantic_dir / "ventas.yaml"
    target.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")

    m = store.get("ventas")
    data = m.model_dump(mode="json")
    data["measures"]["venta_neta"]["description"] = "Venta bruta menos descuentos (sin IVA)"
    del data["measures"]["pedidos"]
    data["measures"]["ticket"] = {"sql": "AVG(monto_bruto)", "owner": "finanzas", "description": "Ticket"}
    store.put(SemanticModel.model_validate(data))

    text = target.read_text(encoding="utf-8")
    assert "# Example semantic model. Measures are defined HERE, once." in text
    assert "# registered connection id; credentials in .env" in text  # an inline comment survives
    assert "{ column: canal,       type: nominal }" in text or "{column: canal, type: nominal}" in text
    assert "Venta bruta menos descuentos (sin IVA)" in text and "ticket:" in text and "pedidos:" not in text
    assert "format: number" not in text  # defaults are not written
    assert store.get("ventas") == SemanticModel.model_validate(data)


def test_saving_a_broken_file_rewrites_it(settings):
    store = ModelStore(settings.semantic_dir)
    settings.semantic_dir.mkdir(parents=True)
    (settings.semantic_dir / "ventas.yaml").write_text("name: [unclosed\n", encoding="utf-8")
    store.put(SemanticModel.model_validate(MODEL))
    assert store.get("ventas") == SemanticModel.model_validate(MODEL)


def test_dimension_over_a_computed_column(client):
    r = client.put("/api/catalog/csv/ventas/computed", json={"name": "zona", "expr": "upper(region)"})
    assert r.status_code == 200, r.text
    model = MODEL | {"dimensions": MODEL["dimensions"] | {"zona": {"column": "zona", "type": "nominal"}}}
    assert client.post("/api/semantic/check", json=model).json() == []
    assert client.put("/api/semantic/ventas", json=model).status_code == 200
    r = client.post("/api/visual/query", json={"model": "ventas", "visual": {
        "mark": "bar", "measure": "venta_neta", "dimension": "zona",
        "filters": [{"dimension": "zona", "op": "eq", "value": "NORTE"}]}})
    assert r.status_code == 200, r.text
    assert r.json()["rows"] == [["NORTE", 140.0]]
    assert 'UPPER("region")' in r.json()["sql"]  # the expression, not a column "zona"


def test_rls_column_cannot_be_computed(client):
    client.put("/api/catalog/csv/ventas/computed", json={"name": "zona", "expr": "upper(region)"})
    model = MODEL | {"rls": {"column": "zona", "claim": "groups"}}
    errors = client.post("/api/semantic/check", json=model).json()
    assert any("RLS needs a physical column" in e for e in errors)
