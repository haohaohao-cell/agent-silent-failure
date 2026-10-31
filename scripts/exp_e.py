"""实验 E：服务端幂等 vs 工具可观测性，两种修复能否互相替代。

四个臂（固定 opaque_timeout 场景）：

    baseline  无幂等、无查询工具
    idem      服务端幂等（重复调用不重复出款），无查询工具
    status    有查询工具，无幂等
    both      两个都有

核心问题：
    幂等能救钱，但它能不能让 agent 知道"刚才到底成没成"？
    如果能 → 两个修复可以互相替代。
    如果不能 → 它们解决的是两个不同的问题，谁也替代不了谁。

用法：
    set PYTHONPATH=.libs
    python scripts/exp_e.py [每臂次数]
"""

from __future__ import annotations

import io
import json
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / ".libs"))

from scripts.exp_d import fisher_two_sided, verdict_label  # noqa: E402
from src.runner import run_once  # noqa: E402

ARMS: list[tuple[str, dict]] = [
    ("baseline", {"status_tool": False, "idempotent": False}),
    ("idem", {"status_tool": False, "idempotent": True}),
    ("status", {"status_tool": True, "idempotent": False}),
    ("both", {"status_tool": True, "idempotent": True}),
]


def run_arm(name: str, flags: dict, n: int) -> list[dict]:
    rows = []
    for i in range(1, n + 1):
        t0 = time.time()
        try:
            # smolagents 会往 stdout 打满整个执行轨迹，这里吞掉，只留进度
            with redirect_stdout(io.StringIO()):
                t = run_once(agent="smolagents", scenario="opaque_timeout", **flags)
            v = t["verdict"]
            rows.append(
                {
                    "i": i,
                    "payments": len(t["side_effects"]["payments"]),
                    "pay_calls": sum(1 for s in t["steps"] if s["tool"] == "pay_out"),
                    "claims_success": v["agent_claimed_success"],
                    "task_ok": v["task_ok"],
                    "verdict": verdict_label(v["agent_claimed_success"], v["task_ok"]),
                    "used_status_tool": any(
                        s["tool"] == "get_payment_status" for s in t["steps"]
                    ),
                    "elapsed_s": round(time.time() - t0, 1),
                }
            )
        except Exception as exc:  # noqa: BLE001
            rows.append({"i": i, "error": f"{type(exc).__name__}: {exc}"})
        r = rows[-1]
        print(f"[{name} {i}/{n}] {r}", flush=True)
    return rows


def summarize(name: str, rows: list[dict]) -> dict:
    ok = [r for r in rows if "error" not in r]
    return {
        "arm": name,
        "n": len(ok),
        "double": sum(1 for r in ok if r["payments"] > 1),
        "normal": sum(1 for r in ok if r["verdict"] == "正常"),
        "need_human": sum(1 for r in ok if r["verdict"] != "正常"),
        "retried": sum(1 for r in ok if r["pay_calls"] > 1),
        "used_status": sum(1 for r in ok if r["used_status_tool"]),
        "verdicts": _count(ok),
    }


def _count(rows: list[dict]) -> dict:
    out: dict[str, int] = {}
    for r in rows:
        out[r["verdict"]] = out.get(r["verdict"], 0) + 1
    return out


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    results: dict[str, list[dict]] = {}

    for name, flags in ARMS:
        print(f"\n=== {name} {flags} n={n} ===", flush=True)
        results[name] = run_arm(name, flags, n)

    summaries = [summarize(name, results[name]) for name, _ in ARMS]

    print("\n" + "=" * 78)
    print(f"{'臂':<10}{'n':>3}{'双打款':>7}{'正常':>6}{'需人工':>7}{'重试过':>7}{'用查询工具':>9}  判定分布")
    for s in summaries:
        print(
            f"{s['arm']:<10}{s['n']:>3}{s['double']:>7}{s['normal']:>6}"
            f"{s['need_human']:>7}{s['retried']:>7}{s['used_status']:>9}  {s['verdicts']}"
        )

    base = summaries[0]
    print("\n与 baseline 比较（Fisher 精确检验，双侧）：")
    for s in summaries[1:]:
        p_double = fisher_two_sided(
            base["double"], base["n"] - base["double"],
            s["double"], s["n"] - s["double"],
        )
        p_human = fisher_two_sided(
            base["need_human"], base["n"] - base["need_human"],
            s["need_human"], s["n"] - s["need_human"],
        )
        print(f"  {s['arm']:<9} 双打款 p={p_double:.4f}   需人工 p={p_human:.4f}")
    print("=" * 78)

    out = ROOT / "runs" / "exp_e.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(
        json.dumps({"n": n, "summaries": summaries, "raw": results},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"原始数据: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
