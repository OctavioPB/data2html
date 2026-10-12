import pytest
from fastapi.testclient import TestClient

from data2html import __version__
from data2html.api.main import app, get_settings
from data2html.api.openapi import DEFAULT_OUT, render_openapi
from data2html.settings import Settings

CSV = b"region,monto\nNorte,10\nSur,20\n"


@pytest.fixture
def client(tmp_path):
    app.dependency_overrides[get_settings] = lambda: Settings(data_dir=tmp_path, max_upload_mb=1)
    yield TestClient(app)
    app.dependency_overrides.clear()


def _upload(client, body: bytes = CSV, name: str = "ventas.csv"):
    return client.post("/api/csv/preview", files={"file": (name, body, "text/csv")})


def _confirm(client, preview: dict, table: str = "ventas"):
    cols = [{k: c[k] for k in ("name", "type", "date_format", "decimal_comma")} for c in preview["columns"]]
    body = {"upload_id": preview["upload_id"], "table": table, "columns": cols}
    return client.post("/api/csv/confirm", json=body)


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "version": __version__}


def test_catalog_starts_empty(client):
    assert client.get("/api/catalog").json() == {"sources": [{"id": "csv", "kind": "csv", "tables": []}]}


def test_csv_upload_flow(client):
    r = _upload(client)
    assert r.status_code == 200
    preview = r.json()
    cols = [(c["name"], c["type"]) for c in preview["columns"]]
    assert cols == [("region", "VARCHAR"), ("monto", "BIGINT")]

    r = _confirm(client, preview)
    assert r.status_code == 201
    assert r.json()["row_count"] == 2

    tables = client.get("/api/catalog").json()["sources"][0]["tables"]
    assert [t["name"] for t in tables] == ["ventas"]
    assert _confirm(client, _upload(client).json()).status_code == 409


def test_patch_descriptions(client):
    _confirm(client, _upload(client).json())
    r = client.patch("/api/catalog/csv/ventas", json={"description": "Ventas diarias",
                                                      "columns": {"monto": "Importe neto en MXN"}})
    assert r.status_code == 200
    t = client.get("/api/catalog").json()["sources"][0]["tables"][0]
    assert t["description"] == "Ventas diarias"
    descs = {c["name"]: c["description"] for c in t["columns"]}
    assert descs == {"region": "", "monto": "Importe neto en MXN"}

    assert client.patch("/api/catalog/csv/ventas", json={"columns": {"nope": "x"}}).status_code == 422
    assert client.patch("/api/catalog/csv/otra", json={"description": "x"}).status_code == 404
    assert client.patch("/api/catalog/pg/ventas", json={"description": "x"}).status_code == 404


@pytest.mark.parametrize("table", ["Ventas", "1ventas", "ventas;drop", "../x", ""])
def test_confirm_rejects_bad_table_names(client, table):
    assert _confirm(client, _upload(client).json(), table=table).status_code == 422


def test_upload_too_large(client):
    assert _upload(client, b"a\n" + b"1\n" * 600_000).status_code == 413


def test_discard_upload(client):
    up = _upload(client).json()["upload_id"]
    assert client.delete(f"/api/csv/uploads/{up}").status_code == 204
    assert client.delete(f"/api/csv/uploads/{up}").status_code == 404


def test_compat_rejects_unknown_dimension(client):
    assert client.get("/api/compat", params={"dimension": "nope"}).status_code == 422


def test_committed_openapi_is_up_to_date():
    # Si falla: python -m data2html.api.openapi && (cd studio && npm run gen:api)
    committed = DEFAULT_OUT.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert committed == render_openapi()
