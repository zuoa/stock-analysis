#!/usr/bin/env python3
"""
实时指标计算模块（P0）
- 趋势：多周期动量 + 相对强弱
- 确认：成交/量比/换手 + 资金连续性
- 风险：振幅/波动/回撤
- 筹码：解禁/减持/回购（扣分）
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional


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


def _pct_change(curr: float, prev: float) -> Optional[float]:
    if curr is None or prev in [None, 0]:
        return None
    return (curr / prev - 1.0) * 100.0


def _extract_close_series(price: Dict, max_points: int = 240) -> List[float]:
    rows = price.get("price_data", []) or []
    closes: List[float] = []
    for row in rows[-max_points:]:
        c = _safe_float(row.get("收盘"))
        if c is not None:
            closes.append(c)
    return closes


def _extract_numeric_series(rows: List[Dict], key: str) -> List[float]:
    out: List[float] = []
    for row in rows:
        v = _safe_float(row.get(key))
        if v is not None:
            out.append(v)
    return out


def _std(values: List[float]) -> Optional[float]:
    if not values:
        return None
    if len(values) == 1:
        return 0.0
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(max(var, 0.0))


def _calc_max_drawdown_pct(closes: List[float], window: int = 60) -> Optional[float]:
    if not closes:
        return None
    arr = closes[-window:] if len(closes) > window else closes
    peak = arr[0]
    max_dd = 0.0
    for px in arr:
        peak = max(peak, px)
        if peak > 0:
            dd = (px / peak - 1.0) * 100.0
            max_dd = min(max_dd, dd)
    return max_dd


def _momentum_pct(closes: List[float], n: int) -> Optional[float]:
    if len(closes) <= n:
        return None
    return _pct_change(closes[-1], closes[-(n + 1)])


def _calc_trend_metrics(stock_closes: List[float], bench_closes: List[float]) -> Dict:
    horizons = [1, 5, 20, 60]
    momentum = {f"return_{h}d": _momentum_pct(stock_closes, h) for h in horizons}

    relative = {}
    for h in horizons:
        sr = momentum.get(f"return_{h}d")
        br = _momentum_pct(bench_closes, h) if bench_closes else None
        relative[f"vs_benchmark_{h}d"] = (sr - br) if sr is not None and br is not None else None

    weighted_ret = 0.0
    weights = {1: 0.35, 5: 0.25, 20: 0.25, 60: 0.15}
    weight_sum = 0.0
    for h, w in weights.items():
        r = momentum.get(f"return_{h}d")
        if r is None:
            continue
        weighted_ret += r * w
        weight_sum += w
    weighted_ret = weighted_ret / weight_sum if weight_sum > 0 else 0.0

    rel_values = [v for v in relative.values() if v is not None]
    rel_avg = sum(rel_values) / len(rel_values) if rel_values else 0.0

    # 1%加权收益约等于2分，5%相对强弱约等于10分
    trend_score = _clamp(50 + weighted_ret * 2.0 + rel_avg * 2.0)

    return {
        "momentum_pct": momentum,
        "relative_strength_pct": relative,
        "trend_score": round(trend_score, 2),
    }


def _calc_confirm_metrics(price_rows: List[Dict], flow_metrics: Dict) -> Dict:
    if not price_rows:
        return {
            "amount_ratio_20d": None,
            "volume_ratio": None,
            "turnover_rate": None,
            "confirm_score": 50.0,
        }

    latest = price_rows[-1]
    recent = price_rows[-20:] if len(price_rows) >= 20 else price_rows
    amount_series = _extract_numeric_series(recent, "成交额")
    latest_amount = _safe_float(latest.get("成交额"))
    avg_amount = (sum(amount_series) / len(amount_series)) if amount_series else None
    amount_ratio = (latest_amount / avg_amount) if latest_amount and avg_amount else None

    volume_ratio = _safe_float(latest.get("量比"))
    turnover_rate = _safe_float(latest.get("换手率"))

    amount_score = _clamp((amount_ratio or 1.0) * 50.0) if amount_ratio else 50.0
    vr_score = _clamp((volume_ratio or 1.0) * 50.0) if volume_ratio else 50.0
    tr_score = _clamp((turnover_rate or 1.0) * 35.0) if turnover_rate else 50.0

    net_inflow_ratio = _safe_float(flow_metrics.get("net_inflow_ratio"), 0.0) or 0.0
    positive_days_5 = int(_safe_float(flow_metrics.get("positive_days_5"), 0) or 0)
    flow_score = _clamp(50 + net_inflow_ratio * 4.0 + positive_days_5 * 8.0)

    confirm_score = (
        amount_score * 0.30
        + vr_score * 0.20
        + tr_score * 0.20
        + flow_score * 0.30
    )

    return {
        "amount_ratio_20d": round(amount_ratio, 4) if amount_ratio is not None else None,
        "volume_ratio": volume_ratio,
        "turnover_rate": turnover_rate,
        "net_inflow_ratio": net_inflow_ratio,
        "positive_days_5": positive_days_5,
        "confirm_score": round(_clamp(confirm_score), 2),
    }


def _calc_risk_metrics(price_rows: List[Dict], closes: List[float], window: int = 60) -> Dict:
    if not price_rows:
        return {
            "intraday_amplitude_pct": None,
            "realized_volatility_20d_pct": None,
            "downside_volatility_20d_pct": None,
            "max_drawdown_window_pct": None,
            "risk_penalty": 20.0,
        }

    latest = price_rows[-1]
    high = _safe_float(latest.get("最高"))
    low = _safe_float(latest.get("最低"))
    close = _safe_float(latest.get("收盘"))
    amplitude = ((high - low) / close * 100.0) if (high is not None and low is not None and close not in [None, 0]) else None

    returns: List[float] = []
    arr = closes[-(window + 1):] if len(closes) > (window + 1) else closes
    for i in range(1, len(arr)):
        if arr[i - 1] == 0:
            continue
        returns.append((arr[i] / arr[i - 1]) - 1.0)

    tail20 = returns[-20:] if len(returns) >= 20 else returns
    daily_std = _std(tail20)
    realized_vol = (daily_std * math.sqrt(252) * 100.0) if daily_std is not None else None

    downside = [r for r in tail20 if r < 0]
    downside_std = _std(downside)
    downside_vol = (downside_std * math.sqrt(252) * 100.0) if downside_std is not None else None

    max_dd = _calc_max_drawdown_pct(closes, window=window)

    # 风险扣分越高越差
    penalty = 0.0
    if amplitude is not None:
        penalty += _clamp((amplitude - 2.0) * 3.0, 0, 20)
    if realized_vol is not None:
        penalty += _clamp((realized_vol - 25.0) * 0.8, 0, 25)
    if downside_vol is not None:
        penalty += _clamp((downside_vol - 18.0) * 0.7, 0, 20)
    if max_dd is not None:
        penalty += _clamp(abs(min(max_dd, 0.0)) * 1.2, 0, 35)

    return {
        "intraday_amplitude_pct": round(amplitude, 4) if amplitude is not None else None,
        "realized_volatility_20d_pct": round(realized_vol, 4) if realized_vol is not None else None,
        "downside_volatility_20d_pct": round(downside_vol, 4) if downside_vol is not None else None,
        "max_drawdown_window_pct": round(max_dd, 4) if max_dd is not None else None,
        "risk_penalty": round(_clamp(penalty, 0, 100), 2),
    }


def _calc_chip_penalty(chip_events: Dict) -> Dict:
    unlock_30d_ratio = _safe_float(chip_events.get("unlock_30d_ratio"), 0.0) or 0.0
    unlock_90d_ratio = _safe_float(chip_events.get("unlock_90d_ratio"), 0.0) or 0.0
    reduction_density_30d = _safe_float(chip_events.get("reduction_density_30d"), 0.0) or 0.0
    repurchase_ratio_90d = _safe_float(chip_events.get("repurchase_ratio_90d"), 0.0) or 0.0

    penalty = 0.0
    penalty += _clamp(unlock_30d_ratio * 6.0, 0, 18)
    penalty += _clamp(unlock_90d_ratio * 3.5, 0, 16)
    penalty += _clamp(reduction_density_30d * 5.0, 0, 15)
    penalty -= _clamp(repurchase_ratio_90d * 4.0, 0, 12)

    return {
        "unlock_30d_ratio": unlock_30d_ratio,
        "unlock_90d_ratio": unlock_90d_ratio,
        "reduction_density_30d": reduction_density_30d,
        "repurchase_ratio_90d": repurchase_ratio_90d,
        "chip_penalty": round(_clamp(penalty, 0, 40), 2),
    }


def calculate_realtime_metrics(
    price: Dict,
    benchmark_price: Optional[Dict] = None,
    flow_metrics: Optional[Dict] = None,
    chip_events: Optional[Dict] = None,
    window: int = 60,
) -> Dict:
    """计算P0实时指标与评分。"""
    flow_metrics = flow_metrics or {}
    chip_events = chip_events or {}

    stock_rows = price.get("price_data", []) or []
    stock_closes = _extract_close_series(price)
    bench_closes = _extract_close_series(benchmark_price or {})

    trend = _calc_trend_metrics(stock_closes, bench_closes)
    confirm = _calc_confirm_metrics(stock_rows, flow_metrics)
    risk = _calc_risk_metrics(stock_rows, stock_closes, window=max(20, window))
    chip = _calc_chip_penalty(chip_events)

    realtime_score = (
        trend.get("trend_score", 50.0) * 0.45
        + confirm.get("confirm_score", 50.0) * 0.30
        + (100.0 - risk.get("risk_penalty", 20.0)) * 0.25
        - chip.get("chip_penalty", 0.0)
    )

    return {
        "window_days": max(20, window),
        "trend": trend,
        "confirm": confirm,
        "risk": risk,
        "chip": chip,
        "realtime_score": round(_clamp(realtime_score), 2),
    }

