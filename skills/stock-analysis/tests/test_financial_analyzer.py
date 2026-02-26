import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from financial_analyzer import FinancialAnalyzer


def load_fixture():
    return json.loads((Path(__file__).parent / "fixtures" / "sample_stock_data.json").read_text(encoding="utf-8"))


def test_generate_summary_has_score_and_sections():
    analyzer = FinancialAnalyzer(load_fixture())
    result = analyzer.generate_summary(level="standard")

    assert 0 <= result["score"] <= 100
    assert result["realtime_score"] is not None
    assert result["event_window_score"] is not None
    assert result["score_weights"]["realtime"] == 0.6
    assert result["score_weights"]["fundamental"] == 0.4
    assert "realtime_metrics" in result
    assert "event_window" in result
    assert "profitability" in result
    assert "anomalies" in result
    assert "performance" in result
    assert result["code"] == "600519"


def test_generate_summary_fallback_to_fundamental_when_no_realtime():
    data = load_fixture()
    data.pop("realtime_metrics", None)
    analyzer = FinancialAnalyzer(data)
    result = analyzer.generate_summary(level="standard")

    assert result["realtime_score"] is None
    assert result["event_window_score"] is not None
    assert result["score_weights"]["realtime"] == 0.0
