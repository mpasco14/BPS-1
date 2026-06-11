from spot_micro_live.phase33b import (
    SpotMicroLiveConfig,
    run_spot_credential_permission_check,
    run_spot_dry_run_execution_contract,
    run_spot_small_limit_order,
    run_venue_availability_check,
)


def test_venue_availability_requires_spot():
    report = run_venue_availability_check(SpotMicroLiveConfig(venue="binance_futures"))

    assert report.passed is False
    assert "binance_spot_must_be_selected_for_brazil_live" in report.blockers


def test_spot_credential_blocks_withdrawal_permission():
    report = run_spot_credential_permission_check(
        SpotMicroLiveConfig(
            api_key="k",
            api_secret="s",
            spot_reading_enabled_declared=True,
            spot_withdrawals_enabled_declared=True,
        )
    )

    assert report.passed is False
    assert "spot_withdrawals_permission_must_be_disabled_for_trading_bot" in report.blockers


def test_spot_dry_run_blocks_notional_above_limit(tmp_path):
    phase32 = tmp_path / "phase32.json"
    readonly = tmp_path / "readonly.json"
    filters = tmp_path / "filters.json"

    phase32.write_text('{"passed": true, "decision": "GO"}', encoding="utf-8")
    readonly.write_text('{"passed": true, "open_orders_count": 0}', encoding="utf-8")
    filters.write_text('{"passed": true}', encoding="utf-8")

    report = run_spot_dry_run_execution_contract(
        SpotMicroLiveConfig(
            phase32_report_path=phase32,
            readonly_report_path=readonly,
            filter_report_path=filters,
            require_filter_validation_passed=True,
            quantity=1,
            price=60000,
            min_order_quote_amount=10,
            max_order_quote_amount=20,
        )
    )

    assert report.passed is False
    assert "notional_above_max_brl_limit" in report.blockers

def test_spot_small_order_blocks_without_unlocks(tmp_path):
    phase32 = tmp_path / "phase32.json"
    readonly = tmp_path / "readonly.json"
    dry_run = tmp_path / "dry_run.json"

    phase32.write_text('{"passed": true, "decision": "GO"}', encoding="utf-8")
    readonly.write_text('{"passed": true}', encoding="utf-8")
    dry_run.write_text('{"passed": true}', encoding="utf-8")

    report = run_spot_small_limit_order(
        SpotMicroLiveConfig(
            api_key="k",
            api_secret="s",
            phase32_report_path=phase32,
            readonly_report_path=readonly,
            dry_run_report_path=dry_run,
            allow_real_order_submission=False,
            allow_real_cancel=False,
            confirmation_phrase="",
        )
    )

    assert report.passed is False
    assert "spot_real_order_submission_not_allowed" in report.blockers
    assert "spot_real_cancel_not_allowed" in report.blockers
    assert "spot_micro_live_confirmation_phrase_required" in report.blockers
