from __future__ import annotations

from dataclasses import asdict

from app.llm.base import LLMProvider
from app.rag.context.builder import build_context
from app.rag.context.citation import reorder_citations
from app.runtime.events.event_bus import EventBus
from app.runtime.events.event_type import SSEEventType
from app.runtime.nodes.base import BaseNode
from app.runtime.state.agent_state import AgentState
from app.skills.injection import build_skill_context_block
from app.skills.registry import SkillRegistry
from app.tools.registry.registry import ToolRegistry

ANSWER_SYSTEM_PROMPT = """你是一个专业的领域助手。请根据以下信息回答用户问题。

{context}"""


class AnswerNode(BaseNode):
    def __init__(
        self,
        llm: LLMProvider,
        event_bus: EventBus,
        tool_registry: ToolRegistry | None = None,
        skill_registry: SkillRegistry | None = None,
    ):
        self.llm = llm
        self.event_bus = event_bus
        self.tool_registry = tool_registry
        self.skill_registry = skill_registry

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
        if state.answered_by_tool:
            return state
        context_parts = []

        capability = await self._build_capability_context()
        if capability:
            context_parts.append(capability)

        if state.memories:
            history = "\n".join(f"[{m['role']}]: {m['content']}" for m in state.memories)
            context_parts.append(f"对话历史：\n{history}")

        if state.retrieved_docs:
            ctx = build_context(chunks=state.retrieved_docs)
            context_parts.append(ctx.text)
            state.citations = [asdict(c) for c in ctx.citations]
        else:
            state.citations = []

        if state.tool_results:
            results = "\n".join(self._format_tool_result(r) for r in state.tool_results)
            context_parts.append(f"工具执行结果：\n{results}")

        if state.attachments:
            atts = "\n\n".join(f"[{a['filename']}]\n{a['content']}" for a in state.attachments)
            context_parts.append(f"用户上传的附件：\n{atts}")

        context = "\n\n".join(context_parts) if context_parts else "无额外上下文"
        base_prompt = (
            state.agent_system_prompt if state.agent_system_prompt else ANSWER_SYSTEM_PROMPT
        )
        if "{context}" in base_prompt:
            system_prompt = base_prompt.format(context=context)
        else:
            system_prompt = f"{base_prompt}\n\n参考信息：\n{context}"

        if state.retrieved_docs:
            system_prompt += (
                "\n\n回答必须严格基于上方检索片段，并遵守："
                "\n1. 在引用检索内容的语句末尾标注上标编号 [N]（N 对应上方片段编号），"
                "如：根据《民法典》第三条，当事人应当……[1]。"
                "未引用的检索片段不要标注；不得编造未在检索片段中出现的法条编号、案例名或具体数字。"
                "\n2. 若所有检索片段均与问题无关或仅部分相关，开头先声明"
                "「知识库中暂无直接相关依据」，再简短给出方向性提示，不得仅凭训练知识作答。"
            )

        # 联网搜索已执行：明确指示 LLM 基于结果回答，不要输出函数调用标记
        if any(r.get("tool") == "web_search" for r in state.tool_results):
            system_prompt += (
                "\n\n系统已为你执行联网搜索，结果见上方「工具执行结果」。"
                "请直接基于这些搜索结果回答用户问题。"
                "不要输出 <function_calls>、<invoke> 等函数调用标记——你无法实际调用工具。"
                "如搜索结果不足，直接说明并给出基于现有信息的回答。"
            )

        if state.reasoning:
            system_prompt += f"\n\n你的思考过程：\n{state.reasoning}\n请基于上述思考给出最终答案。"

        if self.skill_registry is not None:
            skill_block = build_skill_context_block(self.skill_registry)
            if skill_block:
                system_prompt += f"\n\n{skill_block}"

        messages = [{"role": "system", "content": system_prompt}] + state.messages + [{"role": "user", "content": state.query}]
        answer = await self.llm.generate(messages=messages)
        # 按 answer 中 [N] 首次出现顺序重编号 citations，过滤未引用项，规整为正序 1,2,3...
        answer, state.citations = reorder_citations(answer, state.citations)
        state.final_answer = answer
        await self.event_bus.publish(
            SSEEventType.FINAL_ANSWER,
            {"answer": answer, "citations": state.citations},
        )
        return state

    @staticmethod
    def _format_tool_result(r: dict) -> str:
        """格式化单条工具结果为可读文本。"""
        tool = r.get("tool", "unknown")
        if "error" in r:
            return f"- {tool}（查询：{r.get('query', '?')}）失败：{r['error']}"
        result = r.get("result")
        if tool == "web_search" and isinstance(result, list):
            lines = [f"- {tool}（查询：{r.get('query', '?')}），返回 {len(result)} 条："]
            for item in result:
                if isinstance(item, dict):
                    title = item.get("title", "")
                    snippet = item.get("snippet", "")
                    url = item.get("url", "")
                    lines.append(f"  · {title} — {snippet}\n    {url}")
                else:
                    lines.append(f"  · {item}")
            return "\n".join(lines)
        return f"- {tool}: {result}"
