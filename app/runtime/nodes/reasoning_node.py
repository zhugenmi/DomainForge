from __future__ import annotations

from app.llm.base import LLMProvider
from app.runtime.events.event_bus import EventBus
from app.runtime.events.event_type import SSEEventType
from app.runtime.nodes.base import BaseNode
from app.runtime.state.agent_state import AgentState

REASONING_PROMPT = """在回答之前，请对问题做深入思考。
- 拆解问题、识别关键概念
- 列出推理步骤、考虑多种可能性
- 指出需要额外信息的地方

问题：{query}
可用上下文：
{context}

请输出你的思考过程（不要给出最终答案）："""


def _summarize(state: AgentState) -> str:
    parts: list[str] = []
    if state.retrieved_docs:
        docs = "\n".join(f"- {d['content'][:200]}" for d in state.retrieved_docs)
        parts.append(f"检索知识：\n{docs}")
    if state.tool_results:
        tools = "\n".join(f"- {r['tool']}: {r.get('result', r.get('error', ''))}" for r in state.tool_results)
        parts.append(f"工具结果：\n{tools}")
    if state.attachments:
        atts = "\n".join(f"[{a['filename']}]: {a['content'][:200]}" for a in state.attachments)
        parts.append(f"附件：\n{atts}")
    return "\n\n".join(parts) if parts else "无额外上下文"


class ReasoningNode(BaseNode):
    """state.deep_think=True 时产出 CoT 思考链，供 AnswerNode 注入。

    多一次 LLM 调用；默认关闭无成本。
    """

    def __init__(self, llm: LLMProvider, event_bus: EventBus):
        self.llm = llm
        self.event_bus = event_bus

    async def execute(self, state: AgentState) -> AgentState:
        if not state.deep_think:
            return state

        context = _summarize(state)
        prompt = REASONING_PROMPT.format(query=state.query, context=context)
        reasoning = await self.llm.generate(messages=[{"role": "user", "content": prompt}])
        state.reasoning = reasoning
        await self.event_bus.publish(
            SSEEventType.REFLECTION, {"phase": "reasoning", "len": len(reasoning)}
        )
        return state
