from data.learning_feedback_dataset import LearningFeedbackRow
from strategy.regime_optimization import (
    RegimeOptimizationConfig,
    build_regime_optimization_report,
    export_regime_optimization_report,
)


def make_rows(regime: str, wins: int, losses: int, win_pnl: float = 1.0, loss_pnl: float = -1.0):
    rows = []

    for index in range(wins):
        rows.append(
            LearningFeedbackRow(
                decision_id=f"{regime}_win_{index}",
                final_decision="ENTER",
                regime=regime,
                target=1,
                realized_net_pnl_usd=win_pnl,
            )
        )

    for index in range(losses):
        rows.append(
            LearningFeedbackRow(
                decision_id=f"{regime}_loss_{index}",
                final_decision="ENTER",
                regime=regime,
                target=0,
                realized_net_pnl_usd=loss_pnl,
            )
        )

    return rows


def test_regime_optimization_allows_good_regime():
    rows = make_rows("TRENDING_UP", wins=8, losses=2)

    report = build_regime_optimization_report(
        rows=rows,
        config=RegimeOptimizationConfig(min_samples=10),
    )

    assert report.recommendations[0]["action"] == "ALLOW"


def test_regime_optimization_blocks_bad_regime():
    rows = make_rows("NEWS_SHOCK", wins=2, losses=8, win_pnl=0.2, loss_pnl=-1.0)

    report = build_regime_optimization_report(
        rows=rows,
        config=RegimeOptimizationConfig(min_samples=10),
    )

    assert report.passed is False
    assert "NEWS_SHOCK" in report.blocked_regimes


def test_export_regime_optimization_report(tmp_path):
    rows = make_rows("TRENDING_UP", wins=8, losses=2)
    report = build_regime_optimization_report(rows=rows)

    path = export_regime_optimization_report(
        report,
        output_dir=tmp_path,
        name="unit_regime",
    )

    assert path.exists()