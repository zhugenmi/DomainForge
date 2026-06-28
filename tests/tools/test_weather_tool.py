import pytest

from app.tools.builtin.weather_tool import WeatherTool


class _FakeResponse:
    def __init__(self, text: str, status: int = 200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}", request=None, response=self
            )


class _FakeClient:
    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, **kw):
        self.captured_url = url
        self.captured_params = kw.get("params", {})
        return self._response


@pytest.mark.asyncio
async def test_weather_tool_returns_report(monkeypatch):
    client = _FakeClient()
    client._response = _FakeResponse("成都: ⛅️ +8°C")
    monkeypatch.setattr("app.tools.builtin.weather_tool.httpx.AsyncClient", lambda *a, **kw: client)

    tool = WeatherTool()
    result = await tool.execute(city="成都")

    assert result["city"] == "成都"
    assert "成都" in result["report"]
    assert "8°C" in result["report"]
    assert "wttr.in/成都" in client.captured_url
    assert client.captured_params.get("format") == "3"
    assert client.captured_params.get("m") == ""


@pytest.mark.asyncio
async def test_weather_tool_rejects_bad_units():
    tool = WeatherTool()
    result = await tool.execute(city="London", units="x")
    assert "error" in result
    assert "x" in result["error"]


@pytest.mark.asyncio
async def test_weather_tool_handles_http_error(monkeypatch):
    client = _FakeClient()
    client._response = _FakeResponse("", status=500)
    monkeypatch.setattr("app.tools.builtin.weather_tool.httpx.AsyncClient", lambda *a, **kw: client)

    tool = WeatherTool()
    result = await tool.execute(city="nowhere")

    assert "error" in result
    assert "500" in result["error"]
    assert result["city"] == "nowhere"


@pytest.mark.asyncio
async def test_weather_tool_handles_empty_response(monkeypatch):
    client = _FakeClient()
    client._response = _FakeResponse("   ")
    monkeypatch.setattr("app.tools.builtin.weather_tool.httpx.AsyncClient", lambda *a, **kw: client)

    tool = WeatherTool()
    result = await tool.execute(city="x")

    assert "error" in result
    assert "空响应" in result["error"]
