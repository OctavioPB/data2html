import pytest
from pydantic import ValidationError

from data2html.sources.csv_source import (
    ColumnChoice,
    CsvType,
    DateFormat,
    guess_column,
    suggest_table_name,
)


@pytest.mark.parametrize(
    ("values", "type_", "fmt", "comma"),
    [
        (["1", "-2", "", None], CsvType.BIGINT, None, False),
        (["1.5", "2", ".5"], CsvType.DOUBLE, None, False),
        (["1,5", "1.234,75", "3"], CsvType.DOUBLE, None, True),
        (["true", "FALSE"], CsvType.BOOLEAN, None, False),
        (["2026-01-31", "2026-02-01"], CsvType.DATE, DateFormat.iso, False),
        (["2026-01-31 10:00", "2026-02-01T08:30:00"], CsvType.TIMESTAMP, None, False),
        (["13/04/2026", "03/04/2026"], CsvType.DATE, DateFormat.dmy_slash, False),
        (["04/13/2026", "04/03/2026"], CsvType.DATE, DateFormat.mdy_slash, False),
        (["13-04-2026"], CsvType.DATE, DateFormat.dmy_dash, False),
        (["Norte", "Sur"], CsvType.VARCHAR, None, False),
    ],
)
def test_guess_types(values, type_, fmt, comma):
    g = guess_column("c", values)
    assert (g.type, g.date_format, g.decimal_comma) == (type_, fmt, comma)


def test_leading_zeros_stay_text():
    g = guess_column("cp", ["01234", "56789"])
    assert g.type is CsvType.VARCHAR
    assert "ceros a la izquierda" in g.warnings[0]


def test_ambiguous_date_warns_and_assumes_day_first():
    g = guess_column("f", ["03/04/2026", "05/06/2026"])
    assert g.date_format is DateFormat.dmy_slash
    assert "ambigua" in g.warnings[0]


def test_inconsistent_dates_are_text():
    assert guess_column("f", ["13/04/2026", "04/13/2026"]).type is CsvType.VARCHAR


def test_decimal_comma_warns():
    assert "coma decimal" in guess_column("m", ["1,5"]).warnings[0]


def test_huge_integer_is_text():
    assert guess_column("id", ["1234567890123456789012"]).type is CsvType.VARCHAR


def test_empty_column():
    g = guess_column("x", ["", None])
    assert g.type is CsvType.VARCHAR and g.warnings


@pytest.mark.parametrize(
    ("filename", "table"),
    [("Ventas 2026.csv", "ventas_2026"), ("2026-ventas.CSV", "t_2026_ventas"), ("ñ.csv", "tabla")],
)
def test_suggest_table_name(filename, table):
    assert suggest_table_name(filename) == table


def test_options_must_match_type():
    with pytest.raises(ValidationError):
        ColumnChoice(name="x", type=CsvType.VARCHAR, decimal_comma=True)
    with pytest.raises(ValidationError):
        ColumnChoice(name="x", type=CsvType.BIGINT, date_format=DateFormat.iso)
