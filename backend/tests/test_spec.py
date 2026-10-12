import pytest
from pydantic import ValidationError

from data2html.spec import Report, SemanticModel, validate_report
from data2html.spec.export import DEFAULT_OUT, build_schema, render_schema


def test_examples_are_valid(model, report_data):
    assert validate_report(Report.model_validate(report_data), model) == []


def test_unknown_field_is_rejected(report_data):
    report_data["visuals"][0]["colour"] = "region"
    with pytest.raises(ValidationError):
        Report.model_validate(report_data)


def test_duplicate_visual_ids(report_data):
    report_data["visuals"][1]["id"] = "total"
    with pytest.raises(ValidationError, match="duplicados"):
        Report.model_validate(report_data)


def test_measure_sql_in_visual_is_rejected(model, report_data):
    report_data["visuals"][1]["measure"] = "SUM(monto)"
    with pytest.raises(ValidationError):  # no es un identificador válido
        Report.model_validate(report_data)


def test_unknown_measure_and_undeclared_param(model, report_data):
    report_data["visuals"][1]["measure"] = "margen"
    report_data["params"] = {}
    errors = validate_report(Report.model_validate(report_data), model)
    assert any("medida desconocida 'margen'" in e for e in errors)
    assert any("parámetro no declarado 'anio'" in e for e in errors)


def test_incompatible_mark(model, report_data):
    report_data["visuals"][1]["mark"] = "line"  # región es nominal
    errors = validate_report(Report.model_validate(report_data), model)
    assert any("no compatible" in e for e in errors)


def test_dimension_measure_clash(model):
    data = model.model_dump(mode="json")
    data["measures"]["region"] = data["measures"]["venta_neta"]
    with pytest.raises(ValidationError, match="dimensión y medida"):
        SemanticModel.model_validate(data)


def test_measure_with_semicolon(model):
    data = model.model_dump(mode="json")
    data["measures"]["venta_neta"]["sql"] = "SUM(x); DROP TABLE t"
    with pytest.raises(ValidationError):
        SemanticModel.model_validate(data)


def test_schema_exports_both_roots():
    defs = build_schema()["$defs"]
    assert "Report" in defs and "SemanticModel" in defs


def test_committed_schema_is_up_to_date():
    # Si falla: python -m data2html.spec.export
    committed = DEFAULT_OUT.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert committed == render_schema()


# ---------------------------------------------------------------- Fase 5: cambios de contrato


@pytest.mark.parametrize("sql", [
    "SUM(monto_bruto - descuento)",
    "COUNT(*)",
    "COUNT(DISTINCT pedido_id)",
    "SUM(monto_bruto) / NULLIF(COUNT(*), 0)",
    "SUM(CASE WHEN canal = 'Web' THEN monto_bruto ELSE 0 END)",
    "AVG(monto_bruto) FILTER (WHERE descuento > 0)",
])
def test_valid_measures(model, sql):
    data = model.model_dump(mode="json")
    data["measures"]["venta_neta"]["sql"] = sql
    SemanticModel.model_validate(data)


@pytest.mark.parametrize(("sql", "msg"), [
    ("monto_bruto", "debe agregar"),
    ("SUM(monto_bruto) + descuento", "fuera de un agregado"),
    ("(SELECT max(monto_bruto) FROM fact_ventas)", "no se permite"),
    ("SUM(monto_bruto) OVER ()", "no se permite"),
    ("SUM(read_text('x'))", "no permitida"),
    ("SUM(t.monto_bruto)", "sin prefijo"),
    ("SUM(*)", "COUNT"),
    ("SUM(", "inválida"),
])
def test_invalid_measures(model, sql, msg):
    data = model.model_dump(mode="json")
    data["measures"]["venta_neta"]["sql"] = sql
    with pytest.raises(ValidationError, match=msg):
        SemanticModel.model_validate(data)


@pytest.mark.parametrize("f", [
    {"dimension": "canal", "op": "eq", "value": "Web"},
    {"dimension": "canal", "op": "in", "value": ["Web", "Tienda"]},
    {"dimension": "fecha", "op": "between", "value": ["2025-01-01", "2025-06-30"]},
    {"dimension": "fecha", "op": "gte", "param": "anio"},
])
def test_filter_value_or_param(report_data, f):
    report_data["visuals"][1]["filters"] = [f]
    Report.model_validate(report_data)


@pytest.mark.parametrize("f", [
    {"dimension": "canal", "op": "eq"},                                       # ni param ni value
    {"dimension": "canal", "op": "eq", "param": "anio", "value": "x"},         # los dos
    {"dimension": "fecha", "op": "between", "value": ["2025-01-01"]},
    {"dimension": "canal", "op": "in", "value": []},
    {"dimension": "canal", "op": "eq", "value": ["a", "b"]},
    {"dimension": "canal", "op": "like", "value": "W%"},
])
def test_filter_rejections(report_data, f):
    report_data["visuals"][1]["filters"] = [f]
    with pytest.raises(ValidationError):
        Report.model_validate(report_data)


def test_time_grain_only_on_temporal(model, report_data):
    report_data["visuals"][1]["time_grain"] = "month"  # región es nominal
    errors = validate_report(Report.model_validate(report_data), model)
    assert any("time_grain" in e for e in errors)
    report_data["visuals"][1]["time_grain"] = "fortnight"
    with pytest.raises(ValidationError):
        Report.model_validate(report_data)
