from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.llm.base import LLMProvider, ToolCallResponse
from app.observability.logging.logger import get_logger

logger = get_logger("llm.fallback")


@dataclass
class FallbackPolicy:
    primary: LLMProvider
    secondary: LLMProvider | None = None
    max_retries: int = 1
    failures: list[str] = field(default_factory=list)

    def _providers(self) -> list[LLMProvider]:
        return [self.primary] + ([self.secondary] if self.secondary else [])

    async def generate(self, messages: list[dict], **kwargs) -> str:
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            for p in self._providers():
                try:
                    return await p.generate(messages, **kwargs)
                except Exception as e:
                    last_exc = e
                    label = getattr(p, "model", "unknown")
                    logger.warning("llm_fallback", provider=label, attempt=attempt, error=str(e))
                    self.failures.append(f"{label}:{e}")
        raise last_exc or RuntimeError("no provider available")

    async def stream(self, messages: list[dict], **kwargs) -> Any:
        last_exc: Exception | None = None
        for p in self._providers():
            try:
                return p.stream(messages, **kwargs)
            except Exception as e:
                last_exc = e
                logger.warning("llm_fallback_stream", error=str(e))
        raise last_exc or RuntimeError("no provider available")

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        tool_choice: str = "auto",
        **kwargs,
    ) -> ToolCallResponse:
        last_exc: Exception | None = None
        for p in self._providers():
            try:
                return await p.chat_with_tools(messages, tools, tool_choice=tool_choice, **kwargs)
            except NotImplementedError:
                # 该 provider 不支持工具调用，换下一个
                continue
            except Exception as e:
                last_exc = e
                label = getattr(p, "model", "unknown")
                logger.warning("llm_fallback_tools", provider=label, error=str(e))
                self.failures.append(f"{label}:{e}")
        if last_exc:
            raise last_exc
        raise NotImplementedError("no provider supports tool calling")

    async def embed(self, texts: list[str], **kwargs) -> list[list[float]]:
        last_exc: Exception | None = None
        for p in self._providers():
            try:
                return await p.embed(texts, **kwargs)
            except Exception as e:
                last_exc = e
                logger.warning("embedding_fallback", error=str(e))
        raise last_exc or RuntimeError("no embedding provider")
