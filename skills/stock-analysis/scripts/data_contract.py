#!/usr/bin/env python3
"""
统一数据契约定义与校验工具。
"""

from typing import Dict, List, Optional, Tuple


REQUIRED_TOP_LEVEL_KEYS = [
    "code",
    "fetch_time",
    "data_type",
    "basic_info",
]

OPTIONAL_SECTIONS = [
    "financial_data",
    "performance_data",
    "financial_indicators",
    "valuation",
    "price",
    "holder",
    "dividend",
    "news_items",
    "news_sentiment",
]


def validate_stock_data(data: Dict, required_sections: Optional[List[str]] = None) -> Tuple[bool, List[str]]:
    """校验股票数据结构是否满足分析脚本要求。"""
    errors: List[str] = []

    if not isinstance(data, dict):
        return False, ["输入数据不是 JSON object"]

    for key in REQUIRED_TOP_LEVEL_KEYS:
        if key not in data:
            errors.append(f"缺少顶层字段: {key}")

    if "basic_info" in data and not isinstance(data.get("basic_info"), dict):
        errors.append("字段 basic_info 必须是 object")

    if "financial_data" in data:
        financial_data = data.get("financial_data")
        if not isinstance(financial_data, dict):
            errors.append("字段 financial_data 必须是 object")
        else:
            for key in ["balance_sheet", "income_statement", "cash_flow"]:
                if key in financial_data and not isinstance(financial_data.get(key), list):
                    errors.append(f"字段 financial_data.{key} 必须是 array")

    for key in ["financial_indicators", "news_items", "holder", "dividend", "valuation", "price", "news_sentiment", "performance_data"]:
        if key in data and data[key] is not None:
            expected_type = list if key in ["financial_indicators", "news_items"] else dict
            if not isinstance(data[key], expected_type):
                type_name = "array" if expected_type is list else "object"
                errors.append(f"字段 {key} 必须是 {type_name}")

    if "performance_data" in data and isinstance(data.get("performance_data"), dict):
        perf = data["performance_data"]
        for key in ["forecast", "express", "audit"]:
            if key in perf and not isinstance(perf.get(key), list):
                errors.append(f"字段 performance_data.{key} 必须是 array")

    if required_sections:
        for section in required_sections:
            if section not in data:
                errors.append(f"缺少分析所需字段: {section}")

    return len(errors) == 0, errors


def ensure_stock_data(data: Dict, required_sections: Optional[List[str]] = None) -> None:
    """校验失败时抛出 ValueError。"""
    ok, errors = validate_stock_data(data, required_sections=required_sections)
    if not ok:
        raise ValueError("数据结构校验失败: " + "; ".join(errors))
