from pathlib import Path

import pytest

from app.llm.base import LLMProvider
from app.runtime.events.event_bus import EventBus
from app.runtime.nodes.answer_node import AnswerNode
from app.runtime.state.agent_state import AgentState
from app.skills.loader import SkillDescriptor
from app.skills.manifest import SkillManifest
from app.skills.registry import SkillRegistry


class StubLLM(LLMProvider):
    def __init__(self):
        self.last_system = ""

    async def generate(self, messages, **kw):
        self.last_system = messages[0]["content"]
        return "ok"

    async def stream(self, messages, **kw):
        async for _ in []:
            yield ""
        return

    async def embed(self, texts, **kw):
        return [[0.0] * 128 for _ in texts]

    async def chat_with_tools(self, messages, tools, **kw):
        return "ok", None


def _desc(name: str, body: str) -> SkillDescriptor:
    return SkillDescriptor(
        manifest=SkillManifest(
            name=name, description="d", version="", author="", license="", body_md=body
        ),
        path=Path(f"/tmp/{name}"),
        files=["SKILL.md"],
    )


@pytest.mark.asyncio
async def test_skill_block_injected_into_system_prompt():
    reg = SkillRegistry()
    reg.add(_desc("foo", "Do foo things."))
    llm = StubLLM()
    node = AnswerNode(llm=llm, event_bus=EventBus(), skill_registry=reg)
    state = AgentState(query="hi", messages=[])
    await node.execute(state)
    assert "Do foo things." in llm.last_system
    assert "技能：foo" in llm.last_system


@pytest.mark.asyncio
async def test_no_skill_no_block():
    reg = SkillRegistry()
    llm = StubLLM()
    node = AnswerNode(llm=llm, event_bus=EventBus(), skill_registry=reg)
    state = AgentState(query="hi", messages=[])
    await node.execute(state)
    assert "技能指令" not in llm.last_system


@pytest.mark.asyncio
async def test_skill_registry_defaults_to_none_no_injection():
    llm = StubLLM()
    node = AnswerNode(llm=llm, event_bus=EventBus())  # 不传 skill_registry
    state = AgentState(query="hi", messages=[])
    await node.execute(state)
    assert "技能指令" not in llm.last_system
