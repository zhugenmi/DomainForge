from __future__ import annotations

import uuid
from enum import Enum

from pydantic import BaseModel, Field


class SSEEventType(str, Enum):
    INTENT_DETECTED = "intent_detected"
    PLAN_GENERATED = "plan_generated"
    RETRIEVAL_STARTED = "retrieval_started"
    TOOL_CALLED = "tool_called"
    TOOL_RESULT = "tool_result"
    REFLECTION = "reflection"
    FINAL_ANSWER = "final_answer"
    ERROR = "error"


class ChatRequest(BaseModel):
    query: str
    session_id: uuid.UUID | None = None
    agent_id: uuid.UUID | None = None
    web_search: bool = False
    deep_think: bool = False
    attachment_ids: list[uuid.UUID] = Field(default_factory=list)
    model_name: str | None = None


class ChatModelsResponse(BaseModel):
    default: str
    models: list[str]


class ChatResponse(BaseModel):
    session_id: uuid.UUID
    answer: str
    intent: str | None = None


class AttachmentPreview(BaseModel):
    filename: str
    size: int
    chars: int


class AttachmentUploadResponse(BaseModel):
    attachment_ids: list[str]
    previews: list[AttachmentPreview]


class SSEEvent(BaseModel):
    event: SSEEventType
    data: dict = Field(default_factory=dict)
