from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.tools.registry.schema import ToolSchema


class Tool(ABC):
    name: str
    description: str
    schema: ToolSchema
    permission_scope: str = "default"
    timeout: float = 30.0

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any: ...
