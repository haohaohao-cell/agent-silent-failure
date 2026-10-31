"""实验 B：跨模型验证。

问的是：**"缺观测就停摆"是强模型特有的谨慎，还是普遍行为？**

    chat-base      deepseek-chat      无查询工具
    chat-status    deepseek-chat      有查询工具
    reasoner-base  deepseek-reasoner  无查询工具
    reasoner-status deepseek-reasoner 有查询工具

关键比较：
    1. reasoner-base vs chat-base  —— 模型更强，会不会自己想办法？（天花板效应）
    2. reasoner-status vs reasoner-base —— 干预对推理模型还成立吗？

用法：
    set PYTHONPATH=.libs
    python scripts/exp_b.py [每臂次数]
"""

from __future__ import annotations

import io
import json
import os
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
    ("chat-base", {"model": "deepseek-chat", "status_tool": False}),
    ("chat-status", {"model": "deepseek-chat", "status_tool": True}),
    ("reasoner-base", {"model": "deepseek-reasoner", "status_tool": False}),
    ("reasoner-status", {"model": "deepseek-reasoner", "status_tool": True}),
]


def run_arm(name: str, model: str, status_tool: bool, n: int) -> list[dict]:
    os.environ["MODEL_ID"] = model
    rows = []
    for i in range(1, n + 1):
        t0 = time.time()
        try:
            with redirect_stdout(io.StringIO()):
                t = run_once(agent="smolagents", scenario="opaque_timeout",
                             status_tool=status_tool)
            v = t["verdict"]
            msg = t["agent_result"]["message"]
            rows.append({
                "i": i,
                "payments": len(t["side_effects"]["payments"]),
                "pay_calls": sum(1 for s in t["steps"] if s["tool"] == "pay_out"),
                "claims_success": v["agent_claimed_success"],
                "task_ok": v["task_ok"],
                "verdict": verdict_label(v["agent_claimed_success"], v["task_ok"]),
                "steps": len(t["steps"]),
                "has_status_line": "STATUS:" in msg.upper(),
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
        "no_status_line": sum(1 for r in ok if not r["has_status_line"]),
        "mean_steps": round(sum(r["steps"] for r in ok) / max(len(ok), 1), 1),
    }


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    results: dict[str, list[dict]] = {}

    for name, flags in ARMS:
        print(f"\n=== {name} {flags} n={n} ===", flush=True)
        results[name] = run_arm(name, n=n, **flags)

    summaries = {name: summarize(name, results[name]) for name, _ in ARMS}

    print("\n" + "=" * 86)
    print(f"{'臂':<16}{'n':>3}{'双打款':>7}{'正常':>6}{'需人工':>7}"
          f"{'重试':>5}{'无状态行':>8}{'平均步数':>9}")
    for name, _ in ARMS:
        s = summaries[name]
        print(f"{name:<16}{s['n']:>3}{s['double']:>7}{s['normal']:>6}"
              f"{s['need_human']:>7}{s['retried']:>5}{s['no_status_line']:>8}"
              f"{s['mean_steps']:>9}")

    def cmp(a: str, b: str, field: str) -> float:
        sa, sb = summaries[a], summaries[b]
        return fisher_two_sided(
            sa[field], sa["n"] - sa[field], sb[field], sb["n"] - sb[field]
        )

    print("\nFisher 精确检验（双侧）：")
    print(f"  模型效应   reasoner-base vs chat-base     需人工 p={cmp('reasoner-base','chat-base','need_human'):.4f}"
          f"   双打款 p={cmp('reasoner-base','chat-base','double'):.4f}")
    print(f"  干预效应   chat-status vs chat-base       需人工 p={cmp('chat-status','chat-base','need_human'):.4f}")
    print(f"  干预效应   reasoner-status vs reasoner-base 需人工 p={cmp('reasoner-status','reasoner-base','need_human'):.4f}")
    print("=" * 86)

    out = ROOT / "runs" / "exp_b.json"
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
