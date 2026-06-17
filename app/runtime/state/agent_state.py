from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentState:
    query: str
    messages: list[dict[str, str]] = field(default_factory=list)
    intent: str = ""
    plan: list[str] = field(default_factory=list)
    retrieved_docs: list[dict] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)
    memories: list[dict[str, str]] = field(default_factory=list)
    final_answer: str = ""
    retries: int = 0
    max_retries: int = 3
