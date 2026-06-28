import pytest

from app.tools.builtin.calculator_tool import CalculatorTool
from app.tools.builtin.file_tool import FileReadTool, FileWriteTool
from app.tools.builtin.search_tool import SearchTool
from app.tools.builtin.sql_tool import SQLTool
from app.tools.mcp.client import MCPClient


@pytest.mark.asyncio
async def test_calculator_basic():
    t = CalculatorTool()
    r = await t.execute(expression="2 + 3 * 4")
    assert r["result"] == 14


@pytest.mark.asyncio
async def test_calculator_rejects_import():
    t = CalculatorTool()
    r = await t.execute(expression="__import__('os')")
    assert "error" in r


@pytest.mark.asyncio
async def test_file_tool_sandbox_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tools.builtin.file_tool.SANDBOX_ROOT", tmp_path)
    w = FileWriteTool()
    r = await w.execute(path="sub/a.txt", content="hello")
    assert r["size"] == 5
    rd = FileReadTool()
    r2 = await rd.execute(path="sub/a.txt")
    assert r2["content"] == "hello"


@pytest.mark.asyncio
async def test_file_tool_rejects_escape(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tools.builtin.file_tool.SANDBOX_ROOT", tmp_path)
    w = FileWriteTool()
    with pytest.raises(PermissionError):
        await w.execute(path="../../etc/passwd", content="x")


@pytest.mark.asyncio
async def test_sql_tool_rejects_non_select():
    t = SQLTool(dsn="sqlite:///:memory:")
    r = await t.execute(sql="DROP TABLE x")
    assert "error" in r


@pytest.mark.asyncio
async def test_sql_tool_rejects_forbidden_keyword():
    t = SQLTool(dsn="sqlite:///:memory:")
    r = await t.execute(sql="SELECT * FROM x; DELETE FROM y")
    assert "error" in r


@pytest.mark.asyncio
async def test_sql_tool_runs_select_on_sqlite():
    t = SQLTool(dsn="sqlite:///:memory:")
    r = await t.execute(sql="SELECT 1 as one, 2 as two", limit=5)
    assert r["rowcount"] == 1
    assert r["rows"][0] == [1, 2]


@pytest.mark.asyncio
async def test_search_tool_returns_list(monkeypatch):
    t = SearchTool()

    class _Resp:
        text = (
            '<html><body>'
            '<li class="b_algo"><h2><a href="https://a.com">A</a></h2>'
            '<p>Result A snippet</p></li>'
            '<li class="b_algo"><h2><a href="https://b.com">B</a></h2>'
            '<p>Result B longer snippet here</p></li>'
            '</body></html>'
        )

        def raise_for_status(self):
            pass

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, **kw):
            return _Resp()

    import app.tools.builtin.search_tool as mod

    monkeypatch.setattr(mod.httpx, "AsyncClient", lambda *a, **k: _Client())
    out = await t.execute(query="test", top_k=2)
    assert isinstance(out, list)
    assert len(out) == 2
    assert all("snippet" in o for o in out)


@pytest.mark.asyncio
async def test_mcp_client_unavailable_returns_empty():
    c = MCPClient(server_url=None)
    assert not c.available()
    assert await c.list_tools() == []
    r = await c.call_tool("x", {})
    assert "error" in r
