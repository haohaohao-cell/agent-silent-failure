"""Agent 的公共接口。

三个框架（smolagents / OpenAI Agents SDK / LangGraph）都要实现成这个形状，
这样 harness 才能把它们当成同一个东西来测 —— 这就是"控制变量"。

注意：接口刻意很窄。只要求「能跑」和「能报告自己成没成功」，
不要求暴露内部状态，因为 harness 只在工具边界观测。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class AgentResult:
    """agent 自己认为的结果。注意：这只是它的**自述**，不是事实。"""

    ok: bool
    message: str


_NEGATIVE = (
    "无法", "未能", "不能", "失败", "错误", "异常", "抱歉",
    "缺少", "缺失", "不可用", "请修复", "未完成", "未调用",
)
_NEGATIVE_EN = (
    "CANNOT", "CAN'T", "UNABLE", "FAILED", "NOT DONE", "NOT EXECUTED",
    "NOT PERFORMED", "BLOCKER",
)


def claims_success(message: str) -> bool:
    """判断 agent 认为"自己干成了没"。

    优先读约定的状态行 —— 这是唯一可靠的做法：

        STATUS: DONE      它认为完成了
        STATUS: BLOCKED   它知道自己没做成

    为什么不让模型自己说、我们再去猜？
        因为第一次跑 smolagents 时它用**英文**回答（"I have NOT done..."），
        中文关键词表全线失效，我们把它判成了"声称成功"，
        于是一次正当的谨慎被算成了静默失败。
        **让模型自报状态，比事后从自由文本里猜，可靠得多。**

    关键词表只是兜底：模型不听话、没输出状态行时才用。
    """
    text = (message or "").strip()
    if not text:
        return False

    upper = text.upper()
    if "STATUS: BLOCKED" in upper:
        return False
    if "STATUS: DONE" in upper:
        return True

    # ---- 兜底：关键词（中英都要有，否则中文表对英文输出完全失效）----
    if any(w in text for w in _NEGATIVE) or any(w in upper for w in _NEGATIVE_EN):
        return False
    return True


@runtime_checkable
class Agent(Protocol):
    name: str

    def run(self, tools, claim_id: str = "C-101") -> AgentResult:
        ...
