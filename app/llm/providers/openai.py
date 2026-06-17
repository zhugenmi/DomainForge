from __future__ import annotations

from collections.abc import AsyncGenerator

from openai import AsyncOpenAI

from app.configs.settings import settings
from app.llm.base import LLMProvider


class OpenAIProvider(LLMProvider):
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        self.client = AsyncOpenAI(
            api_key=api_key or settings.LLM_API_KEY,
            base_url=base_url or settings.LLM_BASE_URL,
        )
        self.model = model or settings.DEFAULT_LLM_MODEL

    async def generate(self, messages: list[dict[str, str]], **kwargs) -> str:
        response = await self.client.chat.completions.create(
            model=kwargs.pop("model", self.model),
            messages=messages,
            **kwargs,
        )
        return response.choices[0].message.content or ""

    async def stream(self, messages: list[dict[str, str]], **kwargs) -> AsyncGenerator[str, None]:
        stream = await self.client.chat.completions.create(
            model=kwargs.pop("model", self.model),
            messages=messages,
            stream=True,
            **kwargs,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    async def embed(self, texts: list[str], **kwargs) -> list[list[float]]:
        embed_client = AsyncOpenAI(
            api_key=settings.EMBEDDING_API_KEY or settings.LLM_API_KEY,
            base_url=settings.EMBEDDING_BASE_URL,
        )
        response = await embed_client.embeddings.create(
            model=kwargs.pop("model", settings.EMBEDDING_MODEL),
            input=texts,
        )
        return [item.embedding for item in response.data]
