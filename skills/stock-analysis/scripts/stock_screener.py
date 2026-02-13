#!/usr/bin/env python3
"""
A股股票筛选器
根据多种财务指标筛选符合条件的股票

依赖: pip install tushare pandas numpy
环境变量: TUSHARE_TOKEN=你的token
"""

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from functools import wraps
from typing import Dict, List
from env_loader import get_tushare_token

try:
    import numpy as np
    import pandas as pd
    import tushare as ts
except ImportError:
    print("错误: 请先安装依赖库")
    print("pip install tushare pandas numpy")
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

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    last_error = exc
                    if attempt < max_retries - 1:
                        if args and hasattr(args[0], "log"):
                            args[0].log(f"  重试 ({attempt + 1}/{max_retries})...")
                        else:
                            print(f"  重试 ({attempt + 1}/{max_retries})...")
                        time.sleep(delay * (attempt + 1))
            raise last_error

        return wrapper

    return decorator


def normalize_symbol(code: str) -> str:
    code = (code or "").strip().upper()
    if "." in code:
        return code.split(".")[0]
    return code


def to_ts_code(code: str) -> str:
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
    return (ts_code or "").split(".")[0]


class StockScreener:
    """股票筛选器"""

    def __init__(self, token: str = None, quiet: bool = False):
        self.quiet = quiet
        token = token or get_tushare_token()
        if not token:
            print("错误: 未检测到 TUSHARE_TOKEN 环境变量")
            print("请设置环境变量，或在 ~/.aj-skills/.env 中配置 TUSHARE_TOKEN")
            sys.exit(1)

        ts.set_token(token)
        self.pro = ts.pro_api()
        self.all_stocks_data = None

    def log(self, message: str):
        if not self.quiet:
            print(message)

    @retry_on_failure(max_retries=3, delay=2.0)
    def _latest_trade_date(self) -> str:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
        cal = self.pro.trade_cal(exchange="", start_date=start_date, end_date=end_date, is_open="1")
        if cal is None or cal.empty:
            return end_date
        return str(cal.sort_values("cal_date").iloc[-1]["cal_date"])

    @retry_on_failure(max_retries=3, delay=2.0)
    def _get_all_stock_basic(self) -> pd.DataFrame:
        return self.pro.stock_basic(
            exchange="",
            list_status="L",
            fields="ts_code,symbol,name,industry,list_date",
        )

    @retry_on_failure(max_retries=3, delay=2.0)
    def _get_index_constituents(self, index_code: str) -> List[str]:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=90)).strftime("%Y%m%d")
        df = self.pro.index_weight(index_code=index_code, start_date=start_date, end_date=end_date)
        if df is None or df.empty:
            return []
        latest = str(df["trade_date"].max())
        return df[df["trade_date"] == latest]["con_code"].dropna().unique().tolist()

    @retry_on_failure(max_retries=3, delay=2.0)
    def _get_daily_snapshot(self, trade_date: str) -> pd.DataFrame:
        return self.pro.daily(
            trade_date=trade_date,
            fields="ts_code,trade_date,close,pct_chg,vol,amount",
        )

    @retry_on_failure(max_retries=3, delay=2.0)
    def _get_daily_basic_snapshot(self, trade_date: str) -> pd.DataFrame:
        return self.pro.daily_basic(
            trade_date=trade_date,
            fields="ts_code,trade_date,pe_ttm,pb,total_mv,circ_mv,dv_ttm",
        )

    def _collect_scope_ts_codes(self, scope: str = "hs300", custom_codes: List[str] = None) -> List[str]:
        if scope == "all":
            basic = self._get_all_stock_basic()
            return basic["ts_code"].dropna().unique().tolist() if not basic.empty else []

        if scope in INDEX_CODE_MAP:
            return self._get_index_constituents(INDEX_CODE_MAP[scope])

        if scope.startswith("custom:") or custom_codes:
            codes = custom_codes or scope.replace("custom:", "").split(",")
            return [to_ts_code(c.strip()) for c in codes if c.strip()]

        basic = self._get_all_stock_basic()
        return basic["ts_code"].dropna().unique().tolist() if not basic.empty else []

    def _fetch_latest_indicators(self, ts_codes: List[str]) -> pd.DataFrame:
        """按需获取ROE/资产负债率（接口不支持批量，逐只拉取）"""
        rows = []
        total = len(ts_codes)
        for i, ts_code in enumerate(ts_codes):
            try:
                if total > 0 and (i + 1) % 50 == 0:
                    self.log(f"  财务指标进度: {i + 1}/{total}")
                df = self.pro.fina_indicator(ts_code=ts_code, limit=1, fields="ts_code,end_date,roe,debt_to_assets")
                if df is not None and not df.empty:
                    rows.append(df.iloc[0].to_dict())
                time.sleep(0.01)
            except Exception:
                continue
        return pd.DataFrame(rows)

    def load_stock_data(self, scope: str = "hs300", custom_codes: List[str] = None, need_financial: bool = False) -> pd.DataFrame:
        """加载股票数据"""
        self.log(f"正在加载股票数据 (范围: {scope})...")

        try:
            trade_date = self._latest_trade_date()
            target_ts_codes = self._collect_scope_ts_codes(scope, custom_codes)
            if not target_ts_codes:
                return pd.DataFrame()

            self.log(f"  目标股票数量: {len(target_ts_codes)}")
            self.log(f"  使用交易日: {trade_date}")

            basic = self._get_all_stock_basic()
            daily = self._get_daily_snapshot(trade_date)
            daily_basic = self._get_daily_basic_snapshot(trade_date)

            if basic is None or basic.empty or daily is None or daily.empty or daily_basic is None or daily_basic.empty:
                return pd.DataFrame()

            df = basic.merge(daily, on="ts_code", how="inner").merge(daily_basic, on=["ts_code", "trade_date"], how="left")
            df = df[df["ts_code"].isin(target_ts_codes)].copy()

            if need_financial and not df.empty:
                self.log("  获取财务指标(ROE/资产负债率)...")
                indicators = self._fetch_latest_indicators(df["ts_code"].tolist())
                if not indicators.empty:
                    df = df.merge(indicators[["ts_code", "roe", "debt_to_assets"]], on="ts_code", how="left")

            df["代码"] = df["symbol"].apply(normalize_symbol)
            df["名称"] = df["name"]
            df["最新价"] = pd.to_numeric(df["close"], errors="coerce")
            df["涨跌幅"] = pd.to_numeric(df["pct_chg"], errors="coerce")
            df["市盈率-动态"] = pd.to_numeric(df["pe_ttm"], errors="coerce")
            df["市净率"] = pd.to_numeric(df["pb"], errors="coerce")
            df["总市值"] = pd.to_numeric(df["total_mv"], errors="coerce") * 10000
            if "roe" in df.columns:
                df["净资产收益率"] = pd.to_numeric(df["roe"], errors="coerce")
            if "debt_to_assets" in df.columns:
                df["资产负债率"] = pd.to_numeric(df["debt_to_assets"], errors="coerce")

            self.all_stocks_data = df
            self.log(f"已加载 {len(df)} 只股票数据")
            return df

        except Exception as exc:
            self.log(f"加载数据失败: {exc}")
            return pd.DataFrame()

    def _apply_numeric_filter(self, df: pd.DataFrame, column: str, min_val: float = None, max_val: float = None) -> pd.DataFrame:
        """应用数值筛选条件"""
        if column not in df.columns:
            return df

        numeric_col = pd.to_numeric(df[column], errors="coerce")
        if min_val is not None:
            df = df[numeric_col >= min_val]
        if max_val is not None:
            df = df[numeric_col <= max_val]
        return df

    def _find_column(self, columns: List[str], candidates: List[str]) -> str:
        for col in candidates:
            if col in columns:
                return col
        return None

    def apply_filters(self, df: pd.DataFrame, filters: Dict) -> pd.DataFrame:
        """应用筛选条件"""
        filtered = df.copy()

        filtered = self._apply_numeric_filter(filtered, "市盈率-动态", min_val=filters.get("pe_min"), max_val=filters.get("pe_max"))
        filtered = self._apply_numeric_filter(filtered, "市净率", min_val=filters.get("pb_min"), max_val=filters.get("pb_max"))

        if filters.get("roe_min") is not None:
            roe_col = self._find_column(filtered.columns.tolist(), ["净资产收益率", "ROE", "加权净资产收益率"])
            if roe_col:
                filtered = self._apply_numeric_filter(filtered, roe_col, min_val=filters["roe_min"])

        filtered = self._apply_numeric_filter(filtered, "资产负债率", max_val=filters.get("debt_ratio_max"))

        if "总市值" in filtered.columns:
            if filters.get("market_cap_min") is not None or filters.get("market_cap_max") is not None:
                filtered["总市值_亿"] = pd.to_numeric(filtered["总市值"], errors="coerce") / 1e8
                filtered = self._apply_numeric_filter(
                    filtered,
                    "总市值_亿",
                    min_val=filters.get("market_cap_min"),
                    max_val=filters.get("market_cap_max"),
                )

        return filtered

    def _get_numeric_value(self, row: pd.Series, column: str) -> float:
        return pd.to_numeric(row.get(column, np.nan), errors="coerce")

    def calculate_score(self, row: pd.Series) -> float:
        """计算综合评分 (0-100)"""
        score = 50

        try:
            pe = self._get_numeric_value(row, "市盈率-动态")
            if not np.isnan(pe) and pe > 0:
                if pe < 10:
                    score += 15
                elif pe < 15:
                    score += 10
                elif pe < 20:
                    score += 5
                elif pe > 50:
                    score -= 10

            pb = self._get_numeric_value(row, "市净率")
            if not np.isnan(pb) and pb > 0:
                if 0.5 < pb < 1.5:
                    score += 10
                elif 1.5 <= pb < 3:
                    score += 5
                elif pb > 5:
                    score -= 5

            roe_col = self._find_column(list(row.index), ["净资产收益率", "ROE", "加权净资产收益率"])
            if roe_col:
                roe = self._get_numeric_value(row, roe_col)
                if not np.isnan(roe):
                    if roe > 20:
                        score += 15
                    elif roe > 15:
                        score += 10
                    elif roe > 10:
                        score += 5
                    elif roe < 5:
                        score -= 5

            change = self._get_numeric_value(row, "涨跌幅")
            if not np.isnan(change):
                if -5 < change < 0:
                    score += 3
                elif change < -5:
                    score += 5

        except Exception:
            pass

        return max(0, min(100, score))

    def screen(self, scope: str = "hs300", filters: Dict = None, sort_by: str = "score", top_n: int = None) -> List[Dict]:
        """执行筛选"""
        need_financial = bool(filters and (filters.get("roe_min") is not None or filters.get("debt_ratio_max") is not None))

        if scope.startswith("custom:"):
            codes = scope.replace("custom:", "").split(",")
            df = self.load_stock_data(scope="custom", custom_codes=codes, need_financial=need_financial)
        else:
            df = self.load_stock_data(scope=scope, need_financial=need_financial)

        if df.empty:
            return []

        if filters:
            df = self.apply_filters(df, filters)

        if df.empty:
            return []

        df["评分"] = df.apply(self.calculate_score, axis=1)

        if sort_by == "score":
            df = df.sort_values("评分", ascending=False)
        elif sort_by == "pe" and "市盈率-动态" in df.columns:
            df = df.sort_values("市盈率-动态", ascending=True)
        elif sort_by == "pb" and "市净率" in df.columns:
            df = df.sort_values("市净率", ascending=True)
        elif sort_by == "market_cap" and "总市值" in df.columns:
            df = df.sort_values("总市值", ascending=False)

        if top_n:
            df = df.head(top_n)

        results = []
        for _, row in df.iterrows():
            result = {
                "代码": row.get("代码", ""),
                "名称": row.get("名称", ""),
                "最新价": row.get("最新价", ""),
                "涨跌幅": row.get("涨跌幅", ""),
                "市盈率": row.get("市盈率-动态", ""),
                "市净率": row.get("市净率", ""),
                "总市值(亿)": round(float(row.get("总市值", 0)) / 100000000, 2) if row.get("总市值") else "",
                "评分": row.get("评分", 50),
            }
            results.append(result)

        return results


def main():
    def format_table(headers, rows):
        widths = [len(str(h)) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                widths[i] = max(widths[i], len(str(cell)))
        sep = "-+-".join("-" * w for w in widths)
        lines = [" | ".join(str(h).ljust(widths[i]) for i, h in enumerate(headers)), sep]
        for row in rows:
            lines.append(" | ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)))
        return "\n".join(lines)

    parser = argparse.ArgumentParser(description="A股股票筛选器")
    parser.add_argument("--scope", type=str, default="hs300", help="筛选范围: all/hs300/zz500/zz1000/cyb/kcb/custom:代码1,代码2")
    parser.add_argument("--pe-max", type=float, help="最大PE")
    parser.add_argument("--pe-min", type=float, help="最小PE")
    parser.add_argument("--pb-max", type=float, help="最大PB")
    parser.add_argument("--pb-min", type=float, help="最小PB")
    parser.add_argument("--roe-min", type=float, help="最小ROE (%)")
    parser.add_argument("--debt-ratio-max", type=float, help="最大资产负债率 (%)")
    parser.add_argument("--dividend-min", type=float, help="最小股息率 (%)")
    parser.add_argument("--market-cap-min", type=float, help="最小市值 (亿)")
    parser.add_argument("--market-cap-max", type=float, help="最大市值 (亿)")
    parser.add_argument("--sort-by", type=str, default="score", choices=["score", "pe", "pb", "market_cap"], help="排序方式")
    parser.add_argument("--top", type=int, default=50, help="返回前N只股票")
    parser.add_argument("--token", type=str, help="tushare token，优先于环境变量")
    parser.add_argument("--format", choices=["json", "table"], default="json", help="输出格式")
    parser.add_argument("--quiet", action="store_true", help="静默模式")
    parser.add_argument("--output", type=str, help="输出文件路径 (JSON)")

    args = parser.parse_args()

    filter_keys = [
        "pe_max",
        "pe_min",
        "pb_max",
        "pb_min",
        "roe_min",
        "debt_ratio_max",
        "dividend_min",
        "market_cap_min",
        "market_cap_max",
    ]
    filters = {k: getattr(args, k.replace("-", "_")) for k in filter_keys if getattr(args, k.replace("-", "_")) is not None}

    screener = StockScreener(token=args.token, quiet=args.quiet)
    results = screener.screen(scope=args.scope, filters=filters if filters else None, sort_by=args.sort_by, top_n=args.top)

    output = {
        "screen_time": datetime.now().isoformat(),
        "scope": args.scope,
        "filters": filters,
        "count": len(results),
        "results": results,
    }

    output_json = json.dumps(output, ensure_ascii=False, indent=2, default=str)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
        if not args.quiet:
            print(f"筛选结果已保存到: {args.output}")
            print(f"共筛选出 {len(results)} 只股票")
    else:
        if args.format == "table":
            headers = ["代码", "名称", "最新价", "涨跌幅", "市盈率", "市净率", "总市值(亿)", "评分"]
            rows = [[
                x.get("代码", ""),
                x.get("名称", ""),
                x.get("最新价", ""),
                x.get("涨跌幅", ""),
                x.get("市盈率", ""),
                x.get("市净率", ""),
                x.get("总市值(亿)", ""),
                round(float(x.get("评分", 0)), 2),
            ] for x in results]
            print(format_table(headers, rows))
        else:
            print(output_json)


if __name__ == "__main__":
    main()
