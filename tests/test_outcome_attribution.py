from ops.outcome_attribution import (
    TradeOutcomeInput,
    build_outcome_attribution_report,
    export_outcome_attribution_report,
)


def test_outcome_win_by_model_edge():
    report = build_outcome_attribution_report(
        TradeOutcomeInput(
            trade_id="unit_win",
            side="BUY",
            predicted_probability=0.72,
            expected_value_usd=0.5,
            realized_pnl_usd=1.2,
            fees_usd=0.1,
            expected_slippage_pct=0.0005,
            realized_slippage_pct=0.0004,
            latency_ms=100,
            regime="TRENDING_UP",
        )
    )

    assert report.category == "WIN_BY_MODEL_EDGE"
    assert report.is_win is True


def test_outcome_detects_slippage_high():
    report = build_outcome_attribution_report(
        TradeOutcomeInput(
            trade_id="unit_slippage",
            side="BUY",
            predicted_probability=0.72,
            expected_value_usd=0.5,
            realized_pnl_usd=-1,
            expected_slippage_pct=0.0005,
            realized_slippage_pct=0.005,
            latency_ms=100,
            regime="TRENDING_UP",
        )
    )

    assert report.category == "SLIPPAGE_HIGH"


def test_export_outcome_attribution_report(tmp_path):
    report = build_outcome_attribution_report(
        TradeOutcomeInput(
            trade_id="unit_export",
            side="BUY",
            predicted_probability=0.5,
            expected_value_usd=0.1,
            realized_pnl_usd=-0.5,
        )
    )

    path = export_outcome_attribution_report(
        report,
        output_dir=tmp_path,
        name="unit_outcome",
    )

    assert path.exists()