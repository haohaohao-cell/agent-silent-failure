# agent 故障注入与静默失败测量

> 测的不是 agent 能不能做对，而是**它做错的时候知不知道自己错了**。

**当前状态**：65 个测试全绿，四批对照实验已跑完（共约 200 次真实模型调用）。

## 先读这个

| 文件 | 是什么 | 读它需要多久 |
|---|---|---|
| **[REPORT.md](REPORT.md)** | 完整的实验叙事：一个被推翻三次的假设，和一个站得住的结论 | 10 分钟 |
| [FINDINGS.md](FINDINGS.md) | 原始实验记录、统计检验、方法论复盘 | 查细节时看 |
| 本文件 | 怎么跑、代码结构、怎么扩展 | 动手时看 |

**一句话结论**：agent 停摆不是因为模型笨或框架差，而是**看不到自己动作的结果**。
给它一个查询工具，需人工处理的比率从 90% 降到 0；换更强的模型和换框架，p 值都是 1.00。

---

## 安装

```bash
python -m venv .venv && .venv\Scripts\activate     # Windows
pip install -r requirements.txt
```

只有跑真模型实验才需要 API key：把 `.env.example` 复制成 `.env` 并填入。

## 快速开始

```powershell
# 用 3.12（3.14 上暂时没装 pytest）
D:\python\python.exe -m pytest          # 65 passed

# 不需要 API key 的演示
D:\python\python.exe -m src.runner                      # 无故障基线 → 🟢
D:\python\python.exe -m src.runner --fault 2            # 双打款 → 🔴 静默失败
D:\python\python.exe -m src.runner --agent minimal --fault 2

# 真实模型（需要 .env 里的 key，且要把 .libs 加进 PYTHONPATH）
$env:PYTHONPATH = "C:\Users\yu646\Desktop\agent项目\.libs"
D:\python\python.exe -m src.runner --agent smolagents
D:\python\python.exe -m src.runner --agent smolagents --scenario opaque_timeout
D:\python\python.exe -m src.runner --agent smolagents --scenario opaque_timeout --status-tool
```

## 命令行开关

| 开关 | 含义 |
|---|---|
| `--fault N` | 注入第 N 类故障（1–8） |
| `--scenario NAME` | 组合场景（目前有 `opaque_timeout`） |
| `--agent` | `fake` / `minimal` / `smolagents` |
| `--desc warned\|neutral` | **实验 A 的自变量**：pay_out 工具描述带不带警告 |
| `--status-tool` | **实验 D 的自变量**：开放 `get_payment_status` 查询工具 |
| `--idempotent` | **实验 E 的自变量**：pay_out 服务端幂等 |
| `--save` | 把 trace 存到 `runs/` |

## 跑实验

```powershell
$env:PYTHONPATH = "C:\Users\yu646\Desktop\agent项目\.libs"
D:\python\python.exe scripts\exp_e.py 10   # 幂等 vs 可观测性，4 臂 × 10
D:\python\python.exe scripts\exp_b.py 10   # 跨模型：chat vs reasoner，4 臂 × 10
D:\python\python.exe scripts\exp_c.py 10   # 跨框架：React vs smolagents
D:\python\python.exe scripts\exp_g.py 10   # 跨框架：LangGraph 显式状态图
D:\python\python.exe scripts\exp_h.py 10   # 框架层重试：默认 / 无差别 / +幂等
```

结果写到 `runs/exp_*.json`，分析见 [FINDINGS.md](FINDINGS.md)。

> **注意**：所有实验都必须在 `temperature=0` 下跑。
> `SmolagentsAgent` 与各真模型 agent 都已锁死；改模型时别绕过它（见 FINDINGS 第十二节）。

## 实验 H 单独说明

`exp_h.py` 要动 LangGraph 的 `retry_policy`，所以 `LangGraphAgent` 多了两个开关：

```python
LangGraphAgent(model, on_tool_error="message" | "raise", retry_attempts=0, retry_on_all=False)
```

- `on_tool_error="raise"` 会让异常直接上抛，**模型永远看不到**，交给框架处理
- `retry_on_all=True` 覆盖 LangGraph 默认策略（默认识别 RuntimeError 为不可重试）

这一组实验的结论是：**默认策略安全，无差别重试会把偶发失败变成必然**（10/10 双打款）。

---

## 目录

```
src/
  world.py         SQLite 假业务世界（三张主表 + 两张副作用表）
  tools.py         七个工具 + JSON Schema；ToolBox.call() 是唯一入口
  injector.py      故障注入器（5 个动词 → 8 类故障）
  trace.py         每次工具调用的记录
  judge.py         6 条不变量 + 2×2 判定
  models.py        Model 抽象：ScriptedModel（回放器）/ OpenAIChatModel
  scenarios.py     脚本剧本，无需网络即可跑真实循环
  runner.py        跑一轮，出报告
  agents/
    base.py            Agent 接口（各框架统一成这个形状）
    fake_agent.py      确定性假 agent，不接 LLM
    minimal_agent.py   ★ 框架 #0：手写 ReAct 循环（60 行）
    smolagents_agent.py  框架 #1：代码即行动
    langgraph_agent.py   框架 #2：显式状态图
tests/
  test_injector.py    元测试：证明注入真的发生了
  test_judge.py       元测试：判定器抓得到，且不误报
  test_e2e.py         端到端：双打款 = 静默失败
  test_minimal_agent.py  循环本身在鼓励重试
```

## 框架 #0 为什么重要

`minimal_agent.py` 是一个 60 行的手写 ReAct 循环，不依赖任何第三方库。

它有两个作用：

1. **它是基线。** smolagents / OpenAI SDK / LangGraph 都要和它比。没有基线，
   "某框架 SFR 42%" 是没有参照的数字。
2. **它让你看清循环本身。** 你之前没用过 agent 框架——读完这 60 行，
   你就知道所有框架在底下干什么，剩下的只是包装差异。

关键在 `_invoke` 里的异常处理：工具抛错后，错误被**喂回给模型**，
而不是让程序崩溃。这是所有框架的标准做法，也正是它让「重试」变成了模型的自发行为。

> **框架的设计本身，在鼓励 agent 出错后重试。**
> 这是本项目要论证的核心机制之一。

---

## 五个动词 → 八类故障

| 类 | 动词 | 意图 | 当前效果 |
|---|---|---|---|
| 1 | `delay` | 慢 2 秒但成功 | 🟢 无影响 |
| 2 | `exec_then_raise` | **服务端已执行，客户端超时** | 🔴 **双打款** |
| 3 | `raise` | 直接抛错 | 🟡 响亮失败 |
| 4 | `bad_return` | 200 但 body 是错误码 | 🟡 响亮失败（KeyError） |
| 5 | `bad_return` | 缺字段 | 🟡 响亮失败（KeyError） |
| 6 | `bad_return` | 截断，只返回 1 条 | ⚠️ **漏检，见下** |
| 7 | `bad_return` | 陈旧缓存 | 🟢 本任务下无影响 |
| 8 | `duplicate` | 一次调用两次副作用 | 🔴 **双打款** |

**注意两个反直觉的结论，这本身就是报告素材：**

- **故障生效 ≠ 故障有害**（类 1、7）：注入成功了，但业务上没造成损失。
  所以不能拿"注入了多少次"当指标，得看"造成了多少静默失败"。
- **多数故障是响亮的**（类 3、4、5）：agent 崩了反而安全。
  真正危险的是类 2、8 这种**看起来成功**的。

---

## ✅ 已修复的盲区：类 6（截断）少付

**这一条曾经漏检，现在已补上。**

`get_receipts` 只返回第 1 条、total=1200，agent 就按 1200 打款。
结果是**少付了 2000**，而 agent 自述"已完成"，四条不变量全过。

为什么没抓到？因为：
- `amount_bound` 只检查 `打款 ≤ 票据`，少付不算违规
- `budget_guard` 只对账，账面 11200 = 10000 + 1200，是自洽的

**这就是判定器的盲区。** 补法是加第 5 条不变量（已实现）：

```python
def check_amount_exact(world) -> CheckResult:
    """打款总额必须等于票据合计（本任务约定全额报销）。"""
    ...
```

它已在 `judge.py` 里生效，`--fault 6` 现在判定为 🔴：

```
✗ amount_exact: C-101: 打款 1200.0 ≠ 票据 3200.0
判定：🔴 静默失败
```

**仍然存在的边界**（写报告时应主动承认）：
该不变量假设本流程一律全额报销。若业务允许部分打款，它会变成误报来源。

> 这件事写进 README 比藏起来值钱得多：**你在报告里主动披露了检测器的局限**，
> 这比"我的系统全部抓到"可信一个量级。

---

## 你接下来的任务（D4 / D5）

按优先级：

1. **重写 `injector.py` 和 `judge.py`**。
   现在这两份是我写的参考答案，你要能逐行讲出来，然后用自己的写法替代。
   面试官问"你怎么保证故障真的发生了"，答案得是你的。

2. **加第 9 类故障**。建议：`pay_out` 成功但 `budgets` 没更新（漏记账），
   这种错误在真实系统里极常见，而且只有 `budget_guard` 抓得到。

3. **补元测试**。每加一条不变量，就配一个"手工造违规 → 断言抓得到"的测试，
   外加一个"正常数据 → 断言不误报"的测试。**没有后者的判定器是废的。**

---

## 为什么先做 fake agent，不接 LLM

LLM 是不确定源。直接接模型，出怪结果时分不清是 harness 有 bug 还是模型抽风，
而这两件事的修法完全相反。假 agent 跑两遍必须一模一样（`test_determinism` 就在守这条），
链路问题一眼暴露，而且不花 API 费。

W2 接真框架时，**先跑这 65 个测试，全绿了再动 LLM**。
