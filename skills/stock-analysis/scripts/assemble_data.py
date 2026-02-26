#!/usr/bin/env python3
"""
分模块数据聚合器：
- 读取各模块 JSON 文件
- 合并为 financial_analyzer 可用的 stock_data.json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional


SECTION_KEYS = [
    "basic_info",
    "financial_data",
    "financial_indicators",
    "performance_data",
    "valuation",
    "price",
    "flow_metrics",
    "chip_events",
    "realtime_metrics",
    "event_window",
    "holder",
    "dividend",
    "news_items",
    "news_sentiment",
]


def _load_json(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_code(payload: Dict) -> str:
    code = payload.get("code")
    if code:
        return str(code)
    basic = payload.get("basic_info")
    if isinstance(basic, dict) and basic.get("code"):
        return str(basic.get("code"))
    return ""


def _merge_one(target: Dict, payload: Dict, section_name: str, strict_code: bool = True) -> None:
    src_code = _extract_code(payload)
    if src_code:
        if target.get("code") and target.get("code") != src_code and strict_code:
            raise ValueError(f"代码不一致: target={target.get('code')} section({section_name})={src_code}")
        target["code"] = target.get("code") or src_code

    for key in SECTION_KEYS:
        if key in payload and payload[key] is not None:
            target[key] = payload[key]

    sections = target.setdefault("_sections", {})
    sections[section_name] = {
        "fetch_time": payload.get("fetch_time"),
        "source_file": section_name,
    }


def assemble_stock_data(
    code: str = "",
    basic_file: Optional[Path] = None,
    financial_file: Optional[Path] = None,
    valuation_file: Optional[Path] = None,
    price_file: Optional[Path] = None,
    holder_file: Optional[Path] = None,
    news_file: Optional[Path] = None,
    realtime_file: Optional[Path] = None,
    event_window_file: Optional[Path] = None,
    strict_code: bool = True,
) -> Dict:
    result: Dict = {
        "code": str(code or ""),
        "fetch_time": datetime.now().isoformat(),
        "data_type": "assembled",
        "basic_info": {},
    }

    file_map = {
        "basic": basic_file,
        "financial": financial_file,
        "valuation": valuation_file,
        "price": price_file,
        "holder": holder_file,
        "news": news_file,
        "realtime": realtime_file,
        "event_window": event_window_file,
    }

    for section_name, section_path in file_map.items():
        if section_path is None:
            continue
        path = Path(section_path)
        if not path.exists():
            continue
        payload = _load_json(path)
        if not isinstance(payload, dict):
            raise ValueError(f"文件内容不是 object: {path}")
        _merge_one(result, payload, section_name=section_name, strict_code=strict_code)
        result.setdefault("_section_files", {})[section_name] = str(path)

    if not result.get("code"):
        raise ValueError("聚合后缺少 code，请至少提供一个包含 code 的 section 文件或 --code")

    if not isinstance(result.get("basic_info"), dict):
        result["basic_info"] = {}
    if not result["basic_info"].get("code"):
        result["basic_info"]["code"] = result["code"]

    return result


def assemble_from_dir(input_dir: str, code: str = "", strict_code: bool = True) -> Dict:
    root = Path(input_dir)
    return assemble_stock_data(
        code=code,
        basic_file=(root / "basic.json"),
        financial_file=(root / "financial.json"),
        valuation_file=(root / "valuation.json"),
        price_file=(root / "price.json"),
        holder_file=(root / "holder.json"),
        news_file=(root / "news.json"),
        realtime_file=(root / "realtime.json"),
        event_window_file=(root / "event_window.json"),
        strict_code=strict_code,
    )


def _resolve_default_file(input_dir: Optional[str], filename: str) -> Optional[Path]:
    if not input_dir:
        return None
    path = Path(input_dir) / filename
    return path if path.exists() else None


def main():
    parser = argparse.ArgumentParser(description="聚合分模块股票数据为 stock_data.json")
    parser.add_argument("--code", default="", help="股票代码（可选，缺失时从 section 文件推断）")
    parser.add_argument("--input-dir", default="", help="模块文件目录（默认文件名: basic.json 等）")
    parser.add_argument("--basic-file", default="", help="basic 文件路径")
    parser.add_argument("--financial-file", default="", help="financial 文件路径")
    parser.add_argument("--valuation-file", default="", help="valuation 文件路径")
    parser.add_argument("--price-file", default="", help="price 文件路径")
    parser.add_argument("--holder-file", default="", help="holder 文件路径")
    parser.add_argument("--news-file", default="", help="news 文件路径")
    parser.add_argument("--realtime-file", default="", help="realtime 文件路径")
    parser.add_argument("--event-window-file", default="", help="event_window 文件路径")
    parser.add_argument("--no-strict-code", action="store_true", help="关闭代码一致性校验")
    parser.add_argument("--output", required=True, help="输出 stock_data.json 路径")
    parser.add_argument("--quiet", action="store_true", help="静默模式")
    args = parser.parse_args()

    basic_file = Path(args.basic_file) if args.basic_file else _resolve_default_file(args.input_dir, "basic.json")
    financial_file = Path(args.financial_file) if args.financial_file else _resolve_default_file(args.input_dir, "financial.json")
    valuation_file = Path(args.valuation_file) if args.valuation_file else _resolve_default_file(args.input_dir, "valuation.json")
    price_file = Path(args.price_file) if args.price_file else _resolve_default_file(args.input_dir, "price.json")
    holder_file = Path(args.holder_file) if args.holder_file else _resolve_default_file(args.input_dir, "holder.json")
    news_file = Path(args.news_file) if args.news_file else _resolve_default_file(args.input_dir, "news.json")
    realtime_file = Path(args.realtime_file) if args.realtime_file else _resolve_default_file(args.input_dir, "realtime.json")
    event_window_file = (
        Path(args.event_window_file)
        if args.event_window_file
        else _resolve_default_file(args.input_dir, "event_window.json")
    )

    if args.input_dir and not any([args.basic_file, args.financial_file, args.valuation_file, args.price_file, args.holder_file, args.news_file, args.realtime_file, args.event_window_file]):
        result = assemble_from_dir(
            input_dir=args.input_dir,
            code=args.code,
            strict_code=not args.no_strict_code,
        )
    else:
        result = assemble_stock_data(
            code=args.code,
            basic_file=basic_file,
            financial_file=financial_file,
            valuation_file=valuation_file,
            price_file=price_file,
            holder_file=holder_file,
            news_file=news_file,
            realtime_file=realtime_file,
            event_window_file=event_window_file,
            strict_code=not args.no_strict_code,
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    if not args.quiet:
        print(f"聚合完成: {output_path}")
        print(f"code={result.get('code')} sections={list((result.get('_section_files') or {}).keys())}")


if __name__ == "__main__":
    main()
