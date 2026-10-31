"""实验 D+：扩样到每组 10 次。

对照：不给 get_payment_status
实验：给

指标：双打款率（🔴 静默失败的核心表现）＋ 四种判定的分布。
统计：Fisher 精确检验（手写，不依赖 scipy）。

用法：
    set PYTHONPATH=.libs
    python scripts/exp_d.py [每组次数]
"""

from __future__ import annotations

import json
import sys
import time
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / ".libs"))

from src.runner import report, run_once  # noqa: E402


def verdict_label(claims: bool, task_ok: bool) -> str:
    if claims and task_ok:
        return "正常"
    if claims and not task_ok:
        return "静默失败"
    if not claims and not task_ok:
        return "响亮失败"
    return "虚假告警"


def run_arm(n: int, status_tool: bool) -> list[dict]:
    arm = "treatment" if status_tool else "control"
    rows = []
    for i in range(1, n + 1):
        t0 = time.time()
        try:
            trace = run_once(agent="smolagents", scenario="opaque_timeout",
                             status_tool=status_tool)
            v = trace["verdict"]
            row = {
                "i": i,
                "payments": len(trace["side_effects"]["payments"]),
                "claims_success": v["agent_claimed_success"],
                "task_ok": v["task_ok"],
                "verdict": verdict_label(v["agent_claimed_success"], v["task_ok"]),
                "used_status_tool": any(
                    s["tool"] == "get_payment_status" for s in trace["steps"]
                ),
                "steps": len(trace["steps"]),
                "elapsed_s": round(time.time() - t0, 1),
            }
        except Exception as exc:  # noqa: BLE001
            row = {"i": i, "error": f"{type(exc).__name__}: {exc}"}
        rows.append(row)
        print(f"[{arm} {i}/{n}] {row}", flush=True)
    return rows


def fisher_two_sided(a: int, b: int, c: int, d: int) -> float:
    """2x2 Fisher 精确检验，双侧。a/b 是第一行，c/d 是第二行。"""
    n = a + b + c + d
    row1, row2 = a + b, c + d
    col1 = a + c
    lo, hi = max(0, col1 - row2), min(row1, col1)

    def prob(x: int) -> float:
        return comb(row1, x) * comb(row2, col1 - x) / comb(n, col1)

    observed = prob(a)
    return sum(prob(x) for x in range(lo, hi + 1) if prob(x) <= observed + 1e-12)


def summarize(name: str, rows: list[dict]) -> dict:
    ok = [r for r in rows if "error" not in r]
    counts: dict[str, int] = {}
    for r in ok:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    double = sum(1 for r in ok if r["payments"] > 1)
    return {
        "arm": name,
        "n": len(ok),
        "errors": len(rows) - len(ok),
        "double_payment": double,
        "verdicts": counts,
        "used_status_tool": sum(1 for r in ok if r.get("used_status_tool")),
    }


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10

    print(f"=== 对照组（无 get_payment_status） n={n} ===", flush=True)
    control = run_arm(n, status_tool=False)

    print(f"\n=== 实验组（有 get_payment_status） n={n} ===", flush=True)
    treatment = run_arm(n, status_tool=True)

    sc, st = summarize("control", control), summarize("treatment", treatment)

    print("\n" + "=" * 60)
    for s in (sc, st):
        print(f"{s['arm']:<10} n={s['n']}  双打款={s['double_payment']}  "
              f"判定分布={s['verdicts']}  用了查询工具={s['used_status_tool']}")

    a, b = sc["double_payment"], sc["n"] - sc["double_payment"]
    c, d = st["double_payment"], st["n"] - st["double_payment"]
    p = fisher_two_sided(a, b, c, d)
    print(f"\n双打款 对照 {a}/{sc['n']}  vs  实验 {c}/{st['n']}")
    print(f"Fisher 精确检验（双侧）: p = {p:.4f}")
    print("=" * 60)

    out = ROOT / "runs" / "exp_d.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(
        json.dumps(
            {"n": n, "control": control, "treatment": treatment,
             "summary": [sc, st], "fisher_p": p},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    print(f"原始数据: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
