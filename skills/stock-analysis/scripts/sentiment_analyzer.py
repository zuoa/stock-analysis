#!/usr/bin/env python3
"""
新闻舆情分析模块（MVP）
- 词典规则法进行情绪与风险标签识别
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from typing import Dict, List


POSITIVE_WORDS = [
    "增长", "创新高", "突破", "上调", "增持", "回购", "中标", "利好", "超预期", "改善",
]

NEGATIVE_WORDS = [
    "下滑", "亏损", "暴跌", "诉讼", "减持", "处罚", "调查", "违约", "停产", "利空", "风险",
]

RISK_PATTERNS = {
    "监管": ["处罚", "调查", "问询", "立案", "监管"],
    "诉讼": ["诉讼", "仲裁", "索赔"],
    "经营": ["亏损", "下滑", "违约", "停产", "裁员"],
    "股东行为": ["减持", "质押", "冻结"],
}


def _score_text(text: str) -> float:
    if not text:
        return 0.0

    pos = sum(1 for w in POSITIVE_WORDS if w in text)
    neg = sum(1 for w in NEGATIVE_WORDS if w in text)
    raw = pos - neg

    if raw == 0:
        return 0.0

    # 压缩到 [-1, 1]
    return max(-1.0, min(1.0, raw / 5.0))


def _extract_risk_tags(text: str) -> List[str]:
    tags = []
    for tag, patterns in RISK_PATTERNS.items():
        if any(p in text for p in patterns):
            tags.append(tag)
    return tags


def analyze_news_sentiment(news_items: List[Dict]) -> Dict:
    scored_items = []
    all_scores: List[float] = []
    tag_count: Dict[str, int] = {}

    for item in news_items or []:
        title = item.get("title", "")
        summary = item.get("summary", "")
        text = f"{title} {summary}".strip()

        sentiment = _score_text(text)
        tags = _extract_risk_tags(text)

        for tag in tags:
            tag_count[tag] = tag_count.get(tag, 0) + 1

        enriched = {
            **item,
            "sentiment": sentiment,
            "risk_tags": tags,
        }
        scored_items.append(enriched)
        all_scores.append(sentiment)

    overall = sum(all_scores) / len(all_scores) if all_scores else 0.0

    if overall <= -0.3:
        level = "高"
    elif overall <= -0.1:
        level = "中"
    else:
        level = "低"

    top_negative = sorted(
        [x for x in scored_items if x.get("sentiment", 0) < 0],
        key=lambda x: x.get("sentiment", 0),
    )[:5]

    return {
        "analysis_time": datetime.now().isoformat(),
        "news_count": len(scored_items),
        "overall_sentiment": round(overall, 4),
        "risk_level": level,
        "risk_tag_count": tag_count,
        "top_negative_events": top_negative,
        "news_items": scored_items,
    }


def main():
    parser = argparse.ArgumentParser(description="新闻舆情分析工具")
    parser.add_argument("--input", required=True, help="输入新闻 JSON 文件")
    parser.add_argument("--output", help="输出结果 JSON 文件")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    news_items = data.get("news_items", data if isinstance(data, list) else [])
    result = analyze_news_sentiment(news_items)

    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
    else:
        print(output)


if __name__ == "__main__":
    main()
