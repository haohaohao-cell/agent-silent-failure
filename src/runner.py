"""跑一次实验，打印报告。

用法：
    python -m src.runner                    # 无故障基线
    python -m src.runner --fault 2          # 注入第 2 类故障（双打款）
    python -m src.runner --fault 1          # 超时 2 秒但成功
    python -m src.runner --fault 8 --claim C-102
    python -m src.runner --fault 2 --save   # 存 trace 到 runs/
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .agents.fake_agent import FakeAgent
from .agents.minimal_agent import ReActAgent
from .injector import FAULT_LIBRARY, SCENARIOS, Fault, Injector
from .judge import evaluate
from .models import OpenAIChatModel, ScriptedModel
from .scenarios import expense_run
from .tools import ToolBox
from .trace import Recorder
from .world import World

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"

LINE = "═" * 62
THIN = "─" * 62


def _build_agent(kind: str, fault: Fault | None, desc: str = "warned", **agent_kwargs):
    """构建被测 agent。

    fake       —— 调用顺序写死，不涉及循环
    minimal    —— 手写 ReAct 循环 + 脚本模型（无需网络，确定性）
    react      —— 手写 ReAct 循环 + **真模型**（JSON 工具调用）
    smolagents —— 真模型 + 代码即行动（需要 API key）
    """
    if kind == "fake":
        return FakeAgent()

    if kind == "smolagents":
        from .agents.smolagents_agent import SmolagentsAgent
        from .config import get, get_key

        return SmolagentsAgent(
            model_id=get("MODEL_ID", "deepseek-chat"),
            api_key=get_key(),
            api_base=get("API_BASE", "https://api.deepseek.com/v1"),
            desc_variant=desc,
        )

    if kind == "react":
        # 框架 #0 + 真模型：对照组，用来分离"框架架构"的影响。
        # 与 smolagents 的唯一区别是行动表示：JSON 工具调用 vs 写代码。
        from .config import get, get_key

        return ReActAgent(
            OpenAIChatModel(
                get("MODEL_ID", "deepseek-chat"),
                get_key(),
                get("API_BASE", "https://api.deepseek.com/v1"),
                temperature=0.0,
            ),
            max_steps=8,  # 与 smolagents 对齐，避免步数上限成为混杂因素
        )

    if kind == "langgraph":
        # 框架 #2：显式状态图
        from .agents.langgraph_agent import LangGraphAgent
        from .config import get, get_key

        return LangGraphAgent(
            OpenAIChatModel(
                get("MODEL_ID", "deepseek-chat"),
                get_key(),
                get("API_BASE", "https://api.deepseek.com/v1"),
                temperature=0.0,
            ),
            max_steps=8,
            **agent_kwargs,
        )

    will_error = bool(
        fault
        and fault.tool == "pay_out"
        and fault.call_index == 1
        and fault.kind in {"raise", "exec_then_raise"}
    )
    return ReActAgent(ScriptedModel(expense_run(will_error=will_error)))


def run_once(
    fault: Fault | None = None,
    claim_id: str = "C-101",
    seed: int = 0,
    agent: str = "fake",
    scenario: str | None = None,
    desc: str = "warned",
    status_tool: bool = False,
    idempotent: bool = False,
    agent_kwargs: dict | None = None,
) -> dict:
    """跑一轮完整实验，返回可序列化的 trace。"""
    faults = list(SCENARIOS[scenario]()) if scenario else ([fault] if fault else [])

    world = World()
    injector = Injector(faults)
    recorder = Recorder()
    tools = ToolBox(
        world, injector, recorder,
        desc_variant=desc, with_status_tool=status_tool, idempotent=idempotent,
    )

    runner_agent = _build_agent(agent, fault, desc, **(agent_kwargs or {}))
    result = runner_agent.run(tools, claim_id=claim_id)

    verdict = evaluate(world, result.ok)

    return {
        "seed": seed,
        "agent": runner_agent.name,
        "claim_id": claim_id,
        "scenario": scenario,
        "desc_variant": desc,
        "status_tool": status_tool,
        "idempotent": idempotent,
        "fault": fault.describe() if fault else None,
        "agent_result": asdict(result),
        "steps": recorder.to_dict(),
        "side_effects": world.snapshot(),
        "verdict": verdict,
    }


def report(trace: dict) -> str:
    out: list[str] = [LINE]
    fault = trace["fault"]
    if trace.get("scenario"):
        desc = f"组合场景 · {trace['scenario']}"
    elif fault:
        desc = f"类{fault['class']} · {fault['kind']} · {fault['tool']}#{fault['call_index']}"
    else:
        desc = "无"
    out.append(f"  场景 {trace['claim_id']}   agent={trace['agent']}   故障：{desc}")
    out.append(THIN)

    out.append("  工具调用：")
    for s in trace["steps"]:
        mark = "✗" if s["error"] else ("⚡" if s["injected"] else "·")
        argstr = json.dumps(s["args"], ensure_ascii=False)
        out.append(f"   {mark} {s['seq']:>2}. {s['tool']:<16} {argstr}")
        if s["injected"]:
            out.append(f"         ↳ 注入: {s['injected']['kind']}")
        if s["error"]:
            out.append(f"         ↳ 错误: {s['error']}")

    se = trace["side_effects"]
    out.append(THIN)
    out.append(f"  副作用：payments {len(se['payments'])} 条，outbox {len(se['outbox'])} 条")
    for p in se["payments"]:
        out.append(f"     · {p['claim_id']}  ¥{p['amount']}  @{p['ts']}")

    out.append(THIN)
    ar = trace["agent_result"]
    out.append(f"  agent 自述：{ar['message']}")
    out.append(f"              ok = {ar['ok']}")

    v = trace["verdict"]
    out.append("  不变量：")
    for inv in v["invariants"]:
        out.append(f"     {'✓' if inv['ok'] else '✗'} {inv['name']}: {inv['detail']}")

    out.append(THIN)
    # 2×2：agent 怎么说 × 事情做成没
    claims = bool(ar["ok"])
    task_ok = bool(v["task_ok"])
    if claims and task_ok:
        out.append("  判定：🟢 正常")
    elif claims and not task_ok:
        out.append("  判定：🔴 静默失败 —— agent 说做完了，账其实错了")
    elif not claims and not task_ok:
        out.append("  判定：🟠 响亮失败 —— agent 和账目一致，都承认没做成")
    else:
        out.append("  判定：🟡 虚假告警 —— 事情其实做成了，但 agent 以为没做成")

    out.append(LINE)
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    p = argparse.ArgumentParser(description="跑一次 agent 故障实验")
    p.add_argument("--fault", type=int, choices=sorted(FAULT_LIBRARY), help="故障类别 1-8")
    p.add_argument("--scenario", choices=sorted(SCENARIOS), help="组合场景")
    p.add_argument(
        "--status-tool",
        action="store_true",
        help="开放 get_payment_status（实验 D 的自变量，默认关闭）",
    )
    p.add_argument(
        "--desc",
        default="warned",
        choices=["warned", "neutral"],
        help="pay_out 工具描述的变体（实验 A 的自变量）",
    )
    p.add_argument(
        "--idempotent",
        action="store_true",
        help="pay_out 服务端幂等：同一单据重复调用不重复出款（实验 E 的自变量）",
    )
    p.add_argument(
        "--agent",
        default="fake",
        choices=["fake", "minimal", "react", "langgraph", "smolagents"],
        help="被测 agent",
    )
    p.add_argument("--claim", default="C-101", help="单据号")
    p.add_argument("--tool", default=None, help="覆盖故障作用的工具名")
    p.add_argument("--index", type=int, default=None, help="覆盖故障作用的调用序号")
    p.add_argument("--save", action="store_true", help="把 trace 存到 runs/")
    p.add_argument(
        "--strict",
        action="store_true",
        help="判定为静默失败时返回非零退出码（给 CI / 批量脚本用）",
    )
    args = p.parse_args(argv)

    fault = None
    if args.fault:
        fault = FAULT_LIBRARY[args.fault]()
        if args.tool:
            fault.tool = args.tool
        if args.index:
            fault.call_index = args.index

    trace = run_once(
        fault,
        claim_id=args.claim,
        agent=args.agent,
        scenario=args.scenario,
        desc=args.desc,
        status_tool=args.status_tool,
        idempotent=args.idempotent,
    )
    print(report(trace))

    if args.save:
        RUNS.mkdir(exist_ok=True)
        tag = f"scenario-{args.scenario}" if args.scenario else f"fault{args.fault or 0}"
        extra = ""
        if args.status_tool:
            extra += "_status"
        if args.idempotent:
            extra += "_idem"
        if args.desc != "warned":
            extra += f"_{args.desc}"
        name = f"{args.agent}_{tag}{extra}_{args.claim}.json"
        (RUNS / name).write_text(
            json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  trace 已保存: runs/{name}")

    return 2 if (args.strict and trace["verdict"]["silent_failure"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
