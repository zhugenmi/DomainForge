from __future__ import annotations

from datetime import datetime
from typing import Any

from app.tools.base import Tool
from app.tools.registry.schema import ToolParameter, ToolSchema


class CurrentTimeTool(Tool):
    name = "current_time"
    description = "获取系统当前日期时间。当用户问'今天/现在/今年是哪天'、或回答需要知道当前日期时调用。返回 ISO 格式 + 星期。"
    schema = ToolSchema(parameters=[
        ToolParameter(name="timezone", type="string", description="可选时区名（如 'Asia/Shanghai'），缺省用系统本地时区", required=False, default=""),
    ])
    permission_scope = "default"
    timeout = 1.0

    async def execute(self, **kwargs: Any) -> dict:
        tz_name = (kwargs.get("timezone") or "").strip()
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(tz_name) if tz_name else None
        except Exception:
            return {"error": f"未知时区: {tz_name!r}", "hint": "如 'Asia/Shanghai'、'UTC'"}

        now = datetime.now(tz) if tz else datetime.now().astimezone()
        weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        return {
            "iso": now.isoformat(timespec="seconds"),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "weekday": weekdays[now.weekday()],
            "timezone": str(now.tzinfo),
        }
