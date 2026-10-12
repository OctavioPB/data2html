"""Dump the app's OpenAPI to generate the studio's TS types without starting the server.

    python -m data2html.api.openapi [path]   (default: ../studio/src/generated/openapi.json)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from data2html.api.main import app

DEFAULT_OUT = Path(__file__).resolve().parents[4] / "studio/src/generated/openapi.json"


def render_openapi() -> str:
    return json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_openapi(), encoding="utf-8", newline="\n")
    print(f"openapi -> {out}")


if __name__ == "__main__":
    main()
