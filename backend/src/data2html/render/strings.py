"""Viewer chrome strings. Both languages travel in the page so the reader can switch without a
reload; report content (titles, data) is shown as authored and never translated."""

from __future__ import annotations

from data2html.i18n import SUPPORTED, Lang, get_lang, set_lang, tr


def _strings() -> dict[str, str]:
    return {
        "apply": tr("Apply"),
        "params": tr("Parameters"),
        "filteredBy": tr("Filtered by"),
        "removeFilter": tr("Remove filter {filter}"),
        "crossHint": tr("Click a bar or a slice to filter the other visuals."),
        "chartType": tr("Chart type"),
        "loading": tr("Loading…"),
        "noRows": tr("No rows to show."),
        "kpiOneRow": tr("A KPI needs a single row."),
        "tooManySlices": tr("Too many categories for a pie ({n}; max {max}). Use bars or the table."),
        "tooManyColors": tr("{n} color values (max {max}): use the table."),
        "error": tr("Could not load this visual: {error}"),
        "retry": tr("Retry"),
        "downloadCsv": tr("Download the data (CSV)"),
        "downloadPng": tr("Download the chart (PNG)"),
        "asOf": tr("Data as of {when}"),
        "eyebrow": tr("Report"),
        "live": tr("Live data"),
        "snapshot": tr("Snapshot per reader"),
        "signedInAs": tr("Signed in as {user}"),
        "signOut": tr("Sign out"),
        "language": tr("Language"),
        "yes": tr("Yes"),
        "no": tr("No"),
        "chartAria": tr("Chart of {measure} by {dimension}"),
        "mark.table": tr("Table"),
        "mark.kpi": tr("KPI"),
        "mark.bar": tr("Bars"),
        "mark.line": tr("Lines"),
        "mark.pie": tr("Pie"),
    }


def viewer_strings() -> dict[Lang, dict[str, str]]:
    current = get_lang()
    try:
        out: dict[Lang, dict[str, str]] = {}
        for lang in SUPPORTED:
            set_lang(lang)
            out[lang] = _strings()
        return out
    finally:
        set_lang(current)
