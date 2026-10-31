"""把一次真实运行输出渲染成 README 用的终端图。

输入是 `python -m src.runner --fault 2` 的原始 stdout（docs/media/run.txt），
输出是同目录的 PNG。不做任何内容改写，只做着色和等宽排版。
"""

from __future__ import annotations

import io
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# 终端输出里的彩色圆点 emoji 在这里没有字形，去掉（颜色已经表达了含义）。
# 注意不要动 U+2713/U+2717（✓ ✗），它们落在 2600–27BF 区间但 Consolas 之外有字形。
EMOJI = re.compile("[\U0001F300-\U0001FAFF\uFE0F]")

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "media" / "run.txt"
OUT = ROOT / "docs" / "media" / "silent-failure.png"

BG = (27, 31, 39)
CHROME = (36, 41, 51)
DEFAULT = (200, 209, 221)
DIM = (122, 136, 155)
RED = (255, 123, 114)
GREEN = (126, 212, 154)
AMBER = (224, 164, 88)
BLUE = (143, 166, 196)
BAR = (58, 66, 82)

FONTS = Path("C:/Windows/Fonts")
MONO = FONTS / "consola.ttf"
MONO_B = FONTS / "consolab.ttf"
CJK = FONTS / "msyh.ttc"
CJK_B = FONTS / "msyhbd.ttc"
SYM = FONTS / "seguisym.ttf"

SIZE = 15
LINE_H = 25
PAD = 30
CHROME_H = 38

SYMBOLS = set("✓✗↳●─═·—≠¥")


def is_cjk(ch: str) -> bool:
    code = ord(ch)
    return 0x2E80 <= code <= 0x9FFF or 0x3000 <= code <= 0x303F or 0xFF00 <= code <= 0xFFEF


def font_for(ch: str, bold: bool):
    if ch in SYMBOLS:
        return bold_handles(SYM)
    if is_cjk(ch):
        return bold_handles(CJK_B if bold else CJK)
    return bold_handles(MONO_B if bold else MONO)


_cache: dict[tuple[str, float], ImageFont.FreeTypeFont] = {}


def bold_handles(path: Path):
    key = (str(path), SIZE)
    if key not in _cache:
        _cache[key] = ImageFont.truetype(str(path), SIZE)
    return _cache[key]


def line_style(line: str) -> tuple[tuple[int, int, int], bool]:
    if "判定" in line:
        return RED, True
    if "✗" in line:
        return RED, False
    if "✓" in line:
        return GREEN, False
    if "注入" in line or "错误" in line:
        return AMBER, False
    if line.startswith("═") or line.startswith("─"):
        return BAR, False
    if line.startswith("  场景"):
        return BLUE, False
    if line.strip().startswith("↳"):
        return AMBER, False
    return DEFAULT, False


def main() -> None:
    raw = io.open(SRC, encoding="utf-8-sig").read()
    raw = EMOJI.sub("", raw)
    lines = raw.replace("\r\n", "\n").rstrip("\n").split("\n")

    ref = bold_handles(MONO)
    adv = ref.getlength("M")

    width_chars = max(sum(2 if is_cjk(c) else 1 for c in ln) for ln in lines)
    img_w = int(width_chars * adv) + 2 * PAD
    img_h = CHROME_H + PAD + LINE_H * len(lines) + PAD

    img = Image.new("RGB", (img_w, img_h), BG)
    d = ImageDraw.Draw(img)

    # 顶部窗口条
    d.rectangle([0, 0, img_w, CHROME_H], fill=CHROME)
    for i, color in enumerate([(255, 95, 86), (254, 188, 46), (39, 201, 63)]):
        cx = 22 + i * 22
        d.ellipse([cx - 6, CHROME_H // 2 - 6, cx + 6, CHROME_H // 2 + 6], fill=color)
    title = "python -m src.runner --fault 2"
    d.text((104, CHROME_H // 2 - 8), title, font=ref, fill=DIM)

    y = CHROME_H + PAD
    for line in lines:
        color, bold = line_style(line)
        x = float(PAD)
        for ch in line:
            f = font_for(ch, bold)
            w = adv * (2 if is_cjk(ch) else 1)
            d.text((x, y), ch, font=f, fill=color)
            x += w
        y += LINE_H

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT)
    print(f"saved {OUT}  {img.width}x{img.height}")


if __name__ == "__main__":
    main()
