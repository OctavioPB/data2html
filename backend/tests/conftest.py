import copy
import io
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from data2html.api.main import app, get_settings
from data2html.auth import require_author
from data2html.settings import Settings
from data2html.sources.base import Identity
from data2html.sources.catalog_meta import CatalogMeta
from data2html.sources.csv_source import ConfirmRequest, CsvSource
from data2html.spec import SemanticModel

AUTHOR = Identity(user_id="autora", email="autora@example.com", provider="local", author=True)


def pytest_configure(config):
    config.addinivalue_line("markers", "real_auth: do not bypass the studio's author check")


@pytest.fixture(autouse=True)
def _author_session(request):
    """Studio routes require an author session (ADR 0010). Tests about something else get one for free;
    tests marked `real_auth` go through the real sign-in."""
    if request.node.get_closest_marker("real_auth"):
        app.dependency_overrides.pop(require_author, None)
        yield
        return
    app.dependency_overrides[require_author] = lambda: AUTHOR
    yield
    app.dependency_overrides.pop(require_author, None)


EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


@pytest.fixture
def model() -> SemanticModel:
    data = yaml.safe_load((EXAMPLES / "semantic/ventas.yaml").read_text(encoding="utf-8"))
    return SemanticModel.model_validate(data)


@pytest.fixture
def report_data() -> dict:
    return yaml.safe_load((EXAMPLES / "reports/ventas_regionales.yaml").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ viewer (Phase 6)

VIEWER_CSV = (
    b"region,canal,fecha,monto\n"
    b"Norte,Web,2026-01-05,11111\n"
    b"Norte,Tienda,2026-02-20,22222\n"
    b"Sur,Web,2026-02-10,33333\n"
    b"Sur,Tienda,2026-03-01,44444\n"
)

VIEWER_MODEL = {
    "name": "ventas",
    "source": "csv",
    "table": "ventas",
    "dimensions": {
        "region": {"column": "region", "type": "nominal"},
        "canal": {"column": "canal", "type": "nominal"},
        "fecha": {"column": "fecha", "type": "temporal"},
    },
    "measures": {"venta": {"sql": "SUM(monto)", "owner": "finanzas", "description": "Venta"}},
    "rls": {"column": "region", "claim": "groups"},
}

VIEWER_REPORT = {
    "id": "regional",
    "title": "Regional",
    "semantic_model": "ventas",
    "params": {"desde": {"type": "date", "default": "2026-01-01"}},
    "visuals": [
        {"id": "por_region", "title": "Por región", "mark": "bar", "dimension": "region", "measure": "venta",
         "filters": [{"dimension": "fecha", "op": "gte", "param": "desde"}],
         "layout": {"x": 0, "y": 0, "w": 6, "h": 4}},
        {"id": "total", "title": "Total", "mark": "kpi", "measure": "venta",
         "layout": {"x": 6, "y": 0, "w": 6, "h": 2}},
    ],
}

DEV_IDENTITIES = {
    "identities": {
        "norte": {"email": "n@example.com", "groups": ["Norte"]},
        "sur": {"email": "s@example.com", "groups": ["Sur"]},
        "ambas": {"email": "a@example.com", "groups": ["Norte", "Sur"]},
        "nadie": {"email": "x@example.com"},
    }
}


def viewer_base_settings(tmp_path, **kw):
    dev = tmp_path / "dev_identities.yaml"
    dev.write_text(yaml.safe_dump(DEV_IDENTITIES), encoding="utf-8")
    base = {"data_dir": tmp_path, "content_dir": tmp_path / "content", "dev_identities_file": dev,
            "dev_hosts": ("testclient",)}
    return Settings(**(base | kw))


def publish_report(settings, report):
    (settings.semantic_dir).mkdir(parents=True, exist_ok=True)
    (settings.semantic_dir / "ventas.yaml").write_text(yaml.safe_dump(VIEWER_MODEL), encoding="utf-8")
    (settings.reports_dir).mkdir(parents=True, exist_ok=True)
    (settings.reports_dir / f"{report['id']}.yaml").write_text(yaml.safe_dump(report, allow_unicode=True),
                                                                encoding="utf-8")


@pytest.fixture
def report_dict() -> dict:
    return copy.deepcopy(VIEWER_REPORT)


@pytest.fixture
def viewer_settings(tmp_path) -> Settings:
    """CSV table `ventas`, model `ventas` (RLS by groups) and report `regional`, published."""
    s = viewer_base_settings(tmp_path)
    src = CsvSource(s, CatalogMeta(s.catalog_meta_path))
    p = src.preview(src.stage(io.BytesIO(VIEWER_CSV), "ventas.csv"))
    src.confirm(ConfirmRequest(upload_id=p.upload_id, table="ventas",
                               columns=[c.model_dump(exclude={"warnings"}) for c in p.columns]))
    publish_report(s, VIEWER_REPORT)
    return s


@pytest.fixture
def viewer_app(viewer_settings):
    app.dependency_overrides[get_settings] = lambda: viewer_settings
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def publish(viewer_settings):
    """Write a report dict as published content (bypassing the studio's validation)."""
    return lambda report: publish_report(viewer_settings, report)
