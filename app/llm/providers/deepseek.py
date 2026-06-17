from __future__ import annotations

from app.configs.settings import settings
from app.llm.providers.openai import OpenAIProvider


class DeepSeekProvider(OpenAIProvider):
    """DeepSeek (OpenAI 兼容协议)."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str | None = None):
        super().__init__(
            api_key=api_key or settings.LLM_API_KEY,
            base_url=base_url or "https://api.deepseek.com/v1",
            model=model or "deepseek-chat",
        )
