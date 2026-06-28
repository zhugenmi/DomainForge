from __future__ import annotations

from app.llm.base import LLMProvider
from app.observability.logging.logger import get_logger
from app.runtime.events.event_bus import EventBus
from app.runtime.events.event_type import SSEEventType
from app.runtime.nodes.base import BaseNode
from app.runtime.state.agent_state import AgentState
from app.tools.registry.registry import ToolRegistry

logger = get_logger("web_search_node")

SEARCH_QUERY_PROMPT = """从用户问题中提取一个简洁、适合搜索引擎的关键词。
- 去除"请搜索"、"帮我查"、"最新"等对话修饰词，保留核心实体与时间
- 输出语言与用户问题一致
- 只返回搜索词本身，不要引号、不要解释、不要标点

用户问题：{query}
搜索词："""


class WebSearchNode(BaseNode):
    """state.web_search=True 时强制调用 web_search 工具一次，结果并入 tool_results。

    先用 LLM 把用户的对话句提炼成搜索关键词，再调 SearchTool。
    失败时记录错误而非抛异常，避免阻塞后续 answer 节点。
    """

    def __init__(self, llm: LLMProvider, tool_registry: ToolRegistry, event_bus: EventBus):
        self.llm = llm
        self.tool_registry = tool_registry
        self.event_bus = event_bus

    async def _refine_query(self, raw_query: str) -> str:
        """LLM 提炼搜索关键词；空或失败时回退到原始 query。"""
        try:
            prompt = SEARCH_QUERY_PROMPT.format(query=raw_query)
            refined = await self.llm.generate(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=30,
            )
            refined = (refined or "").strip().strip('"').strip("'")
            return refined if refined else raw_query
        except Exception as e:
            logger.warning("web_search_refine_failed", error=str(e), fallback="raw_query")
            return raw_query

    async def execute(self, state: AgentState) -> AgentState:
        if not state.web_search:
            return state

        tool = self.tool_registry.get("web_search")
        if tool is None:
            logger.warning("web_search_tool_not_registered")
            return state

        search_query = await self._refine_query(state.query)
        logger.info("web_search_query", raw=state.query, refined=search_query)

        await self.event_bus.publish(
            SSEEventType.TOOL_CALLED, {"tool": "web_search", "forced": True, "query": search_query}
        )
        try:
            result = await tool.execute(query=search_query, top_k=5)
            state.tool_results.append({"tool": "web_search", "result": result, "query": search_query})
            await self.event_bus.publish(
                SSEEventType.TOOL_RESULT,
                {"tool": "web_search", "count": len(result) if isinstance(result, list) else 1},
            )
        except Exception as e:
            logger.warning("web_search_failed", error=str(e))
            state.tool_results.append({"tool": "web_search", "error": str(e), "query": search_query})
            await self.event_bus.publish(
                SSEEventType.TOOL_RESULT,
                {"tool": "web_search", "error": str(e)},
            )
        return state
