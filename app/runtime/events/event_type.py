from enum import Enum


class SSEEventType(str, Enum):
    INTENT_DETECTED = "intent_detected"
    PLAN_GENERATED = "plan_generated"
    RETRIEVAL_STARTED = "retrieval_started"
    TOOL_CALLED = "tool_called"
    TOOL_RESULT = "tool_result"
    REFLECTION = "reflection"
    FINAL_ANSWER = "final_answer"
    ERROR = "error"
