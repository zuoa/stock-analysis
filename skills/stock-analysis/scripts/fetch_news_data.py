#!/usr/bin/env python3
"""分模块抓取：新闻与舆情数据。"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from sentiment_analyzer import analyze_news_sentiment
from news_fetcher import fetch_news


def main():
    parser = argparse.ArgumentParser(description="抓取新闻与舆情模块 news.json")
    parser.add_argument("--code", required=True, help="股票代码，如 600519")
    parser.add_argument("--name", default="", help="股票名称，可选")
    parser.add_argument("--days", type=int, default=7, help="新闻窗口天数")
    parser.add_argument("--limit", type=int, default=20, help="新闻最大条数")
    parser.add_argument("--provider", choices=["auto", "brave", "tushare", "rss"], default="auto", help="新闻源")
    parser.add_argument("--token", default="", help="tushare token（provider=tushare 时必填）")
    parser.add_argument("--brave-api-key", default="", help="Brave API Key（provider=brave 时必填）")
    parser.add_argument("--news-sources", default="", help="来源过滤，逗号分隔")
    parser.add_argument("--output", required=True, help="输出路径")
    parser.add_argument("--quiet", action="store_true", help="静默模式")
    args = parser.parse_args()

    if args.provider == "tushare" and not str(args.token or "").strip():
        parser.error("provider=tushare 时，--token 不能为空")
    if args.provider == "brave" and not str(args.brave_api_key or "").strip():
        parser.error("provider=brave 时，--brave-api-key 不能为空")

    items = fetch_news(
        code=args.code,
        name=args.name,
        days=max(1, args.days),
        limit=max(1, args.limit),
        provider=args.provider,
        brave_api_key=args.brave_api_key,
        tushare_token=args.token,
    )
    if args.news_sources:
        allow_sources = {x.strip().lower() for x in args.news_sources.split(",") if x.strip()}
        if allow_sources:
            items = [x for x in items if x.get("source", "").lower() in allow_sources]

    sentiment = analyze_news_sentiment(items)

    payload = {
        "code": args.code,
        "fetch_time": datetime.now().isoformat(),
        "section": "news",
        "news_items": items,
        "news_sentiment": {
            "analysis_time": sentiment.get("analysis_time"),
            "news_count": sentiment.get("news_count"),
            "overall_sentiment": sentiment.get("overall_sentiment"),
            "risk_level": sentiment.get("risk_level"),
            "risk_tag_count": sentiment.get("risk_tag_count"),
            "top_negative_events": sentiment.get("top_negative_events"),
        },
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    if not args.quiet:
        print(f"已保存: {out}")


if __name__ == "__main__":
    main()
