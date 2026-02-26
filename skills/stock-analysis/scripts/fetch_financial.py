#!/usr/bin/env python3
"""分模块抓取：财务数据（报表/指标/业绩与审计）。"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="抓取财务模块 financial.json")
    parser.add_argument("--code", required=True, help="股票代码，如 600519")
    parser.add_argument("--years", type=int, default=3, help="历史年数")
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
        "section": "financial",
        "financial_data": df.get_financial_data(code, years=max(1, args.years)),
        "financial_indicators": df.get_financial_indicators(code),
        "performance_data": df.get_performance_data(code, years=max(1, args.years)),
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    if not args.quiet:
        print(f"已保存: {out}")


if __name__ == "__main__":
    main()
