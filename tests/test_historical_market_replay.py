from scenario_testing.historical_market_replay import run_historical_market_replay
from scenario_testing.scenario_models import generate_demo_candles


def test_historical_market_replay_runs_uptrend():
    report = run_historical_market_replay(
        candles=generate_demo_candles(pattern="uptrend", count=8),
        scenario_name="unit_replay_uptrend",
    )

    assert report.passed is True
    assert report.steps_count == 7
    assert report.approved_signals_count > 0


def test_historical_market_replay_blocks_not_enough_candles():
    report = run_historical_market_replay(
        candles=generate_demo_candles(pattern="uptrend", count=1),
        scenario_name="unit_replay_short",
    )

    assert report.passed is False
    assert "not_enough_candles_for_replay" in report.blockers