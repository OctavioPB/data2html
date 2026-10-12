"""Export the contract's JSON Schema for the studio and the AI.

    python -m data2html.spec.export [path]   (default: ../studio/src/generated/spec.schema.json)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic.json_schema import models_json_schema

from data2html.spec.models import Report, SemanticModel


def build_schema() -> dict[str, object]:
    _, schema = models_json_schema(
        [(Report, "validation"), (SemanticModel, "validation")],
        title="data2html report-spec",
    )
    return schema


DEFAULT_OUT = Path(__file__).resolve().parents[4] / "studio/src/generated/spec.schema.json"


def render_schema() -> str:
    return json.dumps(build_schema(), indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_schema(), encoding="utf-8", newline="\n")
    print(f"schema -> {out}")  # ASCII: the Windows console (cp1252) cannot print arrows


if __name__ == "__main__":
    main()
