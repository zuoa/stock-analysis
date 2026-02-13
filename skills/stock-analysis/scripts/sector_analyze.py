#!/usr/bin/env python3
"""板块综合分析脚本（CLI）"""

import argparse
import json
import math
import os
from datetime import datetime
from typing import Dict, List, Tuple


def safe_float(val, default=0.0):
    if val is None:
        return default
    try:
        if isinstance(val, str) and val.lower() == "nan":
            return default
        return float(val)
    except Exception:
        return default


def calc_growth(current, previous):
    if previous in [None, 0]:
        return None
    return (current - previous) / abs(previous) * 100


def format_num(val, unit="", decimal=2):
    v = safe_float(val, default=float("nan"))
    if math.isnan(v):
        return "-"
    if abs(v) >= 1e8:
        return f"{v/1e8:.{decimal}f}亿{unit}"
    if abs(v) >= 1e4:
        return f"{v/1e4:.{decimal}f}万{unit}"
    return f"{v:.{decimal}f}{unit}"


def get_score(stock: Dict) -> Tuple[int, List[str]]:
    score = 60
    reasons: List[str] = []
    fin = stock.get("financials", {})

    roe = safe_float(fin.get("roe"), default=None)
    if roe is not None:
        if roe > 20:
            score += 15
            reasons.append(f"ROE优秀({roe:.1f}%)")
        elif roe > 10:
            score += 8
        elif roe < 0:
            score -= 10
            reasons.append(f"ROE为负({roe:.1f}%)")

    margin = safe_float(fin.get("grossprofit_margin"), default=None)
    if margin is not None:
        if margin > 40:
            score += 10
            reasons.append(f"毛利率高({margin:.1f}%)")
        elif margin > 20:
            score += 5
        elif margin < 10:
            score -= 5
            reasons.append(f"毛利率低({margin:.1f}%)")

    debt = safe_float(fin.get("debt_to_assets"), default=None)
    if debt is not None:
        if debt > 70:
            score -= 10
            reasons.append(f"负债率高({debt:.1f}%)")
        elif debt < 30:
            score += 5

    pe = safe_float(stock.get("pe_ttm"), default=None)
    if pe is not None and pe > 0:
        if pe < 30:
            score += 10
        elif pe < 50:
            score += 5
        elif pe > 100:
            score -= 5
            reasons.append(f"PE较高({pe:.0f}x)")

    net_margin = safe_float(fin.get("netprofit_margin"), default=None)
    if net_margin is not None:
        if net_margin > 20:
            score += 10
            reasons.append(f"净利率高({net_margin:.1f}%)")
        elif net_margin < 0:
            score -= 15
            reasons.append(f"净利率为负({net_margin:.1f}%)")

    income = stock.get("income", {})
    revenues = income.get("revenues", [])
    if len(revenues) >= 2:
        growth = calc_growth(safe_float(revenues[0]), safe_float(revenues[-1]))
        if growth is not None:
            if growth > 50:
                score += 10
                reasons.append(f"营收高增长({growth:.0f}%)")
            elif growth < 0:
                score -= 5

    return min(100, max(0, score)), reasons


def build_analysis(data: Dict) -> Dict:
    stocks = data.get("stocks", {})
    sectors = data.get("sectors", {})

    sector_stats = {}
    all_scores = []

    for sector_name, codes_map in sectors.items():
        codes = list(codes_map.keys()) if isinstance(codes_map, dict) else list(codes_map)
        sector_stocks = {c: stocks[c] for c in codes if c in stocks}

        avg_pe, avg_roe, avg_margin = [], [], []
        total_mv = 0.0

        for code, stock in sector_stocks.items():
            pe = safe_float(stock.get("pe_ttm"), default=None)
            if pe is not None and pe > 0:
                avg_pe.append(pe)
            roe = safe_float(stock.get("financials", {}).get("roe"), default=None)
            if roe is not None:
                avg_roe.append(roe)
            margin = safe_float(stock.get("financials", {}).get("grossprofit_margin"), default=None)
            if margin is not None:
                avg_margin.append(margin)
            total_mv += safe_float(stock.get("total_mv"), default=0.0)

            score, reasons = get_score(stock)
            all_scores.append((code, stock.get("name", code), score, reasons, sector_name))

        sector_stats[sector_name] = {
            "avg_pe": sum(avg_pe) / len(avg_pe) if avg_pe else None,
            "avg_roe": sum(avg_roe) / len(avg_roe) if avg_roe else None,
            "avg_margin": sum(avg_margin) / len(avg_margin) if avg_margin else None,
            "total_mv": total_mv,
            "count": len(sector_stocks),
        }

    sorted_scores = sorted(all_scores, key=lambda x: x[2], reverse=True)

    leaders = {}
    for sector_name in sectors.keys():
        candidates = [x for x in sorted_scores if x[4] == sector_name]
        if candidates:
            top = candidates[0]
            leaders[sector_name] = {"code": top[0], "name": top[1], "score": top[2]}

    return {
        "analysis_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "input_sector": data.get("sector", ""),
        "sector_stats": sector_stats,
        "stock_scores": {
            code: {
                "name": name,
                "score": score,
                "sector": sector,
                "reasons": reasons,
            }
            for code, name, score, reasons, sector in all_scores
        },
        "ranking": [
            {
                "rank": i + 1,
                "code": code,
                "name": name,
                "score": score,
                "sector": sector,
                "reasons": reasons,
            }
            for i, (code, name, score, reasons, sector) in enumerate(sorted_scores)
        ],
        "leaders": leaders,
    }


def render_markdown(data: Dict, analysis: Dict) -> str:
    lines = []
    lines.append(f"# {data.get('sector','板块')} 综合分析报告")
    lines.append("")
    lines.append(f"- 数据时间: {data.get('fetch_time','')}")
    lines.append(f"- 分析时间: {analysis.get('analysis_time','')}")
    lines.append("")

    lines.append("## 一、细分领域概览")
    lines.append("")
    lines.append("| 细分领域 | 公司数 | 平均PE | 平均ROE | 平均毛利率 | 总市值 |")
    lines.append("|----------|--------|--------|---------|------------|--------|")
    for name, stats in analysis.get("sector_stats", {}).items():
        pe = f"{stats['avg_pe']:.1f}" if stats.get("avg_pe") is not None else "-"
        roe = f"{stats['avg_roe']:.1f}%" if stats.get("avg_roe") is not None else "-"
        margin = f"{stats['avg_margin']:.1f}%" if stats.get("avg_margin") is not None else "-"
        mv = format_num(safe_float(stats.get("total_mv"), 0) * 10000, "元")
        lines.append(f"| {name} | {stats.get('count',0)} | {pe} | {roe} | {margin} | {mv} |")

    lines.append("")
    lines.append("## 二、综合评分排名")
    lines.append("")
    lines.append("| 排名 | 代码 | 名称 | 细分领域 | 评分 | 亮点/风险 |")
    lines.append("|------|------|------|----------|------|-----------|")
    for item in analysis.get("ranking", [])[:20]:
        reason = "; ".join(item.get("reasons", [])[:2]) if item.get("reasons") else "-"
        lines.append(
            f"| {item['rank']} | {item['code']} | {item['name']} | {item['sector']} | {item['score']} | {reason} |"
        )

    lines.append("")
    lines.append("## 三、各细分领域龙头")
    lines.append("")
    for sector, top in analysis.get("leaders", {}).items():
        lines.append(f"- **{sector}**: {top['name']}({top['code']}) - 评分 {top['score']}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="板块综合分析")
    parser.add_argument("--input", required=True, help="输入 sector_data.json")
    parser.add_argument("--output", required=True, help="输出 analysis_result.json")
    parser.add_argument("--report-md", help="输出 markdown 报告路径（默认同目录 sector_analysis.md）")
    parser.add_argument("--format", choices=["json", "table"], default="json", help="控制台输出格式")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    analysis = build_analysis(data)

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)

    report_md_path = args.report_md or os.path.join(os.path.dirname(args.output) or ".", "sector_analysis.md")
    md = render_markdown(data, analysis)
    os.makedirs(os.path.dirname(report_md_path) or ".", exist_ok=True)
    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write(md)

    if args.format == "table":
        headers = ["排名", "代码", "名称", "领域", "评分"]
        rows = [[r["rank"], r["code"], r["name"], r["sector"], r["score"]] for r in analysis.get("ranking", [])[:10]]
        widths = [len(str(h)) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                widths[i] = max(widths[i], len(str(cell)))
        sep = "-+-".join("-" * w for w in widths)
        print(" | ".join(str(h).ljust(widths[i]) for i, h in enumerate(headers)))
        print(sep)
        for row in rows:
            print(" | ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)))
    else:
        print(json.dumps({"output": args.output, "report_md": report_md_path, "rank_count": len(analysis.get("ranking", []))}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
