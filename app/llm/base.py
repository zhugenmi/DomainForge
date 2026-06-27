from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field


@dataclass
class ToolCall:
    """单次工具调用请求（LLM 决定调用某工具）。"""

    id: str
    name: str
    arguments: dict


@dataclass
class ToolCallResponse:
    """LLM 在 function-calling 模式下的响应。"""

    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, messages: list[dict[str, str]], **kwargs) -> str: ...

    @abstractmethod
    async def stream(self, messages: list[dict[str, str]], **kwargs) -> AsyncGenerator[str, None]: ...

    @abstractmethod
    async def embed(self, texts: list[str], **kwargs) -> list[list[float]]: ...

    async def chat_with_tools(
        self,
        messages: list[dict[str, str]],
        tools: list[dict],
        tool_choice: str = "auto",
        **kwargs,
    ) -> ToolCallResponse:
        """function-calling 入口。不支持工具调用的 provider 抛 NotImplementedError。

        默认实现抛错，避免强制所有子类实现；支持工具的 provider（如 OpenAIProvider）覆写。
        """
        raise NotImplementedError(f"{self.__class__.__name__} does not support tool calling")
