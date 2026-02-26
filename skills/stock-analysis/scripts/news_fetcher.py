#!/usr/bin/env python3
"""
新闻抓取模块（MVP）
- 基于 Google News RSS 的公开新闻聚合
- 支持 Brave Search API（新闻搜索）
- 输出统一新闻结构，供舆情分析使用
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import List, Optional
from env_loader import get_tushare_token, get_brave_api_key


GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
BING_NEWS_RSS = "https://www.bing.com/news/search"
BRAVE_NEWS_API = "https://api.search.brave.com/res/v1/news/search"
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


def _parse_datetime_any(value: str) -> Optional[datetime]:
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None

    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(UTC8)
    except Exception:
        pass

    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) >= 14:
        try:
            return datetime.strptime(digits[:14], "%Y%m%d%H%M%S").replace(tzinfo=UTC8)
        except Exception:
            pass
    if len(digits) >= 8:
        try:
            return datetime.strptime(digits[:8], "%Y%m%d").replace(tzinfo=UTC8)
        except Exception:
            pass
    return None


def _parse_relative_time(value: str, now: datetime) -> Optional[datetime]:
    s = str(value or "").strip().lower()
    if not s:
        return None

    # English patterns like: "3 hours ago", "2 days ago"
    m = re.search(r"(\d+)\s*(minute|minutes|hour|hours|day|days|week|weeks|month|months|year|years)\s+ago", s)
    if m:
        num = int(m.group(1))
        unit = m.group(2)
        if "minute" in unit:
            return now - timedelta(minutes=num)
        if "hour" in unit:
            return now - timedelta(hours=num)
        if "day" in unit:
            return now - timedelta(days=num)
        if "week" in unit:
            return now - timedelta(weeks=num)
        if "month" in unit:
            return now - timedelta(days=num * 30)
        if "year" in unit:
            return now - timedelta(days=num * 365)

    # Chinese patterns like: "3小时前", "2天前"
    m = re.search(r"(\d+)\s*(分钟|小时|天|周|个月|月|年)\s*前", s)
    if m:
        num = int(m.group(1))
        unit = m.group(2)
        if unit == "分钟":
            return now - timedelta(minutes=num)
        if unit == "小时":
            return now - timedelta(hours=num)
        if unit == "天":
            return now - timedelta(days=num)
        if unit == "周":
            return now - timedelta(weeks=num)
        if unit in ["个月", "月"]:
            return now - timedelta(days=num * 30)
        if unit == "年":
            return now - timedelta(days=num * 365)
    return None


def _extract_brave_datetime(row: dict, now: datetime) -> Optional[datetime]:
    fields = [
        "published_at",
        "published",
        "date",
        "page_age",
        "age",
    ]
    for key in fields:
        val = row.get(key)
        if val in [None, ""]:
            continue
        dt = _parse_datetime_any(str(val))
        if dt is not None:
            return dt
        dt = _parse_relative_time(str(val), now=now)
        if dt is not None:
            return dt
    return None


def _build_brave_freshness(days: int) -> str:
    d = max(1, int(days))
    if d <= 1:
        return "pd"
    if d <= 7:
        return "pw"
    if d <= 31:
        return "pm"
    return "py"


def _map_brave_lang(language: str) -> str:
    lang = (language or "").strip().lower()
    if lang in ["zh-cn", "zh-hans", "zh"]:
        return "zh-hans"
    if lang in ["zh-tw", "zh-hant"]:
        return "zh-hant"
    if lang:
        return lang
    return "zh-hans"


def _request_json(url: str, headers: Optional[dict] = None) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; stock-analysis-news/1.0)",
            "Accept": "application/json",
            **(headers or {}),
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = resp.read().decode("utf-8", errors="ignore")
        return json.loads(payload or "{}")


def _fetch_brave_news(
    code: str,
    name: str,
    days: int,
    limit: int,
    api_key: str,
    language: str = "zh-CN",
) -> List[dict]:
    if not api_key:
        return []

    query = _build_query(code=code, name=name)
    since = datetime.now(UTC8) - timedelta(days=max(1, days))
    now = datetime.now(UTC8)

    params = {
        "q": query,
        "count": max(1, min(int(limit), 20)),
        "freshness": _build_brave_freshness(days),
        "search_lang": _map_brave_lang(language),
        "country": "CN",
        "safesearch": "off",
        "spellcheck": 0,
    }
    url = f"{BRAVE_NEWS_API}?{urllib.parse.urlencode(params)}"
    payload = _request_json(url, headers={"X-Subscription-Token": api_key})

    candidates = []
    for key in ["results"]:
        obj = payload.get(key)
        if isinstance(obj, list):
            candidates = obj
            break
    if not candidates and isinstance(payload.get("news"), dict):
        news_results = payload.get("news", {}).get("results")
        if isinstance(news_results, list):
            candidates = news_results

    out: List[dict] = []
    for row in candidates:
        if not isinstance(row, dict):
            continue

        published_dt = _extract_brave_datetime(row, now=now)
        # 时间过滤严格执行：无法解析时间则跳过
        if published_dt is None or published_dt < since:
            continue

        source = (
            row.get("source")
            or row.get("meta_url", {}).get("hostname")
            or row.get("meta_url", {}).get("netloc")
            or "Brave"
        )
        title = str(row.get("title", "") or "").strip()
        url_val = str(row.get("url", "") or "").strip()
        summary = str(row.get("description", "") or row.get("snippet", "") or "").strip()
        if not title or not url_val:
            continue

        out.append(
            asdict(
                NewsItem(
                    title=title,
                    source=str(source),
                    published_at=published_dt.isoformat(),
                    url=url_val,
                    summary=summary,
                    query=query,
                )
            )
        )

        if len(out) >= max(1, limit):
            break

    return out


def _fetch_tushare_news(code: str, name: str, days: int, limit: int) -> List[dict]:
    token = get_tushare_token()
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


def fetch_news(
    code: str,
    name: str = "",
    days: int = 7,
    limit: int = 20,
    language: str = "zh-CN",
    provider: str = "auto",
    brave_api_key: str = "",
) -> List[dict]:
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

    provider = (provider or "auto").strip().lower()
    brave_key = brave_api_key or get_brave_api_key()
    provider_errors = []

    strategy = []
    if provider == "brave":
        strategy = ["brave"]
    elif provider == "tushare":
        strategy = ["tushare"]
    elif provider == "rss":
        strategy = ["rss"]
    else:
        # auto: 若存在 BRAVE_API_KEY 优先 Brave，否则沿用 tushare + RSS
        strategy = ["brave", "tushare", "rss"] if brave_key else ["tushare", "rss"]

    for source in strategy:
        if source == "brave":
            if not brave_key:
                provider_errors.append("brave: 缺少 BRAVE_API_KEY")
                continue
            try:
                items = _fetch_brave_news(
                    code=code,
                    name=name,
                    days=days,
                    limit=limit,
                    api_key=brave_key,
                    language=language,
                )
                if items:
                    return items
            except Exception as exc:
                provider_errors.append(f"brave: {exc}")
            continue

        if source == "tushare":
            try:
                ts_items = _fetch_tushare_news(code=code, name=name, days=days, limit=limit)
                if ts_items:
                    return ts_items
            except Exception as exc:
                provider_errors.append(f"tushare: {exc}")
            continue

        if source == "rss":
            for provider_name, url in provider_urls:
                try:
                    payload = _request_rss(url)
                    items = _parse_rss(payload, query=query, since=since, limit=limit)
                    if items:
                        return items
                except Exception as exc:
                    provider_errors.append(f"{provider_name}: {exc}")

    if provider_errors:
        raise RuntimeError("所有新闻源不可用: " + "; ".join(provider_errors))

    return []


def main():
    parser = argparse.ArgumentParser(description="A股新闻抓取工具")
    parser.add_argument("--code", required=True, help="股票代码，如 600519")
    parser.add_argument("--name", default="", help="股票名称，可选")
    parser.add_argument("--days", type=int, default=7, help="最近多少天")
    parser.add_argument("--limit", type=int, default=20, help="最多返回条数")
    parser.add_argument("--provider", choices=["auto", "brave", "tushare", "rss"], default="auto", help="新闻源")
    parser.add_argument("--brave-api-key", default="", help="Brave Search API Key（可不传，默认从 ~/.aj-skills/.env 读取 BRAVE_API_KEY）")
    parser.add_argument("--output", help="输出文件路径")
    args = parser.parse_args()

    result = {
        "code": args.code,
        "name": args.name,
        "fetch_time": datetime.now(UTC8).isoformat(),
        "days": args.days,
        "limit": args.limit,
        "provider": args.provider,
        "news_items": [],
    }

    try:
        result["news_items"] = fetch_news(
            args.code,
            name=args.name,
            days=args.days,
            limit=args.limit,
            provider=args.provider,
            brave_api_key=args.brave_api_key,
        )
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
