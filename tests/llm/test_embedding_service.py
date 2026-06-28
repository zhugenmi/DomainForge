from __future__ import annotations

import asyncio

import httpx
import pytest
from openai import RateLimitError

from app.llm.base import LLMProvider
from app.llm.embedding.embedding_service import EmbeddingService


def _make_429_response() -> httpx.Response:
    return httpx.Response(
        status_code=429,
        request=httpx.Request("POST", "https://example.test/embeddings"),
        headers={"retry-after": "0"},
    )


class _StubProvider(LLMProvider):
    """记录调用次数、可选在前 fail_until 次抛 RateLimitError。"""

    def __init__(self, fail_until: int = 0):
        self.calls = 0
        self.fail_until = fail_until  # 0 表示从不失败

    async def generate(self, messages, **kwargs):  # pragma: no cover - 未使用
        raise NotImplementedError

    async def stream(self, messages, **kwargs):  # pragma: no cover - 未使用
        raise NotImplementedError
        yield  # noqa: unreachable - 让它成为 generator

    async def embed(self, texts, **kwargs):
        self.calls += 1
        if self.calls <= self.fail_until:
            raise RateLimitError(
                message="429 Too Many Requests",
                response=_make_429_response(),
                body=None,
            )
        return [[0.0] for _ in texts]


@pytest.mark.asyncio
async def test_embed_retries_on_429_then_succeeds(monkeypatch):
    # 压缩退避等待时间，避免测试变慢
    monkeypatch.setattr("app.llm.embedding.embedding_service._BASE_BACKOFF", 0.01)
    provider = _StubProvider(fail_until=2)
    svc = EmbeddingService(llm=provider, batch_size=2, batch_interval=0.0, max_retries=4)

    out = await svc.embed(["a", "b", "c", "d"])
    assert len(out) == 4
    # 4 文本 / batch=2 → 2 批；第 1 批失败 2 次后成功（3 次调用），第 2 批 1 次成功
    assert provider.calls == 4


@pytest.mark.asyncio
async def test_embed_gives_up_after_max_retries(monkeypatch):
    monkeypatch.setattr("app.llm.embedding.embedding_service._BASE_BACKOFF", 0.01)
    provider = _StubProvider(fail_until=99)  # 永远失败
    svc = EmbeddingService(llm=provider, batch_size=2, batch_interval=0.0, max_retries=2)

    with pytest.raises(RateLimitError):
        await svc.embed(["a", "b"])
    # 1 次初始 + 2 次重试 = 3 次调用
    assert provider.calls == 3


@pytest.mark.asyncio
async def test_embed_batch_interval_applied(monkeypatch):
    slept: list[float] = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    provider = _StubProvider()
    svc = EmbeddingService(llm=provider, batch_size=1, batch_interval=0.5)

    # 3 个 chunk → 3 批 → 中间应有 2 次节流 sleep
    await svc.embed(["a", "b", "c"])
    assert provider.calls == 3
    # 仅检查节流 sleep 存在且值正确（不检查重试退避 sleep，因无失败）
    interval_sleeps = [s for s in slept if s == 0.5]
    assert interval_sleeps == [0.5, 0.5]
