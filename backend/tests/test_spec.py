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
