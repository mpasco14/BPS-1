from argparse import Namespace

from scripts.run_deployment_readiness import maybe_build_inputs_from_args


def test_maybe_build_inputs_none():
    args = Namespace(
        security_passed=False,
        compliance_passed=False,
        runbook_passed=False,
        testnet_warmup_passed=False,
        legal_review_approved=False,
        emergency_safe_mode_active=False,
    )

    assert maybe_build_inputs_from_args(args) is None


def test_maybe_build_inputs_with_values():
    args = Namespace(
        security_passed=True,
        compliance_passed=True,
        runbook_passed=True,
        testnet_warmup_passed=True,
        legal_review_approved=True,
        emergency_safe_mode_active=False,
    )

    inputs = maybe_build_inputs_from_args(args)

    assert inputs is not None
    assert inputs.security_passed is True
    assert inputs.compliance_blocking_fail_count == 0