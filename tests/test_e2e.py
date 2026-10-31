"""端到端：这个项目要证明的那件事。"""

from __future__ import annotations

from src.injector import FAULT_LIBRARY
from src.runner import run_once


def test_baseline_is_clean():
    """无故障 → 一单一次打款，判定正常。"""
    t = run_once()
    assert len(t["side_effects"]["payments"]) == 1
    assert t["verdict"]["violated"] == []
    assert t["verdict"]["silent_failure"] is False


def test_fault2_is_silent_failure():
    """★★★ 整个项目的核心断言 ★★★

    注入"服务端已执行、客户端超时"→ agent 重试 → 打了两次钱
    → 而 agent 自述"已完成报销打款"，判定为静默失败。
    """
    t = run_once(FAULT_LIBRARY[2]())

    assert len(t["side_effects"]["payments"]) == 2, "应该打了两笔"
    assert sum(p["amount"] for p in t["side_effects"]["payments"]) == 6400.0
    assert t["agent_result"]["ok"] is True, "agent 以为一切正常"
    assert t["verdict"]["silent_failure"] is True


def test_fault2_leaves_agent_claiming_success():
    """agent 的自述必须是"成功"—— 否则就不叫静默了。"""
    t = run_once(FAULT_LIBRARY[2]())
    assert "已完成" in t["agent_result"]["message"]


def test_large_claim_needs_approval_and_passes():
    """C-102 金额 6800，走了审批 → 正常。"""
    t = run_once(claim_id="C-102")
    assert len(t["side_effects"]["payments"]) == 1
    assert t["verdict"]["violated"] == []


def _semantic(steps: list[dict]) -> list[dict]:
    """只保留语义字段，去掉耗时。

    回放保证的是"决策序列一致"，不是微秒数一致。
    duration_ms 是观测噪声，把它纳入断言只会让测试变脆。
    """
    return [{k: v for k, v in s.items() if k != "duration_ms"} for s in steps]


def test_determinism():
    """跑两遍必须完全一致 —— 这是复现性的底线。

    （真接 LLM 之后这条会失效，所以必须靠录制回放来维持。）
    """
    a = run_once()
    b = run_once()
    assert a["side_effects"] == b["side_effects"]
    assert _semantic(a["steps"]) == _semantic(b["steps"])
    assert [s["tool"] for s in a["steps"]] == [s["tool"] for s in b["steps"]]


def test_trace_is_complete():
    """六步工具调用，一步都不能漏记。"""
    t = run_once()
    tools = [s["tool"] for s in t["steps"]]
    assert tools == [
        "get_employee",
        "get_receipts",
        "check_budget",
        "submit_approval",
        "pay_out",
        "notify",
    ]


def test_retry_shows_up_in_trace():
    """重试这件事本身必须留在 trace 里，否则事后没法解释钱的去向。"""
    t = run_once(FAULT_LIBRARY[2]())
    pay_calls = [s for s in t["steps"] if s["tool"] == "pay_out"]
    assert len(pay_calls) == 2
    assert pay_calls[0]["error"] is not None
    assert pay_calls[0]["injected"]["class"] == 2
    assert pay_calls[1]["error"] is None
