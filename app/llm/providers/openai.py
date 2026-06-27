from __future__ import annotations

import json
from collections.abc import AsyncGenerator

from openai import AsyncOpenAI

from app.configs.settings import settings
from app.llm.base import LLMProvider, ToolCall, ToolCallResponse


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

    async def chat_with_tools(
        self,
        messages: list[dict[str, str]],
        tools: list[dict],
        tool_choice: str = "auto",
        **kwargs,
    ) -> ToolCallResponse:
        response = await self.client.chat.completions.create(
            model=kwargs.pop("model", self.model),
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            **kwargs,
        )
        msg = response.choices[0].message
        tool_calls: list[ToolCall] = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                except json.JSONDecodeError:
                    args = {"_raw": tc.function.arguments}
                tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        return ToolCallResponse(content=msg.content or "", tool_calls=tool_calls)

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
