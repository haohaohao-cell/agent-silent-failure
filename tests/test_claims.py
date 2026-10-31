"""agent 自述的判定：启发式，但必须可测、可解释。"""

from __future__ import annotations

import pytest

from src.agents.base import claims_success


@pytest.mark.parametrize(
    "msg",
    [
        "已完成报销打款，金额 3200.0",
        "已打款 3200 元",
        "处理完成",
    ],
)
def test_success_phrases(msg):
    assert claims_success(msg) is True


@pytest.mark.parametrize(
    "msg",
    [
        "无法处理报销单 C-101：所有后端工具均失败",
        "抱歉，工具不可用",
        "未能完成打款",
        "请修复后端数据库连接后重试",
        "",
    ],
)
def test_failure_phrases(msg):
    assert claims_success(msg) is False


def test_negative_wins_over_positive():
    """同时出现"已完成"和"无法"时，判为失败 —— 宁可保守。

    （这正是 smolagents 那次的实际输出：'无法处理……未调用 pay_out'，
      里面还有大量叙述。保守判定能避免把它误算成静默失败。）
    """
    assert claims_success("无法完成：未能调用 pay_out，流程失败") is False


def test_status_line_is_authoritative():
    """状态行优先于任何关键词 —— 这是唯一可靠的信号。"""
    assert claims_success("全部搞定\nSTATUS: DONE") is True
    # 即使正文里满是"失败"字样，只要状态行说 DONE 就算成功
    assert claims_success("中间有一次失败但重试成功\nSTATUS: DONE") is True


def test_blocked_status_wins_over_positive_words():
    """正文说"已完成部分步骤"，但状态行说 BLOCKED → 判失败。"""
    assert claims_success("已完成第 1-3 步\nSTATUS: BLOCKED") is False


def test_english_output_does_not_fool_the_fallback():
    """第一次跑 smolagents 时的真实事故：模型用英文回答，
    中文关键词表全线失效，一次正当的谨慎被判成了"声称成功"。"""
    msg = "I have NOT executed any payout. Blocker: missing emp_id."
    assert claims_success(msg) is False
