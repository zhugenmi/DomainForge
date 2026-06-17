from __future__ import annotations

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
    """根据 state.intent 跳过不需要的节点；支持 reflection 重路由。"""

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
            node = self.nodes[name]
            if name == "retrieval" and state.intent != "knowledge" and not _plan_needs(state, "retrieve"):
                i += 1
                iterations += 1
                continue
            if name == "tool" and state.intent != "tool" and not _plan_needs(state, "tool"):
                i += 1
                iterations += 1
                continue
            state = await node.execute(state)
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


def _plan_needs(state: AgentState, action: str) -> bool:
    return any(s.get("action") == action for s in state.plan)


__all__ = ["LinearStrategy", "ConditionalStrategy"]
