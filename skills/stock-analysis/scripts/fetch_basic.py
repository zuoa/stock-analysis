#!/usr/bin/env python3
"""分模块抓取：基础信息。"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="抓取基础信息 basic.json")
    parser.add_argument("--code", required=True, help="股票代码，如 600519")
    parser.add_argument("--token", required=True, help="tushare token（必填）")
    parser.add_argument("--output", required=True, help="输出路径")
    parser.add_argument("--quiet", action="store_true", help="静默模式")
    args = parser.parse_args()

    import data_fetcher as df

    df.CLI_TOKEN = args.token
    df.VERBOSE = not args.quiet
    code = df.normalize_symbol(args.code)

    payload = {
        "code": code,
        "fetch_time": datetime.now().isoformat(),
        "section": "basic",
        "basic_info": df.get_stock_info(code),
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    if not args.quiet:
        print(f"已保存: {out}")


if __name__ == "__main__":
    main()
