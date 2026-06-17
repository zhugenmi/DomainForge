from __future__ import annotations

from typing import Literal

from app.configs.settings import settings
from app.llm.base import LLMProvider
from app.llm.providers.deepseek import DeepSeekProvider
from app.llm.providers.gemini import GeminiProvider
from app.llm.providers.glm import GLMProvider
from app.llm.providers.openai import OpenAIProvider
from app.llm.providers.qwen import QwenProvider
from app.llm.router.fallback import FallbackPolicy

ProviderName = Literal["openai", "deepseek", "glm", "qwen", "gemini"]

_PROVIDERS: dict[str, type[LLMProvider]] = {
    "openai": OpenAIProvider,
    "deepseek": DeepSeekProvider,
    "glm": GLMProvider,
    "qwen": QwenProvider,
    "gemini": GeminiProvider,
}


class ModelRouter:
    """根据任务类型与配置选 provider；构造带 fallback 的策略。"""

    def __init__(self, default_provider: ProviderName | str | None = None):
        self.default = (default_provider or settings.DEFAULT_LLM_PROVIDER or "openai").lower()

    def get_provider(self, name: ProviderName | str | None = None) -> LLMProvider:
        key = (name or self.default).lower()
        cls = _PROVIDERS.get(key, OpenAIProvider)
        return cls()

    def get_fallback(self, primary: ProviderName | str | None = None) -> FallbackPolicy:
        p = self.get_provider(primary)
        secondary_name = settings.FALLBACK_LLM_PROVIDER
        secondary = self.get_provider(secondary_name) if secondary_name else None
        return FallbackPolicy(primary=p, secondary=secondary)

    def get_chat_llm(self) -> LLMProvider:
        """简单场景：直接返回 default provider（无 fallback）。"""
        return self.get_provider(self.default)


__all__ = ["ModelRouter", "ProviderName"]
