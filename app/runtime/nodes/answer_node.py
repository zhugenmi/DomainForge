from __future__ import annotations

from app.llm.base import LLMProvider
from app.runtime.events.event_bus import EventBus
from app.runtime.events.event_type import SSEEventType
from app.runtime.nodes.base import BaseNode
from app.runtime.state.agent_state import AgentState
from app.tools.registry.registry import ToolRegistry

ANSWER_SYSTEM_PROMPT = """你是一个专业的领域助手。请根据以下信息回答用户问题。

{context}"""


class AnswerNode(BaseNode):
    def __init__(self, llm: LLMProvider, event_bus: EventBus, tool_registry: ToolRegistry | None = None):
        self.llm = llm
        self.event_bus = event_bus
        self.tool_registry = tool_registry

    async def _build_capability_context(self) -> str:
        """组装系统能力上下文：可用知识库目录 + 可用工具清单。

        让模型据实回答"有哪些知识库 / 有哪些技能"这类元问题，而非凭训练知识编造。
        任何子查询失败都降级为跳过该段，不影响主回答。
        """
        parts: list[str] = []

        if self.tool_registry is not None:
            catalog_tool = self.tool_registry.get("list_knowledge_bases")
            if catalog_tool is not None:
                try:
                    catalog = await catalog_tool.execute()
                    if catalog:
                        lines = []
                        for c in catalog:
                            builtin_tag = "（内置）" if c.get("is_builtin") else ""
                            lines.append(
                                f"- {c['name']}{builtin_tag}: 文档 {c.get('file_count', 0)} 篇, "
                                f"约 {c.get('word_count', 0)} 字"
                            )
                        parts.append("当前已配置的知识库：\n" + "\n".join(lines))
                except Exception:
                    pass

            tools = self.tool_registry.list_tools()
            if tools:
                lines = [f"- {t.name}: {t.description}" for t in tools]
                parts.append("当前可用的工具/技能：\n" + "\n".join(lines))

        return "\n\n".join(parts)

    async def execute(self, state: AgentState) -> AgentState:
        context_parts = []

        capability = await self._build_capability_context()
        if capability:
            context_parts.append(capability)

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
