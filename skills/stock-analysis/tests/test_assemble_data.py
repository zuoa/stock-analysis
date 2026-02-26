import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from assemble_data import assemble_stock_data, assemble_from_dir


def _write(path: Path, payload: dict):
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_assemble_stock_data_merges_sections(tmp_path: Path):
    basic = tmp_path / "basic.json"
    financial = tmp_path / "financial.json"
    news = tmp_path / "news.json"

    _write(
        basic,
        {
            "code": "600519",
            "fetch_time": "2026-02-26T10:00:00",
            "basic_info": {"code": "600519", "name": "贵州茅台"},
        },
    )
    _write(
        financial,
        {
            "code": "600519",
            "fetch_time": "2026-02-26T10:01:00",
            "financial_indicators": [{"日期": "20251231", "净资产收益率": 24.0}],
        },
    )
    _write(
        news,
        {
            "code": "600519",
            "fetch_time": "2026-02-26T10:02:00",
            "news_items": [{"title": "测试新闻"}],
            "news_sentiment": {"risk_level": "低"},
        },
    )

    result = assemble_stock_data(
        basic_file=basic,
        financial_file=financial,
        news_file=news,
    )

    assert result["code"] == "600519"
    assert result["basic_info"]["name"] == "贵州茅台"
    assert len(result["financial_indicators"]) == 1
    assert result["news_sentiment"]["risk_level"] == "低"
    assert "basic" in result["_sections"]
    assert "financial" in result["_sections"]
    assert "news" in result["_sections"]


def test_assemble_stock_data_strict_code_mismatch(tmp_path: Path):
    basic = tmp_path / "basic.json"
    valuation = tmp_path / "valuation.json"
    _write(basic, {"code": "600519", "basic_info": {"code": "600519"}})
    _write(valuation, {"code": "000001", "valuation": {"pe_percentile": 50}})

    try:
        assemble_stock_data(basic_file=basic, valuation_file=valuation, strict_code=True)
    except ValueError as exc:
        assert "代码不一致" in str(exc)
        return
    assert False, "strict_code=True 时应校验代码一致性"


def test_assemble_from_dir_default_filenames(tmp_path: Path):
    (tmp_path / "basic.json").write_text(
        json.dumps({"code": "600519", "basic_info": {"code": "600519", "name": "贵州茅台"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (tmp_path / "valuation.json").write_text(
        json.dumps({"code": "600519", "valuation": {"pe_percentile": 40}}, ensure_ascii=False),
        encoding="utf-8",
    )
    result = assemble_from_dir(str(tmp_path))
    assert result["code"] == "600519"
    assert result["basic_info"]["name"] == "贵州茅台"
    assert result["valuation"]["pe_percentile"] == 40
