#!/usr/bin/env python3
"""
新闻抓取模块（MVP）
- 基于 Google News RSS 的公开新闻聚合
- 输出统一新闻结构，供舆情分析使用
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import List, Optional


GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
BING_NEWS_RSS = "https://www.bing.com/news/search"
UTC8 = timezone(timedelta(hours=8))


@dataclass
class NewsItem:
    title: str
    source: str
    published_at: str
    url: str
    summary: str
    query: str


def _build_query(code: str, name: str = "") -> str:
    parts = [p for p in [code, name, "A股", "上市公司"] if p]
    return " ".join(parts)


def _parse_rss_datetime(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(UTC8)
    except Exception:
        return None


def _parse_rss(payload: bytes, query: str, since: datetime, limit: int) -> List[dict]:
    root = ET.fromstring(payload)
    channel = root.find("channel")
    if channel is None:
        return []

    items: List[NewsItem] = []
    for item in channel.findall("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        source = (item.findtext("source") or "").strip() or "RSS"
        summary = (item.findtext("description") or "").strip()

        dt = _parse_rss_datetime(pub)
        if dt and dt < since:
            continue

        items.append(
            NewsItem(
                title=title,
                source=source,
                published_at=(dt.isoformat() if dt else ""),
                url=link,
                summary=summary,
                query=query,
            )
        )

        if len(items) >= max(1, limit):
            break

    return [asdict(x) for x in items]


def _request_rss(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; stock-analysis-news/1.0)",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read()


def _fetch_tushare_news(code: str, name: str, days: int, limit: int) -> List[dict]:
    token = os.getenv("TUSHARE_TOKEN") or os.getenv("TS_TOKEN")
    if not token:
        return []

    try:
        import tushare as ts
    except Exception:
        return []

    ts.set_token(token)
    pro = ts.pro_api()

    end_dt = datetime.now(UTC8)
    start_dt = end_dt - timedelta(days=max(1, days))
    start_s = start_dt.strftime("%Y-%m-%d %H:%M:%S")
    end_s = end_dt.strftime("%Y-%m-%d %H:%M:%S")

    candidates = []
    try:
        df = pro.news(start_date=start_s, end_date=end_s)
        if df is not None and not df.empty:
            candidates.append(df)
    except Exception:
        pass

    try:
        df = pro.major_news(start_date=start_s, end_date=end_s)
        if df is not None and not df.empty:
            candidates.append(df)
    except Exception:
        pass

    if not candidates:
        return []

    query_tokens = [t for t in [code, name] if t]
    out: List[dict] = []
    for df in candidates:
        for _, row in df.iterrows():
            title = str(row.get("title", "") or "")
            content = str(row.get("content", "") or row.get("brief", "") or "")
            text = f"{title} {content}"
            if query_tokens and not any(tok in text for tok in query_tokens):
                continue

            pub = str(row.get("datetime", "") or row.get("pub_time", "") or row.get("pubdate", "") or "")
            out.append(
                {
                    "title": title.strip(),
                    "source": str(row.get("src", "") or row.get("media", "") or "Tushare"),
                    "published_at": pub,
                    "url": str(row.get("url", "") or ""),
                    "summary": content[:300],
                    "query": _build_query(code, name),
                }
            )
            if len(out) >= max(1, limit):
                return out

    return out


def fetch_news(code: str, name: str = "", days: int = 7, limit: int = 20, language: str = "zh-CN") -> List[dict]:
    """抓取新闻列表。"""
    query = _build_query(code=code, name=name)
    since = datetime.now(UTC8) - timedelta(days=max(1, days))

    google_params = {
        "q": query,
        "hl": language,
        "gl": "CN",
        "ceid": "CN:zh-Hans",
    }
    bing_params = {
        "q": query,
        "format": "rss",
        "setlang": "zh-cn",
    }

    provider_urls = [
        ("google", f"{GOOGLE_NEWS_RSS}?{urllib.parse.urlencode(google_params)}"),
        ("bing", f"{BING_NEWS_RSS}?{urllib.parse.urlencode(bing_params)}"),
    ]

    provider_errors = []
    try:
        ts_items = _fetch_tushare_news(code=code, name=name, days=days, limit=limit)
        if ts_items:
            return ts_items
    except Exception as exc:
        provider_errors.append(f"tushare: {exc}")

    for provider, url in provider_urls:
        try:
            payload = _request_rss(url)
            items = _parse_rss(payload, query=query, since=since, limit=limit)
            if items:
                return items
        except Exception as exc:
            provider_errors.append(f"{provider}: {exc}")

    if provider_errors:
        raise RuntimeError("所有新闻源不可用: " + "; ".join(provider_errors))

    return []


def main():
    parser = argparse.ArgumentParser(description="A股新闻抓取工具")
    parser.add_argument("--code", required=True, help="股票代码，如 600519")
    parser.add_argument("--name", default="", help="股票名称，可选")
    parser.add_argument("--days", type=int, default=7, help="最近多少天")
    parser.add_argument("--limit", type=int, default=20, help="最多返回条数")
    parser.add_argument("--output", help="输出文件路径")
    args = parser.parse_args()

    result = {
        "code": args.code,
        "name": args.name,
        "fetch_time": datetime.now(UTC8).isoformat(),
        "days": args.days,
        "limit": args.limit,
        "news_items": [],
    }

    try:
        result["news_items"] = fetch_news(args.code, name=args.name, days=args.days, limit=args.limit)
    except Exception as exc:
        result["error"] = str(exc)

    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
    else:
        print(output)


if __name__ == "__main__":
    main()
