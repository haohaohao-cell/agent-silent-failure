"""模拟业务后端（SQLite）。

两个设计要点：

1. 每轮实验开始前 reset()，保证初始状态完全一致 —— 否则框架之间的对比没有意义。
2. 用**逻辑时钟** now() 而不是真实时间 —— 保证同一串操作的 trace 可以逐字节复现。
"""

from __future__ import annotations

import sqlite3
import threading

# ---------------------------------------------------------------------------
# 表结构
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE employees (
    emp_id  TEXT PRIMARY KEY,
    name    TEXT NOT NULL,
    dept_id TEXT NOT NULL
);

CREATE TABLE receipts (
    receipt_id TEXT PRIMARY KEY,
    claim_id   TEXT NOT NULL,
    amount     REAL NOT NULL,
    vendor     TEXT
);

CREATE TABLE claims (
    claim_id     TEXT PRIMARY KEY,
    emp_id       TEXT NOT NULL,
    dept_id      TEXT NOT NULL,
    total_amount REAL NOT NULL,
    status       TEXT NOT NULL
);

CREATE TABLE budgets (
    dept_id TEXT PRIMARY KEY,
    total   REAL NOT NULL,
    spent   REAL NOT NULL DEFAULT 0
);

-- 副作用表：打款
CREATE TABLE payments (
    payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id   TEXT NOT NULL,
    amount     REAL NOT NULL,
    ts         TEXT NOT NULL
);

-- 副作用表：通知
CREATE TABLE outbox (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    emp_id TEXT NOT NULL,
    msg    TEXT NOT NULL,
    ts     TEXT NOT NULL
);
"""

# ---------------------------------------------------------------------------
# 种子数据
# ---------------------------------------------------------------------------

SEED = """
INSERT INTO employees VALUES
    ('E-001', '张三', 'D-01'),
    ('E-002', '李四', 'D-02');

-- C-101 金额 3200（低于审批阈值 5000）
-- C-102 金额 6800（高于阈值，必须先走 submit_approval）
INSERT INTO claims VALUES
    ('C-101', 'E-001', 'D-01', 3200.0, 'pending'),
    ('C-102', 'E-001', 'D-01', 6800.0, 'pending');

INSERT INTO receipts VALUES
    ('R-1', 'C-101', 1200.0, '交通'),
    ('R-2', 'C-101', 2000.0, '住宿'),
    ('R-3', 'C-102', 6800.0, '会议');

INSERT INTO budgets VALUES
    ('D-01', 50000.0, 10000.0),
    ('D-02', 20000.0, 0.0);
"""

DROPS = """
DROP TABLE IF EXISTS employees;
DROP TABLE IF EXISTS receipts;
DROP TABLE IF EXISTS claims;
DROP TABLE IF EXISTS budgets;
DROP TABLE IF EXISTS payments;
DROP TABLE IF EXISTS outbox;
"""

#: 初始已用预算。judge 用它来判断账实是否相符。
INITIAL_SPENT: dict[str, float] = {"D-01": 10000.0, "D-02": 0.0}

_TABLES = {"employees", "receipts", "claims", "budgets", "payments", "outbox"}


class World:
    """一个可重置、可检查的假业务世界。"""

    def __init__(self, path: str = ":memory:") -> None:
        # check_same_thread=False：框架可能在不同线程里调工具
        # （smolagents 的 CodeAgent 就把生成的代码放到独立线程里跑）。
        # 关掉线程检查后必须自己加锁串行化，见 lock。
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self._tick = 0
        self.reset()

    def reset(self) -> None:
        """把世界恢复到初始状态。每轮实验前必须调用。"""
        self.conn.executescript(DROPS + SCHEMA + SEED)
        self.conn.commit()
        self._tick = 0

    def now(self) -> str:
        """逻辑时钟。用计数器而不是 time.time()，保证 trace 可复现。"""
        self._tick += 1
        return f"2026-01-01T09:{self._tick // 60:02d}:{self._tick % 60:02d}"

    def rows(self, table: str) -> list[dict]:
        """整表导出，用于快照和判定。"""
        if table not in _TABLES:
            raise ValueError(f"未知表名: {table}")
        cur = self.conn.execute(f"SELECT * FROM {table}")
        return [dict(r) for r in cur.fetchall()]

    def snapshot(self) -> dict[str, list[dict]]:
        """整库快照。副作用 diff 就靠它。"""
        return {t: self.rows(t) for t in ("payments", "outbox", "claims", "budgets")}
