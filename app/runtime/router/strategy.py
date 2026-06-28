from __future__ import annotations

import asyncio

from app.runtime.nodes.base import BaseNode
from app.runtime.state.agent_state import AgentState


class LinearStrategy:
    """顺序执行所有节点（向后兼容 Phase 1 行为）。"""

    def __init__(self, nodes: list[BaseNode]):
        self.nodes = nodes

    async def run(self, state: AgentState) -> AgentState:
        for n in self.nodes:
            state = await n.execute(state)
        return state


class ConditionalStrategy:
    """根据 state.intent 跳过不需要的节点；支持 reflection 重路由与 retrieval/tool 并行。"""

    def __init__(self, nodes_by_name: dict[str, BaseNode], order: list[str], max_iterations: int = 6):
        self.nodes = nodes_by_name
        self.order = order
        self.max_iterations = max_iterations

    async def run(self, state: AgentState) -> AgentState:
        # 默认顺序：intent -> planner -> memory -> retrieval? -> tool? -> answer -> reflection
        i = 0
        iterations = 0
        while i < len(self.order) and iterations < self.max_iterations:
            name = self.order[i]

            # 并行机会：retrieval 与 tool 都将执行，且 retrieval 结果不被 tool 消费
            # （两者写 state 不同字段：retrieved_docs / tool_results，无竞争）
            if name == "retrieval" and self._will_run(state, "retrieval"):
                tool_idx = self._next_runnable_index(state, "tool", i + 1)
                if tool_idx is not None:
                    await asyncio.gather(
                        self.nodes["retrieval"].execute(state),
                        self.nodes["tool"].execute(state),
                    )
                    i = tool_idx + 1
                    iterations += 2
                    continue

            if name == "retrieval" and not self._will_run(state, "retrieval"):
                i += 1
                iterations += 1
                continue
            if name == "tool" and not self._will_run(state, "tool"):
                i += 1
                iterations += 1
                continue
            if name == "websearch" and not self._will_run(state, "websearch"):
                i += 1
                iterations += 1
                continue
            if name == "reasoning" and not self._will_run(state, "reasoning"):
                i += 1
                iterations += 1
                continue

            state = await self.nodes[name].execute(state)
            reroute = getattr(state, "_reflection_reroute", None)
            if reroute:
                setattr(state, "_reflection_reroute", None)
                target_idx = self.order.index(reroute) if reroute in self.order else -1
                if target_idx >= 0:
                    i = target_idx
                    iterations += 1
                    continue
            i += 1
            iterations += 1
        return state

    def _will_run(self, state: AgentState, name: str) -> bool:
        if name == "retrieval":
            # agent_domain 非空时强制检索：领域 agent 的存在本身表明需要领域知识，
            # 不应依赖意图分类（分类器常把领域问题判为 chat，导致 agent 拿不到上下文）
            return (
                state.intent == "knowledge"
                or _plan_needs(state, "retrieve")
                or bool(state.agent_domain)
            )
        if name == "websearch":
            return state.web_search
        if name == "tool":
            # ReAct 循环：总是跑，LLM 自己决定调不调工具
            return True
        if name == "reasoning":
            return state.deep_think
        return True

    def _next_runnable_index(self, state: AgentState, name: str, start: int) -> int | None:
        for j in range(start, len(self.order)):
            if self.order[j] == name and self._will_run(state, name):
                return j
        return None


def _plan_needs(state: AgentState, action: str) -> bool:
    return any(s.get("action") == action for s in state.plan)


__all__ = ["LinearStrategy", "ConditionalStrategy"]
