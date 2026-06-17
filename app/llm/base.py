from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator


class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, messages: list[dict[str, str]], **kwargs) -> str: ...

    @abstractmethod
    async def stream(self, messages: list[dict[str, str]], **kwargs) -> AsyncGenerator[str, None]: ...

    @abstractmethod
    async def embed(self, texts: list[str], **kwargs) -> list[list[float]]: ...
