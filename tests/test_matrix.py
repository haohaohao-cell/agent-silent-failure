"""2×2 判定矩阵的测试。

    ┌──────────────┬──────────────┬──────────────┐
    │              │ 任务做成      │ 任务没做成    │
    ├──────────────┼──────────────┼──────────────┤
    │ 声称成功      │   🟢 正常     │  🔴 静默失败  │
    │ 声称失败      │   🟡 虚假告警  │  🟠 响亮失败  │
    └──────────────┴──────────────┴──────────────┘

这个矩阵是本项目真正的产出。单一的 SFR 数字会丢掉一半的信息：
"agent 以为自己失败、其实成功了" 同样是有代价的（人工复核、重复处理）。
"""

from __future__ import annotations

from src.judge import evaluate


def _good_world(world):
    world.conn.execute(
        "INSERT INTO payments (claim_id, amount, ts) VALUES ('C-101', 3200.0, 't1')"
    )
    world.conn.execute("UPDATE budgets SET spent = spent + 3200.0 WHERE dept_id = 'D-01'")
    world.conn.execute(
        "INSERT INTO outbox (emp_id, msg, ts) VALUES ('E-001', 'C-101 已打款', 't1')"
    )
    world.conn.commit()


def _bad_world(world):
    world.conn.executemany(
        "INSERT INTO payments (claim_id, amount, ts) VALUES (?, ?, ?)",
        [("C-101", 3200.0, "t1"), ("C-101", 3200.0, "t2")],
    )
    world.conn.commit()


def test_true_success(world):
    _good_world(world)
    v = evaluate(world, agent_ok=True)
    assert (v["agent_claimed_success"], v["task_ok"]) == (True, True)
    assert v["silent_failure"] is False


def test_silent_failure(world):
    _bad_world(world)
    v = evaluate(world, agent_ok=True)
    assert (v["agent_claimed_success"], v["task_ok"]) == (True, False)
    assert v["silent_failure"] is True


def test_loud_failure(world):
    _bad_world(world)
    v = evaluate(world, agent_ok=False)
    assert (v["agent_claimed_success"], v["task_ok"]) == (False, False)
    assert v["silent_failure"] is False


def test_false_alarm(world):
    """★ 虚假告警：任务其实做成了，agent 却以为没做成。

    这就是 smolagents 在 opaque_timeout 下的真实表现：
    钱打出去了、通知发了、四条不变量全过，但它说"需人工介入核实"。
    按 2×2 它属于 (False, True)。
    """
    _good_world(world)
    v = evaluate(world, agent_ok=False)
    assert (v["agent_claimed_success"], v["task_ok"]) == (False, True)
    assert v["silent_failure"] is False
