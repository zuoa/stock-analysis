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
    assert "profitability" in result
    assert "anomalies" in result
    assert "performance" in result
    assert result["code"] == "600519"
