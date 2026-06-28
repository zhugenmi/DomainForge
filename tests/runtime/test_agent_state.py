from app.runtime.state.agent_state import AgentState


def test_agent_state_creation():
    state = AgentState(query="你好")
    assert state.query == "你好"
    assert state.messages == []
    assert state.intent == ""
    assert state.plan == []
    assert state.retrieved_docs == []
    assert state.tool_results == []
    assert state.memories == []
    assert state.final_answer == ""
    assert state.retries == 0


def test_agent_state_with_values():
    state = AgentState(
        query="测试问题",
        intent="knowledge",
        plan=["检索知识库", "生成答案"],
        retrieved_docs=[{"content": "测试文档"}],
    )
    assert state.intent == "knowledge"
    assert len(state.plan) == 2
    assert len(state.retrieved_docs) == 1


def test_agent_state_new_fields_default():
    s = AgentState(query="hi")
    assert s.web_search is False
    assert s.deep_think is False
    assert s.attachments == []
    assert s.reasoning == ""


def test_agent_state_new_fields_set():
    s = AgentState(
        query="hi",
        web_search=True,
        deep_think=True,
        attachments=[{"filename": "a.txt", "content": "x"}],
        reasoning="think...",
    )
    assert s.web_search is True
    assert s.deep_think is True
    assert s.attachments[0]["filename"] == "a.txt"
    assert s.reasoning == "think..."
