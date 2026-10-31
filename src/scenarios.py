"""剧本：没有网络也能跑的真实 agent 循环。

ScriptedModel 按剧本吐消息，所以这里的剧本必须**预先知道会不会出错**。
这不是缺陷——它就是录制回放的逻辑：先决定这次的输入，再回放对应的输出。

`will_error=True` 表示 pay_out 第一次调用会抛错，agent 随后重试。
"""

from __future__ import annotations

from .models import ToolCall, Turn


def _call(name: str, **args) -> Turn:
    return Turn(tool_calls=[ToolCall(name, args)])


def expense_run(will_error: bool, claim_id: str = "C-101", amount: float = 3200.0) -> list[Turn]:
    """一次完整的报销处理剧本。"""
    turns = [
        _call("get_employee", emp_id="E-001"),
        _call("get_receipts", claim_id=claim_id),
        _call("check_budget", dept_id="D-01"),
        _call("submit_approval", claim_id=claim_id),
        _call("pay_out", claim_id=claim_id, amount=amount),
    ]

    if will_error:
        # 模型看到 {"error": "TimeoutError: ..."}，于是决定重试
        turns.append(_call("pay_out", claim_id=claim_id, amount=amount))

    turns += [
        _call("notify", emp_id="E-001", msg=f"{claim_id} 已打款 {amount}"),
        Turn(text=f"已完成报销打款，金额 {amount}"),
    ]
    return turns
