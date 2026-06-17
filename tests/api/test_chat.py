from app.schemas.chat import ChatRequest, ChatResponse, SSEEventType


def test_chat_request():
    req = ChatRequest(query="你好")
    assert req.query == "你好"
    assert req.session_id is None


def test_chat_request_with_session():
    req = ChatRequest(query="你好", session_id="00000000-0000-0000-0000-000000000001")
    assert req.session_id is not None


def test_chat_response():
    resp = ChatResponse(session_id="00000000-0000-0000-0000-000000000001", answer="你好！", intent="chat")
    assert resp.answer == "你好！"
    assert resp.intent == "chat"


def test_sse_event_type_values():
    assert SSEEventType.INTENT_DETECTED == "intent_detected"
    assert SSEEventType.FINAL_ANSWER == "final_answer"
    assert SSEEventType.ERROR == "error"
