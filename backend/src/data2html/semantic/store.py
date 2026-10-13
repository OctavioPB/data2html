"""Semantic models in `content/semantic/<name>.yaml` (versionable in git)."""

from __future__ import annotations

from pathlib import Path

from data2html.content import ContentNotFound, YamlStore
from data2html.spec import SemanticModel

_HEADER = "# Semantic model (data2html). Measures are defined here, once.\n"


class ModelNotFound(ContentNotFound):
    pass


class ModelStore(YamlStore[SemanticModel]):
    not_found = ModelNotFound

    def __init__(self, directory: Path) -> None:
        super().__init__(directory, SemanticModel, _HEADER)
