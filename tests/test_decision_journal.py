from ops.decision_journal import (
    DecisionEvidence,
    append_decision_journal_entry,
    build_decision_journal_entry,
    load_decision_journal,
)


def test_decision_journal_enters_when_all_checks_pass():
    entry = build_decision_journal_entry(
        decision_id="unit_1",
        symbol="BTCUSDT",
        side="BUY",
        evidence=DecisionEvidence(
            expected_value_usd=0.5,
            data_quality_passed=True,
            risk_approved=True,
            execution_allowed=True,
        ),
    )

    assert entry.final_decision == "ENTER"
    assert "ALL_CHECKS_PASSED" in entry.reason_codes


def test_decision_journal_blocks_on_risk():
    entry = build_decision_journal_entry(
        decision_id="unit_2",
        symbol="BTCUSDT",
        side="BUY",
        evidence=DecisionEvidence(
            expected_value_usd=0.5,
            risk_approved=False,
            risk_blockers=["daily_loss_limit_reached"],
        ),
    )

    assert entry.final_decision == "BLOCK"
    assert "RISK_REJECTED" in entry.reason_codes


def test_append_and_load_decision_journal(tmp_path):
    entry = build_decision_journal_entry(
        decision_id="unit_3",
        symbol="BTCUSDT",
        side="BUY",
        evidence=DecisionEvidence(expected_value_usd=0.5),
    )

    path = append_decision_journal_entry(
        entry,
        path=tmp_path / "journal.jsonl",
    )

    loaded = load_decision_journal(path)

    assert path.exists()
    assert len(loaded) == 1
    assert loaded[0].decision_id == "unit_3"