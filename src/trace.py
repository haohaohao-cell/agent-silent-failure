"""Trace 记录：把每一次工具调用都记下来。

这是整个项目的**唯一事实来源**。
如果这里漏记了一次调用，后面的所有判定都是错的 —— 所以 5.3 节的元测试
第一件事就是验证"录制真的记全了"。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Step:
    seq: int                      # 全局序号（第几次工具调用）
    tool: str
    call_index: int               # 该工具自身被调用的次数（从 1 开始）
    args: dict
    injected: dict | None         # 本条注入了什么故障，None 表示没注入
    response: Any                 # 工具返回值（异常时为 None）
    error: str | None             # 异常描述（正常时为 None）
    duration_ms: float


class Recorder:
    """收集 Step，最后导出成 trace。"""

    def __init__(self) -> None:
        self.steps: list[Step] = []

    def add(
        self,
        *,
        tool: str,
        call_index: int,
        args: dict,
        injected: dict | None,
        response: Any,
        error: str | None,
        duration_ms: float,
    ) -> None:
        self.steps.append(
            Step(
                seq=len(self.steps) + 1,
                tool=tool,
                call_index=call_index,
                args=args,
                injected=injected,
                response=response,
                error=error,
                duration_ms=duration_ms,
            )
        )

    def to_dict(self) -> list[dict]:
        return [asdict(s) for s in self.steps]

    def summary(self) -> list[str]:
        """给 CLI 用的简表。"""
        out = []
        for s in self.steps:
            tag = "!" if s.error else ("~" if s.injected else " ")
            out.append(f"{s.seq:>2} {tag} {s.tool:<16} {s.duration_ms:>7.1f}ms")
        return out
