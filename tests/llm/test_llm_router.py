import pytest

from app.llm.base import LLMProvider
from app.llm.router.fallback import FallbackPolicy
from app.llm.router.model_router import ModelRouter
from app.llm.embedding.embedding_service import EmbeddingService
from app.llm.rerank.rerank_service import RerankService


class StubProvider(LLMProvider):
    def __init__(self, name: str, raise_on_gen: bool = False):
        self.name = name
        self.model = name
        self.raise_on_gen = raise_on_gen

    async def generate(self, messages, **kwargs):
        if self.raise_on_gen:
            raise RuntimeError(f"{self.name} fail")
        return f"{self.name}:{messages[-1]['content']}"

    async def stream(self, messages, **kwargs):
        yield f"{self.name}:chunk"

    async def embed(self, texts, **kwargs):
        return [[len(t), 0.0] for t in texts]


def test_model_router_selects_provider():
    router = ModelRouter(default_provider="deepseek")
    p = router.get_provider("glm")
    assert p.__class__.__name__ == "GLMProvider"


def test_model_router_unknown_falls_back_to_openai():
    router = ModelRouter()
    p = router.get_provider("unknown")
    assert p.__class__.__name__ == "OpenAIProvider"


@pytest.mark.asyncio
async def test_fallback_primary_success():
    policy = FallbackPolicy(primary=StubProvider("p", raise_on_gen=False))
    out = await policy.generate([{"role": "user", "content": "hi"}])
    assert out.startswith("p:")


@pytest.mark.asyncio
async def test_fallback_switches_to_secondary():
    policy = FallbackPolicy(
        primary=StubProvider("p", raise_on_gen=True),
        secondary=StubProvider("s"),
    )
    out = await policy.generate([{"role": "user", "content": "hi"}])
    assert out.startswith("s:")


@pytest.mark.asyncio
async def test_embedding_service_batches():
    svc = EmbeddingService(llm=StubProvider("e"))
    vecs = await svc.embed(["a", "bb", "ccc"])
    assert vecs == [[1, 0.0], [2, 0.0], [3, 0.0]]


@pytest.mark.asyncio
async def test_rerank_service_no_endpoint_returns_simple():
    svc = RerankService()
    out = await svc.rerank("合同 法律", ["合同法律文本", "无关内容"], top_n=2)
    assert len(out) == 2
    assert out[0].score >= out[1].score
