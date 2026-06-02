from pathlib import Path

from micro_live.phase33 import (
    MicroLiveConfig,
    run_dry_run_signal,
    run_readonly_check,
    run_small_order,
)


def test_dry_run_blocks_notional_above_limit(tmp_path):
    phase32 = tmp_path / "phase32.json"
    readonly = tmp_path / "readonly.json"

    phase32.write_text('{"passed": true, "decision": "GO"}', encoding="utf-8")
    readonly.write_text('{"passed": true, "final_flat": true, "open_orders_count": 0}', encoding="utf-8")

    report = run_dry_run_signal(
        MicroLiveConfig(
            phase32_report_path=phase32,
            readonly_report_path=readonly,
            quantity=1,
            price=60000,
            max_order_notional_usd=10,
        )
    )

    assert report.passed is False
    assert "notional_above_micro_live_limit" in report.blockers


def test_small_order_blocks_without_unlocks(tmp_path):
    phase32 = tmp_path / "phase32.json"
    readonly = tmp_path / "readonly.json"
    dry_run = tmp_path / "dry_run.json"

    phase32.write_text('{"passed": true, "decision": "GO"}', encoding="utf-8")
    readonly.write_text('{"passed": true, "final_flat": true, "open_orders_count": 0}', encoding="utf-8")
    dry_run.write_text('{"passed": true}', encoding="utf-8")

    report = run_small_order(
        MicroLiveConfig(
            api_key="k",
            api_secret="s",
            rest_base_url="https://fapi.binance.com",
            phase32_report_path=phase32,
            readonly_report_path=readonly,
            dry_run_report_path=dry_run,
            allow_real_order_submission=False,
            allow_real_cancel=False,
            confirmation_phrase="",
        )
    )

    assert report.passed is False
    assert "micro_live_real_order_submission_not_allowed" in report.blockers
    assert "micro_live_real_cancel_not_allowed" in report.blockers
    assert "micro_live_confirmation_phrase_required" in report.blockers


def test_readonly_blocks_missing_credentials(tmp_path):
    phase32 = tmp_path / "phase32.json"
    phase32.write_text('{"passed": true, "decision": "GO"}', encoding="utf-8")

    report = run_readonly_check(
        MicroLiveConfig(
            api_key="",
            api_secret="",
            phase32_report_path=phase32,
        )
    )

    assert report.passed is False
    assert "live_api_key_required" in report.blockers
    assert "live_api_secret_required" in report.blockers