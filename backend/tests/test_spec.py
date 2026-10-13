import pytest
from pydantic import ValidationError

from data2html.spec import (
    Param,
    ParamType,
    ParamValueError,
    Report,
    SemanticModel,
    coerce_param,
    validate_report,
)
from data2html.spec.export import DEFAULT_OUT, build_schema, render_schema


def test_examples_are_valid(model, report_data):
    assert validate_report(Report.model_validate(report_data), model) == []


def test_unknown_field_is_rejected(report_data):
    report_data["visuals"][0]["colour"] = "region"
    with pytest.raises(ValidationError):
        Report.model_validate(report_data)


def test_duplicate_visual_ids(report_data):
    report_data["visuals"][1]["id"] = "total"
    with pytest.raises(ValidationError, match="duplicate"):
        Report.model_validate(report_data)


def test_measure_sql_in_visual_is_rejected(model, report_data):
    report_data["visuals"][1]["measure"] = "SUM(monto)"
    with pytest.raises(ValidationError):  # not a valid identifier
        Report.model_validate(report_data)


def test_unknown_measure_and_undeclared_param(model, report_data):
    report_data["visuals"][1]["measure"] = "margen"
    report_data["params"] = {}
    errors = validate_report(Report.model_validate(report_data), model)
    assert any("unknown measure 'margen'" in e for e in errors)
    assert any("undeclared parameter 'desde'" in e for e in errors)


def test_incompatible_mark(model, report_data):
    report_data["visuals"][1]["mark"] = "line"  # region is nominal
    errors = validate_report(Report.model_validate(report_data), model)
    assert any("not compatible" in e for e in errors)


def test_dimension_measure_clash(model):
    data = model.model_dump(mode="json")
    data["measures"]["region"] = data["measures"]["venta_neta"]
    with pytest.raises(ValidationError, match="both dimension and measure"):
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
    # If this fails: python -m data2html.spec.export
    committed = DEFAULT_OUT.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert committed == render_schema()


# ---------------------------------------------------------------- Phase 5: contract changes


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
    ("monto_bruto", "must aggregate"),
    ("SUM(monto_bruto) + descuento", "outside an aggregate"),
    ("(SELECT max(monto_bruto) FROM fact_ventas)", "is not allowed"),
    ("SUM(monto_bruto) OVER ()", "is not allowed"),
    ("SUM(read_text('x'))", "not allowed"),
    ("SUM(t.monto_bruto)", "without a prefix"),
    ("SUM(*)", "COUNT"),
    ("SUM(", "invalid expression"),
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
    {"dimension": "fecha", "op": "gte", "param": "desde"},
])
def test_filter_value_or_param(report_data, f):
    report_data["visuals"][1]["filters"] = [f]
    Report.model_validate(report_data)


@pytest.mark.parametrize("f", [
    {"dimension": "canal", "op": "eq"},                                       # neither param nor value
    {"dimension": "canal", "op": "eq", "param": "desde", "value": "x"},         # both
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
    report_data["visuals"][1]["time_grain"] = "month"  # region is nominal
    errors = validate_report(Report.model_validate(report_data), model)
    assert any("time_grain" in e for e in errors)
    report_data["visuals"][1]["time_grain"] = "fortnight"
    with pytest.raises(ValidationError):
        Report.model_validate(report_data)


# ---------------------------------------------------------------- Phase 6: typed params and access


def test_param_shorthand_and_full_form(report_data):
    report_data["params"] = {"desde": "date", "n": {"type": "int", "default": 5, "label": "Top"}}
    r = Report.model_validate(report_data)
    assert r.param("desde") == Param(type=ParamType.date)
    assert r.param("n").default == 5 and r.param("n").label == "Top"


@pytest.mark.parametrize("p", [
    "datetime",                                   # unknown type
    {"type": "date", "default": "31/12/2025"},    # default does not parse
    {"type": "int", "default": "x"},
    {"type": "int", "required": True},            # unknown field
])
def test_param_rejections(report_data, p):
    report_data["params"] = {"desde": p}
    with pytest.raises(ValidationError):
        Report.model_validate(report_data)


@pytest.mark.parametrize(("type_", "raw", "expected"), [
    (ParamType.int, "42", 42),
    (ParamType.float, "1.5", 1.5),
    (ParamType.date, "2025-03-01", "2025-03-01"),
    (ParamType.bool, "true", True),
    (ParamType.bool, "0", False),
    (ParamType.str, "Norte", "Norte"),
])
def test_coerce_param(type_, raw, expected):
    assert coerce_param(type_, raw) == expected


@pytest.mark.parametrize(("type_", "raw"), [
    (ParamType.int, "4.2"), (ParamType.int, True), (ParamType.date, "2025-13-01"),
    (ParamType.date, "1; DROP"), (ParamType.bool, "yes"),
])
def test_coerce_param_rejections(type_, raw):
    with pytest.raises(ParamValueError):
        coerce_param(type_, raw)


def test_param_type_must_fit_the_dimension(model, report_data):
    report_data["params"] = {"desde": "int"}      # filters fecha (temporal)
    errors = validate_report(Report.model_validate(report_data), model)
    assert any("cannot filter 'fecha'" in e for e in errors)


def test_access_groups(report_data):
    report_data["access"] = ["Norte", "Direccion"]
    assert Report.model_validate(report_data).access == ("Norte", "Direccion")
    assert Report.model_validate({**report_data, "access": []}).access == ()
