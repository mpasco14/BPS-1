import json

from dashboard.data_loader import (
    find_latest_file,
    load_json_file,
    load_jsonl_file,
    load_latest_paper_trading_report,
)


def test_find_latest_file(tmp_path):
    old_file = tmp_path / "old_summary.json"
    new_file = tmp_path / "new_summary.json"

    old_file.write_text("{}", encoding="utf-8")
    new_file.write_text("{}", encoding="utf-8")

    latest = find_latest_file(tmp_path, "*_summary.json")

    assert latest is not None
    assert latest.name in {"old_summary.json", "new_summary.json"}


def test_load_json_file(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({"a": 1}), encoding="utf-8")

    payload = load_json_file(path)

    assert payload == {"a": 1}


def test_load_jsonl_file(tmp_path):
    path = tmp_path / "trades.jsonl"
    path.write_text('{"a":1}\n{"a":2}\n', encoding="utf-8")

    rows = load_jsonl_file(path)

    assert len(rows) == 2


def test_load_latest_paper_trading_report(tmp_path):
    path = tmp_path / "session_summary.json"
    path.write_text(json.dumps({"metrics": {"net_pnl_usd": 1}}), encoding="utf-8")

    payload, source = load_latest_paper_trading_report(tmp_path)

    assert payload["metrics"]["net_pnl_usd"] == 1
    assert source == path