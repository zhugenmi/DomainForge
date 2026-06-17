from __future__ import annotations

PLANNING_PROMPT = """你是一个任务规划器。判断用户问题是否需要拆解为多个步骤。

对于简单问题（闲聊、单点事实问答），直接返回空计划：
[]

对于需要多步的问题（涉及检索 + 工具 + 综合），返回 JSON 数组，每个步骤形如：
{{"step": "步骤描述", "action": "retrieve|tool|answer"}}

只返回 JSON 数组本身，不要解释。

用户问题：{query}"""

REFLECTION_PROMPT = """你是一个质量评估器。判断给定答案是否充分回答了用户问题。

用户问题：{query}
当前答案：{answer}
已有上下文是否充分：{has_context}

返回严格的 JSON：
{{"sufficient": true/false, "reason": "简短说明", "next_action": "none|retrieve|tool"}}

只返回 JSON。"""


__all__ = ["PLANNING_PROMPT", "REFLECTION_PROMPT"]
