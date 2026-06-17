from __future__ import annotations

from pydantic import BaseModel


class ToolParameter(BaseModel):
    name: str
    type: str = "string"
    description: str = ""
    required: bool = True
    default: object = None


class ToolSchema(BaseModel):
    parameters: list[ToolParameter] = []

    def to_openai_function(self) -> dict:
        properties = {}
        required = []
        for p in self.parameters:
            properties[p.name] = {"type": p.type, "description": p.description}
            if p.required:
                required.append(p.name)
        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }
