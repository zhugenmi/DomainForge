import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

from app.tools.builtin.time_tool import CurrentTimeTool


@pytest.mark.asyncio
async def test_current_time_default_local():
    tool = CurrentTimeTool()
    result = await tool.execute()

    assert "iso" in result
    assert "date" in result
    assert "weekday" in result
    assert result["timezone"]
    today = datetime.now().astimezone().strftime("%Y-%m-%d")
    assert result["date"] == today


@pytest.mark.asyncio
async def test_current_time_explicit_timezone():
    tool = CurrentTimeTool()
    result = await tool.execute(timezone="Asia/Shanghai")

    assert "Asia/Shanghai" in result["timezone"]
    now_sh = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
    assert result["date"] == now_sh


@pytest.mark.asyncio
async def test_current_time_bad_timezone():
    tool = CurrentTimeTool()
    result = await tool.execute(timezone="Mars/Olympus")

    assert "error" in result
    assert "Mars/Olympus" in result["error"]
