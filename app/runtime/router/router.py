from __future__ import annotations

from app.runtime.nodes.base import BaseNode
from app.runtime.router.strategy import ConditionalStrategy, LinearStrategy
from app.runtime.state.agent_state import AgentState


class Router:
    """Runtime 路由器。

    默认采用条件路由（按 intent 跳过无用节点 + reflection 重路由）。
    传入 `linear=True` 时退化为 Phase 1 的线性执行，便于兼容旧测试。
    """

    def __init__(self, nodes: list[BaseNode], linear: bool = False, max_iterations: int = 6):
        self.nodes = nodes
        self.linear = linear
        self.max_iterations = max_iterations

    async def run(self, state: AgentState) -> AgentState:
        if self.linear:
            return await LinearStrategy(self.nodes).run(state)

        nodes_by_name: dict[str, BaseNode] = {}
        order: list[str] = []
        for n in self.nodes:
            name = _node_name(n)
            nodes_by_name[name] = n
            order.append(name)
        return await ConditionalStrategy(
            nodes_by_name, order, max_iterations=self.max_iterations
        ).run(state)


def _node_name(node: BaseNode) -> str:
    cls = node.__class__.__name__.lower()
    return cls.replace("node", "")
