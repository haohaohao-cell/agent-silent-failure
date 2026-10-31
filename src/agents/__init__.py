"""Agent 实现。

目前只有 fake（确定性、不接 LLM）。
W2 要在这里加：
    smolagents_agent.py      代码即行动
    openai_sdk_agent.py      JSON 工具调用 + handoff
    langgraph_agent.py       显式状态图

每个都要实现 base.Agent 接口，并且**用同一套 ToolBox**，
否则就不是受控实验了。
"""

from .base import Agent, AgentResult
from .fake_agent import FakeAgent

__all__ = ["Agent", "AgentResult", "FakeAgent"]
