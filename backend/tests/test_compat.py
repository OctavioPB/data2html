import pytest
from fastapi.testclient import TestClient

from data2html.api.main import app
from data2html.spec import FieldType, Mark, allowed_marks


@pytest.mark.parametrize(
    ("dim", "color", "expected"),
    [
        (None, False, {Mark.kpi, Mark.table}),
        (FieldType.nominal, False, {Mark.table, Mark.bar, Mark.pie}),
        (FieldType.nominal, True, {Mark.table, Mark.bar}),
        (FieldType.temporal, False, {Mark.table, Mark.bar, Mark.line}),
        (FieldType.ordinal, False, {Mark.table, Mark.bar, Mark.line}),
        (FieldType.quantitative, False, {Mark.table}),
    ],
)
def test_allowed_marks(dim, color, expected):
    assert set(allowed_marks(dim, has_color=color)) == expected


def test_table_is_always_allowed():
    for dim in [None, *FieldType]:
        assert Mark.table in allowed_marks(dim)


def test_api_health_and_compat():
    c = TestClient(app)
    assert c.get("/health").json()["status"] == "ok"
    marks = c.get("/api/compat", params={"dimension": "temporal"}).json()["marks"]
    assert set(marks) == {"table", "bar", "line"}
