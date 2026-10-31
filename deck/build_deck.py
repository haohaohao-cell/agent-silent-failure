"""生成《Agent 缺的不是智力，是眼睛》演示文稿。

风格：科研答辩风（白底 / 深学术蓝 / 正红点睛 / 表格与证据优先）
版式：16:9，13.333 x 7.5 英寸
"""

from __future__ import annotations

import re

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

# ---------------------------------------------------------------- 设计系统

WHITE = RGBColor(0xFF, 0xFF, 0xFF)
PANEL = RGBColor(0xF5, 0xF7, 0xFA)
BLUE = RGBColor(0x00, 0x3F, 0x8F)
BLUE2 = RGBColor(0x0B, 0x5C, 0xAD)
BLUE_PALE = RGBColor(0xEA, 0xF2, 0xFF)
RED = RGBColor(0xB5, 0x12, 0x1B)
INK = RGBColor(0x11, 0x11, 0x11)
BODY = RGBColor(0x33, 0x33, 0x33)
MUTED = RGBColor(0x6B, 0x77, 0x85)
BORDER = RGBColor(0xD8, 0xDE, 0xE8)
GREEN = RGBColor(0x1E, 0x7B, 0x45)
AMBER = RGBColor(0xB4, 0x6A, 0x00)
SLATE = RGBColor(0x4A, 0x55, 0x68)

FONT_CN = "Microsoft YaHei"
FONT_MONO = "Consolas"

W, H = 13.333, 7.5
MARGIN = 0.85
CONTENT_W = W - 2 * MARGIN


# ---------------------------------------------------------------- 基础工具

def _set_east_asian(run, name: str) -> None:
    rPr = run._r.get_or_add_rPr()
    ea = rPr.find(qn("a:ea"))
    if ea is None:
        ea = rPr.makeelement(qn("a:ea"), {})
        rPr.append(ea)
    ea.set("typeface", name)


def style(run, size: float, bold: bool = False, color=BODY, name: str = FONT_CN) -> None:
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = name
    _set_east_asian(run, name)


def put(p, text: str, size: float, bold: bool = False, color=BODY,
        name: str = FONT_CN):
    """往段落里写一段统一格式的文字，返回 run。"""
    r = p.add_run()
    r.text = text
    style(r, size, bold, color, name)
    return r


def rich(p, text: str, size: float, color=BODY, bold: bool = False) -> None:
    """支持 **红色加粗** 的内联标记。"""
    for part in re.split(r"(\*\*.*?\*\*)", text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            style(p.add_run_for_text(part[2:-2]), size, True, RED)
        else:
            style(p.add_run_for_text(part), size, bold, color)


class _Para:
    """给 rich() 用的极简适配器。"""

    def __init__(self, p):
        self.p = p

    def add_run_for_text(self, text: str):
        r = self.p.add_run()
        r.text = text
        return r


def textbox(slide, l, t, w, h, anchor=MSO_ANCHOR.TOP):
    tb = slide.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    return tb


def para(tf, first: bool):
    return tf.paragraphs[0] if first else tf.add_paragraph()


def rule(slide, y: float, width: float = CONTENT_W, x: float = MARGIN,
         color=BLUE, thickness: float = 2.0) -> None:
    bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(width), Pt(thickness)
    )
    bar.fill.solid()
    bar.fill.fore_color.rgb = color
    bar.line.fill.background()
    bar.shadow.inherit = False


def card(slide, l, t, w, h, fill=PANEL, line=BORDER):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                   Inches(l), Inches(t), Inches(w), Inches(h))
    shape.adjustments[0] = 0.04
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    if line is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = line
        shape.line.width = Pt(1)
    shape.shadow.inherit = False
    return shape


# ---------------------------------------------------------------- 页面骨架

def new_slide(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])


def header(slide, kicker: str, title: str) -> None:
    tb = textbox(slide, MARGIN, 0.52, CONTENT_W, 0.32)
    put(tb.text_frame.paragraphs[0], kicker, 12, True, BLUE2)

    tb = textbox(slide, MARGIN, 0.88, CONTENT_W, 0.9)
    p = tb.text_frame.paragraphs[0]
    rich(_Para(p), title, 30, INK, True)

    rule(slide, 1.86, thickness=2.0)


def footer(slide, text: str, accent=BLUE) -> None:
    bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(MARGIN), Inches(6.62), Pt(4), Inches(0.42)
    )
    bar.fill.solid()
    bar.fill.fore_color.rgb = accent
    bar.line.fill.background()
    bar.shadow.inherit = False

    tb = textbox(slide, MARGIN + 0.18, 6.62, CONTENT_W - 0.2, 0.5)
    p = tb.text_frame.paragraphs[0]
    rich(_Para(p), text, 15, SLATE)


def bullets(slide, items, left, top, width, size=17.5, gap=14, color=BODY):
    tb = textbox(slide, left, top, width, 4.2)
    tf = tb.text_frame
    for i, item in enumerate(items):
        p = para(tf, i == 0)
        p.space_after = Pt(gap)
        p.line_spacing = 1.25
        mark = p.add_run()
        mark.text = "▪ "
        style(mark, size, True, BLUE2)
        rich(_Para(p), item, size, color)
    return tb


def table(slide, data, left, top, width, row_h, col_w=None,
          header_fill=BLUE, header_color=WHITE, body_size=15,
          header_size=15, cell_fills=None):
    rows, cols = len(data), len(data[0])
    shape = slide.shapes.add_table(rows, cols, Inches(left), Inches(top),
                                   Inches(width), Inches(row_h * rows))
    tbl = shape.table
    tbl.first_row = False
    tbl.horz_banding = False

    if col_w:
        for i, w in enumerate(col_w):
            tbl.columns[i].width = Inches(w)
    for r in range(rows):
        tbl.rows[r].height = Inches(row_h)

    for r in range(rows):
        for c in range(cols):
            cell = tbl.cell(r, c)
            cell.margin_left = Inches(0.16)
            cell.margin_right = Inches(0.12)
            cell.margin_top = Inches(0.08)
            cell.margin_bottom = Inches(0.08)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE

            text = data[r][c]
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]

            is_header = r == 0
            fill = header_fill if is_header else WHITE

            if cell_fills and (r, c) in cell_fills:
                fill, color, bold = cell_fills[(r, c)]
            else:
                color = header_color if is_header else BODY
                bold = is_header

            cell.fill.solid()
            cell.fill.fore_color.rgb = fill

            rich(_Para(p), text, header_size if is_header else body_size,
                 color, bold)
    return tbl


# ---------------------------------------------------------------- 各页

def slide_cover(prs):
    s = new_slide(prs)
    band = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(0.42), Inches(H))
    band.fill.solid()
    band.fill.fore_color.rgb = BLUE
    band.line.fill.background()
    band.shadow.inherit = False

    tb = textbox(s, 1.35, 2.05, 10.6, 1.9)
    p = tb.text_frame.paragraphs[0]
    p.line_spacing = 1.15
    rich(_Para(p), "Agent 缺的不是智力，是眼睛", 46, INK, True)

    tb = textbox(s, 1.35, 3.95, 10.6, 0.5)
    p = tb.text_frame.paragraphs[0]
    rich(_Para(p), "一个关于「静默失败」的故障注入实验", 21, BLUE2)

    rule(s, 4.75, width=4.2, x=1.35, thickness=3)

    tb = textbox(s, 1.35, 5.05, 10.6, 0.9)
    p = tb.text_frame.paragraphs[0]
    rich(_Para(p), "6 组对照实验 · 约 250 次真实模型调用 · 65 个自动化测试", 14, MUTED)
    return s


def slide_problem(prs):
    s = new_slide(prs)
    header(s, "01 / 问题", "agent 不会崩溃，它会自信地给错答案")
    bullets(s, [
        "现有评测都在测「能力」，几乎没人测「元认知」",
        "静默失败：日志全绿、agent 说「已完成」、用户不知情、事已办砸",
        "崩溃是好事 —— 能重试、能报警；沉默才是敌人",
        "所以研究对象不是「它能不能做对」，而是 **它做错时知不知道**",
    ], MARGIN, 2.28, CONTENT_W, size=18.5, gap=18)
    footer(s, "能力可以补，不知情补不了。")
    return s


def slide_bench(prs):
    s = new_slide(prs)
    header(s, "02 / 实验台", "一个会真的打钱的沙盒")
    items = [
        ("场景", "差旅报销审批，6 个工具；\npay_out 真的写库、真的扣预算", BLUE2),
        ("故障", "8 类，全部注入在工具边界；\n核心是「先执行、再抛超时」", RED),
        ("判定", "6 条业务不变量 + 2×2 矩阵；\n不变量由 trace 与数据库核对", BLUE2),
    ]
    w = (CONTENT_W - 0.5) / 3
    for i, (title, body, accent) in enumerate(items):
        x = MARGIN + i * (w + 0.25)
        card(s, x, 2.25, w, 2.75)
        bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(2.25),
                                 Inches(w), Pt(4))
        bar.fill.solid()
        bar.fill.fore_color.rgb = accent
        bar.line.fill.background()
        bar.shadow.inherit = False

        tb = textbox(s, x + 0.28, 2.55, w - 0.5, 0.45)
        put(tb.text_frame.paragraphs[0], title, 19, True, accent)

        tb = textbox(s, x + 0.28, 3.12, w - 0.5, 1.6)
        p = tb.text_frame.paragraphs[0]
        p.line_spacing = 1.35
        rich(_Para(p), body, 14.5, BODY)
    footer(s, "不碰模型、不碰框架内部 —— 所以它对所有框架一视同仁。")
    return s


def slide_matrix(prs):
    s = new_slide(prs)
    header(s, "03 / 判定", "2×2 矩阵：agent 怎么说 × 事情做成没")

    data = [
        ["", "任务做成了", "任务没做成"],
        ["agent 说成功", "● 正常", "● 静默失败"],
        ["agent 说失败", "● 虚假告警", "● 响亮失败"],
    ]
    fills = {
        (1, 1): (RGBColor(0xE8, 0xF5, 0xEC), GREEN, True),
        (1, 2): (RGBColor(0xFB, 0xE9, 0xEA), RED, True),
        (2, 1): (RGBColor(0xFD, 0xF3, 0xE0), AMBER, True),
        (2, 2): (RGBColor(0xEE, 0xF1, 0xF6), SLATE, True),
    }
    table(s, data, MARGIN + 0.9, 2.25, CONTENT_W - 1.8, 0.95,
          col_w=[3.2, 4.0, 4.0], body_size=17, header_size=15, cell_fills=fills)

    tb = textbox(s, MARGIN + 0.9, 5.45, CONTENT_W - 1.8, 0.8)
    p = tb.text_frame.paragraphs[0]
    p.line_spacing = 1.3
    rich(_Para(p), "左上格易被忽略：钱付对了，agent 却以为错了。"
                   "每张虚假告警都是一张人工工单。", 15.5, BODY)
    footer(s, "单一的「失败率」会丢掉一半信息。")
    return s


def slide_collapse(prs):
    s = new_slide(prs)
    header(s, "04 / 第一次崩塌", "空跑能通过全部检查")

    DIM = RGBColor(0xC8, 0xD1, 0xDD)
    OK_GREEN = RGBColor(0x7E, 0xD4, 0x9A)
    BAD_RED = RGBColor(0xFF, 0x7B, 0x72)

    card(s, MARGIN, 2.2, 6.15, 3.55, fill=RGBColor(0x1B, 0x1F, 0x27), line=None)
    lines = [
        ("X get_receipts    thread error", DIM, False),
        ("X get_employee    thread error", DIM, False),
        ("X check_budget    thread error", DIM, False),
        ("payments = 0", DIM, False),
        ("", DIM, False),
        ("判定: 正常", OK_GREEN, True),
        ("问题: 一笔都没打成", BAD_RED, True),
    ]
    tb = textbox(s, MARGIN + 0.4, 2.55, 5.3, 3.0)
    for i, (line, color, bold) in enumerate(lines):
        p = para(tb.text_frame, i == 0)
        p.space_after = Pt(13)
        r = p.add_run()
        r.text = line
        style(r, 14, bold, color, FONT_MONO)

    bullets(s, [
        "所有工具调用因线程错误失败，一笔没打成",
        "判定却是「正常」—— 不变量只写「不许做错」",
        "补上 task_completed 才堵住这个洞",
    ], 7.4, 2.45, 5.0, size=16, gap=22)
    footer(s, "「没有违规」不等于「做成了」—— 这个洞不发现，后面数据全废。")
    return s


def slide_hypothesis(prs):
    s = new_slide(prs)
    header(s, "05 / 假设之死", "它没有重试，它去查了预算")

    card(s, MARGIN, 2.2, CONTENT_W, 0.85, fill=BLUE_PALE, line=BLUE_PALE)
    tb = textbox(s, MARGIN + 0.3, 2.38, CONTENT_W - 0.6, 0.5)
    p = tb.text_frame.paragraphs[0]
    rich(_Para(p), "原假设：agent 遇到工具超时会盲目重试，把一笔钱打两次。",
         16.5, BLUE, True)

    steps = [
        ("X pay_out", "超时，但钱已扣", RED),
        ("· check_budget", "spent 从 10000 变成 13200", BLUE2),
        ("→ 判断", "「钱已经打出去了」，主动放弃重试", GREEN),
    ]
    y = 3.45
    for i, (label, desc, color) in enumerate(steps):
        card(s, MARGIN + 0.5, y, 11.1, 0.78, fill=WHITE)
        tb = textbox(s, MARGIN + 0.8, y + 0.2, 3.0, 0.4)
        r = tb.text_frame.paragraphs[0].add_run()
        r.text = label
        style(r, 15, True, color, FONT_MONO)

        tb = textbox(s, MARGIN + 3.9, y + 0.2, 7.4, 0.4)
        p = tb.text_frame.paragraphs[0]
        rich(_Para(p), desc, 15.5, BODY)
        y += 0.95

    footer(s, "原假设当场死亡：它不是鲁莽，它是在没有依据时选择了停下。")
    return s


def slide_blind(prs):
    s = new_slide(prs)
    header(s, "06 / 转折", "让它失明，才复现出那个场景")

    tb = textbox(s, MARGIN, 2.2, CONTENT_W, 0.5)
    p = tb.text_frame.paragraphs[0]
    rich(_Para(p), "组合故障 opaque_timeout：付款超时，**而且复查时读到旧快照**。",
         16.5, BODY)

    card(s, MARGIN, 2.9, CONTENT_W, 1.85, fill=PANEL)
    tb = textbox(s, MARGIN + 0.55, 3.15, CONTENT_W - 1.1, 1.1)
    p = tb.text_frame.paragraphs[0]
    p.line_spacing = 1.45
    rich(_Para(p), "「pay_out 为不可逆…为避免重复打款不能重试；"
                   "**现有工具无法查询打款状态**，无法确认是否成功。」",
         19.5, INK, True)

    tb = textbox(s, MARGIN + 0.05, 4.85, CONTENT_W - 1.1, 0.35)
    put(tb.text_frame.paragraphs[0], "—— agent 的最终答复，STATUS: BLOCKED", 13, False, MUTED)

    tb = textbox(s, MARGIN, 5.55, CONTENT_W, 0.45)
    p = tb.text_frame.paragraphs[0]
    rich(_Para(p), "单看这一句，像是谨慎；**结合数据看，是失明**。", 16.5, BODY)
    footer(s, "缺口不是「不够谨慎」，而是工具箱里少了一个查询工具。")
    return s


def slide_tempbug(prs):
    s = new_slide(prs)
    header(s, "07 / 方法论", "一个不会报错的 bug：temperature")

    kpis = [("0 / 10", "第 1 次"), ("4 / 10", "第 2 次"), ("2 / 10", "第 3 次")]
    w = (CONTENT_W - 1.0) / 3
    for i, (value, label) in enumerate(kpis):
        x = MARGIN + i * (w + 0.5)
        card(s, x, 2.2, w, 1.55)
        tb = textbox(s, x, 2.42, w, 0.7, anchor=MSO_ANCHOR.MIDDLE)
        p = tb.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        put(p, value, 34, True, RED)

        tb = textbox(s, x, 3.15, w, 0.35)
        p = tb.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        put(p, label, 13, False, MUTED)

    tb = textbox(s, MARGIN, 4.05, CONTENT_W, 0.4)
    p = tb.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    rich(_Para(p), "同一份配置，三次重复 —— 双打款率却不一样", 15, SLATE)

    bullets(s, [
        "排查结果：smolagents 不传 temperature 就用服务商默认值 1.0",
        "此前所有实验都是在噪声里采样的，方差被放大",
        "修复后全部锁定 temperature = 0",
    ], MARGIN, 4.65, CONTENT_W, size=16.5, gap=12)
    footer(s, "这类 bug 不报错，只给你一串看起来很合理的波动。")
    return s


def slide_explain(prs):
    s = new_slide(prs)
    header(s, "08 / 数据", "三个解释，排除两个")

    data = [
        ["候选解释", "检验方式", "结果"],
        ["模型能力不够", "chat vs reasoner", "p = 1.00"],
        ["框架架构不对", "JSON / 代码 / 状态图", "p = 1.00"],
        ["缺少观测手段", "给一个只读查询工具", "p < 0.0001"],
    ]
    fills = {
        (1, 2): (WHITE, MUTED, False),
        (2, 2): (WHITE, MUTED, False),
        (3, 2): (RGBColor(0xFB, 0xE9, 0xEA), RED, True),
    }
    table(s, data, MARGIN, 2.25, CONTENT_W, 0.92,
          col_w=[4.1, 5.0, 3.2], body_size=16, cell_fills=fills)

    tb = textbox(s, MARGIN, 6.02, CONTENT_W, 0.45)
    p = tb.text_frame.paragraphs[0]
    rich(_Para(p), "推理模型更保守：0 次双打款、**0 次完成**、10 次上报。",
         15.5, BODY)
    footer(s, "提高模型能力，只会让它更谨慎地拒绝工作。")
    return s


def slide_result(prs):
    s = new_slide(prs)
    header(s, "09 / 核心结论", "剩下的那个：90% → 0")

    kpis = [
        ("9–10 → 0", "需人工处理（每 10 次）", RED),
        ("0 → 10", "正常完成（每 10 次）", GREEN),
        ("0 → 30", "三框架合计正常完成", GREEN),
    ]
    w = (CONTENT_W - 1.0) / 3
    for i, (value, label, color) in enumerate(kpis):
        x = MARGIN + i * (w + 0.5)
        card(s, x, 2.3, w, 2.0)
        tb = textbox(s, x, 2.62, w, 0.8, anchor=MSO_ANCHOR.MIDDLE)
        p = tb.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        put(p, value, 38, True, color)

        tb = textbox(s, x, 3.55, w, 0.6)
        p = tb.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        p.line_spacing = 1.2
        put(p, label, 13.5, False, SLATE)

    tb = textbox(s, MARGIN, 4.62, CONTENT_W, 0.9)
    p = tb.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    p.line_spacing = 1.3
    rich(_Para(p), "基线 30 次运行，**0 次完成**；加观测后 30 次，**全部完成**。",
         19, INK, True)

    tb = textbox(s, MARGIN, 5.55, CONTENT_W, 0.5)
    p = tb.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    rich(_Para(p), "同一组故障、同一个模型 —— 唯一的区别是多了一个只读工具。",
         15, MUTED)
    footer(s, "唯一同时消除经济损失与人工兜底的干预 —— 换模型、换框架都做不到。")
    return s


def slide_retry(prs):
    s = new_slide(prs)
    header(s, "10 / 反面", "谁在替模型重试")

    data = [
        ["臂", "双打款", "说明"],
        ["异常转消息（现状）", "0 / 10", "模型看到错误，自己判断"],
        ["+ 默认 RetryPolicy", "0 / 10", "框架主动不重试 RuntimeError"],
        ["+ 无差别重试", "10 / 10", "框架重跑节点，模型不知情"],
    ]
    fills = {
        (3, 1): (RGBColor(0xFB, 0xE9, 0xEA), RED, True),
        (3, 2): (WHITE, RED, True),
    }
    table(s, data, MARGIN, 2.15, CONTENT_W, 0.85,
          col_w=[4.3, 2.4, 5.6], body_size=15.5, cell_fills=fills)

    tb = textbox(s, MARGIN, 5.8, CONTENT_W, 0.5)
    p = tb.text_frame.paragraphs[0]
    rich(_Para(p), "模型的重试是**判断**，会犹豫；框架的重试是**机制**，不犹豫。",
         16.5, BODY)
    footer(s, "在基础设施层加个重试，是把偶发失败变成必然重复。", accent=RED)
    return s


def slide_idem(prs):
    s = new_slide(prs)
    header(s, "11 / 机制", "幂等能兜住钱，救不回判断")

    rows = [
        ("服务端幂等", "双打款 2 → 0", "需人工 9 → 8", RED),
        ("只读查询工具", "双打款 → 0", "需人工 9 → 0", GREEN),
    ]
    y = 2.25
    for name, a, b, color in rows:
        card(s, MARGIN, y, CONTENT_W, 0.95)
        tb = textbox(s, MARGIN + 0.35, y + 0.28, 3.2, 0.4)
        p = tb.text_frame.paragraphs[0]
        put(p, name, 17, True, color)

        tb = textbox(s, MARGIN + 3.7, y + 0.28, 3.6, 0.4)
        p = tb.text_frame.paragraphs[0]
        rich(_Para(p), a, 15.5, BODY)

        tb = textbox(s, MARGIN + 7.6, y + 0.28, 3.6, 0.4)
        p = tb.text_frame.paragraphs[0]
        rich(_Para(p), b, 15.5, BODY)
        y += 1.12

    bullets(s, [
        "幂等的返回值里也有信息（already_paid），但它只在 agent **愿意重试** 时才出现",
        "而 agent 大多数时候选择不重试 —— 于是永远学不到",
        "查询工具不同：agent 会主动去查，10 次里 10 次都查了",
    ], MARGIN, 4.75, CONTENT_W, size=15.5, gap=10)
    footer(s, "关键差别不在信息是否存在，而在谁负责去取。")
    return s


def slide_takeaway(prs):
    s = new_slide(prs)
    header(s, "12 / 结论", "对该做 agent 的人，意味着什么")

    items = [
        ("给每个不可逆动作配一个「查状态」的工具", "收益远大于换模型、换框架、改提示词"),
        ("幂等和观测是两件事", "前者防损失，后者恢复可用性，谁也替代不了谁"),
        ("别在基础设施层给有副作用的动作加无差别重试", "模型会犹豫，框架不会"),
        ("上线前问一句：失败时 agent 能查到「到底做没做」吗", "查不到，它就会转人工 —— 或者更糟，蒙"),
    ]
    y = 2.2
    for i, (title, sub) in enumerate(items, 1):
        circle = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(MARGIN), Inches(y + 0.02),
                                    Inches(0.42), Inches(0.42))
        circle.fill.solid()
        circle.fill.fore_color.rgb = BLUE
        circle.line.fill.background()
        circle.shadow.inherit = False
        tf = circle.text_frame
        tf.margin_left = 0
        tf.margin_right = 0
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        put(p, str(i), 14, True, WHITE)

        tb = textbox(s, MARGIN + 0.68, y, CONTENT_W - 0.8, 0.4)
        p = tb.text_frame.paragraphs[0]
        rich(_Para(p), title, 17, INK, True)

        tb = textbox(s, MARGIN + 0.68, y + 0.42, CONTENT_W - 0.8, 0.35)
        p = tb.text_frame.paragraphs[0]
        rich(_Para(p), sub, 14, SLATE)
        y += 1.05

    footer(s, "agent 缺的不是智力，是眼睛。而重试，是把眼睛蒙上。", accent=RED)
    return s


def slide_limits(prs):
    s = new_slide(prs)
    header(s, "13 / 收尾", "局限与方法的复盘")

    left_items = [
        "未覆盖 handoff 多 agent 范式",
        "只有一个业务场景（报销审批）",
        "不变量本身有构造性局限",
        "每臂 n = 10，细微信号测不出",
    ]
    right_items = [
        "n = 3 不是样本，是轶事",
        "自变量要验证「真的改了」",
        "采样温度必须显式锁死",
        "结构保证与统计显著要分开讲",
    ]

    for i, (title, items, accent) in enumerate([
        ("局限", left_items, SLATE),
        ("方法", right_items, BLUE2),
    ]):
        x = MARGIN + i * (CONTENT_W / 2 + 0.15)
        w = CONTENT_W / 2 - 0.15
        card(s, x, 2.2, w, 3.55)
        tb = textbox(s, x + 0.32, 2.42, w - 0.6, 0.4)
        put(tb.text_frame.paragraphs[0], title, 18, True, accent)

        tb = textbox(s, x + 0.32, 3.0, w - 0.6, 2.5)
        for j, item in enumerate(items):
            p = para(tb.text_frame, j == 0)
            p.space_after = Pt(12)
            p.line_spacing = 1.25
            m = p.add_run()
            m.text = "· "
            style(m, 15, True, accent)
            rich(_Para(p), item, 15, BODY)

    tb = textbox(s, MARGIN, 6.0, CONTENT_W, 0.4)
    p = tb.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    rich(_Para(p), "先把测量做对，再谈结论。", 16, INK, True)
    footer(s, "65 个测试 / 6 组实验 / 原始数据全部可复现。")
    return s


NOTES = [
    "开场先说结论：今天讲的不是「agent 会不会犯错」，而是「它犯错的时候知不知道」。"
    "这两件事在工程上是完全不同的两个问题。",

    "现有评测几乎都在测能力——任务成没成。但生产环境里 agent 很少崩溃，"
    "它会一本正经地给你一个错结果，而日志全绿。这就是静默失败。",

    "为了让失败有痕迹，我用了一个真会打钱的沙盒：报销审批，pay_out 真的写库扣预算。"
    "故障全部注入在工具边界，不碰模型也不碰框架内部，所以它对所有框架一视同仁。",

    "判定用 2×2：agent 怎么说 × 事情做成没。右上格是我们要抓的静默失败。"
    "但左下格——钱付对了、agent 却以为错了——是后来意外发现的，"
    "它同样有成本，每次都是一张人工工单。",

    "第一次接真模型，所有工具调用都因线程错误失败，一笔没打成。判定却是「正常」。"
    "因为不变量只写了「不许做错」，而它恰好什么都没做。"
    "补上 task_completed 才堵住——这个洞如果不发现，后面所有数据都是废的。",

    "原假设是它会盲目重试。结果它回去查了预算，发现钱已经扣了，"
    "于是主动放弃重试。假设当场死亡。",

    "这一页建议停两秒让观众读完。它说「现有工具无法查询打款状态」——"
    "缺口不是它不够谨慎，而是工具箱里少了一个查询工具。这句话是整份研究的钥匙。",

    "这里讲一个方法论事故：同一份配置三次跑出 0/10、4/10、2/10。"
    "查下去发现 temperature 从没显式传过，一直用的是服务商默认值 1.0。"
    "这类 bug 不报错，只给你一串看起来很合理的波动。",

    "三个候选解释：模型不够强、框架不对、缺观测。前两个的 p 值都是 1.00。"
    "尤其注意推理模型——它更保守，0 次双打款、0 次完成、10 次上报。"
    "提高模型能力，只是让它更谨慎地拒绝工作。",

    "这是全片的高潮。三个框架合计：基线 30 次运行，0 次完成；加一个只读工具后，30 次全部完成。"
    "唯一的区别就是多了那一个工具。",

    "反面也值得讲。LangGraph 的默认重试策略对 RuntimeError 返回 False，"
    "所以默认是安全的。但一旦改成无差别重试，10 次里 10 次双打款——"
    "模型的重试是判断，会犹豫；框架的重试是机制，不犹豫。",

    "幂等能保证不重复出款，但它只在 agent 愿意重试时才透露信息，而 agent 大多不重试。"
    "查询工具不一样：它会主动去查，10 次里 10 次都查了。"
    "关键差别不在信息是否存在，而在谁负责去取。",

    "四条可以直接拿走的做法。最后一条最重要：上线前问自己——"
    "失败的时候，agent 能查到「到底做没做」吗？查不到，它就会转人工，或者更糟，蒙。",

    "诚实地列局限：没覆盖 handoff 多 agent，只有一个业务场景，不变量本身也有构造性局限。"
    "方法上最想说的一句是：先把测量做对，再谈结论。"
    "n=3 不是样本，是轶事。",
]


def main() -> None:
    prs = Presentation()
    prs.slide_width = Inches(W)
    prs.slide_height = Inches(H)

    slide_cover(prs)
    slide_problem(prs)
    slide_bench(prs)
    slide_matrix(prs)
    slide_collapse(prs)
    slide_hypothesis(prs)
    slide_blind(prs)
    slide_tempbug(prs)
    slide_explain(prs)
    slide_result(prs)
    slide_retry(prs)
    slide_idem(prs)
    slide_takeaway(prs)
    slide_limits(prs)

    for slide, note in zip(prs.slides, NOTES):
        slide.notes_slide.notes_text_frame.text = note

    out = "deck/silent-failure-deck.pptx"
    prs.save(out)
    print(f"saved: {out}  slides={len(prs.slides)}  notes={len(NOTES)}")


if __name__ == "__main__":
    main()
