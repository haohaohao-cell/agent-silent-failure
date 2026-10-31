"""框架 #2：LangGraph（显式状态图）。

和另外两个的架构差异：

    框架 #0（react）      自由循环，JSON 工具调用
    smolagents            自由循环，代码即行动
    LangGraph（本文件）   **显式状态图**：think → act → think，边是声明式的，
                         还能挂 checkpoint、人工中断、条件分支

为什么它值得单独测：
    自由循环的终止条件是"模型自己说完了"；
    状态图的终止条件是**写在边上的**。这两种控制流在出错时可能表现不同——
    图更容易在某个节点卡住，也更容易"按图纸走完但结果不对"。

分工说明（为了让架构变量干净）：
    图编排由 LangGraph 负责；模型调用和工具执行仍走本项目的 harness。
    LangGraph 的模型绑定层（langchain-openai）不参与——那是 SDK 差异，不是架构差异。
"""

from __future__ import annotations

import json
from typing import Any, TypedDict

from .base import AgentResult, claims_success
from .minimal_agent import SYSTEM_PROMPT, USER_PROMPT


class _State(TypedDict):
    messages: list[dict]
    steps: int
    pending: list[dict]
    text: str | None


class LangGraphAgent:
    name = "langgraph"

    def __init__(
        self,
        model,
        max_steps: int = 8,
        on_tool_error: str = "message",
        retry_attempts: int = 0,
        retry_on_all: bool = False,
    ) -> None:
        """三个开关是实验 H 的自变量。

        on_tool_error:
            "message" —— 工具异常转成消息喂回模型（模型自己决定怎么办）
            "raise"   —— 异常直接往上抛，模型**永远看不到**（交给框架处理）

        retry_attempts:
            >1 时给 act 节点挂 LangGraph 的 RetryPolicy。
            框架会在节点抛错后自动重跑整个节点 —— 模型全程不知情。

        retry_on_all:
            False —— 用 LangGraph 默认的 retry_on。
                     注意：默认策略**不重试 RuntimeError**（视为编程错误），
                     只重试 ConnectionError / HTTP 5xx 这类基础设施错误。
            True  —— 无差别重试（"顺手把重试打开"的常见运维做法）。
        """
        self.model = model
        self.max_steps = max_steps
        self.on_tool_error = on_tool_error
        self.retry_attempts = retry_attempts
        self.retry_on_all = retry_on_all

    # ------------------------------------------------------------------
    def run(self, tools, claim_id: str = "C-101") -> AgentResult:
        from langgraph.graph import END, START, StateGraph  # 懒加载

        specs = tools.specs
        max_steps = self.max_steps
        raise_on_error = self.on_tool_error == "raise"

        def think(state: _State) -> dict:
            turn = self.model.complete(state["messages"], specs)
            pending = [
                {"name": c.name, "args": c.args, "id": c.id} for c in turn.tool_calls
            ]
            return {
                "messages": state["messages"] + [turn.raw],
                "steps": state["steps"] + 1,
                "pending": pending,
                "text": turn.text,
            }

        def act(state: _State) -> dict:
            msgs = list(state["messages"])
            for tc in state["pending"]:
                msgs.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": _invoke(tools, tc, raise_on_error),
                    }
                )
            return {"messages": msgs, "pending": []}

        def route(state: _State) -> str:
            if state["steps"] >= max_steps:
                return "end"
            return "act" if state["pending"] else "end"

        graph = StateGraph(_State)
        graph.add_node("think", think)
        if self.retry_attempts > 1:
            # 框架层的自动重试：节点抛错后，整段 act 会被重跑一遍。
            # 对只读节点没问题；对 pay_out 这种有副作用的节点，就是重复执行。
            from langgraph.types import RetryPolicy

            policy = (
                RetryPolicy(max_attempts=self.retry_attempts, retry_on=lambda _e: True)
                if self.retry_on_all
                else RetryPolicy(max_attempts=self.retry_attempts)
            )
            graph.add_node("act", act, retry_policy=policy)
        else:
            graph.add_node("act", act)
        graph.add_edge(START, "think")
        graph.add_conditional_edges("think", route, {"act": "act", "end": END})
        graph.add_edge("act", "think")

        try:
            final: Any = graph.compile().invoke(
                {
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": USER_PROMPT.format(claim_id=claim_id)},
                    ],
                    "steps": 0,
                    "pending": [],
                    "text": None,
                }
            )
        except Exception as exc:  # noqa: BLE001
            return AgentResult(False, f"框架异常: {type(exc).__name__}: {exc}")

        if final.get("pending"):
            return AgentResult(False, f"超过 {max_steps} 步仍未完成")

        text = (final.get("text") or "").strip()
        return AgentResult(claims_success(text), text)


def _invoke(tools, tc: dict, raise_on_error: bool = False) -> str:
    """执行一次工具调用。

    raise_on_error=False：异常变成 {"error": ...} 消息喂回模型（模型能看见）
    raise_on_error=True ：异常直接上抛（模型永远看不到，交给框架处理）
    """
    try:
        return json.dumps(tools.call(tc["name"], **tc["args"]), ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001
        if raise_on_error:
            raise
        return json.dumps(
            {"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False
        )
