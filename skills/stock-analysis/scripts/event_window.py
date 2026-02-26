#!/usr/bin/env python3
"""
事件窗口分析模块（P1）
- 基于日线计算事件后 1/3/5 日价格反应
- 支持相对基准的超额收益（abnormal return）
- 事件源：新闻、业绩预告/快报、审计意见
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Sequence, Tuple


def _safe_float(val, default: Optional[float] = None) -> Optional[float]:
    if val is None:
        return default
    try:
        if isinstance(val, str):
            val = val.replace("%", "").replace(",", "").strip()
            if not val:
                return default
        return float(val)
    except Exception:
        return default


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _parse_datetime(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    s = str(value).strip()
    if not s:
        return None

    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        pass

    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) >= 14:
        try:
            return datetime.strptime(digits[:14], "%Y%m%d%H%M%S")
        except Exception:
            pass
    if len(digits) >= 8:
        try:
            return datetime.strptime(digits[:8], "%Y%m%d")
        except Exception:
            return None
    return None


def _to_ymd(dt: datetime) -> str:
    return dt.strftime("%Y%m%d")


def _event_anchor_date(event_dt: datetime) -> datetime:
    # 对于含具体时间的事件，15:00后视为次一交易日生效
    if event_dt.hour >= 15:
        return (event_dt + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return event_dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _extract_trade_rows(price: Dict) -> List[Dict]:
    rows = price.get("price_data", []) if isinstance(price, dict) else []
    out: List[Dict] = []
    for row in rows:
        d = _parse_datetime(row.get("日期"))
        c = _safe_float(row.get("收盘"))
        if d is None or c in [None, 0]:
            continue
        out.append({"date": d.replace(hour=0, minute=0, second=0, microsecond=0), "close": c, "raw": row})
    out.sort(key=lambda x: x["date"])
    return out


def _locate_trade_index(trade_dates: Sequence[datetime], anchor: datetime) -> Optional[int]:
    for idx, d in enumerate(trade_dates):
        if d >= anchor:
            return idx
    return None


def _pct_change(curr: Optional[float], prev: Optional[float]) -> Optional[float]:
    if curr is None or prev in [None, 0]:
        return None
    return (curr / prev - 1.0) * 100.0


def _avg(values: List[Optional[float]]) -> Optional[float]:
    arr = [x for x in values if x is not None]
    if not arr:
        return None
    return sum(arr) / len(arr)


def _is_negative_audit(opinion: str) -> bool:
    s = str(opinion or "")
    return any(x in s for x in ["非标", "保留", "否定", "无法表示"])


def collect_event_candidates(stock_data: Dict, max_events: int = 60) -> List[Dict]:
    """从 stock_data 聚合事件候选集。"""
    events: List[Dict] = []

    news_items = stock_data.get("news_items", []) if isinstance(stock_data, dict) else []
    for item in news_items or []:
        event_dt = _parse_datetime(item.get("published_at") or item.get("date"))
        if event_dt is None:
            continue
        title = str(item.get("title", "") or "").strip() or "新闻事件"
        events.append(
            {
                "event_date": _to_ymd(event_dt),
                "event_time": event_dt.isoformat(),
                "event_type": "news",
                "title": title,
                "source": item.get("source", ""),
                "sentiment": _safe_float(item.get("sentiment")),
                "importance": _safe_float(item.get("importance"), 1.0) or 1.0,
            }
        )

    perf = stock_data.get("performance_data", {}) if isinstance(stock_data, dict) else {}
    forecast = perf.get("forecast", []) if isinstance(perf, dict) else []
    for row in forecast[:12]:
        event_dt = _parse_datetime(row.get("ann_date"))
        if event_dt is None:
            continue
        pmin = _safe_float(row.get("p_change_min"))
        pmax = _safe_float(row.get("p_change_max"))
        avg_change = None
        if pmin is not None and pmax is not None:
            avg_change = (pmin + pmax) / 2.0
        elif pmin is not None:
            avg_change = pmin
        elif pmax is not None:
            avg_change = pmax

        events.append(
            {
                "event_date": _to_ymd(event_dt),
                "event_time": event_dt.isoformat(),
                "event_type": "forecast",
                "title": f"业绩预告：{row.get('type', '未披露类型')}（净利变动约 {avg_change if avg_change is not None else '-'}%）",
                "source": "performance_data.forecast",
                "sentiment": (avg_change or 0.0) / 50.0 if avg_change is not None else None,
                "importance": 1.3,
            }
        )

    express = perf.get("express", []) if isinstance(perf, dict) else []
    for row in express[:12]:
        event_dt = _parse_datetime(row.get("ann_date"))
        if event_dt is None:
            continue
        yoy = _safe_float(row.get("yoy_net_profit"))
        events.append(
            {
                "event_date": _to_ymd(event_dt),
                "event_time": event_dt.isoformat(),
                "event_type": "express",
                "title": f"业绩快报：净利润同比 {yoy if yoy is not None else '-'}%",
                "source": "performance_data.express",
                "sentiment": (yoy or 0.0) / 50.0 if yoy is not None else None,
                "importance": 1.2,
            }
        )

    audit = perf.get("audit", []) if isinstance(perf, dict) else []
    for row in audit[:8]:
        event_dt = _parse_datetime(row.get("ann_date"))
        if event_dt is None:
            continue
        opinion = str(row.get("audit_result", "") or row.get("audit_agency", "") or "审计披露")
        events.append(
            {
                "event_date": _to_ymd(event_dt),
                "event_time": event_dt.isoformat(),
                "event_type": "audit",
                "title": f"审计意见：{opinion}",
                "source": "performance_data.audit",
                "sentiment": -0.6 if _is_negative_audit(opinion) else 0.1,
                "importance": 1.1,
            }
        )

    # 去重：同日同标题只保留一条
    dedup: Dict[Tuple[str, str], Dict] = {}
    for item in events:
        key = (str(item.get("event_date", "")), str(item.get("title", "")))
        if key not in dedup:
            dedup[key] = item
    merged = list(dedup.values())
    merged.sort(key=lambda x: x.get("event_date", ""), reverse=True)
    return merged[:max_events]


def calculate_event_window(
    price: Dict,
    events: List[Dict],
    benchmark_price: Optional[Dict] = None,
    pre_days: int = 1,
    post_days: Sequence[int] = (1, 3, 5),
    max_events: int = 40,
) -> Dict:
    """计算事件窗口反应。"""
    rows = _extract_trade_rows(price or {})
    if not rows:
        return {
            "pre_days": max(0, int(pre_days)),
            "post_days": [int(x) for x in post_days if int(x) >= 1],
            "event_count": len(events or []),
            "matched_event_count": 0,
            "event_window_score": 50.0,
            "events": [],
            "error": "缺少有效价格序列",
        }

    bench_rows = _extract_trade_rows(benchmark_price or {})
    bench_map = {x["date"]: x["close"] for x in bench_rows}

    trade_dates = [x["date"] for x in rows]
    closes = [x["close"] for x in rows]

    post = sorted({int(x) for x in post_days if int(x) >= 1})
    pre_days = max(0, int(pre_days))

    analyzed: List[Dict] = []
    for event in events[:max_events]:
        event_dt = _parse_datetime(event.get("event_time") or event.get("event_date"))
        if event_dt is None:
            continue
        anchor = _event_anchor_date(event_dt)
        idx = _locate_trade_index(trade_dates, anchor)
        if idx is None:
            continue

        base = closes[idx]
        pre_idx = idx - pre_days
        pre_ret = _pct_change(closes[idx - 1], closes[pre_idx]) if pre_days > 0 and pre_idx >= 0 and idx - 1 >= 0 else None

        row = {
            "event_date": event.get("event_date"),
            "event_trade_date": _to_ymd(trade_dates[idx]),
            "event_type": event.get("event_type"),
            "title": event.get("title"),
            "source": event.get("source"),
            "sentiment": event.get("sentiment"),
            "importance": event.get("importance"),
            "pre_return_pct": round(pre_ret, 4) if pre_ret is not None else None,
        }

        event_date_obj = trade_dates[idx]
        bench_base = bench_map.get(event_date_obj)

        for n in post:
            k = idx + n
            if k >= len(closes):
                row[f"post_{n}d_pct"] = None
                row[f"abnormal_{n}d_pct"] = None
                continue
            post_ret = _pct_change(closes[k], base)
            row[f"post_{n}d_pct"] = round(post_ret, 4) if post_ret is not None else None

            bench_ret = None
            if bench_base not in [None, 0]:
                bench_px = bench_map.get(trade_dates[k])
                bench_ret = _pct_change(bench_px, bench_base)
            abn = (post_ret - bench_ret) if post_ret is not None and bench_ret is not None else None
            row[f"abnormal_{n}d_pct"] = round(abn, 4) if abn is not None else None

        core = row.get("abnormal_3d_pct")
        if core is None:
            core = row.get("post_3d_pct")
        if core is None:
            core = row.get("post_1d_pct")
        score = 50.0 + (core or 0.0) * 4.0
        sentiment = _safe_float(event.get("sentiment"))
        if sentiment is not None:
            score += max(-10.0, min(10.0, sentiment * 10.0))
        row["event_impact_score"] = round(_clamp(score), 2)
        analyzed.append(row)

    analyzed.sort(key=lambda x: x.get("event_trade_date", ""), reverse=True)

    def collect_metric(metric_key: str) -> List[Optional[float]]:
        return [_safe_float(x.get(metric_key)) for x in analyzed]

    avg_post_1 = _avg(collect_metric("post_1d_pct"))
    avg_post_3 = _avg(collect_metric("post_3d_pct"))
    avg_post_5 = _avg(collect_metric("post_5d_pct"))
    avg_abn_1 = _avg(collect_metric("abnormal_1d_pct"))
    avg_abn_3 = _avg(collect_metric("abnormal_3d_pct"))
    avg_abn_5 = _avg(collect_metric("abnormal_5d_pct"))

    post_3_values = [x for x in collect_metric("post_3d_pct") if x is not None]
    positive_ratio_3d = (len([x for x in post_3_values if x > 0]) / len(post_3_values)) if post_3_values else None
    post_5_values = [x for x in collect_metric("post_5d_pct") if x is not None]
    worst_5d = min(post_5_values) if post_5_values else None

    ev_score = 50.0
    if avg_abn_3 is not None:
        ev_score += avg_abn_3 * 6.0
    elif avg_post_3 is not None:
        ev_score += avg_post_3 * 4.0
    if positive_ratio_3d is not None:
        ev_score += (positive_ratio_3d - 0.5) * 40.0
    if worst_5d is not None and worst_5d < -5:
        ev_score -= min(20.0, abs(worst_5d + 5.0) * 1.8)

    ranked = []
    for item in analyzed:
        key = _safe_float(item.get("abnormal_3d_pct"))
        if key is None:
            key = _safe_float(item.get("post_3d_pct"))
        if key is None:
            key = _safe_float(item.get("post_1d_pct"), 0.0)
        ranked.append((key or 0.0, item))

    ranked.sort(key=lambda x: x[0], reverse=True)
    top_positive = [x[1] for x in ranked[:5] if x[0] > 0]
    top_negative = [x[1] for x in sorted(ranked, key=lambda x: x[0])[:5] if x[0] < 0]

    summary = {
        "avg_post_1d_pct": round(avg_post_1, 4) if avg_post_1 is not None else None,
        "avg_post_3d_pct": round(avg_post_3, 4) if avg_post_3 is not None else None,
        "avg_post_5d_pct": round(avg_post_5, 4) if avg_post_5 is not None else None,
        "avg_abnormal_1d_pct": round(avg_abn_1, 4) if avg_abn_1 is not None else None,
        "avg_abnormal_3d_pct": round(avg_abn_3, 4) if avg_abn_3 is not None else None,
        "avg_abnormal_5d_pct": round(avg_abn_5, 4) if avg_abn_5 is not None else None,
        "positive_ratio_3d": round(positive_ratio_3d, 4) if positive_ratio_3d is not None else None,
        "worst_post_5d_pct": round(worst_5d, 4) if worst_5d is not None else None,
    }

    return {
        "pre_days": pre_days,
        "post_days": post,
        "benchmark": (benchmark_price or {}).get("benchmark"),
        "event_count": len(events or []),
        "matched_event_count": len(analyzed),
        "coverage_ratio": round(len(analyzed) / len(events), 4) if events else 0.0,
        "summary": summary,
        "event_window_score": round(_clamp(ev_score), 2),
        "top_positive_events": top_positive,
        "top_negative_events": top_negative,
        "events": analyzed,
    }

