from __future__ import annotations

from typing import Any

from app.tools.base import Tool
from app.tools.registry.schema import ToolParameter, ToolSchema


class CalculatorTool(Tool):
    name = "calculator"
    description = "执行简单的数学计算表达式"
    schema = ToolSchema(parameters=[
        ToolParameter(name="expression", type="string", description="数学表达式，如 '2 + 3 * 4'"),
    ])
    permission_scope = "default"
    timeout = 5.0

    async def execute(self, **kwargs: Any) -> dict:
        expression = kwargs["expression"]
        allowed_chars = set("0123456789+-*/().% ")
        if not all(c in allowed_chars for c in expression):
            return {"error": "表达式包含不允许的字符"}
        try:
            result = eval(expression)  # noqa: S307 - expression is sanitized above
            return {"expression": expression, "result": result}
        except Exception as e:
            return {"error": str(e)}
