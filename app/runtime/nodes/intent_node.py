from __future__ import annotations

from app.llm.base import LLMProvider
from app.runtime.events.event_bus import EventBus
from app.runtime.events.event_type import SSEEventType
from app.runtime.nodes.base import BaseNode
from app.runtime.state.agent_state import AgentState

INTENT_PROMPT = """你是一个意图识别器。根据用户问题，判断用户意图属于以下哪一类：

- chat: 日常闲聊或简单问答
- knowledge: 需要检索知识库的专业问题
- tool: 需要调用工具完成计算、查询等任务

只返回意图类别名称（chat / knowledge / tool），不要返回其他内容。

用户问题：{query}"""

# 复杂度启发式关键词
_HIGH_KEYWORDS = ("对比", "比较", "步骤", "首先", "然后", "分析", "总结", "归纳", "流程", "between", "compare", "step")
_MEDIUM_KEYWORDS = ("详细", "解释", "说明", "如何", "怎么", "为什么", "列出", "explain", "how", "why")


def infer_complexity(query: str) -> str:
    """启发式推断查询复杂度。high → 需规划；medium → 可规划；low → 跳过。"""
    if len(query) < 8:
        return "low"
    q = query.lower()
    if any(k in q for k in _HIGH_KEYWORDS):
        return "high"
    if any(k in q for k in _MEDIUM_KEYWORDS):
        return "medium"
    return "low"


class IntentNode(BaseNode):
    def __init__(self, llm: LLMProvider, event_bus: EventBus):
        self.llm = llm
        self.event_bus = event_bus

    async def execute(self, state: AgentState) -> AgentState:
        await self.event_bus.publish(SSEEventType.INTENT_DETECTED, {"status": "recognizing"})
        prompt = INTENT_PROMPT.format(query=state.query)
        intent = await self.llm.generate(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=10,
        )
        state.intent = intent.strip().lower()
        if state.intent not in ("chat", "knowledge", "tool"):
            state.intent = "chat"
        # 推断复杂度供 Planner 决策
        state.complexity = infer_complexity(state.query)
        await self.event_bus.publish(
            SSEEventType.INTENT_DETECTED, {"intent": state.intent, "complexity": state.complexity}
        )
        return state
