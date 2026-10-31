"""实验 H：框架层重试 —— 谁在替模型重试。

假设：模型自己很少重试（前面四个实验已经证实），
但**框架可以绕过模型直接重试节点**，而且模型全程不知情。

五个臂（固定 opaque_timeout，全部不给 get_payment_status）：

    msg              工具异常转成消息 → 模型自己决定（现状）
    raise            异常上抛 → 图崩溃
    retry-default    上抛 + LangGraph 默认 RetryPolicy
    retry-all        上抛 + 无差别重试（retry_on=lambda e: True）
    retry-all+idem   retry-all + pay_out 服务端幂等

关键差异来自 LangGraph 的默认策略 `default_retry_on`：
它对 RuntimeError 返回 False（视为编程错误），只重试 ConnectionError / HTTP 5xx。
所以"默认重试"实际上是安全的——但很多团队会顺手把重试打开。

用法：
    set PYTHONPATH=.libs
    python scripts/exp_h.py [每臂次数]
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

ARMS: list[tuple[str, dict, bool]] = [
    ("msg", {"agent_kwargs": {"on_tool_error": "message"}}, False),
    ("raise", {"agent_kwargs": {"on_tool_error": "raise"}}, False),
    ("retry-default", {"agent_kwargs": {"on_tool_error": "raise", "retry_attempts": 3}}, False),
    ("retry-all", {"agent_kwargs": {"on_tool_error": "raise", "retry_attempts": 3,
                                    "retry_on_all": True}}, False),
    ("retry-all+idem", {"agent_kwargs": {"on_tool_error": "raise", "retry_attempts": 3,
                                         "retry_on_all": True}}, True),
]


def run_arm(name: str, flags: dict, idempotent: bool, n: int) -> list[dict]:
    rows = []
    for i in range(1, n + 1):
        t0 = time.time()
        try:
            with redirect_stdout(io.StringIO()):
                t = run_once(agent="langgraph", scenario="opaque_timeout",
                             idempotent=idempotent, **flags)
            v = t["verdict"]
            rows.append({
                "i": i,
                "payments": len(t["side_effects"]["payments"]),
                "pay_calls": sum(1 for s in t["steps"] if s["tool"] == "pay_out"),
                "claims_success": v["agent_claimed_success"],
                "task_ok": v["task_ok"],
                "verdict": verdict_label(v["agent_claimed_success"], v["task_ok"]),
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
        "silent": sum(1 for r in ok if r["verdict"] == "静默失败"),
        "normal": sum(1 for r in ok if r["verdict"] == "正常"),
        "need_human": sum(1 for r in ok if r["verdict"] != "正常"),
        "pay_calls_gt1": sum(1 for r in ok if r["pay_calls"] > 1),
    }


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    results: dict[str, list[dict]] = {}

    for name, flags, idem in ARMS:
        print(f"\n=== {name} {'(idem)' if idem else ''} n={n} ===", flush=True)
        results[name] = run_arm(name, flags, idem, n)

    summaries = {name: summarize(name, results[name]) for name, _, _ in ARMS}

    print("\n" + "=" * 88)
    print(f"{'臂':<18}{'n':>3}{'双打款':>7}{'静默失败':>9}{'正常':>6}{'需人工':>7}{'重复调用':>9}")
    for name, _, _ in ARMS:
        s = summaries[name]
        print(f"{name:<18}{s['n']:>3}{s['double']:>7}{s['silent']:>9}"
              f"{s['normal']:>6}{s['need_human']:>7}{s['pay_calls_gt1']:>9}")

    def cmp(a: str, b: str, field: str) -> float:
        sa, sb = summaries[a], summaries[b]
        return fisher_two_sided(sa[field], sa["n"] - sa[field],
                                sb[field], sb["n"] - sb[field])

    print("\nFisher 精确检验（双侧）：")
    print(f"  默认重试有没有效   retry-default vs raise      双打款 p={cmp('retry-default','raise','double'):.4f}")
    print(f"  无差别重试的后果   retry-all vs raise          双打款 p={cmp('retry-all','raise','double'):.4f}")
    print(f"  幂等能否兜住       retry-all+idem vs retry-all 双打款 p={cmp('retry-all+idem','retry-all','double'):.4f}")
    print(f"  幂等能否恢复可用   retry-all+idem vs retry-all 需人工 p={cmp('retry-all+idem','retry-all','need_human'):.4f}")
    print("=" * 88)

    out = ROOT / "runs" / "exp_h.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"n": n, "summaries": summaries, "raw": results},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"原始数据: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
