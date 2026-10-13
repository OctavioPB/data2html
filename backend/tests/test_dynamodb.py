"""DynamoDB Import (ADR 0012) without AWS: botocore's Stubber plays DynamoDB and S3, and the export
files (manifests + gzipped DynamoDB JSON) are built here."""

import gzip
import io
import json
from datetime import UTC, datetime

import boto3
import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber
from pydantic import ValidationError

from data2html.ingest.dynamodb import DynamoIngest, IngestError, ddb_value, extract, plain_text
from data2html.settings import Settings
from data2html.sources.catalog_meta import CatalogMeta
from data2html.sources.dynamodb import DynamoDBSource
from data2html.sources.registry import DynamoDBConfig, SourcesFile

ARN = "arn:aws:dynamodb:us-east-1:123456789012:table/Orders"
EXPORT_ARN = ARN + "/export/01700000000000-abcdef12"
ROOT = "exports/AWSDynamoDB/01700000000000-abcdef12/"

CFG = {
    "type": "dynamodb_export",
    "region": "us-east-1",
    "tables": {
        "pedidos": {
            "table_arn": ARN, "s3_bucket": "d2h-exports", "s3_prefix": "exports",
            "columns": {
                "pedido_id": {"path": "pk"},
                "monto": {"path": "amount", "type": "DECIMAL(12,2)"},
                "fecha": {"path": "created", "type": "DATE"},
                "ts": {"path": "ts", "type": "TIMESTAMP", "unit": "epoch_s"},
                "region": {"path": "customer.region"},
                "tier": {"path": "customer.tier", "type": "BIGINT"},
                "items": {"path": "items", "type": "JSON"},
                "tags": {"path": "tags", "type": "JSON"},
                "vip": {"path": "vip", "type": "BOOLEAN"},
            },
        }
    },
}

ITEMS_1 = [
    {"pk": {"S": "P-1"}, "amount": {"N": "120.50"}, "created": {"S": "2026-01-05"}, "ts": {"N": "1767225600"},
     "customer": {"M": {"region": {"S": "Norte"}, "tier": {"N": "2"}}},
     "items": {"L": [{"M": {"sku": {"S": "A"}, "qty": {"N": "2"}}}]}, "tags": {"SS": ["x", "y"]},
     "vip": {"BOOL": True}, "secret": {"S": "not declared, never exported"}},
    {"pk": {"S": "P-2"}, "amount": {"S": "n/a"}, "created": {"S": "2026-02-30"},
     "customer": {"M": {"region": {"S": "Bajío"}}}, "vip": {"NULL": True}},
]
ITEMS_2 = [{"pk": {"S": "P-3"}}]


def _gz_lines(items):
    return gzip.compress("\n".join(json.dumps({"Item": i}) for i in items).encode())


def _body(data: bytes) -> StreamingBody:
    return StreamingBody(io.BytesIO(data), len(data))


def _export_description(status: str, **extra):
    return {"ExportDescription": {"ExportArn": EXPORT_ARN, "ExportStatus": status, "TableArn": ARN,
                                  "ExportTime": datetime(2026, 10, 12, tzinfo=UTC), **extra}}


class FakeAws:
    def __init__(self):
        creds = {"region_name": "us-east-1", "aws_access_key_id": "x", "aws_secret_access_key": "x"}
        self.ddb = boto3.client("dynamodb", **creds)
        self.s3 = boto3.client("s3", **creds)
        self.ddb_stub = Stubber(self.ddb)
        self.s3_stub = Stubber(self.s3)

    def export_ok(self, data_keys=None, status_flow=("IN_PROGRESS", "COMPLETED")):
        self.ddb_stub.add_response("export_table_to_point_in_time", _export_description(status_flow[0]))
        for st in status_flow[1:]:
            extra = {"ExportManifest": ROOT + "manifest-summary.json"} if st == "COMPLETED" else {}
            self.ddb_stub.add_response("describe_export", _export_description(st, **extra),
                                       {"ExportArn": EXPORT_ARN})
        keys = data_keys or [ROOT + "data/a.json.gz", ROOT + "data/b.json.gz"]
        self._get(ROOT + "manifest-summary.json",
                  json.dumps({"manifestFilesS3Key": ROOT + "manifest-files.json"}).encode())
        files = "\n".join(json.dumps({"dataFileS3Key": k}) for k in keys)
        self._get(ROOT + "manifest-files.json", files.encode())
        for k, items in zip(keys, [ITEMS_1, ITEMS_2], strict=False):
            if k.startswith(ROOT):
                self._get(k, _gz_lines(items))

    def _get(self, key, data):
        self.s3_stub.add_response("get_object", {"Body": _body(data)}, {"Bucket": "d2h-exports", "Key": key})

    def __enter__(self):
        self.ddb_stub.activate()
        self.s3_stub.activate()
        return self

    def __exit__(self, *exc):
        self.ddb_stub.deactivate()
        self.s3_stub.deactivate()


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path, duckdb_memory_limit="256MB", duckdb_threads=1)


@pytest.fixture
def cfg():
    return DynamoDBConfig.model_validate(CFG)


def ingest(settings, cfg, aws):
    return DynamoIngest("ventas_ddb", cfg, settings, dynamodb=aws.ddb, s3=aws.s3, sleep=lambda s: None)


# ------------------------------------------------------------------ conversion helpers


def test_ddb_value_and_plain_text():
    assert ddb_value({"N": "12.50"}) == 12.5 and ddb_value({"N": "3"}) == 3
    nested = {"M": {"a": {"L": [{"S": "x"}, {"BOOL": False}, {"NULL": True}]}}}
    assert ddb_value(nested) == {"a": ["x", False, None]}
    assert ddb_value({"NS": ["1", "2.5"]}) == [1, 2.5]
    cfg = DynamoDBConfig.model_validate(CFG).tables["pedidos"].columns
    assert plain_text({"SS": ["b", "a"]}, cfg["tags"]) == '["b","a"]'
    assert plain_text({"N": "120.50"}, cfg["monto"]) == "120.50"  # exact digits, no float rounding
    assert plain_text({"BOOL": True}, cfg["vip"]) == "true"
    assert plain_text({"NULL": True}, cfg["vip"]) is None and plain_text(None, cfg["vip"]) is None


def test_extract_follows_nested_maps():
    item = {"customer": {"M": {"address": {"M": {"city": {"S": "León"}}}}}, "pk": {"S": "P"}}
    assert extract(item, "pk") == {"S": "P"}
    assert extract(item, "customer.address.city") == {"S": "León"}
    assert extract(item, "customer.phone") is None and extract(item, "pk.x") is None


@pytest.mark.parametrize("bad", [
    {"path": 'a"b'}, {"path": "a..b"}, {"path": "a;DROP"}, {"path": "x", "type": "TEXT"},
    {"path": "x", "type": "DECIMAL(12,2); DROP"},
])
def test_column_config_is_validated(bad):
    data = json.loads(json.dumps(CFG))
    data["tables"]["pedidos"]["columns"] = {"c": bad}
    with pytest.raises(ValidationError):
        DynamoDBConfig.model_validate(data)


def test_source_config_rejects_secrets_and_bad_arns():
    for change in [{"aws_secret_access_key": "x"}, {"region": "us-east-1; rm"}]:
        with pytest.raises(ValidationError):
            SourcesFile.model_validate({"sources": {"d": CFG | change}})
    bad = json.loads(json.dumps(CFG))
    bad["tables"]["pedidos"]["table_arn"] = "arn:aws:s3:::bucket"
    with pytest.raises(ValidationError):
        DynamoDBConfig.model_validate(bad)


# ------------------------------------------------------------------ the pipeline


def test_full_ingest_then_query(settings, cfg):
    with FakeAws() as aws:
        aws.export_ok()
        result = ingest(settings, cfg, aws).run("pedidos")
        aws.ddb_stub.assert_no_pending_responses()
        aws.s3_stub.assert_no_pending_responses()
    assert result.rows == 3 and result.export_arn == EXPORT_ARN
    assert result.warnings == {"monto": 1, "fecha": 1}  # "n/a" and 2026-02-30 did not convert

    src = DynamoDBSource("ventas_ddb", cfg, settings, CatalogMeta(settings.catalog_meta_path))
    (info,) = src.catalog()
    assert info.name == "pedidos" and info.row_count == 3
    # only the declared columns: the item's "secret" attribute is not there
    assert [c.name for c in info.columns] == list(CFG["tables"]["pedidos"]["columns"])
    table = src.execute("SELECT * FROM pedidos ORDER BY pedido_id", {}, identity=None, timeout_s=10)
    rows = table.to_pylist()
    p1, p2, p3 = rows
    assert str(p1["monto"]) == "120.50" and str(p1["fecha"]) == "2026-01-05"
    assert p1["ts"] == datetime(2026, 1, 1, 0, 0)  # epoch 1767225600 in UTC, whatever the server's zone
    assert (p1["region"], p1["tier"], p1["vip"]) == ("Norte", 2, True)
    assert json.loads(p1["items"]) == [{"sku": "A", "qty": 2}] and json.loads(p1["tags"]) == ["x", "y"]
    assert (p2["region"], p2["monto"], p2["fecha"], p2["vip"]) == ("Bajío", None, None, None)
    assert p3["pedido_id"] == "P-3" and p3["region"] is None
    assert src.last_export("pedidos")["rows"] == 3
    # staging and lock are gone
    assert not list((settings.data_dir / "ingest").rglob("*.json.gz"))
    assert not (settings.data_dir / "dynamodb/ventas_ddb/pedidos.lock").exists()


def test_rejects_data_files_outside_the_export(settings, cfg):
    with FakeAws() as aws:
        aws.export_ok(data_keys=[ROOT + "data/a.json.gz", "other-bucket-path/evil.json.gz"])
        with pytest.raises(IngestError, match="outside the export"):
            ingest(settings, cfg, aws).run("pedidos")
    assert not (settings.data_dir / "dynamodb/ventas_ddb/pedidos.parquet").exists()


def test_failed_export_keeps_the_previous_parquet(settings, cfg):
    with FakeAws() as aws:
        aws.export_ok()
        ingest(settings, cfg, aws).run("pedidos")
    parquet = settings.data_dir / "dynamodb/ventas_ddb/pedidos.parquet"
    before = parquet.read_bytes()
    with FakeAws() as aws:
        aws.ddb_stub.add_response("export_table_to_point_in_time", _export_description("IN_PROGRESS"))
        aws.ddb_stub.add_response("describe_export", _export_description(
            "FAILED", FailureCode="PITR_DISABLED", FailureMessage="enable point-in-time recovery"),
            {"ExportArn": EXPORT_ARN})
        with pytest.raises(IngestError, match="PITR_DISABLED"):
            ingest(settings, cfg, aws).run("pedidos")
    assert parquet.read_bytes() == before


def test_one_export_at_a_time(settings, cfg):
    lock = settings.data_dir / "dynamodb/ventas_ddb/pedidos.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("")
    with FakeAws() as aws, pytest.raises(IngestError, match="already running"):
        ingest(settings, cfg, aws).run("pedidos")
    with FakeAws() as aws, pytest.raises(IngestError, match="not configured"):
        ingest(settings, cfg, aws).run("otra")


def test_unexported_tables_are_not_listed(settings, cfg):
    src = DynamoDBSource("ventas_ddb", cfg, settings, CatalogMeta(settings.catalog_meta_path))
    assert src.catalog() == [] and src.last_export("pedidos") is None


# ------------------------------------------------------------------ the studio API


def test_api_status_and_export_now(tmp_path, monkeypatch):
    import time as _time

    import yaml
    from fastapi.testclient import TestClient

    from data2html.api import ingest as ingest_api
    from data2html.api.main import app, get_settings

    f = tmp_path / "sources.yaml"
    f.write_text(yaml.safe_dump({"sources": {"ventas_ddb": CFG}}), encoding="utf-8")
    s = Settings(data_dir=tmp_path, sources_file=f, duckdb_memory_limit="256MB", duckdb_threads=1)
    aws = FakeAws()
    aws.export_ok()

    def stubbed(src, settings):
        return DynamoIngest(src.id, src.cfg, settings, dynamodb=aws.ddb, s3=aws.s3, sleep=lambda _: None)

    monkeypatch.setattr(ingest_api, "make_ingest", stubbed)
    app.dependency_overrides[get_settings] = lambda: s
    try:
        c = TestClient(app)
        st = c.get("/api/ingest/ventas_ddb").json()
        assert st["tables"] == [{"table": "pedidos", "running": False, "last": None, "error": None}]
        with aws:
            assert c.post("/api/ingest/ventas_ddb/pedidos").status_code == 202
            for _ in range(100):
                st = c.get("/api/ingest/ventas_ddb").json()["tables"][0]
                if not st["running"]:
                    break
                _time.sleep(0.05)
        assert st["error"] is None and st["last"]["rows"] == 3
        assert st["last"]["warnings"] == {"monto": 1, "fecha": 1}
        cat = next(x for x in c.get("/api/catalog").json()["sources"] if x["id"] == "ventas_ddb")
        assert cat["kind"] == "dynamodb" and [t["name"] for t in cat["tables"]] == ["pedidos"]
        r = c.post("/api/explore/ventas_ddb/pedidos", json={"filters": [
            {"column": "region", "op": "=", "value": "Bajío"}]})
        assert r.status_code == 200 and r.json()["total"] == 1
        assert c.post("/api/ingest/ventas_ddb/otra").status_code == 404
        assert c.get("/api/ingest/csv").status_code == 404
    finally:
        app.dependency_overrides.clear()
