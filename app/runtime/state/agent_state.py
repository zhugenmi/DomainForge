from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentState:
    query: str
    messages: list[dict[str, str]] = field(default_factory=list)
    intent: str = ""
    complexity: str = "low"  # low / medium / high，由 IntentNode 推断
    plan: list[str] = field(default_factory=list)
    retrieved_docs: list[dict] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)
    memories: list[dict[str, str]] = field(default_factory=list)
    final_answer: str = ""
    retries: int = 0
    max_retries: int = 3
    # 敏感工具二次确认：本轮已确认的工具名集合
    confirmed_tool_names: set[str] = field(default_factory=set)
    # 因等待确认而暂挂的 tool_call（ToolCall 列表）；客户端确认后恢复执行
    pending_tool_calls: list = field(default_factory=list)
    # 暂挂起始时间戳（monotonic-ish），用于超时跳过；0.0 表示未暂挂
    pending_since: float = 0.0
    # agent 配置注入：system_prompt 非空时覆盖 AnswerNode 默认；domain 非空时过滤检索
    agent_system_prompt: str = ""
    agent_domain: str | None = None
    # 聊天输入增强：联网搜索开关 / 深度思考开关 / 附件 / 思考链
    web_search: bool = False
    deep_think: bool = False
    attachments: list[dict] = field(default_factory=list)
    reasoning: str = ""
