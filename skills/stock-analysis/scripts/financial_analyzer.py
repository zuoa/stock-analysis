#!/usr/bin/env python3
"""
A股财务分析模块
提供财务健康度分析、杜邦分析、异常检测等功能

依赖: pip install tushare pandas numpy
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

try:
    import pandas as pd
    import numpy as np
except ImportError:
    print("错误: 请先安装依赖库")
    print("pip install pandas numpy")
    sys.exit(1)

from data_contract import ensure_stock_data


class FinancialAnalyzer:
    """财务分析器"""

    FUNDAMENTAL_WEIGHT = 0.4
    REALTIME_WEIGHT = 0.6

    def __init__(self, stock_data: Dict = None):
        self.stock_data = stock_data or {}
        self.analysis_result = {}

    def load_data(self, file_path: str):
        """从JSON文件加载股票数据"""
        with open(file_path, 'r', encoding='utf-8') as f:
            self.stock_data = json.load(f)

    def _assess_roe(self, roe: float) -> str:
        """根据ROE评估盈利能力"""
        if roe > 20:
            return "优秀 - ROE超过20%，盈利能力很强"
        elif roe > 15:
            return "良好 - ROE在15-20%之间，盈利能力较强"
        elif roe > 10:
            return "一般 - ROE在10-15%之间，盈利能力中等"
        return "较弱 - ROE低于10%，盈利能力需要改善"

    def analyze_profitability(self) -> Dict:
        """盈利能力分析"""
        result = {
            "category": "盈利能力",
            "metrics": {},
            "trend": [],
            "assessment": ""
        }

        indicators = self.stock_data.get('financial_indicators', [])
        if not indicators:
            return result

        metrics = {}
        for indicator in indicators[:8]:
            period = indicator.get('日期', '')
            if period:
                metrics[period] = {
                    "ROE": self._safe_float(indicator.get('净资产收益率', indicator.get('加权净资产收益率'))),
                    "ROA": self._safe_float(indicator.get('总资产报酬率')),
                    "毛利率": self._safe_float(indicator.get('销售毛利率')),
                    "净利率": self._safe_float(indicator.get('销售净利率'))
                }

        if not metrics:
            return result

        latest = list(metrics.values())[0]
        result["metrics"] = {
            "当前ROE": latest.get("ROE"),
            "当前ROA": latest.get("ROA"),
            "当前毛利率": latest.get("毛利率"),
            "当前净利率": latest.get("净利率")
        }

        roe_values = [v.get("ROE") for v in metrics.values() if v.get("ROE") is not None]
        if len(roe_values) >= 2:
            trend = "上升" if roe_values[0] > roe_values[-1] else "下降"
            result["trend"].append(f"ROE呈{trend}趋势")

        roe = latest.get("ROE")
        if roe:
            result["assessment"] = self._assess_roe(roe)

        return result

    def analyze_solvency(self) -> Dict:
        """偿债能力分析"""
        result = {
            "category": "偿债能力",
            "metrics": {},
            "risks": [],
            "assessment": ""
        }

        indicators = self.stock_data.get('financial_indicators', [])
        if not indicators:
            return result

        latest = indicators[0]

        debt_ratio = self._safe_float(latest.get('资产负债率'))
        current_ratio = self._safe_float(latest.get('流动比率'))
        quick_ratio = self._safe_float(latest.get('速动比率'))

        result["metrics"] = {
            "资产负债率": debt_ratio,
            "流动比率": current_ratio,
            "速动比率": quick_ratio
        }

        # 风险评估
        risk_checks = [
            (debt_ratio and debt_ratio > 70, f"资产负债率偏高 ({debt_ratio:.1f}%)，需关注偿债压力"),
            (current_ratio and current_ratio < 1, f"流动比率偏低 ({current_ratio:.2f})，短期偿债能力较弱"),
            (quick_ratio and quick_ratio < 0.8, f"速动比率偏低 ({quick_ratio:.2f})，短期流动性风险"),
        ]
        result["risks"] = [msg for condition, msg in risk_checks if condition]

        # 综合评估
        risk_count = len(result["risks"])
        if risk_count == 0:
            result["assessment"] = "良好 - 偿债能力指标正常，财务结构稳健"
        elif risk_count == 1:
            result["assessment"] = "一般 - 存在一项风险指标，需持续关注"
        else:
            result["assessment"] = "较弱 - 存在多项风险指标，偿债压力较大"

        return result

    def analyze_operation(self) -> Dict:
        """运营效率分析"""
        result = {
            "category": "运营效率",
            "metrics": {},
            "observations": [],
            "assessment": ""
        }

        indicators = self.stock_data.get('financial_indicators', [])
        if not indicators:
            return result

        latest = indicators[0]

        ar_days = self._safe_float(latest.get('应收账款周转天数'))
        inventory_days = self._safe_float(latest.get('存货周转天数'))
        asset_turnover = self._safe_float(latest.get('总资产周转率'))

        result["metrics"] = {
            "应收账款周转率": self._safe_float(latest.get('应收账款周转率')),
            "应收账款周转天数": ar_days,
            "存货周转率": self._safe_float(latest.get('存货周转率')),
            "存货周转天数": inventory_days,
            "总资产周转率": asset_turnover
        }

        # 观察分析
        observations = []
        if ar_days is not None and ar_days > 90:
            observations.append(f"应收账款周转天数较长 ({ar_days:.0f}天)，回款较慢")
        if inventory_days is not None and inventory_days > 180:
            observations.append(f"存货周转天数较长 ({inventory_days:.0f}天)，库存管理需关注")
        if asset_turnover is not None and asset_turnover < 0.5:
            observations.append(f"总资产周转率较低 ({asset_turnover:.2f})，资产利用效率有待提高")
        result["observations"] = observations

        if not result["observations"]:
            result["assessment"] = "良好 - 运营效率指标正常"
        else:
            result["assessment"] = "需关注 - " + "；".join(result["observations"])

        return result

    def _assess_growth_rate(self, avg_growth: float) -> str:
        """评估增长率"""
        if avg_growth > 20:
            return "高成长 - 平均增长率超过20%"
        elif avg_growth > 10:
            return "稳定成长 - 平均增长率10-20%"
        elif avg_growth > 0:
            return "低速成长 - 平均增长率0-10%"
        return "负增长 - 需要深入分析原因"

    def _analyze_growth_trend(self, values: List[float], name: str) -> Optional[str]:
        """分析增长趋势"""
        if not values:
            return None
        if all(g > 0 for g in values[:4]):
            return f"{name}持续正增长"
        elif values[0] < 0:
            return f"{name}负增长，需关注"
        return None

    def analyze_growth(self) -> Dict:
        """成长性分析"""
        result = {
            "category": "成长性",
            "metrics": {},
            "trend": [],
            "assessment": ""
        }

        indicators = self.stock_data.get('financial_indicators', [])
        if not indicators:
            return result

        revenue_growth = []
        profit_growth = []

        for indicator in indicators[:8]:
            rev = self._safe_float(indicator.get('主营业务收入增长率', indicator.get('营业收入增长率')))
            net = self._safe_float(indicator.get('净利润增长率'))
            if rev is not None:
                revenue_growth.append(rev)
            if net is not None:
                profit_growth.append(net)

        if revenue_growth:
            result["metrics"]["最近营收增长率"] = revenue_growth[0]
            result["metrics"]["平均营收增长率"] = sum(revenue_growth) / len(revenue_growth)

        if profit_growth:
            result["metrics"]["最近净利润增长率"] = profit_growth[0]
            result["metrics"]["平均净利润增长率"] = sum(profit_growth) / len(profit_growth)

        # 趋势判断
        for values, name in [(revenue_growth, "营收"), (profit_growth, "净利润")]:
            trend = self._analyze_growth_trend(values, name)
            if trend:
                result["trend"].append(trend)

        avg_growth = result["metrics"].get("平均净利润增长率", 0) or 0
        result["assessment"] = self._assess_growth_rate(avg_growth)

        return result

    def analyze_dupont(self) -> Dict:
        """杜邦分析"""
        result = {
            "category": "杜邦分析",
            "decomposition": {},
            "driver": "",
            "assessment": ""
        }

        indicators = self.stock_data.get('financial_indicators', [])
        if not indicators:
            return result

        latest = indicators[0] if indicators else {}

        # 杜邦分解: ROE = 净利率 × 资产周转率 × 权益乘数
        net_margin = self._safe_float(latest.get('销售净利率'))
        asset_turnover = self._safe_float(latest.get('总资产周转率'))
        equity_multiplier = self._safe_float(latest.get('权益乘数'))
        roe = self._safe_float(latest.get('净资产收益率', latest.get('加权净资产收益率')))

        result["decomposition"] = {
            "ROE": roe,
            "净利率": net_margin,
            "资产周转率": asset_turnover,
            "权益乘数": equity_multiplier
        }

        # 判断ROE驱动因素
        if net_margin and asset_turnover and equity_multiplier:
            drivers = []
            if net_margin > 15:
                drivers.append("高净利率")
            if asset_turnover > 1:
                drivers.append("高周转")
            if equity_multiplier > 2.5:
                drivers.append("高杠杆")

            if drivers:
                result["driver"] = "ROE主要由" + "、".join(drivers) + "驱动"
            else:
                result["driver"] = "ROE驱动因素较为均衡"

        return result

    def detect_anomalies(self) -> Dict:
        """财务异常检测"""
        result = {
            "category": "财务异常检测",
            "signals": [],
            "risk_level": "低",
            "details": []
        }

        indicators = self.stock_data.get('financial_indicators', [])
        if len(indicators) < 2:
            return result

        current = indicators[0]
        previous = indicators[1] if len(indicators) > 1 else {}

        # 1. 应收账款异常
        ar_growth = self._safe_float(current.get('应收账款增长率'))
        revenue_growth = self._safe_float(current.get('营业收入增长率', current.get('主营业务收入增长率')))
        if ar_growth and revenue_growth and ar_growth > revenue_growth * 1.5:
            result["signals"].append({
                "type": "应收账款增速异常",
                "description": f"应收账款增速({ar_growth:.1f}%)显著高于营收增速({revenue_growth:.1f}%)",
                "severity": "中"
            })

        # 2. 存货异常
        inventory_growth = self._safe_float(current.get('存货增长率'))
        if inventory_growth and revenue_growth and inventory_growth > revenue_growth * 2:
            result["signals"].append({
                "type": "存货增速异常",
                "description": f"存货增速({inventory_growth:.1f}%)远高于营收增速({revenue_growth:.1f}%)",
                "severity": "中"
            })

        # 3. 毛利率异常波动
        current_gm = self._safe_float(current.get('销售毛利率'))
        previous_gm = self._safe_float(previous.get('销售毛利率'))
        if current_gm and previous_gm:
            gm_change = abs(current_gm - previous_gm)
            if gm_change > 10:
                result["signals"].append({
                    "type": "毛利率大幅波动",
                    "description": f"毛利率变动{gm_change:.1f}个百分点，需关注原因",
                    "severity": "中"
                })

        # 4. 经营现金流与净利润背离 (需要现金流数据)
        cash_flow = self.stock_data.get('financial_data', {}).get('cash_flow', [])
        income = self.stock_data.get('financial_data', {}).get('income_statement', [])
        if cash_flow and income:
            try:
                ocf = self._safe_float(cash_flow[0].get('经营活动产生的现金流量净额'))
                net_profit = self._safe_float(income[0].get('净利润'))
                if ocf and net_profit and net_profit > 0:
                    ocf_ratio = ocf / net_profit
                    if ocf_ratio < 0.5:
                        result["signals"].append({
                            "type": "现金流与利润背离",
                            "description": f"经营现金流/净利润 = {ocf_ratio:.1%}，盈利质量存疑",
                            "severity": "高"
                        })
            except (IndexError, KeyError):
                pass

        # 确定风险等级
        high_severity = sum(1 for s in result["signals"] if s.get("severity") == "高")
        medium_severity = sum(1 for s in result["signals"] if s.get("severity") == "中")

        if high_severity > 0:
            result["risk_level"] = "高"
        elif medium_severity >= 2:
            result["risk_level"] = "中"
        else:
            result["risk_level"] = "低"

        return result

    def analyze_performance_events(self) -> Dict:
        """业绩预告/快报/审计/主营构成分析。"""
        result = {
            "category": "业绩与审计",
            "signals": [],
            "assessment": "中性",
        }
        perf = self.stock_data.get("performance_data", {}) or {}

        forecast = perf.get("forecast", []) if isinstance(perf, dict) else []
        express = perf.get("express", []) if isinstance(perf, dict) else []
        audit = perf.get("audit", []) if isinstance(perf, dict) else []
        main_business = perf.get("main_business", {}) if isinstance(perf, dict) else {}

        if forecast:
            latest = forecast[0]
            p_change_min = self._safe_float(latest.get("p_change_min"))
            p_change_max = self._safe_float(latest.get("p_change_max"))
            avg_change = None
            if p_change_min is not None and p_change_max is not None:
                avg_change = (p_change_min + p_change_max) / 2
            elif p_change_min is not None:
                avg_change = p_change_min
            elif p_change_max is not None:
                avg_change = p_change_max

            if avg_change is not None:
                if avg_change < -20:
                    result["signals"].append(f"最新业绩预告偏弱（预计净利同比约 {avg_change:.1f}%）")
                elif avg_change > 20:
                    result["signals"].append(f"最新业绩预告较强（预计净利同比约 {avg_change:.1f}%）")

        if express:
            latest = express[0]
            yoy = self._safe_float(latest.get("yoy_net_profit"))
            if yoy is not None:
                if yoy < -20:
                    result["signals"].append(f"业绩快报净利润同比明显下滑（{yoy:.1f}%）")
                elif yoy > 20:
                    result["signals"].append(f"业绩快报净利润同比高增长（{yoy:.1f}%）")

        if audit:
            latest = audit[0]
            opinion = str(latest.get("audit_result", "") or latest.get("audit_agency", ""))
            if opinion and ("非标" in opinion or "保留" in opinion or "否定" in opinion or "无法表示" in opinion):
                result["signals"].append(f"审计意见需关注：{opinion}")
            elif opinion:
                result["signals"].append(f"最近审计信息：{opinion}")

        by_product = (main_business.get("by_product", []) if isinstance(main_business, dict) else []) or []
        if by_product:
            sales = [self._safe_float(x.get("bz_sales")) for x in by_product]
            sales = [x for x in sales if x is not None and x >= 0]
            if sales:
                total = sum(sales)
                if total > 0:
                    top_ratio = max(sales) / total * 100
                    if top_ratio > 70:
                        result["signals"].append(f"主营业务集中度较高（第一业务占比约 {top_ratio:.1f}%）")

        negative = sum(
            1 for x in result["signals"]
            if any(k in x for k in ["偏弱", "下滑", "需关注", "集中度较高"])
        )
        positive = sum(
            1 for x in result["signals"]
            if any(k in x for k in ["较强", "高增长"])
        )

        if negative >= 2:
            result["assessment"] = "偏弱"
        elif positive >= 2 and negative == 0:
            result["assessment"] = "积极"
        else:
            result["assessment"] = "中性"

        return result

    def generate_summary(self, level: str = "standard") -> Dict:
        """生成分析摘要"""
        summary = {
            "code": self.stock_data.get('code', ''),
            "name": self.stock_data.get('basic_info', {}).get('name', ''),
            "analysis_date": datetime.now().isoformat(),
            "level": level
        }

        profitability = self.analyze_profitability()
        solvency = self.analyze_solvency()
        operation = self.analyze_operation()
        growth = self.analyze_growth()
        anomalies = self.detect_anomalies()
        performance = self.analyze_performance_events()

        if level == "summary":
            summary["profitability"] = profitability["assessment"]
            summary["solvency"] = solvency["assessment"]
            summary["growth"] = growth["assessment"]
            summary["risk_level"] = anomalies["risk_level"]
            summary["news_sentiment"] = self.stock_data.get("news_sentiment", {})
            summary["performance"] = performance["assessment"]
        else:
            # standard 和 deep 级别共享基础分析结果
            summary["profitability"] = profitability
            summary["solvency"] = solvency
            summary["operation"] = operation
            summary["growth"] = growth
            summary["dupont"] = self.analyze_dupont()
            summary["anomalies"] = anomalies
            summary["performance"] = performance
            summary["news_sentiment"] = self.stock_data.get("news_sentiment", {})
            if isinstance(self.stock_data.get("realtime_metrics"), dict):
                summary["realtime_metrics"] = self.stock_data.get("realtime_metrics", {})
            if isinstance(self.stock_data.get("event_window"), dict):
                summary["event_window"] = self.stock_data.get("event_window", {})

            if level == "deep":
                summary["historical_indicators"] = self.stock_data.get('financial_indicators', [])

        fundamental_score = self._calculate_fundamental_score(
            profitability,
            solvency,
            growth,
            anomalies,
            summary.get("news_sentiment", {}),
            performance,
        )
        realtime_score = self._calculate_realtime_score()
        event_window_score = self._calculate_event_window_score()
        summary["fundamental_score"] = fundamental_score
        summary["realtime_score"] = realtime_score
        summary["event_window_score"] = event_window_score
        summary["score_weights"] = {
            "fundamental": self.FUNDAMENTAL_WEIGHT if realtime_score is not None else 1.0,
            "realtime": self.REALTIME_WEIGHT if realtime_score is not None else 0.0,
        }
        summary["score"] = self._blend_total_score(fundamental_score, realtime_score)
        summary["summary_title"] = self._build_summary_title(summary)

        return summary

    def _build_summary_title(self, summary: Dict) -> str:
        """生成总结性标题。"""
        name = summary.get("name", "")
        code = summary.get("code", "")
        score = summary.get("score", 50)
        risk_level = summary.get("anomalies", {}).get("risk_level", summary.get("risk_level", "低"))

        if score >= 80 and risk_level in ["低", "中"]:
            conclusion = "财务稳健，估值与风险匹配度较好"
        elif score >= 65:
            conclusion = "基本面中等偏强，建议持续跟踪"
        else:
            conclusion = "基本面或风险信号偏弱，建议谨慎评估"

        return f"{name}({code})：{conclusion}"

    def _calculate_fundamental_score(self, profitability, solvency, growth, anomalies, news_sentiment=None, performance=None) -> int:
        """计算财务与新闻维度综合评分 (0-100)。"""
        score = 50

        # 盈利能力评分
        roe = profitability.get("metrics", {}).get("当前ROE")
        if roe:
            if roe > 20:
                score += 15
            elif roe > 15:
                score += 10
            elif roe > 10:
                score += 5
            elif roe < 5:
                score -= 5

        # 偿债能力评分
        risks = solvency.get("risks", [])
        score += 10 if not risks else -len(risks) * 3

        # 成长性评分
        avg_growth = growth.get("metrics", {}).get("平均净利润增长率", 0) or 0
        if avg_growth > 20:
            score += 15
        elif avg_growth > 10:
            score += 10
        elif avg_growth > 0:
            score += 5
        else:
            score -= 5

        # 风险扣分
        risk_penalties = {"高": 15, "中": 8}
        score -= risk_penalties.get(anomalies.get("risk_level", "低"), 0)

        # 舆情加减分（轻权重，避免压过财务面）
        if isinstance(news_sentiment, dict):
            news_risk = news_sentiment.get("risk_level")
            if news_risk == "高":
                score -= 8
            elif news_risk == "中":
                score -= 4
            elif news_risk == "低" and news_sentiment.get("overall_sentiment", 0) > 0.2:
                score += 2

        if isinstance(performance, dict):
            p_assessment = performance.get("assessment")
            if p_assessment == "偏弱":
                score -= 8
            elif p_assessment == "积极":
                score += 4

        return max(0, min(100, score))

    def _calculate_realtime_score(self) -> Optional[float]:
        """读取实时指标分，如缺失则返回 None。"""
        rt = self.stock_data.get("realtime_metrics")
        if not isinstance(rt, dict):
            return None

        direct = self._safe_float(rt.get("realtime_score"))
        if direct is not None:
            return max(0.0, min(100.0, direct))

        trend = self._safe_float((rt.get("trend") or {}).get("trend_score"))
        confirm = self._safe_float((rt.get("confirm") or {}).get("confirm_score"))
        risk_penalty = self._safe_float((rt.get("risk") or {}).get("risk_penalty"))
        chip_penalty = self._safe_float((rt.get("chip") or {}).get("chip_penalty"))

        if trend is None and confirm is None and risk_penalty is None and chip_penalty is None:
            return None

        trend = trend if trend is not None else 50.0
        confirm = confirm if confirm is not None else 50.0
        risk_penalty = risk_penalty if risk_penalty is not None else 20.0
        chip_penalty = chip_penalty if chip_penalty is not None else 0.0
        score = trend * 0.45 + confirm * 0.30 + (100 - risk_penalty) * 0.25 - chip_penalty
        return max(0.0, min(100.0, score))

    def _calculate_event_window_score(self) -> Optional[float]:
        """读取事件窗口分，如缺失则返回 None。"""
        ew = self.stock_data.get("event_window")
        if not isinstance(ew, dict):
            return None
        score = self._safe_float(ew.get("event_window_score"))
        if score is None:
            return None
        return max(0.0, min(100.0, score))

    def _blend_total_score(self, fundamental_score: int, realtime_score: Optional[float]) -> int:
        """按 4:6 融合财务分与实时分（实时缺失时退化为财务分）。"""
        if realtime_score is None:
            return int(max(0, min(100, round(fundamental_score))))
        total = (
            fundamental_score * self.FUNDAMENTAL_WEIGHT
            + realtime_score * self.REALTIME_WEIGHT
        )
        return int(max(0, min(100, round(total))))

    def compare_stocks(self, stocks_data: List[Dict]) -> Dict:
        """对比多只股票"""
        comparison = {
            "comparison_date": datetime.now().isoformat(),
            "stocks": [],
            "ranking": {}
        }

        stock_scores = []
        for stock in stocks_data:
            self.stock_data = stock
            summary = self.generate_summary(level="summary")
            comparison["stocks"].append({
                "code": stock.get('code', ''),
                "name": stock.get('basic_info', {}).get('name', ''),
                "score": summary.get("score", 50),
                "profitability": summary.get("profitability"),
                "solvency": summary.get("solvency"),
                "growth": summary.get("growth"),
                "risk_level": summary.get("risk_level")
            })
            stock_scores.append((stock.get('code', ''), summary.get("score", 50)))

        # 排名
        stock_scores.sort(key=lambda x: x[1], reverse=True)
        comparison["ranking"] = {code: rank + 1 for rank, (code, _) in enumerate(stock_scores)}

        return comparison

    @staticmethod
    def _safe_float(value) -> Optional[float]:
        """安全转换为浮点数"""
        if value is None or value == '' or value == '--':
            return None
        try:
            if isinstance(value, str):
                value = value.replace('%', '').replace(',', '')
            return float(value)
        except (ValueError, TypeError):
            return None


def _fmt_num(val, ndigits: int = 2) -> str:
    if val is None or val == "":
        return "-"
    try:
        return f"{float(val):.{ndigits}f}"
    except Exception:
        return str(val)


def _assessment_to_score(text: str) -> float:
    s = str(text or "")
    if "优秀" in s or "积极" in s or "稳健" in s:
        return 85.0
    if "良好" in s or "较强" in s:
        return 75.0
    if "一般" in s or "中性" in s:
        return 60.0
    if "需关注" in s or "较弱" in s or "偏弱" in s:
        return 45.0
    return 60.0


def _build_main_business(stock_data: Dict) -> str:
    perf = stock_data.get("performance_data", {}) if isinstance(stock_data, dict) else {}
    main_business = perf.get("main_business", {}) if isinstance(perf, dict) else {}
    by_product = main_business.get("by_product", []) if isinstance(main_business, dict) else []
    if by_product:
        rows = []
        for item in by_product[:3]:
            name = item.get("bz_item", "-")
            sales = _fmt_num(item.get("bz_sales"), 0)
            rows.append(f"- {name}：{sales}")
        return "\n".join(rows)
    return "- 暂无主营构成数据"


def _build_realtime_conclusion(rt: Dict) -> str:
    if not isinstance(rt, dict) or not rt:
        return "未启用实时指标，建议开启 `--with-realtime` 获取趋势/资金/风险/筹码的动态判断。"

    score = float(rt.get("realtime_score", 0) or 0)
    trend = float((rt.get("trend", {}) or {}).get("trend_score", 50) or 50)
    confirm = float((rt.get("confirm", {}) or {}).get("confirm_score", 50) or 50)
    risk_penalty = float((rt.get("risk", {}) or {}).get("risk_penalty", 20) or 20)
    chip_penalty = float((rt.get("chip", {}) or {}).get("chip_penalty", 0) or 0)

    if score >= 70 and trend >= 60 and confirm >= 55 and risk_penalty <= 30 and chip_penalty <= 10:
        return "实时景气度偏强：趋势与成交确认较好，风险与筹码压力可控。"
    if score <= 45 or risk_penalty >= 55 or chip_penalty >= 20:
        return "实时信号偏弱：风险或筹码压力较大，建议降低仓位并等待确认。"
    return "实时信号中性：趋势与确认存在分歧，建议结合后续资金连续性与回撤控制观察。"


def _build_event_window_conclusion(ew: Dict) -> str:
    if not isinstance(ew, dict) or not ew:
        return "未启用事件窗口分析，建议开启 data_fetcher 的 `--with-event-window` 评估事件冲击的持续性。"

    score = float(ew.get("event_window_score", 50) or 50)
    summary = ew.get("summary", {}) if isinstance(ew.get("summary"), dict) else {}
    avg_abn_3 = _fmt_num(summary.get("avg_abnormal_3d_pct"))
    avg_post_3 = _fmt_num(summary.get("avg_post_3d_pct"))
    matched = int(ew.get("matched_event_count", 0) or 0)

    if score >= 65:
        return f"事件窗口偏强：已匹配{matched}个事件，3日平均反应较好（超额约 {avg_abn_3}% / 绝对约 {avg_post_3}%）。"
    if score <= 40:
        return f"事件窗口偏弱：已匹配{matched}个事件，事件后收益承压（超额约 {avg_abn_3}% / 绝对约 {avg_post_3}%）。"
    return f"事件窗口中性：已匹配{matched}个事件，短期反应分化（超额约 {avg_abn_3}% / 绝对约 {avg_post_3}%）。"


def build_report_context(stock_data: Dict, result: Dict) -> Dict:
    basic = stock_data.get("basic_info", {}) if isinstance(stock_data, dict) else {}
    valuation = stock_data.get("valuation", {}) if isinstance(stock_data, dict) else {}
    val_latest = valuation.get("latest", {}) if isinstance(valuation, dict) else {}
    price = stock_data.get("price", {}) if isinstance(stock_data, dict) else {}

    profitability = result.get("profitability", {}) if isinstance(result.get("profitability"), dict) else {}
    profitability_metrics = profitability.get("metrics", {}) if isinstance(profitability, dict) else {}
    solvency = result.get("solvency", {}) if isinstance(result.get("solvency"), dict) else {}
    solvency_metrics = solvency.get("metrics", {}) if isinstance(solvency, dict) else {}
    growth = result.get("growth", {}) if isinstance(result.get("growth"), dict) else {}
    growth_metrics = growth.get("metrics", {}) if isinstance(growth, dict) else {}
    dupont = result.get("dupont", {}) if isinstance(result.get("dupont"), dict) else {}
    dupont_dec = dupont.get("decomposition", {}) if isinstance(dupont, dict) else {}
    anomalies = (result.get("anomalies", {}) or {}).get("signals", [])
    perf = result.get("performance", {}) if isinstance(result.get("performance"), dict) else {}
    news = result.get("news_sentiment", {}) if isinstance(result.get("news_sentiment"), dict) else {}
    rt = result.get("realtime_metrics", {}) if isinstance(result.get("realtime_metrics"), dict) else {}
    ew = result.get("event_window", {}) if isinstance(result.get("event_window"), dict) else {}
    trend = rt.get("trend", {}) if isinstance(rt.get("trend"), dict) else {}
    confirm = rt.get("confirm", {}) if isinstance(rt.get("confirm"), dict) else {}
    risk = rt.get("risk", {}) if isinstance(rt.get("risk"), dict) else {}
    chip = rt.get("chip", {}) if isinstance(rt.get("chip"), dict) else {}
    momentum = trend.get("momentum_pct", {}) if isinstance(trend.get("momentum_pct"), dict) else {}
    relative = trend.get("relative_strength_pct", {}) if isinstance(trend.get("relative_strength_pct"), dict) else {}
    ew_summary = ew.get("summary", {}) if isinstance(ew.get("summary"), dict) else {}

    score_weights = result.get("score_weights", {}) if isinstance(result.get("score_weights"), dict) else {}
    fundamental_weight = float(score_weights.get("fundamental", 1.0) or 1.0)
    realtime_weight = float(score_weights.get("realtime", 0.0) or 0.0)
    fundamental_score = float(result.get("fundamental_score", result.get("score", 0)) or 0)
    realtime_score = float(result.get("realtime_score", 0) or 0)

    profitability_score = _assessment_to_score(profitability.get("assessment", ""))
    safety_score = max(0.0, 100.0 - len(solvency.get("risks", []) if isinstance(solvency, dict) else []) * 20.0)
    growth_score = _assessment_to_score(growth.get("assessment", ""))
    pe_percentile = valuation.get("pe_percentile")
    try:
        valuation_score = max(0.0, 100.0 - abs(float(pe_percentile or 50) - 35.0))
    except Exception:
        valuation_score = 60.0

    ctx = {
        "stock_code": result.get("code", stock_data.get("code", "-")),
        "stock_name": result.get("name", basic.get("name", "-")),
        "summary_title": result.get("summary_title", "-"),
        "analysis_date": result.get("analysis_date", ""),
        "analysis_level": result.get("level", "standard"),
        "overall_score": _fmt_num(result.get("score"), 0),
        "fundamental_score": _fmt_num(result.get("fundamental_score"), 0),
        "realtime_score": _fmt_num(result.get("realtime_score"), 0),
        "fundamental_weight_pct": _fmt_num(fundamental_weight * 100, 0),
        "realtime_weight_pct": _fmt_num(realtime_weight * 100, 0),
        "industry": basic.get("industry", "-"),
        "market_cap": _fmt_num(basic.get("market_cap"), 0),
        "float_cap": _fmt_num(basic.get("float_cap"), 0),
        "listing_date": basic.get("listing_date", "-"),
        "main_business": _build_main_business(stock_data),
        "roe": _fmt_num(profitability_metrics.get("当前ROE")),
        "roa": _fmt_num(profitability_metrics.get("当前ROA")),
        "gross_margin": _fmt_num(profitability_metrics.get("当前毛利率")),
        "net_margin": _fmt_num(profitability_metrics.get("当前净利率")),
        "industry_roe": "-",
        "industry_roa": "-",
        "industry_gross_margin": "-",
        "industry_net_margin": "-",
        "roe_assessment": profitability.get("assessment", "-"),
        "roa_assessment": "-",
        "gross_margin_assessment": "-",
        "net_margin_assessment": "-",
        "asset_turnover": _fmt_num(dupont_dec.get("资产周转率"), 3),
        "equity_multiplier": _fmt_num(dupont_dec.get("权益乘数"), 3),
        "roe_driver": dupont.get("driver", "-"),
        "debt_ratio": _fmt_num(solvency_metrics.get("资产负债率")),
        "current_ratio": _fmt_num(solvency_metrics.get("流动比率"), 3),
        "quick_ratio": _fmt_num(solvency_metrics.get("速动比率"), 3),
        "interest_coverage": "-",
        "debt_ratio_status": "需关注" if (solvency_metrics.get("资产负债率") or 0) > 70 else "正常",
        "current_ratio_status": "偏低" if (solvency_metrics.get("流动比率") or 0) < 1 else "正常",
        "quick_ratio_status": "偏低" if (solvency_metrics.get("速动比率") or 0) < 0.8 else "正常",
        "interest_coverage_status": "-",
        "ar_days": "-",
        "ar_trend": "-",
        "inventory_days": "-",
        "inventory_trend": "-",
        "asset_turnover_trend": "-",
        "revenue_growth": _fmt_num(growth_metrics.get("最近营收增长率")),
        "avg_revenue_growth": _fmt_num(growth_metrics.get("平均营收增长率")),
        "revenue_trend": "；".join(growth.get("trend", [])[:1]) if isinstance(growth, dict) else "-",
        "profit_growth": _fmt_num(growth_metrics.get("最近净利润增长率")),
        "avg_profit_growth": _fmt_num(growth_metrics.get("平均净利润增长率")),
        "profit_trend": "；".join(growth.get("trend", [])[1:2]) if isinstance(growth, dict) else "-",
        "eps_growth": "-",
        "avg_eps_growth": "-",
        "eps_trend": "-",
        "growth_assessment": growth.get("assessment", "-"),
        "trend_score": _fmt_num(trend.get("trend_score")),
        "return_1d": _fmt_num(momentum.get("return_1d")),
        "return_5d": _fmt_num(momentum.get("return_5d")),
        "return_20d": _fmt_num(momentum.get("return_20d")),
        "return_60d": _fmt_num(momentum.get("return_60d")),
        "vs_benchmark_1d": _fmt_num(relative.get("vs_benchmark_1d")),
        "vs_benchmark_5d": _fmt_num(relative.get("vs_benchmark_5d")),
        "vs_benchmark_20d": _fmt_num(relative.get("vs_benchmark_20d")),
        "vs_benchmark_60d": _fmt_num(relative.get("vs_benchmark_60d")),
        "confirm_score": _fmt_num(confirm.get("confirm_score")),
        "amount_ratio_20d": _fmt_num(confirm.get("amount_ratio_20d"), 4),
        "volume_ratio": _fmt_num(confirm.get("volume_ratio"), 4),
        "turnover_rate": _fmt_num(confirm.get("turnover_rate"), 4),
        "net_inflow_ratio": _fmt_num(confirm.get("net_inflow_ratio"), 4),
        "positive_days_5": _fmt_num(confirm.get("positive_days_5"), 0),
        "risk_penalty": _fmt_num(risk.get("risk_penalty")),
        "intraday_amplitude_pct": _fmt_num(risk.get("intraday_amplitude_pct")),
        "realized_volatility_20d_pct": _fmt_num(risk.get("realized_volatility_20d_pct")),
        "downside_volatility_20d_pct": _fmt_num(risk.get("downside_volatility_20d_pct")),
        "max_drawdown_window_pct": _fmt_num(risk.get("max_drawdown_window_pct")),
        "chip_penalty": _fmt_num(chip.get("chip_penalty")),
        "unlock_30d_ratio": _fmt_num(chip.get("unlock_30d_ratio")),
        "unlock_90d_ratio": _fmt_num(chip.get("unlock_90d_ratio")),
        "reduction_density_30d": _fmt_num(chip.get("reduction_density_30d"), 4),
        "repurchase_ratio_90d": _fmt_num(chip.get("repurchase_ratio_90d")),
        "realtime_conclusion": _build_realtime_conclusion(rt),
        "event_window_score": _fmt_num(result.get("event_window_score"), 0),
        "event_window_pre_days": _fmt_num(ew.get("pre_days"), 0),
        "event_window_post_days": ",".join(str(x) for x in (ew.get("post_days") or [])) if ew.get("post_days") else "-",
        "event_window_event_count": _fmt_num(ew.get("event_count"), 0),
        "event_window_matched_count": _fmt_num(ew.get("matched_event_count"), 0),
        "ew_avg_post_1d_pct": _fmt_num(ew_summary.get("avg_post_1d_pct")),
        "ew_avg_post_3d_pct": _fmt_num(ew_summary.get("avg_post_3d_pct")),
        "ew_avg_post_5d_pct": _fmt_num(ew_summary.get("avg_post_5d_pct")),
        "ew_avg_abnormal_1d_pct": _fmt_num(ew_summary.get("avg_abnormal_1d_pct")),
        "ew_avg_abnormal_3d_pct": _fmt_num(ew_summary.get("avg_abnormal_3d_pct")),
        "ew_avg_abnormal_5d_pct": _fmt_num(ew_summary.get("avg_abnormal_5d_pct")),
        "ew_positive_ratio_3d": _fmt_num(
            (ew_summary.get("positive_ratio_3d") * 100) if ew_summary.get("positive_ratio_3d") is not None else None
        ),
        "ew_worst_post_5d_pct": _fmt_num(ew_summary.get("worst_post_5d_pct")),
        "event_window_conclusion": _build_event_window_conclusion(ew),
        "pe_ttm": _fmt_num(basic.get("pe_ttm", val_latest.get("pe_ttm"))),
        "pb": _fmt_num(basic.get("pb", val_latest.get("pb"))),
        "ps": "-",
        "pe_percentile": _fmt_num(valuation.get("pe_percentile")),
        "pb_percentile": _fmt_num(valuation.get("pb_percentile")),
        "ps_percentile": "-",
        "industry_pe": "-",
        "industry_pb": "-",
        "industry_ps": "-",
        "dcf_value": "-",
        "discount_rate": "-",
        "terminal_growth": "-",
        "ddm_value": "-",
        "dividend_growth": "-",
        "relative_value": "-",
        "avg_value": "-",
        "current_price": _fmt_num(price.get("latest_price")),
        "margin_of_safety": "-",
        "safety_price": "-",
        "valuation_conclusion": "-",
        "performance_assessment": perf.get("assessment", "-"),
        "risk_level": (result.get("anomalies", {}) or {}).get("risk_level", result.get("risk_level", "低")),
        "news_count": news.get("news_count", 0),
        "overall_sentiment": _fmt_num(news.get("overall_sentiment"), 4),
        "news_risk_level": news.get("risk_level", "低"),
        "industry_risks": "需结合行业与政策变化持续跟踪。",
        "profitability_score": _fmt_num(profitability_score, 0),
        "safety_score": _fmt_num(safety_score, 0),
        "growth_score": _fmt_num(growth_score, 0),
        "valuation_score": _fmt_num(valuation_score, 0),
        "profitability_weighted": _fmt_num(profitability_score * 0.30, 1),
        "safety_weighted": _fmt_num(safety_score * 0.20, 1),
        "growth_weighted": _fmt_num(growth_score * 0.25, 1),
        "valuation_weighted": _fmt_num(valuation_score * 0.25, 1),
        "fundamental_weighted_score": _fmt_num(fundamental_score * fundamental_weight, 1),
        "realtime_weighted_score": _fmt_num(realtime_score * realtime_weight, 1),
        "investment_recommendation": result.get("summary_title", "-"),
        "report_time": datetime.now().isoformat(),
        "performance_signals": perf.get("signals", []) if isinstance(perf, dict) else [],
        "anomalies": anomalies if isinstance(anomalies, list) else [],
        "top_negative_events": news.get("top_negative_events", []) if isinstance(news, dict) else [],
        "event_window_top_positive": ew.get("top_positive_events", []) if isinstance(ew, dict) else [],
        "event_window_top_negative": ew.get("top_negative_events", []) if isinstance(ew, dict) else [],
        "holder_risks": [],
        "key_observations": [
            result.get("summary_title", ""),
            _build_realtime_conclusion(rt),
            _build_event_window_conclusion(ew),
        ],
    }
    return ctx


def _render_template_content(template: str, context: Dict) -> str:
    text = template

    if_pattern = re.compile(r"{{#if\s+([a-zA-Z0-9_]+)}}(.*?)(?:{{else}}(.*?))?{{/if}}", re.DOTALL)
    each_pattern = re.compile(r"{{#each\s+([a-zA-Z0-9_]+)}}(.*?){{/each}}", re.DOTALL)
    var_pattern = re.compile(r"{{\s*([a-zA-Z0-9_]+)\s*}}")
    this_field_pattern = re.compile(r"{{\s*this\.([a-zA-Z0-9_]+)\s*}}")

    def as_text(v) -> str:
        if v is None:
            return "-"
        if isinstance(v, (int, float, str)):
            return str(v)
        return str(v)

    while True:
        m = if_pattern.search(text)
        if not m:
            break
        key, yes_block, no_block = m.group(1), m.group(2), (m.group(3) or "")
        chosen = yes_block if context.get(key) else no_block
        text = text[:m.start()] + chosen + text[m.end():]

    while True:
        m = each_pattern.search(text)
        if not m:
            break
        key, block = m.group(1), m.group(2)
        items = context.get(key) or []
        rendered_items = []
        for item in items:
            item_block = block
            if isinstance(item, dict):
                item_block = this_field_pattern.sub(lambda mm: as_text(item.get(mm.group(1), "-")), item_block)
                item_block = item_block.replace("{{this}}", as_text(item))
            else:
                item_block = item_block.replace("{{this}}", as_text(item))
            rendered_items.append(item_block)
        text = text[:m.start()] + "".join(rendered_items) + text[m.end():]

    text = var_pattern.sub(lambda m: as_text(context.get(m.group(1), "-")), text)
    text = re.sub(r"{{[^{}]+}}", "-", text)
    return text


def render_markdown_from_template(stock_data: Dict, result: Dict) -> str:
    template_path = Path(__file__).resolve().parents[1] / "templates" / "analysis_report.md"
    if not template_path.exists():
        raise FileNotFoundError(f"模板不存在: {template_path}")
    template = template_path.read_text(encoding="utf-8")
    context = build_report_context(stock_data, result)
    return _render_template_content(template, context)


def main():
    def render_markdown(result: Dict) -> str:
        def _fmt_num(val, ndigits: int = 2, suffix: str = "") -> str:
            if val is None or val == "":
                return "-"
            try:
                return f"{float(val):.{ndigits}f}{suffix}"
            except Exception:
                return str(val)

        title = result.get("summary_title") or f"{result.get('name','')}({result.get('code','')})：综合分析"
        lines = [f"# {result.get('name','')}（{result.get('code','')}）财务分析报告", "", f"**总结标题**: {title}", ""]
        lines.append(f"- 分析时间: {result.get('analysis_date','')}")
        lines.append(f"- 分析级别: {result.get('level','')}")
        lines.append(f"- 综合评分: {result.get('score','')}")
        if result.get("realtime_score") is not None:
            lines.append(f"- 财务分: {result.get('fundamental_score','')}")
            lines.append(f"- 实时分: {result.get('realtime_score','')}")
        lines.append("")

        if isinstance(result.get("profitability"), dict):
            lines.append("## 盈利能力")
            lines.append(result["profitability"].get("assessment", ""))
            lines.append("")

        if isinstance(result.get("solvency"), dict):
            lines.append("## 偿债能力")
            lines.append(result["solvency"].get("assessment", ""))
            lines.append("")

        if isinstance(result.get("growth"), dict):
            lines.append("## 成长性")
            lines.append(result["growth"].get("assessment", ""))
            lines.append("")

        rt = result.get("realtime_metrics", {})
        if isinstance(rt, dict) and rt:
            trend = rt.get("trend", {}) if isinstance(rt.get("trend"), dict) else {}
            confirm = rt.get("confirm", {}) if isinstance(rt.get("confirm"), dict) else {}
            risk = rt.get("risk", {}) if isinstance(rt.get("risk"), dict) else {}
            chip = rt.get("chip", {}) if isinstance(rt.get("chip"), dict) else {}
            momentum = trend.get("momentum_pct", {}) if isinstance(trend.get("momentum_pct"), dict) else {}
            rel = trend.get("relative_strength_pct", {}) if isinstance(trend.get("relative_strength_pct"), dict) else {}

            lines.append("## 实时指标看板")
            lines.append(f"- 基准指数: {rt.get('benchmark', '-')}")
            lines.append(f"- 计算窗口: {rt.get('window_days', '-')}日")
            if rt.get("benchmark_error"):
                lines.append(f"- 基准数据异常: {rt.get('benchmark_error')}")
            lines.append("")
            lines.append("| 维度 | 指标 | 数值 |")
            lines.append("|------|------|------|")
            lines.append(f"| 趋势 | 趋势分 | {_fmt_num(trend.get('trend_score'))} |")
            lines.append(f"| 趋势 | 1/5/20/60日收益(%) | {_fmt_num(momentum.get('return_1d'))} / {_fmt_num(momentum.get('return_5d'))} / {_fmt_num(momentum.get('return_20d'))} / {_fmt_num(momentum.get('return_60d'))} |")
            lines.append(f"| 趋势 | 相对基准1/5/20/60(%) | {_fmt_num(rel.get('vs_benchmark_1d'))} / {_fmt_num(rel.get('vs_benchmark_5d'))} / {_fmt_num(rel.get('vs_benchmark_20d'))} / {_fmt_num(rel.get('vs_benchmark_60d'))} |")
            lines.append(f"| 确认 | 确认分 | {_fmt_num(confirm.get('confirm_score'))} |")
            lines.append(f"| 确认 | 成交额比20日均值 | {_fmt_num(confirm.get('amount_ratio_20d'), 4)} |")
            lines.append(f"| 确认 | 量比/换手率 | {_fmt_num(confirm.get('volume_ratio'), 4)} / {_fmt_num(confirm.get('turnover_rate'), 4)} |")
            lines.append(f"| 确认 | 资金净流入占比/近5日净流入天数 | {_fmt_num(confirm.get('net_inflow_ratio'), 4, '%')} / {_fmt_num(confirm.get('positive_days_5'), 0)} |")
            lines.append(f"| 风险 | 风险扣分 | {_fmt_num(risk.get('risk_penalty'))} |")
            lines.append(f"| 风险 | 振幅/实现波动/下行波动(%) | {_fmt_num(risk.get('intraday_amplitude_pct'))} / {_fmt_num(risk.get('realized_volatility_20d_pct'))} / {_fmt_num(risk.get('downside_volatility_20d_pct'))} |")
            lines.append(f"| 风险 | 窗口最大回撤(%) | {_fmt_num(risk.get('max_drawdown_window_pct'))} |")
            lines.append(f"| 筹码 | 筹码扣分 | {_fmt_num(chip.get('chip_penalty'))} |")
            lines.append(f"| 筹码 | 解禁30/90天占比(%) | {_fmt_num(chip.get('unlock_30d_ratio'))} / {_fmt_num(chip.get('unlock_90d_ratio'))} |")
            lines.append(f"| 筹码 | 减持密度/回购占比 | {_fmt_num(chip.get('reduction_density_30d'), 4)} / {_fmt_num(chip.get('repurchase_ratio_90d'))} |")
            lines.append("")
        elif result.get("realtime_score") is None:
            lines.append("## 实时指标看板")
            lines.append("- 未启用实时指标（可使用 data_fetcher 的 --with-realtime）。")
            lines.append("")

        ew = result.get("event_window", {})
        if isinstance(ew, dict) and ew:
            summary = ew.get("summary", {}) if isinstance(ew.get("summary"), dict) else {}
            lines.append("## 事件窗口分析")
            lines.append(f"- 事件窗口分: {_fmt_num(result.get('event_window_score'), 0)}")
            lines.append(f"- 事件总数/匹配数: {ew.get('event_count', 0)} / {ew.get('matched_event_count', 0)}")
            lines.append(f"- 窗口设置: 前{ew.get('pre_days', '-')}日, 后{','.join(str(x) for x in (ew.get('post_days') or []))}日")
            lines.append("")
            lines.append("| 指标 | 数值 |")
            lines.append("|------|------|")
            lines.append(f"| 平均后1/3/5日收益(%) | {_fmt_num(summary.get('avg_post_1d_pct'))} / {_fmt_num(summary.get('avg_post_3d_pct'))} / {_fmt_num(summary.get('avg_post_5d_pct'))} |")
            lines.append(f"| 平均后1/3/5日超额收益(%) | {_fmt_num(summary.get('avg_abnormal_1d_pct'))} / {_fmt_num(summary.get('avg_abnormal_3d_pct'))} / {_fmt_num(summary.get('avg_abnormal_5d_pct'))} |")
            pr = summary.get("positive_ratio_3d")
            pr_text = _fmt_num(pr * 100 if pr is not None else None)
            lines.append(f"| 后3日上涨占比(%) | {pr_text} |")
            lines.append(f"| 最差后5日收益(%) | {_fmt_num(summary.get('worst_post_5d_pct'))} |")
            lines.append("")
            lines.append(f"- 结论: {_build_event_window_conclusion(ew)}")
            lines.append("")
        elif result.get("event_window_score") is None:
            lines.append("## 事件窗口分析")
            lines.append("- 未启用事件窗口分析（可使用 data_fetcher 的 --with-event-window）。")
            lines.append("")

        perf = result.get("performance", {})
        if isinstance(perf, dict):
            lines.append("## 业绩与审计信号")
            lines.append(f"- 综合评估: {perf.get('assessment', '中性')}")
            for signal in perf.get("signals", []):
                lines.append(f"- {signal}")
            lines.append("")

        news = result.get("news_sentiment", {})
        if isinstance(news, dict):
            lines.append("## 新闻与舆情")
            lines.append(f"- 新闻条数: {news.get('news_count', 0)}")
            lines.append(f"- 综合情绪分: {news.get('overall_sentiment', 0)}")
            lines.append(f"- 风险等级: {news.get('risk_level', '低')}")
            if news.get("error"):
                lines.append(f"- 抓取异常: {news.get('error')}")
            lines.append("")

        anomalies = result.get("anomalies", {})
        if isinstance(anomalies, dict):
            lines.append("## 风险提示")
            lines.append(f"- 风险等级: {anomalies.get('risk_level', '低')}")
            for s in anomalies.get("signals", []):
                lines.append(f"- {s.get('type','')}: {s.get('description','')}")
            lines.append("")

        return "\n".join(lines)

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

    parser = argparse.ArgumentParser(description="A股财务分析器")
    parser.add_argument("--input", type=str, required=True, help="输入数据文件 (JSON)")
    parser.add_argument("--level", type=str, default="standard",
                       choices=["summary", "standard", "deep"],
                       help="分析深度级别")
    parser.add_argument("--mode", type=str, default="single",
                       choices=["single", "comparison"],
                       help="分析模式: single(单只)/comparison(对比)")
    parser.add_argument("--format", choices=["json", "table"], default="json", help="输出格式")
    parser.add_argument("--quiet", action="store_true", help="静默模式")
    parser.add_argument("--output", type=str, help="输出文件路径 (JSON)")
    parser.add_argument("--report-md", type=str, help="输出Markdown报告路径（默认同目录 analysis_report.md）")

    args = parser.parse_args()

    # 加载数据
    with open(args.input, 'r', encoding='utf-8') as f:
        data = json.load(f)

    analyzer = FinancialAnalyzer()

    if args.mode == "single":
        ensure_stock_data(data, required_sections=["financial_indicators"])
        analyzer.stock_data = data
        result = analyzer.generate_summary(level=args.level)
    else:
        # 对比模式
        stocks = data.get('stocks', [data])
        for stock in stocks:
            ensure_stock_data(stock, required_sections=["financial_indicators"])
        result = analyzer.compare_stocks(stocks)

    # 输出
    output_json = json.dumps(result, ensure_ascii=False, indent=2, default=str)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output_json)
        if not args.quiet:
            print(f"分析结果已保存到: {args.output}")
    else:
        if args.format == "table":
            if args.mode == "comparison":
                rows = [[x.get("code", ""), x.get("name", ""), x.get("score", ""), x.get("risk_level", "")] for x in result.get("stocks", [])]
                print(format_table(["代码", "名称", "评分", "风险等级"], rows))
            else:
                rows = [[
                    result.get("code", ""),
                    result.get("name", ""),
                    result.get("score", ""),
                    result.get("profitability", {}).get("assessment", "") if isinstance(result.get("profitability"), dict) else result.get("profitability", ""),
                    result.get("risk_level", result.get("anomalies", {}).get("risk_level", "")),
                ]]
                print(format_table(["代码", "名称", "评分", "盈利评估", "风险等级"], rows))
        else:
            print(output_json)

    # 单股模式必须产出Markdown报告
    if args.mode == "single":
        if args.report_md:
            report_md_path = args.report_md
        elif args.output:
            report_md_path = os.path.join(os.path.dirname(args.output) or ".", "analysis_report.md")
        else:
            report_md_path = "analysis_report.md"
        try:
            md_content = render_markdown_from_template(data, result)
        except Exception:
            md_content = render_markdown(result)
        with open(report_md_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        if not args.quiet:
            print(f"Markdown报告已保存到: {report_md_path}")


if __name__ == "__main__":
    main()
