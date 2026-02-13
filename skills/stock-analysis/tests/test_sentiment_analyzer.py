from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from sentiment_analyzer import analyze_news_sentiment


def test_sentiment_analyzer_detects_risk_tags_and_scores():
    items = [
        {
            "title": "公司被监管调查并收到处罚",
            "summary": "存在诉讼风险",
            "source": "测试源",
            "published_at": "2026-02-12T10:00:00+08:00",
            "url": "https://example.com/a",
            "query": "600519",
        },
        {
            "title": "公司中标并回购股份，业绩增长",
            "summary": "多重利好",
            "source": "测试源",
            "published_at": "2026-02-12T12:00:00+08:00",
            "url": "https://example.com/b",
            "query": "600519",
        },
    ]

    result = analyze_news_sentiment(items)
    assert result["news_count"] == 2
    assert "监管" in result["risk_tag_count"]
    assert isinstance(result["overall_sentiment"], float)
