from argparse import Namespace

from scripts.run_pre_live_check import maybe_override_inputs


def test_maybe_override_inputs_none():
    args = Namespace(
        paper_days=None,
        testnet_days=None,
        paper_trades=None,
        testnet_trades=None,
        paper_fill_rate=None,
        testnet_fill_rate=None,
        legal_review_approved=False,
        testnet_completed=False,
    )

    assert maybe_override_inputs(args) is None


def test_maybe_override_inputs_with_values():
    args = Namespace(
        paper_days=14,
        testnet_days=7,
        paper_trades=50,
        testnet_trades=10,
        paper_fill_rate=0.7,
        testnet_fill_rate=0.6,
        legal_review_approved=True,
        testnet_completed=True,
    )

    inputs = maybe_override_inputs(args)

    assert inputs is not None
    assert inputs.paper_days_completed == 14
    assert inputs.legal_review_approved is True