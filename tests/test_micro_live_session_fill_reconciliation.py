from micro_live_session.fill_reconciliation_review import review_micro_live_fill_reconciliation
from micro_live_session.small_order_gate import MicroLiveSmallOrderReport


def test_fill_reconciliation_dry_run_flat_passes():
    order = MicroLiveSmallOrderReport(
        status="DRY_RUN",
        passed=True,
        submitted=False,
        dry_run=True,
        symbol="BTCUSDT",
        side="BUY",
        quantity=0.001,
        price=6000,
        notional_usd=6,
        order_plan={},
        config={},
    )

    report = review_micro_live_fill_reconciliation(
        small_order=order,
        submitted=False,
        local_position_qty=0,
        exchange_position_qty=0,
    )

    assert report.passed is True
    assert report.final_flat is True


def test_fill_reconciliation_blocks_position_mismatch():
    order = MicroLiveSmallOrderReport(
        status="DRY_RUN",
        passed=True,
        submitted=False,
        dry_run=True,
        symbol="BTCUSDT",
        side="BUY",
        quantity=0.001,
        price=6000,
        notional_usd=6,
        order_plan={},
        config={},
    )

    report = review_micro_live_fill_reconciliation(
        small_order=order,
        submitted=True,
        local_position_qty=0.001,
        exchange_position_qty=0,
    )

    assert report.passed is False
    assert "local_exchange_position_mismatch" in report.blockers