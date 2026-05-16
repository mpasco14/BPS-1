import pytest

from risk.risk_manager import assess_signal_risk
from tests.test_risk_manager import custom_profile, sample_signal

from execution.paper_executor import (
    PaperExecutor,
    apply_entry_slippage,
    apply_exit_slippage,
)


def approved_assessment(direction="LONG"):
    if direction == "LONG":
        signal = sample_signal(combined_score=0.9, microstructure_score=0.4)
    else:
        signal = sample_signal(
            combined_score=-0.9,
            tech_score=-0.8,
            microstructure_score=-0.4,
            onchain_score=-0.05,
            sentiment_score=-0.03,
        )

    return assess_signal_risk(
        signal=signal,
        entry_price=60000,
        profile=custom_profile(),
    )


def test_apply_entry_slippage_long():
    assert apply_entry_slippage(
        direction="LONG",
        entry_price=60000,
        slippage_pct=0.001,
    ) == pytest.approx(60060)


def test_apply_entry_slippage_short():
    assert apply_entry_slippage(
        direction="SHORT",
        entry_price=60000,
        slippage_pct=0.001,
    ) == pytest.approx(59940)


def test_apply_exit_slippage_long():
    assert apply_exit_slippage(
        side="LONG",
        exit_price=60210,
        slippage_pct=0.001,
    ) == pytest.approx(60149.79)


def test_execute_approved_long_assessment():
    executor = PaperExecutor(slippage_pct=0.0, entry_fee_usd=0.05, exit_fee_usd=0.05)

    result = executor.execute(approved_assessment("LONG"))

    assert result.decision == "FILLED"
    assert result.position is not None
    assert executor.position_book.open_count() == 1


def test_rejects_blocked_assessment():
    signal = sample_signal(combined_score=0.1)
    assessment = assess_signal_risk(
        signal=signal,
        entry_price=60000,
        profile=custom_profile(),
    )

    executor = PaperExecutor(slippage_pct=0.0)

    result = executor.execute(assessment)

    assert result.decision == "REJECTED"
    assert executor.position_book.open_count() == 0


def test_update_position_hits_take_profit():
    executor = PaperExecutor(slippage_pct=0.0, entry_fee_usd=0.05, exit_fee_usd=0.05)

    result = executor.execute(approved_assessment("LONG"))
    position_id = result.position["position_id"]

    closed = executor.update_position_with_price(
        position_id=position_id,
        price=60210,
    )

    assert closed is not None
    assert closed.status == "CLOSED"
    assert closed.close_reason == "take_profit"
    assert round(closed.realized_pnl_usd, 2) == 2.00


def test_update_position_hits_stop_loss():
    executor = PaperExecutor(slippage_pct=0.0, entry_fee_usd=0.05, exit_fee_usd=0.05)

    result = executor.execute(approved_assessment("LONG"))
    position_id = result.position["position_id"]

    closed = executor.update_position_with_price(
        position_id=position_id,
        price=59895,
    )

    assert closed is not None
    assert closed.status == "CLOSED"
    assert closed.close_reason == "stop_loss"
    assert round(closed.realized_pnl_usd, 2) == -1.15


def test_manual_close_position():
    executor = PaperExecutor(slippage_pct=0.0, entry_fee_usd=0.05, exit_fee_usd=0.05)

    result = executor.execute(approved_assessment("LONG"))
    position_id = result.position["position_id"]

    closed = executor.close_position(
        position_id=position_id,
        exit_price=60100,
        reason="manual",
    )

    assert closed.status == "CLOSED"
    assert closed.close_reason == "manual"