"""极简配置读取。不引入 python-dotenv，避免多一个依赖。

约定：项目根目录放一个 `.env`，内容形如

    DEEPSEEK_API_KEY=sk-xxxxxxxx
    MODEL_ID=deepseek-chat
    API_BASE=https://api.deepseek.com/v1

`.env` 已在 .gitignore 里，不会进版本库。
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_env(path: Path | None = None) -> None:
    p = path or (ROOT / ".env")
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_key(name: str = "DEEPSEEK_API_KEY") -> str:
    load_env()
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"缺少 {name}。\n"
            f"请在 {ROOT / '.env'} 里写一行：\n    {name}=sk-xxxx"
        )
    return value


def get(name: str, default: str = "") -> str:
    load_env()
    return os.environ.get(name, default).strip() or default
