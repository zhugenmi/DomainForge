from __future__ import annotations

import pytest

from app.runtime.events.event_bus import EventBus
from app.runtime.nodes.retrieval_node import RetrievalNode
from app.runtime.state.agent_state import AgentState


class _StubChunk:
    def __init__(self, cid, content, doc_id, metadata, score):
        self.id = cid
        self.content = content
        self.document_id = doc_id
        self.metadata_ = metadata
        self.score = score


class _StubRAG:
    def __init__(self, chunks):
        self._chunks = chunks

    async def search(self, query, domain=None):
        return self._chunks


@pytest.mark.asyncio
async def test_retrieval_node_preserves_id_score_metadata():
    chunks = [
        _StubChunk("c1", "第三条 内容。", "d1", {"title": "民法典.txt", "article": "第三条"}, 0.91),
        _StubChunk("c2", "第四条 内容。", "d1", {"title": "民法典.txt", "article": "第四条"}, 0.82),
    ]
    bus = EventBus()
    node = RetrievalNode(rag_service=_StubRAG(chunks), event_bus=bus)
    state = AgentState(query="Q", intent="knowledge")

    await node.execute(state)

    assert len(state.retrieved_docs) == 2
    d0 = state.retrieved_docs[0]
    assert d0["id"] == "c1"
    assert d0["document_id"] == "d1"
    assert d0["score"] == 0.91
    assert d0["metadata"]["article"] == "第三条"
    assert d0["content"] == "第三条 内容。"
    bus.done()
    _ = [e async for e in bus.stream()]


@pytest.mark.asyncio
async def test_retrieval_node_skips_when_chat_intent_no_domain():
    bus = EventBus()
    node = RetrievalNode(rag_service=_StubRAG([]), event_bus=bus)
    state = AgentState(query="Q", intent="chat")  # 无 agent_domain
    await node.execute(state)
    assert state.retrieved_docs == []
    bus.done()
    _ = [e async for e in bus.stream()]
