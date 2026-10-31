"""模型抽象层。

只做一件事：把「一次模型调用」抽象出来，让 agent 循环不关心背后是谁。

两个实现：

    ScriptedModel      给定一串预先写好的回复，按顺序吐出来。
                       确定性 → 可测试 → 这就是**回放器**的雏形。
    OpenAIChatModel    走 HTTP 调任意 OpenAI 兼容接口（DeepSeek / 通义 / vLLM…）。
                       只用标准库 urllib，不装任何 SDK。

为什么先写 ScriptedModel 不是"偷懒"：
    录制回放需要它。没有它，"同一 trace 跑两遍结果必须一致"这条根本做不到。
    它既是测试替身，也是项目后面要用的基础设施。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ToolCall:
    name: str
    args: dict
    id: str = ""


@dataclass
class Turn:
    """模型的一次输出：要么说话，要么调工具（可以同时）。"""

    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)

    @property
    def raw(self) -> dict:
        """还原成 OpenAI 协议的 assistant message，好塞回对话历史。"""
        msg: dict = {"role": "assistant", "content": self.text or ""}
        if self.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.args, ensure_ascii=False),
                    },
                }
                for tc in self.tool_calls
            ]
        return msg


class Model(Protocol):
    def complete(self, messages: list[dict], tools: list[dict]) -> Turn:
        ...


# ---------------------------------------------------------------------------
# 1) 脚本模型：确定性，用于测试和回放
# ---------------------------------------------------------------------------

class ScriptedModel:
    """按剧本回复。剧本跑完还继续要，就抛错——说明循环有问题。"""

    def __init__(self, script: list[Turn], name: str = "scripted") -> None:
        self.script = list(script)
        self.name = name
        self.calls = 0

    def complete(self, messages: list[dict], tools: list[dict]) -> Turn:
        self.calls += 1
        if not self.script:
            raise RuntimeError("剧本已用完，但 agent 还要继续 —— 检查循环终止条件")
        turn = self.script.pop(0)
        # 补上 id，让 tool 消息能对上
        for i, tc in enumerate(turn.tool_calls):
            if not tc.id:
                tc.id = f"call_{self.calls}_{i}"
        return turn


# ---------------------------------------------------------------------------
# 2) 真实模型：OpenAI 兼容接口，只用标准库
# ---------------------------------------------------------------------------

class OpenAIChatModel:
    """任何 OpenAI 兼容端点都能用。

        OpenAIChatModel("deepseek-chat", api_key, "https://api.deepseek.com/v1")
        OpenAIChatModel("qwen-plus",     api_key, "https://dashscope.aliyuncs.com/compatible-mode/v1")
    """

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str = "https://api.deepseek.com/v1",
        temperature: float = 0.0,
        timeout: int = 90,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.timeout = timeout
        self.name = model

    def complete(self, messages: list[dict], tools: list[dict]) -> Turn:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:500]
            raise RuntimeError(f"模型接口 {exc.code}: {body}") from exc

        msg = data["choices"][0]["message"]
        calls = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function", {})
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            calls.append(ToolCall(fn.get("name", ""), args, tc.get("id", "")))

        return Turn(text=msg.get("content"), tool_calls=calls)
