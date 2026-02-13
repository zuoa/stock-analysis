import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from valuation_calculator import ValuationCalculator


def load_fixture():
    return json.loads((Path(__file__).parent / "fixtures" / "sample_stock_data.json").read_text(encoding="utf-8"))


def test_relative_valuation_uses_pe_ttm_latest():
    data = load_fixture()
    data["basic_info"]["pe_ttm"] = None
    calc = ValuationCalculator(data)
    result = calc.relative_valuation()

    assert result["current_valuation"]["PE_TTM"] == 24.0


def test_ddm_returns_value_with_dividend_history():
    calc = ValuationCalculator(load_fixture())
    result = calc.ddm_valuation(required_return=10)
    assert result.get("per_share_value") is not None
