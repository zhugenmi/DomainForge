import pytest

from app.tools.builtin.calculator_tool import CalculatorTool
from app.tools.registry.registry import ToolRegistry
from app.tools.registry.schema import ToolParameter, ToolSchema


def test_tool_schema_to_openai():
    schema = ToolSchema(parameters=[
        ToolParameter(name="query", type="string", description="search query"),
        ToolParameter(name="top_k", type="integer", description="num results", required=False),
    ])
    result = schema.to_openai_function()
    assert result["type"] == "object"
    assert "query" in result["properties"]
    assert result["required"] == ["query"]


def test_registry_register_and_get():
    reg = ToolRegistry()
    tool = CalculatorTool()
    reg.register(tool)

    assert reg.get("calculator") is tool
    assert reg.get("nonexistent") is None


def test_registry_list_tools():
    reg = ToolRegistry()
    tool = CalculatorTool()
    reg.register(tool)

    tools = reg.list_tools()
    assert len(tools) == 1
    assert tools[0].name == "calculator"


def test_registry_get_openai_tools():
    reg = ToolRegistry()
    tool = CalculatorTool()
    reg.register(tool)

    openai_tools = reg.get_openai_tools()
    assert len(openai_tools) == 1
    assert openai_tools[0]["type"] == "function"
    assert openai_tools[0]["function"]["name"] == "calculator"


@pytest.mark.asyncio
async def test_calculator_tool():
    tool = CalculatorTool()
    result = await tool.execute(expression="2 + 3")
    assert result["result"] == 5


@pytest.mark.asyncio
async def test_calculator_tool_invalid():
    tool = CalculatorTool()
    result = await tool.execute(expression="import os")
    assert "error" in result
