#!/usr/bin/env python3
"""
环境变量加载工具：
- 优先读取当前进程环境变量
- 缺失时回退读取 ~/.aj-skills/.env
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict


AJ_ENV_PATH = Path.home() / ".aj-skills" / ".env"


def _parse_env_file(path: Path) -> Dict[str, str]:
    if not path.exists() or not path.is_file():
        return {}

    data: Dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            data[key] = value
    return data


def get_env(name: str, default: str = "") -> str:
    val = os.getenv(name)
    if val:
        return val
    from_file = _parse_env_file(AJ_ENV_PATH).get(name)
    if from_file:
        return from_file
    return default


def get_tushare_token() -> str:
    return get_env("TUSHARE_TOKEN") or get_env("TS_TOKEN")
