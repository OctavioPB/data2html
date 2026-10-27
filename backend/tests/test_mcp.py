"""The MCP server (ADR 0014) end to end against the app: tools → agent API → RLS. The test client stands
in for the httpx client that `python -m data2html.mcp` uses."""

import asyncio

import pytest

pytest.importorskip("mcp")  # optional extra: pip install -e ".[mcp]"

from fastapi.testclient import TestClient  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

from data2html.api.main import app  # noqa: E402
from data2html.mcp.server import build_server  # noqa: E402
from tests.security.test_agent_tokens import agent_settings, new_token  # noqa: E402, F401 - fixture


def call(server, tool: str, **args):
    result = asyncio.run(server.call_tool(tool, args))
    return result.structured_content


def server_for(user_id: str):
    return build_server(TestClient(app, headers={"Authorization": f"Bearer {new_token(user_id)}"}))


def test_tools_are_read_only(agent_settings):  # noqa: F811
    tools = asyncio.run(server_for("norte").list_tools())
    names = {t.name for t in tools}
    assert names == {"whoami", "list_models", "query_measure", "list_reports", "get_report_visual",
                     "list_tables", "profile_table"}
    assert all(t.annotations.read_only_hint for t in tools)


def test_query_measure_carries_the_token_owner_rls(agent_settings):  # noqa: F811
    norte, sur = server_for("norte"), server_for("sur")
    assert call(norte, "query_measure", model="ventas", measure="venta", dimension="region")["rows"] == [
        ["Norte", 33333]]
    assert call(sur, "query_measure", model="ventas", measure="venta", dimension="region")["rows"] == [
        ["Sur", 77777]]


def test_report_visual_with_params_and_cross_filters(agent_settings):  # noqa: F811
    norte = server_for("norte")
    out = call(norte, "get_report_visual", report="regional", visual="total", params={"desde": "2026-01-01"},
               cross_filters={"canal": "Web"})
    assert out["rows"] == [[11111]]
    reports = call(norte, "list_reports")["result"]
    assert reports[0]["id"] == "regional" and reports[0]["params"][0]["name"] == "desde"


def test_profile_filters_columns(agent_settings):  # noqa: F811
    out = call(server_for("autor"), "profile_table", source="csv", table="ventas", columns=["canal"])
    assert [c["name"] for c in out["columns"]] == ["canal"]


def test_errors_become_tool_errors(agent_settings):  # noqa: F811
    with pytest.raises(ToolError, match="403"):
        call(server_for("norte"), "list_tables")
    bad = build_server(TestClient(app, headers={"Authorization": "Bearer d2h_nope"}))
    with pytest.raises(ToolError, match="/tokens"):
        call(bad, "whoami")


def test_stdio_entry_point_needs_a_token(monkeypatch):
    import subprocess
    import sys

    env = {k: v for k, v in __import__("os").environ.items() if k != "D2H_TOKEN"}
    r = subprocess.run([sys.executable, "-m", "data2html.mcp"], env=env, capture_output=True, text=True,
                       timeout=60, check=False)
    assert r.returncode == 1 and "D2H_TOKEN" in r.stderr and r.stdout == ""
