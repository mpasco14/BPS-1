from data.learning_feedback_dataset import (
    build_learning_feedback_row,
    export_learning_feedback_jsonl,
    load_learning_feedback_jsonl,
)
from ops.decision_journal import DecisionEvidence, build_decision_journal_entry
from ops.outcome_attribution import TradeOutcomeInput, build_outcome_attribution_report


def test_build_learning_feedback_row_with_outcome():
    decision = build_decision_journal_entry(
        decision_id="unit_decision",
        symbol="BTCUSDT",
        side="BUY",
        evidence=DecisionEvidence(
            model_probability=0.7,
            expected_value_usd=0.5,
            timeframe="5m",
        ),
    )
    outcome = build_outcome_attribution_report(
        TradeOutcomeInput(
            trade_id="unit_trade",
            side="BUY",
            predicted_probability=0.7,
            expected_value_usd=0.5,
            realized_pnl_usd=1.0,
        )
    )

    row = build_learning_feedback_row(decision=decision, outcome=outcome)

    assert row.decision_id == "unit_decision"
    assert row.trade_id == "unit_trade"
    assert row.target == 1


def test_export_and_load_learning_feedback_jsonl(tmp_path):
    decision = build_decision_journal_entry(
        decision_id="unit_decision_2",
        symbol="BTCUSDT",
        side="BUY",
        evidence=DecisionEvidence(expected_value_usd=0.5),
    )
    row = build_learning_feedback_row(decision=decision)

    path = export_learning_feedback_jsonl([row], path=tmp_path / "feedback.jsonl")
    loaded = load_learning_feedback_jsonl(path)

    assert path.exists()
    assert len(loaded) == 1
    assert loaded[0].decision_id == "unit_decision_2"