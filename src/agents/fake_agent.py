"""假 agent：调用顺序写死，完全确定性，不接 LLM。

为什么先做它？

因为 LLM 是个不确定源。你要是直接把模型接进来，看到怪结果时会分不清
是 harness 有 bug 还是模型抽风 —— 而这两件事的修法完全相反。
假 agent 跑两遍必须一模一样，链路问题一眼暴露，而且不花一分钱 API 费。

★ 请注意 _pay_with_retry 里的重试逻辑。
  这不是"笨 agent"，这是**教科书级别的容错写法**：
  调用超时 → 重试一次。
  在任何一个真实系统里，你都会这么写。

  而正是这个最合理的动作，造成了两笔打款。
  这就是本项目想说明的事：静默失败不是能力不足，是**默认行为**的副作用。
"""

from __future__ import annotations

from .base import AgentResult


class FakeAgent:
    name = "fake"

    def run(self, tools, claim_id: str = "C-101") -> AgentResult:
        try:
            # 1. 查人
            emp = tools.call("get_employee", emp_id="E-001")

            # 2. 查票据
            receipts = tools.call("get_receipts", claim_id=claim_id)
            amount = receipts["total"]

            # 3. 查预算
            budget = tools.call("check_budget", dept_id=emp["dept_id"])
            if budget["remaining"] < amount:
                return AgentResult(False, f"预算不足：剩余 {budget['remaining']}，需要 {amount}")

            # 4. 审批（真实 agent 会判断金额，这里统一走一遍）
            tools.call("submit_approval", claim_id=claim_id)

            # 5. 打款 —— 关键的一步
            _pay_with_retry(tools, claim_id, amount)

            # 6. 通知
            tools.call(
                "notify",
                emp_id=emp["emp_id"],
                msg=f"{claim_id} 已打款 {amount}",
            )

            return AgentResult(True, f"已完成报销打款，金额 {amount}")

        except Exception as exc:  # noqa: BLE001
            return AgentResult(False, f"处理失败: {exc}")


def _pay_with_retry(tools, claim_id: str, amount: float, retries: int = 1) -> dict:
    """超时重试一次。

    ← 双打款就发生在这里：第一次调用其实已经把钱打出去了，
      只是客户端没收到确认；重试又打了一次。
    """
    for attempt in range(retries + 1):
        try:
            return tools.call("pay_out", claim_id=claim_id, amount=amount)
        except Exception:
            if attempt == retries:
                raise
            # 这里本该先查询"这笔到底打没打出去"，但绝大多数 agent 不会
