import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from data_contract import validate_stock_data


def load_fixture():
    return json.loads((Path(__file__).parent / "fixtures" / "sample_stock_data.json").read_text(encoding="utf-8"))


def test_validate_stock_data_success():
    ok, errors = validate_stock_data(load_fixture(), required_sections=["financial_data", "price", "valuation"])
    assert ok
    assert errors == []


def test_validate_stock_data_missing_key():
    data = load_fixture()
    data.pop("basic_info")
    ok, errors = validate_stock_data(data)
    assert not ok
    assert any("basic_info" in err for err in errors)
