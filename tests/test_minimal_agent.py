"""框架 #0（手写 ReAct 循环）的测试。

重点不是"它能不能跑通"，而是**证明循环本身在鼓励重试**。
"""

from __future__ import annotations

import pytest

from src.agents.minimal_agent import ReActAgent
from src.injector import FAULT_LIBRARY, Fault, Injector
from src.models import ScriptedModel, ToolCall, Turn
from src.runner import run_once
from src.scenarios import expense_run
from src.tools import ToolBox
from src.trace import Recorder
from src.world import World


def _run(script, faults=None):
    world = World()
    recorder = Recorder()
    tools = ToolBox(world, Injector(faults or []), recorder)
    agent = ReActAgent(ScriptedModel(script))
    return agent.run(tools), world, recorder


def test_clean_loop_completes():
    result, world, recorder = _run(expense_run(will_error=False))
    assert result.ok is True
    assert "已完成" in result.message
    assert len(world.rows("payments")) == 1
    assert len(recorder.steps) == 6


def test_tool_error_is_fed_back_to_model():
    """关键机制：工具抛错不会让 agent 崩溃，错误会被喂回模型。"""
    _, _, recorder = _run(
        expense_run(will_error=True), [FAULT_LIBRARY[2]()]
    )
    first_pay = [s for s in recorder.steps if s.tool == "pay_out"][0]
    assert first_pay.error is not None


def test_retry_produces_double_payment():
    """★ 手写循环 + 重试 → 同样双打款，同样静默失败。

    这说明双打款不是某个框架的 bug，而是**循环范式本身的自然后果**。
    """
    result, world, _ = _run(expense_run(will_error=True), [FAULT_LIBRARY[2]()])
    assert result.ok is True
    assert len(world.rows("payments")) == 2


def test_max_steps_is_enforced():
    """模型一直要工具、不给答案 → 必须能停下来。"""
    forever = [Turn(tool_calls=[ToolCall("get_employee", {"emp_id": "E-001"})])] * 50
    world = World()
    tools = ToolBox(world, Injector([]), Recorder())
    agent = ReActAgent(ScriptedModel(forever), max_steps=3)
    result = agent.run(tools)
    assert result.ok is False
    assert "3" in result.message


def test_unknown_tool_is_reported_not_raised():
    """模型幻觉出一个不存在的工具 → 变成错误消息，不是崩溃。

    而且它最后说了"抱歉"，所以自述是**失败**，不是成功。
    """
    world = World()
    tools = ToolBox(world, Injector([]), Recorder())
    script = [
        Turn(tool_calls=[ToolCall("delete_all_money", {})]),
        Turn(text="抱歉，工具不可用"),
    ]
    result = ReActAgent(ScriptedModel(script)).run(tools)
    assert result.ok is False, "agent 自己说了抱歉，不该被当成成功"


def test_minimal_agent_end_to_end_is_silent_failure():
    """通过 runner 跑完整链路，判定必须和 fake agent 一致。"""
    trace = run_once(FAULT_LIBRARY[2](), agent="minimal")
    assert len(trace["side_effects"]["payments"]) == 2
    assert trace["verdict"]["silent_failure"] is True
    assert trace["agent"] == "minimal"


def test_minimal_baseline_is_clean():
    trace = run_once(agent="minimal")
    assert len(trace["side_effects"]["payments"]) == 1
    assert trace["verdict"]["violated"] == []
