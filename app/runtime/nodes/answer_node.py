from __future__ import annotations

from app.llm.base import LLMProvider
from app.runtime.events.event_bus import EventBus
from app.runtime.events.event_type import SSEEventType
from app.runtime.nodes.base import BaseNode
from app.runtime.state.agent_state import AgentState

ANSWER_SYSTEM_PROMPT = """你是一个专业的领域助手。请根据以下信息回答用户问题。

{context}"""


class AnswerNode(BaseNode):
    def __init__(self, llm: LLMProvider, event_bus: EventBus):
        self.llm = llm
        self.event_bus = event_bus

    async def execute(self, state: AgentState) -> AgentState:
        context_parts = []

        if state.memories:
            history = "\n".join(f"[{m['role']}]: {m['content']}" for m in state.memories)
            context_parts.append(f"对话历史：\n{history}")

        if state.retrieved_docs:
            docs = "\n".join(f"- {d['content']}" for d in state.retrieved_docs)
            context_parts.append(f"检索到的知识：\n{docs}")

        if state.tool_results:
            results = "\n".join(f"- {r['tool']}: {r['result']}" for r in state.tool_results)
            context_parts.append(f"工具执行结果：\n{results}")

        context = "\n\n".join(context_parts) if context_parts else "无额外上下文"
        system_prompt = ANSWER_SYSTEM_PROMPT.format(context=context)

        messages = [{"role": "system", "content": system_prompt}] + state.messages + [{"role": "user", "content": state.query}]
        answer = await self.llm.generate(messages=messages)
        state.final_answer = answer
        await self.event_bus.publish(SSEEventType.FINAL_ANSWER, {"answer": answer})
        return state
