"""`python -m data2html.mcp`: the MCP server over stdio, started by Claude Desktop.

Environment:
- `D2H_TOKEN` (required): personal access token, created at <D2H_URL>/tokens.
- `D2H_URL`: the data2html backend (default http://127.0.0.1:8000).

stdout is the MCP channel: nothing else may print to it.
"""

from __future__ import annotations

import os
import sys

import httpx

from data2html.mcp.server import build_server


def main() -> int:
    token = os.environ.get("D2H_TOKEN", "").strip()
    if not token:
        print("D2H_TOKEN is not set: create a token at <data2html>/tokens", file=sys.stderr)
        return 1
    url = os.environ.get("D2H_URL", "http://127.0.0.1:8000").rstrip("/")
    with httpx.Client(base_url=url, headers={"Authorization": f"Bearer {token}"}, timeout=120) as http:
        build_server(http).run("stdio")
    return 0


raise SystemExit(main())
