"""Semantic models in `content/semantic/<name>.yaml` (versionable in git)."""

from __future__ import annotations

import os
import threading
from pathlib import Path

import yaml
from pydantic import ValidationError

from data2html.spec import SemanticModel

_HEADER = "# Semantic model (data2html). Measures are defined here, once.\n"


class ModelNotFound(LookupError):
    pass


class ModelStore:
    def __init__(self, directory: Path) -> None:
        self._dir = directory
        self._lock = threading.Lock()

    def _path(self, name: str) -> Path:
        # `name` already matches Ident (^[a-z][a-z0-9_]*$): it cannot escape the directory
        return self._dir / f"{name}.yaml"

    def list(self) -> tuple[list[SemanticModel], dict[str, str]]:
        """Valid models and, separately, files that do not validate (file name → error)."""
        models: list[SemanticModel] = []
        broken: dict[str, str] = {}
        if not self._dir.exists():
            return models, broken
        for f in sorted(self._dir.glob("*.yaml")):
            try:
                models.append(SemanticModel.model_validate(yaml.safe_load(f.read_text(encoding="utf-8"))))
            except (ValidationError, yaml.YAMLError) as e:
                broken[f.name] = str(e).split("\n")[0]
        return models, broken

    def get(self, name: str) -> SemanticModel:
        path = self._path(name)
        if not path.exists():
            raise ModelNotFound(name)
        return SemanticModel.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))

    def put(self, model: SemanticModel) -> None:
        text = yaml.safe_dump(model.model_dump(mode="json", exclude_none=True), allow_unicode=True,
                              sort_keys=False, width=100)
        with self._lock:
            self._dir.mkdir(parents=True, exist_ok=True)
            path = self._path(model.name)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(_HEADER + text, encoding="utf-8", newline="\n")
            os.replace(tmp, path)

    def delete(self, name: str) -> None:
        path = self._path(name)
        if not path.exists():
            raise ModelNotFound(name)
        path.unlink()
