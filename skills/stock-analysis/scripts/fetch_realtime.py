#!/usr/bin/env python3
"""分模块抓取：实时指标（趋势/确认/风险/筹码）。"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from realtime_metrics import calculate_realtime_metrics


def main():
    parser = argparse.ArgumentParser(description="抓取实时模块 realtime.json")
    parser.add_argument("--code", required=True, help="股票代码，如 600519")
    parser.add_argument("--benchmark", default="hs300", choices=["hs300", "zz500", "zz1000", "cyb", "kcb"], help="相对强弱基准指数")
    parser.add_argument("--window", type=int, default=60, help="窗口（日）")
    parser.add_argument("--token", required=True, help="tushare token（必填）")
    parser.add_argument("--output", required=True, help="输出路径")
    parser.add_argument("--quiet", action="store_true", help="静默模式")
    args = parser.parse_args()

    import data_fetcher as df

    df.CLI_TOKEN = args.token
    df.VERBOSE = not args.quiet
    code = df.normalize_symbol(args.code)
    window = max(20, int(args.window))

    basic_info = df.get_stock_info(code)
    price = df.get_price_data(code, days=max(60, window))
    flow_metrics = df.get_flow_metrics(code, days=20)
    chip_events = df.get_chip_events(code, basic_info=basic_info)
    benchmark_price = df.get_index_price_data(args.benchmark, days=max(60, window))
    realtime_metrics = calculate_realtime_metrics(
        price=price,
        benchmark_price=benchmark_price,
        flow_metrics=flow_metrics,
        chip_events=chip_events,
        window=window,
    )
    realtime_metrics["benchmark"] = args.benchmark
    if isinstance(benchmark_price, dict) and benchmark_price.get("error"):
        realtime_metrics["benchmark_error"] = benchmark_price.get("error")

    payload = {
        "code": code,
        "fetch_time": datetime.now().isoformat(),
        "section": "realtime",
        "flow_metrics": flow_metrics,
        "chip_events": chip_events,
        "realtime_metrics": realtime_metrics,
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    if not args.quiet:
        print(f"已保存: {out}")


if __name__ == "__main__":
    main()
