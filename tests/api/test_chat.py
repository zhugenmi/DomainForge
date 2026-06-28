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


def test_chat_request_new_fields_default():
    req = ChatRequest(query="hi")
    assert req.web_search is False
    assert req.deep_think is False
    assert req.attachment_ids == []


def test_chat_request_with_flags_and_attachments():
    req = ChatRequest(
        query="hi",
        web_search=True,
        deep_think=True,
        attachment_ids=["00000000-0000-0000-0000-000000000001"],
    )
    assert req.web_search is True
    assert req.deep_think is True
    assert len(req.attachment_ids) == 1


def test_attachment_upload_response():
    from app.schemas.chat import AttachmentPreview, AttachmentUploadResponse
    resp = AttachmentUploadResponse(
        attachment_ids=["00000000-0000-0000-0000-000000000001"],
        previews=[AttachmentPreview(filename="a.txt", size=10, chars=10)],
    )
    assert resp.previews[0].filename == "a.txt"
