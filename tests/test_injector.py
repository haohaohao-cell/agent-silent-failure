"""元测试：证明注入器真的注入了。

这组测试是整个项目的信任地基。它们绿了，后面的实验数字才有意义。
"""

from __future__ import annotations

import time

import pytest

from src.injector import FAULT_LIBRARY, Fault, Injector, ToolFault


def test_no_fault_passes_through(make_tools):
    tools, _ = make_tools()
    emp = tools.call("get_employee", emp_id="E-001")
    assert emp["name"] == "张三"


def test_delay_actually_delays(make_tools):
    """类1：必须真的变慢，而且最终结果正确。

    用 0.2 秒而不是 2 秒，否则每跑一次测试就等两秒，没人受得了。
    """
    fault = Fault(1, "get_employee", 1, "delay", {"seconds": 0.2})
    tools, _ = make_tools([fault])

    t0 = time.perf_counter()
    emp = tools.call("get_employee", emp_id="E-001")
    elapsed = time.perf_counter() - t0

    assert elapsed >= 0.2, f"注入器没生效：只花了 {elapsed:.3f}s"
    assert emp["name"] == "张三"


def test_raise_does_not_touch_db(make_tools, world):
    """类3：抛异常，且不应该产生任何副作用。"""
    fault = Fault(3, "pay_out", 1, "raise", {"reason": "503"})
    tools, _ = make_tools([fault])

    with pytest.raises(ToolFault):
        tools.call("pay_out", claim_id="C-101", amount=100)

    assert world.rows("payments") == [], "raise 故障不该写库"


def test_exec_then_raise_writes_then_raises(make_tools, world):
    """★ 类2：先执行（副作用发生），再抛错。

    这是双打款的来源，也是整个项目最关键的一条断言。
    """
    fault = Fault(2, "pay_out", 1, "exec_then_raise", {"reason": "timeout"})
    tools, _ = make_tools([fault])

    with pytest.raises(ToolFault):
        tools.call("pay_out", claim_id="C-101", amount=100)

    payments = world.rows("payments")
    assert len(payments) == 1, "服务端应该已经执行了，只是客户端没收到确认"
    assert payments[0]["amount"] == 100


def test_bad_return_does_not_touch_db(make_tools, world):
    """类4/5/6/7：伪造返回值，真实逻辑一行都不该跑。"""
    fault = Fault(4, "pay_out", 1, "bad_return", {"value": {"status": "ok"}})
    tools, _ = make_tools([fault])

    resp = tools.call("pay_out", claim_id="C-101", amount=100)

    assert resp == {"status": "ok"}
    assert world.rows("payments") == [], "bad_return 不该真的执行"


def test_duplicate_runs_twice(make_tools, world):
    """类8：一次调用，两次副作用。"""
    fault = Fault(8, "pay_out", 1, "duplicate")
    tools, _ = make_tools([fault])

    tools.call("pay_out", claim_id="C-101", amount=100)

    assert len(world.rows("payments")) == 2


def test_lookup_is_call_index_exact(make_tools, world):
    """故障只打在指定的那一次调用上，第 2 次必须正常。"""
    fault = Fault(3, "pay_out", 1, "raise", {"reason": "503"})
    tools, _ = make_tools([fault])

    with pytest.raises(ToolFault):
        tools.call("pay_out", claim_id="C-101", amount=100)

    tools.call("pay_out", claim_id="C-101", amount=100)
    assert len(world.rows("payments")) == 1


def test_trace_records_call_even_on_error(make_tools):
    """漏记是致命错误：抛异常的调用也必须留在 trace 里。"""
    fault = Fault(3, "pay_out", 1, "raise", {"reason": "503"})
    tools, recorder = make_tools([fault])

    with pytest.raises(ToolFault):
        tools.call("pay_out", claim_id="C-101", amount=100)

    steps = recorder.to_dict()
    assert len(steps) == 1
    assert steps[0]["error"] is not None
    assert steps[0]["injected"]["class"] == 3


@pytest.mark.parametrize("cls", sorted(FAULT_LIBRARY))
def test_every_fault_is_constructible(cls):
    """八类故障都能造出来，且工具名合法。"""
    f = FAULT_LIBRARY[cls]()
    assert isinstance(f, Fault)
    assert f.cls == cls
    assert f.kind in {"delay", "raise", "exec_then_raise", "bad_return", "duplicate"}


def test_unknown_kind_raises():
    inj = Injector([Fault(99, "pay_out", 1, "nonsense")])
    with pytest.raises(ValueError):
        inj.around("pay_out", 1, lambda: {})
