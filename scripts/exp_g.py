"""实验 G：加入第三个框架 LangGraph（显式状态图）。

补齐"跨框架"这条局限：此前只对比了两种自由循环（JSON 调用 / 代码即行动），
现在加入一个**显式状态图**，看结论是否仍然成立。

用法：
    set PYTHONPATH=.libs
    python scripts/exp_g.py [每臂次数]
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
    ("graph-base", {"status_tool": False}),
    ("graph-status", {"status_tool": True}),
]


def run_arm(name: str, status_tool: bool, n: int) -> list[dict]:
    rows = []
    for i in range(1, n + 1):
        t0 = time.time()
        try:
            with redirect_stdout(io.StringIO()):
                t = run_once(agent="langgraph", scenario="opaque_timeout",
                             status_tool=status_tool)
            v = t["verdict"]
            rows.append({
                "i": i,
                "payments": len(t["side_effects"]["payments"]),
                "pay_calls": sum(1 for s in t["steps"] if s["tool"] == "pay_out"),
                "claims_success": v["agent_claimed_success"],
                "task_ok": v["task_ok"],
                "verdict": verdict_label(v["agent_claimed_success"], v["task_ok"]),
                "steps": len(t["steps"]),
                "used_status_tool": any(s["tool"] == "get_payment_status" for s in t["steps"]),
                "elapsed_s": round(time.time() - t0, 1),
            })
        except Exception as exc:  # noqa: BLE001
            rows.append({"i": i, "error": f"{type(exc).__name__}: {exc}"})
        print(f"[{name} {i}/{n}] {rows[-1]}", flush=True)
    return rows


def summarize(name: str, rows: list[dict]) -> dict:
    ok = [r for r in rows if "error" not in r]
    return {
        "arm": name,
        "n": len(ok),
        "errors": len(rows) - len(ok),
        "double": sum(1 for r in ok if r["payments"] > 1),
        "normal": sum(1 for r in ok if r["verdict"] == "正常"),
        "need_human": sum(1 for r in ok if r["verdict"] != "正常"),
        "retried": sum(1 for r in ok if r["pay_calls"] > 1),
        "mean_steps": round(sum(r["steps"] for r in ok) / max(len(ok), 1), 1),
    }


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    results: dict[str, list[dict]] = {}

    for name, flags in ARMS:
        print(f"\n=== {name} {flags} n={n} ===", flush=True)
        results[name] = run_arm(name, n=n, **flags)

    summaries = {name: summarize(name, results[name]) for name, _ in ARMS}

    print("\n" + "=" * 72)
    print(f"{'臂':<16}{'n':>3}{'双打款':>7}{'正常':>6}{'需人工':>7}{'重试':>5}{'平均步数':>9}")
    for name, _ in ARMS:
        s = summaries[name]
        print(f"{name:<16}{s['n']:>3}{s['double']:>7}{s['normal']:>6}"
              f"{s['need_human']:>7}{s['retried']:>5}{s['mean_steps']:>9}")

    a, b = summaries["graph-base"], summaries["graph-status"]
    p = fisher_two_sided(a["need_human"], a["n"] - a["need_human"],
                         b["need_human"], b["n"] - b["need_human"])
    print(f"\n观测效应（需人工）graph-status vs graph-base: p = {p:.4f}")
    print("=" * 72)

    out = ROOT / "runs" / "exp_g.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"n": n, "summaries": summaries, "raw": results},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"原始数据: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
