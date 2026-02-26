#!/usr/bin/env python3
"""
A股数据获取模块
使用tushare获取股票财务数据、行情数据、股东信息等

依赖: pip install tushare pandas
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from functools import wraps
from typing import Callable, Dict, Optional, Sequence, Tuple
from news_fetcher import fetch_news
from sentiment_analyzer import analyze_news_sentiment
from realtime_metrics import calculate_realtime_metrics
from event_window import collect_event_candidates, calculate_event_window

try:
    import pandas as pd
    import tushare as ts
except ImportError:
    print("错误: 请先安装依赖库")
    print("pip install tushare pandas")
    sys.exit(1)


INDEX_CODE_MAP = {
    "hs300": "000300.SH",
    "zz500": "000905.SH",
    "zz1000": "000852.SH",
    "cyb": "399006.SZ",
    "kcb": "000688.SH",
}


def retry_on_failure(max_retries: int = 3, delay: float = 1.0):
    """网络请求重试装饰器"""

    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    last_error = exc
                    if attempt < max_retries - 1:
                        time.sleep(delay * (attempt + 1))
            return {"error": f"重试{max_retries}次后失败: {str(last_error)}"}

        return wrapper

    return decorator


def get_tushare_pro(token: str):
    """初始化tushare pro客户端"""
    if not token:
        raise RuntimeError("缺少 tushare token，请通过 --token 传入")

    ts.set_token(token)
    return ts.pro_api()


PRO = None
CLI_TOKEN = None
VERBOSE = True


def pro():
    """延迟初始化tushare客户端。"""
    global PRO
    if PRO is None:
        PRO = get_tushare_pro(CLI_TOKEN)
    return PRO


def log(message: str):
    if VERBOSE:
        print(message)


def format_table(headers, rows) -> str:
    widths = [len(str(h)) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))

    sep = "-+-".join("-" * w for w in widths)
    lines = [" | ".join(str(h).ljust(widths[i]) for i, h in enumerate(headers)), sep]
    for row in rows:
        lines.append(" | ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)))
    return "\n".join(lines)


def safe_float(value) -> Optional[float]:
    """安全转换为浮点数"""
    if value is None or value == "" or value == "--":
        return None
    try:
        if pd.isna(value):
            return None
        if isinstance(value, str):
            value = value.replace("%", "").replace(",", "")
        return float(value)
    except (ValueError, TypeError):
        return None


def parse_event_window_post_days(raw: str) -> Tuple[int, ...]:
    """解析事件窗口后验天数参数，如: 1,3,5"""
    if not raw:
        return (1, 3, 5)
    values = []
    for part in str(raw).split(","):
        part = part.strip()
        if not part:
            continue
        try:
            day = int(part)
            if day >= 1:
                values.append(day)
        except Exception:
            continue
    if not values:
        return (1, 3, 5)
    return tuple(sorted(set(values)))


def get_cache_path(code: str, data_type: str) -> str:
    """获取缓存文件路径（可按TTL过期）"""
    cache_dir = os.path.join(os.path.dirname(__file__), ".cache")
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"{code}_{data_type}.json")


def get_legacy_cache_path(code: str, data_type: str) -> str:
    """兼容旧版按日缓存文件命名"""
    cache_dir = os.path.join(os.path.dirname(__file__), ".cache")
    os.makedirs(cache_dir, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    return os.path.join(cache_dir, f"{code}_{data_type}_{today}.json")


def _parse_iso_dt(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def load_cache(code: str, data_type: str, ttl_minutes: int = 1440) -> Optional[dict]:
    """加载缓存数据（按TTL有效）"""
    paths = [get_cache_path(code, data_type), get_legacy_cache_path(code, data_type)]
    for cache_path in paths:
        if not os.path.exists(cache_path):
            continue
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if ttl_minutes and ttl_minutes > 0:
                ts = _parse_iso_dt(data.get("_cache_saved_at", "")) or _parse_iso_dt(data.get("fetch_time", ""))
                if ts:
                    age_min = (datetime.now() - ts).total_seconds() / 60
                    if age_min > ttl_minutes:
                        continue
            return data
        except (json.JSONDecodeError, IOError):
            continue
    return None


def save_cache(code: str, data_type: str, data: dict):
    """保存缓存数据"""
    cache_path = get_cache_path(code, data_type)
    try:
        to_save = dict(data)
        to_save["_cache_saved_at"] = datetime.now().isoformat()
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(to_save, f, ensure_ascii=False, default=str)
    except IOError:
        pass


def normalize_symbol(code: str) -> str:
    """统一为6位symbol"""
    code = (code or "").strip().upper()
    if "." in code:
        return code.split(".")[0]
    return code


def to_ts_code(code: str) -> str:
    """将symbol转换为ts_code"""
    code = (code or "").strip().upper()
    if "." in code:
        return code

    symbol = normalize_symbol(code)
    if symbol.startswith(("6", "9", "5")):
        suffix = "SH"
    elif symbol.startswith(("4", "8")):
        suffix = "BJ"
    else:
        suffix = "SZ"
    return f"{symbol}.{suffix}"


def ts_to_symbol(ts_code: str) -> str:
    """ts_code转symbol"""
    return (ts_code or "").split(".")[0]


def latest_trade_date() -> str:
    """获取最近交易日"""
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
    cal = pro().trade_cal(exchange="", start_date=start_date, end_date=end_date, is_open="1")
    if cal is None or cal.empty:
        return end_date
    cal = cal.sort_values("cal_date")
    return str(cal.iloc[-1]["cal_date"])


def _format_date_ymd(date_str: str) -> str:
    """YYYYMMDD -> YYYY-MM-DD"""
    if not date_str or len(str(date_str)) != 8:
        return date_str
    s = str(date_str)
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


@retry_on_failure(max_retries=2, delay=1.0)
def get_stock_info(code: str) -> dict:
    """获取股票基本信息"""
    try:
        ts_code = to_ts_code(code)

        basic = pro().stock_basic(
            ts_code=ts_code,
            list_status="L",
            fields="ts_code,symbol,name,industry,list_date",
        )
        if basic is None or basic.empty:
            return {"code": normalize_symbol(code), "error": "未找到股票基础信息"}

        info = basic.iloc[0].to_dict()

        db = pro().daily_basic(
            ts_code=ts_code,
            fields="ts_code,trade_date,total_mv,circ_mv,total_share,float_share,pe_ttm,pb",
            limit=1,
        )
        latest_db = db.iloc[0].to_dict() if db is not None and not db.empty else {}

        return {
            "code": info.get("symbol", normalize_symbol(code)),
            "name": info.get("name", ""),
            "industry": info.get("industry", ""),
            "market_cap": safe_float(latest_db.get("total_mv")) * 10000 if latest_db.get("total_mv") is not None else None,
            "float_cap": safe_float(latest_db.get("circ_mv")) * 10000 if latest_db.get("circ_mv") is not None else None,
            "total_shares": safe_float(latest_db.get("total_share")) * 10000 if latest_db.get("total_share") is not None else None,
            "float_shares": safe_float(latest_db.get("float_share")) * 10000 if latest_db.get("float_share") is not None else None,
            "pe_ttm": safe_float(latest_db.get("pe_ttm")),
            "pb": safe_float(latest_db.get("pb")),
            "listing_date": _format_date_ymd(info.get("list_date", "")),
            "ts_code": ts_code,
        }
    except Exception as exc:
        return {"code": normalize_symbol(code), "error": str(exc)}


def _df_to_records(df: pd.DataFrame, max_records: int) -> list:
    if df is None or df.empty:
        return []
    if "end_date" in df.columns:
        df = df.sort_values("end_date", ascending=False)
    return df.head(max_records).to_dict(orient="records")


def _add_income_aliases(records: list) -> list:
    for row in records:
        row["净利润"] = row.get("n_income")
        row["营业收入"] = row.get("revenue")
        row["主营业务收入"] = row.get("total_revenue")
    return records


def _add_cashflow_aliases(records: list) -> list:
    for row in records:
        row["经营活动产生的现金流量净额"] = row.get("n_cashflow_act")
        row["购建固定资产、无形资产和其他长期资产支付的现金"] = row.get("c_pay_acq_const_fiolta")
    return records


def _add_balance_aliases(records: list) -> list:
    for row in records:
        row["总资产"] = row.get("total_assets")
        row["总负债"] = row.get("total_liab")
        assets = safe_float(row.get("total_assets"))
        liab = safe_float(row.get("total_liab"))
        row["资产负债率"] = (liab / assets * 100) if assets and liab is not None else None
    return records


@retry_on_failure(max_retries=2, delay=1.0)
def get_financial_data(code: str, years: int = 3) -> dict:
    """获取财务数据（资产负债表、利润表、现金流量表）"""
    max_records = min(years * 4, 12)
    ts_code = to_ts_code(code)

    result = {
        "balance_sheet": [],
        "income_statement": [],
        "cash_flow": [],
    }

    try:
        bs = pro().balancesheet(ts_code=ts_code, limit=max_records)
        result["balance_sheet"] = _add_balance_aliases(_df_to_records(bs, max_records))
    except Exception as exc:
        result["balance_sheet_error"] = str(exc)

    try:
        inc = pro().income(ts_code=ts_code, limit=max_records)
        result["income_statement"] = _add_income_aliases(_df_to_records(inc, max_records))
    except Exception as exc:
        result["income_statement_error"] = str(exc)

    try:
        cf = pro().cashflow(ts_code=ts_code, limit=max_records)
        result["cash_flow"] = _add_cashflow_aliases(_df_to_records(cf, max_records))
    except Exception as exc:
        result["cash_flow_error"] = str(exc)

    return result


def _map_indicator_row(row: Dict) -> Dict:
    """tushare指标映射为现有中文字段"""
    return {
        **row,
        "日期": row.get("end_date"),
        "净资产收益率": row.get("roe"),
        "加权净资产收益率": row.get("roe_waa"),
        "总资产报酬率": row.get("roa"),
        "销售毛利率": row.get("grossprofit_margin"),
        "销售净利率": row.get("netprofit_margin"),
        "资产负债率": row.get("debt_to_assets"),
        "流动比率": row.get("current_ratio"),
        "速动比率": row.get("quick_ratio"),
        "应收账款周转率": row.get("arturn"),
        "应收账款周转天数": row.get("ar_days"),
        "存货周转率": row.get("invturn"),
        "存货周转天数": row.get("inv_days"),
        "总资产周转率": row.get("assets_turn"),
        "营业收入增长率": row.get("tr_yoy"),
        "主营业务收入增长率": row.get("tr_yoy"),
        "净利润增长率": row.get("netprofit_yoy"),
        "应收账款增长率": row.get("recp_yoy"),
        "存货增长率": row.get("inv_yoy"),
        "权益乘数": row.get("assets_to_eqt"),
    }


def get_financial_indicators(code: str, limit: int = 8) -> list:
    """获取财务指标"""
    ts_code = to_ts_code(code)
    try:
        df = pro().fina_indicator(ts_code=ts_code, limit=limit)
        if df is None or df.empty:
            return []
        if "end_date" in df.columns:
            df = df.sort_values("end_date", ascending=False)
        records = df.head(limit).to_dict(orient="records")
        return [_map_indicator_row(r) for r in records]
    except Exception:
        return []


@retry_on_failure(max_retries=2, delay=1.0)
def get_performance_data(code: str, years: int = 3) -> dict:
    """获取业绩预告/快报/审计意见/主营构成。"""
    ts_code = to_ts_code(code)
    start_date = (datetime.now() - timedelta(days=365 * max(1, years))).strftime("%Y%m%d")
    end_date = datetime.now().strftime("%Y%m%d")

    result = {
        "forecast": [],
        "express": [],
        "audit": [],
        "main_business": {
            "by_product": [],
            "by_region": [],
        },
    }

    try:
        df = pro().forecast(ts_code=ts_code, start_date=start_date, end_date=end_date)
        if df is not None and not df.empty:
            df = df.sort_values("ann_date", ascending=False)
            result["forecast"] = df.head(12).to_dict(orient="records")
    except Exception as exc:
        result["forecast_error"] = str(exc)

    try:
        df = pro().express(ts_code=ts_code, start_date=start_date, end_date=end_date)
        if df is not None and not df.empty:
            df = df.sort_values("ann_date", ascending=False)
            result["express"] = df.head(8).to_dict(orient="records")
    except Exception as exc:
        result["express_error"] = str(exc)

    try:
        df = pro().fina_audit(ts_code=ts_code, start_date=start_date, end_date=end_date)
        if df is not None and not df.empty:
            df = df.sort_values("ann_date", ascending=False)
            result["audit"] = df.head(8).to_dict(orient="records")
    except Exception as exc:
        result["audit_error"] = str(exc)

    for biz_type, key in [("P", "by_product"), ("D", "by_region")]:
        try:
            df = pro().fina_mainbz(ts_code=ts_code, type=biz_type, start_date=start_date, end_date=end_date)
            if df is not None and not df.empty:
                # 仅保留最近一期构成并按收入排序
                latest_period = str(df["end_date"].max())
                latest_df = df[df["end_date"] == latest_period].copy()
                if "bz_sales" in latest_df.columns:
                    latest_df["bz_sales"] = pd.to_numeric(latest_df["bz_sales"], errors="coerce")
                    latest_df = latest_df.sort_values("bz_sales", ascending=False)
                result["main_business"][key] = latest_df.head(20).to_dict(orient="records")
        except Exception as exc:
            result[f"main_business_{key}_error"] = str(exc)

    return result


def get_valuation_data(code: str) -> dict:
    """获取估值数据"""
    ts_code = to_ts_code(code)
    result = {}

    try:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=3 * 365)).strftime("%Y%m%d")
        df = pro().daily_basic(
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
            fields="ts_code,trade_date,pe_ttm,pb",
        )

        if df is None or df.empty:
            return result

        df = df.sort_values("trade_date")
        latest = df.iloc[-1].to_dict()

        result["latest"] = {
            "date": latest.get("trade_date"),
            "pe_ttm": safe_float(latest.get("pe_ttm")),
            "pb": safe_float(latest.get("pb")),
        }
        result["history_count"] = len(df)

        pe = safe_float(latest.get("pe_ttm"))
        pb = safe_float(latest.get("pb"))

        if pe is not None:
            series = pd.to_numeric(df["pe_ttm"], errors="coerce").dropna()
            if not series.empty:
                result["pe_percentile"] = float((series <= pe).mean() * 100)

        if pb is not None:
            series = pd.to_numeric(df["pb"], errors="coerce").dropna()
            if not series.empty:
                result["pb_percentile"] = float((series <= pb).mean() * 100)

    except Exception as exc:
        result["error"] = str(exc)
        result["note"] = "估值历史数据获取失败，将使用基本信息中的估值"

    return result


@retry_on_failure(max_retries=2, delay=1.0)
def get_holder_data(code: str) -> dict:
    """获取股东信息"""
    ts_code = to_ts_code(code)
    result = {}

    try:
        top10 = pro().top10_holders(ts_code=ts_code)
        if top10 is not None and not top10.empty:
            top10 = top10.sort_values(["end_date", "hold_ratio"], ascending=[False, False])
            result["top_10_holders"] = top10.head(10).to_dict(orient="records")
    except Exception as exc:
        result["top_10_holders_error"] = str(exc)

    try:
        holders = pro().stk_holdernumber(ts_code=ts_code)
        if holders is not None and not holders.empty:
            holders = holders.sort_values("end_date", ascending=False)
            result["holder_count_history"] = holders.head(10).to_dict(orient="records")
    except Exception as exc:
        result["holder_count_error"] = str(exc)

    return result


@retry_on_failure(max_retries=2, delay=1.0)
def get_dividend_data(code: str) -> dict:
    """获取分红数据"""
    ts_code = to_ts_code(code)

    try:
        df = pro().dividend(ts_code=ts_code)
        if df is None or df.empty:
            return {"dividend_history": [], "dividend_count": 0}

        if "end_date" in df.columns:
            df = df.sort_values("end_date", ascending=False)

        records = df.to_dict(orient="records")
        for row in records:
            row["每股股利"] = row.get("cash_div_tax")
            row["派息"] = row.get("cash_div_tax")

        return {
            "dividend_history": records,
            "dividend_count": len(records),
        }
    except Exception:
        return {"dividend_history": [], "dividend_count": 0}


@retry_on_failure(max_retries=2, delay=1.0)
def get_price_data(code: str, days: int = 60) -> dict:
    """获取价格数据"""
    ts_code = to_ts_code(code)

    try:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=max(40, days * 3))).strftime("%Y%m%d")

        df = pro().daily(
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
            fields="ts_code,trade_date,open,high,low,close,pct_chg,vol,amount",
        )
        if df is None or df.empty:
            return {}

        df = df.sort_values("trade_date").tail(max(60, days))
        latest = df.iloc[-1]

        db_map = {}
        try:
            db = pro().daily_basic(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                fields="ts_code,trade_date,turnover_rate,volume_ratio",
            )
            if db is not None and not db.empty:
                db = db.sort_values("trade_date")
                db_map = {
                    str(row.get("trade_date")): {
                        "turnover_rate": safe_float(row.get("turnover_rate")),
                        "volume_ratio": safe_float(row.get("volume_ratio")),
                    }
                    for _, row in db.iterrows()
                }
        except Exception:
            db_map = {}

        price_data = []
        for _, row in df.tail(min(max(days, 60), 180)).iterrows():
            trade_date = str(row.get("trade_date"))
            ext = db_map.get(trade_date, {})
            price_data.append(
                {
                    "日期": trade_date,
                    "开盘": row.get("open"),
                    "最高": row.get("high"),
                    "最低": row.get("low"),
                    "收盘": row.get("close"),
                    "涨跌幅": row.get("pct_chg"),
                    "成交量": row.get("vol"),
                    "成交额": row.get("amount"),
                    "量比": ext.get("volume_ratio"),
                    "换手率": ext.get("turnover_rate"),
                }
            )

        tr_20 = [safe_float(x.get("换手率")) for x in price_data[-20:]]
        tr_20 = [x for x in tr_20 if x is not None]

        return {
            "latest_price": safe_float(latest.get("close")),
            "latest_date": str(latest.get("trade_date")),
            "price_change_pct": safe_float(latest.get("pct_chg")),
            "volume": safe_float(latest.get("vol")),
            "turnover": safe_float(latest.get("amount")),
            "high_60d": safe_float(df["high"].max()),
            "low_60d": safe_float(df["low"].min()),
            "avg_volume_20d": safe_float(df.tail(20)["vol"].mean()),
            "avg_amount_20d": safe_float(df.tail(20)["amount"].mean()),
            "avg_turnover_rate_20d": safe_float(sum(tr_20) / len(tr_20)) if tr_20 else None,
            "price_data": price_data,
        }
    except Exception as exc:
        return {"error": str(exc)}


@retry_on_failure(max_retries=2, delay=1.0)
def get_index_price_data(index_name: str, days: int = 60) -> dict:
    """获取基准指数价格数据（用于相对强弱）"""
    index_code = INDEX_CODE_MAP.get(index_name)
    if not index_code:
        return {"error": f"不支持的benchmark: {index_name}"}

    try:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=max(40, days * 3))).strftime("%Y%m%d")
        df = pro().index_daily(
            ts_code=index_code,
            start_date=start_date,
            end_date=end_date,
            fields="ts_code,trade_date,open,high,low,close,pct_chg,vol,amount",
        )
        if df is None or df.empty:
            return {}

        df = df.sort_values("trade_date").tail(max(60, days))
        latest = df.iloc[-1]

        rows = []
        for _, row in df.tail(min(max(days, 60), 180)).iterrows():
            rows.append(
                {
                    "日期": str(row.get("trade_date")),
                    "开盘": row.get("open"),
                    "最高": row.get("high"),
                    "最低": row.get("low"),
                    "收盘": row.get("close"),
                    "涨跌幅": row.get("pct_chg"),
                    "成交量": row.get("vol"),
                    "成交额": row.get("amount"),
                }
            )

        return {
            "benchmark": index_name,
            "benchmark_ts_code": index_code,
            "latest_price": safe_float(latest.get("close")),
            "latest_date": str(latest.get("trade_date")),
            "price_change_pct": safe_float(latest.get("pct_chg")),
            "price_data": rows,
        }
    except Exception as exc:
        return {"error": str(exc)}


def get_flow_metrics(code: str, days: int = 20) -> dict:
    """获取资金流指标（大单净流入及连续性）。"""
    ts_code = to_ts_code(code)
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=max(20, days * 3))).strftime("%Y%m%d")

    try:
        df = pro().moneyflow(ts_code=ts_code, start_date=start_date, end_date=end_date)
        if df is None or df.empty:
            return {}

        df = df.sort_values("trade_date").tail(max(5, days))
        net_values = []
        for _, row in df.iterrows():
            buy_lg = safe_float(row.get("buy_lg_amount")) or 0.0
            buy_elg = safe_float(row.get("buy_elg_amount")) or 0.0
            sell_lg = safe_float(row.get("sell_lg_amount")) or 0.0
            sell_elg = safe_float(row.get("sell_elg_amount")) or 0.0
            net = buy_lg + buy_elg - sell_lg - sell_elg
            net_values.append(net)

        latest_row = df.iloc[-1]
        latest_net = net_values[-1] if net_values else 0.0
        latest_amount = safe_float(latest_row.get("amount"))
        net_ratio = (latest_net / latest_amount * 100.0) if latest_amount not in [None, 0] else None
        tail_5 = net_values[-5:] if len(net_values) >= 5 else net_values
        positive_days_5 = len([x for x in tail_5 if x > 0])

        return {
            "latest_trade_date": str(latest_row.get("trade_date")),
            "latest_net_inflow": round(latest_net, 4),
            "net_inflow_ratio": round(net_ratio, 4) if net_ratio is not None else None,
            "positive_days_5": positive_days_5,
        }
    except Exception as exc:
        return {"error": str(exc)}


def get_chip_events(code: str, basic_info: Optional[dict] = None) -> dict:
    """获取筹码供给侧事件（解禁/减持/回购）。"""
    ts_code = to_ts_code(code)
    basic_info = basic_info or {}
    float_shares = safe_float(basic_info.get("float_shares"))
    total_shares = safe_float(basic_info.get("total_shares"))

    end_date = datetime.now().strftime("%Y%m%d")
    start_30 = (datetime.now() + timedelta(days=30)).strftime("%Y%m%d")
    start_90 = (datetime.now() + timedelta(days=90)).strftime("%Y%m%d")
    back_30 = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
    back_90 = (datetime.now() - timedelta(days=90)).strftime("%Y%m%d")

    result = {
        "unlock_30d_ratio": 0.0,
        "unlock_90d_ratio": 0.0,
        "reduction_density_30d": 0.0,
        "repurchase_ratio_90d": 0.0,
    }

    try:
        df = pro().share_float(ts_code=ts_code)
        if df is not None and not df.empty:
            df = df.sort_values("float_date")
            df30 = df[(df["float_date"] <= start_30) & (df["float_date"] >= end_date)]
            df90 = df[(df["float_date"] <= start_90) & (df["float_date"] >= end_date)]
            col = "float_share" if "float_share" in df.columns else None
            if col:
                unlock_30 = safe_float(pd.to_numeric(df30[col], errors="coerce").sum(), 0.0) or 0.0
                unlock_90 = safe_float(pd.to_numeric(df90[col], errors="coerce").sum(), 0.0) or 0.0
                if float_shares and float_shares > 0:
                    # share_float 通常单位为万股，这里统一换算为股
                    result["unlock_30d_ratio"] = round(unlock_30 * 10000 / float_shares * 100.0, 4)
                    result["unlock_90d_ratio"] = round(unlock_90 * 10000 / float_shares * 100.0, 4)
    except Exception as exc:
        result["unlock_error"] = str(exc)

    try:
        df = pro().stk_holdertrade(ts_code=ts_code, start_date=back_30, end_date=end_date)
        if df is not None and not df.empty:
            de_col = "in_de" if "in_de" in df.columns else None
            if de_col:
                de_count = len(df[df[de_col] == "DE"])
                result["reduction_density_30d"] = round(de_count / 30.0, 4)
            else:
                result["reduction_density_30d"] = round(len(df) / 30.0, 4)
    except Exception as exc:
        result["reduction_error"] = str(exc)

    try:
        df = pro().repurchase(ts_code=ts_code)
        if df is not None and not df.empty:
            date_col = "ann_date" if "ann_date" in df.columns else None
            if date_col:
                recent = df[df[date_col] >= back_90]
            else:
                recent = df

            rep_ratio = 0.0
            if total_shares and total_shares > 0 and "vol" in recent.columns:
                vol = pd.to_numeric(recent["vol"], errors="coerce").fillna(0).sum()
                rep_ratio = float(vol) * 10000 / total_shares * 100.0
            else:
                rep_ratio = len(recent) * 0.3
            result["repurchase_ratio_90d"] = round(rep_ratio, 4)
    except Exception as exc:
        result["repurchase_error"] = str(exc)

    return result


@retry_on_failure(max_retries=2, delay=1.0)
def get_index_constituents(index_name: str) -> list:
    """获取指数成分股"""
    index_code = INDEX_CODE_MAP.get(index_name)
    if not index_code:
        return []

    try:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=90)).strftime("%Y%m%d")
        df = pro().index_weight(index_code=index_code, start_date=start_date, end_date=end_date)
        if df is None or df.empty:
            return []

        latest = str(df["trade_date"].max())
        latest_df = df[df["trade_date"] == latest]
        if latest_df.empty:
            latest_df = df

        codes = latest_df["con_code"].dropna().unique().tolist()
        return [ts_to_symbol(c) for c in codes]
    except Exception as exc:
        print(f"获取指数成分股失败: {exc}")
        return []


def get_all_a_stocks() -> list:
    """获取全部A股代码"""
    try:
        df = pro().stock_basic(exchange="", list_status="L", fields="symbol")
        if df is not None and not df.empty:
            return df["symbol"].dropna().unique().tolist()
        return []
    except Exception as exc:
        print(f"获取全部A股失败: {exc}")
        return []


def fetch_stock_data(
    code: str,
    data_type: str = "all",
    years: int = 3,
    use_cache: bool = True,
    with_realtime: bool = False,
    with_event_window: bool = False,
    benchmark: str = "hs300",
    realtime_window: int = 60,
    event_window_pre: int = 1,
    event_window_post: Sequence[int] = (1, 3, 5),
    cache_ttl_min: int = 1440,
) -> dict:
    """获取单只股票的数据"""
    code = normalize_symbol(code)
    cache_key = data_type
    if with_realtime:
        cache_key += f"_rt_{benchmark}_{max(20, realtime_window)}"
    if with_event_window:
        post_key = "-".join(str(int(x)) for x in sorted(set(event_window_post)) if int(x) >= 1) or "1-3-5"
        cache_key += f"_ew_{benchmark}_p{max(0, int(event_window_pre))}_w{post_key}"

    if use_cache:
        cached = load_cache(code, cache_key, ttl_minutes=cache_ttl_min)
        if cached:
            log(f"使用缓存数据: {code}")
            return cached

    result = {
        "code": code,
        "fetch_time": datetime.now().isoformat(),
        "data_type": data_type,
    }

    log(f"正在获取 {code} 的数据...")

    if data_type in ["all", "basic", "news"]:
        log("  - 获取基本信息...")
        result["basic_info"] = get_stock_info(code)

    if data_type in ["all", "financial"]:
        log("  - 获取财务数据...")
        result["financial_data"] = get_financial_data(code, years)
        log("  - 获取财务指标...")
        result["financial_indicators"] = get_financial_indicators(code)
        log("  - 获取业绩与审计数据...")
        result["performance_data"] = get_performance_data(code, years)

    if data_type in ["all", "valuation"]:
        log("  - 获取估值数据...")
        result["valuation"] = get_valuation_data(code)
        log("  - 获取价格数据...")
        result["price"] = get_price_data(code, days=max(60, realtime_window))

    if with_realtime:
        if "basic_info" not in result:
            log("  - 获取基本信息（实时模块依赖）...")
            result["basic_info"] = get_stock_info(code)
        if "price" not in result:
            log("  - 获取价格数据（实时模块依赖）...")
            result["price"] = get_price_data(code, days=max(60, realtime_window))

        log("  - 获取资金流指标...")
        result["flow_metrics"] = get_flow_metrics(code, days=20)
        log("  - 获取筹码事件...")
        result["chip_events"] = get_chip_events(code, basic_info=result.get("basic_info", {}))
        log(f"  - 计算实时指标（benchmark={benchmark}）...")
        benchmark_price = get_index_price_data(benchmark, days=max(60, realtime_window))
        result["realtime_metrics"] = calculate_realtime_metrics(
            price=result.get("price", {}),
            benchmark_price=benchmark_price,
            flow_metrics=result.get("flow_metrics", {}),
            chip_events=result.get("chip_events", {}),
            window=max(20, realtime_window),
        )
        result["realtime_metrics"]["benchmark"] = benchmark
        if isinstance(benchmark_price, dict) and benchmark_price.get("error"):
            result["realtime_metrics"]["benchmark_error"] = benchmark_price.get("error")

    if with_event_window:
        log(f"  - 计算事件窗口（benchmark={benchmark}）...")
        result = attach_event_window(
            result,
            benchmark=benchmark,
            pre_days=event_window_pre,
            post_days=event_window_post,
        )

    if data_type in ["all", "holder"]:
        log("  - 获取股东数据...")
        result["holder"] = get_holder_data(code)
        log("  - 获取分红数据...")
        result["dividend"] = get_dividend_data(code)

    if use_cache:
        save_cache(code, cache_key, result)

    log(f"数据获取完成: {code}")
    return result


def fetch_multiple_stocks(
    codes: list,
    data_type: str = "basic",
    with_realtime: bool = False,
    with_event_window: bool = False,
    benchmark: str = "hs300",
    realtime_window: int = 60,
    event_window_pre: int = 1,
    event_window_post: Sequence[int] = (1, 3, 5),
    cache_ttl_min: int = 1440,
) -> dict:
    """获取多只股票数据"""
    result = {
        "fetch_time": datetime.now().isoformat(),
        "stocks": [],
        "success_count": 0,
        "fail_count": 0,
    }

    total = len(codes)
    for i, code in enumerate(codes):
        code = normalize_symbol(code)
        log(f"[{i + 1}/{total}] 获取 {code}...")
        try:
            stock_data = fetch_stock_data(
                code,
                data_type,
                use_cache=True,
                with_realtime=with_realtime,
                with_event_window=with_event_window,
                benchmark=benchmark,
                realtime_window=realtime_window,
                event_window_pre=event_window_pre,
                event_window_post=event_window_post,
                cache_ttl_min=cache_ttl_min,
            )
            if "error" not in stock_data.get("basic_info", {}):
                result["stocks"].append(stock_data)
                result["success_count"] += 1
            else:
                result["fail_count"] += 1
        except Exception as exc:
            log(f"  获取失败: {exc}")
            result["fail_count"] += 1

        if i < total - 1:
            time.sleep(0.2)

    return result


def attach_news_data(
    result: dict,
    days: int = 7,
    limit: int = 20,
    news_sources: str = "",
    news_provider: str = "auto",
    brave_api_key: str = "",
    tushare_token: str = "",
) -> dict:
    """为结果补充新闻与舆情数据。"""
    code = result.get("code", "")
    basic = result.get("basic_info", {})
    name = basic.get("name", "")

    try:
        items = fetch_news(
            code=code,
            name=name,
            days=days,
            limit=limit,
            provider=news_provider,
            brave_api_key=brave_api_key,
            tushare_token=tushare_token,
        )
        if news_sources:
            allow_sources = {x.strip().lower() for x in news_sources.split(",") if x.strip()}
            if allow_sources:
                items = [x for x in items if x.get("source", "").lower() in allow_sources]

        sentiment = analyze_news_sentiment(items)
        result["news_items"] = items
        result["news_sentiment"] = {
            "analysis_time": sentiment.get("analysis_time"),
            "news_count": sentiment.get("news_count"),
            "overall_sentiment": sentiment.get("overall_sentiment"),
            "risk_level": sentiment.get("risk_level"),
            "risk_tag_count": sentiment.get("risk_tag_count"),
            "top_negative_events": sentiment.get("top_negative_events"),
        }
    except Exception as exc:
        result["news_items"] = []
        result["news_sentiment"] = {
            "analysis_time": datetime.now().isoformat(),
            "news_count": 0,
            "overall_sentiment": 0.0,
            "risk_level": "低",
            "risk_tag_count": {},
            "top_negative_events": [],
            "error": str(exc),
        }
    return result


def attach_event_window(
    result: dict,
    benchmark: str = "hs300",
    pre_days: int = 1,
    post_days: Sequence[int] = (1, 3, 5),
    max_events: int = 40,
) -> dict:
    """为结果补充事件窗口分析。"""
    if not isinstance(result, dict):
        return result

    code = result.get("code", "")
    if "price" not in result or not result.get("price"):
        if code:
            log("  - 获取价格数据（事件窗口依赖）...")
            result["price"] = get_price_data(code, days=max(90, max(post_days, default=5) * 12))

    benchmark_price = get_index_price_data(benchmark, days=max(90, max(post_days, default=5) * 12))
    candidates = collect_event_candidates(result, max_events=max_events * 2)
    ew = calculate_event_window(
        price=result.get("price", {}),
        events=candidates,
        benchmark_price=benchmark_price,
        pre_days=pre_days,
        post_days=post_days,
        max_events=max_events,
    )
    ew["benchmark"] = benchmark
    ew["event_sources"] = ["news_items", "performance_data.forecast", "performance_data.express", "performance_data.audit"]
    if isinstance(benchmark_price, dict) and benchmark_price.get("error"):
        ew["benchmark_error"] = benchmark_price.get("error")
    result["event_window"] = ew
    return result


def summarize_table(result: dict) -> str:
    basic = result.get("basic_info", {})
    price = result.get("price", {})
    valuation = result.get("valuation", {})
    sentiment = result.get("news_sentiment", {})
    realtime = result.get("realtime_metrics", {})
    event_window = result.get("event_window", {})
    headers = ["代码", "名称", "行业", "最新价", "PE_TTM", "PB", "实时分", "事件窗分", "舆情", "数据类型"]
    rows = [[
        result.get("code", ""),
        basic.get("name", ""),
        basic.get("industry", ""),
        price.get("latest_price", ""),
        basic.get("pe_ttm", valuation.get("latest", {}).get("pe_ttm", "")),
        basic.get("pb", valuation.get("latest", {}).get("pb", "")),
        realtime.get("realtime_score", "-"),
        event_window.get("event_window_score", "-"),
        sentiment.get("risk_level", "-"),
        result.get("data_type", ""),
    ]]
    return format_table(headers, rows)


def main():
    default_years = int(os.getenv("STOCK_ANALYSIS_DEFAULT_YEARS", "3"))
    default_news_days = int(os.getenv("STOCK_ANALYSIS_DEFAULT_NEWS_DAYS", "7"))
    default_news_limit = int(os.getenv("STOCK_ANALYSIS_DEFAULT_NEWS_LIMIT", "20"))
    default_news_provider = os.getenv("STOCK_ANALYSIS_NEWS_PROVIDER", "auto")
    default_cache_ttl = int(os.getenv("STOCK_ANALYSIS_CACHE_TTL_MIN", "1440"))
    parser = argparse.ArgumentParser(description="A股数据获取工具")
    parser.add_argument("--code", type=str, help="股票代码 (如: 600519)")
    parser.add_argument("--codes", type=str, help="多个股票代码，逗号分隔 (如: 600519,000858)")
    parser.add_argument(
        "--data-type",
        type=str,
        default="basic",
        choices=["all", "basic", "financial", "valuation", "holder", "news"],
        help="数据类型 (默认: basic)",
    )
    parser.add_argument("--years", type=int, default=default_years, help=f"获取多少年的历史数据 (默认: {default_years})")
    parser.add_argument("--scope", type=str, help="筛选范围: hs300/zz500/cyb/kcb/all")
    parser.add_argument("--no-cache", action="store_true", help="不使用缓存")
    parser.add_argument("--token", type=str, required=True, help="tushare token（必填）")
    parser.add_argument("--with-news", action="store_true", help="附加最近新闻与舆情")
    parser.add_argument("--news-days", type=int, default=default_news_days, help=f"新闻窗口天数 (默认: {default_news_days})")
    parser.add_argument("--news-limit", type=int, default=default_news_limit, help=f"新闻最大条数 (默认: {default_news_limit})")
    parser.add_argument("--news-sources", type=str, default="", help="新闻来源过滤，逗号分隔")
    parser.add_argument("--news-provider", choices=["auto", "brave", "tushare", "rss"], default=default_news_provider, help=f"新闻源 (默认: {default_news_provider})")
    parser.add_argument("--brave-api-key", type=str, default="", help="Brave Search API Key（news-provider=brave 时必填）")
    parser.add_argument("--with-realtime", action="store_true", help="附加实时指标（趋势/确认/风险/筹码）")
    parser.add_argument("--with-event-window", action="store_true", help="附加事件窗口分析（事件后1/3/5日反应）")
    parser.add_argument("--benchmark", type=str, default="hs300", choices=["hs300", "zz500", "zz1000", "cyb", "kcb"], help="相对强弱基准指数")
    parser.add_argument("--realtime-window", type=int, default=60, help="实时指标窗口（日）")
    parser.add_argument("--event-window-pre", type=int, default=1, help="事件窗口前置天数（默认: 1）")
    parser.add_argument("--event-window-post", type=str, default="1,3,5", help="事件窗口后验天数，逗号分隔（默认: 1,3,5）")
    parser.add_argument("--cache-ttl-min", type=int, default=default_cache_ttl, help=f"缓存TTL分钟数 (默认: {default_cache_ttl})")
    parser.add_argument("--format", choices=["json", "table"], default="json", help="输出格式")
    parser.add_argument("--quiet", action="store_true", help="静默模式，仅输出结果")
    parser.add_argument("--output", type=str, help="输出文件路径 (JSON)")

    args = parser.parse_args()
    if not str(args.token or "").strip():
        parser.error("--token 不能为空（请确认 TUSHARE_TOKEN 已正确导出，或直接传入明文）")
    global CLI_TOKEN, VERBOSE
    CLI_TOKEN = args.token
    VERBOSE = not args.quiet
    event_window_post = parse_event_window_post_days(args.event_window_post)

    result = {}

    if args.code:
        result = fetch_stock_data(
            args.code,
            args.data_type,
            args.years,
            use_cache=not args.no_cache,
            with_realtime=args.with_realtime,
            with_event_window=args.with_event_window,
            benchmark=args.benchmark,
            realtime_window=args.realtime_window,
            event_window_pre=args.event_window_pre,
            event_window_post=event_window_post,
            cache_ttl_min=args.cache_ttl_min,
        )
        if args.data_type in ["all", "news"] or args.with_news:
            log("  - 获取新闻与舆情...")
            result = attach_news_data(
                result,
                days=args.news_days,
                limit=args.news_limit,
                news_sources=args.news_sources,
                news_provider=args.news_provider,
                brave_api_key=args.brave_api_key,
                tushare_token=args.token,
            )
            if args.with_event_window:
                log("  - 事件窗口重算（纳入新闻事件）...")
                result = attach_event_window(
                    result,
                    benchmark=args.benchmark,
                    pre_days=args.event_window_pre,
                    post_days=event_window_post,
                )
    elif args.codes:
        codes = [c.strip() for c in args.codes.split(",") if c.strip()]
        result = fetch_multiple_stocks(
            codes,
            args.data_type,
            with_realtime=args.with_realtime,
            with_event_window=args.with_event_window,
            benchmark=args.benchmark,
            realtime_window=args.realtime_window,
            event_window_pre=args.event_window_pre,
            event_window_post=event_window_post,
            cache_ttl_min=args.cache_ttl_min,
        )
        if args.with_news:
            for item in result.get("stocks", []):
                attach_news_data(
                    item,
                    days=args.news_days,
                    limit=args.news_limit,
                    news_sources=args.news_sources,
                    news_provider=args.news_provider,
                    brave_api_key=args.brave_api_key,
                    tushare_token=args.token,
                )
                if args.with_event_window:
                    attach_event_window(
                        item,
                        benchmark=args.benchmark,
                        pre_days=args.event_window_pre,
                        post_days=event_window_post,
                    )
    elif args.scope:
        if args.scope == "all":
            codes = get_all_a_stocks()
        else:
            codes = get_index_constituents(args.scope)
        result = {"scope": args.scope, "stocks": codes, "count": len(codes)}
    else:
        print("请提供 --code, --codes 或 --scope 参数")
        sys.exit(1)

    output = json.dumps(result, ensure_ascii=False, indent=2, default=str)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        log(f"\n数据已保存到: {args.output}")
    else:
        if args.format == "table":
            if args.scope and "stocks" in result:
                rows = [[result.get("scope", ""), result.get("count", 0)]]
                print(format_table(["范围", "股票数量"], rows))
            elif args.codes and "stocks" in result:
                rows = [[s.get("code", ""), s.get("basic_info", {}).get("name", "")] for s in result["stocks"]]
                print(format_table(["代码", "名称"], rows))
            else:
                print(summarize_table(result))
        else:
            print(output)


if __name__ == "__main__":
    main()
