"""Versioned content (ADR 0008): one validated YAML file per item in `content/<kind>/<name>.yaml`."""

from __future__ import annotations

import io
import os
import threading
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import YAMLError

from data2html.scrub import scrub


class ContentNotFound(LookupError):
    pass


class YamlStore[T: BaseModel]:
    not_found: type[ContentNotFound] = ContentNotFound

    def __init__(self, directory: Path, model: type[T], header: str, key: str = "name") -> None:
        self._dir = directory
        self._model = model
        self._header = header
        self._key = key  # field that names the file
        self._lock = threading.Lock()

    def _path(self, name: str) -> Path:
        # `name` already matches Ident (^[a-z][a-z0-9_]*$): it cannot escape the directory
        return self._dir / f"{name}.yaml"

    def _load(self, path: Path) -> T:
        return self._model.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))

    def list(self) -> tuple[list[T], dict[str, str]]:
        """Valid items and, separately, files that do not validate (file name → error)."""
        items: list[T] = []
        broken: dict[str, str] = {}
        if not self._dir.exists():
            return items, broken
        for f in sorted(self._dir.glob("*.yaml")):
            try:
                items.append(self._load(f))
            except (ValidationError, yaml.YAMLError) as e:
                broken[f.name] = scrub(str(e).split("\n")[0])
        return items, broken

    def get(self, name: str) -> T:
        path = self._path(name)
        if not path.exists():
            raise self.not_found(name)
        return self._load(path)

    def put(self, item: T) -> None:
        """Write the item. An existing file is updated in place (round-trip), so hand-written comments,
        key order and flow style survive; only values that changed are rewritten."""
        data = item.model_dump(mode="json", exclude_none=True, exclude_defaults=True)
        with self._lock:
            self._dir.mkdir(parents=True, exist_ok=True)
            path = self._path(getattr(item, self._key))
            text = _update_yaml(path.read_text(encoding="utf-8"), data) if path.exists() else None
            if text is None:
                text = self._header + yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=100)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(text, encoding="utf-8", newline="\n")
            os.replace(tmp, path)

    def delete(self, name: str) -> None:
        path = self._path(name)
        if not path.exists():
            raise self.not_found(name)
        path.unlink()


# ------------------------------------------------------------------ comment-preserving updates


def _merge(old: Any, new: Any) -> Any:
    """`new` values into `old`'s ruamel nodes, keeping the nodes (and so their comments) that remain."""
    if isinstance(old, CommentedMap) and isinstance(new, dict):
        for k in [k for k in old if k not in new]:
            del old[k]
        for k, v in new.items():
            old[k] = _merge(old[k], v) if k in old else v
        return old
    if isinstance(old, CommentedSeq) and isinstance(new, list):
        # lists of objects with an `id` (report visuals) are matched by id, not by position
        keyed = all(isinstance(x, dict) and "id" in x for x in new)
        if keyed and all(isinstance(x, CommentedMap) for x in old):
            by_id = {x.get("id"): x for x in old}
            merged = [_merge(by_id[x["id"]], x) if x["id"] in by_id else x for x in new]
        else:
            merged = list(new)
        old[:] = merged
        return old
    return new


def _update_yaml(text: str, data: dict[str, Any]) -> str | None:
    """`text` updated to `data`, or None if it cannot be parsed (then the file is rewritten)."""
    rt = YAML(typ="rt")
    rt.preserve_quotes = True
    rt.width = 100
    rt.indent(mapping=2, sequence=4, offset=2)
    try:
        doc = rt.load(text)
    except YAMLError:
        return None
    if not isinstance(doc, CommentedMap):
        return None
    out = io.StringIO()
    rt.dump(_merge(doc, data), out)
    return out.getvalue()
