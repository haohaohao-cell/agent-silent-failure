"""幂等的单元测试。

实验 E 的自变量必须在跑实验之前被证明真的生效 ——
否则又是一个"自变量没改到"的坑。
"""

from __future__ import annotations

from src.injector import Injector
from src.tools import ToolBox
from src.trace import Recorder
from src.world import World


def _tools(world, idempotent: bool) -> ToolBox:
    return ToolBox(world, Injector([]), Recorder(), idempotent=idempotent)


def test_without_idempotency_double_call_pays_twice():
    world = World()
    tools = _tools(world, idempotent=False)

    tools.call("pay_out", claim_id="C-101", amount=3200.0)
    tools.call("pay_out", claim_id="C-101", amount=3200.0)

    assert len(world.rows("payments")) == 2
    assert world.rows("budgets")[0]["spent"] == 10000.0 + 6400.0


def test_with_idempotency_double_call_pays_once():
    world = World()
    tools = _tools(world, idempotent=True)

    first = tools.call("pay_out", claim_id="C-101", amount=3200.0)
    second = tools.call("pay_out", claim_id="C-101", amount=3200.0)

    assert first["status"] == "ok"
    assert second["status"] == "already_paid"
    assert second["deduplicated"] is True
    assert len(world.rows("payments")) == 1
    assert world.rows("budgets")[0]["spent"] == 10000.0 + 3200.0


def test_idempotency_does_not_tell_you_it_was_retried():
    """★ 关键性质：幂等让重复调用无害，但**不提供观测**。

    第二次调用返回 already_paid，这是"我这一次没造成新后果"，
    不等于"上一次成功了没有"。agent 拿不到历史，仍然不知道自己处在什么状态。
    """
    world = World()
    tools = _tools(world, idempotent=True)

    tools.call("pay_out", claim_id="C-101", amount=3200.0)
    second = tools.call("pay_out", claim_id="C-101", amount=3200.0)

    # 它能看到"已付过一次"，但看不到"第一次是在什么情况下成功的"
    assert "ts" not in second, "幂等返回不应携带可追溯的时间信息"
