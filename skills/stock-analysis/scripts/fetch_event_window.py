#!/usr/bin/env python3
"""分模块抓取：事件窗口分析。"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from event_window import collect_event_candidates, calculate_event_window
from news_fetcher import fetch_news


def _parse_post_days(raw: str):
    values = []
    for p in str(raw or "").split(","):
        p = p.strip()
        if not p:
            continue
        try:
            v = int(p)
            if v >= 1:
                values.append(v)
        except Exception:
            continue
    if not values:
        return (1, 3, 5)
    return tuple(sorted(set(values)))


def main():
    parser = argparse.ArgumentParser(description="抓取事件窗口模块 event_window.json")
    parser.add_argument("--code", required=True, help="股票代码，如 600519")
    parser.add_argument("--name", default="", help="股票名称，可选")
    parser.add_argument("--years", type=int, default=2, help="业绩事件回溯年数")
    parser.add_argument("--days", type=int, default=7, help="新闻窗口天数")
    parser.add_argument("--limit", type=int, default=20, help="新闻最大条数")
    parser.add_argument("--provider", choices=["auto", "brave", "tushare", "rss"], default="auto", help="新闻源")
    parser.add_argument("--brave-api-key", default="", help="Brave API Key（provider=brave 时必填）")
    parser.add_argument("--benchmark", default="hs300", choices=["hs300", "zz500", "zz1000", "cyb", "kcb"], help="基准指数")
    parser.add_argument("--pre-days", type=int, default=1, help="前置窗口天数")
    parser.add_argument("--post-days", default="1,3,5", help="后验窗口天数，逗号分隔")
    parser.add_argument("--max-events", type=int, default=40, help="最大事件数")
    parser.add_argument("--token", required=True, help="tushare token（必填）")
    parser.add_argument("--output", required=True, help="输出路径")
    parser.add_argument("--quiet", action="store_true", help="静默模式")
    args = parser.parse_args()

    if not str(args.token or "").strip():
        parser.error("--token 不能为空（请确认 TUSHARE_TOKEN 已正确导出，或直接传入明文）")
    if args.provider == "tushare" and not str(args.token or "").strip():
        parser.error("provider=tushare 时，--token 不能为空")
    if args.provider == "brave" and not str(args.brave_api_key or "").strip():
        parser.error("provider=brave 时，--brave-api-key 不能为空")

    import data_fetcher as df

    df.CLI_TOKEN = args.token
    df.VERBOSE = not args.quiet
    code = df.normalize_symbol(args.code)
    post_days = _parse_post_days(args.post_days)

    basic_info = df.get_stock_info(code)
    name = args.name or basic_info.get("name", "")
    price = df.get_price_data(code, days=max(120, max(post_days) * 20))
    benchmark_price = df.get_index_price_data(args.benchmark, days=max(120, max(post_days) * 20))
    performance_data = df.get_performance_data(code, years=max(1, args.years))
    news_items = fetch_news(
        code=code,
        name=name,
        days=max(1, args.days),
        limit=max(1, args.limit),
        provider=args.provider,
        brave_api_key=args.brave_api_key,
        tushare_token=args.token,
    )

    event_source = {
        "code": code,
        "news_items": news_items,
        "performance_data": performance_data,
    }
    candidates = collect_event_candidates(event_source, max_events=max(10, args.max_events * 2))
    event_window = calculate_event_window(
        price=price,
        events=candidates,
        benchmark_price=benchmark_price,
        pre_days=max(0, args.pre_days),
        post_days=post_days,
        max_events=max(10, args.max_events),
    )
    event_window["benchmark"] = args.benchmark
    if isinstance(benchmark_price, dict) and benchmark_price.get("error"):
        event_window["benchmark_error"] = benchmark_price.get("error")

    payload = {
        "code": code,
        "fetch_time": datetime.now().isoformat(),
        "section": "event_window",
        "event_window": event_window,
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    if not args.quiet:
        print(f"已保存: {out}")


if __name__ == "__main__":
    main()
