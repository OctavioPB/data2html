import datetime as dt
import decimal

import pytest
from fastapi.testclient import TestClient

from data2html.api.explore import to_cell
from data2html.api.main import app, get_settings
from data2html.settings import Settings

CSV = (
    b"region,monto,fecha\n"
    b"Norte,10,2026-01-05\n"
    b"Sur,25,2026-02-10\n"
    b"Norte,5,2026-03-15\n"
)


@pytest.fixture
def client(tmp_path):
    app.dependency_overrides[get_settings] = lambda: Settings(data_dir=tmp_path)
    c = TestClient(app)
    p = c.post("/api/csv/preview", files={"file": ("ventas.csv", CSV, "text/csv")}).json()
    cols = [{k: col[k] for k in ("name", "type", "date_format", "decimal_comma")} for col in p["columns"]]
    r = c.post("/api/csv/confirm", json={"upload_id": p["upload_id"], "table": "ventas", "columns": cols})
    assert r.status_code == 201
    yield c
    app.dependency_overrides.clear()


def explore(client, **body):
    return client.post("/api/explore/csv/ventas", json=body)


def test_first_page(client):
    r = explore(client, limit=2).json()
    assert r["total"] == 3 and r["offset"] == 0
    assert [c["name"] for c in r["columns"]] == ["region", "monto", "fecha"]
    assert r["rows"] == [["Norte", 10, "2026-01-05"], ["Sur", 25, "2026-02-10"]]


def test_next_page_without_total(client):
    r = explore(client, offset=2, limit=2, with_total=False).json()
    assert r["total"] is None and r["rows"] == [["Norte", 5, "2026-03-15"]]


def test_filter_sort_search(client):
    r = explore(client, filters=[{"column": "monto", "op": ">=", "value": 10}],
                sort=[{"column": "monto", "desc": True}], search="r").json()
    assert [row[0] for row in r["rows"]] == ["Sur", "Norte"] and r["total"] == 2


def test_bad_requests(client):
    assert explore(client, filters=[{"column": "nope", "op": "is_null"}]).status_code == 422
    assert explore(client, limit=100_000).status_code == 422
    bad_date = {"column": "fecha", "op": "=", "value": "no-es-fecha"}
    assert explore(client, filters=[bad_date]).status_code == 422
    assert client.post("/api/explore/csv/otra", json={}).status_code == 404
    assert client.post("/api/explore/pg/ventas", json={}).status_code == 404


def test_computed_column_lifecycle(client):
    r = client.put("/api/catalog/csv/ventas/computed", json={"name": "con_iva", "expr": "monto * 1.16"})
    assert r.status_code == 200
    (cc,) = r.json()["computed"]
    assert (cc["name"], cc["expr"]) == ("con_iva", "monto * 1.16") and cc["type"].startswith("DECIMAL")

    page = explore(client, sort=[{"column": "con_iva", "desc": True}], limit=1).json()
    assert page["columns"][-1] == {"name": "con_iva", "type": cc["type"], "computed": True}
    assert page["rows"][0][-1] == pytest.approx(29.0)

    # descriptions work for computed columns too
    r = client.patch("/api/catalog/csv/ventas", json={"columns": {"con_iva": "Monto con IVA"}})
    assert r.status_code == 200

    assert client.delete("/api/catalog/csv/ventas/computed/con_iva").json()["computed"] == []
    assert client.delete("/api/catalog/csv/ventas/computed/con_iva").status_code == 404


@pytest.mark.parametrize(("body", "msg"), [
    ({"name": "x", "expr": "read_text('/etc/passwd')"}, "not allowed"),
    ({"name": "x", "expr": "(SELECT 1)"}, "SUBQUERY"),
    ({"name": "x", "expr": "monto + region"}, ""),  # type error: DuckDB catches it on trial
    ({"name": "monto", "expr": "1"}, "already exists"),
    ({"name": "Mal Nombre", "expr": "1"}, ""),
])
def test_computed_rejected(client, body, msg):
    r = client.put("/api/catalog/csv/ventas/computed", json=body)
    assert r.status_code == 422
    assert msg in str(r.json()["detail"])


@pytest.mark.parametrize(("value", "cell"), [
    (None, None), (3, 3), (2**60, str(2**60)), (decimal.Decimal("1.5"), 1.5),
    (dt.date(2026, 1, 2), "2026-01-02"), (b"\x00\x01", "<binary, 2 bytes>"), ([1, 2], "[1, 2]"),
])
def test_to_cell(value, cell):
    assert to_cell(value) == cell


def test_computed_column_descriptions_round_trip(client):
    r = client.put("/api/catalog/csv/ventas/computed", json={"name": "neto", "expr": "monto - 1"})
    assert r.status_code == 200, r.text
    r = client.patch("/api/catalog/csv/ventas", json={"columns": {"neto": "Monto menos un peso"}})
    assert r.status_code == 200, r.text
    (neto,) = r.json()["computed"]
    assert (neto["name"], neto["description"]) == ("neto", "Monto menos un peso")
    cat = next(s for s in client.get("/api/catalog").json()["sources"] if s["id"] == "csv")
    ventas = next(t for t in cat["tables"] if t["name"] == "ventas")
    assert ventas["computed"][0]["description"] == "Monto menos un peso"
