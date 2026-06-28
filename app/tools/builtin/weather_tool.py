from __future__ import annotations

from typing import Any

import httpx

from app.tools.base import Tool
from app.tools.registry.schema import ToolParameter, ToolSchema

_USER_AGENT = "curl/8.4.0"


class WeatherTool(Tool):
    name = "weather"
    description = "查询某城市当前天气（基于 wttr.in，无需 API key）。返回紧凑文本如 '成都: ⛅️ +8°C'。"
    schema = ToolSchema(parameters=[
        ToolParameter(name="city", type="string", description="城市名（中文/英文均可），如 '成都' 或 'London'"),
        ToolParameter(name="units", type="string", description="单位制：'m' 公制（默认）、'u' 美制", required=False, default="m"),
    ])
    permission_scope = "default"
    timeout = 10.0

    WTTR_URL = "https://wttr.in"

    async def execute(self, **kwargs: Any) -> dict:
        city = kwargs["city"].strip()
        units = kwargs.get("units", "m") or "m"
        if units not in ("m", "u"):
            return {"error": f"非法 units: {units!r}（仅支持 'm' 或 'u'）"}

        url = f"{self.WTTR_URL}/{city}"
        params = {"format": "3", "T": "", units: ""}
        headers = {"User-Agent": _USER_AGENT}
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                resp = await client.get(url, params=params, headers=headers)
                resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            return {"error": f"wttr.in 返回 {e.response.status_code}", "city": city}
        except (httpx.RequestError, httpx.TimeoutException) as e:
            return {"error": f"请求 wttr.in 失败: {e}", "city": city}

        text = resp.text.strip()
        if not text:
            return {"error": "wttr.in 返回空响应", "city": city}
        return {"city": city, "report": text}
