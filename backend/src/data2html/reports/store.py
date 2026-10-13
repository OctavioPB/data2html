"""Reports in `content/reports/<id>.yaml`. Saving is publishing: the viewer serves what is here."""

from __future__ import annotations

from pathlib import Path

from data2html.content import ContentNotFound, YamlStore
from data2html.spec import Report

_HEADER = "# Report (data2html). Visuals name measures of the semantic model; no SQL here.\n"


class ReportNotFound(ContentNotFound):
    pass


class ReportStore(YamlStore[Report]):
    not_found = ReportNotFound

    def __init__(self, directory: Path) -> None:
        super().__init__(directory, Report, _HEADER, key="id")
