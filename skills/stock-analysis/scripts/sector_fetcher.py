#!/usr/bin/env python3
"""板块数据获取脚本（CLI）"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Dict, List

try:
    import pandas as pd
    import tushare as ts
except ImportError:
    print("错误: 请先安装依赖库")
    print("pip install tushare pandas")
    sys.exit(1)

from env_loader import get_tushare_token


DEFAULT_SECTORS = {
    "AI芯片": {
        "688256": "寒武纪-U",
        "688041": "海光信息",
        "688047": "龙芯中科",
        "300474": "景嘉微",
    },
    "服务器": {
        "603019": "中科曙光",
        "000977": "浪潮信息",
        "601138": "工业富联",
        "000938": "紫光股份",
    },
    "光模块/CPO": {
        "300308": "中际旭创",
        "300502": "新易盛",
        "300394": "天孚通信",
        "000988": "华工科技",
    },
    "IDC/数据中心": {
        "603881": "数据港",
        "300738": "奥飞数据",
        "300383": "光环新网",
    },
}


def to_ts_code(code: str) -> str:
    code = str(code).strip().upper()
    if "." in code:
        return code
    if code.startswith(("6", "9", "5")):
        return f"{code}.SH"
    if code.startswith(("4", "8")):
        return f"{code}.BJ"
    return f"{code}.SZ"


def flatten_sector_codes(sectors: Dict[str, Dict[str, str]]) -> Dict[str, str]:
    merged: Dict[str, str] = {}
    for stocks in sectors.values():
        merged.update(stocks)
    return merged


def load_sector_config(path: str) -> Dict[str, Dict[str, str]]:
    if not path:
        return DEFAULT_SECTORS
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("sector 配置文件必须是 object")
    return data


def init_pro(token: str = ""):
    t = token or get_tushare_token()
    if not t:
        raise RuntimeError("未检测到 TUSHARE_TOKEN，请设置环境变量或 ~/.aj-skills/.env")
    ts.set_token(t)
    return ts.pro_api()


def fetch_basic_info(pro, code: str, name_hint: str) -> Dict:
    ts_code = to_ts_code(code)
    daily = pro.daily_basic(ts_code=ts_code, fields="ts_code,trade_date,close,pe_ttm,pb,ps_ttm,total_mv,circ_mv", limit=1)
    latest = daily.iloc[0].to_dict() if daily is not None and not daily.empty else {}

    base = pro.stock_basic(ts_code=ts_code, list_status="L", fields="ts_code,symbol,name,industry")
    b = base.iloc[0].to_dict() if base is not None and not base.empty else {}

    return {
        "code": code,
        "name": b.get("name", name_hint or code),
        "ts_code": ts_code,
        "industry": b.get("industry", ""),
        "trade_date": latest.get("trade_date"),
        "close": latest.get("close"),
        "pe_ttm": latest.get("pe_ttm"),
        "pb": latest.get("pb"),
        "ps_ttm": latest.get("ps_ttm"),
        "total_mv": latest.get("total_mv"),  # 万元
        "circ_mv": latest.get("circ_mv"),
    }


def fetch_financial_info(pro, code: str) -> Dict:
    ts_code = to_ts_code(code)
    df = pro.fina_indicator(ts_code=ts_code, limit=1)
    if df is None or df.empty:
        return {}
    row = df.iloc[0].to_dict()
    return {
        "roe": row.get("roe"),
        "roa": row.get("roa"),
        "grossprofit_margin": row.get("grossprofit_margin"),
        "netprofit_margin": row.get("netprofit_margin"),
        "debt_to_assets": row.get("debt_to_assets"),
        "current_ratio": row.get("current_ratio"),
        "quick_ratio": row.get("quick_ratio"),
        "eps": row.get("eps"),
        "bps": row.get("bps"),
        "cfps": row.get("cfps"),
        "ocfps": row.get("ocfps"),
    }


def fetch_income_info(pro, code: str) -> Dict:
    ts_code = to_ts_code(code)
    df = pro.income(ts_code=ts_code, limit=4)
    if df is None or df.empty:
        return {}
    return {
        "revenues": df.get("revenue", pd.Series(dtype=float)).tolist()[:4],
        "net_profits": df.get("n_income", pd.Series(dtype=float)).tolist()[:4],
        "end_dates": df.get("end_date", pd.Series(dtype=str)).tolist()[:4],
    }


def format_table(headers: List[str], rows: List[List]) -> str:
    widths = [len(str(h)) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    sep = "-+-".join("-" * w for w in widths)
    lines = [" | ".join(str(h).ljust(widths[i]) for i, h in enumerate(headers)), sep]
    for row in rows:
        lines.append(" | ".join(str(c).ljust(widths[i]) for i, c in enumerate(row)))
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="板块数据获取")
    parser.add_argument("--sector-name", default="算力板块", help="板块名称")
    parser.add_argument("--sector-file", help="板块配置JSON路径（格式: {细分领域: {代码: 名称}}）")
    parser.add_argument("--token", help="tushare token")
    parser.add_argument("--sleep", type=float, default=0.1, help="每只股票请求间隔秒")
    parser.add_argument("--format", choices=["json", "table"], default="json", help="控制台输出格式")
    parser.add_argument("--output", required=True, help="输出JSON路径")
    args = parser.parse_args()

    sectors = load_sector_config(args.sector_file)
    stocks = flatten_sector_codes(sectors)

    pro = init_pro(args.token)

    result = {
        "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sector": args.sector_name,
        "sectors": sectors,
        "stocks": {},
        "success_count": 0,
        "fail_count": 0,
    }

    for i, (code, name_hint) in enumerate(stocks.items(), 1):
        try:
            basic = fetch_basic_info(pro, code, name_hint)
            fin = fetch_financial_info(pro, code)
            inc = fetch_income_info(pro, code)
            result["stocks"][code] = {**basic, "financials": fin, "income": inc}
            result["success_count"] += 1
            print(f"[{i}/{len(stocks)}] ✓ {basic.get('name', code)} ({code})")
        except Exception as exc:
            result["fail_count"] += 1
            result.setdefault("errors", {})[code] = str(exc)
            print(f"[{i}/{len(stocks)}] ✗ {code}: {exc}")
        time.sleep(max(0, args.sleep))

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)

    if args.format == "table":
        rows = [[code, info.get("name", ""), info.get("close", ""), info.get("pe_ttm", ""), info.get("pb", "")] for code, info in result["stocks"].items()]
        print(format_table(["代码", "名称", "收盘", "PE", "PB"], rows))
    else:
        print(json.dumps({"output": args.output, "success": result["success_count"], "fail": result["fail_count"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
