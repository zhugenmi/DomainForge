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
