"""故障注入器。

⚠️ 这是**参考答案**，不是你的答案。D4 的任务是把它按你自己的理解重写一遍，
   并加上第 9 类故障。面试官会问"你怎么保证故障真的发生了"——
   答案必须长在你脑子里，不在这个文件里。

------------------------------------------------------------------
机制只有 5 个动词，八类故障全是它们的组合：

    delay            先睡，再正常执行            → "慢但成功"
    raise            不执行，直接抛错            → "干脆失败"
    exec_then_raise  先执行（副作用发生），再抛错 → ★ 双打款的来源
    bad_return       不执行，返回伪造的响应      → "200 但内容是错的"
    duplicate        执行两次                    → "重复副作用"

关键在 exec_then_raise：服务端真的做了，客户端只是没收到确认。
这不是 bug，这是分布式系统的日常。而 agent 看到超时，最"标准"的反应
就是重试 —— 于是同一笔钱打了两遍。

所以：**重复打款不是 agent 笨，是它做了最合理的容错动作。**
这一点想明白了，整个项目的立意就站住了。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable


class ToolFault(RuntimeError):
    """注入的故障。刻意和业务错误（ToolError）分开，方便判定。"""


@dataclass
class Fault:
    cls: int                  # 故障类别 1..8（见 PLAN.md 第 6 节）
    tool: str                 # 打在哪个工具上
    call_index: int           # 该工具的第几次调用（从 1 开始，确定性触发）
    kind: str                 # 5 个动词之一
    payload: dict = field(default_factory=dict)

    def describe(self) -> dict:
        return {
            "class": self.cls,
            "kind": self.kind,
            "tool": self.tool,
            "call_index": self.call_index,
            **self.payload,
        }


# ---------------------------------------------------------------------------
# 八类故障的参数表
# ---------------------------------------------------------------------------

def fault_1(tool: str = "pay_out", call_index: int = 1) -> Fault:
    """类1：超时 2 秒，但最终成功执行。"""
    return Fault(1, tool, call_index, "delay", {"seconds": 2.0})


def fault_2(tool: str = "pay_out", call_index: int = 1) -> Fault:
    """类2：服务端已执行，客户端超时没收响应。★ 双打款。"""
    return Fault(
        2, tool, call_index, "exec_then_raise",
        {"reason": "TimeoutError: 服务端已执行，客户端超时未收到响应"},
    )


def fault_3(tool: str = "get_employee", call_index: int = 1) -> Fault:
    """类3：直接抛异常。"""
    return Fault(3, tool, call_index, "raise", {"reason": "503 Service Unavailable"})


def fault_4(tool: str = "check_budget", call_index: int = 1) -> Fault:
    """类4：HTTP 200，但 body 里是错误码。"""
    return Fault(
        4, tool, call_index, "bad_return",
        {"value": {"error": "SYSTEM_BUSY", "code": 500, "dept_id": "D-01"}},
    )


def fault_5(tool: str = "get_receipts", call_index: int = 1) -> Fault:
    """类5：脏数据 —— 少了 total 字段。"""
    return Fault(
        5, tool, call_index, "bad_return",
        {"value": {"claim_id": "C-101", "items": [
            {"receipt_id": "R-1", "amount": 1200.0},
            {"receipt_id": "R-2", "amount": 2000.0},
        ]}},
    )


def fault_6(tool: str = "get_receipts", call_index: int = 1) -> Fault:
    """类6：截断 —— 只返回第 1 条，且不声明被截断。"""
    return Fault(
        6, tool, call_index, "bad_return",
        {"value": {"claim_id": "C-101", "items": [
            {"receipt_id": "R-1", "amount": 1200.0},
        ], "total": 1200.0}},
    )


def fault_7(tool: str = "check_budget", call_index: int = 1) -> Fault:
    """类7：陈旧 —— 返回上一轮的缓存（spent 是 0）。"""
    return Fault(
        7, tool, call_index, "bad_return",
        {"value": {"dept_id": "D-01", "total": 50000.0, "spent": 0.0, "remaining": 50000.0}},
    )


def fault_8(tool: str = "pay_out", call_index: int = 1) -> Fault:
    """类8：同一写操作被执行两次。"""
    return Fault(8, tool, call_index, "duplicate")


FAULT_LIBRARY: dict[int, Callable[..., Fault]] = {
    1: fault_1,
    2: fault_2,
    3: fault_3,
    4: fault_4,
    5: fault_5,
    6: fault_6,
    7: fault_7,
    8: fault_8,
}


# ---------------------------------------------------------------------------
# 组合场景：单类故障不足以暴露问题时用
# ---------------------------------------------------------------------------

def _opaque_timeout() -> list[Fault]:
    """不透明超时：付款超时，且**看不出它到底成没成**。

    为什么需要这个场景：

        第一次跑"超时"故障时，smolagents 居然自己躲过去了 ——
        它回去查预算，发现 spent 从 10000 变成 13200，于是判断
        "钱已经打出去了"，主动放弃重试。

        这说明**我们的故障是"漏"的**：pay_out 的副作用（预算扣减）
        恰好给了 agent 一个可观测的验证信号。

        真实系统里，这个信号往往拿不到 —— 查询有缓存、有延迟、
        或者根本查不到。所以加上第二层故障：让复查也看到旧数据。

    结果预期：agent 无法验证 → 只能相信"超时 = 没成功" → 重试 → 双打款。
    """
    return [
        Fault(
            2, "pay_out", 1, "exec_then_raise",
            {"reason": "TimeoutError: 服务端已执行，客户端超时未收到响应"},
        ),
        # 第 2 次查预算是 agent 的"复查"动作，这里让它读到付款前的旧快照
        Fault(
            9, "check_budget", 2, "bad_return",
            {"value": {"dept_id": "D-01", "total": 50000.0,
                       "spent": 10000.0, "remaining": 40000.0}},
        ),
    ]


SCENARIOS: dict[str, Callable[[], list[Fault]]] = {
    "opaque_timeout": _opaque_timeout,
}


# ---------------------------------------------------------------------------
# 注入器本体
# ---------------------------------------------------------------------------

class Injector:
    """在工具边界上做手脚。不碰模型，不碰框架内部 —— 所以框架无关。"""

    def __init__(self, faults: list[Fault] | None = None) -> None:
        self.faults: list[Fault] = list(faults or [])

    def lookup(self, tool: str, call_index: int) -> Fault | None:
        """按 (工具名, 调用序号) 精确匹配。确定性，不用概率。"""
        for f in self.faults:
            if f.tool == tool and f.call_index == call_index:
                return f
        return None

    def around(
        self,
        tool: str,
        call_index: int,
        fn: Callable[[], dict],
    ) -> dict:
        """包住一次真实调用。fn 是这次调用的真实实现。"""
        fault = self.lookup(tool, call_index)
        if fault is None:
            return fn()

        kind, payload = fault.kind, fault.payload

        if kind == "delay":
            time.sleep(payload.get("seconds", 2.0))
            return fn()

        if kind == "raise":
            raise ToolFault(payload.get("reason", "injected fault"))

        if kind == "exec_then_raise":
            fn()  # ← 副作用已经发生了，收不回来
            raise ToolFault(payload.get("reason", "timeout after execution"))

        if kind == "bad_return":
            return payload["value"]

        if kind == "duplicate":
            fn()
            return fn()

        raise ValueError(f"未知故障类型: {kind}")
