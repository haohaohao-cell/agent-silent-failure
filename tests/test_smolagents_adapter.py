"""框架 #1 适配器的接线测试。

**不需要 API key，也不调用模型。**
这里只验证一件事：smolagents 的工具如果被调用，是否真的走过了
ToolBox.call() —— 也就是故障注入和 trace 录制有没有生效。

这是整个多框架对比的前提。接线错了，后面所有数据都是假的。
"""

from __future__ import annotations

import pytest

from src.injector import Fault, Injector
from src.tools import ToolBox
from src.trace import Recorder
from src.world import World

smolagents = pytest.importorskip("smolagents", reason="未安装 smolagents")

from src.agents.smolagents_agent import build_tools  # noqa: E402


@pytest.fixture()
def wired():
    world = World()
    recorder = Recorder()
    toolbox = ToolBox(
        world,
        Injector([Fault(2, "pay_out", 1, "exec_then_raise", {"reason": "timeout"})]),
        recorder,
    )
    return toolbox, build_tools(toolbox), world, recorder


def test_builds_all_six_tools(wired):
    _, tools, _, _ = wired
    assert [t.name for t in tools] == [
        "get_employee",
        "get_receipts",
        "check_budget",
        "submit_approval",
        "pay_out",
        "notify",
    ]


def test_forward_goes_through_toolbox(wired):
    """★ 核心断言：框架里的工具调用必须被 harness 看见。"""
    _, tools, world, recorder = wired

    emp = [t for t in tools if t.name == "get_employee"][0]
    out = emp.forward(emp_id="E-001")

    assert out["name"] == "张三"
    assert len(recorder.steps) == 1
    assert recorder.steps[0].tool == "get_employee"


def test_fault_reaches_framework_layer(wired):
    """注入的故障必须能穿过 smolagents 的 Tool 包装。"""
    _, tools, world, recorder = wired
    pay = [t for t in tools if t.name == "pay_out"][0]

    with pytest.raises(Exception):
        pay.forward(claim_id="C-101", amount=100)

    assert len(world.rows("payments")) == 1, "服务端应该已执行"
    assert recorder.steps[0].error is not None


def test_tool_description_is_passed_through(wired):
    """工具的 description 和 inputs 要真的传下去，否则模型不知道该调什么。"""
    _, tools, _, _ = wired
    pay = [t for t in tools if t.name == "pay_out"][0]
    assert "打款" in pay.description
    assert set(pay.inputs) == {"claim_id", "amount"}
