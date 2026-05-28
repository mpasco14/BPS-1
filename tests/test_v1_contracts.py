from v1_acceptance.v1_contracts import (
    V1OperatingModesContract,
    build_default_v1_contract_bundle,
    evaluate_v1_contracts,
)


def test_v1_default_contracts_pass():
    report = evaluate_v1_contracts(
        contracts=build_default_v1_contract_bundle()
    )

    assert report.passed is True
    assert report.status == "PASS"


def test_v1_contracts_block_active_active_execution():
    bundle = build_default_v1_contract_bundle()
    modes = V1OperatingModesContract.model_validate(bundle.operating_modes)
    modes.active_active_execution_allowed = True
    bundle.operating_modes = modes.model_dump(mode="json")

    report = evaluate_v1_contracts(contracts=bundle)

    assert report.passed is False
    assert "active_active_execution_forbidden_in_v1" in report.blockers