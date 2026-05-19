from argparse import Namespace

from scripts.run_testnet_warmup import maybe_build_inputs_from_args


def test_maybe_build_inputs_none():
    args = Namespace(
        days=None,
        trades=None,
        fill_rate=None,
        slippage_error_pct=None,
        critical_alerts=None,
        warning_alerts=None,
        ops_passed=False,
        runbook_passed=False,
    )

    assert maybe_build_inputs_from_args(args) is None


def test_maybe_build_inputs_with_values():
    args = Namespace(
        days=14,
        trades=50,
        fill_rate=0.75,
        slippage_error_pct=0.0005,
        critical_alerts=0,
        warning_alerts=1,
        ops_passed=True,
        runbook_passed=True,
    )

    inputs = maybe_build_inputs_from_args(args)

    assert inputs is not None
    assert inputs.days_completed == 14
    assert inputs.ops_check_passed is True