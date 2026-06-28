import pytest

from app.tools.builtin.search_tool import SearchTool


class _FakeResponse:
    def __init__(self, text: str, status: int = 200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.mark.asyncio
async def test_search_tool_parses_bing_results(monkeypatch):
    sample_html = """
    <html><body>
    <li class="b_algo">
      <h2><a href="https://example.com/a">Result <strong>One</strong></a></h2>
      <p>Snippet for result one with details</p>
    </li>
    <li class="b_algo">
      <h2><a href="https://example.com/b">Result Two</a></h2>
      <p>Snippet for result two</p>
    </li>
    </body></html>
    """

    captured = {}

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, **kw):
            captured["url"] = url
            captured["params"] = kw.get("params", {})
            return _FakeResponse(sample_html)

    monkeypatch.setattr("app.tools.builtin.search_tool.httpx.AsyncClient", _FakeClient)

    tool = SearchTool()
    results = await tool.execute(query="test", top_k=5)

    assert len(results) == 2
    assert results[0]["title"] == "Result One"
    assert results[0]["url"] == "https://example.com/a"
    assert "Snippet for result one" in results[0]["snippet"]
    assert "bing.com/search" in captured["url"]
    assert captured["params"].get("q") == "test"


@pytest.mark.asyncio
async def test_search_tool_respects_top_k(monkeypatch):
    sample_html = "".join(
        f'<li class="b_algo"><h2><a href="u{i}">T{i}</a></h2><p>S{i}</p></li>'
        for i in range(10)
    )

    class _FakeClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, **kw): return _FakeResponse(sample_html)

    monkeypatch.setattr("app.tools.builtin.search_tool.httpx.AsyncClient", _FakeClient)

    tool = SearchTool()
    results = await tool.execute(query="test", top_k=3)
    assert len(results) == 3


@pytest.mark.asyncio
async def test_search_tool_returns_empty_on_no_results(monkeypatch):
    class _FakeClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, **kw): return _FakeResponse("<html></html>")

    monkeypatch.setattr("app.tools.builtin.search_tool.httpx.AsyncClient", _FakeClient)

    tool = SearchTool()
    results = await tool.execute(query="test", top_k=5)
    assert results == []
