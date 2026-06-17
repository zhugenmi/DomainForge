from __future__ import annotations

from app.configs.settings import settings
from app.llm.providers.openai import OpenAIProvider


class GeminiProvider(OpenAIProvider):
    """Google Gemini (OpenAI 兼容协议入口)."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str | None = None):
        super().__init__(
            api_key=api_key or settings.LLM_API_KEY,
            base_url=base_url or "https://generativelanguage.googleapis.com/v1beta/openai",
            model=model or "gemini-1.5-pro",
        )
