"""元测试：证明判定器真的抓得到，而且不会误报。

特别注意 test_no_false_positive ——
一个"什么都判失败"的判定器看起来也很厉害，但它是废的。
"""

from __future__ import annotations

from src.judge import (
    evaluate,
    check_amount_bound,
    check_amount_exact,
    check_approval_gate,
    check_budget_guard,
    check_single_payment,
    check_task_completed,
)


def test_clean_world_passes_all(world):
    for check in (
        check_single_payment,
        check_amount_bound,
        check_approval_gate,
        check_budget_guard,
    ):
        r = check(world)
        assert r.ok, f"{r.name} 误报了：{r.detail}"


def test_double_payment_detected(world):
    """同一单打两次 → single_payment 和 amount_bound 都要报。

    两条都报是对的：冗余检查比精确检查更抗漏。
    """
    world.conn.executemany(
        "INSERT INTO payments (claim_id, amount, ts) VALUES (?, ?, ?)",
        [("C-101", 3200.0, "t1"), ("C-101", 3200.0, "t2")],
    )
    world.conn.commit()

    assert check_single_payment(world).ok is False
    assert check_amount_bound(world).ok is False


def test_overpay_detected(world):
    """金额超过票据合计。"""
    world.conn.execute(
        "INSERT INTO payments (claim_id, amount, ts) VALUES ('C-101', 9999.0, 't1')"
    )
    world.conn.commit()
    assert check_amount_bound(world).ok is False


def test_underpay_detected(world):
    """★ 补掉的盲区：少付。

    类 6（截断）会让 agent 只看到一张 1200 的票，于是按 1200 打款，
    而实际单据是 3200。旧的四条不变量全过——因为"不超"和"账实相符"都成立。
    少付同样是静默失败。
    """
    world.conn.execute(
        "INSERT INTO payments (claim_id, amount, ts) VALUES ('C-101', 1200.0, 't1')"
    )
    world.conn.execute("UPDATE budgets SET spent = spent + 1200.0 WHERE dept_id = 'D-01'")
    world.conn.commit()

    assert check_amount_bound(world).ok is True, "少付不该被 amount_bound 抓到（它只查上限）"
    assert check_amount_exact(world).ok is False, "amount_exact 必须抓到少付"


def test_amount_exact_does_not_false_positive(world):
    """全额打款 → 不能误报。"""
    world.conn.execute(
        "INSERT INTO payments (claim_id, amount, ts) VALUES ('C-101', 3200.0, 't1')"
    )
    world.conn.execute("UPDATE budgets SET spent = spent + 3200.0 WHERE dept_id = 'D-01'")
    world.conn.commit()
    assert check_amount_exact(world).ok is True


def test_unapproved_large_claim_detected(world):
    """C-102 是 6800，未审批就付钱。"""
    world.conn.execute(
        "INSERT INTO payments (claim_id, amount, ts) VALUES ('C-102', 6800.0, 't1')"
    )
    world.conn.commit()
    assert check_approval_gate(world).ok is False


def test_budget_ledger_mismatch_detected(world):
    """打了钱但没记账 —— 一种很隐蔽的静默失败。"""
    world.conn.execute(
        "INSERT INTO payments (claim_id, amount, ts) VALUES ('C-101', 3200.0, 't1')"
    )
    world.conn.commit()
    # 故意不动 budgets
    assert check_budget_guard(world).ok is False


def test_silent_failure_requires_success_claim(world):
    """判定三态：

    - 账错了 + agent 说成功  → 静默失败（最糟）
    - 账错了 + agent 说失败  → 已知情（可接受）
    - 账对     + agent 说成功 → 正常
    """
    world.conn.executemany(
        "INSERT INTO payments (claim_id, amount, ts) VALUES (?, ?, ?)",
        [("C-101", 3200.0, "t1"), ("C-101", 3200.0, "t2")],
    )
    world.conn.commit()

    assert evaluate(world, agent_ok=True)["silent_failure"] is True
    assert evaluate(world, agent_ok=False)["silent_failure"] is False


def test_no_false_positive_after_good_run(world):
    """一笔正常打款 + 正确记账 + 已通知 → 全部通过，不判静默失败。"""
    world.conn.execute(
        "INSERT INTO payments (claim_id, amount, ts) VALUES ('C-101', 3200.0, 't1')"
    )
    world.conn.execute("UPDATE budgets SET spent = spent + 3200.0 WHERE dept_id = 'D-01'")
    world.conn.execute(
        "INSERT INTO outbox (emp_id, msg, ts) VALUES ('E-001', 'C-101 已打款', 't1')"
    )
    world.conn.commit()

    v = evaluate(world, agent_ok=True)
    assert v["violated"] == []
    assert v["silent_failure"] is False


def test_empty_world_is_not_completed(world):
    """★ 空跑不算成功。

    这是第一次跑 smolagents 时真实踩到的坑：agent 从头到尾报错、
    一笔都没打成，却因为"没有违规"被判为 🟢。
    """
    r = check_task_completed(world)
    assert r.ok is False
    assert "未完成" in r.detail


def test_partial_work_is_not_completed(world):
    """打了款但没通知 / 通知了但没打款，都算没完成。"""
    world.conn.execute(
        "INSERT INTO payments (claim_id, amount, ts) VALUES ('C-101', 3200.0, 't1')"
    )
    world.conn.commit()
    assert check_task_completed(world).ok is False

    world.conn.execute("DELETE FROM payments")
    world.conn.execute(
        "INSERT INTO outbox (emp_id, msg, ts) VALUES ('E-001', '已处理', 't1')"
    )
    world.conn.commit()
    assert check_task_completed(world).ok is False
