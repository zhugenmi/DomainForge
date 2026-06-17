from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.llm.base import LLMProvider
from app.observability.logging.logger import get_logger

logger = get_logger("llm.fallback")


@dataclass
class FallbackPolicy:
    primary: LLMProvider
    secondary: LLMProvider | None = None
    max_retries: int = 1
    failures: list[str] = field(default_factory=list)

    async def generate(self, messages: list[dict], **kwargs) -> str:
        providers = [self.primary]
        if self.secondary:
            providers.append(self.secondary)

        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            for i, p in enumerate(providers):
                try:
                    return await p.generate(messages, **kwargs)
                except Exception as e:
                    last_exc = e
                    label = getattr(p, "model", "unknown")
                    logger.warning("llm_fallback", provider=label, attempt=attempt, error=str(e))
                    self.failures.append(f"{label}:{e}")
        raise last_exc or RuntimeError("no provider available")

    async def stream(self, messages: list[dict], **kwargs) -> Any:
        providers = [self.primary]
        if self.secondary:
            providers.append(self.secondary)
        last_exc: Exception | None = None
        for p in providers:
            try:
                return p.stream(messages, **kwargs)
            except Exception as e:
                last_exc = e
                logger.warning("llm_fallback_stream", error=str(e))
        raise last_exc or RuntimeError("no provider available")

    async def embed(self, texts: list[str], **kwargs) -> list[list[float]]:
        providers = [self.primary]
        if self.secondary:
            providers.append(self.secondary)
        last_exc: Exception | None = None
        for p in providers:
            try:
                return await p.embed(texts, **kwargs)
            except Exception as e:
                last_exc = e
                logger.warning("embedding_fallback", error=str(e))
        raise last_exc or RuntimeError("no embedding provider")
